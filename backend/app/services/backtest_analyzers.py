"""
Backtrader 分析器增强
提供详细的回测数据采集
"""
import backtrader as bt
from collections import OrderedDict
from datetime import datetime


class DetailedTradeAnalyzer(bt.Analyzer):
    """详细交易分析器 - 记录每笔交易的详细信息"""
    
    def __init__(self):
        self.trades = []
        self.trade_count = 0
    
    def notify_trade(self, trade):
        if trade.isclosed:
            self.trade_count += 1
            self.trades.append({
                'id': self.trade_count,
                'ref': trade.ref,
                'datetime': self.datas[0].datetime.datetime(0).strftime('%Y-%m-%d %H:%M:%S'),
                'symbol': trade.data._name or 'unknown',
                'direction': 'buy' if trade.history[0].event.size > 0 else 'sell',
                'size': abs(trade.size),
                'price': trade.price,
                'value': abs(trade.value),
                'commission': trade.commission,
                'pnl': trade.pnl,
                'pnlcomm': trade.pnlcomm,
                'barlen': trade.barlen,
            })
    
    def get_analysis(self):
        return {'trades': self.trades}


class EquityCurveAnalyzer(bt.Analyzer):
    """资金曲线分析器 - 记录每日资金变化"""
    
    def __init__(self):
        self.equity_curve = []
        self._last_value = None
    
    def start(self):
        self._last_value = self.strategy.broker.getvalue()
    
    def next(self):
        dt = self.datas[0].datetime.datetime(0)
        total = self.strategy.broker.getvalue()
        cash = self.strategy.broker.getcash()
        position_value = total - cash
        
        self.equity_curve.append({
            'date': dt.strftime('%Y-%m-%d'),
            'total_assets': round(total, 2),
            'cash': round(cash, 2),
            'position_value': round(position_value, 2),
        })
    
    def get_analysis(self):
        return {'equity_curve': self.equity_curve}


class TradeSignalAnalyzer(bt.Analyzer):
    """交易信号分析器 - 记录买卖信号"""
    
    def __init__(self):
        self.signals = []
    
    def notify_order(self, order):
        if order.status == order.Completed:
            signal_type = 'buy' if order.isbuy() else 'sell'
            dt = self.datas[0].datetime.datetime(0)
            self.signals.append({
                'date': dt.strftime('%Y-%m-%d'),
                'type': signal_type,
                'price': round(order.executed.price, 4),
                'size': abs(order.executed.size),
            })
    
    def get_analysis(self):
        return {'signals': self.signals}


class MonthlyReturnsAnalyzer(bt.Analyzer):
    """月度收益分析器"""
    
    def __init__(self):
        self.monthly_returns = {}
        self.month_start_value = None
        self.current_month = None
    
    def start(self):
        self.month_start_value = self.strategy.broker.getvalue()
    
    def next(self):
        dt = self.datas[0].datetime.datetime(0)
        month_key = (dt.year, dt.month)
        current_value = self.strategy.broker.getvalue()
        
        if self.current_month != month_key:
            # 记录上个月的收益
            if self.current_month and self.month_start_value:
                ret = (current_value - self.month_start_value) / self.month_start_value
                self.monthly_returns[self.current_month] = round(ret, 6)
            
            # 开始新月份
            self.month_start_value = current_value
            self.current_month = month_key
    
    def stop(self):
        # 记录最后一个月的收益
        if self.current_month and self.month_start_value:
            current_value = self.strategy.broker.getvalue()
            ret = (current_value - self.month_start_value) / self.month_start_value
            self.monthly_returns[self.current_month] = round(ret, 6)
    
    def get_analysis(self):
        return {'monthly_returns': self.monthly_returns}


class DrawdownAnalyzer(bt.Analyzer):
    """回撤分析器 - 记录每日回撤"""
    
    def __init__(self):
        self.drawdown_curve = []
        self.peak = 0
    
    def start(self):
        self.peak = self.strategy.broker.getvalue()
    
    def next(self):
        dt = self.datas[0].datetime.datetime(0)
        current = self.strategy.broker.getvalue()
        
        if current > self.peak:
            self.peak = current
        
        dd = (current - self.peak) / self.peak if self.peak > 0 else 0
        
        self.drawdown_curve.append({
            'date': dt.strftime('%Y-%m-%d'),
            'drawdown': round(dd, 6),
            'peak': round(self.peak, 2),
            'trough': round(current, 2),
        })
    
    def get_analysis(self):
        return {'drawdown_curve': self.drawdown_curve}


def get_all_analyzers():
    """获取所有自定义分析器"""
    return {
        'detailed_trades': DetailedTradeAnalyzer,
        'equity_curve': EquityCurveAnalyzer,
        'trade_signals': TradeSignalAnalyzer,
        'monthly_returns': MonthlyReturnsAnalyzer,
        'drawdown': DrawdownAnalyzer,
    }
