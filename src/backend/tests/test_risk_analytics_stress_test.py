from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.risk_analytics import get_backtest_service
from app.schemas.backtest import BacktestResult, TaskStatus
from tests.conftest import app, register_and_login


@pytest.mark.asyncio
async def test_stress_test_service_calculates_loss_drawdown_and_recovery_days():
    from app.services.risk_analytics.stress_test import StressTestService

    service = StressTestService()
    result = service.run_scenarios(
        equity_curve=[100.0, 98.0, 94.0, 90.0, 92.0, 96.0, 101.0],
        equity_dates=[
            "2020-03-01",
            "2020-03-02",
            "2020-03-03",
            "2020-03-04",
            "2020-03-05",
            "2020-03-06",
            "2020-03-07",
        ],
        scenarios=[
            {
                "id": "custom_drop",
                "name": "Custom Drop",
                "start_date": "2020-03-02",
                "end_date": "2020-03-07",
            }
        ],
    )

    assert result.status == "ok"
    assert result.scenario_count == 1
    scenario = result.results[0]
    assert scenario.scenario_id == "custom_drop"
    assert scenario.status == "ok"
    assert scenario.observation_count == 6
    assert scenario.max_loss == pytest.approx(-0.081633, abs=1e-6)
    assert scenario.max_drawdown == pytest.approx(-0.081633, abs=1e-6)
    assert scenario.recovery_days == 5


@pytest.mark.asyncio
async def test_stress_test_service_marks_uncovered_scenario_as_degraded():
    from app.services.risk_analytics.stress_test import StressTestService

    service = StressTestService()
    result = service.run_scenarios(
        equity_curve=[100.0, 101.0, 102.0],
        equity_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        scenarios=[
            {
                "id": "old",
                "name": "Old Crisis",
                "start_date": "2020-03-01",
                "end_date": "2020-03-31",
            }
        ],
    )

    assert result.status == "degraded"
    assert result.results[0].status == "degraded"
    assert result.results[0].reason == "scenario_not_covered"
    assert result.results[0].observation_count == 0


@pytest.mark.asyncio
async def test_stress_test_api_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/risk-analytics/stress-test/task123", json={})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_stress_test_api_returns_selected_scenario_results(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_stress_user")
    backtest_result = BacktestResult(
        task_id="task123",
        strategy_id="strategy1",
        symbol="000001.SZ",
        start_date=datetime(2020, 3, 1, tzinfo=timezone.utc),
        end_date=datetime(2020, 3, 7, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        equity_curve=[100.0, 98.0, 94.0, 90.0, 92.0, 96.0, 101.0],
        equity_dates=[
            "2020-03-01",
            "2020-03-02",
            "2020-03-03",
            "2020-03-04",
            "2020-03-05",
            "2020-03-06",
            "2020-03-07",
        ],
        created_at=datetime(2020, 3, 7, tzinfo=timezone.utc),
    )
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=backtest_result))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.post(
            "/api/v1/risk-analytics/stress-test/task123",
            headers=headers,
            json={
                "scenarios": [
                    {
                        "id": "covid_window",
                        "name": "COVID window",
                        "start_date": "2020-03-02",
                        "end_date": "2020-03-07",
                    }
                ]
            },
        )
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backtest_id"] == "task123"
    assert payload["status"] == "ok"
    assert payload["scenario_count"] == 1
    assert payload["results"][0]["scenario_id"] == "covid_window"
    assert payload["results"][0]["max_drawdown"] == pytest.approx(-0.081633, abs=1e-6)


@pytest.mark.asyncio
async def test_stress_test_api_returns_404_when_backtest_missing(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_stress_missing_user")
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=None))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.post(
            "/api/v1/risk-analytics/stress-test/missing", headers=headers, json={}
        )
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 404
