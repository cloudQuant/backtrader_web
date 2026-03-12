"""
Parameter optimization API routes.

Provides:
- POST /submit: submit an optimization task
- GET  /progress/{task_id}: query progress
- GET  /results/{task_id}: fetch results
- POST /cancel/{task_id}: cancel a task
- GET  /strategy-params/{strategy_id}: fetch default params
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.param_optimization_service import (
    _build_results_response as _build_optimization_results_response,
)
from app.services.param_optimization_service import (
    cancel_optimization,
    get_optimization_progress,
    get_optimization_results,
    submit_optimization,
)
from app.services.strategy_service import get_template_by_id

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Schemas ----


class ParamRangeSpec(BaseModel):
    """Specification for a parameter range in optimization.

    Attributes:
        start: Start value of the range.
        end: End value of the range.
        step: Step size for incrementing the value.
        type: Data type (int or float).
    """

    start: float
    end: float
    step: float
    type: str = "float"  # int or float


class OptimizationSubmitRequest(BaseModel):
    """Request schema for submitting an optimization task.

    Attributes:
        strategy_id: The ID of the strategy to optimize.
        param_ranges: Dictionary mapping parameter names to their range specs.
        n_workers: Number of parallel worker processes (1-32).
    """

    strategy_id: str
    param_ranges: dict[str, ParamRangeSpec]
    n_workers: int = Field(default=4, ge=1, le=32)


class OptimizationSubmitResponse(BaseModel):
    """Response schema for optimization task submission.

    Attributes:
        task_id: The unique identifier of the created task.
        total_combinations: Total number of parameter combinations to test.
        message: Human-readable status message.
    """

    task_id: str
    total_combinations: int
    message: str


# ---- Endpoints ----


@router.get("/strategy-params/{strategy_id}", summary="Get strategy default parameters")
async def get_strategy_params(
    strategy_id: str,
    current_user=Depends(get_current_user),
):
    """Return strategy parameter specifications (name/type/default/description).

    Args:
        strategy_id: The unique identifier of the strategy.
        current_user: The authenticated user.

    Returns:
        A dictionary containing strategy_id, strategy_name, and params list.

    Raises:
        HTTPException: If the strategy does not exist (404).
    """
    tpl = get_template_by_id(strategy_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    params = []
    for name, spec in tpl.params.items():
        params.append(
            {
                "name": name,
                "type": spec.type,
                "default": spec.default,
                "description": spec.description or name,
            }
        )

    return {"strategy_id": strategy_id, "strategy_name": tpl.name, "params": params}


@router.post(
    "/submit", response_model=OptimizationSubmitResponse, summary="Submit optimization task"
)
async def submit_optimization_task(
    request: OptimizationSubmitRequest,
    current_user=Depends(get_current_user),
):
    """Submit an optimization task and return a task ID.

    Args:
        request: The optimization task request containing strategy_id,
            param_ranges, and n_workers.
        current_user: The authenticated user.

    Returns:
        OptimizationSubmitResponse: Response containing task_id,
            total_combinations, and a message.

    Raises:
        HTTPException: If strategy not found (404) or parameter grid is empty (400).
    """
    from app.services.param_optimization_service import generate_param_grid

    # Validate strategy
    tpl = get_template_by_id(request.strategy_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Strategy {request.strategy_id} not found")

    # Build param_ranges dict
    param_ranges = {}
    for name, spec in request.param_ranges.items():
        param_ranges[name] = {
            "start": spec.start,
            "end": spec.end,
            "step": spec.step,
            "type": spec.type,
        }

    # Pre-calculate combination count
    grid = generate_param_grid(param_ranges)
    if not grid:
        raise HTTPException(
            status_code=400, detail="Parameter grid is empty, please check parameter ranges"
        )

    from app.services.optimization_execution_manager import (
        get_optimization_execution_manager,
    )

    try:
        # Create persisted task in DB first
        mgr = get_optimization_execution_manager()
        db_task = await mgr.create_task(
            user_id=current_user.sub,
            strategy_id=request.strategy_id,
            total=len(grid),
            param_ranges=param_ranges,
            n_workers=request.n_workers,
        )
        task_id = db_task.id

        submit_optimization(
            strategy_id=request.strategy_id,
            param_ranges=param_ranges,
            n_workers=request.n_workers,
            task_id=task_id,
            persist_to_db=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return OptimizationSubmitResponse(
        task_id=task_id,
        total_combinations=len(grid),
        message=f"Optimization task submitted, total {len(grid)} parameter combinations, using {request.n_workers} workers",
    )


@router.get("/progress/{task_id}", summary="Query optimization progress")
async def get_progress(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """Return current progress of an optimization task.

    Task may be in DB (persisted) or in-memory. Ownership is enforced via user_id.
    Uses results endpoint for data access control.

    Args:
        task_id: The unique identifier of the optimization task.
        current_user: The authenticated user.

    Returns:
        A dictionary containing task progress information.

    Raises:
        HTTPException: If the task does not exist (404).
    """
    from app.services.optimization_execution_manager import (
        get_optimization_execution_manager,
    )

    mgr = get_optimization_execution_manager()
    db_task = await mgr.get_task(task_id, user_id=current_user.sub)
    if db_task:
        total = db_task.total or 0
        done = (db_task.completed or 0) + (db_task.failed or 0)
        return {
            "task_id": task_id,
            "status": db_task.status,
            "strategy_id": db_task.strategy_id,
            "total": total,
            "completed": db_task.completed or 0,
            "failed": db_task.failed or 0,
            "progress": round(done / total * 100, 1) if total > 0 else 0,
            "n_workers": db_task.n_workers or 4,
            "created_at": db_task.created_at.isoformat() if db_task.created_at else "",
        }
    progress = get_optimization_progress(task_id, user_id=current_user.sub, use_db=False)
    if not progress:
        raise HTTPException(status_code=404, detail="Optimization task not found")
    return progress


@router.get("/results/{task_id}", summary="Get optimization results")
async def get_results(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """Return full results of an optimization task.

    Args:
        task_id: The unique identifier of the optimization task.
        current_user: The authenticated user.

    Returns:
        A dictionary containing the optimization results.

    Raises:
        HTTPException: If the task does not exist (404).
    """
    from app.services.optimization_execution_manager import (
        get_optimization_execution_manager,
    )

    mgr = get_optimization_execution_manager()
    db_task = await mgr.get_task(task_id, user_id=current_user.sub)
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
        results = _build_optimization_results_response(task_dict, task_id)
        return results
    results = get_optimization_results(task_id, user_id=current_user.sub, use_db=False)
    if not results:
        raise HTTPException(status_code=404, detail="Optimization task not found")
    return results


@router.post("/cancel/{task_id}", summary="Cancel optimization task")
async def cancel_task(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """Cancel a running optimization task.

    Cancellation is persisted to DB for cross-instance visibility. If the task
    runs on another instance, it will stop when it checks the DB.

    Args:
        task_id: The unique identifier of the optimization task.
        current_user: The authenticated user.

    Returns:
        A message confirming cancellation request.

    Raises:
        HTTPException: If the task does not exist (404).
    """
    from app.services.optimization_execution_manager import (
        get_optimization_execution_manager,
    )

    mgr = get_optimization_execution_manager()
    ok_db = await mgr.set_cancelled(task_id, user_id=current_user.sub)
    ok_mem = cancel_optimization(task_id, user_id=current_user.sub, use_db=False)
    if not ok_db and not ok_mem:
        raise HTTPException(status_code=404, detail="Optimization task not found")
    return {"message": "Cancellation requested", "task_id": task_id}
