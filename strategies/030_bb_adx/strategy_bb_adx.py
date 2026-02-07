"""BB_ADX Bollinger Bands + ADX mean reversion strategy.

This module implements a mean reversion trading strategy that utilizes Bollinger Bands
for signals and ADX for locating and avoiding trends.

Strategy Overview:
    - Uses Bollinger Bands to identify overbought/oversold conditions
    - Uses ADX to filter out trending markets (only trade when ADX < threshold)
    - Goes long when price crosses back above lower band from below
    - Goes short when price crosses back below upper band from above
    - Exits when price crosses the middle band

Reference:
    backtrader-backtests/BollBand and ADX/BB_ADX.py
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


class BBADXStrategy(bt.Strategy):
    """Mean Reversion trading strategy that utilizes Bollinger Bands for signals and ADX for locating and avoiding trends.

    Strategy Logic:
        - Entry: When ADX < ADX_Max (non-trending market)
          - Short: Price crosses back below upper Bollinger Band from above
          - Long: Price crosses back above lower Bollinger Band from below
        - Exit:
          - Long exit: Price crosses above middle band
          - Short exit: Price crosses below middle band
        - Stop loss: Set at the opposite band

    Attributes:
        order: Reference to current pending order.
        stopprice: Current stop loss price.
        closepos: Reference to stop loss order.
        adx: Average Directional Movement Index indicator.
        bb: Bollinger Bands indicator.
        bar_num: Counter for total bars processed.
        buy_count: Counter for buy orders executed.
        sell_count: Counter for sell orders executed.
        win_count: Counter for profitable trades.
        loss_count: Counter for unprofitable trades.
        sum_profit: Total profit/loss from all closed trades.
        entry_price: Entry price of current position.
    """

    params = (
        ('BB_MA', 20),
        ('BB_SD', 2),
        ('ADX_Period', 14),
        ('ADX_Max', 40),
    )

    def __init__(self):
        """Initializes all variables to be used in this strategy."""
        # Initialize variables
        object.__setattr__(self, 'order', None)
        object.__setattr__(self, 'stopprice', None)
        object.__setattr__(self, 'closepos', None)
        object.__setattr__(self, 'adx', bt.indicators.AverageDirectionalMovementIndex(self.data, period=self.params.ADX_Period))
        object.__setattr__(self, 'bb', bt.indicators.BollingerBands(self.data, period=self.params.BB_MA, devfactor=self.params.BB_SD))

        # Statistics variables - use object.__setattr__ to bypass backtrader's line system
        object.__setattr__(self, 'bar_num', 0)
        object.__setattr__(self, 'buy_count', 0)
        object.__setattr__(self, 'sell_count', 0)
        object.__setattr__(self, 'win_count', 0)
        object.__setattr__(self, 'loss_count', 0)
        object.__setattr__(self, 'sum_profit', 0.0)
        object.__setattr__(self, 'entry_price', 0.0)

    def notify_order(self, order):
        """Run on every next iteration. Checks order status and logs accordingly."""
        if order.status in [order.Submitted, order.Accepted]:
            return
        elif order.status == order.Completed:
            if order.isbuy():
                object.__setattr__(self, 'buy_count', self.buy_count + 1)
                object.__setattr__(self, 'entry_price', order.executed.price)
            if order.issell():
                object.__setattr__(self, 'sell_count', self.sell_count + 1)
                if self.position.size == 0:
                    # Calculate profit/loss when closing position
                    pass
        elif order.status in [order.Rejected, order.Margin]:
            pass

        object.__setattr__(self, 'order', None)

    def notify_trade(self, trade):
        """Run on every next iteration. Logs data on every trade when closed."""
        if trade.isclosed:
            object.__setattr__(self, 'sum_profit', self.sum_profit + trade.pnlcomm)
            if trade.pnlcomm > 0:
                object.__setattr__(self, 'win_count', self.win_count + 1)
            else:
                object.__setattr__(self, 'loss_count', self.loss_count + 1)

    def next(self):
        """Runs for every candlestick. Checks conditions to enter and exit trades."""
        object.__setattr__(self, 'bar_num', self.bar_num + 1)

        if self.order:
            return

        if self.position.size == 0:
            if self.adx[0] < self.params.ADX_Max:
                if (self.data.close[-1] > self.bb.lines.top[-1]) and (self.data.close[0] <= self.bb.lines.top[0]):
                    self.order = self.sell()
                    self.stopprice = self.bb.lines.top[0]
                    self.closepos = self.buy(exectype=bt.Order.Stop, price=self.stopprice)

                elif (self.data.close[-1] < self.bb.lines.bot[-1]) and (self.data.close[0] >= self.bb.lines.bot[0]):
                    self.order = self.buy()
                    self.stopprice = self.bb.lines.bot[0]
                    self.closepos = self.sell(exectype=bt.Order.Stop, price=self.stopprice)

        elif self.position.size > 0:
            if (self.data.close[-1] < self.bb.lines.mid[-1]) and (self.data.close[0] >= self.bb.lines.mid[0]):
                self.closepos = self.close()
        elif self.position.size < 0:
            if (self.data.close[-1] > self.bb.lines.mid[-1]) and (self.data.close[0] <= self.bb.lines.mid[0]):
                self.closepos = self.close()

    def stop(self):
        """Output statistical information."""
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )
