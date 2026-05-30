from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.risk_analytics import get_backtest_service, get_benchmark_service
from app.schemas.backtest import BacktestResult, TaskStatus
from app.schemas.risk_analytics import BenchmarkReturnsResult
from tests.conftest import app, register_and_login


def _backtest_result() -> BacktestResult:
    return BacktestResult(
        task_id="task123",
        strategy_id="strategy1",
        symbol="000001.SZ",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 6, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        equity_curve=[100.0, 102.0, 101.0, 104.0, 103.0, 106.0],
        equity_dates=[
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-06",
        ],
        created_at=datetime(2024, 1, 6, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_benchmark_metrics_service_calculates_alpha_beta_ir_and_tracking_error():
    from app.services.risk_analytics.benchmark_metrics import BenchmarkMetricsService

    result = BenchmarkMetricsService().calculate(
        strategy_returns=[0.02, -0.009804, 0.029703, -0.009615, 0.029126],
        benchmark_returns=[0.01, -0.00495, 0.014925, -0.004902, 0.014778],
        benchmark_id="hs300",
        risk_free_rate=0.0,
    )

    assert result.status == "ok"
    assert result.benchmark_id == "hs300"
    assert result.observation_count == 5
    assert result.beta > 1.0
    assert result.alpha is not None
    assert result.tracking_error > 0
    assert result.information_ratio > 0


@pytest.mark.asyncio
async def test_benchmark_metrics_service_returns_degraded_for_insufficient_overlap():
    from app.services.risk_analytics.benchmark_metrics import BenchmarkMetricsService

    result = BenchmarkMetricsService().calculate(
        strategy_returns=[0.01],
        benchmark_returns=[0.01],
        benchmark_id="hs300",
    )

    assert result.status == "degraded"
    assert result.reason == "insufficient_overlap"
    assert result.observation_count == 1


@pytest.mark.asyncio
async def test_benchmark_metrics_api_requires_auth(client: AsyncClient):
    response = await client.get(
        "/api/v1/risk-analytics/benchmark-metrics/task123?benchmark_id=hs300"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_benchmark_metrics_api_returns_metrics_for_backtest(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_benchmark_metrics_user")
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=_backtest_result()))

    class FakeBenchmarkService:
        async def get_benchmark_returns(self, benchmark_id: str, start_date: str, end_date: str):
            return BenchmarkReturnsResult(
                status="ok",
                benchmark_id=benchmark_id,
                symbol="000300.SH",
                start_date=start_date,
                end_date=end_date,
                observation_count=6,
                dates=[
                    "2024-01-01",
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                ],
                returns=[0.01, -0.00495, 0.014925, -0.004902, 0.014778],
            )

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    app.dependency_overrides[get_benchmark_service] = lambda: FakeBenchmarkService()
    try:
        response = await client.get(
            "/api/v1/risk-analytics/benchmark-metrics/task123?benchmark_id=hs300",
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)
        app.dependency_overrides.pop(get_benchmark_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backtest_id"] == "task123"
    assert payload["benchmark_id"] == "hs300"
    assert payload["status"] == "ok"
    assert payload["observation_count"] == 5
    assert payload["beta"] > 1.0
    assert payload["information_ratio"] > 0
