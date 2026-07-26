#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 EURUSD Dual MA Crossover Strategy Runner.

模拟交易：连接 MT5 WebSocket 获取实时行情，使用 backtrader 内置 broker 进行模拟交易。
凭证从 config.yaml 读取，策略配置同样从 config.yaml 读取。
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

_bt_web = Path(__file__).resolve().parents[3]
_bt_project = _bt_web.parent / "backtrader"
if _bt_project.exists() and str(_bt_project) not in sys.path:
    sys.path.insert(0, str(_bt_project))
_bt_api_py = _bt_web.parent / "bt_api_py"
if _bt_api_py.exists() and str(_bt_api_py) not in sys.path:
    sys.path.insert(0, str(_bt_api_py))
_pymt5 = _bt_web.parent / "pymt5"
if _pymt5.exists() and str(_pymt5) not in sys.path:
    sys.path.insert(0, str(_pymt5))

import yaml
import backtrader as bt
try:
    from backtrader.feeds.btapifeed import BtApiFeed
    from backtrader.stores.btapistore import BtApiStore
except ImportError:
    BtApiFeed = None
    BtApiStore = None

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
logger = logging.getLogger(__name__)
HEARTBEAT_FILE_NAME = "heartbeat.json"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0

from strategy_mt5_eurusd_ma_cross import Mt5EurusdMaCrossStrategy


