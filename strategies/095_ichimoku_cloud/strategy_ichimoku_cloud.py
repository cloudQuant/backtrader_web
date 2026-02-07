#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ichimoku Cloud trading strategy.

Ichimoku云图策略 - 基于一目均衡表指标的趋势跟踪系统。
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


class IchimokuCloudStrategy(bt.Strategy):
    """Ichimoku Cloud trading strategy.

    This strategy implements a trend-following approach using the Ichimoku Kinko
    Hyo technical indicator. The Ichimoku Cloud (Kumo) is used to determine
    market trend direction and generate trading signals based on price position
    relative to the cloud boundaries.

    Entry Conditions:
        - Long: Price > Senkou Span A and Price > Senkou Span B (price is above
          the cloud, indicating bullish trend)

    Exit Conditions:
        - Price < Senkou Span A and Price < Senkou Span B (price breaks below
          both cloud boundaries, indicating trend reversal)

    Attributes:
        ichimoku: The Ichimoku indicator instance providing cloud calculations.
        order: Reference to the current pending order, or None if no order is
            pending.
        bar_num: Counter tracking the total number of bars processed.
        buy_count: Counter tracking the number of executed buy orders.
        sell_count: Counter tracking the number of executed sell orders.

    Parameters:
        stake: Number of shares/units per trade (default: 10).
        tenkan: Tenkan-sen (Conversion Line) period in bars (default: 9).
        kijun: Kijun-sen (Base Line) period in bars (default: 26).
        senkou: Senkou Span B period in bars (default: 52).
        senkou_lead: Forward displacement for cloud in bars (default: 26).
        chikou: Chikou Span (Lagging Line) displacement in bars (default: 26).
    """
    params = dict(
        stake=10,
        tenkan=9,
        kijun=26,
        senkou=52,
        senkou_lead=26,
        chikou=26,
    )

    def __init__(self):
        """Initialize the Ichimoku Cloud strategy.

        Sets up the Ichimoku indicator with configurable parameters and
        initializes tracking variables for order management and statistics.
        """
        self.ichimoku = bt.indicators.Ichimoku(
            self.data,
            tenkan=self.p.tenkan,
            kijun=self.p.kijun,
            senkou=self.p.senkou,
            senkou_lead=self.p.senkou_lead,
            chikou=self.p.chikou,
        )

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track trade execution statistics.

        This method is called by the backtrader engine when an order's status
        changes. It updates the buy/sell counters when orders are completed
        and resets the order reference when the order is no longer active.

        Args:
            order: The backtrader Order object with updated status information.
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

        This method is called by the backtrader engine for each new bar.
        It implements the core strategy logic:
        1. Checks for pending orders and returns if one exists
        2. Retrieves current price and Ichimoku cloud values
        3. Enters long position when price is above cloud
        4. Exits position when price breaks below cloud

        Trading Logic:
            - No position: Enter long if close > senkou_a AND close > senkou_b
            - Has position: Close position if close < senkou_a AND close < senkou_b
        """
        self.bar_num += 1

        if self.order:
            return

        close = self.data.close[0]
        senkou_a = self.ichimoku.senkou_span_a[0]
        senkou_b = self.ichimoku.senkou_span_b[0]

        if not self.position:
            # Price is above cloud (relaxed condition)
            if close > senkou_a and close > senkou_b:
                self.order = self.buy(size=self.p.stake)
        else:
            # Price breaks below both cloud boundaries
            if close < senkou_a and close < senkou_b:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        IchimokuCloudStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredIchimokuCloudStrategy(IchimokuCloudStrategy):
        params = params

    return ConfiguredIchimokuCloudStrategy
