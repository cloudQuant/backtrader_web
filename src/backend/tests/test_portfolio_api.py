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

import json
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


def test_parse_positions_for_portfolio_keeps_dual_side_same_symbol(monkeypatch, tmp_path):
    """Dual-side logs must not collapse long and short rows for the same symbol."""
    from app.api import portfolio_api

    precise_log = [
        {
            "datetime": "2026-06-24 11:00:00",
            "data_name": "IF2609",
            "size": 1,
            "price": 5000.0,
        },
        {
            "datetime": "2026-06-24 11:01:00",
            "data_name": "IF2609",
            "size": -2,
            "price": 5010.0,
        },
        {
            "datetime": "2026-06-24 11:02:00",
            "data_name": "IF2609",
            "size": 3,
            "price": 5020.0,
        },
    ]

    monkeypatch.setattr(portfolio_api, "parse_current_position", lambda _log_dir: [])
    monkeypatch.setattr(portfolio_api, "parse_position_log", lambda _log_dir: precise_log)

    result = portfolio_api._parse_positions_for_portfolio(tmp_path)

    assert len(result) == 2
    by_direction = {"long" if row["size"] > 0 else "short": row for row in result}
    assert by_direction["long"]["price"] == 5020.0
    assert by_direction["short"]["price"] == 5010.0


def test_parse_positions_for_portfolio_keeps_bybit_position_idx_dual_side(
    monkeypatch, tmp_path
):
    """Bybit hedge logs with positive sizes must keep both positionIdx legs."""
    from app.api import portfolio_api

    precise_log = [
        {
            "datetime": "2026-06-24 11:00:00",
            "data_name": "BTCUSDT",
            "positionIdx": "1",
            "size": 0.1,
            "price": 60000.0,
        },
        {
            "datetime": "2026-06-24 11:01:00",
            "data_name": "BTCUSDT",
            "positionIdx": "2",
            "size": 0.2,
            "price": 60100.0,
        },
    ]

    monkeypatch.setattr(portfolio_api, "parse_current_position", lambda _log_dir: [])
    monkeypatch.setattr(portfolio_api, "parse_position_log", lambda _log_dir: precise_log)

    result = portfolio_api._parse_positions_for_portfolio(tmp_path)

    assert len(result) == 2
    by_idx = {str(row["positionIdx"]): row for row in result}
    assert by_idx["1"]["price"] == pytest.approx(60000.0)
    assert by_idx["2"]["price"] == pytest.approx(60100.0)


def test_portfolio_position_row_direction_treats_bybit_position_idx_zero_as_one_way():
    """Bybit positionIdx=0 should defer to signed size in one-way mode."""
    from app.api import portfolio_api

    assert (
        portfolio_api._position_row_direction(
            {"data_name": "BTCUSDT", "positionIdx": "0", "size": 0.1},
            0.1,
        )
        == "long"
    )
    assert (
        portfolio_api._position_row_direction(
            {"data_name": "BTCUSDT", "positionIdx": "0", "size": -0.1},
            -0.1,
        )
        == "short"
    )


def test_parse_positions_for_portfolio_flat_log_clears_stale_position(monkeypatch, tmp_path):
    """A latest flat log row must clear earlier position rows and stale snapshots."""
    from app.api import portfolio_api

    stale_snapshot = [{"data_name": "IF2609", "size": 1, "price": 5000.0}]
    precise_log = [
        {
            "datetime": "2026-06-24 11:00:00",
            "data_name": "IF2609",
            "size": 1,
            "price": 5000.0,
        },
        {
            "datetime": "2026-06-24 11:02:00",
            "data_name": "IF2609",
            "size": 0,
            "price": 0.0,
        },
    ]

    monkeypatch.setattr(portfolio_api, "parse_current_position", lambda _log_dir: stale_snapshot)
    monkeypatch.setattr(portfolio_api, "parse_position_log", lambda _log_dir: precise_log)

    result = portfolio_api._parse_positions_for_portfolio(tmp_path)

    assert result == []


def test_parse_positions_for_portfolio_flat_log_does_not_fallback_to_stale_snapshot(
    monkeypatch, tmp_path
):
    """A log-confirmed flat position is authoritative over stale snapshots."""
    from app.api import portfolio_api

    stale_snapshot = [{"data_name": "IF2609", "size": 1, "price": 5000.0}]
    flat_log = [
        {
            "datetime": "2026-06-24 11:02:00",
            "data_name": "IF2609",
            "size": 0,
            "price": 0.0,
        },
    ]

    monkeypatch.setattr(portfolio_api, "parse_current_position", lambda _log_dir: stale_snapshot)
    monkeypatch.setattr(portfolio_api, "parse_position_log", lambda _log_dir: flat_log)

    result = portfolio_api._parse_positions_for_portfolio(tmp_path)

    assert result == []


def test_parse_positions_for_portfolio_directional_flat_keeps_opposite_side(
    monkeypatch, tmp_path
):
    """A long-side flat row must not clear a still-open short row for the same symbol."""
    from app.api import portfolio_api

    precise_log = [
        {
            "datetime": "2026-06-24 11:00:00",
            "data_name": "IF2609",
            "direction": "long",
            "size": 1,
            "price": 5000.0,
        },
        {
            "datetime": "2026-06-24 11:01:00",
            "data_name": "IF2609",
            "direction": "short",
            "size": -2,
            "price": 5010.0,
        },
        {
            "datetime": "2026-06-24 11:02:00",
            "data_name": "IF2609",
            "direction": "long",
            "size": 0,
            "price": 0.0,
        },
    ]

    monkeypatch.setattr(portfolio_api, "parse_current_position", lambda _log_dir: [])
    monkeypatch.setattr(portfolio_api, "parse_position_log", lambda _log_dir: precise_log)

    result = portfolio_api._parse_positions_for_portfolio(tmp_path)

    nonflat = [row for row in result if abs(float(row.get("size") or 0.0)) > 0]
    assert len(nonflat) == 1
    assert nonflat[0]["direction"] == "short"
    assert nonflat[0]["price"] == 5010.0


def test_snapshot_positions_for_portfolio_preserves_explicit_margin_value():
    """Snapshot fallback should keep exchange-reported margin instead of re-estimating it."""
    from app.api import portfolio_api
    from app.services.position_valuation import PositionSpec, value_position

    rows = portfolio_api._snapshot_positions_for_portfolio(
        {
            "positions": [
                {
                    "data_name": "XAUUSD",
                    "direction": "long",
                    "size": 0.1,
                    "price": 2300.0,
                    "current_price": 2310.0,
                    "margin_value": 39.0,
                    "use_margin": 39.0,
                }
            ]
        }
    )

    assert rows[0]["margin_value"] == 39.0
    valued = value_position(rows[0], spec=PositionSpec(multiplier=100, margin_rate=0.02))
    assert valued is not None
    assert valued.margin_value == 39.0


def test_snapshot_positions_for_portfolio_preserves_signed_short_without_direction():
    """Legacy snapshots may encode short direction only through a negative size."""
    from app.api import portfolio_api

    rows = portfolio_api._snapshot_positions_for_portfolio(
        {
            "positions": [
                {
                    "data_name": "EURUSD",
                    "size": -0.01,
                    "price": 1.1381,
                    "market_value": -0.0113789,
                }
            ]
        }
    )

    assert rows[0]["size"] == pytest.approx(-0.01)


def test_snapshot_positions_for_portfolio_handles_sell_direction_alias():
    """Snapshot fallback should not turn sell-side rows into long exposure."""
    from app.api import portfolio_api

    rows = portfolio_api._snapshot_positions_for_portfolio(
        {
            "positions": [
                {
                    "data_name": "BTCUSDT",
                    "direction": "sell",
                    "size": 0.25,
                    "price": 60000.0,
                }
            ]
        }
    )

    assert rows[0]["size"] == pytest.approx(-0.25)


def test_snapshot_positions_for_portfolio_handles_numeric_short_direction():
    """CTP/MT5-style numeric short codes should remain short in snapshot fallback."""
    from app.api import portfolio_api

    rows = portfolio_api._snapshot_positions_for_portfolio(
        {
            "positions": [
                {
                    "data_name": "IF2609",
                    "PosiDirection": 3,
                    "size": 1,
                    "price": 5000.0,
                }
            ]
        }
    )

    assert rows[0]["size"] == pytest.approx(-1.0)


def test_snapshot_positions_for_portfolio_preserves_raw_ctp_asset_aliases():
    """Snapshot fallback should keep raw CTP fields for multiplier-aware valuation."""
    from app.api import portfolio_api
    from app.services.position_valuation import contract_spec_for, value_position

    rows = portfolio_api._snapshot_positions_for_portfolio(
        {
            "positions": [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "Price": 5000.0,
                    "LastPrice": 5001.0,
                    "VolumeMultiple": 300,
                    "LongMarginRatioByMoney": 0.1,
                    "OpenRatioByMoney": 0.23,
                    "source": "ctp_gateway",
                }
            ]
        }
    )

    valued = value_position(rows[0], spec=contract_spec_for("IF2609", rows[0]))

    assert rows[0]["data_name"] == "IF2609"
    assert rows[0]["size"] == pytest.approx(1.0)
    assert rows[0]["VolumeMultiple"] == 300
    assert rows[0]["market_value_estimated"] is True
    assert valued is not None
    assert valued.market_value == pytest.approx(1_500_300.0)
    assert valued.pnl == pytest.approx(265.5)


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


def test_asset_spec_lookup_supports_exchange_prefixed_symbols():
    from app.api.portfolio_api import _asset_spec_for_symbol

    spec = {"symbol": "IF2609", "multiplier": 300}

    assert _asset_spec_for_symbol({"IF2609": spec}, "CFFEX.IF2609") == spec
    assert _asset_spec_for_symbol({"IF2609": spec}, "IF2609.CFFEX") == spec
    assert _asset_spec_for_symbol({"rb2601": spec}, "SHFE_rb2601") == spec


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
async def test_portfolio_overview_does_not_fallback_position_value_when_gateway_confirms_flat():
    """An empty gateway position snapshot is confirmed flat, not missing data."""
    from app.api.portfolio_api import get_portfolio_overview

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return []

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "account_id": "acct-a",
                "value": 10000.0,
                "cash": 9500.0,
                "account_source": "gateway",
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT-SWAP",
                },
            }
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 10000.0
    assert result["total_cash"] == 9500.0
    assert result["total_position_value"] == 0.0
    assert result["net_position_value"] == 0.0
    assert result["strategies"][0]["position_source"] == "gateway"
    assert result["strategies"][0]["valuation_status"] == "confirmed"


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
async def test_portfolio_positions_use_live_gateway_positions_without_log_dir():
    """Running gateway positions should be valued even when no log dir exists."""
    from app.api.portfolio_api import get_portfolio_positions

    instance = {
        **_INSTANCE_A,
        "params": {"symbol": "XAUUSD"},
    }

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.1,
                    "price_open": 2300.0,
                    "last_price": 2310.0,
                    "profit": 100.0,
                    "commission": -1.0,
                    "swap": -0.5,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {"XAUUSD": {"contract_size": 100, "margin_rate": 0.02}}

    mgr = GatewayManager([instance])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["total"] == 1
    assert result["positions"][0]["data_name"] == "XAUUSD"
    assert result["positions"][0]["size"] == 0.1
    assert result["positions"][0]["market_value"] == 23100.0
    assert result["positions"][0]["margin_value"] == 462.0
    assert result["positions"][0]["multiplier"] == 100.0
    assert result["positions"][0]["commission"] == 1.0
    assert result["positions"][0]["position_pnl"] == 98.5
    assert result["summary"]["gross_market_value"] == 23100.0


@pytest.mark.asyncio
async def test_portfolio_positions_value_bybit_v5_short_with_real_execution_fee():
    """Bybit v5 raw side/exec fields should value shorts and real fees correctly."""
    from app.api.portfolio_api import get_portfolio_positions

    instance = {
        **_INSTANCE_A,
        "params": {"trading_mode": "live", "symbol": "BTCUSDT"},
    }

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "size": "0.1",
                    "avgPrice": "60000",
                    "markPrice": "59000",
                    "positionValue": "5900",
                    "positionIM": "590",
                    "unrealisedPnl": "100",
                    "leverage": "10",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "contract_size": 1,
                    "quote_asset": "USDT",
                    "commission_rate": 0.0004,
                    "source": "bybit_gateway",
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "BTCUSDT"
            return [
                {
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "execQty": "0.1",
                    "execPrice": "60000",
                    "execFee": "3",
                    "feeCurrency": "USDT",
                    "execTime": "1",
                }
            ]

    mgr = GatewayManager([instance])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "BTCUSDT"
    assert row["size"] == pytest.approx(-0.1)
    assert row["direction"] == "short"
    assert row["market_value"] == 5900.0
    assert row["signed_market_value"] == -5900.0
    assert row["margin_value"] == 590.0
    assert row["commission"] == 3.0
    assert row["gross_pnl"] == 100.0
    assert row["position_pnl"] == 97.0
    assert row["asset_spec_source"] == "bybit_gateway"
    assert result["summary"]["total_short_value"] == 5900.0
    assert result["summary"]["net_market_value"] == -5900.0
    assert result["summary"]["total_pnl"] == 97.0


@pytest.mark.asyncio
async def test_portfolio_positions_use_runtime_config_asset_specs_when_gateway_specs_empty(
    tmp_path,
):
    """Persisted runtime contract metadata should backstop gateway spec query gaps."""
    from app.api.portfolio_api import get_portfolio_positions

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "config.yaml").write_text(
        "contract_metadata:\n"
        "  IF2609:\n"
        "    symbol: IF2609\n"
        "    multiplier: 300\n"
        "    margin_rate: 0.1\n"
        "    commission_rate: 0.000023\n"
        "    source: runtime_config\n",
        encoding="utf-8",
    )
    instance = {
        **_INSTANCE_A,
        "runtime_dir": str(runtime_dir),
        "params": {"trading_mode": "live", "symbol": "IF2609"},
    }

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "IF2609",
                    "direction": "long",
                    "volume": 1,
                    "price": 5000.0,
                    "current_price": 5001.0,
                    "profit": 300.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {}

    mgr = GatewayManager([instance])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["market_value"] == 1_500_300.0
    assert row["margin_value"] == 150_030.0
    assert row["multiplier"] == 300.0
    assert row["commission"] == 34.5
    assert row["position_pnl"] == 265.5
    assert row["asset_spec_source"] == "runtime_config"


