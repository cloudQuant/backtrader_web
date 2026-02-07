#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bollinger Bands Mean Reversion Strategy.

This strategy implements a mean reversion approach using Bollinger Bands
technical indicator. It identifies overbought and oversold conditions and
executes trades when price reverts to the mean.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class BollingerBandsStrategy(bt.Strategy):
    """Bollinger Bands mean reversion strategy.

    This strategy implements a mean reversion approach using Bollinger Bands
    technical indicator. The strategy identifies overbought and oversold
    conditions and executes trades when price reverts to the mean.

    Trading Logic:
        - Marks a buy signal when price breaks below the lower band (oversold)
        - Executes buy when price rises back above the middle band
        - Marks a sell signal when price breaks above the upper band (overbought)
        - Executes sell when price falls back below the middle band

    Attributes:
        dataclose: LineSeries object providing access to close prices.
        bband: Bollinger Bands indicator with top, mid, and bottom lines.
        redline (bool): Flag indicating price broke below lower band.
        blueline (bool): Flag indicating price broke above upper band.
        order: Reference to the current pending order.
        last_operation (str): Last executed operation, either "BUY" or "SELL".
        bar_num (int): Counter for the number of bars processed.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.
    """
    params = dict(
        stake=10,
        bbands_period=20,
        devfactor=2.0,
    )

    def __init__(self):
        """Initialize the Bollinger Bands strategy.

        Sets up the Bollinger Bands indicator, initializes state variables for
        tracking signals and orders, and prepares counters for trade statistics.
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
        self.bband = bt.indicators.BBands(
            self.datas[0],
            period=self.p.bbands_period,
            devfactor=self.p.devfactor
        )

        self.redline = False  # Price has broken below lower band
        self.blueline = False  # Price has broken above upper band

        self.order = None
        self.last_operation = "SELL"

        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status information.
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

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Args:
            trade: The trade object containing trade details.
        """
        pass

    def next(self):
        """Execute the strategy logic for each bar.

        This method implements the mean reversion logic by monitoring price
        relative to Bollinger Bands and executing trades when appropriate
        signals are generated.
        """
        self.bar_num += 1

        if self.order:
            return

        # Price breaks below lower band, mark buy signal
        if self.dataclose[0] < self.bband.l.bot[0] and self.last_operation != "BUY":
            self.redline = True

        # Price breaks above upper band, mark sell signal
        if self.dataclose[0] > self.bband.l.top[0] and self.last_operation != "SELL":
            self.blueline = True

        # Price rises back above middle band, execute buy
        if self.dataclose[0] > self.bband.l.mid[0] and self.last_operation != "BUY" and self.redline:
            self.order = self.buy(size=self.p.stake)
            self.redline = False

        # Price breaks above upper band, buy immediately
        if self.dataclose[0] > self.bband.l.top[0] and self.last_operation != "BUY":
            self.order = self.buy(size=self.p.stake)

        # Price falls back below middle band, execute sell
        if self.dataclose[0] < self.bband.l.mid[0] and self.last_operation != "SELL" and self.blueline:
            self.blueline = False
            self.redline = False
            self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Called when the strategy execution is complete."""
        pass
