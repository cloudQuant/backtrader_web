"""
Trading workspace schemas.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TradingPosition(BaseModel):
    """Position snapshot for a strategy unit."""

    data_name: str = ""
    direction: str = ""
    size: float = 0.0
    price: float | None = None
    current_price: float | None = None
    market_value: float | None = None
    pnl: float | None = None


class TradingSnapshot(BaseModel):
    """Trading runtime snapshot for a strategy unit."""

    instance_id: str | None = None
    instance_status: str = "idle"
    mode: str = "paper"
    error: str | None = None
    started_at: str | None = None
    stopped_at: str | None = None
    gateway_summary: str | None = None
    long_position: float = 0.0
    short_position: float = 0.0
    today_pnl: float | None = None
    position_pnl: float | None = None
    latest_price: float | None = None
    change_pct: float | None = None
    long_market_value: float | None = None
    short_market_value: float | None = None
    leverage: float | None = None
    cumulative_pnl: float | None = None
    max_drawdown_rate: float | None = None
    trading_day: str | None = None
    updated_at: str | None = None
    detail_route: str | None = None
    positions: list[TradingPosition] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class TradingGatewayConfig(BaseModel):
    """Gateway preset selection stored on a strategy unit."""

    preset_id: str | None = None
    name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class AutoTradingSession(BaseModel):
    """A configured trading session window."""

    name: str = ""
    open: str = "09:00"
    close: str = "15:00"


class AutoTradingConfigPayload(BaseModel):
    """Workspace-facing auto-trading configuration."""

    enabled: bool = False
    buffer_minutes: int = 15
    sessions: list[AutoTradingSession] = Field(default_factory=list)
    scope: str = "all"

    model_config = ConfigDict(extra="ignore")


class AutoTradingScheduleItem(BaseModel):
    """Computed schedule item for the current day."""

    session: str = ""
    start: str = ""
    stop: str = ""
    market_open: str | None = None
    market_close: str | None = None


class PositionManagerItem(BaseModel):
    """Aggregated position row used by the position manager dialog."""

    unit_id: str
    unit_name: str
    symbol: str
    symbol_name: str | None = None
    trading_mode: str = "paper"
    long_position: float = 0.0
    short_position: float = 0.0
    avg_price: float | None = None
    latest_price: float | None = None
    position_pnl: float = 0.0
    market_value: float = 0.0


class PositionManagerResponse(BaseModel):
    """Workspace-level aggregated position payload."""

    positions: list[PositionManagerItem] = Field(default_factory=list)
    total_long_value: float = 0.0
    total_short_value: float = 0.0
    total_pnl: float = 0.0


class TradingDailySummaryItem(BaseModel):
    """Daily trading summary row."""

    trading_date: str
    daily_pnl: float = 0.0
    trade_count: int = 0
    cumulative_pnl: float = 0.0
    max_drawdown: float = 0.0


class TradingDailySummaryResponse(BaseModel):
    """Workspace-level daily summary payload."""

    summaries: list[TradingDailySummaryItem] = Field(default_factory=list)
