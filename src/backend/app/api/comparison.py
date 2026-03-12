"""
Backtest comparison API routes.

Supports comparing and analyzing multiple backtest results.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.schemas.comparison import (
    ComparisonCreate,
    ComparisonDetail,
    ComparisonListResponse,
    ComparisonResponse,
    ComparisonUpdate,
)
from app.services.comparison_service import ComparisonService

logger = logging.getLogger(__name__)

router = APIRouter()


def get_comparison_service():
    """Dependency injection for ComparisonService.

    Returns:
        ComparisonService: An instance of the comparison service.
    """
    return ComparisonService()


# ==================== Comparison API ====================


@router.post("/", response_model=ComparisonResponse, summary="Create backtest comparison")
async def create_comparison(
    request: ComparisonCreate,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Create a new backtest comparison.

    Args:
        request: The comparison creation request containing name, description,
            backtest_task_ids, and type.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        ComparisonResponse: The created comparison details.
    """
    comparison = await service.create_comparison(
        user_id=current_user.sub,
        name=request.name,
        description=request.description,
        backtest_task_ids=request.backtest_task_ids,
        comparison_type=request.type,
        is_public=False,
    )

    return comparison


@router.get(
    "/{comparison_id}", response_model=ComparisonDetail, summary="Get backtest comparison details"
)
async def get_comparison_detail(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Get comparison detail by ID.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        ComparisonDetail: The comparison details.

    Raises:
        HTTPException: If the comparison does not exist (404) or user lacks
            permission to access it (403).
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")

    # Check permissions
    if comparison.user_id != current_user.sub and not comparison.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this comparison"
        )

    return comparison


@router.put(
    "/{comparison_id}", response_model=ComparisonResponse, summary="Update backtest comparison"
)
async def update_comparison(
    comparison_id: str,
    request: ComparisonUpdate,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Update a backtest comparison.

    Args:
        comparison_id: The unique identifier of the comparison.
        request: The update request containing fields to modify.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        ComparisonResponse: The updated comparison details.

    Raises:
        HTTPException: If the comparison does not exist or user lacks permission (404).
    """
    comparison = await service.update_comparison(
        comparison_id=comparison_id,
        user_id=current_user.sub,
        update_data=request.model_dump(exclude_none=True),
    )

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparison not found or no permission to update",
        )

    return comparison


@router.delete("/{comparison_id}", summary="Delete backtest comparison")
async def delete_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Delete a backtest comparison.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A message confirming deletion.

    Raises:
        HTTPException: If the comparison does not exist or user lacks permission (404).
    """
    success = await service.delete_comparison(comparison_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comparison not found or no permission to delete",
        )

    return {"message": "Comparison deleted successfully"}


@router.get("/", response_model=ComparisonListResponse, summary="List backtest comparisons")
async def list_comparisons(
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_public: bool | None = Query(None, description="Filter by public status"),
):
    """Get the list of backtest comparisons.

    Args:
        current_user: The authenticated user.
        service: The comparison service.
        limit: Maximum number of comparisons to return (1-100).
        offset: Number of comparisons to skip.
        is_public: Filter to show only public comparisons (optional).

    Returns:
        ComparisonListResponse: Response containing total count and comparison list.
    """
    comparisons, total = await service.list_comparisons(
        user_id=current_user.sub,
        limit=limit,
        offset=offset,
        is_public=is_public,
    )

    return ComparisonListResponse(total=total, items=comparisons)


@router.post("/{comparison_id}/toggle-favorite", summary="Toggle favorite status")
async def toggle_comparison_favorite(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Toggle the favorite status of a comparison.

    Adds or removes the comparison from the user's favorites list.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A dictionary containing comparison_id and the updated is_favorite status.

    Raises:
        HTTPException: If the comparison does not exist (404).
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")

    # Toggle favorite status
    comparison.is_favorite = not comparison.is_favorite

    # Update
    updated_comparison = await service.update_comparison(
        comparison_id=comparison_id,
        user_id=current_user.sub,
        update_data={"is_favorite": comparison.is_favorite},
    )

    return {
        "comparison_id": comparison_id,
        "is_favorite": updated_comparison.is_favorite,
    }


@router.post("/{comparison_id}/share", summary="Share backtest comparison")
async def share_comparison(
    comparison_id: str,
    request: dict,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Share a backtest comparison with other users.

    Args:
        comparison_id: The unique identifier of the comparison.
        request: The share request containing shared_with_user_ids list.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A message confirming the comparison has been shared.

    Raises:
        HTTPException: If the comparison does not exist (404) or user lacks
            permission to share (403).
    """
    _shared_with_user_ids = request.get("shared_with_user_ids", [])

    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")

    # Check permissions
    if comparison.user_id != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No permission to share this comparison"
        )

    # TODO: Implement share logic
    # await service.share_comparison(comparison_id, current_user.sub, shared_with_user_ids)

    return {
        "comparison_id": comparison_id,
        "message": "Comparison shared successfully",
    }


# ==================== Comparison Data API ====================


async def _get_comparison_or_404(
    comparison_id: str,
    user_id: str,
    service: ComparisonService,
) -> Any:
    """Get comparison data or return 404 if not found.

    Args:
        comparison_id: The unique identifier of the comparison.
        user_id: The authenticated user's ID.
        service: The comparison service.

    Returns:
        The comparison data.

    Raises:
        HTTPException: If the comparison does not exist (404).
    """
    comparison = await service.get_comparison(comparison_id, user_id)

    if not comparison:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comparison not found")

    return comparison


@router.get("/{comparison_id}/metrics", summary="Get metrics comparison data")
async def get_metrics_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Get metrics comparison data for multiple backtests.

    Returns comparison of metrics including total return, annualized return,
    Sharpe ratio, maximum drawdown, win rate, etc.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A dictionary containing comparison_id and metrics_comparison data.
    """
    comparison = await _get_comparison_or_404(comparison_id, current_user.sub, service)

    return {
        "comparison_id": comparison_id,
        "metrics_comparison": comparison.comparison_data.get("metrics_comparison", {}),
    }


@router.get("/{comparison_id}/equity", summary="Get equity curve comparison data")
async def get_equity_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Get equity curve comparison data for multiple backtests.

    Returns equity curve data for each backtest, suitable for plotting.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A dictionary containing comparison_id and equity_comparison data.
    """
    comparison = await _get_comparison_or_404(comparison_id, current_user.sub, service)

    return {
        "comparison_id": comparison_id,
        "equity_comparison": comparison.comparison_data.get("equity_comparison", {}),
    }


@router.get("/{comparison_id}/trades", summary="Get trades comparison data")
async def get_trades_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Get trades comparison data for multiple backtests.

    Returns comparison of trade statistics including trade count, PnL, etc.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A dictionary containing comparison_id and trades_comparison data.
    """
    comparison = await _get_comparison_or_404(comparison_id, current_user.sub, service)

    return {
        "comparison_id": comparison_id,
        "trades_comparison": comparison.comparison_data.get("trades_comparison", {}),
    }


@router.get("/{comparison_id}/drawdown", summary="Get drawdown comparison data")
async def get_drawdown_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """Get drawdown comparison data for multiple backtests.

    Returns drawdown curve data for each backtest.

    Args:
        comparison_id: The unique identifier of the comparison.
        current_user: The authenticated user.
        service: The comparison service.

    Returns:
        A dictionary containing comparison_id and drawdown_comparison data.
    """
    comparison = await _get_comparison_or_404(comparison_id, current_user.sub, service)

    return {
        "comparison_id": comparison_id,
        "drawdown_comparison": comparison.comparison_data.get("drawdown_comparison", {}),
    }
