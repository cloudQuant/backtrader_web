#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StopTrail Trailing Stop Strategy

Reference: backtrader-master2/samples/stoptrail/trail.py
Uses trailing stop orders to protect profits
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


class StopTrailStrategy(bt.Strategy):
    """Trailing stop strategy.

    Buys when moving averages cross over (golden cross) and uses trailing
    stop orders to protect profits.

    Note: The current implementation uses a simple crossover for exit.
    To use actual trailing stop orders, uncomment the trail order code in next().
    """
    params = dict(
        p1=5,
        p2=20,
        trailpercent=0.02,
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables."""
        ma1 = bt.ind.SMA(period=self.p.p1)
        ma2 = bt.ind.SMA(period=self.p.p2)
        self.crossover = bt.ind.CrossOver(ma1, ma2)
        self.order = None
        self.stop_order = None

        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

        Args:
            order: The order object with status update.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            if order == self.order:
                self.order = None
            elif order == self.stop_order:
                self.stop_order = None

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Args:
            trade: The trade object that was closed.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Implements a simple moving average crossover strategy:
        - Buy when short MA crosses above long MA (golden cross)
        - Sell when short MA crosses below long MA (death cross)

        To use trailing stop orders, replace the exit logic with:
            self.stop_order = self.sell(trailpercent=self.p.trailpercent)
        """
        self.bar_num += 1

        # Buy signal: short-term MA crosses above long-term MA
        if not self.position:
            if self.crossover > 0:  # Golden cross
                self.order = self.buy()
        # Sell signal: short-term MA crosses below long-term MA
        elif self.crossover < 0:  # Death cross
            self.order = self.close()

    def stop(self):
        """Print strategy performance summary when backtesting ends."""
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_stoptrail_strategy(config: Dict[str, Any] = None):
    """Run the StopTrail Strategy backtest.

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
    cerebro.addstrategy(StopTrailStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_stoptrail_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
