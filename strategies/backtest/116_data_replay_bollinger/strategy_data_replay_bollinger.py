#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Data Replay - Bollinger Bands Strategy.

This module tests the data replay functionality using a Bollinger Bands
breakout strategy. Daily data is replayed as weekly data.

Reference: test_58_data_replay.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ReplayBollingerStrategy(bt.Strategy):
    """Test data replay strategy with Bollinger Bands breakout.

    Strategy logic:
        - Buy when price breaks above the upper band
        - Sell and close position when price falls below the middle band
    """
    params = (('period', 20), ('devfactor', 2.0))

    def __init__(self):
        """Initialize the ReplayBollingerStrategy.

        Sets up the Bollinger Bands indicator and initializes tracking
        variables for orders, bars, and trade counts.
        """
        self.boll = bt.ind.BollingerBands(period=self.p.period, devfactor=self.p.devfactor)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def log(self, txt, dt=None):
        """Log strategy messages with timestamp.

        Args:
            txt: The message text to log.
            dt: Optional datetime object for the log entry. If None, uses the
                current bar's datetime from the first data feed.
        """
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def notify_order(self, order):
        """Handle order status changes and updates.

        Called by the backtrader engine when an order's status changes. Logs
        order events and updates the buy/sell counters.

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
        """Handle trade lifecycle events.

        Called when a trade is opened or closed. Logs the trade status,
        profit/loss information, and price details.

        Args:
            trade: The trade object with updated status and P&L information.
        """
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def next(self):
        """Execute trading logic for each bar.

        This method is called by the backtrader engine for each bar of data.
        Implements the Bollinger Bands breakout strategy:
        - Buy when price breaks above the upper band (no existing position)
        - Close position when price falls below the middle band (existing position)

        Only one order is allowed at a time to prevent over-trading.
        """
        self.bar_num += 1
        if self.order:
            return

        # Buy when price breaks above the upper band
        if self.data.close[0] > self.boll.top[0]:
            if not self.position:
                self.order = self.buy()
        # Sell when price falls below the middle band
        elif self.data.close[0] < self.boll.mid[0]:
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
    """Create a ReplayBollingerStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of ReplayBollingerStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return ReplayBollingerStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Data Replay Bollinger Bands Strategy")
    print("Params:", get_strategy_params())
