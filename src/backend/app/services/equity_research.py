from __future__ import annotations

from typing import Any


class EquityResearchService:
    """Read-only equity research facade.

    The page should reflect real persisted/vendor data only. Until a symbol is backed by a
    concrete data source, return stable empty structures instead of synthetic market data.
    """

    def search(self, keyword: str) -> dict[str, Any]:
        return {"items": [], "total": 0}

    def get_quote(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "name": symbol,
            "price": None,
            "previous_close": None,
            "change_pct": None,
            "currency": None,
            "provider": None,
        }

    def info(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "name": symbol,
            "asset_type": None,
            "exchange": None,
            "sector": None,
            "industry": None,
            "country": None,
            "listing_currency": None,
            "description": None,
            "provider": None,
        }

    def history(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "rows": []}

    def financials(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "annual": [],
            "quarterly": [],
            "provider": None,
        }

    def peers(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "items": [], "total": 0}

    def technicals(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "factors": {}}


_equity_research_service = EquityResearchService()


def get_equity_research_service() -> EquityResearchService:
    return _equity_research_service
