#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Simple RSI Strategy with EMA trend filter.

Reference: https://github.com/backtrader/backhacker
A strategy combining RSI oversold/overbought signals with EMA trend following.

Strategy Logic:
- Buy when RSI is oversold (< 30) and fast EMA is above slow EMA (uptrend)
- Sell when RSI is overbought (> 70)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


class SimpleRSIStrategy(bt.Strategy):
    """Simple RSI strategy with EMA trend filter.

    This strategy combines RSI mean-reversion signals with EMA trend following:
    - Buy signal: RSI < oversold threshold AND fast EMA > slow EMA
    - Sell signal: RSI > overbought threshold

    Attributes:
        params: Strategy parameters including EMA periods, RSI settings, and position size
        dataclose: Reference to close prices
        ema_fast: Fast exponential moving average
        ema_slow: Slow exponential moving average
        rsi: Relative Strength Index indicator
        order: Current pending order
        last_operation: Last operation type ('BUY' or 'SELL')
        bar_num: Counter for processed bars
        buy_count: Counter for executed buy orders
        sell_count: Counter for executed sell orders
    """
    params = dict(
        stake=10,
        period_ema_fast=10,
        period_ema_slow=100,
        rsi_period=14,
        rsi_oversold=30,
        rsi_overbought=70,
    )

    def __init__(self):
        """Initialize strategy with indicators and state variables."""
        self.dataclose = self.datas[0].close
        self.ema_fast = bt.ind.EMA(period=self.p.period_ema_fast)
        self.ema_slow = bt.ind.EMA(period=self.p.period_ema_slow)
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)

        self.order = None
        self.last_operation = "SELL"

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0

    def notify_order(self, order):
        """Handle order status changes.

        Args:
            order: The order object with updated status
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

        Implements a state machine that only buys after a sell and only
        sells after a buy, preventing multiple consecutive same-side orders.
        """
        self.bar_num += 1
        if self.order:
            return  # Wait for pending order to complete

        # Only buy if last operation was not BUY (i.e., we're not already long)
        if self.last_operation != "BUY":
            if self.rsi[0] < self.p.rsi_oversold and self.ema_fast[0] > self.ema_slow[0]:
                # RSI oversold + uptrend confirmation = buy signal
                self.order = self.buy(size=self.p.stake)

        # Only sell if last operation was not SELL (i.e., we're not already short/cash)
        if self.last_operation != "SELL":
            if self.rsi[0] > self.p.rsi_overbought:
                # RSI overbought = sell signal
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

    return SimpleRSIStrategy, params


if __name__ == "__main__":
    # Example usage with config loading
    cerebro = bt.Cerebro()

    # Load strategy with config parameters
    strategy_class, strategy_params = get_strategy_from_config()
    cerebro.addstrategy(strategy_class, **strategy_params)

    print(f"Strategy: {strategy_class.__name__}")
    print(f"Parameters: {strategy_params}")
