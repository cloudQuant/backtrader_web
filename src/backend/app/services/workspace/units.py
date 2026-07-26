"""Unit management operations (simple CRUD subset).

Handles delete, bulk-delete, reorder, and rename operations for strategy
units. These methods have no dependency on ``TradingWorkspaceService`` and
can be extracted cleanly.

The more complex unit operations (create, batch_create, list, get, update)
remain on :class:`app.services.workspace_service.WorkspaceService` because
they depend on ``self.trading_service`` for hydration and normalization.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.workspace import StrategyUnit
from app.schemas.workspace import (
    GroupRenameRequest,
    StrategyUnitCreate,
    StrategyUnitUpdate,
    UnitRenameRequest,
    UnitRuntimeInfoResponse,
)
from app.services import workspace_unit_runtime
from app.services.param_optimization_service import get_optimization_progress
from app.services.workspace._helpers import compute_rename

logger = logging.getLogger(__name__)


_JSON_FIELD_NAMES = {
    "data_config",
    "unit_settings",
    "params",
    "optimization_config",
    "gateway_config",
    "trading_snapshot",
    "metrics_snapshot",
}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return value


async def create_unit(
    workspace_id: str,
    user_id: str,
    data: StrategyUnitCreate,
    trading_service: Any,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_unit_data_config

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None

        max_order_q = select(func.coalesce(func.max(StrategyUnit.sort_order), -1)).where(
            StrategyUnit.workspace_id == workspace_id
        )
        max_order = (await session.execute(max_order_q)).scalar() or 0

        unit = StrategyUnit(
            workspace_id=workspace_id,
            group_name=data.group_name,
            strategy_id=data.strategy_id,
            strategy_name=data.strategy_name,
            symbol=data.symbol,
            symbol_name=data.symbol_name,
            timeframe=data.timeframe,
            timeframe_n=data.timeframe_n,
            category=data.category,
            sort_order=max_order + 1,
            data_config=_json_safe_value(_normalize_unit_data_config(data.data_config)),
            unit_settings=_json_safe_value(data.unit_settings),
            params=_json_safe_value(data.params),
            optimization_config=_json_safe_value(data.optimization_config),
            trading_mode=trading_service.normalize_trading_mode(data.trading_mode),
            gateway_config=_json_safe_value(
                trading_service.normalize_gateway_config(
                    data.gateway_config.model_dump()
                    if hasattr(data.gateway_config, "model_dump")
                    else data.gateway_config
                )
            ),
            lock_trading=bool(data.lock_trading),
            lock_running=bool(data.lock_running),
            trading_snapshot=_json_safe_value(
                data.trading_snapshot.model_dump()
                if hasattr(data.trading_snapshot, "model_dump")
                else data.trading_snapshot
            ),
        )
        session.add(unit)
        await session.commit()
        await session.refresh(unit)
        workspace_unit_runtime.sync_workspace_unit_runtime(
            unit,
            cast("dict[str, Any]", ws.settings) or {},
            str(ws.workspace_type),
        )
        return WorkspaceService._unit_to_dict(unit)


async def batch_create_units(
    workspace_id: str,
    user_id: str,
    units_data: list[StrategyUnitCreate],
    trading_service: Any,
) -> list[dict[str, Any]] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_unit_data_config

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None

        max_order_q = select(func.coalesce(func.max(StrategyUnit.sort_order), -1)).where(
            StrategyUnit.workspace_id == workspace_id
        )
        max_order = (await session.execute(max_order_q)).scalar() or 0

        created = []
        for i, data in enumerate(units_data):
            unit = StrategyUnit(
                workspace_id=workspace_id,
                group_name=data.group_name,
                strategy_id=data.strategy_id,
                strategy_name=data.strategy_name,
                symbol=data.symbol,
                symbol_name=data.symbol_name,
                timeframe=data.timeframe,
                timeframe_n=data.timeframe_n,
                category=data.category,
                sort_order=max_order + 1 + i,
                data_config=_json_safe_value(_normalize_unit_data_config(data.data_config)),
                unit_settings=_json_safe_value(data.unit_settings),
                params=_json_safe_value(data.params),
                optimization_config=_json_safe_value(data.optimization_config),
                trading_mode=trading_service.normalize_trading_mode(data.trading_mode),
                gateway_config=_json_safe_value(
                    trading_service.normalize_gateway_config(
                        data.gateway_config.model_dump()
                        if hasattr(data.gateway_config, "model_dump")
                        else data.gateway_config
                    )
                ),
                lock_trading=bool(data.lock_trading),
                lock_running=bool(data.lock_running),
                trading_snapshot=_json_safe_value(
                    data.trading_snapshot.model_dump()
                    if hasattr(data.trading_snapshot, "model_dump")
                    else data.trading_snapshot
                ),
            )
            session.add(unit)
            created.append(unit)

        await session.commit()
        for unit in created:
            await session.refresh(unit)
            workspace_unit_runtime.sync_workspace_unit_runtime(
                unit,
                cast("dict[str, Any]", ws.settings) or {},
                str(ws.workspace_type),
            )
        return [WorkspaceService._unit_to_dict(unit) for unit in created]


async def list_units(
    workspace_id: str,
    user_id: str,
    trading_service: Any,
) -> list[dict[str, Any]] | None:
    from app.services.backtest.service import BacktestService
    from app.services.workspace_service import WorkspaceService, _normalize_workspace_type

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
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
            # Initial table rendering must stay local: full log parsing and
            # broker gateway reads are reserved for explicit detail/status
            # refreshes, otherwise a workspace with many units blocks the UI.
            changed = await trading_service.hydrate_units(
                units,
                user_id,
                full_log=False,
                refresh_gateway=False,
            )
            if changed:
                await session.commit()
            return [WorkspaceService._unit_to_dict(unit) for unit in units]

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
        backtest_service = None
        for unit in units:
            unit_obj = cast(Any, unit)
            last_task_id = str(unit_obj.last_task_id or "").strip()
            if not last_task_id:
                continue

            task = task_by_id.get(last_task_id)
            elapsed_seconds = WorkspaceService._task_elapsed_seconds(task)
            if elapsed_seconds is not None and unit_obj.last_run_time != elapsed_seconds:
                unit_obj.last_run_time = elapsed_seconds
                changed = True

            if str(unit_obj.run_status or "") != "completed":
                continue

            if backtest_service is None:
                backtest_service = BacktestService()

            resolved_bar_count = await WorkspaceService._resolve_unit_bar_count(
                backtest_service,
                last_task_id,
                user_id,
            )
            if resolved_bar_count > 0 and int(unit_obj.bar_count or 0) != resolved_bar_count:
                unit_obj.bar_count = resolved_bar_count
                changed = True

        if changed:
            await session.commit()

        opt_progress_map: dict[str, dict[str, Any]] = {}
        opt_task_ids = {
            str(cast(Any, unit).last_optimization_task_id)
            for unit in units
            if cast(Any, unit).last_optimization_task_id
        }
        if opt_task_ids:
            for task_id in opt_task_ids:
                try:
                    progress = get_optimization_progress(task_id, user_id=user_id, use_db=True)
                    opt_info = WorkspaceService._optimization_progress_response_to_opt_info(
                        progress
                    )
                    if opt_info:
                        opt_progress_map[task_id] = opt_info
                except Exception:
                    logger.debug(
                        "Failed to load optimization progress for task %s", task_id, exc_info=True
                    )

        return [
            WorkspaceService._unit_to_dict(
                unit,
                opt_progress_map.get(
                    str(cast(Any, unit).last_optimization_task_id),
                    {},
                )
                if cast(Any, unit).last_optimization_task_id
                else {},
            )
            for unit in units
        ]


async def get_unit(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    trading_service: Any,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_workspace_type

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
            changed = await trading_service.hydrate_units([unit], user_id)
            if changed:
                await session.commit()
        return WorkspaceService._unit_to_dict(unit)


async def get_unit_runtime_info(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    trading_service: Any,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_workspace_type

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        if _normalize_workspace_type(getattr(ws, "workspace_type", None)) == "trading":
            changed = await trading_service.hydrate_units([unit], user_id)
            if changed:
                await session.commit()

        runtime_dir = workspace_unit_runtime.unit_dir(workspace_id, unit_id)
        if not runtime_dir.is_dir():
            return None

        log_dir = runtime_dir / "logs"
        files: list[dict[str, Any]] = []
        for relative_path in WorkspaceService._collect_runtime_files(runtime_dir):
            file_path = runtime_dir / relative_path
            if not file_path.is_file():
                continue
            files.append(
                {
                    "name": file_path.name,
                    "relative_path": relative_path.as_posix(),
                    "size": file_path.stat().st_size,
                    "kind": WorkspaceService._runtime_file_kind(relative_path),
                }
            )

        return UnitRuntimeInfoResponse(
            unit_id=unit_id,
            runtime_dir=str(runtime_dir),
            log_dir=str(log_dir) if log_dir.is_dir() else None,
            files=files,
        ).model_dump()


async def get_unit_runtime_dir(
    workspace_id: str,
    unit_id: str,
    user_id: str,
) -> Path | None:
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        runtime_dir = workspace_unit_runtime.unit_dir(workspace_id, unit_id)
        return runtime_dir if runtime_dir.is_dir() else None


async def read_unit_runtime_file(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    relative_path: str,
    tail: int | None = None,
) -> str | None:
    from app.services.workspace_service import WorkspaceService

    runtime_dir = await get_unit_runtime_dir(workspace_id, unit_id, user_id)
    if runtime_dir is None:
        return None
    file_path = WorkspaceService._resolve_runtime_file(runtime_dir, relative_path)
    if file_path is None or not file_path.is_file():
        return None

    content = file_path.read_text(encoding="utf-8", errors="replace")
    if tail is not None and tail > 0:
        lines = content.splitlines()
        content = "\n".join(lines[-tail:])
    return content


async def open_unit_runtime_dir(
    workspace_id: str,
    unit_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService

    runtime_dir = await get_unit_runtime_dir(workspace_id, unit_id, user_id)
    if runtime_dir is None:
        return None
    WorkspaceService._open_path_in_file_manager(runtime_dir)
    return {
        "unit_id": unit_id,
        "runtime_dir": str(runtime_dir),
        "message": "策略单元目录已打开",
    }


async def update_unit(
    workspace_id: str,
    unit_id: str,
    user_id: str,
    data: StrategyUnitUpdate,
    trading_service: Any,
) -> dict[str, Any] | None:
    from app.services.workspace_service import WorkspaceService, _normalize_unit_data_config

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "data_config":
                value = _normalize_unit_data_config(cast(dict[str, Any] | None, value))
            elif key == "trading_mode":
                value = trading_service.normalize_trading_mode(value)
            elif key == "gateway_config":
                value = trading_service.normalize_gateway_config(
                    value.model_dump()
                    if hasattr(value, "model_dump")
                    else cast(dict[str, Any], value)
                )
            elif key == "trading_snapshot":
                value = (
                    value.model_dump()
                    if hasattr(value, "model_dump")
                    else cast(dict[str, Any], value)
                )
            if key in _JSON_FIELD_NAMES:
                value = _json_safe_value(value)
            setattr(unit, key, value)
        await session.commit()
        await session.refresh(unit)
        workspace_unit_runtime.sync_workspace_unit_runtime(
            unit,
            cast("dict[str, Any]", ws.settings) or {},
            str(ws.workspace_type),
        )
        return WorkspaceService._unit_to_dict(unit)


async def delete_unit(workspace_id: str, unit_id: str, user_id: str) -> bool:
    """Delete a single strategy unit and its runtime directory."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return False
        await session.delete(unit)
        await session.commit()
        workspace_unit_runtime.remove_unit_dir(workspace_id, unit_id)
        return True


