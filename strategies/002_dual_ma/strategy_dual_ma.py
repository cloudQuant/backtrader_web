#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dual moving average crossover strategy.

This strategy implements a classic moving average crossover trading system:
- Golden cross: Buy signal when short-term MA crosses above long-term MA
- Death cross: Sell signal when short-term MA crosses below long-term MA

The strategy uses full position sizing (90% of available cash) for each
trade and closes the entire position when a sell signal is generated.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class ExtendPandasFeed(bt.feeds.PandasData):
    """Extended Pandas data feed with convertible bond specific fields."""

    params = (
        ("datetime", None),
        ("open", 0),
        ("high", 1),
        ("low", 2),
        ("close", 3),
        ("volume", 4),
        ("openinterest", -1),
        ("pure_bond_value", 5),
        ("convert_value", 6),
        ("pure_bond_premium_rate", 7),
        ("convert_premium_rate", 8),
    )

    lines = ("pure_bond_value", "convert_value", "pure_bond_premium_rate", "convert_premium_rate")


class TwoMAStrategy(bt.Strategy):
    """Dual moving average crossover strategy.

    Strategy Logic:
        - Golden cross: Buy signal when short MA crosses above long MA
        - Death cross: Sell signal when short MA crosses below long MA
        - Position sizing: 90% of available cash per trade

    Parameters:
        short_period (int): Period for short-term moving average (default: 5)
        long_period (int): Period for long-term moving average (default: 20)
    """

    params = (
        ("short_period", 5),
        ("long_period", 20),
    )

    def log(self, txt, dt=None):
        """Log strategy information with timestamp."""
        if dt is None:
            try:
                dt_val = self.datas[0].datetime[0]
                if dt_val > 0:
                    dt = bt.num2date(dt_val)
                else:
                    dt = None
            except (IndexError, ValueError):
                dt = None

        if dt:
            print("{}, {}".format(dt.isoformat(), txt))
        else:
            print("%s" % txt)

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.short_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.short_period
        )
        self.long_ma = bt.indicators.SimpleMovingAverage(
            self.datas[0].close, period=self.p.long_period
        )

        self.crossover = bt.indicators.CrossOver(self.short_ma, self.long_ma)

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1

        # Golden cross - buy
        if not self.position:
            if self.crossover > 0:
                cash = self.broker.get_cash()
                price = self.datas[0].close[0]
                size = int(cash * 0.9 / price)
                if size > 0:
                    self.buy(size=size)
                    self.buy_count += 1
        else:
            # Death cross - sell
            if self.crossover < 0:
                self.close()
                self.sell_count += 1

    def stop(self):
        """Log final statistics when backtest completes."""
        self.log(
            f"bar_num = {self.bar_num}, buy_count = {self.buy_count}, sell_count = {self.sell_count}"
        )

    def notify_order(self, order):
        """Handle order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: Price={order.executed.price:.2f}, Size={order.executed.size:.2f}")
            else:
                self.log(f"SELL: Price={order.executed.price:.2f}, Size={order.executed.size:.2f}")

    def notify_trade(self, trade):
        """Handle trade completion notifications."""
        if trade.isclosed:
            self.log(f"Trade completed: Gross profit={trade.pnl:.2f}, Net profit={trade.pnlcomm:.2f}")
