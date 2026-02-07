"""MACD ATR Strategy.

This module implements a strategy based on MACD crossover and SMA direction filtering,
using ATR dynamic stop loss.

Strategy Overview:
    Entry condition: MACD line crosses above signal line AND SMA direction is
        downward (counter-trend entry).
    Exit condition: Price falls below ATR dynamic stop loss price.

Reference:
    backtrader-master2/samples/macd-settings/macd-settings.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
import yaml
from pathlib import Path


def load_config():
    """Load strategy configuration from config.yaml.

    Returns:
        dict: Configuration dictionary containing strategy parameters.
    """
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class MACDATRStrategy(bt.Strategy):
    """MACD ATR Strategy.

    Entry condition: MACD line crosses above signal line AND SMA direction is
        downward (counter-trend entry).
    Exit condition: Price falls below ATR dynamic stop loss price.

    Attributes:
        macd: MACD indicator instance.
        mcross: CrossOver indicator for MACD and signal line.
        atr: ATR indicator instance.
        sma: SMA indicator instance.
        smadir: SMA direction indicator.
        order: Current pending order.
        pstop: Current stop loss price.
        bar_num: Number of bars processed.
        buy_count: Number of buy orders executed.
        sell_count: Number of sell orders executed.
        win_count: Number of profitable trades.
        loss_count: Number of losing trades.
        sum_profit: Total profit/loss from all closed trades.
    """
    params = (
        ('macd1', 12),
        ('macd2', 26),
        ('macdsig', 9),
        ('atrperiod', 14),
        ('atrdist', 3.0),
        ('smaperiod', 30),
        ('dirperiod', 10),
    )

    def __init__(self):
        """Initialize the MACD ATR strategy.

        Sets up the technical indicators used for trading signals and initializes
        the tracking variables for orders, trades, and statistics.
        """
        self.macd = bt.indicators.MACD(
            self.data,
            period_me1=self.p.macd1,
            period_me2=self.p.macd2,
            period_signal=self.p.macdsig
        )
        self.mcross = bt.indicators.CrossOver(self.macd.macd, self.macd.signal)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atrperiod)
        self.sma = bt.indicators.SMA(self.data, period=self.p.smaperiod)
        self.smadir = self.sma - self.sma(-self.p.dirperiod)

        self.order = None
        self.pstop = 0

        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

        Updates the buy/sell order counters when orders are completed and
        clears the pending order reference when the order is no longer alive.

        Args:
            order: The order object with status information.
        """
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_count += 1
            else:
                self.sell_count += 1
        if not order.alive():
            self.order = None

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Updates profit/loss statistics and win/loss counters when a trade is closed.

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

        This method is called for each bar in the data feed and implements the
        core strategy logic:

        Entry conditions:
        - MACD line crosses above signal line (bullish signal)
        - SMA direction is negative (counter-trend entry)

        Exit conditions:
        - Close price falls below the ATR-based trailing stop loss

        The stop loss is dynamically adjusted based on ATR to track price movement.
        """
        self.bar_num += 1

        if self.order:
            return

        if not self.position:
            if self.mcross[0] > 0.0 and self.smadir < 0.0:
                self.order = self.buy()
                pdist = self.atr[0] * self.p.atrdist
                self.pstop = self.data.close[0] - pdist
        else:
            pclose = self.data.close[0]
            pstop = self.pstop

            if pclose < pstop:
                self.order = self.close()
            else:
                pdist = self.atr[0] * self.p.atrdist
                self.pstop = max(pstop, pclose - pdist)

    def stop(self):
        """Print final strategy statistics when backtesting completes.

        Calculates and displays the win rate and total profit/loss along with
        trading statistics including number of bars processed, buy/sell counts,
        and win/loss counts.
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )
