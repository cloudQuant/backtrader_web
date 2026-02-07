#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Donchian Channel Strategy - Classic trend-following breakout strategy.

This strategy implements a classic trend-following approach using the
Donchian Channel indicator. It goes long when price breaks above the
upper channel and short when price breaks below the lower channel.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class DonchianChannelIndicator(bt.Indicator):
    """Donchian Channel indicator.

    The Donchian Channel is a trend-following indicator that calculates
    the highest high and lowest low over a specified period.

    Attributes:
        dch: Donchian Channel High (upper band) - highest high over period.
        dcl: Donchian Channel Low (lower band) - lowest low over period.
        dcm: Donchian Channel Middle (middle band) - average of upper and lower.
    """
    lines = ('dch', 'dcl', 'dcm')
    params = dict(period=20)

    def __init__(self):
        """Initialize the Donchian Channel indicator.

        Sets up the three channel lines using the Highest and Lowest indicators.
        """
        self.lines.dch = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.lines.dcl = bt.indicators.Lowest(self.data.low, period=self.p.period)
        self.lines.dcm = (self.lines.dch + self.lines.dcl) / 2


class DonchianChannelStrategy(bt.Strategy):
    """Donchian Channel breakout strategy.

    This strategy implements a classic trend-following approach using the
    Donchian Channel indicator:
    - Go long when price breaks above the upper channel
    - Go short when price breaks below the lower channel

    Attributes:
        dataclose: Reference to the close price data.
        indicator: Donchian Channel indicator instance.
        order: Current pending order.
        last_operation: Last executed operation ("BUY" or "SELL").
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        stake=10,
        period=20,
    )

    def __init__(self):
        """Initialize the Donchian Channel strategy.

        Sets up the indicator, data references, and tracking variables for
        orders and statistics.
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
        self.indicator = DonchianChannelIndicator(self.datas[0], period=self.p.period)

        self.order = None
        self.last_operation = "SELL"

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status.
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

        Implements the Donchian Channel breakout strategy:
        - Buy when close price breaks above the upper channel
        - Sell when close price breaks below the lower channel
        """
        self.bar_num += 1

        if self.order:
            return

        if self.dataclose[0] > self.indicator.dch[0] and self.last_operation != "BUY":
            self.order = self.buy(size=self.p.stake)
        elif self.dataclose[0] < self.indicator.dcl[0] and self.last_operation != "SELL":
            self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Called when the backtest is finished."""
        pass
