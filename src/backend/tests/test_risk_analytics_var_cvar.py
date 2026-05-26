from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.risk_analytics import get_backtest_service
from app.schemas.backtest import BacktestResult, TaskStatus
from tests.conftest import app, register_and_login


@pytest.mark.asyncio
async def test_var_cvar_historical_calculates_tail_losses_from_equity_curve():
    from app.services.risk_analytics.var_cvar import VarCvarService

    service = VarCvarService()
    result = service.calculate_from_equity_curve(
        [100.0, 99.0, 101.0, 98.0, 97.0, 103.0, 100.0, 102.0, 99.0, 101.0],
        method="historical",
        min_observations=5,
    )

    assert result.status == "ok"
    assert result.method == "historical"
    assert result.observation_count == 9
    assert result.var_95 < 0
    assert result.var_99 < 0
    assert result.cvar_95 <= result.var_95
    assert result.cvar_99 <= result.var_99


@pytest.mark.asyncio
async def test_var_cvar_parametric_uses_return_mean_and_volatility():
    from app.services.risk_analytics.var_cvar import VarCvarService

    service = VarCvarService()
    result = service.calculate_from_returns(
        [0.01, -0.02, 0.015, -0.01, 0.005, -0.03, 0.02, -0.005, 0.012, -0.018],
        method="parametric",
        min_observations=5,
    )

    assert result.status == "ok"
    assert result.method == "parametric"
    assert result.var_95 < 0
    assert result.var_99 < result.var_95
    assert result.cvar_95 <= result.var_95
    assert result.cvar_99 <= result.var_99


@pytest.mark.asyncio
async def test_var_cvar_returns_degraded_when_history_is_too_short():
    from app.services.risk_analytics.var_cvar import VarCvarService

    service = VarCvarService()
    result = service.calculate_from_equity_curve([100.0, 101.0, 100.0], min_observations=30)

    assert result.status == "degraded"
    assert result.reason == "insufficient_history"
    assert result.observation_count == 2
    assert result.var_95 is None
    assert result.cvar_95 is None


@pytest.mark.asyncio
async def test_var_cvar_api_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/risk-analytics/var-cvar/task123")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_var_cvar_api_returns_result_for_backtest(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_var_user")

    equity_curve = [
        100.0,
        99.0,
        101.0,
        98.0,
        97.0,
        103.0,
        100.0,
        102.0,
        99.0,
        101.0,
        100.0,
        104.0,
        102.0,
        105.0,
        103.0,
        106.0,
        101.0,
        107.0,
        104.0,
        108.0,
        106.0,
        109.0,
        105.0,
        110.0,
        108.0,
        111.0,
        109.0,
        112.0,
        110.0,
        113.0,
        111.0,
    ]
    backtest_result = BacktestResult(
        task_id="task123",
        strategy_id="strategy1",
        symbol="000001.SZ",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        equity_curve=equity_curve,
        equity_dates=[f"2024-01-{day:02d}" for day in range(1, 32)],
        created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
    )
    mock_backtest_service = SimpleNamespace(
        get_result=AsyncMock(return_value=backtest_result),
    )

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get(
            "/api/v1/risk-analytics/var-cvar/task123?method=historical",
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backtest_id"] == "task123"
    assert payload["status"] == "ok"
    assert payload["method"] == "historical"
    assert payload["observation_count"] == 30
    assert payload["var_95"] < 0
    mock_backtest_service.get_result.assert_awaited_once()


@pytest.mark.asyncio
async def test_var_cvar_api_returns_404_when_backtest_missing(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_var_missing_user")
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=None))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get("/api/v1/risk-analytics/var-cvar/missing", headers=headers)
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 404
