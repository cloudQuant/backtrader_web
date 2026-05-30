import asyncio

import pytest


@pytest.mark.asyncio
async def test_data_topic_hub_ttl_coalesce_push_only_drop_and_retire():
    from app.services.data_topic_hub import DataTopicHub, Producer, TopicPolicy

    calls: list[list[str]] = []

    class QuoteProducer(Producer):
        def topic_patterns(self) -> list[str]:
            return ["market:quote:*"]

        async def refresh(self, topics: list[str]) -> dict[str, dict]:
            calls.append(topics)
            return {
                topic: {"symbol": topic.rsplit(":", 1)[-1], "price": 100 + len(calls)}
                for topic in topics
            }

        def max_requests_per_sec(self) -> float:
            return 100.0

    hub = DataTopicHub()
    hub.register_topic(
        "market:quote:RB2510",
        TopicPolicy(ttl_ms=200, coalesce_within_ms=50, drop_on_idle=True),
    )
    hub.register_topic("market:quote:PUSH", TopicPolicy(push_only=True, ttl_ms=200))
    hub.register_producer(QuoteProducer())

    first = await hub.peek("market:quote:RB2510")
    second = await hub.peek("market:quote:RB2510")
    assert first["price"] == second["price"]
    assert len(calls) == 1

    assert await hub.peek("market:quote:PUSH") is None

    received: list[dict] = []
    subscription_id = hub.subscribe(
        "tester", "market:quote:*", lambda topic, value: received.append(value)
    )
    await hub.push("market:quote:RB2510", {"price": 101})
    await hub.push("market:quote:RB2510", {"price": 102})
    await asyncio.sleep(0.06)
    assert received[-1] == {"price": 102}

    hub.unsubscribe(subscription_id)
    hub.retire_topic("market:quote:RB2510")
    assert hub.peek_raw("market:quote:RB2510") is None


@pytest.mark.asyncio
async def test_data_topic_hub_refresh_timeout_and_error_subscriber():
    from app.services.data_topic_hub import DataTopicHub, Producer, TopicPolicy

    class SlowProducer(Producer):
        def topic_patterns(self) -> list[str]:
            return ["market:history:*"]

        async def refresh(self, topics: list[str]) -> dict[str, dict]:
            await asyncio.sleep(0.05)
            return {topic: {"ok": True} for topic in topics}

    errors: list[dict] = []
    hub = DataTopicHub()
    hub.register_topic("market:history:RB2510:D1:1d", TopicPolicy(refresh_timeout_ms=10))
    hub.register_producer(SlowProducer())
    hub.subscribe_errors(lambda error: errors.append(error))

    value = await hub.request("market:history:RB2510:D1:1d", force=True)

    assert value is None
    assert errors[-1]["topic"] == "market:history:RB2510:D1:1d"
    assert errors[-1]["code"] == "refresh_timeout"


@pytest.mark.asyncio
async def test_data_topic_hub_push_forwards_to_ws_gateway():
    from app.services.data_topic_hub import DataTopicHub, TopicPolicy
    from app.services.ws_gateway import WSGateway

    hub = DataTopicHub()
    gateway = WSGateway(token_validator=lambda token: True)
    await gateway.connect("client-a", token="ok")
    await gateway.subscribe("client-a", ["market:quote:*"])
    hub.set_ws_gateway(gateway)
    hub.register_topic("market:quote:RB2510", TopicPolicy(ttl_ms=200))

    delivered = await hub.push("market:quote:RB2510", {"price": 101})

    assert delivered == 1
    assert gateway._messages == [("client-a", "market:quote:RB2510", {"price": 101})]
