"""
Backtest schemas.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Task status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestRequest(BaseModel):
    """Backtest request schema."""
    strategy_id: str = Field(..., description="Strategy ID")
    symbol: str = Field(..., description="Stock symbol")
    start_date: datetime = Field(..., description="Start date")
    end_date: datetime = Field(..., description="End date")
    initial_cash: float = Field(100000.0, description="Initial cash")
    commission: float = Field(0.001, description="Commission rate")
    params: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00",
                "end_date": "2024-01-01T00:00:00",
                "initial_cash": 100000,
                "commission": 0.001,
                "params": {"fast_period": 5, "slow_period": 20},
            }
        }
    )


class BacktestResponse(BaseModel):
    """Backtest task response schema."""
    task_id: str = Field(..., description="Task ID")
    status: TaskStatus = Field(..., description="Task status")
    message: Optional[str] = Field(None, description="Status message")


class TradeRecord(BaseModel):
    """Trade record schema."""
    datetime: Optional[str] = None
    date: Optional[str] = None
    dtopen: Optional[str] = None
    dtclose: Optional[str] = None
    direction: Optional[str] = None
    type: Optional[str] = None
    price: float = 0
    size: float = 0
    value: float = 0
    commission: float = 0
    pnl: Optional[float] = None
    pnlcomm: Optional[float] = None
    barlen: Optional[int] = None


class BacktestResult(BaseModel):
    """Backtest result schema."""
    task_id: str
    strategy_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    status: TaskStatus

    # Performance metrics
    total_return: float = Field(0, description="Total return (%)")
    annual_return: float = Field(0, description="Annualized return (%)")
    sharpe_ratio: float = Field(0, description="Sharpe ratio")
    max_drawdown: float = Field(0, description="Maximum drawdown (%)")
    win_rate: float = Field(0, description="Win rate (%)")
    metrics_source: str = Field("manual", description="Source of metric calculations")

    # Trade statistics
    total_trades: int = Field(0, description="Total trades")
    profitable_trades: int = Field(0, description="Profitable trades")
    losing_trades: int = Field(0, description="Losing trades")

    # Equity curve data
    equity_curve: List[float] = Field(default_factory=list, description="Equity curve")
    equity_dates: List[str] = Field(default_factory=list, description="Date sequence")
    drawdown_curve: List[float] = Field(default_factory=list, description="Drawdown curve")

    # Trade records
    trades: List[TradeRecord] = Field(default_factory=list, description="Trade records")

    # Meta info
    created_at: datetime
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BacktestListResponse(BaseModel):
    """Backtest list response schema."""
    total: int
    items: List[BacktestResult]
