"""
Workspace service.

Handles workspace and strategy unit CRUD, bulk operations,
and workspace-level run orchestration (Phase 3).
"""

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import async_session_maker
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

logger = logging.getLogger(__name__)


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
                if key == "csv" and "directory_path" not in value and isinstance(value.get("file_path"), str):
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


def _workspace_to_response(ws: Workspace) -> WorkspaceResponse:
    """Convert a Workspace ORM object to a WorkspaceResponse, including aggregated fields."""
    units = ws.strategy_units or []
    completed_count = sum(1 for u in units if u.run_status == "completed")
    return WorkspaceResponse(
        id=ws.id,
        user_id=ws.user_id,
        name=ws.name,
        description=ws.description,
        settings=_normalize_workspace_settings(ws.settings),
        unit_count=len(units),
        completed_count=completed_count,
        status=_aggregate_workspace_status(units),
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


class WorkspaceService:
    """Service for workspace and strategy unit management."""

    # ------------------------------------------------------------------
    # Workspace CRUD
    # ------------------------------------------------------------------

    async def create_workspace(self, user_id: str, data: WorkspaceCreate) -> WorkspaceResponse:
        async with async_session_maker() as session:
            ws = Workspace(
                user_id=user_id,
                name=data.name,
                description=data.description,
                settings=_normalize_workspace_settings(data.settings),
            )
            session.add(ws)
            await session.commit()
            await session.refresh(ws, attribute_names=["strategy_units"])
            return _workspace_to_response(ws)

    async def get_workspace(self, workspace_id: str, user_id: str) -> WorkspaceResponse | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id)
            if ws is None:
                return None
            return _workspace_to_response(ws)

    async def list_workspaces(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[WorkspaceResponse]]:
        async with async_session_maker() as session:
            # Count
            count_q = select(func.count()).select_from(Workspace).where(Workspace.user_id == user_id)
            total = (await session.execute(count_q)).scalar() or 0

            # Fetch with units eagerly loaded
            q = (
                select(Workspace)
                .where(Workspace.user_id == user_id)
                .options(selectinload(Workspace.strategy_units))
                .order_by(Workspace.updated_at.desc())
                .offset(skip)
                .limit(limit)
            )
            result = await session.execute(q)
            workspaces = list(result.scalars().unique().all())
            return total, [_workspace_to_response(ws) for ws in workspaces]

    async def update_workspace(
        self, workspace_id: str, user_id: str, data: WorkspaceUpdate
    ) -> WorkspaceResponse | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id)
            if ws is None:
                return None
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if key == "settings" and isinstance(value, dict):
                    existing = _normalize_workspace_settings(ws.settings)
                    for settings_key, settings_value in value.items():
                        if settings_key != "data_source":
                            existing[settings_key] = settings_value
                    if isinstance(value.get("data_source"), dict):
                        merged_data_source = dict(existing.get("data_source") or {})
                        for source_key, source_value in value["data_source"].items():
                            if source_key in {"csv", "mysql", "postgresql", "mongodb"} and isinstance(source_value, dict):
                                current_section = dict(merged_data_source.get(source_key) or {})
                                current_section.update(source_value)
                                merged_data_source[source_key] = current_section
                            else:
                                merged_data_source[source_key] = source_value
                        existing["data_source"] = merged_data_source
                    ws.settings = existing
                else:
                    setattr(ws, key, value)
            await session.commit()
            await session.refresh(ws, attribute_names=["strategy_units"])
            return _workspace_to_response(ws)

    async def delete_workspace(self, workspace_id: str, user_id: str) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            await session.delete(ws)
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Strategy Unit CRUD
    # ------------------------------------------------------------------

    async def create_unit(
        self, workspace_id: str, user_id: str, data: StrategyUnitCreate
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            # Determine next sort_order
            max_order_q = (
                select(func.coalesce(func.max(StrategyUnit.sort_order), -1))
                .where(StrategyUnit.workspace_id == workspace_id)
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
                data_config=data.data_config,
                unit_settings=data.unit_settings,
                params=data.params,
                optimization_config=data.optimization_config,
            )
            session.add(unit)
            await session.commit()
            await session.refresh(unit)
            return self._unit_to_dict(unit)

    async def batch_create_units(
        self, workspace_id: str, user_id: str, units_data: list[StrategyUnitCreate]
    ) -> list[dict[str, Any]] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            max_order_q = (
                select(func.coalesce(func.max(StrategyUnit.sort_order), -1))
                .where(StrategyUnit.workspace_id == workspace_id)
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
                    data_config=data.data_config,
                    unit_settings=data.unit_settings,
                    params=data.params,
                    optimization_config=data.optimization_config,
                )
                session.add(unit)
                created.append(unit)

            await session.commit()
            for u in created:
                await session.refresh(u)
            return [self._unit_to_dict(u) for u in created]

    async def list_units(
        self, workspace_id: str, user_id: str
    ) -> list[dict[str, Any]] | None:
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
            return [self._unit_to_dict(u) for u in units]

    async def get_unit(
        self, workspace_id: str, unit_id: str, user_id: str
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None:
                return None
            return self._unit_to_dict(unit)

    async def update_unit(
        self, workspace_id: str, unit_id: str, user_id: str, data: StrategyUnitUpdate
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None:
                return None
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(unit, key, value)
            await session.commit()
            await session.refresh(unit)
            return self._unit_to_dict(unit)

    async def delete_unit(
        self, workspace_id: str, unit_id: str, user_id: str
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None:
                return False
            await session.delete(unit)
            await session.commit()
            return True

    async def bulk_delete_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str]
    ) -> int:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return 0
            from sqlalchemy import delete as sa_delete

            result = await session.execute(
                sa_delete(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                )
            )
            await session.commit()
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------

    async def reorder_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str]
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            for idx, uid in enumerate(unit_ids):
                unit = await self._get_unit(session, workspace_id, uid)
                if unit:
                    unit.sort_order = idx
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Group rename / Unit rename
    # ------------------------------------------------------------------

    async def rename_group(
        self, workspace_id: str, user_id: str, req: GroupRenameRequest
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False

            q = (
                select(StrategyUnit)
                .where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(req.unit_ids),
                )
            )
            result = await session.execute(q)
            units = list(result.scalars().all())

            for unit in units:
                unit.group_name = self._compute_rename(unit, req.mode, req.value, req.search, req.replace)

            await session.commit()
            return True

    async def rename_unit(
        self, workspace_id: str, user_id: str, req: UnitRenameRequest
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            unit = await self._get_unit(session, workspace_id, req.unit_id)
            if unit is None:
                return False
            unit.strategy_name = self._compute_rename(
                unit, req.mode, req.value, req.search, req.replace
            )
            await session.commit()
            return True

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
        from app.services.backtest_service import BacktestService

        backtest_service = BacktestService()
        results: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return []

            q = (
                select(StrategyUnit)
                .where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                )
            )
            db_result = await session.execute(q)
            units = list(db_result.scalars().all())

            if not units:
                return []

            # Mark all as queued
            for unit in units:
                unit.run_status = "queued"
            await session.commit()

            # Submit backtest for each unit, write back task_id immediately
            async def _submit_single(unit: StrategyUnit) -> dict[str, Any]:
                try:
                    bt_request = self._build_backtest_request(unit)
                    response = await backtest_service.run_backtest(user_id, bt_request)
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
                    return {"unit_id": unit.id, "task_id": None, "status": "failed", "error": str(e)}

            if parallel:
                results = list(await asyncio.gather(*[_submit_single(u) for u in units]))
            else:
                for unit in units:
                    results.append(await _submit_single(unit))

        # Fire-and-forget background polling for completion (Bug-1 fix)
        submitted = [(r["unit_id"], r["task_id"]) for r in results if r.get("task_id")]
        if submitted:
            asyncio.create_task(
                self._background_poll_units(
                    workspace_id, user_id, submitted, backtest_service
                )
            )

        return results

    async def stop_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Stop running units by cancelling their associated backtest tasks."""
        from app.services.backtest_service import BacktestService

        backtest_service = BacktestService()
        results: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return []

            q = (
                select(StrategyUnit)
                .where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                    StrategyUnit.run_status.in_(["running", "queued"]),
                )
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

            return [
                UnitStatusResponse(
                    id=u.id,
                    run_status=u.run_status or "idle",
                    last_task_id=u.last_task_id,
                    metrics_snapshot=u.metrics_snapshot or {},
                    run_count=u.run_count or 0,
                    last_run_time=u.last_run_time,
                )
                for u in units
            ]

    # ------------------------------------------------------------------
    # Optimization orchestration (Phase 4)
    # ------------------------------------------------------------------

    async def submit_unit_optimization(
        self, workspace_id: str, user_id: str, req: UnitOptimizationRequest
    ) -> dict[str, Any] | None:
        """Submit optimization for a strategy unit. Delegates to existing optimization service."""
        from app.services.optimization_execution_manager import get_optimization_execution_manager
        from app.services.param_optimization_service import generate_param_grid, submit_optimization

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

            submit_optimization(
                strategy_id=strategy_id,
                param_ranges=param_ranges,
                n_workers=req.n_workers,
                task_id=task_id,
                persist_to_db=True,
            )

            # Update unit with optimization task id — merge into existing config
            unit.last_optimization_task_id = task_id
            existing_oc = dict(unit.optimization_config or {})
            existing_oc.update({
                "param_ranges": param_ranges,
                "n_workers": req.n_workers,
                "mode": req.mode,
                "timeout": req.timeout,
                "task_id": task_id,
            })
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
        """Get optimization progress for a unit."""
        from app.services.param_optimization_service import get_optimization_progress

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            progress = get_optimization_progress(
                unit.last_optimization_task_id, user_id=user_id, use_db=True
            )
            return progress

    async def get_unit_optimization_results(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Get optimization results for a unit.

        The results are sorted by the unit's configured ``objective``
        (from ``optimization_config.objective``), defaulting to
        ``annual_return`` if not set.
        """
        from app.services.param_optimization_service import (
            _build_results_response,
            get_optimization_results,
        )
        from app.services.optimization_execution_manager import get_optimization_execution_manager

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            task_id = unit.last_optimization_task_id
            # Read user-configured objective from optimization_config
            oc = unit.optimization_config or {}
            objective = oc.get("objective", "annual_return") or "annual_return"

            # Try DB first
            mgr = get_optimization_execution_manager()
            db_task = await mgr.get_task(task_id, user_id=user_id)
            if db_task and db_task.results is not None:
                task_dict = {
                    "status": db_task.status,
                    "strategy_id": db_task.strategy_id,
                    "param_names": list((db_task.param_ranges or {}).keys()),
                    "total": db_task.total,
                    "completed": db_task.completed,
                    "failed": db_task.failed,
                    "results": db_task.results,
                }
                return _build_results_response(task_dict, task_id, objective=objective)

            return get_optimization_results(task_id, user_id=user_id, use_db=False)

    async def cancel_unit_optimization(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Cancel a running optimization task for a strategy unit."""
        from app.services.optimization_execution_manager import get_optimization_execution_manager

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return {"error": "No optimization task found for this unit"}

            task_id = unit.last_optimization_task_id
            mgr = get_optimization_execution_manager()
            cancelled = await mgr.cancel_task(task_id, user_id=user_id)
            return {"task_id": task_id, "cancelled": cancelled}

    async def apply_best_params(
        self, workspace_id: str, user_id: str, req: ApplyBestParamsRequest
    ) -> dict[str, Any] | None:
        """Apply best params from optimization result to a strategy unit."""
        from app.services.optimization_execution_manager import get_optimization_execution_manager

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, req.unit_id)
            if unit is None:
                return None

            mgr = get_optimization_execution_manager()
            db_task = await mgr.get_task(req.optimization_task_id, user_id=user_id)
            if not db_task or not db_task.results:
                return {"error": "Optimization results not found"}

            results = db_task.results
            if req.result_index >= len(results):
                return {"error": f"Result index {req.result_index} out of range"}

            best = results[req.result_index]
            best_params = best.get("params", {})

            # Merge into unit params
            current_params = unit.params or {}
            current_params.update(best_params)
            unit.params = current_params
            await session.commit()

            return {
                "unit_id": req.unit_id,
                "applied_params": best_params,
                "metrics": {k: v for k, v in best.items() if k != "params"},
            }

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

        Accepts optional config parameters (Bug-10 fix) so front-end settings
        actually influence the calculation.
        """
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=True)
            if ws is None:
                return None

            units = ws.strategy_units or []

            # --- Filter by date range (Bug-6 fix) ---
            def _unit_in_range(u: StrategyUnit) -> bool:
                """Return True if unit's data period overlaps the requested range."""
                dc = u.data_config or {}
                u_start = dc.get("start_date", "")
                u_end = dc.get("end_date", "")
                if start_date and u_end and u_end < start_date:
                    return False
                if end_date and u_start and u_start > end_date:
                    return False
                return True

            filtered_units = [u for u in units if _unit_in_range(u)]
            completed_units = [u for u in filtered_units if u.metrics_snapshot]

            # Extended metric keys for Iteration 124 report columns
            _ext_keys = [
                "total_return", "annual_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "total_trades", "profitable_trades", "losing_trades",
                "initial_cash", "final_value", "net_value", "net_profit",
                "max_leverage", "max_market_value", "max_drawdown_value",
                "adjusted_return_risk", "avg_profit", "avg_profit_rate",
                "total_win_amount", "total_loss_amount", "profit_loss_ratio",
                "profit_factor", "profit_rate_factor", "profit_loss_rate_ratio",
                "odds", "daily_avg_return", "daily_max_loss", "daily_max_profit",
                "weekly_avg_return", "weekly_max_loss", "weekly_max_profit",
                "monthly_avg_return", "monthly_max_loss", "monthly_max_profit",
                "trading_cost", "trading_days",
            ]

            # --- Build weight map (Bug-8 fix) ---
            # If weight_mode == "custom" but no explicit weights, auto-generate
            # from each unit's initial_cash proportion.
            _weights = weights or {}
            if weight_mode == "custom" and not _weights and completed_units:
                total_cash = sum(
                    (u.metrics_snapshot or {}).get("initial_cash", 0)
                    for u in completed_units
                )
                if total_cash > 0:
                    _weights = {
                        u.id: (u.metrics_snapshot or {}).get("initial_cash", 0) / total_cash
                        for u in completed_units
                    }

            # --- Helper: recalculate annual_return using provided annual_days
            #     and calc_method (Bug-7 fix) ---
            def _recalc_annual(m: dict[str, Any]) -> float | None:
                """Recalculate annual_return from total_return + trading_days."""
                tr = m.get("total_return")
                td = m.get("trading_days")
                if tr is None or not td or td <= 0:
                    return m.get("annual_return")
                if calc_method == "compound":
                    # compound: (1 + total_return)^(annual_days/trading_days) - 1
                    try:
                        return round(((1 + tr) ** (annual_days / td) - 1), 6)
                    except (OverflowError, ValueError):
                        return m.get("annual_return")
                else:
                    # simple: total_return * (annual_days / trading_days)
                    return round(tr * (annual_days / td), 6)

            # Per-unit metrics rows
            rows: list[dict[str, Any]] = []
            for u in filtered_units:
                m = u.metrics_snapshot or {}
                dc = u.data_config or {}
                row: dict[str, Any] = {
                    "id": u.id,
                    "strategy_name": u.strategy_name or u.strategy_id or "",
                    "symbol": u.symbol or "",
                    "symbol_name": u.symbol_name or "",
                    "timeframe": u.timeframe or "",
                    "group_name": u.group_name or "",
                    "category": u.category or "",
                    "run_status": u.run_status or "idle",
                    "run_count": u.run_count or 0,
                    "last_run_time": u.last_run_time,
                    "last_task_id": u.last_task_id,
                    "start_date": dc.get("start_date"),
                    "data_source": f"{u.symbol or ''}_{u.timeframe or ''}",
                }

                # Apply max_cash override
                if max_cash is not None and m:
                    row["initial_cash"] = max_cash
                else:
                    row["initial_cash"] = m.get("initial_cash")

                for k in _ext_keys:
                    if k == "initial_cash":
                        continue  # already handled above
                    row[k] = m.get(k)

                # Recalculate annual_return with user config
                if m:
                    row["annual_return"] = _recalc_annual(m)

                rows.append(row)

            # Weighted average helper
            def _weighted_avg(key: str) -> float | None:
                vals: list[tuple[float, float]] = []
                for u in completed_units:
                    m = u.metrics_snapshot or {}
                    if key == "annual_return":
                        v = _recalc_annual(m)
                    else:
                        v = m.get(key)
                    if v is None:
                        continue
                    w = _weights.get(u.id, 1.0) if weight_mode == "custom" and _weights else 1.0
                    vals.append((v, w))
                if not vals:
                    return None
                total_w = sum(w for _, w in vals)
                if total_w == 0:
                    return None
                return round(sum(v * w for v, w in vals) / total_w, 4)

            def _safe_sum(key: str) -> int | None:
                vals = [m.get(key) for u in completed_units if (m := u.metrics_snapshot) and m.get(key) is not None]
                return sum(vals) if vals else None

            summary = {
                "total_units": len(units),
                "completed_units": len(completed_units),
                "avg_total_return": _weighted_avg("total_return"),
                "avg_annual_return": _weighted_avg("annual_return"),
                "avg_sharpe_ratio": _weighted_avg("sharpe_ratio"),
                "avg_max_drawdown": _weighted_avg("max_drawdown"),
                "avg_win_rate": _weighted_avg("win_rate"),
                "total_trades": _safe_sum("total_trades"),
                "best_return_unit": max(
                    completed_units,
                    key=lambda u: (u.metrics_snapshot or {}).get("total_return", float("-inf")),
                    default=None,
                ),
                "worst_drawdown_unit": max(
                    completed_units,
                    key=lambda u: abs((u.metrics_snapshot or {}).get("max_drawdown", 0)),
                    default=None,
                ),
                # Echo config so frontend knows what was used
                "config": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_cash": max_cash,
                    "calc_method": calc_method,
                    "annual_days": annual_days,
                    "weight_mode": weight_mode,
                },
            }
            # Serialize unit references in summary
            for key in ("best_return_unit", "worst_drawdown_unit"):
                u = summary[key]
                if u is not None:
                    summary[key] = {
                        "id": u.id,
                        "strategy_name": u.strategy_name or u.strategy_id or "",
                        "symbol": u.symbol or "",
                        "value": (u.metrics_snapshot or {}).get(
                            "total_return" if key == "best_return_unit" else "max_drawdown"
                        ),
                    }

            return {
                "workspace_id": workspace_id,
                "workspace_name": ws.name,
                "summary": summary,
                "units": rows,
            }

    async def delete_workspace_report(
        self, workspace_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Clear cached report config on the workspace.

        NOTE: This no longer wipes unit ``metrics_snapshot`` (which are run
        results, not report artefacts).  It only resets the saved report
        configuration stored in ``workspace.settings.report_config`` so that
        the next GET /report returns a fresh default-config aggregation.
        """
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            settings = dict(ws.settings or {})
            had_config = "report_config" in settings
            settings.pop("report_config", None)
            ws.settings = settings
            await session.commit()
            return {
                "workspace_id": workspace_id,
                "cleared": had_config,
                "message": "报告缓存配置已清除，单元运行指标未受影响",
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_backtest_request(unit: StrategyUnit) -> BacktestRequest:
        """Build a BacktestRequest from a strategy unit's configuration."""
        settings = unit.unit_settings or {}
        data_cfg = unit.data_config or {}
        params = unit.params or {}

        return BacktestRequest(
            strategy_id=unit.strategy_id or "",
            symbol=unit.symbol or data_cfg.get("symbol", ""),
            start_date=data_cfg.get("start_date", "2023-01-01T00:00:00"),
            end_date=data_cfg.get("end_date", "2024-01-01T00:00:00"),
            initial_cash=settings.get("initial_cash", 100000),
            commission=settings.get("commission", 0.001),
            timeframe=unit.timeframe or "1d",
            timeframe_n=unit.timeframe_n or 1,
            bar_count=unit.bar_count,
            params=params,
        )

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
            final_status = await self._poll_task_completion(
                backtest_service, task_id, user_id
            )
            elapsed = time.monotonic() - start_ts

            async with async_session_maker() as s:
                u = await self._get_unit(s, workspace_id, unit_id)
                if u:
                    u.run_count = (u.run_count or 0) + 1
                    u.last_run_time = round(elapsed, 2)
                    if final_status == TaskStatus.COMPLETED:
                        u.run_status = "completed"
                        bt_result = await backtest_service.get_result(task_id, user_id)
                        if bt_result:
                            from app.services.fincore_metrics_helper import calculate_extended_metrics
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
                                u.metrics_snapshot = metrics
                                u.bar_count = len(bt_result.equity_curve or [])
                            except Exception as me:
                                logger.warning("Extended metrics failed for unit %s: %s", unit_id, me)
                                u.metrics_snapshot = {
                                    "total_return": bt_result.total_return,
                                    "annual_return": bt_result.annual_return,
                                    "sharpe_ratio": bt_result.sharpe_ratio,
                                    "max_drawdown": bt_result.max_drawdown,
                                    "win_rate": bt_result.win_rate,
                                    "total_trades": bt_result.total_trades,
                                }
                    elif final_status == TaskStatus.CANCELLED:
                        u.run_status = "cancelled"
                    else:
                        u.run_status = "failed"
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
    def _unit_to_dict(unit: StrategyUnit) -> dict[str, Any]:
        return {
            "id": unit.id,
            "workspace_id": unit.workspace_id,
            "group_name": unit.group_name or "",
            "strategy_id": unit.strategy_id,
            "strategy_name": unit.strategy_name or "",
            "symbol": unit.symbol or "",
            "symbol_name": unit.symbol_name or "",
            "timeframe": unit.timeframe or "1d",
            "timeframe_n": unit.timeframe_n or 1,
            "category": unit.category or "",
            "sort_order": unit.sort_order or 0,
            "data_config": unit.data_config or {},
            "unit_settings": unit.unit_settings or {},
            "params": unit.params or {},
            "optimization_config": unit.optimization_config or {},
            "run_status": unit.run_status or "idle",
            "run_count": unit.run_count or 0,
            "last_run_time": unit.last_run_time,
            "last_task_id": unit.last_task_id,
            "last_optimization_task_id": unit.last_optimization_task_id,
            "bar_count": unit.bar_count,
            "metrics_snapshot": unit.metrics_snapshot or {},
            "created_at": unit.created_at.isoformat() if unit.created_at else None,
            "updated_at": unit.updated_at.isoformat() if unit.updated_at else None,
        }

    @staticmethod
    def _compute_rename(
        unit: StrategyUnit,
        mode: str,
        value: str,
        search: str,
        replace: str,
    ) -> str:
        if mode == "custom":
            return value
        elif mode == "strategy":
            return unit.strategy_name or ""
        elif mode == "symbol":
            return unit.symbol or ""
        elif mode == "symbol_name":
            return unit.symbol_name or ""
        elif mode == "category":
            return unit.category or ""
        elif mode == "replace":
            current = unit.group_name or ""
            return current.replace(search, replace) if search else current
        return value
