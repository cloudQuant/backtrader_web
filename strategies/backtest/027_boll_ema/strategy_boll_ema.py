"""Bollinger Bands + EMA Strategy.

This module implements the BollEMA strategy which combines Bollinger Bands and
Exponential Moving Average (EMA) to generate trading signals.

Strategy Overview:
    The BollEMA strategy generates buy and sell signals based on:
    - Price breaking above/below Bollinger Bands
    - EMA position relative to the middle band
    - Historical price position (last 3 bars)
    - Bollinger Band width as a volatility filter

Reference:
    backtrader-example/strategies/bollema.py
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


class BollEMAStrategy(bt.Strategy):
    """Bollinger Bands + EMA combination trading strategy.

    This strategy implements a trend-following approach using Bollinger Bands
    for entry signals and EMA for trend confirmation. It trades both long and
    short positions with volatility-based filtering.

    Entry Conditions:
        Long (Buy):
            - Current close breaks above upper Bollinger Band
            - Previous close also above upper Band (consecutive break)
            - EMA is above middle band (uptrend confirmation)
            - Last 3 closes all above middle band (trend persistence)
            - Band width > boll_diff parameter (volatility filter)

        Short (Sell):
            - Current close breaks below lower Bollinger Band
            - Previous close also below lower Band (consecutive break)
            - EMA is below middle band (downtrend confirmation)
            - Last 3 closes all below middle band (trend persistence)
            - Band width > boll_diff parameter (volatility filter)

    Exit Conditions:
        Long Position:
            - Stop loss: Price drops by price_diff from entry
            - Trend change: EMA crosses below middle band

        Short Position:
            - Stop loss: Price rises by price_diff from entry
            - Trend change: EMA crosses above middle band

    Attributes:
        bar_num (int): Counter for number of bars processed by the strategy.
        buy_count (int): Total number of buy orders executed.
        sell_count (int): Total number of sell orders executed.
        sum_profit (float): Cumulative profit/loss from all completed trades.
        win_count (int): Number of profitable trades closed.
        loss_count (int): Number of unprofitable trades closed.
        trade_count (int): Total number of completed trades.
        marketposition (int): Current position state. 0=flat, 1=long, -1=short.
        last_price (float): Execution price of the most recent order.
        data0: Reference to the primary data feed.
        boll: Bollinger Bands indicator instance.
        ema: Exponential Moving Average indicator instance.
    """

    params = (
        ("period_boll", 136),
        ("period_ema", 99),
        ("boll_diff", 0.5),    # Minimum Bollinger Band width for entry (volatility filter)
        ("price_diff", 0.3),   # Stop loss threshold from entry price
    )

    def log(self, txt, dt=None, force=False):
        """Log output function.

        Args:
            txt: Text message to log.
            dt: datetime object for the log entry. If None, uses current bar's datetime.
            force: If True, forces output regardless of other conditions.
        """
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the BollEMA strategy.

        Sets up indicators, data references, and tracking variables for
        trade statistics and position management.

        Indicators created:
            - Bollinger Bands: period_boll (default 136) with standard deviation
            - EMA: period_ema (default 99) on close price
        """
        # Initialize statistical counters - bypass backtrader's line system
        object.__setattr__(self, 'bar_num', 0)
        object.__setattr__(self, 'buy_count', 0)
        object.__setattr__(self, 'sell_count', 0)
        object.__setattr__(self, 'sum_profit', 0.0)
        object.__setattr__(self, 'win_count', 0)
        object.__setattr__(self, 'loss_count', 0)
        object.__setattr__(self, 'trade_count', 0)

        # Get data reference
        object.__setattr__(self, 'data0', self.datas[0])

        # Create Bollinger Bands indicator with specified period
        object.__setattr__(self, 'boll', bt.indicators.BollingerBands(self.data0, period=self.p.period_boll))
        # Create EMA indicator for trend confirmation
        object.__setattr__(self, 'ema', bt.indicators.ExponentialMovingAverage(self.data0.close, period=self.p.period_ema))

        # Trading state variables
        object.__setattr__(self, 'marketposition', 0)
        object.__setattr__(self, 'last_price', 0)

    def notify_trade(self, trade):
        """Handle trade completion events.

        Called by backtrader when a trade is closed. Updates win/loss statistics
        and cumulative profit tracking.

        Args:
            trade (backtrader.Trade): The trade object that has been completed.
                                     Contains PnL information and trade status.

        Note:
            Only processes closed trades (trade.isclosed == True).
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
        """Handle order status updates.

        Called by backtrader when order status changes. Tracks execution prices
        for stop-loss calculations.

        Args:
            order (backtrader.Order): The order object with updated status.
                                     Contains execution information when filled.

        Note:
            Only records price from Completed orders. Other statuses (Submitted,
            Accepted, Canceled, etc.) are ignored.
        """
        if order.status == order.Completed:
            self.last_price = order.executed.price

    def gt_last_mid(self):
        """Check if last 3 bars' close prices are above middle band.

        Verifies that the price has maintained position above the middle
        Bollinger Band for the previous 3 bars, indicating sustained uptrend.

        Returns:
            bool: True if all of the last 3 closes were above the middle band,
                  False otherwise.

        Note:
            Index notation: [-1]=previous bar, [-2]=2 bars ago, [-3]=3 bars ago.
        """
        data = self.data0
        return (data.close[-1] > self.boll.mid[-1] and
                data.close[-2] > self.boll.mid[-2] and
                data.close[-3] > self.boll.mid[-3])

    def lt_last_mid(self):
        """Check if last 3 bars' close prices are below middle band.

        Verifies that the price has maintained position below the middle
        Bollinger Band for the previous 3 bars, indicating sustained downtrend.

        Returns:
            bool: True if all of the last 3 closes were below the middle band,
                  False otherwise.

        Note:
            Index notation: [-1]=previous bar, [-2]=2 bars ago, [-3]=3 bars ago.
        """
        data = self.data0
        return (data.close[-1] < self.boll.mid[-1] and
                data.close[-2] < self.boll.mid[-2] and
                data.close[-3] < self.boll.mid[-3])

    def close_gt_up(self):
        """Check if close price is consecutively above upper band.

        Detects consecutive breakouts above the upper Bollinger Band,
        indicating strong upward momentum.

        Returns:
            bool: True if both current [0] and previous [-1] closes are above
                  the upper band, False otherwise.
        """
        data = self.data0
        return data.close[0] > self.boll.top[0] and data.close[-1] > self.boll.top[-1]

    def close_lt_dn(self):
        """Check if close price is consecutively below lower band.

        Detects consecutive breakouts below the lower Bollinger Band,
        indicating strong downward momentum.

        Returns:
            bool: True if both current [0] and previous [-1] closes are below
                  the lower band, False otherwise.
        """
        data = self.data0
        return data.close[0] < self.boll.bot[0] and data.close[-1] < self.boll.bot[-1]

    def next(self):
        """Execute trading logic for each bar.

        Main strategy logic called on each bar. Implements state machine
        with three states: flat (0), long (1), and short (-1).

        Flow:
            1. Increment bar counter
            2. If flat: Check entry conditions for long/short
            3. If long: Check exit conditions (stop loss or EMA crossover)
            4. If short: Check exit conditions (stop loss or EMA crossover)

        Entry logic uses full available cash (ignores position sizing for simplicity).
        """
        self.bar_num += 1

        data = self.data0
        up = self.boll.top[0]      # Upper band
        mid = self.boll.mid[0]      # Middle band (SMA)
        dn = self.boll.bot[0]      # Lower band
        ema = self.ema[0]          # EMA value
        diff = up - dn             # Band width (volatility measure)

        if self.marketposition == 0:
            # FLAT STATE: Check entry conditions
            # Long entry: price breakout + uptrend confirmation + volatility filter
            if self.close_gt_up() and ema > mid and self.gt_last_mid() and diff > self.p.boll_diff:
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.buy(data, size=size)
                    self.marketposition = 1
                    self.buy_count += 1

            # Short entry: price breakdown + downtrend confirmation + volatility filter
            if self.close_lt_dn() and ema < mid and self.lt_last_mid() and diff > self.p.boll_diff:
                size = int(self.broker.getcash() / data.close[0])
                if size > 0:
                    self.sell(data, size=size)
                    self.marketposition = -1
                    self.sell_count += 1

        elif self.marketposition == 1:
            # LONG STATE: Check exit conditions
            # Exit on stop loss (price drop) OR trend change (EMA crosses below mid)
            if self.last_price - data.close[0] > self.p.price_diff or ema <= mid:
                self.close()
                self.marketposition = 0
                self.sell_count += 1

        elif self.marketposition == -1:
            # SHORT STATE: Check exit conditions
            # Exit on stop loss (price rise) OR trend change (EMA crosses above mid)
            if data.close[0] - self.last_price > self.p.price_diff or ema >= mid:
                self.close()
                self.marketposition = 0
                self.buy_count += 1

    def stop(self):
        """Output statistics when strategy ends.

        Called by backtrader after backtesting completes. Calculates and prints
        comprehensive performance statistics including win rate and total profit.
        """
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
