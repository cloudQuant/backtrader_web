"""
Strategy schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.workspace import (
    ReportCreateRequest,
    StrategyUnitResponse,
    UnitStatusResponse,
)


class StrategyType(str, Enum):
    """Strategy type enumeration."""

    backtest = "backtest"
    simulate = "simulate"
    live = "live"


class ParamSpec(BaseModel):
    """Parameter specification schema."""

    type: str = Field("float", description="Parameter type: int/float/string/enum")
    default: Any = Field(..., description="Default value")
    min: float | None = Field(None, description="Minimum value")
    max: float | None = Field(None, description="Maximum value")
    options: list[Any] | None = Field(None, description="Enum options")
    description: str | None = Field(None, description="Parameter description")


class StrategyCreate(BaseModel):
    """Strategy creation request schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Strategy name")
    description: str | None = Field(None, description="Strategy description")
    code: str = Field(..., description="Strategy code")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Parameter definitions")
    category: str = Field("custom", description="Strategy category")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Dual MA Crossover / 双均线交叉策略",
                    "description": "Trend-following strategy based on fast/slow MA golden/death cross, suitable for daily timeframe / 基于快慢均线金叉死叉的趋势跟踪策略，适用于日线级别",
                    "code": "class MaCrossStrategy(bt.Strategy):\n    params = (('fast', 5), ('slow', 20))\n    def next(self):\n        if self.fast[0] > self.slow[0]:\n            self.buy()\n        elif self.fast[0] < self.slow[0]:\n            self.sell()",
                    "params": {
                        "fast_period": {
                            "type": "int",
                            "default": 5,
                            "min": 2,
                            "max": 50,
                            "description": "Fast MA period / 快线周期",
                        },
                        "slow_period": {
                            "type": "int",
                            "default": 20,
                            "min": 10,
                            "max": 200,
                            "description": "Slow MA period / 慢线周期",
                        },
                    },
                    "category": "Trend Following / 趋势跟踪",
                },
                {
                    "name": "MACD Trend Following / MACD趋势跟踪",
                    "description": "MACD-based trend strategy using DIF/DEA crossover for trade signals / 基于MACD指标的趋势策略，利用DIF与DEA交叉产生交易信号",
                    "code": "class MacdStrategy(bt.Strategy):\n    params = (('fast', 12), ('slow', 26), ('signal', 9))\n    ...",
                    "params": {
                        "fast_period": {
                            "type": "int",
                            "default": 12,
                            "min": 5,
                            "max": 30,
                            "description": "Fast EMA period / 快线EMA周期",
                        },
                        "slow_period": {
                            "type": "int",
                            "default": 26,
                            "min": 15,
                            "max": 60,
                            "description": "Slow EMA period / 慢线EMA周期",
                        },
                        "signal_period": {
                            "type": "int",
                            "default": 9,
                            "min": 3,
                            "max": 20,
                            "description": "Signal line period / 信号线周期",
                        },
                    },
                    "category": "Trend Following / 趋势跟踪",
                },
            ]
        }
    )


class StrategyCopilotDraftRequest(BaseModel):
    """Strategy copilot draft generation request."""

    prompt: str = Field(..., min_length=1, description="Natural language strategy requirement / 自然语言策略需求")
    knowledge_base_id: str | None = Field(default=None, description="Optional knowledge base ID / 可选知识库ID")
    thinking_mode: bool = Field(default=False, description="Enable deep reasoning mode / 是否启用深度推理模式")


class AIStrategyDataSourceSpec(BaseModel):
    """Structured data source hints for orchestration."""

    type: str = Field(default="csv", description="Suggested data source type / 建议数据源类型")
    symbol: str | None = Field(default=None, description="Suggested symbol code / 建议标的代码")
    symbol_name: str | None = Field(default=None, description="Suggested symbol name / 建议标的名称")
    timeframe: str = Field(default="1d", description="Suggested timeframe / 建议周期")
    timeframe_n: int = Field(default=1, ge=1, description="Suggested timeframe multiplier / 建议周期倍数")
    start_date: str | None = Field(default=None, description="Suggested start date / 建议开始日期")
    end_date: str | None = Field(default=None, description="Suggested end date / 建议结束日期")
    adjustment: str | None = Field(default=None, description="Adjustment method or data adjustment suggestion / 复权方式或数据调整建议")


