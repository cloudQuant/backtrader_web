#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stochastic Cross Strategy - Combines MA trend with Stochastic oscillator signals.

This strategy combines Simple Moving Average (SMA) trend indicators with
Stochastic oscillator signals to generate buy and sell signals.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class StochasticCrossStrategy(bt.Strategy):
    """A quantitative trading strategy based on Stochastic oscillator crossover.

    This strategy combines Simple Moving Average (SMA) trend indicators with
    Stochastic oscillator signals to generate buy and sell signals. The strategy
    aims to capture trend reversals by entering positions when the market is
    oversold in an uptrend and exiting when overbought in a downtrend.

    Trading Logic:
        - Buy Signal: Short-term MA > Long-term MA AND Stochastic %K < oversold threshold (20)
        - Sell Signal: Short-term MA < Long-term MA AND Stochastic %K > overbought threshold (80)

    Attributes:
        dataclose: Reference to the close price line of the primary data feed.
        ma1: Short-term Simple Moving Average indicator (default 14-period).
        ma2: Long-term Simple Moving Average indicator (default 30-period).
        stoch: Stochastic oscillator indicator providing %K and %D lines.
        order: Reference to the currently pending order, or None if no order is active.
        last_operation: String tracking the last executed operation ("BUY" or "SELL").
        bar_num: Integer counter for the number of bars processed during the backtest.
        buy_count: Integer counter for the total number of buy orders executed.
        sell_count: Integer counter for the total number of sell orders executed.
    """
    params = dict(
        stake=10,
        ma1=14,
        ma2=30,
        stoch_period=14,
        oversold=20,
        overbought=80,
    )

    def __init__(self):
        """Initialize the StochasticCrossStrategy.

        Sets up the technical indicators (SMA and Stochastic), initializes
        tracking variables for orders and statistics.
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
        self.ma1 = bt.ind.SMA(self.datas[0], period=self.p.ma1)
        self.ma2 = bt.ind.SMA(self.datas[0], period=self.p.ma2)
        self.stoch = bt.ind.Stochastic(self.datas[0], period=self.p.stoch_period)

        self.order = None
        self.last_operation = "SELL"

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object that has been updated. Contains status,
                execution price, size, and other order-related information.
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
        """Execute the trading logic for each bar.

        This method implements the core trading strategy: checking conditions and placing
        orders when entry signals are detected.

        The strategy:
            1. Increments the bar counter
            2. Returns early if there's a pending order (prevents over-trading)
            3. Checks for buy signal: uptrend (MA1 > MA2) + oversold Stochastic
            4. Checks for sell signal: downtrend (MA1 < MA2) + overbought Stochastic
        """
        self.bar_num += 1

        if self.order:
            return

        # Buy condition: short-term MA > long-term MA AND Stochastic oversold
        if self.last_operation != "BUY":
            if self.ma1[0] > self.ma2[0] and self.stoch.percK[0] < self.p.oversold:
                self.order = self.buy(size=self.p.stake)

        # Sell condition: short-term MA < long-term MA AND Stochastic overbought
        if self.last_operation != "SELL":
            if self.ma1[0] < self.ma2[0] and self.stoch.percK[0] > self.p.overbought:
                self.order = self.sell(size=self.p.stake)

    def stop(self):
        """Perform cleanup actions when the backtest completes."""
        pass