@pytest.mark.asyncio
async def test_portfolio_positions_persist_gateway_asset_specs_to_workspace_unit():
    """Portfolio risk views should store exchange specs for later snapshot valuation."""
    from app.api.portfolio_api import get_portfolio_positions
    from app.db.database import async_session_maker
    from app.models.user import User
    from app.models.workspace import StrategyUnit, Workspace

    user_id = "u-portfolio-spec-persist"
    current_user = SimpleNamespace(sub=user_id)
    user = User(
        id=user_id,
        username=user_id,
        email=f"{user_id}@example.com",
        hashed_password="x",
    )
    workspace = Workspace(
        id="ws-portfolio-spec-persist",
        user_id=user_id,
        name="组合风控规格持久化",
        workspace_type="trading",
    )
    unit = StrategyUnit(
        id="unit-portfolio-spec-persist",
        workspace_id=workspace.id,
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="IF实盘",
        symbol="IF2609",
        run_status="running",
        trading_mode="live",
        trading_instance_id="inst-portfolio-spec-persist",
        params={
            "contract_metadata": {
                "IF2609": {
                    "source": "stale_local",
                    "multiplier": 1,
                    "margin_rate": 1,
                    "commission_rate": 0,
                }
            }
        },
    )
    async with async_session_maker() as session:
        session.add_all([user, workspace, unit])
        await session.commit()

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-portfolio-spec-persist"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-portfolio-spec-persist"
            return [
                {
                    "instrument": "IF2609",
                    "direction": "long",
                    "volume": 1,
                    "price": 5000.0,
                    "current_price": 5001.0,
                    "profit": 300.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-portfolio-spec-persist"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "symbol": "IF2609",
                    "source": "ctp_gateway",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            }

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-portfolio-spec-persist"
            return {
                "gateway_key": "manual:CTP:spec",
                "value": 100000.0,
                "cash": 90000.0,
            }

    result = await get_portfolio_positions(current_user=current_user, mgr=GatewayManager([]))

    row = result["positions"][0]
    assert row["market_value"] == 1_500_300.0
    assert row["margin_value"] == 150_030.0
    assert row["commission"] == 34.5
    assert row["position_pnl"] == 265.5
    assert row["asset_spec_source"] == "ctp_gateway"

    async with async_session_maker() as session:
        stored = await session.get(StrategyUnit, "unit-portfolio-spec-persist")
        assert stored is not None
        metadata = stored.params["contract_metadata"]["IF2609"]
        assert metadata["source"] == "stale_local+ctp_gateway"
        assert metadata["multiplier"] == 300
        assert metadata["margin_rate"] == 0.1
        assert metadata["commission_rate"] == 0.000023


@pytest.mark.asyncio
async def test_portfolio_positions_recalculate_stale_local_net_pnl_with_asset_specs(tmp_path):
    """Local position snapshots with stale net PnL must be revalued with asset metadata."""
    from app.api.portfolio_api import get_portfolio_positions

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "current_position.json").write_text(
        json.dumps(
            [
                {
                    "data_name": "IF2609",
                    "size": 1,
                    "price": 5000.0,
                    "current_price": 5001.0,
                    "gross_pnl": 1.0,
                    "position_pnl": 1.0,
                    "pnlcomm": 1.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    instance = {
        **_INSTANCE_A,
        "log_dir": str(log_dir),
        "params": {
            "trading_mode": "paper",
            "symbol": "IF2609",
            "contract_metadata": {
                "IF2609": {
                    "source": "runtime_config",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            },
        },
    }

    result = await get_portfolio_positions(current_user=_USER, mgr=_MockManager([instance]))

    row = result["positions"][0]
    assert row["market_value"] == 1_500_300.0
    assert row["margin_value"] == 150_030.0
    assert row["gross_pnl"] == 300.0
    assert row["commission"] == 34.5
    assert row["position_pnl"] == 265.5
    assert row["asset_spec_source"] == "runtime_config"
    assert row["valuation_status"] == "estimated"
    assert any("重新计算" in item for item in row["valuation_warnings"])
    assert result["summary"]["total_pnl"] == 265.5


@pytest.mark.asyncio
async def test_portfolio_positions_warn_when_bound_gateway_position_query_fails():
    """A bound gateway query failure must not be reported as confirmed flat."""
    from app.api.portfolio_api import get_portfolio_positions

    instance = {
        **_INSTANCE_A,
        "params": {
            "trading_mode": "live",
            "symbol": "IF2609",
        },
    }

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            raise RuntimeError("gateway runtime missing")

    mgr = GatewayManager([instance])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["positions"] == []
    assert result["summary"] == _EMPTY_POSITION_SUMMARY
    assert any("交易所网关持仓查询失败" in item for item in result["warnings"])


@pytest.mark.asyncio
async def test_portfolio_overview_uses_live_gateway_account_without_log_dir():
    """Live account equity should populate overview when local logs are absent."""
    from app.api.portfolio_api import get_portfolio_overview

    instance = {
        **_INSTANCE_A,
        "params": {
            "trading_mode": "live",
            "symbol": "XAUUSD",
        },
    }

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.1,
                    "price_open": 2300.0,
                    "last_price": 2310.0,
                    "profit": 100.0,
                    "commission": -1.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {"XAUUSD": {"contract_size": 100, "margin_rate": 0.02}}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "gateway_key": "manual:MT5:demo",
                "account_source": "adapter.get_balance",
                "value": 100250.0,
                "cash": 99050.0,
                "margin": 1200.0,
            }

    mgr = GatewayManager([instance])

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 100250.0
    assert result["total_cash"] == 99050.0
    assert result["total_initial_capital"] == 100250.0
    assert result["total_pnl"] == 0.0
    assert result["total_position_value"] == 23100.0
    strategy = result["strategies"][0]
    assert strategy["total_assets"] == 100250.0
    assert strategy["account_source"] == "adapter.get_balance"
    assert strategy["account_counted_in_totals"] is True


@pytest.mark.asyncio
async def test_portfolio_overview_reads_crypto_account_balance_aliases():
    """Crypto exchange balance aliases must contribute to live account totals."""
    from app.api.portfolio_api import get_portfolio_overview

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "gateway_key": "manual:BYBIT:unified",
                "account_source": "adapter.get_balance",
                "account_type": "UNIFIED",
                "totalEquity": "10,250.5",
                "totalWalletBalance": {"amount": "10,000.0"},
                "totalAvailableBalance": {"amount": "9,125.25"},
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "BTCUSDT"},
            }
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 10250.5
    assert result["total_cash"] == 9125.25
    assert result["total_initial_capital"] == 10250.5
    assert result["strategies"][0]["total_assets"] == 10250.5
    assert result["strategies"][0]["account_counted_in_totals"] is True


@pytest.mark.asyncio
async def test_portfolio_overview_reads_okx_account_balance_aliases():
    """OKX account aliases should contribute value, available cash, and margin."""
    from app.api.portfolio_api import get_portfolio_overview

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "gateway_key": "manual:OKX:main",
                "account_source": "adapter.get_balance",
                "totalEq": "2,500.0",
                "availEq": "2,100.0",
                "imr": "400.0",
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "BTC-USDT-SWAP"},
            }
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 2500.0
    assert result["total_cash"] == 2100.0
    assert result["total_initial_capital"] == 2500.0
    assert result["strategies"][0]["total_assets"] == 2500.0
    assert result["strategies"][0]["account_counted_in_totals"] is True


@pytest.mark.asyncio
async def test_portfolio_overview_derives_cash_from_equity_minus_margin_before_balance():
    """Balance must not be treated as available cash when margin is in use."""
    from app.api.portfolio_api import get_portfolio_overview

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "gateway_key": "manual:MT5:demo",
                "account_source": "adapter.get_balance",
                "balance": 100000.0,
                "equity": 100250.0,
                "margin": 1200.0,
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            }
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 100250.0
    assert result["total_cash"] == 99050.0
    assert result["total_initial_capital"] == 100250.0


@pytest.mark.asyncio
async def test_portfolio_overview_counts_shared_gateway_account_once_without_logs():
    """Multiple strategies on one gateway must not double count account equity."""
    from app.api.portfolio_api import get_portfolio_overview

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            return instance_id in {"inst-a", "inst-b"}

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id in {"inst-a", "inst-b"}
            return {
                "gateway_key": "manual:MT5:shared",
                "account_source": "adapter.get_balance",
                "value": 100250.0,
                "cash": 99050.0,
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "id": "inst-a",
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            },
            {
                **_INSTANCE_B,
                "id": "inst-b",
                "status": "running",
                "params": {"trading_mode": "live", "symbol": "EURUSD"},
            },
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 100250.0
    assert result["total_cash"] == 99050.0
    assert result["total_initial_capital"] == 100250.0
    assert [item["account_counted_in_totals"] for item in result["strategies"]] == [True, False]


@pytest.mark.asyncio
async def test_portfolio_overview_does_not_merge_distinct_accounts_by_currency_only():
    """Currency is not an account identity; USD accounts can be separate."""
    from app.api.portfolio_api import get_portfolio_overview

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            return instance_id in {"inst-a", "inst-b"}

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            values = {
                "inst-a": 100250.0,
                "inst-b": 50300.0,
            }
            return {
                "account_source": "adapter.get_balance",
                "value": values[instance_id],
                "cash": values[instance_id] - 1000.0,
                "currency": "USD",
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "id": "inst-a",
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            },
            {
                **_INSTANCE_B,
                "id": "inst-b",
                "status": "running",
                "params": {"trading_mode": "live", "symbol": "EURUSD"},
            },
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_overview(current_user=_USER, mgr=mgr)

    assert result["total_assets"] == 150550.0
    assert result["total_cash"] == 148550.0
    assert result["total_initial_capital"] == 150550.0
    assert [item["account_counted_in_totals"] for item in result["strategies"]] == [True, True]


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


@pytest.mark.asyncio
async def test_portfolio_equity_uses_live_gateway_account_without_log_dir():
    """Equity should show a live account point when no local logs exist."""
    from app.api.portfolio_api import get_portfolio_equity

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "gateway_key": "manual:MT5:demo",
                "account_source": "adapter.get_balance",
                "value": 100250.0,
                "cash": 99050.0,
                "updated_at": "2026-06-26T09:30:00+08:00",
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            }
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_equity(current_user=_USER, mgr=mgr)

    assert result["dates"] == ["2026-06-26T09:30:00+08:00"]
    assert result["total_equity"] == [100250.0]
    assert result["total_drawdown"] == [0.0]
    assert result["strategies"][0]["values"] == [100250.0]
    assert result["strategies"][0]["value_source"] == "adapter.get_balance"


@pytest.mark.asyncio
async def test_portfolio_equity_counts_shared_gateway_account_once_without_logs():
    """Equity must not double count one shared live account."""
    from app.api.portfolio_api import get_portfolio_equity

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            return instance_id in {"inst-a", "inst-b"}

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id in {"inst-a", "inst-b"}
            return {
                "gateway_key": "manual:MT5:shared",
                "account_source": "adapter.get_balance",
                "value": 100250.0,
                "cash": 99050.0,
                "updated_at": "2026-06-26T09:30:00+08:00",
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "id": "inst-a",
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            },
            {
                **_INSTANCE_B,
                "id": "inst-b",
                "status": "running",
                "params": {"trading_mode": "live", "symbol": "EURUSD"},
            },
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_equity(current_user=_USER, mgr=mgr)

    assert result["total_equity"] == [100250.0]
    assert len(result["strategies"]) == 1
    assert result["strategies"][0]["instance_id"] == "inst-a"


