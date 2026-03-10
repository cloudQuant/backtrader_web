#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Strategy Runner - DataReplayBollinger BandsStrategy"""

import os
import yaml
from pathlib import Path

import backtrader as bt

# Import strategy class
from strategy_data_replay_bollinger import ReplayBollingerStrategy

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """Load configuration from config.yaml"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """Locate data file path"""
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR / "datas" / filename,
        BASE_DIR.parent / "datas" / filename,
    BASE_DIR.parent.parent / "datas" / filename,  # Add repository root datas folder
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found: {filename}")


def run():
    """Run strategy backtest"""
    config = load_config()

    # Create cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # Add strategy (load parameters from config)
    params = config.get('params', {})
    cerebro.addstrategy(ReplayBollingerStrategy, **params)




    # Load data
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', '2005-2006-day-001')
    print(f"Loading data: {symbol}.txt...")
    data_path = resolve_data_path(f"{symbol}.txt")
    data = bt.feeds.BacktraderCSVData(dataname=str(data_path))

    # UsereplayFunction to replay daily data as weekly data
    cerebro.replaydata(
        data,
        timeframe=bt.TimeFrame.Weeks,
        compression=1
    )

    # Backtest configuration
    bt_config = config.get('backtest', {})
    cerebro.broker.setcash(bt_config.get('initial_cash', 100000))
    cerebro.addsizer(bt.sizers.FixedSize, stake=bt_config.get('stake', 10))

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Weeks, annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    # Logging configuration
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    cerebro.addobserver(
        bt.observers.TradeLogger,
        log_orders=True,
        log_trades=True,
        log_positions=True,
        log_data=True,
        log_indicators=True,       # Include strategy indicators in data log
        log_dir=log_dir,
        log_file_enabled=True,
        file_format='log',         # Default log (tab-separated), 'csv' also available
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
    print(f"\nRunning {config['strategy']['name']}...")
    results = cerebro.run(preload=False)
    strat = results[0]

    # Get results
    sharpe = strat.analyzers.sharpe.get_analysis()
    ret = strat.analyzers.returns.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    sharpe_ratio = sharpe.get('sharperatio', None)
    annual_return = ret.get('rnorm', 0)
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    total_trades = trades.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("\n" + "=" * 60)
    print("Data Replay Bollinger Bands Strategy Backtest Results (Weekly):")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 60)

    # **Critical**: Identical assertions from original test file
    assert strat.bar_num == 419, f"Expected bar_num=419, got {strat.bar_num}"
    assert abs(final_value - 103822.30) < 0.01, f"Expected final_value=103822.30, got {final_value}"
    assert abs(sharpe_ratio - 0.717232637621499) < 1e-6, f"Expected sharpe_ratio=0.717232637621499, got {sharpe_ratio}"
    assert abs(annual_return - 0.01893228430548803) < 1e-6, f"Expected annual_return=0.01893228430548803, got {annual_return}"
    assert abs(max_drawdown - 1.9767203338832484) < 1e-6, f"Expected max_drawdown=1.9767203338832484, got {max_drawdown}"
    assert total_trades == 2, f"Expected total_trades=2, got {total_trades}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    run()
