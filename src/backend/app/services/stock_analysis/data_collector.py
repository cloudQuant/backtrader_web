"""Data collection for native stock analysis."""

from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_instrument import MarketInstrumentService
from app.services.news_intelligence import get_news_intelligence_service


class StockAnalysisDataCollector:
    """Collect current-project data used by the stock analysis pipeline."""

    _BULLISH_NEWS_TERMS = (
        "增长",
        "增持",
        "回购",
        "分红",
        "预增",
        "上调",
        "获批",
        "中标",
        "突破",
        "改善",
        "利好",
    )
    _BEARISH_NEWS_TERMS = (
        "下滑",
        "下降",
        "亏损",
        "减持",
        "处罚",
        "立案",
        "风险",
        "违约",
        "暴跌",
        "利空",
        "监管",
    )

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
        info, peers = await self._collect_company_context(
            symbol=symbol,
            market_type=market_type,
            market_payload=market_payload,
        )
        history = market_payload.get("history") or {"rows": []}
        financials = await self._collect_financials(
            symbol=symbol,
            market_type=market_type,
            analysis_date=analysis_date,
            market_payload=market_payload,
        )
        technicals = {"factors": market_payload.get("indicators") or {}}
        news = await self._collect_news(user_id, symbol, market_type)

        missing_fields = [
            name
            for name, value in {
                "quote": quote,
                "info": info,
                "history": history.get("rows") if isinstance(history, dict) else None,
                "financials": self._has_financial_data(financials),
                "technicals": technicals,
            }.items()
            if value is False or not value
        ]
        degraded_reasons: list[str] = []
        if not self._has_financial_data(financials):
            degraded_reasons.append("财务数据为空")
        if not news.get("items"):
            degraded_reasons.append("新闻数据为空")
        data_quality = {
            "status": "degraded" if missing_fields else "ok",
            "missing_fields": missing_fields,
            "degraded_reasons": degraded_reasons,
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

    async def _collect_news(self, user_id: str, symbol: str, market_type: str) -> dict[str, Any]:
        local_news = {"items": [], "total": 0, "status": "degraded"}
        try:
            local_news = await get_news_intelligence_service(self.db).list_articles(
                user_id, ticker=symbol
            )
            if not local_news.get("items"):
                normalized_symbol = self._cn_stock_code(symbol)
                if normalized_symbol != symbol.upper():
                    local_news = await get_news_intelligence_service(self.db).list_articles(
                        user_id, ticker=normalized_symbol
                    )
        except Exception:
            pass

        if local_news.get("items") or not self._is_cn_stock(symbol, market_type):
            return local_news

        try:
            raw_news = await asyncio.to_thread(
                self._fetch_cn_stock_news, self._cn_stock_code(symbol)
            )
            items = self._normalize_cn_news(raw_news, symbol)
        except Exception:
            items = []
        if not items:
            return local_news
        return {
            "items": items,
            "total": len(items),
            "status": "ok",
            "provider": "akshare",
        }

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
                # Submitting a stock-analysis task is an explicit user query.
                # Do not let a stale warehouse snapshot masquerade as current data.
                refresh_online=True,
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

    async def _collect_company_context(
        self,
        *,
        symbol: str,
        market_type: str,
        market_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Enrich an explicit A-share analysis request with issuer and peer context."""
        info = self._build_info(market_payload)
        peers = {"items": [], "total": 0}
        if not self._is_cn_stock(symbol, market_type):
            return info, peers

        try:
            profile_frame = await asyncio.to_thread(
                self._fetch_cn_company_profile, self._cn_xq_symbol(symbol)
            )
        except Exception:
            return info, peers

        profile = self._frame_key_values(profile_frame)
        info = self._merge_cn_company_profile(info, profile)
        industry = self._profile_industry(profile)
        if not industry:
            return info, peers

        try:
            members_frame = await asyncio.to_thread(self._fetch_cn_industry_members, industry)
        except Exception:
            return info, peers
        items = self._normalize_cn_industry_peers(
            members_frame,
            symbol=symbol,
            industry=industry,
        )
        if not items:
            return info, peers
        return info, {"items": items, "total": len(items), "provider": "akshare"}

    async def _collect_financials(
        self,
        *,
        symbol: str,
        market_type: str,
        analysis_date: date,
        market_payload: dict[str, Any],
    ) -> dict[str, Any]:
        financials = self._build_financials(market_payload)
        if not self._is_cn_stock(symbol, market_type):
            return financials

        try:
            abstract, indicators = await asyncio.to_thread(
                self._fetch_cn_financial_frames,
                self._cn_stock_code(symbol),
                analysis_date.year - 2,
            )
            annual, quarterly = self._normalize_cn_financials(
                abstract,
                indicators,
                analysis_date=analysis_date,
            )
        except Exception:
            return financials

        if annual or quarterly:
            financials.update(
                {
                    "annual": annual,
                    "quarterly": quarterly,
                    "provider": "akshare",
                }
            )
        return financials

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
    def _is_cn_stock(symbol: str, market_type: str) -> bool:
        return market_type == "A股" and bool(
            re.fullmatch(r"\d{6}", StockAnalysisDataCollector._cn_stock_code(symbol))
        )

    @staticmethod
    def _cn_stock_code(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]
        if normalized.startswith(("SH", "SZ", "BJ")):
            normalized = normalized[2:]
        return normalized

    @staticmethod
    def _fetch_cn_financial_frames(symbol: str, start_year: int) -> tuple[Any, Any]:
        import akshare as ak

        return (
            ak.stock_financial_abstract(symbol=symbol),
            ak.stock_financial_analysis_indicator(symbol=symbol, start_year=str(start_year)),
        )

    @staticmethod
    def _fetch_cn_stock_news(symbol: str) -> Any:
        import akshare as ak

        return ak.stock_news_em(symbol=symbol)

    @staticmethod
    def _fetch_cn_company_profile(symbol: str) -> Any:
        import akshare as ak

        return ak.stock_individual_basic_info_xq(symbol=symbol)

    @staticmethod
    def _fetch_cn_industry_members(industry: str) -> Any:
        import akshare as ak

        return ak.stock_board_industry_cons_em(symbol=industry)

    @classmethod
    def _normalize_cn_financials(
        cls,
        abstract: Any,
        indicators: Any,
        *,
        analysis_date: date,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        abstract_rows = cls._frame_rows(abstract)
        if not abstract_rows:
            return [], []

        date_columns = sorted(
            {
                report_date
                for row in abstract_rows
                for column in row
                if (report_date := cls._report_date(column)) is not None
                and report_date <= analysis_date.isoformat()
            }
        )
        metric_candidates = {
            "revenue": ("营业总收入", "营业收入"),
            "net_income": ("归母净利润", "净利润"),
            "eps": ("基本每股收益", "摊薄每股收益"),
            "roe": ("净资产收益率(ROE)", "净资产收益率"),
        }
        metric_rows: dict[str, dict[str, Any]] = {}
        for field, candidates in metric_candidates.items():
            for candidate in candidates:
                matched = next(
                    (
                        row
                        for row in abstract_rows
                        if str(row.get("指标") or "").strip() == candidate
                    ),
                    None,
                )
                if matched is not None:
                    metric_rows[field] = matched
                    break

        growth_by_date: dict[str, dict[str, float]] = {}
        for row in cls._frame_rows(indicators):
            report_date = cls._report_date(row.get("日期"))
            if report_date is None or report_date > analysis_date.isoformat():
                continue
            growth = {
                field: value
                for field, column in {
                    "revenue_growth": "主营业务收入增长率(%)",
                    "profit_growth": "净利润增长率(%)",
                }.items()
                if (value := cls._number(row.get(column))) is not None
            }
            if growth:
                growth_by_date[report_date] = growth

        records: list[dict[str, Any]] = []
        for report_date in date_columns:
            compact_date = report_date.replace("-", "")
            record: dict[str, Any] = {"report_date": report_date}
            for field, row in metric_rows.items():
                if (value := cls._number(row.get(compact_date))) is not None:
                    record[field] = value
            record.update(growth_by_date.get(report_date, {}))
            if len(record) > 1:
                records.append(record)

        annual = [record for record in records if record["report_date"].endswith("-12-31")][-2:]
        quarterly = [record for record in records if not record["report_date"].endswith("-12-31")][
            -4:
        ]
        return annual, quarterly

    @classmethod
    def _normalize_cn_news(cls, raw_news: Any, symbol: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in cls._frame_rows(raw_news)[:20]:
            headline = str(row.get("新闻标题") or "").strip()
            if not headline:
                continue
            content = str(row.get("新闻内容") or "").strip()
            sentiment = cls._classify_cn_news_sentiment(f"{headline} {content}")
            items.append(
                {
                    "headline": headline,
                    "summary": content,
                    "content": content,
                    "published_at": str(row.get("发布时间") or "").strip() or None,
                    "source": str(row.get("文章来源") or "AkShare").strip() or "AkShare",
                    "url": str(row.get("新闻链接") or "").strip(),
                    "tickers": [symbol],
                    "sentiment": sentiment,
                    "impact": "MEDIUM" if sentiment != "UNKNOWN" else "UNKNOWN",
                    "threat": "MEDIUM" if sentiment == "BEARISH" else "UNKNOWN",
                    "status": "ok",
                    "source_flag": "akshare",
                }
            )
        return items

    @classmethod
    def _classify_cn_news_sentiment(cls, text: str) -> str:
        """Classify only supported directional evidence; unknown is not neutral evidence."""
        normalized = text.strip()
        bullish = sum(term in normalized for term in cls._BULLISH_NEWS_TERMS)
        bearish = sum(term in normalized for term in cls._BEARISH_NEWS_TERMS)
        if bullish > bearish and bullish:
            return "BULLISH"
        if bearish > bullish and bearish:
            return "BEARISH"
        return "UNKNOWN"

    @staticmethod
    def _frame_key_values(frame: Any) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for row in StockAnalysisDataCollector._frame_rows(frame):
            key = str(row.get("item") or "").strip()
            if key:
                values[key] = row.get("value")
        return values

    @classmethod
    def _merge_cn_company_profile(
        cls, info: dict[str, Any], profile: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(info)
        name = cls._text(profile.get("org_short_name_cn")) or cls._text(profile.get("org_name_cn"))
        description = cls._text(profile.get("main_operation_business")) or cls._text(
            profile.get("org_cn_introduction")
        )
        industry = cls._profile_industry(profile)
        if name:
            merged["name"] = name
        if description:
            merged["description"] = description
        if industry:
            merged["industry"] = industry
            merged["sector"] = cls._cn_sector(industry)
        if name or description or industry:
            merged["company_profile_provider"] = "akshare.xueqiu"
        return merged

    @classmethod
    def _normalize_cn_industry_peers(
        cls, frame: Any, *, symbol: str, industry: str
    ) -> list[dict[str, Any]]:
        requested_code = cls._cn_stock_code(symbol)
        items: list[dict[str, Any]] = []
        seen_codes: set[str] = set()
        for row in cls._frame_rows(frame):
            code = cls._cn_stock_code(str(row.get("代码") or row.get("symbol") or ""))
            name = cls._text(row.get("名称") or row.get("name"))
            if (
                not re.fullmatch(r"\d{6}", code)
                or code == requested_code
                or code in seen_codes
                or not name
            ):
                continue
            seen_codes.add(code)
            items.append(
                {
                    "symbol": cls._cn_stock_symbol(code),
                    "name": name,
                    "industry": industry,
                }
            )
            if len(items) == 3:
                break
        return items

    @staticmethod
    def _frame_rows(frame: Any) -> list[dict[str, Any]]:
        try:
            rows = frame.to_dict(orient="records")
        except (AttributeError, TypeError, ValueError):
            return []
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _profile_industry(cls, profile: dict[str, Any]) -> str | None:
        value = profile.get("affiliate_industry")
        if isinstance(value, dict):
            return cls._text(value.get("ind_name") or value.get("name"))
        text = cls._text(value)
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(parsed, dict):
            return cls._text(parsed.get("ind_name") or parsed.get("name"))
        return text

    @staticmethod
    def _cn_sector(industry: str) -> str:
        return "金融业" if "银行" in industry else industry

    @classmethod
    def _cn_xq_symbol(cls, symbol: str) -> str:
        code = cls._cn_stock_code(symbol)
        exchange = cls._infer_exchange(code)
        return f"{exchange}{code}" if exchange else code

    @classmethod
    def _cn_stock_symbol(cls, code: str) -> str:
        exchange = cls._infer_exchange(code)
        return f"{code}.{exchange}" if exchange else code

    @staticmethod
    def _report_date(value: Any) -> str | None:
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) != 8:
            return None
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:])).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) else None

    @staticmethod
    def _has_financial_data(financials: dict[str, Any]) -> bool:
        return bool(financials.get("annual") or financials.get("quarterly"))

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
