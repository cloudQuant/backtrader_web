#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Percent Rank Strategy.

This module tests a mean reversion strategy based on the percentile ranking
of MACD histogram values. It buys when the indicator is at extreme lows and
sells when at extreme highs.

Reference: https://github.com/backtrader/backhacker
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class PercentRankStrategy(bt.Strategy):
    """Percent Rank mean reversion strategy.

    This strategy uses percentile ranking of MACD histogram values to identify
    extreme conditions for mean reversion trades. It waits for confirmation
    before entering positions.

    Trading Rules:
        - Buy when percentile drops to limit1 (e.g., 10%), then rises above limit2 (e.g., 30%)
        - Sell when percentile rises to (100-limit1) (e.g., 90%), then falls below (100-limit2) (e.g., 70%)

    Attributes:
        dataclose: Close price data series.
        ma1: Short-term EMA for MACD calculation.
        ma2: Long-term EMA for MACD calculation.
        diff: MACD histogram (EMA1 - EMA2).
        prank: Percentile rank of MACD histogram (0-100 scale).
        buy_limit1: Lower percentile threshold for buy signal.
        sell_limit1: Upper percentile threshold for sell signal.
        buy_limit2: Confirmation threshold for buy entry.
        sell_limit2: Confirmation threshold for sell entry.
        pending_buy: Flag indicating buy signal triggered, waiting for confirmation.
        pending_sell: Flag indicating sell signal triggered, waiting for confirmation.
        order: Current pending order.
        last_operation: Last executed operation ("BUY" or "SELL").
        bar_num: Number of bars processed.
        buy_count: Total buy orders executed.
        sell_count: Total sell orders executed.

    Args:
        stake: Number of shares per trade (default: 10).
        percent_period: Period for percentile rank calculation (default: 200).
        limit1: Initial trigger threshold (default: 10).
        limit2: Confirmation threshold (default: 30).
        period1: Short EMA period for MACD (default: 12).
        period2: Long EMA period for MACD (default: 26).
    """
    params = dict(
        stake=10,
        percent_period=200,
        limit1=10,
        limit2=30,
        period1=12,
        period2=26,
    )

    def __init__(self):
        """Initialize strategy indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.ma1 = bt.ind.EMA(self.datas[0], period=self.p.period1)
        self.ma2 = bt.ind.EMA(self.datas[0], period=self.p.period2)
        self.diff = self.ma1 - self.ma2
        self.prank = bt.ind.PercentRank(self.diff, period=self.p.percent_period) * 100

        self.buy_limit1 = self.p.limit1
        self.sell_limit1 = 100 - self.buy_limit1
        self.buy_limit2 = self.p.limit2
        self.sell_limit2 = 100 - self.buy_limit2

        self.pending_buy = False
        self.pending_sell = False

        self.order = None
        self.last_operation = "SELL"

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status.
        """
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
                self.last_operation = "BUY"
            else:
                self.sell_count += 1
                self.last_operation = "SELL"
        self.order = None

    def next(self):
        """Execute trading logic for each bar.

        Implements a two-stage entry system: initial trigger at extreme levels,
        followed by confirmation when percentile moves back toward mean.
        """
        self.bar_num += 1
        if self.order:
            return

        # Buy logic: Wait for extreme low, then confirmation on rise
        if self.last_operation != "BUY":
            if self.prank[0] <= self.buy_limit1:
                # Trigger: percentile at extreme low
                self.pending_buy = True
            elif self.pending_buy and self.prank[0] >= self.buy_limit2:
                # Confirmation: percentile has risen back up
                self.pending_buy = False
                self.order = self.buy(size=self.p.stake)

        # Sell logic: Wait for extreme high, then confirmation on decline
        if self.last_operation != "SELL":
            if self.prank[0] >= self.sell_limit1:
                # Trigger: percentile at extreme high
                self.pending_sell = True
            elif self.pending_sell and self.prank[0] <= self.sell_limit2:
                # Confirmation: percentile has fallen back down
                self.pending_sell = False
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

    return PercentRankStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
