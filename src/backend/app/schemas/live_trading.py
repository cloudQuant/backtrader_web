"""
Live trading schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LiveTradingSubmitRequest(BaseModel):
    """Live trading strategy submission request schema."""

    strategy_name: Optional[str] = Field(None, description="Strategy name (built-in strategies)")
    strategy_code: Optional[str] = Field(None, description="Strategy code")
    exchange: str = Field(..., description="Exchange (binance, okex, huobi, etc.)")
    symbols: List[str] = Field(
        ..., min_length=1, description="Symbol list (e.g., ['BTC/USDT', 'ETH/USDT'])"
    )
    initial_cash: float = Field(100000.0, gt=0, le=10000000, description="Initial capital (USDT)")
    strategy_params: Optional[Dict[str, Any]] = Field(None, description="Strategy parameters")
    timeframe: str = Field("1d", description="Timeframe (1m, 5m, 15m, 30m, 1h, 1d, 1w, 1M)")
    start_date: Optional[datetime] = Field(None, description="Start time")
    end_date: Optional[datetime] = Field(None, description="End time")
    api_key: str = Field(..., description="API Key")
    secret: str = Field(..., description="Secret Key")
    sandbox: bool = Field(False, description="Whether to use test environment")


class LiveTradingTaskResponse(BaseModel):
    """Live trading task response schema."""

    task_id: str = Field(..., description="Task ID")
    user_id: str = Field(..., description="User ID")
    status: str = Field(..., description="Task status: running, stopped, error")
    config: Dict[str, Any] = Field(..., description="Task configuration")
    created_at: datetime = Field(..., description="Creation time")


class LiveTradingTaskListResponse(BaseModel):
    """Live trading task list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    tasks: List[LiveTradingTaskResponse] = Field(..., description="Task list")


class LiveTradingDataResponse(BaseModel):
    """Live trading data response schema."""

    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status")
    cash: float = Field(..., description="Available cash")
    value: float = Field(..., description="Total equity")
    positions: List[Dict[str, Any]] = Field(..., description="Position list")
    orders: List[Dict[str, Any]] = Field(..., description="Order list")


class LiveTradingPosition(BaseModel):
    """Live trading position schema."""

    symbol: str = Field(..., description="Symbol code")
    size: float = Field(..., description="Position size (positive for long, negative for short)")
    avg_price: float = Field(..., description="Average cost price")
    market_value: float = Field(..., description="Market value")
    unrealized_pnl: float = Field(..., description="Unrealized profit/loss")
    unrealized_pnl_pct: float = Field(..., description="Unrealized profit/loss percentage")


class LiveTradingOrder(BaseModel):
    """Live trading order schema."""

    order_id: str = Field(..., description="Order ID")
    symbol: str = Field(..., description="Symbol code")
    order_type: str = Field(..., description="Order type")
    side: str = Field(..., description="Order side")
    size: float = Field(..., description="Order quantity")
    price: Optional[float] = Field(None, description="Limit order price")
    status: str = Field(..., description="Order status")
    filled_size: float = Field(..., description="Filled quantity")
    created_at: datetime = Field(..., description="Creation time")


class LiveTradingTrade(BaseModel):
    """Live trading trade schema."""

    trade_id: str = Field(..., description="Trade ID")
    order_id: str = Field(..., description="Order ID")
    symbol: str = Field(..., description="Symbol code")
    side: str = Field(..., description="Trade side")
    size: float = Field(..., description="Trade quantity")
    price: float = Field(..., description="Trade price")
    commission: float = Field(..., description="Commission")
    pnl: float = Field(..., description="Profit/loss")
    pnl_pct: float = Field(..., description="Profit/loss percentage")
    created_at: datetime = Field(..., description="Trade time")


class LiveAccountInfo(BaseModel):
    """Live trading account info schema."""

    cash: float = Field(..., description="Available cash")
    value: float = Field(..., description="Total equity")
    available_cash: float = Field(..., description="Available cash (including margin)")
    buying_power: float = Field(..., description="Buying power")
    margin: float = Field(..., description="Margin")
    maintenance_margin: float = Field(..., description="Maintenance margin")


class LiveTick(BaseModel):
    """Live trading tick schema."""

    symbol: str = Field(..., description="Symbol code")
    timestamp: datetime = Field(..., description="Timestamp")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    volume: float = Field(..., description="Volume")
    bid: Optional[float] = Field(None, description="Bid price")
    ask: Optional[float] = Field(None, description="Ask price")
    bid_size: Optional[float] = Field(None, description="Bid size")
    ask_size: Optional[float] = Field(None, description="Ask size")


class LiveTickUpdate(BaseModel):
    """Live tick update schema."""

    type: str = Field("tick_update", description="Message type")
    symbol: str = Field(..., description="Symbol code")
    timestamp: str = Field(..., description="Timestamp (ISO 8601)")
    data: LiveTick = Field(..., description="Tick data")


class LivePositionUpdate(BaseModel):
    """Live position update schema."""

    type: str = Field("position_update", description="Message type")
    symbol: str = Field(..., description="Symbol code")
    data: LiveTradingPosition = Field(..., description="Position data")


class LiveOrderUpdate(BaseModel):
    """Live order update schema."""

    type: str = Field("order_update", description="Message type")
    order_id: str = Field(..., description="Order ID")
    data: Dict[str, Any] = Field(..., description="Order data")


class LiveTradeUpdate(BaseModel):
    """Live trade update schema."""

    type: str = Field("trade_update", description="Message type")
    trade_id: str = Field(..., description="Trade ID")
    data: LiveTradingTrade = Field(..., description="Trade data")


class LiveAccountUpdate(BaseModel):
    """Live account update schema."""

    type: str = Field("account_update", description="Message type")
    cash: float = Field(..., description="Cash")
    value: float = Field(..., description="Total equity")


class LiveSignalUpdate(BaseModel):
    """Strategy signal update schema."""

    type: str = Field("signal_update", description="Message type")
    symbol: str = Field(..., description="Symbol code")
    signal: str = Field(..., description="Signal type: buy, sell, close")
    data: Dict[str, Any] = Field(..., description="Signal data")
