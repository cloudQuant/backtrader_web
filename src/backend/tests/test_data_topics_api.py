import asyncio

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.db.database import create_default_admin
from tests.conftest import register_and_login

settings = get_settings()


async def _get_admin_headers(client: AsyncClient) -> dict[str, str]:
    await create_default_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_data_topics_list_refresh_and_stats_require_admin(client: AsyncClient, monkeypatch):
    import app.services.data_topic_hub as data_topic_module
    from app.services.ws_gateway import WSGateway

    class QuoteProducer(data_topic_module.Producer):
        def topic_patterns(self) -> list[str]:
            return ["market:quote:*"]

        async def refresh(self, topics: list[str]) -> dict[str, dict]:
            return {topic: {"symbol": topic.rsplit(":", 1)[-1], "price": 100.0} for topic in topics}

    hub = data_topic_module.DataTopicHub()
    hub.register_topic("market:quote:RB2510", data_topic_module.TopicPolicy(ttl_ms=200))
    hub.register_producer(QuoteProducer())
    hub.subscribe("page-a", "market:quote:*", lambda topic, value: None)
    gateway = WSGateway(token_validator=lambda token: True)
    await gateway.connect("client-a", token="ok")
    await gateway.subscribe("client-a", ["market:quote:*"])
    hub.set_ws_gateway(gateway)
    monkeypatch.setattr(data_topic_module, "_shared_hub", hub)

    _, headers = await register_and_login(client, username="data_topics_user")

    listed = await client.get("/api/v1/data-topics", headers=headers)
    refreshed = await client.post(
        "/api/v1/data-topics/market:quote:RB2510/refresh", headers=headers
    )
    stats_non_admin = await client.get("/api/v1/data-topics/stats", headers=headers)
    stats_admin = await client.get(
        "/api/v1/data-topics/stats", headers=await _get_admin_headers(client)
    )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["topic"] == "market:quote:RB2510"
    assert listed.json()["items"][0]["subscription_count"] == 1
    assert listed.json()["items"][0]["last_error"] is None

    assert refreshed.status_code == 200
    assert refreshed.json()["value"]["symbol"] == "RB2510"

    assert stats_non_admin.status_code == 403
    assert stats_admin.status_code == 200
    assert stats_admin.json()["total_topics"] == 1
    assert stats_admin.json()["topics_with_value"] == 1
    assert stats_admin.json()["subscription_count"] == 1
    assert stats_admin.json()["ws_gateway"]["connection_count"] == 1
    assert stats_admin.json()["ws_gateway"]["subscription_count"] == 1


@pytest.mark.asyncio
async def test_data_topics_list_and_stats_expose_last_refresh_error(
    client: AsyncClient, monkeypatch
):
    import app.services.data_topic_hub as data_topic_module

    class SlowProducer(data_topic_module.Producer):
        def topic_patterns(self) -> list[str]:
            return ["market:history:*"]

        async def refresh(self, topics: list[str]) -> dict[str, dict]:
            await asyncio.sleep(0.05)
            return {topic: {"ok": True} for topic in topics}

    hub = data_topic_module.DataTopicHub()
    hub.register_topic(
        "market:history:RB2510:D1:1d", data_topic_module.TopicPolicy(refresh_timeout_ms=10)
    )
    hub.register_producer(SlowProducer())
    monkeypatch.setattr(data_topic_module, "_shared_hub", hub)

    _, headers = await register_and_login(client, username="data_topics_error_user")

    refreshed = await client.post(
        "/api/v1/data-topics/market:history:RB2510:D1:1d/refresh", headers=headers
    )
    listed = await client.get("/api/v1/data-topics", headers=headers)
    stats_admin = await client.get(
        "/api/v1/data-topics/stats", headers=await _get_admin_headers(client)
    )

    assert refreshed.status_code == 200
    assert refreshed.json()["value"] is None
    assert listed.status_code == 200
    assert listed.json()["items"][0]["last_error"]["code"] == "refresh_timeout"
    assert stats_admin.status_code == 200
    assert stats_admin.json()["error_count"] == 1
