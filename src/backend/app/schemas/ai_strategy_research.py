"""Schemas for AI-driven strategy research loops."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.strategy import StrategyCopilotRunResult, StrategyResponse
from app.schemas.workspace import StrategyUnitResponse, UnitStatusResponse, WorkspaceResponse

AIStrategyResearchWorkflowMode = Literal["auto", "prompt"]
AIStrategyResearchWorkflowStep = Literal[
    "ideation",
    "generation",
    "backtest",
    "review",
    "optimization",
    "validation",
    "robustness",
    "paper_trading",
]

AI_STRATEGY_RESEARCH_DEFAULT_WORKFLOW_STEPS: tuple[AIStrategyResearchWorkflowStep, ...] = (
    "ideation",
    "generation",
    "backtest",
    "review",
    "optimization",
)

AI_STRATEGY_RESEARCH_WORKFLOW_STEP_LABELS: dict[AIStrategyResearchWorkflowStep, str] = {
    "ideation": "策略构思",
    "generation": "策略生成",
    "backtest": "策略回测",
    "review": "策略审查",
    "optimization": "策略优化",
    "validation": "样本外验证",
    "robustness": "稳健性验证",
    "paper_trading": "模拟交易",
}

AI_STRATEGY_RESEARCH_WORKFLOW_STEP_DESCRIPTIONS: dict[AIStrategyResearchWorkflowStep, str] = {
    "ideation": "比较候选信号家族，明确入场、出场、仓位和风控假设。",
    "generation": "生成完整可运行的 Backtrader Strategy 脚本，不能留 pass、TODO 或伪代码。",
    "backtest": "自动提交回测并记录 Sharpe、收益、回撤、交易次数和质量门槛差距。",
    "review": "审查回测结果、失败原因、过拟合风险和实盘可执行性。",
    "optimization": "根据审查意见继续优化代码、参数和风控，必要时进入下一轮回测。",
    "validation": "对达标策略执行样本外验证，确认稳健性后再晋级。",
    "robustness": "执行过拟合、参数扰动和 Monte Carlo 等稳健性验证，未通过不得晋级。",
    "paper_trading": "达标后进入模拟交易，复核滑点、费用、估值置信度和滚动表现。",
}


class AIStrategyResearchConfigProfile(BaseModel):
    """A reusable local YAML profile for the AI research form."""

    id: str = Field(
        ...,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="Stable profile identifier used in URLs and YAML.",
    )
    name: str = Field(..., min_length=1, max_length=120, description="Profile display name")
    description: str = Field("", max_length=500, description="Optional profile notes")
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="AI research form snapshot; frontend converts it to a run request.",
    )
    created_at: str | None = Field(None, description="ISO timestamp when the profile was created")
    updated_at: str | None = Field(None, description="ISO timestamp when the profile was updated")


class AIStrategyResearchConfigProfileCreate(BaseModel):
    """Create a reusable AI research configuration profile."""

    id: str | None = Field(
        None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="Optional stable profile id; generated when omitted.",
    )
    name: str = Field(..., min_length=1, max_length=120, description="Profile display name")
    description: str = Field("", max_length=500, description="Optional profile notes")
    config: dict[str, Any] = Field(default_factory=dict, description="AI research form snapshot")


class AIStrategyResearchConfigProfileUpdate(BaseModel):
    """Update a reusable AI research configuration profile."""

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=500)
    config: dict[str, Any] | None = Field(None, description="AI research form snapshot")


class AIStrategyResearchConfigProfileListResponse(BaseModel):
    """List response for local AI research configuration profiles."""

    file_path: str
    total: int
    items: list[AIStrategyResearchConfigProfile]


class AIStrategyResearchConfigProfileImportRequest(BaseModel):
    """Import one or more AI research configuration profiles from YAML text."""

    raw_yaml: str = Field(..., min_length=1, description="YAML content selected in the frontend")
    name: str | None = Field(None, max_length=120, description="Fallback profile name")
    profile_id: str | None = Field(
        None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="Optional profile id used when the YAML does not contain one.",
    )


class AIStrategyResearchConfigProfileImportResponse(BaseModel):
    """Import response for YAML profile content."""

    file_path: str
    total: int
    items: list[AIStrategyResearchConfigProfile]


class InvestmentMandateCreate(BaseModel):
    """Create and parse a structured investment demand for AI research."""

    raw_prompt: str = Field(..., min_length=1, description="Original user investment demand")
    symbol: str | None = Field(None, max_length=50, description="Optional target symbol")
    symbol_name: str | None = Field(
        None, max_length=200, description="Optional symbol display name"
    )
    timeframe: str | None = Field(None, max_length=20, description="Optional target timeframe")
    objective: str | None = Field(None, max_length=500, description="Optional user-edited goal")
    risk_constraints: dict[str, Any] = Field(default_factory=dict)
    trading_constraints: dict[str, Any] = Field(default_factory=dict)
    quality_gates: dict[str, Any] = Field(default_factory=dict)


class InvestmentMandateResponse(BaseModel):
    """Structured investment demand confirmed before running AI research."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    raw_prompt: str
    structured_goal: dict[str, Any] = Field(default_factory=dict)
    asset_scope: dict[str, Any] = Field(default_factory=dict)
    timeframe: str | None = None
    objective: str | None = None
    risk_constraints: dict[str, Any] = Field(default_factory=dict)
    trading_constraints: dict[str, Any] = Field(default_factory=dict)
    quality_gates: dict[str, Any] = Field(default_factory=dict)
    status: str = "confirmed"
    source: str = "rule"
    created_at: str
    updated_at: str


class ResearchPipelineEventResponse(BaseModel):
    """One persisted stage event for an AI research run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    workspace_id: str | None = None
    mandate_id: str | None = None
    stage: str
    status: str
    iteration: int | None = None
    summary: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str


class ResearchTimelineResponse(BaseModel):
    """Timeline response for one AI research run."""

    run_id: str
    total: int
    items: list[ResearchPipelineEventResponse] = Field(default_factory=list)


class AIStrategyResearchVersionResponse(BaseModel):
    """Strategy code version generated inside one AI research run."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    workspace_id: str | None = None
    mandate_id: str | None = None
    strategy_id: str | None = None
    unit_id: str | None = None
    backtest_task_id: str | None = None
    version_no: int
    version_name: str
    parent_version_id: str | None = None
    strategy_name: str | None = None
    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    ai_rationale: str | None = None
    change_summary: str | None = None
    backtest_metrics: dict[str, Any] = Field(default_factory=dict)
    quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    quality_gate_status: str = "pending"
    review: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class AIStrategyResearchVersionListResponse(BaseModel):
    """List response for AI research strategy versions."""

    run_id: str
    total: int
    items: list[AIStrategyResearchVersionResponse] = Field(default_factory=list)


class AIStrategyResearchVersionCompareResponse(BaseModel):
    """Comparison between two AI research strategy versions."""

    run_id: str
    left: AIStrategyResearchVersionResponse
    right: AIStrategyResearchVersionResponse
    metric_deltas: dict[str, Any] = Field(default_factory=dict)
    gate_deltas: dict[str, Any] = Field(default_factory=dict)
    code_diff: str = ""
    verdict: str = "mixed"
    summary: str = ""


def _default_ai_research_workflow_steps() -> list[AIStrategyResearchWorkflowStep]:
    return list(AI_STRATEGY_RESEARCH_DEFAULT_WORKFLOW_STEPS)


def _research_workflow_step_lines(request: AIStrategyResearchRunRequest) -> list[str]:
    lines: list[str] = []
    mode_label = (
        "自动规划并执行完整投研流水线"
        if request.workflow_mode == "auto"
        else "按用户提示执行指定投研流水线"
    )
    lines.append(f"模式：{mode_label}。")
    for index, step in enumerate(request.workflow_steps, start=1):
        label = AI_STRATEGY_RESEARCH_WORKFLOW_STEP_LABELS[step]
        description = AI_STRATEGY_RESEARCH_WORKFLOW_STEP_DESCRIPTIONS[step]
        lines.append(f"{index}. {label}：{description}")
    return lines