class AIStrategyBacktestSpec(BaseModel):
    """Structured backtest defaults for orchestration."""

    initial_cash: float = Field(default=100000.0, gt=0, description="Suggested initial capital / 建议初始资金")
    commission: float = Field(default=0.001, ge=0, description="Suggested commission rate / 建议手续费率")
    annual_days: int = Field(default=252, ge=1, description="Suggested annualized trading days / 建议年化交易日")
    calc_method: str = Field(default="simple", description="Suggested return calculation method / 建议收益计算方式")
    weight_mode: str = Field(default="equal", description="Suggested portfolio weight mode / 建议组合权重模式")


class AIStrategyExecutionPlan(BaseModel):
    """Execution/workspace defaults for orchestration."""

    workspace_type: str = Field(default="research", description="Suggested workspace type / 建议工作区类型")
    group_name: str | None = Field(default=None, description="Suggested group name / 建议分组名")
    run_parallel: bool = Field(default=False, description="Suggest parallel execution / 是否建议并行运行")


class AIStrategyDraft(BaseModel):
    """Structured AI strategy draft used by Copilot flows."""

    name: str = Field(..., min_length=1, max_length=100, description="Suggested strategy name")
    description: str = Field(..., description="Suggested strategy description")
    code: str = Field(..., description="Backtrader strategy code draft")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Suggested parameter schema")
    category: str = Field("custom", description="Suggested strategy category")
    assumptions: list[str] = Field(default_factory=list, description="Key assumptions list / 关键假设列表")
    risk_points: list[str] = Field(default_factory=list, description="Main risk points list / 主要风险点列表")
    data_source: AIStrategyDataSourceSpec = Field(
        default_factory=AIStrategyDataSourceSpec,
        description="Structured data source suggestion / 结构化数据源建议",
    )
    backtest_defaults: AIStrategyBacktestSpec = Field(
        default_factory=AIStrategyBacktestSpec,
        description="Structured backtest defaults / 结构化回测默认值",
    )
    execution_plan: AIStrategyExecutionPlan = Field(
        default_factory=AIStrategyExecutionPlan,
        description="Structured execution plan / 结构化执行计划",
    )
    rationale: str | None = Field(None, description="Why this draft was generated")
    next_steps: list[str] = Field(default_factory=list, description="Suggested next refinement steps")
    suggested_symbol: str | None = Field(None, description="Suggested default symbol")
    suggested_timeframe: str | None = Field(None, description="Suggested default timeframe")


class StrategyCopilotDraftResponse(BaseModel):
    """Strategy copilot draft generation response."""

    answer: str = Field(..., description="AI-generated explanation text / AI生成的说明文本")
    strategy_draft: AIStrategyDraft = Field(..., description="Structured strategy draft / 结构化策略草稿")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="Citation list / 引用列表")
    context_chunks_used: int = Field(default=0, description="Number of context chunks used / 使用的上下文块数量")
    tokens_used: int = Field(default=0, description="Token consumption / Token消耗")
    model_id: str | None = Field(default=None, description="Model ID used / 使用的模型ID")
    reasoning: str | None = Field(default=None, description="Model reasoning summary / 模型推理摘要")


