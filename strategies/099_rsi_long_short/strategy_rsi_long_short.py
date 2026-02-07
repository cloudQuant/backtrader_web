#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RSI Long/Short Dual RSI Strategy.

This strategy implements a dual-RSI approach combining long and short period
RSI indicators to identify entry and exit points. The long period RSI provides
confirmation of overall trend strength, while the short period RSI identifies
short-term momentum for precise entry/exit timing.

Entry conditions:
    - Long: Long period RSI > 50 AND Short period RSI > 65

Exit conditions:
    - Short period RSI < 45

The dual-RSI approach helps filter false signals by requiring confirmation
from both timeframes. The long RSI confirms the overall trend direction,
while the short RSI provides the timing for entry and exit.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class RsiLongShortStrategy(bt.Strategy):
    """RSI Long/Short Dual RSI Strategy.

    This strategy implements a dual-RSI approach combining long and short period
    RSI indicators to identify entry and exit points. The long period RSI provides
    confirmation of overall trend strength, while the short period RSI identifies
    short-term momentum for precise entry/exit timing.

    Entry conditions:
        - Long: Long period RSI > 50 AND Short period RSI > 65

    Exit conditions:
        - Short period RSI < 45

    Attributes:
        params (dict): Strategy parameters with the following keys:
            stake (int): Number of shares/contracts per trade. Default is 10.
            period_long (int): Period for long-term RSI calculation. Default is 14.
            period_short (int): Period for short-term RSI calculation. Default is 5.
            buy_rsi_long (float): RSI threshold for long period to trigger buy.
                Default is 50.
            buy_rsi_short (float): RSI threshold for short period to trigger buy.
                Default is 65.
            sell_rsi_short (float): RSI threshold for short period to trigger sell.
                Default is 45.
        rsi_long (bt.indicators.RSI): Long period RSI indicator instance.
        rsi_short (bt.indicators.RSI): Short period RSI indicator instance.
        order (bt.Order): Current pending order, or None if no pending orders.
        bar_num (int): Counter for the number of bars processed during backtest.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.
    """

    params = dict(
        stake=10,
        period_long=14,
        period_short=5,
        buy_rsi_long=50,
        buy_rsi_short=65,
        sell_rsi_short=45,
    )

    def __init__(self):
        """Initialize the RSI Long/Short strategy.

        Creates the long and short period RSI indicators and initializes
        tracking variables for orders and statistics.
        """
        self.rsi_long = bt.indicators.RSI(self.data, period=self.p.period_long)
        self.rsi_short = bt.indicators.RSI(self.data, period=self.p.period_short)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by Backtrader when an order changes status. Updates buy/sell
        counters when orders complete and clears the pending order reference.

        Args:
            order (bt.Order): The order object with updated status.
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

        This method is called by Backtrader for each new bar of data.
        Implements the dual-RSI strategy logic:
        1. Skip if there's a pending order
        2. If not in position: Enter long when both RSI conditions are met
        3. If in position: Exit when short RSI falls below sell threshold
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # Entry: Long period RSI strong AND Short period RSI strong
            if self.rsi_long[0] > self.p.buy_rsi_long and self.rsi_short[0] > self.p.buy_rsi_short:
                self.order = self.buy(size=self.p.stake)
        else:
            # Exit: Short period RSI falls back
            if self.rsi_short[0] < self.p.sell_rsi_short:
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


__all__ = ['RsiLongShortStrategy', 'load_config', 'get_strategy_params']
