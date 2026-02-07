#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pandas Data Loading Strategy.

This module demonstrates how to load data from Pandas DataFrame
into Backtrader using a dual moving average crossover strategy.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class SimpleMAStrategy(bt.Strategy):
    """Simple dual moving average crossover strategy for testing Pandas data loading.

    Strategy logic:
        - Buy when fast MA crosses above slow MA
        - Sell and close position when fast MA crosses below slow MA

    Attributes:
        fast_ma: Fast moving average indicator.
        slow_ma: Slow moving average indicator.
        crossover: Crossover indicator between fast and slow MAs.
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = (('fast_period', 10), ('slow_period', 30))

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.fast_ma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_ma = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ma, self.slow_ma)
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

    def notify_trade(self, trade):
        """Handle trade notifications."""

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
        """Called when the backtest is finished."""


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


def load_data_from_pandas(dataframe, **kwargs):
    """Load data from Pandas DataFrame into Backtrader.

    Args:
        dataframe: Pandas DataFrame with OHLCV data.
        **kwargs: Additional arguments for PandasData feed.

    Returns:
        bt.feeds.PandasData: Backtrader data feed.
    """
    return bt.feeds.PandasData(dataname=dataframe, **kwargs)


if __name__ == '__main__':
    # Example usage with config
    config = load_config()
    params = get_strategy_params(config)
    print(f"Strategy: {config['strategy']['name']}")
    print(f"Parameters: {params}")
