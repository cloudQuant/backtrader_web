#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cheat On Open Strategy

Reference: backtrader-master2/samples/cheat-on-open/cheat-on-open.py
Dual moving average crossover with cheat-on-open execution (orders fill at open)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from pathlib import Path
from typing import Dict, Any, List

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


class CheatOnOpenStrategy(bt.Strategy):
    """Dual moving average crossover strategy with cheat-on-open execution.

    This strategy implements a classic dual moving average crossover system and
    demonstrates the use of the cheat-on-open feature to execute orders at the
    opening price of the next bar instead of the closing price. This more
    realistically simulates end-of-day analysis and next-day trading decisions.

    Strategy Logic:
        The strategy uses two Simple Moving Averages (SMA) with different periods:
        - Short SMA (fast): Responds quickly to price changes
        - Long SMA (slow): Smooths out noise, shows overall trend

        Crossover signals:
        - Bullish crossover (short crosses above long): Buy signal
        - Bearish crossover (short crosses below long): Exit signal

    Cheat On Open Behavior:
        With cheat_on_open=True in Cerebro:
        - Strategy's next() method is called BEFORE the bar opens
        - Can access previous bar's indicators for decision making
        - Orders placed in next() execute at the CURRENT bar's open price
        - Simulates overnight decisions and market-on-open orders

    Parameters:
        periods (list): List of two integers specifying SMA periods.
            First element is fast SMA period (default: 10).
            Second element is slow SMA period (default: 30).
    """

    params = dict(
        periods=[10, 30],
    )

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables.

        Creates the dual moving average system with a crossover signal detector.
        Also initializes all tracking variables for monitoring strategy performance.
        """
        # Create Simple Moving Averages for each period in params
        # Fast SMA (shorter period) reacts quickly to price changes
        # Slow SMA (longer period) shows overall trend direction
        mas = [bt.ind.SMA(period=x) for x in self.p.periods]

        # Create crossover signal detector
        # Returns: > 0 when fast SMA crosses above slow SMA (bullish)
        #          < 0 when fast SMA crosses below slow SMA (bearish)
        self.signal = bt.ind.CrossOver(*mas)

        # Initialize order tracking
        self.order = None

        # Initialize performance tracking variables
        self.bar_num = 0      # Total bars processed
        self.buy_count = 0    # Total buy orders executed
        self.sell_count = 0   # Total sell orders executed
        self.win_count = 0    # Number of winning trades
        self.loss_count = 0   # Number of losing trades
        self.sum_profit = 0.0 # Cumulative profit/loss

    def notify_order(self, order):
        """Handle order status updates and track executed orders.

        This method is called by the backtrader engine whenever an order's
        status changes. It updates buy/sell counters when orders complete.

        Args:
            order (bt.Order): The order object with updated status information.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
            self.order = None

    def notify_trade(self, trade):
        """Handle trade completion updates and calculate profit/loss.

        This method is called when a trade is closed (position fully exited).
        It tracks wins, losses, and cumulative profit to evaluate strategy
        performance.

        Args:
            trade (bt.Trade): The trade object with profit/loss information.
        """
        if trade.isclosed:
            # Add trade profit/loss to cumulative total
            self.sum_profit += trade.pnlcomm

            # Track win/loss statistics
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        With cheat_on_open=True, this method is called BEFORE the bar opens,
        allowing decisions based on previous bar's data to execute at the
        current bar's open price.

        Implements dual moving average crossover strategy:
        1. Check for pending orders and wait if one exists
        2. Exit long position when fast SMA crosses below slow SMA
        3. Enter long position when fast SMA crosses above slow SMA

        The strategy only takes long positions, aiming to capture uptrends
        identified by the bullish crossover of the moving averages.
        """
        self.bar_num += 1

        # Skip if order already pending - wait for it to complete
        if self.order is not None:
            return

        # Exit logic: Close position if bearish crossover (short < long)
        if self.position:
            if self.signal < 0:
                self.order = self.close()

        # Entry logic: Open position if bullish crossover (short > long)
        elif self.signal > 0:
            self.order = self.buy()

    def stop(self):
        """Print strategy performance summary after backtest completion.

        This method is called once at the end of the backtest. It calculates
        and displays win rate and final statistics to evaluate strategy
        performance.
        """
        # Calculate win rate (percentage of profitable trades)
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0

        # Display final performance summary
        print(f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
              f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
              f"wins={self.win_count}, losses={self.loss_count}, "
              f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}")


def run_cheat_on_open_strategy(config: Dict[str, Any] = None):
    """Run the Cheat On Open Strategy backtest.

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

    cerebro = bt.Cerebro(
        stdstats=True,
        cheat_on_open=backtest_config.get('cheat_on_open', True)
    )
    cerebro.broker.setcash(backtest_config.get('initial_cash', 100000.0))
    cerebro.broker.setcommission(backtest_config.get('commission', 0.001))

    # Add strategy with parameters from config
    cerebro.addstrategy(CheatOnOpenStrategy, **params)

    return cerebro


if __name__ == "__main__":
    # Load config and run strategy
    config = load_config()
    cerebro = run_cheat_on_open_strategy(config)
    results = cerebro.run()
    print(f"Final Value: {cerebro.broker.getvalue():.2f}")