def _format_research_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    number = float(value)
    if not number.is_integer():
        return f"{number:.{digits}f}"
    if digits <= 0:
        return str(int(number))
    return f"{number:.{digits}f}"


def _research_symbol_label(request: AIStrategyResearchRunRequest) -> str:
    symbol = request.symbol.strip() or "待研究标的"
    symbol_name = request.symbol_name.strip()
    return f"{symbol_name}（{symbol}）" if symbol_name else symbol


_RESEARCH_FUTURES_SUFFIXES = (".CFE", ".CFFEX", ".SHFE", ".INE", ".DCE", ".CZCE", ".GFEX")
_RESEARCH_FUTURES_PREFIXES = (
    "IF",
    "IC",
    "IH",
    "IM",
    "T",
    "TF",
    "TL",
    "TS",
    "AU",
    "AG",
    "CU",
    "AL",
    "ZN",
    "PB",
    "NI",
    "SN",
    "AO",
    "RB",
    "HC",
    "SS",
    "BU",
    "RU",
    "BR",
    "FU",
    "SP",
    "WR",
    "SC",
    "LU",
    "NR",
    "BC",
    "EC",
    "A",
    "B",
    "C",
    "CS",
    "EB",
    "EG",
    "I",
    "J",
    "JD",
    "JM",
    "L",
    "LH",
    "M",
    "P",
    "PG",
    "PP",
    "RR",
    "V",
    "Y",
    "SA",
    "FG",
    "MA",
    "TA",
    "SR",
    "CF",
    "OI",
    "RM",
    "AP",
    "CJ",
    "CY",
    "PF",
    "PK",
    "SF",
    "SM",
    "UR",
    "WH",
    "ZC",
    "SI",
    "LC",
)


def _is_research_futures_symbol(symbol: str) -> bool:
    normalized = symbol.strip().upper()
    if not normalized:
        return False
    if normalized.endswith(_RESEARCH_FUTURES_SUFFIXES):
        return True
    for prefix in sorted(_RESEARCH_FUTURES_PREFIXES, key=len, reverse=True):
        if not normalized.startswith(prefix):
            continue
        suffix = normalized[len(prefix) :]
        if any(ch.isdigit() for ch in suffix):
            return True
        if not suffix and len(prefix) >= 2:
            return True
    return False


