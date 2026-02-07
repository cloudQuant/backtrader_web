"""Run script for Hans123 Intraday Breakout Strategy.

This script runs the Hans123 intraday breakout strategy using rebar
futures data RB889.csv. The strategy is based on breakout of high/low
points from first N bars after market open, with moving average filter.
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

# Import strategy and data feed from strategy_hanse123.py
from strategy_hanse123 import Hans123Strategy, RbPandasFeed

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
    """Locate data files by searching multiple possible directory paths.

    This function searches for data files in several predefined locations relative
    to the script directory, avoiding issues with relative paths. It also checks
    an optional environment variable for custom data directory location.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the first found data file.

    Raises:
        FileNotFoundError: If the data file cannot be found in any of the
            searched locations.
    """
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


def load_rb889_data(filename: str = "RB889.csv", max_rows: int = 50000) -> pd.DataFrame:
    """Load rebar futures data.

    Maintains original data loading logic while limiting data rows to speed up testing.

    Args:
        filename: Name of the CSV file to load.
        max_rows: Maximum number of rows to load (for faster testing).

    Returns:
        DataFrame containing the loaded and processed futures data.
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
    # Remove erroneous data with close price of 0
    df = df.astype("float")
    df = df[(df["open"] > 0) & (df['close'] > 0)]
    # Limit data rows to speed up testing
    if max_rows and len(df) > max_rows:
        df = df.iloc[-max_rows:]
    return df


def run():
    """Run the Hans123 intraday breakout strategy backtest.

    This test function:
    1. Loads RB889 rebar futures data from CSV file
    2. Configures cerebro with data feed, commission info, and strategy
    3. Runs backtest with Hans123 strategy (MA period=200, bar_num=2)
    4. Collects performance metrics (Sharpe ratio, returns, drawdown, trades)
    5. Asserts that results match expected values

    Raises:
        AssertionError: If any of the test assertions fail (bar count, trade counts,
            Sharpe ratio, annual return, max drawdown, or final value).
        FileNotFoundError: If RB889.csv data file cannot be located.
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
    cerebro.addstrategy(Hans123Strategy,
                       ma_period=params.get('ma_period', 200),
                       bar_num=params.get('bar_num', 2))



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
    print("Hans123 Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # Assert test results (exact values from original test)
    assert strat.bar_num == 49801, f"Expected bar_num=49801, got {strat.bar_num}"
    assert strat.buy_count == 346, f"Expected buy_count=346, got {strat.buy_count}"
    assert strat.sell_count == 252, f"Expected sell_count=252, got {strat.sell_count}"
    assert total_trades == 598, f"Expected total_trades=598, got {total_trades}"
    assert abs(sharpe_ratio - (-0.38853827472284613)) < 1e-6, f"Expected sharpe_ratio=-0.38853827472284613, got {sharpe_ratio}"
    assert abs(annual_return - (-0.05485916735255581)) < 1e-6, f"Expected annual_return=-0.05485916735255581, got {annual_return}"
    assert abs(max_drawdown - 0.34452640045840965) < 1e-6, f"Expected max_drawdown=0.34452640045840965, got {max_drawdown}"
    assert abs(final_value - 844664.1285503485) < 0.01, f"Expected final_value=844664.13, got {final_value}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Hans123 Intraday Breakout Strategy")
    print("=" * 60)
    run()
