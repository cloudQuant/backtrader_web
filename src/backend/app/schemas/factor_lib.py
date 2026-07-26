"""Factor library schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class FactorEvaluationRequest(BaseModel):
    """Factor evaluation request."""

    factor_values: list[float | None] = Field(..., description="Factor values")
    future_returns: list[float | None] = Field(..., description="Forward returns")
    quantiles: int = Field(5, ge=2, le=10, description="Quantile bucket count")


class FactorEvaluationResult(BaseModel):
    """Factor evaluation result."""

    status: Literal["ok", "degraded"]
    observation_count: int = 0
    ic_mean: float | None = None
    ic_std: float | None = None
    ic_ir: float | None = None
    ic_t_stat: float | None = None
    long_short_return: float | None = None
    reason: str | None = None


class FactorCorrelationRequest(BaseModel):
    """Factor correlation analysis request."""

    factor_values: dict[str, list[float | None]] = Field(..., description="Factor value series")
    threshold: float = Field(0.8, ge=0, le=1, description="High correlation threshold")


class HighCorrelationPair(BaseModel):
    """High factor correlation pair."""

    factor_a: str
    factor_b: str
    correlation: float


class FactorCorrelationResult(BaseModel):
    """Factor correlation analysis result."""

    status: Literal["ok", "degraded"]
    factor_count: int = 0
    observation_count: int = 0
    matrix: dict[str, dict[str, float]] = Field(default_factory=dict)
    high_correlation_pairs: list[HighCorrelationPair] = Field(default_factory=list)
    reason: str | None = None


class CustomFactorRequest(BaseModel):
    """Custom factor calculation request."""

    expression: str = Field(..., min_length=1, max_length=500)
    records: list[dict[str, float | int | None]] = Field(..., description="OHLCV records")


class CustomFactorResult(BaseModel):
    """Custom factor calculation result."""

    status: Literal["ok", "degraded"]
    values: list[float | None] = Field(default_factory=list)
    observation_count: int = 0
    reason: str | None = None
