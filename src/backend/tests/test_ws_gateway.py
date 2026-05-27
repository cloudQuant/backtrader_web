import asyncio

import pytest


@pytest.mark.asyncio
async def test_ws_gateway_auth_subscribe_and_publish_fanout():
    from app.services.ws_gateway import WSGateway

    gateway = WSGateway(token_validator=lambda token: token == "valid")

    assert await gateway.connect("client-bad", token="bad") is False
    assert await gateway.connect("client-a", token="valid") is True
    assert await gateway.connect("client-b", token="valid") is True

    await gateway.subscribe("client-a", ["market:quote:*"])
    await gateway.subscribe("client-b", ["market:quote:RB2510"])
    delivered = await gateway.publish("market:quote:RB2510", {"price": 100})

    assert delivered == 2
    assert gateway.metrics().connection_count == 2
    assert gateway.metrics().subscription_count == 2


@pytest.mark.asyncio
async def test_ws_gateway_heartbeat_timeout_disconnects_idle_client():
    from app.services.ws_gateway import WSGateway

    gateway = WSGateway(token_validator=lambda token: True, heartbeat_timeout_ms=5)
    await gateway.connect("client-a", token="any")
    await asyncio.sleep(0.01)

    closed = gateway.close_idle_connections()

    assert closed == ["client-a"]
    assert gateway.metrics().connection_count == 0
