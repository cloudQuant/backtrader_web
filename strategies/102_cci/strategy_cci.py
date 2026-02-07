#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Commodity Channel Index (CCI) Strategy.

This strategy uses the CCI indicator to identify overbought and oversold
conditions for generating trading signals.

The Commodity Channel Index (CCI) was developed by Donald Lambert and is
a momentum-based oscillator used to help determine when an asset is reaching
overbought or oversold conditions. Unlike many other oscillators, CCI is
not range-bound, which allows it to extend beyond typical limits.

Key concepts:
    - CCI measures the current price level relative to an average price level
    - Values above +100 suggest overbought conditions
    - Values below -100 suggest oversold conditions
    - The indicator is scale-independent and can be used on any timeframe

Entry conditions:
    - Long: CCI crosses above -100 from below (rising from oversold)

Exit conditions:
    - CCI crosses below +100 from above (falling from overbought)

The strategy uses threshold crossings rather than absolute level crossings,
which helps enter positions as momentum starts to shift rather than waiting
for extreme readings to reverse.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class CciStrategy(bt.Strategy):
    """Commodity Channel Index (CCI) momentum trading strategy.

    This strategy uses the CCI indicator to identify overbought and oversold
    conditions for generating trading signals.

    Entry Conditions:
        - Long: CCI crosses above -100 from below (rising from oversold)

    Exit Conditions:
        - CCI crosses below +100 from above (falling from overbought)

    Attributes:
        cci: CCI indicator instance.
        order: Current pending order.
        bar_num: Counter for processed bars.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """

    params = dict(
        stake=10,
        period=20,
        oversold=-100,
        overbought=100,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.cci = bt.indicators.CommodityChannelIndex(self.data, period=self.p.period)

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
        4. Generate entry/exit signals based on CCI
        """
        self.bar_num += 1

        if self.order:
            return

        if len(self) < 2:
            return

        if not self.position:
            # Entry: CCI crossing above oversold threshold
            if self.cci[-1] < self.p.oversold and self.cci[0] >= self.p.oversold:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: CCI crossing below overbought threshold
            if self.cci[-1] > self.p.overbought and self.cci[0] <= self.p.overbought:
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


__all__ = ['CciStrategy', 'load_config', 'get_strategy_params']
