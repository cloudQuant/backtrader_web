#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Timer Strategy - Dual moving average crossover with timer functionality.

Tests strategy timer functionality using a dual moving average crossover strategy.

Reference source: backtrader-master2/samples/timers/scheduled.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class TimerStrategy(bt.Strategy):
    """Timer strategy - Dual moving average crossover.

    Strategy logic:
        - Buy when the fast line crosses above the slow line
        - Sell and close position when the fast line crosses below the slow line
        - Simultaneously test timer functionality
    """
    params = dict(
        when=bt.timer.SESSION_START,
        timer=True,
        fast_period=10,
        slow_period=30,
    )

    def __init__(self):
        """Initialize the TimerStrategy with indicators and tracking variables.

        This method sets up the dual moving average crossover indicators,
        optionally adds a timer based on strategy parameters, and initializes
        counters for tracking strategy execution.
        """
        # Load parameters from config.yaml if exists
        config_path = Path(__file__).parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if 'params' in config:
                    for key, value in config['params'].items():
                        if key == 'when' and isinstance(value, str):
                            if value == 'SESSION_START':
                                self.p.when = bt.timer.SESSION_START
                        elif hasattr(self.p, key):
                            setattr(self.p, key, value)

        self.fast_ma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_ma = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ma, self.slow_ma)

        if self.p.timer:
            self.add_timer(when=self.p.when)

        self.bar_num = 0
        self.timer_count = 0
        self.buy_count = 0
        self.sell_count = 0
        self.order = None

    def notify_order(self, order):
        """Handle order status updates and track executed trades.

        Args:
            order (bt.Order): The order object with updated status information.
        """
        if not order.alive():
            self.order = None
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

    def next(self):
        """Execute the main strategy logic on each bar.

        Trading Rules:
            1. Increment bar counter for each new bar processed
            2. Skip trading if there's a pending order
            3. Bullish crossover (fast > slow): Buy
            4. Bearish crossover (fast < slow): Close position
        """
        self.bar_num += 1
        if self.order:
            return
        if self.crossover > 0:
            if self.position:
                self.order = self.close()
            self.order = self.buy()
        elif self.crossover < 0:
            if self.position:
                self.order = self.close()

    def notify_timer(self, timer, when, *args, **kwargs):
        """Handle timer events and track timer notifications.

        Args:
            timer (bt.Timer): The timer object that triggered this callback.
            when: The timing information indicating when the timer fired.
            *args: Additional positional arguments passed from the timer.
            **kwargs: Additional keyword arguments passed from the timer.
        """
        self.timer_count += 1
