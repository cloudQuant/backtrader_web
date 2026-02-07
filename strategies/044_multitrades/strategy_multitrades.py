#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MultiTrades Strategy

Reference: backtrader-master2/samples/multitrades/multitrades.py
Manages multiple concurrent trades with different trade IDs
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import itertools
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


class MultiTradesStrategy(bt.Strategy):
    """Strategy using multiple trade IDs to manage concurrent trades.

    This strategy demonstrates the use of trade IDs to manage multiple
    concurrent trades independently. Each trade is tracked separately
    using its unique trade ID.

    Trade ID cycling allows managing multiple concurrent positions:
    - With mtrade=True: cycles through trade IDs [0, 1, 2]
    - With mtrade=False: always uses trade ID [0]

    This is useful when you want to:
    * Track multiple entry points independently
    * Scale in/out of positions at different levels
    * Run multiple parallel strategies within one strategy instance
    """

    params = dict(
        period=15,
        stake=1,
        onlylong=False,
        mtrade=True,
    )

    def __init__(self):
        """Initialize the MultiTrades strategy with indicators and tracking variables.

        Sets up the technical indicators (SMA and crossover), configures trade ID
        cycling for multi-trade mode, and initializes all tracking variables for
        performance monitoring.
        """
        self.order = None
        # Create SMA and crossover signal
        sma = bt.ind.SMA(self.data, period=self.p.period)
        self.signal = bt.ind.CrossOver(self.data.close, sma)

        # Cycle through trade IDs (0, 1, 2) for multi-trade mode
        # This allows up to 3 concurrent trades to be tracked independently
        if self.p.mtrade:
            self.tradeid = itertools.cycle([0, 1, 2])
        else:
            self.tradeid = itertools.cycle([0])

        self.curtradeid = 0

        # Initialize tracking variables for performance analysis
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

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

    def notify_trade(self, trade):
        """Handle trade completion updates.

        Args:
            trade: The trade object with profit/loss information.

        Note:
            This method is called when a trade is closed (position fully exited).
            Tracks win/loss statistics and cumulative profit/loss.
        """
        if trade.isclosed:
            # Add profit/loss including commissions to total
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Strategy logic:
        1. On bullish crossover: close existing trade (if any) and open new long
        2. On bearish crossover: close existing trade (if any) and open new short
        3. Each trade gets a unique trade ID for independent tracking

        The strategy uses trade IDs to manage multiple concurrent positions,
        allowing independent tracking and exit of each trade.
        """
        self.bar_num += 1

        # Skip if order already pending to prevent order stacking
        if self.order:
            return

        if self.signal > 0.0:
            # Bullish crossover detected - price crossed above SMA
            # Close any existing position with current trade ID before opening new one
            if self.position:
                self.close(tradeid=self.curtradeid)
            # Get next trade ID from the cycle for the new trade
            self.curtradeid = next(self.tradeid)
            # Open long position with the new trade ID
            self.buy(size=self.p.stake, tradeid=self.curtradeid)

        elif self.signal < 0.0:
            # Bearish crossover detected - price crossed below SMA
            # Close any existing position with current trade ID before opening new one
            if self.position:
                self.close(tradeid=self.curtradeid)
            # Only enter short if not restricted to long-only mode
            if not self.p.onlylong:
                self.curtradeid = next(self.tradeid)
                # Open short position with the new trade ID
                self.sell(size=self.p.stake, tradeid=self.curtradeid)

    def stop(self):
        """Print strategy performance summary after backtest completion.

        Calculates and displays:
        - Final datetime and bar number
        - Total buy and sell order counts
        - Win/loss statistics with win rate percentage
        - Total profit/loss including commissions
        """
        # Calculate win rate as percentage, avoiding division by zero
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_multitrades_strategy(config: Dict[str, Any] = None):
    """Run the MultiTrades Strategy backtest.

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
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Add strategy with parameters from config
    cerebro.addstrategy(MultiTradesStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_multitrades_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
