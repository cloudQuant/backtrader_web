#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 USDJPY ADX Trend Following Strategy.

Trend-following strategy based on ADX and Directional Indicators:
- Buy when ADX > threshold and +DI > -DI (strong uptrend)
- Close when ADX drops below threshold or +DI < -DI (trend weakens)
"""
from __future__ import annotations

import backtrader as bt


class Mt5UsdjpyTrendFollowStrategy(bt.Strategy):
    """ADX trend following strategy for USDJPY on H4.

    Parameters:
        adx_period (int): ADX calculation period (default: 14)
        adx_threshold (int): Minimum ADX value for trend strength (default: 25)
        volume (float): Trade volume in lots (default: 0.01)
    """

    params = (
        ("adx_period", 14),
        ("adx_threshold", 25),
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
        self.adx = bt.indicators.AverageDirectionalMovementIndex(
            self.datas[0], period=self.p.adx_period
        )
        self.plus_di = bt.indicators.PlusDirectionalIndicator(
            self.datas[0], period=self.p.adx_period
        )
        self.minus_di = bt.indicators.MinusDirectionalIndicator(
            self.datas[0], period=self.p.adx_period
        )
        self.order = None
        self.trade_count = 0

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            direction = "BUY" if order.isbuy() else "SELL"
            self.log(f"{direction} executed @ {order.executed.price:.3f}")
        self.order = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.log(f"Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}")
            self.trade_count += 1

    def next(self):
        if self.order:
            return

        if not self.position:
            if self.adx[0] > self.p.adx_threshold and self.plus_di[0] > self.minus_di[0]:
                self.order = self.buy(size=self.p.volume)
        else:
            if self.adx[0] < self.p.adx_threshold or self.plus_di[0] < self.minus_di[0]:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
