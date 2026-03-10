#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SuperTrend Strategy.

This module implements and tests the SuperTrend strategy, a trend-following
trading approach that uses the Average True Range (ATR) indicator to identify
trend direction and generate buy/sell signals.

The SuperTrend indicator consists of two lines:
1. SuperTrend line: A dynamic support/resistance level
2. Direction line: Indicates uptrend (1) or downtrend (-1)

Reference: https://github.com/Backtesting/strategies
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class SuperTrendIndicator(bt.Indicator):
    """SuperTrend Indicator.

    A trend-following indicator that uses Average True Range (ATR) to
    identify the direction of the trend and potential entry/exit points.
    The indicator consists of two lines:
    - supertrend: The dynamic support/resistance level
    - direction: Trend direction (1 for uptrend, -1 for downtrend)

    Attributes:
        lines: Tuple containing 'supertrend' and 'direction' line names.
        params: Dictionary with 'period' (ATR period) and 'multiplier'
            (ATR multiplier for band width) parameters.

    Example:
        >>> indicator = SuperTrendIndicator(data, period=10, multiplier=3.0)
        >>> print(indicator.supertrend[0])  # Current SuperTrend value
        >>> print(indicator.direction[0])   # Current trend direction
    """
    lines = ('supertrend', 'direction')
    params = dict(
        period=10,
        multiplier=3.0,
    )

    def __init__(self):
        """Initialize the SuperTrend indicator.

        Sets up the ATR indicator and calculates the middle price (HL2)
        which is the average of high and low prices. These values are
        used in the next() method to calculate the SuperTrend bands.
        """
        self.atr = bt.indicators.ATR(self.data, period=self.p.period)
        self.hl2 = (self.data.high + self.data.low) / 2.0

    def next(self):
        """Calculate the SuperTrend indicator values for the current bar.

        This method implements the SuperTrend algorithm:
        1. Calculate upper and lower bands using ATR
        2. Determine trend direction based on previous values
        3. Update SuperTrend line based on price action and band values

        The algorithm:
        - In uptrend: SuperTrend is max(lower_band, previous_SuperTrend)
        - In downtrend: SuperTrend is min(upper_band, previous_SuperTrend)
        - Trend flips when price crosses the SuperTrend line

        Note:
            During the initialization period (before period+1 bars), the
            indicator uses HL2 as the SuperTrend value and direction=1.
        """
        if len(self) < self.p.period + 1:
            self.lines.supertrend[0] = self.hl2[0]
            self.lines.direction[0] = 1
            return

        atr = self.atr[0]
        hl2 = self.hl2[0]

        upper_band = hl2 + self.p.multiplier * atr
        lower_band = hl2 - self.p.multiplier * atr

        prev_supertrend = self.lines.supertrend[-1]
        prev_direction = self.lines.direction[-1]

        # Uptrend
        if prev_direction == 1:
            if self.data.close[0] < prev_supertrend:
                self.lines.supertrend[0] = upper_band
                self.lines.direction[0] = -1
            else:
                self.lines.supertrend[0] = max(lower_band, prev_supertrend)
                self.lines.direction[0] = 1
        # Downtrend
        else:
            if self.data.close[0] > prev_supertrend:
                self.lines.supertrend[0] = lower_band
                self.lines.direction[0] = 1
            else:
                self.lines.supertrend[0] = min(upper_band, prev_supertrend)
                self.lines.direction[0] = -1


class SuperTrendStrategy(bt.Strategy):
    """SuperTrend Strategy.

    A trend-following strategy that generates buy and sell signals based
    on the SuperTrend indicator. The strategy goes long when the trend
    turns positive and exits when the trend turns negative.

    Attributes:
        params: Dictionary containing:
            - stake: Number of shares to trade per order (default: 10)
            - period: ATR period for SuperTrend calculation (default: 10)
            - multiplier: ATR multiplier for SuperTrend bands (default: 3.0)
        dataclose: Reference to the close price of the data feed.
        supertrend: SuperTrendIndicator instance.
        order: Current pending order (None if no pending order).
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for total buy orders executed.
        sell_count: Counter for total sell orders executed.

    Trading Rules:
        - Buy when trend turns up (direction changes from -1 to 1)
        - Sell when trend turns down (direction changes to -1)

    Example:
        >>> cerebro = bt.Cerebro()
        >>> cerebro.addstrategy(SuperTrendStrategy, stake=10, period=10, multiplier=3.0)
        >>> results = cerebro.run()
    """
    params = dict(
        stake=10,
        period=10,
        multiplier=3.0,
    )

    def __init__(self):
        """Initialize the SuperTrend strategy.

        Sets up the data reference, creates the SuperTrend indicator,
        and initializes tracking variables for orders and statistics.
        """
        self.dataclose = self.datas[0].close
        self.supertrend = SuperTrendIndicator(
            self.datas[0],
            period=self.p.period,
            multiplier=self.p.multiplier
        )
        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Called by the backtrader engine when an order's status changes.
        Updates buy/sell counters when orders are completed and clears
        the pending order reference.

        Args:
            order: The Order object with updated status.
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

        This method is called by the backtrader engine for each new bar.
        It implements the following trading logic:
        1. Increment bar counter
        2. Skip if there's a pending order
        3. Generate buy orders when trend turns from down to up
        4. Generate sell orders when in position and trend turns down

        Note:
            Only one position is allowed at a time. The strategy will
            enter long when the SuperTrend direction changes from -1 to 1,
            and exit when the direction changes to -1.
        """
        self.bar_num += 1
        if self.order:
            return

        # Buy when trend turns up
        if not self.position:
            if self.supertrend.direction[0] == 1 and self.supertrend.direction[-1] == -1:
                self.order = self.buy(size=self.p.stake)
        else:
            # Sell when trend turns down
            if self.supertrend.direction[0] == -1:
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

    return SuperTrendStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
