"""
Paper trading schemas.
"""

from datetime import datetime

from pydantic import BaseModel, Field


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
        pattern=r"^\d{6}\.(SH|SZ)$",
        description="Stock code, e.g., 000001.SZ or 600000.SH, must be A-share format: 6 digits.SH or .SZ",
    )
    order_type: str = Field(
        ...,
        description="Order type: market (market order), limit (limit order), stop (stop loss), stop_limit (stop limit)",
    )
    side: str = Field(..., description="Order side: buy (long) or sell (close long or short)")
    size: int = Field(..., gt=0, description="Order size, must be positive integer")
    price: float | None = Field(
        None, gt=0, description="Limit order price (not required for market orders)"
    )
    stop_price: float | None = Field(
        None, gt=0, description="Stop price (required for stop orders)"
    )
    limit_price: float | None = Field(
        None, gt=0, description="Take profit price (required for stop limit orders)"
    )


class OrderResponse(BaseModel):
    """Paper trading order response schema."""

    id: str = Field(..., description="Order ID")
    account_id: str = Field(..., description="Account ID")
    symbol: str = Field(..., description="Stock code")
    order_type: str = Field(..., description="Order type")
    side: str = Field(..., description="Order side")
    size: int = Field(..., description="Order size")
    price: float | None = Field(None, description="Limit order price")
    stop_price: float | None = Field(None, description="Stop price")
    limit_price: float | None = Field(None, description="Take profit price")
    filled_size: int = Field(default=0, description="Filled size")
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

    id: str = Field(..., description="Position ID")
    account_id: str = Field(..., description="Account ID")
    symbol: str = Field(..., description="Stock code")
    size: int = Field(
        ...,
        description="Position size (positive for long, negative for short, e.g., 100 means long 100 shares, -50 means short 50 shares)",
    )
    avg_price: float = Field(default=0, description="Average cost price")
    market_value: float = Field(
        default=0,
        description="Market value (size * market price), e.g., size=100, market_price=105.5, then market_value=10550",
    )
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

    id: str = Field(..., description="Trade ID")
    account_id: str = Field(..., description="Account ID")
    order_id: str | None = Field(None, description="Order ID")
    symbol: str = Field(..., description="Stock code")
    side: str = Field(..., description="Trade side: buy (buy) or sell (sell)")
    size: int = Field(..., description="Trade size")
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
