#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Slope Strategy.

This module tests a trend-following strategy based on the slope direction
of a simple moving average.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class SlopeStrategy(bt.Strategy):
    """Slope strategy based on moving average direction.

    This strategy identifies trend direction by monitoring the slope of a
    simple moving average. It buys when the MA is rising and sells when falling.

    Trading Rules:
        - Buy when current MA value > previous MA value (rising slope)
        - Sell when current MA value < previous MA value (falling slope)

    Attributes:
        dataclose: Close price data series.
        ma: Simple moving average indicator.
        order: Current pending order.
        last_operation: Last executed operation ("BUY" or "SELL").
        bar_num: Number of bars processed.
        buy_count: Total buy orders executed.
        sell_count: Total sell orders executed.

    Args:
        stake: Number of shares per trade (default: 10).
        ma_period: Period for moving average calculation (default: 14).
    """
    params = dict(
        stake=10,
        ma_period=14,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.ma = bt.ind.SMA(self.datas[0], period=self.p.ma_period)

        self.order = None
        self.last_operation = "SELL"

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.last_operation = "BUY"
            else:
                self.sell_count += 1
                self.last_operation = "SELL"
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Monitors MA slope and generates buy/sell signals based on direction.
        """
        self.bar_num += 1
        if self.order:
            return

        # Buy signal: MA is rising (current > previous)
        if self.last_operation != "BUY":
            if self.ma[0] > self.ma[-1]:
                self.order = self.buy(size=self.p.stake)

        # Sell signal: MA is falling (current < previous)
        if self.last_operation != "SELL":
            if self.ma[0] < self.ma[-1]:
                self.order = self.sell(size=self.p.stake)


def load_config(config_path=None):
    """Load strategy configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        dict: Configuration dictionary with strategy parameters.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def get_strategy_from_config(config_path=None):
    """Get strategy class with parameters loaded from config.yaml.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Tuple: (Strategy class, params dict)
    """
    config = load_config(config_path)
    params = config.get('params', {})

    return SlopeStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
