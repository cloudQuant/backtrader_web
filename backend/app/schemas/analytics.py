"""
回测分析数据模型
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


class PerformanceMetrics(BaseModel):
    """绩效指标"""
    initial_capital: float = Field(..., description="初始资金")
    final_assets: float = Field(..., description="最终资产")
    total_return: float = Field(..., description="总收益率")
    annualized_return: float = Field(..., description="年化收益率")
    max_drawdown: float = Field(..., description="最大回撤")
    max_drawdown_duration: int = Field(0, description="最大回撤持续天数")
    sharpe_ratio: Optional[float] = Field(None, description="夏普比率")
    sortino_ratio: Optional[float] = Field(None, description="索提诺比率")
    calmar_ratio: Optional[float] = Field(None, description="卡玛比率")
    win_rate: float = Field(0, description="胜率")
    profit_factor: float = Field(0, description="盈亏比")
    trade_count: int = Field(0, description="交易次数")
    avg_trade_return: float = Field(0, description="平均每笔收益率")
    avg_holding_days: float = Field(0, description="平均持仓天数")
    avg_win: float = Field(0, description="平均盈利")
    avg_loss: float = Field(0, description="平均亏损")
    max_consecutive_wins: int = Field(0, description="最大连续盈利次数")
    max_consecutive_losses: int = Field(0, description="最大连续亏损次数")


class EquityPoint(BaseModel):
    """资金曲线点"""
    date: str
    total_assets: float
    cash: float
    position_value: float
    benchmark: Optional[float] = None


class DrawdownPoint(BaseModel):
    """回撤点"""
    date: str
    drawdown: float
    peak: float
    trough: float


class TradeRecord(BaseModel):
    """交易记录"""
    id: int
    datetime: str
    symbol: str
    direction: str
    price: float
    size: int
    value: float
    commission: float
    pnl: Optional[float] = None
    return_pct: Optional[float] = None
    holding_days: Optional[int] = None
    cumulative_pnl: float = 0


class TradeSignal(BaseModel):
    """交易信号"""
    date: str
    type: str
    price: float
    size: int
    reason: Optional[str] = None


class KlineData(BaseModel):
    """K线数据"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    change_pct: Optional[float] = None


class MonthlyReturn(BaseModel):
    """月度收益"""
    year: int
    month: int
    return_pct: float


class OptimizationResultItem(BaseModel):
    """单个参数优化结果"""
    params: Dict[str, Any]
    total_return: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    trade_count: int
    rank: int = 0
    is_best: bool = False


class BacktestDetailResponse(BaseModel):
    """回测详情响应"""
    task_id: str
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    metrics: PerformanceMetrics
    equity_curve: List[EquityPoint]
    drawdown_curve: List[DrawdownPoint]
    trades: List[TradeRecord]
    created_at: str


class KlineWithSignalsResponse(BaseModel):
    """K线与信号响应"""
    symbol: str
    klines: List[KlineData]
    signals: List[TradeSignal]
    indicators: Dict[str, List[Optional[float]]]


class OptimizationResponse(BaseModel):
    """参数优化响应"""
    task_id: str
    parameters: List[str]
    results: List[OptimizationResultItem]
    best: Optional[OptimizationResultItem] = None


class MonthlyReturnsResponse(BaseModel):
    """月度收益响应"""
    returns: List[MonthlyReturn]
    years: List[int]
    summary: Dict[int, float]
