#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 EMA + ATR Trailing Stop Strategy.

Trend-following strategy with dynamic trailing stop:
- Buy when price is above EMA (uptrend)
- Use ATR-based trailing stop to lock in profits
- Exit when price drops below trailing stop level
"""
from __future__ import annotations

import backtrader as bt


class Mt5EmaAtrTrailStrategy(bt.Strategy):
    """EMA trend + ATR trailing stop strategy for MT5 forex trading.

    Parameters:
        ema_period (int): EMA trend filter period (default: 50)
        atr_period (int): ATR period for stop calculation (default: 14)
        atr_multiplier (float): ATR multiplier for trailing stop distance (default: 2.0)
        volume (float): Trade volume in lots (default: 0.01)
    """

    params = (
        ("ema_period", 50),
        ("atr_period", 14),
        ("atr_multiplier", 2.0),
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
        self.ema = bt.indicators.ExponentialMovingAverage(
            self.datas[0].close, period=self.p.ema_period
        )
        self.atr = bt.indicators.AverageTrueRange(
            self.datas[0], period=self.p.atr_period
        )
        self.order = None
        self.trail_stop = 0.0
        self.highest_since_entry = 0.0
        self.trade_count = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            direction = "BUY" if order.isbuy() else "SELL"
            self.log(f"{direction} executed @ {order.executed.price:.5f}")
            if order.isbuy():
                self.highest_since_entry = order.executed.price
                self.trail_stop = order.executed.price - self.atr[0] * self.p.atr_multiplier
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}")
            self.trade_count += 1

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.datas[0].close[0] > self.ema[0]:
                self.order = self.buy(size=self.p.volume)
        else:
            current_high = self.datas[0].high[0]
            if current_high > self.highest_since_entry:
                self.highest_since_entry = current_high
                self.trail_stop = self.highest_since_entry - self.atr[0] * self.p.atr_multiplier

            if self.datas[0].close[0] < self.trail_stop:
                self.log(f"Trail stop hit @ {self.trail_stop:.5f}")
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
