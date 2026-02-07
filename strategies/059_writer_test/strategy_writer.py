#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Writer Output Test Strategy.

This module demonstrates the Writer output functionality using a
price and SMA crossover strategy.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class WriterTestStrategy(bt.Strategy):
    """Strategy to test Writer - price and SMA crossover.

    Strategy logic:
    - Buy when price crosses above SMA
    - Sell and close position when price crosses below SMA

    Attributes:
        crossover: CrossOver indicator tracking price vs SMA.
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for buy orders executed.
        sell_count: Counter for sell orders executed.
    """
    params = (('period', 15),)

    def __init__(self):
        """Initialize the WriterTestStrategy."""
        sma = bt.ind.SMA(self.data, period=self.p.period)
        self.crossover = bt.ind.CrossOver(self.data.close, sma)
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status changes and update trade counters."""
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

    def next(self):
        """Execute the trading logic for each bar."""
        self.bar_num += 1
        if self.crossover > 0 and not self.position:
            self.buy()
        elif self.crossover < 0 and self.position:
            self.close()


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


def setup_writer(cerebro, config=None):
    """Setup writer for cerebro.

    Args:
        cerebro: Backtrader Cerebro instance.
        config: Configuration dictionary. If None, loads from default path.
    """
    if config is None:
        config = load_config()

    writer_config = config.get('writer', {})
    csv = writer_config.get('csv', False)
    rounding = writer_config.get('rounding', 4)

    cerebro.addwriter(bt.WriterFile, csv=csv, rounding=rounding)


if __name__ == '__main__':
    # Example usage with config
    config = load_config()
    params = get_strategy_params(config)
    print(f"Strategy: {config['strategy']['name']}")
    print(f"Parameters: {params}")
