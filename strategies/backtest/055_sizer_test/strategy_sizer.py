#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sizer Position Manager Strategy.

This module demonstrates the use of Sizer (position manager) in Backtrader
to control the size of each trade.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class LongOnlySizer(bt.Sizer):
    """Sizer that only allows long position sizing.

    This sizer enforces long-only trading by:
    1. Returning the configured stake for buy orders
    2. Only allowing sells up to the current position size
    3. Preventing short selling
    """

    params = (('stake', 1),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        """Calculate the position size for an order.

        Args:
            comminfo: Commission info object.
            cash: Available cash.
            data: Data feed.
            isbuy: True if this is a buy order, False for sell.

        Returns:
            int: The number of units/shares to trade.
        """
        if isbuy:
            return self.p.stake
        position = self.broker.getposition(data)
        if not position.size:
            return 0
        return self.p.stake


class SizerTestStrategy(bt.Strategy):
    """Strategy for testing Sizer functionality.

    This strategy uses a simple SMA crossover to generate buy/sell signals
    and tracks the number of trades executed to verify sizer behavior.
    """

    params = (('period', 15),)

    def __init__(self):
        """Initialize the SizerTestStrategy with indicators and tracking variables."""
        # Create SMA indicator with the configured period
        sma = bt.ind.SMA(self.data, period=self.p.period)
        # CrossOver indicator: >0 when price crosses above SMA, <0 when below
        self.crossover = bt.ind.CrossOver(self.data, sma)
        # Initialize tracking variables for strategy execution
        self.bar_num = 0  # Count of bars processed
        self.buy_count = 0  # Count of completed buy orders
        self.sell_count = 0  # Count of completed sell orders

    def notify_order(self, order):
        """Handle order status updates."""
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1
        if self.crossover > 0:
            self.buy()
        elif self.crossover < 0:
            self.sell()

    def stop(self):
        """Print strategy statistics after backtest completion."""
        print(f"SizerTest: bar_num={self.bar_num}, buy={self.buy_count}, sell={self.sell_count}")


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


def get_sizer_config(config=None):
    """Get sizer configuration.

    Args:
        config: Configuration dictionary. If None, loads from default path.

    Returns:
        dict: Sizer configuration.
    """
    if config is None:
        config = load_config()
    return config.get('sizer', {})


def setup_sizer(cerebro, config=None):
    """Setup sizer for cerebro.

    Args:
        cerebro: Backtrader Cerebro instance.
        config: Configuration dictionary. If None, loads from default path.
    """
    sizer_config = get_sizer_config(config)
    sizer_type = sizer_config.get('type', 'LongOnly')
    stake = sizer_config.get('stake', 100)

    if sizer_type == 'LongOnly':
        cerebro.addsizer(LongOnlySizer, stake=stake)
    elif sizer_type == 'Fixed':
        cerebro.addsizer(bt.sizers.FixedSize, stake=stake)


if __name__ == '__main__':
    # Example usage with config
    config = load_config()
    params = get_strategy_params(config)
    print(f"Strategy: {config['strategy']['name']}")
    print(f"Parameters: {params}")
    print(f"Sizer: {config['sizer']}")