def _research_asset_constraint_line(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if _is_research_futures_symbol(symbol):
        return (
            "按期货/合约资产处理，必须使用交易所或本地资产规格中的合约乘数、"
            "保证金、杠杆、最小变动价位和真实手续费估算仓位与风险。"
        )
    if any(token in normalized for token in ("USDT", "USDC", "PERP", "SWAP", "BTC", "ETH")):
        return "按数字资产或永续合约处理，必须显式考虑资金费率、杠杆、滑点、交易费率和保证金约束。"
    if normalized.endswith((".SZ", ".SH", ".BJ")):
        return "按股票资产处理，必须控制单票仓位、换手率、手续费和不可成交假设，避免过度交易。"
    return "必须从交易所或本地资产规格读取手续费、合约乘数、保证金、价格精度和最小下单量，并在仓位 sizing 中使用这些约束。"


def _build_default_ai_research_prompt(request: AIStrategyResearchRunRequest) -> str:
    quality_lines = [
        f"目标 Sharpe 不低于 {_format_research_number(request.target_sharpe)}。",
        f"至少产生 {_format_research_number(request.min_total_trades, 0)} 笔有效交易，避免只靠少数交易达标。",
    ]
    if request.max_drawdown_limit is not None:
        quality_lines.append(
            f"最大回撤控制在 {_format_research_number(request.max_drawdown_limit, 0)}% 以内。"
        )
    if request.min_total_return is not None:
        quality_lines.append(
            f"总收益率不低于 {_format_research_number(request.min_total_return, 0)}%。"
        )
    if request.min_annual_return is not None:
        quality_lines.append(
            f"年化收益率不低于 {_format_research_number(request.min_annual_return, 0)}%。"
        )
    if request.min_win_rate is not None:
        quality_lines.append(f"胜率不低于 {_format_research_number(request.min_win_rate, 0)}%。")

    validation_lines = [
        f"回测区间：{request.start_date or '可用历史数据起点'} 至 {request.end_date or '最新可得数据'}。",
        (
            f"运行口径：年化天数 {_format_research_number(request.annual_days, 0)}，"
            f"收益计算 {request.calc_method}，组合权重 {request.weight_mode}。"
        ),
    ]
    if request.out_of_sample_validation:
        requirements = [
            f"保留 {_format_research_number(request.out_of_sample_ratio * 100, 0)}% 数据做样本外验证"
        ]
        if request.require_out_of_sample_validation:
            requirements.append("达标后必须通过样本外验证才能进入模拟交易")
        if request.min_out_of_sample_sharpe is not None:
            requirements.append(
                f"样本外 Sharpe 不低于 {_format_research_number(request.min_out_of_sample_sharpe)}"
            )
        if request.min_out_of_sample_trades is not None:
            requirements.append(
                f"样本外交易数不少于 {_format_research_number(request.min_out_of_sample_trades, 0)}"
            )
        validation_lines.append(f"{'，'.join(requirements)}。")
    else:
        validation_lines.append("暂不启用样本外验证，但策略说明中必须提示过拟合风险。")

    if request.robustness_validation:
        robustness_methods = "、".join(request.robustness_methods or ["monte_carlo"])
        validation_lines.append(
            "晋级前必须完成稳健性验证："
            f"方法 {robustness_methods}，"
            f"稳健性得分不低于 {_format_research_number(request.min_robustness_score)}。"
        )

    if request.start_paper_trading:
        validation_lines.append(
            "质量门槛达成后进入模拟交易，至少观察 "
            f"{_format_research_number(request.min_paper_trading_days, 0)} 天，"
            "重点复核真实手续费、滑点、估值置信度、回撤和滚动 Sharpe。"
        )
    else:
        validation_lines.append("本轮只完成研究和回测，不自动启动模拟交易。")

    signal_families = "趋势跟随、均值回归、波动率过滤、突破确认和风险预算"
    return "\n".join(
        [
            (
                f"请为 {_research_symbol_label(request)} 生成一套 {request.timeframe} "
                "级别的可执行 Backtrader 策略，并自动迭代回测直到达到质量门槛。"
            ),
            "",
            "专业流水线：",
            *_research_workflow_step_lines(request),
            "",
            "研究方向：",
            f"1. 先比较 {signal_families} 等候选逻辑，再选择最适合该标的的可执行方案。",
            "2. 策略必须包含明确的入场、出场、止损/止盈、仓位 sizing 和异常行情保护。",
            f"3. {_research_asset_constraint_line(request.symbol)}",
            "",
            "质量门槛：",
            *[f"{index + 1}. {line}" for index, line in enumerate(quality_lines)],
            "",
            "验证与晋级：",
            *[f"{index + 1}. {line}" for index, line in enumerate(validation_lines)],
            "",
            (
                "输出要求：生成完整可运行的 Backtrader Strategy 脚本，参数默认值要便于自动改稿；"
                "每轮改进都应解释为什么可能改善 Sharpe、回撤、交易次数或实盘可执行性。"
            ),
        ]
    )


class AIStrategyResearchRunRequest(BaseModel):
    """Request to run an AI strategy generate/backtest/improve loop."""

    prompt: str = Field(
        "",
        description=(
            "Natural language strategy objective. When omitted, the platform generates "
            "a structured objective from symbol, timeframe, quality gates, and promotion settings."
        ),
    )
    workflow_mode: AIStrategyResearchWorkflowMode = Field(
        "auto",
        description=(
            "How the research workflow is planned: auto generates a professional objective "
            "from controls; prompt requires a user-provided objective."
        ),
    )
    workflow_steps: list[AIStrategyResearchWorkflowStep] = Field(
        default_factory=_default_ai_research_workflow_steps,
        min_length=1,
        description="Ordered professional research workflow steps to execute and report.",
    )
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
    out_of_sample_validation: bool = Field(
        True,
        description="Run an out-of-sample validation backtest before paper trading when dates allow",
    )
    require_out_of_sample_validation: bool = Field(
        False,
        description=(
            "When enabled, an achieved training backtest cannot be promoted to paper trading "
            "unless out-of-sample validation runs and passes"
        ),
    )
    out_of_sample_ratio: float = Field(
        0.25,
        ge=0.05,
        le=0.5,
        description="Fraction of the requested date range reserved for out-of-sample validation",
    )
    min_out_of_sample_sharpe: float | None = Field(
        None,
        description="Optional minimum Sharpe for out-of-sample validation; defaults to 60% of target",
    )
    min_out_of_sample_trades: int | None = Field(
        None,
        ge=0,
        description="Optional minimum trades for out-of-sample validation",
    )
    robustness_validation: bool = Field(
        False,
        description="Run robustness/overfitting validation before paper trading",
    )
    require_robustness_validation: bool = Field(
        False,
        description=(
            "When enabled, an achieved backtest cannot be promoted to paper trading "
            "unless robustness validation runs and passes"
        ),
    )
    robustness_methods: list[str] = Field(
        default_factory=lambda: ["monte_carlo"],
        description="Robustness methods, e.g. monte_carlo, parameter_sensitivity, walk_forward",
    )
    min_robustness_score: float = Field(
        55.0,
        ge=0,
        le=100,
        description="Minimum robustness score required for promotion",
    )
    robustness_monte_carlo_iterations: int = Field(
        300,
        ge=50,
        le=5000,
        description="Monte Carlo iterations used by robustness validation",
    )
    robustness_random_seed: int | None = Field(
        None,
        ge=0,
        description="Optional deterministic random seed for robustness validation",
    )
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
    mandate_id: str | None = Field(
        None,
        description="Confirmed investment mandate ID used to audit this research run",
    )
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
    min_paper_trading_days: int = Field(
        7,
        ge=0,
        le=365,
        description="Minimum paper-trading observation days before live handoff eligibility",
    )
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
    continuation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Internal context carried from a previous research/paper review run",
    )

    @model_validator(mode="after")
    def fill_generated_prompt(self) -> AIStrategyResearchRunRequest:
        prompt = self.prompt.strip()
        if self.workflow_mode == "prompt" and not prompt:
            raise ValueError("workflow_mode='prompt' requires a non-empty prompt")
        if prompt:
            object.__setattr__(self, "prompt", prompt)
            return self
        object.__setattr__(self, "prompt", _build_default_ai_research_prompt(self))
        fields_set = getattr(self, "__pydantic_fields_set__", None)
        if isinstance(fields_set, set):
            fields_set.discard("prompt")
        return self


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
    validation_unit: StrategyUnitResponse | None = None
    validation_run_result: StrategyCopilotRunResult | None = None
    validation_unit_status: UnitStatusResponse | None = None
    validation_status: str | None = None
    validation_window: dict[str, str] | None = None
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    validation_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    validation_failures: list[str] = Field(default_factory=list)
    validation_failure_reason: str | None = None
    robustness_status: str | None = None
    robustness_result: dict[str, Any] = Field(default_factory=dict)
    robustness_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    robustness_failures: list[str] = Field(default_factory=list)
    robustness_failure_reason: str | None = None
    quality_score: float = 0.0
    quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    passed: bool = False
    failure_reason: str | None = None
    quality_gate_failures: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured diagnosis of this backtest round and improvement focus",
    )
    improvement_plan: list[str] = Field(
        default_factory=list,
        description="Concrete changes the next strategy revision should prioritize",
    )
    improvement_notes: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class AIStrategyPaperTradingStart(BaseModel):
    """Paper trading workspace/unit started after research success."""

    workspace: WorkspaceResponse
    unit: StrategyUnitResponse
    run_result: StrategyCopilotRunResult | None = None
    started: bool = False
    handoff: dict[str, Any] | None = None
    run_record: AIStrategyResearchRunRecord | None = None


