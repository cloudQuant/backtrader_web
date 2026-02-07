#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Supertrend RSI Strategy.

This module implements a trend-following strategy that combines the
SuperTrend indicator with RSI for additional confirmation.

Reference: backtrader-strategies-compendium/strategies/SupertrendRSI.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class SupertrendIndicator(bt.Indicator):
    """SuperTrend indicator for trend-following analysis.

    The SuperTrend indicator is a trend-following indicator that uses
    Average True Range (ATR) to determine the direction of the trend.
    It provides dynamic support and resistance levels based on price volatility.

    The indicator calculates:
        1. Basic Upper Band: (High + Low) / 2 - (ATR Multiplier * ATR)
        2. Basic Lower Band: (High + Low) / 2 + (ATR Multiplier * ATR)
        3. Final Bands: Incorporates previous period values for smoothness
        4. SuperTrend Line: Switches between final bands based on price action

    Attributes:
        atr: Average True Range indicator instance
        avg: Average of high and low prices (HL/2)
        basic_up: Basic upper band calculation
        basic_down: Basic lower band calculation

    Args:
        atr_period: Period for ATR calculation (default: 14)
        atr_multiplier: Multiplier for ATR bands (default: 3)
    """
    lines = ('supertrend', 'final_up', 'final_down')
    params = dict(atr_period=14, atr_multiplier=3)
    plotinfo = dict(subplot=False)

    def __init__(self):
        """Initialize the SuperTrend indicator.

        Calculates the ATR and basic bands needed for SuperTrend calculation.
        """
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.avg = (self.data.high + self.data.low) / 2
        self.basic_up = self.avg - self.p.atr_multiplier * self.atr
        self.basic_down = self.avg + self.p.atr_multiplier * self.atr

    def prenext(self):
        """Initialize indicator values before minimum period is reached.

        Sets all line values to zero during the warmup period before
        enough data is available for ATR calculation.
        """
        self.l.final_up[0] = 0
        self.l.final_down[0] = 0
        self.l.supertrend[0] = 0

    def next(self):
        """Calculate SuperTrend values for the current bar.

        The calculation logic:
        1. Update final_up band: If previous close > previous final_up,
           use max(basic_up, previous final_up) for continuity
        2. Update final_down band: If previous close < previous final_down,
           use min(basic_down, previous final_down) for continuity
        3. Determine SuperTrend line:
           - If current close > previous final_down: uptrend (use final_up)
           - If current close < previous final_up: downtrend (use final_down)
           - Otherwise: maintain previous SuperTrend value
        """
        if self.data.close[-1] > self.l.final_up[-1]:
            self.l.final_up[0] = max(self.basic_up[0], self.l.final_up[-1])
        else:
            self.l.final_up[0] = self.basic_up[0]

        if self.data.close[-1] < self.l.final_down[-1]:
            self.l.final_down[0] = min(self.basic_down[0], self.l.final_down[-1])
        else:
            self.l.final_down[0] = self.basic_down[0]

        if self.data.close[0] > self.l.final_down[-1]:
            self.l.supertrend[0] = self.l.final_up[0]
        elif self.data.close[0] < self.l.final_up[-1]:
            self.l.supertrend[0] = self.l.final_down[0]
        else:
            self.l.supertrend[0] = self.l.supertrend[-1]


class SupertrendRsiStrategy(bt.Strategy):
    """Supertrend RSI strategy.

    This strategy combines SuperTrend and RSI indicators to generate
    long-only trading signals.

    Entry conditions:
        - Long: Price > SuperTrend AND RSI > threshold (default 40)

    Exit conditions:
        - Price < SuperTrend

    Attributes:
        supertrend: SuperTrend indicator instance
        rsi: RSI indicator instance
        order: Current pending order
        bar_num: Number of bars processed
        buy_count: Number of buy orders executed
        sell_count: Number of sell orders executed

    Args:
        stake: Number of shares/contracts per trade (default: 10)
        atr_period: ATR period for SuperTrend calculation (default: 14)
        atr_mult: ATR multiplier for SuperTrend calculation (default: 2)
        rsi_period: RSI calculation period (default: 14)
        rsi_threshold: RSI threshold for entry signal (default: 40)
    """
    params = dict(
        stake=10,
        atr_period=14,
        atr_mult=2,
        rsi_period=14,
        rsi_threshold=40,
    )

    def __init__(self):
        """Initialize the Supertrend RSI strategy.

        Creates the SuperTrend and RSI indicators with configured parameters
        and initializes tracking variables for orders and statistics.
        """
        self.supertrend = SupertrendIndicator(
            self.data, atr_period=self.p.atr_period, atr_multiplier=self.p.atr_mult
        )
        self.rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by the backtrader engine when an order's status changes.
        Tracks completed buy and sell orders for performance statistics.

        Args:
            order: The order object with updated status
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

        Implements the strategy logic:
        - Enter long when price > SuperTrend AND RSI > threshold
        - Exit when price < SuperTrend

        Only one active order is allowed at a time. The bar counter
        is incremented on each call to track total bars processed.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Price > SuperTrend AND RSI is strong
            if self.data.close[0] > self.supertrend.supertrend[0] and self.rsi[0] > self.p.rsi_threshold:
                self.order = self.buy(size=self.p.stake)
        else:
            # Price < SuperTrend
            if self.data.close[0] < self.supertrend.supertrend[0]:
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
    """Create a SupertrendRsiStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of SupertrendRsiStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return SupertrendRsiStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("Supertrend RSI Strategy")
    print("Params:", get_strategy_params())
