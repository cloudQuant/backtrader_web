"""
Backtest API routes.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, Query, Response

from app.api.backtest_enhanced import cancel_backtest as cancel_backtest_primary
from app.api.backtest_enhanced import delete_backtest as delete_backtest_primary
from app.api.backtest_enhanced import get_backtest_result as get_backtest_result_primary
from app.api.backtest_enhanced import get_backtest_status as get_backtest_status_primary
from app.api.backtest_enhanced import list_backtests as list_backtests_primary
from app.api.backtest_enhanced import run_backtest as run_backtest_primary
from app.api.deps import get_current_user, mark_deprecated
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
)
from app.services.backtest_service import BacktestService

router = APIRouter()
_DEPRECATED_SUCCESSOR = "/api/v1/backtests"


@lru_cache
def get_backtest_service():
    return BacktestService()


@router.post("/run", response_model=BacktestResponse, summary="Run backtest")
async def run_backtest(
    request: BacktestRequest,
    response: Response,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Submit a backtest task.

    .. deprecated:: 1.0.0
        Use :func:`app.api.backtest_enhanced.run_backtest` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "backtest")
    return await run_backtest_primary(request, current_user, service)


@router.get("/{task_id}", response_model=BacktestResult, summary="Get backtest result")
async def get_backtest_result(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get a backtest result by task ID.

    .. deprecated:: 1.0.0
        Use :func:`app.api.backtest_enhanced.get_backtest_result` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "backtest")
    return await get_backtest_result_primary(task_id, current_user, service)


@router.get("/{task_id}/status", summary="Get backtest task status")
async def get_backtest_status(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Get a backtest task status by task ID.

    .. deprecated:: 1.0.0
        Use :func:`app.api.backtest_enhanced.get_backtest_status` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "backtest")
    return await get_backtest_status_primary(task_id, current_user, service)


@router.get("/", response_model=BacktestListResponse, summary="List backtest history")
async def list_backtests(
    response: Response,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
    limit: int = Query(20, ge=1, le=100, description="Max number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query("created_at", description="Sort field: created_at/strategy_id/symbol"),
    sort_order: str = Query("desc", description="Sort direction: asc/desc"),
):
    """List backtest history for the current user (supports sorting).

    .. deprecated:: 1.0.0
        Use :func:`app.api.backtest_enhanced.list_backtests` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "backtest")
    return await list_backtests_primary(
        current_user,
        service,
        limit,
        offset,
        sort_by,
        sort_order,
    )


@router.post("/{task_id}/cancel", summary="Cancel backtest task")
async def cancel_backtest(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Cancel a running backtest task.

    .. deprecated:: 1.0.0
        Use :func:`app.api.backtest_enhanced.cancel_backtest` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "backtest")
    return await cancel_backtest_primary(task_id, current_user, service)


@router.delete("/{task_id}", summary="Delete backtest result")
async def delete_backtest(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """Delete a backtest result.

    .. deprecated:: 1.0.0
        Use :func:`app.api.backtest_enhanced.delete_backtest` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "backtest")
    return await delete_backtest_primary(task_id, current_user, service)
