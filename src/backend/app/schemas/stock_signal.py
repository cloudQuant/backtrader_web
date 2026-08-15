"""Public schemas for the auditable single-stock signal lifecycle."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

StockSignalAction = Literal["BUY", "SELL", "WATCH"]
StockSignalEligibility = Literal["eligible", "degraded", "rejected"]
StockSignalOutcomeStatus = Literal["pending", "partial", "scored", "unscorable"]


class StockSignalRecordResponse(BaseModel):
    """A redacted, user-visible prediction record."""

    id: str
    source: str
    universe_code: str
    symbol: str
    symbol_name: str | None = None
    market_type: str
    as_of_date: date
    available_at: datetime
    next_trading_date: date | None = None
    signal_action: StockSignalAction
    action_label: str
    confidence_score: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    expected_excess_return: float | None = None
    eligibility_status: StockSignalEligibility
    quality_reasons: list[str] = Field(default_factory=list)
    feature_version: str
    decision_policy_version: str
    model_version: str
    outcome_status: StockSignalOutcomeStatus
    outcome_reason: str | None = None
    entry_date: date | None = None
    entry_price: float | None = None
    horizon_1d_return: float | None = None
    horizon_5d_return: float | None = None
    horizon_20d_return: float | None = None
    benchmark_20d_return: float | None = None
    excess_20d_return: float | None = None
    buy_is_correct_20d: bool | None = None
    sell_is_correct_20d: bool | None = None


class StockSignalHistoryResponse(BaseModel):
    """Cursor-like historical records for one stock."""

    items: list[StockSignalRecordResponse] = Field(default_factory=list)
    next_cursor: str | None = None


class StockSignalActionSummary(BaseModel):
    """Outcome metrics for one visible action."""

    action: StockSignalAction
    generated_count: int = Field(ge=0)
    scorable_count: int = Field(ge=0)
    success_count: int = Field(ge=0)
    success_rate: float | None = Field(default=None, ge=0, le=1)
    average_return: float | None = None
    median_return: float | None = None
    average_excess_return: float | None = None


class StockSignalSummaryResponse(BaseModel):
    """A quality scorecard with denominators explicit."""

    symbol: str
    horizon: Literal[1, 5, 20] = 20
    actioned_generated_count: int = Field(ge=0)
    actioned_scorable_count: int = Field(ge=0)
    actioned_success_count: int = Field(ge=0)
    actioned_success_rate: float | None = Field(default=None, ge=0, le=1)
    coverage_rate: float | None = Field(default=None, ge=0, le=1)
    maturity_rate: float | None = Field(default=None, ge=0, le=1)
    actions: list[StockSignalActionSummary] = Field(default_factory=list)
    confidence_bins: list[dict[str, Any]] = Field(default_factory=list)


class StockSignalRunResponse(BaseModel):
    """A public view of the latest batch run."""

    id: str
    source: str
    universe_code: str
    as_of_date: date
    status: str
    expected_count: int
    created_count: int
    eligible_count: int
    degraded_count: int
    failed_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None


class OpeningActionPreviewRequest(BaseModel):
    """No-account input used to transform signals into suggested opening actions."""

    held_symbols: list[str] = Field(default_factory=list, max_length=200)
    as_of_date: date | None = None

    @field_validator("held_symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        return sorted({" ".join(value.split()).upper() for value in values if value.strip()})


class OpeningActionPreviewResponse(BaseModel):
    """Read-only execution handoff with no order capability."""

    execution_disabled: Literal[True] = True
    as_of_date: date
    next_trading_date: date | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
