"""Performance attribution API routes."""

from functools import lru_cache

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.perf_attribution import (
    BrinsonAttributionRequest,
    BrinsonAttributionResult,
    FamaFrenchAttributionRequest,
    FamaFrenchAttributionResult,
)
from app.services.perf_attribution import BrinsonAttributionService, FamaFrenchAttributionService

router = APIRouter(prefix="/perf-attribution", tags=["Performance Attribution"])


@lru_cache
def get_brinson_attribution_service() -> BrinsonAttributionService:
    """Return cached Brinson attribution service dependency."""
    return BrinsonAttributionService()


@lru_cache
def get_fama_french_attribution_service() -> FamaFrenchAttributionService:
    """Return cached Fama-French attribution service dependency."""
    return FamaFrenchAttributionService()


@router.post("/brinson", response_model=BrinsonAttributionResult, summary="Calculate Brinson attribution")
async def calculate_brinson_attribution(
    request: BrinsonAttributionRequest,
    current_user=Depends(get_current_user),
    service: BrinsonAttributionService = Depends(get_brinson_attribution_service),
) -> BrinsonAttributionResult:
    """Calculate Brinson attribution effects."""
    return service.calculate(
        portfolio_weights=request.portfolio_weights,
        benchmark_weights=request.benchmark_weights,
        portfolio_returns=request.portfolio_returns,
        benchmark_returns=request.benchmark_returns,
    )


@router.post(
    "/fama-french",
    response_model=FamaFrenchAttributionResult,
    summary="Calculate Fama-French attribution",
)
async def calculate_fama_french_attribution(
    request: FamaFrenchAttributionRequest,
    current_user=Depends(get_current_user),
    service: FamaFrenchAttributionService = Depends(get_fama_french_attribution_service),
) -> FamaFrenchAttributionResult:
    """Estimate Fama-French three-factor attribution."""
    return service.calculate(
        strategy_returns=request.strategy_returns,
        market_returns=request.market_returns,
        smb_returns=request.smb_returns,
        hml_returns=request.hml_returns,
    )
