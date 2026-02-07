#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MACD + DMI Simplified Strategy

MACD+DMI简化策略 - 结合MACD动量和DMI趋势指标的交易系统。
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


class MacdDmiSimpleStrategy(bt.Strategy):
    """MACD + DMI Simplified Strategy.

    A trading strategy that combines MACD (Moving Average Convergence Divergence)
    and DMI (Directional Movement Index) indicators to generate trading signals.
    This is a simplified version designed to avoid attribute conflicts present in
    earlier backtrader implementations.

    Entry Logic:
        - Long: MACD line crosses above signal line (golden cross)
        - Short: MACD line crosses below signal line (death cross)

    Exit Logic:
        - Long position: Close when MACD crosses below signal line
        - Short position: Close when MACD crosses above signal line

    Attributes:
        macd: MACD indicator with configurable periods
        dmi: Directional Movement Index indicator
        macd_cross: Crossover signal indicator (positive for golden cross,
            negative for death cross)
        order: Current pending order (None if no order pending)
        bar_num: Counter for the number of bars processed
        buy_count: Total number of buy orders executed
        sell_count: Total number of sell orders executed

    Parameters:
        stake: Number of shares/contracts per trade (default: 10)
        macd_fast: Fast EMA period for MACD calculation (default: 12)
        macd_slow: Slow EMA period for MACD calculation (default: 26)
        macd_signal: Signal line EMA period for MACD (default: 9)
        dmi_period: Period for DMI calculation (default: 14)
    """
    params = dict(
        stake=10,
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        dmi_period=14,
    )

    def __init__(self):
        """Initialize the MACD + DMI strategy.

        Sets up the technical indicators and initializes tracking variables for
        order management and statistics.
        """
        # MACD indicator
        self.macd = bt.indicators.MACD(
            self.data,
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )

        # DMI indicator
        self.dmi = bt.indicators.DirectionalMovementIndex(
            self.data, period=self.p.dmi_period
        )

        # MACD crossover signal
        self.macd_cross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by backtrader when an order's status changes. This method updates
        the buy/sell counters when orders are completed and clears the pending
        order reference.

        Args:
            order: The order object with updated status.

        Note:
            Orders with status Submitted or Accepted are ignored as they are
            still pending execution. Only Completed orders trigger counter updates.
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

        This method is called by backtrader for each new data bar. It implements
        the core trading strategy:

        1. Increments the bar counter
        2. Checks if there's a pending order (if so, waits)
        3. If no position: enters long on MACD golden cross, short on death cross
        4. If in position: exits on MACD crossover reversal

        Entry signals are based on the MACD crossover indicator:
        - macd_cross > 0: MACD line crossed above signal line (bullish)
        - macd_cross < 0: MACD line crossed below signal line (bearish)

        Note:
            The DMI indicator is calculated but not actively used in this
            simplified version. It's maintained for potential future enhancements.
        """
        self.bar_num += 1

        if self.order:
            return

        plus_di = self.dmi.DIplus[0]
        minus_di = self.dmi.DIminus[0]

        if not self.position:
            # Long entry: MACD golden cross
            if self.macd_cross[0] > 0:
                self.order = self.buy(size=self.p.stake)
            # Short entry: MACD death cross
            elif self.macd_cross[0] < 0:
                self.order = self.sell(size=self.p.stake)
        else:
            # Exit condition: MACD reverse crossover
            if self.position.size > 0 and self.macd_cross[0] < 0:
                self.order = self.close()
            elif self.position.size < 0 and self.macd_cross[0] > 0:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        MacdDmiSimpleStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredMacdDmiSimpleStrategy(MacdDmiSimpleStrategy):
        params = params

    return ConfiguredMacdDmiSimpleStrategy
