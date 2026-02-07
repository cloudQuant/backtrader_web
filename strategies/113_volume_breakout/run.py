#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略运行脚本 - 成交量突破策略"""

import os
import datetime
import yaml
from pathlib import Path

import backtrader as bt

# 导入策略类
from strategy_volume_breakout import VolumeBreakoutStrategy

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
    """运行策略回测"""
    config = load_config()

    # 创建cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # 添加策略（从config加载参数）
    params = config.get('params', {})
    cerebro.addstrategy(VolumeBreakoutStrategy, **params)




    # 加载数据
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', 'ORCL')
    print(f"Loading stock data: {symbol}...")
    data_path = resolve_data_path("orcl-1995-2014.txt")
    data = bt.feeds.GenericCSVData(
        dataname=str(data_path),
        dtformat='%Y-%m-%d',
        datetime=0, open=1, high=2, low=3, close=4, volume=5, openinterest=-1,
        fromdate=datetime.datetime(2010, 1, 1),
        todate=datetime.datetime(2014, 12, 31),
    )
    cerebro.adddata(data)
    print(f"Data range: 2010-01-01 to 2014-12-31")

    # 回测配置
    bt_config = config.get('backtest', {})
    cerebro.broker.setcash(bt_config.get('initial_cash', 100000))
    cerebro.broker.setcommission(commission=bt_config.get('commission', 0.001))

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
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
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
    annual_return = strat.analyzers.returns.get_analysis().get('rnorm', 0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
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
    print(f"  final_value: {final_value:.2f}")
    print("=" * 60)

    # **关键**：与原test文件完全相同的断言
    assert strat.bar_num == 1238, f"Expected bar_num=1238, got {strat.bar_num}"
    assert abs(final_value - 99987.80) < 0.01, f"Expected final_value=99987.80, got {final_value}"
    assert abs(sharpe_ratio - (-0.1545232366102227)) < 1e-6, f"Expected sharpe_ratio=-0.1545232366102227, got {sharpe_ratio}"
    assert abs(annual_return - (-2.4463477104822622e-05)) < 1e-6, f"Expected annual_return=-2.4463477104822622e-05, got {annual_return}"
    assert abs(max_drawdown - 0.05240649826015478) < 1e-6, f"Expected max_drawdown=0.05240649826015478, got {max_drawdown}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    run()
