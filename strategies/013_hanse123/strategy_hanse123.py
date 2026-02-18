#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hans123 Intraday Breakout Strategy.

Based on breakout of high/low prices from N bars after market open:
- MA rising AND price > MA AND price breaks upper band -> Go long
- MA falling AND price < MA AND price breaks lower band -> Go short
- Close all positions before market close (14:55)

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class Hans123Strategy(bt.Strategy):
    """Hans123 Intraday Breakout Strategy (with MA filter).

    Uses high/low prices from N bars after market open as breakout range:
    - MA rising + price > MA + price breaks upper band -> Go long
    - MA falling + price < MA + price breaks lower band -> Go short
    - Close positions before market close
    """
    author = 'yunjinqi'
    params = (
        ("ma_period", 200),
        ("bar_num", 2),
    )

    def log(self, txt, dt=None):
        """Log strategy information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the strategy."""
        self.bar_num = 0
        self.day_bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # Calculate MA indicator
        self.ma_value = bt.indicators.SMA(self.datas[0].close, period=self.p.ma_period)
        # Save trading status
        self.marketposition = 0
        # Save current trading day's high, low, and close prices
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # Upper and lower bands
        self.upper_line = None
        self.lower_line = None

    def prenext(self):
        """Called before minimum period is reached."""
        pass

    def next(self):
        """Main strategy logic, called for each bar."""
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

        # If current bar count equals the period for calculating high/low, calculate upper/lower bands
        if self.day_bar_num == self.p.bar_num:
            self.upper_line = self.now_high
            self.lower_line = self.now_low

        # If it's the last minute of current trading day
        if self.current_hour == 15:
            self.now_high = 0
            self.now_low = 999999999
            self.now_close = None
            self.day_bar_num = 0

        # Hans123 improved version: Use MA to filter trades
        if len(data.close) > self.p.ma_period and self.day_bar_num >= self.p.bar_num:
            # Start trading
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            # Open positions
            if open_time_1 or open_time_2:
                # Open long position
                if self.marketposition == 0 and self.ma_value[0] > self.ma_value[-1] and data.close[0] > self.ma_value[0] and data.close[0] > self.upper_line:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.buy(data, size=lots)
                    self.buy_count += 1
                    self.marketposition = 1
                # Open short position
                if self.marketposition == 0 and self.ma_value[0] < self.ma_value[-1] and data.close[0] < self.ma_value[0] and data.close[0] < self.lower_line:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.sell(data, size=lots)
                    self.sell_count += 1
                    self.marketposition = -1
            # Close positions
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
        """Called when a trade is completed."""
        if trade.isclosed:
            self.log(f"Trade completed: pnl={trade.pnl:.2f}, pnlcomm={trade.pnlcomm:.2f}")

    def stop(self):
        """Called when backtesting ends."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")


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
