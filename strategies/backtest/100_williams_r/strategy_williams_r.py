#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Williams %R Strategy.

This strategy uses the Williams %R indicator to identify overbought and
oversold conditions for generating trading signals.

Williams %R was developed by Larry Williams and is a momentum indicator
that measures overbought and oversold levels. It is similar to the Stochastic
oscillator but uses a different scaling.

The indicator ranges from 0 to -100:
- Values above -20 indicate overbought conditions
- Values below -80 indicate oversold conditions
- The indicator is typically used with a 14-period lookback

Entry conditions:
    - Long: Williams %R < -80 (oversold) and starts rising

Exit conditions:
    - Williams %R > -20 (overbought)

The strategy waits for the indicator to show signs of reversal in
oversold territory before entering, which helps avoid catching falling knives.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class WilliamsRStrategy(bt.Strategy):
    """Williams %R momentum trading strategy.

    This strategy uses the Williams %R indicator to identify overbought and
    oversold conditions for generating trading signals.

    Entry Conditions:
        - Long: Williams %R < -80 (oversold) and starts rising

    Exit Conditions:
        - Williams %R > -20 (overbought)

    Attributes:
        williams: Williams %R indicator instance.
        order: Current pending order.
        bar_num: Counter for processed bars.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """

    params = dict(
        stake=10,
        period=14,
        oversold=-80,
        overbought=-20,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.williams = bt.indicators.WilliamsR(self.data, period=self.p.period)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track completed trades.

        Args:
            order: The order object with updated status.
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

        Implements the core strategy logic:
        1. Track bar progression
        2. Check for pending orders
        3. Ensure minimum data availability
        4. Generate entry/exit signals based on Williams %R
        """
        self.bar_num += 1

        if self.order:
            return

        if len(self) < 2:
            return

        if not self.position:
            # Entry: Williams %R rising from oversold territory
            if self.williams[-1] < self.p.oversold and self.williams[0] > self.williams[-1]:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: Williams %R entering overbought territory
            if self.williams[0] > self.p.overbought:
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


__all__ = ['WilliamsRStrategy', 'load_config', 'get_strategy_params']
