#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Chandelier Exit Strategy.

This module implements the Chandelier Exit strategy which combines
moving average crossover with the Chandelier Exit indicator for
trend-following with volatility-adjusted trailing stops.

Reference: backtrader-strategies-compendium/strategies/MA_Chandelier.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class ChandelierExitIndicator(bt.Indicator):
    """Chandelier Exit volatility-based trailing stop indicator.

    This indicator calculates trailing stop levels for both long and short
    positions based on the Highest high, Lowest low, and Average True Range (ATR).

    Lines:
        long: Long exit level (Highest high - ATR * multiplier)
        short: Short exit level (Lowest low + ATR * multiplier)

    Params:
        period (int): Lookback period for Highest/Lowest and ATR calculation. Default is 22.
        multip (float): Multiplier for ATR. Default is 3.
    """
    lines = ('long', 'short')
    params = dict(period=22, multip=3)
    plotinfo = dict(subplot=False)

    def __init__(self):
        """Initialize the Chandelier Exit indicator.

        Sets up the calculation pipeline by:
        1. Computing the Highest high over the lookback period
        2. Computing the Lowest low over the lookback period
        3. Computing Average True Range (ATR) over the lookback period
        4. Calculating long exit as Highest high - (ATR * multiplier)
        5. Calculating short exit as Lowest low + (ATR * multiplier)
        """
        highest = bt.ind.Highest(self.data.high, period=self.p.period)
        lowest = bt.ind.Lowest(self.data.low, period=self.p.period)
        atr = self.p.multip * bt.ind.ATR(self.data, period=self.p.period)
        self.lines.long = highest - atr
        self.lines.short = lowest + atr


class ChandelierExitStrategy(bt.Strategy):
    """Chandelier Exit trailing stop strategy.

    This strategy combines moving average crossover with the Chandelier Exit
    indicator to determine entry and exit points.

    Entry conditions:
        Long: SMA8 > SMA15 AND Price > Chandelier Short

    Exit conditions:
        SMA8 < SMA15 AND Price < Chandelier Long

    Args:
        stake (int): Number of shares to trade. Default is 10.
        sma_fast (int): Fast SMA period. Default is 8.
        sma_slow (int): Slow SMA period. Default is 15.
        ce_period (int): Chandelier Exit period. Default is 22.
        ce_mult (float): Chandelier Exit ATR multiplier. Default is 3.

    Attributes:
        sma_fast: Fast simple moving average indicator.
        sma_slow: Slow simple moving average indicator.
        ce: Chandelier Exit indicator instance.
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Total number of buy orders executed.
        sell_count: Total number of sell orders executed.
    """
    params = dict(
        stake=10,
        sma_fast=8,
        sma_slow=15,
        ce_period=22,
        ce_mult=3,
    )

    def __init__(self):
        """Initialize the Chandelier Exit strategy.

        Sets up the required indicators and initializes tracking variables:
        - Fast and slow Simple Moving Averages for trend detection
        - Chandelier Exit indicator for trailing stop levels
        - Order tracking to prevent duplicate orders
        - Counters for bars processed and trades executed
        """
        self.sma_fast = bt.indicators.SMA(self.data, period=self.p.sma_fast)
        self.sma_slow = bt.indicators.SMA(self.data, period=self.p.sma_slow)
        self.ce = ChandelierExitIndicator(
            self.data, period=self.p.ce_period, multip=self.p.ce_mult
        )

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status notifications.

        Updates trade counters when orders are completed and clears the
        pending order reference. Ignores orders that are still pending
        (Submitted or Accepted status).

        Args:
            order: The Order object with updated status information.
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
        """Execute the strategy logic for each bar.

        This method is called on every bar during the backtest. It:
        1. Increments the bar counter
        2. Skips trading if an order is already pending
        3. If no position: Enters long when SMA fast > SMA slow AND
           price > Chandelier short exit level
        4. If in position: Exits when SMA fast < SMA slow AND
           price < Chandelier long exit level

        The Chandelier Exit acts as a volatility-adjusted trailing stop,
        helping to protect profits during adverse price movements.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # SMA golden cross AND price above Chandelier Short
            if self.sma_fast[0] > self.sma_slow[0] and self.data.close[0] > self.ce.short[0]:
                self.order = self.buy(size=self.p.stake)
        else:
            # SMA death cross AND price below Chandelier Long
            if self.sma_fast[0] < self.sma_slow[0] and self.data.close[0] < self.ce.long[0]:
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
    """Create a ChandelierExitStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of ChandelierExitStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return ChandelierExitStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Chandelier Exit Strategy")
    print("Params:", get_strategy_params())
