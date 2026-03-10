#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MACD + RSI + Bollinger Bands Multi-Indicator Strategy.

This module implements a multi-confirmation strategy combining MACD, RSI,
and Bollinger Bands to generate trading signals based on mean reversion.

Reference: backtrader_NUPL_strategy/hope/Hope_bbands.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class MacdRsiBbStrategy(bt.Strategy):
    """MACD + RSI + BB Multi-Indicator Strategy.

    Entry conditions:
    - Long: Price breaks above lower Bollinger Band and RSI < 35

    Exit conditions:
    - Price breaks above upper Bollinger Band and RSI > 65
    """
    params = dict(
        stake=10,
        bb_period=20,
        bb_dev=2.0,
        rsi_period=14,
        rsi_oversold=35,
        rsi_overbought=65,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables.

        Creates the following indicators:
        - Bollinger Bands: For identifying price extremes and volatility
        - RSI: For identifying overbought/oversold conditions
        - MACD: For trend confirmation (calculated but not used in current logic)

        Also initializes tracking variables for order management and trade
        statistics.
        """
        self.bbands = bt.indicators.BollingerBands(
            self.data, period=self.p.bb_period, devfactor=self.p.bb_dev
        )
        self.rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)
        self.macd = bt.indicators.MACD(self.data)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates and track trade statistics.

        Called by the backtrader engine when an order's status changes.
        Tracks the number of buy and sell orders that complete successfully.

        Args:
            order: The order object with updated status information.
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

        This method is called by the backtrader engine for each new bar
        of data. It implements the following logic:

        Long entry (when not in position):
        - Previous close was below lower Bollinger Band
        - Current close crosses back above lower Bollinger Band
        - RSI is oversold (below threshold)

        Exit (when in position):
        - Current close is above upper Bollinger Band
        - RSI is overbought (above threshold)
        """
        self.bar_num += 1

        if self.order:
            return

        if len(self) < 2:
            return

        if not self.position:
            # Price recovers from below lower band and RSI is oversold
            if (self.data.close[-1] < self.bbands.bot[-1] and
                self.data.close[0] > self.bbands.bot[0] and
                self.rsi[0] < self.p.rsi_oversold):
                self.order = self.buy(size=self.p.stake)
        else:
            # Price touches upper band and RSI is overbought
            if self.data.close[0] > self.bbands.top[0] and self.rsi[0] > self.p.rsi_overbought:
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
    """Create a MacdRsiBbStrategy instance with parameters from config or kwargs.

    Args:
        **kwargs: Strategy parameters that override config values.

    Returns:
        An instance of MacdRsiBbStrategy class.
    """
    config_params = get_strategy_params()
    config_params.update(kwargs)

    return MacdRsiBbStrategy(**config_params)


if __name__ == "__main__":
    # Example usage
    print("MACD + RSI + Bollinger Bands Strategy")
    print("Params:", get_strategy_params())
