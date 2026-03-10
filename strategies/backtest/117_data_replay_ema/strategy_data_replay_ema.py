#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Data Replay - EMA Dual Moving Average Strategy.

This module tests data replay functionality using an EMA dual moving
average crossover strategy. Daily data is replayed as weekly data.

Reference: test_58_data_replay.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ReplayEMAStrategy(bt.Strategy):
    """Strategy for testing data replay - EMA dual moving average crossover.

    Strategy logic:
    - Buy when fast EMA crosses above slow EMA
    - Sell and close position when fast EMA crosses below slow EMA
    """
    params = (('fast_period', 12), ('slow_period', 26))

    def __init__(self):
        """Initialize the EMA crossover strategy with indicators and tracking variables.

        Sets up the exponential moving averages, crossover indicator, and
        initializes counters for tracking strategy execution.
        """
        self.fast_ema = bt.ind.EMA(period=self.p.fast_period)
        self.slow_ema = bt.ind.EMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ema, self.slow_ema)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def log(self, txt, dt=None):
        """Log strategy messages with timestamps.

        Args:
            txt: The message text to log.
            dt: Optional datetime object. If not provided, uses the current
                bar's datetime from the first data feed.
        """
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def notify_order(self, order):
        """Handle order status updates and log order execution details.

        Called by the backtrader engine when an order's status changes. Logs
        order events including rejections, cancellations, partial fills, and
        completed executions. Tracks buy and sell order counts.

        Args:
            order: The order object with updated status information.
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
        """Handle trade status updates and log trade performance metrics.

        Called by the backtrader engine when a trade's status changes. Logs
        profit/loss information when trades are closed and entry prices when
        trades are opened.

        Args:
            trade: The trade object with updated status information.
        """
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def next(self):
        """Execute trading logic for each bar.

        Implements the EMA crossover strategy:
        - When fast EMA crosses above slow EMA (crossover > 0): close any existing
          position and open a new long position
        - When fast EMA crosses below slow EMA (crossover < 0): close any
          existing position

        Only one order is allowed at a time. The bar counter is incremented
        on each call for test verification purposes.
        """
        self.bar_num += 1
        if self.order:
            return
        if self.crossover > 0:
            if self.position:
                self.order = self.close()
            self.order = self.buy()
        elif self.crossover < 0:
            if self.position:
                self.order = self.close()


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to the config.yaml file. If None, uses default path.

    Returns:
        Dictionary containing configuration parameters.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def get_strategy_params(config=None):
    """Get strategy parameters from config.

    Args:
        config: Configuration dictionary. If None, loads from default path.

    Returns:
        Dictionary of strategy parameters.
    """
    if config is None:
        config = load_config()

    return config.get('params', {})


def create_strategy(**kwargs):
    """Create a ReplayEMAStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of ReplayEMAStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return ReplayEMAStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Data Replay EMA Strategy")
    print("Params:", get_strategy_params())
