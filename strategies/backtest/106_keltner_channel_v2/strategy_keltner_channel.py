#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Keltner Channel Trading Strategy.

This strategy implements a trend-following system based on Keltner Channel
breakouts. It takes long positions when price breaks above the upper band,
indicating strong bullish momentum and the start of a potential uptrend.
Positions are closed when price falls back below the middle line (EMA),
suggesting the trend has weakened or reversed.

Keltner Channel Overview:
    - Middle Line: Exponential Moving Average (EMA) of price
    - Upper Band: EMA + (ATR × multiplier)
    - Lower Band: EMA - (ATR × multiplier)
    - Bands expand and contract based on volatility (ATR)

Unlike Bollinger Bands which use standard deviation, Keltner Channels use ATR,
making them more responsive to price changes and gap moves.

Trading Logic:
    Entry (Long): Price breaks above the upper Keltner Channel band
    Exit: Price falls below the middle line (EMA)

The strategy aims to capture breakout moves by entering when price shows
sufficient strength to break through the upper Keltner Channel band.

Parameters:
    stake: Number of shares/units per trade (default: 10)
    period: Period for the EMA middle line (default: 20)
    atr_mult: Multiplier for ATR band width (default: 2.0)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class KeltnerChannelIndicator(bt.Indicator):
    """Keltner Channel volatility-based indicator.

    The Keltner Channel is a technical analysis indicator that consists of
    three lines designed to capture price volatility and trend direction.
    Unlike Bollinger Bands which use standard deviation, Keltner Channels
    use the Average True Range (ATR) to determine band width.

    Construction:
        - Middle Line (mid): Exponential Moving Average (EMA) of close prices
        - Upper Band (top): EMA + (ATR × multiplier)
        - Lower Band (bot): EMA - (ATR × multiplier)

    Lines:
        mid: Middle line (Exponential Moving Average)
        top: Upper band (mid + atr_mult * ATR)
        bot: Lower band (mid - atr_mult * ATR)

    Parameters:
        period (int): Period for the EMA middle line calculation (default: 20)
        atr_mult (float): Multiplier for ATR band width (default: 2.0)
        atr_period (int): Period for ATR calculation (default: 14)
    """

    lines = ('mid', 'top', 'bot')
    params = dict(period=20, atr_mult=2.0, atr_period=14)

    def __init__(self):
        """Initialize Keltner Channel indicator calculations.

        Creates the three lines of the Keltner Channel:
        1. Middle line as EMA of closing prices
        2. ATR to measure volatility
        3. Upper and lower bands by adding/subtracting ATR multiple from EMA
        """
        # Calculate middle line as EMA of closing prices
        self.l.mid = bt.indicators.EMA(self.data.close, period=self.p.period)

        # Calculate Average True Range to measure volatility
        atr = bt.indicators.ATR(self.data, period=self.p.atr_period)

        # Calculate upper and lower bands
        self.l.top = self.l.mid + self.p.atr_mult * atr
        self.l.bot = self.l.mid - self.p.atr_mult * atr


class KeltnerChannelStrategy(bt.Strategy):
    """Keltner Channel breakout trading strategy.

    This strategy implements a trend-following system based on Keltner Channel
    breakouts. It takes long positions when price breaks above the upper band,
    indicating strong bullish momentum and the start of a potential uptrend.
    Positions are closed when price falls back below the middle line (EMA).

    Trading Logic:
        Entry (Long): Price closes above the upper Keltner Channel band
        Exit: Price closes below the middle line (EMA)

    Parameters:
        stake (int): Number of shares/units per trade (default: 10)
        period (int): Period for the EMA middle line (default: 20)
        atr_mult (float): Multiplier for ATR band width (default: 2.0)

    Note:
        This strategy performs best in markets with clear trending behavior
        and can experience whipsaws in ranging or choppy markets.
    """

    params = dict(
        stake=10,
        period=20,
        atr_mult=2.0,
    )

    def __init__(self):
        """Initialize the strategy and set up indicators.

        Creates the Keltner Channel indicator with specified parameters
        and initializes all tracking variables for monitoring strategy
        performance and order status.
        """
        # Initialize Keltner Channel indicator
        self.kc = KeltnerChannelIndicator(
            self.data, period=self.p.period, atr_mult=self.p.atr_mult
        )

        # Initialize tracking variables
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        This method is called by the backtrader engine whenever an order's
        status changes. It updates the buy/sell counters when orders are
        completed and clears the order reference to allow new orders.

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
        """Execute trading logic for each bar.

        This method is called for every bar of data after all indicators
        have been calculated. It implements the core Keltner Channel strategy:
        1. Check for pending orders and wait if one exists
        2. Generate buy signal when price breaks above upper band
        3. Generate exit signal when price falls below middle band

        The strategy only takes long positions, aiming to capture bullish
        breakouts and trends. The middle band (EMA) serves as a trailing
        stop-loss level once in a position.
        """
        self.bar_num += 1

        # Wait for pending order to complete before placing new orders
        if self.order:
            return

        if not self.position:
            # No current position - look for breakout entry signal
            # Price breaks above upper band indicates strong bullish momentum
            if self.data.close[0] > self.kc.top[0]:
                # Enter long position with specified stake size
                self.order = self.buy(size=self.p.stake)
        else:
            # Currently in position - look for exit signal
            # Price falls below middle band suggests trend weakening
            if self.data.close[0] < self.kc.mid[0]:
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


__all__ = ['KeltnerChannelStrategy', 'KeltnerChannelIndicator', 'load_config', 'get_strategy_params']
