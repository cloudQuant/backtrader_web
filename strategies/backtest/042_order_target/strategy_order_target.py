#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Order Target Strategy

Reference: backtrader-master2/samples/order_target/order_target.py
Demonstrates order_target_percent for dynamic position sizing
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


class OrderTargetStrategy(bt.Strategy):
    """Order target strategy using dynamic position sizing.

    This strategy adjusts the target position percentage based on the day of month.
    In odd months: target = day/100 (e.g., 15th = 15%)
    In even months: target = (31-day)/100 (e.g., 15th = 16%)

    This demonstrates the use of order_target_percent for automatic position
    management. The strategy will automatically buy or sell to reach the
    target percentage, without needing to calculate the exact number of shares.

    Attributes:
        order: Current pending order.
        bar_num: Number of bars processed.
        buy_count: Total buy orders executed.
        sell_count: Total sell orders executed.
        win_count: Number of profitable trades.
        loss_count: Number of losing trades.
        sum_profit: Total profit/loss from all closed trades.

    Args:
        use_target_percent: Whether to use order_target_percent (default: True).
    """
    params = (
        ('use_target_percent', True),
    )

    def __init__(self):
        """Initialize strategy state variables."""
        self.order = None
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with updated status.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def notify_trade(self, trade):
        """Handle trade completion and track statistics.

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

        Calculates target position based on day of month and submits
        order_target_percent to adjust position.

        The position target varies by date:
        - Odd months: target = day / 100 (1st = 1%, 15th = 15%, 31st = 31%)
        - Even months: target = (31 - day) / 100 (1st = 30%, 15th = 16%, 31st = 0%)

        This creates a pattern of increasing then decreasing positions throughout
        the month, demonstrating how order_target_percent automatically handles
        both buying and selling to reach the desired position size.
        """
        self.bar_num += 1

        if self.order:
            return

        # Calculate target size based on day of month
        dt = self.data.datetime.date()
        size = dt.day
        if (dt.month % 2) == 0:
            # Even months: inverse relationship (later day = smaller position)
            size = 31 - size

        percent = size / 100.0
        self.order = self.order_target_percent(target=percent)

    def stop(self):
        """Print final statistics when backtesting ends."""
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_order_target_strategy(config: Dict[str, Any] = None):
    """Run the Order Target Strategy backtest.

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
    cerebro.broker.setcash(backtest_config.get('initial_cash', 1000000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Add strategy with parameters from config
    cerebro.addstrategy(OrderTargetStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_order_target_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
