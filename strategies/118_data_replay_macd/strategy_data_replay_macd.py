#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Data Replay - MACD Strategy.

This module tests the data replay functionality using MACD crossover
strategy. Daily data is replayed as weekly data.

Reference source: test_58_data_replay.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ReplayMACDStrategy(bt.Strategy):
    """Strategy for testing data replay - MACD crossover.

    Strategy logic:
        - Buy when MACD line crosses above signal line
        - Sell and close position when MACD line crosses below signal line

    Attributes:
        macd: MACD indicator instance.
        crossover: CrossOver indicator for MACD and signal line.
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """
    params = (('fast_period', 12), ('slow_period', 26), ('signal_period', 9))

    def __init__(self):
        """Initialize the ReplayMACDStrategy with indicators and tracking variables.

        This method sets up the MACD indicator with configurable periods and
        initializes tracking variables for order management and statistics.

        The strategy uses:
        - MACD indicator for trend analysis
        - CrossOver indicator to detect signal line crossovers
        - Order tracking to prevent multiple simultaneous orders
        - Counters for buy/sell orders and processed bars
        """
        self.macd = bt.ind.MACD(
            period_me1=self.p.fast_period,
            period_me2=self.p.slow_period,
            period_signal=self.p.signal_period
        )
        self.crossover = bt.ind.CrossOver(self.macd.macd, self.macd.signal)
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def log(self, txt, dt=None):
        """Log a message with timestamp for this strategy.

        This method prints log messages with an ISO-formatted timestamp, using
        the current bar's datetime if no timestamp is provided.

        Args:
            txt: The message text to log.
            dt: Optional datetime object for the log entry. If None, uses the
                current bar's datetime from the first data feed.
        """
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def notify_order(self, order):
        """Handle order status changes and update tracking variables.

        This method is called by the backtrader engine whenever an order's status
        changes. It logs order events and updates the buy/sell counters for
        completed orders.

        Args:
            order: The order object with updated status information.

        Order Statuses Handled:
            - Submitted: Order has been submitted to the broker.
            - Accepted: Order has been accepted by the broker.
            - Rejected: Order was rejected (insufficient funds, etc.).
            - Margin: Order requires margin (not enough cash).
            - Cancelled: Order was cancelled.
            - Partial: Order was partially filled.
            - Completed: Order was fully executed.

        Side Effects:
            - Updates self.buy_count when buy orders complete.
            - Updates self.sell_count when sell orders complete.
            - Sets self.order to None when order is no longer alive.
            - Logs all order status changes.
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
        """Handle trade lifecycle events and log trade statistics.

        This method is called by the backtrader engine when a trade's status
        changes. It logs profit/loss information when trades close and entry
        prices when trades are opened.

        Args:
            trade: The trade object with updated status information.

        Trade States Handled:
            - Open: Trade has been opened (position entered).
            - Closed: Trade has been closed (position exited).

        Side Effects:
            - Logs closed trades with symbol, gross profit, and net profit.
            - Logs opened trades with symbol and entry price.
        """
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def next(self):
        """Execute trading logic for each bar in the backtest.

        This method is called by the backtrader engine for each bar after all
        indicators have been calculated. It implements the MACD crossover strategy:
        - Buy when MACD crosses above the signal line
        - Sell and close position when MACD crosses below the signal line

        The method also logs detailed indicator values for debugging purposes,
        including MACD, signal line, and crossover values for each bar.

        Trading Logic:
            1. Check for pending orders and wait if one exists
            2. If crossover > 0 (MACD crosses above signal):
               - Close existing position if any
               - Open new long position
            3. If crossover < 0 (MACD crosses below signal):
               - Close existing position if any

        Side Effects:
            - Increments self.bar_num counter
            - Logs detailed indicator values for each bar
            - May create buy or close orders
            - Updates self.order with pending order reference
        """
        self.bar_num += 1
        # Print detailed MACD values for debugging in first 10 bars and key positions
        macd_val = self.macd.macd[0] if len(self.macd.macd) > 0 else 'N/A'
        signal_val = self.macd.signal[0] if len(self.macd.signal) > 0 else 'N/A'
        me1_val = self.macd.me1[0] if len(self.macd.me1) > 0 else 'N/A'
        me2_val = self.macd.me2[0] if len(self.macd.me2) > 0 else 'N/A'
        self.log(f"bar_num: {self.bar_num}, close: {self.data.close[0]}, len: {len(self.data)}, me1: {me1_val}, me2: {me2_val}, MACD: {macd_val}, signal: {signal_val}, crossover: {self.crossover[0]}")
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
    """Create a ReplayMACDStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of ReplayMACDStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return ReplayMACDStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Data Replay MACD Strategy")
    print("Params:", get_strategy_params())
