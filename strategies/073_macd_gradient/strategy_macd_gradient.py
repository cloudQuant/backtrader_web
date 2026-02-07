#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MACD Gradient (Momentum) Strategy.

Reference source: https://github.com/backtrader/backhacker
Momentum strategy based on consecutive MACD rise/fall.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class MACDGradientStrategy(bt.Strategy):
    """MACD Gradient (Momentum) Strategy.

    This strategy uses MACD momentum to generate trading signals:
    - Buy when MACD shows three consecutive periods of upward momentum
    - Sell when MACD shows three consecutive periods of downward momentum

    Entry conditions:
        - MACD[0] > MACD[-1] > MACD[-2] (consecutive rising)

    Exit conditions:
        - MACD[0] < MACD[-1] < MACD[-2] (consecutive falling)
    """
    params = dict(
        stake=10,
        period_me1=12,
        period_me2=26,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.macd = bt.ind.MACD(self.data.close, period_me1=self.p.period_me1, period_me2=self.p.period_me2)

        self.order = None
        self.last_operation = "SELL"

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object that was updated.
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
        """Execute trading logic for each bar."""
        self.bar_num += 1
        if self.order:
            return

        # Buy when MACD shows consecutive upward momentum
        if self.last_operation != "BUY":
            if self.macd.macd[0] > self.macd.macd[-1] > self.macd.macd[-2]:
                self.order = self.buy(size=self.p.stake)

        # Sell when MACD shows consecutive downward momentum
        if self.last_operation != "SELL":
            if self.macd.macd[0] < self.macd.macd[-1] < self.macd.macd[-2]:
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

    return MACDGradientStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
