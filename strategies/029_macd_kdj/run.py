"""Run script for MACD+KDJ combined strategy.

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

from strategy_macd_kdj import MACDKDJStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory to avoid relative path failures.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path object pointing to the found data file.

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


def load_sh600000_data():
    """Load Shanghai Stock Exchange data (sh600000.csv) for backtesting.

    Returns:
        bt.feeds.PandasData: Data feed configured with OHLCV data.

    Raises:
        FileNotFoundError: If the data file cannot be located.
    """
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


def run():
    """Run the MACD+KDJ combined strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates a Cerebro backtest engine
    3. Loads Shanghai stock data
    4. Adds the MACDKDJStrategy with configured parameters
    5. Runs the backtest with analyzers
    6. Validates results against expected values

    Expected Results:
        - bar_num: 5382
        - buy_count: 215
        - sell_count: 216
        - total_trades: 212
        - final_value: 5870.49
        - sharpe_ratio: -0.12656086550315188
        - annual_return: -0.12361020751082702
        - max_drawdown: 0.9863327709363255
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True)
    initial_cash = backtest_config.get('initial_cash', 100000.0)
    cerebro.broker.setcash(initial_cash)

    print("Loading Shanghai Stock Exchange data...")
    data_feed = load_sh600000_data()
    cerebro.adddata(data_feed, name="SH600000")

    cerebro.addstrategy(



        MACDKDJStrategy,
        macd_fast_period=params.get('macd_fast_period', 12),
        macd_slow_period=params.get('macd_slow_period', 26),
        macd_signal_period=params.get('macd_signal_period', 9),
        kdj_fast_period=params.get('kdj_fast_period', 9),
        kdj_slow_period=params.get('kdj_slow_period', 3),
    )

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

    print("Starting backtest...")
    results = cerebro.run()

    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    drawdown_info = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown_info["max"]["drawdown"] / 100 if drawdown_info["max"]["drawdown"] else 0
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    print("\n" + "=" * 50)
    print("MACD+KDJ Strategy Backtest Results:")
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

    assert strat.bar_num == 5382, f"Expected bar_num=5382, got {strat.bar_num}"
    assert strat.buy_count == 215, f"Expected buy_count=215, got {strat.buy_count}"
    assert strat.sell_count == 216, f"Expected sell_count=216, got {strat.sell_count}"
    assert total_trades == 212, f"Expected total_trades=212, got {total_trades}"
    assert abs(final_value - 5870.49) < 0.01, f"Expected final_value=5870.49, got {final_value}"
    assert abs(sharpe_ratio - (-0.12656086550315188)) < 1e-6, f"Expected sharpe_ratio=-0.12656086550315188, got {sharpe_ratio}"
    assert abs(annual_return - (-0.12361020751082702)) < 1e-6, f"Expected annual_return=-0.12361020751082702, got {annual_return}"
    assert abs(max_drawdown - 0.9863327709363255) < 1e-6, f"Expected max_drawdown=0.9863327709363255, got {max_drawdown}"

    print("\nAll tests passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("MACD+KDJ Strategy Run")
    print("=" * 60)
    run()
