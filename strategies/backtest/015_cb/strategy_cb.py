#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Convertible Bond Intraday Strategy.

An intraday trading strategy for convertible bonds based on multi-factor screening:
- Price > 20-period MA
- Price > time-average price line
- Price change between -1% and 1%
- Volume < 4x 30-period average volume
- MA rising but with slowing growth rate

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class ExtendPandasFeed(bt.feeds.PandasData):
    """Extended Pandas data feed for convertible bonds."""
    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', -1),
    )


class ConvertibleBondIntradayStrategy(bt.Strategy):
    """Convertible Bond Multi-Factor Intraday Strategy.

    Uses multiple factors for screening and trading:
    - Price > 20-period MA
    - Price > time-average price line
    - Price change between -1% and 1%
    - Volume < 4x 30-period average volume
    - MA rising but with slowing growth rate
    """
    author = 'yunjinqi'
    params = (
        ("ma_period", 20),
        ("can_trade_num", 2),
    )

    def log(self, txt, dt=None):
        """Log strategy information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the strategy."""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # Maximum number of convertible bonds that can be held simultaneously
        self.can_trade_num = self.p.can_trade_num
        # Calculate 20-period MA for each convertible bond
        self.cb_ma_dict = {data._name: bt.indicators.SMA(data.close, period=self.p.ma_period) for data in self.datas[1:]}
        # Calculate 30-period average volume
        self.cb_avg_volume_dict = {data._name: bt.indicators.SMA(data.volume, period=30) for data in self.datas[1:]}
        # Record previous day's close price
        self.cb_pre_close_dict = {data._name: None for data in self.datas[1:]}
        # Record bar number when opening position
        self.cb_bar_num_dict = {data._name: None for data in self.datas[1:]}
        # Record opening position price
        self.cb_open_position_price_dict = {data._name: None for data in self.datas[1:]}
        # Use lowest point of last 20 periods as previous low
        self.cb_low_point_dict = {data._name: bt.indicators.Lowest(data.low, period=20) for data in self.datas[1:]}

    def prenext(self):
        """Called before minimum period is reached."""
        self.next()

    def next(self):
        """Main strategy logic, called for each bar."""
        self.bar_num += 1
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])

        for data in self.datas[1:]:
            data_datetime = bt.num2date(data.datetime[0])
            if data_datetime == self.current_datetime:
                data_name = data._name
                close_price = data.close[0]

                # Check if previous day's close price exists
                pre_close = self.cb_pre_close_dict[data_name]
                if pre_close is None:
                    pre_close = data.open[0]
                    self.cb_pre_close_dict[data_name] = pre_close

                # Update close price (directly update for daily data)
                self.cb_pre_close_dict[data_name] = close_price

                # Expiration closing logic
                position_size = self.getposition(data).size
                if position_size > 0:
                    try:
                        _ = data.open[2]
                    except:
                        self.close(data)
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                # Prepare to close position
                open_bar_num = self.cb_bar_num_dict[data_name]
                if open_bar_num is not None:
                    # Close position after holding for 10 bars
                    if open_bar_num < self.bar_num - 10:
                        self.close(data)
                        self.sell_count += 1
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                open_bar_num = self.cb_bar_num_dict[data_name]
                if open_bar_num is not None:
                    # Close position if price falls below previous low point
                    low_point = self.cb_low_point_dict[data_name][0]
                    if close_price < low_point:
                        self.close(data)
                        self.sell_count += 1
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                open_bar_num = self.cb_bar_num_dict[data_name]
                if open_bar_num is not None:
                    # Take profit if return exceeds 3%
                    open_position_price = self.cb_open_position_price_dict[data_name]
                    if open_position_price and close_price / open_position_price > 1.03:
                        self.close(data)
                        self.sell_count += 1
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                # Prepare to open position
                ma_line = self.cb_ma_dict[data_name]
                ma_price = ma_line[0]
                if close_price > ma_price:
                    # Check if price change is between -1% and 1%
                    up_percent = close_price / pre_close
                    if up_percent > 0.99 and up_percent < 1.01:
                        # Check if volume is less than 4x average volume
                        volume = data.volume[0]
                        avg_volume = self.cb_avg_volume_dict[data_name][0]
                        if avg_volume > 0 and volume < avg_volume * 4:
                            # MA rising but with slowing growth rate
                            if ma_line[0] > ma_line[-1] and ma_line[0] - ma_line[-1] < ma_line[-1] - ma_line[-2]:
                                open_bar_num = self.cb_bar_num_dict[data_name]
                                if self.can_trade_num > 0 and open_bar_num is None:
                                    total_value = self.broker.getvalue()
                                    plan_tobuy_value = 0.4 * total_value
                                    lots = int(plan_tobuy_value / close_price)
                                    if lots > 0:
                                        self.buy(data, size=lots)
                                        self.buy_count += 1
                                        self.can_trade_num -= 1
                                        self.cb_bar_num_dict[data_name] = self.bar_num
                                        try:
                                            self.cb_open_position_price_dict[data_name] = data.open[1]
                                        except:
                                            self.cb_open_position_price_dict[data_name] = close_price

    def notify_order(self, order):
        """Called when order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: {order.p.data._name} price={order.executed.price:.2f}")
            else:
                self.log(f"SELL: {order.p.data._name} price={order.executed.price:.2f}")

    def notify_trade(self, trade):
        """Called when a trade is completed."""
        if trade.isclosed:
            self.log(f"Trade completed: {trade.getdataname()} pnl={trade.pnl:.2f}")

    def stop(self):
        """Called when backtesting ends."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
