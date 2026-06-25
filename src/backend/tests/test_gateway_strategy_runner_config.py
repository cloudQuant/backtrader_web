import importlib.util
import json
import os
import time
from pathlib import Path


def _load_runner(strategy_dir: str):
    repo_root = Path(__file__).resolve().parents[3]
    run_path = repo_root / "strategies" / "simulate" / strategy_dir / "run.py"
    spec = importlib.util.spec_from_file_location(f"{strategy_dir}_runner_test", run_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_heartbeat(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _wait_for_heartbeat(path: Path, *, status: str | None = None, after_timestamp: float | None = None) -> dict:
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

    assert module._resolve_heartbeat_interval({"logging": {"heartbeat_interval_seconds": "8"}}) == 8.0
    assert module._resolve_feed_qcheck({}) == 0.5
    assert module._resolve_log_ticks({}) is False
    assert module._resolve_trade_logger_option({}, "log_indicators", False) is False
    assert module._resolve_trade_logger_option({"logging": {"log_indicators": "1"}}, "log_indicators", False) is True
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