async def bulk_delete_units(workspace_id: str, user_id: str, unit_ids: list[str]) -> int:
    """Delete multiple units in one transaction."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return 0

        result = await session.execute(
            sa_delete(StrategyUnit).where(
                StrategyUnit.workspace_id == workspace_id,
                StrategyUnit.id.in_(unit_ids),
            )
        )
        await session.commit()
        for uid in unit_ids:
            workspace_unit_runtime.remove_unit_dir(workspace_id, uid)
        return result.rowcount or 0


async def reorder_units(workspace_id: str, user_id: str, unit_ids: list[str]) -> bool:
    """Set ``sort_order`` for units based on the provided id list."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        for idx, uid in enumerate(unit_ids):
            unit = await WorkspaceService._get_unit(session, workspace_id, uid)
            if unit:
                unit_row: Any = unit
                unit_row.sort_order = idx
        await session.commit()
        return True


async def rename_group(workspace_id: str, user_id: str, req: GroupRenameRequest) -> bool:
    """Rename the group for a set of units."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False

        q = select(StrategyUnit).where(
            StrategyUnit.workspace_id == workspace_id,
            StrategyUnit.id.in_(req.unit_ids),
        )
        result = await session.execute(q)
        units = list(result.scalars().all())

        for unit in units:
            unit.group_name = compute_rename(unit, req.mode, req.value, req.search, req.replace)

        await session.commit()
        return True


async def rename_unit(workspace_id: str, user_id: str, req: UnitRenameRequest) -> bool:
    """Rename a single unit's strategy_name."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        unit = await WorkspaceService._get_unit(session, workspace_id, req.unit_id)
        if unit is None:
            return False
        unit_row: Any = unit
        unit_row.strategy_name = compute_rename(unit, req.mode, req.value, req.search, req.replace)
        await session.commit()
        return True
