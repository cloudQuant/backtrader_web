import pytest


@pytest.mark.asyncio
async def test_capability_status_returns_product_domains(client):
    response = await client.get("/api/v1/status/capabilities")

    assert response.status_code == 200
    payload = response.json()
    domain_ids = {domain["id"] for domain in payload["domains"]}

    assert {"data", "research", "trading", "portfolio", "ai", "admin"} <= domain_ids
    research = next(domain for domain in payload["domains"] if domain["id"] == "research")
    assert research["status"] == "available"
    assert any(capability["id"] == "research.backtests" for capability in research["capabilities"])
    capability_ids = {
        capability["id"]
        for domain in payload["domains"]
        for capability in domain["capabilities"]
    }
    assert "trading.brokers" not in capability_ids
    assert "portfolio.ledger" not in capability_ids


@pytest.mark.asyncio
async def test_capability_status_marks_optional_router_degraded(client, monkeypatch):
    from app.api import router as router_module

    monkeypatch.setitem(
        router_module.optional_router_status,
        "kb_chat",
        {"available": False, "error": "import failed"},
    )

    response = await client.get("/api/v1/status/capabilities")

    assert response.status_code == 200
    ai_domain = next(domain for domain in response.json()["domains"] if domain["id"] == "ai")
    chat_capability = next(
        capability for capability in ai_domain["capabilities"] if capability["id"] == "ai.chat"
    )

    assert ai_domain["status"] == "degraded"
    assert chat_capability["available"] is False
    assert "kb_chat" in chat_capability["degraded_reason"]


@pytest.mark.asyncio
async def test_router_status_endpoint_keeps_existing_shape(client):
    response = await client.get("/api/v1/status/routers")

    assert response.status_code == 200
    assert "optional_routers" in response.json()
