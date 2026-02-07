"""Run script for BollEMA Bollinger Bands + EMA strategy.

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

from strategy_boll_ema import BollEMAStrategy, load_config

BASE_DIR = Path(__file__).resolve().parent


def resolve_data_path(filename: str) -> Path:
    """Locate data files based on the script directory to avoid relative path failures.

    Args:
        filename: Name of the data file to locate.

    Returns:
        Path: The resolved path to the data file.

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
    """Load Shanghai stock data (sh600000.csv) for backtesting.

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
    # Filter for test date range
    df = df[(df.index >= '2000-01-01') & (df.index <= '2022-12-31')]
    # Remove invalid data points
    df = df[df['close'] > 0]

    # Select required OHLCV columns
    df = df[['open', 'high', 'low', 'close', 'volume']]

    # Create data feed with column mapping
    data_feed = bt.feeds.PandasData(
        dataname=df,
        datetime=None,  # Using index as datetime
        open=0,
        high=1,
        low=2,
        close=3,
        volume=4,
        openinterest=-1,
    )
    return data_feed


def run():
    """Run the BollEMA Bollinger Bands + EMA strategy backtest.

    This function:
    1. Loads configuration from config.yaml
    2. Creates a Cerebro backtest engine
    3. Loads Shanghai stock data
    4. Adds the BollEMAStrategy with configured parameters
    5. Runs the backtest with analyzers
    6. Validates results against expected values

    Expected Results:
        - bar_num: 5280
        - buy_count: 43
        - sell_count: 44
        - win_count: 10
        - loss_count: 26
        - total_trades: 37
        - final_value: 705655.57
        - sharpe_ratio: 0.33646909650176043
        - annual_return: 0.09519461079565394
        - max_drawdown: 0.4537757234136652
    """
    # Load configuration
    config = load_config()
    params = config.get('params', {})
    backtest_config = config.get('backtest', {})

    cerebro = bt.Cerebro(stdstats=True, runonce=False)
    initial_cash = backtest_config.get('initial_cash', 100000.0)
    cerebro.broker.setcash(initial_cash)

    print("Loading Shanghai stock data...")
    data_feed = load_sh600000_data()
    cerebro.adddata(data_feed, name="SH600000")

    # Add strategy with specified parameters
    cerebro.addstrategy(BollEMAStrategy,



                       period_boll=params.get('period_boll', 136),
                       period_ema=params.get('period_ema', 99),
                       boll_diff=params.get('boll_diff', 0.5),
                       price_diff=params.get('price_diff', 0.3))

    # Attach performance analyzers
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

    # Extract strategy results
    strat = results[0]
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    drawdown_info = strat.analyzers.my_drawdown.get_analysis()
    max_drawdown = drawdown_info["max"]["drawdown"] / 100 if drawdown_info["max"]["drawdown"] else 0
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
    final_value = cerebro.broker.getvalue()

    # Print results summary
    print("\n" + "=" * 50)
    print("BollEMA Bollinger Bands + EMA Strategy Backtest Results:")
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

    # Assert expected values with strict tolerances
    assert strat.bar_num == 5280
    assert strat.buy_count == 43, f"Expected buy_count=43, got {strat.buy_count}"
    assert strat.sell_count == 44, f"Expected sell_count=44, got {strat.sell_count}"
    assert strat.win_count == 10, f"Expected win_count=10, got {strat.win_count}"
    assert strat.loss_count == 26, f"Expected loss_count=26, got {strat.loss_count}"
    assert total_trades == 37, f"Expected total_trades=37, got {total_trades}"
    assert abs(final_value - 705655.57) < 1e-2, f"Expected final_value=705655.57, got {final_value}"
    assert abs(sharpe_ratio - 0.33646909650176043) < 1e-6, f"sharpe_ratio={sharpe_ratio} out of range"
    assert abs(annual_return - 0.09519461079565394) < 1e-6, f"annual_return={annual_return} out of range"
    assert abs(max_drawdown - 0.4537757234136652) < 1e-6, f"max_drawdown={max_drawdown} out of range"

    print("\nTest passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("BollEMA Bollinger Bands + EMA Strategy Run")
    print("=" * 60)
    run()