@pytest.mark.asyncio
async def test_portfolio_equity_does_not_backfill_before_strategy_first_point():
    """A strategy should contribute zero before its first equity point."""
    from app.api.portfolio_api import get_portfolio_equity

    mgr = _MockManager([_INSTANCE_A, _INSTANCE_B])

    def mock_parse_value(log_dir):
        if "strat_001" in str(log_dir):
            return {"dates": ["2026-06-25", "2026-06-26"], "equity_curve": [100.0, 110.0]}
        return {"dates": ["2026-06-26"], "equity_curve": [200.0]}

    with (
        patch("app.api.portfolio_api.get_strategy_dir", side_effect=lambda s: f"/fake/{s}"),
        patch("app.api.portfolio_api.find_latest_log_dir", side_effect=lambda d: f"{d}/logs"),
        patch("app.api.portfolio_api.parse_value_log", side_effect=mock_parse_value),
    ):
        result = await get_portfolio_equity(current_user=_USER, mgr=mgr)

    assert result["dates"] == ["2026-06-25", "2026-06-26"]
    assert result["total_equity"] == [100.0, 310.0]
    by_instance = {item["instance_id"]: item for item in result["strategies"]}
    assert by_instance["inst-a"]["values"] == [100.0, 110.0]
    assert by_instance["inst-b"]["values"] == [0.0, 200.0]


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


@pytest.mark.asyncio
async def test_portfolio_allocation_uses_live_gateway_account_without_log_dir():
    """Allocation should include live account equity when no local logs exist."""
    from app.api.portfolio_api import get_portfolio_allocation

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id == "inst-a"
            return {
                "gateway_key": "manual:MT5:demo",
                "account_source": "adapter.get_balance",
                "value": 100250.0,
                "cash": 99050.0,
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            }
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_allocation(current_user=_USER, mgr=mgr)

    assert result["total"] == 100250.0
    assert result["items"] == [
        {
            "strategy_id": "strat_001",
            "strategy_name": "MA Cross",
            "instance_id": "inst-a",
            "value": 100250.0,
            "value_source": "adapter.get_balance",
            "weight": 100.0,
        }
    ]


@pytest.mark.asyncio
async def test_portfolio_allocation_counts_shared_gateway_account_once_without_logs():
    """Allocation must not double count one shared live account."""
    from app.api.portfolio_api import get_portfolio_allocation

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            return instance_id in {"inst-a", "inst-b"}

        def query_instance_gateway_positions(self, instance_id):
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

        def query_instance_gateway_account(self, instance_id):
            assert instance_id in {"inst-a", "inst-b"}
            return {
                "gateway_key": "manual:MT5:shared",
                "account_source": "adapter.get_balance",
                "value": 100250.0,
                "cash": 99050.0,
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "id": "inst-a",
                "params": {"trading_mode": "live", "symbol": "XAUUSD"},
            },
            {
                **_INSTANCE_B,
                "id": "inst-b",
                "status": "running",
                "params": {"trading_mode": "live", "symbol": "EURUSD"},
            },
        ]
    )

    with patch("app.api.portfolio_api.get_strategy_dir", side_effect=ValueError("not found")):
        result = await get_portfolio_allocation(current_user=_USER, mgr=mgr)

    assert result["total"] == 100250.0
    assert len(result["items"]) == 1
    assert result["items"][0]["value"] == 100250.0
    assert result["items"][0]["weight"] == 100.0


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
    """Position with size=0 is hidden from portfolio positions."""
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

    assert result["positions"] == []
    assert result["summary"] == _EMPTY_POSITION_SUMMARY


@pytest.mark.asyncio
async def test_portfolio_positions_use_contract_multiplier_and_commission():
    """Futures positions use contract multiplier and net out real commission."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "unit_settings": {
                        "multiplier": 10,
                        "margin": 0.1,
                        "commission": 0.0002,
                    }
                },
            }
        ]
    )
    mock_positions = [
        {
            "data_name": "rb2610",
            "size": 1,
            "price": 3127.0,
            "current_price": 3126.0,
            "market_value": 3126.0,
            "commission": 2.5,
        },
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["positions"][0]["market_value"] == 31260.0
    assert result["positions"][0]["signed_market_value"] == 31260.0
    assert result["positions"][0]["margin_value"] == 3126.0
    assert result["positions"][0]["multiplier"] == 10.0
    assert result["positions"][0]["commission"] == 2.5
    assert result["positions"][0]["position_pnl"] == -12.5
    assert result["summary"]["total_long_value"] == 31260.0
    assert result["summary"]["total_pnl"] == -12.5


@pytest.mark.asyncio
async def test_portfolio_positions_revalue_stale_snapshot_with_saved_asset_spec():
    """Portfolio risk should not reuse stale local PnL when saved asset specs exist."""
    from app.api.portfolio_api import get_portfolio_positions

    mgr = _MockManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "contract_metadata": {
                        "IF2609": {
                            "symbol": "IF2609",
                            "multiplier": 300,
                            "margin_rate": 0.1,
                            "commission_rate": 0.000023,
                            "source": "runtime_asset_spec",
                        }
                    }
                },
            }
        ]
    )
    mock_positions = [
        {
            "data_name": "IF2609",
            "size": 1,
            "price": 5000.0,
            "current_price": 5001.0,
            "market_value": 5001.0,
            "position_pnl": 1.0,
            "position_source": "snapshot",
        },
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["market_value"] == pytest.approx(1_500_300.0)
    assert row["margin_value"] == pytest.approx(150_030.0)
    assert row["leverage"] == pytest.approx(10.0)
    assert row["gross_pnl"] == pytest.approx(300.0)
    assert row["commission"] == pytest.approx(34.5)
    assert row["position_pnl"] == pytest.approx(265.5)
    assert result["summary"]["total_pnl"] == pytest.approx(265.5)
    assert any("重新计算" in warning for warning in row["valuation_warnings"])


@pytest.mark.asyncio
async def test_portfolio_positions_revalue_stale_snapshot_with_local_asset_spec(monkeypatch):
    """Local exchange metadata should repair stale snapshot PnL when runtime specs are absent."""
    from app.api import portfolio_api
    from app.api.portfolio_api import get_portfolio_positions

    monkeypatch.setattr(
        portfolio_api,
        "query_local_asset_spec",
        lambda symbol: {
            "symbol": symbol,
            "multiplier": 300,
            "margin_rate": 0.1,
            "commission_rate": 0.000023,
            "source": "local_futures_commission",
        },
    )

    mgr = _MockManager([_INSTANCE_A])
    mock_positions = [
        {
            "data_name": "IF2609",
            "size": 1,
            "price": 5000.0,
            "current_price": 5001.0,
            "market_value": 5001.0,
            "position_pnl": 1.0,
            "position_source": "snapshot",
        },
    ]

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value="/fake/dir"),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value="/fake/logs"),
        patch("app.api.portfolio_api.parse_current_position", return_value=mock_positions),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["asset_spec_source"] == "local_futures_commission"
    assert row["market_value"] == pytest.approx(1_500_300.0)
    assert row["margin_value"] == pytest.approx(150_030.0)
    assert row["gross_pnl"] == pytest.approx(300.0)
    assert row["commission"] == pytest.approx(34.5)
    assert row["position_pnl"] == pytest.approx(265.5)
    assert result["summary"]["total_pnl"] == pytest.approx(265.5)


@pytest.mark.asyncio
async def test_portfolio_positions_use_local_mt5_forex_contract_size_when_log_fallback(
    tmp_path,
):
    """MT5 forex log fallback must use contract size before calculating PnL."""
    from app.api.portfolio_api import get_portfolio_positions

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "current_position.json").write_text(
        json.dumps(
            [
                {
                    "data_name": "NZDUSD",
                    "size": 0.01,
                    "price": 0.5649913,
                    "current_price": 0.56501,
                    "market_value": 0.0056501,
                }
            ]
        ),
        encoding="utf-8",
    )

    mgr = _MockManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "NZDUSD",
                    "data": {"exchange": "MT5", "asset_type": "forex"},
                    "unit_settings": {"commission": 0.00007},
                },
            }
        ]
    )

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value=str(tmp_path)),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value=str(log_dir)),
        patch("app.api.portfolio_api.load_runtime_config", return_value={}),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "NZDUSD"
    assert row["market_value"] == pytest.approx(565.01)
    assert row["signed_market_value"] == pytest.approx(565.01)
    assert row["multiplier"] == pytest.approx(100000.0)
    assert row["asset_spec_source"] == "local_mt5_defaults"
    assert row["gross_pnl"] == pytest.approx(0.01)
    assert row["commission"] == pytest.approx(0.0395)
    assert row["position_pnl"] == pytest.approx(-0.03)
    assert result["summary"]["total_long_value"] == pytest.approx(565.01)
    assert result["summary"]["total_pnl"] == pytest.approx(-0.03)


@pytest.mark.asyncio
async def test_portfolio_positions_value_gateway_current_position_fallback(tmp_path):
    """Raw gateway fields in current_position.json still produce signed, fee-aware PnL."""
    from app.api.portfolio_api import get_portfolio_positions

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "current_position.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "BTCUSDT",
                    "positionSide": "SHORT",
                    "positionAmt": "0.25",
                    "entryPrice": "60000",
                    "markPrice": "59000",
                    "position_fee": "0.25",
                    "contract_size": "1",
                }
            ]
        ),
        encoding="utf-8",
    )

    mgr = _MockManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "BTCUSDT"},
            }
        ]
    )

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value=str(tmp_path)),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value=str(log_dir)),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "BTCUSDT"
    assert row["size"] == -0.25
    assert row["signed_market_value"] == -14750.0
    assert row["commission"] == 0.25
    assert row["position_pnl"] == 249.75
    assert result["summary"]["short_count"] == 1
    assert result["summary"]["net_market_value"] == -14750.0


@pytest.mark.asyncio
async def test_portfolio_positions_value_raw_ctp_current_position_spec_aliases(tmp_path):
    """CTP raw current_position aliases must not fall back to multiplier=1."""
    from app.api.portfolio_api import get_portfolio_positions

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "current_position.json").write_text(
        json.dumps(
            [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "Price": 5000.0,
                    "LastPrice": 5001.0,
                    "VolumeMultiple": 300,
                    "LongMarginRatioByMoney": 0.1,
                    "OpenRatioByMoney": 0.23,
                    "source": "ctp_gateway",
                }
            ]
        ),
        encoding="utf-8",
    )

    mgr = _MockManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "IF2609"},
            }
        ]
    )

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value=str(tmp_path)),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value=str(log_dir)),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "IF2609"
    assert row["market_value"] == 1_500_300.0
    assert row["margin_value"] == 150_030.0
    assert row["multiplier"] == 300.0
    assert row["commission"] == 34.5
    assert row["position_pnl"] == 265.5


@pytest.mark.asyncio
async def test_portfolio_positions_value_raw_ctp_position_log_aliases(tmp_path):
    """Raw CTP aliases in position.log must feed portfolio positions before snapshot fallback."""
    from app.api.portfolio_api import get_portfolio_positions

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "datetime": "2026-06-24 11:02:00",
                "InstrumentID": "IF2609",
                "PosiDirection": "2",
                "Position": 1,
                "Price": 5000.0,
                "LastPrice": 5001.0,
                "VolumeMultiple": 300,
                "LongMarginRatioByMoney": 0.1,
                "OpenRatioByMoney": 0.23,
                "source": "ctp_gateway",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    mgr = _MockManager(
        [
            {
                **_INSTANCE_A,
                "params": {"trading_mode": "live", "symbol": "IF2609"},
            }
        ]
    )

    with (
        patch("app.api.portfolio_api.get_strategy_dir", return_value=str(tmp_path)),
        patch("app.api.portfolio_api.find_latest_log_dir", return_value=str(log_dir)),
    ):
        result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "IF2609"
    assert row["market_value"] == 1_500_300.0
    assert row["margin_value"] == 150_030.0
    assert row["commission"] == 34.5
    assert row["position_pnl"] == 265.5


@pytest.mark.asyncio
async def test_portfolio_positions_expose_gateway_valuation_metadata():
    """Live portfolio positions show gateway/spec provenance for risk review."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "IF2609",
                    "direction": "long",
                    "volume": 1,
                    "price_open": 5000.0,
                    "last_price": 5001.0,
                    "profit": 300.0,
                    "commission": 34.5069,
                    "use_margin": 150030.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["position_source"] == "gateway"
    assert row["asset_spec_source"] == "ctp_gateway"
    assert row["valuation_status"] == "confirmed"
    assert row["valuation_warnings"] == []
    assert row["market_value"] == 1500300.0
    assert row["margin_value"] == 150030.0
    assert row["commission"] == pytest.approx(34.5069)


