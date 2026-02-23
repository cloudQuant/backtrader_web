"""
Backtest analytics schemas.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PerformanceMetrics(BaseModel):
    """Performance metrics schema."""
    initial_capital: float = Field(..., description="Initial capital")
    final_assets: float = Field(..., description="Final assets")
    total_return: float = Field(..., description="Total return")
    annualized_return: float = Field(..., description="Annualized return")
    max_drawdown: float = Field(..., description="Maximum drawdown")
    max_drawdown_duration: int = Field(0, description="Maximum drawdown duration (days)")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    sortino_ratio: Optional[float] = Field(None, description="Sortino ratio")
    calmar_ratio: Optional[float] = Field(None, description="Calmar ratio")
    win_rate: float = Field(0, description="Win rate")
    profit_factor: float = Field(0, description="Profit factor")
    trade_count: int = Field(0, description="Trade count")
    avg_trade_return: float = Field(0, description="Average return per trade")
    avg_holding_days: float = Field(0, description="Average holding days")
    avg_win: float = Field(0, description="Average win")
    avg_loss: float = Field(0, description="Average loss")
    max_consecutive_wins: int = Field(0, description="Maximum consecutive wins")
    max_consecutive_losses: int = Field(0, description="Maximum consecutive losses")


class EquityPoint(BaseModel):
    """Equity curve point schema."""
    date: str
    total_assets: float
    cash: float
    position_value: float
    benchmark: Optional[float] = None


class DrawdownPoint(BaseModel):
    """Drawdown point schema."""
    date: str
    drawdown: float
    peak: float
    trough: float


class TradeRecord(BaseModel):
    """Trade record schema."""
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
    """Trade signal schema."""
    date: str
    type: str
    price: float
    size: Optional[float] = 0
    reason: Optional[str] = None


class KlineData(BaseModel):
    """K-line data schema."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    change_pct: Optional[float] = None


class MonthlyReturn(BaseModel):
    """Monthly return schema."""
    year: int
    month: int
    return_pct: float


class OptimizationResultItem(BaseModel):
    """Single parameter optimization result schema."""
    params: Dict[str, Any]
    total_return: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    trade_count: int
    rank: int = 0
    is_best: bool = False


class BacktestDetailResponse(BaseModel):
    """Backtest detail response schema."""
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
    """K-line with signals response schema."""
    symbol: str
    klines: List[KlineData]
    signals: List[TradeSignal]
    indicators: Dict[str, List[Optional[float]]]


class OptimizationResponse(BaseModel):
    """Parameter optimization response schema."""
    task_id: str
    parameters: List[str]
    results: List[OptimizationResultItem]
    best: Optional[OptimizationResultItem] = None


class MonthlyReturnsResponse(BaseModel):
    """Monthly returns response schema."""
    returns: List[MonthlyReturn]
    years: List[int]
    summary: Dict[int, float]
