#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pinkfish Challenge Strategy

Reference: backtrader-master2/samples/pinkfish-challenge/pinkfish-challenge.py
Buy when price makes a new N-day high, sell after holding for a fixed number of days
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


class PinkfishStrategy(bt.Strategy):
    """Pinkfish Challenge strategy - buy on N-day high, sell after fixed days.

    This strategy implements a simple trend-following approach:
    1. Buy when price makes a new N-day high
    2. Hold for a fixed number of days
    3. Sell regardless of price

    This is a momentum-based strategy that buys when price shows strength
    (making new highs) and exits after a predetermined time period.
    """

    params = (
        ('highperiod', 20),
        ('sellafter', 2),
    )

    def __init__(self):
        """Initialize the Pinkfish Challenge strategy.

        Sets up the indicator for tracking highest highs and initializes
        performance tracking variables for monitoring trade statistics.
        """
        # Track the highest high over the specified period
        # This indicator updates each bar to show the maximum high price
        # over the last highperiod bars
        self.highest = bt.ind.Highest(self.data.high, period=self.p.highperiod)

        # Track which bar we entered the market
        # Used to calculate how many bars we've held a position
        self.inmarket = 0

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
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

    def notify_trade(self, trade):
        """Handle trade completion updates.

        Args:
            trade: The trade object with profit/loss information.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Strategy logic:
        1. If not in position: buy when current high equals N-day highest high
        2. If in position: sell after holding for specified number of bars
        """
        self.bar_num += 1

        if not self.position:
            # Enter when price makes new N-day high
            if self.data.high[0] >= self.highest[0]:
                self.buy()
                self.inmarket = len(self)
        else:
            # Exit after holding for specified number of bars
            if (len(self) - self.inmarket) >= self.p.sellafter:
                self.sell()

    def stop(self):
        """Print strategy performance summary after backtest completion."""
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_pinkfish_strategy(config: Dict[str, Any] = None):
    """Run the Pinkfish Challenge Strategy backtest.

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

    # Add strategy with parameters from config
    cerebro.addstrategy(PinkfishStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_pinkfish_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
