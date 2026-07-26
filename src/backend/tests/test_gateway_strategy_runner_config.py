import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest


def _load_runner(strategy_dir: str):
    repo_root = Path(__file__).resolve().parents[3]
    run_path = repo_root / "strategies" / "simulate" / strategy_dir / "run.py"
    spec = importlib.util.spec_from_file_location(f"{strategy_dir}_runner_test", run_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeBroker:
    def __init__(self):
        self.commission_infos = []
        self.stock_commissions = []

    def addcommissioninfo(self, comminfo, name=None):
        self.commission_infos.append((name, comminfo))

    def setcommission(self, **kwargs):
        self.stock_commissions.append(kwargs)


class _FakeCerebro:
    def __init__(self):
        self.broker = _FakeBroker()


def _read_heartbeat(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _wait_for_heartbeat(
    path: Path, *, status: str | None = None, after_timestamp: float | None = None
) -> dict:
    deadline = time.monotonic() + 2.0
    last_payload: dict = {}
    while time.monotonic() < deadline:
        if path.exists():
            payload = _read_heartbeat(path)
            last_payload = payload
            if status is not None and payload.get("status") != status:
                time.sleep(0.02)
                continue
            if after_timestamp is not None and payload.get("timestamp", 0.0) <= after_timestamp:
                time.sleep(0.02)
                continue
            return payload
        time.sleep(0.02)
    raise AssertionError(f"heartbeat did not reach expected state: {last_payload}")


def test_gateway_runner_disables_tick_logging_by_default():
    module = _load_runner("gateway_dual_ma")

    assert module._resolve_log_ticks({}) is False
    assert module._resolve_trade_logger_option({}, "log_positions", True) is True
    assert module._resolve_trade_logger_option({}, "log_indicators", False) is False
    assert module._resolve_trade_logger_option({}, "log_signals", True) is True
    assert module._resolve_dispatch_ticks({}) is False


def test_gateway_runner_configuration_helpers_import_without_local_backtrader(monkeypatch):
    """Public Backtrader lacks gateway adapters but must not block config inspection."""
    repo_root = Path(__file__).resolve().parents[3]
    local_backtrader = repo_root.parent / "backtrader"
    path_exists = Path.exists

    def _without_local_backtrader(path: Path) -> bool:
        if path == local_backtrader:
            return False
        return path_exists(path)

    for module_name in tuple(sys.modules):
        if module_name == "backtrader" or module_name.startswith("backtrader."):
            monkeypatch.delitem(sys.modules, module_name)
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if Path(entry).resolve() != local_backtrader],
    )
    monkeypatch.setattr(Path, "exists", _without_local_backtrader)
    module = _load_runner("gateway_dual_ma")

    assert module.BtApiFeed is None
    assert module.BtApiStore is None
    assert module._resolve_log_ticks({}) is False


def test_gateway_runner_allows_explicit_live_logging_overrides():
    module = _load_runner("gateway_boll_breakout")

    assert module._resolve_log_ticks({"live": {"log_ticks": True}}) is True
    assert module._resolve_log_ticks({"simulate": {"log_ticks": "1"}}) is True
    assert (
        module._resolve_trade_logger_option(
            {"live": {"log_positions": "0", "log_indicators": "1", "log_signals": False}},
            "log_positions",
            True,
        )
        is False
    )
    assert (
        module._resolve_trade_logger_option(
            {"live": {"log_positions": "0", "log_indicators": "1", "log_signals": False}},
            "log_indicators",
            False,
        )
        is True
    )
    assert (
        module._resolve_trade_logger_option(
            {"live": {"log_positions": "0", "log_indicators": "1", "log_signals": False}},
            "log_signals",
            True,
        )
        is False
    )
    assert module._resolve_dispatch_ticks({"live": {"dispatch_ticks": True}}) is True
    assert module._resolve_dispatch_ticks({"gateway": {"notify_ticks": "1"}}) is True


def test_gateway_runner_defaults_to_memory_bounded_headless_cerebro():
    module = _load_runner("gateway_dual_ma")

    assert module._resolve_exactbars({}) is True
    assert module._resolve_stdstats({}) is False


