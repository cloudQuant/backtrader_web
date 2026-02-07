#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UDVD (Upper/Lower Shadow Difference) Strategy

UDVD策略 - 基于K线实体动量的趋势跟踪系统。
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


class UdvdStrategy(bt.Strategy):
    """UDVD (Upper/Lower Shadow Difference) Trading Strategy.

    A simplified trend-following strategy that uses candlestick body momentum
    to determine market direction. The strategy calculates the Simple Moving
    Average (SMA) of the candle body (close - open) to smooth out price noise
    and identify the underlying trend.

    Trading Logic:
        - When SMA of candle body is positive: Enter long position (bullish trend)
        - When SMA of candle body becomes negative or zero: Exit long position

    The strategy assumes that sustained positive candle body pressure indicates
    institutional buying and an uptrend, while negative pressure indicates
    distribution and a downtrend.

    Attributes:
        order: Current pending order object, or None if no order is pending.
        bar_num: Counter tracking the number of bars processed during the backtest.
        buy_count: Total number of buy orders executed during the backtest.
        sell_count: Total number of sell orders executed during the backtest.
        candle_body: Indicator calculating close price minus open price for each bar.
        signal: Simple Moving Average of candle_body over the specified period.

    Args:
        stake: Number of shares/contracts to trade per order. Defaults to 10.
        period: Period for the SMA calculation used to smooth the candle body signal.
            A longer period provides smoother signals but slower reaction to trend changes.
            Defaults to 3.
    """
    params = dict(
        stake=10,
        period=3,
    )

    def __init__(self):
        """Initialize the UDVD strategy indicators and state variables.

        Creates the candle body indicator (close - open) and applies a Simple
        Moving Average (SMA) to smooth the signal. Also initializes tracking
        variables for order management and performance statistics.
        """
        # Calculate bullish/bearish candle signal
        self.candle_body = self.data.close - self.data.open
        self.signal = bt.indicators.SMA(self.candle_body, period=self.p.period)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track execution statistics.

        Called by the backtrader engine when an order's status changes.
        Updates buy/sell counters when orders are executed and clears
        the pending order reference.

        Args:
            order: The order object that has been updated. Contains status,
                execution price, size, and other order-related information.

        Order Status Handling:
            - Submitted/Accepted: No action taken, order still pending.
            - Completed: Increment buy_count or sell_count based on order type.
            - Other statuses: Clear the pending order reference.
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
        """Execute the main trading logic for each bar.

        This method is called by the backtrader engine for each new bar.
        It implements the core UDVD strategy logic: enter long when the
        smoothed candle body signal is positive, exit when it becomes negative.

        The method also ensures only one order is active at a time by
        checking self.order before placing new orders.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Signal is positive (overall bullish)
            if self.signal[0] > 0:
                self.order = self.buy(size=self.p.stake)
        else:
            # Signal is negative
            if self.signal[0] <= 0:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        UdvdStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredUdvdStrategy(UdvdStrategy):
        params = params

    return ConfiguredUdvdStrategy
