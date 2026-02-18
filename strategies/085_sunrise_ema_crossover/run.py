#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Strategy Runner - Sunrise Volatility ExpansionStrategy"""

import os
import yaml
import datetime
from pathlib import Path

import backtrader as bt

# Import strategy class
from strategy_sunrise_ema_crossover import SunriseVolatilityExpansionStrategy

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
    cerebro.addstrategy(SunriseVolatilityExpansionStrategy, **params)




    # Load data
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', 'XAUUSD')
    print(f"Loading data: {symbol}...")
    data_path = resolve_data_path("XAUUSD_5m_5Yea.csv")
    
    # XAUUSD CSV format: Date,Time,Open,High,Low,Close,Volume
    # Date format: 20200821, Time format: 00:00:00
    data = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y%m%d',
        tmformat='%H:%M:%S',
        datetime=0, time=1, open=2, high=3, low=4, close=5, volume=6, openinterest=-1,
        fromdate=datetime.datetime(2024, 6, 1),
        todate=datetime.datetime(2025, 6, 30),
    )
    cerebro.adddata(data)
    print(f"Data loaded from {datetime.datetime(2024, 6, 1)} to {datetime.datetime(2025, 6, 30)}")

    # Backtest configuration
    bt_config = config.get('backtest', {})
    cerebro.broker.setcash(bt_config.get('initial_cash', 100000))
    cerebro.broker.setcommission(commission=bt_config.get('commission', 0.001))

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
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
    results = cerebro.run()
    strat = results[0]

    # Get results
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
    final_value = cerebro.broker.getvalue()

    # Print results
    print("\n" + "=" * 60)
    print("Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value}")
    print("=" * 60)

    # **Critical**: Identical assertions from original test file
    # final_value tolerance: 0.01, other metrics tolerance: 1e-6
    assert strat.bar_num == 76055, f"Expected bar_num=76055, got {strat.bar_num}"
    assert abs(final_value - 99780.54) < 0.01, f"Expected final_value=99780.54, got {final_value}"
    assert abs(sharpe_ratio - (-0.058262402599915615)) < 1e-6, f"Expected sharpe_ratio=-0.058262402599915615, got {sharpe_ratio}"
    assert abs(annual_return - (-0.0016463951849173732)) < 1e-6, f"Expected annual_return=-0.0016463951849173732, got {annual_return}"
    assert abs(max_drawdown - 2.169140984136156) < 1e-6, f"Expected max_drawdown=2.169140984136156, got {max_drawdown}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    run()