def test_gateway_runner_prefers_mt5_env_credentials(monkeypatch):
    module = _load_runner("gateway_dual_ma")
    monkeypatch.setenv("MT5_LOGIN", "222222")
    monkeypatch.setenv("MT5_PASSWORD", "env-pass")
    monkeypatch.setenv("MT5_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("MT5_WS_URI", "env-ws")

    runtime = module._build_mt5_store_config(
        {
            "gateway": {
                "login": "333333",
                "password": "gateway-pass",
                "account_id": "gateway-account",
                "ws_uri": "gateway-ws",
            },
            "mt5": {"login": "111111", "password": "config-pass", "ws_uri": "config-ws"},
        },
        "mt5_gateway",
        "OTC",
    )

    assert runtime["config"]["login"] == "222222"
    assert runtime["config"]["password"] == "env-pass"
    assert runtime["config"]["account_id"] == "env-account"
    assert runtime["config"]["ws_uri"] == "env-ws"


def test_gateway_runner_store_configs_include_strategy_identity(monkeypatch):
    for strategy_dir in ("gateway_dual_ma", "gateway_boll_breakout"):
        module = _load_runner(strategy_dir)
        config = {"workspace_unit": {"unit_id": "unit-42"}}
        monkeypatch.delenv("BT_TRADING_INSTANCE_ID", raising=False)

        assert (
            module._merge_gateway_env_config(config, "ctp_gateway", "CTP", "FUTURE")["config"][
                "strategy_id"
            ]
            == "unit-42"
        )
        assert (
            module._build_ctp_store_config(config, "ctp_gateway", "FUTURE")["config"]["strategy_id"]
            == "unit-42"
        )
        assert (
            module._build_ib_store_config(config, "ib_gateway", "STK")["config"]["strategy_id"]
            == "unit-42"
        )
        assert (
            module._build_mt5_store_config(config, "mt5_gateway", "OTC")["config"]["strategy_id"]
            == "unit-42"
        )

        monkeypatch.setenv("BT_TRADING_INSTANCE_ID", "inst-42")
        assert (
            module._merge_gateway_env_config(config, "ctp_gateway", "CTP", "FUTURE")["config"][
                "strategy_id"
            ]
            == "inst-42"
        )


def test_gateway_runner_contract_commission_uses_exchange_fee_and_fixed_margin():
    for strategy_dir in ("gateway_dual_ma", "gateway_boll_breakout"):
        module = _load_runner(strategy_dir)
        cerebro = _FakeCerebro()

        module._apply_contract_commission(
            cerebro,
            {
                "data": {
                    "asset_type": "future",
                    "contract_metadata": {
                        "IF2609": {
                            "VolumeMultiple": 300,
                            "margin_initial": 150000,
                            "OpenRatioByMoney": 0.23,
                            "CloseRatioByMoney": 0.3,
                            "CloseTodayRatioByMoney": 3.45,
                            "OpenRatioByVolume": 1.2,
                            "CloseRatioByVolume": 2.0,
                            "CloseTodayRatioByVolume": 4.5,
                        }
                    },
                }
            },
            "IF2609",
        )

        assert cerebro.broker.stock_commissions == []
        assert len(cerebro.broker.commission_infos) == 1
        name, comminfo = cerebro.broker.commission_infos[0]
        assert name == "IF2609"
        assert comminfo.get_param("mult") == pytest.approx(300.0)
        assert comminfo.get_param("commission") == pytest.approx(0.000023)
        assert comminfo.get_margin(5000.0) == pytest.approx(150000.0)
        assert comminfo.getcommission(1, 5000.0, role="open") == pytest.approx(35.7)
        assert comminfo.getcommission(1, 5000.0, role="close") == pytest.approx(47.0)
        assert comminfo.getcommission(1, 5000.0, role="close_today") == pytest.approx(522.0)


def test_gateway_runner_contract_commission_preserves_okx_maker_taker_rates():
    for strategy_dir in ("gateway_dual_ma", "gateway_boll_breakout"):
        module = _load_runner(strategy_dir)
        cerebro = _FakeCerebro()

        module._apply_contract_commission(
            cerebro,
            {
                "data": {
                    "asset_type": "swap",
                    "contract_metadata": {
                        "BTC-USDT-SWAP": {
                            "multiplier": 0.01,
                            "margin_rate": 0.1,
                            "commission_rate": 0.0005,
                            "maker_commission_rate": -0.0002,
                            "taker_commission_rate": 0.0005,
                        }
                    },
                }
            },
            "BTC-USDT-SWAP",
        )

        assert cerebro.broker.stock_commissions == []
        assert len(cerebro.broker.commission_infos) == 1
        name, comminfo = cerebro.broker.commission_infos[0]
        assert name == "BTC-USDT-SWAP"
        assert comminfo.get_param("mult") == pytest.approx(0.01)
        assert comminfo.getcommission(10, 60000.0, role="maker") == pytest.approx(-1.2)
        assert comminfo.getcommission(10, 60000.0, role="taker") == pytest.approx(3.0)
        assert comminfo.getcommission(10, 60000.0) == pytest.approx(3.0)


def test_gateway_runner_contract_commission_uses_inverse_comminfo():
    for strategy_dir in ("gateway_dual_ma", "gateway_boll_breakout"):
        module = _load_runner(strategy_dir)
        cerebro = _FakeCerebro()

        module._apply_contract_commission(
            cerebro,
            {
                "data": {
                    "asset_type": "swap",
                    "contract_metadata": {
                        "BTC-USD-SWAP": {
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
                            "maker_commission_rate": -0.0001,
                        }
                    },
                }
            },
            "BTC-USD-SWAP",
        )

        assert cerebro.broker.stock_commissions == []
        assert len(cerebro.broker.commission_infos) == 1
        name, comminfo = cerebro.broker.commission_infos[0]
        assert name == "BTC-USD-SWAP"
        assert comminfo.__class__.__name__ == "ComminfoFuturesInverse"
        assert comminfo.get_param("mult") == pytest.approx(100.0)
        assert comminfo.get_margin(50000.0) == pytest.approx(10.0)
        assert comminfo.getoperationcost(100, 50000.0) == pytest.approx(1000.0)
        assert comminfo.getcommission(100, 50000.0) == pytest.approx(5.0)
        assert comminfo.getcommission(100, 50000.0, role="maker") == pytest.approx(-1.0)
        assert comminfo.profitandloss(100, 50000.0, 55000.0) == pytest.approx(1000.0)


def test_gateway_runner_allows_cerebro_memory_overrides():
    module = _load_runner("gateway_boll_breakout")

    assert module._resolve_exactbars({"live": {"exactbars": "0"}}) == 0
    assert module._resolve_exactbars({"simulate": {"exactbars": "-1"}}) == -1
    assert module._resolve_exactbars({"cerebro": {"exactbars": False}}) is False
    assert module._resolve_stdstats({"live": {"stdstats": "1"}}) is True


def test_gateway_runner_writes_periodic_heartbeat(tmp_path):
    module = _load_runner("gateway_dual_ma")
    heartbeat_path = tmp_path / module.HEARTBEAT_FILE_NAME

    heartbeat = module._start_runner_heartbeat(tmp_path, interval_seconds=0.05)
    try:
        first = _wait_for_heartbeat(heartbeat_path, status="running")
        second = _wait_for_heartbeat(
            heartbeat_path,
            status="running",
            after_timestamp=float(first["timestamp"]),
        )
    finally:
        module._stop_runner_heartbeat(heartbeat)

    stopped = _wait_for_heartbeat(heartbeat_path, status="stopped")
    assert first["pid"] == os.getpid()
    assert second["pid"] == os.getpid()
    assert stopped["pid"] == os.getpid()
    assert stopped["started_at"] == first["started_at"]
    assert heartbeat[1].is_alive() is False


def test_gateway_runner_resolves_heartbeat_interval_from_config():
    module = _load_runner("gateway_boll_breakout")

    assert module._resolve_heartbeat_interval({}) == 30.0
    assert module._resolve_heartbeat_interval({"live": {"heartbeat_interval_seconds": "5"}}) == 5.0
    assert module._resolve_heartbeat_interval({"simulate": {"heartbeat_interval": "0.1"}}) == 1.0


def test_mt5_runner_defaults_to_memory_bounded_headless_live_mode():
    module = _load_runner("mt5_eurusd_ma_cross")

    assert (
        module._resolve_heartbeat_interval({"logging": {"heartbeat_interval_seconds": "8"}}) == 8.0
    )
    assert module._resolve_feed_qcheck({}) == 0.5
    assert module._resolve_log_ticks({}) is False
    assert module._resolve_trade_logger_option({}, "log_indicators", False) is False
    assert (
        module._resolve_trade_logger_option(
            {"logging": {"log_indicators": "1"}}, "log_indicators", False
        )
        is True
    )
    assert module._resolve_dispatch_ticks({}) is False
    assert module._resolve_exactbars({}) is True
    assert module._resolve_stdstats({}) is False
    assert module._resolve_dispatch_ticks({"gateway": {"notify_ticks": "1"}}) is True


def test_mt5_runner_prefers_env_credentials(monkeypatch):
    module = _load_runner("mt5_eurusd_ma_cross")
    monkeypatch.setenv("MT5_LOGIN", "222222")
    monkeypatch.setenv("MT5_PASSWORD", "env-pass")
    monkeypatch.setenv("MT5_ACCOUNT_ID", "env-account")
    monkeypatch.setenv("MT5_WS_URI", "env-ws")

    store_cfg = module.build_mt5_store_config(
        {
            "gateway": {"login": "333333", "exchange_type": "MT5", "asset_type": "OTC"},
            "mt5": {"login": "111111", "password": "config-pass", "ws_uri": "config-ws"},
        }
    )

    assert store_cfg["login"] == "222222"
    assert store_cfg["password"] == "env-pass"
    assert store_cfg["account_id"] == "env-account"
    assert store_cfg["ws_uri"] == "env-ws"
