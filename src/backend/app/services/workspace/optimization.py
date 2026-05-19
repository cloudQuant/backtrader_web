"""Workspace optimization query operations.

Handles progress, results, cancel, apply-best-params, and artifact-metadata
lookups for unit-level optimization tasks. The heavy ``submit_unit_optimization``
and ``get_unit_optimization_result_payload`` remain on
:class:`app.services.workspace_service.WorkspaceService` because they depend on
``_build_optimization_trial_payload`` (150-line static method) and runtime-dir
sync logic.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from app.db.database import async_session_maker
from app.schemas.workspace import ApplyBestParamsRequest
from app.services.optimization_execution_manager import get_optimization_execution_manager
from app.services.optimization_task_state import build_results_response
from app.services.param_optimization_service import (
    get_optimization_progress,
    get_optimization_results,
)
from app.services.workspace._helpers import build_optimization_artifact_metadata

logger = logging.getLogger(__name__)


async def get_unit_optimization_result_artifact_metadata(
    workspace_id: str,
    user_id: str,
    unit_id: str,
    result_index: int,
) -> dict[str, Any] | None:
    """Return artifact metadata for a specific optimization result row."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
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
        return build_optimization_artifact_metadata(task_id, result_index, result_entry)


async def get_unit_optimization_progress(
    workspace_id: str, user_id: str, unit_id: str
) -> dict[str, Any] | None:
    """Get optimization progress for a unit."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return None

        return get_optimization_progress(
            unit.last_optimization_task_id, user_id=user_id, use_db=True
        )


async def get_unit_optimization_results(
    workspace_id: str, user_id: str, unit_id: str
) -> dict[str, Any] | None:
    """Get optimization results for a unit, sorted by configured objective."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return None

        task_id = unit.last_optimization_task_id
        oc = unit.optimization_config or {}
        objective_key = oc.get("objective", "sharpe_max") or "sharpe_max"
        objective_map = {
            "sharpe_max": "sharpe_ratio",
            "max_return": "annual_return",
            "min_drawdown": "max_drawdown",
        }
        objective = objective_map.get(str(objective_key), str(objective_key))
        reverse_sort = objective != "max_drawdown"

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
            results_response = build_results_response(task_id, task_dict)
            rows = list(results_response.get("rows") or [])
            rows.sort(
                key=lambda row: row.get(objective, 999999 if not reverse_sort else -999999),
                reverse=reverse_sort,
            )
            results_response["rows"] = rows
            results_response["best"] = rows[0] if rows else None
            results_response["objective"] = objective
            return results_response

        results_response = get_optimization_results(task_id, user_id=user_id, use_db=False)
        if results_response:
            rows = list(results_response.get("rows") or [])
            rows.sort(
                key=lambda row: row.get(objective, 999999 if not reverse_sort else -999999),
                reverse=reverse_sort,
            )
            results_response["rows"] = rows
            results_response["best"] = rows[0] if rows else None
            results_response["objective"] = objective
        return results_response


async def cancel_unit_optimization(
    workspace_id: str, user_id: str, unit_id: str
) -> dict[str, Any] | None:
    """Cancel a running optimization task for a strategy unit."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return {"error": "No optimization task found for this unit"}

        task_id = unit.last_optimization_task_id
        mgr = get_optimization_execution_manager()
        cancelled = await mgr.set_cancelled(task_id, user_id=user_id)
        return {"task_id": task_id, "cancelled": cancelled}


async def apply_best_params(
    workspace_id: str, user_id: str, req: ApplyBestParamsRequest
) -> dict[str, Any] | None:
    """Apply best params from optimization result to a strategy unit."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, req.unit_id)
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

        current_params = unit.params or {}
        current_params.update(best_params)
        unit.params = current_params
        await session.commit()

        return {
            "unit_id": req.unit_id,
            "applied_params": best_params,
            "metrics": {k: v for k, v in best.items() if k != "params"},
        }
