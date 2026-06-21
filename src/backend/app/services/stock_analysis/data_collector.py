"""Data collection for native stock analysis."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.equity_research import get_equity_research_service
from app.services.news_intelligence import get_news_intelligence_service


class StockAnalysisDataCollector:
    """Collect current-project data used by the stock analysis pipeline."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.equity_research = get_equity_research_service()

    async def collect(
        self,
        *,
        user_id: str,
        symbol: str,
        market_type: str,
        analysis_date: date,
    ) -> dict[str, Any]:
        quote = self._safe_call(self.equity_research.get_quote, symbol, default={})
        info = self._safe_call(self.equity_research.info, symbol, default={})
        history = self._safe_call(self.equity_research.history, symbol, default={"rows": []})
        financials = self._safe_call(
            self.equity_research.financials, symbol, default={"annual": [], "quarterly": []}
        )
        peers = self._safe_call(self.equity_research.peers, symbol, default={"items": []})
        technicals = self._safe_call(self.equity_research.technicals, symbol, default={"factors": {}})
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
            return await get_news_intelligence_service(self.db).list_articles(user_id, ticker=symbol)
        except Exception:
            return {"items": [], "total": 0, "status": "degraded"}

    @staticmethod
    def _safe_call(func, *args, default):
        try:
            return func(*args)
        except Exception:
            return default
