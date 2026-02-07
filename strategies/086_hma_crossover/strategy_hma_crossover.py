#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HMA Crossover Hull Moving Average Strategy

Hull移动平均线交叉策略 - 基于HMA的趋势跟踪系统。
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


class HmaCrossoverStrategy(bt.Strategy):
    """HMA Crossover Hull Moving Average Strategy.

    This strategy implements a dual moving average crossover system using
    Hull Moving Averages (HMA), which are known for reducing lag compared
    to traditional moving averages.

    Trading Logic:
        Long Entry:
            - Fast HMA crosses above slow HMA (bullish signal)
        Short Entry:
            - Fast HMA crosses below slow HMA (bearish signal)
        Long Exit:
            - Fast HMA falls below slow HMA
        Short Exit:
            - Fast HMA rises above slow HMA

    The strategy also calculates Average True Range (ATR) as a reference
    for market volatility, though it is not directly used in position sizing
    or stop-loss logic in this implementation.

    Attributes:
        dataclose: Reference to the close price of the primary data feed.
        hma_fast: Fast Hull Moving Average indicator.
        hma_slow: Slow Hull Moving Average indicator.
        atr: Average True Range indicator for volatility measurement.
        order: Reference to the current pending order.
        prev_rel: Boolean indicating if fast HMA was above slow HMA on
            the previous bar.
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for the number of buy orders executed.
        sell_count: Counter for the number of sell orders executed.

    Parameters:
        stake (int): Number of shares/contracts per trade. Default is 10.
        hma_fast (int): Period for the fast HMA. Default is 60.
        hma_slow (int): Period for the slow HMA. Default is 90.
        atr_period (int): Period for the ATR indicator. Default is 14.
    """
    params = dict(
        stake=10,
        hma_fast=60,
        hma_slow=90,
        atr_period=14,
    )

    def __init__(self):
        """Initialize the HMA Crossover strategy.

        Sets up the indicators and tracking variables for the strategy.
        Initializes fast and slow Hull Moving Averages, ATR indicator,
        and counters for tracking trades and bars.
        """
        self.dataclose = self.datas[0].close

        # Hull Moving Average indicators
        self.hma_fast = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.hma_fast
        )
        self.hma_slow = bt.indicators.HullMovingAverage(
            self.data.close, period=self.p.hma_slow
        )

        # ATR indicator
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)

        self.order = None
        self.prev_rel = None  # fast > slow on previous bar

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        This method is called by the backtrader engine when an order's
        status changes. It tracks completed orders by incrementing the
        buy_count or sell_count counters and clears the pending order
        reference when the order is no longer active.

        Args:
            order (bt.Order): The order object with updated status.

        Order Status Handling:
            - Submitted/Accepted: Order is pending, no action needed.
            - Completed: Order was filled, increment the appropriate counter.
            - Other statuses: Clear the order reference to allow new trades.
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

        This method is called by the backtrader engine for each bar of data.
        It implements the core crossover logic to generate entry and exit signals.

        The strategy:
        1. Checks if there's a pending order (if so, waits)
        2. Compares fast and slow HMA values to detect crossovers
        3. Enters long when fast HMA crosses above slow HMA
        4. Enters short when fast HMA crosses below slow HMA
        5. Exits positions when the crossover reverses

        Note:
            The crossover is detected by comparing the current relationship
            (rel_now) with the previous bar's relationship (prev_rel). A
            crossover occurs when these values differ.
        """
        self.bar_num += 1

        if self.order:
            return

        f0, s0 = float(self.hma_fast[0]), float(self.hma_slow[0])
        rel_now = f0 > s0

        if self.prev_rel is None:
            self.prev_rel = rel_now
            return

        pos_sz = self.position.size

        # Long entry: fast line crosses above slow line from below
        if pos_sz == 0 and (not self.prev_rel) and rel_now:
            self.order = self.buy(size=self.p.stake)

        # Short entry: fast line crosses below slow line from above
        elif pos_sz == 0 and self.prev_rel and (not rel_now):
            self.order = self.sell(size=self.p.stake)

        # Long exit: fast line falls below slow line
        elif pos_sz > 0 and not rel_now:
            self.order = self.close()

        # Short exit: fast line rises above slow line
        elif pos_sz < 0 and rel_now:
            self.order = self.close()

        self.prev_rel = rel_now


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        HmaCrossoverStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredHmaCrossoverStrategy(HmaCrossoverStrategy):
        params = params

    return ConfiguredHmaCrossoverStrategy
