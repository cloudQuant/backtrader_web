#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ETF Rotation Strategy.

An ETF rotation strategy based on moving average ratio:
- Calculate price/MA ratio for two ETFs
- Clear positions when both ETFs are below their MAs
- Hold the ETF with the higher ratio when at least one is above its MA

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class EtfRotationStrategy(bt.Strategy):
    """ETF Rotation Strategy based on MA ratio.

    This strategy rotates between two ETFs (SSE 50 ETF and ChiNext ETF):
    1. Calculate price/MA ratio for both ETFs
    2. If both ETFs are below their MAs, clear positions
    3. If at least one ETF is above its MA, hold the one with higher ratio
    """
    # Strategy author
    author = 'yunjinqi'
    # Strategy parameters
    params = (("ma_period", 20),)

    def log(self, txt, dt=None):
        """Log strategy information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the ETF rotation strategy."""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # Calculate MA for both ETFs
        self.sz_ma = bt.indicators.SMA(self.datas[0].close, period=self.p.ma_period)
        self.cy_ma = bt.indicators.SMA(self.datas[1].close, period=self.p.ma_period)

    def prenext(self):
        """Called before minimum period is reached."""
        self.next()

    def next(self):
        """Execute core ETF rotation strategy logic."""
        self.bar_num += 1
        # Data for both ETFs
        sz_data = self.datas[0]
        cy_data = self.datas[1]
        # Calculate current positions
        self.sz_pos = self.getposition(sz_data).size
        self.cy_pos = self.getposition(cy_data).size
        # Get current prices for both ETFs
        sz_close = sz_data.close[0]
        cy_close = cy_data.close[0]

        # If both ETFs are below their MAs, clear positions
        if sz_close < self.sz_ma[0] and cy_close < self.cy_ma[0]:
            if self.sz_pos > 0:
                self.close(sz_data)
            if self.cy_pos > 0:
                self.close(cy_data)

        # If at least one ETF is above its MA
        if sz_close > self.sz_ma[0] or cy_close > self.cy_ma[0]:
            # If SSE 50 momentum indicator is higher
            if sz_close / self.sz_ma[0] > cy_close / self.cy_ma[0]:

                # If no current position, buy SSE 50 ETF directly
                if self.sz_pos == 0 and self.cy_pos == 0:
                    # Get account value
                    total_value = self.broker.get_value()
                    # Calculate buy quantity
                    lots = int(0.95 * total_value / sz_close)
                    # Buy
                    self.buy(sz_data, size=lots)
                    self.buy_count += 1

                # If not holding sz but holding cy, close ChiNext ETF and buy sz
                if self.sz_pos == 0 and self.cy_pos > 0:
                    # Close ChiNext ETF
                    self.close(cy_data)
                    self.sell_count += 1
                    # Get account value
                    total_value = self.broker.get_value()
                    # Calculate buy quantity
                    lots = int(0.95 * total_value / sz_close)
                    # Buy
                    self.buy(sz_data, size=lots)
                    self.buy_count += 1

                # If already holding sz, ignore
                if self.sz_pos > 0:
                    pass

            # If ChiNext momentum indicator is higher
            if sz_close / self.sz_ma[0] < cy_close / self.cy_ma[0]:
                # If no current position, buy ChiNext ETF directly
                if self.sz_pos == 0 and self.cy_pos == 0:
                    # Get account value
                    total_value = self.broker.get_value()
                    # Calculate buy quantity
                    lots = int(0.95 * total_value / cy_close)
                    # Buy
                    self.buy(cy_data, size=lots)
                    self.buy_count += 1

                # If not holding cy but holding sz, close SSE 50 ETF and buy cy
                if self.sz_pos > 0 and self.cy_pos == 0:
                    # Close SSE 50 ETF
                    self.close(sz_data)
                    self.sell_count += 1
                    # Get account value
                    total_value = self.broker.get_value()
                    # Calculate buy quantity
                    lots = int(0.95 * total_value / cy_close)
                    # Buy
                    self.buy(cy_data, size=lots)
                    self.buy_count += 1

                # If already holding cy, ignore
                if self.cy_pos > 0:
                    pass

    def notify_order(self, order):
        """Called when order status changes."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Rejected:
            self.log(f"Rejected : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Margin:
            self.log(f"Margin : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Cancelled:
            self.log(f"Cancelled : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Partial:
            self.log(f"Partial : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f" BUY : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

            else:  # Sell
                self.log(f" SELL : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

    def notify_trade(self, trade):
        """Handle trade lifecycle events."""
        # Output information when trade ends
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}' .format(
                            trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} ' .format(
                            trade.getdataname(), trade.price))

    def stop(self):
        """Called when backtesting ends."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
