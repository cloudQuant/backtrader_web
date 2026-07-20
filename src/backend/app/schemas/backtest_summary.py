"""Compact, contract-stable backtest first-screen response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.backtest import TaskStatus


class CanonicalMetrics(BaseModel):
    """The canonical metrics envelope shared by result, summary, and research paths."""

    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_loss_ratio: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_holding_bars: float = 0.0


class BacktestSummaryResponse(BaseModel):
    """Small first paint response; intentionally excludes curves and trades."""

    task_id: str
    strategy_id: str
    symbol: str
    status: TaskStatus
    metrics: CanonicalMetrics = Field(default_factory=CanonicalMetrics)
    data_precheck: dict[str, Any] = Field(default_factory=dict)
    robustness: dict[str, Any] = Field(default_factory=dict)
