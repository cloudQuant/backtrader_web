#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OCO (One Cancels Other) Order Strategy

Reference: backtrader-master2/samples/oco/oco.py
Multiple orders where execution of one cancels the others
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
from pathlib import Path
from typing import Dict, Any

import yaml
import backtrader as bt


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Configuration dictionary.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class OCOOrderStrategy(bt.Strategy):
    """Strategy demonstrating OCO (One Cancels Other) order functionality.

    This strategy implements a moving average crossover system with OCO limit
    orders to enter positions. When a bullish crossover is detected, three
    limit buy orders are placed at different price levels using OCO linkage.
    When one order fills, the others are automatically cancelled.

    Strategy Logic:
        1. Entry: When fast SMA crosses above slow SMA (bullish signal)
        2. OCO Orders: Place 3 limit orders at progressively lower prices
        3. Execution: First order to fill cancels the others
        4. Exit: Close position after holding for specified number of bars

    OCO Order Structure:
        - Order 1 (Primary): Close to current price, short validity (3 days)
        - Order 2: Further from price, long validity (1000 days)
        - Order 3: Furthest from price, long validity (1000 days)
        - All orders linked via OCO: only one can execute
    """

    params = dict(
        p1=5,          # Fast SMA period
        p2=15,         # Slow SMA period
        limit=0.005,   # Limit price offset (0.5%)
        limdays=3,     # Primary order validity
        limdays2=1000, # Secondary order validity
        hold=10,       # Hold period in bars
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables.

        Creates the dual moving average system for signal generation and
        initializes all tracking variables for OCO order management and
        performance monitoring.
        """
        # Create Simple Moving Averages for crossover signal
        ma1 = bt.ind.SMA(period=self.p.p1)  # Fast SMA (5 periods)
        ma2 = bt.ind.SMA(period=self.p.p2)  # Slow SMA (15 periods)

        # Create crossover signal detector
        self.cross = bt.ind.CrossOver(ma1, ma2)

        # Track OCO order references
        self.orefs = list()

        # Track when position was opened for time-based exit
        self.holdstart = 0

        # Initialize performance tracking variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates and manage OCO order tracking.

        This method is called by the backtrader engine whenever an order's
        status changes. It tracks completed orders and manages the OCO
        order reference list by removing cancelled or completed orders.

        Args:
            order (bt.Order): The order object with updated status information.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
            # Record bar when position was opened for time-based exit
            self.holdstart = len(self)

        # Remove completed or cancelled orders from OCO tracking list
        if not order.alive() and order.ref in self.orefs:
            self.orefs.remove(order.ref)

    def notify_trade(self, trade):
        """Handle trade completion updates and calculate profit/loss.

        This method is called when a trade is closed (position fully exited).
        It tracks wins, losses, and cumulative profit to evaluate strategy
        performance.

        Args:
            trade (bt.Trade): The trade object with profit/loss information.
        """
        if trade.isclosed:
            # Add trade profit/loss to cumulative total
            self.sum_profit += trade.pnlcomm

            # Track win/loss statistics
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Implements the OCO order strategy:
        1. Wait for any active OCO orders to complete before placing new ones
        2. On bullish crossover, place 3 limit orders at different price levels
        3. Link orders via OCO so only one can execute
        4. Hold position for specified number of bars then exit
        """
        self.bar_num += 1

        # Wait for OCO orders to complete/cancel before placing new ones
        if self.orefs:
            return

        if not self.position:
            # No current position - look for entry signal
            if self.cross > 0.0:
                # Bullish crossover: place OCO limit orders
                # Calculate three progressively lower price levels
                p1 = self.data.close[0] * (1.0 - self.p.limit)
                p2 = self.data.close[0] * (1.0 - 2 * 2 * self.p.limit)
                p3 = self.data.close[0] * (1.0 - 3 * 3 * self.p.limit)

                # Set validity periods for orders
                valid1 = datetime.timedelta(self.p.limdays)
                valid2 = valid3 = datetime.timedelta(self.p.limdays2)

                # Create OCO limit buy orders
                # o1: Primary order at closest level
                # o2, o3: Secondary orders linked to o1 via OCO
                o1 = self.buy(exectype=bt.Order.Limit, price=p1, valid=valid1, size=1)
                o2 = self.buy(exectype=bt.Order.Limit, price=p2, valid=valid2, oco=o1, size=1)
                o3 = self.buy(exectype=bt.Order.Limit, price=p3, valid=valid3, oco=o1, size=1)

                # Track order references to prevent duplicate placement
                self.orefs = [o1.ref, o2.ref, o3.ref]

        else:
            # Currently in position - implement time-based exit
            if (len(self) - self.holdstart) >= self.p.hold:
                self.close()

    def stop(self):
        """Print strategy performance summary after backtest completion.

        This method is called once at the end of the backtest. It calculates
        and displays win rate and final statistics to evaluate strategy
        performance with OCO orders.
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0

        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_oco_order_strategy(config: Dict[str, Any] = None):
    """Run the OCO Order Strategy backtest.

    Args:
        config: Configuration dictionary. If None, loads from config.yaml.

    Returns:
        Configured Cerebro instance.
    """
    if config is None:
        config = load_config()

    # Extract parameters from config
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Add strategy with parameters from config
    cerebro.addstrategy(OCOOrderStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_oco_order_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