class AIStrategyPaperTradingStartRequest(BaseModel):
    """Request to promote an existing AI research run into paper trading."""

    research_workspace_id: str | None = Field(None, description="Workspace that stores the run")
    trading_workspace_id: str | None = Field(None, description="Existing trading workspace")
    paper_workspace_name: str | None = Field(None, description="Name for generated paper workspace")
    gateway_config: dict[str, Any] = Field(default_factory=dict, description="Paper gateway config")


class AIStrategyPaperTradingRuleEvaluation(BaseModel):
    """Evaluation for one paper trading monitoring rule."""

    key: str
    label: str
    metric: str
    window: str
    direction: str
    threshold: float
    actual: float | None = None
    source: str | None = None
    status: str
    passed: bool = False
    margin: float | None = None
    gap: float | None = None
    gap_ratio: float | None = None
    distance_to_pass: float | None = None
    action: str


class AIStrategyPaperTradingReview(BaseModel):
    """Current paper trading validation state for an AI research run."""

    run_id: str
    research_workspace_id: str
    paper_workspace_id: str | None = None
    paper_unit_id: str | None = None
    paper_trading_started: bool = False
    workspace: WorkspaceResponse | None = None
    unit: StrategyUnitResponse | None = None
    unit_status: UnitStatusResponse | None = None
    monitoring_plan: list[dict[str, Any]] = Field(default_factory=list)
    evaluations: list[AIStrategyPaperTradingRuleEvaluation] = Field(default_factory=list)
    ready_for_live: bool = False
    status: str
    reviewed_at: str | None = None
    live_readiness_checklist: list[dict[str, Any]] = Field(default_factory=list)
    live_readiness_expires_at: str | None = None
    pipeline: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    live_handoff: AIStrategyLiveHandoffPackage | None = None


