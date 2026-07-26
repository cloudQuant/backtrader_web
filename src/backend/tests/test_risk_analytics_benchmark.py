from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.risk_analytics import get_benchmark_service
from tests.conftest import app, register_and_login


@pytest.mark.asyncio
async def test_benchmark_service_fetches_prices_and_calculates_returns():
    from app.services.risk_analytics.benchmark import BenchmarkService

    fetcher = AsyncMock(
        return_value=[
            {"date": "2024-01-01", "close": 100.0},
            {"date": "2024-01-02", "close": 102.0},
            {"date": "2024-01-03", "close": 101.0},
        ]
    )
    service = BenchmarkService(data_fetcher=fetcher)

    result = await service.get_benchmark_returns("hs300", "2024-01-01", "2024-01-03")

    assert result.status == "ok"
    assert result.benchmark_id == "hs300"
    assert result.symbol == "000300.SH"
    assert result.observation_count == 3
    assert result.dates == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert result.returns == [pytest.approx(0.02), pytest.approx(-0.009804)]
    fetcher.assert_awaited_once_with("000300.SH", "2024-01-01", "2024-01-03")


@pytest.mark.asyncio
async def test_benchmark_service_returns_degraded_for_unknown_benchmark():
    from app.services.risk_analytics.benchmark import BenchmarkService

    result = await BenchmarkService(data_fetcher=AsyncMock()).get_benchmark_returns(
        "unknown", "2024-01-01", "2024-01-03"
    )

    assert result.status == "degraded"
    assert result.reason == "unknown_benchmark"
    assert result.returns == []


@pytest.mark.asyncio
async def test_benchmark_api_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/risk-analytics/benchmark/hs300?start_date=2024-01-01&end_date=2024-01-03"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_benchmark_api_returns_benchmark_returns(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_benchmark_user")

    class FakeBenchmarkService:
        async def get_benchmark_returns(self, benchmark_id: str, start_date: str, end_date: str):
            from app.schemas.risk_analytics import BenchmarkReturnsResult

            return BenchmarkReturnsResult(
                status="ok",
                benchmark_id=benchmark_id,
                symbol="000300.SH",
                start_date=start_date,
                end_date=end_date,
                observation_count=3,
                dates=["2024-01-01", "2024-01-02", "2024-01-03"],
                returns=[0.02, -0.009804],
            )

    app.dependency_overrides[get_benchmark_service] = lambda: FakeBenchmarkService()
    try:
        response = await client.get(
            "/api/v1/risk-analytics/benchmark/hs300?start_date=2024-01-01&end_date=2024-01-03",
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(get_benchmark_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["benchmark_id"] == "hs300"
    assert payload["symbol"] == "000300.SH"
    assert payload["returns"] == [0.02, -0.009804]
