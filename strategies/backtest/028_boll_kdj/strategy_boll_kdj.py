"""BOLLKDJ Bollinger Bands + KDJ strategy.

This module implements a technical analysis strategy that combines Bollinger Bands and KDJ
indicators to generate trading signals.

Strategy Overview:
    The BOLLKDJ strategy generates buy/sell signals based on:
    - Bollinger Bands crossover signals (price crossing upper/lower bands)
    - KDJ indicator golden cross (bullish) and death cross (bearish) signals
    - Combined signals for entry and exit decisions
    - Stop-loss mechanism based on price difference threshold

Reference:
    backtrader-example/strategies/bollkdj.py
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
    """KDJ (Stochastic) technical indicator.

    The KDJ indicator is a momentum oscillator that consists of three lines:
    - K line: The fast stochastic line
    - D line: The smoothed K line (signal line)
    - J line: A derivative of K and D (J = 3*K - 2*D) that is more sensitive

    This implementation uses the StochasticFull indicator as the underlying
    calculation and extracts the K, D, and J values.

    Attributes:
        kd (bt.indicators.StochasticFull): The underlying StochasticFull indicator
            that provides the K and D values. J is calculated from K and D.
    """
    lines = ('K', 'D', 'J')

    params = (
        ('period', 9),
        ('period_dfast', 3),
        ('period_dslow', 3),
    )

    def __init__(self):
        """Initialize the KDJ indicator.

        Creates a StochasticFull indicator with the specified parameters.
        The K, D, and J values are calculated in the next() method rather than
        using line binding to avoid index synchronization issues.
        """
        self.kd = bt.indicators.StochasticFull(
            self.data,
            period=self.p.period,
            period_dfast=self.p.period_dfast,
            period_dslow=self.p.period_dslow,
        )

    def next(self):
        """Calculate KDJ values for the current bar.

        Updates the K, D, and J lines based on the StochasticFull indicator values.
        J is calculated as: J = 3*K - 2*D, which makes it more sensitive to
        price movements than K or D alone.
        """
        self.l.K[0] = self.kd.percD[0]
        self.l.D[0] = self.kd.percDSlow[0]
        self.l.J[0] = self.l.K[0] * 3 - self.l.D[0] * 2


class BOLLKDJStrategy(bt.Strategy):
    """Bollinger Bands + KDJ combination trading strategy.

    This strategy combines Bollinger Bands and KDJ indicators to generate
    trading signals based on trend and momentum conditions.

    Strategy Logic:
        Buy Signal:
            - Price crosses below Bollinger lower band (oversold condition)
            - KDJ golden cross at low level (K crosses above D, all lines <= 25)

        Sell Signal:
            - Price crosses above Bollinger upper band (overbought condition)
            - KDJ death cross at high level (K crosses below D, all lines >= 75)

        Exit Conditions:
            - Stop loss: Price moves against position by price_diff amount
            - Reverse signal: Opposite buy/sell signal is generated

    Attributes:
        bar_num (int): Counter for the number of bars processed.
        buy_count (int): Number of buy orders executed.
        sell_count (int): Number of sell orders executed.
        sum_profit (float): Total profit/loss from all completed trades.
        win_count (int): Number of profitable trades.
        loss_count (int): Number of unprofitable trades.
        trade_count (int): Total number of completed trades.
        data0 (bt.DataBase): Reference to the primary data feed.
        boll (bt.indicators.BollingerBands): Bollinger Bands indicator.
        kdj (KDJ): Custom KDJ indicator instance.
        marketposition (int): Current market position: 0=flat, 1=long, -1=short.
        position_price (float): Entry price of the current position.
        boll_signal (int): Bollinger Bands signal: 1=buy, -1=sell, 0=none.
        kdj_signal (int): KDJ signal: 1=buy, -1=sell, 0=none.
    """

    params = (
        ("boll_period", 53),
        ("boll_mult", 2),
        ("kdj_period", 9),
        ("kdj_ma1", 3),
        ("kdj_ma2", 3),
        ("price_diff", 0.5),  # Stop loss price difference
    )

    def log(self, txt, dt=None, force=False):
        """Log a message with timestamp.

        Args:
            txt (str): The message text to log.
            dt (datetime.datetime, optional): The datetime to use for the timestamp.
            force (bool): If True, force logging; otherwise suppress logging.
        """
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the BOLLKDJ strategy.

        Sets up trading statistics, indicators, and signal tracking variables.
        Creates Bollinger Bands and KDJ indicators for signal generation.
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

        # Bollinger Bands indicator
        self.boll = bt.indicators.BollingerBands(
            self.data0, period=self.p.boll_period, devfactor=self.p.boll_mult
        )
        # KDJ indicator
        self.kdj = KDJ(
            self.data0, period=self.p.kdj_period,
            period_dfast=self.p.kdj_ma1, period_dslow=self.p.kdj_ma2
        )

        # Trading state
        self.marketposition = 0
        self.position_price = 0

        # Signals
        self.boll_signal = 0
        self.kdj_signal = 0

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Updates win/loss statistics and cumulative profit.

        Args:
            trade (bt.Trade): The completed trade object containing PnL information.
        """
        if not trade.isclosed:
            return
        self.trade_count += 1
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl

    def notify_order(self, order):
        """Handle order status change notifications.

        Records the execution price for stop-loss calculations.

        Args:
            order (bt.Order): The order object with updated status information.
        """
        if order.status == order.Completed:
            self.position_price = order.executed.price

    def up_across(self):
        """Check if price crosses above the upper Bollinger Band.

        Returns:
            bool: True if the previous close was below the upper band and the
                current close is above the upper band, False otherwise.
        """
        data = self.data0
        return data.close[-1] < self.boll.top[-1] and data.close[0] > self.boll.top[0]

    def dn_across(self):
        """Check if price crosses below the lower Bollinger Band.

        Returns:
            bool: True if the previous close was above the lower band and the
                current close is below the lower band, False otherwise.
        """
        data = self.data0
        return data.close[-1] > self.boll.bot[-1] and data.close[0] < self.boll.bot[0]

    def check_boll_signal(self):
        """Check for Bollinger Band crossover signals.

        Updates the boll_signal attribute based on price crossovers.
        """
        if self.up_across():
            self.boll_signal = -1  # Sell signal
        elif self.dn_across():
            self.boll_signal = 1   # Buy signal

    def check_kdj_signal(self):
        """Check for KDJ golden cross and death cross signals.

        Updates the kdj_signal attribute based on KDJ line crossovers.
        """
        condition1 = self.kdj.J[-1] - self.kdj.D[-1]
        condition2 = self.kdj.J[0] - self.kdj.D[0]
        # Golden cross at low level
        if condition1 < 0 and condition2 > 0 and (self.kdj.K[0] <= 25 and self.kdj.D[0] <= 25 and self.kdj.J[0] <= 25):
            self.kdj_signal = 1
        # Death cross at high level
        elif condition1 > 0 and condition2 < 0 and (self.kdj.K[0] >= 75 and self.kdj.D[0] >= 75 and self.kdj.J[0] >= 75):
            self.kdj_signal = -1

    def next(self):
        """Execute strategy logic for each bar.

        Implements the complete trading logic:
        1. Updates bar counter
        2. Checks for Bollinger Band and KDJ signals
        3. Executes trades based on current position and signals
        """
        self.bar_num += 1

        # Check signals
        self.check_boll_signal()
        self.check_kdj_signal()

        data = self.data0

        # No position
        if self.marketposition == 0:
            # Buy condition
            if self.boll_signal > 0 and self.kdj_signal > 0:
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.buy(data, size=size)
                    self.marketposition = 1
                    self.buy_count += 1
                self.boll_signal = 0
                self.kdj_signal = 0
            # Sell condition
            elif self.boll_signal < 0 and self.kdj_signal < 0:
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.sell(data, size=size)
                    self.marketposition = -1
                    self.sell_count += 1
                self.boll_signal = 0
                self.kdj_signal = 0
        # Short position
        elif self.marketposition == -1:
            # Stop loss
            if self.position_price > 0 and (data.close[0] - self.position_price > self.p.price_diff):
                self.close()
                self.marketposition = 0
                self.position_price = 0
                self.boll_signal = 0
                self.kdj_signal = 0
                self.buy_count += 1
            # Close on reverse signal
            elif self.boll_signal > 0 and self.kdj_signal > 0:
                self.close()
                self.marketposition = 0
                self.position_price = 0
                self.boll_signal = 0
                self.kdj_signal = 0
                self.buy_count += 1
        # Long position
        elif self.marketposition == 1:
            # Stop loss
            if self.position_price - data.close[0] > self.p.price_diff:
                self.close()
                self.marketposition = 0
                self.position_price = 0
                self.boll_signal = 0
                self.kdj_signal = 0
                self.sell_count += 1
            # Close on reverse signal
            elif self.boll_signal < 0 and self.kdj_signal < 0:
                self.close()
                self.marketposition = 0
                self.position_price = 0
                self.boll_signal = 0
                self.kdj_signal = 0
                self.sell_count += 1

    def stop(self):
        """Output performance statistics when the strategy completes.

        Logs comprehensive statistics including trade counts, win rate,
        and total profit.
        """
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
