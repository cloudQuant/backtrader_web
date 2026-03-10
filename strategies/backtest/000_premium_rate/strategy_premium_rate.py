#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Convertible bond premium rate moving average crossover strategy.

This module implements a trading strategy that uses convertible bond conversion
premium rates to generate trading signals. The strategy calculates moving
averages on the conversion premium rate and executes trades based on
crossover signals.

Trading Logic:
    - Buy signal: Short-term MA crosses above long-term MA
    - Sell signal: Short-term MA crosses below long-term MA (close position)
    - Position sizing: 95% of available cash per trade
    - Commission: 0.03% per trade
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class ExtendPandasFeed(bt.feeds.PandasData):
    """Extended Pandas data feed with convertible bond-specific fields.

    This custom data feed extends the standard Backtrader PandasData feed
    to support convertible bond data with additional fields for pure bond
    value, conversion value, and their respective premium rates.
    """

    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', -1),
        ('pure_bond_value', 5),
        ('convert_value', 6),
        ('pure_bond_premium_rate', 7),
        ('convert_premium_rate', 8)
    )

    lines = ('pure_bond_value', 'convert_value',
             'pure_bond_premium_rate', 'convert_premium_rate')


class PremiumRateCrossoverStrategy(bt.Strategy):
    """Conversion premium rate moving average crossover strategy.

    This strategy implements a dual moving average crossover system using
    convertible bond conversion premium rates as the underlying data series.

    Strategy Logic:
        1. Calculate short-term and long-term moving averages of the
           conversion premium rate
        2. Generate buy signal when short MA crosses above long MA
        3. Generate exit signal when short MA crosses below long MA
        4. Use 95% of available cash for position sizing on entry
        5. Only hold one position at a time (long-only)

    Parameters:
        short_period (int): Period for the short-term moving average (default: 10)
        long_period (int): Period for the long-term moving average (default: 60)
    """

    params = (
        ('short_period', 10),
        ('long_period', 60),
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.premium_rate = self.datas[0].convert_premium_rate
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.premium_rate, period=self.p.short_period
        )
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.premium_rate, period=self.p.long_period
        )
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track execution counts."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute trading logic on each bar."""
        self.bar_num += 1
        if self.order:
            return

        if not self.position:
            if self.crossover > 0:
                cash = self.broker.getcash()
                size = int((cash * 0.95) / self.datas[0].close[0])
                self.order = self.buy(size=size)
        else:
            if self.crossover < 0:
                self.order = self.close()
