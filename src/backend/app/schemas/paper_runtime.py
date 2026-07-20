"""API schemas for workspace-based paper trading runtimes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaperEquitySnapshotCreate(BaseModel):
    """Record an idempotent mark-to-market snapshot for the current user's runtime."""

    observed_at: datetime | None = None
    source: str = Field("manual", min_length=1, max_length=32)
    total_equity: float
    cash: float = 0.0
    position_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperEquitySnapshotResponse(BaseModel):
    """One equity observation in UTC."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    observed_at: datetime
    source: str
    total_equity: float
    cash: float
    position_value: float
    unrealized_pnl: float
    realized_pnl: float

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at_to_utc(cls, value: datetime) -> datetime:
        """SQLite may return naive datetimes; the public contract is always UTC."""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class PaperEquityCurveResponse(BaseModel):
    """Cursor-safe equity curve response without fabricated zero points."""

    instance_id: str
    points: list[PaperEquitySnapshotResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    sampled: bool = False
    sampling: str = "none"


class RiskRuleCreate(BaseModel):
    """Create a risk rule scoped to a runtime, unit, workspace, or account."""

    name: str = Field(..., min_length=1, max_length=200)
    rule_type: str = Field(..., min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["info", "warning", "error", "critical"] = "warning"
    workspace_id: str | None = None
    unit_id: str | None = None
    instance_id: str | None = None
    paper_account_id: str | None = None


class RiskRuleResponse(RiskRuleCreate):
    """A persisted risk rule."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class RiskRuleUpdate(BaseModel):
    """Patch a current user's risk rule."""

    name: str | None = Field(None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    severity: Literal["info", "warning", "error", "critical"] | None = None
    is_active: bool | None = None


class PaperRuntimeAlertResponse(BaseModel):
    """A persisted, scoped alert safe for display."""

    id: str
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    instance_id: str | None = None
    workspace_id: str | None = None
    unit_id: str | None = None
    created_at: datetime | None = None


class PaperRuntimeReviewRequest(BaseModel):
    """Persist a paper observation report."""

    status: str = Field("completed", min_length=1, max_length=32)
    summary: str | None = Field(None, max_length=5000)
    report: dict[str, Any] = Field(default_factory=dict)
    observation_start_at: datetime | None = None
    observation_end_at: datetime | None = None


class LiveHandoffDecisionRequest(BaseModel):
    """Record an explicit paper-to-live decision."""

    decision: Literal["approved", "rejected", "requested_changes"]
    rationale: str | None = Field(None, max_length=5000)
    checklist: dict[str, Any] = Field(default_factory=dict)


class PaperRuntimePreOrderRiskRequest(BaseModel):
    """Inputs required to validate a proposed paper-runtime order."""

    order_notional: float = Field(..., gt=0)
    current_equity: float = Field(..., gt=0)
    projected_position_value: float = 0.0
    drawdown_pct: float = 0.0
    daily_loss_pct: float = 0.0
    daily_trade_count: int = Field(0, ge=0)


class PaperRuntimePreOrderRiskResponse(BaseModel):
    """A fail-closed decision safe to display before order submission."""

    allowed: bool
    reason: str | None = None
    rule_ids: list[str] = Field(default_factory=list)


class PaperRuntimeResponse(BaseModel):
    """Workspace runtime identity and latest persisted state."""

    instance_id: str
    workspace_id: str
    unit_id: str
    workspace_name: str
    unit_name: str
    symbol: str
    status: str
    paused: bool
    positions: list[dict[str, Any]] = Field(default_factory=list)
    orders: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    latest_equity: PaperEquitySnapshotResponse | None = None
