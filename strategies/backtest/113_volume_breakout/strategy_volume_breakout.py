#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Volume Breakout Strategy.

This module implements a momentum-based trading strategy that uses volume
spikes combined with RSI indicators for entry and exit signals.

Reference: backtrader_NUPL_strategy/hope/Hope_vol.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class VolumeBreakoutStrategy(bt.Strategy):
    """A momentum-based trading strategy using volume breakout signals.

    This strategy identifies potential breakouts by monitoring volume spikes
    relative to a moving average. When volume exceeds the threshold, it enters
    a long position expecting continued momentum. Exit signals are based on
    RSI overbought conditions or a maximum holding period.

    Entry Logic:
        - Long entry: Current volume > N-day volume SMA * multiplier
        - This identifies unusual trading activity that may precede price moves

    Exit Logic:
        - RSI exit: RSI > threshold (default 70) indicating overbought conditions
        - Time exit: Position held for more than 5 bars

    Attributes:
        vol_ma: Simple moving average of volume for the specified period.
        rsi: Relative Strength Index indicator for exit signals.
        order: Current pending order object (None if no pending order).
        bar_num: Total number of bars processed during the backtest.
        bar_executed: Bar number when the last order was executed.
        buy_count: Total number of buy orders executed during the backtest.
        sell_count: Total number of sell orders executed during the backtest.

    Parameters:
        stake: Number of shares/contracts per trade (default: 10).
        vol_period: Period for volume moving average (default: 20).
        vol_mult: Volume multiplier for breakout signal (default: 1.05).
        rsi_period: Period for RSI calculation (default: 14).
        rsi_exit: RSI threshold for exit signal (default: 70).
    """
    params = dict(
        stake=10,
        vol_period=20,
        vol_mult=1.05,
        rsi_period=14,
        rsi_exit=70,
    )

    def __init__(self):
        """Initialize the VolumeBreakoutStrategy with indicators and tracking variables.

        Sets up the technical indicators (volume SMA and RSI) and initializes
        variables for tracking orders and trade statistics. Indicators are
        automatically registered with the strategy by backtrader.
        """
        self.vol_ma = bt.indicators.SMA(self.data.volume, period=self.p.vol_period)
        self.rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)

        self.order = None
        self.bar_num = 0
        self.bar_executed = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates from the broker.

        This method is called by backtrader whenever an order's status changes.
        It tracks completed orders to maintain buy/sell statistics and clears
        the pending order reference when the order is complete or cancelled.

        Args:
            order: The order object containing status and execution details.
                Status can be Submitted, Accepted, Completed, or Cancelled.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.bar_executed = len(self)
            else:
                self.sell_count += 1
        self.order = None

    def next(self):
        """Execute the main trading logic for each bar.

        This method is called by backtrader for every new bar of data. It implements
        the core trading logic:

        1. Increments the bar counter
        2. Checks if there's a pending order (no action if pending)
        3. If not in position: checks for volume breakout signal to enter long
        4. If in position: checks for exit conditions (RSI overbought or time exit)

        The strategy only takes long positions and enters when volume spikes above
        the moving average threshold, expecting continued momentum.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Volume breakout condition for entry
            if self.data.volume[0] > self.vol_ma[0] * self.p.vol_mult:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit conditions: RSI overbought or maximum holding period reached
            if self.rsi[0] > self.p.rsi_exit or len(self) > self.bar_executed + 5:
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
    """Create a VolumeBreakoutStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of VolumeBreakoutStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return VolumeBreakoutStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Volume Breakout Strategy")
    print("Params:", get_strategy_params())
