#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Commission Schemes Strategy.

This module tests different commission calculation schemes using a
dual moving average crossover strategy.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class CommissionStrategy(bt.Strategy):
    """Strategy to test commission schemes using dual moving average crossover.

    This strategy implements a simple moving average crossover trading system
    where buy signals are generated when the fast MA crosses above the slow MA,
    and sell signals are generated when the fast MA crosses below the slow MA.

    Attributes:
        fast_ma: Fast moving average indicator.
        slow_ma: Slow moving average indicator.
        crossover: Crossover indicator between fast and slow MAs.
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for the number of buy orders executed.
        sell_count: Counter for the number of sell orders executed.
        total_commission: Accumulated commission from all executed orders.
    """

    params = (('stake', 10), ('fast_period', 10), ('slow_period', 30))

    def __init__(self):
        """Initialize the CommissionStrategy."""
        self.fast_ma = bt.ind.SMA(period=self.p.fast_period)
        self.slow_ma = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ma, self.slow_ma)
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.total_commission = 0.0

    def notify_order(self, order):
        """Handle order status changes and track commission."""
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
            self.total_commission += order.executed.comm

    def next(self):
        """Execute trading logic for each bar."""
        self.bar_num += 1
        if self.crossover > 0:
            if self.position:
                self.order = self.close()
            self.order = self.buy(size=self.p.stake)
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


def get_commission_config(config=None):
    """Get commission configuration.

    Args:
        config: Configuration dictionary. If None, loads from default path.

    Returns:
        dict: Commission configuration.
    """
    if config is None:
        config = load_config()
    return config.get('commission', {})


def setup_commission(cerebro, config=None):
    """Setup commission scheme for cerebro.

    Args:
        cerebro: Backtrader Cerebro instance.
        config: Configuration dictionary. If None, loads from default path.
    """
    comm_config = get_commission_config(config)
    comm_type = comm_config.get('type', 'percentage')
    rate = comm_config.get('rate', 0.001)

    if comm_type == 'percentage':
        cerebro.broker.setcommission(
            commission=rate,
            commtype=bt.CommInfoBase.COMM_PERC,
            stocklike=True
        )
    elif comm_type == 'fixed':
        cerebro.broker.setcommission(
            commission=rate,
            commtype=bt.CommInfoBase.COMM_FIXED,
            stocklike=True
        )


if __name__ == '__main__':
    # Example usage with config
    config = load_config()
    params = get_strategy_params(config)
    print(f"Strategy: {config['strategy']['name']}")
    print(f"Parameters: {params}")
    print(f"Commission: {config['commission']}")
