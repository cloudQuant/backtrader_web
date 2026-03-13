#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 Dual Moving Average Crossover Strategy.

Classic dual MA crossover for MT5 forex pairs:
- Golden cross (short MA > long MA): open long
- Death cross (short MA < long MA): close long
"""
from __future__ import annotations

import backtrader as bt


class Mt5DualMAStrategy(bt.Strategy):
    """Dual moving average crossover strategy for MT5 forex trading.

    Parameters:
        short_period (int): Short-term MA period (default: 10)
        long_period (int): Long-term MA period (default: 30)
        volume (float): Trade volume in lots (default: 0.01)
    """

    params = (
        ("short_period", 10),
        ("long_period", 30),
        ("volume", 0.01),
    )

    def log(self, txt, dt=None):
        if dt is None:
            try:
                dt = bt.num2date(self.datas[0].datetime[0])
            except (IndexError, ValueError):
                dt = None
        prefix = dt.isoformat() if dt else "---"
        print(f"{prefix}, {txt}")

    def __init__(self):
        self.short_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.short_period
        )
        self.long_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.long_period
        )
        self.crossover = bt.indicators.CrossOver(self.short_ma, self.long_ma)
        self.order = None
        self.trade_count = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY executed @ {order.executed.price:.5f}")
            else:
                self.log(f"SELL executed @ {order.executed.price:.5f}")
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}")
            self.trade_count += 1

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.crossover > 0:
                self.order = self.buy(size=self.p.volume)
        else:
            if self.crossover < 0:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
