from typing import Literal

from pydantic import BaseModel, Field


class PortfolioLedgerVarCvarResult(BaseModel):
    portfolio_id: str
    status: Literal["ok", "degraded"] = Field(...)
    method: Literal["historical", "parametric", "monte_carlo"] = Field(...)
    observation_count: int = Field(..., ge=0)
    var_95: float | None = None
    var_99: float | None = None
    cvar_95: float | None = None
    cvar_99: float | None = None
    reason: str | None = None


class PortfolioLedgerPositionSizingResult(BaseModel):
    portfolio_id: str
    status: Literal["ok", "degraded"]
    method: Literal["volatility_target"]
    observation_count: int = 0
    annualized_volatility: float | None = None
    target_volatility: float | None = None
    recommended_position: float | None = None
    max_position: float | None = None
    reason: str | None = None


class PortfolioLedgerBenchmarkMetricsResult(BaseModel):
    portfolio_id: str
    status: Literal["ok", "degraded"]
    benchmark_id: str
    observation_count: int = 0
    alpha: float | None = None
    beta: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    risk_free_rate: float = 0.0
    reason: str | None = None


class PortfolioLedgerBrinsonRequest(BaseModel):
    benchmark_weights: dict[str, float] = Field(default_factory=dict)
    benchmark_returns: dict[str, float] = Field(default_factory=dict)


class PortfolioLedgerBrinsonResult(BaseModel):
    portfolio_id: str
    status: Literal["ok", "degraded"]
    asset_count: int = 0
    allocation_effect: float | None = None
    selection_effect: float | None = None
    interaction_effect: float | None = None
    total_excess_return: float | None = None
    reason: str | None = None


class PortfolioLedgerFamaFrenchRequest(BaseModel):
    market_returns: list[float] | None = None
    smb_returns: list[float] = Field(default_factory=list)
    hml_returns: list[float] = Field(default_factory=list)
    benchmark_id: str | None = None


class PortfolioLedgerFamaFrenchResult(BaseModel):
    portfolio_id: str
    status: Literal["ok", "degraded"]
    observation_count: int = 0
    alpha: float | None = None
    market_beta: float | None = None
    smb_beta: float | None = None
    hml_beta: float | None = None
    r_squared: float | None = None
    benchmark_id: str | None = None
    reason: str | None = None