@pytest.mark.asyncio
async def test_portfolio_positions_filter_shared_gateway_rows_by_source_symbol():
    """Shared gateway account positions must not be duplicated into every strategy."""
    from app.api.portfolio_api import get_portfolio_positions

    raw_positions = [
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "size": 0.1,
            "price": 60000.0,
            "current_price": 61000.0,
        },
        {
            "symbol": "ETH/USDT",
            "side": "long",
            "size": 2.0,
            "price": 3000.0,
            "current_price": 3100.0,
        },
    ]

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            return instance_id in {"inst-btc", "inst-eth"}

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id in {"inst-btc", "inst-eth"}
            return list(raw_positions)

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id in {"inst-btc", "inst-eth"}
            return {
                symbol: {"source": "shared_gateway", "contract_size": 1, "commission_rate": 0.0}
                for symbol in symbols
            }

    mgr = GatewayManager(
        [
            {
                "id": "inst-btc",
                "strategy_id": "btc_strategy",
                "strategy_name": "BTC Strategy",
                "status": "running",
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC/USDT",
                },
            },
            {
                "id": "inst-eth",
                "strategy_id": "eth_strategy",
                "strategy_name": "ETH Strategy",
                "status": "running",
                "params": {
                    "trading_mode": "live",
                    "symbol": "ETHUSDT",
                },
            },
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["total"] == 2
    rows_by_instance = {row["instance_id"]: row for row in result["positions"]}
    assert rows_by_instance["inst-btc"]["data_name"] == "BTCUSDT"
    assert rows_by_instance["inst-btc"]["market_value"] == 6100.0
    assert rows_by_instance["inst-eth"]["data_name"] == "ETH/USDT"
    assert rows_by_instance["inst-eth"]["market_value"] == 6200.0
    assert result["summary"]["gross_market_value"] == 12300.0


@pytest.mark.asyncio
async def test_portfolio_positions_value_raw_ib_gateway_rows():
    """Raw IB Web portfolio fields must be normalized before position valuation."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "account": "U123456",
                    "symbol": "AAPL",
                    "secType": "STK",
                    "position": 10,
                    "avgCost": 150.0,
                    "marketPrice": 155.0,
                    "marketValue": 1550.0,
                    "unrealizedPNL": 50.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "AAPL" in symbols
            return {"AAPL": {"source": "ib_gateway", "contract_size": 1, "commission_rate": 0.0}}

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "AAPL",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "AAPL"
    assert row["size"] == 10.0
    assert row["price"] == 150.0
    assert row["latest_price"] == 155.0
    assert row["market_value"] == 1550.0
    assert row["position_pnl"] == 50.0
    assert result["summary"]["total_pnl"] == 50.0


@pytest.mark.asyncio
async def test_portfolio_positions_value_ib_client_portal_field_names():
    """IBKR Client Portal positions use description and mkt*/Pnl fields."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "acctId": "U1234567",
                    "description": "SPY",
                    "assetClass": "STK",
                    "position": 5.0,
                    "avgPrice": 434.93,
                    "mktPrice": 471.16000365,
                    "mktValue": 2355.8,
                    "unrealizedPnl": 181.15,
                    "realizedPnl": 0.0,
                    "currency": "USD",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "SPY" in symbols
            return {"SPY": {"source": "ib_gateway", "contract_size": 1, "commission_rate": 0.0}}

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "SPY",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["total"] == 1
    row = result["positions"][0]
    assert row["data_name"] == "SPY"
    assert row["size"] == 5.0
    assert row["price"] == pytest.approx(434.93)
    assert row["latest_price"] == pytest.approx(471.16000365)
    assert row["market_value"] == pytest.approx(2355.8)
    assert row["position_pnl"] == pytest.approx(181.15)
    assert result["summary"]["total_pnl"] == pytest.approx(181.15)


@pytest.mark.asyncio
async def test_portfolio_positions_preserve_gateway_market_value_when_multiplier_missing():
    """Gateway marketValue must protect exposure when contract specs are incomplete."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "account": "U123456",
                    "symbol": "ES",
                    "secType": "FUT",
                    "position": 1,
                    "avgCost": 5000.0,
                    "marketPrice": 5010.0,
                    "marketValue": 250500.0,
                    "unrealizedPNL": 500.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "ES" in symbols
            return {"ES": {"source": "ib_gateway", "commission_rate": 0.0001}}

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "ES",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "ES"
    assert row["market_value"] == pytest.approx(250500.0)
    assert row["signed_market_value"] == pytest.approx(250500.0)
    assert row["gross_pnl"] == pytest.approx(500.0)
    assert row["commission"] == pytest.approx(25.0)
    assert row["position_pnl"] == pytest.approx(475.0)
    assert result["summary"]["gross_market_value"] == pytest.approx(250500.0)
    assert result["summary"]["total_pnl"] == pytest.approx(475.0)


@pytest.mark.asyncio
async def test_portfolio_positions_estimate_fee_when_gateway_returns_gross_pnl_without_fee():
    """Gross exchange PnL must not be treated as net PnL when commission is absent."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "PositionCost": 1_500_000.0,
                    "SettlementPrice": 5010.0,
                    "PositionProfit": 3000.0,
                    "UseMargin": 150300.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["gross_pnl"] == 3000.0
    assert row["commission"] == pytest.approx(34.5)
    assert row["position_pnl"] == pytest.approx(2965.5)
    assert result["summary"]["total_pnl"] == pytest.approx(2965.5)


@pytest.mark.asyncio
async def test_portfolio_positions_use_symbol_scoped_trade_fee_without_trade_symbol():
    """Symbol-scoped trade queries may return rows without a symbol field."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "Price": 5000.0,
                    "LastPrice": 5010.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "VolumeMultiple": 300,
                    "LongMarginRatioByMoney": 0.1,
                    "OpenRatioByMoney": 0.23,
                    "quote_asset": "CNY",
                    "fee_currency": "CNY",
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "IF2609"
            assert limit == 500
            return [
                {
                    "direction": "buy",
                    "TradeVolume": 1,
                    "Price": 5000.0,
                    "Commission": 34.5,
                }
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["gross_pnl"] == pytest.approx(3000.0)
    assert row["commission"] == pytest.approx(34.5)
    assert row["commission_source"] == "gateway.trades"
    assert row["position_pnl"] == pytest.approx(2965.5)
    assert result["summary"]["total_pnl"] == pytest.approx(2965.5)


@pytest.mark.asyncio
async def test_portfolio_positions_exclude_future_exit_fee_from_open_pnl():
    """Gateway exit fee metadata must not be pre-deducted from open position PnL."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 2,
                    "PositionCost": 3_000_000.0,
                    "SettlementPrice": 5001.0,
                    "PositionProfit": 600.0,
                    "today_volume": 1,
                    "history_volume": 1,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "VolumeMultiple": 300,
                    "OpenRatioByMoney": 0.23,
                    "CloseRatioByMoney": 0.3,
                    "CloseTodayRatioByMoney": 3.45,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["gross_pnl"] == 600.0
    assert row["commission"] == pytest.approx(69.0)
    assert row["position_pnl"] == pytest.approx(531.0)
    assert result["summary"]["total_pnl"] == pytest.approx(531.0)


@pytest.mark.asyncio
async def test_portfolio_positions_recalculate_generic_gateway_position_pnl():
    """Generic gateway position_pnl must be recalculated with asset specs."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "Price": 5000.0,
                    "LastPrice": 5010.0,
                    "position_pnl": 10.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "multiplier": 300,
                    "commission_rate": 0.000023,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["gross_pnl"] == 3000.0
    assert row["commission"] == pytest.approx(34.5)
    assert row["position_pnl"] == pytest.approx(2965.5)
    assert result["summary"]["total_pnl"] == pytest.approx(2965.5)


@pytest.mark.asyncio
async def test_portfolio_positions_handle_raw_ctp_short_direction():
    """Raw CTP PosiDirection='3' rows are short positions in portfolio risk."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "3",
                    "Position": 1,
                    "PositionCost": 1_500_000.0,
                    "SettlementPrice": 4990.0,
                    "PositionProfit": 3000.0,
                    "Commission": 34.5,
                    "UseMargin": 149700.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["direction"] == "short"
    assert row["size"] == -1.0
    assert row["market_value"] == 1_497_000.0
    assert row["signed_market_value"] == -1_497_000.0
    assert row["position_pnl"] == 2965.5
    assert row["gross_pnl"] == 3000.0
    assert row["commission"] == 34.5
    assert result["summary"]["short_count"] == 1
    assert result["summary"]["net_market_value"] == -1_497_000.0
    assert result["summary"]["total_pnl"] == 2965.5


@pytest.mark.asyncio
async def test_portfolio_positions_prefer_gateway_latest_price_over_ctp_settlement():
    """CTP settlement price is only a fallback when a gateway latest price is unavailable."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "PositionCost": 1_500_000.0,
                    "SettlementPrice": 4990.0,
                    "UseMargin": 180_000.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "multiplier": 300,
                    "margin_rate": 0.12,
                    "commission_rate": 0.0,
                    "current_price": 5010.0,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["latest_price"] == 5010.0
    assert row["market_value"] == 1_503_000.0
    assert row["position_pnl"] == 3_000.0
    assert row["margin_value"] == 180_000.0


@pytest.mark.asyncio
async def test_portfolio_positions_use_mt5_gateway_latest_price_from_asset_spec():
    """MT5 live positions should use gateway cached latest price when the row lacks it."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.02,
                    "price": 2330.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "mt5_gateway",
                    "contract_size": 100,
                    "margin_initial": 1950.0,
                    "current_price": 2331.0,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["latest_price"] == 2331.0
    assert row["market_value"] == 4662.0
    assert row["position_pnl"] == 2.0
    assert row["margin_value"] == 39.0


@pytest.mark.asyncio
async def test_portfolio_positions_use_local_asset_spec_when_gateway_specs_empty():
    """Portfolio risk should use local contract metadata when the gateway omits it."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.02,
                    "price": 2330.0,
                    "current_price": 2331.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {}

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["asset_spec_source"] == "local_mt5_defaults"
    assert row["multiplier"] == 100.0
    assert row["latest_price"] == 2331.0
    assert row["market_value"] == 4662.0
    assert row["position_pnl"] == 2.0


@pytest.mark.asyncio
async def test_portfolio_positions_use_mt5_position_current_price():
    """MT5 position rows can carry price_current without relying on tick cache."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.02,
                    "price": 2330.0,
                    "current_price": 2331.0,
                    "profit": 2.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "mt5_gateway",
                    "contract_size": 100,
                    "margin_initial": 1950.0,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["latest_price"] == 2331.0
    assert row["market_value"] == 4662.0
    assert row["position_pnl"] == 2.0


@pytest.mark.asyncio
async def test_portfolio_positions_handle_binance_gateway_position_fields():
    """Binance direct positions use positionAmt/markPrice/unRealizedProfit fields."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "position_symbol_name": "BTCUSDT",
                    "position_volume": "0.02",
                    "position_side": "BOTH",
                    "avg_price": "60000",
                    "mark_price": "61000",
                    "position_unrealized_pnl": "20",
                    "leverage": "10",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "source": "binance_gateway",
                    "contract_size": 1,
                    "commission_rate": 0.0004,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["data_name"] == "BTCUSDT"
    assert row["size"] == 0.02
    assert row["latest_price"] == 61000.0
    assert row["market_value"] == 1220.0
    assert row["margin_rate"] == 0.1
    assert row["margin_value"] == 122.0
    assert row["gross_pnl"] == 20.0
    assert row["commission"] == pytest.approx(0.48)
    assert row["position_pnl"] == pytest.approx(19.52)
    assert result["summary"]["long_count"] == 1


@pytest.mark.asyncio
async def test_portfolio_positions_use_gateway_trades_for_current_open_commission():
    """Replay gateway fills to use real open-position commission when possible."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "position_symbol_name": "BTCUSDT",
                    "positionAmt": "0.02",
                    "positionSide": "BOTH",
                    "entryPrice": "60000",
                    "markPrice": "61000",
                    "unRealizedProfit": "20",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "source": "binance_gateway",
                    "contract_size": 1,
                    "commission_rate": 0.0004,
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "BTCUSDT"
            assert limit == 500
            return [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "qty": "0.02",
                    "commission": "0.5",
                    "time": 1710000000000,
                }
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["gross_pnl"] == pytest.approx(20.0)
    assert row["commission"] == pytest.approx(0.5)
    assert row["position_pnl"] == pytest.approx(19.5)
    assert result["summary"]["total_pnl"] == pytest.approx(19.5)


@pytest.mark.asyncio
async def test_portfolio_positions_value_gateway_long_short_aliases_with_real_fee():
    """Gateway long_position/short_position aliases should still use specs and real fees."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "long_position": "2",
                    "short_position": "0",
                    "avg_price": "5000",
                    "last_price": "5001",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "VolumeMultiple": 300,
                    "LongMarginRatioByMoney": 0.1,
                    "OpenRatioByMoney": 0.23,
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "IF2609"
            assert limit == 500
            return [
                {
                    "InstrumentID": "IF2609",
                    "direction": "buy",
                    "TradeVolume": 2,
                    "Commission": 46.0,
                    "trade_time": 1710000000000,
                }
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)
    row = result["positions"][0]

    assert row["data_name"] == "IF2609"
    assert row["size"] == pytest.approx(2.0)
    assert row["market_value"] == pytest.approx(3_000_600.0)
    assert row["margin_value"] == pytest.approx(300_060.0)
    assert row["multiplier"] == pytest.approx(300.0)
    assert row["commission"] == pytest.approx(46.0)
    assert row["gross_pnl"] == pytest.approx(600.0)
    assert row["position_pnl"] == pytest.approx(554.0)
    assert row["asset_spec_source"] == "ctp_gateway"
    assert result["summary"]["total_pnl"] == pytest.approx(554.0)


@pytest.mark.asyncio
async def test_portfolio_positions_recalculate_gateway_exchange_pnl_with_contract_multiplier():
    """Gateway gross PnL fields must not bypass contract multiplier valuation."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "long_position": "2",
                    "short_position": "0",
                    "avg_price": "5000",
                    "last_price": "5001",
                    "PositionProfit": "2",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "VolumeMultiple": 300,
                    "LongMarginRatioByMoney": 0.1,
                    "OpenRatioByMoney": 0.23,
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "IF2609"
            assert limit == 500
            return [
                {
                    "InstrumentID": "IF2609",
                    "direction": "buy",
                    "TradeVolume": 2,
                    "Commission": 46.0,
                    "trade_time": 1710000000000,
                }
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)
    row = result["positions"][0]

    assert row["market_value"] == pytest.approx(3_000_600.0)
    assert row["margin_value"] == pytest.approx(300_060.0)
    assert row["multiplier"] == pytest.approx(300.0)
    assert row["commission"] == pytest.approx(46.0)
    assert row["gross_pnl"] == pytest.approx(600.0)
    assert row["position_pnl"] == pytest.approx(554.0)
    assert result["summary"]["total_pnl"] == pytest.approx(554.0)


@pytest.mark.asyncio
async def test_portfolio_positions_hide_gateway_long_short_zero_aliases():
    """Gateway rows with explicit zero long/short positions must not display."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "long_position": "0",
                    "short_position": "0",
                    "avg_price": "5000",
                    "last_price": "5001",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            return {"IF2609": {"source": "ctp_gateway", "VolumeMultiple": 300}}

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["positions"] == []
    assert result["summary"] == _EMPTY_POSITION_SUMMARY


@pytest.mark.asyncio
async def test_portfolio_positions_recalculate_unscaled_gateway_unrealized_profit():
    """Raw gateway unrealizedProfit can be a price delta and must use contract specs."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "PosiDirection": "2",
                    "Position": 1,
                    "Price": 5000.0,
                    "LastPrice": 5010.0,
                    "unrealizedProfit": 10.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "ctp_gateway",
                    "VolumeMultiple": 300,
                    "OpenRatioByMoney": 0.23,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["multiplier"] == pytest.approx(300.0)
    assert row["market_value"] == pytest.approx(1_503_000.0)
    assert row["gross_pnl"] == pytest.approx(3000.0)
    assert row["commission"] == pytest.approx(34.5)
    assert row["position_pnl"] == pytest.approx(2965.5)
    assert result["summary"]["total_pnl"] == pytest.approx(2965.5)


@pytest.mark.asyncio
async def test_portfolio_positions_match_gateway_trade_fees_by_position_side():
    """Hedge-mode long/short positions must not net each other's open fills."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "position_symbol_name": "BTCUSDT",
                    "positionAmt": "0.01",
                    "positionSide": "LONG",
                    "entryPrice": "60000",
                    "markPrice": "61000",
                    "unRealizedProfit": "10",
                },
                {
                    "position_symbol_name": "BTCUSDT",
                    "positionAmt": "0.02",
                    "positionSide": "SHORT",
                    "entryPrice": "62000",
                    "markPrice": "61000",
                    "unRealizedProfit": "20",
                },
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "source": "binance_gateway",
                    "contract_size": 1,
                    "commission_rate": 0.0004,
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "BTCUSDT"
            assert limit == 500
            return [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "positionSide": "LONG",
                    "qty": "0.01",
                    "commission": "0.5",
                    "time": 1710000000000,
                },
                {
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "positionSide": "SHORT",
                    "qty": "0.02",
                    "commission": "1.25",
                    "time": 1710000001000,
                },
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)
    by_direction = {row["direction"]: row for row in result["positions"]}

    assert by_direction["long"]["commission"] == pytest.approx(0.5)
    assert by_direction["long"]["position_pnl"] == pytest.approx(9.5)
    assert by_direction["short"]["commission"] == pytest.approx(1.25)
    assert by_direction["short"]["position_pnl"] == pytest.approx(18.75)
    assert result["summary"]["long_count"] == 1
    assert result["summary"]["short_count"] == 1
    assert result["summary"]["total_pnl"] == pytest.approx(28.25)


@pytest.mark.asyncio
async def test_portfolio_positions_match_gateway_trade_fees_by_position_idx():
    """Bybit hedge-mode fees must bind to the matching positionIdx leg."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "symbol": "BTCUSDT",
                    "positionIdx": "1",
                    "size": "0.01",
                    "avgPrice": "60000",
                    "markPrice": "61000",
                    "unrealisedPnl": "10",
                },
                {
                    "symbol": "BTCUSDT",
                    "positionIdx": "2",
                    "size": "0.02",
                    "avgPrice": "62000",
                    "markPrice": "61000",
                    "unrealisedPnl": "20",
                },
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "source": "bybit_gateway",
                    "contract_size": 1,
                    "commission_rate": 0.0004,
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "BTCUSDT"
            assert limit == 500
            return [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "positionIdx": "1",
                    "execQty": "0.01",
                    "execFee": "0.5",
                    "execTime": "1710000000000",
                },
                {
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "positionIdx": "2",
                    "execQty": "0.02",
                    "execFee": "1.25",
                    "execTime": "1710000001000",
                },
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)
    by_direction = {row["direction"]: row for row in result["positions"]}

    assert by_direction["long"]["commission"] == pytest.approx(0.5)
    assert by_direction["long"]["position_pnl"] == pytest.approx(9.5)
    assert by_direction["short"]["commission"] == pytest.approx(1.25)
    assert by_direction["short"]["position_pnl"] == pytest.approx(18.75)
    assert result["summary"]["total_pnl"] == pytest.approx(28.25)


