#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 EURUSD Dual MA Crossover Strategy Runner.

模拟交易：连接 MT5 WebSocket 获取实时行情，使用 backtrader 内置 broker 进行模拟交易。
凭证从 config.yaml 读取，策略配置同样从 config.yaml 读取。
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os
import sys
import threading
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
from backtrader.feeds.btapifeed import BtApiFeed
from backtrader.stores.btapistore import BtApiStore

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
logger = logging.getLogger(__name__)

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
    return {
        "exchange_type": gateway.get("exchange_type", "MT5"),
        "asset_type": gateway.get("asset_type", "OTC"),
        "account_id": mt5.get("login", "default"),
        "login": mt5.get("login", ""),
        "password": mt5.get("password", ""),
        "ws_uri": mt5.get("ws_uri", ""),
        "symbol_suffix": mt5.get("symbol_suffix", ""),
        "gateway_start_local_runtime": True,
        "gateway_startup_timeout_sec": 120,
        "gateway_command_timeout_sec": 30,
    }


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
    if not store_cfg.get("login") or not store_cfg.get("password"):
        raise SystemExit(
            "MT5 凭证不完整。请在 config.yaml 中的 mt5 节点配置 login 和 password。"
        )

    print("=" * 60)
    print("MT5 EURUSD MA Cross Strategy")
    print("=" * 60)
    print(f"  Symbol: {symbol}")
    print(f"  Timeframe: {timeframe_str}")
    print(f"  Login: {store_cfg['login']}")
    print(f"  WebSocket: {store_cfg.get('ws_uri', 'default')}")

    store = BtApiStore(provider="mt5_gateway", **store_cfg)
    store.start()
    try:
        data = BtApiFeed(
            store=store,
            dataname=symbol,
            timeframe=bt_timeframe,
            compression=compression,
            backfill_start=True,
        )

        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)

        cerebro = bt.Cerebro(quicknotify=True)
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
            log_positions=True,
            log_indicators=True,
            log_signals=True,
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
        if store.is_connected:
            store.stop()

    print("Strategy finished.")
    return results


if __name__ == "__main__":
    run()
