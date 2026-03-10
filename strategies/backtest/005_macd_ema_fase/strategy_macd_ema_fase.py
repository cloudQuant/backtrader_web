#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MACD + EMA futures trend strategy.

Uses MACD golden cross/death cross as entry signals and EMA as stop-loss filter.
This strategy is designed for futures trading with trend-following approach.

Trading Logic:
    - Close long positions when price falls below EMA
    - Close short positions when price rises above EMA
    - Open long when DIF crosses from negative to positive with MACD bar > 0
    - Open short when DIF crosses from positive to negative with MACD bar < 0
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class RbPandasFeed(bt.feeds.PandasData):
    """Pandas data feed for rebar futures data."""

    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', 5),
    )


class MacdEmaStrategy(bt.Strategy):
    """MACD + EMA futures trend strategy.

    Uses MACD golden cross/death cross as entry signals and EMA as stop-loss filter.

    Parameters:
        period_me1 (int): Fast EMA period for MACD (default: 10)
        period_me2 (int): Slow EMA period for MACD (default: 20)
        period_signal (int): Signal line period for MACD (default: 9)
    """

    author = 'yunjinqi'
    params = (
        ("period_me1", 10),
        ("period_me2", 20),
        ("period_signal", 9),
    )

    def log(self, txt, dt=None):
        """Log information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the MACD EMA strategy."""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # MACD indicator
        self.bt_macd_indicator = bt.indicators.MACD(
            self.datas[0],
            period_me1=self.p.period_me1,
            period_me2=self.p.period_me2,
            period_signal=self.p.period_signal
        )
        # EMA indicator
        self.ema = bt.indicators.ExponentialMovingAverage(
            self.datas[0], period=self.p.period_me1
        )

    def prenext(self):
        """Handle the prenext phase before minimum period is reached."""
        pass

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1
        # Get MACD indicator values
        dif = self.bt_macd_indicator.macd
        dea = self.bt_macd_indicator.signal
        # Calculate MACD value for current bar
        macd_value = 2 * (dif[0] - dea[0])
        # Current state
        data = self.datas[0]
        size = self.getposition(self.datas[0]).size

        # Close long position
        if size > 0 and data.close[0] < self.ema[0]:
            self.close(data)
            self.sell_count += 1
            size = 0

        # Close short position
        if size < 0 and data.close[0] > self.ema[0]:
            self.close(data)
            self.buy_count += 1
            size = 0

        # Open long: DIF changes from negative to positive and MACD bar > 0
        if size == 0 and dif[-1] < 0 and dif[0] > 0 and macd_value > 0:
            self.buy(data, size=1)
            self.buy_count += 1

        # Open short: DIF changes from positive to negative and MACD bar < 0
        if size == 0 and dif[-1] > 0 and dif[0] < 0 and macd_value < 0:
            self.sell(data, size=1)
            self.sell_count += 1

    def notify_order(self, order):
        """Handle order status notifications."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: price={order.executed.price:.2f}, cost={order.executed.value:.2f}")
            else:
                self.log(f"SELL: price={order.executed.price:.2f}, cost={order.executed.value:.2f}")

    def notify_trade(self, trade):
        """Handle trade completion notifications."""
        if trade.isclosed:
            self.log(f"Trade completed: gross_profit={trade.pnl:.2f}, net_profit={trade.pnlcomm:.2f}")

    def stop(self):
        """Called when the backtest is finished."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
