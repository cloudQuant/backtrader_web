from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OverfittingMethod(str, Enum):
    WALK_FORWARD = "walk_forward"
    OUT_OF_SAMPLE = "out_of_sample"
    MONTE_CARLO = "monte_carlo"


class OverfittingRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OverfittingAnalysisRequest(BaseModel):
    methods: list[OverfittingMethod] = Field(
        default_factory=lambda: [OverfittingMethod.MONTE_CARLO],
        description="Requested analysis methods",
    )
    walk_forward_train_days: int = Field(
        default=180,
        ge=30,
        le=2000,
        description="In-sample window size in days for walk-forward analysis",
    )
    walk_forward_test_days: int = Field(
        default=60,
        ge=10,
        le=1000,
        description="Out-of-sample window size in days for walk-forward analysis",
    )
    walk_forward_step_days: int = Field(
        default=30,
        ge=10,
        le=1000,
        description="Rolling step size in days for walk-forward analysis",
    )
    walk_forward_max_concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum concurrent slice backtests for walk-forward analysis",
    )
    out_of_sample_ratio: float = Field(
        default=0.3,
        gt=0.05,
        lt=0.95,
        description="Out-of-sample holdout ratio",
    )
    monte_carlo_iterations: int = Field(
        default=500,
        ge=50,
        le=5000,
        description="Bootstrap iterations for Monte Carlo analysis",
    )
    random_seed: int | None = Field(
        default=None,
        ge=0,
        description="Optional deterministic random seed",
    )

    @field_validator("methods")
    @classmethod
    def validate_methods(cls, value: list[OverfittingMethod]) -> list[OverfittingMethod]:
        if not value:
            raise ValueError("At least one overfitting method must be provided")
        unique_methods: list[OverfittingMethod] = []
        seen: set[OverfittingMethod] = set()
        for item in value:
            if item in seen:
                continue
            unique_methods.append(item)
            seen.add(item)
        return unique_methods


class OverfittingMethodResult(BaseModel):
    method: OverfittingMethod = Field(..., description="Detection method")
    status: str = Field(..., description="Method execution status")
    risk_level: OverfittingRiskLevel = Field(..., description="Method-level risk level")
    score: float = Field(..., ge=0, le=100, description="Method robustness score")
    explanation: str = Field(..., description="Method explanation")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Method supporting metrics")
    degraded: bool = Field(default=False, description="Whether the method result is degraded")


class OverfittingTaskSubmission(BaseModel):
    task_id: str = Field(..., description="Async overfitting task id")
    backtest_id: str = Field(..., description="Backtest task id")
    status: str = Field(..., description="Task status")
    methods: list[OverfittingMethod] = Field(default_factory=list, description="Requested methods")


class OverfittingTaskResult(BaseModel):
    task_id: str = Field(..., description="Async overfitting task id")
    backtest_id: str = Field(..., description="Backtest task id")
    status: str = Field(..., description="Task status")
    overall_level: OverfittingRiskLevel = Field(..., description="Overall overfitting risk level")
    robustness_score: float = Field(..., ge=0, le=100, description="Overall robustness score")
    summary: str = Field(..., description="Task summary")
    methods: list[OverfittingMethodResult] = Field(
        default_factory=list, description="Method results"
    )
    error_message: str | None = Field(default=None, description="Failure reason if task failed")
