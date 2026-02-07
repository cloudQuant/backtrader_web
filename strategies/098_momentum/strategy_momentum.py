#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Momentum Trading Strategy.

This strategy uses the Momentum indicator to identify trend changes and
generate trading signals. It goes long when momentum turns positive and
exits when momentum turns negative.

The Momentum indicator measures the rate of change (speed) of price movements.
It calculates the difference between the current price and the price N periods ago.

Trading Logic:
    - Entry (Long): When momentum changes from negative to positive (crosses above 0)
    - Exit: When momentum changes from positive to negative (crosses below 0)

Parameters:
    stake (int): Number of shares/contracts per trade. Default is 10.
    period (int): Period for the momentum indicator calculation. Default is 20.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class MomentumStrategy(bt.Strategy):
    """Momentum-based trading strategy.

    This strategy uses the Momentum indicator to identify trend changes and
    generate trading signals. It goes long when momentum turns positive and
    exits when momentum turns negative.

    Trading Logic:
        - Entry (Long): When momentum changes from negative to positive (crosses above 0)
        - Exit: When momentum changes from positive to negative (crosses below 0)

    Attributes:
        momentum (bt.indicators.Momentum): The momentum indicator with configurable period.
        order (bt.Order): Current pending order, or None if no order is pending.
        bar_num (int): Counter for the number of bars processed.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.

    Parameters:
        stake (int): Number of shares/contracts per trade. Default is 10.
        period (int): Period for the momentum indicator calculation. Default is 20.
    """

    params = dict(
        stake=10,
        period=20,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables.

        Creates the momentum indicator and initializes tracking variables
        for order management and statistics.
        """
        # Calculate momentum indicator on closing prices
        self.momentum = bt.indicators.Momentum(self.data.close, period=self.p.period)

        # Initialize state variables
        self.order = None  # Track current pending order
        self.bar_num = 0   # Count of bars processed
        self.buy_count = 0  # Statistics tracking
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by Backtrader when an order's status changes. Updates statistics
        and clears the pending order reference when the order is completed or
        cancelled.

        Args:
            order (bt.Order): The order object that was updated. Status can be
                Submitted, Accepted, Completed, Canceled, Margin, or Rejected.

        Note:
            This method does not process orders in Submitted or Accepted states
            as they are still pending execution.
        """
        # Ignore pending orders
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return

        # Update trade statistics
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

        # Clear order reference
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        This method is called by Backtrader for each bar of data. It implements
        the core trading logic:

        1. Check if there's a pending order (skip if yes)
        2. Ensure we have enough data for momentum calculation
        3. If not in position: Check for momentum cross above 0 (buy signal)
        4. If in position: Check for momentum cross below 0 (exit signal)

        The momentum crossover is detected by comparing the previous bar's
        momentum value with the current bar's value.
        """
        self.bar_num += 1

        # Wait for pending order to complete
        if self.order:
            return

        # Ensure minimum data for momentum calculation
        if len(self) < 2:
            return

        if not self.position:
            # Entry logic: Momentum changes from negative to positive
            # [-1] is previous bar, [0] is current bar
            if self.momentum[-1] <= 0 and self.momentum[0] > 0:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit logic: Momentum changes from positive to negative
            if self.momentum[-1] > 0 and self.momentum[0] <= 0:
                self.order = self.close()


def load_config(config_path=None):
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        dict: Configuration dictionary with strategy parameters.
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
        dict: Strategy parameters for backtrader.
    """
    if config is None:
        config = load_config()

    return config.get('params', {})


__all__ = ['MomentumStrategy', 'load_config', 'get_strategy_params']
