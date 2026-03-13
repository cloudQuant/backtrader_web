#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 XAUUSD Range Breakout Strategy.

Breakout strategy based on the highest high and lowest low of the last N bars:
- Buy when price breaks above the N-bar high
- Close when price falls below the N-bar low
"""
from __future__ import annotations

import backtrader as bt


class Mt5XauusdBreakoutStrategy(bt.Strategy):
    """Range breakout strategy for XAUUSD on H1.

    Parameters:
        lookback (int): Number of bars for high/low range (default: 20)
        volume (float): Trade volume in lots (default: 0.01)
        stop_loss_pips (int): Stop loss in pips (default: 200)
        take_profit_pips (int): Take profit in pips (default: 400)
    """

    params = (
        ("lookback", 20),
        ("volume", 0.01),
        ("stop_loss_pips", 200),
        ("take_profit_pips", 400),
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
        self.highest = bt.indicators.Highest(
            self.datas[0].high, period=self.p.lookback
        )
        self.lowest = bt.indicators.Lowest(
            self.datas[0].low, period=self.p.lookback
        )
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
            if self.datas[0].close[0] > self.highest[-1]:
                self.order = self.buy(size=self.p.volume)
        else:
            if self.datas[0].close[0] < self.lowest[-1]:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
