"""Run script for Convertible Bond Multi-Factor Intraday Strategy.

This script runs the convertible bond multi-factor intraday trading strategy
using convertible bond data. The strategy uses multiple factors for screening
and trading.
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

# Import strategy and data feed from strategy_cb.py
from strategy_cb import ConvertibleBondIntradayStrategy, ExtendPandasFeed

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


def clean_bond_data():
    """Clean and prepare convertible bond data."""
    df = pd.read_csv(resolve_data_path("bond_merged_all_data.csv"))
    df.columns = [
        "symbol",
        "bond_symbol",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "pure_bond_value",
        "convert_value",
        "pure_bond_premium_rate",
        "convert_premium_rate",
    ]
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df[df["datetime"] > pd.to_datetime("2018-01-01")]

    datas = {}
    for symbol, data in df.groupby("symbol", sort=True):
        data = data.set_index("datetime")
        data = data.drop(["symbol", "bond_symbol"], axis=1)
        data = data.dropna()
        datas[symbol] = data.astype("float")

    return datas


def run():
    """Run the convertible bond multi-factor intraday strategy backtest.

    Performs backtesting using convertible bond data.
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    data_config = config.get('data', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)

    # Load index data
    print("Loading index data...")
    index_data = pd.read_csv(resolve_data_path('bond_index_000000.csv'))
    index_data.index = pd.to_datetime(index_data['datetime'])
    index_data = index_data[index_data.index > pd.to_datetime("2018-01-01")]
    index_data = index_data.drop(['datetime'], axis=1)
    print(f"Index data range: {index_data.index[0]} to {index_data.index[-1]}, total {len(index_data)} bars")

    feed = ExtendPandasFeed(dataname=index_data)
    cerebro.adddata(feed, name='000000')

    # Clean and load convertible bond data
    print("\nLoading convertible bond data...")
    datas = clean_bond_data()
    print(f"Total {len(datas)} convertible bonds")

    added_count = 0
    max_bonds = 30  # Limit the number of bonds to speed up testing
    for symbol, data in datas.items():
        if len(data) > 30:
            if added_count >= max_bonds:
                break
            feed = ExtendPandasFeed(dataname=data)
            cerebro.adddata(feed, name=symbol)
            comm = ComminfoFuturesPercent(
                commission=backtest_config.get('commission', 0.0001),
                margin=backtest_config.get('margin', 0.1),
                mult=backtest_config.get('mult', 1)
            )
            cerebro.broker.addcommissioninfo(comm, name=symbol)
            added_count += 1

    print(f"Successfully added {added_count} convertible bond data feeds")

    # Set initial capital
    cerebro.broker.setcash(backtest_config.get('initial_cash', 1000000.0))

    # Add strategy
    cerebro.addstrategy(ConvertibleBondIntradayStrategy,



                       ma_period=params.get('ma_period', 20),
                       can_trade_num=params.get('can_trade_num', 2))

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
    print("Convertible Bond Multi-Factor Intraday Strategy Backtest Results:")
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
    assert strat.bar_num == 1885, f"Expected bar_num=1885, got {strat.bar_num}"
    assert strat.buy_count == 300, f"Expected buy_count=300, got {strat.buy_count}"
    assert strat.sell_count == 294, f"Expected sell_count=294, got {strat.sell_count}"
    assert total_trades == 299, f"Expected total_trades=299, got {total_trades}"
    # assert sharpe_ratio is None or -20 < sharpe_ratio < 20, f"Expected sharpe_ratio=0.23032590904888126, got {sharpe_ratio}"
    assert abs(annual_return - (0.030084430622900046)) < 1e-6, f"Expected annual_return=0.030084430622900046, got {annual_return}"
    assert abs(max_drawdown - 0.17750189678557882) < 1e-6, f"Expected max_drawdown=0.17750189678557882, got {max_drawdown}"
    assert abs(final_value - 1248218.9149463978) < 0.01, f"Expected final_value=1248218.9149463978, got {final_value}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Convertible Bond Multi-Factor Intraday Strategy")
    print("=" * 60)
    run()
