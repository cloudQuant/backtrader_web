#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Calmar Ratio Analyzer Strategy.

This module implements a dual moving average crossover strategy for testing
the Calmar ratio analyzer which measures risk-adjusted returns.

Calmar Ratio = Annualized Return / Maximum Drawdown
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class CalmarTestStrategy(bt.Strategy):
    """A dual moving average crossover strategy for testing the Calmar analyzer.

    This strategy implements a simple trend-following approach using two Simple
    Moving Averages (SMA). It generates buy signals when the faster SMA crosses
    above the slower SMA, and sell signals when it crosses below.

    Attributes:
        crossover (bt.ind.CrossOver): Indicator that signals when SMAs cross.
        order (bt.Order): Reference to the currently pending order.
        bar_num (int): Counter tracking the number of bars processed.
        buy_count (int): Counter tracking the number of completed buy orders.
        sell_count (int): Counter tracking the number of completed sell orders.

    params:
        p1 (int): Period for the fast SMA. Defaults to 15 periods.
        p2 (int): Period for the slow SMA. Defaults to 50 periods.
    """

    params = (('p1', 15), ('p2', 50))

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        ma1 = bt.ind.SMA(period=self.p.p1)
        ma2 = bt.ind.SMA(period=self.p.p2)
        self.crossover = bt.ind.CrossOver(ma1, ma2)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track completed trades."""
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
