#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sky Garden Intraday Breakout Strategy Runner.

Loads configuration from config.yaml and runs backtest using zinc futures
data ZN889.csv.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from pathlib import Path
import yaml

import pandas as pd
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# Import strategy and data feed from local strategy module
from strategy_sky_garden import SkyGardenStrategy, ZnPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load strategy configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory to avoid relative path failures."""
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


def load_zn889_data(filename: str = "ZN889.csv") -> pd.DataFrame:
    """Load zinc futures data.

    Maintains the original data loading logic.

    Args:
        filename: Name of the CSV file containing zinc futures data.

    Returns:
        DataFrame with zinc futures data.
    """
    df = pd.read_csv(resolve_data_path(filename))
    # Only keep these columns from the data
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest']]
    df.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']
    # Sort and remove duplicates
    df = df.sort_values("datetime")
    df = df.drop_duplicates("datetime")
    df.index = pd.to_datetime(df['datetime'])
    df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]
    # Shorten date range to speed up testing
    df = df[df.index >= '2020-01-01']
    return df


def run():
    """Run the Sky Garden intraday breakout strategy backtest.

    Runs backtest using zinc futures data ZN889.csv.

    Raises:
        AssertionError: If any of the test assertions fail.
    """
    # Load configuration
    config = load_config()
    backtest_config = config['backtest']
    params_config = config['params']

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Load data
    print("Loading zinc futures data...")
    df = load_zn889_data("ZN889.csv")
    print(f"Data range: {df.index[0]} to {df.index[-1]}, total {len(df)} records")

    # Load data using ZnPandasFeed
    name = "ZN"
    feed = ZnPandasFeed(dataname=df)
    cerebro.adddata(feed, name=name)

    # Set contract trading information
    comm = ComminfoFuturesPercent(
        commission=backtest_config['commission'],
        margin=backtest_config['margin'],
        mult=backtest_config['multiplier']
    )
    cerebro.broker.addcommissioninfo(comm, name=name)
    cerebro.broker.setcash(backtest_config['initial_cash'])

    # Add strategy with fixed parameters k1=8, k2=8
    cerebro.addstrategy(SkyGardenStrategy, k1=params_config['k1'], k2=params_config['k2'])




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
    print("Sky Garden Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # Assert test results (exact values) - based on data after 2018-01-01
    assert strat.bar_num == 32349, f"Expected bar_num=32349, got {strat.bar_num}"
    assert strat.buy_count == 20, f"Expected buy_count=20, got {strat.buy_count}"
    assert strat.sell_count == 21, f"Expected sell_count=21, got {strat.sell_count}"
    assert total_trades > 0, f"Expected total_trades > 0, got {total_trades}"
    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert abs(sharpe_ratio - (1.7399955949849073)) < 1e-6, f"Expected sharpe_ratio=0.4071392839128455, got {sharpe_ratio}"
    assert abs(annual_return - (0.1594097201976482)) < 1e-6, f"Expected annual_return=0.05046792274087781, got {annual_return}"
    assert abs(max_drawdown - 0.1489498258942073) < 1e-6, f"Expected max_drawdown=0.16266069999999963, got {max_drawdown}"
    assert abs(final_value - 64961.97000000003) < 0.01, f"Expected final_value=61050.48500000002, got {final_value}"

    print("\nAll tests passed!")
    return final_value


if __name__ == "__main__":
    print("=" * 60)
    print("Sky Garden Intraday Breakout Strategy Test")
    print("=" * 60)
    run()
