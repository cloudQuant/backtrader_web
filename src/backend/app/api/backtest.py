"""
Backtest API routes.
"""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
)
from app.services.backtest_service import BacktestService

router = APIRouter()


@lru_cache
def get_backtest_service():
    return BacktestService()


@router.post("/run", response_model=BacktestResponse, summary="Run backtest")
async def run_backtest(
    request: BacktestRequest,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Submit a backtest task.

    Args:
        request: Backtest request payload.
        current_user: Authenticated user.
        service: Backtest service dependency.

    Returns:
        A task response containing task_id and initial status.
    """
    result = await service.run_backtest(current_user.sub, request)
    return result


@router.get("/{task_id}", response_model=BacktestResult, summary="Get backtest result")
async def get_backtest_result(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get a backtest result by task ID.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.
        service: Backtest service dependency.

    Returns:
        BacktestResult if found and authorized.

    Raises:
        HTTPException: If result not found (404).
    """
    result = await service.get_result(task_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found",
        )
    return result


@router.get("/{task_id}/status", summary="Get backtest task status")
async def get_backtest_status(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get a backtest task status by task ID.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.
        service: Backtest service dependency.

    Returns:
        Dictionary containing task_id and status.

    Raises:
        HTTPException: If task not found (404).
    """
    task_status = await service.get_task_status(task_id, user_id=current_user.sub)
    if task_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return {"task_id": task_id, "status": task_status}


@router.get("/", response_model=BacktestListResponse, summary="List backtest history")
async def list_backtests(
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
    limit: int = Query(20, ge=1, le=100, description="Max number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query("created_at", description="Sort field: created_at/strategy_id/symbol"),
    sort_order: str = Query("desc", description="Sort direction: asc/desc"),
):
    """List backtest history for the current user (supports sorting).

    Args:
        current_user: Authenticated user.
        service: Backtest service dependency.
        limit: Maximum number of results to return (1-100).
        offset: Number of results to skip.
        sort_by: Field to sort by.
        sort_order: Sort direction (asc or desc).

    Returns:
        BacktestListResponse containing total count and list of results.
    """
    results = await service.list_results(
        current_user.sub, limit, offset,
        sort_by=sort_by, sort_desc=(sort_order == "desc"),
    )
    return results


@router.post("/{task_id}/cancel", summary="Cancel backtest task")
async def cancel_backtest(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Cancel a running backtest task.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.
        service: Backtest service dependency.

    Returns:
        Success message with task_id.

    Raises:
        HTTPException: If cancellation fails (400).
    """
    success = await service.cancel_task(task_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task not found, unauthorized, or already completed",
        )
    return {"message": "Task cancelled", "task_id": task_id}


@router.delete("/{task_id}", summary="Delete backtest result")
async def delete_backtest(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Delete a backtest result.

    Args:
        task_id: The unique identifier for the backtest task.
        current_user: Authenticated user.
        service: Backtest service dependency.

    Returns:
        Success message.

    Raises:
        HTTPException: If deletion fails (404).
    """
    success = await service.delete_result(task_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest result not found or unauthorized",
        )
    return {"message": "Deleted successfully"}
