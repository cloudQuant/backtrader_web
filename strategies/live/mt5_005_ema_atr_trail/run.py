#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 EMA + ATR Trailing Stop Strategy Runner."""

import os
import sys
from pathlib import Path

import yaml
import backtrader as bt

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategy_mt5_ema_atr_trail import Mt5EmaAtrTrailStrategy


def load_config():
    with open(BASE_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run():
    config = load_config()
    params = config.get("params", {})
    data_cfg = config.get("data", {})
    symbol = data_cfg.get("symbol", "AUDUSD")

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.addstrategy(Mt5EmaAtrTrailStrategy, **params)

    store = bt.stores.BtApiStore(provider="mt5_gateway")
    store.start()

    data = store.getdata(dataname=symbol, timeframe=bt.TimeFrame.Minutes, compression=60)
    cerebro.adddata(data, name=symbol)

    cerebro.broker.setcash(10000)

    print(f"Starting MT5 EMA+ATR Trail strategy on {symbol}...")
    cerebro.run()
    print("Strategy finished.")


if __name__ == "__main__":
    run()
