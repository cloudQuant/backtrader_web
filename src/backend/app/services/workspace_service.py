"""
Workspace service.

Handles workspace and strategy unit CRUD, bulk operations,
and workspace-level run orchestration (Phase 3).
"""

import logging
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
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services import workspace_unit_runtime
from app.services.optimization.execution_manager import get_optimization_execution_manager
from app.services.trading_workspace_service import TradingWorkspaceService
from app.services.workspace.config import (
    _default_unit_end_date_iso,
    _default_unit_start_date_iso,
    _is_trading_workspace,
    _normalize_unit_data_config,
    _normalize_workspace_settings,
    _normalize_workspace_trading_config,
    _normalize_workspace_type,
    _workspace_to_response,
)
from app.services.workspace.run_ops import WorkspaceRunOpsMixin

# These names are re-exported here for sibling slices (workspace/units.py,
# workspace/optimization.py, workspace/lifecycle.py, workspace/_helpers.py)
# that import them from this module rather than from workspace.config.
__all__ = [
    "WorkspaceService",
    "_normalize_unit_data_config",
    "_normalize_workspace_settings",
    "_normalize_workspace_trading_config",
    "_normalize_workspace_type",
    "_workspace_to_response",
]

logger = logging.getLogger(__name__)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}

_DEFAULT_UNIT_START_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)
_ACTIVE_OPTIMIZATION_STATUSES = {"pending", "queued", "running"}
_TERMINAL_OPTIMIZATION_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


class WorkspaceService(WorkspaceRunOpsMixin):
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

    # --- Run / Stop / Status / Polling delegated to mixin ---
    # These methods are defined in workspace.run_ops.WorkspaceRunOpsMixin
    # and mixed into WorkspaceService at class definition time.

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

            changed = await self.trading_service.hydrate_units(
                units,
                user_id,
                full_log=False,
            )
            if changed:
                await session.commit()
            response_units = units
            if not unit_ids:
                response_units = [
                    unit
                    for unit in units
                    if str(unit.run_status or "").lower() in {"queued", "running"}
                    or str(
                        (_dict_or_empty(unit.trading_snapshot).get("instance_status") or "")
                    ).lower()
                    in {"queued", "running"}
                ]
            response = await self.trading_service.build_positions_response(
                response_units,
                user_id,
                hydrate=False,
            )
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
        """Submit optimization for a strategy unit."""
        from app.services.workspace.optimization import submit_unit_optimization as _impl

        return await _impl(
            workspace_id,
            user_id,
            req,
            load_workspace=self._load_workspace,
            get_unit=self._get_unit,
        )

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
