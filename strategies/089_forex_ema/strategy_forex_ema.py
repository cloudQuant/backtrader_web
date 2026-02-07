#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Forex EMA Triple Moving Average Strategy

外汇三指数移动平均线策略 - 基于EMA排列的趋势跟踪系统。
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


class ForexEmaStrategy(bt.Strategy):
    """Forex EMA Triple Moving Average Strategy.

    This strategy implements a triple EMA crossover system commonly used in
    forex trading. It uses three exponential moving averages with different
    periods to identify trend direction and generate trading signals.

    Strategy Logic:
        The strategy enters long positions when the short-term EMA crosses
        above the medium-term EMA, with confirmation from price action and
        EMA alignment. Conversely, it enters short positions when the
        short-term EMA crosses below the medium-term EMA with similar
        confirmations.

        Positions are closed when the crossover signal reverses, providing
        a natural exit mechanism that follows price momentum.

    Parameters:
        stake (int): Number of units/shares per trade. Default is 10.
        shortema (int): Period for the short-term EMA. Default is 5.
        mediumema (int): Period for the medium-term EMA. Default is 20.
        longema (int): Period for the long-term EMA. Default is 50.

    Attributes:
        shortema (ExponentialMovingAverage): Short-term EMA indicator.
        mediumema (ExponentialMovingAverage): Medium-term EMA indicator.
        longema (ExponentialMovingAverage): Long-term EMA indicator.
        shortemacrossover (CrossOver): Crossover indicator for short/medium EMAs.
        order (Order): Current pending order, or None if no pending order.
        bar_num (int): Counter for the number of bars processed.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.

    Entry Conditions:
        Long Entry:
            - Short-term EMA crosses above medium-term EMA (crossover > 0)
            - Current bar's low is above long-term EMA
            - Medium-term EMA is above long-term EMA
            - Short-term EMA is above long-term EMA

        Short Entry:
            - Short-term EMA crosses below medium-term EMA (crossover < 0)
            - Current bar's high is below long-term EMA
            - Medium-term EMA is below long-term EMA
            - Short-term EMA is below long-term EMA

    Exit Conditions:
        - Long position closed when short-term EMA crosses below medium-term EMA
        - Short position closed when short-term EMA crosses above medium-term EMA

    Example:
        >>> cerebro = bt.Cerebro()
        >>> cerebro.addstrategy(ForexEmaStrategy, stake=10, shortema=5,
        ...                     mediumema=20, longema=50)
        >>> cerebro.run()
    """
    params = dict(
        stake=10,
        shortema=5,
        mediumema=20,
        longema=50,
    )

    def __init__(self):
        """Initialize the Forex EMA strategy with indicators and state variables.

        This method sets up the three exponential moving average indicators
        and the crossover indicator used for signal generation. It also
        initializes state variables for tracking orders and execution counts.

        Indicators Created:
            - shortema: EMA with period from params.shortema
            - mediumema: EMA with period from params.mediumema
            - longema: EMA with period from params.longema
            - shortemacrossover: CrossOver of shortema and mediumema

        State Variables Initialized:
            - order: Set to None, tracks pending orders
            - bar_num: Set to 0, counts bars processed
            - buy_count: Set to 0, tracks buy executions
            - sell_count: Set to 0, tracks sell executions
        """
        self.shortema = bt.indicators.ExponentialMovingAverage(
            self.data, period=self.p.shortema
        )
        self.mediumema = bt.indicators.ExponentialMovingAverage(
            self.data, period=self.p.mediumema
        )
        self.longema = bt.indicators.ExponentialMovingAverage(
            self.data, period=self.p.longema
        )

        self.shortemacrossover = bt.indicators.CrossOver(self.shortema, self.mediumema)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track executed trades.

        This callback method is invoked by the backtrader engine whenever an
        order's status changes. It counts completed buy and sell orders and
        clears the pending order reference when the order is filled or
        cancelled.

        Args:
            order (Order): The order object with updated status.

        Order Status Handling:
            - Submitted/Acpected: Order is pending, no action taken
            - Completed: Order filled, increment buy_count or sell_count
            - Other statuses (Cancelled, Margin, Expired): Order cleared

        Side Effects:
            - Increments buy_count when a buy order is completed
            - Increments sell_count when a sell order is completed
            - Sets self.order to None when order is no longer pending
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
        It implements the core strategy logic: checking entry conditions,
        placing orders, and managing existing positions.

        Execution Flow:
            1. Increment bar counter
            2. Skip processing if an order is already pending
            3. If no position, check entry conditions (long or short)
            4. If position exists, check exit conditions

        Entry Conditions:
            Long Entry:
                - Crossover signal > 0 (short EMA crossed above medium EMA)
                - Current bar low > long EMA
                - Medium EMA > long EMA
                - Short EMA > long EMA

            Short Entry:
                - Crossover signal < 0 (short EMA crossed below medium EMA)
                - Current bar high < long EMA
                - Medium EMA < long EMA
                - Short EMA < long EMA

        Exit Conditions:
            - Long position: close when crossover < 0
            - Short position: close when crossover > 0

        Side Effects:
            - Places buy/sell/close orders via self.order
            - Updates self.bar_num counter
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Long entry condition
            if (self.shortemacrossover > 0 and
                self.data.low[0] > self.longema[0] and
                self.mediumema[0] > self.longema[0] and
                self.shortema[0] > self.longema[0]):
                self.order = self.buy(size=self.p.stake)
            # Short entry condition
            elif (self.shortemacrossover < 0 and
                  self.data.high[0] < self.longema[0] and
                  self.mediumema[0] < self.longema[0] and
                  self.shortema[0] < self.longema[0]):
                self.order = self.sell(size=self.p.stake)
        else:
            # Exit condition: reverse crossover
            if self.position.size > 0 and self.shortemacrossover < 0:
                self.order = self.close()
            elif self.position.size < 0 and self.shortemacrossover > 0:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        ForexEmaStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredForexEmaStrategy(ForexEmaStrategy):
        params = params

    return ConfiguredForexEmaStrategy
