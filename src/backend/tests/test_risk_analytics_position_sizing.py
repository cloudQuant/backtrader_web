from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.risk_analytics import get_backtest_service
from app.schemas.backtest import BacktestResult, TaskStatus
from tests.conftest import app, register_and_login


def _backtest_result(equity_curve: list[float]) -> BacktestResult:
    return BacktestResult(
        task_id="task123",
        strategy_id="strategy1",
        symbol="000001.SZ",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        equity_curve=equity_curve,
        equity_dates=[f"2024-01-{day:02d}" for day in range(1, len(equity_curve) + 1)],
        created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_position_sizing_service_calculates_volatility_target_fraction():
    from app.services.risk_analytics.position_sizing import PositionSizingService

    equity_curve = [100000, 101000, 100000, 101000, 100000, 101000, 100000, 101000, 100000, 101000, 100000]
    result = PositionSizingService().calculate_for_equity_curve(
        equity_curve,
        target_volatility=0.10,
        max_position=1.0,
        min_observations=5,
    )

    assert result.status == "ok"
    assert result.method == "volatility_target"
    assert result.observation_count == 10
    assert result.annualized_volatility > 0
    assert 0 < result.recommended_position <= 1.0
    assert result.recommended_position < 1.0


@pytest.mark.asyncio
async def test_position_sizing_service_calculates_risk_parity_weights():
    from app.services.risk_analytics.position_sizing import PositionSizingService

    result = PositionSizingService().calculate_risk_parity_weights({"low_vol": 0.10, "high_vol": 0.20})

    assert result == {"low_vol": pytest.approx(2 / 3), "high_vol": pytest.approx(1 / 3)}


@pytest.mark.asyncio
async def test_position_sizing_service_returns_degraded_when_history_is_short():
    from app.services.risk_analytics.position_sizing import PositionSizingService

    result = PositionSizingService().calculate_for_equity_curve([100000, 100100], min_observations=5)

    assert result.status == "degraded"
    assert result.reason == "insufficient_history"
    assert result.recommended_position is None


@pytest.mark.asyncio
async def test_position_sizing_api_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/risk-analytics/position-sizing/task123")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_position_sizing_api_returns_recommendation_for_backtest(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_position_user")
    equity_curve = [100000, 101000, 100000, 101000, 100000, 101000, 100000, 101000, 100000, 101000, 100000]
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=_backtest_result(equity_curve)))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get(
            "/api/v1/risk-analytics/position-sizing/task123?target_volatility=0.1",
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backtest_id"] == "task123"
    assert payload["status"] == "ok"
    assert payload["method"] == "volatility_target"
    assert 0 < payload["recommended_position"] <= 1.0


@pytest.mark.asyncio
async def test_position_sizing_api_returns_404_when_backtest_missing(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_position_missing_user")
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=None))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get("/api/v1/risk-analytics/position-sizing/missing", headers=headers)
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 404
