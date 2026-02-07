#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Renko EMA Crossover Strategy

Renko EMA交叉策略 - 结合Renko图过滤和EMA交叉的趋势跟踪系统。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import yaml
from pathlib import Path
import backtrader as bt


def load_config(config_path: str = None) -> dict:
    """从config.yaml加载配置文件

    Args:
        config_path: 配置文件路径，默认为当前目录下的config.yaml

    Returns:
        dict: 配置字典
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


class RenkoEmaStrategy(bt.Strategy):
    """Renko EMA Crossover Strategy.

    This strategy combines Renko chart filtering with Exponential Moving Average
    (EMA) crossover signals to generate trade entries and exits. The Renko filter
    smooths price data by only updating when price moves by a specified brick size,
    which can help reduce noise and false signals.

    Entry conditions:
        - Long: Fast EMA crosses above slow EMA

    Exit conditions:
        - Fast EMA crosses below slow EMA

    Attributes:
        order (bt.Order): Reference to the current pending order. None if no order.
        bar_num (int): Counter for the number of bars processed.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.
        fast_ema (bt.indicators.EMA): Fast exponential moving average indicator.
        slow_ema (bt.indicators.EMA): Slow exponential moving average indicator.
        crossover (bt.indicators.CrossOver): Crossover indicator for the two EMAs.
        p (AutoOrderedDict): Strategy parameters containing:
            - stake (int): Number of shares per trade. Default is 10.
            - fast_period (int): Period for fast EMA. Default is 10.
            - slow_period (int): Period for slow EMA. Default is 20.
            - renko_brick_size (float): Brick size for Renko filter. Default is 1.0.
    """
    params = dict(
        stake=10,
        fast_period=10,
        slow_period=20,
        renko_brick_size=1.0,
    )

    def __init__(self):
        """Initialize the Renko EMA Crossover Strategy.

        Sets up the Renko filter on the data feed, creates the fast and slow
        EMA indicators, initializes the crossover indicator, and sets up
        tracking variables for orders and bar counts.
        """
        # Add Renko filter to smooth price data
        self.data.addfilter(bt.filters.Renko, size=self.p.renko_brick_size)

        # Create EMA indicators for crossover signals
        self.fast_ema = bt.indicators.EMA(self.data, period=self.p.fast_period)
        self.slow_ema = bt.indicators.EMA(self.data, period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ema, self.slow_ema)

        # Initialize tracking variables
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        This method is called by the backtrader engine whenever an order's
        status changes. It tracks completed orders to maintain buy/sell counts.

        Args:
            order (bt.Order): The order object with updated status information.

        Note:
            Orders with status Submitted or Accepted are ignored as they are
            still pending execution. Only Completed orders update the tracking
            counters.
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

        This method is called on every bar of data after indicator calculations.
        It implements the core trading logic:

        1. Increments the bar counter
        2. Skips if there's a pending order
        3. Enters long when fast EMA crosses above slow EMA (no position)
        4. Exits position when fast EMA crosses below slow EMA

        Note:
            The strategy only takes long positions. Short positions are not used.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            if self.crossover[0] > 0:
                self.order = self.buy(size=self.p.stake)
        elif self.crossover[0] < 0:
            self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        RenkoEmaStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredRenkoEmaStrategy(RenkoEmaStrategy):
        params = params

    return ConfiguredRenkoEmaStrategy
