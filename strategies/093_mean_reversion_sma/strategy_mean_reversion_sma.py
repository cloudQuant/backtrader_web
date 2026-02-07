#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mean Reversion SMA Strategy

均值回归SMA策略 - 基于简单移动平均线的均值回归交易系统。
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import yaml
import math
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


class MeanReversionSmaStrategy(bt.Strategy):
    """A mean reversion trading strategy based on Simple Moving Average (SMA).

    This strategy implements a mean reversion approach by identifying when prices
    deviate significantly from their SMA. It enters long positions when the price
    drops below the SMA by a specified percentage threshold (dip_size) and exits
    when the price returns to the SMA level.

    Entry Conditions:
        - Buy when price drops below SMA by more than dip_size percentage.

    Exit Conditions:
        - Sell when price returns to or above SMA.

    Attributes:
        sma (bt.indicators.SMA): The Simple Moving Average indicator.
        order (bt.Order): The current pending order, or None if no order is pending.
        bar_num (int): Counter tracking the number of bars processed.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.

    Args:
        period (int): The period for the SMA calculation. Default is 20.
        order_percentage (float): The percentage of available cash to use per
            trade. Default is 0.95 (95%).
        dip_size (float): The percentage drop below SMA required to trigger a
            buy signal. Default is 0.025 (2.5%).

    Example:
        >>> cerebro = bt.Cerebro()
        >>> cerebro.addstrategy(MeanReversionSmaStrategy, period=20, dip_size=0.03)
    """
    params = dict(
        period=20,
        order_percentage=0.95,
        dip_size=0.025,
    )

    def __init__(self):
        """Initialize the MeanReversionSmaStrategy.

        Sets up the SMA indicator and initializes tracking variables for orders
        and trade statistics.
        """
        self.sma = bt.indicators.SMA(self.data, period=self.p.period)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def log(self, txt, dt=None):
        """Log a message with timestamp for strategy monitoring.

        Args:
            txt (str): The message text to log.
            dt (datetime.datetime, optional): The datetime to use for the log
                entry. If None, uses the current bar's datetime.
        """
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def notify_order(self, order):
        """Handle order status updates and logging.

        Called by the backtrader engine when an order changes status. Logs
        order completion, rejection, cancellation, and other status changes.
        Updates buy/sell counters when orders are completed.

        Args:
            order (bt.Order): The order object with updated status.
        """
        if not order.alive():
            self.order = None

        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Rejected:
            self.log(f"Rejected : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Margin:
            self.log(f"Margin : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Cancelled:
            self.log(f"Concelled : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Partial:
            self.log(f"Partial : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.log(
                    f" BUY : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

            else:  # Sell
                self.sell_count += 1
                self.log(
                    f" SELL : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

    def notify_trade(self, trade):
        """Handle trade lifecycle events (open/close).

        Called by the backtrader engine when a trade is opened or closed.
        Logs profit/loss information when trades close.

        Args:
            trade (bt.Trade): The trade object with updated status.
        """
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def next(self):
        """Execute trading logic for each bar.

        This method is called by the backtrader engine for each bar. Implements
        the mean reversion strategy logic:
        1. If no position exists, check if price has dropped below SMA by
           dip_size percentage and buy if so.
        2. If a position exists, close it when price returns to SMA level.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Price drops below SMA by more than dip_size percentage
            dip_ratio = (self.data.close[0] / self.sma[0]) - 1
            if dip_ratio <= -self.p.dip_size:
                amount = self.p.order_percentage * self.broker.cash
                size = math.floor(amount / self.data.close[0])
                if size > 0:
                    self.order = self.buy(size=size)
        else:
            # Price returns to SMA
            if self.data.close[0] >= self.sma[0]:
                self.order = self.close()


# 从配置文件加载参数的便捷函数
def create_strategy_from_config():
    """从config.yaml创建策略实例的便捷函数

    Returns:
        MeanReversionSmaStrategy: 配置好的策略类
    """
    config = load_config()
    params = config.get('params', {})

    class ConfiguredMeanReversionSmaStrategy(MeanReversionSmaStrategy):
        params = params

    return ConfiguredMeanReversionSmaStrategy
