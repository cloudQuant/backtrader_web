"""Strategy score API routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.schemas.strategy_score import StrategyScoreRequest, StrategyScoreResponse
from app.services.strategy_score import StrategyScoreService

router = APIRouter()


@lru_cache
def get_strategy_score_service() -> StrategyScoreService:
    """Return singleton strategy score service."""
    return StrategyScoreService()


@router.post("/score", response_model=StrategyScoreResponse, summary="Create strategy score")
async def create_strategy_score(
    data: StrategyScoreRequest,
    current_user=Depends(get_current_user),
    service: StrategyScoreService = Depends(get_strategy_score_service),
):
    """Create or refresh a strategy score."""
    try:
        return await service.score_backtest(
            backtest_id=data.backtest_id,
            user_id=current_user.sub,
            backtest_result=data.backtest_result,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/score/{backtest_id}", response_model=StrategyScoreResponse, summary="Get strategy score")
async def get_strategy_score(
    backtest_id: str,
    current_user=Depends(get_current_user),
    service: StrategyScoreService = Depends(get_strategy_score_service),
):
    """Get persisted strategy score by backtest id."""
    result = await service.get_score_by_backtest_id(backtest_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(status_code=404, detail="Strategy score not found")
    return result
