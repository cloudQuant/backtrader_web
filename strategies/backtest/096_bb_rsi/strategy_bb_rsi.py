#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bollinger Bands + RSI Strategy.

This strategy implements a mean-reversion approach combining two
complementary technical indicators:
- Bollinger Bands: Identify price extremes relative to recent volatility
- RSI: Identify momentum extremes (overbought/oversold conditions)

Strategy Logic:
    Long-only mean reversion that buys on oversold conditions and exits
    on overbought conditions or price returning to the mean.

Entry Conditions (Long):
    - RSI < rsi_oversold (default 30): Indicates oversold momentum
    - Close < lower Bollinger Band: Indicates price below statistical range
    - Both conditions must be true simultaneously (AND logic)

Exit Conditions:
    - RSI > rsi_overbought (default 70): Indicates overbought momentum
    - Close > upper Bollinger Band: Indicates price above statistical range
    - Either condition triggers exit (OR logic)

Position Management:
    - Fixed position size: stake parameter (default 10 shares/contracts)
    - Only one position at a time (long-only)
    - No pyramiding or partial exits
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class BbRsiStrategy(bt.Strategy):
    """Bollinger Bands + RSI mean-reversion strategy."""

    params = dict(
        stake=10,              # Fixed position size (shares/contracts per trade)
        bb_period=20,          # Bollinger Bands lookback period
        bb_devfactor=2.0,      # Standard deviation multiplier (2.0 = 2 sigma)
        rsi_period=14,         # RSI calculation period
        rsi_oversold=30,       # RSI threshold for buy signal (oversold)
        rsi_overbought=70,     # RSI threshold for sell signal (overbought)
    )

    def __init__(self):
        """Initialize the BbRsi strategy.

        Creates indicators and initializes tracking variables for orders
        and trade statistics.
        """
        # Create RSI indicator for momentum analysis
        self.rsi = bt.indicators.RSI(self.data, period=self.p.rsi_period)
        # Create Bollinger Bands for volatility-based price range
        self.bbands = bt.indicators.BollingerBands(
            self.data, period=self.p.bb_period, devfactor=self.p.bb_devfactor
        )

        # Initialize tracking variables
        self.order = None      # Track pending order
        self.bar_num = 0       # Count bars processed
        self.buy_count = 0     # Count buy orders executed
        self.sell_count = 0    # Count sell orders executed

    def notify_order(self, order):
        """Handle order status updates.

        Called by backtrader when order status changes. Updates buy/sell counters
        when orders are completed and clears the pending order reference to allow
        new orders to be placed.

        Args:
            order (bt.Order): The order object with updated status. Contains
                            information about execution price, status, etc.
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

        Implements the core Bollinger Bands + RSI mean-reversion strategy.

        Flow:
            1. Increment bar counter
            2. Check if pending order exists - if so, wait for execution
            3. If no position: Check entry conditions (oversold)
            4. If has position: Check exit conditions (overbought)

        Entry Logic:
            - Buy when RSI < rsi_oversold AND close < lower Bollinger Band
            - Fixed position size: stake parameter

        Exit Logic:
            - Sell when RSI > rsi_overbought OR close > upper Bollinger Band
            - Closes entire position (no partial exits)
        """
        self.bar_num += 1

        # Only proceed if no pending order
        if self.order:
            return

        if not self.position:
            # ENTRY LOGIC: No position, look for buy opportunity
            # Buy when both oversold conditions are met
            if self.rsi[0] < self.p.rsi_oversold and self.data.close[0] < self.bbands.bot[0]:
                self.order = self.buy(size=self.p.stake)
        else:
            # EXIT LOGIC: Have position, look for exit signal
            # Exit when either overbought condition is met (OR logic)
            if self.rsi[0] > self.p.rsi_overbought or self.data.close[0] > self.bbands.top[0]:
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


# For backward compatibility - also expose as BbRsiStrategy
__all__ = ['BbRsiStrategy', 'load_config', 'get_strategy_params']
