#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Heikin Ashi Strategy.

This module tests a strategy combining Heikin Ashi candlestick patterns
with simple moving average crossover signals.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class HeikinAshiStrategy(bt.Strategy):
    """Heikin Ashi strategy with moving average crossover.

    This strategy combines Heikin Ashi candlestick analysis with a simple
    moving average crossover system for trend following.

    Trading Rules:
        - Buy when short MA crosses above long MA (golden cross)
        - Close position when short MA crosses below long MA (death cross)

    Attributes:
        dataclose: Close price data series.
        ha: Heikin Ashi indicator.
        sma_short: Short-term simple moving average (10 periods).
        sma_long: Long-term simple moving average (30 periods).
        crossover: Crossover indicator signals.
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Total buy orders executed.
        sell_count: Total sell orders executed.

    Args:
        stake: Number of shares/shares per trade (default: 10).
    """
    params = dict(
        stake=10,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.ha = bt.indicators.HeikinAshi(self.datas[0])
        # Use simple moving average crossover for signals
        self.sma_short = bt.indicators.SMA(self.dataclose, period=10)
        self.sma_long = bt.indicators.SMA(self.dataclose, period=30)
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)

        self.order = None

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
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements a trend-following strategy based on MA crossover.
        """
        self.bar_num += 1
        if self.order:
            return

        # Buy on golden cross, close position on death cross
        if self.crossover > 0:
            self.order = self.buy(size=self.p.stake)
        elif self.crossover < 0:
            self.order = self.close()


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

    return HeikinAshiStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
