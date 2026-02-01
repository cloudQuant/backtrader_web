"""
Backtrader Web - 量化回测可视化框架

用法:
    from backtrader_web import WebServer
    import backtrader as bt

    cerebro = bt.Cerebro()
    # ... 配置策略和数据
    
    server = WebServer(cerebro)
    server.run(port=8000)
"""

from .server import WebServer
from .analyzer import BacktestAnalyzer

__version__ = "0.1.0"
__all__ = ["WebServer", "BacktestAnalyzer"]
