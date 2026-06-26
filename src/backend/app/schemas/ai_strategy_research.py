"""Schemas for AI-driven strategy research loops."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.strategy import StrategyCopilotRunResult, StrategyResponse
from app.schemas.workspace import StrategyUnitResponse, UnitStatusResponse, WorkspaceResponse


class AIStrategyResearchRunRequest(BaseModel):
    """Request to run an AI strategy generate/backtest/improve loop."""

    prompt: str = Field(..., min_length=1, description="Natural language strategy objective")
    symbol: str = Field(..., min_length=1, max_length=50, description="Backtest/trading symbol")
    symbol_name: str = Field("", max_length=200, description="Symbol display name")
    timeframe: str = Field("1d", max_length=10, description="K-line timeframe")
    timeframe_n: int = Field(1, ge=1, description="Timeframe multiplier")
    start_date: str | None = Field(None, description="Backtest start date")
    end_date: str | None = Field(None, description="Backtest end date")

    target_sharpe: float = Field(1.0, description="Target Sharpe ratio")
    min_total_trades: int = Field(1, ge=0, description="Minimum completed trades")
    max_drawdown_limit: float | None = Field(
        None,
        ge=0,
        description="Optional maximum allowed drawdown magnitude, ratio or percent",
    )
    min_total_return: float | None = Field(
        None,
        description="Optional minimum total return, ratio or percent",
    )
    min_annual_return: float | None = Field(
        None,
        description="Optional minimum annualized return, ratio or percent",
    )
    min_win_rate: float | None = Field(
        None,
        ge=0,
        description="Optional minimum win rate, ratio or percent",
    )
    max_iterations: int = Field(3, ge=1, le=8, description="Maximum improvement rounds")
    backtest_timeout_seconds: float = Field(
        600.0, ge=1.0, le=3600.0, description="Per-round backtest wait timeout"
    )
    poll_interval_seconds: float = Field(
        2.0, ge=0.1, le=30.0, description="Backtest status poll interval"
    )

    initial_cash: float = Field(100000.0, gt=0, description="Backtest initial cash")
    commission: float = Field(0.001, ge=0, description="Backtest commission rate")
    annual_days: int = Field(252, ge=1, description="Annualized trading days")
    calc_method: str = Field("simple", description="Return calculation method")
    weight_mode: str = Field("equal", description="Portfolio weight mode")

    research_workspace_id: str | None = Field(None, description="Existing research workspace")
    trading_workspace_id: str | None = Field(None, description="Existing trading workspace")
    seed_strategy_id: str | None = Field(
        None,
        description="Optional existing strategy ID to continue research from",
    )
    continue_from_run_id: str | None = Field(
        None,
        description="Optional previous AI research run ID whose best strategy should seed this run",
    )
    start_paper_trading: bool = Field(True, description="Start paper trading after success")
    paper_workspace_name: str | None = Field(None, description="Name for generated paper workspace")

    group_name: str | None = Field(None, max_length=200, description="Research unit group name")
    knowledge_base_id: str | None = Field(None, description="Optional knowledge base ID")
    thinking_mode: bool = Field(False, description="Enable deep reasoning when supported")

    data_config: dict[str, Any] = Field(default_factory=dict, description="Unit data config")
    unit_settings: dict[str, Any] = Field(default_factory=dict, description="Unit settings")
    optimization_config: dict[str, Any] = Field(
        default_factory=dict, description="Unit optimization config"
    )
    gateway_config: dict[str, Any] = Field(default_factory=dict, description="Paper gateway config")


class AIStrategyResearchIteration(BaseModel):
    """One generate/backtest/improve round."""

    iteration: int
    strategy: StrategyResponse
    unit: StrategyUnitResponse
    run_result: StrategyCopilotRunResult
    unit_status: UnitStatusResponse | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    sharpe_ratio: float = 0.0
    total_trades: int = 0
    quality_score: float = 0.0
    quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    passed: bool = False
    failure_reason: str | None = None
    quality_gate_failures: list[str] = Field(default_factory=list)
    improvement_notes: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class AIStrategyPaperTradingStart(BaseModel):
    """Paper trading workspace/unit started after research success."""

    workspace: WorkspaceResponse
    unit: StrategyUnitResponse
    run_result: StrategyCopilotRunResult | None = None
    started: bool = False
    handoff: dict[str, Any] | None = None


class AIStrategyPaperTradingStartRequest(BaseModel):
    """Request to promote an existing AI research run into paper trading."""

    research_workspace_id: str | None = Field(None, description="Workspace that stores the run")
    trading_workspace_id: str | None = Field(None, description="Existing trading workspace")
    paper_workspace_name: str | None = Field(None, description="Name for generated paper workspace")
    gateway_config: dict[str, Any] = Field(default_factory=dict, description="Paper gateway config")


class AIStrategyResearchRunRecord(BaseModel):
    """Compact persisted summary for one AI strategy research run."""

    run_id: str
    prompt: str
    symbol: str
    symbol_name: str = ""
    timeframe: str = "1d"
    timeframe_n: int = 1
    status: str
    achieved: bool
    target_sharpe: float
    quality_gates: dict[str, Any] = Field(default_factory=dict)
    min_total_trades: int = 0
    max_iterations: int = 0
    iteration_count: int = 0
    best_iteration: int | None = None
    best_sharpe: float = 0.0
    best_quality_score: float = 0.0
    best_quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    best_metrics: dict[str, Any] = Field(default_factory=dict)
    best_strategy_id: str | None = None
    best_strategy_name: str | None = None
    research_workspace_id: str
    seed_strategy_id: str | None = None
    continued_from_run_id: str | None = None
    paper_workspace_id: str | None = None
    paper_unit_id: str | None = None
    paper_trading_started: bool = False
    next_actions: list[str] = Field(default_factory=list)
    started_at: str
    completed_at: str
    iterations: list[dict[str, Any]] = Field(default_factory=list)


class AIStrategyResearchRunListResponse(BaseModel):
    """Recent AI strategy research run records."""

    total: int
    items: list[AIStrategyResearchRunRecord] = Field(default_factory=list)


class AIStrategyResearchRunResponse(BaseModel):
    """Result of the AI strategy research loop."""

    run_id: str
    status: str
    achieved: bool
    target_sharpe: float
    started_at: str
    completed_at: str
    best_iteration: int | None = None
    best_quality_score: float = 0.0
    best_quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    best_metrics: dict[str, Any] = Field(default_factory=dict)
    research_workspace: WorkspaceResponse
    iterations: list[AIStrategyResearchIteration] = Field(default_factory=list)
    best_strategy: StrategyResponse | None = None
    paper_trading: AIStrategyPaperTradingStart | None = None
    run_record: AIStrategyResearchRunRecord | None = None
    next_actions: list[str] = Field(default_factory=list)
    message: str