class AIStrategyLiveHandoffApprovalRequest(BaseModel):
    """Manual approval or rejection for a live handoff package."""

    decision: str = Field(..., description="Approval decision: approved or rejected")
    approver: str | None = Field(None, max_length=120, description="Human approver name or ID")
    comment: str | None = Field(None, max_length=2000, description="Decision note")
    account_confirmed: bool = Field(False, description="Live account and permissions checked")
    risk_limit_confirmed: bool = Field(False, description="Live risk limits checked")
    deployment_window: str | None = Field(
        None, max_length=200, description="Planned go-live window"
    )


class AIStrategyLiveHandoffApprovalRecord(BaseModel):
    """Persisted manual decision for a live handoff package."""

    run_id: str
    research_workspace_id: str
    decision: str
    approved: bool = False
    decided_at: str
    decided_by: str
    comment: str | None = None
    account_confirmed: bool = False
    risk_limit_confirmed: bool = False
    deployment_window: str | None = None
    handoff_status_at_decision: str
    blockers: list[str] = Field(default_factory=list)


class AIStrategyLiveHandoffPackage(BaseModel):
    """Structured package for manual live-trading approval from a paper candidate."""

    run_id: str
    research_workspace_id: str
    generated_at: str
    ready_for_live: bool = False
    status: str
    approval_required: bool = True
    expires_at: str | None = None
    paper_workspace_id: str | None = None
    paper_unit_id: str | None = None
    best_strategy_id: str | None = None
    best_strategy_name: str | None = None
    symbol: str
    symbol_name: str = ""
    timeframe: str = "1d"
    timeframe_n: int = 1
    target_sharpe: float
    best_sharpe: float = 0.0
    best_metrics: dict[str, Any] = Field(default_factory=dict)
    asset_specs: dict[str, Any] = Field(default_factory=dict)
    backtest_environment: dict[str, Any] = Field(default_factory=dict)
    robustness_validation: dict[str, Any] = Field(default_factory=dict)
    paper_review_status: str | None = None
    paper_reviewed_at: str | None = None
    paper_review_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    paper_monitoring_plan: list[dict[str, Any]] = Field(default_factory=list)
    live_readiness_checklist: list[dict[str, Any]] = Field(default_factory=list)
    approvals_required: list[dict[str, Any]] = Field(default_factory=list)
    deployment_blockers: list[str] = Field(default_factory=list)
    approval_status: str | None = None
    approval: AIStrategyLiveHandoffApprovalRecord | None = None
    handoff: dict[str, Any] = Field(default_factory=dict)
    pipeline: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)


class AIStrategyLiveTradingPrepareRequest(BaseModel):
    """Request to materialize an approved live handoff as a locked live unit."""

    research_workspace_id: str | None = Field(None, description="Workspace that stores the run")
    trading_workspace_id: str | None = Field(None, description="Existing live trading workspace")
    live_workspace_name: str | None = Field(None, description="Name for generated live workspace")
    gateway_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Live gateway config; required when persisted handoff credentials are redacted",
    )


class AIStrategyLiveTradingPrepare(BaseModel):
    """Locked live trading workspace/unit prepared from an approved handoff."""

    workspace: WorkspaceResponse
    unit: StrategyUnitResponse
    prepared: bool = False
    handoff: dict[str, Any] | None = None
    next_actions: list[str] = Field(default_factory=list)


class AIStrategyResearchRunRecord(BaseModel):
    """Compact persisted summary for one AI strategy research run."""

    run_id: str
    prompt: str
    workflow_mode: AIStrategyResearchWorkflowMode = "auto"
    workflow_steps: list[AIStrategyResearchWorkflowStep] = Field(
        default_factory=_default_ai_research_workflow_steps
    )
    symbol: str
    symbol_name: str = ""
    timeframe: str = "1d"
    timeframe_n: int = 1
    start_date: str | None = None
    end_date: str | None = None
    initial_cash: float = 100000.0
    commission: float = 0.001
    annual_days: int = 252
    calc_method: str = "simple"
    weight_mode: str = "equal"
    group_name: str | None = None
    asset_specs: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved exchange/local asset specs used for backtest, paper handoff and valuation",
    )
    backtest_environment: dict[str, Any] = Field(
        default_factory=dict,
        description="Effective cash, commission, multiplier and margin assumptions used by the run",
    )
    knowledge_base_id: str | None = None
    thinking_mode: bool = False
    status: str
    achieved: bool
    target_sharpe: float
    quality_gates: dict[str, Any] = Field(default_factory=dict)
    min_total_trades: int = 0
    max_iterations: int = 0
    backtest_timeout_seconds: float = 600.0
    poll_interval_seconds: float = 2.0
    iteration_count: int = 0
    best_iteration: int | None = None
    best_sharpe: float = 0.0
    best_quality_score: float = 0.0
    best_quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    robustness_validation: dict[str, Any] = Field(default_factory=dict)
    best_diagnostics: dict[str, Any] = Field(default_factory=dict)
    best_metrics: dict[str, Any] = Field(default_factory=dict)
    best_strategy_id: str | None = None
    best_strategy_name: str | None = None
    research_workspace_id: str
    mandate_id: str | None = None
    seed_strategy_id: str | None = None
    continued_from_run_id: str | None = None
    continuation_source: str | None = None
    continuation_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Redacted reason/context used to continue this run from a failed review or prior run",
    )
    paper_workspace_id: str | None = None
    paper_workspace_name: str | None = None
    paper_unit_id: str | None = None
    paper_trading_started: bool = False
    paper_monitoring_plan: list[dict[str, Any]] = Field(default_factory=list)
    paper_handoff: dict[str, Any] = Field(default_factory=dict)
    paper_review_status: str | None = None
    paper_review_ready_for_live: bool = False
    paper_reviewed_at: str | None = None
    paper_review_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    paper_review_next_actions: list[str] = Field(default_factory=list)
    live_readiness_checklist: list[dict[str, Any]] = Field(default_factory=list)
    live_readiness_expires_at: str | None = None
    live_handoff: AIStrategyLiveHandoffPackage | None = None
    live_handoff_approval: AIStrategyLiveHandoffApprovalRecord | None = None
    live_workspace_id: str | None = None
    live_workspace_name: str | None = None
    live_unit_id: str | None = None
    live_trading_prepared: bool = False
    live_trading_prepared_at: str | None = None
    pipeline: dict[str, Any] = Field(default_factory=dict)
    promotion_audit: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Stage-by-stage promotion evidence from research through paper/live readiness",
    )
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
    robustness_validation: dict[str, Any] = Field(default_factory=dict)
    best_diagnostics: dict[str, Any] = Field(default_factory=dict)
    best_metrics: dict[str, Any] = Field(default_factory=dict)
    research_workspace: WorkspaceResponse
    mandate_id: str | None = None
    iterations: list[AIStrategyResearchIteration] = Field(default_factory=list)
    best_strategy: StrategyResponse | None = None
    paper_trading: AIStrategyPaperTradingStart | None = None
    paper_monitoring_plan: list[dict[str, Any]] = Field(default_factory=list)
    pipeline: dict[str, Any] = Field(default_factory=dict)
    promotion_audit: list[dict[str, Any]] = Field(default_factory=list)
    run_record: AIStrategyResearchRunRecord | None = None
    next_actions: list[str] = Field(default_factory=list)
    message: str


class AIStrategyResearchTaskResponse(BaseModel):
    """Async task state for a long-running AI research loop."""

    task_id: str
    status: str
    submitted_at: str
    started_at: str | None = None
    completed_at: str | None = None
    run_id: str | None = None
    research_workspace_id: str | None = None
    mandate_id: str | None = None
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    request_explicit_fields: list[str] = Field(default_factory=list)
    continued_from_run_id: str | None = None
    continuation_source: str | None = None
    continuation_context: dict[str, Any] = Field(default_factory=dict)
    current_stage: str = "queued"
    progress: float = 0.0
    current_iteration: int | None = None
    iteration_count: int = 0
    max_iterations: int | None = None
    latest_iteration: dict[str, Any] | None = None
    best_iteration_payload: dict[str, Any] | None = None
    run_status: str | None = None
    achieved: bool | None = None
    target_sharpe: float | None = None
    best_iteration: int | None = None
    best_sharpe: float | None = None
    best_quality_score: float | None = None
    best_quality_gate_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    robustness_validation: dict[str, Any] = Field(default_factory=dict)
    best_diagnostics: dict[str, Any] = Field(default_factory=dict)
    best_metrics: dict[str, Any] = Field(default_factory=dict)
    best_strategy_id: str | None = None
    best_strategy_name: str | None = None
    asset_specs: dict[str, Any] = Field(default_factory=dict)
    backtest_environment: dict[str, Any] = Field(default_factory=dict)
    paper_workspace_id: str | None = None
    paper_workspace_name: str | None = None
    paper_unit_id: str | None = None
    paper_trading_started: bool = False
    paper_monitoring_plan: list[dict[str, Any]] = Field(default_factory=list)
    paper_handoff: dict[str, Any] = Field(default_factory=dict)
    paper_review_status: str | None = None
    paper_review_ready_for_live: bool = False
    paper_reviewed_at: str | None = None
    paper_review_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    paper_review_next_actions: list[str] = Field(default_factory=list)
    live_readiness_checklist: list[dict[str, Any]] = Field(default_factory=list)
    live_readiness_expires_at: str | None = None
    live_handoff: AIStrategyLiveHandoffPackage | None = None
    live_handoff_approval: AIStrategyLiveHandoffApprovalRecord | None = None
    live_workspace_id: str | None = None
    live_workspace_name: str | None = None
    live_unit_id: str | None = None
    live_trading_prepared: bool = False
    live_trading_prepared_at: str | None = None
    pipeline: dict[str, Any] = Field(default_factory=dict)
    promotion_audit: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    current_backtest_task_id: str | None = None
    cancelled_backtest_task_id: str | None = None
    child_cancelled: bool = False
    error: str | None = None
    message: str = ""
    result: AIStrategyResearchRunResponse | None = None


class AIStrategyResearchTaskListResponse(BaseModel):
    """Current AI strategy research tasks for the authenticated user."""

    total: int
    items: list[AIStrategyResearchTaskResponse] = Field(default_factory=list)


class AIStrategyResearchTaskContinueRequest(BaseModel):
    """Overrides used when continuing a recovered AI research task snapshot."""

    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional AIStrategyResearchRunRequest fields to override when rebuilding "
            "a continuation request from the saved task snapshot"
        ),
    )


class AIStrategyResearchRunContinueRequest(BaseModel):
    """Overrides used when continuing from a persisted AI research run record."""

    overrides: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional AIStrategyResearchRunRequest fields to override when rebuilding "
            "a continuation request from the saved run record"
        ),
    )
