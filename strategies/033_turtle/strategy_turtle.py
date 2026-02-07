"""Turtle trading strategy.

This module implements a classic Turtle trading strategy based on
price breakout and trend following principles.

Strategy Overview:
    - Uses moving average as a trend filter (bull/bear market regime)
    - Buys when price breaks out above N-day high during bull market
    - Uses trailing stop loss to protect profits
    - Exits when the trend reverses (price breaks below long-term MA)

Reference:
    weekend-backtrader/strategy/turtle.py and main.py
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


class TurtleStrategy(bt.Strategy):
    """Turtle trading strategy implementation.

    This strategy is based on the classic Turtle Trading system, a trend-following
    approach that buys breakouts in the direction of the long-term trend.

    Trading Logic:
        1. Enter long when:
           - Price is above long-term MA (bull market regime)
           - Price rate of change exceeds threshold (breakout detection)

        2. Exit position when:
           - Price falls below long-term MA (trend reversal)
           - Trailing stop loss is hit

        3. Risk management:
           - Trailing stop loss protects profits during favorable moves
           - Stop loss is cancelled when position is closed

    Note:
        Configuration loading from config.yaml should be done by passing
        parameters explicitly when adding the strategy, rather than loading
        config in the __init__ method, to avoid conflicts with backtrader's metaclass.
    """
    params = (
        ('maperiod', 15),
        ('breakout_period_days', 20),  # Breakout period, originally 100, adjusted to 20 for data
        ('price_rate_of_change_perc', 0.1),  # Price rate of change threshold
        ('regime_filter_ma_period', 200),  # Trend filter MA period
        ('trailing_stop_loss_perc', 0.1),  # Trailing stop loss percentage
    )

    def __init__(self):
        """Initialize the Turtle trading strategy.

        Sets up the strategy's state variables, indicators, and tracking
        mechanisms for orders and trades.
        """
        self.order = None
        self.stop_order = None
        self.buyprice = None
        self.buycomm = None

        # Moving average indicators
        self.sma = bt.indicators.SimpleMovingAverage(
            self.datas[0],
            period=self.params.maperiod
        )
        self.sma_regime = bt.indicators.SimpleMovingAverage(
            self.datas[0],
            period=self.params.regime_filter_ma_period
        )

        # Statistical variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def _is_bull_regime(self):
        """Determine if currently in a bull market trend."""
        return self.data.close[0] > self.sma_regime[0]

    def notify_order(self, order):
        """Handle order status updates.

        This method is called by Backtrader whenever an order's status changes.
        It tracks buy/sell order execution and records execution prices and
        commissions.

        Args:
            order (bt.Order): The order object with updated status.
        """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_count += 1
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:
                self.sell_count += 1

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            pass

        self.order = None

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        This method is called when a trade is closed. It updates the strategy's
        performance statistics including total profit, win count, and loss count.

        Args:
            trade (bt.Trade): The completed trade object containing profit/loss
                information in the `pnlcomm` attribute (profit/loss including
                commissions).
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute the strategy's trading logic for each bar.

        This method is called for each new bar of data. It implements the
        Turtle trading strategy's entry and exit logic.
        """
        self.bar_num += 1

        if self.order:
            return

        # Calculate price rate of change
        if len(self.data) <= self.params.breakout_period_days:
            return

        past_price = self.data.close[-self.params.breakout_period_days]
        yesterdays_price = self.data.close[-1]

        if yesterdays_price == 0 or past_price == 0:
            return

        rate_of_change = (yesterdays_price - past_price) / yesterdays_price

        if not self.position:
            # Entry conditions: bull market trend + price breakout
            if self._is_bull_regime() and rate_of_change > self.params.price_rate_of_change_perc:
                self.order = self.buy()
                # Set trailing stop loss
                self.stop_order = self.sell(
                    exectype=bt.Order.StopTrail,
                    trailpercent=self.params.trailing_stop_loss_perc
                )
        else:
            # Exit condition: break below trend line
            if not self._is_bull_regime():
                self.order = self.close()
                if self.stop_order and self.stop_order.alive():
                    self.cancel(self.stop_order)

    def stop(self):
        """Output final trading statistics when backtesting completes.

        This method is called once when the backtesting run finishes. It prints
        a summary of the strategy's performance.
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )
