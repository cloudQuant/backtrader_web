#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MultiData Strategy.

This module demonstrates multi-data source functionality where a strategy
can use signals from one data source to trade on another.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class MultiDataStrategy(bt.Strategy):
    """Multi-data strategy using signals from data1 to trade on data0.

    This strategy demonstrates how to use signals generated from one data
    source (data1) to execute trades on another data source (data0).
    This is useful for pairs trading or using one indicator as a signal
    for trading another asset.

    Attributes:
        params: Dictionary containing strategy parameters.
            period (int): SMA period for signal generation (default: 15).
            stake (int): Number of shares/contracts per trade (default: 10).
    """

    params = dict(period=15, stake=10)

    def __init__(self):
        """Initialize the MultiData strategy with indicators and counters."""
        self.orderid = None  # Track active order to prevent duplicate orders
        # Create SMA and crossover signal on the second data source
        # data1 serves as the signal generator for trading data0
        sma = bt.ind.SMA(self.data1, period=self.p.period)
        # CrossOver produces: +1 on bullish cross, -1 on bearish cross, 0 otherwise
        self.signal = bt.ind.CrossOver(self.data1.close, sma)
        # Initialize counters for tracking execution statistics
        self.bar_num = 0  # Total bars processed during backtest
        self.buy_count = 0  # Number of buy orders completed
        self.sell_count = 0  # Number of sell orders completed

    def notify_order(self, order):
        """Handle order status updates."""
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        self.orderid = None

    def next(self):
        """Execute trading logic for each bar.

        Strategy logic:
        1. Generate signals from data1 (SMA crossover)
        2. Execute trades on data0 based on those signals
        3. Buy on bullish crossover, sell on bearish crossover
        """
        self.bar_num += 1
        # Skip if order already pending
        if self.orderid:
            return

        if not self.position:
            # Open long position on bullish crossover
            if self.signal > 0.0:
                self.buy(size=self.p.stake)
        else:
            # Close position on bearish crossover
            if self.signal < 0.0:
                self.sell(size=self.p.stake)

    def stop(self):
        """Print strategy performance summary after backtest completion."""
        print(f"MultiData: bar_num={self.bar_num}, buy={self.buy_count}, sell={self.sell_count}")
        print(f"  Starting Value: {self.broker.startingcash:.2f}")
        print(f"  Ending Value: {self.broker.getvalue():.2f}")


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
