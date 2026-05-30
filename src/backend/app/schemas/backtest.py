"""
Backtest schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Any

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
    runtime_dir: str | None = Field(None, description="Optional unit runtime directory")
    symbol: str = Field(..., description="Stock symbol")
    start_date: datetime = Field(..., description="Start date")
    end_date: datetime = Field(..., description="End date")
    initial_cash: float = Field(100000.0, description="Initial cash")
    commission: float = Field(0.001, description="Commission rate")
    timeframe: str = Field("1d", description="K-line timeframe e.g. 1d, 1h, 5m")
    timeframe_n: int = Field(1, ge=1, description="Timeframe multiplier")
    bar_count: int | None = Field(None, description="Number of bars to load (None = all)")
    params: dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "strategy_id": "strat_7f8e9d0c1b2a",
                    "symbol": "000001.SZ",
                    "start_date": "2023-01-01T00:00:00",
                    "end_date": "2024-01-01T00:00:00",
                    "initial_cash": 100000,
                    "commission": 0.001,
                    "timeframe": "1d",
                    "timeframe_n": 1,
                    "params": {"fast_period": 5, "slow_period": 20},
                },
                {
                    "strategy_id": "strat_3c4d5e6f7a8b",
                    "symbol": "600519.SH",
                    "start_date": "2022-06-01T00:00:00",
                    "end_date": "2023-12-31T00:00:00",
                    "initial_cash": 500000,
                    "commission": 0.0003,
                    "timeframe": "1h",
                    "timeframe_n": 4,
                    "params": {"period": 20, "devfactor": 2.0},
                },
            ]
        }
    )


class BacktestResponse(BaseModel):
    """Backtest task response schema."""

    task_id: str = Field(..., description="Task ID", examples=["task_9a8b7c6d5e4f"])
    status: TaskStatus = Field(..., description="Task status")
    message: str | None = Field(
        None,
        description="Status message",
        examples=["Backtest task submitted, queuing / 回测任务已提交，正在排队中"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "task_id": "task_9a8b7c6d5e4f",
                    "status": "pending",
                    "message": "Backtest task submitted, queuing / 回测任务已提交，正在排队中",
                }
            ]
        }
    )


class TradeRecord(BaseModel):
    """Trade record schema."""

    datetime: str | None = None
    date: str | None = None
    dtopen: str | None = None
    dtclose: str | None = None
    direction: str | None = None
    type: str | None = None
    price: float = 0
    size: float = 0
    value: float = 0
    commission: float = 0
    pnl: float | None = None
    pnlcomm: float | None = None
    barlen: int | None = None


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
    equity_curve: list[float] = Field(default_factory=list, description="Equity curve")
    equity_dates: list[str] = Field(default_factory=list, description="Date sequence")
    drawdown_curve: list[float] = Field(default_factory=list, description="Drawdown curve")

    # Trade records
    trades: list[TradeRecord] = Field(default_factory=list, description="Trade records")

    # Meta info
    created_at: datetime
    error_message: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "task_id": "task_9a8b7c6d5e4f",
                    "strategy_id": "strat_7f8e9d0c1b2a",
                    "symbol": "000001.SZ",
                    "start_date": "2023-01-01T00:00:00Z",
                    "end_date": "2024-01-01T00:00:00Z",
                    "status": "completed",
                    "total_return": 23.56,
                    "annual_return": 18.42,
                    "sharpe_ratio": 1.35,
                    "max_drawdown": -12.8,
                    "win_rate": 58.3,
                    "metrics_source": "quantstats",
                    "total_trades": 42,
                    "profitable_trades": 24,
                    "losing_trades": 18,
                    "equity_curve": [100000, 101200, 99800, 103500, 123560],
                    "equity_dates": [
                        "2023-01-03",
                        "2023-02-01",
                        "2023-03-01",
                        "2023-06-01",
                        "2024-01-01",
                    ],
                    "drawdown_curve": [0, 0, -1.38, 0, 0],
                    "trades": [
                        {
                            "dtopen": "2023-01-15",
                            "dtclose": "2023-02-20",
                            "direction": "long",
                            "price": 13.25,
                            "size": 1000,
                            "pnl": 1200.0,
                            "pnlcomm": 1173.5,
                            "barlen": 25,
                        }
                    ],
                    "created_at": "2025-01-15T10:30:00Z",
                    "error_message": None,
                }
            ]
        },
    )


class BacktestListResponse(BaseModel):
    """Backtest list response schema."""

    total: int
    items: list[BacktestResult]
