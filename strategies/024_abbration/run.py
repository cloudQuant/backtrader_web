"""Run script for Abbration Bollinger Band breakout strategy.

This script loads configuration from config.yaml, runs a backtest on
Shanghai stock data (sh600000.csv), and validates results against
expected values.

Usage:
    python run.py
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from pathlib import Path

import pandas as pd
import backtrader as bt

from strategy_abbration import AbbrationStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Locate a data file by searching multiple possible directory paths.

    This function searches for data files in several predefined locations
    to avoid relative path issues when running tests from different working
    directories. It supports an environment variable for custom data directory
    configuration.

    Args:
        filename: Name of the data file to locate (e.g., 'sh600000.csv').

    Returns:
        Path object pointing to the located data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            search paths.

    Search Paths:
        1. Current strategy directory
        2. Parent directory (strategies/)
        3. Grandparent directory (project root)
        4. tests/datas/ directory
        5. Custom directory from BACKTRADER_DATA_DIR environment variable
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


def load_sh600000_data():
    """Load Shanghai stock data (sh600000.csv) for backtesting.

    Returns:
        bt.feeds.PandasData: Data feed configured with OHLCV data.

    Raises:
        FileNotFoundError: If the data file cannot be located.
    """
    data_path = resolve_data_path("sh600000.csv")
    df = pd.read_csv(data_path)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')  # Sort in chronological order
    df = df.set_index('datetime')
    df = df[(df.index >= '2000-01-01') & (df.index <= '2022-12-31')]
    df = df[df['close'] > 0]  # Filter invalid data

    # Reorder columns to match PandasData default format
    df = df[['open', 'high', 'low', 'close', 'volume']]

    data_feed = bt.feeds.PandasData(
        dataname=df,
        datetime=None,  # Use index as date
        open=0,
        high=1,
        low=2,
        close=3,
        volume=4,
        openinterest=-1,
    )
    return data_feed


def run():
    """Run the Abbration Bollinger Band breakout strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates a Cerebro backtest engine
    3. Loads Shanghai stock data
    4. Adds the AbbrationStrategy with configured parameters
    5. Runs the backtest with analyzers
    6. Validates results against expected values

    Expected Results:
        - bar_num: 5216
        - buy_count: 19
        - sell_count: 20
        - win_count: 9
        - loss_count: 6
        - total_trades: 16
        - final_value: 423,916.71
        - sharpe_ratio: 0.2701748176643007
        - annual_return: 0.06952761581010602
        - max_drawdown: 0.46515816375898594
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Set initial capital
    initial_cash = backtest_config.get('initial_cash', 100000.0)
    cerebro.broker.setcash(initial_cash)

    # Load data
    print("Loading Shanghai stock data...")
    data_feed = load_sh600000_data()
    cerebro.adddata(data_feed, name="SH600000")

    # Add strategy with parameters from config
    cerebro.addstrategy(



        AbbrationStrategy,
        boll_period=params.get('boll_period', 200),
        boll_mult=params.get('boll_mult', 2),
    )

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
    drawdown_info = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown_info["max"]["drawdown"] / 100 if drawdown_info["max"]["drawdown"] else 0
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("\n" + "=" * 50)
    print("Abbration Bollinger Band breakout strategy backtest results:")
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

    # Assertions - ensure strategy runs correctly
    assert strat.bar_num == 5216, f"Expected bar_num=5216, got {strat.bar_num}"
    assert strat.buy_count == 19, f"Expected buy_count=19, got {strat.buy_count}"
    assert strat.sell_count == 20, f"Expected sell_count=20, got {strat.sell_count}"
    assert strat.win_count == 9, f"Expected win_count=9, got {strat.win_count}"
    assert strat.loss_count == 6, f"Expected loss_count=6, got {strat.loss_count}"
    assert total_trades == 16, f"Expected total_trades=16, got {total_trades}"
    assert abs(final_value - 423916.71) < 0.01, f"Expected final_value=423916.71, got {final_value}"
    assert abs(sharpe_ratio - 0.2701748176643007) < 1e-6, f"Expected sharpe_ratio=0.2701748176643007, got {sharpe_ratio}"
    assert abs(annual_return - (0.06952761581010602)) < 1e-6, f"Expected annual_return=0.06952761581010602, got {annual_return}"
    assert abs(max_drawdown - 0.46515816375898594) < 1e-6, f"Expected max_drawdown=0.46515816375898594, got {max_drawdown}"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Abbration Bollinger Band breakout strategy run")
    print("=" * 60)
    run()
