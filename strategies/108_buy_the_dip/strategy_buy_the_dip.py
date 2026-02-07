#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Buy The Dip Strategy.

This module implements a mean-reversion trading strategy that buys after
consecutive down days and sells after holding for a specified number of days.

Reference: backtrader-strategies-compendium/strategies/BuyTheDip.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class BuyTheDipStrategy(bt.Strategy):
    """A mean-reversion strategy that buys after consecutive down days.

    This strategy implements a simple buy-the-dip approach by detecting
    consecutive downward price movements and entering a long position.
    The position is closed after a fixed holding period, regardless of
    profit or loss.

    Entry conditions:
        - Consecutive N days of decline (default: 3 days)

    Exit conditions:
        - Sell after holding for N days (default: 5 days)

    Attributes:
        order: The current pending order object, or None if no order is pending.
        bar_executed: The bar number when the last order was executed.
        bar_num: Total number of bars processed during the backtest.
        buy_count: Total number of buy orders executed.
        sell_count: Total number of sell orders executed.

    Args:
        stake: Number of shares to buy/sell per trade (default: 10).
        hold_days: Number of bars to hold position before selling (default: 5).
        consecutive_down: Number of consecutive down bars to trigger buy signal
            (default: 3).

    """

    params = dict(
        stake=10,
        hold_days=5,
        consecutive_down=3,
    )

    def __init__(self):
        """Initialize the strategy with default tracking variables.

        Sets up instance variables to track orders, execution state, and
        trading statistics.
        """
        self.order = None
        self.bar_executed = 0
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track execution statistics.

        Called by Backtrader when an order changes status. Updates trading
        statistics when orders are completed and clears the pending order
        reference.

        Args:
            order: The order object that has been updated.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
            self.bar_executed = len(self)
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        This method is called by Backtrader for each bar of data. It implements
        the core strategy logic:
        1. Increments the bar counter
        2. Skips if there's a pending order
        3. For entries: checks for consecutive down days and buys if detected
        4. For exits: closes position after the specified holding period
        """
        self.bar_num += 1

        if self.order:
            return

        if len(self) < self.p.consecutive_down + 1:
            return

        if not self.position:
            # Check for consecutive down days
            all_down = True
            for i in range(self.p.consecutive_down):
                if self.data.close[-i] >= self.data.close[-i-1]:
                    all_down = False
                    break

            if all_down:
                self.order = self.buy(size=self.p.stake)
        else:
            # Sell after holding for N days
            if len(self) >= self.bar_executed + self.p.hold_days:
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


# Strategy factory function that can be used by the backtesting engine
def create_strategy(**kwargs):
    """Create a BuyTheDipStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of BuyTheDipStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return BuyTheDipStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Buy The Dip Strategy")
    print("Params:", get_strategy_params())
