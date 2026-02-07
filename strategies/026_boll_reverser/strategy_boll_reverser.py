"""BollReverser Bollinger Band reversal strategy.

This module tests a mean-reversion Bollinger Band strategy that trades
against breakouts. The strategy goes short when price breaks above the
upper band (betting on reversal from overbought) and goes long when price
breaks below the lower band (betting on reversal from oversold).

Strategy Logic:
    - Open short when price continuously exceeds upper band (overbought reversal)
    - Open long when price continuously falls below lower band (oversold reversal)
    - Close long position when price crosses above upper band
    - Close short position when price crosses below lower band

This is the opposite approach to the trend-following Boll strategy.

Reference:
    backtrader-example/strategies/boll_reverser.py
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


class BollReverserStrategy(bt.Strategy):
    """BollReverser Bollinger Band reversal (mean-reversion) strategy.

    This strategy implements a mean-reversion trading system using Bollinger Bands.
    It trades against breakouts, betting that prices will reverse back toward
    the mean after becoming overbought or oversold.

    Strategy Rules (Reversal Approach):
        1. Entry signals:
           - Short: Close > top band for 2 consecutive bars (overbought)
           - Long: Close < bottom band for 2 consecutive bars (oversold)
        2. Exit signals:
           - Long exit: Close crosses above upper band (resistance)
           - Short exit: Close crosses below lower band (support)

    This is the opposite of the trend-following Boll strategy. Instead of
    trading with breakouts, it fades them and expects mean reversion.

    Attributes:
        params: Strategy parameters including:
            - period_boll (int): Bollinger Band period (default: 52).
        bar_num: Counter for total bars processed.
        buy_count: Counter for buy orders executed.
        sell_count: Counter for sell orders executed.
        sum_profit: Total profit/loss from all closed trades.
        win_count: Number of profitable trades.
        loss_count: Number of unprofitable trades.
        trade_count: Total number of completed trades.
        data0: Reference to the first data feed.
        boll: Bollinger Bands indicator with top, mid, and bot lines.
    """

    params = (
        ("period_boll", 52),
    )

    def log(self, txt, dt=None, force=False):
        """Log output function with timestamp.

        Args:
            txt: Text content to log.
            dt: Datetime for the log entry. Defaults to current data datetime.
            force: Whether to force output. If False, logging is skipped.
        """
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """Initialize the BollReverser strategy.

        Sets up tracking counters, data references, and the Bollinger Bands
        indicator for generating reversal signals.
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

        # Bollinger Band indicator
        self.boll = bt.indicators.BollingerBands(self.data0, period=self.p.period_boll)

    def notify_trade(self, trade):
        """Handle trade completion notification.

        Updates win/loss counters and accumulates total profit/loss when
        a trade closes.

        Args:
            trade: Trade object containing trade information.
        """
        if not trade.isclosed:
            return
        self.trade_count += 1
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl

    def close_gt_up(self):
        """Check if closing price is continuously above upper band.

        Detects overbought condition where price has broken above the upper
        Bollinger Band for two consecutive bars, signaling a potential
        short entry (mean-reversion).

        Returns:
            bool: True if current and previous close are above upper band.
        """
        data = self.data0
        return data.close[0] > self.boll.top[0] and data.close[-1] > self.boll.top[-1]

    def close_lt_dn(self):
        """Check if closing price is continuously below lower band.

        Detects oversold condition where price has broken below the lower
        Bollinger Band for two consecutive bars, signaling a potential
        long entry (mean-reversion).

        Returns:
            bool: True if current and previous close are below lower band.
        """
        data = self.data0
        return data.close[0] < self.boll.bot[0] and data.close[-1] < self.boll.bot[-1]

    def close_across_top(self):
        """Check if price crosses above upper band.

        Detects when price crosses from below the upper band to above it.
        This signals an exit for long positions as price hits resistance
        at the upper band.

        Returns:
            bool: True if previous close was below and current close is above upper band.
        """
        data = self.data0
        return data.close[-1] < self.boll.top[-1] and data.close[0] > self.boll.top[0]

    def close_across_bot(self):
        """Check if price crosses below lower band.

        Detects when price crosses from above the lower band to below it.
        This signals an exit for short positions as price hits support
        at the lower band.

        Returns:
            bool: True if previous close was above and current close is below lower band.
        """
        data = self.data0
        return data.close[-1] > self.boll.bot[-1] and data.close[0] < self.boll.bot[0]

    def next(self):
        """Execute the core BollReverser strategy logic.

        This method implements the mean-reversion trading logic:

        1. Entry conditions (position.size == 0):
           - Short entry: close_gt_up() (overbought, expect reversal down)
           - Long entry: close_lt_dn() (oversold, expect reversal up)

        2. Exit conditions:
           - Long exit (position.size > 0): close_across_top() (price hits upper band)
           - Short exit (position.size < 0): close_across_bot() (price hits lower band)

        Position sizing:
           - Uses all available cash for new positions
           - size = int(cash / close_price)
        """
        self.bar_num += 1
        position = self.getposition()

        if position.size == 0:
            # No current position - look for entry opportunities
            if self.close_gt_up():
                # Overbought - open short position expecting reversal down
                size = int(self.broker.getcash() / self.data0.close[0])
                if size > 0:
                    self.sell(size=size)
                    self.sell_count += 1
            elif self.close_lt_dn():
                # Oversold - open long position expecting reversal up
                size = int(self.broker.getcash() / self.data0.close[0])
                if size > 0:
                    self.buy(size=size)
                    self.buy_count += 1
        elif position.size > 0:
            # Long position active - check exit condition
            if self.close_across_top():
                # Price crossed above upper band - close long position
                self.close()
                self.sell_count += 1
        elif position.size < 0:
            # Short position active - check exit condition
            if self.close_across_bot():
                # Price crossed below lower band - close short position
                self.close()
                self.buy_count += 1

    def stop(self):
        """Output statistics when strategy ends.

        Calculates and logs final statistics including total bars,
        order counts, win/loss ratio, and total profit/loss.
        """
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
