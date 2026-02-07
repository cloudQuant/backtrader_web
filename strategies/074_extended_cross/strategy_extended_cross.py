#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Extended Cross Strategy.

Reference: https://github.com/backtrader/backhacker
Moving average crossover strategy using ATR expansion.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ExtendedCrossStrategy(bt.Strategy):
    """Extended cross strategy.

    This strategy implements an ATR-expanded moving average crossover:
    - Buy when fast EMA crosses above (slow EMA + ATR) and price is above long-term EMA
    - Sell when fast EMA crosses below (slow EMA - ATR) and price is below long-term EMA
    """
    params = dict(
        stake=10,
        ma1=5,
        ma2=20,
        ma3=50,
        atr_mult=1,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.ma1 = bt.ind.EMA(self.datas[0], period=self.p.ma1)
        self.ma2 = bt.ind.EMA(self.datas[0], period=self.p.ma2)
        self.ma3 = bt.ind.EMA(self.datas[0], period=self.p.ma3)
        self.atr = bt.ind.ATR(self.datas[0])

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

        # Buy: MA1 > (MA2 + ATR) and price > MA3
        if self.last_operation != "BUY":
            if self.ma1[0] > (self.ma2[0] + self.p.atr_mult * self.atr[0]) and self.dataclose[0] > self.ma3[0]:
                self.order = self.buy(size=self.p.stake)

        # Sell: MA1 < (MA2 - ATR) and price < MA3
        if self.last_operation != "SELL":
            if self.ma1[0] < (self.ma2[0] - self.p.atr_mult * self.atr[0]) and self.dataclose[0] < self.ma3[0]:
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

    return ExtendedCrossStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
