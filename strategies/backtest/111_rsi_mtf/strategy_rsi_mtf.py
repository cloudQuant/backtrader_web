#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RSI MTF (Multiple Time Frame) Strategy.

This module implements a multi-timeframe approach using RSI indicators
with different periods to identify trading opportunities.

Reference: backtrader-strategies-compendium/strategies/RsiMtf.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class RsiMtfStrategy(bt.Strategy):
    """RSI MTF (Multiple Time Frame) Strategy.

    This strategy implements a multi-timeframe approach using RSI indicators
    with different periods to identify trading opportunities. By combining
    a long-period RSI (trend filter) with a short-period RSI (momentum
    trigger), the strategy aims to enter trades when both trend and momentum
    align and exit when momentum reverses.

    Strategy Logic:
        Entry (Long):
            - Long period RSI > buy_rsi_long (default 50): Indicates
              bullish trend strength
            - Short period RSI > buy_rsi_short (default 70): Indicates
              strong short-term momentum
            - Both conditions must be true simultaneously

        Exit:
            - Short period RSI < sell_rsi_short (default 35): Indicates
              momentum loss and potential reversal

    Attributes:
        rsi_long (bt.indicators.RSI): Long period RSI indicator for trend
            identification. Default period is 14 bars.
        rsi_short (bt.indicators.RSI): Short period RSI indicator for
            momentum detection. Default period is 3 bars.
        order (bt.Order): Current pending order. Used to track order status
            and prevent duplicate orders.
        bar_num (int): Counter tracking the number of bars processed during
            the backtest.
        buy_count (int): Total number of buy orders executed during the
            strategy run.
        sell_count (int): Total number of sell orders executed during the
            strategy run.

    Parameters:
        stake (int): Number of shares/contracts per trade. Default is 10.
        period_long (int): Period for long-term RSI. Default is 14.
        period_short (int): Period for short-term RSI. Default is 3.
        buy_rsi_long (float): RSI level for long-term trend confirmation.
            Default is 50.
        buy_rsi_short (float): RSI level for short-term momentum trigger.
            Default is 70.
        sell_rsi_short (float): RSI level for exit signal. Default is 35.
    """
    params = dict(
        stake=10,
        period_long=14,
        period_short=3,
        buy_rsi_long=50,
        buy_rsi_short=70,
        sell_rsi_short=35,
    )

    def __init__(self):
        """Initialize the RSI MTF strategy.

        Sets up the RSI indicators with long and short periods and initializes
        tracking variables for orders and statistics.

        The initialization creates:
            - Long period RSI: Used for trend identification
            - Short period RSI: Used for momentum signals
            - Order tracking: Prevents duplicate orders
            - Counters: For buy/sell orders and bars processed
        """
        self.rsi_long = bt.indicators.RSI(self.data, period=self.p.period_long)
        self.rsi_short = bt.indicators.RSI(self.data, period=self.p.period_short)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status notifications.

        This method is called by the backtrader engine when an order's status
        changes. It updates the buy/sell counters and clears the pending order
        reference when the order is completed.

        Args:
            order (bt.Order): The order object containing status updates and
                execution details.

        Order Status Handling:
            - Submitted/Accepted: Order pending execution, no action taken
            - Completed: Order executed, increment buy/sell counter
            - Other statuses: Clear the order reference
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

        This method is called for each bar of data during the backtest.
        It implements the RSI MTF strategy by checking entry and exit conditions.

        Entry Logic:
            - Only enter when not currently in a position
            - Requires both RSI conditions to be met:
                * Long period RSI > buy_rsi_long (default 50)
                * Short period RSI > buy_rsi_short (default 70)
            - Executes a buy order for stake shares

        Exit Logic:
            - Only exit when currently in a position
            - Triggered when short period RSI < sell_rsi_short (default 35)
            - Closes the entire position

        Risk Management:
            - Checks for pending orders before placing new ones
            - Maintains self.order to prevent duplicate orders
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Entry: Long period RSI strong AND Short period RSI strong
            if self.rsi_long[0] > self.p.buy_rsi_long and self.rsi_short[0] > self.p.buy_rsi_short:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: Short period RSI declines
            if self.rsi_short[0] < self.p.sell_rsi_short:
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
    """Create a RsiMtfStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of RsiMtfStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return RsiMtfStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("RSI MTF Strategy")
    print("Params:", get_strategy_params())
