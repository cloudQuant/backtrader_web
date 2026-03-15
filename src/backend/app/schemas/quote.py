"""
Quote page schemas.

Unified quote data models for the multi-source quote display page.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data-source metadata
# ---------------------------------------------------------------------------

class DataSourceInfo(BaseModel):
    """Metadata for a single data source (CTP / IB / MT5 / …)."""

    source: str = Field(..., description="Backend identifier, e.g. CTP, IB_WEB, MT5")
    source_label: str = Field(..., description="Display label, e.g. IB")
    status: str = Field(
        ...,
        description=(
            "One of: available, not_configured, not_connected, unavailable"
        ),
    )
    status_message: str | None = Field(None, description="Human-readable status hint")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Supported capabilities, e.g. ['quote', 'search', 'chart']",
    )


class DataSourceListResponse(BaseModel):
    """Response for listing all data sources with their status."""

    sources: list[DataSourceInfo]


# ---------------------------------------------------------------------------
# Quote tick row
# ---------------------------------------------------------------------------

class QuoteTick(BaseModel):
    """A single instrument quote row for the table."""

    source: str = Field(..., description="Backend data-source id")
    source_label: str = Field(..., description="Display label")
    symbol: str = Field(..., description="Instrument code")
    name: str = Field("", description="Instrument name")
    exchange: str = Field("", description="Exchange or category")
    category: str = Field("", description="Instrument category")
    last_price: float | None = Field(None, description="Latest price")
    change: float | None = Field(None, description="Price change amount")
    change_pct: float | None = Field(None, description="Price change percent")
    bid_price: float | None = Field(None, description="Best bid")
    ask_price: float | None = Field(None, description="Best ask")
    high_price: float | None = Field(None, description="Highest price")
    low_price: float | None = Field(None, description="Lowest price")
    open_price: float | None = Field(None, description="Opening price")
    prev_close: float | None = Field(None, description="Previous close")
    volume: float | None = Field(None, description="Volume")
    turnover: float | None = Field(None, description="Turnover / amount")
    open_interest: float | None = Field(None, description="Open interest")
    update_time: str | None = Field(None, description="Last update ISO timestamp")
    status: str = Field("normal", description="Row status: normal, missing, error")
    error_message: str | None = Field(None)


class QuoteListResponse(BaseModel):
    """Batch quote response."""

    source: str
    source_label: str
    total: int
    ticks: list[QuoteTick]
    update_time: str | None = Field(None, description="Server-side fetch timestamp")
    refresh_mode: str = Field(
        "polling",
        description="Current refresh mode: push | polling | manual",
    )


# ---------------------------------------------------------------------------
# Symbol management
# ---------------------------------------------------------------------------

class SymbolItem(BaseModel):
    """A symbol entry (for search results or default list)."""

    symbol: str
    name: str = ""
    exchange: str = ""
    category: str = ""


class SymbolSearchRequest(BaseModel):
    """Search symbols within a data source."""

    source: str = Field(..., description="Backend data-source id")
    keyword: str = Field(..., min_length=1, description="Search keyword")


class SymbolSearchResponse(BaseModel):
    """Search result."""

    source: str
    keyword: str
    results: list[SymbolItem]


class CustomSymbolsRequest(BaseModel):
    """Add or remove custom symbols."""

    source: str = Field(..., description="Backend data-source id")
    symbols: list[str] = Field(..., min_length=1)


class CustomSymbolsResponse(BaseModel):
    """Current custom symbol list after mutation."""

    source: str
    symbols: list[str]


class DefaultSymbolsResponse(BaseModel):
    """Default + custom symbols for a data source."""

    source: str
    default_symbols: list[SymbolItem]
    custom_symbols: list[str]


# ---------------------------------------------------------------------------
# Chart data (P1)
# ---------------------------------------------------------------------------

class KlineBar(BaseModel):
    """A single OHLCV bar for chart rendering."""

    date: str = Field(..., description="Bar datetime string")
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class ChartDataResponse(BaseModel):
    """K-line / chart data response."""

    source: str
    symbol: str
    timeframe: str = Field("M1", description="Timeframe, e.g. M1, M5, M15, H1, D1")
    bars: list[KlineBar]
    total: int = 0
