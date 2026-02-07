#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""策略运行脚本 - 双均线交叉策略"""

import os
import yaml
from pathlib import Path

import backtrader as bt
import pandas as pd

# 导入策略类
from strategy_dual_ma import TwoMAStrategy, ExtendPandasFeed

BASE_DIR = Path(__file__).resolve().parent


def load_config():
    """从config.yaml加载配置"""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_data_path(filename: str) -> Path:
    """查找数据文件路径"""
    search_paths = []

    # 1. Current directory
    search_paths.append(BASE_DIR / filename)

    # 2. tests directory and project root directory
    search_paths.append(BASE_DIR.parent / filename)
    repo_root = BASE_DIR.parent.parent
    search_paths.append(repo_root / filename)

    # 3. Common data directories
    search_paths.append(repo_root / "datas" / filename)
    search_paths.append(repo_root / "examples" / filename)
    search_paths.append(repo_root / "tests" / "datas" / filename)

    # 4. Directory specified by environment variable
    data_dir = os.environ.get("BACKTRADER_DATA_DIR")
    if data_dir:
        search_paths.append(Path(data_dir) / filename)

    for candidate in search_paths:
        if candidate.exists():
            return candidate

    fallback = Path(filename)
    if fallback.exists():
        return fallback

    searched = " , ".join(str(path) for path in search_paths + [fallback.resolve()])
    raise FileNotFoundError(f"Data file not found: {filename}. Tried paths: {searched}")


def load_bond_data(filename: str = "113013.csv") -> pd.DataFrame:
    """加载可转债数据"""
    df = pd.read_csv(resolve_data_path(filename))
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
    df = df.set_index("datetime")
    df = df.drop(["symbol", "bond_symbol"], axis=1)
    df = df.dropna()
    df = df.astype("float")
    return df


def run():
    """运行策略回测"""
    config = load_config()

    # 创建cerebro
    cerebro = bt.Cerebro(stdstats=True)

    # 添加策略（从config加载参数）
    params = config.get('params', {})
    cerebro.addstrategy(TwoMAStrategy, **params)




    # 加载数据
    data_config = config.get('data', {})
    symbol = data_config.get('symbol', '113013')
    print(f"Loading bond data: {symbol}.csv...")
    df = load_bond_data(f"{symbol}.csv")
    print(f"Data range: {df.index[0]} to {df.index[-1]}, total {len(df)} records")

    # 添加数据
    feed = ExtendPandasFeed(dataname=df)
    cerebro.adddata(feed, name=symbol)

    # 回测配置
    bt_config = config.get('backtest', {})
    cerebro.broker.setcommission(commission=bt_config.get('commission', 0.001))
    cerebro.broker.setcash(bt_config.get('initial_cash', 100000.0))

    # 添加分析器
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

    # 运行回测
    print("Starting backtest...")
    results = cerebro.run()
    strat = results[0]

    # 获取结果
    sharpe_ratio = strat.analyzers.my_sharpe.get_analysis().get("sharperatio")
    annual_return = strat.analyzers.my_returns.get_analysis().get("rnorm")
    max_drawdown = strat.analyzers.my_drawdown.get_analysis()["max"]["drawdown"] / 100
    trade_analysis = strat.analyzers.my_trade_analyzer.get_analysis()
    total_trades = trade_analysis.get("total", {}).get("total", 0)
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
    assert strat.bar_num == 1424, f"Expected bar_num=1424, got {strat.bar_num}"
    assert strat.buy_count == 52, f"Expected buy_count=52, got {strat.buy_count}"
    assert strat.sell_count == 51, f"Expected sell_count=51, got {strat.sell_count}"
    assert total_trades == 51, f"Expected total_trades=51, got {total_trades}"
    assert abs(sharpe_ratio - (-0.4876104524755018)) < 1e-6, f"Expected sharpe_ratio=-0.4876104524755018, got {sharpe_ratio}"
    assert abs(annual_return - (-0.02770615921670656)) < 1e-6, f"Expected annual_return=-0.02770615921670656, got {annual_return}"
    assert abs(max_drawdown - 0.23265126671771275) < 1e-6, f"Expected max_drawdown=0.23265126671771275, got {max_drawdown}"
    assert abs(final_value - 85129.07932299998) < 0.01, f"Expected final_value=85129.07932299998, got {final_value}"

    print("\nAll tests passed!")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Dual Moving Average Strategy Backtest")
    print("=" * 60)
    run()
