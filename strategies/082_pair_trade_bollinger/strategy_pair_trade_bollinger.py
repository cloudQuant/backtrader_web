#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Pair Trade Bollinger Strategy.

Reference: https://github.com/mean_reversion_strategies
Uses Bollinger Bands and simplified hedge ratio for pair trading.
The original strategy uses Kalman Filter, here simplified to rolling OLS regression.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
import backtrader as bt
import yaml
from pathlib import Path


class PairTradeBollingerStrategy(bt.Strategy):
    """Pair trading Bollinger Bands strategy.

    Uses two correlated assets for pair trading:
    - Calculate the Z-Score of the price spread
    - Go long on spread when Z-Score is below lower band
    - Go short on spread when Z-Score is above upper band
    - Close positions when Z-Score returns to mean
    """
    params = dict(
        lookback=20,
        entry_zscore=1.5,
        exit_zscore=0.2,
        stake=10,
    )

    def __init__(self):
        """Initialize the Pair Trade Bollinger Strategy.

        Sets up the strategy by:
        - Storing references to close prices of both data feeds
        - Initializing tracking variables for orders, statistics, and position state
        - Creating an empty spread history list for hedge ratio calculations

        Attributes:
            data0_close: Reference to close prices of the first asset (data0).
            data1_close: Reference to close prices of the second asset (data1).
            order: Current pending order, or None if no orders are pending.
            spread_history: List tracking historical spread values for Z-score calculation.
            hedge_ratio: Current hedge ratio used to size positions in the second asset.
                Starts at 1.0 and is updated dynamically using rolling regression.
            bar_num: Counter for the number of bars processed.
            buy_count: Counter for total buy orders executed.
            sell_count: Counter for total sell orders executed.
            position_state: Current position state encoded as:
                0 - Flat (no position)
                1 - Long spread (long data0, short data1)
                -1 - Short spread (short data0, long data1)
        """
        self.data0_close = self.datas[0].close
        self.data1_close = self.datas[1].close
        self.order = None

        self.spread_history = []
        self.hedge_ratio = 1.0

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

        # Position state: 0=flat, 1=long spread, -1=short spread
        self.position_state = 0

    def notify_order(self, order):
        """Handle order status notifications.

        This method is called by the backtrader engine whenever an order's
        status changes. It updates the buy/sell counters when orders are
        completed and clears the pending order reference.

        Args:
            order: The order object with status information.

        Order Status Handling:
            - Submitted/Accepted: No action taken, order is still pending.
            - Completed: Increments buy_count or sell_count based on order type.
            - Other statuses: Clears the pending order reference.

        Note:
            This method only tracks completed orders. Rejected, cancelled,
            or expired orders will also result in clearing self.order.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        self.order = None

    def calculate_zscore(self):
        """Calculate the Z-Score of the price spread.

        Returns:
            float: The Z-Score value, or 0 if insufficient data.
        """
        if len(self.spread_history) < self.p.lookback:
            return 0

        recent = self.spread_history[-self.p.lookback:]
        mean = np.mean(recent)
        std = np.std(recent)
        if std == 0:
            return 0
        return (self.spread_history[-1] - mean) / std

    def calculate_hedge_ratio(self):
        """Calculate hedge ratio using rolling regression.

        Returns:
            float: The calculated hedge ratio, or 1.0 if calculation fails.
        """
        if len(self) < self.p.lookback:
            return 1.0

        y = [self.data0_close[-i] for i in range(self.p.lookback)]
        x = [self.data1_close[-i] for i in range(self.p.lookback)]

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(len(x)))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(len(x)))

        if denominator == 0:
            return 1.0
        return numerator / denominator

    def next(self):
        """Execute trading logic for each bar.

        This method is called for every bar of data during the backtest.
        It implements the core pair trading logic:

        1. Updates the hedge ratio using rolling regression
        2. Calculates the current spread between the two assets
        3. Computes the Z-Score of the spread
        4. Enters positions when the Z-Score exceeds entry thresholds
        5. Exits positions when the Z-Score reverts toward the mean

        Trading Logic:
            - When flat (position_state == 0):
                * Go long spread if Z-Score < -entry_zscore (buy data0, sell data1)
                * Go short spread if Z-Score > entry_zscore (sell data0, buy data1)
            - When long spread (position_state == 1):
                * Close both legs if Z-Score > -exit_zscore
            - When short spread (position_state == -1):
                * Close both legs if Z-Score < exit_zscore

        Note:
            - No new orders are placed if there's a pending order
            - The hedge ratio is recalculated each bar using rolling OLS regression
            - Position sizing for data1 is adjusted by the hedge ratio
        """
        self.bar_num += 1

        # Update hedge ratio
        self.hedge_ratio = self.calculate_hedge_ratio()

        # Calculate spread
        spread = self.data0_close[0] - self.hedge_ratio * self.data1_close[0]
        self.spread_history.append(spread)

        if len(self.spread_history) < self.p.lookback:
            return

        zscore = self.calculate_zscore()

        if self.order:
            return

        # Trading logic
        if self.position_state == 0:
            # When flat
            if zscore < -self.p.entry_zscore:
                # Go long spread: buy data0, sell data1
                self.buy(data=self.datas[0], size=self.p.stake)
                self.sell(data=self.datas[1], size=int(self.p.stake * self.hedge_ratio))
                self.position_state = 1
            elif zscore > self.p.entry_zscore:
                # Go short spread: sell data0, buy data1
                self.sell(data=self.datas[0], size=self.p.stake)
                self.buy(data=self.datas[1], size=int(self.p.stake * self.hedge_ratio))
                self.position_state = -1

        elif self.position_state == 1:
            # When long spread, close position when Z-Score returns to mean
            if zscore > -self.p.exit_zscore:
                self.close(data=self.datas[0])
                self.close(data=self.datas[1])
                self.position_state = 0

        elif self.position_state == -1:
            # When short spread, close position when Z-Score returns to mean
            if zscore < self.p.exit_zscore:
                self.close(data=self.datas[0])
                self.close(data=self.datas[1])
                self.position_state = 0


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

    return PairTradeBollingerStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
