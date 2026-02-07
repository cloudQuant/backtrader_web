"""Run script for TimeLine MA (Fenshi MA) Futures Strategy.

This script runs the TimeLine MA strategy using rebar futures data RB889.csv.
The strategy is based on time average price line and moving average filter,
with trailing stop loss.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import yaml
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# Import strategy and data feed from strategy_fenshi_ma.py
from strategy_fenshi_ma import TimeLineMaStrategy, RbPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config(config_file: str = "config.yaml") -> Dict[str, Any]:
    """Load strategy configuration from YAML file.

    Args:
        config_file: Path to the configuration file.

    Returns:
        Dictionary containing configuration parameters.
    """
    config_path = BASE_DIR / config_file
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory to avoid relative path failures."""
    search_paths = [
        BASE_DIR / "datas" / filename,
        BASE_DIR.parent / "datas" / filename,
        BASE_DIR.parent.parent / "datas" / filename,
        BASE_DIR.parent.parent / "tests" / "datas" / filename,
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent.parent / filename,
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found: {filename}")


def load_rb889_data(filename: str = "RB889.csv") -> pd.DataFrame:
    """Load rebar futures data.

    Keep the original data loading logic.
    """
    df = pd.read_csv(resolve_data_path(filename))
    # Only use these columns from the data
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest']]
    df.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'openinterest']
    # Sort and deduplicate
    df = df.sort_values("datetime")
    df = df.drop_duplicates("datetime")
    df.index = pd.to_datetime(df['datetime'])
    df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]
    # Remove error data with close price of 0
    df = df.astype("float")
    df = df[(df["open"] > 0) & (df['close'] > 0)]
    # Shorten date range to speed up testing
    df = df[df.index >= '2019-01-01']
    return df


def run():
    """Run the TimeLine MA strategy backtest.

    Run backtest using rebar futures data RB889.csv.
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    data_config = config.get('data', {})
    backtest_config = config.get('backtest', {})

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Load data
    print("Loading rebar futures data...")
    data_filename = data_config.get('symbol', 'RB889') + '.csv'
    df = load_rb889_data(data_filename)
    print(f"Data range: {df.index[0]} to {df.index[-1]}, total {len(df)} bars")

    # Use RbPandasFeed to load data
    name = "RB"
    feed = RbPandasFeed(dataname=df)
    cerebro.adddata(feed, name=name)

    # Set contract trading information
    comm = ComminfoFuturesPercent(
        commission=backtest_config.get('commission', 0.0001),
        margin=backtest_config.get('margin', 0.10),
        mult=backtest_config.get('mult', 10)
    )
    cerebro.broker.addcommissioninfo(comm, name=name)
    cerebro.broker.setcash(backtest_config.get('initial_cash', 1000000.0))

    # Add strategy with parameters from config
    cerebro.addstrategy(TimeLineMaStrategy,



                       ma_period=params.get('ma_period', 200),
                       stop_mult=params.get('stop_mult', 1))

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
    print("Time line MA strategy backtest results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # Assert test results (exact values from original test) - based on data after 2019-01-01
    assert strat.bar_num == 41306, f"Expected bar_num=41306, got {strat.bar_num}"
    assert strat.buy_count == 337, f"Expected buy_count=337, got {strat.buy_count}"
    assert strat.sell_count == 240, f"Expected sell_count=240, got {strat.sell_count}"
    assert total_trades == 577, f"Expected total_trades=577, got {total_trades}"
    # assert sharpe_ratio is None or -20 < sharpe_ratio < 20, f"Expected sharpe_ratio=0.691750545190999, got {sharpe_ratio}"
    assert abs(annual_return - (0.04084785450929118)) < 1e-6, f"Expected annual_return=0.04084785450929118, got {annual_return}"
    assert abs(max_drawdown - 0.17075848708181077) < 1e-6, f"Expected max_drawdown=0.17075848708181077, got {max_drawdown}"
    assert abs(final_value - 1105093.7719086385) < 0.01, f"Expected final_value=1105093.7719086385, got {final_value}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Time Line MA (TimeLine MA) Intraday Strategy")
    print("=" * 60)
    run()
