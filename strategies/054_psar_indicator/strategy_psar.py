#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parabolic SAR Indicator Strategy.

This module implements a trading strategy using the Parabolic SAR
(Stop and Reverse) indicator for generating buy/sell signals.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class PSARStrategy(bt.Strategy):
    """Parabolic SAR (Stop and Reverse) strategy.

    This strategy uses the Parabolic SAR indicator to generate buy/sell
    signals based on price momentum and trend direction.

    Entry conditions:
        - Price crosses above PSAR (go long)

    Exit conditions:
        - Price crosses below PSAR (close position)

    Attributes:
        psar: Parabolic SAR indicator.
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.psar = bt.ind.ParabolicSAR()
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates."""
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1
        if self.order:
            return
        # Buy when price crosses above PSAR, sell when price crosses below PSAR
        if self.data.close[0] > self.psar[0] and not self.position:
            self.order = self.buy()
        elif self.data.close[0] < self.psar[0] and self.position:
            self.order = self.close()

    def stop(self):
        """Print strategy statistics after backtest completion."""
        print(f"PSAR: bar_num={self.bar_num}, buy={self.buy_count}, sell={self.sell_count}")


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
