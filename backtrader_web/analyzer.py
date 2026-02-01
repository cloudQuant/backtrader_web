"""
回测结果分析器 - 解析backtrader回测结果
"""
import backtrader as bt
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
import json


@dataclass
class TradeRecord:
    """交易记录"""
    datetime: str
    direction: str  # buy/sell
    price: float
    size: int
    value: float
    pnl: float = 0.0
    pnl_percent: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    # 基本信息
    strategy_name: str = ""
    symbol: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 100000.0
    final_value: float = 100000.0
    
    # 收益指标
    total_return: float = 0.0
    annual_return: float = 0.0
    
    # 风险指标
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    
    # 交易统计
    total_trades: int = 0
    profitable_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # 曲线数据
    equity_curve: List[float] = field(default_factory=list)
    equity_dates: List[str] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)
    
    # 交易记录
    trades: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class EquityObserver(bt.Observer):
    """资金曲线观察器"""
    lines = ('value',)
    plotinfo = dict(plot=True, subplot=True)
    
    def next(self):
        self.lines.value[0] = self._owner.broker.getvalue()


class BacktestAnalyzer:
    """回测分析器"""
    
    def __init__(self, cerebro: bt.Cerebro):
        self.cerebro = cerebro
        self.results = None
        self._setup_analyzers()
    
    def _setup_analyzers(self):
        """添加分析器"""
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02)
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self.cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return', timeframe=bt.TimeFrame.Days)
        
        # 添加资金曲线观察器
        self.cerebro.addobserver(EquityObserver)
    
    def run(self) -> BacktestResult:
        """运行回测并返回结果"""
        initial_cash = self.cerebro.broker.getvalue()
        self.results = self.cerebro.run()
        
        return self._parse_results(initial_cash)
    
    def _parse_results(self, initial_cash: float) -> BacktestResult:
        """解析回测结果"""
        strat = self.results[0]
        final_value = self.cerebro.broker.getvalue()
        
        # 基本收益
        total_return = ((final_value - initial_cash) / initial_cash) * 100
        
        # 获取数据时间范围
        data = strat.data
        start_date = bt.num2date(data.datetime.array[0]).strftime("%Y-%m-%d")
        end_date = bt.num2date(data.datetime.array[-1]).strftime("%Y-%m-%d")
        
        # 计算年化收益
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end_dt - start_dt).days
        years = total_days / 365.0 if total_days > 0 else 1
        annual_return = (((final_value / initial_cash) ** (1 / years)) - 1) * 100 if years > 0 else 0
        
        # 夏普比率
        sharpe_ratio = 0.0
        try:
            sharpe_analysis = strat.analyzers.sharpe.get_analysis()
            sharpe_ratio = sharpe_analysis.get('sharperatio') or 0.0
        except Exception:
            pass
        
        # 最大回撤
        max_drawdown = 0.0
        try:
            drawdown_analysis = strat.analyzers.drawdown.get_analysis()
            max_drawdown = drawdown_analysis.get('max', {}).get('drawdown', 0.0) or 0.0
        except Exception:
            pass
        
        # 交易统计
        total_trades = 0
        profitable_trades = 0
        losing_trades = 0
        try:
            trade_analysis = strat.analyzers.trades.get_analysis()
            total_trades = trade_analysis.get('total', {}).get('total', 0) or 0
            profitable_trades = trade_analysis.get('won', {}).get('total', 0) or 0
            losing_trades = trade_analysis.get('lost', {}).get('total', 0) or 0
        except Exception:
            pass
        
        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 资金曲线
        equity_curve, equity_dates, drawdown_curve = self._get_equity_curve(strat, initial_cash)
        
        # 策略名称
        strategy_name = strat.__class__.__name__
        
        # 标的代码
        symbol = getattr(data, '_name', '') or getattr(data._dataname, 'name', 'Unknown') if hasattr(data, '_dataname') else 'Unknown'
        
        return BacktestResult(
            strategy_name=strategy_name,
            symbol=str(symbol),
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            final_value=round(final_value, 2),
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            sharpe_ratio=round(sharpe_ratio, 2) if sharpe_ratio else 0.0,
            max_drawdown=round(max_drawdown, 2),
            total_trades=total_trades,
            profitable_trades=profitable_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 1),
            equity_curve=equity_curve,
            equity_dates=equity_dates,
            drawdown_curve=drawdown_curve,
            trades=[],
        )
    
    def _get_equity_curve(self, strat, initial_cash: float):
        """获取资金曲线"""
        equity_curve = []
        equity_dates = []
        drawdown_curve = []
        
        try:
            # 从TimeReturn分析器获取每日收益
            time_return = strat.analyzers.time_return.get_analysis()
            
            current_value = initial_cash
            peak = initial_cash
            
            for dt, ret in sorted(time_return.items()):
                current_value = current_value * (1 + (ret or 0))
                equity_curve.append(round(current_value, 2))
                
                if hasattr(dt, 'strftime'):
                    equity_dates.append(dt.strftime("%Y-%m-%d"))
                else:
                    equity_dates.append(str(dt))
                
                if current_value > peak:
                    peak = current_value
                dd = ((peak - current_value) / peak) * 100 if peak > 0 else 0
                drawdown_curve.append(round(dd, 2))
                
        except Exception as e:
            # 简化处理
            data = strat.data
            equity_curve = [initial_cash, self.cerebro.broker.getvalue()]
            equity_dates = [
                bt.num2date(data.datetime.array[0]).strftime("%Y-%m-%d"),
                bt.num2date(data.datetime.array[-1]).strftime("%Y-%m-%d")
            ]
            drawdown_curve = [0, 0]
        
        return equity_curve, equity_dates, drawdown_curve
