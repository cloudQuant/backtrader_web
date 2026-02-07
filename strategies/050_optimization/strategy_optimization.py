#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parameter Optimization Strategy.

This module demonstrates parameter optimization functionality using a
strategy combining SMA and MACD indicators. The optimal parameters
are found by maximizing the Sharpe ratio.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class OptimizeStrategy(bt.Strategy):
    """A dual-indicator strategy combining SMA and MACD for parameter optimization.

    This strategy uses a Simple Moving Average (SMA) and Moving Average
    Convergence Divergence (MACD) indicators to generate trading signals.
    The primary signal comes from the MACD line crossing over its signal line.
    The SMA parameter is optimized to find the best risk-adjusted returns.

    The strategy enters a long position when the MACD line crosses above
    the signal line (bullish crossover) and exits when it crosses below
    (bearish crossover).

    Attributes:
        sma: Simple Moving Average indicator with configurable period.
        macd: MACD indicator with configurable fast, slow, and signal periods.
        crossover: CrossOver indicator detecting when MACD crosses its signal.
        order: Reference to the current pending order, or None if no order.
        bar_num: Counter tracking the number of bars processed.
        buy_count: Total number of completed buy orders.
        sell_count: Total number of completed sell orders.

    Args:
        smaperiod: Period for the Simple Moving Average. Defaults to 15.
        macdperiod1: Fast EMA period for MACD calculation. Defaults to 12.
        macdperiod2: Slow EMA period for MACD calculation. Defaults to 26.
        macdperiod3: Signal line EMA period for MACD. Defaults to 9.
    """
    params = (
        ('smaperiod', 15),
        ('macdperiod1', 12),
        ('macdperiod2', 26),
        ('macdperiod3', 9),
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.sma = bt.ind.SMA(period=self.p.smaperiod)
        self.macd = bt.ind.MACD(
            period_me1=self.p.macdperiod1,
            period_me2=self.p.macdperiod2,
            period_signal=self.p.macdperiod3
        )
        self.crossover = bt.ind.CrossOver(self.macd.macd, self.macd.signal)
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
        """Execute trading logic for the current bar."""
        self.bar_num += 1
        if self.order:
            return
        if self.crossover > 0:
            if not self.position:
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
