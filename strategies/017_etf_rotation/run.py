"""Run script for ETF Rotation Strategy.

This script runs an ETF rotation strategy that rotates between SSE 50 ETF and
ChiNext ETF based on momentum indicators. The strategy uses moving average
ratios to determine which ETF shows stronger momentum and allocates capital
accordingly.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import yaml
import backtrader as bt

# Import strategy from strategy_etf_rotation.py
from strategy_etf_rotation import EtfRotationStrategy

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
        BASE_DIR.parent.parent / "datas" / filename,  # 项目根目录datas
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


def load_etf_data(filename: str) -> pd.DataFrame:
    """Load ETF data from CSV file and prepare for backtrader.

    This function reads ETF price data from a CSV file with two columns
    (date and closing price), then augments it with the additional columns
    required by backtrader (open, high, low, volume, openinterest).

    The input CSV format should be:
    - Skip 1 header row
    - Column 0: Date (FSRQ format or similar)
    - Column 1: Closing price

    Since only closing prices are available, open/high/low are set to the
    close value, and volume/openinterest are set to dummy values.

    Args:
        filename: Name of the CSV file to load (e.g., 'SSE50_ETF.csv').
            The file is located using resolve_data_path().

    Returns:
        DataFrame with datetime index and columns:
            - open: Opening price (equal to close)
            - high: Highest price (equal to close)
            - low: Lowest price (equal to close)
            - close: Closing price (from input data)
            - volume: Trading volume (dummy value: 1000000)
            - openinterest: Open interest (dummy value: 1000000)

    Raises:
        FileNotFoundError: If the data file cannot be located.
        ValueError: If the CSV file format is invalid.
    """
    df = pd.read_csv(resolve_data_path(filename), skiprows=1, header=None)
    df.columns = ['datetime', 'close']
    df['open'] = df['close']
    df['high'] = df['close']
    df['low'] = df['close']
    df['volume'] = 1000000
    df['openinterest'] = 1000000
    df.index = pd.to_datetime(df['datetime'])
    df = df[['open', 'high', 'low', 'close', 'volume', 'openinterest']]
    df = df.astype('float')
    return df


def run():
    """Run the ETF rotation strategy backtest with historical data.

    This end-to-end test loads historical data for SSE 50 ETF and ChiNext ETF,
    runs the EtfRotationStrategy backtest, and validates the results against
    expected performance metrics.

    Test Configuration:
        - Initial Capital: 50,000
        - Commission: 0.02% (0.0002)
        - MA Period: 20 days
        - Data: SSE 50 ETF and ChiNext ETF from 2011-09-20 onwards
        - Start date: 2011-09-20 (filtered after loading)

    Assertions:
        - bar_num == 2600 (total bars processed)
        - buy_count > 0 (at least one buy order)
        - sell_count > 0 (at least one sell order)
        - total_trades > 0 (at least one completed trade)
        - sharpe_ratio == 0.5429576897026931 (exact value)
        - annual_return == 0.16189795444232807 (exact value)
        - max_drawdown == 0.3202798124215756 (exact value)
        - final_value == 235146.28691140004 (exact value)

    Raises:
        AssertionError: If any of the performance assertions fail.
        FileNotFoundError: If required data files are missing.
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    data_config = config.get('data', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)

    # Load SSE 50 ETF data (SSE 50 ETF - Shanghai Stock Exchange 50 Index ETF)
    print("Loading SSE 50 ETF data...")
    df1 = load_etf_data("SSE50_ETF.csv")
    df1 = df1[df1.index >= pd.to_datetime("2011-09-20")]
    print(f"SSE 50 ETF data range: {df1.index[0]} to {df1.index[-1]}, total {len(df1)} records")
    feed1 = bt.feeds.PandasDirectData(dataname=df1)
    cerebro.adddata(feed1, name="sz")

    # Load ChiNext ETF data (ChiNext ETF - Chinese Growth Enterprise Market Index ETF)
    print("Loading ChiNext ETF data...")
    df2 = load_etf_data("ChiNext_ETF.csv")
    print(f"ChiNext ETF data range: {df2.index[0]} to {df2.index[-1]}, total {len(df2)} records")
    feed2 = bt.feeds.PandasDirectData(dataname=df2)
    cerebro.adddata(feed2, name="cy")

    # Set initial capital and commission
    cerebro.broker.setcash(backtest_config.get('initial_cash', 50000.0))
    cerebro.broker.setcommission(commission=backtest_config.get('commission', 0.0002), stocklike=True)

    # Add strategy
    cerebro.addstrategy(EtfRotationStrategy, ma_period=params.get('ma_period', 20))




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
    print("\nStarting backtest...")
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
    print("ETF Rotation Strategy Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 50)

    # Assert test results - using exact assertions from original test
    # final_value tolerance: 0.01, other indicators tolerance: 1e-6
    assert strat.bar_num == 2600, f"Expected bar_num=2600, got {strat.bar_num}"
    assert strat.buy_count == 266, f"Expected buy_count=266, got {strat.buy_count}"
    assert strat.sell_count == 129, f"Expected sell_count=129, got {strat.sell_count}"
    assert total_trades == 265, f"Expected total_trades=265, got {total_trades}"
    assert abs(sharpe_ratio - 0.5429576897026931) < 1e-6, f"Expected sharpe_ratio=0.5429576897026931, got {sharpe_ratio}"
    assert abs(annual_return - 0.16189795444232807) < 1e-6, f"Expected annual_return=0.16189795444232807, got {annual_return}"
    assert abs(max_drawdown - 0.3202798124215756) < 1e-6, f"Expected max_drawdown=0.3202798124215756, got {max_drawdown}"
    assert abs(final_value - 235146.28691140004) < 0.01, f"Expected final_value=235146.28691140004, got {final_value}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("ETF Rotation Strategy")
    print("=" * 60)
    run()
