#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Triple Cross Moving Average Crossover Strategy - Trend strategy based on MA alignment.

This strategy implements a trend-following approach using three simple
moving averages (SMA) with different periods.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class TripleCrossStrategy(bt.Strategy):
    """Triple Moving Average Crossover Strategy.

    This strategy implements a trend-following approach using three simple
    moving averages (SMA) with different periods.

    Trading Logic:
        - Buy when short-term MA > medium-term MA > long-term MA (bullish alignment)
        - Sell when short-term MA < medium-term MA < long-term MA (bearish alignment)

    Attributes:
        dataclose: Close price data series.
        ma1: Short-term simple moving average.
        ma2: Medium-term simple moving average.
        ma3: Long-term simple moving average.
        order: Current pending order.
        last_operation: Last executed operation ("BUY" or "SELL").
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        stake=10,
        ma1_period=5,
        ma2_period=8,
        ma3_period=13,
    )

    def __init__(self):
        """Initialize the TripleCrossStrategy.

        Sets up the three simple moving averages and initializes tracking
        variables for orders and statistics.
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
        self.ma1 = bt.ind.SMA(self.datas[0], period=self.p.ma1_period)
        self.ma2 = bt.ind.SMA(self.datas[0], period=self.p.ma2_period)
        self.ma3 = bt.ind.SMA(self.datas[0], period=self.p.ma3_period)

        self.order = None
        self.last_operation = "SELL"

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with status information.
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

        Implements the triple moving average crossover strategy:
        - Buy when MA1 > MA2 > MA3 (bullish alignment)
        - Sell when MA1 < MA2 < MA3 (bearish alignment)
        """
        self.bar_num += 1

        if self.order:
            return

        # Buy condition: MA1 > MA2 > MA3 (bullish alignment)
        if self.last_operation != "BUY":
            if self.ma1[0] > self.ma2[0] > self.ma3[0]:
                self.order = self.buy(size=self.p.stake)

        # Sell condition: MA1 < MA2 < MA3 (bearish alignment)
        if self.last_operation != "SELL":
            if self.ma1[0] < self.ma2[0] < self.ma3[0]:
                self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Called when the strategy execution is complete."""
        pass
