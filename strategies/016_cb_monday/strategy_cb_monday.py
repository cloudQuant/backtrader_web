#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Convertible Bond Friday Rotation Strategy.

Every Friday, buy the 3 convertible bonds with the highest premium rates:
- Close existing positions every Friday
- Select the 3 convertible bonds with the highest premium rates to buy
- Hold until next Friday for rebalancing

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class ExtendPandasFeed(bt.feeds.PandasData):
    """Extended Pandas data feed for convertible bonds (with premium rate)."""
    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', -1),
        ('premium_rate', 5),
    )
    lines = ('premium_rate',)


class ConvertibleBondFridayRotationStrategy(bt.Strategy):
    """Convertible Bond Friday High Premium Rotation Strategy.

    Every Friday:
    - Close existing positions
    - Buy the 3 convertible bonds with the highest premium rates
    - Hold until next Friday
    """
    author = 'yunjinqi'
    params = (
        ("hold_num", 3),
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
        self.data_order_dict = {}
        self.order_list = []

    def prenext(self):
        """Called before minimum period is reached."""
        self.next()

    def next(self):
        """Main strategy logic, called for each bar."""
        self.bar_num += 1
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])
        total_value = self.broker.get_value()
        available_cash = self.broker.get_cash()

        # If today is Friday, start closing existing positions and prepare new orders
        today = self.current_datetime.weekday() + 1

        if today == 5:
            # Close existing positions
            for data, order in self.order_list:
                size = self.getposition(data).size
                if size > 0:
                    self.close(data)
                    self.sell_count += 1
                if size == 0:
                    self.cancel(order)
            self.order_list = []

            # Collect currently tradable convertible bonds
            result = []
            for data in self.datas[1:]:
                data_datetime = bt.num2date(data.datetime[0])
                if data_datetime == self.current_datetime:
                    data_name = data._name
                    premium_rate = data.premium_rate[0]
                    result.append([data, premium_rate])

            # Sort by premium rate
            sorted_result = sorted(result, key=lambda x: x[1])

            # Buy the ones with highest premium rates
            for data, _ in sorted_result[-self.p.hold_num:]:
                close_price = data.close[0]
                total_value = self.broker.getvalue()
                plan_tobuy_value = 0.1 * total_value
                lots = 10 * int(plan_tobuy_value / (close_price * 10))
                if lots > 0:
                    order = self.buy(data, size=lots)
                    self.buy_count += 1
                    self.order_list.append([data, order])

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
