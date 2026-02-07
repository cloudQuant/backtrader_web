#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Alligator Strategy.

Reference: https://github.com/Backtesting/strategies
Bill Williams Alligator indicator strategy
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class AlligatorIndicator(bt.Indicator):
    """Alligator Indicator - Bill Williams.

    The Alligator indicator consists of three smoothed moving averages:
    - Jaw (blue line): 13-period SMMA, shifted forward 8 bars
    - Teeth (red line): 8-period SMMA, shifted forward 5 bars
    - Lips (green line): 5-period SMMA, shifted forward 3 bars

    The indicator is used to identify trending periods and potential
    entry/exit points. When the three lines are intertwined, the market
    is ranging. When they separate, a trend is emerging.

    Attributes:
        jaw: The jaw line (13-period SMMA)
        teeth: The teeth line (8-period SMMA)
        lips: The lips line (5-period SMMA)

    Args:
        jaw_period: Period for the jaw line calculation (default: 13).
        teeth_period: Period for the teeth line calculation (default: 8).
        lips_period: Period for the lips line calculation (default: 5).
    """
    lines = ('jaw', 'teeth', 'lips')
    params = dict(
        jaw_period=13,
        teeth_period=8,
        lips_period=5,
    )

    def __init__(self):
        """Initialize the Alligator indicator.

        Creates three Smoothed Moving Average (SMMA) lines for the jaw,
        teeth, and lips. The SMMA is equivalent to an EMA with alpha = 1/period.
        """
        self.lines.jaw = bt.indicators.SmoothedMovingAverage(
            self.data.close, period=self.p.jaw_period
        )
        self.lines.teeth = bt.indicators.SmoothedMovingAverage(
            self.data.close, period=self.p.teeth_period
        )
        self.lines.lips = bt.indicators.SmoothedMovingAverage(
            self.data.close, period=self.p.lips_period
        )


class AlligatorStrategy(bt.Strategy):
    """Alligator trading strategy.

    This strategy implements a simple Alligator-based trading approach:
    - Buy when price breaks above the jaw line
    - Sell when price breaks below the jaw line

    The jaw line acts as a trend filter - when price is above it, the
    trend is considered bullish, and when below, bearish.

    Attributes:
        dataclose: Reference to close prices
        alligator: Alligator indicator instance
        order: Current pending order
        bar_num: Number of bars processed
        buy_count: Number of buy orders executed
        sell_count: Number of sell orders executed

    Args:
        stake: Number of shares to trade per order (default: 10).
        jaw_period: Period for the Alligator jaw line (default: 13).
        teeth_period: Period for the Alligator teeth line (default: 8).
        lips_period: Period for the Alligator lips line (default: 5).
    """
    params = dict(
        stake=10,
        jaw_period=13,
        teeth_period=8,
        lips_period=5,
    )

    def __init__(self):
        """Initialize the Alligator strategy.

        Sets up the data reference, creates the Alligator indicator,
        and initializes tracking variables for orders and bar counts.
        """
        self.dataclose = self.datas[0].close
        self.alligator = AlligatorIndicator(
            self.datas[0],
            jaw_period=self.p.jaw_period,
            teeth_period=self.p.teeth_period,
            lips_period=self.p.lips_period
        )
        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status notifications.

        Updates buy/sell counters when orders are completed and clears
        the pending order reference.

        Args:
            order: The order object with status information.
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

        This method is called on each bar of data. It implements the
        Alligator-based trading logic:
        - Buy signal: Price closes above the jaw line (no position)
        - Sell signal: Price closes below the jaw line (holding position)

        Only one order is allowed at a time. If an order is pending,
        no new orders are placed.
        """
        self.bar_num += 1
        if self.order:
            return

        # Buy when price is above the jaw line
        if not self.position:
            if self.dataclose[0] > self.alligator.jaw[0]:
                self.order = self.buy(size=self.p.stake)
        else:
            # Sell when price breaks below the jaw line
            if self.dataclose[0] < self.alligator.jaw[0]:
                self.order = self.sell(size=self.p.stake)


def load_config(config_path=None):
    """Load strategy configuration from YAML file.

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


def get_strategy_from_config(config_path=None):
    """Get strategy class with parameters loaded from config.yaml.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Tuple: (Strategy class, params dict)
    """
    config = load_config(config_path)
    params = config.get('params', {})

    return AlligatorStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
