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
from unittest.mock import patch

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


_EMPTY_POSITION_SUMMARY = {
    "total_long_value": 0.0,
    "total_short_value": 0.0,
    "gross_market_value": 0.0,
    "net_market_value": 0.0,
    "total_pnl": 0.0,
    "long_count": 0,
    "short_count": 0,
    "flat_count": 0,
}


def test_parse_positions_for_portfolio_prefers_position_log_precision(monkeypatch, tmp_path):
    """Current-position snapshots can be rounded; position.log keeps MT5 precision."""
    from app.api import portfolio_api

    rounded_snapshot = [
        {
            "data_name": "EURUSD",
            "size": -0.01,
            "price": 1.1381,
            "market_value": -0.01,
        }
    ]
    precise_log = [
        {
            "datetime": "2026-06-24 11:02:00",
            "data_name": "EURUSD",
            "size": -0.01,
            "price": 1.1381,
            "market_value": -0.0113789,
        }
    ]

    monkeypatch.setattr(portfolio_api, "parse_current_position", lambda _log_dir: rounded_snapshot)
    monkeypatch.setattr(portfolio_api, "parse_position_log", lambda _log_dir: precise_log)

    result = portfolio_api._parse_positions_for_portfolio(tmp_path)

    assert result == precise_log


def test_resolve_instance_log_dir_falls_back_when_explicit_log_dir_is_stale(tmp_path):
    """A stale persisted log_dir must not hide an active runtime_dir/logs."""
    from app.api import portfolio_api

    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "value.log").write_text(
        "dt\tvalue\tcash\n2026-06-25\t100000\t100000\n",
        encoding="utf-8",
    )

    result = portfolio_api._resolve_instance_log_dir(
        {
            "strategy_id": "simulate/gateway_dual_ma",
            "log_dir": str(tmp_path / "stale" / "logs"),
            "runtime_dir": str(runtime_dir),
        }
    )

    assert result == log_dir


class _MockManager:
    """Mock LiveTradingManager that returns configurable instances."""

    def __init__(self, instances=None):
        self._instances = instances or []

    def list_instances(self, **kwargs):
        return self._instances


# ── Helper patches ────────────────────────────────────────────────────────────


def _patch_deps(manager):
    """Return a context manager that patches get_current_user and _get_manager."""

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
    assert result["total_position_value"] == 70000.0
    assert result["net_position_value"] == 70000.0
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
async def test_portfolio_overview_position_value_uses_gross_market_value_for_shorts():
    """Overview position value is gross exposure; net exposure is separate."""
    from app.api.portfolio_api import get_portfolio_overview

    mgr = _MockManager([_INSTANCE_A])
    mock_value_data = {
        "equity_curve": [100000.0, 99000.0],
        "cash_curve": [100000.0, 120000.0],
    }
    mock_positions = [
        {"data_name": "IF2609", "size": -2.0, "price": 5000.0, "market_value": -10000.0},
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_value_log", return_value=mock_value_data),
        patch("app.api.portfolio_api.parse_trade_log", return_value=[]),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 99000.0
    assert result["total_cash"] == 120000.0
    assert result["total_position_value"] == 10000.0
    assert result["net_position_value"] == -10000.0


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
    assert result == {"total": 0, "positions": [], "summary": _EMPTY_POSITION_SUMMARY}


@pytest.mark.asyncio
async def test_portfolio_positions_with_data():
    """Positions are aggregated across strategies."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([_INSTANCE_A])
    mock_positions = [
        {
            "datetime": "2026-06-25T08:42:00.000+00:00",
            "data_name": "BTC/USDT",
            "size": 0.5,
            "price": 60000.0,
            "market_value": 30000.0,
        },
        {
            "dt": "2026-06-25",
            "log_time": "2026-06-25T09:01:00.000+08:00",
            "data_name": "ETH/USDT",
            "size": -2.0,
            "price": 3000.0,
            "market_value": 6000.0,
        },
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
    assert result["positions"][0]["market_value"] == 30000.0
    assert result["positions"][0]["signed_market_value"] == 30000.0
    assert result["positions"][1]["market_value"] == 6000.0
    assert result["positions"][1]["signed_market_value"] == -6000.0
    assert result["positions"][0]["strategy_name"] == "MA Cross"
    assert result["positions"][0]["updated_at"] == "2026-06-25T08:42:00.000+00:00"
    assert result["positions"][1]["updated_at"] == "2026-06-25T09:01:00.000+08:00"
    assert result["positions"][1]["data_time"] == "2026-06-25"
    assert sum(item["signed_market_value"] for item in result["positions"]) == 24000.0
    assert result["summary"] == {
        "total_long_value": 30000.0,
        "total_short_value": 6000.0,
        "gross_market_value": 36000.0,
        "net_market_value": 24000.0,
        "total_pnl": 0.0,
        "long_count": 1,
        "short_count": 1,
        "flat_count": 0,
    }


@pytest.mark.asyncio
async def test_portfolio_positions_preserve_small_market_value_latest_price():
    """Small MT5 position values should keep enough precision to price correctly."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([_INSTANCE_A])
    mock_positions = [
        {
            "data_name": "NZDUSD",
            "size": -0.01,
            "price": 0.5667,
            "market_value": -0.0056649,
        },
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["positions"][0]["latest_price"] == 0.5665
    assert result["positions"][0]["market_value"] == 0.005665
    assert result["positions"][0]["signed_market_value"] == -0.005665
    assert result["summary"]["total_short_value"] == 0.01


@pytest.mark.asyncio
async def test_portfolio_positions_strategy_dir_error():
    """ValueError from get_strategy_dir is handled gracefully."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager([_INSTANCE_A])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("bad")):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result == {"total": 0, "positions": [], "summary": _EMPTY_POSITION_SUMMARY}


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


@pytest.mark.asyncio
async def test_portfolio_trades_workspace_filter_applies_before_limit(
    tmp_path,
    monkeypatch,
):
    """Workspace filtering must happen before limiting recent portfolio trades."""
    from app.api.portfolio_api import get_portfolio_trades
    from app.db.database import async_session_maker
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace
    from app.services import workspace_unit_runtime

    monkeypatch.setattr(
        workspace_unit_runtime,
        "_WORKSPACE_UNITS_ROOT",
        tmp_path / "workspace_units",
    )

    current_user = SimpleNamespace(sub="u-trades-filter")
    user = User(
        id="u-trades-filter",
        username="u-trades-filter",
        email="u-trades-filter@example.com",
        hashed_password="x",
    )
    ctp_workspace = Workspace(
        id="ws-ctp-filter",
        user_id="u-trades-filter",
        name="CTP模拟工作区",
        workspace_type="trading",
    )
    mt5_workspace = Workspace(
        id="ws-mt5-filter",
        user_id="u-trades-filter",
        name="MT5模拟工作区",
        workspace_type="trading",
    )
    ctp_unit = StrategyUnit(
        id="unit-ctp-filter",
        workspace_id="ws-ctp-filter",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP趋势",
        symbol="IF2609",
        run_status="running",
        trading_instance_id="inst-ctp-filter",
        sort_order=1,
    )
    mt5_unit = StrategyUnit(
        id="unit-mt5-filter",
        workspace_id="ws-mt5-filter",
        strategy_id="simulate/mt5_eurusd_ma_cross",
        strategy_name="MT5趋势",
        symbol="EURUSD",
        run_status="running",
        trading_instance_id="inst-mt5-filter",
        sort_order=1,
    )

    async with async_session_maker() as session:
        session.add_all([user, ctp_workspace, mt5_workspace, ctp_unit, mt5_unit])
        await session.commit()

    def write_trade_log(workspace_id: str, unit_id: str, data_name: str, dtclose: str) -> None:
        log_dir = workspace_unit_runtime.unit_dir(workspace_id, unit_id) / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "trade.log").write_text(
            "ref\tisclosed\tdtopen\tdtclose\tdata_name\tlong\tsize\tprice\tvalue\t"
            "commission\tpnl\tpnlcomm\tbarlen\n"
            f"1\t1\t2026-06-25 09:00:00\t{dtclose}\t{data_name}\t1\t1\t"
            "1\t1\t0\t10\t10\t1\n",
            encoding="utf-8",
        )

    write_trade_log(
        "ws-ctp-filter",
        "unit-ctp-filter",
        "IF2609",
        "2026-06-24 09:01:00",
    )
    write_trade_log(
        "ws-mt5-filter",
        "unit-mt5-filter",
        "EURUSD",
        "2026-06-25 09:02:00",
    )

    mgr = _MockManager([])

    unfiltered = await get_portfolio_trades(limit=1, current_user=current_user, mgr=mgr)
    assert unfiltered["total"] == 2
    assert unfiltered["trades"][0]["data_name"] == "EURUSD"

    ctp_only = await get_portfolio_trades(
        limit=1,
        workspace_ids=["ws-ctp-filter"],
        current_user=current_user,
        mgr=mgr,
    )
    assert ctp_only["total"] == 1
    assert ctp_only["trades"][0]["data_name"] == "IF2609"
    assert ctp_only["trades"][0]["strategy_name"] == "CTP模拟工作区 / CTP趋势"


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


@pytest.mark.asyncio
async def test_portfolio_equity_prefers_intraday_datetimes():
    """Live equity curves should keep intraday points when value.log has them."""
    from app.api.portfolio_api import get_portfolio_equity

    mgr = _MockManager([_INSTANCE_A])
    mock_value_data = {
        "dates": ["2026-06-25", "2026-06-25", "2026-06-25"],
        "datetimes": [
            "2026-06-25T08:31:00.000+00:00",
            "2026-06-25T08:32:00.000+00:00",
            "2026-06-25T08:33:00.000+00:00",
        ],
        "equity_curve": [100000.0, 100025.0, 100010.0],
        "cash_curve": [99000.0, 99025.0, 99010.0],
    }

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_value_log", return_value=mock_value_data),
    ):
        result = await get_portfolio_equity(current_user=_USER, mgr=mgr)

    assert result["dates"] == mock_value_data["datetimes"]
    assert result["total_equity"] == [100000.0, 100025.0, 100010.0]


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
    assert result == {"total": 0, "positions": [], "summary": _EMPTY_POSITION_SUMMARY}


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
    assert result["summary"]["flat_count"] == 1


@pytest.mark.asyncio
async def test_portfolio_prefers_active_workspace_units_when_manager_is_empty(
    tmp_path,
    monkeypatch,
):
    """Active trading workspace units are visible across process boundaries."""
    from app.api.portfolio_api import (
        get_portfolio_overview,
        get_portfolio_positions,
        get_portfolio_trades,
    )
    from app.db.database import async_session_maker
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace
    from app.services import workspace_unit_runtime

    monkeypatch.setattr(
        workspace_unit_runtime,
        "_WORKSPACE_UNITS_ROOT",
        tmp_path / "workspace_units",
    )

    user = User(id="u1", username="u1", email="u1@example.com", hashed_password="x")
    workspace = Workspace(
        id="ws-1",
        user_id="u1",
        name="期货模拟工作区",
        workspace_type="trading",
    )
    unit = StrategyUnit(
        id="unit-1",
        workspace_id="ws-1",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测01-短周期均线-1m",
        symbol="IF2609",
        run_status="running",
        trading_instance_id="inst-db-1",
        sort_order=1,
    )

    async with async_session_maker() as session:
        session.add_all([user, workspace, unit])
        await session.commit()

    log_dir = workspace_unit_runtime.unit_dir("ws-1", "unit-1") / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "value.log").write_text(
        "dt\tvalue\tcash\n"
        "2026-06-24 00:00:00\t100000\t99000\n"
        "2026-06-24 00:01:00\t100200\t99100\n",
        encoding="utf-8",
    )
    (log_dir / "position.log").write_text(
        "dt\tdata_name\tsize\tprice\n"
        "2026-06-24 00:01:00\tIF2609\t1\t5000\n",
        encoding="utf-8",
    )
    (log_dir / "trade.log").write_text(
        "ref\tisclosed\tdtopen\tdtclose\tdata_name\tlong\tsize\tprice\tvalue\t"
        "commission\tpnl\tpnlcomm\tbarlen\n"
        "1\t1\t2026-06-24 00:00:00\t2026-06-24 00:01:00\tIF2609\t1\t1\t"
        "5000\t5000\t1\t200\t199\t1\n",
        encoding="utf-8",
    )

    mgr = _MockManager([])

    overview = await get_portfolio_overview(current_user=_USER, mgr=mgr)
    assert overview["strategy_count"] == 1
    assert overview["running_count"] == 1
    assert overview["total_assets"] == 100200.0
    assert overview["strategies"][0]["strategy_name"] == (
        "期货模拟工作区 / CTP压测01-短周期均线-1m"
    )

    positions = await get_portfolio_positions(current_user=_USER, mgr=mgr)
    assert positions["total"] == 1
    assert positions["positions"][0]["data_name"] == "IF2609"
    assert positions["summary"]["long_count"] == 1

    trades = await get_portfolio_trades(limit=10, current_user=_USER, mgr=mgr)
    assert trades["total"] == 1
    assert trades["trades"][0]["strategy_name"] == (
        "期货模拟工作区 / CTP压测01-短周期均线-1m"
    )
