#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 Bollinger Bands Breakout Strategy.

Breakout strategy based on Bollinger Bands:
- Buy when price closes above the upper band
- Close when price falls back below the middle band
"""
from __future__ import annotations

import backtrader as bt


class Mt5BollBreakoutStrategy(bt.Strategy):
    """Bollinger Bands breakout strategy for MT5 forex trading.

    Parameters:
        boll_period (int): Bollinger Bands period (default: 20)
        boll_dev (float): Standard deviation multiplier (default: 2.0)
        volume (float): Trade volume in lots (default: 0.01)
    """

    params = (
        ("boll_period", 20),
        ("boll_dev", 2.0),
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
        self.boll = bt.indicators.BollingerBands(
            self.datas[0].close,
            period=self.p.boll_period,
            devfactor=self.p.boll_dev,
        )
        self.order = None
        self.trade_count = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            direction = "BUY" if order.isbuy() else "SELL"
            self.log(f"{direction} executed @ {order.executed.price:.5f}")
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}")
            self.trade_count += 1

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.datas[0].close[0] > self.boll.lines.top[0]:
                self.order = self.buy(size=self.p.volume)
        else:
            if self.datas[0].close[0] < self.boll.lines.mid[0]:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
