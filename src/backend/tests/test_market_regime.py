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
async def test_market_regime_detector_identifies_bull_low_vol_regime():
    from app.services.market_regime.detector import MarketRegimeDetector

    prices = [100 + index for index in range(40)]
    result = MarketRegimeDetector().detect(prices, min_observations=20)

    assert result.status == "ok"
    assert result.trend_regime == "bull"
    assert result.volatility_regime in {"low", "medium"}
    assert result.overall_regime in {"bull_low_vol", "bull_medium_vol"}


@pytest.mark.asyncio
async def test_market_regime_detector_identifies_high_volatility():
    from app.services.market_regime.detector import MarketRegimeDetector

    prices = [100, 110, 95, 120, 90, 125, 85, 130, 80, 135, 75, 140, 70, 145, 65, 150, 60, 155, 55, 160]
    result = MarketRegimeDetector().detect(prices, min_observations=10)

    assert result.status == "ok"
    assert result.volatility_regime == "high"


@pytest.mark.asyncio
async def test_market_regime_detector_returns_degraded_for_short_history():
    from app.services.market_regime.detector import MarketRegimeDetector

    result = MarketRegimeDetector().detect([100, 101], min_observations=5)

    assert result.status == "degraded"
    assert result.reason == "insufficient_history"


@pytest.mark.asyncio
async def test_market_regime_api_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/risk-analytics/market-regime/task123")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_market_regime_api_returns_regime_for_backtest(client: AsyncClient):
    _, headers = await register_and_login(client, username="market_regime_user")
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=_backtest_result([100 + index for index in range(40)])))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get("/api/v1/risk-analytics/market-regime/task123", headers=headers)
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backtest_id"] == "task123"
    assert payload["status"] == "ok"
    assert payload["trend_regime"] == "bull"
