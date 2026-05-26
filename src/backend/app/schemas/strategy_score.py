"""Strategy score schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.backtest import BacktestResult


class ScoreLevel(str, Enum):
    """Strategy score level."""

    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class ScoreDimension(BaseModel):
    """Single score dimension."""

    key: str = Field(..., description="Dimension key")
    label: str = Field(..., description="Dimension label")
    score: float = Field(..., ge=0, le=100, description="Dimension score")
    weight: float = Field(..., ge=0, le=1, description="Dimension weight")
    explanation: str = Field(..., description="Human-readable explanation")
    sub_metrics: dict[str, Any] = Field(default_factory=dict, description="Supporting metrics")
    degraded: bool = Field(False, description="Whether this dimension uses a degraded fallback")


class StrategyScoreRequest(BaseModel):
    """Strategy score request payload."""

    backtest_id: str | None = Field(default=None, description="Backtest task id")
    backtest_result: BacktestResult | None = Field(
        default=None,
        description="Optional inline backtest result payload",
    )

    @model_validator(mode="after")
    def validate_data_source(self) -> StrategyScoreRequest:
        """Require either backtest id or backtest payload."""
        if not self.backtest_id and self.backtest_result is None:
            raise ValueError("Either backtest_id or backtest_result must be provided")
        if self.backtest_id and self.backtest_result and self.backtest_id != self.backtest_result.task_id:
            raise ValueError("backtest_id must match backtest_result.task_id when both are provided")
        return self


class StrategyScoreResponse(BaseModel):
    """Strategy score response."""

    backtest_id: str = Field(..., description="Backtest task id")
    total_score: float = Field(..., ge=0, le=100, description="Weighted total score")
    level: ScoreLevel = Field(..., description="Score level")
    model_version: str = Field(..., description="Scoring model version")
    disclaimer: str = Field(..., description="Risk disclaimer")
    dimensions: list[ScoreDimension] = Field(default_factory=list, description="Dimension breakdown")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "backtest_id": "task_123",
                "total_score": 78.5,
                "level": "A",
                "model_version": "v1",
                "disclaimer": "评分仅供研究参考，不构成投资建议。",
                "dimensions": [
                    {
                        "key": "profitability",
                        "label": "收益质量",
                        "score": 82.0,
                        "weight": 0.2,
                        "explanation": "收益率和夏普表现较好。",
                        "sub_metrics": {"annual_return": 18.4, "sharpe_ratio": 1.35},
                        "degraded": False,
                    }
                ],
            }
        }
    )
