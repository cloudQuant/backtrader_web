"""Strategy explanation schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class StrategyIndicator(BaseModel):
    """Indicator extracted from strategy source."""

    name: str = Field(..., description="Indicator class or function name")
    alias: str | None = Field(default=None, description="Attribute alias on self")
    params: dict[str, Any] = Field(default_factory=dict, description="Indicator parameters")


class StrategySignal(BaseModel):
    """Trading signal extracted from strategy source."""

    condition: str = Field(..., description="Source-level condition text")
    side: str = Field(..., description="Signal side such as buy/sell/close/stop_loss")


class StrategyRiskControl(BaseModel):
    """Risk control extracted from strategy source."""

    type: str = Field(..., description="Risk control type")
    value: Any | None = Field(default=None, description="Risk control value")
    source: str | None = Field(default=None, description="Source-level expression")


class StrategyParamInfo(BaseModel):
    """Strategy parameter extracted from params."""

    name: str = Field(..., description="Parameter name")
    default: Any | None = Field(default=None, description="Default value")


class StrategyStructure(BaseModel):
    """Structured static analysis result."""

    parsable: bool = Field(..., description="Whether Python AST parsing succeeded")
    indicators: list[StrategyIndicator] = Field(default_factory=list)
    entry_signals: list[StrategySignal] = Field(default_factory=list)
    exit_signals: list[StrategySignal] = Field(default_factory=list)
    risk_controls: list[StrategyRiskControl] = Field(default_factory=list)
    params: list[StrategyParamInfo] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    raw_code: str | None = Field(default=None)
    parse_error: str | None = Field(default=None)


class StrategyExplainRequest(BaseModel):
    """Request to explain a strategy."""

    code: str | None = Field(default=None, description="Strategy source code")
    strategy_id: str | None = Field(default=None, description="Persisted strategy id")
    backtest_id: str | None = Field(default=None, description="Backtest task id")
    strategy_name: str | None = Field(default=None, description="Optional display name")
    category: str | None = Field(default=None, description="Optional strategy category")
    params: dict[str, Any] | None = Field(default=None, description="Optional parameter metadata")

    @model_validator(mode="after")
    def require_source(self) -> StrategyExplainRequest:
        if not self.code and not self.strategy_id and not self.backtest_id:
            raise ValueError("one of code, strategy_id, or backtest_id is required")
        return self


class StrategyExplanation(BaseModel):
    """Strategy explanation response."""

    code_hash: str = Field(..., description="SHA-256 hash of source code")
    strategy_name: str = Field(..., description="Strategy display name")
    summary: str = Field(..., description="One-sentence strategy summary")
    indicators_explanation: str = Field(..., description="Indicator explanation")
    entry_explanation: str = Field(..., description="Entry condition explanation")
    exit_explanation: str = Field(..., description="Exit condition explanation")
    params_explanation: str = Field(..., description="Parameter explanation")
    market_fit: str = Field(..., description="Suitable market regime")
    risk_notes: list[str] = Field(default_factory=list, description="Risk notes")
    ast: StrategyStructure = Field(..., description="Static analysis payload")
    reason_code: str = Field(
        ..., description="ai_generated/static_fallback/cache_hit/ai_not_configured"
    )
    model_id: str | None = Field(default=None, description="AI model id")
    cached: bool = Field(default=False, description="Whether response came from cache")
    disclaimer: str = Field(default="解释仅供研究参考，不构成投资建议。")
