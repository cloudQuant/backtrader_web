"""Strategy explainer API routes."""

from __future__ import annotations

import typing
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.schemas.strategy_explanation import StrategyExplainRequest, StrategyExplanation
from app.services.strategy_explainer import StrategyExplainerService

router = APIRouter()


@lru_cache
def get_strategy_explainer_service() -> StrategyExplainerService:
    """Return singleton strategy explainer service."""
    return StrategyExplainerService()


@router.post("/explain", response_model=StrategyExplanation, summary="Explain strategy code")
async def explain_strategy(
    data: StrategyExplainRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyExplainerService = Depends(get_strategy_explainer_service),
) -> typing.Any:
    """Explain a strategy from code, strategy id, or backtest id."""
    try:
        return await service.explain(data, user_id=current_user.sub)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/explain/cached/{code_hash}",
    response_model=StrategyExplanation,
    summary="Get cached strategy explanation",
)
async def get_cached_strategy_explanation(
    code_hash: str,
    current_user: typing.Any = Depends(get_current_user),
    service: StrategyExplainerService = Depends(get_strategy_explainer_service),
) -> typing.Any:
    """Get cached strategy explanation by code hash."""
    result = await service.get_cached_explanation(code_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="Strategy explanation not found")
    return result
