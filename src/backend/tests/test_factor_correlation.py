import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_factor_correlation_service_calculates_matrix_and_high_pairs():
    from app.services.factor_lib.correlation import FactorCorrelationService

    result = FactorCorrelationService().analyze(
        {
            "momentum": [1.0, 2.0, 3.0, 4.0],
            "trend": [2.0, 4.0, 6.0, 8.0],
            "reversal": [4.0, 3.0, 2.0, 1.0],
        },
        threshold=0.9,
    )

    assert result.status == "ok"
    assert result.factor_count == 3
    assert result.observation_count == 4
    assert result.matrix["momentum"]["trend"] == pytest.approx(1.0)
    assert result.matrix["momentum"]["reversal"] == pytest.approx(-1.0)
    pairs = {(pair.factor_a, pair.factor_b) for pair in result.high_correlation_pairs}
    assert ("momentum", "trend") in pairs
    assert ("momentum", "reversal") in pairs


@pytest.mark.asyncio
async def test_factor_correlation_service_returns_degraded_for_insufficient_factors():
    from app.services.factor_lib.correlation import FactorCorrelationService

    result = FactorCorrelationService().analyze({"only": [1.0, 2.0, 3.0]})

    assert result.status == "degraded"
    assert result.reason == "insufficient_factors"


@pytest.mark.asyncio
async def test_custom_factor_service_evaluates_safe_expression():
    from app.services.factor_lib.custom import CustomFactorService

    result = CustomFactorService().calculate(
        expression="(close - open) / open",
        records=[
            {"open": 100.0, "close": 110.0},
            {"open": 100.0, "close": 95.0},
        ],
    )

    assert result.status == "ok"
    assert result.values == [pytest.approx(0.1), pytest.approx(-0.05)]


@pytest.mark.asyncio
async def test_custom_factor_service_rejects_unsafe_expression():
    from app.services.factor_lib.custom import CustomFactorService

    result = CustomFactorService().calculate(
        expression="__import__('os').system('echo unsafe')",
        records=[{"open": 100.0, "close": 110.0}],
    )

    assert result.status == "degraded"
    assert result.reason == "unsafe_expression"
    assert result.values == []


@pytest.mark.asyncio
async def test_factor_correlation_api_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/factor-lib/correlation",
        json={"factor_values": {"a": [1, 2], "b": [2, 4]}},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_factor_correlation_api_returns_result(client: AsyncClient):
    _, headers = await register_and_login(client, username="factor_corr_user")

    response = await client.post(
        "/api/v1/factor-lib/correlation",
        headers=headers,
        json={"factor_values": {"a": [1, 2, 3], "b": [2, 4, 6]}, "threshold": 0.9},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["matrix"]["a"]["b"] == pytest.approx(1.0)
    assert payload["high_correlation_pairs"][0]["factor_a"] == "a"


@pytest.mark.asyncio
async def test_custom_factor_api_returns_values(client: AsyncClient):
    _, headers = await register_and_login(client, username="custom_factor_user")

    response = await client.post(
        "/api/v1/factor-lib/custom/calculate",
        headers=headers,
        json={
            "expression": "(close - open) / open",
            "records": [{"open": 100, "close": 110}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["values"] == [pytest.approx(0.1)]
