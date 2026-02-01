#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
示例: 使用WebServer展示回测结果

用法:
    python examples/demo_webserver.py
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
from backtrader_web import WebServer
from backtrader_web.data import get_stock_data


# 定义策略
class MaCrossStrategy(bt.Strategy):
    """双均线交叉策略"""
    params = (
        ('fast_period', 5),
        ('slow_period', 20),
    )
    
    def __init__(self):
        self.fast_ma = bt.indicators.SMA(period=self.params.fast_period)
        self.slow_ma = bt.indicators.SMA(period=self.params.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
    
    def next(self):
        if not self.position:
            if self.crossover > 0:
                self.buy()
        elif self.crossover < 0:
            self.sell()


def main():
    # 创建Cerebro引擎
    cerebro = bt.Cerebro()
    
    # 设置初始资金
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)
    
    # 获取股票数据 (平安银行)
    print("📥 下载股票数据...")
    data = get_stock_data('000001', '2023-01-01', '2024-01-01')
    cerebro.adddata(data)
    
    # 添加策略
    cerebro.addstrategy(MaCrossStrategy, fast_period=5, slow_period=20)
    
    # 使用WebServer运行回测并展示结果
    server = WebServer(cerebro)
    server.run(port=8000)


if __name__ == '__main__':
    main()
