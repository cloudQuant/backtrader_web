#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Multi-data source simple moving average crossover strategy.

This strategy implements a trend-following approach using moving average
crossovers across multiple convertible bonds simultaneously. It maintains
equal weight positions across all tradable assets.

Strategy Logic:
    1. Calculate 60-day simple moving average for each convertible bond
    2. Buy when price crosses above the moving average (uptrend signal)
    3. Sell when price crosses below the moving average (downtrend signal)
    4. Allocate equal portfolio weight to each tradable bond
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import backtrader.indicators as btind
import pandas as pd


class ExtendPandasFeed(bt.feeds.PandasData):
    """Extended Pandas data feed with convertible bond-specific fields."""

    params = (
        ("datetime", None),
        ("open", 0),
        ("high", 1),
        ("low", 2),
        ("close", 3),
        ("volume", 4),
        ("openinterest", -1),
        ("pure_bond_value", 5),
        ("convert_value", 6),
        ("pure_bond_premium_rate", 7),
        ("convert_premium_rate", 8),
    )
    lines = ("pure_bond_value", "convert_value", "pure_bond_premium_rate", "convert_premium_rate")


class SimpleMAMultiDataStrategy(bt.Strategy):
    """Multi-data source simple moving average crossover strategy.

    Strategy Logic:
        - Buy: previous_close < previous_ma AND current_close > current_ma
        - Sell: previous_close > previous_ma AND current_close < current_ma
        - Equal weight allocation across all tradable bonds

    Parameters:
        period (int): Moving average period (default: 60 days)
        verbose (bool): Enable detailed logging output (default: False)
    """

    params = (
        ("period", 60),
        ("verbose", False),
    )

    def log(self, txt, dt=None):
        """Log strategy messages to console."""
        if self.p.verbose:
            dt = dt or self.datas[0].datetime.date(0)
            print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

        # Create moving average indicators for each convertible bond
        self.stock_ma_dict = {}
        for idx, data in enumerate(self.datas[1:], start=1):
            ma = btind.SimpleMovingAverage(data.close, period=self.p.period)
            setattr(self, f"ma_{data._name}", ma)
            self.stock_ma_dict[data._name] = ma

        self.position_dict = {}
        self.stock_dict = {}

    def prenext(self):
        """Handle prenext phase by calling next()."""
        self.next()

    def next(self):
        """Execute strategy logic for each bar."""
        self.bar_num += 1

        current_date = self.datas[0].datetime.date(0).strftime("%Y-%m-%d")

        total_value = self.broker.get_value()
        total_cash = self.broker.get_cash()

        # Identify tradable bonds
        for data in self.datas[1:]:
            data_date = data.datetime.date(0).strftime("%Y-%m-%d")
            if current_date == data_date:
                stock_name = data._name
                if stock_name not in self.stock_dict:
                    self.stock_dict[stock_name] = 1

        total_target_stock_num = len(self.stock_dict)
        if total_target_stock_num == 0:
            return

        total_holding_stock_num = len(self.position_dict)

        # Calculate position size
        if total_holding_stock_num < total_target_stock_num:
            remaining = total_target_stock_num - total_holding_stock_num
            if remaining > 0:
                now_value = total_cash / remaining
                stock_value = total_value / total_target_stock_num
                now_value = min(now_value, stock_value)
            else:
                now_value = total_value / total_target_stock_num
        else:
            now_value = total_value / total_target_stock_num

        # Loop through convertible bonds and execute trading logic
        for data in self.datas[1:]:
            data_date = data.datetime.date(0).strftime("%Y-%m-%d")
            if current_date != data_date:
                continue

            ma_indicator = self.stock_ma_dict.get(data._name)
            if ma_indicator is None:
                continue

            if len(ma_indicator) < self.p.period + 1:
                continue

            close = data.close[0]
            pre_close = data.close[-1]
            ma = ma_indicator[0]
            pre_ma = ma_indicator[-1]

            if ma <= 0 or pre_ma <= 0 or pd.isna(ma) or pd.isna(pre_ma):
                continue

            # Close long signal
            if pre_close > pre_ma and close < ma:
                if self.getposition(data).size > 0:
                    self.close(data)
                    self.sell_count += 1
                    if data._name in self.position_dict:
                        self.position_dict.pop(data._name)

                if data._name in self.position_dict and self.getposition(data).size == 0:
                    order = self.position_dict[data._name]
                    self.cancel(order)
                    self.position_dict.pop(data._name)

            # Open long signal
            if pre_close < pre_ma and close > ma:
                if self.getposition(data).size == 0 and data._name not in self.position_dict:
                    lots = now_value / data.close[0]
                    lots = int(lots / 10) * 10
                    if lots > 0:
                        order = self.buy(data, size=lots)
                        self.position_dict[data._name] = order
                        self.buy_count += 1

    def notify_order(self, order):
        """Handle order status updates."""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Rejected:
            self.log(f"Rejected: {order.p.data._name}")
        elif order.status == order.Margin:
            self.log(f"Margin: {order.p.data._name}")
        elif order.status == order.Cancelled:
            self.log(f"Cancelled: {order.p.data._name}")
        elif order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: {order.p.data._name} @ {order.executed.price:.2f}")
            else:
                self.log(f"SELL: {order.p.data._name} @ {order.executed.price:.2f}")

    def notify_trade(self, trade):
        """Handle trade lifecycle events."""
        if trade.isclosed:
            self.log(
                f"Trade closed: {trade.getdataname()}, PnL: {trade.pnl:.2f}, Net: {trade.pnlcomm:.2f}"
            )
        if trade.isopen:
            self.log(f"Trade opened: {trade.getdataname()} @ {trade.price:.2f}")

    def stop(self):
        """Print strategy completion statistics."""
        print(
            f"Strategy ended: bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}"
        )
