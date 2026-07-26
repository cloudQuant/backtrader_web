import pytest
from httpx import AsyncClient

from app.services.data_topic_hub import TopicPolicy, get_shared_data_topic_hub
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
async def test_options_chain_calculates_pcr_max_pain_greeks_and_publishes_topics(
    client: AsyncClient,
):
    _, headers = await register_and_login(client, username="option_user")
    hub = get_shared_data_topic_hub()
    topic_policies = {
        "option:atm_iv:data_governance:RB2510": TopicPolicy(ttl_ms=1000),
        "fno:pcr:data_governance:RB2510": TopicPolicy(ttl_ms=1000),
        "fno:max_pain:data_governance:RB2510": TopicPolicy(ttl_ms=1000),
        "option:chain:data_governance:RB2510:2026-12-31": TopicPolicy(ttl_ms=1000),
    }
    for topic_name, policy in topic_policies.items():
        hub.register_topic(topic_name, policy)
    real_chain = {
        "underlying": "RB2510",
        "symbol": "RB2510",
        "expiry": "2026-12-31",
        "spot": 3524.0,
        "rows": [
            {
                "strike": 3450.0,
                "call": {"oi": 120, "volume": 18, "iv": 0.21},
                "put": {"oi": 260, "volume": 32, "iv": 0.24},
            },
            {
                "strike": 3500.0,
                "call": {"oi": 220, "volume": 26, "iv": 0.22},
                "put": {"oi": 210, "volume": 25, "iv": 0.23},
            },
            {
                "strike": 3550.0,
                "call": {"oi": 300, "volume": 34, "iv": 0.225},
                "put": {"oi": 180, "volume": 21, "iv": 0.235},
            },
            {
                "strike": 3600.0,
                "call": {"oi": 340, "volume": 38, "iv": 0.23},
                "put": {"oi": 120, "volume": 15, "iv": 0.245},
            },
        ],
        "timestamp": "2026-05-26T00:00:00+00:00",
    }
    await hub.push("option:chain:data_governance:RB2510:2026-12-31", real_chain)

    response = await client.get(
        "/api/v1/options-chain/RB2510",
        headers=headers,
        params={"expiry": "2026-12-31", "provider": "data_governance"},
    )
    topic = hub.peek_raw("option:atm_iv:data_governance:RB2510")
    pcr_topic = hub.peek_raw("fno:pcr:data_governance:RB2510")
    max_pain_topic = hub.peek_raw("fno:max_pain:data_governance:RB2510")
    chain_topic = hub.peek_raw("option:chain:data_governance:RB2510:2026-12-31")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["underlying"] == "RB2510"
    assert data["source"] == "data_governance"
    assert data["pcr"] > 0
    assert data["max_pain"] in [row["strike"] for row in data["rows"]]
    assert data["atm_strike"] == 3500.0
    assert data["atm_iv"] == 0.22
    assert data["strike_count"] == 4
    assert data["timestamp"] == "2026-05-26T00:00:00+00:00"
    assert data["rows"][0]["call"]["oi"] == 120
    assert data["rows"][0]["call"]["volume"] == 18
    assert data["rows"][0]["call"]["iv"] == 0.21
    assert data["rows"][0]["put"]["oi"] == 260
    assert data["rows"][0]["put"]["volume"] == 32
    assert data["rows"][0]["put"]["iv"] == 0.24
    assert data["rows"][0]["call"]["greeks"]["delta"] is not None
    assert topic == data["atm_iv"]
    assert pcr_topic == data["pcr"]
    assert max_pain_topic == data["max_pain"]
    assert chain_topic["underlying"] == "RB2510"


@pytest.mark.asyncio
async def test_options_chain_data_governance_without_real_rows_degrades(client: AsyncClient):
    _, headers = await register_and_login(client, username="option_no_real_chain")

    response = await client.get(
        "/api/v1/options-chain/NOCHAIN2510",
        headers=headers,
        params={"expiry": "2026-12-31", "provider": "data_governance"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["reason"] == "insufficient_real_chain_data"
    assert data["source"] == "data_governance"
    assert data["rows"] == []


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
