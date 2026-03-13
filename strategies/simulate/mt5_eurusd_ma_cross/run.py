#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 EURUSD Dual MA Crossover Strategy Runner."""

import os
import sys
from pathlib import Path, Path as _Path

# Add local backtrader + bt_api_py to sys.path so BtApiStore is importable
_bt_web = _Path(__file__).resolve().parents[3]
_bt_project = _bt_web.parent / "backtrader"
if _bt_project.exists() and str(_bt_project) not in sys.path:
    sys.path.insert(0, str(_bt_project))
_bt_api_py = _bt_web.parent / "bt_api_py"
if _bt_api_py.exists() and str(_bt_api_py) not in sys.path:
    sys.path.insert(0, str(_bt_api_py))

import yaml
import backtrader as bt

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategy_mt5_eurusd_ma_cross import Mt5EurusdMaCrossStrategy


def load_config():
    with open(BASE_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run():
    config = load_config()
    params = config.get("params", {})
    data_cfg = config.get("data", {})
    symbol = data_cfg.get("symbol", "EURUSD")

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.addstrategy(Mt5EurusdMaCrossStrategy, **params)

    store = bt.stores.BtApiStore(provider="mt5_gateway")
    store.start()

    data = store.getdata(dataname=symbol, timeframe=bt.TimeFrame.Minutes, compression=15)
    cerebro.adddata(data, name=symbol)

    sim_cfg = config.get("simulate", {})
    cerebro.broker.setcash(sim_cfg.get("initial_cash", 10000))
    cerebro.broker.setcommission(commission=sim_cfg.get("commission", 0.00007))

    print(f"Starting MT5 EURUSD MA Cross strategy on {symbol}...")
    cerebro.run()
    print("Strategy finished.")


if __name__ == "__main__":
    run()
