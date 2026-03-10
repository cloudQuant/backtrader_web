#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dual Thrust intraday breakout strategy.

Calculate upper and lower bands based on N-day high/low prices,
open positions on breakout, and close positions before market close.

Strategy Logic:
    1. At market close (15:00), save daily data to history
    2. Calculate upper/lower bands using N-day lookback period
    3. Generate entry signals during trading hours (9-11, 21-23)
    4. Handle position reversals when price crosses bands
    5. Close all positions before market close (14:55)

Formula:
    Range = max(HH - LC, HC - LL)
    Upper Line = Open + k1 × Range
    Lower Line = Open - k2 × Range

Where:
    HH = Highest high in lookback period
    HC = Highest close in lookback period
    LC = Lowest close in lookback period
    LL = Lowest low in lookback period
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class FgPandasFeed(bt.feeds.PandasData):
    """Pandas data feed for glass futures data."""

    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', 5),
    )


class DualThrustStrategy(bt.Strategy):
    """Dual Thrust intraday breakout strategy.

    Parameters:
        look_back_days (int): Number of days for lookback period (default: 10)
        k1 (float): Upper band coefficient (default: 0.5)
        k2 (float): Lower band coefficient (default: 0.5)
    """

    author = 'yunjinqi'
    params = (
        ("look_back_days", 10),
        ("k1", 0.5),
        ("k2", 0.5),
    )

    def log(self, txt, dt=None):
        """Log information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the Dual Thrust strategy with tracking variables."""
        self.bar_num = 0
        self.pre_date = None
        self.buy_count = 0
        self.sell_count = 0
        # Save current trading day's high, low, and close prices
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # Save historical daily high, low, and close prices
        self.day_high_list = []
        self.day_low_list = []
        self.day_close_list = []
        # Save trading status
        self.marketposition = 0

    def prenext(self):
        """Handle prenext phase when minimum period is not yet reached."""
        pass

    def next(self):
        """Execute trading logic for each bar."""
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])
        self.current_hour = self.current_datetime.hour
        self.current_minute = self.current_datetime.minute
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

        # Sufficient data length, start calculating indicators and trading signals
        if len(self.day_high_list) > self.p.look_back_days:
            # Calculate range
            hh = max(self.day_high_list[-1 * self.p.look_back_days:])
            lc = min(self.day_close_list[-1 * self.p.look_back_days:])
            hc = max(self.day_close_list[-1 * self.p.look_back_days:])
            ll = min(self.day_low_list[-1 * self.p.look_back_days:])
            range_price = max(hh - lc, hc - ll)
            # Calculate upper and lower bands
            close = data.close[0]
            upper_line = self.now_open + self.p.k1 * range_price
            lower_line = self.now_open - self.p.k2 * range_price

            # Start trading
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            if open_time_1 or open_time_2:
                # Open long position
                if self.marketposition == 0 and close > upper_line:
                    self.buy(data, size=1)
                    self.buy_count += 1
                    self.marketposition = 1

                # Open short position
                if self.marketposition == 0 and close < lower_line:
                    self.sell(data, size=1)
                    self.sell_count += 1
                    self.marketposition = -1

            # Close long and open short
            if self.marketposition == 1 and close < lower_line:
                self.close(data)
                self.sell(data, size=1)
                self.sell_count += 1
                self.marketposition = -1

            # Close short and open long
            if self.marketposition == -1 and close > upper_line:
                self.close(data)
                self.buy(data, size=1)
                self.buy_count += 1
                self.marketposition = 1

            # Close positions before market close
            if self.marketposition != 0 and self.current_hour == 14 and self.current_minute == 55:
                self.close(data)
                self.marketposition = 0

    def notify_order(self, order):
        """Handle order status updates."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: price={order.executed.price:.2f}")
            else:
                self.log(f"SELL: price={order.executed.price:.2f}")

    def notify_trade(self, trade):
        """Handle trade completion notifications."""
        if trade.isclosed:
            self.log(f"Trade completed: pnl={trade.pnl:.2f}, pnlcomm={trade.pnlcomm:.2f}")

    def stop(self):
        """Log final statistics when backtesting completes."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
