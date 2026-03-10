#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R-Breaker intraday breakout strategy.

Calculate Pivot, R1/R3, S1/S3 price levels based on previous day's
high, low, and close. Open positions on breakouts, close positions
before market close.

Price Levels:
    Pivot = (High + Low + Close) / 3
    R1 = Pivot + k1 × (High - Low)
    R3 = Pivot + (k1 + k2) × (High - Low)
    S1 = Pivot - k1 × (High - Low)
    S3 = Pivot - (k1 + k2) × (High - Low)

Trading Logic:
    - Long: Price breaks above R3
    - Short: Price breaks below S3
    - Reverse long to short at R1
    - Reverse short to long at S1
    - Close all positions at 14:55
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


class RBreakerStrategy(bt.Strategy):
    """R-Breaker intraday breakout strategy.

    Calculate Pivot, R1/R3, S1/S3 price levels based on previous day's
    high, low, and close. Open positions on breakouts, close positions
    before market close.

    Parameters:
        k1 (float): Coefficient for R1/S1 calculation (default: 0.5)
        k2 (float): Additional coefficient for R3/S3 calculation (default: 0.5)
    """

    author = 'yunjinqi'
    params = (
        ("k1", 0.5),
        ("k2", 0.5),
    )

    def log(self, txt, dt=None):
        """Log strategy information with timestamp."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize R-Breaker strategy with tracking variables."""
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
        """Handle bars before minimum period is reached."""
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
        if len(self.day_high_list) > 1:
            pre_high = self.day_high_list[-1]
            pre_low = self.day_low_list[-1]
            pre_close = self.day_close_list[-1]
            pivot = (pre_high + pre_low + pre_close) / 3
            r1 = pivot + (self.p.k1) * (pre_high - pre_low)
            r3 = pivot + (self.p.k1 + self.p.k2) * (pre_high - pre_low)
            s1 = pivot - (self.p.k1) * (pre_high - pre_low)
            s3 = pivot - (self.p.k1 + self.p.k2) * (pre_high - pre_low)

            # Start trading
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            close = data.close[0]
            if open_time_1 or open_time_2:
                # Open long position
                if self.marketposition == 0 and close > r3:
                    self.buy(data, size=1)
                    self.buy_count += 1
                    self.marketposition = 1

                # Open short position
                if self.marketposition == 0 and close < s3:
                    self.sell(data, size=1)
                    self.sell_count += 1
                    self.marketposition = -1

                # Close long and open short
                if self.marketposition == 1 and close < r1:
                    self.close(data)
                    self.sell(data, size=1)
                    self.sell_count += 1
                    self.marketposition = -1

                # Close short and open long
                if self.marketposition == -1 and close > s1:
                    self.close(data)
                    self.buy(data, size=1)
                    self.buy_count += 1
                    self.marketposition = 1

        # Close position before market close
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