def load_config() -> dict:
    """Load strategy config from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        raise SystemExit("config.yaml 不存在。")
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_mt5_store_config(config: dict) -> dict:
    """从 config.yaml 合并 MT5 连接和 gateway 配置。"""
    mt5 = dict(config.get("mt5", {}) or {})
    gateway = dict(config.get("gateway", {}) or {})
    login = str(
        os.environ.get("MT5_LOGIN")
        or os.environ.get("MT5_ACCOUNT")
        or gateway.get("login")
        or mt5.get("login")
        or ""
    ).strip()
    return {
        "exchange_type": gateway.get("exchange_type", "MT5"),
        "asset_type": gateway.get("asset_type", "OTC"),
        "account_id": os.environ.get("MT5_ACCOUNT_ID") or os.environ.get("MT5_ACCOUNT") or login or "default",
        "login": login,
        "password": str(os.environ.get("MT5_PASSWORD") or os.environ.get("MT5_PASS") or mt5.get("password", "")).strip(),
        "ws_uri": os.environ.get("MT5_WS_URI") or mt5.get("ws_uri", ""),
        "symbol_suffix": os.environ.get("MT5_SYMBOL_SUFFIX") or mt5.get("symbol_suffix", ""),
        "gateway_start_local_runtime": True,
        "gateway_startup_timeout_sec": 120,
        "gateway_command_timeout_sec": 30,
    }


def _safe_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _resolve_heartbeat_interval(config: dict) -> float:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    logging_cfg = dict(config.get("logging") or {})
    gateway = dict(config.get("gateway") or {})
    for section in (live, simulate, logging_cfg, gateway):
        for key in ("heartbeat_interval_seconds", "heartbeat_interval"):
            if key in section:
                return max(_safe_float(section.get(key), DEFAULT_HEARTBEAT_INTERVAL_SECONDS), 1.0)
    return DEFAULT_HEARTBEAT_INTERVAL_SECONDS


def _write_runner_heartbeat(log_dir: Path, started_at: float, status: str = "running") -> None:
    heartbeat_path = log_dir / HEARTBEAT_FILE_NAME
    tmp_path = log_dir / f".{HEARTBEAT_FILE_NAME}.{os.getpid()}.tmp"
    payload = {
        "pid": os.getpid(),
        "status": status,
        "timestamp": time.time(),
        "started_at": started_at,
    }
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, heartbeat_path)
    except OSError as exc:
        logger.debug("Could not write runner heartbeat: %s", exc)
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _start_runner_heartbeat(
    log_dir: Path,
    interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> tuple[threading.Event, threading.Thread]:
    try:
        interval = float(interval_seconds)
    except (TypeError, ValueError):
        interval = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    interval = max(interval, 0.05)
    stop_event = threading.Event()
    started_at = time.time()

    def _loop() -> None:
        while not stop_event.is_set():
            _write_runner_heartbeat(log_dir, started_at, "running")
            stop_event.wait(interval)
        _write_runner_heartbeat(log_dir, started_at, "stopped")

    thread = threading.Thread(target=_loop, name="runner-heartbeat", daemon=True)
    thread.start()
    return stop_event, thread


def _stop_runner_heartbeat(heartbeat: tuple[threading.Event, threading.Thread]) -> None:
    stop_event, thread = heartbeat
    stop_event.set()
    thread.join(timeout=2.0)


def _resolve_feed_qcheck(config: dict) -> float:
    live = dict(config.get("live") or {})
    data = dict(config.get("data") or {})
    gateway = dict(config.get("gateway") or {})
    value = (
        live.get("qcheck")
        or live.get("qcheck_seconds")
        or data.get("qcheck")
        or gateway.get("qcheck")
    )
    return max(_safe_float(value, 0.5), 0.05)


def _resolve_log_ticks(config: dict) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    logging_cfg = dict(config.get("logging") or {})
    value = (
        live.get("log_ticks")
        if live.get("log_ticks") is not None
        else (
            simulate.get("log_ticks")
            if simulate.get("log_ticks") is not None
            else logging_cfg.get("log_ticks")
        )
    )
    return _safe_bool(value, default=False)


def _resolve_trade_logger_option(config: dict, key: str, default: bool) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    logging_cfg = dict(config.get("logging") or {})
    for section in (live, simulate, logging_cfg):
        if key in section:
            return _safe_bool(section.get(key), default=default)
    return default


def _resolve_dispatch_ticks(config: dict) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    gateway = dict(config.get("gateway") or {})
    for section in (live, simulate, gateway):
        for key in ("dispatch_ticks", "notify_ticks"):
            if key in section:
                return _safe_bool(section.get(key), default=False)
    return False


def _resolve_exactbars(config: dict):
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    cerebro_cfg = dict(config.get("cerebro") or {})
    for section in (live, simulate, cerebro_cfg):
        if "exactbars" not in section:
            continue
        value = section.get("exactbars")
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "yes", "on"}:
            return True
        if text in {"false", "no", "off"}:
            return False
        try:
            return int(value)
        except (TypeError, ValueError):
            return _safe_bool(value, default=True)
    return True


def _resolve_stdstats(config: dict) -> bool:
    live = dict(config.get("live") or {})
    simulate = dict(config.get("simulate") or {})
    cerebro_cfg = dict(config.get("cerebro") or {})
    for section in (live, simulate, cerebro_cfg):
        if "stdstats" in section:
            return _safe_bool(section.get("stdstats"), default=False)
    return False


def run():
    """主入口：连接 MT5 运行模拟交易。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = load_config()
    params = config.get("params", {}) or {}
    data_cfg = config.get("data", {}) or {}
    sim_cfg = config.get("simulate", {}) or {}
    symbol = data_cfg.get("symbol", "EURUSD")
    timeframe_str = data_cfg.get("timeframe", "15s")
    sec_map = {"5s": 5, "10s": 10, "15s": 15, "30s": 30, "45s": 45}
    tf_map = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
        "M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440,
    }
    if timeframe_str in sec_map:
        compression = sec_map[timeframe_str]
        bt_timeframe = bt.TimeFrame.Seconds
    else:
        compression = tf_map.get(timeframe_str, 15)
        bt_timeframe = bt.TimeFrame.Minutes
        if compression >= 1440:
            bt_timeframe = bt.TimeFrame.Days
            compression = compression // 1440

    duration_seconds = int(sim_cfg.get("duration_seconds", 86400))
    session_timeout = int(sim_cfg.get("session_timeout", duration_seconds + 100))

    store_cfg = build_mt5_store_config(config)
    if BtApiFeed is None or BtApiStore is None:
        raise SystemExit("Gateway runner requires the bt_api_py Backtrader feed and store adapters")
    if not store_cfg.get("login") or not store_cfg.get("password"):
        raise SystemExit(
            "MT5 凭证不完整。请设置 MT5_LOGIN/MT5_PASSWORD，或在 config.yaml 的 mt5 节点配置 login 和 password。"
        )

    print("=" * 60)
    print("MT5 EURUSD MA Cross Strategy")
    print("=" * 60)
    print(f"  Symbol: {symbol}")
    print(f"  Timeframe: {timeframe_str}")
    print(f"  Login: {store_cfg['login']}")
    print(f"  WebSocket: {store_cfg.get('ws_uri', 'default')}")

    log_dir = BASE_DIR / "logs"
    heartbeat = _start_runner_heartbeat(log_dir, _resolve_heartbeat_interval(config))
    store = None
    try:
        store = BtApiStore(provider="mt5_gateway", **store_cfg)
        store.start()
        data = BtApiFeed(
            store=store,
            dataname=symbol,
            timeframe=bt_timeframe,
            compression=compression,
            backfill_start=True,
            qcheck=_resolve_feed_qcheck(config),
            dispatch_ticks=_resolve_dispatch_ticks(config),
        )

        log_dir.mkdir(exist_ok=True)

        cerebro = bt.Cerebro(
            quicknotify=True,
            exactbars=_resolve_exactbars(config),
            stdstats=_resolve_stdstats(config),
        )
        cerebro.broker.setcash(sim_cfg.get("initial_cash", 10000))
        cerebro.broker.setcommission(commission=sim_cfg.get("commission", 0.00007))
        cerebro.adddata(data, name=symbol)
        cerebro.addstrategy(Mt5EurusdMaCrossStrategy, **params)
        cerebro.addobserver(
            bt.observers.TradeLogger,
            log_dir=str(log_dir),
            log_format="json",
            log_orders=True,
            log_trades=True,
            log_positions=_resolve_trade_logger_option(config, "log_positions", True),
            log_indicators=_resolve_trade_logger_option(config, "log_indicators", False),
            log_signals=_resolve_trade_logger_option(config, "log_signals", True),
            log_ticks=_resolve_log_ticks(config),
        )

        print(f"  启动模拟交易 (timeout={session_timeout}s)...")
        stop_timer = threading.Timer(session_timeout, cerebro.runstop)
        stop_timer.daemon = True
        stop_timer.start()
        try:
            results = cerebro.run()
        finally:
            stop_timer.cancel()
    finally:
        try:
            if store is not None and getattr(store, "is_connected", False):
                store.stop()
        finally:
            _stop_runner_heartbeat(heartbeat)

    print("Strategy finished.")
    return results


if __name__ == "__main__":
    run()
