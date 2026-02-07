#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sky Garden intraday breakout strategy.

Opens positions based on gap opening and first candlestick high/low breakouts.
Closes positions before market close.

Strategy Logic:
    1. Track daily high/low/close prices
    2. At market close (15:00), store daily data and reset
    3. When sufficient data exists:
       - Record first candlestick high/low
       - Check gap opening conditions (k1 for bullish, k2 for bearish)
       - Enter long if open gaps up and breaks first candlestick high
       - Enter short if open gaps down and breaks first candlestick low
    4. Close all positions at 14:55 before market close

Gap Conditions:
    - Bullish gap: Open > Previous_Close × (1 + k1/1000)
    - Bearish gap: Open < Previous_Close × (1 - k2/1000)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class ZnPandasFeed(bt.feeds.PandasData):
    """Pandas data feed for zinc futures data."""

    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', 5),
    )


class SkyGardenStrategy(bt.Strategy):
    """Sky Garden intraday breakout strategy.

    Opens positions based on gap opening and first candlestick high/low breakouts.
    Closes positions before market close.

    Parameters:
        k1 (int): Bullish gap threshold in thousandths (default: 8 = 0.8%)
        k2 (int): Bearish gap threshold in thousandths (default: 8 = 0.8%)
    """

    author = 'yunjinqi'
    params = (
        ("k1", 8),
        ("k2", 8),
    )

    def log(self, txt, dt=None):
        """Log information with timestamp."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the Sky Garden strategy."""
        self.bar_num = 0
        self.day_bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.pre_date = None
        # Store current trading day's high, low, and close prices
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # Store historical daily high, low, and close prices
        self.day_high_list = []
        self.day_low_list = []
        self.day_close_list = []
        # Store trading status
        self.marketposition = 0
        # High and low prices of the first candlestick
        self.first_bar_high_price = 0
        self.first_bar_low_price = 0

    def prenext(self):
        """Called before minimum period is reached."""
        pass

    def next(self):
        """Execute trading logic for each bar."""
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])
        self.current_hour = self.current_datetime.hour
        self.current_minute = self.current_datetime.minute
        self.day_bar_num += 1
        self.bar_num += 1
        data = self.datas[0]

        # Update high, low, and close prices
        self.now_high = max(self.now_high, data.high[0])
        self.now_low = min(self.now_low, data.low[0])
        if self.now_close is None:
            self.now_open = data.open[0]
        self.now_close = data.close[0]

        # If it's the last minute of a new trading day
        if self.current_hour == 15:
            self.day_high_list.append(self.now_high)
            self.day_low_list.append(self.now_low)
            self.day_close_list.append(self.now_close)
            self.now_high = 0
            self.now_low = 999999999
            self.now_close = None
            self.day_bar_num = 0

        # Sufficient data length, start calculating indicators and trading signals
        if len(self.day_high_list) > 1:
            pre_high = self.day_high_list[-1]
            pre_low = self.day_low_list[-1]
            pre_close = self.day_close_list[-1]

            # Calculate Sky Garden opening conditions
            # If it's the first candlestick at market open
            if self.day_bar_num == 0:
                self.first_bar_high_price = data.high[0]
                self.first_bar_low_price = data.low[0]

            # Start trading
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            close = data.close[0]
            if open_time_1 or open_time_2:
                # Open long position
                if self.marketposition == 0 and self.now_open > pre_close * (self.p.k1 / 1000 + 1) and data.close[0] > self.first_bar_high_price:
                    self.buy(data, size=1)
                    self.buy_count += 1
                    self.marketposition = 1

                # Open short position
                if self.marketposition == 0 and self.now_open < pre_close * (-1 * self.p.k2 / 1000 + 1) and data.close[0] < self.first_bar_low_price:
                    self.sell(data, size=1)
                    self.sell_count += 1
                    self.marketposition = -1

        # Close positions before market close
        if self.marketposition != 0 and self.current_hour == 14 and self.current_minute == 55:
            self.close(data)
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
        """Called when a trade is closed."""
        if trade.isclosed:
            self.log(f"Trade completed: pnl={trade.pnl:.2f}, pnlcomm={trade.pnlcomm:.2f}")

    def stop(self):
        """Called when backtesting is complete."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
