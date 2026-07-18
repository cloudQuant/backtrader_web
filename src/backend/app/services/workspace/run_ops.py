"""Workspace run/stop/status/polling operations mixin.

Extracted from workspace_service.py in iteration 174 to keep
the service file below the 800-line bar.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.backtest import BacktestRequest, TaskStatus
from app.schemas.workspace import UnitStatusResponse
from app.services import workspace_unit_runtime
from app.services.fincore_metrics_helper import calculate_extended_metrics
from app.services.workspace.config import (
    _normalize_workspace_type,
    _workspace_settings_dict,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.backtest.service import BacktestService
    from app.services.trading_workspace_service import TradingWorkspaceService

logger = logging.getLogger(__name__)


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

    async def run_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str], parallel: bool = False
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

            if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
                results = await self.trading_service.start_units(
                    units,
                    user_id,
                    _workspace_settings_dict(ws),
                )
                await session.commit()
                return results

            # Mark all as queued
            for unit in units:
                unit.run_status = "queued"
            await session.commit()

            from app.services.backtest.service import BacktestService

            backtest_service = BacktestService()

            # Submit backtest for each unit, write back task_id immediately
            async def _submit_single(unit: StrategyUnit) -> dict[str, Any]:
                try:
                    workspace_settings = _workspace_settings_dict(ws)
                    workspace_unit_runtime.sync_unit_runtime(unit, workspace_settings)
                    bt_request = self._build_backtest_request(unit)
                    response = None
                    deadline = time.monotonic() + 1800
                    while response is None:
                        try:
                            response = await backtest_service.run_backtest(user_id, bt_request)
                        except ValueError as exc:
                            if "concurrent task limit" not in str(exc).lower():
                                raise
                            if time.monotonic() >= deadline:
                                raise TimeoutError(
                                    "Timed out waiting for an available backtest execution slot"
                                ) from exc
                            await asyncio.sleep(2)
                    task_id = response.task_id

                    # Immediately write task_id and set running (Bug-2 fix)
                    async with async_session_maker() as s2:
                        u = await self._get_unit(s2, workspace_id, str(unit.id))
                        if u:
                            u_row: Any = u
                            u_row.last_task_id = task_id
                            u_row.run_status = "running"
                            await s2.commit()

                    return {"unit_id": unit.id, "task_id": task_id, "status": "running"}

                except Exception as e:
                    logger.error("Unit %s submit failed: %s", unit.id, e)
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
        self, workspace_id: str, user_id: str, unit_ids: list[str]
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
                results = await self.trading_service.stop_units(units, user_id)
                await session.commit()
                return results

            from app.services.backtest.service import BacktestService

            backtest_service = BacktestService()

            q = select(StrategyUnit).where(
                StrategyUnit.workspace_id == workspace_id,
                StrategyUnit.id.in_(unit_ids),
                StrategyUnit.run_status.in_(["running", "queued"]),
            )
            db_result = await session.execute(q)
            units = list(db_result.scalars().all())

            for unit in units:
                cancelled = False
                if unit.last_task_id:
                    cancelled = await backtest_service.cancel_task(unit.last_task_id, user_id)
                unit.run_status = "cancelled" if cancelled else "idle"
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
                await self.trading_service.hydrate_units(units, user_id, full_log=False)
                return self.trading_service.build_status_responses(units)

            from app.services.backtest.service import BacktestService

            backtest_service = BacktestService()

            task_ids = [
                str(cast(Any, unit).last_task_id) for unit in units if cast(Any, unit).last_task_id
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
                last_task_id = str(unit_obj.last_task_id or "").strip()
                run_status = str(unit_obj.run_status or "")
                bar_count = int(unit_obj.bar_count or 0)
                task = task_by_id.get(last_task_id) if last_task_id else None
                if task is not None:
                    elapsed_seconds = self._task_elapsed_seconds(task)
                    if elapsed_seconds is not None and unit_obj.last_run_time != elapsed_seconds:
                        unit_obj.last_run_time = elapsed_seconds
                if run_status in {"queued", "running"}:
                    if not last_task_id:
                        unit_obj.run_status = "idle"
                        run_status = "idle"
                        changed = True
                    else:
                        task_status = await backtest_service.get_task_status(last_task_id, user_id)
                        if task_status == TaskStatus.COMPLETED:
                            unit_obj.run_status = "completed"
                            run_status = "completed"
                            changed = True
                        elif task_status == TaskStatus.CANCELLED:
                            unit_obj.run_status = "cancelled"
                            run_status = "cancelled"
                            changed = True
                        elif task_status == TaskStatus.FAILED or task_status is None:
                            unit_obj.run_status = "failed"
                            run_status = "failed"
                            changed = True
                if (
                    run_status == "completed"
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
                status_task = (
                    task_by_id.get(str(u_obj.last_task_id)) if u_obj.last_task_id else None
                )
                error_message = (
                    str(status_task.error_message)
                    if status_task and status_task.error_message
                    else None
                )
                run_progress, run_message = _unit_run_progress(
                    status_task,
                    str(u_obj.run_status or "idle"),
                )
                responses.append(
                    UnitStatusResponse(
                        id=str(u_obj.id),
                        run_status=str(u_obj.run_status or "idle"),
                        last_task_id=str(u_obj.last_task_id) if u_obj.last_task_id else None,
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
            task = await backtest_service.task_manager.get_task(task_id, user_id=user_id)
            elapsed = self._task_elapsed_seconds(task)
            if elapsed is None:
                elapsed = round(time.monotonic() - start_ts, 2)

            async with async_session_maker() as s:
                u = await self._get_unit(s, workspace_id, unit_id)
                if u:
                    unit_obj = cast(Any, u)
                    unit_obj.run_count = (unit_obj.run_count or 0) + 1
                    unit_obj.last_run_time = elapsed
                    if final_status == TaskStatus.COMPLETED:
                        unit_obj.run_status = "completed"
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
                                metrics = calculate_extended_metrics(log_data)
                                unit_obj.metrics_snapshot = metrics
                            except Exception as me:
                                logger.warning(
                                    "Extended metrics failed for unit %s: %s", unit_id, me
                                )
                                unit_obj.metrics_snapshot = {
                                    "total_return": bt_result.total_return,
                                    "annual_return": bt_result.annual_return,
                                    "sharpe_ratio": bt_result.sharpe_ratio,
                                    "max_drawdown": bt_result.max_drawdown,
                                    "win_rate": bt_result.win_rate,
                                    "total_trades": bt_result.total_trades,
                                }
                            unit_obj.bar_count = await self._resolve_unit_bar_count(
                                backtest_service,
                                task_id,
                                user_id,
                                bt_result,
                            )
                    elif final_status == TaskStatus.CANCELLED:
                        unit_obj.run_status = "cancelled"
                    else:
                        unit_obj.run_status = "failed"
                    await s.commit()

        except Exception as e:
            logger.error("Background poll failed for unit %s: %s", unit_id, e)
            try:
                async with async_session_maker() as s_err:
                    u_err = await self._get_unit(s_err, workspace_id, unit_id)
                    if u_err:
                        u_err_row: Any = u_err
                        u_err_row.run_status = "failed"
                        u_err_row.run_count = (u_err.run_count or 0) + 1
                        u_err_row.last_run_time = round(time.monotonic() - start_ts, 2)
                        await s_err.commit()
            except Exception:
                logger.exception("Failed to update unit %s status after error", unit_id)

    @staticmethod
    async def _poll_task_completion(
        backtest_service: BacktestService,  # noqa: F821
        task_id: str,
        user_id: str,
        timeout: float = 600,
        interval: float = 2.0,
    ) -> TaskStatus:
        """Poll backtest task status until terminal state or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = await backtest_service.get_task_status(task_id, user_id)
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return status
            await asyncio.sleep(interval)
        return TaskStatus.FAILED
