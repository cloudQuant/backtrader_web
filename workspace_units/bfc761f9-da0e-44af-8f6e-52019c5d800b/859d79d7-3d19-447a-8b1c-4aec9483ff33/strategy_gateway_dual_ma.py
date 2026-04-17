#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generic live-paper dual moving average crossover strategy."""

from __future__ import annotations

import backtrader as bt


class GatewayDualMaStrategy(bt.Strategy):
    """Dual moving average crossover strategy for gateway-backed paper trading."""

    params = (
        ("fast_period", 5),
        ("slow_period", 20),
        ("position_size", 1.0),
        ("allow_short", True),
    )

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

    def log(self, message: str, dt=None) -> None:
        if dt is None:
            try:
                dt = bt.num2date(self.datas[0].datetime[0])
            except (IndexError, ValueError):
                dt = None
        prefix = dt.isoformat() if dt else "---"
        print(f"{prefix}, {message}")

    def notify_order(self, order) -> None:
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            direction = "BUY" if order.isbuy() else "SELL"
            self.log(f"{direction} executed @ {order.executed.price:.6f}")
        self.order = None

    def notify_trade(self, trade) -> None:
        if trade.isclosed:
            self.trade_count += 1
            self.log(f"Trade PnL: gross={trade.pnl:.2f}, net={trade.pnlcomm:.2f}")

    def next(self) -> None:
        if self.order:
            return

        size = float(self.p.position_size or 0)
        if size <= 0:
            return

        if not self.position:
            if self.crossover > 0:
                self.order = self.buy(size=size)
            elif self.p.allow_short and self.crossover < 0:
                self.order = self.sell(size=size)
            return

        if self.position.size > 0 and self.crossover < 0:
            if self.p.allow_short:
                self.order = self.sell(size=size * 2)
            else:
                self.order = self.close()
        elif self.position.size < 0 and self.crossover > 0:
            self.order = self.buy(size=size * 2)

    def stop(self) -> None:
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
