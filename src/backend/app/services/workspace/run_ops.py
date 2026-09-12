"""Workspace run/stop/status/polling operations mixin.

Extracted from workspace_service.py in iteration 174 to keep
the service file below the 800-line bar.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import case, func, or_, select, update

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.backtest import BacktestRequest, TaskStatus
from app.schemas.workspace import UnitStatusResponse
from app.services import workspace_unit_runtime
from app.services.ai_research_provenance import (
    AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD,
    verify_ai_research_paper_runtime_anchor_for_unit,
)
from app.services.fincore_metrics_helper import calculate_extended_metrics
from app.services.live_trading_manager import get_live_trading_manager
from app.services.workspace.config import (
    _normalize_workspace_type,
    _workspace_settings_dict,
)
from app.services.workspace.units import (
    AIStrategyResearchPaperRuntimeStopError,
    is_server_owned_ai_research_live_handoff_unit,
    is_server_owned_ai_research_paper_runtime,
    is_server_owned_ai_research_unit,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.backtest.service import BacktestService
    from app.services.trading_workspace_service import TradingWorkspaceService

logger = logging.getLogger(__name__)

_MARKET_DATA_BINDING_TRADING_UNSUPPORTED = "MARKET_DATA_BINDING_TRADING_UNSUPPORTED"
_AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID = "AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID"
_UNIT_RUN_LEASE_PREFIX = "lease-"
_UNIT_RUN_STATUS_MATERIALIZING = "materializing"
_UNIT_RUN_STATUS_CANCELLING = "cancelling"
_UNIT_RUN_ACTIVE_STATUSES = (
    "queued",
    _UNIT_RUN_STATUS_MATERIALIZING,
    "running",
    _UNIT_RUN_STATUS_CANCELLING,
)


def _is_unit_run_lease_token(task_id: object) -> bool:
    """Return whether ``last_task_id`` currently holds a pending-run lease."""
    return isinstance(task_id, str) and task_id.startswith(_UNIT_RUN_LEASE_PREFIX)


def _new_unit_run_lease_token() -> str:
    """Create a persisted token that fits the legacy 36-character task-id column."""
    # ``last_task_id`` is nullable and has no FK.  While a unit is queued it
    # also carries this opaque lease, which gives all later state transitions a
    # durable compare-and-swap value without a schema migration.
    return f"{_UNIT_RUN_LEASE_PREFIX}{uuid.uuid4().hex[:30]}"


def _public_unit_run_status(run_status: object, task_id: object) -> str:
    """Map internal runtime-fence states to the established public status values."""
    status = str(run_status or "idle").strip().lower()
    if status in {_UNIT_RUN_STATUS_MATERIALIZING, _UNIT_RUN_STATUS_CANCELLING}:
        return "queued" if _is_unit_run_lease_token(task_id) else "running"
    return status or "idle"


def _requires_research_market_data_binding(unit: StrategyUnit) -> bool:
    """Return whether a unit is restricted to the research backtest bridge."""
    data_config = getattr(unit, "data_config", None)
    return workspace_unit_runtime._market_data_binding_required(
        data_config if isinstance(data_config, dict) else None
    )


def _has_valid_ai_research_paper_runtime_anchor(
    unit: StrategyUnit,
    *,
    user_id: str,
    workspace_id: str,
    workspace_settings: dict[str, Any] | None = None,
) -> bool:
    """Allow an AI paper runtime only when its identity remains server-attested."""
    if str(getattr(unit, "trading_mode", "") or "").strip().casefold() != "paper":
        return True
    if not is_server_owned_ai_research_paper_runtime(unit):
        return True
    settings = getattr(unit, "unit_settings", None)
    anchor = (
        settings.get(AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD) if isinstance(settings, dict) else None
    )
    return verify_ai_research_paper_runtime_anchor_for_unit(
        anchor,
        user_id=user_id,
        paper_workspace_id=workspace_id,
        paper_unit_id=str(unit.id),
        unit=unit,
        workspace_settings=workspace_settings,
        # A workspace launch replaces the isolated directory before the
        # manager starts it. The post-sync path compares the new files to the
        # signed expected digest and then installs a snapshot digest.
        require_runtime_snapshot=False,
    )


async def _initialize_paper_runtime_snapshots(
    user_id: str,
    runtime_snapshots: list[tuple[str, dict[str, Any], dict[str, Any]]],
) -> None:
    """Persist initial paper-runtime equity points without delaying a unit start response."""
    if not runtime_snapshots:
        return

    from app.services.paper_runtime_service import PaperRuntimeService

    runtime_service = PaperRuntimeService()
    for instance_id, metrics, unit_settings in runtime_snapshots:
        try:
            await runtime_service.record_snapshot(
                user_id,
                instance_id,
                {
                    "source": "initial",
                    "total_equity": float(
                        unit_settings.get("initial_cash") or metrics.get("initial_cash") or 100000.0
                    ),
                    "cash": float(unit_settings.get("initial_cash") or 100000.0),
                    "metadata": {"event": "runtime_started"},
                },
            )
        except Exception:
            logger.warning(
                "Unable to record initial paper runtime snapshot for %s",
                instance_id,
                exc_info=True,
            )


def _schedule_paper_runtime_snapshots(user_id: str, units: list[StrategyUnit]) -> None:
    """Schedule paper equity snapshots after trading instances have started."""
    from app.services.paper_runtime_scheduler import get_paper_runtime_snapshot_scheduler

    snapshot_scheduler = get_paper_runtime_snapshot_scheduler()
    runtime_snapshots: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for unit in units:
        instance_id = str(getattr(unit, "trading_instance_id", "") or "").strip()
        is_paper = str(getattr(unit, "trading_mode", "paper") or "paper").lower() == "paper"
        is_running = str(getattr(unit, "run_status", "") or "").lower() == "running"
        if not instance_id or not is_paper or not is_running:
            continue
        metrics = cast(dict[str, Any], getattr(unit, "metrics_snapshot", {}) or {})
        settings = cast(dict[str, Any], getattr(unit, "unit_settings", {}) or {})
        runtime_snapshots.append((instance_id, dict(metrics), dict(settings)))
        snapshot_scheduler.ensure_running(user_id, instance_id)
    if runtime_snapshots:
        asyncio.create_task(_initialize_paper_runtime_snapshots(user_id, runtime_snapshots))


def _task_runtime_info(task: BacktestTask | None) -> dict[str, Any]:
    if task is None:
        return {}
    request_data = task.request_data if isinstance(task.request_data, dict) else {}
    runtime = request_data.get("_runtime") if isinstance(request_data, dict) else {}
    return runtime if isinstance(runtime, dict) else {}


def _unit_run_progress(
    task: BacktestTask | None,
    run_status: str,
) -> tuple[float | None, str | None]:
    runtime = _task_runtime_info(task)
    raw_progress = runtime.get("progress")
    progress = float(raw_progress) if isinstance(raw_progress, (int, float)) else None
    message = runtime.get("message") if isinstance(runtime.get("message"), str) else None
    if progress is None:
        if run_status in {"queued", "idle"}:
            progress = 0.0
        elif run_status == "running":
            progress = 10.0
        elif run_status in {"completed", "failed", "cancelled"}:
            progress = 100.0
    if progress is not None:
        progress = max(0.0, min(progress, 100.0))
    return progress, message


class WorkspaceRunOpsMixin:
    """Mixin providing run/stop/status/polling methods for WorkspaceService."""

    if TYPE_CHECKING:
        # These attributes/methods are provided by the composing class
        # (``WorkspaceService``); declared here so mypy can type-check the mixin.
        trading_service: TradingWorkspaceService

        @staticmethod
        async def _load_workspace(
            session: AsyncSession,
            workspace_id: str,
            user_id: str,
            load_units: bool = True,
        ) -> Workspace | None: ...

        @staticmethod
        async def _get_unit(
            session: AsyncSession, workspace_id: str, unit_id: str
        ) -> StrategyUnit | None: ...

        @staticmethod
        def _build_backtest_request(unit: StrategyUnit) -> BacktestRequest: ...

        @staticmethod
        def _task_elapsed_seconds(task: BacktestTask | None) -> float | None: ...

        @staticmethod
        async def _resolve_unit_bar_count(
            backtest_service: BacktestService,
            task_id: str,
            user_id: str | None,
            bt_result: Any | None = None,
        ) -> int: ...

        @staticmethod
        def _optimization_progress_response_to_opt_info(
            progress: dict[str, Any] | None,
        ) -> dict[str, Any] | None: ...

    async def _claim_research_unit_run(
        self,
        workspace_id: str,
        unit_id: str,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Atomically reserve one research unit before creating its runtime.

        The lease lives in ``last_task_id`` only while the row is ``queued``.
        It is never returned as a task id and every later transition compares
        it, so a delayed request cannot update a newer run for the same unit.
        ``UPDATE ... WHERE`` provides the compare-and-swap semantics on
        SQLite, PostgreSQL, and MySQL without relying on an ORM identity map.
        """
        lease_token = _new_unit_run_lease_token()
        async with async_session_maker() as claim_session:
            claim_result = await claim_session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    or_(
                        StrategyUnit.run_status.is_(None),
                        StrategyUnit.run_status.notin_(_UNIT_RUN_ACTIVE_STATUSES),
                    ),
                )
                .values(
                    run_status="queued",
                    last_task_id=lease_token,
                )
            )
            if int(getattr(claim_result, "rowcount", 0) or 0) == 1:
                await claim_session.commit()
                return lease_token, None

            # A competing request owns the queued/running row.  Fetch a
            # fresh row solely for a stable response; it must not materialize
            # a runtime or invoke the backtest service.
            current_unit = await self._get_unit(claim_session, workspace_id, unit_id)
            if current_unit is None:
                return None, {
                    "unit_id": unit_id,
                    "task_id": None,
                    "status": "failed",
                    "error": "WORKSPACE_UNIT_NOT_FOUND",
                }

            current_status = _public_unit_run_status(
                getattr(current_unit, "run_status", ""),
                getattr(current_unit, "last_task_id", None),
            )
            current_task_id = getattr(current_unit, "last_task_id", None)
            return None, {
                "unit_id": unit_id,
                "task_id": None if _is_unit_run_lease_token(current_task_id) else current_task_id,
                "status": current_status if current_status in {"queued", "running"} else "queued",
                "already_running": True,
            }

    async def _unit_run_lease_is_active(
        self,
        session: AsyncSession,
        workspace_id: str,
        unit_id: str,
        lease_token: str,
        task_id: str | None = None,
    ) -> bool:
        """Check this request's queued lease or its CAS-promoted task identity."""
        ownership_conditions = [
            (StrategyUnit.run_status == "queued") & (StrategyUnit.last_task_id == lease_token)
        ]
        if task_id:
            ownership_conditions.append(
                StrategyUnit.run_status.in_(("running", _UNIT_RUN_STATUS_MATERIALIZING))
                & (StrategyUnit.last_task_id == task_id)
            )
        result = await session.execute(
            select(StrategyUnit.id).where(
                StrategyUnit.id == unit_id,
                StrategyUnit.workspace_id == workspace_id,
                or_(*ownership_conditions),
            )
        )
        return result.scalar_one_or_none() is not None

    async def _begin_research_runtime_materialization(
        self,
        workspace_id: str,
        unit_id: str,
        lease_token: str,
        task_id: str | None,
    ) -> bool:
        """Fence one deterministic runtime write behind the current claim.

        A stop cannot release a unit after this compare-and-swap while a
        writer is in ``sync_unit_runtime``.  It instead changes the row to
        ``cancelling`` and the writer releases it only after the synchronous
        write has returned.  This prevents a replacement lease from writing
        the same directory concurrently with the old request.
        """
        expected_status = "running" if task_id else "queued"
        expected_identity = task_id or lease_token
        async with async_session_maker() as session:
            result = await session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.run_status == expected_status,
                    StrategyUnit.last_task_id == expected_identity,
                )
                .values(run_status=_UNIT_RUN_STATUS_MATERIALIZING)
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def _complete_research_runtime_materialization(
        self,
        workspace_id: str,
        unit_id: str,
        lease_token: str,
        task_id: str | None,
    ) -> bool:
        """Release a write fence back to its active queued/running state."""
        active_status = "running" if task_id else "queued"
        identity = task_id or lease_token
        async with async_session_maker() as session:
            result = await session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.run_status == _UNIT_RUN_STATUS_MATERIALIZING,
                    StrategyUnit.last_task_id == identity,
                )
                .values(run_status=active_status)
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def _promote_research_unit_run_lease(
        self,
        workspace_id: str,
        unit_id: str,
        lease_token: str,
        task_id: str,
    ) -> bool:
        """Replace a pending lease with its task id if this request still owns it."""
        async with async_session_maker() as session:
            result = await session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.run_status == "queued",
                    StrategyUnit.last_task_id == lease_token,
                )
                .values(run_status="running", last_task_id=task_id)
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def _finish_research_unit_run_lease(
        self,
        workspace_id: str,
        unit_id: str,
        lease_token: str,
        *,
        status: str,
        increment_run_count: bool = False,
    ) -> bool:
        """Finish a no-task lease after its last runtime writer has exited."""
        values: dict[Any, Any] = {
            # A stop that raced a materialization owns the cancelled outcome.
            # Do not turn it into a generic submission failure while releasing
            # the same fenced token.
            "run_status": case(
                (StrategyUnit.run_status == _UNIT_RUN_STATUS_CANCELLING, "cancelled"),
                else_=status,
            ),
            "last_task_id": None,
        }
        if increment_run_count:
            values["run_count"] = func.coalesce(StrategyUnit.run_count, 0) + 1
        async with async_session_maker() as session:
            result = await session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.run_status.in_(
                        ("queued", _UNIT_RUN_STATUS_MATERIALIZING, _UNIT_RUN_STATUS_CANCELLING)
                    ),
                    StrategyUnit.last_task_id == lease_token,
                )
                .values(values)
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def _finish_research_unit_run_task(
        self,
        workspace_id: str,
        unit_id: str,
        task_id: str,
        *,
        status: str,
        increment_run_count: bool = False,
    ) -> bool:
        """Finish only the real task atomically promoted from this run's lease."""
        values: dict[Any, Any] = {
            "run_status": case(
                (StrategyUnit.run_status == _UNIT_RUN_STATUS_CANCELLING, "cancelled"),
                else_=status,
            )
        }
        if increment_run_count:
            values["run_count"] = func.coalesce(StrategyUnit.run_count, 0) + 1
        async with async_session_maker() as session:
            result = await session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.run_status.in_(
                        ("running", _UNIT_RUN_STATUS_MATERIALIZING, _UNIT_RUN_STATUS_CANCELLING)
                    ),
                    StrategyUnit.last_task_id == task_id,
                )
                .values(values)
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def _finalize_research_runtime_execution(
        self,
        workspace_id: str,
        unit_id: str,
        task_id: str,
        status: TaskStatus,
    ) -> None:
        """Release a promoted bound unit only after its execution coroutine exits."""
        await self._finish_research_unit_run_task(
            workspace_id,
            unit_id,
            task_id,
            status=str(status.value),
            increment_run_count=True,
        )

    async def _stop_bound_research_unit_run(
        self,
        backtest_service: BacktestService,
        workspace_id: str,
        user_id: str,
        unit_id: str,
    ) -> tuple[bool, bool]:
        """Stop one bound unit from a fresh DB snapshot without stale ORM writes.

        Returns ``(handled_as_bound_unit, cancelled)``.  A queued lease can be
        made terminal directly because a writer must first atomically change it
        to ``materializing``.  A materializing lease stays fenced as
        ``cancelling`` until its writer returns.  A real task is cancelled
        before its unit state is fenced, so an unavailable remote runner never
        releases a live subprocess.
        """
        async with async_session_maker() as session:
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not _requires_research_market_data_binding(unit):
                return False, False
            run_status = str(getattr(unit, "run_status", "") or "").strip().lower()
            task_or_lease = str(getattr(unit, "last_task_id", "") or "").strip()

        if not task_or_lease:
            return True, False

        if _is_unit_run_lease_token(task_or_lease):
            if run_status == "queued":
                # No writer can pass its queued->materializing CAS after this
                # transition, so it is safe to release this no-task lease.
                async with async_session_maker() as session:
                    result = await session.execute(
                        update(StrategyUnit)
                        .where(
                            StrategyUnit.id == unit_id,
                            StrategyUnit.workspace_id == workspace_id,
                            StrategyUnit.run_status == "queued",
                            StrategyUnit.last_task_id == task_or_lease,
                        )
                        .values(run_status="cancelled", last_task_id=None)
                    )
                    await session.commit()
                if int(getattr(result, "rowcount", 0) or 0) == 1:
                    return True, True
                # Promotion/materialization may have won after the fresh read.
                # Re-read recursively and act on the exact current identity.
                return await self._stop_bound_research_unit_run(
                    backtest_service, workspace_id, user_id, unit_id
                )

            if run_status == _UNIT_RUN_STATUS_MATERIALIZING:
                async with async_session_maker() as session:
                    result = await session.execute(
                        update(StrategyUnit)
                        .where(
                            StrategyUnit.id == unit_id,
                            StrategyUnit.workspace_id == workspace_id,
                            StrategyUnit.run_status == _UNIT_RUN_STATUS_MATERIALIZING,
                            StrategyUnit.last_task_id == task_or_lease,
                        )
                        .values(run_status=_UNIT_RUN_STATUS_CANCELLING)
                    )
                    await session.commit()
                if int(getattr(result, "rowcount", 0) or 0) == 1:
                    return True, True
                return await self._stop_bound_research_unit_run(
                    backtest_service, workspace_id, user_id, unit_id
                )

            if run_status == _UNIT_RUN_STATUS_CANCELLING:
                # The exact writer owns the final release after sync returns.
                return True, True
            return True, False

        if run_status not in {"queued", "running", _UNIT_RUN_STATUS_MATERIALIZING}:
            return True, run_status == _UNIT_RUN_STATUS_CANCELLING

        try:
            cancelled = await backtest_service.cancel_task(task_or_lease, user_id)
        except Exception:
            logger.warning(
                "Unable to cancel bound backtest %s for unit %s",
                task_or_lease,
                unit_id,
                exc_info=True,
            )
            return True, False
        if not cancelled:
            # A different API process may still own a running subprocess.  The
            # unit remains active and therefore non-claimable.
            return True, False

        async with async_session_maker() as session:
            result = await session.execute(
                update(StrategyUnit)
                .where(
                    StrategyUnit.id == unit_id,
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.last_task_id == task_or_lease,
                    StrategyUnit.run_status.in_(
                        ("queued", "running", _UNIT_RUN_STATUS_MATERIALIZING)
                    ),
                )
                .values(run_status=_UNIT_RUN_STATUS_CANCELLING)
            )
            await session.commit()
        # A local task may have completed and finalized between cancellation
        # and this fence update.  It is still safe to report the cancellation;
        # the exact terminal row remains unclaimable until this transaction.
        del result
        return True, True

    async def _start_trading_units_in_background(
        self,
        workspace_id: str,
        user_id: str,
        unit_ids: list[str],
    ) -> None:
        """Start a queued trading batch without holding the initiating request open."""
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return

            result = await session.execute(
                select(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                    StrategyUnit.run_status == "queued",
                )
            )
            units = list(result.scalars().all())
            if not units:
                return

            launchable_units: list[StrategyUnit] = []
            for unit in units:
                if not _has_valid_ai_research_paper_runtime_anchor(
                    unit,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    workspace_settings=_workspace_settings_dict(ws),
                ):
                    unit.run_status = "failed"
                    unit.trading_snapshot = self.trading_service.default_snapshot(
                        unit=unit,
                        instance_status="error",
                        error=_AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID,
                    )
                    await session.commit()
                    continue
                if _requires_research_market_data_binding(unit):
                    # A sealed historical research artifact is never a
                    # paper/live market-data authorization.  This guard also
                    # covers a stale queued row reached after a multi-unit
                    # request has returned.
                    unit.run_status = "failed"
                    unit.trading_snapshot = self.trading_service.default_snapshot(
                        unit=unit,
                        instance_status="error",
                        error=_MARKET_DATA_BINDING_TRADING_UNSUPPORTED,
                    )
                    await session.commit()
                    continue
                launchable_units.append(unit)
            units = launchable_units
            if not units:
                return

            # The first manager access loads broker plugins and restores
            # persisted runtime state.  Defer it until bound research units
            # have been rejected, then keep the synchronous setup off the
            # ASGI event loop before a permitted unit starts.
            await asyncio.to_thread(get_live_trading_manager)

            for unit in units:
                try:
                    # ``start_units`` ultimately prepares broker runtimes and
                    # can take seconds per unit. Start and commit one at a
                    # time so status polling and other API requests get a
                    # scheduling opportunity between units in a large batch.
                    await self.trading_service.start_units(
                        [unit],
                        user_id,
                        _workspace_settings_dict(ws),
                    )
                except Exception as exc:
                    logger.exception(
                        "Trading batch start failed for workspace %s unit %s",
                        workspace_id,
                        unit.id,
                    )
                    unit.run_status = "failed"
                    unit.trading_snapshot = self.trading_service.default_snapshot(
                        unit=unit,
                        instance_status="error",
                        error=str(exc),
                    )
                await session.commit()
                await asyncio.sleep(0)

        _schedule_paper_runtime_snapshots(user_id, units)

    async def run_units(
        self,
        workspace_id: str,
        user_id: str,
        unit_ids: list[str],
        parallel: bool = False,
        *,
        allow_server_owned_ai_research_live_handoff_start: bool = False,
        live_handoff_pre_start_validator: Callable[[], Awaitable[None]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run backtest for selected strategy units.

        Delegates to the existing BacktestService for each unit.
        Sequential by default; parallel if requested.

        Returns list of {unit_id, task_id, status} dicts.
        """
        results: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return []

            q = select(StrategyUnit).where(
                StrategyUnit.workspace_id == workspace_id,
                StrategyUnit.id.in_(unit_ids),
            )
            db_result = await session.execute(q)
            units = list(db_result.scalars().all())

            if not units:
                return []

            if not allow_server_owned_ai_research_live_handoff_start and any(
                is_server_owned_ai_research_live_handoff_unit(unit) for unit in units
            ):
                # A prepared live handoff is intentionally not an ordinary
                # workspace run target.  The research service owns its
                # one-shot activation capability and revalidates paper
                # evidence before it delegates here.
                raise ValueError("AI_RESEARCH_LIVE_HANDOFF_SERVER_ACTIVATION_REQUIRED")

            if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
                untrusted_paper_units = [
                    unit
                    for unit in units
                    if not _has_valid_ai_research_paper_runtime_anchor(
                        unit,
                        user_id=user_id,
                        workspace_id=workspace_id,
                        workspace_settings=_workspace_settings_dict(ws),
                    )
                ]
                if untrusted_paper_units:
                    untrusted_unit_ids = {id(unit) for unit in untrusted_paper_units}
                    for unit in untrusted_paper_units:
                        unit.run_status = "failed"
                        unit.trading_snapshot = self.trading_service.default_snapshot(
                            unit=unit,
                            instance_status="error",
                            error=_AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID,
                        )
                        results.append(
                            {
                                "unit_id": unit.id,
                                "task_id": None,
                                "status": "failed",
                                "error": _AI_RESEARCH_PAPER_RUNTIME_PROVENANCE_INVALID,
                            }
                        )
                    await session.commit()
                    if len(untrusted_paper_units) == len(units):
                        return results
                    units = [unit for unit in units if id(unit) not in untrusted_unit_ids]

                bound_units = [
                    unit for unit in units if _requires_research_market_data_binding(unit)
                ]
                if bound_units:
                    bound_unit_ids = {id(unit) for unit in bound_units}
                    for unit in bound_units:
                        # The research binding owns one immutable historical
                        # CSV, so it cannot be implicitly repurposed for
                        # paper or live data transport.
                        unit.run_status = "failed"
                        unit.trading_snapshot = self.trading_service.default_snapshot(
                            unit=unit,
                            instance_status="error",
                            error=_MARKET_DATA_BINDING_TRADING_UNSUPPORTED,
                        )
                        results.append(
                            {
                                "unit_id": unit.id,
                                "task_id": None,
                                "status": "failed",
                                "error": _MARKET_DATA_BINDING_TRADING_UNSUPPORTED,
                            }
                        )
                    await session.commit()
                    if len(bound_units) == len(units):
                        return results
                    units = [unit for unit in units if id(unit) not in bound_unit_ids]

                # A large trading workspace used to start every process inside
                # this request.  Launching dozens of units serially exceeded
                # the frontend timeout even though the starts were valid.
                # Preserve immediate start semantics for a single unit, while
                # committing multi-unit batches as queued work and returning
                # promptly for status polling.
                if len(units) > 1:
                    queued_unit_ids: list[str] = []
                    for unit in units:
                        current_status = str(unit.run_status or "idle").strip().lower()
                        if current_status in {"queued", "running"}:
                            results.append(
                                {
                                    "unit_id": unit.id,
                                    "task_id": unit.trading_instance_id,
                                    "status": current_status,
                                    "already_running": True,
                                }
                            )
                            continue
                        unit.run_status = "queued"
                        unit.trading_snapshot = self.trading_service.default_snapshot(
                            unit=unit,
                            instance_status="queued",
                        )
                        queued_unit_ids.append(str(unit.id))
                        results.append(
                            {
                                "unit_id": unit.id,
                                "task_id": unit.trading_instance_id,
                                "status": "queued",
                            }
                        )
                    await session.commit()
                    if queued_unit_ids:
                        asyncio.get_running_loop().call_soon(
                            asyncio.create_task,
                            self._start_trading_units_in_background(
                                workspace_id,
                                user_id,
                                queued_unit_ids,
                            ),
                        )
                    return results

                results = await self.trading_service.start_units(
                    units,
                    user_id,
                    _workspace_settings_dict(ws),
                    allow_server_owned_ai_research_live_handoff_start=(
                        allow_server_owned_ai_research_live_handoff_start
                    ),
                    live_handoff_pre_start_validator=live_handoff_pre_start_validator,
                )
                await session.commit()
                _schedule_paper_runtime_snapshots(user_id, units)
                return results

            from app.services.backtest.service import BacktestService

            backtest_service = BacktestService()

            # The lease protocol protects sealed research data only.  Keep
            # ordinary legacy units on their established queued/running path
            # while refusing to let an unleased stale snapshot become bound
            # halfway through a submission.
            legacy_units = [
                unit for unit in units if not _requires_research_market_data_binding(unit)
            ]
            if legacy_units:
                for legacy_unit in legacy_units:
                    legacy_unit.run_status = "queued"
                await session.commit()

            # Sealed units receive an independent DB compare-and-swap claim.
            # The outer ``units`` objects are display snapshots, not a
            # concurrency boundary: a second HTTP request may have loaded the
            # same unit before this request enters its preflight.
            async def _submit_single(unit: StrategyUnit) -> dict[str, Any]:
                binding_required = _requires_research_market_data_binding(unit)
                lease_token: str | None = None
                if binding_required:
                    lease_token, already_running = await self._claim_research_unit_run(
                        workspace_id,
                        str(unit.id),
                    )
                    if lease_token is None:
                        # The loser deliberately does no binding read, runtime
                        # write, or task submission.  It only reports the
                        # fresh state observed by the failed conditional update.
                        return cast(dict[str, Any], already_running)

                task_id: str | None = None
                try:
                    workspace_settings = _workspace_settings_dict(ws)

                    async def runtime_preflight() -> Path:
                        """Rebuild a current unit snapshot after binding checks.

                        BacktestService owns the private execution capability
                        and invokes this immediately before task creation and
                        again before its subprocess starts.  Keeping the
                        authorization replay here preserves WorkspaceService
                        as the only caller allowed to materialize a unit
                        runtime directory.
                        """
                        # A parallel batch cannot share the outer workspace
                        # session with concurrent binding queries.  Read the
                        # unit once in an independent session and use that
                        # same snapshot for both strict-binding resolution and
                        # runtime materialization.  The outer ``unit`` may
                        # otherwise retain an older, yet valid OOS window.
                        materialization_started = False
                        try:
                            if binding_required:
                                assert lease_token is not None
                                materialization_started = (
                                    await self._begin_research_runtime_materialization(
                                        workspace_id,
                                        str(unit.id),
                                        lease_token,
                                        task_id,
                                    )
                                )
                                if not materialization_started:
                                    raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                                        "WORKSPACE_UNIT_RUN_CLAIM_LOST"
                                    )

                            async with async_session_maker() as binding_session:
                                current_unit = await self._get_unit(
                                    binding_session,
                                    workspace_id,
                                    str(unit.id),
                                )
                                if current_unit is None:
                                    raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                                        "MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED"
                                    )

                                current_binding_required = _requires_research_market_data_binding(
                                    current_unit
                                )
                                if binding_required != current_binding_required:
                                    # A legacy caller cannot quietly acquire a
                                    # sealed historical transport after the unit
                                    # was loaded.  It must restart through the
                                    # bound lease path.
                                    raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                                        "MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED"
                                    )

                                market_data_binding = None
                                if current_binding_required:
                                    market_data_binding = await workspace_unit_runtime.resolve_required_market_data_binding(
                                        current_unit,
                                        user_id,
                                        db=binding_session,
                                    )
                                    if market_data_binding is None:
                                        raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                                            "MARKET_DATA_BINDING_RUNTIME_REVALIDATION_FAILED"
                                        )
                                runtime_dir = workspace_unit_runtime.sync_unit_runtime(
                                    current_unit,
                                    workspace_settings,
                                    market_data_binding=market_data_binding,
                                )

                            if binding_required:
                                assert lease_token is not None
                                if not await self._complete_research_runtime_materialization(
                                    workspace_id,
                                    str(unit.id),
                                    lease_token,
                                    task_id,
                                ):
                                    # A stop won while ``sync_unit_runtime``
                                    # was writing.  The cancelling state stays
                                    # non-claimable until this writer returns;
                                    # no later request can cross-write the
                                    # deterministic directory.
                                    raise workspace_unit_runtime.MarketDataBindingRuntimeError(
                                        "WORKSPACE_UNIT_RUN_CLAIM_LOST"
                                    )
                            return runtime_dir
                        except BaseException:
                            if binding_required and materialization_started:
                                assert lease_token is not None
                                if task_id is None:
                                    # No child task exists for this callback.
                                    # Release only after the synchronous writer
                                    # has returned; preserving ``cancelling``
                                    # as cancelled avoids a stale failure
                                    # reopening the row incorrectly.
                                    restored = (
                                        await self._complete_research_runtime_materialization(
                                            workspace_id,
                                            str(unit.id),
                                            lease_token,
                                            None,
                                        )
                                    )
                                    if not restored:
                                        await self._finish_research_unit_run_lease(
                                            workspace_id,
                                            str(unit.id),
                                            lease_token,
                                            status="failed",
                                        )
                            raise

                    async def claim_promoter(created_task_id: str) -> bool:
                        """Promote the queued lease before service scheduling starts."""
                        nonlocal task_id
                        if not binding_required:
                            return True
                        assert lease_token is not None
                        promoted = await self._promote_research_unit_run_lease(
                            workspace_id,
                            str(unit.id),
                            lease_token,
                            created_task_id,
                        )
                        if promoted:
                            task_id = created_task_id
                        return promoted

                    async def claim_finalizer(final_status: TaskStatus) -> None:
                        """Release the bound unit after its local execution has exited."""
                        if not binding_required or task_id is None:
                            return
                        await self._finalize_research_runtime_execution(
                            workspace_id,
                            str(unit.id),
                            task_id,
                            final_status,
                        )

                    bt_request = self._build_backtest_request(unit)
                    response = None
                    deadline = time.monotonic() + 1800
                    while response is None:
                        try:
                            response = await backtest_service.run_workspace_unit_backtest(
                                user_id,
                                bt_request,
                                workspace_id=workspace_id,
                                unit_id=str(unit.id),
                                runtime_preflight=runtime_preflight,
                                claim_promoter=claim_promoter if binding_required else None,
                                claim_finalizer=claim_finalizer if binding_required else None,
                            )
                        except ValueError as exc:
                            if "concurrent task limit" not in str(exc).lower():
                                raise
                            if binding_required:
                                # The next trusted preflight rematerializes
                                # the deterministic directory under the same
                                # fenced lease.  Do not delete it here: an
                                # unsynchronised delete can erase a newer
                                # claimant's runtime after this retry loses its
                                # ownership.
                                assert lease_token is not None
                            if time.monotonic() >= deadline:
                                raise TimeoutError(
                                    "Timed out waiting for an available backtest execution slot"
                                ) from exc
                            await asyncio.sleep(2)
                    response_task_id = str(response.task_id)
                    if binding_required:
                        # BacktestService invokes the promoter after task
                        # persistence and before scheduling.  A response that
                        # lacks this exact promotion is a server contract
                        # failure, never a reason to fall back to an outer
                        # stale update.
                        if task_id != response_task_id:
                            raise RuntimeError("WORKSPACE_UNIT_RUN_CLAIM_LOST")
                        # Keep the original token in the callback closure:
                        # BacktestService replays that callback after this
                        # method returns, where it accepts the exact
                        # CAS-promoted task id alongside the original lease.
                    else:
                        task_id = response_task_id
                        # Preserve the legacy unbound write-back behaviour.
                        async with async_session_maker() as s2:
                            u = await self._get_unit(s2, workspace_id, str(unit.id))
                            if u:
                                u_row: Any = u
                                u_row.last_task_id = task_id
                                u_row.run_status = "running"
                                await s2.commit()

                    return {"unit_id": unit.id, "task_id": task_id, "status": "running"}

                except asyncio.CancelledError:
                    if binding_required and task_id is not None:
                        cancelled = False
                        try:
                            cancelled = await backtest_service.cancel_task(task_id, user_id)
                        except Exception:
                            logger.warning(
                                "Unable to cancel bound backtest %s for unit %s",
                                task_id,
                                unit.id,
                                exc_info=True,
                            )
                        if cancelled:
                            await self._finish_research_unit_run_task(
                                workspace_id,
                                str(unit.id),
                                task_id,
                                status="cancelled",
                            )
                    elif binding_required and lease_token is not None:
                        await self._finish_research_unit_run_lease(
                            workspace_id,
                            str(unit.id),
                            lease_token,
                            status="cancelled",
                        )
                    raise

                except Exception as e:
                    logger.error("Unit %s submit failed: %s", unit.id, e)
                    if binding_required and task_id is not None:
                        await self._finish_research_unit_run_task(
                            workspace_id,
                            str(unit.id),
                            task_id,
                            status="failed",
                            increment_run_count=True,
                        )
                    elif binding_required and lease_token is not None:
                        await self._finish_research_unit_run_lease(
                            workspace_id,
                            str(unit.id),
                            lease_token,
                            status="failed",
                            increment_run_count=True,
                        )
                    elif not binding_required:
                        async with async_session_maker() as s_err:
                            u_err = await self._get_unit(s_err, workspace_id, str(unit.id))
                            if u_err:
                                u_err_row: Any = u_err
                                u_err_row.run_status = "failed"
                                u_err_row.run_count = (u_err.run_count or 0) + 1
                                await s_err.commit()
                    return {
                        "unit_id": unit.id,
                        "task_id": None,
                        "status": "failed",
                        "error": str(e),
                    }

            if parallel:
                results = list(await asyncio.gather(*[_submit_single(u) for u in units]))
            else:
                for unit in units:
                    results.append(await _submit_single(unit))

        # Fire-and-forget background polling for completion (Bug-1 fix)
        submitted = [(r["unit_id"], r["task_id"]) for r in results if r.get("task_id")]
        if submitted:
            asyncio.create_task(
                self._background_poll_units(workspace_id, user_id, submitted, backtest_service)
            )

        return results

    async def stop_units(
        self,
        workspace_id: str,
        user_id: str,
        unit_ids: list[str],
        *,
        allow_server_owned_ai_research_stop: bool = False,
        allow_server_owned_ai_research_live_handoff_stop: bool = False,
    ) -> list[dict[str, Any]]:
        """Stop running units by cancelling their associated backtest tasks."""
        results: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return []

            if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
                q = select(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                )
                db_result = await session.execute(q)
                units = list(db_result.scalars().all())
                if not (
                    allow_server_owned_ai_research_stop
                    or allow_server_owned_ai_research_live_handoff_stop
                ) and any(is_server_owned_ai_research_unit(unit) for unit in units):
                    raise AIStrategyResearchPaperRuntimeStopError()
                results = await self.trading_service.stop_units(
                    units,
                    user_id,
                    allow_server_owned_ai_research_stop=(allow_server_owned_ai_research_stop),
                    allow_server_owned_ai_research_live_handoff_stop=(
                        allow_server_owned_ai_research_live_handoff_stop
                    ),
                )
                await session.commit()
                from app.services.paper_runtime_scheduler import (
                    get_paper_runtime_snapshot_scheduler,
                )

                snapshot_scheduler = get_paper_runtime_snapshot_scheduler()
                for unit in units:
                    instance_id = str(getattr(unit, "trading_instance_id", "") or "").strip()
                    if instance_id:
                        await snapshot_scheduler.stop(instance_id)
                return results

            from app.services.backtest.service import BacktestService

            backtest_service = BacktestService()

            # Bound units use independent fresh sessions for every transition.
            # Never write an ORM object loaded before a concurrent promoter:
            # doing so can overwrite a promoted task id without cancelling it.
            legacy_unit_ids: list[str] = []
            for unit_id in unit_ids:
                handled, cancelled = await self._stop_bound_research_unit_run(
                    backtest_service,
                    workspace_id,
                    user_id,
                    str(unit_id),
                )
                if handled:
                    results.append({"unit_id": unit_id, "cancelled": cancelled})
                else:
                    legacy_unit_ids.append(str(unit_id))

            if legacy_unit_ids:
                q = select(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(legacy_unit_ids),
                    StrategyUnit.run_status.in_(["running", "queued"]),
                )
                db_result = await session.execute(q)
                units = list(db_result.scalars().all())

                for unit in units:
                    # A unit may have become bound after the fresh helper's
                    # first read.  Delegate once more instead of applying the
                    # legacy ORM write to a sealed data run.
                    if _requires_research_market_data_binding(unit):
                        handled, cancelled = await self._stop_bound_research_unit_run(
                            backtest_service,
                            workspace_id,
                            user_id,
                            str(unit.id),
                        )
                        if handled:
                            results.append({"unit_id": unit.id, "cancelled": cancelled})
                        continue

                    cancelled = False
                    if unit.last_task_id:
                        cancelled = await backtest_service.cancel_task(unit.last_task_id, user_id)
                        if cancelled:
                            unit.run_status = "cancelled"
                    elif str(unit.run_status or "").strip().lower() == "queued":
                        # Preserve the legacy no-task queued behavior outside
                        # the sealed-runtime protocol.
                        cancelled = True
                        unit.run_status = "cancelled"
                    results.append({"unit_id": unit.id, "cancelled": cancelled})

                await session.commit()

        return results

    async def get_units_status(
        self,
        workspace_id: str,
        user_id: str,
        unit_ids: list[str] | None = None,
    ) -> list[UnitStatusResponse] | None:
        """Get run status of all units (polling endpoint)."""
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            q = select(StrategyUnit).where(StrategyUnit.workspace_id == workspace_id)
            if unit_ids:
                q = q.where(StrategyUnit.id.in_(unit_ids))
            q = q.order_by(StrategyUnit.sort_order)
            result = await session.execute(q)
            units = list(result.scalars().all())

            if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
                # The status endpoint is polled frequently by the trading workspace UI.
                # Persisting every hydrated runtime snapshot here causes concurrent
                # polling requests to lock large batches of strategy_units rows.
                # Never make an external broker call from the high-frequency
                # polling endpoint.  A gateway outage should be surfaced by the
                # start/detail flows, not turn every workspace status request
                # into a blocked connection attempt.
                # A queued batch has not necessarily created every runtime
                # instance yet. Refreshing those rows makes polling compete
                # with startup for the instance store and can turn a fast
                # status request into a broker-start bottleneck. Persisted
                # queued state is authoritative until the worker promotes it
                # to running.
                running_units = [
                    unit
                    for unit in units
                    if str(unit.run_status or "").strip().lower() == "running"
                ]
                if running_units:
                    await self.trading_service.hydrate_units(
                        running_units,
                        user_id,
                        full_log=False,
                        refresh_gateway=False,
                    )
                return self.trading_service.build_status_responses(units)

            from app.services.backtest.service import BacktestService

            backtest_service = BacktestService()

            task_ids = [
                str(cast(Any, unit).last_task_id)
                for unit in units
                if cast(Any, unit).last_task_id
                and not _is_unit_run_lease_token(cast(Any, unit).last_task_id)
            ]
            task_by_id: dict[str, BacktestTask] = {}
            if task_ids:
                task_result = await session.execute(
                    select(BacktestTask).where(BacktestTask.id.in_(task_ids))
                )
                task_by_id = {str(task.id): task for task in task_result.scalars().all()}

            changed = False
            for unit in units:
                unit_obj = cast(Any, unit)
                metrics_snapshot = cast(dict[str, Any], unit_obj.metrics_snapshot or {})
                raw_last_task_id = str(unit_obj.last_task_id or "").strip()
                pending_lease = _is_unit_run_lease_token(raw_last_task_id)
                last_task_id = "" if pending_lease else raw_last_task_id
                internal_run_status = str(unit_obj.run_status or "").strip().lower()
                is_bound_unit = _requires_research_market_data_binding(unit_obj)
                run_status = _public_unit_run_status(internal_run_status, raw_last_task_id)
                bar_count = int(unit_obj.bar_count or 0)
                task = task_by_id.get(last_task_id) if last_task_id else None
                if task is not None and not is_bound_unit:
                    elapsed_seconds = self._task_elapsed_seconds(task)
                    if elapsed_seconds is not None and unit_obj.last_run_time != elapsed_seconds:
                        unit_obj.last_run_time = elapsed_seconds
                if internal_run_status in _UNIT_RUN_ACTIVE_STATUSES:
                    if pending_lease:
                        # A queued lease is an in-progress submission, not a
                        # missing task.  It remains authoritative until the
                        # owner either promotes its exact token or releases
                        # it with a terminal compare-and-swap update.
                        pass
                    elif not last_task_id:
                        unit_obj.run_status = "idle"
                        run_status = "idle"
                        changed = True
                    else:
                        task_status = await backtest_service.get_task_status(last_task_id, user_id)
                        if is_bound_unit:
                            # Bound runtime execution owns its terminal CAS in
                            # the same process that exits the child task.  A
                            # status observer is not allowed to commit an ORM
                            # snapshot after a newer lease has replaced this
                            # task id.  Terminal task state is only recovery
                            # evidence while the fenced owner finalizes.
                            if task_status is None:
                                logger.warning(
                                    "Backtest status is unavailable for unit %s task %s",
                                    unit_obj.id,
                                    last_task_id,
                                )
                        elif task_status == TaskStatus.COMPLETED:
                            unit_obj.run_status = "completed"
                            run_status = "completed"
                            changed = True
                        elif task_status == TaskStatus.CANCELLED:
                            unit_obj.run_status = "cancelled"
                            run_status = "cancelled"
                            changed = True
                        elif task_status == TaskStatus.FAILED:
                            unit_obj.run_status = "failed"
                            run_status = "failed"
                            changed = True
                        elif task_status is None:
                            # Preserve the historical legacy-unit behaviour
                            # outside the sealed-data protocol.
                            unit_obj.run_status = "failed"
                            run_status = "failed"
                            changed = True
                if (
                    not is_bound_unit
                    and run_status == "completed"
                    and last_task_id
                    and (bar_count == 0 or not metrics_snapshot.get("total_trades"))
                ):
                    bt_result = await backtest_service.get_result(last_task_id, user_id)
                    if bt_result and (bt_result.equity_curve or bt_result.trades):
                        log_data = {
                            "equity_curve": bt_result.equity_curve or [],
                            "equity_dates": bt_result.equity_dates or [],
                            "trades": [
                                t.model_dump() if hasattr(t, "model_dump") else t
                                for t in (bt_result.trades or [])
                            ],
                        }
                        try:
                            metrics = calculate_extended_metrics(log_data)
                            unit_obj.metrics_snapshot = metrics
                        except Exception:
                            unit_obj.metrics_snapshot = {
                                "total_return": bt_result.total_return,
                                "annual_return": bt_result.annual_return,
                                "sharpe_ratio": bt_result.sharpe_ratio,
                                "max_drawdown": bt_result.max_drawdown,
                                "win_rate": bt_result.win_rate,
                                "total_trades": bt_result.total_trades,
                                "profitable_trades": bt_result.profitable_trades,
                                "losing_trades": bt_result.losing_trades,
                                "initial_cash": 100000.0,
                                "final_value": (bt_result.equity_curve or [100000.0])[-1]
                                if (bt_result.equity_curve or [])
                                else 100000.0,
                            }
                        unit_obj.bar_count = await self._resolve_unit_bar_count(
                            backtest_service,
                            last_task_id,
                            user_id,
                            bt_result,
                        )
                        changed = True

            if changed:
                await session.commit()

            # Collect optimization progress for units with active tasks
            opt_progress_map: dict[str, dict[str, Any]] = {}
            opt_task_ids = {
                str(cast(Any, u).last_optimization_task_id)
                for u in units
                if cast(Any, u).last_optimization_task_id
            }
            if opt_task_ids:
                from app.services.param_optimization_service import get_optimization_progress

                for tid in opt_task_ids:
                    try:
                        progress = get_optimization_progress(tid, user_id=user_id, use_db=True)
                        opt_info = self._optimization_progress_response_to_opt_info(progress)
                        if opt_info:
                            opt_progress_map[tid] = opt_info
                    except Exception:
                        logger.debug(
                            "Failed to load optimization progress for task %s", tid, exc_info=True
                        )

            responses: list[UnitStatusResponse] = []
            for u in units:
                u_obj = cast(Any, u)
                opt_tid = (
                    str(u_obj.last_optimization_task_id)
                    if u_obj.last_optimization_task_id
                    else None
                )
                opt_info = opt_progress_map.get(opt_tid, {}) if opt_tid else {}
                raw_last_task_id = str(u_obj.last_task_id or "").strip()
                pending_lease = _is_unit_run_lease_token(raw_last_task_id)
                status_task = (
                    task_by_id.get(raw_last_task_id)
                    if raw_last_task_id and not pending_lease
                    else None
                )
                error_message = (
                    str(status_task.error_message)
                    if status_task and status_task.error_message
                    else None
                )
                public_run_status = _public_unit_run_status(
                    getattr(u_obj, "run_status", "idle"),
                    raw_last_task_id,
                )
                run_progress, run_message = _unit_run_progress(
                    status_task,
                    public_run_status,
                )
                responses.append(
                    UnitStatusResponse(
                        id=str(u_obj.id),
                        run_status=public_run_status,
                        last_task_id=raw_last_task_id
                        if raw_last_task_id and not pending_lease
                        else None,
                        error_message=error_message,
                        metrics_snapshot=cast(dict[str, Any], u_obj.metrics_snapshot or {}),
                        run_progress=run_progress,
                        run_message=run_message,
                        run_count=int(u_obj.run_count or 0),
                        last_run_time=(
                            float(u_obj.last_run_time) if u_obj.last_run_time is not None else None
                        ),
                        bar_count=(int(u_obj.bar_count) if u_obj.bar_count is not None else None),
                        trading_instance_id=(
                            str(u_obj.trading_instance_id)
                            if getattr(u_obj, "trading_instance_id", None)
                            else None
                        ),
                        trading_snapshot=cast(
                            dict[str, Any], getattr(u_obj, "trading_snapshot", {}) or {}
                        ),
                        trading_mode=self.trading_service.normalize_trading_mode(
                            getattr(u_obj, "trading_mode", "paper")
                        ),
                        lock_trading=bool(getattr(u_obj, "lock_trading", False)),
                        lock_running=bool(getattr(u_obj, "lock_running", False)),
                        opt_status=opt_info.get("opt_status"),
                        opt_total=opt_info.get("opt_total"),
                        opt_completed=opt_info.get("opt_completed"),
                        opt_progress=opt_info.get("opt_progress"),
                        opt_elapsed_time=opt_info.get("opt_elapsed_time"),
                        opt_remaining_time=opt_info.get("opt_remaining_time"),
                    )
                )
            return responses

    async def _background_poll_units(
        self,
        workspace_id: str,
        user_id: str,
        submitted: list[tuple[str, str]],
        backtest_service: BacktestService,  # noqa: F821
    ) -> None:
        """Background task: poll all submitted units **in parallel**, then update metrics."""
        await asyncio.gather(
            *(
                self._poll_single_unit(workspace_id, user_id, unit_id, task_id, backtest_service)
                for unit_id, task_id in submitted
            ),
            return_exceptions=True,
        )

    async def _poll_single_unit(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        task_id: str,
        backtest_service: BacktestService,  # noqa: F821
    ) -> None:
        """Poll a single unit's backtest task until completion, then update metrics."""
        start_ts = time.monotonic()
        try:
            final_status = await self._poll_task_completion(backtest_service, task_id, user_id)
            if final_status is None:
                # A local observer timeout says nothing about the persistent
                # task or subprocess.  Keep the exact task/lease active for a
                # later status poll instead of reopening the unit for a
                # concurrent replacement run.
                logger.warning("Backtest observer timed out for unit %s task %s", unit_id, task_id)
                return
            task = await backtest_service.task_manager.get_task(task_id, user_id=user_id)
            elapsed = self._task_elapsed_seconds(task)
            if elapsed is None:
                elapsed = round(time.monotonic() - start_ts, 2)

            final_run_status = "failed"
            result_values: dict[str, Any] = {
                "run_count": func.coalesce(StrategyUnit.run_count, 0) + 1,
                "last_run_time": elapsed,
            }
            if final_status == TaskStatus.COMPLETED:
                final_run_status = "completed"
                bt_result = await backtest_service.get_result(task_id, user_id)
                if bt_result:
                    log_data = {
                        "equity_curve": bt_result.equity_curve or [],
                        "equity_dates": bt_result.equity_dates or [],
                        "trades": [
                            t.model_dump() if hasattr(t, "model_dump") else t
                            for t in (bt_result.trades or [])
                        ],
                    }
                    try:
                        result_values["metrics_snapshot"] = calculate_extended_metrics(log_data)
                    except Exception as metric_error:
                        logger.warning(
                            "Extended metrics failed for unit %s: %s", unit_id, metric_error
                        )
                        result_values["metrics_snapshot"] = {
                            "total_return": bt_result.total_return,
                            "annual_return": bt_result.annual_return,
                            "sharpe_ratio": bt_result.sharpe_ratio,
                            "max_drawdown": bt_result.max_drawdown,
                            "win_rate": bt_result.win_rate,
                            "total_trades": bt_result.total_trades,
                        }
                    result_values["bar_count"] = await self._resolve_unit_bar_count(
                        backtest_service,
                        task_id,
                        user_id,
                        bt_result,
                    )
            elif final_status == TaskStatus.CANCELLED:
                final_run_status = "cancelled"

            async with async_session_maker() as s:
                current_unit = await self._get_unit(s, workspace_id, unit_id)
                if current_unit is not None and _requires_research_market_data_binding(
                    current_unit
                ):
                    # The scheduled service finalizer owns the exact
                    # task-id/state transition after its coroutine (and any
                    # subprocess) has actually exited.  A polling observer
                    # only sees persistent task status and must not reopen a
                    # bound runtime directory while local cleanup is pending.
                    return
                # A background observer may finish after a stop/retry has
                # replaced the task with a new queued lease.  Update only the
                # exact active task it observed; a stale timeout must not
                # overwrite the new task's status or metrics.
                await s.execute(
                    update(StrategyUnit)
                    .where(
                        StrategyUnit.id == unit_id,
                        StrategyUnit.workspace_id == workspace_id,
                        StrategyUnit.last_task_id == task_id,
                        StrategyUnit.run_status.in_(("queued", "running")),
                    )
                    .values(run_status=final_run_status, **result_values)
                )
                await s.commit()

        except Exception as e:
            logger.error("Background poll failed for unit %s: %s", unit_id, e)
            # Observation failures are not task-manager terminal evidence.
            # Leaving the exact running task authoritative is fail-closed: a
            # later poll can reconcile it, while a transient DB/network error
            # cannot release the unit for another runtime writer.

    @staticmethod
    async def _poll_task_completion(
        backtest_service: BacktestService,  # noqa: F821
        task_id: str,
        user_id: str,
        timeout: float = 600,
        interval: float = 2.0,
    ) -> TaskStatus | None:
        """Poll backtest task status until terminal state or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = await backtest_service.get_task_status(task_id, user_id)
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return status
            await asyncio.sleep(interval)
        return None
