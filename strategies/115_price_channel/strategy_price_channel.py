#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Price Channel Breakout Strategy.

This module implements a trend-following strategy based on price channel
breakouts. It enters long positions when price creates an N-day high and
exits when price falls below an M-day low.

Reference: backtrader-strategies-compendium
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class PriceChannelStrategy(bt.Strategy):
    """Price Channel breakout trading strategy.

    This strategy implements a trend-following approach based on price channel
    breakouts. It enters long positions when the price breaks above the highest
    high of the specified entry period and exits when the price breaks below
    the lowest low of the exit period.

    Entry conditions:
        - Long: Price creates N-day high (breaks above entry_period highest high)

    Exit conditions:
        - Long: Price falls below M-day low (breaks below exit_period lowest low)

    Attributes:
        params: Dictionary containing strategy parameters:
            - stake (int): Number of shares/contracts per trade (default: 10)
            - entry_period (int): Period for highest high calculation (default: 20)
            - exit_period (int): Period for lowest low calculation (default: 10)

    Note:
        This strategy only implements long positions. Short selling is not
        supported in this implementation.
    """
    params = dict(
        stake=10,
        entry_period=20,
        exit_period=10,
    )

    def __init__(self):
        """Initialize the Price Channel strategy with indicators and state variables.

        Sets up the highest high and lowest low indicators used for signal
        generation, and initializes tracking variables for order management
        and performance statistics.

        Attributes created:
            highest_entry: Indicator tracking the highest high over entry_period.
            lowest_exit: Indicator tracking the lowest low over exit_period.
            order: Reference to the current pending order (None if no pending order).
            bar_num: Counter for the number of bars processed.
            buy_count: Counter for the number of buy orders executed.
            sell_count: Counter for the number of sell orders executed.
        """
        self.highest_entry = bt.indicators.Highest(self.data.high, period=self.p.entry_period)
        self.lowest_exit = bt.indicators.Lowest(self.data.low, period=self.p.exit_period)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track execution statistics.

        Called by the backtrader engine when an order's status changes. Updates
        the buy/sell counters when orders are completed and clears the order
        reference when the order is no longer active.

        Args:
            order: The order object with updated status information.

        Note:
            This method ignores Submitted and Accepted status notifications,
            only processing Completed orders. The order reference is set to
            None after processing to allow new orders to be placed.
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
        It implements the core trading logic:

        1. Increments the bar counter
        2. Checks if there's a pending order (if so, returns early)
        3. If no position: Enters long when price breaks above entry_period high
        4. If has position: Exits when price breaks below exit_period low

        Note:
            The strategy uses [0] for current bar values and [-1] for
            previous bar values when comparing to indicator levels.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Price creates new high
            if self.data.high[0] >= self.highest_entry[-1]:
                self.order = self.buy(size=self.p.stake)
        else:
            # Price creates new low
            if self.data.low[0] <= self.lowest_exit[-1]:
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
    """Create a PriceChannelStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of PriceChannelStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return PriceChannelStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Price Channel Strategy")
    print("Params:", get_strategy_params())
