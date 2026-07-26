from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_intelligence import (
    NewsAnalysisModel,
    NewsArticleModel,
    NewsSourceModel,
)
from app.services.data_topic_hub import get_shared_data_topic_hub

_RSS_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


class NewsIntelligenceService:
    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._hub = get_shared_data_topic_hub()
        self._rss_fetcher = self._default_rss_fetcher

    async def add_source(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_db()
        name = str(payload.get("name") or "").strip()
        result = await self.db.execute(
            select(NewsSourceModel).where(
                NewsSourceModel.owner_id == user_id,
                NewsSourceModel.name == name,
            )
        )
        source = result.scalar_one_or_none()
        if source is None:
            source = NewsSourceModel(
                owner_id=user_id,
                name=name,
                url=str(payload.get("url") or "").strip(),
                tier=int(payload.get("tier") or 2),
                status="active",
                metadata_json=dict(payload.get("metadata") or {}),
            )
            self.db.add(source)
        else:
            source.url = str(payload.get("url") or source.url or "").strip()
            source.tier = int(payload.get("tier") or source.tier or 2)
            source.status = str(payload.get("status") or source.status or "active")
            source.metadata_json = dict(payload.get("metadata") or source.metadata_json or {})
        await self.db.commit()
        await self.db.refresh(source)
        return self._serialize_source(source)

    async def ingest(self, user_id: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
        self._require_db()
        inserted = 0
        source_rows = (
            (
                await self.db.execute(
                    select(NewsSourceModel).where(NewsSourceModel.owner_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        sources = {source.name: source for source in source_rows}
        canonical_urls = [self._canonicalize_url(str(item.get("url") or "")) for item in articles]
        existing_keys = set(
            (
                await self.db.execute(
                    select(NewsArticleModel.canonical_url).where(
                        NewsArticleModel.owner_id == user_id,
                        NewsArticleModel.canonical_url.in_(canonical_urls),
                    )
                )
            )
            .scalars()
            .all()
        )
        for item in articles:
            canonical_url = self._canonicalize_url(str(item.get("url") or ""))
            if canonical_url in existing_keys:
                continue
            classified = self.analyze(item.get("headline", ""), allow_ai=False)
            cluster_id = hashlib.sha256(
                item.get("headline", "").lower().encode("utf-8")
            ).hexdigest()[:12]
            source_name = str(item.get("source") or "unknown")
            source = sources.get(source_name)
            headline = str(item.get("headline") or "").strip()
            article_summary = str(item.get("summary") or "").strip()
            article_content = str(item.get("content") or article_summary).strip()
            article = NewsArticleModel(
                owner_id=user_id,
                source_id=source.id if source is not None else None,
                source=source_name,
                headline=headline,
                url=str(item.get("url") or "").strip(),
                canonical_url=canonical_url,
                tickers=[
                    str(ticker).strip()
                    for ticker in list(item.get("tickers") or [])
                    if str(ticker).strip()
                ],
                priority=str(item.get("priority") or "P2"),
                tier=int(item.get("tier") or (source.tier if source is not None else 2)),
                source_flag=str(item.get("source_flag") or "rss"),
                sentiment=classified["sentiment"],
                impact=classified["impact"],
                threat=classified["threat"],
                cluster_id=cluster_id,
                summary=article_summary or self._build_summary(headline, classified),
                content=article_content
                or article_summary
                or self._build_summary(headline, classified),
                status=classified["status"],
            )
            self.db.add(article)
            await self.db.flush()
            self.db.add(
                NewsAnalysisModel(
                    owner_id=user_id,
                    article_id=article.id,
                    headline=article.headline,
                    sentiment=classified["sentiment"],
                    impact=classified["impact"],
                    threat=classified["threat"],
                    status=classified["status"],
                    provider="rules",
                )
            )
            existing_keys.add(canonical_url)
            inserted += 1
            record = self._serialize_article(article)
            await self._hub.push("news:general", record)
            await self._hub.push(f"news:cluster:{record['cluster_id']}", record)
            await self._hub.push(f"news:category:{record['sentiment'].lower()}", record)
            for ticker in record["tickers"]:
                await self._hub.push(f"news:symbol:{ticker}", record)
        await self.db.commit()
        total = await self._article_count(user_id)
        return {"inserted_count": inserted, "total": total}

    async def pull_source(
        self,
        user_id: str,
        source_name: str,
        *,
        limit: int = 20,
    ) -> dict[str, Any] | None:
        self._require_db()
        result = await self.db.execute(
            select(NewsSourceModel).where(
                NewsSourceModel.owner_id == user_id,
                NewsSourceModel.name == source_name,
            )
        )
        source = result.scalar_one_or_none()
        if source is None:
            return None
        try:
            feed_text = await self._rss_fetcher(str(source.url or ""))
            articles = self._parse_feed_items(feed_text, source, limit=limit)
        except (ET.ParseError, ValueError):
            return {
                "source": source_name,
                "status": "degraded",
                "reason": "invalid_feed",
                "fetched_count": 0,
                "inserted_count": 0,
                "total": await self._article_count(user_id),
            }
        except httpx.HTTPError:
            return {
                "source": source_name,
                "status": "degraded",
                "reason": "fetch_failed",
                "fetched_count": 0,
                "inserted_count": 0,
                "total": await self._article_count(user_id),
            }
        ingested = await self.ingest(user_id, articles)
        return {
            "source": source_name,
            "status": "ok",
            "fetched_count": len(articles),
            "inserted_count": ingested["inserted_count"],
            "total": ingested["total"],
        }

    async def list_articles(
        self,
        user_id: str,
        *,
        sentiment: str | None = None,
        source: str | None = None,
        ticker: str | None = None,
        cluster_id: str | None = None,
    ) -> dict[str, Any]:
        self._require_db()
        query = select(NewsArticleModel).where(NewsArticleModel.owner_id == user_id)
        if sentiment:
            query = query.where(NewsArticleModel.sentiment == str(sentiment).upper())
        if source:
            query = query.where(NewsArticleModel.source == str(source).strip())
        if cluster_id:
            query = query.where(NewsArticleModel.cluster_id == str(cluster_id).strip())
        result = await self.db.execute(query.order_by(NewsArticleModel.created_at.desc()))
        rows = list(result.scalars().all())
        if ticker:
            expected_ticker = str(ticker).strip().upper()
            rows = [
                item
                for item in rows
                if expected_ticker
                in {
                    str(value).strip().upper()
                    for value in list(item.tickers or [])
                    if str(value).strip()
                }
            ]
        items = [self._serialize_article(item) for item in rows]
        return {"items": items, "total": len(items)}

    async def get_article_content(self, user_id: str, article_id: str) -> dict[str, Any] | None:
        """Return the locally stored article body for the requesting owner only."""
        self._require_db()
        result = await self.db.execute(
            select(NewsArticleModel).where(
                NewsArticleModel.id == article_id,
                NewsArticleModel.owner_id == user_id,
            )
        )
        article = result.scalar_one_or_none()
        if article is None:
            return None
        content = str(article.content or article.summary or "").strip()
        return {
            "id": article.id,
            "headline": article.headline,
            "content": content,
            "summary": article.summary,
            "source": article.source,
            "url": article.url,
        }

    async def latest(self, user_id: str) -> dict[str, Any]:
        self._require_db()
        result = await self.db.execute(
            select(NewsArticleModel)
            .where(NewsArticleModel.owner_id == user_id)
            .order_by(NewsArticleModel.created_at.desc())
        )
        article = result.scalars().first()
        return (
            self._serialize_article(article)
            if article is not None
            else {"headline": "No news", "sentiment": "NEUTRAL"}
        )

    def analyze(self, headline: str, *, allow_ai: bool) -> dict[str, Any]:
        text = headline.lower()
        sentiment = "NEUTRAL"
        impact = "LOW"
        threat = "LOW"
        status = "ok"
        if any(word in text for word in ["surge", "bullish", "beat", "strong"]):
            sentiment = "BULLISH"
            impact = "HIGH"
        elif any(word in text for word in ["drop", "bearish", "miss", "weak"]):
            sentiment = "BEARISH"
            impact = "HIGH"
            threat = "HIGH"
        elif allow_ai:
            status = "degraded"
        return {"status": status, "sentiment": sentiment, "impact": impact, "threat": threat}

    async def analyze_headline(
        self,
        user_id: str,
        headline: str,
        *,
        allow_ai: bool,
    ) -> dict[str, Any]:
        self._require_db()
        result = self.analyze(headline, allow_ai=allow_ai)
        self.db.add(
            NewsAnalysisModel(
                owner_id=user_id,
                article_id=None,
                headline=headline,
                sentiment=result["sentiment"],
                impact=result["impact"],
                threat=result["threat"],
                status=result["status"],
                provider="rules" if result["status"] == "ok" else "fallback",
            )
        )
        await self.db.commit()
        return result

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        parsed = urlparse(url)
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ]
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), "")
        )

    async def _article_count(self, user_id: str) -> int:
        result = await self.db.execute(
            select(NewsArticleModel.id).where(NewsArticleModel.owner_id == user_id)
        )
        return len(list(result.scalars().all()))

    async def _default_rss_fetcher(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            response = await client.get(
                url,
                follow_redirects=True,
                headers=_RSS_REQUEST_HEADERS,
            )
            response.raise_for_status()
            return response.text

    def _parse_feed_items(
        self,
        feed_text: str,
        source: NewsSourceModel,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        root = ET.fromstring(feed_text)
        default_tickers = [
            str(item).strip()
            for item in list((source.metadata_json or {}).get("tickers") or [])
            if str(item).strip()
        ]
        items: list[dict[str, Any]] = []
        for entry in self._iter_feed_entries(root):
            headline = self._entry_text(entry, "title")
            link = self._entry_link(entry)
            if not headline or not link:
                continue
            categories = self._entry_categories(entry)
            tickers = categories or default_tickers
            summary = self._entry_summary(entry)
            items.append(
                {
                    "headline": headline,
                    "url": link,
                    "source": source.name,
                    "tickers": tickers,
                    "tier": source.tier,
                    "source_flag": "rss_pull",
                    "summary": summary,
                }
            )
            if len(items) >= max(limit, 1):
                break
        if not items:
            raise ValueError("invalid_feed")
        return items

    def _iter_feed_entries(self, root: ET.Element) -> list[ET.Element]:
        entries = [
            element for element in root.iter() if self._tag_name(element.tag) in {"item", "entry"}
        ]
        return entries

    def _entry_text(self, entry: ET.Element, field_name: str) -> str:
        for child in entry:
            if self._tag_name(child.tag) == field_name:
                return " ".join(str(text).strip() for text in child.itertext() if str(text).strip())
        return ""

    def _entry_summary(self, entry: ET.Element) -> str:
        for field_name in ("description", "summary", "encoded", "content"):
            text = self._entry_text(entry, field_name)
            if text:
                return self._clean_feed_text(text)
        return ""

    def _entry_link(self, entry: ET.Element) -> str:
        for child in entry:
            if self._tag_name(child.tag) != "link":
                continue
            href = str(child.attrib.get("href") or "").strip()
            if href:
                return href
            text = str(child.text or "").strip()
            if text:
                return text
        return ""

    def _entry_categories(self, entry: ET.Element) -> list[str]:
        categories: list[str] = []
        for child in entry:
            if self._tag_name(child.tag) != "category":
                continue
            value = str(child.attrib.get("term") or child.text or "").strip()
            if value:
                categories.append(value)
        return categories

    def _tag_name(self, tag: str) -> str:
        return str(tag).split("}")[-1].split(":")[-1]

    def _clean_feed_text(self, text: str) -> str:
        decoded = html.unescape(str(text or "")).strip()
        without_tags = re.sub(r"<[^>]+>", " ", decoded)
        return " ".join(without_tags.split())

    def _serialize_source(self, source: NewsSourceModel) -> dict[str, Any]:
        return {
            "id": source.id,
            "name": source.name,
            "url": source.url,
            "tier": source.tier,
            "status": source.status,
        }

    def _serialize_article(self, article: NewsArticleModel) -> dict[str, Any]:
        return {
            "id": article.id,
            "headline": article.headline,
            "url": article.url,
            "canonical_url": article.canonical_url,
            "source": article.source,
            "tickers": list(article.tickers or []),
            "priority": article.priority,
            "tier": article.tier,
            "source_flag": article.source_flag,
            "sentiment": article.sentiment,
            "impact": article.impact,
            "threat": article.threat,
            "cluster_id": article.cluster_id,
            "summary": article.summary,
            "has_content": bool(str(article.content or article.summary or "").strip()),
            "status": article.status,
        }

    def _build_summary(self, headline: str, classified: dict[str, Any]) -> str:
        return (
            f"{headline} | sentiment={classified['sentiment']} | "
            f"impact={classified['impact']} | threat={classified['threat']}"
        )

    def _require_db(self) -> None:
        if self.db is None:
            raise RuntimeError("database_session_required")


def get_news_intelligence_service(db: AsyncSession | None = None) -> NewsIntelligenceService:
    return NewsIntelligenceService(db)
