"""
Workspace service.

Handles workspace and strategy unit CRUD, bulk operations,
and workspace-level run orchestration (Phase 3).
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.optimization import OptimizationTask
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.backtest import BacktestRequest, TaskStatus
from app.schemas.workspace import (
    ApplyBestParamsRequest,
    GroupRenameRequest,
    StrategyUnitCreate,
    StrategyUnitUpdate,
    UnitOptimizationRequest,
    UnitRenameRequest,
    UnitStatusResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services import workspace_unit_runtime
from app.services.fincore_metrics_helper import calculate_extended_metrics
from app.services.optimization_execution_manager import get_optimization_execution_manager
from app.services.param_optimization_service import (
    get_optimization_progress,
    submit_optimization,
)
from app.services.trading_workspace_service import TradingWorkspaceService

logger = logging.getLogger(__name__)

_DEFAULT_UNIT_START_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)
_ACTIVE_OPTIMIZATION_STATUSES = {"pending", "queued", "running"}
_TERMINAL_OPTIMIZATION_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}
_ALLOWED_RUNTIME_FILE_EXTENSIONS = frozenset(
    {".log", ".yaml", ".yml", ".json", ".txt", ".py", ".md", ".csv"}
)


def _default_workspace_settings() -> dict[str, Any]:
    return {
        "data_source": {
            "type": "csv",
            "csv": {
                "directory_path": "",
                "delimiter": ",",
                "encoding": "utf-8",
                "has_header": True,
            },
            "mysql": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "",
                "username": "",
                "password": "",
                "table": "",
            },
            "postgresql": {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "",
                "schema": "public",
                "username": "",
                "password": "",
                "table": "",
            },
            "mongodb": {
                "uri": "mongodb://127.0.0.1:27017",
                "database": "",
                "collection": "",
                "username": "",
                "password": "",
                "auth_source": "admin",
            },
        }
    }


def _normalize_workspace_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "trading" if text == "trading" else "research"


def _is_trading_workspace(value: Any) -> bool:
    return _normalize_workspace_type(value) == "trading"


def _normalize_workspace_trading_config(config: dict[str, Any] | None) -> dict[str, Any]:
    return dict(config) if isinstance(config, dict) else {}


def _normalize_workspace_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _default_workspace_settings()
    if not isinstance(settings, dict):
        return normalized

    for key, value in settings.items():
        if key != "data_source":
            normalized[key] = value

    data_source = settings.get("data_source")
    if isinstance(data_source, dict):
        merged_data_source = dict(normalized["data_source"])
        for key, value in data_source.items():
            if key in {"csv", "mysql", "postgresql", "mongodb"} and isinstance(value, dict):
                section = dict(merged_data_source[key])
                if (
                    key == "csv"
                    and "directory_path" not in value
                    and isinstance(value.get("file_path"), str)
                ):
                    section["directory_path"] = value["file_path"]
                for section_key, section_value in value.items():
                    if key == "csv" and section_key == "file_path":
                        continue
                    section[section_key] = section_value
                merged_data_source[key] = section
            else:
                merged_data_source[key] = value
        normalized["data_source"] = merged_data_source

    return normalized


def _aggregate_workspace_status(units: list[StrategyUnit]) -> str:
    """Compute workspace status from child unit statuses."""
    if not units:
        return "idle"
    statuses = {u.run_status for u in units}
    if statuses & {"running", "queued"}:
        return "running"
    if all(s == "completed" for s in statuses):
        return "completed"
    if "failed" in statuses and not (statuses & {"running", "queued"}):
        return "error"
    return "idle"


def _workspace_settings_dict(ws: Workspace) -> dict[str, Any]:
    raw_settings = ws.__dict__.get("settings")
    if isinstance(raw_settings, dict):
        return _normalize_workspace_settings(raw_settings)
    return _normalize_workspace_settings(None)


def _default_unit_start_date_iso() -> str:
    return _DEFAULT_UNIT_START_DATE.isoformat()


def _default_unit_end_date_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _normalize_unit_data_config(data_config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(data_config or {})
    range_type = str(normalized.get("range_type") or "date").strip().lower()
    normalized["range_type"] = range_type if range_type in {"date", "sample"} else "date"
    if normalized["range_type"] == "date":
        if not str(normalized.get("start_date") or "").strip():
            normalized["start_date"] = _default_unit_start_date_iso()
        normalized["use_end_date"] = normalized.get("use_end_date") is not False
        if normalized["use_end_date"] and not str(normalized.get("end_date") or "").strip():
            normalized["end_date"] = _default_unit_end_date_iso()
        normalized.pop("sample_count", None)
        normalized.pop("bar_count", None)
    else:
        if normalized.get("sample_count") in (None, "", 0):
            normalized["sample_count"] = 1000
    return normalized


def _workspace_to_response(ws: Workspace) -> WorkspaceResponse:
    """Convert a Workspace ORM object to a WorkspaceResponse, including aggregated fields."""
    units = ws.strategy_units or []
    completed_count = sum(1 for u in units if u.run_status == "completed")
    return WorkspaceResponse(
        id=ws.id,
        user_id=ws.user_id,
        name=ws.name,
        description=ws.description,
        workspace_type=_normalize_workspace_type(getattr(ws, "workspace_type", None)),
        settings=_normalize_workspace_settings(ws.settings),
        trading_config=_normalize_workspace_trading_config(getattr(ws, "trading_config", None)),
        unit_count=len(units),
        completed_count=completed_count,
        status=_aggregate_workspace_status(units),
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


class WorkspaceService:
    """Service for workspace and strategy unit management."""

    def __init__(self) -> None:
        self.trading_service = TradingWorkspaceService()

    @staticmethod
    def _requested_bar_count(unit: StrategyUnit) -> int | None:
        from app.services.workspace._helpers import requested_bar_count
        return requested_bar_count(unit)

    @staticmethod
    async def _resolve_unit_log_dir(
        backtest_service: "BacktestService",  # noqa: F821
        task_id: str,
        user_id: str | None,
    ) -> Path | None:
        task = await backtest_service.task_manager.get_task(task_id, user_id=user_id)
        if not task or not task.log_dir:
            return None

        try:
            from app.api.analytics import _resolve_log_dir

            strategy_id = str(getattr(task, "strategy_id", "") or "").strip()
            if strategy_id:
                resolved = await _resolve_log_dir(task_id, strategy_id)
                if resolved and resolved.is_dir():
                    return resolved
        except Exception as exc:
            logger.debug("Failed to resolve unit log dir for task %s: %s", task_id, exc)

        persisted_log_dir = Path(task.log_dir)
        return persisted_log_dir if persisted_log_dir.is_dir() else None

    @staticmethod
    def _db_task_elapsed_seconds(task: BacktestTask | OptimizationTask | None) -> float | None:
        from app.services.workspace._helpers import db_task_elapsed_seconds
        return db_task_elapsed_seconds(task)

    @staticmethod
    def _task_elapsed_seconds(task: BacktestTask | None) -> float | None:
        from app.services.workspace._helpers import task_elapsed_seconds
        return task_elapsed_seconds(task)

    @staticmethod
    def _runtime_optimization_elapsed_seconds(task: dict[str, Any] | None) -> float | None:
        from app.services.workspace._helpers import runtime_optimization_elapsed_seconds
        return runtime_optimization_elapsed_seconds(task)

    @staticmethod
    def _parse_runtime_datetime(value: Any) -> datetime | None:
        from app.services.workspace._helpers import parse_runtime_datetime
        return parse_runtime_datetime(value)

    @staticmethod
    def _build_runtime_optimization_progress(task: dict[str, Any] | None) -> dict[str, Any] | None:
        from app.services.workspace._helpers import build_runtime_optimization_progress
        return build_runtime_optimization_progress(task)

    @staticmethod
    def _build_db_optimization_progress(task: OptimizationTask | None) -> dict[str, Any] | None:
        from app.services.workspace._helpers import build_db_optimization_progress
        return build_db_optimization_progress(task)

    @staticmethod
    def _resolve_optimization_progress(
        runtime_task: dict[str, Any] | None,
        db_task: OptimizationTask | None,
    ) -> dict[str, Any] | None:
        from app.services.workspace._helpers import resolve_optimization_progress
        return resolve_optimization_progress(runtime_task, db_task)

    @staticmethod
    def _optimization_progress_response_to_opt_info(
        progress: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        from app.services.workspace._helpers import optimization_progress_response_to_opt_info
        return optimization_progress_response_to_opt_info(progress)

    @staticmethod
    async def _resolve_unit_bar_count(
        backtest_service: "BacktestService",  # noqa: F821
        task_id: str,
        user_id: str | None,
        bt_result: Any | None = None,
    ) -> int:
        resolved_log_dir = await WorkspaceService._resolve_unit_log_dir(
            backtest_service,
            task_id,
            user_id,
        )
        if resolved_log_dir:
            from app.services.log_parser_service import parse_log_dir

            log_result = parse_log_dir(resolved_log_dir)
            if log_result:
                kline = log_result.get("kline")
                if isinstance(kline, dict):
                    dates = kline.get("dates")
                    if isinstance(dates, list) and dates:
                        return len(dates)

        if bt_result is not None:
            equity_dates = getattr(bt_result, "equity_dates", None) or []
            if equity_dates:
                return len(equity_dates)
            equity_curve = getattr(bt_result, "equity_curve", None) or []
            if equity_curve:
                return len(equity_curve)

        return 0

    @staticmethod
    def _resolve_optimization_artifact_log_dir(result_entry: dict[str, Any]) -> Path | None:
        from app.services.workspace._helpers import resolve_optimization_artifact_log_dir
        return resolve_optimization_artifact_log_dir(result_entry)

    @staticmethod
    def _build_optimization_artifact_metadata(
        task_id: str,
        result_index: int,
        result_entry: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.workspace._helpers import build_optimization_artifact_metadata
        return build_optimization_artifact_metadata(task_id, result_index, result_entry)

    @staticmethod
    def _build_optimization_trial_payload(
        task_id: str,
        result_index: int,
        unit: StrategyUnit,
        log_result: dict[str, Any],
        created_at: str,
        result_entry: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.workspace.optimization import build_optimization_trial_payload
        return build_optimization_trial_payload(
            task_id,
            result_index,
            unit,
            log_result,
            created_at,
            result_entry,
        )

    async def get_unit_optimization_result_artifact_metadata(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        result_index: int,
    ) -> dict[str, Any] | None:
        """Delegate to :mod:`app.services.workspace.optimization`."""
        from app.services.workspace.optimization import (
            get_unit_optimization_result_artifact_metadata as _impl,
        )
        return await _impl(workspace_id, user_id, unit_id, result_index)

    async def get_unit_optimization_result_payload(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        result_index: int,
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            task_id = unit.last_optimization_task_id
            mgr = get_optimization_execution_manager()
            db_task = await mgr.get_task(task_id, user_id=user_id)
            if (
                not db_task
                or not db_task.results
                or result_index < 0
                or result_index >= len(db_task.results)
            ):
                return None

            result_entry = cast(dict[str, Any], db_task.results[result_index] or {})
            log_dir = self._resolve_optimization_artifact_log_dir(result_entry)
            if log_dir is None:
                return None

            from app.services.log_parser_service import parse_log_dir

            strategy_root = log_dir.parent if log_dir.name == "logs" else log_dir
            log_result = parse_log_dir(log_dir, strategy_dir=strategy_root)
            if not log_result:
                return None

            created_at = db_task.created_at.isoformat() if db_task.created_at else ""
            return self._build_optimization_trial_payload(
                task_id,
                result_index,
                unit,
                log_result,
                created_at,
                result_entry,
            )

    async def reconcile_orphaned_run_statuses(self) -> int:
        """Delegate to :func:`app.services.workspace.reconciliation.reconcile_orphaned_run_statuses`.

        Kept as a thin facade so existing callers (FastAPI lifespan) keep
        working unchanged. The implementation lives in
        :mod:`app.services.workspace.reconciliation`.
        """
        from app.services.workspace.reconciliation import (
            reconcile_orphaned_run_statuses as _impl,
        )

        return await _impl()

    async def reconcile_completed_bar_counts(self) -> int:
        """Delegate to :func:`app.services.workspace.reconciliation.reconcile_completed_bar_counts`.

        Passes the class-bound ``_resolve_unit_bar_count`` static helper as
        the ``resolve_bar_count`` callback so the extracted function stays
        free of a back-import on this module.
        """
        from app.services.workspace.reconciliation import (
            reconcile_completed_bar_counts as _impl,
        )

        return await _impl(WorkspaceService._resolve_unit_bar_count)

    # ------------------------------------------------------------------
    # Workspace CRUD
    # ------------------------------------------------------------------

    async def create_workspace(self, user_id: str, data: WorkspaceCreate) -> WorkspaceResponse:
        """Delegate to :func:`app.services.workspace.lifecycle.create_workspace`."""
        from app.services.workspace.lifecycle import create_workspace as _impl
        return await _impl(user_id, data)

    async def get_workspace(self, workspace_id: str, user_id: str) -> WorkspaceResponse | None:
        """Delegate to :func:`app.services.workspace.lifecycle.get_workspace`."""
        from app.services.workspace.lifecycle import get_workspace as _impl
        return await _impl(workspace_id, user_id)

    async def list_workspaces(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        workspace_type: str | None = None,
    ) -> tuple[int, list[WorkspaceResponse]]:
        """Delegate to :func:`app.services.workspace.lifecycle.list_workspaces`."""
        from app.services.workspace.lifecycle import list_workspaces as _impl
        return await _impl(user_id, skip=skip, limit=limit, workspace_type=workspace_type)

    async def update_workspace(
        self, workspace_id: str, user_id: str, data: WorkspaceUpdate
    ) -> WorkspaceResponse | None:
        """Delegate to :func:`app.services.workspace.lifecycle.update_workspace`."""
        from app.services.workspace.lifecycle import update_workspace as _impl
        return await _impl(workspace_id, user_id, data)

    async def delete_workspace(self, workspace_id: str, user_id: str) -> bool:
        """Delegate to :func:`app.services.workspace.lifecycle.delete_workspace`."""
        from app.services.workspace.lifecycle import delete_workspace as _impl
        return await _impl(workspace_id, user_id)

    # ------------------------------------------------------------------
    # Strategy Unit CRUD
    # ------------------------------------------------------------------

    async def create_unit(
        self, workspace_id: str, user_id: str, data: StrategyUnitCreate
    ) -> dict[str, Any] | None:
        from app.services.workspace.units import create_unit as _impl
        return await _impl(workspace_id, user_id, data, self.trading_service)

    async def batch_create_units(
        self, workspace_id: str, user_id: str, units_data: list[StrategyUnitCreate]
    ) -> list[dict[str, Any]] | None:
        from app.services.workspace.units import batch_create_units as _impl
        return await _impl(workspace_id, user_id, units_data, self.trading_service)

    async def list_units(self, workspace_id: str, user_id: str) -> list[dict[str, Any]] | None:
        from app.services.workspace.units import list_units as _impl
        return await _impl(workspace_id, user_id, self.trading_service)

    async def get_unit(
        self, workspace_id: str, unit_id: str, user_id: str
    ) -> dict[str, Any] | None:
        from app.services.workspace.units import get_unit as _impl
        return await _impl(workspace_id, unit_id, user_id, self.trading_service)

    async def get_unit_runtime_info(
        self,
        workspace_id: str,
        unit_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        from app.services.workspace.units import get_unit_runtime_info as _impl
        return await _impl(workspace_id, unit_id, user_id, self.trading_service)

    async def read_unit_runtime_file(
        self,
        workspace_id: str,
        unit_id: str,
        user_id: str,
        relative_path: str,
        tail: int | None = None,
    ) -> str | None:
        from app.services.workspace.units import read_unit_runtime_file as _impl
        return await _impl(workspace_id, unit_id, user_id, relative_path, tail)

    async def open_unit_runtime_dir(
        self,
        workspace_id: str,
        unit_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        from app.services.workspace.units import open_unit_runtime_dir as _impl
        return await _impl(workspace_id, unit_id, user_id)

    async def update_unit(
        self, workspace_id: str, unit_id: str, user_id: str, data: StrategyUnitUpdate
    ) -> dict[str, Any] | None:
        from app.services.workspace.units import update_unit as _impl
        return await _impl(workspace_id, unit_id, user_id, data, self.trading_service)

    async def delete_unit(self, workspace_id: str, unit_id: str, user_id: str) -> bool:
        """Delegate to :func:`app.services.workspace.units.delete_unit`."""
        from app.services.workspace.units import delete_unit as _impl
        return await _impl(workspace_id, unit_id, user_id)

    async def bulk_delete_units(self, workspace_id: str, user_id: str, unit_ids: list[str]) -> int:
        """Delegate to :func:`app.services.workspace.units.bulk_delete_units`."""
        from app.services.workspace.units import bulk_delete_units as _impl
        return await _impl(workspace_id, user_id, unit_ids)

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------

    async def reorder_units(self, workspace_id: str, user_id: str, unit_ids: list[str]) -> bool:
        """Delegate to :func:`app.services.workspace.units.reorder_units`."""
        from app.services.workspace.units import reorder_units as _impl
        return await _impl(workspace_id, user_id, unit_ids)

    # ------------------------------------------------------------------
    # Group rename / Unit rename
    # ------------------------------------------------------------------

    async def rename_group(self, workspace_id: str, user_id: str, req: GroupRenameRequest) -> bool:
        """Delegate to :func:`app.services.workspace.units.rename_group`."""
        from app.services.workspace.units import rename_group as _impl
        return await _impl(workspace_id, user_id, req)

    async def rename_unit(self, workspace_id: str, user_id: str, req: UnitRenameRequest) -> bool:
        """Delegate to :func:`app.services.workspace.units.rename_unit`."""
        from app.services.workspace.units import rename_unit as _impl
        return await _impl(workspace_id, user_id, req)

    # ------------------------------------------------------------------
    # Run orchestration (Phase 3)
    # ------------------------------------------------------------------

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
                    cast(dict[str, Any], _workspace_settings_dict(ws)),
                )
                await session.commit()
                return results

            # Mark all as queued
            for unit in units:
                unit.run_status = "queued"
            await session.commit()

            from app.services.backtest_service import BacktestService

            backtest_service = BacktestService()

            # Submit backtest for each unit, write back task_id immediately
            async def _submit_single(unit: StrategyUnit) -> dict[str, Any]:
                try:
                    workspace_settings = cast(dict[str, Any], _workspace_settings_dict(ws))
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
                        u = await self._get_unit(s2, workspace_id, unit.id)
                        if u:
                            u.last_task_id = task_id
                            u.run_status = "running"
                            await s2.commit()

                    return {"unit_id": unit.id, "task_id": task_id, "status": "running"}

                except Exception as e:
                    logger.error("Unit %s submit failed: %s", unit.id, e)
                    async with async_session_maker() as s_err:
                        u_err = await self._get_unit(s_err, workspace_id, unit.id)
                        if u_err:
                            u_err.run_status = "failed"
                            u_err.run_count = (u_err.run_count or 0) + 1
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

            from app.services.backtest_service import BacktestService

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
        self, workspace_id: str, user_id: str
    ) -> list[UnitStatusResponse] | None:
        """Get run status of all units (polling endpoint)."""
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            q = (
                select(StrategyUnit)
                .where(StrategyUnit.workspace_id == workspace_id)
                .order_by(StrategyUnit.sort_order)
            )
            result = await session.execute(q)
            units = list(result.scalars().all())

            if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
                changed = await self.trading_service.hydrate_units(units, user_id)
                if changed:
                    await session.commit()
                return self.trading_service.build_status_responses(units)

            from app.services.backtest_service import BacktestService

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
                for tid in opt_task_ids:
                    try:
                        progress = get_optimization_progress(tid, user_id=user_id, use_db=True)
                        opt_info = self._optimization_progress_response_to_opt_info(progress)
                        if opt_info:
                            opt_progress_map[tid] = opt_info
                    except Exception:
                        pass

            responses: list[UnitStatusResponse] = []
            for u in units:
                u_obj = cast(Any, u)
                opt_tid = (
                    str(u_obj.last_optimization_task_id)
                    if u_obj.last_optimization_task_id
                    else None
                )
                opt_info = opt_progress_map.get(opt_tid, {}) if opt_tid else {}
                responses.append(
                    UnitStatusResponse(
                        id=str(u_obj.id),
                        run_status=str(u_obj.run_status or "idle"),
                        last_task_id=str(u_obj.last_task_id) if u_obj.last_task_id else None,
                        metrics_snapshot=cast(dict[str, Any], u_obj.metrics_snapshot or {}),
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

    async def get_trading_auto_config(
        self,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None or not _is_trading_workspace(ws.workspace_type):
                return None
            return self.trading_service.get_auto_trading_config()

    async def update_trading_auto_config(
        self,
        workspace_id: str,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None or not _is_trading_workspace(ws.workspace_type):
                return None
            config = self.trading_service.update_auto_trading_config(payload)
            trading_config = _normalize_workspace_trading_config(ws.trading_config)
            trading_config["auto_trading"] = config
            ws.trading_config = trading_config
            await session.commit()
            return config

    async def get_trading_auto_schedule(
        self,
        workspace_id: str,
        user_id: str,
    ) -> list[dict[str, Any]] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None or not _is_trading_workspace(ws.workspace_type):
                return None
            return self.trading_service.get_auto_trading_schedule()

    async def get_trading_positions(
        self,
        workspace_id: str,
        user_id: str,
        unit_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None or not _is_trading_workspace(ws.workspace_type):
                return None

            q = select(StrategyUnit).where(StrategyUnit.workspace_id == workspace_id)
            if unit_ids:
                q = q.where(StrategyUnit.id.in_(unit_ids))
            q = q.order_by(StrategyUnit.sort_order)
            result = await session.execute(q)
            units = list(result.scalars().all())

            changed = await self.trading_service.hydrate_units(units, user_id)
            if changed:
                await session.commit()
            response = await self.trading_service.build_positions_response(units, user_id)
            return response.model_dump()

    async def get_trading_daily_summary(
        self,
        workspace_id: str,
        user_id: str,
        *,
        unit_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None or not _is_trading_workspace(ws.workspace_type):
                return None

            q = select(StrategyUnit).where(StrategyUnit.workspace_id == workspace_id)
            if unit_id:
                q = q.where(StrategyUnit.id == unit_id)
            q = q.order_by(StrategyUnit.sort_order)
            result = await session.execute(q)
            units = list(result.scalars().all())

            changed = await self.trading_service.hydrate_units(units, user_id)
            if changed:
                await session.commit()
            response = await self.trading_service.build_daily_summary_response(
                units,
                user_id,
                start_date=start_date,
                end_date=end_date,
            )
            return response.model_dump()

    # ------------------------------------------------------------------
    # Optimization orchestration (Phase 4)
    # ------------------------------------------------------------------

    async def submit_unit_optimization(
        self, workspace_id: str, user_id: str, req: UnitOptimizationRequest
    ) -> dict[str, Any] | None:
        """Submit optimization for a strategy unit. Delegates to existing optimization service."""
        from app.services.param_optimization_service import generate_param_grid

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, req.unit_id)
            if unit is None:
                return None

            # Build param_ranges dict
            param_ranges = {}
            for name, spec in req.param_ranges.items():
                param_ranges[name] = {
                    "start": spec.start,
                    "end": spec.end,
                    "step": spec.step,
                    "type": spec.type,
                }

            grid = generate_param_grid(param_ranges)
            if not grid:
                return {"error": "Parameter grid is empty"}

            strategy_id = unit.strategy_id or ""

            # Sync unit runtime dir so optimization uses unit's symbol/data config
            workspace_settings = cast(dict[str, Any], _workspace_settings_dict(ws))
            unit_runtime_dir = workspace_unit_runtime.sync_unit_runtime(unit, workspace_settings)

            # Create persisted task in DB
            mgr = get_optimization_execution_manager()
            db_task = await mgr.create_task(
                user_id=user_id,
                strategy_id=strategy_id,
                total=len(grid),
                param_ranges=param_ranges,
                n_workers=req.n_workers,
            )
            task_id = db_task.id
            artifact_root = unit_runtime_dir / "optimization_runs" / task_id
            artifact_root.mkdir(parents=True, exist_ok=True)
            _write_json_file(
                artifact_root / "manifest.json",
                {
                    "task_id": task_id,
                    "workspace_id": workspace_id,
                    "unit_id": unit.id,
                    "strategy_id": strategy_id,
                    "param_names": list(param_ranges.keys()),
                    "param_ranges": param_ranges,
                    "n_workers": req.n_workers,
                    "created_at": db_task.created_at.isoformat() if db_task.created_at else "",
                },
            )

            submit_optimization(
                strategy_id=strategy_id,
                param_ranges=param_ranges,
                n_workers=req.n_workers,
                task_id=task_id,
                persist_to_db=True,
                strategy_dir=str(unit_runtime_dir),
                artifact_root=str(artifact_root),
            )

            # Update unit with optimization task id — merge into existing config
            unit.last_optimization_task_id = task_id
            existing_oc = dict(unit.optimization_config or {})
            existing_oc.update(
                {
                    "param_ranges": param_ranges,
                    "n_workers": req.n_workers,
                    "artifact_root": str(artifact_root),
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            unit.optimization_config = existing_oc
            await session.commit()

            return {
                "task_id": task_id,
                "unit_id": req.unit_id,
                "total_combinations": len(grid),
                "n_workers": req.n_workers,
            }

    async def get_unit_optimization_progress(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Delegate to :mod:`app.services.workspace.optimization`."""
        from app.services.workspace.optimization import (
            get_unit_optimization_progress as _impl,
        )
        return await _impl(workspace_id, user_id, unit_id)

    async def get_unit_optimization_results(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Delegate to :mod:`app.services.workspace.optimization`."""
        from app.services.workspace.optimization import (
            get_unit_optimization_results as _impl,
        )
        return await _impl(workspace_id, user_id, unit_id)

    async def cancel_unit_optimization(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Delegate to :mod:`app.services.workspace.optimization`."""
        from app.services.workspace.optimization import (
            cancel_unit_optimization as _impl,
        )
        return await _impl(workspace_id, user_id, unit_id)

    async def apply_best_params(
        self, workspace_id: str, user_id: str, req: ApplyBestParamsRequest
    ) -> dict[str, Any] | None:
        """Delegate to :mod:`app.services.workspace.optimization`."""
        from app.services.workspace.optimization import apply_best_params as _impl
        return await _impl(workspace_id, user_id, req)

    # ------------------------------------------------------------------
    # Combined report (Phase 5)
    # ------------------------------------------------------------------

    async def get_workspace_report(
        self,
        workspace_id: str,
        user_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        max_cash: float | None = None,
        calc_method: str = "simple",
        annual_days: int = 252,
        weight_mode: str = "equal",
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        """Generate a combined report aggregating metrics across all units.

        Delegates to :func:`app.services.workspace.reports.get_workspace_report`;
        kept here as a thin facade so existing callers do not need to change.
        """
        from app.services.workspace.reports import get_workspace_report as _impl

        return await _impl(
            workspace_id=workspace_id,
            user_id=user_id,
            load_workspace=WorkspaceService._load_workspace,
            start_date=start_date,
            end_date=end_date,
            max_cash=max_cash,
            calc_method=calc_method,
            annual_days=annual_days,
            weight_mode=weight_mode,
            weights=weights,
        )

    async def delete_workspace_report(
        self, workspace_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Clear cached report config on the workspace.

        Delegates to :func:`app.services.workspace.reports.delete_workspace_report`.
        """
        from app.services.workspace.reports import delete_workspace_report as _impl

        return await _impl(
            workspace_id=workspace_id,
            user_id=user_id,
            load_workspace=WorkspaceService._load_workspace,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_backtest_request(unit: StrategyUnit) -> BacktestRequest:
        """Build a BacktestRequest from a strategy unit's configuration."""
        settings = unit.unit_settings or {}
        data_cfg = _normalize_unit_data_config(unit.data_config)
        params = unit.params or {}

        return BacktestRequest(
            strategy_id=unit.strategy_id or "",
            runtime_dir=str(workspace_unit_runtime.unit_dir(unit.workspace_id, unit.id)),
            symbol=unit.symbol or data_cfg.get("symbol", ""),
            start_date=data_cfg.get("start_date", _default_unit_start_date_iso()),
            end_date=data_cfg.get("end_date", _default_unit_end_date_iso()),
            initial_cash=settings.get("initial_cash", 100000),
            commission=settings.get("commission", 0.001),
            timeframe=unit.timeframe or "1d",
            timeframe_n=unit.timeframe_n or 1,
            bar_count=WorkspaceService._requested_bar_count(unit),
            params=params,
        )

    @staticmethod
    def _collect_runtime_files(runtime_dir: Path) -> list[Path]:
        from app.services.workspace._helpers import collect_runtime_files
        return collect_runtime_files(runtime_dir)

    @staticmethod
    def _runtime_file_kind(relative_path: Path) -> str:
        from app.services.workspace._helpers import runtime_file_kind
        return runtime_file_kind(relative_path)

    @staticmethod
    def _resolve_runtime_file(runtime_dir: Path, relative_path: str) -> Path | None:
        from app.services.workspace._helpers import resolve_runtime_file
        return resolve_runtime_file(runtime_dir, relative_path)

    @staticmethod
    def _open_path_in_file_manager(path: Path) -> None:
        from app.services.workspace._helpers import open_path_in_file_manager
        open_path_in_file_manager(path)

    async def _background_poll_units(
        self,
        workspace_id: str,
        user_id: str,
        submitted: list[tuple[str, str]],
        backtest_service: "BacktestService",  # noqa: F821
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
        backtest_service: "BacktestService",  # noqa: F821
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
                        u_err.run_status = "failed"
                        u_err.run_count = (u_err.run_count or 0) + 1
                        u_err.last_run_time = round(time.monotonic() - start_ts, 2)
                        await s_err.commit()
            except Exception:
                logger.exception("Failed to update unit %s status after error", unit_id)

    @staticmethod
    async def _poll_task_completion(
        backtest_service: "BacktestService",  # noqa: F821
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

    @staticmethod
    async def _load_workspace(
        session: AsyncSession,
        workspace_id: str,
        user_id: str,
        load_units: bool = True,
    ) -> Workspace | None:
        q = select(Workspace).where(Workspace.id == workspace_id, Workspace.user_id == user_id)
        if load_units:
            q = q.options(selectinload(Workspace.strategy_units))
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_unit(
        session: AsyncSession, workspace_id: str, unit_id: str
    ) -> StrategyUnit | None:
        q = select(StrategyUnit).where(
            StrategyUnit.id == unit_id,
            StrategyUnit.workspace_id == workspace_id,
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    def _unit_to_dict(unit: StrategyUnit, opt_info: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.services.workspace._helpers import unit_to_dict
        return unit_to_dict(unit, opt_info)

    @staticmethod
    def _compute_rename(
        unit: StrategyUnit,
        mode: str,
        value: str,
        search: str,
        replace: str,
    ) -> str:
        from app.services.workspace._helpers import compute_rename
        return compute_rename(unit, mode, value, search, replace)
