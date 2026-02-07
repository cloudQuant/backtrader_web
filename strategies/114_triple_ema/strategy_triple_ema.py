#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Triple EMA (Triple Exponential Moving Average) Strategy.

This module implements a trend-following strategy using three EMAs
with different periods to identify trend direction.

Reference: backtrader-strategies-compendium
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class TripleEmaStrategy(bt.Strategy):
    """Triple EMA (Triple Exponential Moving Average) Strategy.

    This strategy uses three EMAs with different periods to identify trend
    direction and generate trading signals based on their alignment.

    Entry conditions:
    - Long: EMA5 > EMA10 > EMA20 (bullish alignment)

    Exit conditions:
    - Exit long when EMA5 < EMA10 < EMA20 (bearish alignment)
    """
    params = dict(
        stake=10,
        fast=5,
        mid=10,
        slow=20,
    )

    def __init__(self):
        """Initialize the Triple EMA strategy.

        Sets up the three EMA indicators with different periods and
        initializes tracking variables for order management and statistics.
        """
        self.ema_fast = bt.indicators.EMA(self.data, period=self.p.fast)
        self.ema_mid = bt.indicators.EMA(self.data, period=self.p.mid)
        self.ema_slow = bt.indicators.EMA(self.data, period=self.p.slow)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status notifications.

        Updates buy/sell counters when orders complete and clears the
        pending order reference.

        Args:
            order: The order object with updated status.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements the triple EMA trend-following strategy:
        - Enter long when EMA5 > EMA10 > EMA20 (bullish alignment)
        - Exit long when EMA5 < EMA10 < EMA20 (bearish alignment)
        - Only one position at a time (no pyramiding)
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Bullish alignment
            if self.ema_fast[0] > self.ema_mid[0] > self.ema_slow[0]:
                self.order = self.buy(size=self.p.stake)
        else:
            # Bearish alignment
            if self.ema_fast[0] < self.ema_mid[0] < self.ema_slow[0]:
                self.order = self.close()


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to the config.yaml file. If None, uses default path.

    Returns:
        Dictionary containing configuration parameters.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def get_strategy_params(config=None):
    """Get strategy parameters from config.

    Args:
        config: Configuration dictionary. If None, loads from default path.

    Returns:
        Dictionary of strategy parameters.
    """
    if config is None:
        config = load_config()

    return config.get('params', {})


def create_strategy(**kwargs):
    """Create a TripleEmaStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of TripleEmaStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return TripleEmaStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Triple EMA Strategy")
    print("Params:", get_strategy_params())
