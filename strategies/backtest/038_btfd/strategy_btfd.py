#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BTFD (Buy The F* Dip) Strategy

Reference: backtrader-master2/samples/btfd/btfd.py
Buy when price drops beyond a threshold, sell after holding for a fixed number of days
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


class BTFDStrategy(bt.Strategy):
    """BTFD (Buy The F* Dip) Strategy.

    Buy when the intraday price drops beyond a threshold, close the position
    after holding for a fixed number of days.
    """
    params = (
        ('fall', -0.01),
        ('hold', 2),
        ('approach', 'highlow'),
        ('target', 1.0),
    )

    def __init__(self):
        """Initialize the BTFD strategy with price drop calculation and tracking variables.

        Sets up the price drop calculation based on the specified approach and
        initializes counters for tracking trades, wins, losses, and profits.

        The approach parameter determines how price drops are calculated:
        - 'closeclose': Close price relative to previous close
        - 'openclose': Close price relative to same day open
        - 'highclose': Close price relative to same day high
        - 'highlow': Low price relative to same day high
        """
        if self.p.approach == 'closeclose':
            self.pctdown = self.data.close / self.data.close(-1) - 1.0
        elif self.p.approach == 'openclose':
            self.pctdown = self.data.close / self.data.open - 1.0
        elif self.p.approach == 'highclose':
            self.pctdown = self.data.close / self.data.high - 1.0
        elif self.p.approach == 'highlow':
            self.pctdown = self.data.low / self.data.high - 1.0

        self.barexit = 0
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates and track completed orders.

        Args:
            order: The order object that has been updated.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1

    def notify_trade(self, trade):
        """Handle trade completion and track win/loss statistics.

        Args:
            trade: The trade object that has been closed.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute the trading logic for each bar.

        Implements the BTFD strategy:
        1. If in a position and the holding period has elapsed, close the position
        2. If not in a position and price drop exceeds the threshold, buy
        """
        self.bar_num += 1
        if self.position:
            if len(self) == self.barexit:
                self.close()
        else:
            if self.pctdown <= self.p.fall:
                self.order_target_percent(target=self.p.target)
                self.barexit = len(self) + self.p.hold

    def stop(self):
        """Print final strategy statistics when backtesting completes.

        Calculates and displays the final performance metrics including
        total trades, win rate, and total profit/loss.
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_btfd_strategy(config: Dict[str, Any] = None):
    """Run the BTFD Strategy backtest.

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

    if backtest_config.get('cheat_on_close', False):
        cerebro.broker.set_coc(True)

    # Add strategy with parameters from config
    cerebro.addstrategy(BTFDStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_btfd_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