@pytest.mark.asyncio
async def test_portfolio_positions_warn_when_gateway_trade_fee_currency_differs():
    """Trade fees paid in another currency must not be treated as quote-currency PnL."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "position_symbol_name": "BTCUSDT",
                    "positionAmt": "0.02",
                    "entryPrice": "60000",
                    "markPrice": "61000",
                    "unRealizedProfit": "20",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            return {
                "BTCUSDT": {
                    "source": "binance_gateway",
                    "contract_size": 1,
                    "quote_asset": "USDT",
                    "commission_rate": 0.0004,
                }
            }

        def query_instance_gateway_trades(self, instance_id, *, symbol=None, limit=100):
            assert instance_id == "inst-a"
            assert symbol == "BTCUSDT"
            return [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "qty": "0.02",
                    "commission": "0.001",
                    "commissionAsset": "BNB",
                    "time": 1710000000000,
                }
            ]

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["commission"] == pytest.approx(0.48)
    assert row["position_pnl"] == pytest.approx(19.52)
    assert any("手续费币种" in item for item in row["valuation_warnings"])
    assert row["valuation_status"] == "estimated"


@pytest.mark.asyncio
async def test_portfolio_positions_use_gateway_fee_cost_dict_as_real_commission():
    """Exchange fee objects must be treated as exact commission in portfolio risk."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "position_symbol_name": "BTCUSDT",
                    "position_volume": "0.02",
                    "position_side": "BOTH",
                    "avg_price": "60000",
                    "mark_price": "61000",
                    "position_unrealized_pnl": "20",
                    "fee": {"cost": "0.12", "currency": "USDT"},
                    "leverage": "10",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "source": "binance_gateway",
                    "contract_size": 1,
                    "commission_rate": 0.0004,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["commission"] == pytest.approx(0.12)
    assert row["position_pnl"] == pytest.approx(19.88)
    assert result["summary"]["total_pnl"] == pytest.approx(19.88)


