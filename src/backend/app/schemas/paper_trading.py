"""
Paper trading schemas.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AccountCreate(BaseModel):
    """Paper trading account creation request schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Account name")
    initial_cash: float = Field(100000.0, gt=0, le=10000000, description="Initial cash")
    commission_rate: float = Field(
        0.001,
        ge=0,
        le=0.01,
        description="Commission rate (default 0.1%), e.g., 0.001 means 0.1%, 0.003 means 0.3%",
    )
    slippage_rate: float = Field(
        0.001,
        ge=0,
        le=0.01,
        description="Slippage rate (default 0.1%), e.g., 0.001 means 0.1% slippage per trade",
    )


class AccountResponse(BaseModel):
    """Paper trading account response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Account ID")
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="Account name")
    initial_cash: float = Field(..., description="Initial cash")
    current_cash: float = Field(..., description="Current cash")
    total_equity: float = Field(..., description="Total equity (cash + position value)")
    profit_loss: float = Field(..., description="Profit/loss")
    profit_loss_pct: float = Field(
        ...,
        description="Profit/loss percentage (%), e.g., 10.0 means 10% return, -5.0 means 5% loss",
    )
    commission_rate: float = Field(..., description="Commission rate")
    slippage_rate: float = Field(..., description="Slippage rate")
    is_active: bool = Field(..., description="Whether active")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")


class AccountListResponse(BaseModel):
    """Account list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    items: list[AccountResponse]


class OrderRequest(BaseModel):
    """Paper trading order request schema."""

    account_id: str = Field(..., description="Account ID")
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=40,
        description="Trading symbol, e.g., 000001.SZ, BTC/USDT, BTCUSDT, XAUUSD, or IF2609",
    )
    order_type: str = Field(
        ...,
        description="Order type: market (market order), limit (limit order), stop (stop loss), stop_limit (stop limit)",
    )
    side: str = Field(..., description="Order side: buy (long) or sell (close long or short)")
    size: float = Field(..., gt=0, description="Order size, must be positive")
    price: float | None = Field(
        None, gt=0, description="Limit order price (not required for market orders)"
    )
    stop_price: float | None = Field(
        None, gt=0, description="Stop price (required for stop orders)"
    )
    limit_price: float | None = Field(
        None, gt=0, description="Take profit price (required for stop limit orders)"
    )

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"market", "limit", "stop", "stop_limit"}:
            raise ValueError("order_type must be one of: market, limit, stop, stop_limit")
        return normalized

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"buy", "sell"}:
            raise ValueError("side must be one of: buy, sell")
        return normalized

    @model_validator(mode="after")
    def validate_required_prices(self) -> "OrderRequest":
        if self.order_type == "limit" and self.price is None and self.limit_price is None:
            raise ValueError("limit orders require price or limit_price")
        if self.order_type == "stop" and self.stop_price is None and self.price is None:
            raise ValueError("stop orders require stop_price or price")
        if self.order_type == "stop_limit" and (
            self.stop_price is None or self.limit_price is None
        ):
            raise ValueError("stop_limit orders require stop_price and limit_price")
        return self


class OrderResponse(BaseModel):
    """Paper trading order response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Order ID")
    account_id: str = Field(..., description="Account ID")
    symbol: str = Field(..., description="Trading symbol")
    order_type: str = Field(..., description="Order type")
    side: str = Field(..., description="Order side")
    size: float = Field(..., description="Order size")
    price: float | None = Field(None, description="Limit order price")
    stop_price: float | None = Field(None, description="Stop price")
    limit_price: float | None = Field(None, description="Take profit price")
    filled_size: float = Field(default=0, description="Filled size")
    avg_fill_price: float = Field(default=0, description="Average fill price")
    status: str = Field(
        ...,
        description="Order status: pending (waiting), partial_filled (partially filled), filled (completed), cancelled (cancelled), rejected (rejected)",
    )
    rejected_reason: str | None = Field(None, description="Rejection reason")
    commission: float = Field(default=0, description="Commission")
    slippage: float = Field(default=0, description="Slippage")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")
    filled_at: datetime | None = Field(None, description="Fill time")


class OrderListResponse(BaseModel):
    """Order list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    items: list[OrderResponse]


class PositionResponse(BaseModel):
    """Paper trading position response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Position ID")
    account_id: str = Field(..., description="Account ID")
    symbol: str = Field(..., description="Trading symbol")
    size: float = Field(
        ...,
        description="Position size (positive for long, negative for short, e.g., 100 means long 100 shares, -0.5 means short half a lot)",
    )
    avg_price: float = Field(default=0, description="Average cost price")
    market_value: float = Field(
        default=0,
        description="Notional market value (size * market price * multiplier)",
    )
    margin_value: float = Field(default=0, description="Reserved margin for the position")
    multiplier: float = Field(default=1, description="Contract multiplier")
    margin_rate: float = Field(default=1, description="Margin rate")
    commission_rate: float = Field(default=0, description="Commission rate used for valuation")
    commission_amount: float = Field(default=0, description="Fixed commission per lot/contract")
    unrealized_pnl: float = Field(
        default=0,
        description="Unrealized profit/loss (calculated at current market price, positive for profit, negative for loss)",
    )
    unrealized_pnl_pct: float = Field(
        default=0,
        description="Unrealized profit/loss percentage, e.g., 15.5 means 15.5% profit, -8.2 means 8.2% loss",
    )
    entry_price: float = Field(default=0, description="Entry price")
    entry_time: datetime | None = Field(None, description="Entry time")
    updated_at: datetime = Field(..., description="Update time")


class PositionListResponse(BaseModel):
    """Position list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    items: list[PositionResponse]


class TradeResponse(BaseModel):
    """Paper trading trade response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Trade ID")
    account_id: str = Field(..., description="Account ID")
    order_id: str | None = Field(None, description="Order ID")
    symbol: str = Field(..., description="Trading symbol")
    side: str = Field(..., description="Trade side: buy (buy) or sell (sell)")
    size: float = Field(..., description="Trade size")
    price: float = Field(..., description="Trade price")
    commission: float = Field(default=0, description="Commission")
    slippage: float = Field(default=0, description="Slippage")
    pnl: float = Field(default=0, description="Profit/loss (realized P&L)")
    pnl_pct: float = Field(default=0, description="Profit/loss percentage")
    created_at: datetime = Field(..., description="Trade time")


class TradeListResponse(BaseModel):
    """Trade list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    items: list[TradeResponse]
