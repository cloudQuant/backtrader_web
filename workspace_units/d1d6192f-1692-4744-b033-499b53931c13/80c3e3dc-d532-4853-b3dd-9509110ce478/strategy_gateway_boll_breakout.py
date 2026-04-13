#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generic live-paper Bollinger breakout strategy."""

from __future__ import annotations

import backtrader as bt


class GatewayBollBreakoutStrategy(bt.Strategy):
    """Bollinger breakout strategy with optional long/short entries."""

    params = (
        ("boll_period", 20),
        ("boll_dev", 2.0),
        ("position_size", 1.0),
        ("allow_short", True),
    )

    def __init__(self):
        self.boll = bt.indicators.BollingerBands(
            self.datas[0].close,
            period=self.p.boll_period,
            devfactor=self.p.boll_dev,
        )
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

        close_price = self.datas[0].close[0]
        upper = self.boll.top[0]
        middle = self.boll.mid[0]
        lower = self.boll.bot[0]

        if not self.position:
            if close_price > upper:
                self.order = self.buy(size=size)
            elif self.p.allow_short and close_price < lower:
                self.order = self.sell(size=size)
            return

        if self.position.size > 0 and close_price < middle:
            self.order = self.close()
        elif self.position.size < 0 and close_price > middle:
            self.order = self.close()

    def stop(self) -> None:
        self.log(f"Strategy finished. Total trades: {self.trade_count}")
