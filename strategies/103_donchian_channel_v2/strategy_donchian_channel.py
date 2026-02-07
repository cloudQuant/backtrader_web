#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Donchian Channel Strategy.

This is a classic breakout trading strategy based on the Donchian Channel,
developed by Richard Donchian. It forms the core of the famous Turtle Trading
System popularized by Richard Dennis.

The Donchian Channel consists of three lines:
    - Upper Channel: N-period highest high
    - Lower Channel: N-period lowest low
    - Middle Channel: Average of upper and lower

Trading Logic:
    Entry (Long): Price breaks above the N-period highest high
    Exit: Price breaks below the N-period lowest low

The strategy is purely price-action based and does not use any derived
indicators. It aims to capture large trends by entering on breakouts
and exiting when the trend reverses. This is a trend-following system
that experiences whipsaws in ranging markets but can generate large
profits during sustained trends.

Parameters:
    stake: Number of shares/contracts per trade
    period: Lookback period for channel calculation (default: 20)

Note:
    This strategy performs best in markets with clear, sustained trends
    and can experience significant drawdowns during choppy or ranging
    periods. Consider using filters like ADX or volume to reduce false
    breakouts.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class DonchianChannelStrategy(bt.Strategy):
    """Donchian Channel strategy.

    Entry conditions:
    - Long: Price breaks above N-period highest price.

    Exit conditions:
    - Price breaks below N-period lowest price.
    """

    params = dict(
        stake=10,
        period=20,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.highest = bt.indicators.Highest(self.data.high, period=self.p.period)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.p.period)

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
            # Price breaks above upper band
            if self.data.close[0] > self.highest[-1]:
                self.order = self.buy(size=self.p.stake)
        else:
            # Price breaks below lower band
            if self.data.close[0] < self.lowest[-1]:
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


__all__ = ['DonchianChannelStrategy', 'load_config', 'get_strategy_params']
