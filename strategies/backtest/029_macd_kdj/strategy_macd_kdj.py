"""MACD+KDJ combined strategy.

This module implements the MACD+KDJ combined strategy using
MACD (Moving Average Convergence Divergence) for trend following
and KDJ (Stochastic) for entry/exit timing signals.

Strategy Overview:
    * MACD golden cross (MACD line crosses above signal line) -> Buy signal
    * KDJ death cross (K line crosses below D line) -> Sell signal
    * MACD golden cross closes existing short positions
    * KDJ death cross closes existing long positions

Reference:
    backtrader-example/strategies/macdkdj.py
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


class KDJ(bt.Indicator):
    """KDJ (Stochastic) Technical Indicator.

    The KDJ indicator is a momentum oscillator that compares a specific closing
    price of a security to a range of its prices over a certain period of time.
    It consists of three lines: K, D, and J, where K and D are similar to the
    Stochastic oscillator, and J is a derivative line.
    """
    lines = ('K', 'D', 'J')

    params = (
        ('period', 9),
        ('period_dfast', 3),
        ('period_dslow', 3),
    )

    def __init__(self):
        """Initialize the KDJ indicator with a StochasticFull base."""
        self.kd = bt.indicators.StochasticFull(
            self.data,
            period=self.p.period,
            period_dfast=self.p.period_dfast,
            period_dslow=self.p.period_dslow,
        )

    def next(self):
        """Calculate KDJ values for the current bar."""
        self.l.K[0] = self.kd.percD[0]
        self.l.D[0] = self.kd.percDSlow[0]
        self.l.J[0] = self.l.K[0] * 3 - self.l.D[0] * 2


class MACDKDJStrategy(bt.Strategy):
    """Combined MACD and KDJ trading strategy.

    This strategy uses MACD (Moving Average Convergence Divergence) for trend
    following and KDJ (Stochastic) for entry/exit timing signals.

    Strategy Logic:
        * MACD golden cross (MACD line crosses above signal line) -> Buy signal
        * KDJ death cross (K line crosses below D line) -> Sell signal
        * MACD golden cross closes existing short positions
        * KDJ death cross closes existing long positions

    Entry Rules:
        * When flat (no position):
            - Enter long on MACD golden cross
            - Enter short on KDJ death cross

    Exit Rules:
        * When long: Exit on KDJ death cross
        * When short: Exit on MACD golden cross

    Attributes:
        bar_num (int): Counter for number of bars processed.
        buy_count (int): Number of buy orders executed.
        sell_count (int): Number of sell orders executed.
        sum_profit (float): Total profit/loss from all closed trades.
        win_count (int): Number of profitable trades.
        loss_count (int): Number of unprofitable trades.
        trade_count (int): Total number of completed trades.
        data0 (Data feed): Reference to the primary data feed.
        macd (MACD): MACD indicator instance.
        kdj (KDJ): KDJ indicator instance.
        marketposition (int): Current market position (-1=short, 0=flat, 1=long).
    """

    params = (
        ('macd_fast_period', 12),
        ('macd_slow_period', 26),
        ('macd_signal_period', 9),
        ('kdj_fast_period', 9),
        ('kdj_slow_period', 3),
    )

    def log(self, txt, dt=None, force=False):
        """Logging utility for strategy output.

        Args:
            txt (str): Text message to log.
            dt (datetime, optional): Datetime object for the log entry.
            force (bool): If True, force output; otherwise suppress logging.
        """
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the MACD+KDJ strategy.

        Sets up statistical tracking variables, initializes MACD and KDJ
        indicators, and establishes the data feed reference.
        """
        # Record statistics
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0
        self.trade_count = 0

        # Get data reference
        self.data0 = self.datas[0]

        # MACD indicator
        self.macd = bt.indicators.MACD(
            self.data0,
            period_me1=self.p.macd_fast_period,
            period_me2=self.p.macd_slow_period,
            period_signal=self.p.macd_signal_period
        )
        # KDJ indicator
        self.kdj = KDJ(
            self.data0,
            period=self.p.kdj_fast_period,
            period_dfast=self.p.kdj_slow_period,
            period_dslow=self.p.kdj_slow_period
        )

        # Trading status
        self.marketposition = 0

    def notify_trade(self, trade):
        """Callback when a trade is completed.

        Updates trade statistics including win/loss count and total profit/loss
        when a trade is closed.

        Args:
            trade (Trade): Trade object containing information about the
                completed trade, including PnL and status.
        """
        if not trade.isclosed:
            return
        self.trade_count += 1
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl

    def next(self):
        """Execute trading logic for each bar.

        Implements the core strategy logic by checking for MACD golden cross
        and KDJ death cross conditions, then executing trades based on the
        current market position.
        """
        self.bar_num += 1
        data = self.data0

        # MACD golden cross condition
        macd_golden_cross = (self.macd.macd[0] > self.macd.signal[0] and
                            self.macd.macd[-1] < self.macd.signal[-1])
        # KDJ death cross condition
        kdj_death_cross = (self.kdj.K[0] < self.kdj.D[0] and
                          self.kdj.K[-1] > self.kdj.D[-1])

        if self.marketposition == 0:
            # MACD golden cross buy signal
            if macd_golden_cross:
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.buy(size=size)
                    self.marketposition = 1
                    self.buy_count += 1
            # KDJ death cross sell signal
            elif kdj_death_cross:
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.sell(size=size)
                    self.marketposition = -1
                    self.sell_count += 1
        elif self.marketposition == -1:
            # Short position: MACD golden cross to close
            if macd_golden_cross:
                self.close()
                self.marketposition = 0
                self.buy_count += 1
        elif self.marketposition == 1:
            # Long position: KDJ death cross to close
            if kdj_death_cross:
                self.close()
                self.marketposition = 0
                self.sell_count += 1

    def stop(self):
        """Output statistics when strategy execution stops.

        Calculates and logs final performance metrics including total bars
        processed, trade counts, win rate, and total profit/loss.
        """
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
