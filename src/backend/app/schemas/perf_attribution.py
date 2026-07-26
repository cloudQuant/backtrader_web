"""Performance attribution schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class BrinsonAttributionRequest(BaseModel):
    """Brinson attribution request."""

    portfolio_weights: dict[str, float] = Field(..., description="Portfolio asset weights")
    benchmark_weights: dict[str, float] = Field(..., description="Benchmark asset weights")
    portfolio_returns: dict[str, float] = Field(..., description="Portfolio asset returns")
    benchmark_returns: dict[str, float] = Field(..., description="Benchmark asset returns")


class BrinsonAttributionResult(BaseModel):
    """Brinson attribution result."""

    status: Literal["ok", "degraded"]
    asset_count: int = 0
    allocation_effect: float | None = None
    selection_effect: float | None = None
    interaction_effect: float | None = None
    total_excess_return: float | None = None
    reason: str | None = None


class FamaFrenchAttributionRequest(BaseModel):
    """Fama-French three-factor attribution request."""

    strategy_returns: list[float] = Field(..., description="Strategy return series")
    market_returns: list[float] = Field(..., description="Market factor return series")
    smb_returns: list[float] = Field(..., description="SMB factor return series")
    hml_returns: list[float] = Field(..., description="HML factor return series")


class FamaFrenchAttributionResult(BaseModel):
    """Fama-French three-factor attribution result."""

    status: Literal["ok", "degraded"]
    observation_count: int = 0
    alpha: float | None = None
    market_beta: float | None = None
    smb_beta: float | None = None
    hml_beta: float | None = None
    r_squared: float | None = None
    reason: str | None = None
