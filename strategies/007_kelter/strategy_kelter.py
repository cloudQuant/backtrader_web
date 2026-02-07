#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Keltner Channel multi-contract futures strategy.

The strategy implements a trend-following approach using Keltner Channel
breakouts as entry signals and automatic contract rollover for futures trading.

Entry Logic:
    - Long entry: Price closes above upper line AND middle line is rising
    - Short entry: Price closes below lower line AND middle line is falling

Exit Logic:
    - Close long when price closes below middle line
    - Close short when price closes above middle line

Rollover Logic:
    - Identifies dominant contract (highest open interest) at each bar
    - Automatically closes old contract position and opens new contract position
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


class KeltnerStrategy(bt.Strategy):
    """Keltner Channel multi-contract futures strategy.

    Indicators:
        - Middle line: SMA of typical price (HLC/3), default 110-period
        - ATR: Average True Range, default 110-period
        - Upper line: Middle line + (ATR * multiplier), default 3x ATR
        - Lower line: Middle line - (ATR * multiplier), default 3x ATR

    Parameters:
        avg_period (int): Period for middle line and ATR (default: 110)
        atr_multi (int): ATR multiplier for bands (default: 3)
    """

    author = 'yunjinqi'
    params = (
        ("avg_period", 110),
        ("atr_multi", 3),
    )

    def log(self, txt, dt=None):
        """Log strategy information with timestamp."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize the Keltner Channel strategy."""
        # Initialize tracking variables
        self.bar_num = 0
        self.current_date = None
        self.buy_count = 0
        self.sell_count = 0

        # Calculate Keltner Channel indicators
        self.middle_price = (self.datas[0].high + self.datas[0].low + self.datas[0].close) / 3
        self.middle_line = bt.indicators.SMA(self.middle_price, period=self.p.avg_period)
        self.atr = bt.indicators.AverageTrueRange(self.datas[0], period=self.p.avg_period)
        self.upper_line = self.middle_line + self.atr * self.p.atr_multi
        self.lower_line = self.middle_line - self.atr * self.p.atr_multi

        # Track which contract is currently being held
        self.holding_contract_name = None

    def prenext(self):
        """Handle pre-next phase for futures data."""
        self.next()

    def next(self):
        """Execute trading logic for each bar."""
        # Each time it runs, increment bar_num and update trading date
        self.current_date = bt.num2date(self.datas[0].datetime[0])
        self.bar_num += 1
        data = self.datas[0]

        # Close long position if price crosses below middle line
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size > 0 and data.close[0] < self.middle_line[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.sell_count += 1
            self.holding_contract_name = None

        # Close short position if price crosses above middle line
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size < 0 and data.close[0] > self.middle_line[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.buy_count += 1
            self.holding_contract_name = None

        # Open long position on upper rail breakout with rising middle line
        if self.holding_contract_name is None and data.close[-1] < self.upper_line[-1] and data.close[0] > self.upper_line[0] and self.middle_line[0] > self.middle_line[-1]:
            dominant_contract = self.get_dominant_contract()
            if dominant_contract is not None:
                next_data = self.getdatabyname(dominant_contract)
                self.buy(next_data, size=1)
                self.buy_count += 1
                self.holding_contract_name = dominant_contract

        # Open short position on lower rail breakout with falling middle line
        if self.holding_contract_name is None and data.close[-1] > self.lower_line[-1] and data.close[0] < self.lower_line[0] and self.middle_line[0] < self.middle_line[-1]:
            dominant_contract = self.get_dominant_contract()
            if dominant_contract is not None:
                next_data = self.getdatabyname(dominant_contract)
                self.sell(next_data, size=1)
                self.sell_count += 1
                self.holding_contract_name = dominant_contract

        # Rollover to next contract if dominant contract changes
        if self.holding_contract_name is not None:
            dominant_contract = self.get_dominant_contract()
            # If a new dominant contract appears, start rollover
            if dominant_contract is not None and dominant_contract != self.holding_contract_name:
                # Next dominant contract
                next_data = self.getdatabyname(dominant_contract)
                # Current contract position size and data
                size = self.getpositionbyname(self.holding_contract_name).size
                data = self.getdatabyname(self.holding_contract_name)
                # Close old position
                self.close(data)
                # Open new position with same size and direction
                if size > 0:
                    self.buy(next_data, size=abs(size))
                if size < 0:
                    self.sell(next_data, size=abs(size))
                self.holding_contract_name = dominant_contract

    def get_dominant_contract(self):
        """Select the contract with the largest open interest as the dominant contract."""
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

        # Sort by open interest and return the contract with highest open interest
        target_datas = sorted(target_datas, key=lambda x: x[1])
        return target_datas[-1][0]

    def notify_order(self, order):
        """Handle order status updates."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: data_name:{order.p.data._name} price:{order.executed.price:.2f}")
            else:
                self.log(f"SELL: data_name:{order.p.data._name} price:{order.executed.price:.2f}")

    def notify_trade(self, trade):
        """Handle trade status updates."""
        # Output information when a trade is completed
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))
        if trade.isopen:
            self.log('open symbol is : {} , price : {}'.format(
                trade.getdataname(), trade.price))

    def stop(self):
        """Log final statistics when backtesting completes."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
