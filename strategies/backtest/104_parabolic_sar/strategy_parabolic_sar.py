#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Parabolic SAR (Stop and Reverse) Strategy.

This strategy implements a trend-following system using the Parabolic SAR
indicator, which is a technical analysis method used to determine trend
direction and potential reversals. The Parabolic SAR was developed by
J. Welles Wilder Jr. and is particularly useful in trending markets.

The Parabolic SAR indicator:
    - Uses a series of dots placed above or below price bars
    - Dots below price indicate bullish trend (long position)
    - Dots above price indicate bearish trend (short position)
    - When dots flip from below to above, it generates a sell signal
    - When dots flip from above to below, it generates a buy signal
    - The acceleration factor (af) increases as the trend continues
    - Provides trailing stop-loss levels that adjust dynamically

Trading Logic:
    Entry (Long): When price crosses ABOVE SAR from below
    Exit: When price crosses BELOW SAR from above

The acceleration factor starts at a minimum value (typically 0.02) and
increases each time a new extreme is reached, up to a maximum value
(typically 0.2). This causes the SAR to converge toward price as the
trend continues, providing a trailing stop-loss that locks in profits.

Parameters:
    stake: Number of shares/units per trade (default: 10)
    af: Initial acceleration factor (default: 0.02)
    afmax: Maximum acceleration factor (default: 0.2)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ParabolicSarStrategy(bt.Strategy):
    """Parabolic SAR (Stop and Reverse) indicator-based trading strategy.

    This strategy implements a trend-following system using the Parabolic SAR
    indicator. The Parabolic SAR is particularly effective in trending markets
    as it provides clear entry and exit signals while also functioning as a
    trailing stop-loss mechanism.

    Trading Logic:
        The strategy uses crossover signals between price and SAR:
        - When price crosses ABOVE SAR from below: Enter long position
        - When price crosses BELOW SAR from above: Exit long position

    Entry Conditions:
        - No current position exists
        - Price closes above the SAR line (bullish signal)

    Exit Conditions:
        - Currently in long position
        - Price closes below the SAR line (bearish signal/reversal)

    Parameters:
        stake (int): Number of shares/units per trade (default: 10).
        af (float): Initial acceleration factor for SAR calculation (default: 0.02).
        afmax (float): Maximum acceleration factor (default: 0.2).

    Note:
        The Parabolic SAR is most effective in strong trending markets and
        can produce false signals in ranging or choppy markets. Consider
        combining with other indicators for filtering signals in sideways markets.
    """

    params = dict(
        stake=10,
        af=0.02,
        afmax=0.2,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables.

        Sets up the Parabolic SAR indicator with the specified parameters,
        creates a crossover detector, and initializes all tracking variables
        for monitoring strategy performance.
        """
        # Initialize Parabolic SAR indicator with acceleration factor parameters
        self.sar = bt.indicators.ParabolicSAR(
            self.data, af=self.p.af, afmax=self.p.afmax
        )

        # Create crossover indicator to detect when price crosses SAR
        self.crossover = bt.indicators.CrossOver(self.data.close, self.sar)

        # Initialize tracking variables
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track executed orders.

        This method is called by the backtrader engine whenever an order's
        status changes. It updates the buy/sell counters when orders are
        completed and clears the order reference.

        Args:
            order (bt.Order): The order object with updated status information.
        """
        # Ignore orders still waiting to be executed
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return

        # Track completed orders
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

        # Clear order reference to allow new orders
        self.order = None

    def next(self):
        """Execute trading logic on each bar.

        This method is called for every bar of data after all indicators
        have been calculated. It implements the core Parabolic SAR strategy:
        1. Check for pending orders and wait if one exists
        2. Generate buy signal when price crosses above SAR
        3. Generate exit signal when price crosses below SAR

        The strategy only takes long positions, using the SAR as both
        entry signal generator and trailing stop-loss.
        """
        self.bar_num += 1

        # Wait for pending order to complete before placing new orders
        if self.order:
            return

        if not self.position:
            # No current position - look for entry signal
            # Price crosses above SAR indicates potential uptrend start
            if self.crossover[0] > 0:
                # Enter long position with specified stake size
                self.order = self.buy(size=self.p.stake)
        else:
            # Currently in position - look for exit signal
            # Price crosses below SAR indicates trend reversal
            if self.crossover[0] < 0:
                # Close entire position
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


__all__ = ['ParabolicSarStrategy', 'load_config', 'get_strategy_params']
