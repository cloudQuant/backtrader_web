#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Order Close Strategy - Executes orders at closing price.

This strategy uses SMA crossover signals and executes orders at the close
of each bar using bt.Order.Close execution type.

Reference: backtrader-master2/samples/order-close/close-daily.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class OrderCloseStrategy(bt.Strategy):
    """Strategy that executes orders at closing price.

    This strategy uses SMA crossover signals and executes orders
    at the close of each bar using bt.Order.Close execution type.

    Attributes:
        params: Strategy parameters (period for SMA)
        crossover: CrossOver indicator tracking price vs SMA
        order: Current pending order
        bar_num: Counter for processed bars
        buy_count: Counter for executed buy orders
        sell_count: Counter for executed sell orders
    """
    params = (('period', 15),)

    def __init__(self):
        """Initialize strategy with indicators and counters."""
        # Load parameters from config.yaml if exists
        config_path = Path(__file__).parent / 'config.yaml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if 'params' in config:
                    for key, value in config['params'].items():
                        if hasattr(self.params, key):
                            setattr(self.params, key, value)

        sma = bt.ind.SMA(period=self.p.period)
        self.crossover = bt.ind.CrossOver(self.data.close, sma)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status changes.

        Args:
            order: The order object with updated status
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
            self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Buy on bullish crossover, close position on bearish crossover.
        All orders are executed at closing price.
        """
        self.bar_num += 1
        if self.order:
            return  # Wait for pending order to complete

        if not self.position:
            if self.crossover > 0:
                # Execute buy order at closing price
                self.order = self.buy(exectype=bt.Order.Close)
        else:
            if self.crossover < 0:
                # Execute close order at closing price
                self.order = self.close(exectype=bt.Order.Close)

    def stop(self):
        """Print strategy statistics after backtest completion."""
        print(f"OrderClose: bar_num={self.bar_num}, buy={self.buy_count}, sell={self.sell_count}")
