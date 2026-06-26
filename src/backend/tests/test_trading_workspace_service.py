import json
from types import SimpleNamespace

import pytest
import yaml

from app.services import trading_workspace_service as trading_workspace_service_module
from app.services import workspace_unit_runtime
from app.services.position_valuation import PositionSpec, contract_spec_for, value_position
from app.services.trading_asset_info_service import (
    load_runtime_config,
    normalize_asset_spec,
    normalize_gateway_position,
    persist_asset_specs,
    query_gateway_asset_spec,
    query_gateway_last_price,
    signed_gateway_size,
    symbol_aliases,
    symbols_for_instance,
)
from app.services.trading_workspace_service import TradingWorkspaceService


def _make_strategy_template(tmp_path, strategy_id: str, module_basename: str):
    """Create a self-contained strategy template dir.

    The runtime sync copies every ``*.py`` from the template dir resolved via
    ``get_strategy_dir``. The real templates live under the gitignored
    ``src/strategies/`` tree, so tests must not depend on them being present;
    we build a minimal template on disk and point ``get_strategy_dir`` at it.
    """
    template_dir = tmp_path / "templates" / strategy_id.replace("/", "__")
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "run.py").write_text("# runtime entrypoint\n", encoding="utf-8")
    (template_dir / f"{module_basename}.py").write_text(
        "import backtrader as bt\n\n\nclass S(bt.Strategy):\n    pass\n",
        encoding="utf-8",
    )
    return template_dir


def _make_basic_trading_unit(strategy_id: str = "simulate/gateway_dual_ma"):
    return SimpleNamespace(
        workspace_id="ws-refresh",
        id="unit-refresh",
        group_name="均线金叉",
        strategy_id=strategy_id,
        strategy_name="Refresh Runner",
        symbol="EURUSD",
        symbol_name="EURUSD",
        timeframe="1m",
        timeframe_n=1,
        category="forex",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
    )


def test_build_instance_params_keeps_explicit_gateway_for_paper_units():
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        group_name="均线金叉",
        strategy_name="Paper MA",
        params={"fast_period": 5},
        symbol="AAPL",
        symbol_name="Apple",
        timeframe="1m",
        timeframe_n=1,
        category="stock",
        data_config={},
        unit_settings={},
        trading_mode="paper",
        gateway_config={
            "preset_id": "ib_web_stock_gateway",
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "gateway",
                    "exchange_type": "IB_WEB",
                    "asset_type": "STK",
                    "account_id": "DU123456",
                },
                "ib_web": {
                    "account_id": "DU123456",
                    "base_url": "https://localhost:5000",
                },
            },
        },
    )

    params = TradingWorkspaceService._build_instance_params(unit)

    assert params["trading_mode"] == "paper"
    assert params["gateway"]["exchange_type"] == "IB_WEB"
    assert params["ib_web"]["account_id"] == "DU123456"


def test_default_snapshot_and_normalized_trade_rows_expose_trades():
    unit = SimpleNamespace(
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="IF2609",
        symbol_name="沪深300",
        strategy_name="CTP Demo",
    )

    snapshot = TradingWorkspaceService.default_snapshot(unit=unit)
    rows = TradingWorkspaceService._normalize_trade_rows(
        [
            {
                "ref": 7,
                "datetime": "2026-06-22",
                "dtopen": "2026-06-22 09:31:00",
                "dtclose": "2026-06-22 09:42:00",
                "data_name": "IF2609",
                "direction": "sell",
                "size": -2,
                "price": 3910.1234,
                "value": 7820.246,
                "commission": 3.4567,
                "pnl": 20,
                "pnlcomm": 18.25,
                "barlen": "5",
            }
        ],
        unit=unit,
    )

    assert snapshot["trades"] == []
    assert rows == [
        {
            "id": "7",
            "datetime": "2026-06-22",
            "dtopen": "2026-06-22 09:31:00",
            "dtclose": "2026-06-22 09:42:00",
            "data_name": "IF2609",
            "direction": "short",
            "size": 2.0,
            "price": 3910.1234,
            "value": 7820.25,
            "commission": 3.4567,
            "pnl": 20.0,
            "pnlcomm": 18.25,
            "barlen": 5,
        }
    ]


def test_build_snapshot_filters_flat_positions_and_values_futures(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="paper",
        gateway_config={},
        symbol="rb2610",
        symbol_name="螺纹钢",
        strategy_name="RB Trend",
        unit_settings={"multiplier": 10, "margin": 0.1, "commission": 0.0002},
        params={},
        data_config={},
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_position_log",
        lambda _log_dir: [
            {"data_name": "rb2610", "size": 0, "price": 3127.0, "current_price": 3126.0},
            {
                "data_name": "rb2610",
                "size": 1,
                "price": 3127.0,
                "current_price": 3126.0,
                "commission": 2.5,
            },
        ],
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_current_position",
        lambda _log_dir: [],
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert len(snapshot["positions"]) == 1
    assert snapshot["long_position"] == 1.0
    assert snapshot["short_position"] == 0.0
    assert snapshot["long_market_value"] == 31260.0
    assert snapshot["position_pnl"] == -12.5
    assert snapshot["positions"][0]["market_value"] == 31260.0
    assert snapshot["positions"][0]["margin_value"] == 3126.0
    assert snapshot["positions"][0]["multiplier"] == 10.0
    assert snapshot["positions"][0]["commission"] == 2.5


def test_build_snapshot_prefers_live_gateway_positions(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="XAUUSD",
        symbol_name="黄金/美元",
        strategy_name="MT5 Gold",
        unit_settings={},
        params={},
        data_config={},
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_position_log",
        lambda _log_dir: [
            {"data_name": "XAUUSD", "size": 2, "price": 2000.0, "current_price": 2000.0}
        ],
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_current_position",
        lambda _log_dir: [],
    )

    class FakeManager:
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-1"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-1"
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
            assert instance_id == "inst-1"
            assert "XAUUSD" in symbols
            return {"XAUUSD": {"contract_size": 100, "margin_rate": 0.02}}

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert len(snapshot["positions"]) == 1
    assert snapshot["positions"][0]["size"] == 0.1
    assert snapshot["long_position"] == 0.1
    assert snapshot["long_market_value"] == 23100.0
    assert snapshot["positions"][0]["margin_value"] == 462.0
    assert snapshot["positions"][0]["multiplier"] == 100.0
    assert snapshot["positions"][0]["commission"] == 1.0
    assert snapshot["positions"][0]["position_source"] == "gateway"
    assert snapshot["positions"][0]["asset_spec_source"] is None
    assert snapshot["positions"][0]["valuation_status"] == "confirmed"
    assert snapshot["position_source"] == "gateway"
    assert snapshot["valuation_status"] == "confirmed"
    assert snapshot["position_pnl"] == 98.5


def test_build_snapshot_uses_gateway_asset_spec_fee_for_position_pnl(monkeypatch, tmp_path):
    """Gateway asset specs attached to current rows must feed workspace PnL."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="XAUUSD",
        symbol_name="黄金/美元",
        strategy_name="MT5 Gold",
        unit_settings={},
        params={},
        data_config={},
    )

    class FakeManager:
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-1"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-1"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.1,
                    "price_open": 2300.0,
                    "last_price": 2310.0,
                    "profit": 100.0,
                }
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-1"
            assert "XAUUSD" in symbols
            return {
                "XAUUSD": {
                    "source": "gateway.get_symbol_info",
                    "contract_size": 100,
                    "margin_rate": 0.02,
                    "commission_rate": 0.001,
                }
            }

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert snapshot["positions"][0]["commission"] == pytest.approx(23.0)
    assert snapshot["positions"][0]["position_pnl"] == pytest.approx(77.0)
    assert snapshot["position_pnl"] == pytest.approx(77.0)
    assert snapshot["valuation_status"] == "estimated"
    assert any("按资产费率估算" in item for item in snapshot["valuation_warnings"])


def test_build_snapshot_filters_gateway_positions_to_unit_symbol(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="XAUUSD",
        symbol_name="黄金/美元",
        strategy_name="MT5 Gold",
        unit_settings={},
        params={},
        data_config={},
    )

    class FakeManager:
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-1"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-1"
            return [
                {
                    "instrument": "XAUUSD",
                    "direction": "buy",
                    "volume": 0.1,
                    "price_open": 2300.0,
                    "last_price": 2310.0,
                    "profit": 100.0,
                    "commission": -1.0,
                },
                {
                    "instrument": "EURUSD",
                    "direction": "buy",
                    "volume": 1.0,
                    "price_open": 1.08,
                    "last_price": 1.09,
                    "profit": 1000.0,
                    "commission": -2.0,
                },
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-1"
            assert "XAUUSD" in symbols
            assert "EURUSD" not in symbols
            return {
                "XAUUSD": {
                    "symbol": "XAUUSD",
                    "source": "gateway.get_symbol_info",
                    "contract_size": 100,
                    "margin_initial": 2000.0,
                }
            }

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert [row["data_name"] for row in snapshot["positions"]] == ["XAUUSD"]
    assert snapshot["long_position"] == pytest.approx(0.1)
    assert snapshot["long_market_value"] == pytest.approx(23_100.0)
    assert snapshot["position_pnl"] == pytest.approx(99.0)
    assert snapshot["asset_spec_source"] == "gateway.get_symbol_info"


def test_build_snapshot_matches_compact_exchange_symbols(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="BTC/USDT",
        symbol_name="BTC/USDT",
        strategy_name="Crypto Demo",
        unit_settings={},
        params={},
        data_config={},
    )

    class FakeManager:
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-1"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-1"
            return [
                {
                    "symbol": "BTCUSDT",
                    "direction": "long",
                    "volume": 0.25,
                    "price": 100.0,
                    "last_price": 110.0,
                    "profit": 2.5,
                    "commission": -0.01,
                },
                {
                    "symbol": "ETHUSDT",
                    "direction": "long",
                    "volume": 2.0,
                    "price": 2000.0,
                    "last_price": 2100.0,
                    "profit": 200.0,
                },
            ]

        def query_instance_asset_specs(self, instance_id, symbols):
            assert instance_id == "inst-1"
            assert "BTCUSDT" in symbols
            assert "ETHUSDT" not in symbols
            return {
                "BTC/USDT": {
                    "symbol": "BTC/USDT",
                    "source": "gateway.get_symbol_info",
                    "contract_size": 1,
                    "margin_rate": 0.5,
                }
            }

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert [row["data_name"] for row in snapshot["positions"]] == ["BTCUSDT"]
    assert snapshot["long_position"] == pytest.approx(0.25)
    assert snapshot["long_market_value"] == pytest.approx(27.5)
    assert snapshot["position_pnl"] == pytest.approx(2.49)
    assert snapshot["positions"][0]["margin_value"] == pytest.approx(13.75)
    assert snapshot["asset_spec_source"] == "gateway.get_symbol_info"


def test_build_snapshot_marks_live_gateway_fallback_as_estimated(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="IF2609",
        symbol_name="沪深300",
        strategy_name="CTP Demo",
        unit_settings={"multiplier": 300, "margin": 0.1},
        params={},
        data_config={},
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_position_log",
        lambda _log_dir: [
            {"data_name": "IF2609", "size": 1, "price": 4810.0, "current_price": 4820.0}
        ],
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_current_position",
        lambda _log_dir: [],
    )

    class FakeManager:
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-1"
            return False

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert snapshot["position_source"] == "log"
    assert snapshot["valuation_status"] == "estimated"
    assert snapshot["positions"][0]["position_source"] == "log"
    assert any("未能从交易所网关确认当前持仓" in item for item in snapshot["valuation_warnings"])


def test_build_snapshot_clears_stale_log_positions_when_gateway_is_flat(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        trading_instance_id="inst-1",
        trading_mode="live",
        gateway_config={},
        symbol="IF2609",
        symbol_name="沪深300",
        strategy_name="CTP Demo",
        unit_settings={"multiplier": 300, "margin": 0.1},
        params={},
        data_config={},
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_position_log",
        lambda _log_dir: [
            {"data_name": "IF2609", "size": 1, "price": 4810.0, "current_price": 4820.0}
        ],
    )
    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_current_position",
        lambda _log_dir: [],
    )

    class FakeManager:
        def has_instance_gateway(self, instance_id):
            assert instance_id == "inst-1"
            return True

        def query_instance_gateway_positions(self, instance_id):
            assert instance_id == "inst-1"
            return []

        def query_instance_asset_specs(self, instance_id, symbols):
            return {}

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {"id": "inst-1", "status": "running", "log_dir": str(log_dir)},
        full_log=False,
    )

    assert snapshot["positions"] == []
    assert snapshot["long_position"] == 0.0
    assert snapshot["short_position"] == 0.0
    assert snapshot["long_market_value"] == 0.0
    assert snapshot["position_pnl"] == 0.0
    assert snapshot["position_source"] == "gateway"
    assert snapshot["valuation_status"] == "confirmed"


def test_latest_position_rows_keeps_dual_side_and_flat_clears_stale():
    dual_side_rows = [
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
    flat_rows = [
        dual_side_rows[0],
        dual_side_rows[1],
        {
            "datetime": "2026-06-24 11:03:00",
            "data_name": "IF2609",
            "size": 0,
            "price": 0.0,
        },
    ]

    dual_result = TradingWorkspaceService._latest_position_rows(dual_side_rows)
    flat_result = TradingWorkspaceService._latest_position_rows(flat_rows)

    assert len(dual_result) == 2
    by_direction = {"long" if row["size"] > 0 else "short": row for row in dual_result}
    assert by_direction["long"]["price"] == 5020.0
    assert by_direction["short"]["price"] == 5010.0
    assert len(flat_result) == 1
    assert flat_result[0]["size"] == 0


def test_latest_position_rows_keeps_bybit_position_idx_dual_side_rows():
    """Bybit hedge logs use positive size plus positionIdx for long/short legs."""
    rows = [
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

    result = TradingWorkspaceService._latest_position_rows(rows)

    assert len(result) == 2
    by_idx = {str(row["positionIdx"]): row for row in result}
    assert by_idx["1"]["price"] == pytest.approx(60000.0)
    assert by_idx["2"]["price"] == pytest.approx(60100.0)


def test_position_log_row_direction_treats_bybit_position_idx_zero_as_one_way():
    """Bybit positionIdx=0 identifies one-way mode, not a flat position."""
    assert (
        TradingWorkspaceService._position_log_row_direction(
            {"data_name": "BTCUSDT", "positionIdx": "0", "size": 0.1},
            0.1,
        )
        == "long"
    )
    assert (
        TradingWorkspaceService._position_log_row_direction(
            {"data_name": "BTCUSDT", "positionIdx": "0", "size": -0.1},
            -0.1,
        )
        == "short"
    )


def test_latest_position_rows_directional_flat_keeps_opposite_side():
    rows = [
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

    result = TradingWorkspaceService._latest_position_rows(rows)

    nonflat = [row for row in result if abs(float(row.get("size") or 0.0)) > 0]
    flat = [row for row in result if abs(float(row.get("size") or 0.0)) == 0]
    assert len(nonflat) == 1
    assert nonflat[0]["direction"] == "short"
    assert nonflat[0]["price"] == 5010.0
    assert len(flat) == 1
    assert flat[0]["direction"] == "long"


def test_position_valuation_uses_workspace_fee_method():
    spec = contract_spec_for(
        "rb2610",
        {
            "multiplier": 10,
            "long_margin_rate": 10,
            "commission_method": "percent_10k",
            "open_commission_rate": 2,
        },
    )

    valued = value_position(
        {"data_name": "rb2610", "size": 1, "price": 3127.0, "current_price": 3126.0},
        spec=spec,
    )

    assert valued is not None
    assert valued.market_value == pytest.approx(31260.0)
    assert valued.margin_rate == pytest.approx(0.1)
    assert valued.margin_value == pytest.approx(3126.0)
    assert valued.commission == pytest.approx(6.254)
    assert round(valued.pnl, 2) == -16.25


def test_position_valuation_uses_normalized_local_futures_metadata():
    spec = normalize_asset_spec(
        {
            "REFERENCE_CODE": "IF2609",
            "CONTRACT_MULTIPLIER": 300,
            "MARGIN_BUY": 10,
            "COMMISSION_OPEN_RATIO": 0.23,
        },
        symbol="IF2609",
        source="local_futures_commission",
    )

    valued = value_position(
        {"data_name": "IF2609", "size": 1, "price": 5000.0, "current_price": 5001.0},
        spec=contract_spec_for("IF2609", {"contract_metadata": {"IF2609": spec}}),
    )

    assert valued is not None
    assert valued.multiplier == 300
    assert valued.margin_rate == pytest.approx(0.1)
    assert valued.gross_pnl == pytest.approx(300.0)
    assert valued.commission == pytest.approx(34.5)
    assert valued.pnl == pytest.approx(265.5)


def test_position_valuation_includes_close_today_fee_when_position_is_today():
    spec = normalize_asset_spec(
        {
            "InstrumentID": "IF2609",
            "VolumeMultiple": 300,
            "LongMarginRatioByMoney": 0.1,
            "OpenRatioByMoney": 0.23,
            "CloseRatioByMoney": 0.3,
            "CloseTodayRatioByMoney": 3.45,
        },
        symbol="IF2609",
        source="ctp_gateway",
    )

    contract_spec = contract_spec_for("IF2609", {"contract_metadata": {"IF2609": spec}})
    valued = value_position(
        {
            "data_name": "IF2609",
            "size": 1,
            "today_position": 1,
            "price": 5000.0,
            "current_price": 5001.0,
        },
        spec=contract_spec,
    )

    assert valued is not None
    assert contract_spec.close_today_commission_rate == pytest.approx(0.000345)
    assert valued.gross_pnl == pytest.approx(300.0)
    assert valued.commission == pytest.approx(552.1035)
    assert valued.pnl == pytest.approx(-252.1035)


def test_position_valuation_keeps_ctp_decimal_commission_rate():
    spec = normalize_asset_spec(
        {
            "InstrumentID": "IF2609",
            "VolumeMultiple": 300,
            "LongMarginRatioByMoney": 0.1,
            "OpenRatioByMoney": 0.000023,
        },
        symbol="IF2609",
        source="ctp_gateway",
    )

    contract_spec = contract_spec_for("IF2609", {"contract_metadata": {"IF2609": spec}})
    valued = value_position(
        {"data_name": "IF2609", "size": 1, "price": 5000.0, "current_price": 5001.0},
        spec=contract_spec,
    )

    assert contract_spec.commission_rate == pytest.approx(0.000023)
    assert valued is not None
    assert valued.commission == pytest.approx(34.5)


def test_position_valuation_uses_taker_rate_when_only_maker_taker_available():
    spec = normalize_asset_spec(
        {
            "symbol": "BTC-USDT-SWAP",
            "contract_size": 0.01,
            "taker_commission_rate": 0.00045,
            "maker_commission_rate": -0.0001,
        },
        symbol="BTC-USDT-SWAP",
        source="okx_get_fee",
    )

    contract_spec = contract_spec_for(
        "BTC-USDT-SWAP", {"contract_metadata": {"BTC-USDT-SWAP": spec}}
    )
    valued = value_position(
        {
            "data_name": "BTC-USDT-SWAP",
            "size": 2,
            "price": 60000.0,
            "current_price": 60100.0,
        },
        spec=contract_spec,
    )

    assert spec["maker_commission_rate"] == pytest.approx(-0.0001)
    assert spec["taker_commission_rate"] == pytest.approx(0.00045)
    assert contract_spec.commission_rate == pytest.approx(0.00045)
    assert valued is not None
    assert valued.multiplier == pytest.approx(0.01)
    assert valued.gross_pnl == pytest.approx(2.0)
    assert valued.commission == pytest.approx(1.0809)
    assert valued.pnl == pytest.approx(0.9191)


def test_position_valuation_uses_fee_cost_dict_as_real_commission():
    spec = normalize_asset_spec(
        {
            "symbol": "BTCUSDT",
            "contract_size": 1,
            "commission_rate": 0.01,
        },
        symbol="BTCUSDT",
        source="binance_gateway",
    )

    valued = value_position(
        {
            "data_name": "BTCUSDT",
            "size": 0.02,
            "price": 60000.0,
            "current_price": 61000.0,
            "gross_pnl": 20.0,
            "fee": {"cost": "0.12", "currency": "USDT"},
        },
        spec=contract_spec_for("BTCUSDT", {"contract_metadata": {"BTCUSDT": spec}}),
    )

    assert valued is not None
    assert valued.commission == pytest.approx(0.12)
    assert valued.pnl == pytest.approx(19.88)


def test_position_valuation_uses_bybit_exec_fee_v2_as_real_commission():
    spec = normalize_asset_spec(
        {
            "symbol": "BTCUSDT",
            "contract_size": 1,
            "commission_rate": 0.01,
        },
        symbol="BTCUSDT",
        source="bybit_gateway",
    )

    valued = value_position(
        {
            "data_name": "BTCUSDT",
            "size": 0.02,
            "price": 60000.0,
            "current_price": 61000.0,
            "gross_pnl": 20.0,
            "execFeeV2": "0.15",
            "feeCurrency": "USDT",
        },
        spec=contract_spec_for("BTCUSDT", {"contract_metadata": {"BTCUSDT": spec}}),
    )

    assert valued is not None
    assert valued.commission == pytest.approx(0.15)
    assert valued.pnl == pytest.approx(19.85)


def test_position_valuation_preserves_signed_internal_commission_rebate():
    valued = value_position(
        {
            "data_name": "BTC-USDT-SWAP",
            "size": 1,
            "price": 60000.0,
            "current_price": 60005.0,
            "gross_pnl": 5.0,
            "commission": -0.25,
            "commission_signed": True,
        },
        spec=PositionSpec(multiplier=1),
    )

    assert valued is not None
    assert valued.commission == pytest.approx(-0.25)
    assert valued.pnl == pytest.approx(5.25)


def test_position_valuation_normalizes_ctp_percent_10k_open_ratio():
    spec = normalize_asset_spec(
        {
            "InstrumentID": "IF2609",
            "VolumeMultiple": 300,
            "LongMarginRatioByMoney": 0.1,
            "OpenRatioByMoney": 0.23,
        },
        symbol="IF2609",
        source="ctp_gateway",
    )

    contract_spec = contract_spec_for("IF2609", {"contract_metadata": {"IF2609": spec}})
    valued = value_position(
        {"data_name": "IF2609", "size": 1, "price": 5000.0, "current_price": 5001.0},
        spec=contract_spec,
    )

    assert spec["commission_rate"] == pytest.approx(0.000023)
    assert contract_spec.commission_rate == pytest.approx(0.000023)
    assert valued is not None
    assert valued.commission == pytest.approx(34.5)


def test_position_valuation_uses_raw_ctp_position_spec_aliases():
    """Raw CTP aliases from logs/snapshots must drive multiplier, margin and fee."""
    row = {
        "data_name": "IF2609",
        "PosiDirection": "2",
        "Position": 1,
        "Price": 5000.0,
        "LastPrice": 5001.0,
        "VolumeMultiple": 300,
        "LongMarginRatioByMoney": 0.1,
        "OpenRatioByMoney": 0.23,
        "source": "ctp_gateway",
    }

    contract_spec = contract_spec_for("IF2609", row)
    valued = value_position(row, spec=contract_spec)

    assert contract_spec.multiplier == pytest.approx(300)
    assert contract_spec.commission_rate == pytest.approx(0.000023)
    assert valued is not None
    assert valued.market_value == pytest.approx(1_500_300.0)
    assert valued.margin_value == pytest.approx(150_030.0)
    assert valued.gross_pnl == pytest.approx(300.0)
    assert valued.commission == pytest.approx(34.5)
    assert valued.pnl == pytest.approx(265.5)


def test_position_valuation_parses_local_fixed_fee_and_margin_strings():
    spec = normalize_asset_spec(
        {
            "REFERENCE_CODE": "IF2609",
            "CONTRACT_MULTIPLIER": 300,
            "MARGIN_PER_LOT": "150000元/手",
            "COMMISSION_OPEN_AMOUNT": "3.01元/手",
        },
        symbol="IF2609",
        source="local_futures_commission",
    )
    contract_spec = contract_spec_for("IF2609", {"contract_metadata": {"IF2609": spec}})
    valued = value_position(
        {"data_name": "IF2609", "size": 1, "price": 5000.0, "current_price": 5001.0},
        spec=contract_spec,
    )

    assert contract_spec.margin_amount == pytest.approx(150000.0)
    assert contract_spec.commission_amount == pytest.approx(3.01)
    assert valued is not None
    assert valued.margin_value == pytest.approx(150000.0)
    assert valued.commission == pytest.approx(3.01)
    assert valued.pnl == pytest.approx(296.99)


def test_position_valuation_uses_directional_margin_amounts():
    contract_spec = contract_spec_for(
        "IF2609",
        {
            "contract_metadata": {
                "IF2609": {
                    "multiplier": 300,
                    "long_margin_amount": 150000.0,
                    "short_margin_amount": 151500.0,
                }
            }
        },
    )

    long_position = value_position(
        {"data_name": "IF2609", "size": 2, "price": 5000.0, "current_price": 5001.0},
        spec=contract_spec,
    )
    short_position = value_position(
        {"data_name": "IF2609", "size": -2, "price": 5000.0, "current_price": 4999.0},
        spec=contract_spec,
    )

    assert long_position is not None
    assert short_position is not None
    assert long_position.margin_value == pytest.approx(300000.0)
    assert short_position.margin_value == pytest.approx(303000.0)


def test_position_valuation_uses_mt5_margin_initial_per_lot():
    """MT5 margin_initial is per lot and must not be treated as a margin rate."""
    spec = normalize_asset_spec(
        {
            "symbol": "XAUUSD",
            "contract_size": 100,
            "margin_initial": 1950.0,
        },
        symbol="XAUUSD",
        source="mt5_gateway",
    )

    contract_spec = contract_spec_for("XAUUSD", {"contract_metadata": {"XAUUSD": spec}})
    valued = value_position(
        {"data_name": "XAUUSD", "size": 0.02, "price": 2330.0, "current_price": 2331.0},
        spec=contract_spec,
    )

    assert contract_spec.has_margin_amount is True
    assert contract_spec.margin_amount == pytest.approx(1950.0)
    assert valued is not None
    assert valued.market_value == pytest.approx(4662.0)
    assert valued.margin_value == pytest.approx(39.0)
    assert valued.gross_pnl == pytest.approx(2.0)


def test_normalize_gateway_position_handles_raw_mt5_position_side_values():
    long_row = normalize_gateway_position(
        {
            "trade_symbol": "XAUUSD",
            "trade_action": "0",
            "trade_volume": 0.02,
            "price_open": 2330.0,
        }
    )
    short_row = normalize_gateway_position(
        {
            "trade_symbol": "XAUUSD",
            "trade_action": "POSITION_TYPE_SELL",
            "trade_volume": 0.03,
            "price_open": 2331.0,
        }
    )
    numeric_short_row = normalize_gateway_position(
        {
            "trade_symbol": "XAUUSD",
            "type": 1,
            "volume": 0.04,
            "price_open": 2332.0,
        }
    )

    assert long_row["size"] == pytest.approx(0.02)
    assert short_row["size"] == pytest.approx(-0.03)
    assert numeric_short_row["size"] == pytest.approx(-0.04)


def test_normalize_gateway_position_handles_binance_camel_position_side():
    row = normalize_gateway_position(
        {
            "position_symbol_name": "BTCUSDT",
            "positionSide": "SHORT",
            "positionAmt": "0.25",
            "entryPrice": "64000",
            "markPrice": "63800",
        }
    )
    valued = value_position(row, spec=PositionSpec(multiplier=1, margin_rate=0.05))

    assert row["size"] == pytest.approx(-0.25)
    assert valued is not None
    assert valued.direction == "short"
    assert valued.gross_pnl == pytest.approx(50.0)


def test_binance_notional_alias_is_explicit_market_value():
    row = normalize_gateway_position(
        {
            "position_symbol_name": "BTCUSDT",
            "positionAmt": "0.25",
            "positionSide": "LONG",
            "entryPrice": "60000",
            "markPrice": "61000",
            "notional": "15250",
            "isolatedMargin": "800",
            "unRealizedProfit": "250",
            "source": "binance_gateway",
        },
        asset_spec={"contract_size": 1, "source": "binance_gateway"},
    )
    valued = value_position(row, spec=PositionSpec(multiplier=1, margin_rate=0.05))

    assert row["market_value"] == pytest.approx(15250.0)
    assert valued is not None
    assert valued.market_value == pytest.approx(15250.0)
    assert row["margin_value"] == pytest.approx(800.0)
    assert valued.margin_value == pytest.approx(800.0)
    assert valued.pnl == pytest.approx(250.0)


def test_normalize_gateway_position_handles_raw_ctp_position_direction_values():
    long_row = normalize_gateway_position(
        {
            "InstrumentID": "IF2609",
            "PosiDirection": "2",
            "Position": 1,
            "PositionCost": 1_500_000.0,
            "VolumeMultiple": 300,
        }
    )
    short_row = normalize_gateway_position(
        {
            "InstrumentID": "IF2609",
            "PosiDirection": "3",
            "Position": 2,
            "PositionCost": 3_000_000.0,
        },
        asset_spec={"multiplier": 300},
    )

    assert long_row["symbol"] == "IF2609"
    assert long_row["size"] == pytest.approx(1.0)
    assert long_row["price"] == pytest.approx(5000.0)
    assert short_row["size"] == pytest.approx(-2.0)
    assert short_row["price"] == pytest.approx(5000.0)


def test_normalize_gateway_position_handles_raw_ib_portfolio_fields():
    row = normalize_gateway_position(
        {
            "symbol": "AAPL",
            "secType": "STK",
            "position": 10,
            "avgCost": 150.0,
            "marketPrice": 155.0,
            "marketValue": 1550.0,
            "unrealizedPNL": 50.0,
        },
        asset_spec={"source": "ib_gateway", "contract_size": 1},
    )

    valued = value_position(
        row,
        spec=contract_spec_for("AAPL", {"contract_metadata": {"AAPL": row}}),
    )

    assert row["size"] == pytest.approx(10.0)
    assert row["price"] == pytest.approx(150.0)
    assert row["current_price"] == pytest.approx(155.0)
    assert row["market_value"] == pytest.approx(1550.0)
    assert row["gross_pnl"] == pytest.approx(50.0)
    assert valued is not None
    assert valued.market_value == pytest.approx(1550.0)
    assert valued.pnl == pytest.approx(50.0)


def test_normalize_gateway_position_handles_ib_client_portal_field_names():
    """IBKR Client Portal portfolio positions use mkt*/Pnl field names."""
    row = normalize_gateway_position(
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
        },
        asset_spec={"source": "ib_gateway", "contract_size": 1},
    )

    valued = value_position(
        row,
        spec=contract_spec_for("SPY", {"contract_metadata": {"SPY": row}}),
    )

    assert row["symbol"] == "SPY"
    assert row["size"] == pytest.approx(5.0)
    assert row["price"] == pytest.approx(434.93)
    assert row["current_price"] == pytest.approx(471.16000365)
    assert row["market_value"] == pytest.approx(2355.8)
    assert row["gross_pnl"] == pytest.approx(181.15)
    assert valued is not None
    assert valued.market_value == pytest.approx(2355.8)
    assert valued.pnl == pytest.approx(181.15)


def test_value_position_preserves_exchange_market_value_when_multiplier_missing():
    """Exchange-reported market value is authoritative when specs are incomplete."""
    row = normalize_gateway_position(
        {
            "symbol": "ES",
            "secType": "FUT",
            "position": 1,
            "avgCost": 5000.0,
            "marketPrice": 5010.0,
            "marketValue": 250500.0,
            "unrealizedPNL": 500.0,
        },
        asset_spec={"source": "ib_gateway", "commission_rate": 0.0001},
    )

    valued = value_position(
        row,
        spec=contract_spec_for("ES", {"contract_metadata": {"ES": row}}),
    )

    assert valued is not None
    assert valued.multiplier == pytest.approx(1.0)
    assert valued.market_value == pytest.approx(250500.0)
    assert valued.margin_value == pytest.approx(250500.0)
    assert valued.commission == pytest.approx(25.0)
    assert valued.pnl == pytest.approx(475.0)


def test_value_position_handles_raw_numeric_short_direction():
    valued = value_position(
        {
            "data_name": "XAUUSD",
            "type": 1,
            "volume": 0.02,
            "price_open": 2330.0,
            "price_current": 2329.0,
        },
        spec=contract_spec_for(
            "XAUUSD",
            {"contract_metadata": {"XAUUSD": {"contract_size": 100}}},
        ),
    )

    assert valued is not None
    assert valued.size == pytest.approx(-0.02)
    assert valued.market_value == pytest.approx(4658.0)
    assert valued.gross_pnl == pytest.approx(2.0)


def test_normalize_gateway_position_prefers_live_price_over_ctp_settlement_price():
    row = normalize_gateway_position(
        {
            "InstrumentID": "IF2609",
            "PosiDirection": "2",
            "Position": 1,
            "PositionCost": 1_500_000.0,
            "SettlementPrice": 4990.0,
        },
        asset_spec={
            "source": "ctp_gateway",
            "multiplier": 300,
            "margin_rate": 0.12,
            "current_price": 5010.0,
        },
    )

    valued = value_position(
        row,
        spec=contract_spec_for("IF2609", {"contract_metadata": {"IF2609": row}}),
    )

    assert row["current_price"] == pytest.approx(5010.0)
    assert valued is not None
    assert valued.market_value == pytest.approx(1_503_000.0)
    assert valued.gross_pnl == pytest.approx(3_000.0)


def test_normalize_gateway_position_preserves_raw_ctp_asset_aliases_without_spec():
    """Gateway rows can carry CTP asset aliases even when the spec query is empty."""
    row = normalize_gateway_position(
        {
            "InstrumentID": "IF2609",
            "PosiDirection": "2",
            "Position": 1,
            "PositionCost": 1_500_000.0,
            "LastPrice": 5001.0,
            "VolumeMultiple": 300,
            "LongMarginRatioByMoney": 0.1,
            "OpenRatioByMoney": 0.23,
            "source": "ctp_gateway",
        },
        asset_spec={},
    )

    valued = value_position(row, spec=contract_spec_for("IF2609", row))

    assert row["VolumeMultiple"] == 300
    assert row["price"] == pytest.approx(5000.0)
    assert row["OpenRatioByMoney"] == pytest.approx(0.23)
    assert valued is not None
    assert valued.market_value == pytest.approx(1_500_300.0)
    assert valued.margin_value == pytest.approx(150_030.0)
    assert valued.pnl == pytest.approx(265.5)


def test_exchange_prefixed_symbol_aliases_match_contract_metadata():
    spec = normalize_asset_spec(
        {
            "REFERENCE_CODE": "IF2609",
            "CONTRACT_MULTIPLIER": 300,
            "MARGIN_BUY": 10,
            "COMMISSION_OPEN_RATIO": 0.23,
        },
        symbol="IF2609",
        source="local_futures_commission",
    )

    aliases = symbol_aliases("CFFEX.IF2609")
    valued = value_position(
        {"data_name": "CFFEX.IF2609", "size": 1, "price": 5000.0, "current_price": 5001.0},
        spec=contract_spec_for("CFFEX.IF2609", {"contract_metadata": {"IF2609": spec}}),
    )

    assert "IF2609" in aliases
    assert "IF2609.CFFEX" in aliases
    assert valued is not None
    assert valued.multiplier == 300
    assert valued.margin_rate == pytest.approx(0.1)
    assert valued.gross_pnl == pytest.approx(300.0)


def test_crypto_symbol_aliases_match_compact_and_separated_forms():
    separated_aliases = symbol_aliases("BTC/USDT")
    compact_aliases = symbol_aliases("BTCUSDT")
    spec = {"symbol": "BTC/USDT", "contract_size": 1}

    assert "BTCUSDT" in separated_aliases
    assert "BTC/USDT" in compact_aliases
    assert (
        trading_workspace_service_module._asset_spec_for_symbol({"BTC/USDT": spec}, "BTCUSDT")
        == spec
    )


def test_workspace_asset_spec_lookup_supports_exchange_prefixed_symbols():
    spec = {"symbol": "IF2609", "multiplier": 300}

    assert (
        trading_workspace_service_module._asset_spec_for_symbol({"IF2609": spec}, "CFFEX.IF2609")
        == spec
    )
    assert (
        trading_workspace_service_module._asset_spec_for_symbol({"IF2609": spec}, "IF2609.CFFEX")
        == spec
    )


def test_gateway_asset_spec_query_uses_instrument_for_exchange_prefixed_symbol():
    class FakeTrader:
        def query_instrument(self, instrument, timeout=2):
            assert instrument == "IF2609"
            return {"InstrumentID": instrument, "VolumeMultiple": 300, "PriceTick": 0.2}

    class FakeFeed:
        trader_client = FakeTrader()

    class FakeAdapter:
        feed = FakeFeed()

    gateway = {"runtime": SimpleNamespace(adapter=FakeAdapter())}

    spec = query_gateway_asset_spec(gateway, "CFFEX.IF2609")

    assert spec["symbol"] == "CFFEX.IF2609"
    assert spec["multiplier"] == 300
    assert spec["price_tick"] == pytest.approx(0.2)


def test_position_valuation_prefers_exchange_margin_and_pnl():
    spec = normalize_asset_spec(
        {
            "symbol": "IF2506",
            "multiplier": 300,
            "long_margin_rate": 0.12,
            "open_fee_rate": 0.000023,
        },
        source="ctp_gateway",
    )
    row = normalize_gateway_position(
        {
            "instrument": "IF2506",
            "direction": "long",
            "volume": 10,
            "price": 4000.0,
            "current_price": 4020.0,
            "profit": 30000.0,
            "commission": 45.0,
            "use_margin": 1_440_000.0,
        },
        asset_spec=spec,
    )

    valued = value_position(
        row, spec=contract_spec_for("IF2506", {"contract_metadata": {"IF2506": spec}})
    )

    assert valued is not None
    assert valued.market_value == pytest.approx(12_060_000.0)
    assert valued.margin_value == pytest.approx(1_440_000.0)
    assert valued.commission == pytest.approx(45.0)
    assert valued.gross_pnl == pytest.approx(30_000.0)
    assert valued.pnl == pytest.approx(29_955.0)


def test_inverse_okx_contract_uses_contract_value_for_quote_valuation():
    spec = normalize_asset_spec(
        {
            "instId": "BTC-USD-SWAP",
            "instType": "SWAP",
            "ctType": "inverse",
            "multiplier": "1",
            "ctVal": "100",
            "ctMult": "1",
            "ctValCcy": "USD",
            "baseCcy": "BTC",
            "quoteCcy": "USD",
            "settleCcy": "BTC",
            "taker_commission_rate": 0.0005,
        },
        symbol="BTC-USD-SWAP",
        source="okx_get_instruments",
    )
    row = normalize_gateway_position(
        {
            "instId": "BTC-USD-SWAP",
            "pos": "100",
            "posSide": "long",
            "avgPx": "50000",
            "markPx": "55000",
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USD-SWAP", {"contract_metadata": {"BTC-USD-SWAP": spec}}),
    )

    assert valued is not None
    assert spec["contract_value_currency"] == "USD"
    assert spec["multiplier"] == pytest.approx(100.0)
    assert row["multiplier"] == pytest.approx(100.0)
    assert valued.market_value == pytest.approx(10_000.0)
    assert valued.gross_pnl == pytest.approx(1_000.0)
    assert valued.commission == pytest.approx(10.0)
    assert valued.pnl == pytest.approx(990.0)


def test_inverse_raw_metadata_prefers_ctval_over_multiplier_aliases():
    """Raw inverse metadata can carry ctMult/multiplier=1; ctVal is the contract value."""
    spec = {
        "source": "okx_get_instruments",
        "instType": "SWAP",
        "ctType": "inverse",
        "multiplier": 1,
        "ctVal": 100,
        "ctMult": 1,
        "ctValCcy": "USD",
        "baseCcy": "BTC",
        "quoteCcy": "USD",
        "settleCcy": "BTC",
        "margin_rate": 0.1,
        "taker_commission_rate": 0.0005,
    }
    contract_spec = contract_spec_for(
        "BTC-USD-SWAP",
        {"contract_metadata": {"BTC-USD-SWAP": spec}},
    )
    valued = value_position(
        {
            "instId": "BTC-USD-SWAP",
            "posSide": "long",
            "pos": 100,
            "avgPx": 50000.0,
            "markPx": 55000.0,
            "multiplier": 1,
            "ctVal": 100,
            "ctMult": 1,
            "ctType": "inverse",
            "ctValCcy": "USD",
            "baseCcy": "BTC",
            "quoteCcy": "USD",
            "settleCcy": "BTC",
        },
        spec=contract_spec,
    )

    assert contract_spec.multiplier == pytest.approx(100.0)
    assert valued is not None
    assert valued.multiplier == pytest.approx(100.0)
    assert valued.market_value == pytest.approx(10_000.0)
    assert valued.gross_pnl == pytest.approx(1_000.0)
    assert valued.commission == pytest.approx(10.0)
    assert valued.pnl == pytest.approx(990.0)


def test_explicit_inverse_flag_drives_contract_valuation_without_cttype():
    """Some adapters expose inverse as a boolean flag without ctType/ctValCcy aliases."""
    spec = normalize_asset_spec(
        {
            "symbol": "BTCUSD",
            "instType": "SWAP",
            "inverse": True,
            "multiplier": 1,
            "ctVal": 100,
            "ctMult": 1,
            "margin_rate": 0.1,
            "taker_commission_rate": 0.0005,
        },
        symbol="BTCUSD",
        source="gateway.get_symbol_info",
    )
    row = normalize_gateway_position(
        {
            "symbol": "BTCUSD",
            "posSide": "long",
            "pos": 2,
            "avgPx": 50000.0,
            "markPx": 55000.0,
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTCUSD", {"contract_metadata": {"BTCUSD": spec}}),
    )

    assert spec["inverse"] is True
    assert spec["multiplier"] == pytest.approx(100.0)
    assert row["inverse"] is True
    assert valued is not None
    assert valued.multiplier == pytest.approx(100.0)
    assert valued.market_value == pytest.approx(200.0)
    assert valued.margin_value == pytest.approx(20.0)
    assert valued.gross_pnl == pytest.approx(20.0)
    assert valued.commission == pytest.approx(0.2)
    assert valued.pnl == pytest.approx(19.8)


def test_normalize_gateway_position_does_not_double_subtract_explicit_net_pnl():
    row = normalize_gateway_position(
        {
            "instrument": "IF2506",
            "direction": "long",
            "volume": 1,
            "price": 4000.0,
            "current_price": 4001.0,
            "gross_pnl": 300.0,
            "pnlcomm": 265.5,
            "commission": 34.5,
        },
        asset_spec={"multiplier": 300, "margin_rate": 0.1},
    )

    valued = value_position(
        row,
        spec=contract_spec_for(
            "IF2506",
            {
                "contract_metadata": {
                    "IF2506": {
                        "multiplier": 300,
                        "margin_rate": 0.1,
                    }
                }
            },
        ),
    )

    assert row["pnlcomm"] == pytest.approx(265.5)
    assert row["position_pnl"] == pytest.approx(265.5)
    assert row["gross_pnl"] == pytest.approx(300.0)
    assert valued is not None
    assert valued.commission == pytest.approx(34.5)
    assert valued.gross_pnl == pytest.approx(300.0)
    assert valued.pnl == pytest.approx(265.5)


def test_normalize_gateway_position_uses_position_fee_as_real_commission():
    spec = normalize_asset_spec(
        {
            "symbol": "BTC-USDT-SWAP",
            "contract_size": 1,
            "commission_rate": 0.01,
        },
        source="okx_gateway",
    )
    row = normalize_gateway_position(
        {
            "instrument": "BTC-USDT-SWAP",
            "position_side": "long",
            "position_volume": 1,
            "avg_price": 60000.0,
            "mark_price": 60005.0,
            "position_unrealized_pnl": 5.0,
            "position_fee": -0.25,
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for(
            "BTC-USDT-SWAP",
            {"contract_metadata": {"BTC-USDT-SWAP": spec}},
        ),
    )

    assert row["commission"] == pytest.approx(0.25)
    assert row["position_pnl"] == pytest.approx(4.75)
    assert valued is not None
    assert valued.commission == pytest.approx(0.25)
    assert valued.pnl == pytest.approx(4.75)


def test_normalize_gateway_position_prefers_okx_upl_over_position_pnl():
    """OKX position pnl is not the current unrealized PnL for open-position risk."""
    spec = normalize_asset_spec(
        {
            "instId": "BTC-USDT-SWAP",
            "instType": "SWAP",
            "ctVal": "0.01",
            "settleCcy": "USDT",
        },
        symbol="BTC-USDT-SWAP",
        source="okx_gateway",
    )
    row = normalize_gateway_position(
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
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USDT-SWAP", {"contract_metadata": {"BTC-USDT-SWAP": spec}}),
    )

    assert row["gross_pnl"] == pytest.approx(2.0)
    assert row["position_pnl"] == pytest.approx(1.88)
    assert valued is not None
    assert valued.gross_pnl == pytest.approx(2.0)
    assert valued.commission == pytest.approx(0.12)
    assert valued.pnl == pytest.approx(1.88)


def test_normalize_gateway_position_replays_trade_fees_for_current_open_position():
    spec = normalize_asset_spec(
        {
            "symbol": "BTCUSDT",
            "contract_size": 1,
            "commission_rate": 0.0004,
        },
        source="binance_gateway",
    )
    row = normalize_gateway_position(
        {
            "position_symbol_name": "BTCUSDT",
            "positionAmt": "0.02",
            "positionSide": "BOTH",
            "entryPrice": "60000",
            "markPrice": "61000",
            "unRealizedProfit": "20",
        },
        asset_spec=spec,
        recent_trades=[
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.01",
                "commission": "0.2",
                "time": 1,
            },
            {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "qty": "0.01",
                "commission": "0.3",
                "time": 2,
            },
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.02",
                "commission": "0.5",
                "time": 3,
            },
        ],
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTCUSDT", {"contract_metadata": {"BTCUSDT": spec}}),
    )

    assert row["commission"] == pytest.approx(0.5)
    assert row["commission_source"] == "gateway.trades"
    assert row["gross_pnl"] == pytest.approx(20.0)
    assert row["pnlcomm"] == pytest.approx(19.5)
    assert valued is not None
    assert valued.commission == pytest.approx(0.5)
    assert valued.pnl == pytest.approx(19.5)


def test_normalize_gateway_position_understands_bybit_v5_position_and_execution_fields():
    spec = normalize_asset_spec(
        {
            "symbol": "BTCUSDT",
            "contract_size": 1,
            "quote_asset": "USDT",
            "commission_rate": 0.0004,
        },
        source="bybit_gateway",
    )

    row = normalize_gateway_position(
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
        },
        asset_spec=spec,
        recent_trades=[
            {
                "symbol": "BTCUSDT",
                "side": "Sell",
                "execQty": "0.1",
                "execPrice": "60000",
                "execFeeV2": "3",
                "feeCurrency": "USDT",
                "execTime": "1",
            }
        ],
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTCUSDT", {"contract_metadata": {"BTCUSDT": spec}}),
    )

    assert signed_gateway_size({"symbol": "BTCUSDT", "positionIdx": "2", "size": "1"}) == -1
    assert row["size"] == pytest.approx(-0.1)
    assert row["market_value"] == pytest.approx(5900.0)
    assert row["margin_value"] == pytest.approx(590.0)
    assert row["commission"] == pytest.approx(3.0)
    assert row["commission_source"] == "gateway.trades"
    assert row["gross_pnl"] == pytest.approx(100.0)
    assert row["position_pnl"] == pytest.approx(97.0)
    assert valued is not None
    assert valued.direction == "short"
    assert valued.market_value == pytest.approx(5900.0)
    assert valued.margin_value == pytest.approx(590.0)
    assert valued.commission == pytest.approx(3.0)
    assert valued.pnl == pytest.approx(97.0)


def test_normalize_gateway_position_does_not_use_trade_fee_in_other_currency():
    spec = normalize_asset_spec(
        {
            "symbol": "BTCUSDT",
            "quote_asset": "USDT",
            "contract_size": 1,
            "commission_rate": 0.0004,
        },
        source="binance_gateway",
    )
    row = normalize_gateway_position(
        {
            "position_symbol_name": "BTCUSDT",
            "positionAmt": "0.02",
            "entryPrice": "60000",
            "markPrice": "61000",
            "unRealizedProfit": "20",
        },
        asset_spec=spec,
        recent_trades=[
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.02",
                "commission": "0.001",
                "commissionAsset": "BNB",
                "time": 1,
            }
        ],
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTCUSDT", {"contract_metadata": {"BTCUSDT": spec}}),
    )

    assert "commission" not in row
    assert "commission_source" not in row
    assert row["commission_currency_mismatch"] is True
    assert valued is not None
    assert valued.commission == pytest.approx(0.48)
    assert valued.pnl == pytest.approx(19.52)


def test_normalize_gateway_position_converts_base_currency_position_fee_to_quote_value():
    spec = normalize_asset_spec(
        {
            "instId": "BTC-USD-SWAP",
            "instType": "SWAP",
            "ctType": "inverse",
            "ctVal": "100",
            "ctValCcy": "USD",
            "baseCcy": "BTC",
            "quoteCcy": "USD",
            "settleCcy": "BTC",
            "source": "okx_gateway",
        },
        symbol="BTC-USD-SWAP",
        source="okx_gateway",
    )
    row = normalize_gateway_position(
        {
            "instId": "BTC-USD-SWAP",
            "posSide": "long",
            "pos": "1",
            "avgPx": "50000",
            "markPx": "60000",
            "upl": "20",
            "fee": "-0.00005",
            "feeCcy": "BTC",
            "source": "okx_gateway",
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USD-SWAP", {"contract_metadata": {"BTC-USD-SWAP": spec}}),
    )

    assert row["commission"] == pytest.approx(2.5)
    assert row["position_pnl"] == pytest.approx(17.5)
    assert valued is not None
    assert valued.commission == pytest.approx(2.5)
    assert valued.pnl == pytest.approx(17.5)


def test_normalize_gateway_position_converts_base_currency_trade_fee_to_quote_value():
    spec = normalize_asset_spec(
        {
            "instId": "BTC-USD-SWAP",
            "instType": "SWAP",
            "ctType": "inverse",
            "ctVal": "100",
            "ctValCcy": "USD",
            "baseCcy": "BTC",
            "quoteCcy": "USD",
            "settleCcy": "BTC",
            "source": "okx_gateway",
        },
        symbol="BTC-USD-SWAP",
        source="okx_gateway",
    )
    row = normalize_gateway_position(
        {
            "instId": "BTC-USD-SWAP",
            "posSide": "long",
            "pos": "1",
            "avgPx": "50000",
            "markPx": "60000",
            "upl": "20",
            "source": "okx_gateway",
        },
        asset_spec=spec,
        recent_trades=[
            {
                "instId": "BTC-USD-SWAP",
                "side": "buy",
                "fillSz": "1",
                "fillPx": "50000",
                "fillFee": "-0.0001",
                "feeCcy": "BTC",
                "ts": "1",
            }
        ],
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USD-SWAP", {"contract_metadata": {"BTC-USD-SWAP": spec}}),
    )

    assert row["commission"] == pytest.approx(5.0)
    assert row["commission_source"] == "gateway.trades"
    assert row["pnlcomm"] == pytest.approx(15.0)
    assert valued is not None
    assert valued.commission == pytest.approx(5.0)
    assert valued.pnl == pytest.approx(15.0)


def test_normalize_gateway_position_preserves_okx_positive_fee_as_rebate():
    spec = normalize_asset_spec(
        {
            "symbol": "BTC-USDT-SWAP",
            "contract_size": 1,
            "commission_rate": 0.01,
        },
        source="okx_gateway",
    )
    row = normalize_gateway_position(
        {
            "instrument": "BTC-USDT-SWAP",
            "position_side": "long",
            "position_volume": 1,
            "avg_price": 60000.0,
            "mark_price": 60005.0,
            "position_unrealized_pnl": 5.0,
            "position_fee": 0.25,
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USDT-SWAP", {"contract_metadata": {"BTC-USDT-SWAP": spec}}),
    )

    assert row["commission"] == pytest.approx(-0.25)
    assert row["position_pnl"] == pytest.approx(5.25)
    assert valued is not None
    assert valued.commission == pytest.approx(-0.25)
    assert valued.pnl == pytest.approx(5.25)


def test_normalize_gateway_position_recognizes_okx_exchange_name_typo_for_signed_fee():
    row = normalize_gateway_position(
        {
            "exchange_nae": "OKX",
            "position_symbol_name": "BTC-USDT-SWAP",
            "position_side": "long",
            "position_volume": 1,
            "avg_price": 60000.0,
            "mark_price": 60005.0,
            "position_unrealized_pnl": 5.0,
            "position_fee": 0.25,
        }
    )
    valued = value_position(row, spec=PositionSpec(multiplier=1, commission_rate=0.01))
    direct = value_position(
        {
            "exchange_nae": "OKX",
            "data_name": "BTC-USDT-SWAP",
            "size": 1,
            "price": 60000.0,
            "current_price": 60005.0,
            "gross_pnl": 5.0,
            "position_fee": 0.25,
        },
        spec=PositionSpec(multiplier=1, commission_rate=0.01),
    )

    assert row["commission"] == pytest.approx(-0.25)
    assert row["position_pnl"] == pytest.approx(5.25)
    assert valued is not None
    assert valued.commission == pytest.approx(-0.25)
    assert valued.pnl == pytest.approx(5.25)
    assert direct is not None
    assert direct.commission == pytest.approx(-0.25)
    assert direct.pnl == pytest.approx(5.25)


def test_normalize_gateway_position_handles_raw_okx_position_aliases():
    row = normalize_gateway_position(
        {
            "instId": "BTC-USDT-SWAP",
            "posSide": "long",
            "pos": "1",
            "avgPx": "60000",
            "markPx": "60005",
            "upl": "5",
            "fee": "-0.25",
            "imr": "3000",
            "lever": "20",
            "mgnMode": "cross",
            "source": "okx_gateway",
        },
        asset_spec={"contract_size": 1, "source": "okx_gateway"},
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USDT-SWAP", {"contract_metadata": {"BTC-USDT-SWAP": row}}),
    )

    assert row["data_name"] == "BTC-USDT-SWAP"
    assert row["size"] == pytest.approx(1.0)
    assert row["price"] == pytest.approx(60000.0)
    assert row["current_price"] == pytest.approx(60005.0)
    assert row["commission"] == pytest.approx(0.25)
    assert row["position_pnl"] == pytest.approx(4.75)
    assert row["margin_value"] == pytest.approx(3000.0)
    assert row["leverage"] == "20"
    assert row["margin_type"] == "cross"
    assert valued is not None
    assert valued.margin_rate == pytest.approx(0.05)
    assert valued.pnl == pytest.approx(4.75)


def test_value_position_prefers_unrealized_upl_over_generic_pnl():
    valued = value_position(
        {
            "data_name": "BTC-USDT-SWAP",
            "size": 1,
            "avgPx": 60000.0,
            "markPx": 60005.0,
            "upl": 5.0,
            "pnl": 1.25,
            "position_fee": 0.25,
        },
        spec=PositionSpec(multiplier=1, commission_rate=0.01),
    )

    assert valued is not None
    assert valued.gross_pnl == pytest.approx(5.0)
    assert valued.pnl == pytest.approx(4.75)


def test_value_position_converts_base_currency_fee_to_quote_value():
    valued = value_position(
        {
            "data_name": "BTC-USD-SWAP",
            "size": 1,
            "avgPx": 50000.0,
            "markPx": 60000.0,
            "upl": 20.0,
            "fee": "-0.00005",
            "feeCcy": "BTC",
            "source": "okx_gateway",
        },
        spec=PositionSpec(
            multiplier=100.0,
            contract_type="inverse",
            contract_value_currency="USD",
            base_asset="BTC",
            quote_asset="USD",
            settle_currency="BTC",
            is_inverse=True,
        ),
    )

    assert valued is not None
    assert valued.commission == pytest.approx(2.5)
    assert valued.pnl == pytest.approx(17.5)


def test_okx_max_leverage_drives_margin_rate_when_no_margin_rate():
    spec = normalize_asset_spec(
        {
            "symbol": "BTC-USDT-SWAP",
            "contract_size": "0.01",
            "max_leverage": "20",
            "source": "okx_gateway",
        },
        symbol="BTC-USDT-SWAP",
        source="okx_gateway",
    )
    row = normalize_gateway_position(
        {
            "instId": "BTC-USDT-SWAP",
            "posSide": "long",
            "pos": "1",
            "avgPx": "60000",
            "markPx": "60005",
            "source": "okx_gateway",
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USDT-SWAP", {"contract_metadata": {"BTC-USDT-SWAP": spec}}),
    )

    assert spec["margin_rate"] == pytest.approx(0.05)
    assert spec["leverage"] == pytest.approx(20.0)
    assert row["leverage"] == pytest.approx(20.0)
    assert valued is not None
    assert valued.margin_rate == pytest.approx(0.05)


def test_normalize_asset_spec_accepts_raw_okx_instrument_fields():
    spec = normalize_asset_spec(
        {
            "instId": "BTC-USDT-SWAP",
            "instType": "SWAP",
            "ctVal": "0.01",
            "ctMult": "1",
            "tickSz": "0.1",
            "lotSz": "1",
            "minSz": "1",
            "maxLmtSz": "1000",
            "maxMktSz": "500",
            "lever": "20",
            "source": "okx_get_instruments",
        },
        symbol="BTC-USDT-SWAP",
        source="okx_gateway",
    )

    assert spec["asset_type"] == "SWAP"
    assert spec["multiplier"] == pytest.approx(0.01)
    assert spec["contract_size"] == pytest.approx(0.01)
    assert spec["contract_notional_value"] == pytest.approx(0.01)
    assert spec["contract_multiplier_raw"] == pytest.approx(1.0)
    assert spec["price_tick"] == pytest.approx(0.1)
    assert spec["min_order_size"] == pytest.approx(1.0)
    assert spec["max_order_size"] == pytest.approx(1000.0)
    assert spec["market_max_order_size"] == pytest.approx(500.0)
    assert spec["order_size_step"] == pytest.approx(1.0)
    assert spec["margin_rate"] == pytest.approx(0.05)


def test_raw_okx_contract_value_keeps_swap_notional_and_pnl_correct():
    spec = normalize_asset_spec(
        {
            "instId": "BTC-USDT-SWAP",
            "instType": "SWAP",
            "ctVal": "0.01",
            "ctMult": "1",
            "lever": "20",
            "takerU": "-0.0005",
            "source": "okx_get_instruments",
        },
        symbol="BTC-USDT-SWAP",
        source="okx_gateway",
    )
    row = normalize_gateway_position(
        {
            "instId": "BTC-USDT-SWAP",
            "posSide": "long",
            "pos": "10",
            "avgPx": "60000",
            "markPx": "61000",
            "upl": "100",
            "fee": "-0.5",
            "source": "okx_gateway",
        },
        asset_spec=spec,
    )

    valued = value_position(
        row,
        spec=contract_spec_for("BTC-USDT-SWAP", {"contract_metadata": {"BTC-USDT-SWAP": spec}}),
    )

    assert row["multiplier"] == pytest.approx(0.01)
    assert row["size"] == pytest.approx(10.0)
    assert valued is not None
    assert valued.multiplier == pytest.approx(0.01)
    assert valued.market_value == pytest.approx(6100.0)
    assert valued.margin_rate == pytest.approx(0.05)
    assert valued.margin_value == pytest.approx(305.0)
    assert valued.commission == pytest.approx(0.5)
    assert valued.gross_pnl == pytest.approx(100.0)
    assert valued.pnl == pytest.approx(99.5)


def test_okx_position_notional_usd_alias_is_explicit_market_value():
    row = normalize_gateway_position(
        {
            "position_symbol_name": "BTC-USDT-SWAP",
            "position_side": "long",
            "position_volume": 10,
            "avg_price": 60000.0,
            "mark_price": 61000.0,
            "position_notional_usd": 6100.0,
            "position_unrealized_pnl": 100.0,
            "position_fee": -0.5,
            "source": "okx_gateway",
        },
        asset_spec={"contract_size": 0.01, "source": "okx_gateway"},
    )

    valued = value_position(row, spec=PositionSpec(multiplier=0.01, margin_rate=0.05))

    assert row["market_value"] == pytest.approx(6100.0)
    assert valued is not None
    assert valued.market_value == pytest.approx(6100.0)
    assert valued.margin_value == pytest.approx(305.0)
    assert valued.pnl == pytest.approx(99.5)


def test_normalize_gateway_position_keeps_fee_estimation_when_only_swap_is_present():
    spec = normalize_asset_spec(
        {
            "symbol": "XAUUSD",
            "contract_size": 100,
            "commission_rate": 0.001,
        },
        source="mt5_gateway",
    )
    row = normalize_gateway_position(
        {
            "instrument": "XAUUSD",
            "direction": "buy",
            "volume": 0.02,
            "price": 2330.0,
            "current_price": 2331.0,
            "profit": 2.0,
            "swap": -0.1,
        },
        asset_spec=spec,
    )

    assert "position_pnl" not in row
    assert row["gross_pnl"] == pytest.approx(2.0)
    assert row["swap"] == pytest.approx(-0.1)

    valued = value_position(
        row,
        spec=contract_spec_for("XAUUSD", {"contract_metadata": {"XAUUSD": spec}}),
    )

    assert valued is not None
    assert valued.commission == pytest.approx(4.66)
    assert valued.pnl == pytest.approx(-2.76)


def test_position_valuation_treats_profit_alias_as_gross_pnl():
    valued = value_position(
        {
            "data_name": "IF2609",
            "size": 1,
            "price": 5000.0,
            "current_price": 5008.0,
            "profit": 3000.0,
        },
        spec=contract_spec_for(
            "IF2609",
            {
                "contract_metadata": {
                    "IF2609": {
                        "multiplier": 300,
                        "commission_rate": 0.000023,
                    }
                }
            },
        ),
    )

    assert valued is not None
    assert valued.gross_pnl == pytest.approx(3000.0)
    assert valued.commission == pytest.approx(34.5)
    assert valued.pnl == pytest.approx(2965.5)


def test_gateway_position_pnl_alias_is_gross_until_explicitly_net():
    spec = normalize_asset_spec(
        {
            "InstrumentID": "IF2609",
            "VolumeMultiple": 300,
            "OpenRatioByMoney": 0.23,
        },
        symbol="IF2609",
        source="ctp_gateway",
    )
    contract_spec = contract_spec_for("IF2609", {"contract_metadata": {"IF2609": spec}})

    row = normalize_gateway_position(
        {
            "InstrumentID": "IF2609",
            "PosiDirection": "2",
            "Position": 1,
            "Price": 5000.0,
            "LastPrice": 5010.0,
            "position_pnl": 3000.0,
        },
        asset_spec=spec,
    )
    valued = value_position(row, spec=contract_spec)
    direct = value_position(
        {
            "data_name": "IF2609",
            "size": 1,
            "price": 5000.0,
            "current_price": 5010.0,
            "position_pnl": 3000.0,
        },
        spec=contract_spec,
    )

    assert "pnlcomm" not in row
    assert "position_pnl" not in row
    assert row["gross_pnl"] == pytest.approx(3000.0)
    assert valued is not None
    assert valued.gross_pnl == pytest.approx(3000.0)
    assert valued.commission == pytest.approx(34.5)
    assert valued.pnl == pytest.approx(2965.5)
    assert direct is not None
    assert direct.gross_pnl == pytest.approx(3000.0)
    assert direct.pnl == pytest.approx(2965.5)


def test_normalize_asset_spec_accepts_raw_binance_fee_payload():
    spec = normalize_asset_spec(
        {
            "data": [
                {
                    "symbol": "BTCUSDT",
                    "makerCommission": 15,
                    "takerCommission": 20,
                }
            ]
        },
        symbol="BTCUSDT",
        source="binance_get_fee",
    )

    assert spec["maker_commission_rate"] == pytest.approx(0.0015)
    assert spec["taker_commission_rate"] == pytest.approx(0.002)
    assert spec["commission_rate"] == pytest.approx(0.002)


def test_normalize_asset_spec_accepts_raw_okx_fee_sign_payload():
    spec = normalize_asset_spec(
        {
            "data": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "makerU": "0.0002",
                    "takerU": "-0.0005",
                }
            ]
        },
        symbol="BTC-USDT-SWAP",
        source="okx_get_fee",
    )

    assert spec["maker_commission_rate"] == pytest.approx(-0.0002)
    assert spec["taker_commission_rate"] == pytest.approx(0.0005)
    assert spec["commission_rate"] == pytest.approx(0.0005)


def test_normalize_asset_spec_accepts_raw_bybit_v5_instrument_payload():
    spec = normalize_asset_spec(
        {
            "retCode": 0,
            "result": {
                "category": "linear",
                "list": [
                    {
                        "symbol": "ETHUSDT",
                        "contractType": "LinearPerpetual",
                        "priceFilter": {"tickSize": "0.01"},
                    },
                    {
                        "symbol": "BTCUSDT",
                        "contractType": "LinearPerpetual",
                        "baseCoin": "BTC",
                        "quoteCoin": "USDT",
                        "settleCoin": "USDT",
                        "priceFilter": {"tickSize": "0.10"},
                        "lotSizeFilter": {
                            "minOrderQty": "0.001",
                            "maxOrderQty": "100",
                            "qtyStep": "0.001",
                        },
                        "leverageFilter": {"maxLeverage": "100"},
                    },
                ],
            },
        },
        symbol="BTCUSDT",
        source="bybit_get_exchange_info",
    )

    assert spec["symbol"] == "BTCUSDT"
    assert spec["contract_type"] == "LinearPerpetual"
    assert spec["asset_type"] == "linear"
    assert spec["base_asset"] == "BTC"
    assert spec["quote_asset"] == "USDT"
    assert spec["settle_currency"] == "USDT"
    assert spec["multiplier"] == pytest.approx(1.0)
    assert spec["margin_rate"] == pytest.approx(0.01)
    assert spec["tick_size"] == pytest.approx(0.1)
    assert spec["min_order_size"] == pytest.approx(0.001)
    assert spec["max_order_size"] == pytest.approx(100)
    assert spec["order_size_step"] == pytest.approx(0.001)


def test_query_gateway_asset_spec_merges_adapter_fee_method():
    class FakeAdapter:
        def get_symbol_info(self, symbol):
            assert symbol == "BTCUSDT"
            return {"symbol": symbol, "contract_size": 0.001}

        def get_fee(self, symbol):
            assert symbol == "BTCUSDT"
            return {
                "makerCommissionRate": "0.0001",
                "takerCommissionRate": "0.0004",
            }

    gateway = {"runtime": SimpleNamespace(adapter=FakeAdapter())}

    spec = query_gateway_asset_spec(gateway, "BTCUSDT")

    assert spec["contract_size"] == pytest.approx(0.001)
    assert spec["maker_commission_rate"] == pytest.approx(0.0001)
    assert spec["taker_commission_rate"] == pytest.approx(0.0004)
    assert spec["commission_rate"] == pytest.approx(0.0004)
    assert spec["source"] == "gateway.get_symbol_info"
    assert spec["fee_source"] == "gateway.get_fee"


def test_query_gateway_asset_spec_falls_back_to_feed_exchange_info():
    class FakeRequestData:
        def __init__(self, data):
            self._data = data

        def get_data(self):
            return self._data

    class FakeFeed:
        asset_type = "SWAP"

        def __init__(self):
            self.info_calls = []
            self.fee_calls = []

        def get_exchange_info(self, symbol=None):
            self.info_calls.append(symbol)
            return FakeRequestData(
                {
                    "retCode": 0,
                    "result": {
                        "category": "linear",
                        "list": [
                            {"symbol": "ETHUSDT", "priceFilter": {"tickSize": "0.01"}},
                            {
                                "symbol": "BTCUSDT",
                                "contractType": "LinearPerpetual",
                                "baseCoin": "BTC",
                                "quoteCoin": "USDT",
                                "settleCoin": "USDT",
                                "priceFilter": {"tickSize": "0.10"},
                                "lotSizeFilter": {"minOrderQty": "0.001", "qtyStep": "0.001"},
                                "leverageFilter": {"maxLeverage": "50"},
                            },
                        ],
                    },
                }
            )

        def get_fee(self, symbol):
            self.fee_calls.append(symbol)
            if symbol != "BTCUSDT":
                raise ValueError("unknown symbol")
            return {"makerCommissionRate": "0.0002", "takerCommissionRate": "0.0006"}

    feed = FakeFeed()
    gateway = {"runtime": SimpleNamespace(adapter=SimpleNamespace(feed=feed))}

    spec = query_gateway_asset_spec(gateway, "BTCUSDT")

    assert feed.info_calls[0] == "BTCUSDT"
    assert feed.fee_calls[0] == "BTCUSDT"
    assert spec["symbol"] == "BTCUSDT"
    assert spec["multiplier"] == pytest.approx(1.0)
    assert spec["margin_rate"] == pytest.approx(0.02)
    assert spec["tick_size"] == pytest.approx(0.1)
    assert spec["min_order_size"] == pytest.approx(0.001)
    assert spec["order_size_step"] == pytest.approx(0.001)
    assert spec["commission_rate"] == pytest.approx(0.0006)
    assert spec["source"] == "gateway.feed.get_exchange_info"
    assert spec["fee_source"] == "gateway.feed.get_fee"


def test_query_gateway_asset_spec_uses_symbol_aliases_for_exchange_methods():
    class FakeAdapter:
        def __init__(self):
            self.info_calls = []
            self.fee_calls = []

        def get_symbol_info(self, symbol):
            self.info_calls.append(symbol)
            if symbol != "IF2609":
                raise ValueError("unknown symbol")
            return {"InstrumentID": symbol, "VolumeMultiple": 300}

        def get_fee(self, symbol):
            self.fee_calls.append(symbol)
            if symbol != "IF2609":
                raise ValueError("unknown symbol")
            return {
                "OpenRatioByMoney": 0.23,
                "CloseTodayRatioByMoney": 3.45,
            }

    adapter = FakeAdapter()
    gateway = {"runtime": SimpleNamespace(adapter=adapter)}

    spec = query_gateway_asset_spec(gateway, "CFFEX.IF2609")

    assert adapter.info_calls[:2] == ["CFFEX.IF2609", "IF2609"]
    assert adapter.fee_calls[:2] == ["CFFEX.IF2609", "IF2609"]
    assert spec["multiplier"] == pytest.approx(300)
    assert spec["commission_rate"] == pytest.approx(0.000023)
    assert spec["close_today_commission_rate"] == pytest.approx(0.000345)
    assert spec["source"] == "gateway.get_symbol_info"
    assert spec["fee_source"] == "gateway.get_fee"


def test_query_gateway_last_price_uses_symbol_aliases_for_exchange_methods():
    class FakeAdapter:
        def __init__(self):
            self.calls = []

        def get_ticker(self, symbol):
            self.calls.append(symbol)
            if symbol != "IF2609":
                raise ValueError("unknown symbol")
            return {"last": "5001.5"}

    adapter = FakeAdapter()
    gateway = {"runtime": SimpleNamespace(adapter=adapter)}

    price = query_gateway_last_price(gateway, "CFFEX.IF2609")

    assert adapter.calls[:2] == ["CFFEX.IF2609", "IF2609"]
    assert price == pytest.approx(5001.5)


def test_symbols_for_instance_includes_existing_contract_metadata(tmp_path):
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "data": {"symbol": "IF2609"},
                "contract_metadata": {"rb2601": {"symbol": "rb2601"}},
                "live": {"contract_metadata": {"cu2601": {"InstrumentID": "cu2601"}}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    instance = {"params": {"contract_metadata": {"al2601": {"REFERENCE_CODE": "al2601"}}}}

    symbols = symbols_for_instance(instance, strategy_dir)

    assert "IF2609" in symbols
    assert "rb2601" in symbols
    assert "cu2601" in symbols
    assert "al2601" in symbols


def test_load_runtime_config_ignores_non_text_config_reader():
    config_path = SimpleNamespace()
    config_path.is_file = lambda: True
    config_path.read_text = lambda encoding="utf-8": SimpleNamespace()

    class FakeStrategyDir:
        def __truediv__(self, _name):
            return config_path

    assert load_runtime_config(FakeStrategyDir()) == {}


def test_persist_asset_specs_writes_runtime_sections_used_by_templates(tmp_path):
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    (strategy_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "live": {"qcheck": 0.5},
                "simulate": {"initial_cash": 100000},
                "params": {"fast_period": 5},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    instance = {"params": {}}
    spec = {
        "symbol": "IF2609",
        "multiplier": 300,
        "margin_rate": 0.12,
        "commission_rate": 0.000023,
    }

    persist_asset_specs(strategy_dir, instance, {"IF2609": spec})

    config = yaml.safe_load((strategy_dir / "config.yaml").read_text("utf-8"))
    assert config["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert config["params"]["contract_metadata"]["IF2609"]["margin_rate"] == 0.12
    assert config["live"]["contract_metadata"]["IF2609"]["commission_rate"] == 0.000023
    assert config["simulate"]["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert config["backtest"]["multiplier"] == 300
    assert instance["params"]["contract_metadata"]["IF2609"]["margin_rate"] == 0.12


def test_sync_trading_unit_runtime_copies_template_and_merges_unit_config(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
    template_dir = _make_strategy_template(
        tmp_path, "simulate/gateway_boll_breakout", "strategy_gateway_boll_breakout"
    )
    monkeypatch.setattr(workspace_unit_runtime, "get_strategy_dir", lambda _sid: template_dir)
    unit = SimpleNamespace(
        workspace_id="ws-1",
        id="unit-1",
        group_name="布林突破",
        strategy_id="simulate/gateway_boll_breakout",
        strategy_name="Boll AAPL",
        symbol="AAPL",
        symbol_name="Apple",
        timeframe="1m",
        timeframe_n=1,
        category="stock",
        data_config={"range_type": "sample", "sample_count": 300},
        unit_settings={
            "duration_seconds": 1800,
            "session_timeout": 1860,
            "qcheck_seconds": 0.25,
            "log_ticks": True,
            "log_positions": False,
            "log_indicators": True,
            "log_signals": False,
            "dispatch_ticks": True,
            "exactbars": -1,
            "stdstats": True,
        },
        params={"boll_period": 16, "boll_dev": 2.2},
        optimization_config={},
        gateway_config={
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "gateway",
                    "exchange_type": "IB_WEB",
                    "asset_type": "STK",
                    "account_id": "DU123456",
                },
                "ib_web": {
                    "account_id": "DU123456",
                    "base_url": "https://localhost:5000",
                },
            }
        },
    )

    runtime_dir = workspace_unit_runtime.sync_trading_unit_runtime(unit, {})

    assert (runtime_dir / "run.py").is_file()
    assert (runtime_dir / "strategy_gateway_boll_breakout.py").is_file()
    config_text = (runtime_dir / "config.yaml").read_text("utf-8")
    assert "Boll AAPL" in config_text
    assert "DU123456" in config_text
    assert "boll_period: 16" in config_text
    config = yaml.safe_load(config_text)
    assert config["live"]["qcheck"] == 0.25
    assert config["live"]["log_ticks"] is True
    assert config["live"]["log_positions"] is False
    assert config["live"]["log_indicators"] is True
    assert config["live"]["log_signals"] is False
    assert config["live"]["dispatch_ticks"] is True
    assert config["live"]["exactbars"] == -1
    assert config["live"]["stdstats"] is True


def test_sync_trading_unit_runtime_refreshes_existing_template_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
    template_dir = _make_strategy_template(
        tmp_path, "simulate/gateway_dual_ma", "strategy_gateway_dual_ma"
    )
    monkeypatch.setattr(workspace_unit_runtime, "get_strategy_dir", lambda _sid: template_dir)
    unit = _make_basic_trading_unit()
    runtime_dir = workspace_unit_runtime.unit_dir(unit.workspace_id, unit.id)
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "run.py").write_text("# stale runtime entrypoint\n", encoding="utf-8")
    (runtime_dir / "strategy_gateway_dual_ma.py").write_text("# stale strategy\n", encoding="utf-8")
    (template_dir / "run.py").write_text("# refreshed runtime entrypoint\n", encoding="utf-8")

    workspace_unit_runtime.sync_trading_unit_runtime(unit, {})

    assert (runtime_dir / "run.py").read_text("utf-8") == "# refreshed runtime entrypoint\n"
    assert "class S" in (runtime_dir / "strategy_gateway_dual_ma.py").read_text("utf-8")

    (template_dir / "run.py").write_text("# refreshed runtime entrypoint v2\n", encoding="utf-8")

    workspace_unit_runtime.sync_trading_unit_runtime(unit, {})

    assert (runtime_dir / "run.py").read_text("utf-8") == "# refreshed runtime entrypoint v2\n"


def test_sync_trading_unit_runtime_normalizes_futures_data_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_unit_runtime, "_WORKSPACE_UNITS_ROOT", tmp_path)
    template_dir = _make_strategy_template(
        tmp_path, "simulate/gateway_dual_ma", "strategy_gateway_dual_ma"
    )
    monkeypatch.setattr(workspace_unit_runtime, "get_strategy_dir", lambda _sid: template_dir)
    unit = SimpleNamespace(
        workspace_id="ws-ctp",
        id="unit-ctp",
        group_name="均线金叉",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="IF Future",
        symbol="IF2609",
        symbol_name="沪深300主力",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={"range_type": "sample", "sample_count": 300},
        unit_settings={},
        params={"fast_period": 3, "slow_period": 8},
        optimization_config={},
        gateway_config={
            "params": {
                "gateway": {
                    "enabled": True,
                    "provider": "ctp_gateway",
                    "exchange_type": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": "089763",
                    "password": "gateway-secret",
                    "access_token": "gateway-token",
                },
                "ctp": {
                    "broker_id": "9999",
                    "investor_id": "089763",
                    "user_id": "089763",
                    "password": "secret",
                    "auth_code": "auth-secret",
                },
            }
        },
    )

    runtime_dir = workspace_unit_runtime.sync_trading_unit_runtime(unit, {})
    config = yaml.safe_load((runtime_dir / "config.yaml").read_text("utf-8"))

    assert config["data"]["asset_type"] == "future"
    assert config["data"]["data_type"] == "futures"
    assert config["data"]["exchange"] == "CTP"
    assert config["live"]["qcheck"] == 0.5
    assert config["live"]["log_ticks"] is False
    assert config["live"]["log_positions"] is True
    assert config["live"]["log_indicators"] is False
    assert config["live"]["log_signals"] is True
    assert config["live"]["dispatch_ticks"] is False
    assert config["live"]["exactbars"] is True
    assert config["live"]["stdstats"] is False
    config_text = yaml.safe_dump(config, allow_unicode=True)
    assert "gateway-secret" not in config_text
    assert "gateway-token" not in config_text
    assert "auth-secret" not in config_text
    assert "secret" not in config_text
    assert "password" not in config["gateway"]
    assert "access_token" not in config["gateway"]
    assert "password" not in config["ctp"]
    assert "auth_code" not in config["ctp"]


def test_build_status_responses_tolerates_malformed_snapshot_values():
    unit = SimpleNamespace(
        id="unit-1",
        run_status="running",
        last_task_id=None,
        metrics_snapshot=["unexpected"],
        run_count=2,
        last_run_time=12.5,
        bar_count=30,
        trading_instance_id="inst-1",
        trading_snapshot="unexpected",
        trading_mode="paper",
        lock_trading=False,
        lock_running=False,
    )

    responses = TradingWorkspaceService().build_status_responses([unit])

    assert len(responses) == 1
    assert responses[0].id == "unit-1"
    assert responses[0].metrics_snapshot == {}
    assert responses[0].trading_snapshot == {}


def test_build_snapshot_falls_back_to_runtime_logs_when_log_dir_missing(tmp_path):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "log_time": "2026-06-25T07:17:41.329+08:00",
                "datetime": "2026-06-25 09:17:00",
                "data_name": "IF2609",
                "size": -1,
                "price": 4814.3593,
                "value": 4810.6,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    unit = SimpleNamespace(
        trading_instance_id="inst-1",
        trading_mode="paper",
        gateway_config={},
        symbol="IF2609",
        symbol_name="沪深300",
        strategy_name="CTP压测01",
    )

    snapshot, _metrics, _bar_count, _elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {
            "id": "inst-1",
            "status": "running",
            "runtime_dir": str(runtime_dir),
            "log_dir": None,
        },
    )

    assert snapshot["instance_status"] == "running"
    assert snapshot["short_position"] == 1.0
    assert snapshot["short_market_value"] == 4810.6
    assert snapshot["positions"][0]["updated_at"] == "2026-06-25T07:17:41.329+08:00"
    assert snapshot["positions"][0]["data_time"] == "2026-06-25 09:17:00"
    assert snapshot["updated_at"] == "2026-06-25T07:17:41.329+08:00"


def test_build_snapshot_light_hydrate_skips_full_log_and_preserves_summary(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "datetime": "2026-06-25 09:18:00",
                "data_name": "XAUUSD",
                "size": 0.01,
                "price": 4001.66,
                "value": 40.02,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    unit = SimpleNamespace(
        trading_instance_id="inst-1",
        trading_mode="paper",
        gateway_config={},
        symbol="XAUUSD",
        symbol_name="黄金/美元",
        strategy_name="MT5压测01",
        trading_snapshot={
            "today_pnl": 12.34,
            "cumulative_pnl": 56.78,
            "trades": [{"id": "old-trade"}],
        },
    )

    def fail_parse_log_dir(_log_dir):
        raise AssertionError("parse_log_dir should not run for light hydrate")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "parse_log_dir",
        fail_parse_log_dir,
    )

    snapshot, metrics, bar_count, elapsed = TradingWorkspaceService._build_snapshot(
        unit,
        {
            "id": "inst-1",
            "status": "running",
            "runtime_dir": str(runtime_dir),
            "log_dir": None,
        },
        full_log=False,
    )

    assert snapshot["positions"][0]["updated_at"] == "2026-06-25 09:18:00"
    assert snapshot["long_position"] == 0.01
    assert snapshot["today_pnl"] == 12.34
    assert snapshot["cumulative_pnl"] == 56.78
    assert snapshot["trades"] == [{"id": "old-trade"}]
    assert metrics == {}
    assert bar_count is None
    assert elapsed is None


@pytest.mark.asyncio
async def test_build_positions_response_can_skip_hydration(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-1",
        strategy_name="Unit One",
        strategy_id="simulate/gateway_dual_ma",
        symbol="EURUSD",
        symbol_name="Euro",
        trading_mode="paper",
        trading_snapshot={
            "positions": [
                {
                    "size": 2,
                    "price": 1.2,
                    "updated_at": "2026-06-25 09:00:00",
                    "data_time": "2026-06-25 08:59:00",
                }
            ],
            "long_position": 2.0,
            "short_position": 0.0,
            "latest_price": 1.25,
            "position_pnl": 0.1,
            "long_market_value": 2.5,
            "short_market_value": 0.0,
            "updated_at": "2026-06-25 09:00:00",
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)

    assert result.positions[0].unit_id == "unit-1"
    assert result.positions[0].updated_at == "2026-06-25 09:00:00"
    assert result.positions[0].data_time == "2026-06-25 08:59:00"
    assert result.total_long_value == 2.5


@pytest.mark.asyncio
async def test_build_positions_response_prefers_net_pnl_fields_in_snapshot_rows(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-1",
        strategy_name="Unit One",
        strategy_id="simulate/gateway_dual_ma",
        symbol="BTC-USDT-SWAP",
        symbol_name="BTC swap",
        trading_mode="live",
        trading_snapshot={
            "positions": [
                {
                    "data_name": "BTC-USDT-SWAP",
                    "direction": "long",
                    "size": 1,
                    "price": 60000.0,
                    "current_price": 60005.0,
                    "market_value": 60005.0,
                    "gross_pnl": 5.0,
                    "position_pnl": 5.0,
                    "pnlcomm": 4.75,
                    "commission": 0.25,
                    "updated_at": "2026-06-25 09:00:00",
                }
            ],
            "position_pnl": 5.0,
            "long_position": 1.0,
            "short_position": 0.0,
            "long_market_value": 60005.0,
            "short_market_value": 0.0,
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)

    assert result.positions[0].position_pnl == pytest.approx(4.75)
    assert result.total_pnl == pytest.approx(4.75)


@pytest.mark.asyncio
async def test_build_positions_response_revalues_gross_pnl_rows_without_explicit_net_pnl(
    monkeypatch,
):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-1",
        strategy_name="Unit One",
        strategy_id="simulate/gateway_dual_ma",
        symbol="BTC-USDT-SWAP",
        symbol_name="BTC swap",
        trading_mode="live",
        unit_settings={},
        params={},
        data_config={},
        gateway_config={},
        trading_snapshot={
            "positions": [
                {
                    "data_name": "BTC-USDT-SWAP",
                    "direction": "long",
                    "size": 1,
                    "price": 60000.0,
                    "current_price": 60005.0,
                    "market_value": 60005.0,
                    "margin_value": 3000.25,
                    "multiplier": 1,
                    "margin_rate": 0.05,
                    "gross_pnl": 5.0,
                    "position_pnl": 5.0,
                    "commission": 0.25,
                    "commission_signed": True,
                    "position_source": "gateway",
                    "asset_spec_source": "snapshot",
                    "updated_at": "2026-06-25 09:00:00",
                }
            ],
            "position_pnl": 5.0,
            "long_position": 1.0,
            "short_position": 0.0,
            "long_market_value": 60005.0,
            "short_market_value": 0.0,
            "position_source": "gateway",
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)
    row = result.positions[0]

    assert row.gross_pnl == pytest.approx(5.0)
    assert row.commission == pytest.approx(0.25)
    assert row.position_pnl == pytest.approx(4.75)
    assert result.total_pnl == pytest.approx(4.75)


@pytest.mark.asyncio
async def test_build_positions_response_skips_zero_position_rows_even_with_stale_snapshot():
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-zero",
        strategy_name="Zero Unit",
        strategy_id="simulate/gateway_dual_ma",
        symbol="BTC-USDT-SWAP",
        symbol_name="BTC",
        trading_mode="live",
        trading_snapshot={
            "positions": [
                {
                    "data_name": "BTC-USDT-SWAP",
                    "direction": "long",
                    "size": 0,
                    "price": 60000.0,
                    "market_value": 0.0,
                    "position_pnl": 0.0,
                }
            ],
            "long_position": 1.0,
            "short_position": 0.0,
            "position_pnl": 999.0,
            "long_market_value": 60000.0,
            "short_market_value": 0.0,
        },
    )

    result = await service.build_positions_response([unit], "user-1", hydrate=False)

    assert result.positions == []
    assert result.total_long_value == 0.0
    assert result.total_pnl == 0.0


@pytest.mark.asyncio
async def test_build_positions_response_preserves_micro_nonzero_positions(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-micro",
        strategy_name="Micro Unit",
        strategy_id="simulate/gateway_dual_ma",
        symbol="BTC-USDT-SWAP",
        symbol_name="BTC",
        trading_mode="live",
        unit_settings={},
        params={},
        data_config={},
        gateway_config={},
        trading_snapshot={
            "positions": [
                {
                    "data_name": "BTC-USDT-SWAP",
                    "position_volume": "0.00004",
                    "avgPx": "60000",
                    "markPx": "60010",
                    "contract_size": 1,
                    "source": "gateway",
                    "position_source": "gateway",
                }
            ],
            "position_source": "gateway",
            "long_position": 0.0,
            "short_position": 0.0,
            "position_pnl": 0.0,
            "long_market_value": 0.0,
            "short_market_value": 0.0,
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)

    assert len(result.positions) == 1
    assert result.positions[0].long_position == pytest.approx(0.00004)
    assert result.positions[0].market_value == pytest.approx(2.4)
    assert result.total_long_value == pytest.approx(2.4)


@pytest.mark.asyncio
async def test_build_positions_response_exposes_valuation_metadata(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-1",
        strategy_name="Unit One",
        strategy_id="simulate/gateway_dual_ma",
        symbol="IF2609",
        symbol_name="沪深300",
        trading_mode="live",
        trading_snapshot={
            "positions": [
                {
                    "data_name": "IF2609",
                    "direction": "long",
                    "size": 1,
                    "price": 5000.0,
                    "current_price": 5001.0,
                    "market_value": 1_500_300.0,
                    "margin_value": 150_030.0,
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission": 34.5069,
                    "gross_pnl": 300.0,
                    "position_pnl": 265.49,
                    "position_source": "gateway",
                    "asset_spec_source": "ctp_gateway",
                    "valuation_status": "confirmed",
                    "valuation_warnings": [],
                    "updated_at": "2026-06-25 09:00:00",
                }
            ],
            "long_position": 1.0,
            "short_position": 0.0,
            "latest_price": 5001.0,
            "position_pnl": 265.49,
            "long_market_value": 1_500_300.0,
            "short_market_value": 0.0,
            "position_source": "gateway",
            "asset_spec_source": "ctp_gateway",
            "valuation_status": "confirmed",
            "valuation_warnings": [],
            "updated_at": "2026-06-25 09:00:00",
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)
    row = result.positions[0]

    assert row.symbol == "IF2609"
    assert row.margin_value == 150030.0
    assert row.multiplier == 300
    assert row.margin_rate == 0.1
    assert row.commission == pytest.approx(34.5069)
    assert row.gross_pnl == 300.0
    assert row.position_source == "gateway"
    assert row.asset_spec_source == "ctp_gateway"
    assert row.valuation_status == "confirmed"


@pytest.mark.asyncio
async def test_build_positions_response_values_raw_ctp_snapshot_aliases(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-ctp",
        strategy_name="CTP Unit",
        strategy_id="simulate/gateway_dual_ma",
        symbol="IF2609",
        symbol_name="沪深300",
        trading_mode="live",
        unit_settings={},
        params={},
        data_config={},
        gateway_config={},
        trading_snapshot={
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
                    "source": "gateway",
                    "updated_at": "2026-06-25 09:00:00",
                    "data_time": "2026-06-25 08:59:00",
                }
            ],
            "position_source": "gateway",
            "long_position": 0.0,
            "short_position": 0.0,
            "position_pnl": 0.0,
            "long_market_value": 0.0,
            "short_market_value": 0.0,
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)
    row = result.positions[0]

    assert row.symbol == "IF2609"
    assert row.data_name == "IF2609"
    assert row.long_position == 1.0
    assert row.short_position == 0.0
    assert row.latest_price == 5001.0
    assert row.market_value == 1_500_300.0
    assert row.margin_value == 150_030.0
    assert row.multiplier == 300
    assert row.margin_rate == 0.1
    assert row.gross_pnl == 300.0
    assert row.commission == pytest.approx(34.5)
    assert row.position_pnl == pytest.approx(265.5)
    assert row.position_source == "gateway"
    assert row.valuation_status == "confirmed"
    assert result.total_long_value == 1_500_300.0
    assert result.total_pnl == pytest.approx(265.5)


@pytest.mark.asyncio
async def test_build_positions_response_values_raw_okx_snapshot_aliases(monkeypatch):
    service = TradingWorkspaceService()
    unit = SimpleNamespace(
        id="unit-okx",
        strategy_name="OKX Unit",
        strategy_id="simulate/gateway_dual_ma",
        symbol="BTC-USDT-SWAP",
        symbol_name="BTC perpetual",
        trading_mode="live",
        unit_settings={},
        params={},
        data_config={},
        gateway_config={},
        trading_snapshot={
            "positions": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "posSide": "long",
                    "pos": "1",
                    "avgPx": "60000",
                    "markPx": "60005",
                    "upl": "5",
                    "fee": "-0.25",
                    "imr": "3000",
                    "lever": "20",
                    "contract_size": 1,
                    "source": "okx_gateway",
                    "position_source": "gateway",
                    "updated_at": "2026-06-25 09:00:00",
                    "data_time": "2026-06-25 08:59:00",
                }
            ],
            "position_source": "gateway",
            "long_position": 0.0,
            "short_position": 0.0,
            "position_pnl": 0.0,
            "long_market_value": 0.0,
            "short_market_value": 0.0,
        },
    )

    async def fail_hydrate(_units, _user_id):
        raise AssertionError("hydrate_units should not run when hydrate=False")

    monkeypatch.setattr(service, "hydrate_units", fail_hydrate)

    result = await service.build_positions_response([unit], "user-1", hydrate=False)
    row = result.positions[0]

    assert row.symbol == "BTC-USDT-SWAP"
    assert row.data_name == "BTC-USDT-SWAP"
    assert row.long_position == 1.0
    assert row.short_position == 0.0
    assert row.latest_price == 60005.0
    assert row.market_value == 60005.0
    assert row.margin_value == 3000.0
    assert row.multiplier == 1
    assert row.margin_rate == 0.05
    assert row.gross_pnl == pytest.approx(5.0)
    assert row.commission == pytest.approx(0.25)
    assert row.position_pnl == pytest.approx(4.75)
    assert row.position_source == "gateway"
    assert row.valuation_status == "confirmed"
    assert result.total_long_value == 60005.0
    assert result.total_pnl == pytest.approx(4.75)


@pytest.mark.asyncio
async def test_start_units_keeps_already_running_instance_running(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    stale_tick_log = log_dir / "tick.log"
    stale_tick_log.write_text("keep-running-log\n", encoding="utf-8")
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测01",
        symbol="IF2609",
        symbol_name="沪深300",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="inst-1",
        run_status="failed",
        run_count=7,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    monkeypatch.setattr(
        workspace_unit_runtime,
        "sync_trading_unit_runtime",
        lambda *_args, **_kwargs: runtime_dir,
    )

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "user-1"
            return {
                "id": "inst-1",
                "status": "running",
                "pid": 12345,
                "runtime_dir": str(runtime_dir),
                "log_dir": None,
                "error": None,
            }

        async def start_instance(self, _instance_id):
            raise AssertionError("start_instance should not be called for running units")

        def add_instance(self, *_args, **_kwargs):
            raise AssertionError("add_instance should not be called for existing units")

        def remove_instance(self, *_args, **_kwargs):
            raise AssertionError("remove_instance should not be called for matching runtime dirs")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().start_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "task_id": "inst-1",
            "status": "running",
            "already_running": True,
        }
    ]
    assert unit.run_status == "running"
    assert unit.run_count == 7
    assert unit.trading_snapshot["instance_status"] == "running"
    assert stale_tick_log.read_text("utf-8") == "keep-running-log\n"


@pytest.mark.asyncio
async def test_stop_units_exposes_open_order_cancel_metadata(monkeypatch):
    cancel_metadata = {
        "gateway_key": "manual:CTP:simnow",
        "status": "warning",
        "open_order_count": 1,
        "cancelled_count": 0,
        "skipped_count": 1,
    }
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测01",
        symbol="IF2609",
        symbol_name="沪深300",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="inst-1",
        run_status="running",
        run_count=1,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    class FakeManager:
        async def stop_instance(self, instance_id):
            assert instance_id == "inst-1"
            return {"id": "inst-1", "status": "stopped", "open_order_cancel": cancel_metadata}

        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "user-1"
            return None

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().stop_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "cancelled": True,
            "open_order_cancel": cancel_metadata,
        }
    ]
    assert unit.run_status == "idle"
    assert unit.trading_snapshot["open_order_cancel"] == cancel_metadata


@pytest.mark.asyncio
async def test_stop_units_preserves_failed_open_order_cancel_metadata(monkeypatch):
    cancel_metadata = {
        "gateway_key": "manual:CTP:simnow",
        "status": "error",
        "message": "failed to cancel one or more open orders",
        "open_order_count": 1,
        "failed_count": 1,
    }
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测01",
        symbol="IF2609",
        symbol_name="沪深300",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="inst-1",
        run_status="running",
        run_count=1,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    class FakeManager:
        async def stop_instance(self, instance_id):
            assert instance_id == "inst-1"
            exc = RuntimeError("停止策略前撤销交易所挂单失败")
            exc.open_order_cancel = cancel_metadata
            raise exc

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().stop_units([unit], user_id="user-1")

    assert results[0]["cancelled"] is False
    assert results[0]["open_order_cancel"] == cancel_metadata
    assert "撤销交易所挂单失败" in results[0]["error"]
    assert unit.run_status == "failed"
    assert unit.trading_snapshot["open_order_cancel"] == cancel_metadata


@pytest.mark.asyncio
async def test_start_units_cleans_stale_runtime_logs_before_new_start(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "tick.log").write_text("old ticks\n", encoding="utf-8")
    (log_dir / "trade.log").write_text("old trades\n", encoding="utf-8")
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测02",
        symbol="IF2609",
        symbol_name="沪深300",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="inst-1",
        run_status="idle",
        run_count=2,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    monkeypatch.setattr(
        workspace_unit_runtime,
        "sync_trading_unit_runtime",
        lambda *_args, **_kwargs: runtime_dir,
    )

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "user-1"
            return {
                "id": "inst-1",
                "status": "stopped",
                "pid": None,
                "runtime_dir": str(runtime_dir),
                "log_dir": str(log_dir),
                "error": None,
            }

        async def start_instance(self, instance_id):
            assert instance_id == "inst-1"
            assert log_dir.is_dir()
            assert list(log_dir.iterdir()) == []
            return {
                "id": "inst-1",
                "status": "running",
                "pid": 12346,
                "runtime_dir": str(runtime_dir),
                "log_dir": str(log_dir),
                "error": None,
                "started_at": "2026-06-24 12:00:00",
            }

        def add_instance(self, *_args, **_kwargs):
            raise AssertionError("add_instance should not be called for existing units")

        def remove_instance(self, *_args, **_kwargs):
            raise AssertionError("remove_instance should not be called")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().start_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "task_id": "inst-1",
            "status": "running",
            "already_running": False,
        }
    ]
    assert unit.run_status == "running"
    assert unit.run_count == 3
    assert unit.trading_snapshot["instance_status"] == "running"
    assert list(log_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_start_units_reattaches_missing_instance_record_to_running_pid(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    unit = SimpleNamespace(
        id="unit-1",
        workspace_id="ws-1",
        group_name="压测",
        strategy_id="simulate/gateway_dual_ma",
        strategy_name="CTP压测08",
        symbol="rb2610",
        symbol_name="螺纹钢",
        timeframe="1m",
        timeframe_n=1,
        category="future",
        data_config={},
        unit_settings={},
        params={},
        optimization_config={},
        gateway_config={},
        trading_mode="paper",
        lock_running=False,
        lock_trading=False,
        trading_instance_id="stale-inst",
        run_status="idle",
        run_count=3,
        trading_snapshot={},
        metrics_snapshot={},
        bar_count=None,
        last_run_time=None,
    )

    monkeypatch.setattr(
        workspace_unit_runtime,
        "sync_trading_unit_runtime",
        lambda *_args, **_kwargs: runtime_dir,
    )

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert user_id == "user-1"
            if instance_id == "stale-inst":
                return None
            assert instance_id == "new-inst"
            return {
                "id": "new-inst",
                "status": "running",
                "pid": 23456,
                "runtime_dir": str(runtime_dir),
                "log_dir": None,
                "error": None,
            }

        def add_instance(self, strategy_id, params, user_id=None, runtime_dir=None):
            assert strategy_id == "simulate/gateway_dual_ma"
            assert user_id == "user-1"
            assert runtime_dir == str(tmp_path / "runtime")
            return {"id": "new-inst"}

        async def start_instance(self, _instance_id):
            raise AssertionError("start_instance should not be called after reattaching PID")

        def remove_instance(self, *_args, **_kwargs):
            raise AssertionError("remove_instance should not be called")

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    results = await TradingWorkspaceService().start_units([unit], user_id="user-1")

    assert results == [
        {
            "unit_id": "unit-1",
            "task_id": "new-inst",
            "status": "running",
            "already_running": True,
        }
    ]
    assert unit.trading_instance_id == "new-inst"
    assert unit.run_status == "running"
    assert unit.run_count == 3
    assert unit.trading_snapshot["instance_status"] == "running"


def test_instance_log_result_falls_back_to_runtime_logs_when_log_dir_missing(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    log_dir = runtime_dir / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "value.log").write_text(
        "dt\tvalue\tcash\n2026-06-25\t100000\t100000\n",
        encoding="utf-8",
    )
    unit = SimpleNamespace(trading_instance_id="inst-1")

    class FakeManager:
        def get_instance(self, instance_id, user_id=None):
            assert instance_id == "inst-1"
            assert user_id == "u1"
            return {
                "id": "inst-1",
                "status": "running",
                "runtime_dir": str(runtime_dir),
                "log_dir": None,
            }

    monkeypatch.setattr(
        trading_workspace_service_module,
        "get_live_trading_manager",
        lambda: FakeManager(),
    )

    result = TradingWorkspaceService._instance_log_result(unit, "u1")

    assert result is not None
    assert result["log_dir"] == str(log_dir)
    assert result["equity_curve"] == [100000.0]


@pytest.mark.asyncio
async def test_daily_summary_counts_trades_once_per_day(monkeypatch):
    unit = SimpleNamespace(trading_instance_id="inst-1")

    def fake_log_result(_unit, _user_id):
        return {
            "equity_dates": ["2026-06-22 09:31:00", "2026-06-22 09:32:00"],
            "equity_curve": [100000.0, 100120.0],
            "drawdown_curve": [0.0, 0.1],
            "initial_cash": 100000.0,
            "trades": [
                {"dtclose": "2026-06-22 09:31:00"},
                {"dtclose": "2026-06-22 09:32:00"},
            ],
        }

    monkeypatch.setattr(
        TradingWorkspaceService,
        "_instance_log_result",
        staticmethod(fake_log_result),
    )

    result = await TradingWorkspaceService().build_daily_summary_response([unit], "u1")

    assert len(result.summaries) == 1
    assert result.summaries[0].trading_date == "2026-06-22"
    assert result.summaries[0].daily_pnl == 120.0
    assert result.summaries[0].cumulative_pnl == 120.0
    assert result.summaries[0].trade_count == 2
