#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Buy Dip Strategy.

This module tests a simple mean reversion strategy that buys after two
consecutive down candles and holds for a fixed number of bars.

Reference: https://github.com/Backtesting/strategies
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class BuyDipStrategy(bt.Strategy):
    """Buy Dip strategy for catching short-term pullbacks.

    This is a simple mean reversion strategy that buys after two consecutive
    down candles (indicating a short-term dip) and holds for a fixed period.

    Trading Rules:
        - Buy when close[0] < close[-1] and close[-1] < close[-2] (two down candles)
        - Sell after holding for hold_bars periods (default: 5 bars)

    Attributes:
        dataclose: Close price data series.
        order: Current pending order.
        bar_executed: The bar number when the current position was entered.
        bar_num: Number of bars processed.
        buy_count: Total buy orders executed.
        sell_count: Total sell orders executed.

    Args:
        stake: Number of shares per trade (default: 10).
        hold_bars: Number of bars to hold position before selling (default: 5).
    """
    params = dict(
        stake=10,
        hold_bars=5,
    )

    def __init__(self):
        """Initialize strategy state variables."""
        self.dataclose = self.datas[0].close
        self.order = None
        self.bar_executed = 0

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
                self.bar_executed = len(self)
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements a dip-buying strategy with fixed holding period.
        """
        self.bar_num += 1
        if self.order:
            return

        if not self.position:
            # Entry: Buy after two consecutive down candles
            if self.dataclose[0] < self.dataclose[-1]:
                if self.dataclose[-1] < self.dataclose[-2]:
                    self.order = self.buy(size=self.p.stake)
        else:
            # Exit: Sell after holding for N bars
            if len(self) >= (self.bar_executed + self.p.hold_bars):
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

    return BuyDipStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
