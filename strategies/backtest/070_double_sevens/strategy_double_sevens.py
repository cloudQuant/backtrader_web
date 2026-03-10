#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Double Sevens Strategy - Larry Connor's mean-reversion trading system.

This strategy implements a mean-reversion trading system that buys at N-day
lows and sells at N-day highs when price is above a moving average threshold.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class DoubleSevensStrategy(bt.Strategy):
    """Larry Connor's Double Sevens mean-reversion trading strategy.

    This strategy implements a mean-reversion approach that:
    1. Only trades when price is above the 200-day or 70-day moving average (trend filter)
    2. Buys when price makes a new N-day low (buying the dip)
    3. Sells when price makes a new N-day high (selling the rip)

    The strategy is designed to capture short-term reversals within an overall
    uptrend, avoiding long positions during downtrends by requiring price to
    be above the moving average threshold.

    Attributes:
        dataclose: Reference to the close price data series.
        sma200: 200-period Simple Moving Average indicator.
        sma: Short-period (default 70) Simple Moving Average indicator.
        high_bar: N-period Highest close price indicator.
        low_bar: N-period Lowest close price indicator.
        order: Reference to the current pending order.
        last_operation: String tracking the last operation ('BUY' or 'SELL').
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for the number of buy orders executed.
        sell_count: Counter for the number of sell orders executed.
    """
    params = dict(
        stake=10,
        period=7,  # N-day high/low period
        sma_short=70,
        sma_long=200,
    )

    def __init__(self):
        """Initialize the Double Sevens strategy.

        Sets up the required indicators (SMA, Highest, Lowest) and initializes
        tracking variables for orders, operations, and statistics.
        """
        # Load parameters from config.yaml if exists
        config_path = Path(__file__).parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if 'params' in config:
                    for key, value in config['params'].items():
                        if hasattr(self.p, key):
                            setattr(self.p, key, value)

        self.dataclose = self.datas[0].close
        self.sma200 = bt.ind.SMA(self.datas[0], period=self.p.sma_long)
        self.sma = bt.ind.SMA(self.datas[0], period=self.p.sma_short)
        self.high_bar = bt.ind.Highest(self.datas[0].close, period=self.p.period)
        self.low_bar = bt.ind.Lowest(self.datas[0].close, period=self.p.period)

        self.order = None
        self.last_operation = "SELL"

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object that has changed status.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.last_operation = "BUY"
            else:
                self.sell_count += 1
                self.last_operation = "SELL"

        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        This method implements the Double Sevens strategy logic:
        1. Buy when price is above MA and makes new N-day low
        2. Sell when price makes new N-day high
        """
        self.bar_num += 1

        if self.order:
            return

        # Buy condition: Price above moving average + new N-day low
        if self.last_operation != "BUY":
            above_ma = self.dataclose[0] > self.sma200[0] or self.dataclose[0] > self.sma[0]
            at_low = self.dataclose[0] <= self.low_bar[0]
            if above_ma and at_low:
                self.order = self.buy(size=self.p.stake)

        # Sell condition: new N-day high
        if self.last_operation != "SELL":
            if self.dataclose[0] >= self.high_bar[0]:
                self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Called when the backtest is finished."""
        pass
