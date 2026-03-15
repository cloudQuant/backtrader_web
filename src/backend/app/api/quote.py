"""
Quote page API routes.

Provides endpoints for the unified quote display page:
- Data-source listing with status
- Default + custom symbol management
- Batch quote fetching
- Symbol search
"""

import logging

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.schemas.quote import (
    ChartDataResponse,
    CustomSymbolsRequest,
    CustomSymbolsResponse,
    DataSourceListResponse,
    DefaultSymbolsResponse,
    QuoteListResponse,
    SymbolSearchResponse,
)
from app.services.quote_service import QuoteService, get_quote_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Data Sources ====================


@router.get(
    "/sources",
    response_model=DataSourceListResponse,
    summary="List available data sources with status",
)
async def list_data_sources(
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Return all data sources (CTP, IB, MT5, Binance, OKX) with their
    current availability status derived from gateway connections."""
    sources = svc.get_data_sources()
    return {"sources": sources}


# ==================== Symbols ====================


@router.get(
    "/symbols",
    response_model=DefaultSymbolsResponse,
    summary="Get default + custom symbols for a data source",
)
async def get_symbols(
    source: str = Query(..., description="Backend data-source id, e.g. CTP"),
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Return the default symbol list and the user's custom symbols for the
    specified data source."""
    return svc.get_symbols(source, current_user.sub)


@router.post(
    "/symbols/add",
    response_model=CustomSymbolsResponse,
    summary="Add custom symbols",
)
async def add_custom_symbols(
    req: CustomSymbolsRequest,
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Add one or more custom symbols for the current user and data source."""
    updated = svc.add_custom_symbols(req.source, current_user.sub, req.symbols)
    return {"source": req.source, "symbols": updated}


@router.post(
    "/symbols/remove",
    response_model=CustomSymbolsResponse,
    summary="Remove custom symbols",
)
async def remove_custom_symbols(
    req: CustomSymbolsRequest,
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Remove one or more custom symbols for the current user and data source."""
    updated = svc.remove_custom_symbols(req.source, current_user.sub, req.symbols)
    return {"source": req.source, "symbols": updated}


@router.get(
    "/symbols/search",
    response_model=SymbolSearchResponse,
    summary="Search symbols within a data source",
)
async def search_symbols(
    source: str = Query(..., description="Backend data-source id"),
    keyword: str = Query(..., min_length=1, description="Search keyword"),
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Search symbols by code or name within the specified data source."""
    results = svc.search_symbols(source, keyword)
    return {"source": source, "keyword": keyword, "results": results}


# ==================== Quotes ====================


@router.get(
    "/ticks",
    response_model=QuoteListResponse,
    summary="Fetch quotes for a data source",
)
async def get_quotes(
    source: str = Query(..., description="Backend data-source id"),
    symbols: str | None = Query(None, description="Comma-separated symbols (optional)"),
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Fetch batch quotes for the given data source.

    If *symbols* is omitted, returns quotes for all default + custom symbols.
    """
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    return svc.get_quotes(source, current_user.sub, symbol_list)


# ==================== Chart Data (P1) ====================


@router.get(
    "/chart",
    response_model=ChartDataResponse,
    summary="Fetch K-line / chart data for a symbol",
)
async def get_chart_data(
    source: str = Query(..., description="Backend data-source id"),
    symbol: str = Query(..., description="Instrument symbol"),
    timeframe: str = Query("M1", description="Timeframe: M1, M5, M15, M30, H1, H4, D1"),
    count: int = Query(200, ge=10, le=1000, description="Number of bars"),
    current_user=Depends(get_current_user),
    svc: QuoteService = Depends(get_quote_service),
):
    """Fetch OHLCV bars for chart rendering via gateway command channel."""
    return svc.get_chart_data(source, symbol, timeframe, count)
