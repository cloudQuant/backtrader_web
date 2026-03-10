#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""DEMA Crossover Strategy.

This strategy implements a trend-following approach using two DEMA indicators
with different periods. It generates buy signals when the fast DEMA crosses
above the slow DEMA (golden cross) and sell signals when the fast DEMA crosses
below the slow DEMA (death cross).

Entry conditions:
    - Long: Fast DEMA crosses above Slow DEMA (golden cross)

Exit conditions:
    - Close Position: Fast DEMA crosses below Slow DEMA (death cross)

The Double Exponential Moving Average (DEMA) was developed by Patrick Mulloy
and attempts to reduce the lag inherent in traditional moving averages by
using a more complex calculation that applies smoothing twice.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class DemaCrossoverStrategy(bt.Strategy):
    """DEMA Crossover Double Exponential Moving Average Strategy.

    This strategy implements a trend-following approach using two DEMA indicators
    with different periods. It generates buy signals when the fast DEMA crosses
    above the slow DEMA (golden cross) and sell signals when the fast DEMA crosses
    below the slow DEMA (death cross).

    Entry conditions:
        - Long: Fast DEMA crosses above Slow DEMA (crossover > 0)

    Exit conditions:
        - Close Position: Fast DEMA crosses below Slow DEMA (crossover < 0)
    """

    params = dict(
        stake=10,
        fast_period=5,
        slow_period=21,
    )

    def __init__(self):
        """Initialize the DEMA Crossover Strategy.

        Sets up the DEMA indicators, crossover signal, and tracking variables.
        The fast DEMA reacts quickly to price changes while the slow DEMA
        provides a smoother trend line.
        """
        self.dema_fast = bt.indicators.DEMA(self.data, period=self.p.fast_period)
        self.dema_slow = bt.indicators.DEMA(self.data, period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.dema_fast, self.dema_slow)

        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by the backtrader engine when an order changes status. This method
        tracks completed orders by incrementing buy/sell counters and resets the
        pending order reference when the order is complete.

        Args:
            order (bt.Order): The order object with updated status.
                Status can be Submitted, Accepted, Completed, Canceled, Expired, or Margin.

        Note:
            Submitted and Accepted orders are ignored as they are still pending.
            Only Completed orders trigger buy/sell counter updates.
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

        This method is called by the backtrader engine for each bar of data.
        It implements the core strategy logic:

        1. Increments the bar counter
        2. Skips trading if an order is already pending
        3. If no position exists, enters long when golden cross occurs
        4. If position exists, exits when death cross occurs

        The strategy only takes long positions and uses close orders to exit.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            # DEMA golden cross - fast DEMA crosses above slow DEMA
            if self.crossover[0] > 0:
                self.order = self.buy(size=self.p.stake)
        else:
            # DEMA death cross - fast DEMA crosses below slow DEMA
            if self.crossover[0] < 0:
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


__all__ = ['DemaCrossoverStrategy', 'load_config', 'get_strategy_params']
