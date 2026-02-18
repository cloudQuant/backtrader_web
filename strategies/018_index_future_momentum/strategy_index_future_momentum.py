#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Treasury Futures MACD Strategy.

A treasury futures trading strategy based on MACD indicator:
- Fast line crosses above slow line AND MACD > 0 -> Go long
- Fast line crosses below slow line AND MACD < 0 -> Go short
- Supports contract rollover

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class TreasuryFuturesMacdStrategy(bt.Strategy):
    """Treasury Futures MACD Trading Strategy with rollover support.

    This strategy uses MACD indicator for trading and automatically handles contract rollover:
    - Open long position when short-term EMA crosses above long-term EMA and MACD > 0
    - Open short position when short-term EMA crosses below long-term EMA and MACD < 0
    - Close position when price crosses back through short-term EMA
    - Automatically rollover to dominant contract
    """
    # Strategy author
    author = 'yunjinqi'
    # Strategy parameters
    params = (("period_me1", 10),
              ("period_me2", 20),
              ("period_dif", 9),

              )

    def log(self, txt, dt=None):
        """Log strategy information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the strategy and set up indicators."""
        # Common attribute variables
        self.bar_num = 0  # Number of bars run in next()
        self.buy_count = 0
        self.sell_count = 0
        self.current_date = None  # Current trading day
        # Calculate MACD indicator
        self.ema_1 = bt.indicators.ExponentialMovingAverage(self.datas[0].close, period=self.p.period_me1)
        self.ema_2 = bt.indicators.ExponentialMovingAverage(self.datas[0].close, period=self.p.period_me2)
        self.dif = self.ema_1 - self.ema_2
        self.dea = bt.indicators.ExponentialMovingAverage(self.dif, period=self.p.period_dif)
        self.macd = (self.dif - self.dea) * 2
        # Save currently held contract
        self.holding_contract_name = None

    def prenext(self):
        """Called before minimum period is reached."""
        self.next()

    def next(self):
        """Execute main strategy logic."""
        # Increment bar_num and update trading day each run
        self.current_date = bt.num2date(self.datas[0].datetime[0])
        self.bar_num += 1
        data = self.datas[0]
        # Open positions, close existing first
        # Close long position
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size > 0 and \
                data.close[0] < self.ema_1[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.holding_contract_name = None
        # Close short position
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size < 0 and \
                data.close[0] > self.ema_1[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.holding_contract_name = None

        # Open long position
        if self.holding_contract_name is None and self.ema_1[-1] < self.ema_2[-1] and self.ema_1[0] > self.ema_2[0] and \
                self.macd[0] > 0:
            dominant_contract = self.get_dominant_contract()
            next_data = self.getdatabyname(dominant_contract)
            self.buy(next_data, size=1)
            self.buy_count += 1
            self.holding_contract_name = dominant_contract

        # Open short position
        if self.holding_contract_name is None and self.ema_1[-1] > self.ema_2[-1] and self.ema_1[0] < self.ema_2[0] and \
                self.macd[0] < 0:
            dominant_contract = self.get_dominant_contract()
            next_data = self.getdatabyname(dominant_contract)
            self.sell(next_data, size=1)
            self.sell_count += 1
            self.holding_contract_name = dominant_contract

        # Rollover to next contract
        if self.holding_contract_name is not None:
            dominant_contract = self.get_dominant_contract()
            # If a new dominant contract appears, start rollover
            if dominant_contract != self.holding_contract_name:
                # Next dominant contract
                next_data = self.getdatabyname(dominant_contract)
                # Current contract position size and data
                size = self.getpositionbyname(self.holding_contract_name).size  # Position size
                data = self.getdatabyname(self.holding_contract_name)
                # Close old position
                self.close(data)
                # Open new position
                if size > 0:
                    self.buy(next_data, size=abs(size))
                if size < 0:
                    self.sell(next_data, size=abs(size))
                self.holding_contract_name = dominant_contract

    def get_dominant_contract(self):
        """Determine dominant contract (based on open interest)."""
        # Use contract with highest open interest as dominant contract, return data name
        # Can customize how to calculate dominant contract as needed

        # Get currently trading instruments
        target_datas = []
        for data in self.datas[1:]:
            try:
                data_date = bt.num2date(data.datetime[0])
                if self.current_date == data_date:
                    target_datas.append([data._name, data.openinterest[0]])
            except:
                self.log(f"{data._name} not yet listed for trading")

        target_datas = sorted(target_datas, key=lambda x: x[1])
        print(target_datas)
        return target_datas[-1][0]

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
                self.log(
                    f" BUY : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

            else:  # Sell
                self.log(
                    f" SELL : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

    def notify_trade(self, trade):
        """Handle trade lifecycle events."""
        # Output information when trade ends
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def stop(self):
        """Called when backtesting ends."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
