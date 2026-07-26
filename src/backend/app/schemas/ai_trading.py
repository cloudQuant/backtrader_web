"""Schemas for AI-driven natural language trading.

Defines the data structures for trading intents, execution requests,
risk assessments, and trading logs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TradeAction(str, Enum):
    """Supported trading actions."""

    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"
    CANCEL = "cancel"
    QUERY = "query"
    MODIFY = "modify"


class OrderType(str, Enum):
    """Order type for trade execution."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class RiskLevel(str, Enum):
    """Risk assessment level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TradeStatus(str, Enum):
    """Status of a trade execution."""

    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradingIntent(BaseModel):
    """Structured trading intent parsed from natural language."""

    action: TradeAction
    symbol: str | None = None
    exchange: str | None = None
    quantity: float | None = None
    price: float | None = None
    order_type: OrderType = OrderType.MARKET
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    raw_input: str = ""
    additional_params: dict[str, Any] = Field(default_factory=dict)


class RiskAssessment(BaseModel):
    """Risk assessment result from the risk guard."""

    approved: bool
    risk_level: RiskLevel
    warnings: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    max_loss_estimate: float | None = None
    position_impact: str | None = None


class AITradingRequest(BaseModel):
    """Request to execute a natural language trade."""

    message: str = Field(..., min_length=1, max_length=500)
    gateway_id: str | None = None
    account_id: str | None = None
    dry_run: bool = True
    auto_confirm: bool = False
    knowledge_base_id: str | None = None
    conversation_id: str | None = None


class AITradingResponse(BaseModel):
    """Response from AI trading execution."""

    trade_id: str
    intent: TradingIntent
    risk_assessment: RiskAssessment
    status: TradeStatus
    message: str
    execution_result: dict[str, Any] | None = None
    ai_reasoning: str = ""
    suggestions: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    degraded: bool = False
    diagnostic_message: str | None = None


class TradeConfirmRequest(BaseModel):
    """Request to confirm a pending trade."""

    trade_id: str
    confirmed: bool
    user_note: str | None = None


class TradeConfirmResponse(BaseModel):
    """Response after trade confirmation."""

    trade_id: str
    status: TradeStatus
    message: str
    execution_result: dict[str, Any] | None = None


class AITradingHistoryItem(BaseModel):
    """A single AI trading history entry."""

    trade_id: str
    user_input: str
    intent: TradingIntent
    risk_assessment: RiskAssessment
    status: TradeStatus
    execution_result: dict[str, Any] | None = None
    ai_reasoning: str = ""
    reflection: str | None = None
    created_at: datetime
    executed_at: datetime | None = None


class AITradingHistoryResponse(BaseModel):
    """Response for trading history query."""

    total: int
    items: list[AITradingHistoryItem]


class AITradingConfigResponse(BaseModel):
    """Current AI trading configuration."""

    enabled: bool
    default_mode: str = "paper"
    max_single_trade_amount: float = 10000.0
    max_daily_trades: int = 50
    max_position_ratio: float = 0.3
    require_confirmation_above: float = 5000.0
    blocked_symbols: list[str] = Field(default_factory=list)
    available_gateways: list[dict[str, Any]] = Field(default_factory=list)
    available_accounts: list[dict[str, Any]] = Field(default_factory=list)


class ConditionalOrderCreate(BaseModel):
    """Request to create a conditional (trigger) order."""

    condition: str = Field(..., min_length=1, max_length=500)
    action_message: str = Field(..., min_length=1, max_length=500)
    gateway_id: str | None = None
    dry_run: bool = True
    expiry_hours: float = 24.0


class ConditionalOrder(BaseModel):
    """A conditional order waiting to be triggered."""

    id: str
    user_id: str
    condition: str
    action_message: str
    gateway_id: str | None = None
    dry_run: bool = True
    status: str = "active"  # active, triggered, expired, cancelled
    created_at: str
    expires_at: str
    triggered_at: str | None = None


class ConditionalOrderListResponse(BaseModel):
    """Response for listing conditional orders."""

    total: int
    items: list[ConditionalOrder]
