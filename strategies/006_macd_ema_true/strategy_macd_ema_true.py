#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MACD EMA Multi-Contract Futures Trend Strategy.

Uses custom MACD indicator (aligned with domestic Chinese standards).
Supports rollover logic for contract expiration.

Strategy Logic:
    1. Close existing positions when price crosses EMA
    2. Open long positions on MACD golden cross with positive MACD
    3. Open short positions on MACD death cross with negative MACD
    4. Handle contract rollover when dominant contract changes
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


class MacdEmaTrueStrategy(bt.Strategy):
    """MACD + EMA Multi-Contract Futures Trend Strategy.

    Uses custom MACD indicator (aligned with domestic Chinese standards).
    Supports rollover logic for contract expiration.

    Parameters:
        period_me1 (int): Fast EMA period (default: 10)
        period_me2 (int): Slow EMA period (default: 20)
        period_dif (int): DIF EMA period (default: 9)
    """

    author = 'yunjinqi'
    params = (
        ("period_me1", 10),
        ("period_me2", 20),
        ("period_dif", 9),
    )

    def log(self, txt, dt=None):
        """Logs information with timestamp."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the MACD EMA strategy with indicators and tracking variables."""
        self.bar_num = 0
        self.current_date = None
        self.buy_count = 0
        self.sell_count = 0
        # Calculate MACD indicator
        self.ema_1 = bt.indicators.ExponentialMovingAverage(self.datas[0].close, period=self.p.period_me1)
        self.ema_2 = bt.indicators.ExponentialMovingAverage(self.datas[0].close, period=self.p.period_me2)
        self.dif = self.ema_1 - self.ema_2
        self.dea = bt.indicators.ExponentialMovingAverage(self.dif, period=self.p.period_dif)
        self.macd = (self.dif - self.dea) * 2
        # Track which contract is currently held
        self.holding_contract_name = None

    def prenext(self):
        """Handle the prenext phase by calling next() directly."""
        self.next()

    def next(self):
        """Execute the main trading logic for each bar."""
        # Increment bar_num and update trading date on each run
        self.current_date = bt.num2date(self.datas[0].datetime[0])
        self.bar_num += 1
        data = self.datas[0]

        # Open positions, close existing positions first
        # Close long position
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size > 0 and data.close[0] < self.ema_1[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.sell_count += 1
            self.holding_contract_name = None

        # Close short position
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size < 0 and data.close[0] > self.ema_1[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.buy_count += 1
            self.holding_contract_name = None

        # Open long position
        if self.holding_contract_name is None and self.ema_1[-1] < self.ema_2[-1] and self.ema_1[0] > self.ema_2[0] and self.macd[0] > 0:
            dominant_contract = self.get_dominant_contract()
            if dominant_contract is not None:
                next_data = self.getdatabyname(dominant_contract)
                self.buy(next_data, size=1)
                self.buy_count += 1
                self.holding_contract_name = dominant_contract

        # Open short position
        if self.holding_contract_name is None and self.ema_1[-1] > self.ema_2[-1] and self.ema_1[0] < self.ema_2[0] and self.macd[0] < 0:
            dominant_contract = self.get_dominant_contract()
            if dominant_contract is not None:
                next_data = self.getdatabyname(dominant_contract)
                self.sell(next_data, size=1)
                self.sell_count += 1
                self.holding_contract_name = dominant_contract

        # Rollover to next contract
        if self.holding_contract_name is not None:
            dominant_contract = self.get_dominant_contract()
            # If a new dominant contract appears, start the rollover
            if dominant_contract is not None and dominant_contract != self.holding_contract_name:
                # Next dominant contract
                next_data = self.getdatabyname(dominant_contract)
                # Current contract position size and data
                size = self.getpositionbyname(self.holding_contract_name).size
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
        """Returns the dominant contract name (contract with highest open interest)."""
        target_datas = []
        for data in self.datas[1:]:
            try:
                data_date = bt.num2date(data.datetime[0])
                if self.current_date == data_date:
                    target_datas.append([data._name, data.openinterest[0]])
            except:
                pass
        if not target_datas:
            return None
        target_datas = sorted(target_datas, key=lambda x: x[1])
        return target_datas[-1][0]

    def notify_order(self, order):
        """Handle order status updates and log completed trades."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: data_name:{order.p.data._name} price:{order.executed.price:.2f}")
            else:
                self.log(f"SELL: data_name:{order.p.data._name} price:{order.executed.price:.2f}")

    def notify_trade(self, trade):
        """Handle trade lifecycle events and log trade details."""
        # Output information when a trade ends
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                            trade.getdataname(),trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                            trade.getdataname(),trade.price))

    def stop(self):
        """Log final statistics when the backtest completes."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
