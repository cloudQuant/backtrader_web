"""Bollinger Band Strategy.

This module implements a trend-following Bollinger Band strategy that trades
breakouts from the Bollinger Bands. The strategy goes long when price
breaks above the upper band and goes short when price breaks below the
lower band.

Strategy Logic:
    - Open long when closing price exceeds upper band for 2 consecutive bars
    - Open short when closing price falls below lower band for 2 consecutive bars
    - Close position when price crosses the middle band (moving average)
    - Includes stop-loss protection at price_diff threshold

Reference:
    backtrader-example/strategies/boll.py
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


class BollStrategy(bt.Strategy):
    """Bollinger Band trend-following strategy.

    This strategy implements a breakout trading system using Bollinger Bands.
    It trades in the direction of the breakout when price moves outside the
    bands for two consecutive bars, and exits when price returns to the
    middle band (moving average).

    Strategy Rules:
        1. Entry signals:
           - Long: Close > top band for 2 consecutive bars
           - Short: Close < bottom band for 2 consecutive bars
        2. Exit signals:
           - Long: Close crosses below middle band
           - Short: Close crosses above middle band
        3. Risk management:
           - Stop loss at price_diff from entry price

    Attributes:
        params: Strategy parameters including:
            - period_boll (int): Bollinger Band period (default: 245).
            - price_diff (float): Stop loss price difference (default: 0.5).
        bar_num: Counter for total bars processed.
        buy_count: Counter for buy orders executed.
        sell_count: Counter for sell orders executed.
        sum_profit: Total profit/loss from all closed trades.
        win_count: Number of profitable trades.
        loss_count: Number of unprofitable trades.
        trade_count: Total number of completed trades.
        data0: Reference to the first data feed.
        boll: Bollinger Bands indicator.
        marketposition: Current position state (0=flat, 1=long, -1=short).
        position_price: Entry price of current position.
    """

    params = (
        ("period_boll", 245),
        ("price_diff", 0.5),  # Stop loss price difference
    )

    def log(self, txt, dt=None, force=False):
        """Log strategy information with timestamp.

        Args:
            txt: Text message to log.
            dt: Optional datetime for the log entry. Uses current bar if None.
            force: If False, logging is skipped. Used to control output verbosity.
        """
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the Bollinger Band strategy.

        Sets up tracking counters, data references, and the Bollinger Bands
        indicator. The indicator provides top (upper band), mid (middle band/SMA),
        and bot (lower band) lines for trading signals.
        """
        # Record statistical data
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0
        self.trade_count = 0

        # Get data reference
        self.data0 = self.datas[0]

        # Bollinger Band indicator
        self.boll = bt.indicators.BollingerBands(self.data0, period=self.p.period_boll)

        # Trading status
        self.marketposition = 0  # 0=flat, 1=long, -1=short
        self.position_price = 0

    def notify_trade(self, trade):
        """Handle trade completion and update statistics.

        This callback is invoked when a trade closes. It updates win/loss
        counters and accumulates total profit/loss.

        Args:
            trade: The Trade object that has closed.
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
        """Handle order status changes and track entry price.

        This callback is invoked when an order status changes. It tracks
        the execution price for stop-loss calculations.

        Args:
            order: The Order object whose status has changed.
        """
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            # Track execution price for stop-loss calculations
            self.position_price = order.executed.price

    def close_gt_up(self):
        """Check if closing price is continuously above upper band.

        Verifies that the current and previous bars both closed above
        the upper Bollinger Band, indicating a strong breakout.

        Returns:
            bool: True if close[0] > top and close[-1] > top[-1].
        """
        data = self.data0
        return data.close[0] > self.boll.top[0] and data.close[-1] > self.boll.top[-1]

    def close_lt_dn(self):
        """Check if closing price is continuously below lower band.

        Verifies that the current and previous bars both closed below
        the lower Bollinger Band, indicating a strong breakdown.

        Returns:
            bool: True if close[0] < bot and close[-1] < bot[-1].
        """
        data = self.data0
        return data.close[0] < self.boll.bot[0] and data.close[-1] < self.boll.bot[-1]

    def down_across_mid(self):
        """Check if price is crossing middle band downward.

        Detects when price crosses from above the middle band to below it,
        signaling a potential exit for long positions.

        Returns:
            bool: True if close[-1] > mid[-1] and close[0] < mid[0].
        """
        data = self.data0
        return data.close[-1] > self.boll.mid[-1] and data.close[0] < self.boll.mid[0]

    def up_across_mid(self):
        """Check if price is crossing middle band upward.

        Detects when price crosses from below the middle band to above it,
        signaling a potential exit for short positions.

        Returns:
            bool: True if close[-1] < mid[-1] and close[0] > mid[0].
        """
        data = self.data0
        return data.close[-1] < self.boll.mid[-1] and data.close[0] > self.boll.mid[0]

    def next(self):
        """Execute the core Bollinger Band strategy logic.

        This method implements the complete trading logic:

        1. Entry conditions (when marketposition == 0):
           - Long entry: close_gt_up() (price breaks above upper band)
           - Short entry: close_lt_dn() (price breaks below lower band)

        2. Exit conditions for long positions (marketposition > 0):
           - Stop loss: position_price - close > price_diff
           - Normal exit: down_across_mid() (price crosses below middle band)

        3. Exit conditions for short positions (marketposition < 0):
           - Stop loss: close - position_price > price_diff
           - Normal exit: up_across_mid() (price crosses above middle band)

        Position sizing:
           - Uses all available cash for new positions
           - size = int(cash / close_price)
        """
        self.bar_num += 1
        data = self.data0

        # Open position logic - no current position
        if self.marketposition == 0:
            if self.close_gt_up():
                # Breakout above upper band - open long position
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.buy(data, size=size)
                    self.marketposition = 1
                    self.buy_count += 1
            elif self.close_lt_dn():
                # Breakdown below lower band - open short position
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.sell(data, size=size)
                    self.marketposition = -1
                    self.sell_count += 1

        # Long position management
        elif self.marketposition > 0:
            # Check stop loss - close below entry by price_diff
            if self.position_price - data.close[0] > self.p.price_diff:
                self.close()
                self.marketposition = 0
                self.sell_count += 1
            # Check normal exit - price crosses below middle band
            elif self.down_across_mid():
                self.close()
                self.marketposition = 0
                self.sell_count += 1

        # Short position management
        elif self.marketposition < 0:
            # Check stop loss - close above entry by price_diff
            if data.close[0] - self.position_price > self.p.price_diff:
                self.close()
                self.marketposition = 0
                self.buy_count += 1
            # Check normal exit - price crosses above middle band
            elif self.up_across_mid():
                self.close()
                self.marketposition = 0
                self.buy_count += 1

    def stop(self):
        """Log final statistics when the backtest completes.

        Outputs summary statistics including total bars, order counts,
        win/loss ratio, and total profit/loss.
        """
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
