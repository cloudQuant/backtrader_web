#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Slippage Simulation Strategy

Reference: backtrader-master2/samples/slippage/slippage.py
Demonstrates the impact of slippage on trading performance
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from pathlib import Path
from typing import Dict, Any

import yaml
import backtrader as bt


def load_config(config_path: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml file. If None, uses default path.

    Returns:
        Configuration dictionary.
    """
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class SlippageStrategy(bt.Strategy):
    """Simple Moving Average (SMA) crossover strategy for slippage testing.

    This strategy uses two SMA indicators with different periods to generate
    crossover signals. It is specifically designed to test the impact of
    slippage on trading performance.

    Trading Logic:
        - Go long when fast SMA crosses above slow SMA
        - Close position when fast SMA crosses below slow SMA

    The purpose of this strategy is to demonstrate how slippage affects
    backtesting results. Comparing results with and without slippage
    helps understand the real-world cost of trading.
    """
    params = (
        ('p1', 10),
        ('p2', 30),
    )

    def __init__(self):
        """Initialize the strategy with SMA indicators and tracking variables."""
        sma1 = bt.ind.SMA(period=self.p.p1)
        sma2 = bt.ind.SMA(period=self.p.p2)
        self.signal = bt.ind.CrossOver(sma1, sma2)
        self.order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates and track completed orders.

        Args:
            order: The order object with updated status.
        """
        if order.status == bt.Order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def notify_trade(self, trade):
        """Track trade results when a trade is closed.

        Args:
            trade: The completed trade object.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Implements SMA crossover strategy:
        1. Check for pending orders
        2. Enter long when fast SMA crosses above slow SMA
        3. Close position when fast SMA crosses below slow SMA
        """
        self.bar_num += 1

        if self.order:
            return

        if self.signal > 0:
            # Bullish crossover: close existing position and go long
            if self.position:
                self.order = self.close()
            self.order = self.buy()
        elif self.signal < 0:
            # Bearish crossover: close existing position
            if self.position:
                self.order = self.close()

    def stop(self):
        """Print final statistics when the strategy stops.

        Displays win rate and total profit/loss for the backtest period.
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_slippage_strategy(config: Dict[str, Any] = None):
    """Run the Slippage Strategy backtest.

    This function demonstrates how to apply slippage to a backtest.
    The slippage percentage represents the expected difference between
    the expected execution price and the actual execution price.

    Args:
        config: Configuration dictionary. If None, loads from config.yaml.

    Returns:
        Configured Cerebro instance.
    """
    if config is None:
        config = load_config()

    # Extract parameters from config
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 50000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Apply slippage to all orders
    slippage_perc = backtest_config.get('slippage_perc', 0.01)
    cerebro.broker.set_slippage_perc(slippage_perc)

    # Add strategy with parameters from config
    cerebro.addstrategy(SlippageStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_slippage_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
