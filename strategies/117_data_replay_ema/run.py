#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略运行脚本 - 数据重放EMA双均线策略"""

import os
import yaml
from pathlib import Path

import backtrader as bt

# 导入策略类
from strategy_data_replay_ema import ReplayEMAStrategy

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
    cerebro.addstrategy(ReplayEMAStrategy, **params)
    # 加载数据
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', '2005-2006-day-001')
    print(f"Loading data: {symbol}.txt...")
    data_path = resolve_data_path(f"{symbol}.txt")
    data = bt.feeds.BacktraderCSVData(dataname=str(data_path))

    # 使用replay功能将日线数据重放为周线数据
    cerebro.replaydata(
        data,
        timeframe=bt.TimeFrame.Weeks,
        compression=1
    )

    # 回测配置
    bt_config = config.get('backtest', {})
    cerebro.broker.setcash(bt_config.get('initial_cash', 100000))
    cerebro.addsizer(bt.sizers.FixedSize, stake=bt_config.get('stake', 10))

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Weeks, annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    # 日志配置
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')

    # 运行回测
    print(f"\nRunning {config['strategy']['name']}...")
    results = cerebro.run(preload=False)
    strat = results[0]

    # 获取结果
    sharpe = strat.analyzers.sharpe.get_analysis()
    ret = strat.analyzers.returns.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    sharpe_ratio = sharpe.get('sharperatio', None)
    annual_return = ret.get('rnorm', 0)
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0)
    total_trades = trades.get('total', {}).get('total', 0)
    final_value = cerebro.broker.getvalue()

    # 打印结果
    print("\n" + "=" * 60)
    print("Data Replay EMA Strategy Backtest Results (Weekly):")
    print(f"  bar_num: {strat.bar_num}")
    print(f"  buy_count: {strat.buy_count}")
    print(f"  sell_count: {strat.sell_count}")
    print(f"  total_trades: {total_trades}")
    print(f"  sharpe_ratio: {sharpe_ratio}")
    print(f"  annual_return: {annual_return}")
    print(f"  max_drawdown: {max_drawdown}")
    print(f"  final_value: {final_value:.2f}")
    print("=" * 60)

    # **关键**：与原test文件完全相同的断言
    assert strat.bar_num == 384, f"Expected bar_num=384, got {strat.bar_num}"
    assert abs(final_value - 104553.50) < 0.01, f"Expected final_value=104553.50, got {final_value}"
    assert abs(sharpe_ratio - 0.8871126960270267) < 1e-6, f"Expected sharpe_ratio=0.8871126960270267, got {sharpe_ratio}"
    assert abs(annual_return - 0.022514058583059444) < 1e-6, f"Expected annual_return=0.022514058583059444, got {annual_return}"
    assert abs(max_drawdown - 1.7853002550428876) < 1e-6, f"Expected max_drawdown=1.7853002550428876, got {max_drawdown}"
    assert total_trades == 9, f"Expected total_trades=9, got {total_trades}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    run()
