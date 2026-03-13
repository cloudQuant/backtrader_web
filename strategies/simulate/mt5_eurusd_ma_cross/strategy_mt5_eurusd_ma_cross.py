#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MT5 EURUSD Dual MA Crossover Strategy.

Classic dual moving average crossover for EURUSD on M15:
- Buy when fast MA (10) crosses above slow MA (30)
- Close when fast MA crosses below slow MA
"""
from __future__ import annotations

import backtrader as bt


class Mt5EurusdMaCrossStrategy(bt.Strategy):
    """Dual MA crossover strategy for EURUSD on M15.

    Parameters:
        fast_period (int): Fast MA period (default: 10)
        slow_period (int): Slow MA period (default: 30)
        lot_size (float): Trade volume in lots (default: 0.01)
        stop_loss_pips (int): Stop loss in pips (default: 30)
        take_profit_pips (int): Take profit in pips (default: 50)
    """

    params = (
        ("fast_period", 10),
        ("slow_period", 30),
        ("lot_size", 0.01),
        ("stop_loss_pips", 30),
        ("take_profit_pips", 50),
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
        self.fast_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.fast_period
        )
        self.slow_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.slow_period
        )
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
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
            if self.crossover > 0:
                self.order = self.buy(size=self.p.lot_size)
        else:
            if self.crossover < 0:
                self.order = self.close()

    def stop(self):
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
