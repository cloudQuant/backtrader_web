#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VWR (Variability-Weighted Return) Analyzer Strategy.

This module implements a dual moving average crossover strategy for testing
the VWR analyzer which measures risk-adjusted returns considering volatility.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class VWRTestStrategy(bt.Strategy):
    """Dual moving average crossover strategy for testing the VWR analyzer.

    This strategy implements a simple crossover trading system using two
    Simple Moving Averages (SMA). When the shorter SMA crosses above the
    longer SMA, a long position is entered. When the shorter SMA crosses
    below the longer SMA, the position is closed.

    Attributes:
        crossover (bt.ind.CrossOver): Indicator tracking SMA crossovers.
        order (bt.Order): Reference to the current pending order.
        bar_num (int): Counter for the number of bars processed.
        buy_count (int): Counter for the number of buy orders executed.
        sell_count (int): Counter for the number of sell orders executed.

    params:
        p1 (int): Period for the fast SMA. Defaults to 10.
        p2 (int): Period for the slow SMA. Defaults to 30.
    """
    params = (('p1', 10), ('p2', 30))

    def __init__(self):
        """Initialize the VWR test strategy."""
        ma1 = bt.ind.SMA(period=self.p.p1)
        ma2 = bt.ind.SMA(period=self.p.p2)
        self.crossover = bt.ind.CrossOver(ma1, ma2)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates."""
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

    def stop(self):
        """Called when the backtest is complete."""
        pass


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
