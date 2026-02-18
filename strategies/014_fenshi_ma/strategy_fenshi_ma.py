#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Time-Line Moving Average Strategy.

An intraday trading strategy based on time-average price line and moving average filter:
- MA rising AND price > MA AND price breaks above time-average price line -> Go long
- MA falling AND price < MA AND price breaks below time-average price line -> Go short
- Uses trailing stop loss
- Close all positions before market close (14:55)

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class TimeLine(bt.Indicator):
    """Time-average price line indicator.

    Calculates the cumulative average of daily close prices as the time-average price line."""
    lines = ('day_avg_price',)
    params = (("day_end_time", (15, 0, 0)),)

    def __init__(self):
        """Initialize the time-average price line indicator."""
        self.day_close_price_list = []

    def next(self):
        """Calculate current bar's time-average price."""
        self.day_close_price_list.append(self.data.close[0])
        self.lines.day_avg_price[0] = sum(self.day_close_price_list) / len(self.day_close_price_list)

        self.current_datetime = bt.num2date(self.data.datetime[0])
        self.current_hour = self.current_datetime.hour
        self.current_minute = self.current_datetime.minute
        day_end_hour, day_end_minute, _ = self.p.day_end_time
        if self.current_hour == day_end_hour and self.current_minute == day_end_minute:
            self.day_close_price_list = []


class TimeLineMaStrategy(bt.Strategy):
    """Time-Line Moving Average Strategy.

    Uses time-average price line combined with moving average for trading:
    - MA rising + price > MA + price breaks above time-average price line -> Go long
    - MA falling + price < MA + price breaks below time-average price line -> Go short
    - Uses trailing stop loss
    - Close positions before market close
    """
    author = 'yunjinqi'
    params = (
        ("ma_period", 200),
        ("stop_mult", 1),
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
        # Time-average price line indicator
        self.day_avg_price = TimeLine(self.datas[0])
        self.ma_value = bt.indicators.SMA(self.datas[0].close, period=self.p.ma_period)
        # Trading status
        self.marketposition = 0
        # Current trading day's high, low, and close prices
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # Trailing stop loss order
        self.stop_order = None

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
        if self.current_hour == 15:
            self.now_high = 0
            self.now_low = 999999999
            self.now_close = None
            self.day_bar_num = 0

        # Initialize position status
        size = self.getposition(data).size
        if size == 0:
            self.marketposition = 0
            if self.stop_order is not None:
                self.broker.cancel(self.stop_order)
                self.stop_order = None

        # Time-line MA strategy
        if len(data.close) > self.p.ma_period:
            # Start trading
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            # Open positions
            if open_time_1 or open_time_2:
                # Go long
                if self.marketposition == 0 and self.day_bar_num >= 3 and self.ma_value[0] > self.ma_value[-1] and data.close[0] > self.ma_value[0] and data.close[0] > self.day_avg_price[0] and data.close[-1] < self.day_avg_price[-1]:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.buy(data, size=lots)
                    self.buy_count += 1
                    self.marketposition = 1
                    self.stop_order = self.sell(data, size=lots, exectype=bt.Order.StopTrail, trailpercent=self.p.stop_mult / 100)
                # Go short
                if self.marketposition == 0 and self.day_bar_num >= 3 and self.ma_value[0] < self.ma_value[-1] and data.close[0] < self.ma_value[0] and data.close[0] < self.day_avg_price[0] and data.close[-1] > self.day_avg_price[-1]:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.sell(data, size=lots)
                    self.sell_count += 1
                    self.marketposition = -1
                    self.stop_order = self.buy(data, size=lots, exectype=bt.Order.StopTrail, trailpercent=self.p.stop_mult / 100)

            # Signal-based position closing
            # Close long position
            if self.marketposition > 0 and data.close[0] < self.day_avg_price[0] and data.close[0] < self.now_low:
                self.close(data)
                self.marketposition = 0
                if self.stop_order is not None:
                    self.broker.cancel(self.stop_order)
                self.stop_order = None
            # Close short position
            if self.marketposition < 0 and data.close[0] > self.day_avg_price[0] and data.close[0] > self.now_high:
                self.close(data)
                self.marketposition = 0
                if self.stop_order is not None:
                    self.broker.cancel(self.stop_order)
                self.stop_order = None

            # Close positions before market close
            if self.marketposition != 0 and self.current_hour == 14 and self.current_minute == 55:
                self.close(data)
                self.marketposition = 0
                if self.stop_order is not None:
                    self.broker.cancel(self.stop_order)
                self.stop_order = None

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
