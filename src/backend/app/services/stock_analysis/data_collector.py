"""Data collection for native stock analysis."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_instrument import MarketInstrumentService
from app.services.news_intelligence import get_news_intelligence_service


class StockAnalysisDataCollector:
    """Collect current-project data used by the stock analysis pipeline."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.market_service = MarketInstrumentService()

    async def collect(
        self,
        *,
        user_id: str,
        symbol: str,
        market_type: str,
        analysis_date: date,
    ) -> dict[str, Any]:
        market_payload = await self._collect_market(symbol=symbol, analysis_date=analysis_date)
        quote = self._build_quote(market_payload)
        info = self._build_info(market_payload)
        history = market_payload.get("history") or {"rows": []}
        financials = self._build_financials(market_payload)
        peers = {"items": [], "total": 0}
        technicals = {"factors": market_payload.get("indicators") or {}}
        news = await self._collect_news(user_id, symbol)

        missing_fields = [
            name
            for name, value in {
                "quote": quote,
                "info": info,
                "history": history.get("rows") if isinstance(history, dict) else None,
                "financials": financials,
                "technicals": technicals,
            }.items()
            if not value
        ]
        data_quality = {
            "status": "degraded" if missing_fields else "ok",
            "missing_fields": missing_fields,
            "degraded_reasons": ["新闻数据为空"] if not news.get("items") else [],
        }

        return {
            "symbol": symbol,
            "market_type": market_type,
            "analysis_date": analysis_date.isoformat(),
            "quote": quote,
            "info": info,
            "history": history,
            "financials": financials,
            "peers": peers,
            "technicals": technicals,
            "news": news,
            "data_quality": data_quality,
        }

    async def _collect_news(self, user_id: str, symbol: str) -> dict[str, Any]:
        try:
            return await get_news_intelligence_service(self.db).list_articles(
                user_id, ticker=symbol
            )
        except Exception:
            return {"items": [], "total": 0, "status": "degraded"}

    async def _collect_market(self, *, symbol: str, analysis_date: date) -> dict[str, Any]:
        end_date = analysis_date
        start_date = end_date - timedelta(days=365)
        try:
            return await self.market_service.lookup(
                asset_type="stock",
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                period="daily",
            )
        except Exception:
            return {
                "symbol": symbol,
                "name": symbol,
                "provider": None,
                "snapshot": {},
                "history": {"rows": []},
                "indicators": {},
            }

    @staticmethod
    def _build_quote(payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = payload.get("snapshot") or {}
        symbol = snapshot.get("symbol") or payload.get("symbol")
        return {
            "symbol": symbol,
            "name": snapshot.get("name") or payload.get("name") or symbol,
            "price": snapshot.get("price"),
            "previous_close": snapshot.get("previous_close"),
            "change": snapshot.get("change"),
            "change_pct": snapshot.get("change_pct"),
            "currency": "CNY",
            "provider": payload.get("provider"),
            "updated_at": snapshot.get("update_time"),
        }

    @staticmethod
    def _build_info(payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = payload.get("snapshot") or {}
        symbol = snapshot.get("symbol") or payload.get("symbol")
        return {
            "symbol": symbol,
            "name": snapshot.get("name") or payload.get("name") or symbol,
            "asset_type": "stock",
            "exchange": StockAnalysisDataCollector._infer_exchange(str(symbol or "")),
            "country": "CN",
            "listing_currency": "CNY",
            "provider": payload.get("provider"),
        }

    @staticmethod
    def _build_financials(payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = payload.get("snapshot") or {}
        valuation = {
            key: snapshot.get(key)
            for key in ("market_cap", "float_market_cap", "pe", "pb", "turnover")
            if snapshot.get(key) is not None
        }
        return {
            "symbol": payload.get("symbol"),
            "annual": [],
            "quarterly": [],
            "valuation": valuation,
            "provider": payload.get("provider"),
        }

    @staticmethod
    def _infer_exchange(symbol: str) -> str | None:
        code = symbol.strip().upper()
        if "." in code:
            code = code.split(".", 1)[0]
        if code.startswith(("6", "9")):
            return "SH"
        if code.startswith(("0", "2", "3")):
            return "SZ"
        if code.startswith(("4", "8")):
            return "BJ"
        return None
