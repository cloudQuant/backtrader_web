#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Abberation (Bollinger Band breakout) futures strategy.

Go long when breaking through the upper Bollinger Band, go short when breaking
through the lower band. Close long position when falling below the middle band,
close short position when breaking through the middle band.

Strategy Logic:
    1. Open long when price breaks above upper Bollinger Band
    2. Open short when price breaks below lower Bollinger Band
    3. Close long when price falls below middle band
    4. Close short when price rises above middle band

Position Sizing:
    Uses 1x leverage based on total account value
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


class AbberationStrategy(bt.Strategy):
    """Abberation Bollinger Band breakout strategy.

    Go long when breaking through the upper Bollinger Band, go short when breaking
    through the lower band. Close long position when falling below the middle band,
    close short position when breaking through the middle band.

    Parameters:
        boll_period (int): Period for Bollinger Bands calculation (default: 200)
        boll_mult (float): Standard deviation multiplier for bands (default: 2)
    """

    author = 'yunjinqi'
    params = (
        ("boll_period", 200),
        ("boll_mult", 2),
    )

    def log(self, txt, dt=None):
        """Log information function."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the strategy with indicators and state variables."""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # Calculate Bollinger Band indicator
        self.boll_indicator = bt.indicators.BollingerBands(
            self.datas[0], period=self.p.boll_period, devfactor=self.p.boll_mult
        )
        # Save trading status
        self.marketposition = 0

    def prenext(self):
        """Called before minimum period is reached."""
        pass

    def next(self):
        """Called for each bar during backtesting."""
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])
        self.current_hour = self.current_datetime.hour
        self.current_minute = self.current_datetime.minute
        self.bar_num += 1
        data = self.datas[0]

        # Bollinger Band upper rail, lower rail, middle rail
        top = self.boll_indicator.top
        bot = self.boll_indicator.bot
        mid = self.boll_indicator.mid

        # Open long position
        if self.marketposition == 0 and data.close[0] > top[0] and data.close[-1] < top[-1]:
            # Get the number of lots for 1x leverage order
            info = self.broker.getcommissioninfo(data)
            symbol_multi = info.p.mult
            close = data.close[0]
            total_value = self.broker.getvalue()
            lots = total_value / (symbol_multi * close)
            self.buy(data, size=lots)
            self.buy_count += 1
            self.marketposition = 1

        # Open short position
        if self.marketposition == 0 and data.close[0] < bot[0] and data.close[-1] > bot[-1]:
            # Get the number of lots for 1x leverage order
            info = self.broker.getcommissioninfo(data)
            symbol_multi = info.p.mult
            close = data.close[0]
            total_value = self.broker.getvalue()
            lots = total_value / (symbol_multi * close)
            self.sell(data, size=lots)
            self.sell_count += 1
            self.marketposition = -1

        # Close long position
        if self.marketposition == 1 and data.close[0] < mid[0] and data.close[-1] > mid[-1]:
            self.close()
            self.sell_count += 1
            self.marketposition = 0

        # Close short position
        if self.marketposition == -1 and data.close[0] > mid[0] and data.close[-1] < mid[-1]:
            self.close()
            self.buy_count += 1
            self.marketposition = 0

    def notify_order(self, order):
        """Called when order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: price={order.executed.price:.2f}")
            else:
                self.log(f"SELL: price={order.executed.price:.2f}")

    def notify_trade(self, trade):
        """Called when a trade is completed."""
        if trade.isclosed:
            self.log(f"Trade completed: pnl={trade.pnl:.2f}, pnlcomm={trade.pnlcomm:.2f}")

    def stop(self):
        """Called when backtesting ends."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
