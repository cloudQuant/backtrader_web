#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 MACD Trend Following Strategy.

Trend-following strategy based on MACD:
- Buy when MACD line crosses above the signal line and histogram is positive
- Close when MACD line crosses below the signal line
"""
from __future__ import annotations

import backtrader as bt


class Mt5MACDTrendStrategy(bt.Strategy):
    """MACD trend following strategy for MT5 forex/metals trading.

    Parameters:
        fast_period (int): Fast EMA period (default: 12)
        slow_period (int): Slow EMA period (default: 26)
        signal_period (int): Signal line period (default: 9)
        volume (float): Trade volume in lots (default: 0.01)
    """

    params = (
        ("fast_period", 12),
        ("slow_period", 26),
        ("signal_period", 9),
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
        self.macd = bt.indicators.MACD(
            self.datas[0].close,
            period_me1=self.p.fast_period,
            period_me2=self.p.slow_period,
            period_signal=self.p.signal_period,
        )
        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.order = None
        self.trade_count = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            direction = "BUY" if order.isbuy() else "SELL"
            self.log(f"{direction} executed @ {order.executed.price:.2f}")
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}")
            self.trade_count += 1

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.macd_cross > 0 and self.macd.macd[0] > 0:
                self.order = self.buy(size=self.p.volume)
        else:
            if self.macd_cross < 0:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
