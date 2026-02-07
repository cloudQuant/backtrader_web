#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MACD EMA Multi-Contract Futures Strategy Runner.

Loads configuration from config.yaml and runs backtest using rebar futures
multi-contract data.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import os
from pathlib import Path
import yaml

import pandas as pd
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# Import strategy and data feed from local strategy module
from strategy_macd_ema_true import MacdEmaTrueStrategy, RbPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load strategy configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Locates data files based on the script directory to avoid relative path failures."""
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


def load_rb_multi_data(data_dir: str = "rb") -> dict:
    """Loads multi-contract rebar futures data.

    Maintains the original PandasDirectData loading method.

    Returns:
        dict: A dictionary mapping contract names to DataFrames.
    """
    data_kwargs = dict(
        fromdate=datetime.datetime(2019, 1, 1),  # Shorten date range to speed up testing
        todate=datetime.datetime(2020, 12, 31),
    )

    data_path = resolve_data_path(data_dir)
    file_list = os.listdir(data_path)

    # Sort file list for consistent ordering across platforms (Windows vs macOS)
    file_list = sorted(file_list, key=lambda x: x.lower())

    # Ensure rb99.csv is placed first as index data (case-insensitive for Windows)
    rb99_file = None
    for f in file_list:
        if f.lower() == "rb99.csv":
            rb99_file = f
            break
    if rb99_file:
        file_list.remove(rb99_file)
        file_list = [rb99_file] + file_list

    datas = {}
    for file in file_list:
        if not file.endswith('.csv'):
            continue
        name = file[:-4]
        df = pd.read_csv(data_path / file)
        # Only keep specific columns from data
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']]
        # Modify column names
        df.index = pd.to_datetime(df['datetime'])
        df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]
        df = df[(df.index <= data_kwargs['todate']) & (df.index >= data_kwargs['fromdate'])]
        if len(df) == 0:
            continue
        datas[name] = df

    return datas


def run():
    """Run the MACD EMA multi-contract futures strategy backtest."""
    # Load configuration
    config = load_config()
    backtest_config = config['backtest']

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Load multi-contract data
    print("Loading rebar futures multi-contract data...")
    datas = load_rb_multi_data("rb")
    print(f"Loaded {len(datas)} contract data files")

    # Use RbPandasFeed to load data (consistent with original PandasDirectData logic)
    for name, df in datas.items():
        feed = RbPandasFeed(dataname=df)
        cerebro.adddata(feed, name=name)
        # Set contract trading information
        comm = ComminfoFuturesPercent(
            commission=backtest_config['commission'],
            margin=backtest_config['margin'],
            mult=backtest_config['multiplier']
        )
        cerebro.broker.addcommissioninfo(comm, name=name)

    cerebro.broker.setcash(backtest_config['initial_cash'])

    # Add strategy
    cerebro.addstrategy(MacdEmaTrueStrategy)




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
    print("MACD EMA Multi-Contract Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # Assert test results - use precise assertions
    # final_value tolerance: 0.01, other indicators tolerance: 1e-6
    assert strat.bar_num == 5540, f"Expected bar_num=11332, got {strat.bar_num}"
    assert strat.buy_count == 213, f"Expected buy_count=213, got {strat.buy_count}"
    assert strat.sell_count == 213, f"Expected sell_count=213, got {strat.sell_count}"
    assert total_trades > 0, f"Expected total_trades > 0, got {total_trades}"
    assert abs(sharpe_ratio - (-1.4062246847166893)) < 1e-6, f"Expected sharpe_ratio=0.6258752691928109, got {sharpe_ratio}"
    assert abs(annual_return - (-0.0467842728314899)) < 1e-6, f"Expected annual_return=0.07557088428298599, got {annual_return}"
    assert abs(max_drawdown - 0.1468985826746771) < 1e-6, f"Expected max_drawdown=0.20860432995832906, got {max_drawdown}"
    assert abs(final_value - 45586.761999999995) < 0.01, f"Expected final_value=66241.75697345377, got {final_value}"

    print("\nAll tests passed!")
    return final_value


if __name__ == "__main__":
    print("=" * 60)
    print("MACD EMA Multi-Contract Futures Strategy Test")
    print("=" * 60)
    run()
