"""
Backtest comparison schemas.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComparisonCreate(BaseModel):
    """Comparison creation request schema."""

    name: str = Field(..., min_length=1, max_length=200, description="Comparison name")
    description: str | None = Field(None, description="Comparison description")
    type: str = Field("metrics", description="Comparison type: metrics, equity, trades, drawdown")
    backtest_task_ids: list[str] = Field(
        ..., min_length=2, description="Backtest task ID list (at least 2)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "MA Strategy Comparison",
                "description": "Compare 5/20 MA vs 10/30 MA strategies",
                "type": "metrics",
                "backtest_task_ids": ["task_001", "task_002"],
            }
        }
    )


class ComparisonUpdate(BaseModel):
    """Comparison update request schema."""

    name: str | None = Field(None, min_length=1, max_length=200, description="Comparison name")
    description: str | None = Field(None, description="Comparison description")
    backtest_task_ids: list[str] | None = Field(None, description="Backtest task ID list")
    is_public: bool | None = Field(None, description="Whether public")


class ComparisonResponse(BaseModel):
    """Comparison response schema."""

    id: str = Field(..., description="Comparison ID")
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="Comparison name")
    description: str | None = Field(None, description="Comparison description")
    type: str = Field(..., description="Comparison type")
    backtest_task_ids: list[str] = Field(..., description="Backtest task ID list")
    comparison_data: dict[str, Any] = Field(..., description="Comparison results")
    is_favorite: bool = Field(..., description="Whether favorited")
    is_public: bool = Field(..., description="Whether public")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")

    model_config = ConfigDict(from_attributes=True)


class ComparisonListResponse(BaseModel):
    """Comparison list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    items: list[ComparisonResponse] = Field(..., description="Comparison list")


class MetricsComparison(BaseModel):
    """Metrics comparison schema."""

    metrics_comparison: dict[str, dict[str, float]] = Field(
        ..., description="Metrics comparison data"
    )
    best_metrics: dict[str, dict[str, Any]] = Field(..., description="Best metrics")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "metrics_comparison": {
                    "task_001": {
                        "total_return": 0.15,
                        "sharpe_ratio": 1.5,
                        "max_drawdown": -0.08,
                    },
                    "task_002": {
                        "total_return": 0.18,
                        "sharpe_ratio": 1.6,
                        "max_drawdown": -0.10,
                    },
                },
                "best_metrics": {
                    "total_return": {"task_id": "task_002", "value": 0.18},
                    "sharpe_ratio": {"task_id": "task_002", "value": 1.6},
                    "max_drawdown": {"task_id": "task_001", "value": -0.08},
                },
            }
        }
    )


class EquityComparison(BaseModel):
    """Equity curve comparison schema."""

    equity_comparison: dict[str, Any] = Field(..., description="Equity curve comparison data")
    dates: list[str] = Field(..., description="Date list")
    curves: dict[str, list[float]] = Field(..., description="Equity curves for each backtest")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "equity_comparison": {},
                "dates": ["2023-01-01", "2023-01-02", "2023-01-03"],
                "curves": {
                    "task_001": [100000, 100500, 101000],
                    "task_002": [100000, 100300, 100800],
                },
            }
        }
    )


class TradesComparison(BaseModel):
    """Trades comparison schema."""

    trades_comparison: dict[str, dict[str, Any]] = Field(..., description="Trades comparison data")


class DrawdownComparison(BaseModel):
    """Drawdown comparison schema."""

    max_drawdowns: dict[str, float] = Field(..., description="Maximum drawdown for each backtest")
    drawdown_curves: dict[str, list[float]] = Field(
        ..., description="Drawdown curves for each backtest"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "max_drawdowns": {
                    "task_001": -0.08,
                    "task_002": -0.10,
                },
                "drawdown_curves": {
                    "task_001": [0, -0.01, -0.05, -0.08],
                    "task_002": [0, -0.02, -0.06, -0.10],
                },
            }
        }
    )


class ComparisonDetail(BaseModel):
    """Comparison detail schema."""

    comparison_id: str = Field(..., description="Comparison ID")
    type: str = Field(..., description="Comparison type")
    name: str = Field(..., description="Comparison name")
    description: str | None = Field(None, description="Comparison description")
    backtest_task_ids: list[str] = Field(..., description="Backtest task ID list")
    created_at: datetime = Field(..., description="Creation time")

    # Include different comparison data based on type
    metrics: MetricsComparison | None = Field(None, description="Metrics comparison")
    equity: EquityComparison | None = Field(None, description="Equity curve comparison")
    trades: TradesComparison | None = Field(None, description="Trades comparison")
    drawdown: DrawdownComparison | None = Field(None, description="Drawdown comparison")
