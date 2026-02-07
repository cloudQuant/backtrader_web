#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HMA MultiTrend multi-period Hull Moving Average trend strategy.

HMA多趋势策略 - 使用4条HMA判断趋势方向的多周期系统。
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


class HmaMultiTrendStrategy(bt.Strategy):
    """HMA MultiTrend multi-period Hull Moving Average trend strategy.

    Entry conditions:
        - Long: fast > mid1 > mid2 > mid3 (all HMAs in ascending order)
        - Short: fast < mid1 < mid2 < mid3 (all HMAs in descending order)

    Exit conditions:
        - Reverse trend signal
    """
    params = dict(
        stake=10,
        fast=10,
        mid1=20,
        mid2=30,
        mid3=50,
        atr_period=14,
        adx_period=14,
        adx_threshold=0.0,  # Disable ADX filter
    )

    def __init__(self):
        """Initialize the HMA MultiTrend strategy with indicators and tracking variables.

        Creates four Hull Moving Average indicators with different periods to
        establish a trend-following system. Also initializes ATR for volatility
        measurement and ADX for trend strength filtering. Sets up counters to
        track trading activity.
        """
        self.hma_fast = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.fast
        )
        self.hma_mid1 = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.mid1
        )
        self.hma_mid2 = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.mid2
        )
        self.hma_mid3 = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.mid3
        )

        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.adx = bt.indicators.ADX(self.data, period=self.p.adx_period)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track completed trades.

        Called by Backtrader when an order changes status. Counts completed
        buy and sell orders for performance tracking. Resets the order reference
        when the order is complete or cancelled.

        Args:
            order: The Backtrader Order object with updated status.
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
        """Execute trading logic for each bar in the backtest.

        Implements the core strategy logic:
        1. Checks if there's a pending order (no action if order pending)
        2. Applies ADX filter if enabled
        3. Evaluates trend conditions using HMA alignment
        4. Enters long when all HMAs are in ascending order
        5. Enters short when all HMAs are in descending order
        6. Exits positions when the trend reverses
        """
        self.bar_num += 1

        if self.order:
            return

        # ADX filter
        if self.adx[0] < self.p.adx_threshold:
            return

        # Trend conditions
        long_cond = (self.hma_fast[0] > self.hma_mid1[0] >
                     self.hma_mid2[0] > self.hma_mid3[0])
        short_cond = (self.hma_fast[0] < self.hma_mid1[0] <
                      self.hma_mid2[0] < self.hma_mid3[0])

        if not self.position:
            if long_cond:
                self.order = self.buy(size=self.p.stake)
            elif short_cond:
                self.order = self.sell(size=self.p.stake)
        else:
            # Close position on reverse signal
            if self.position.size > 0 and short_cond:
                self.order = self.close()
            elif self.position.size < 0 and long_cond:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        HmaMultiTrendStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredHmaMultiTrendStrategy(HmaMultiTrendStrategy):
        params = params

    return ConfiguredHmaMultiTrendStrategy
