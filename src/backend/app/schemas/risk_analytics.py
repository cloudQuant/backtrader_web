"""Schemas for risk analytics responses."""

from typing import Literal

from pydantic import BaseModel, Field


class VarCvarResult(BaseModel):
    """VaR/CVaR calculation result."""

    status: Literal["ok", "degraded"] = Field(..., description="Calculation status")
    method: Literal["historical", "parametric", "monte_carlo"] = Field(
        ..., description="Calculation method"
    )
    observation_count: int = Field(..., ge=0, description="Number of return observations")
    var_95: float | None = Field(None, description="95% VaR as return ratio")
    var_99: float | None = Field(None, description="99% VaR as return ratio")
    cvar_95: float | None = Field(None, description="95% CVaR as return ratio")
    cvar_99: float | None = Field(None, description="99% CVaR as return ratio")
    reason: str | None = Field(None, description="Degraded result reason")
    backtest_id: str | None = Field(None, description="Backtest task ID")


class StressScenario(BaseModel):
    """Stress scenario definition."""

    id: str = Field(..., description="Scenario identifier")
    name: str = Field(..., description="Scenario display name")
    start_date: str = Field(..., description="Scenario start date YYYY-MM-DD")
    end_date: str = Field(..., description="Scenario end date YYYY-MM-DD")


class StressTestRequest(BaseModel):
    """Stress test request."""

    scenarios: list[StressScenario] | None = Field(None, description="Selected scenarios")


class StressScenarioResult(BaseModel):
    """Stress scenario calculation result."""

    scenario_id: str
    scenario_name: str
    status: Literal["ok", "degraded"]
    start_date: str
    end_date: str
    observation_count: int = 0
    max_loss: float | None = None
    max_drawdown: float | None = None
    recovery_days: int | None = None
    reason: str | None = None


class StressTestResult(BaseModel):
    """Stress test response."""

    status: Literal["ok", "degraded"]
    scenario_count: int
    results: list[StressScenarioResult]
    backtest_id: str | None = None


class KellyResult(BaseModel):
    """Kelly position sizing recommendation."""

    status: Literal["ok", "degraded"]
    trade_count: int = 0
    win_rate: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    payoff_ratio: float | None = None
    full_kelly: float | None = None
    half_kelly: float | None = None
    quarter_kelly: float | None = None
    recommendation: str | None = None
    reason: str | None = None
    backtest_id: str | None = None


class PositionSizingResult(BaseModel):
    """Volatility targeting position sizing recommendation."""

    status: Literal["ok", "degraded"]
    method: Literal["volatility_target"]
    observation_count: int = 0
    annualized_volatility: float | None = None
    target_volatility: float | None = None
    recommended_position: float | None = None
    max_position: float | None = None
    reason: str | None = None
    backtest_id: str | None = None


class BenchmarkReturnsResult(BaseModel):
    """Benchmark return series response."""

    status: Literal["ok", "degraded"]
    benchmark_id: str
    symbol: str | None = None
    start_date: str
    end_date: str
    observation_count: int = 0
    dates: list[str] = Field(default_factory=list)
    returns: list[float] = Field(default_factory=list)
    reason: str | None = None


class BenchmarkMetricsResult(BaseModel):
    """Strategy-vs-benchmark metrics response."""

    status: Literal["ok", "degraded"]
    benchmark_id: str
    observation_count: int = 0
    alpha: float | None = None
    beta: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    risk_free_rate: float = 0.0
    reason: str | None = None
    backtest_id: str | None = None


class MarketRegimeResult(BaseModel):
    """Market regime classification result."""

    status: Literal["ok", "degraded"]
    observation_count: int = 0
    volatility_regime: Literal["low", "medium", "high"] | None = None
    trend_regime: Literal["bull", "sideways", "bear"] | None = None
    overall_regime: str | None = None
    annualized_volatility: float | None = None
    trend_return: float | None = None
    reason: str | None = None
    backtest_id: str | None = None
