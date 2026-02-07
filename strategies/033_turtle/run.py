#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Turtle trading strategy runner.

This module provides a run() function to execute the Turtle strategy backtest.
It loads configuration from config.yaml, data from strategy_turtle module,
and runs the backtest with the same assertions as the original test file.

The strategy class is defined inline in this file to avoid issues with
backtrader's metaclass when importing strategy classes from separate modules.
"""
import os
import yaml
import datetime
from pathlib import Path

import pandas as pd
import backtrader as bt

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml.

    Returns:
        dict: Configuration dictionary containing strategy parameters.
    """
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """Locate data files by searching multiple potential directory paths.

    Args:
        filename: The name of the data file to locate.

    Returns:
        Path: The absolute path to the located data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the searched directories.
    """
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR / "datas" / filename,
        BASE_DIR.parent / "datas" / filename,
        BASE_DIR.parent.parent / "datas" / filename,  # Add repository root datas folder
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for p in search_paths:
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot find data file: {filename}")


def load_sh600000_data():
    """Load Shanghai stock data (SH600000) for backtesting.

    Returns:
        bt.feeds.PandasData: Data feed for backtrader.
    """
    print("Loading Shanghai stock data...")
    data_path = resolve_data_path("sh600000.csv")
    df = pd.read_csv(data_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')
    df = df.set_index('datetime')
    df = df[(df.index >= '2000-01-01') & (df.index <= '2022-12-31')]
    df = df[df['close'] > 0]

    df = df[['open', 'high', 'low', 'close', 'volume']]

    data_feed = bt.feeds.PandasData(
        dataname=df,
        datetime=None,
        open=0,
        high=1,
        low=2,
        close=3,
        volume=4,
        openinterest=-1,
    )
    return data_feed


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
    """
    params = (
        ('maperiod', 15),
        ('breakout_period_days', 20),
        ('price_rate_of_change_perc', 0.1),
        ('regime_filter_ma_period', 200),
        ('trailing_stop_loss_perc', 0.1),
    )

    def __init__(self):
        """Initialize the Turtle trading strategy."""
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
        """Handle order status updates."""
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
        """Handle trade completion notifications."""
        if trade.isclosed:
            self.sum_profit += trade.pnlcomm
            if trade.pnlcomm > 0:
                self.win_count += 1
            else:
                self.loss_count += 1

    def next(self):
        """Execute the strategy's trading logic for each bar."""
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
        """Output final trading statistics when backtesting completes."""
        win_rate = (self.win_count / (self.win_count + self.loss_count) * 100) if (self.win_count + self.loss_count) > 0 else 0
        print(
            f"{self.data.datetime.datetime(0)}, bar_num={self.bar_num}, "
            f"buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, "
            f"win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}"
        )


def run():
    """Run the Turtle trading strategy backtest.

    This function creates a cerebro instance, loads Shanghai stock data,
    runs the backtesting with TurtleStrategy, and verifies results using
    assertions matching the original test file.

    Returns:
        Backtest results.
    """
    # Load configuration
    config = load_config()

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.broker.setcash(config['backtest']['initial_cash'])
    cerebro.broker.setcommission(commission=config['backtest']['commission'])

    # Load data
    data_feed = load_sh600000_data()
    cerebro.adddata(data_feed, name="SH600000")

    # Add strategy with parameters from config
    params = config.get('params', {})
    cerebro.addstrategy(TurtleStrategy, **params)

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="my_sharpe")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="my_returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="my_drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trade")

    # 日志配置
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    cerebro.addobserver(
        bt.observers.TradeLogger,
        log_orders=True,
        log_trades=True,
        log_positions=True,
        log_data=True,
        log_indicators=True,       # 在data日志中包含策略指标
        log_dir=log_dir,
        log_file_enabled=True,
        file_format='log',         # 默认log(tab分隔)，也可选'csv'
        # MySQL disabled by default - uncomment to enable
        # mysql_enabled=True,
        # mysql_host='localhost',
        # mysql_port=3306,
        # mysql_user='root',
        # mysql_password='your_password',
        # mysql_database='backtrder_web',
        # mysql_table_prefix='bt',
    )

    print("Starting backtest...")
    results = cerebro.run()
    strat = results[0]

    # Get analyzer results
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get('sharperatio', None)
    returns = strat.analyzers.my_returns.get_analysis()
    annual_return = returns.get('rnorm', 0)
    drawdown = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    trade_analysis = strat.analyzers.my_trade.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    print("=" * 50)
    print("Turtle trading strategy backtest results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  win_count: {strat.win_count}")
    print(f"  loss_count: {strat.loss_count}")
    print(f"  sum_profit: {strat.sum_profit:.2f}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 50)

    # Assertions - using precise assertions (matching original test file)
    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 5216, f"Expected bar_num=5216, got {strat.bar_num}"
    assert strat.buy_count == 46, f"Expected buy_count=46, got {strat.buy_count}"
    assert strat.sell_count == 46, f"Expected sell_count=46, got {strat.sell_count}"
    assert strat.win_count == 17, f"Expected win_count=17, got {strat.win_count}"
    assert strat.loss_count == 29, f"Expected loss_count=29, got {strat.loss_count}"
    assert total_trades == 46, f"Expected total_trades=46, got {total_trades}"
    assert abs(final_value - 100008.96) < 0.01, f"Expected final_value=100008.96, got {final_value}"
    assert abs(sharpe_ratio - (-248.19599467327285)) < 1e-6, f"Expected sharpe_ratio=-248.19599467327285, got {sharpe_ratio}"
    assert abs(annual_return - (4.1691151679622e-06)) < 1e-6, f"Expected annual_return=4.1691151679622e-06, got {annual_return}"
    assert abs(max_drawdown - 0.02450295600930705) < 1e-6, f"Expected max_drawdown=0.02450295600930705, got {max_drawdown}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Turtle trading strategy run")
    print("=" * 60)
    run()
