"""Unit tests for app/api/portfolio_api.py.

Tests cover all portfolio endpoints with mocked dependencies:
- Portfolio overview (empty, single strategy, multiple strategies)
- Positions aggregation
- Trades aggregation
- Equity curve generation
- Asset allocation
- Simulation variants (delegate to live endpoints)
- Edge cases (ValueError, missing log dirs, NaN values)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

_USER = SimpleNamespace(sub="u1")

_INSTANCE_A = {
    "id": "inst-a",
    "strategy_id": "strat_001",
    "strategy_name": "MA Cross",
    "status": "running",
}

_INSTANCE_B = {
    "id": "inst-b",
    "strategy_id": "strat_002",
    "strategy_name": "RSI Mean Reversion",
    "status": "stopped",
}


class _MockManager:
    """Mock LiveTradingManager that returns configurable instances."""

    def __init__(self, instances=None):
        self._instances = instances or []

    def list_instances(self, **kwargs):
        return self._instances


# ── Helper patches ────────────────────────────────────────────────────────────


def _patch_deps(manager):
    """Return a context manager that patches get_current_user and _get_manager."""
    from unittest.mock import AsyncMock

    return (
        patch("app.api.portfolio_api.get_current_user", return_value=_USER),
        patch("app.api.portfolio_api._get_manager", return_value=manager),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio Overview
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_portfolio_overview_empty():
    """Empty portfolio returns zero totals."""
    from app.api.portfolio_api import get_portfolio_overview

    mgr = _MockManager([])
    result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 0
    assert result["strategy_count"] == 0
    assert result["running_count"] == 0
    assert result["strategies"] == []


@pytest.mark.asyncio
async def test_portfolio_overview_no_log_dir():
    """Instance with no log directory returns zero metrics."""
    from app.api.portfolio_api import get_portfolio_overview

    mgr = _MockManager([_INSTANCE_A])

    with (
        patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")),
    ):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["strategy_count"] == 1
    assert result["strategies"][0]["total_assets"] == 0
    assert result["strategies"][0]["pnl"] == 0


@pytest.mark.asyncio
async def test_portfolio_overview_with_data():
    """Instance with log data returns computed metrics."""
    from app.api.portfolio_api import get_portfolio_overview

    mgr = _MockManager([_INSTANCE_A])

    mock_value_data = {
        "equity_curve": [100000.0, 105000.0, 110000.0],
        "cash_curve": [50000.0, 45000.0, 40000.0],
    }
    mock_trades = [
        {"pnlcomm": 500.0},
        {"pnlcomm": -200.0},
        {"pnlcomm": 300.0},
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/dir/logs"),
        patch("app.api.portfolio_api.parse_value_log", return_value=mock_value_data),
        patch("app.api.portfolio_api.parse_trade_log", return_value=mock_trades),
    ):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 110000.0
    assert result["total_cash"] == 40000.0
    assert result["total_initial_capital"] == 100000.0
    assert result["total_pnl"] == 10000.0
    assert result["total_pnl_pct"] == 10.0
    assert result["strategy_count"] == 1
    assert result["running_count"] == 1

    strat = result["strategies"][0]
    assert strat["strategy_id"] == "strat_001"
    assert strat["total_assets"] == 110000.0
    assert strat["pnl"] == 10000.0
    assert strat["total_trades"] == 3
    # 2 winning trades out of 3
    assert strat["win_rate"] == 66.7


@pytest.mark.asyncio
async def test_portfolio_overview_multiple_strategies():
    """Multiple strategies are aggregated correctly."""
    from app.api.portfolio_api import get_portfolio_overview

    mgr = _MockManager([_INSTANCE_A, _INSTANCE_B])

    value_data_a = {"equity_curve": [100000.0, 110000.0], "cash_curve": [50000.0, 55000.0]}
    value_data_b = {"equity_curve": [200000.0, 190000.0], "cash_curve": [100000.0, 95000.0]}

    def mock_parse_value(log_dir):
        if "strat_001" in str(log_dir):
            return value_data_a
        return value_data_b

    def mock_get_strategy_dir(sid):
        return f"/fake/{sid}"

    def mock_find_log(d):
        return f"{d}/logs"

    with (
        patch("app.api.portfolio_api.get_strategy_dir", side_effect=mock_get_strategy_dir),
        patch("app.api.portfolio_api.find_latest_log_dir", side_effect=mock_find_log),
        patch("app.api.portfolio_api.parse_value_log", side_effect=mock_parse_value),
        patch("app.api.portfolio_api.parse_trade_log", return_value=[]),
    ):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    # 110000 + 190000 = 300000
    assert result["total_assets"] == 300000.0
    # 100000 + 200000 = 300000 initial
    assert result["total_initial_capital"] == 300000.0
    assert result["strategy_count"] == 2
    assert result["running_count"] == 1  # only inst-a is running


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio Positions
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_portfolio_positions_empty():
    """No instances returns empty positions."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([])
    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)
    assert result == {"total": 0, "positions": []}


@pytest.mark.asyncio
async def test_portfolio_positions_with_data():
    """Positions are aggregated across strategies."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([_INSTANCE_A])
    mock_positions = [
        {"data_name": "BTC/USDT", "size": 0.5, "price": 60000.0, "market_value": 30000.0},
        {"data_name": "ETH/USDT", "size": -2.0, "price": 3000.0, "market_value": 6000.0},
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["total"] == 2
    assert result["positions"][0]["direction"] == "long"
    assert result["positions"][1]["direction"] == "short"
    assert result["positions"][0]["strategy_name"] == "MA Cross"


@pytest.mark.asyncio
async def test_portfolio_positions_strategy_dir_error():
    """ValueError from get_strategy_dir is handled gracefully."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([_INSTANCE_A])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("bad")):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result == {"total": 0, "positions": []}


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio Trades
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_portfolio_trades_empty():
    """No instances returns empty trades."""
    from app.api.portfolio_api import get_portfolio_trades

    mgr = _MockManager([])
    result = await get_portfolio_trades(limit=200, current_user=_USER, mgr=mgr)
    assert result == {"total": 0, "trades": []}


@pytest.mark.asyncio
async def test_portfolio_trades_sorted_and_limited():
    """Trades are sorted by dtclose descending and limited."""
    from app.api.portfolio_api import get_portfolio_trades

    mgr = _MockManager([_INSTANCE_A])
    mock_trades = [
        {"dtclose": "2024-01-01", "pnlcomm": 100},
        {"dtclose": "2024-01-03", "pnlcomm": -50},
        {"dtclose": "2024-01-02", "pnlcomm": 200},
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_trade_log", return_value=mock_trades),
    ):
        result = await get_portfolio_trades(limit=2, current_user=_USER, mgr=mgr)

    assert result["total"] == 3
    assert len(result["trades"]) == 2
    # Most recent first
    assert result["trades"][0]["dtclose"] == "2024-01-03"
    assert result["trades"][1]["dtclose"] == "2024-01-02"


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio Equity
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_portfolio_equity_empty():
    """No instances returns empty equity."""
    from app.api.portfolio_api import get_portfolio_equity

    mgr = _MockManager([])
    result = await get_portfolio_equity(current_user=_USER, mgr=mgr)
    assert result == {"dates": [], "total_equity": [], "total_drawdown": [], "strategies": []}


@pytest.mark.asyncio
async def test_portfolio_equity_with_data():
    """Equity curve is aggregated across strategies."""
    from app.api.portfolio_api import get_portfolio_equity

    mgr = _MockManager([_INSTANCE_A])
    mock_value_data = {
        "dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "equity_curve": [100000.0, 105000.0, 103000.0],
        "cash_curve": [50000.0, 45000.0, 48000.0],
    }

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_value_log", return_value=mock_value_data),
    ):
        result = await get_portfolio_equity(current_user=_USER, mgr=mgr)

    assert result["dates"] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert result["total_equity"] == [100000.0, 105000.0, 103000.0]
    # Drawdown: peak=105000, dd on day 3 = -(105000-103000)/105000
    assert result["total_drawdown"][0] == 0  # no drawdown on day 1
    assert result["total_drawdown"][1] == 0  # new peak on day 2
    assert result["total_drawdown"][2] < 0  # drawdown on day 3
    assert len(result["strategies"]) == 1
    assert result["strategies"][0]["strategy_id"] == "strat_001"


# ══════════════════════════════════════════════════════════════════════════════
# Portfolio Allocation
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_portfolio_allocation_empty():
    """No instances returns empty allocation."""
    from app.api.portfolio_api import get_portfolio_allocation

    mgr = _MockManager([])
    result = await get_portfolio_allocation(current_user=_USER, mgr=mgr)
    assert result == {"total": 0, "items": []}


@pytest.mark.asyncio
async def test_portfolio_allocation_with_data():
    """Allocation weights are calculated correctly."""
    from app.api.portfolio_api import get_portfolio_allocation

    mgr = _MockManager([_INSTANCE_A, _INSTANCE_B])

    def mock_parse_value(log_dir):
        if "strat_001" in str(log_dir):
            return {"equity_curve": [100000.0, 75000.0]}  # final = 75000
        return {"equity_curve": [200000.0, 225000.0]}  # final = 225000

    with (
        patch("app.api.portfolio_api.get_strategy_dir", side_effect=lambda s: f"/fake/{s}"),
        patch("app.api.portfolio_api.find_latest_log_dir", side_effect=lambda d: f"{d}/logs"),
        patch("app.api.portfolio_api.parse_value_log", side_effect=mock_parse_value),
    ):
        result = await get_portfolio_allocation(current_user=_USER, mgr=mgr)

    # Total = 75000 + 225000 = 300000
    assert result["total"] == 300000.0
    assert len(result["items"]) == 2
    # strat_001: 75000/300000 = 25%
    assert result["items"][0]["weight"] == 25.0
    # strat_002: 225000/300000 = 75%
    assert result["items"][1]["weight"] == 75.0


# ══════════════════════════════════════════════════════════════════════════════
# Simulation Variants (delegate to live endpoints)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_simulation_overview_delegates():
    """Simulation overview delegates to live overview."""
    from app.api.portfolio_api import get_simulation_portfolio_overview

    mgr = _MockManager([])
    result = await get_simulation_portfolio_overview(current_user=_USER, mgr=mgr)
    assert result["strategy_count"] == 0


@pytest.mark.asyncio
async def test_simulation_positions_delegates():
    """Simulation positions delegates to live positions."""
    from app.api.portfolio_api import get_simulation_portfolio_positions

    mgr = _MockManager([])
    result = await get_simulation_portfolio_positions(current_user=_USER, mgr=mgr)
    assert result == {"total": 0, "positions": []}


@pytest.mark.asyncio
async def test_simulation_trades_delegates():
    """Simulation trades delegates to live trades."""
    from app.api.portfolio_api import get_simulation_portfolio_trades

    mgr = _MockManager([])
    result = await get_simulation_portfolio_trades(limit=100, current_user=_USER, mgr=mgr)
    assert result == {"total": 0, "trades": []}


@pytest.mark.asyncio
async def test_simulation_equity_delegates():
    """Simulation equity delegates to live equity."""
    from app.api.portfolio_api import get_simulation_portfolio_equity

    mgr = _MockManager([])
    result = await get_simulation_portfolio_equity(current_user=_USER, mgr=mgr)
    assert result == {"dates": [], "total_equity": [], "total_drawdown": [], "strategies": []}


@pytest.mark.asyncio
async def test_simulation_allocation_delegates():
    """Simulation allocation delegates to live allocation."""
    from app.api.portfolio_api import get_simulation_portfolio_allocation

    mgr = _MockManager([])
    result = await get_simulation_portfolio_allocation(current_user=_USER, mgr=mgr)
    assert result == {"total": 0, "items": []}


# ══════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_safe_round_nan_and_inf():
    """_safe_round handles NaN and Infinity."""
    from app.api.portfolio_api import _safe_round

    assert _safe_round(float("nan")) == 0.0
    assert _safe_round(float("inf")) == 0.0
    assert _safe_round(float("-inf")) == 0.0
    assert _safe_round(3.14159, 2) == 3.14


@pytest.mark.asyncio
async def test_portfolio_overview_zero_initial_capital():
    """Zero initial capital doesn't cause division by zero."""
    from app.api.portfolio_api import get_portfolio_overview

    mgr = _MockManager([_INSTANCE_A])
    mock_value_data = {"equity_curve": [], "cash_curve": []}

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_value_log", return_value=mock_value_data),
        patch("app.api.portfolio_api.parse_trade_log", return_value=[]),
    ):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_pnl_pct"] == 0
    assert result["strategies"][0]["pnl_pct"] == 0


@pytest.mark.asyncio
async def test_portfolio_positions_flat_position():
    """Position with size=0 is labeled 'flat'."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([_INSTANCE_A])
    mock_positions = [
        {"data_name": "BTC/USDT", "size": 0, "price": 60000.0, "market_value": 0},
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["positions"][0]["direction"] == "flat"
