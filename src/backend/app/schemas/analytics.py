"""
Backtest analytics schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "initial_capital": 100000.0,
                "final_assets": 115000.0,
                "total_return": 0.15,
                "annualized_return": 0.15,
                "max_drawdown": -0.08,
                "max_drawdown_duration": 15,
                "sharpe_ratio": 1.5,
                "sortino_ratio": 2.0,
                "calmar_ratio": 1.8,
                "win_rate": 0.6,
                "profit_factor": 1.8,
                "trade_count": 50,
                "avg_trade_return": 0.003,
                "avg_holding_days": 5.5,
                "avg_win": 500.0,
                "avg_loss": -300.0,
                "max_consecutive_wins": 8,
                "max_consecutive_losses": 3,
            }
        }
    )


class EquityPoint(BaseModel):
    """Equity curve point schema."""

    date: str
    total_assets: float
    cash: float
    position_value: float
    benchmark: Optional[float] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2023-01-01",
                "total_assets": 100000.0,
                "cash": 50000.0,
                "position_value": 50000.0,
                "benchmark": 100000.0,
            }
        }
    )


class DrawdownPoint(BaseModel):
    """Drawdown point schema."""

    date: str
    drawdown: float
    peak: float
    trough: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2023-02-15",
                "drawdown": -0.05,
                "peak": 105000.0,
                "trough": 99750.0,
            }
        }
    )


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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "datetime": "2023-01-15 09:30:00",
                "symbol": "000001.SZ",
                "direction": "buy",
                "price": 10.5,
                "size": 1000,
                "value": 10500.0,
                "commission": 10.5,
                "pnl": 500.0,
                "return_pct": 0.048,
                "holding_days": 5,
                "cumulative_pnl": 500.0,
            }
        }
    )


class TradeSignal(BaseModel):
    """Trade signal schema."""

    date: str
    type: str
    price: float
    size: Optional[float] = 0
    reason: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2023-01-15",
                "type": "buy",
                "price": 10.5,
                "size": 1000,
                "reason": "MA crossover",
            }
        }
    )


class KlineData(BaseModel):
    """K-line data schema."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    change_pct: Optional[float] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2023-01-01",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.3,
                "volume": 1000000,
                "change_pct": 0.03,
            }
        }
    )


class MonthlyReturn(BaseModel):
    """Monthly return schema."""

    year: int
    month: int
    return_pct: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2023,
                "month": 1,
                "return_pct": 0.05,
            }
        }
    )


class OptimizationResultItem(BaseModel):
    """Single parameter optimization result schema."""

    params: Dict[str, Any]
    total_return: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    trade_count: int
    rank: int = 0
    is_best: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "params": {"fast_period": 5, "slow_period": 20},
                "total_return": 0.2,
                "max_drawdown": -0.1,
                "sharpe_ratio": 1.8,
                "trade_count": 45,
                "rank": 1,
                "is_best": True,
            }
        }
    )


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
