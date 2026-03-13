#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 AUDUSD RSI Pullback Entry Strategy.

Mean-reversion strategy based on RSI oversold/overbought levels:
- Buy when RSI drops below the oversold threshold (pullback entry)
- Close when RSI rises above the overbought threshold
"""
from __future__ import annotations

import backtrader as bt


class Mt5AudusdRsiPullbackStrategy(bt.Strategy):
    """RSI pullback entry strategy for AUDUSD on M15.

    Parameters:
        rsi_period (int): RSI calculation period (default: 14)
        oversold (int): Oversold threshold to trigger buy (default: 30)
        overbought (int): Overbought threshold to trigger sell (default: 70)
        volume (float): Trade volume in lots (default: 0.01)
    """

    params = (
        ("rsi_period", 14),
        ("oversold", 30),
        ("overbought", 70),
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
        self.rsi = bt.indicators.RelativeStrengthIndex(
            self.datas[0].close, period=self.p.rsi_period
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
            if self.rsi[0] < self.p.oversold:
                self.order = self.buy(size=self.p.volume)
        else:
            if self.rsi[0] > self.p.overbought:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
