#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dual Thrust Intraday Breakout Strategy Runner.

Loads configuration from config.yaml and runs backtest using glass futures
data FG889.csv.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import yaml

import pandas as pd
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesFixed

# Import strategy and data feed from local strategy module
from strategy_dual_thrust import DualThrustStrategy, FgPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load strategy configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory to avoid relative path failures.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the located data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any search path.
    """
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent.parent / filename,
        BASE_DIR.parent.parent / "datas" / filename,
        BASE_DIR.parent.parent / "tests" / "datas" / filename,
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found: {filename}")


def load_fg_data(filename: str = "FG889.csv", max_rows: int = None) -> pd.DataFrame:
    """Load glass futures data from CSV file.

    Maintains the original data loading logic with date range filtering.

    Args:
        filename: Name of the CSV file to load.
        max_rows: Maximum number of rows to load for faster testing.

    Returns:
        DataFrame containing the loaded futures data with filtered date range.
    """
    data_kwargs = dict(
        fromdate=datetime.datetime(2020, 1, 1),  # Further shorten date range to accelerate testing
        todate=datetime.datetime(2021, 7, 31),
    )

    df = pd.read_csv(resolve_data_path(filename))
    # Only keep these columns from the data
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest']]
    df.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']
    # Rename columns
    df.index = pd.to_datetime(df['datetime'])
    df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]
    df = df[(df.index <= data_kwargs['todate']) & (df.index >= data_kwargs['fromdate'])]
    return df


def run():
    """Run the Dual Thrust intraday breakout strategy backtest.

    Performs backtesting using glass futures data from FG889.csv file.

    Raises:
        AssertionError: If test assertions fail.
    """
    # Load configuration
    config = load_config()
    backtest_config = config['backtest']

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Load data
    print("Loading glass futures data...")
    df = load_fg_data("FG889.csv")
    print(f"Data range: {df.index[0]} to {df.index[-1]}, total {len(df)} bars")

    # Load data using FgPandasFeed
    name = "FG"
    feed = FgPandasFeed(dataname=df)
    cerebro.adddata(feed, name=name)

    # Set contract trading information (using fixed commission)
    comm = ComminfoFuturesFixed(
        commission=backtest_config['commission'],
        margin=backtest_config['margin'],
        mult=backtest_config['multiplier']
    )
    cerebro.broker.addcommissioninfo(comm, name=name)
    cerebro.broker.setcash(backtest_config['initial_cash'])

    # Add strategy
    cerebro.addstrategy(DualThrustStrategy)




    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.TotalValue, _name="my_value")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="my_sharpe")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="my_returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="my_drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="my_trade_analyzer")
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

    # Run backtest
    print("Starting backtest...")
    results = cerebro.run()

    # Get results
    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    max_drawdown = strat.analyzers.my_drawdown.get_analysis()["max"]["drawdown"] / 100
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("\n" + "=" * 50)
    print("Dual Thrust Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # Assert test results (exact values) - Based on data from 2020-01-01 to 2021-07-31
    assert strat.bar_num == 123960, f"Expected bar_num=123960, got {strat.bar_num}"
    assert strat.buy_count == 14, f"Expected buy_count=14, got {strat.buy_count}"
    assert strat.sell_count == 7, f"Expected sell_count=7, got {strat.sell_count}"
    assert total_trades == 21, f"Expected total_trades=21, got {total_trades}"
    # final_value tolerance: 0.01, other indicators tolerance: 1e-6
    assert abs(sharpe_ratio - (-16.73034120003273)) < 1e-6, f"Expected sharpe_ratio=-16.73034120003273, got {sharpe_ratio}"
    assert abs(annual_return - (-0.016015877679295135)) < 1e-6, f"Expected annual_return=-0.016015877679295135, got {annual_return}"
    assert abs(max_drawdown - 0.04545908283255804) < 1e-6, f"Expected max_drawdown=0.04545908283255804, got {max_drawdown}"
    assert abs(final_value - 48788.0) < 0.01, f"Expected final_value=48788.0, got {final_value}"

    print("\nAll tests passed!")
    return final_value


if __name__ == "__main__":
    print("=" * 60)
    print("Dual Thrust Intraday Breakout Strategy Test")
    print("=" * 60)
    run()
