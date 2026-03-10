#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fei's Four Price Improved Strategy.

An intraday breakout strategy based on Fei's four-price method with Bollinger Band filter:
- Go long when price breaks above Bollinger upper band, middle band is rising, and price breaks previous day's high
- Go short when price breaks below Bollinger lower band, middle band is falling, and price breaks previous day's low
- Close all positions before market close (14:55)

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class FeiStrategy(bt.Strategy):
    """Fei's Four Price Improved Strategy.

    Uses Bollinger Bands as filter:
    - Go long when price breaks above Bollinger upper band, middle band is rising, and price breaks previous day's high
    - Go short when price breaks below Bollinger lower band, middle band is falling, and price breaks previous day's low
    - Close all positions before market close
    """
    author = 'yunjinqi'
    params = (
        ("boll_period", 200),
        ("boll_mult", 2),
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
        # Calculate Bollinger Band indicator
        self.boll_indicator = bt.indicators.BollingerBands(
            self.datas[0], period=self.p.boll_period, devfactor=self.p.boll_mult
        )
        # Save trading status
        self.marketposition = 0
        # Save current trading day's high, low, and close prices
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # Save historical daily high, low, and close price lists
        self.day_high_list = []
        self.day_low_list = []
        self.day_close_list = []

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

        # If it's the last minute of a new trading day
        if self.current_hour == 15:
            self.day_high_list.append(self.now_high)
            self.day_low_list.append(self.now_low)
            self.day_close_list.append(self.now_close)
            self.now_high = 0
            self.now_low = 999999999
            self.now_close = None
            self.day_bar_num = 0

        # Fei's four-price improved version: Use Bollinger Bands as filter
        if len(self.day_high_list) > 1:
            top = self.boll_indicator.top
            bot = self.boll_indicator.bot
            mid = self.boll_indicator.mid
            pre_high = self.day_high_list[-1]
            pre_low = self.day_low_list[-1]

            # Start trading
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            # Open positions
            if open_time_1 or open_time_2:
                # Open long position
                if self.marketposition == 0 and data.close[0] > top[0] and mid[0] > mid[-1] and data.close[0] > pre_high:
                    # Get order size for 1x leverage
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.buy(data, size=lots)
                    self.buy_count += 1
                    self.marketposition = 1
                # Open short position
                if self.marketposition == 0 and mid[0] < mid[-1] and data.close[0] < bot[0] and data.close[0] < pre_low:
                    # Get order size for 1x leverage
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.sell(data, size=lots)
                    self.sell_count += 1
                    self.marketposition = -1

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
