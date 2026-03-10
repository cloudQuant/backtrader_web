#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Two Period RSI Strategy - Larry Connor's mean reversion strategy.

This strategy implements Larry Connor's 2-Period RSI approach which buys
when price is above the 200-day MA and 2-period RSI is below 5.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class TwoPeriodRSIStrategy(bt.Strategy):
    """Two Period RSI Strategy.

    Larry Connor's strategy:
    1. Price is above the 200-day moving average
    2. Buy when 2-period RSI is below 5
    3. Sell when price crosses above the 5-day moving average

    Attributes:
        dataclose: Reference to the close price data.
        rsi: 2-period RSI indicator.
        sma5: 5-period Simple Moving Average.
        sma200: 200-period Simple Moving Average.
        order: Current pending order.
        last_operation: Last operation type ("BUY" or "SELL").
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = dict(
        stake=10,
        rsi_period=2,
        sma_short=5,
        sma_long=200,
        rsi_buy_threshold=5,
    )

    def __init__(self):
        """Initialize the Two Period RSI strategy.

        Sets up the indicators and tracking variables for the strategy.
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
        self.rsi = bt.indicators.RSI_Safe(self.datas[0], period=self.p.rsi_period)
        self.sma5 = bt.ind.SMA(self.datas[0], period=self.p.sma_short)
        self.sma200 = bt.ind.SMA(self.datas[0], period=self.p.sma_long)

        self.order = None
        self.last_operation = "SELL"

        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object containing status and execution information.
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

        Implements Larry Connor's 2-Period RSI strategy:
        1. Buy when price is above the 200-day MA and 2-period RSI is below 5
        2. Sell when price crosses above the 5-day MA
        """
        self.bar_num += 1

        if self.order:
            return

        # Buy condition: Price above 200-day MA and RSI below 5
        if self.last_operation != "BUY":
            if self.dataclose[0] > self.sma200[0] and self.rsi[0] < self.p.rsi_buy_threshold:
                self.order = self.buy(size=self.p.stake)

        # Sell condition: Price crosses above 5-day MA
        if self.last_operation != "SELL":
            if self.dataclose[0] > self.sma5[0]:
                self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Called when the backtesting is finished."""
        pass
