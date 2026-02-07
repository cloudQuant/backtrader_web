#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Up Down Candles Strategy

涨跌蜡烛均值回归策略 - 基于蜡烛强度和价格收益率识别超买超卖机会。
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


class UpDownCandleStrength(bt.Indicator):
    """Up Down Candle Strength Indicator.

    This indicator calculates the strength of price movement by measuring
    the ratio of up candles to down candles over a specified period.

    The strength value ranges from 0.0 (all down candles) to 1.0 (all up candles),
    with 0.5 indicating an equal number of up and down candles.

    Attributes:
        lines.strength: The calculated strength ratio (0.0 to 1.0).
        params.period: The number of periods to analyze for candle strength.

    Note:
        A strength value of 0.5 is returned when there are no clear up or down
        candles (i.e., all candles have equal open and close prices).
    """
    lines = ('strength',)
    params = dict(period=20,)

    def __init__(self):
        """Initialize the UpDownCandleStrength indicator.

        Sets the minimum period required for calculation based on the
        configured period parameter.
        """
        self.addminperiod(self.p.period)

    def next(self):
        """Calculate the candle strength ratio for the current bar.

        Counts the number of up candles (close > open) and down candles
        (close < open) over the specified period and calculates the ratio.

        The strength value is calculated as:
            strength = up_count / (up_count + down_count)

        If no candles have clear directional movement (all open == close),
        the strength is set to 0.5 (neutral).
        """
        up_count = 0
        down_count = 0
        for i in range(self.p.period):
            if self.data.close[-i] > self.data.open[-i]:
                up_count += 1
            elif self.data.close[-i] < self.data.open[-i]:
                down_count += 1

        total = up_count + down_count
        if total == 0:
            self.lines.strength[0] = 0.5
        else:
            self.lines.strength[0] = up_count / total


class PercentReturnsPeriod(bt.Indicator):
    """Period Percentage Returns Indicator.

    Calculates the percentage return of price over a specified period.
    This measures the cumulative price change from N periods ago to the
    current period, expressed as a percentage.

    Attributes:
        lines.returns: The calculated percentage return.
        params.period: The number of periods to calculate returns over.

    Note:
        Returns are calculated as:
            returns = (current_close - close_N_periods_ago) / close_N_periods_ago
    """
    lines = ('returns',)
    params = dict(period=40,)

    def __init__(self):
        """Initialize the PercentReturnsPeriod indicator.

        Sets the minimum period required for calculation based on the
        configured period parameter.
        """
        self.addminperiod(self.p.period)

    def next(self):
        """Calculate the percentage return for the current bar.

        Computes the return from N periods ago to the current period.
        Returns 0 if the closing price N periods ago is zero to avoid
        division by zero errors.

        The return is calculated as:
            returns = (close[0] - close[-period]) / close[-period]
        """
        if self.data.close[-self.p.period] != 0:
            self.lines.returns[0] = (self.data.close[0] - self.data.close[-self.p.period]) / self.data.close[-self.p.period]
        else:
            self.lines.returns[0] = 0


class UpDownCandlesStrategy(bt.Strategy):
    """Up Down Candles Strategy.

    A mean reversion strategy that identifies overbought and oversold
    conditions based on price returns over a specified period. The strategy
    assumes that extreme price movements will revert to the mean.

    Trading Logic:
        - When returns are strongly negative (< -threshold), the asset is
          considered oversold and the strategy goes long.
        - When returns are strongly positive (> +threshold), the asset is
          considered overbought and the strategy goes short.
        - Positions are closed when returns revert toward zero.

    Attributes:
        params.stake: The number of shares/units to trade per order.
        params.strength_period: Period for candle strength calculation (default: 20).
        params.returns_period: Period for returns calculation (default: 40).
        params.returns_threshold: Minimum return threshold to trigger trades (default: 0.01).
    """
    params = dict(
        stake=10,
        strength_period=20,
        returns_period=40,
        returns_threshold=0.01,
    )

    def __init__(self):
        """Initialize the UpDownCandlesStrategy.

        Sets up the indicators and tracking variables for the strategy.
        Creates the candle strength and period returns indicators, and
        initializes counters for tracking trades and bars.
        """
        self.dataclose = self.datas[0].close

        self.strength = UpDownCandleStrength(
            self.datas[0],
            period=self.p.strength_period
        )

        self.returns = PercentReturnsPeriod(
            self.datas[0],
            period=self.p.returns_period
        )

        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by Backtrader when an order's status changes. Tracks completed
        orders by incrementing buy/sell counters and resets the order reference
        when the order is complete or cancelled.

        Args:
            order: The order object with updated status information.
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
        """Execute the strategy logic for each bar.

        This method is called by Backtrader for each bar of data.
        Implements the mean reversion trading logic:

        1. Skip if there's a pending order
        2. Skip if returns are within the threshold (no signal)
        3. If no position:
           - Go long when returns are strongly negative (oversold)
           - Go short when returns are strongly positive (overbought)
        4. If in position:
           - Close long positions when returns turn positive
           - Close short positions when returns turn negative
        """
        self.bar_num += 1

        if self.order:
            return

        returns = self.returns[0]

        if abs(returns) < self.p.returns_threshold:
            return

        if not self.position:
            # Mean reversion: short when overbought, long when oversold
            if returns < -self.p.returns_threshold:
                self.order = self.buy(size=self.p.stake)
            elif returns > self.p.returns_threshold:
                self.order = self.sell(size=self.p.stake)
        else:
            # Close position when returns revert to within threshold
            if self.position.size > 0 and returns > 0:
                self.order = self.close()
            elif self.position.size < 0 and returns < 0:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        UpDownCandlesStrategy: 配置好的策略实例
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredUpDownCandlesStrategy(UpDownCandlesStrategy):
        params = params

    return ConfiguredUpDownCandlesStrategy