@pytest.mark.asyncio
async def test_portfolio_positions_warn_when_position_fee_dict_currency_differs():
    """Position fee objects in non-valuation currency must fall back to estimated fees."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "position_symbol_name": "BTCUSDT",
                    "positionAmt": "0.02",
                    "entryPrice": "60000",
                    "markPrice": "61000",
                    "unRealizedProfit": "20",
                    "fee": {"cost": "0.001", "currency": "BNB"},
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSDT" in symbols
            return {
                "BTCUSDT": {
                    "source": "binance_gateway",
                    "contract_size": 1,
                    "quote_asset": "USDT",
                    "commission_rate": 0.0004,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["commission"] == pytest.approx(0.48)
    assert row["position_pnl"] == pytest.approx(19.52)
    assert any("手续费币种" in item for item in row["valuation_warnings"])
    assert row["valuation_status"] == "estimated"
    assert result["summary"]["total_pnl"] == pytest.approx(19.52)


@pytest.mark.asyncio
async def test_portfolio_positions_preserve_okx_positive_fee_as_rebate():
    """OKX positive position fee means rebate, not an extra portfolio cost."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "BTC-USDT-SWAP",
                    "position_side": "long",
                    "position_volume": 1,
                    "avg_price": 60000.0,
                    "mark_price": 60005.0,
                    "position_unrealized_pnl": 5.0,
                    "position_fee": 0.25,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTC-USDT-SWAP" in symbols
            return {
                "BTC-USDT-SWAP": {
                    "source": "okx_gateway",
                    "contract_size": 1,
                    "commission_rate": 0.0004,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT-SWAP",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["commission"] == pytest.approx(-0.25)
    assert row["position_pnl"] == pytest.approx(5.25)
    assert result["summary"]["total_pnl"] == pytest.approx(5.25)


@pytest.mark.asyncio
async def test_portfolio_positions_prefer_okx_upl_over_position_pnl():
    """OKX open-position PnL should use upl, not the position pnl accumulator."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instId": "BTC-USDT-SWAP",
                    "posSide": "long",
                    "pos": "2",
                    "avgPx": "60000",
                    "markPx": "60100",
                    "upl": "2.0",
                    "pnl": "999.0",
                    "fee": "-0.12",
                    "source": "okx_gateway",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTC-USDT-SWAP" in symbols
            return {
                "BTC-USDT-SWAP": {
                    "source": "okx_gateway",
                    "instType": "SWAP",
                    "ctVal": "0.01",
                    "settleCcy": "USDT",
                    "commission_rate": 0.0004,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTC-USDT-SWAP",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["gross_pnl"] == pytest.approx(2.0)
    assert row["commission"] == pytest.approx(0.12)
    assert row["position_pnl"] == pytest.approx(1.88)
    assert result["summary"]["total_pnl"] == pytest.approx(1.88)


@pytest.mark.asyncio
async def test_portfolio_positions_use_explicit_inverse_flag_without_cttype():
    """Portfolio risk should not require ctType when the gateway says inverse=true."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "symbol": "BTCUSD",
                    "posSide": "long",
                    "pos": 2,
                    "avgPx": 50000.0,
                    "markPx": 55000.0,
                    "source": "okx_gateway",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSD" in symbols
            return {
                "BTCUSD": {
                    "source": "gateway.get_symbol_info",
                    "instType": "SWAP",
                    "inverse": True,
                    "multiplier": 1,
                    "ctVal": 100,
                    "ctMult": 1,
                    "margin_rate": 0.1,
                    "taker_commission_rate": 0.0005,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTCUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["multiplier"] == pytest.approx(100.0)
    assert row["market_value"] == pytest.approx(200.0)
    assert row["margin_value"] == pytest.approx(20.0)
    assert row["gross_pnl"] == pytest.approx(20.0)
    assert row["commission"] == pytest.approx(0.1)
    assert row["position_pnl"] == pytest.approx(19.9)
    assert result["summary"]["gross_market_value"] == pytest.approx(200.0)
    assert result["summary"]["total_pnl"] == pytest.approx(19.9)


@pytest.mark.asyncio
async def test_portfolio_positions_convert_inverse_exchange_upl_to_quote_value():
    """Inverse exchange UPL is settled in base coin and must be valued in quote currency."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "symbol": "BTCUSD",
                    "side": "Buy",
                    "size": "2",
                    "avgPrice": "50000",
                    "markPrice": "55000",
                    "unrealisedPnl": "0.0003636363636363636",
                    "settleCoin": "BTC",
                    "category": "inverse",
                    "source": "bybit_gateway",
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "BTCUSD" in symbols
            return {
                "BTCUSD": {
                    "source": "gateway.get_symbol_info",
                    "instType": "SWAP",
                    "contractType": "InversePerpetual",
                    "ctVal": 100,
                    "ctValCcy": "USD",
                    "baseCcy": "BTC",
                    "quoteCcy": "USD",
                    "settleCcy": "BTC",
                    "taker_commission_rate": 0.0005,
                    "margin_rate": 0.1,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "BTCUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["market_value"] == pytest.approx(200.0)
    assert row["gross_pnl"] == pytest.approx(20.0)
    assert row["commission"] == pytest.approx(0.1)
    assert row["position_pnl"] == pytest.approx(19.9)
    assert result["summary"]["total_pnl"] == pytest.approx(19.9)


@pytest.mark.asyncio
async def test_portfolio_positions_handle_raw_mt5_numeric_short_type():
    """Raw MT5 type=1 positions are shorts, not long exposure."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "type": 1,
                    "volume": 0.02,
                    "price": 2330.0,
                    "current_price": 2329.0,
                    "profit": 2.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "mt5_gateway",
                    "contract_size": 100,
                    "margin_initial": 1950.0,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["direction"] == "short"
    assert row["size"] == -0.02
    assert row["signed_market_value"] == -4658.0
    assert row["market_value"] == 4658.0
    assert row["gross_pnl"] == 2.0
    assert result["summary"]["short_count"] == 1
    assert result["summary"]["net_market_value"] == -4658.0


@pytest.mark.asyncio
async def test_portfolio_positions_estimate_mt5_fee_when_position_commission_missing():
    """MT5 missing commission must not be treated as confirmed zero-fee PnL."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.02,
                    "price": 2330.0,
                    "current_price": 2331.0,
                    "profit": 2.0,
                    "swap": -0.1,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "mt5_gateway",
                    "contract_size": 100,
                    "margin_initial": 1950.0,
                    "commission_rate": 0.001,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["commission"] == pytest.approx(4.66)
    assert row["gross_pnl"] == 2.0
    assert row["position_pnl"] == pytest.approx(-2.76)
    assert row["valuation_status"] == "estimated"
    assert any("按资产费率估算" in item for item in row["valuation_warnings"])
    assert result["summary"]["total_pnl"] == pytest.approx(-2.76)


@pytest.mark.asyncio
async def test_portfolio_positions_estimate_fee_when_gateway_commission_is_zero():
    """Gateway position commission=0 should not hide configured exchange fees."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.02,
                    "price": 2330.0,
                    "current_price": 2331.0,
                    "profit": 2.0,
                    "swap": -0.1,
                    "commission": 0.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "mt5_gateway",
                    "contract_size": 100,
                    "margin_initial": 1950.0,
                    "commission_rate": 0.001,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["commission"] == pytest.approx(4.66)
    assert row["position_pnl"] == pytest.approx(-2.76)
    assert row["valuation_status"] == "estimated"
    assert any("按资产费率估算" in item for item in row["valuation_warnings"])
    assert result["summary"]["total_pnl"] == pytest.approx(-2.76)


@pytest.mark.asyncio
async def test_portfolio_positions_use_mt5_margin_initial_per_lot():
    """MT5 margin_initial is fixed per lot, not a full-notional margin rate."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.02,
                    "price": 2330.0,
                    "last_price": 2331.0,
                    "profit": 2.0,
                    "commission": 0.0,
                    "swap": 0.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "mt5_gateway",
                    "contract_size": 100,
                    "margin_initial": 1950.0,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "XAUUSD",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    row = result["positions"][0]
    assert row["position_source"] == "gateway"
    assert row["asset_spec_source"] == "mt5_gateway"
    assert row["valuation_status"] == "confirmed"
    assert row["valuation_warnings"] == []
    assert row["market_value"] == pytest.approx(4662.0)
    assert row["margin_value"] == pytest.approx(39.0)
    assert row["position_pnl"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_portfolio_positions_hide_explicit_zero_gateway_position():
    """A gateway row with an explicit zero size must not revive stale side fields."""
    from app.api.portfolio_api import get_portfolio_positions

    class GatewayManager(_MockManager):
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-a"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-a"
            return [
                {
                    "InstrumentID": "IF2609",
                    "Position": 0,
                    "long_position": 1,
                    "Price": 5000,
                    "LastPrice": 5010,
                    "PositionProfit": 10,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-a"
            assert "IF2609" in symbols
            return {
                "IF2609": {
                    "source": "gateway.query_instrument",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "open_commission_rate": 0.000023,
                }
            }

    mgr = GatewayManager(
        [
            {
                **_INSTANCE_A,
                "params": {
                    "trading_mode": "live",
                    "symbol": "IF2609",
                },
            }
        ]
    )

    result = await get_portfolio_positions(current_user=_USER, mgr=mgr)

    assert result["total"] == 0
    assert result["positions"] == []
    assert result["summary"] == _EMPTY_POSITION_SUMMARY


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
        "dt\tvalue\tcash\n2026-06-24 00:00:00\t100000\t99000\n2026-06-24 00:01:00\t100200\t99100\n",
        encoding="utf-8",
    )
    (log_dir / "position.log").write_text(
        "dt\tdata_name\tsize\tprice\n2026-06-24 00:01:00\tIF2609\t1\t5000\n",
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
    assert trades["trades"][0]["strategy_name"] == ("期货模拟工作区 / CTP压测01-短周期均线-1m")
