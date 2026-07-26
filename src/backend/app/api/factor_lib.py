"""Factor library API routes."""

import typing
from functools import lru_cache

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.factor_lib import (
    CustomFactorRequest,
    CustomFactorResult,
    FactorCorrelationRequest,
    FactorCorrelationResult,
    FactorEvaluationRequest,
    FactorEvaluationResult,
)
from app.services.factor_lib import CustomFactorService, FactorCorrelationService, FactorEvaluator

router = APIRouter(prefix="/factor-lib", tags=["Factor Library"])


@lru_cache
def get_factor_evaluator() -> FactorEvaluator:
    """Return cached factor evaluator dependency."""
    return FactorEvaluator()


@lru_cache
def get_factor_correlation_service() -> FactorCorrelationService:
    """Return cached factor correlation service dependency."""
    return FactorCorrelationService()


@lru_cache
def get_custom_factor_service() -> CustomFactorService:
    """Return cached custom factor service dependency."""
    return CustomFactorService()


@router.post("/evaluate", response_model=FactorEvaluationResult, summary="Evaluate factor IC/IR")
async def evaluate_factor(
    request: FactorEvaluationRequest,
    current_user: typing.Any = Depends(get_current_user),
    evaluator: FactorEvaluator = Depends(get_factor_evaluator),
) -> FactorEvaluationResult:
    """Evaluate a factor value series against future returns."""
    return evaluator.evaluate(
        factor_values=request.factor_values,
        future_returns=request.future_returns,
        quantiles=request.quantiles,
    )


@router.post(
    "/correlation",
    response_model=FactorCorrelationResult,
    summary="Analyze factor correlation",
)
async def analyze_factor_correlation(
    request: FactorCorrelationRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: FactorCorrelationService = Depends(get_factor_correlation_service),
) -> FactorCorrelationResult:
    """Analyze correlation between factor value series."""
    return service.analyze(request.factor_values, threshold=request.threshold)


@router.post(
    "/custom/calculate",
    response_model=CustomFactorResult,
    summary="Calculate custom factor values",
)
async def calculate_custom_factor(
    request: CustomFactorRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: CustomFactorService = Depends(get_custom_factor_service),
) -> CustomFactorResult:
    """Calculate values for a safe custom arithmetic factor expression."""
    return service.calculate(expression=request.expression, records=request.records)
