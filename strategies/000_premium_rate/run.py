#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略运行脚本 - 可转债溢价率双均线策略"""

import os
import yaml
from pathlib import Path

import backtrader as bt
import sys
import pandas as pd

# 导入策略类
from strategy_premium_rate import PremiumRateCrossoverStrategy, ExtendPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """查找数据文件路径"""
    search_paths = [
        BASE_DIR / filename,
        BASE_DIR.parent / filename,
        BASE_DIR.parent / "datas" / filename,
        BASE_DIR.parent.parent / "datas" / filename,  # 项目根目录下的datas
    ]

    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(f"Data file not found: {filename}")


def load_bond_data(csv_file: str) -> pd.DataFrame:
    """加载可转债数据"""
    df = pd.read_csv(csv_file)
    df.columns = ['BOND_CODE', 'BOND_SYMBOL', 'datetime', 'open', 'high', 'low',
                  'close', 'volume', 'pure_bond_value', 'convert_value',
                  'pure_bond_premium_rate', 'convert_premium_rate']

    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')
    df = df.drop(['BOND_CODE', 'BOND_SYMBOL'], axis=1)
    df = df.dropna()
    df = df.astype(float)

    return df


def run():
    """运行策略回测"""
    config = load_config()

    # 创建cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # 添加策略（从config加载参数）
    params = config.get('params', {})
    cerebro.addstrategy(PremiumRateCrossoverStrategy, **params)

    


    # 加载数据
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', '113013')
    print(f"Loading convertible bond data: {symbol}.csv...")
    data_path = resolve_data_path(f"{symbol}.csv")
    df = load_bond_data(str(data_path))
    print(f"Data range: {df.index[0]} to {df.index[-1]}, total {len(df)} records")

    feed = ExtendPandasFeed(dataname=df)
    cerebro.adddata(feed, name=symbol)

    # 回测配置
    bt_config = config.get('backtest', {})
    cerebro.broker.setcash(bt_config.get('initial_cash', 100000))
    cerebro.broker.setcommission(commission=bt_config.get('commission', 0.0003))

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe',
                        annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
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

    # 运行回测
    print(f"\nRunning {config['strategy']['name']}...")
    results = cerebro.run()
    strat = results[0]

    # 获取结果
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio')
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm100')
    max_drawdown = strat.analyzers.drawdown.get_analysis()['max']['drawdown']
    trade_analysis = strat.analyzers.trades.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # 打印结果
    print("\n" + "=" * 60)
    print("Backtest Results:")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  total_trades: {total_trades}")
    print(f"  final_value: {final_value}")
    print("=" * 60)

    # **关键**：与原test文件完全相同的断言
    assert strat.bar_num == 1384, f"Expected bar_num=1384, got {strat.bar_num}"
    assert abs(final_value - 104275.87) < 0.01, \
        f"Expected final_value=104275.87, got {final_value}"
    assert sharpe_ratio is not None, "Sharpe ratio should not be None"
    assert abs(sharpe_ratio - 0.11457095300469224) < 1e-6, \
        f"Expected sharpe_ratio=0.11457095300469224, got {sharpe_ratio}"
    assert abs(annual_return - 0.733367887488441) < 1e-6, \
        f"Expected annual_return=0.733367887488441, got {annual_return}"
    assert abs(max_drawdown - 17.413029757464745) < 1e-6, \
        f"Expected max_drawdown=17.413, got {max_drawdown}"
    assert total_trades == 21, f"Expected total_trades=21, got {total_trades}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    run()