class StrategyUpdate(BaseModel):
    """Strategy update request schema."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    code: str | None = None
    params: dict[str, ParamSpec] | None = None
    category: str | None = None


class StrategyResponse(BaseModel):
    """Strategy response schema."""

    id: str = Field(..., description="Strategy ID", examples=["strat_7f8e9d0c1b2a"])
    user_id: str = Field(..., description="User ID", examples=["usr_a1b2c3d4e5f6"])
    name: str = Field(..., description="Strategy name", examples=["Dual MA Crossover / 双均线交叉策略"])
    description: str | None = Field(None, description="Strategy description", examples=["Trend-following strategy based on fast/slow MA crossover / 基于快慢均线金叉死叉的趋势跟踪策略"])
    code: str = Field(..., description="Strategy code")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Parameter definitions")
    category: str = Field(..., description="Strategy category", examples=["Trend Following / 趋势跟踪"])
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "strat_7f8e9d0c1b2a",
                    "user_id": "usr_a1b2c3d4e5f6",
                    "name": "Dual MA Crossover / 双均线交叉策略",
                    "description": "Trend-following strategy based on fast/slow MA crossover, suitable for daily timeframe / 基于快慢均线金叉死叉的趋势跟踪策略，适用于日线级别",
                    "code": "class MaCrossStrategy(bt.Strategy):\n    params = (('fast', 5), ('slow', 20))\n    ...",
                    "params": {
                        "fast_period": {
                            "type": "int",
                            "default": 5,
                            "min": 2,
                            "max": 50,
                            "description": "Fast MA period / 快线周期",
                        },
                    },
                    "category": "Trend Following / 趋势跟踪",
                    "created_at": "2025-01-10T09:00:00Z",
                    "updated_at": "2025-01-12T14:30:00Z",
                }
            ]
        },
    )


class StrategyDraftWorkspaceAddRequest(BaseModel):
    """Add AI strategy draft to workspace request."""

    strategy_draft: AIStrategyDraft = Field(..., description="AI-generated strategy draft / AI生成的策略草稿")
    strategy_id: str | None = Field(default=None, description="Optional existing strategy ID / 可选已有策略ID")
    symbol: str = Field(default="", description="Symbol code / 标的代码")
    symbol_name: str = Field(default="", description="Symbol name / 标的名称")
    timeframe: str | None = Field(default=None, description="Timeframe / 周期")
    timeframe_n: int = Field(default=1, ge=1, description="Timeframe multiplier / 周期倍数")
    group_name: str = Field(default="", description="Workspace group name / 工作区分组名称")
    data_config: dict[str, Any] = Field(default_factory=dict, description="Data configuration / 数据配置")
    unit_settings: dict[str, Any] = Field(default_factory=dict, description="Unit settings / 单元配置")
    optimization_config: dict[str, Any] = Field(default_factory=dict, description="Optimization configuration / 优化配置")


class StrategyDraftWorkspaceAddResponse(BaseModel):
    """Add AI strategy draft to workspace response."""

    workspace_id: str = Field(..., description="Workspace ID / 工作区ID")
    created_strategy: bool = Field(..., description="Whether a new strategy was created / 是否新建了策略")
    strategy: StrategyResponse = Field(..., description="Persisted strategy / 落库后的策略")
    unit: StrategyUnitResponse = Field(..., description="Created workspace unit / 创建的工作区单元")


class StrategyCopilotBacktestRequest(StrategyDraftWorkspaceAddRequest):
    """Add AI draft to workspace and trigger backtest."""

    parallel: bool = Field(default=False, description="Run in parallel / 是否并行运行")
    report_config: ReportCreateRequest | None = Field(default=None, description="Optional report configuration / 可选报告配置")


class StrategyCopilotRunResult(BaseModel):
    """Run result for a single copilot-created unit."""

    unit_id: str
    task_id: str | None = None
    status: str
    error: str | None = None


class StrategyCopilotBacktestResponse(BaseModel):
    """Backtest orchestration response for strategy copilot."""

    workspace_id: str
    created_strategy: bool
    strategy: StrategyResponse
    unit: StrategyUnitResponse
    run_result: StrategyCopilotRunResult
    unit_status: UnitStatusResponse | None = None
    report_ready: bool = False
    report: dict[str, Any] | None = None


class StrategyListResponse(BaseModel):
    """Strategy list response schema."""

    total: int
    items: list[StrategyResponse]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total": 2,
                    "items": [
                        {
                            "id": "strat_7f8e9d0c1b2a",
                            "user_id": "usr_a1b2c3d4e5f6",
                            "name": "Dual MA Crossover / 双均线交叉策略",
                            "description": "Trend-following strategy based on fast/slow MA crossover / 基于快慢均线金叉死叉的趋势跟踪策略",
                            "code": "class MaCrossStrategy(bt.Strategy): ...",
                            "params": {},
                            "category": "Trend Following / 趋势跟踪",
                            "created_at": "2025-01-10T09:00:00Z",
                            "updated_at": "2025-01-12T14:30:00Z",
                        },
                        {
                            "id": "strat_3c4d5e6f7a8b",
                            "user_id": "usr_a1b2c3d4e5f6",
                            "name": "Bollinger Breakout / 布林带突破策略",
                            "description": "Generate trade signals when price breaks Bollinger Bands / 价格突破布林带上下轨时产生交易信号",
                            "code": "class BollingerStrategy(bt.Strategy): ...",
                            "params": {},
                            "category": "Mean Reversion / 均值回归",
                            "created_at": "2025-01-08T10:15:00Z",
                            "updated_at": "2025-01-11T16:45:00Z",
                        },
                    ],
                }
            ]
        }
    )


class StrategyTemplate(BaseModel):
    """Strategy template schema."""

    id: str
    name: str
    description: str
    code: str
    params: dict[str, ParamSpec]
    category: str
