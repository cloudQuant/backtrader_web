#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sharpe Ratio and TimeReturn Analyzer Strategy.

This module evaluates the Sharpe ratio and TimeReturn analyzers using a
dual moving average crossover strategy.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class SharpeTestStrategy(bt.Strategy):
    """Test strategy for Sharpe ratio analysis using dual moving average crossover.

    This strategy implements a simple moving average crossover system where:
    - Buy signal occurs when the fast MA crosses above the slow MA
    - Sell signal occurs when the fast MA crosses below the slow MA

    Attributes:
        crossover: Indicator tracking MA crossover signals
        order: Current pending order
        bar_num: Counter for processed bars
        buy_count: Number of buy orders executed
        sell_count: Number of sell orders executed

    Args:
        p1: Period for the fast moving average (default: 10)
        p2: Period for the slow moving average (default: 30)
    """
    params = (('p1', 10), ('p2', 30))

    def __init__(self):
        """Initialize the SharpeTestStrategy."""
        ma1 = bt.ind.SMA(period=self.p.p1)
        ma2 = bt.ind.SMA(period=self.p.p2)
        self.crossover = bt.ind.CrossOver(ma1, ma2)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order notification events."""
        if not order.alive():
            self.order = None
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

    def next(self):
        """Execute trading logic for each bar."""
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


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        dict: Configuration dictionary.
    """
    if config_path is None:
        config_path = Path(__file__).parent / 'config.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def get_strategy_params(config=None):
    """Get strategy parameters from config.

    Args:
        config: Configuration dictionary. If None, loads from default path.

    Returns:
        dict: Strategy parameters.
    """
    if config is None:
        config = load_config()
    return config.get('params', {})


if __name__ == '__main__':
    # Example usage with config
    config = load_config()
    params = get_strategy_params(config)
    print(f"Strategy: {config['strategy']['name']}")
    print(f"Parameters: {params}")
