"""Abbration Bollinger Band breakout strategy.

This module implements a trend-following strategy using Bollinger Bands.
The strategy goes long when price breaks above the upper band and goes short
when price breaks below the lower band. Positions are closed when price
returns to the middle band.

Strategy Overview:
    - Long Entry: Price breaks above upper Bollinger Band (crosses from below)
    - Short Entry: Price breaks below lower Bollinger Band (crosses from above)
    - Exit: Price crosses back through the middle Bollinger Band

Reference:
    backtrader-example/strategies/abbration.py
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


class AbbrationStrategy(bt.Strategy):
    """Bollinger Band breakout trading strategy.

    This strategy implements a mean-reversion trading approach using Bollinger Bands.
    It enters positions when price breaks out of the bands and exits when price
    returns to the mean (middle band).

    Trading Logic:
        - Long Entry: Price breaks above upper Bollinger Band (crosses from below)
        - Short Entry: Price breaks below lower Bollinger Band (crosses from above)
        - Exit: Price crosses back through the middle Bollinger Band

    Attributes:
        bar_num (int): Total number of bars processed during backtest.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.
        sum_profit (float): Cumulative profit/loss from all completed trades.
        win_count (int): Number of profitable trades.
        loss_count (int): Number of unprofitable trades.
        data0 (object): Reference to the primary data feed (self.datas[0]).
        boll_indicator (bt.indicators.BollingerBands): Bollinger Bands indicator.
        marketposition (int): Current market position (0=flat, 1=long, -1=short).

    Parameters:
        boll_period (int): Period for Bollinger Band calculation. Default is 200.
        boll_mult (float): Standard deviation multiplier for bands. Default is 2.0.
    """

    params = (
        ("boll_period", 200),
        ("boll_mult", 2),
    )

    def log(self, txt, dt=None, force=False):
        """Log messages with optional timestamp.

        Args:
            txt: Text message to log.
            dt: Optional datetime for the log entry. If None, uses current bar's datetime.
            force: If True, always log. If False, suppress logging (default).
        """
        if not force:
            return
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the strategy with indicators and tracking variables.

        Sets up:
            - Statistical tracking variables (bar count, trade counts, P&L)
            - Data feed references
            - Bollinger Band indicator
            - Market position state
        """
        # Record statistical data
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # Get data reference - standard access through datas list
        self.data0 = self.datas[0]

        # Calculate Bollinger Band indicator
        self.boll_indicator = bt.indicators.BollingerBands(
            self.data0, period=self.p.boll_period, devfactor=self.p.boll_mult
        )

        # Save trading state
        self.marketposition = 0

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Called by backtrader when a trade is closed. Updates win/loss statistics
        and cumulative profit tracking.

        Args:
            trade: Trade object containing information about the completed trade.
        """
        if not trade.isclosed:
            return
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl
        self.log(f"Trade completed: Gross profit={trade.pnl:.2f}, Net profit={trade.pnlcomm:.2f}, Cumulative={self.sum_profit:.2f}")

    def notify_order(self, order):
        """Handle order status change notifications.

        Called by backtrader when order status changes. Logs executed orders
        and order status changes (canceled, margin, rejected).

        Args:
            order: Order object containing status and execution information.
        """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"Buy executed: Price={order.executed.price:.2f}, Size={order.executed.size}")
            else:
                self.log(f"Sell executed: Price={order.executed.price:.2f}, Size={order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """Execute trading logic for each bar.

        Implements the core strategy logic:
            1. Increment bar counter
            2. Check for long entry: price breaks above upper band from below
            3. Check for short entry: price breaks below lower band from above
            4. Check for long exit: price crosses below middle band from above
            5. Check for short exit: price crosses above middle band from below

        Entry conditions require a breakout (previous bar outside, current bar outside)
        to avoid entering on false breakouts.
        """
        self.bar_num += 1

        data = self.data0
        top = self.boll_indicator.top
        bot = self.boll_indicator.bot
        mid = self.boll_indicator.mid

        # Open long: Price breaks above upper band from below
        if self.marketposition == 0 and data.close[0] > top[0] and data.close[-1] < top[-1]:
            size = int(self.broker.getcash() / data.close[0])
            if size > 0:
                self.buy(data, size=size)
                self.marketposition = 1
                self.buy_count += 1

        # Open short: Price breaks below lower band from above
        if self.marketposition == 0 and data.close[0] < bot[0] and data.close[-1] > bot[-1]:
            size = int(self.broker.getcash() / data.close[0])
            if size > 0:
                self.sell(data, size=size)
                self.marketposition = -1
                self.sell_count += 1

        # Close long: Price crosses below middle band from above
        if self.marketposition == 1 and data.close[0] < mid[0] and data.close[-1] > mid[-1]:
            self.close()
            self.marketposition = 0
            self.sell_count += 1

        # Close short: Price crosses above middle band from below
        if self.marketposition == -1 and data.close[0] > mid[0] and data.close[-1] < mid[-1]:
            self.close()
            self.marketposition = 0
            self.buy_count += 1

    def stop(self):
        """Output final statistics when backtest completes.

        Called by backtrader after all bars have been processed.
        Calculates and logs:
            - Total bars processed
            - Buy/sell order counts
            - Win/loss trade counts
            - Win rate percentage
            - Total profit/loss
        """
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
