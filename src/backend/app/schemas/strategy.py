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
            "example": {
                "name": "Dual Moving Average Strategy",
                "description": "Trend strategy based on fast and slow moving average crossover",
                "code": "class MaCrossStrategy(bt.Strategy):\n    params = (('fast', 5), ('slow', 20))\n    ...",
                "params": {
                    "fast_period": {
                        "type": "int",
                        "default": 5,
                        "min": 2,
                        "max": 50,
                        "description": "Fast period",
                    },
                    "slow_period": {
                        "type": "int",
                        "default": 20,
                        "min": 10,
                        "max": 200,
                        "description": "Slow period",
                    },
                },
                "category": "trend",
            }
        }
    )


class StrategyCopilotDraftRequest(BaseModel):
    """Strategy copilot draft generation request."""

    prompt: str = Field(..., min_length=1, description="自然语言策略需求")
    knowledge_base_id: str | None = Field(default=None, description="可选知识库ID")
    thinking_mode: bool = Field(default=False, description="是否启用深度推理模式")


class AIStrategyDataSourceSpec(BaseModel):
    """Structured data source hints for orchestration."""

    type: str = Field(default="csv", description="建议数据源类型")
    symbol: str | None = Field(default=None, description="建议标的代码")
    symbol_name: str | None = Field(default=None, description="建议标的名称")
    timeframe: str = Field(default="1d", description="建议周期")
    timeframe_n: int = Field(default=1, ge=1, description="建议周期倍数")
    start_date: str | None = Field(default=None, description="建议开始日期")
    end_date: str | None = Field(default=None, description="建议结束日期")
    adjustment: str | None = Field(default=None, description="复权方式或数据调整建议")


class AIStrategyBacktestSpec(BaseModel):
    """Structured backtest defaults for orchestration."""

    initial_cash: float = Field(default=100000.0, gt=0, description="建议初始资金")
    commission: float = Field(default=0.001, ge=0, description="建议手续费率")
    annual_days: int = Field(default=252, ge=1, description="建议年化交易日")
    calc_method: str = Field(default="simple", description="建议收益计算方式")
    weight_mode: str = Field(default="equal", description="建议组合权重模式")


class AIStrategyExecutionPlan(BaseModel):
    """Execution/workspace defaults for orchestration."""

    workspace_type: str = Field(default="research", description="建议工作区类型")
    group_name: str | None = Field(default=None, description="建议分组名")
    run_parallel: bool = Field(default=False, description="是否建议并行运行")


class AIStrategyDraft(BaseModel):
    """Structured AI strategy draft used by Copilot flows."""

    name: str = Field(..., min_length=1, max_length=100, description="Suggested strategy name")
    description: str = Field(..., description="Suggested strategy description")
    code: str = Field(..., description="Backtrader strategy code draft")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Suggested parameter schema")
    category: str = Field("custom", description="Suggested strategy category")
    assumptions: list[str] = Field(default_factory=list, description="关键假设列表")
    risk_points: list[str] = Field(default_factory=list, description="主要风险点列表")
    data_source: AIStrategyDataSourceSpec = Field(
        default_factory=AIStrategyDataSourceSpec,
        description="结构化数据源建议",
    )
    backtest_defaults: AIStrategyBacktestSpec = Field(
        default_factory=AIStrategyBacktestSpec,
        description="结构化回测默认值",
    )
    execution_plan: AIStrategyExecutionPlan = Field(
        default_factory=AIStrategyExecutionPlan,
        description="结构化执行计划",
    )
    rationale: str | None = Field(None, description="Why this draft was generated")
    next_steps: list[str] = Field(default_factory=list, description="Suggested next refinement steps")
    suggested_symbol: str | None = Field(None, description="Suggested default symbol")
    suggested_timeframe: str | None = Field(None, description="Suggested default timeframe")


class StrategyCopilotDraftResponse(BaseModel):
    """Strategy copilot draft generation response."""

    answer: str = Field(..., description="AI生成的说明文本")
    strategy_draft: AIStrategyDraft = Field(..., description="结构化策略草稿")
    citations: list[dict[str, Any]] = Field(default_factory=list, description="引用列表")
    context_chunks_used: int = Field(default=0, description="使用的上下文块数量")
    tokens_used: int = Field(default=0, description="Token消耗")
    model_id: str | None = Field(default=None, description="使用的模型ID")
    reasoning: str | None = Field(default=None, description="模型推理摘要")


class StrategyUpdate(BaseModel):
    """Strategy update request schema."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    code: str | None = None
    params: dict[str, ParamSpec] | None = None
    category: str | None = None


class StrategyResponse(BaseModel):
    """Strategy response schema."""

    id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="Strategy name")
    description: str | None = Field(None, description="Strategy description")
    code: str = Field(..., description="Strategy code")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Parameter definitions")
    category: str = Field(..., description="Strategy category")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")

    model_config = ConfigDict(from_attributes=True)


class StrategyDraftWorkspaceAddRequest(BaseModel):
    """Add AI strategy draft to workspace request."""

    strategy_draft: AIStrategyDraft = Field(..., description="AI生成的策略草稿")
    strategy_id: str | None = Field(default=None, description="可选已有策略ID")
    symbol: str = Field(default="", description="标的代码")
    symbol_name: str = Field(default="", description="标的名称")
    timeframe: str | None = Field(default=None, description="周期")
    timeframe_n: int = Field(default=1, ge=1, description="周期倍数")
    group_name: str = Field(default="", description="工作区分组名称")
    data_config: dict[str, Any] = Field(default_factory=dict, description="数据配置")
    unit_settings: dict[str, Any] = Field(default_factory=dict, description="单元配置")
    optimization_config: dict[str, Any] = Field(default_factory=dict, description="优化配置")


class StrategyDraftWorkspaceAddResponse(BaseModel):
    """Add AI strategy draft to workspace response."""

    workspace_id: str = Field(..., description="工作区ID")
    created_strategy: bool = Field(..., description="是否新建了策略")
    strategy: StrategyResponse = Field(..., description="落库后的策略")
    unit: StrategyUnitResponse = Field(..., description="创建的工作区单元")


class StrategyCopilotBacktestRequest(StrategyDraftWorkspaceAddRequest):
    """Add AI draft to workspace and trigger backtest."""

    parallel: bool = Field(default=False, description="是否并行运行")
    report_config: ReportCreateRequest | None = Field(default=None, description="可选报告配置")


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


class StrategyTemplate(BaseModel):
    """Strategy template schema."""

    id: str
    name: str
    description: str
    code: str
    params: dict[str, ParamSpec]
    category: str
