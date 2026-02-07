"""BtcSentiment Bitcoin Sentiment Strategy.

This module implements a BTC trading strategy based on Google Trends sentiment data.
The strategy uses Bollinger Bands on sentiment data to generate trading signals.

Strategy Overview:
    - Long: When sentiment exceeds the upper Bollinger Band
    - Short: When sentiment falls below the lower Bollinger Band
    - Close: When sentiment returns to the middle region

Reference:
    Backtrader-Guide-AlgoTrading101/bt_main_btc.py and strategies.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class BtcSentimentStrategy(bt.Strategy):
    """BTC trading strategy based on Google Trends sentiment data.

    This strategy goes long when the sentiment indicator exceeds the upper Bollinger Band,
    goes short when it falls below the lower band, and closes positions when returning to
    the middle region.

    Attributes:
        btc_price: BTC price data from the first data feed.
        google_sentiment: Google Trends sentiment data from the second data feed.
        bbands: Bollinger Bands indicator calculated on sentiment data.
        order: Current pending order.
        bar_num: Counter for the number of bars processed.
        buy_count: Counter for buy orders executed.
        sell_count: Counter for sell orders executed.
        win_count: Counter for profitable trades.
        loss_count: Counter for unprofitable trades.
        sum_profit: Total profit/loss from all closed trades.
    """
    params = (
        ('period', 10),
        ('devfactor', 1),
    )

    def __init__(self):
        """Initialize the BtcSentiment strategy.

        Sets up the data feeds, indicators, and tracking variables for the strategy.
        The strategy uses BTC price data from the first feed and Google Trends sentiment
        data from the second feed. Bollinger Bands are calculated on the sentiment data
        to generate trading signals.
        """
        self.btc_price = self.datas[0].close
        self.google_sentiment = self.datas[1].close
        self.bbands = bt.indicators.BollingerBands(
            self.google_sentiment,
            period=self.params.period,
            devfactor=self.params.devfactor
        )
        self.order = None

        # Statistics variables
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.sum_profit = 0.0

    def notify_order(self, order):
        """Handle order status updates.

        Tracks the number of buy and sell orders as they are executed.
        Resets the pending order reference when the order is completed,
        canceled, margin-triggered, or rejected.

        Args:
            order: The order object with updated status information.
        """
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.buy_count += 1
            elif order.issell():
                self.sell_count += 1

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            pass

        self.order = None

    def notify_trade(self, trade):
        """Handle trade completion notifications.

        Tracks profit/loss for each completed trade and increments the
        win or loss counters accordingly.

        Args:
            trade: The trade object with P&L information.
        """
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute trading logic for each bar.

        Implements the Bollinger Bands-based sentiment strategy:
        - Long: When sentiment exceeds the upper Bollinger Band
        - Short: When sentiment falls below the lower Bollinger Band
        - Close: When sentiment returns to the middle region

        Only one order is allowed at a time to prevent over-trading.
        """
        self.bar_num += 1

        if self.order:
            return

        # Long signal - sentiment indicator exceeds upper Bollinger Band
        if self.google_sentiment > self.bbands.lines.top[0]:
            if not self.position:
                self.order = self.buy()

        # Short signal - sentiment indicator falls below lower Bollinger Band
        elif self.google_sentiment < self.bbands.lines.bot[0]:
            if not self.position:
                self.order = self.sell()

        # Neutral signal - close position
        else:
            if self.position:
                self.order = self.close()

    def stop(self):
        """Output statistics when the strategy stops.

        Calculates and prints the final performance statistics including
        bar count, order counts, win/loss counts, win rate percentage,
        and total profit/loss.

        Returns:
            None
        """
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )
