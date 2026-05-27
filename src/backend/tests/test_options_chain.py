import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


def test_max_pain_against_manual():
    from app.services.options_chain import OptionsChainService

    service = OptionsChainService()
    rows = [
        {"strike": 90.0, "call": {"oi": 10}, "put": {"oi": 100}},
        {"strike": 100.0, "call": {"oi": 20}, "put": {"oi": 20}},
        {"strike": 110.0, "call": {"oi": 100}, "put": {"oi": 10}},
    ]

    assert abs(service.calculate_max_pain(rows) - 100.0) <= 1.0


@pytest.mark.asyncio
async def test_options_chain_calculates_pcr_max_pain_greeks_and_publishes_topics(client: AsyncClient):
    _, headers = await register_and_login(client, username="option_user")
    await client.post(
        "/api/v1/data-topics/register",
        headers=headers,
        json={"topic": "market:quote:RB2510", "policy": {"ttl_ms": 1000}},
    )
    await client.post(
        "/api/v1/data-topics/register",
        headers=headers,
        json={"topic": "option:atm_iv:data_governance:RB2510", "policy": {"ttl_ms": 1000}},
    )
    await client.post(
        "/api/v1/data-topics/register",
        headers=headers,
        json={"topic": "fno:pcr:data_governance:RB2510", "policy": {"ttl_ms": 1000}},
    )
    await client.post(
        "/api/v1/data-topics/register",
        headers=headers,
        json={"topic": "fno:max_pain:data_governance:RB2510", "policy": {"ttl_ms": 1000}},
    )
    await client.post(
        "/api/v1/data-topics/register",
        headers=headers,
        json={"topic": "option:chain:data_governance:RB2510:2026-12-31", "policy": {"ttl_ms": 1000}},
    )
    await client.post(
        "/api/v1/data-topics/market:quote:RB2510/push",
        headers=headers,
        json={"value": {"price": 3524.0}},
    )

    response = await client.get(
        "/api/v1/options-chain/RB2510",
        headers=headers,
        params={"expiry": "2026-12-31", "provider": "auto"},
    )
    topic = await client.get(
        "/api/v1/data-topics/option:atm_iv:data_governance:RB2510/peek",
        headers=headers,
    )
    pcr_topic = await client.get(
        "/api/v1/data-topics/fno:pcr:data_governance:RB2510/peek",
        headers=headers,
    )
    max_pain_topic = await client.get(
        "/api/v1/data-topics/fno:max_pain:data_governance:RB2510/peek",
        headers=headers,
    )
    chain_topic = await client.get(
        "/api/v1/data-topics/option:chain:data_governance:RB2510:2026-12-31/peek",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["underlying"] == "RB2510"
    assert data["source"] == "data_governance"
    assert data["pcr"] > 0
    assert data["max_pain"] in [row["strike"] for row in data["rows"]]
    assert data["atm_strike"] == data["max_pain"]
    assert data["strike_count"] == 9
    assert data["timestamp"]
    assert data["rows"][0]["call"]["volume"] > 0
    assert data["rows"][0]["call"]["iv"] > 0
    assert data["rows"][0]["put"]["volume"] > 0
    assert data["rows"][0]["put"]["iv"] > 0
    assert data["rows"][0]["call"]["greeks"]["delta"] is not None
    assert topic.status_code == 200
    assert topic.json()["value"] == data["atm_iv"]
    assert pcr_topic.status_code == 200
    assert pcr_topic.json()["value"] == data["pcr"]
    assert max_pain_topic.status_code == 200
    assert max_pain_topic.json()["value"] == data["max_pain"]
    assert chain_topic.status_code == 200
    assert chain_topic.json()["value"]["underlying"] == "RB2510"


@pytest.mark.asyncio
async def test_options_chain_returns_degraded_for_insufficient_data(client: AsyncClient):
    _, headers = await register_and_login(client, username="option_degraded")

    response = await client.get(
        "/api/v1/options-chain/UNKNOWN",
        headers=headers,
        params={"expiry": "2026-12-31", "provider": "empty"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["reason"] == "insufficient_data"
