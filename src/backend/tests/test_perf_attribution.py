import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_brinson_service_calculates_effects():
    from app.services.perf_attribution.brinson import BrinsonAttributionService

    result = BrinsonAttributionService().calculate(
        portfolio_weights={"tech": 0.6, "finance": 0.4},
        benchmark_weights={"tech": 0.5, "finance": 0.5},
        portfolio_returns={"tech": 0.10, "finance": 0.02},
        benchmark_returns={"tech": 0.08, "finance": 0.03},
    )

    assert result.status == "ok"
    assert result.allocation_effect == pytest.approx(0.005)
    assert result.selection_effect == pytest.approx(0.005)
    assert result.interaction_effect == pytest.approx(0.003)
    assert result.total_excess_return == pytest.approx(0.013)
    assert result.asset_count == 2


@pytest.mark.asyncio
async def test_brinson_service_returns_degraded_for_missing_assets():
    from app.services.perf_attribution.brinson import BrinsonAttributionService

    result = BrinsonAttributionService().calculate(
        portfolio_weights={"tech": 1.0},
        benchmark_weights={},
        portfolio_returns={"tech": 0.1},
        benchmark_returns={},
    )

    assert result.status == "degraded"
    assert result.reason == "insufficient_assets"


@pytest.mark.asyncio
async def test_brinson_api_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/perf-attribution/brinson",
        json={
            "portfolio_weights": {"tech": 0.6},
            "benchmark_weights": {"tech": 0.5},
            "portfolio_returns": {"tech": 0.1},
            "benchmark_returns": {"tech": 0.08},
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_brinson_api_returns_result(client: AsyncClient):
    _, headers = await register_and_login(client, username="perf_attr_user")

    response = await client.post(
        "/api/v1/perf-attribution/brinson",
        headers=headers,
        json={
            "portfolio_weights": {"tech": 0.6, "finance": 0.4},
            "benchmark_weights": {"tech": 0.5, "finance": 0.5},
            "portfolio_returns": {"tech": 0.10, "finance": 0.02},
            "benchmark_returns": {"tech": 0.08, "finance": 0.03},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["allocation_effect"] == pytest.approx(0.005)
    assert payload["selection_effect"] == pytest.approx(0.005)
    assert payload["interaction_effect"] == pytest.approx(0.003)
