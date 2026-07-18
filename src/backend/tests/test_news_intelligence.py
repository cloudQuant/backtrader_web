import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.news_intelligence import NewsAnalysisModel, NewsArticleModel, NewsSourceModel
from app.services.data_topic_hub import TopicPolicy, get_shared_data_topic_hub
from app.services.news_intelligence import NewsIntelligenceService
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_news_intelligence_dedup_classify_cluster_and_publish_topic(client: AsyncClient):
    _, headers = await register_and_login(client, username="news_user")
    hub = get_shared_data_topic_hub()
    hub.register_topic("news:symbol:RB2510", TopicPolicy(push_only=True))

    source = await client.post(
        "/api/v1/news-intelligence/sources",
        headers=headers,
        json={"name": "demo", "url": "https://example.com/rss", "tier": 2},
    )
    ingest = await client.post(
        "/api/v1/news-intelligence/articles/ingest",
        headers=headers,
        json={
            "articles": [
                {
                    "headline": "RB2510 surges after bullish demand shock",
                    "url": "https://example.com/a?utm_source=x",
                    "source": "demo",
                    "tickers": ["RB2510"],
                },
                {
                    "headline": "RB2510 surges after bullish demand shock",
                    "url": "https://example.com/a",
                    "source": "demo",
                    "tickers": ["RB2510"],
                },
            ]
        },
    )
    latest = await client.get("/api/v1/news-intelligence/articles", headers=headers)
    topic = hub.peek_raw("news:symbol:RB2510")

    assert source.status_code == 201
    assert ingest.status_code == 200
    assert ingest.json()["inserted_count"] == 1
    assert latest.status_code == 200
    article = latest.json()["items"][0]
    assert article["sentiment"] == "BULLISH"
    assert article["impact"] in {"HIGH", "MEDIUM", "LOW"}
    assert article["cluster_id"]
    assert article["summary"]
    assert topic["headline"].startswith("RB2510")

    async with async_session_maker() as session:
        sources = (await session.execute(select(NewsSourceModel))).scalars().all()
        articles = (await session.execute(select(NewsArticleModel))).scalars().all()
        analyses = (await session.execute(select(NewsAnalysisModel))).scalars().all()

    assert len(sources) == 1
    assert len(articles) == 1
    assert len(analyses) == 1
    assert articles[0].canonical_url == "https://example.com/a"


@pytest.mark.asyncio
async def test_news_intelligence_ai_fallback_degrades_when_unavailable(client: AsyncClient):
    _, headers = await register_and_login(client, username="news_degraded")

    response = await client.post(
        "/api/v1/news-intelligence/analyze",
        headers=headers,
        json={"headline": "Unclear macro policy update", "allow_ai": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}
    assert response.json()["sentiment"] in {"BULLISH", "BEARISH", "NEUTRAL"}

    async with async_session_maker() as session:
        analyses = (await session.execute(select(NewsAnalysisModel))).scalars().all()

    assert len(analyses) == 1


@pytest.mark.asyncio
async def test_news_intelligence_pull_source_and_filter_articles(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_rss_fetcher(self, url: str) -> str:
        assert url == "https://example.com/feed.xml"
        return """
<rss>
  <channel>
    <item>
      <title>RB2510 surges after bullish demand shock</title>
      <link>https://example.com/rss/rb2510?utm_source=test</link>
      <description>Demand shock lifted steel-linked futures.</description>
      <category>RB2510</category>
    </item>
    <item>
      <title>BU2501 drops on weak inventory data</title>
      <link>https://example.com/rss/bu2501</link>
      <category>BU2501</category>
    </item>
  </channel>
</rss>
"""

    monkeypatch.setattr(NewsIntelligenceService, "_default_rss_fetcher", fake_rss_fetcher)
    _, headers = await register_and_login(client, username="news_pull_user")

    source = await client.post(
        "/api/v1/news-intelligence/sources",
        headers=headers,
        json={
            "name": "terminal-rss",
            "url": "https://example.com/feed.xml",
            "tier": 2,
            "metadata": {"tickers": ["RB2510"]},
        },
    )
    pulled = await client.post(
        "/api/v1/news-intelligence/sources/terminal-rss/pull",
        headers=headers,
        params={"limit": 10},
    )
    bullish = await client.get(
        "/api/v1/news-intelligence/articles",
        headers=headers,
        params={"sentiment": "BULLISH"},
    )
    rb_articles = await client.get(
        "/api/v1/news-intelligence/articles",
        headers=headers,
        params={"ticker": "RB2510"},
    )
    all_articles = await client.get(
        "/api/v1/news-intelligence/articles",
        headers=headers,
    )
    cluster_id = all_articles.json()["items"][0]["cluster_id"]
    cluster_articles = await client.get(
        "/api/v1/news-intelligence/articles",
        headers=headers,
        params={"cluster_id": cluster_id},
    )

    assert source.status_code == 201
    assert pulled.status_code == 200
    assert pulled.json()["status"] == "ok"
    assert pulled.json()["fetched_count"] == 2
    assert pulled.json()["inserted_count"] == 2

    assert bullish.status_code == 200
    assert bullish.json()["total"] == 1
    assert bullish.json()["items"][0]["headline"].startswith("RB2510")

    assert rb_articles.status_code == 200
    assert rb_articles.json()["total"] == 1
    assert rb_articles.json()["items"][0]["tickers"] == ["RB2510"]
    assert "Demand shock" in rb_articles.json()["items"][0]["summary"]

    assert cluster_articles.status_code == 200
    assert cluster_articles.json()["total"] == 1
    assert cluster_articles.json()["items"][0]["cluster_id"] == cluster_id


@pytest.mark.asyncio
async def test_news_intelligence_default_rss_fetcher_uses_financial_feed_headers(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    class FakeResponse:
        text = "<rss><channel></channel></rss>"

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str, **kwargs):
            captured["url"] = url
            captured["get_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr("app.services.news_intelligence.httpx.AsyncClient", FakeAsyncClient)

    body = await NewsIntelligenceService()._default_rss_fetcher(
        "https://feeds.bloomberg.com/markets/news.rss"
    )

    get_kwargs = captured["get_kwargs"]
    assert body.startswith("<rss")
    assert captured["url"] == "https://feeds.bloomberg.com/markets/news.rss"
    assert "headers" in get_kwargs
    assert "Mozilla/5.0" in get_kwargs["headers"]["User-Agent"]
    assert "application/rss+xml" in get_kwargs["headers"]["Accept"]
