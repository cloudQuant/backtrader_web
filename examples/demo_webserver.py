#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Example: Using WebServer to display backtest results.

Usage:
    python examples/demo_webserver.py
"""
import sys
import os

# Add project path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtrader as bt
from backtrader_web import WebServer
from backtrader_web.data import get_stock_data


# Define strategy
class MaCrossStrategy(bt.Strategy):
    """Dual moving average crossover strategy."""
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
    # Create Cerebro engine
    cerebro = bt.Cerebro()

    # Set initial capital
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)

    # Get stock data (Ping An Bank)
    print("📥 Downloading stock data...")
    data = get_stock_data('000001', '2023-01-01', '2024-01-01')
    cerebro.adddata(data)

    # Add strategy
    cerebro.addstrategy(MaCrossStrategy, fast_period=5, slow_period=20)

    # Run backtest with WebServer
    server = WebServer(cerebro)
    server.run(port=8000)


if __name__ == '__main__':
    main()
