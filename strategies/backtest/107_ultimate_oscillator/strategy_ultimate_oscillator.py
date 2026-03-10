#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ultimate Oscillator Strategy.

This strategy uses the Ultimate Oscillator (UO) indicator to identify
overbought and oversold conditions. UO combines three time periods
(7, 14, and 28 periods) to reduce false signals and provide more
reliable trading signals.

The Ultimate Oscillator was developed by Larry Williams to address
the problem of divergences that occur with single-timeframe oscillators.
By integrating three different timeframes, the UO provides a more
balanced view of momentum across short, intermediate, and long-term periods.

Calculation:
    The UO is calculated using three separate average true range-based
    buying pressures over different periods, then weighted and combined
    into a single oscillator ranging from 0 to 100.

Key concepts:
    - Values above 70 suggest overbought conditions
    - Values below 30 suggest oversold conditions
    - Bullish divergence: Price makes new low but UO doesn't (potential reversal)
    - Bearish divergence: Price makes new high but UO doesn't (potential reversal)

Trading Logic:
    Entry (Long): UO < 30 (oversold condition)
    Exit: UO > 70 (overbought condition)

Parameters:
    stake: Number of shares/contracts per trade (default: 10)
    p1: First timeframe period (default: 7)
    p2: Second timeframe period (default: 14)
    p3: Third timeframe period (default: 28)
    oversold: Oversold threshold (default: 30)
    overbought: Overbought threshold (default: 70)

Note:
    The multi-timeframe approach makes the UO less prone to whipsaws
    and false signals compared to single-timeframe oscillators like RSI
    or Stochastic.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class UltimateOscillatorStrategy(bt.Strategy):
    """Ultimate Oscillator momentum trading strategy.

    This strategy uses the Ultimate Oscillator (UO) indicator to identify
    overbought and oversold conditions. UO combines three time periods
    (7, 14, and 28 periods) to reduce false signals and provide more
    reliable trading signals.

    Entry Conditions:
        - Long: UO < 30 (oversold condition)

    Exit Conditions:
        - UO > 70 (overbought condition)

    Attributes:
        uo: Ultimate Oscillator indicator instance.
        order: Current pending order.
        bar_num: Counter for processed bars.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
    """

    params = dict(
        stake=10,
        p1=7,
        p2=14,
        p3=28,
        oversold=30,
        overbought=70,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        self.uo = bt.indicators.UltimateOscillator(
            self.data, p1=self.p.p1, p2=self.p.p2, p3=self.p.p3
        )

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
        3. Generate entry/exit signals based on UO thresholds
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Entry: UO in oversold territory
            if self.uo[0] < self.p.oversold:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: UO in overbought territory
            if self.uo[0] > self.p.overbought:
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


__all__ = ['UltimateOscillatorStrategy', 'load_config', 'get_strategy_params']
