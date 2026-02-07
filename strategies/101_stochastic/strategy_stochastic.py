#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stochastic Oscillator Strategy.

This strategy uses the Stochastic oscillator (also known as KD indicator)
to generate trading signals based on crossovers and overbought/oversold levels.

The Stochastic oscillator was developed by George Lane and compares
a specific closing price of a security to a range of its prices over a
certain period of time.

Components:
    - %K line: The current value of the stochastic
    - %D line: A moving average of %K (typically 3-period SMA)

Trading Logic:
    Entry (Long): K line crosses above D line and in oversold zone (K < 20)
    Exit: K line crosses below D line and in overbought zone (K > 80)

The strategy waits for both the crossover signal AND the price to be
in the appropriate zone (oversold for entry, overbought for exit).
This helps filter out false signals that occur in neutral territory.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class StochasticStrategy(bt.Strategy):
    """Stochastic oscillator strategy.

    Entry conditions:
    - Long: K line crosses above D line and in oversold zone (K < 20)

    Exit conditions:
    - K line crosses below D line and in overbought zone (K > 80)
    """

    params = dict(
        stake=10,
        period=14,
        period_dfast=3,
        oversold=20,
        overbought=80,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.stoch = bt.indicators.Stochastic(
            self.data,
            period=self.p.period,
            period_dfast=self.p.period_dfast,
        )
        self.crossover = bt.indicators.CrossOver(self.stoch.percK, self.stoch.percD)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object that was updated.
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
        """Execute trading logic for each bar."""
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # K crosses above D and in oversold zone
            if self.crossover[0] > 0 and self.stoch.percK[0] < self.p.oversold:
                self.order = self.buy(size=self.p.stake)
        else:
            # K crosses below D and in overbought zone
            if self.crossover[0] < 0 and self.stoch.percK[0] > self.p.overbought:
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


__all__ = ['StochasticStrategy', 'load_config', 'get_strategy_params']
