from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.risk_analytics import get_backtest_service
from app.schemas.backtest import BacktestResult, TaskStatus, TradeRecord
from tests.conftest import app, register_and_login


def _trade(pnl: float) -> TradeRecord:
    return TradeRecord(
        datetime="2024-01-01T00:00:00+00:00",
        direction="long",
        price=10.0,
        size=100,
        value=1000.0,
        commission=1.0,
        pnl=pnl,
        pnlcomm=pnl,
        barlen=5,
    )


def _backtest_result(trades: list[TradeRecord]) -> BacktestResult:
    return BacktestResult(
        task_id="task123",
        strategy_id="strategy1",
        symbol="000001.SZ",
        start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        status=TaskStatus.COMPLETED,
        total_trades=len(trades),
        profitable_trades=sum(1 for trade in trades if (trade.pnlcomm or 0) > 0),
        losing_trades=sum(1 for trade in trades if (trade.pnlcomm or 0) < 0),
        trades=trades,
        created_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_kelly_service_calculates_fractional_recommendations():
    from app.services.risk_analytics.kelly import KellyService

    trades = [_trade(120.0), _trade(80.0), _trade(100.0), _trade(-50.0), _trade(-50.0)]
    result = KellyService().calculate(trades)

    assert result.status == "ok"
    assert result.trade_count == 5
    assert result.win_rate == pytest.approx(0.6)
    assert result.avg_win == pytest.approx(100.0)
    assert result.avg_loss == pytest.approx(50.0)
    assert result.payoff_ratio == pytest.approx(2.0)
    assert result.full_kelly == pytest.approx(0.4)
    assert result.half_kelly == pytest.approx(0.2)
    assert result.quarter_kelly == pytest.approx(0.1)
    assert result.recommendation == "fractional_kelly"


@pytest.mark.asyncio
async def test_kelly_service_returns_degraded_for_insufficient_closed_trades():
    from app.services.risk_analytics.kelly import KellyService

    result = KellyService().calculate([_trade(100.0)], min_trades=3)

    assert result.status == "degraded"
    assert result.reason == "insufficient_trades"
    assert result.full_kelly is None


@pytest.mark.asyncio
async def test_kelly_api_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/risk-analytics/kelly/task123")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_kelly_api_returns_recommendation_for_backtest(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_kelly_user")
    trades = [_trade(120.0), _trade(80.0), _trade(100.0), _trade(-50.0), _trade(-50.0)]
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=_backtest_result(trades)))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get("/api/v1/risk-analytics/kelly/task123", headers=headers)
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["backtest_id"] == "task123"
    assert payload["status"] == "ok"
    assert payload["full_kelly"] == pytest.approx(0.4)
    assert payload["half_kelly"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_kelly_api_returns_404_when_backtest_missing(client: AsyncClient):
    _, headers = await register_and_login(client, username="risk_kelly_missing_user")
    mock_backtest_service = SimpleNamespace(get_result=AsyncMock(return_value=None))

    app.dependency_overrides[get_backtest_service] = lambda: mock_backtest_service
    try:
        response = await client.get("/api/v1/risk-analytics/kelly/missing", headers=headers)
    finally:
        app.dependency_overrides.pop(get_backtest_service, None)

    assert response.status_code == 404
