"""
Realtime market data schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RealtimeTickSubscribeRequest(BaseModel):
    """Subscribe to realtime ticks."""

    symbols: List[str] = Field(
        ...,
        min_length=1,
        description="Symbols to subscribe to (e.g. ['BTC/USDT', 'ETH/USDT']).",
    )
    broker_id: Optional[str] = Field(
        None,
        description="Broker id (optional). If omitted, the default broker is used.",
    )


class RealtimeTickUnsubscribeRequest(BaseModel):
    """Unsubscribe from realtime ticks."""

    symbols: List[str] = Field(..., min_length=1, description="Symbols to unsubscribe from.")
    broker_id: Optional[str] = Field(None, description="Broker id (optional).")


class RealtimeHistoricalTickRequest(BaseModel):
    """Fetch historical tick/ohlcv-like data for a symbol."""

    broker_id: str = Field(..., description="Broker id.")
    symbol: str = Field(..., description="Symbol (e.g. BTC/USDT).")
    start_date: str = Field(..., description="Start datetime in ISO 8601 format.")
    end_date: str = Field(..., description="End datetime in ISO 8601 format.")
    frequency: str = Field("1d", description="Bar frequency (e.g. 1m/5m/15m/1h/1d/1w/1M).")


class RealtimeTick(BaseModel):
    """A single tick (or bar) snapshot."""

    symbol: str = Field(..., description="Symbol.")
    timestamp: datetime = Field(..., description="Timestamp.")
    open: float = Field(..., description="Open.")
    high: float = Field(..., description="High.")
    low: float = Field(..., description="Low.")
    close: float = Field(..., description="Close.")
    volume: float = Field(..., description="Volume.")
    bid: Optional[float] = Field(None, description="Best bid price.")
    ask: Optional[float] = Field(None, description="Best ask price.")
    bid_size: Optional[float] = Field(None, description="Best bid size.")
    ask_size: Optional[float] = Field(None, description="Best ask size.")


# Alias used by the API for backwards compatibility.
RealtimeTickResponse = RealtimeTick


class RealtimeTickUpdate(BaseModel):
    """Realtime tick update message (typically delivered via WebSocket)."""

    type: str = Field("tick_update", description="Message type.")
    broker_id: str = Field(..., description="Broker id.")
    symbol: str = Field(..., description="Symbol.")
    timestamp: str = Field(..., description="Timestamp in ISO 8601 format.")
    data: RealtimeTick = Field(..., description="Tick payload.")


class RealtimeTickBatchResponse(BaseModel):
    """Batch tick response for a single symbol."""

    symbol: str = Field(..., description="Symbol.")
    tick: Optional[RealtimeTick] = Field(None, description="Latest tick (if available).")
    ticks: Optional[List[RealtimeTick]] = Field(
        None, description="Historical ticks (if requested)."
    )


class RealtimeTickListResponse(BaseModel):
    """Tick list response."""

    total: int = Field(..., ge=0, description="Total number of symbols.")
    symbols: List[str] = Field(..., description="Symbol list.")
    ticks: Dict[str, Any] = Field(..., description="Tick map keyed by symbol.")
