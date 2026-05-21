"""Strategy service (CRUD + template/config loading)."""

import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml

from app.db.sql_repository import SQLRepository
from app.models.strategy import Strategy
from app.schemas.strategy import (
    AIStrategyBacktestSpec,
    AIStrategyDataSourceSpec,
    AIStrategyDraft,
    AIStrategyExecutionPlan,
    ParamSpec,
    StrategyCopilotBacktestRequest,
    StrategyCopilotBacktestResponse,
    StrategyCopilotDraftRequest,
    StrategyCopilotDraftResponse,
    StrategyCopilotRunResult,
    StrategyCreate,
    StrategyDraftWorkspaceAddRequest,
    StrategyDraftWorkspaceAddResponse,
    StrategyListResponse,
    StrategyResponse,
    StrategyTemplate,
    StrategyType,
    StrategyUpdate,
)
from app.utils.response_cache import invalidate_cache

logger = logging.getLogger(__name__)

STRATEGIES_DIR = Path(__file__).resolve().parents[4] / "strategies"


def get_strategy_dir(strategy_id: str) -> Path:
    """Resolve strategy directory path with path traversal protection.

    strategy_id must be in format \"type/name\" (e.g. simulate/cu_macd_atr) or
    \"name\" for backtest-style ids. The resolved path is constrained to
    STRATEGIES_DIR to prevent directory traversal.

    Args:
        strategy_id: Strategy identifier (e.g. backtest/002_dual_ma).

    Returns:
        Path to the strategy directory.

    Raises:
        ValueError: If strategy_id contains path traversal or invalid chars.
    """
    if ".." in strategy_id or strategy_id.startswith("/") or "\\" in strategy_id:
        raise ValueError(f"Invalid strategy_id: {strategy_id}")
    path = (STRATEGIES_DIR / strategy_id).resolve()
    try:
        path.relative_to(STRATEGIES_DIR.resolve())
    except ValueError:
        raise ValueError(f"Strategy path escapes base directory: {strategy_id}") from None
    return path


def _infer_category(name: str, description: str) -> str:
    """Infer strategy category from name and description.

    Args:
        name: Strategy name.
        description: Strategy description.

    Returns:
        Inferred category string (trend, mean_reversion, volatility, etc.).
    """
    text = (name + description).lower()
    if any(
        k in text
        for k in ["ma", "trend", "supertrend", "turtle", "breakout", "momentum", "crossover"]
    ):
        return "trend"
    if any(
        k in text
        for k in [
            "rsi",
            "mean_reversion",
            "reversal",
            "oscillator",
            "overbought",
            "oversold",
            "kdj",
            "stochastic",
        ]
    ):
        return "mean_reversion"
    if any(k in text for k in ["boll", "bollinger", "atr", "volatility", "vix", "chandelier"]):
        return "volatility"
    if any(k in text for k in ["arbitrage", "hedge", "long_short", "pair"]):
        return "arbitrage"
    if any(k in text for k in ["macd", "ema", "signal", "indicator"]):
        return "indicator"
    return "custom"


def _strategy_name_from_prompt(prompt: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(prompt or "")).strip(" \n\t，。,.!?！？")
    if not cleaned:
        return "AI Generated Strategy"
    return f"AI策略 - {cleaned[:24]}"


def _class_name_from_prompt(prompt: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", str(prompt or ""))
    if not tokens:
        return "AIGeneratedStrategy"
    return "".join(token.capitalize() for token in tokens[:4]) + "Strategy"


def _infer_timeframe(prompt: str) -> str | None:
    text = str(prompt or "").lower()
    if any(token in text for token in ["1m", "5m", "15m", "30m", "60m", "分钟"]):
        return "15m"
    if any(token in text for token in ["1h", "4h", "hour", "小时"]):
        return "1h"
    if any(token in text for token in ["日线", "daily", "1d"]):
        return "1d"
    if any(token in text for token in ["周线", "weekly", "1w"]):
        return "1w"
    return None


def _infer_data_source_type(prompt: str) -> str:
    text = str(prompt or "").lower()
    if any(token in text for token in ["akshare", "a股", "沪深", "基金", "期货"]):
        return "csv"
    if any(token in text for token in ["yfinance", "yahoo", "美股", "us stock"]):
        return "csv"
    return "csv"


def _build_ai_param_specs(prompt: str) -> dict[str, ParamSpec]:
    text = str(prompt or "").lower()
    params: dict[str, ParamSpec] = {}

    def add_param(name: str, spec: ParamSpec) -> None:
        if name not in params:
            params[name] = spec

    if any(token in text for token in ["ma", "均线", "crossover", "cross", "trend", "趋势"]):
        add_param(
            "fast_period",
            ParamSpec(type="int", default=10, min=2, max=60, description="Fast moving average period"),
        )
        add_param(
            "slow_period",
            ParamSpec(type="int", default=30, min=10, max=240, description="Slow moving average period"),
        )
    if any(token in text for token in ["rsi", "超卖", "超买"]):
        add_param(
            "rsi_period",
            ParamSpec(type="int", default=14, min=2, max=60, description="RSI lookback period"),
        )
        add_param(
            "oversold",
            ParamSpec(type="float", default=30, min=5, max=50, description="RSI oversold threshold"),
        )
        add_param(
            "overbought",
            ParamSpec(type="float", default=70, min=50, max=95, description="RSI overbought threshold"),
        )
    if any(token in text for token in ["atr", "止损", "volatility", "波动"]):
        add_param(
            "atr_period",
            ParamSpec(type="int", default=14, min=5, max=60, description="ATR calculation period"),
        )
        add_param(
            "atr_stop_multiplier",
            ParamSpec(type="float", default=2.0, min=0.5, max=10.0, description="ATR stop multiplier"),
        )
    if any(token in text for token in ["breakout", "突破", "channel", "唐奇安"]):
        add_param(
            "breakout_period",
            ParamSpec(type="int", default=20, min=5, max=120, description="Breakout lookback period"),
        )
    if not params:
        add_param(
            "lookback_period",
            ParamSpec(type="int", default=20, min=2, max=200, description="Generic lookback period"),
        )
        add_param(
            "signal_threshold",
            ParamSpec(type="float", default=0.0, min=-10.0, max=10.0, description="Generic signal threshold"),
        )

    add_param(
        "risk_pct",
        ParamSpec(type="float", default=0.02, min=0.001, max=0.2, description="Risk budget per trade"),
    )
    return params


def _render_param_default(value: object) -> str:
    if isinstance(value, str):
        return repr(value)
    return str(value)


def build_ai_strategy_draft(prompt: str, references: list[str] | None = None) -> AIStrategyDraft:
    """Build a deterministic fallback strategy draft from natural language input."""
    name = _strategy_name_from_prompt(prompt)
    category = _infer_category(name, prompt)
    class_name = _class_name_from_prompt(prompt)
    params = _build_ai_param_specs(prompt)
    timeframe = _infer_timeframe(prompt)
    prompt_comment = re.sub(r"\s+", " ", str(prompt or "")).strip()
    prompt_comment = prompt_comment.replace('"""', "'''")
    reference_note = ""
    if references:
        reference_note = "\n".join(f"- {title}" for title in references[:3])
    param_lines = "\n".join(
        f"        ('{key}', {_render_param_default(spec.default)}),"
        for key, spec in params.items()
    )
    setup_lines = ["        self.close = self.datas[0].close"]
    if "fast_period" in params:
        setup_lines.extend(
            [
                "        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.p.fast_period)",
                "        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.p.slow_period)",
            ]
        )
    if "rsi_period" in params:
        setup_lines.append(
            "        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)"
        )
    if "atr_period" in params:
        setup_lines.append(
            "        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)"
        )
    setup_block = "\n".join(setup_lines)

    code = f'''import backtrader as bt


class {class_name}(bt.Strategy):
    """
    Auto-generated draft from Backtrader Web AI Copilot.
    Original prompt: {prompt_comment}
    """

    params = (
{param_lines}
    )

    def __init__(self):
{setup_block}

    def next(self):
        # TODO: Refine the trading rules below according to the original prompt.
        # Prompt: {prompt_comment}
        if not self.position:
            # TODO: implement entry rules
            pass
        else:
            # TODO: implement exit / stop / take-profit rules
            pass
'''

    rationale = (
        f"该草案基于自然语言需求“{prompt_comment[:80]}”生成，已按 {category} 类策略补齐常见参数和 Backtrader 类骨架。"
    )
    if reference_note:
        rationale += f"\n参考过的知识库文档：\n{reference_note}"

    return AIStrategyDraft(
        name=name,
        description=f"AI Copilot 根据自然语言需求生成的 {category} 策略草案。",
        code=code,
        params=params,
        category=category,
        assumptions=[
            "默认使用标准 OHLCV K 线数据，并按信号所在 bar 后续执行。",
            "默认未加入滑点、停牌、涨跌停和撮合冲击等市场微观结构约束。",
        ],
        risk_points=[
            "需要验证参数稳定性，避免仅在样本内表现良好。",
            "需要结合交易成本与回撤约束评估真实可执行性。",
        ],
        data_source=AIStrategyDataSourceSpec(
            type=_infer_data_source_type(prompt_comment),
            symbol=None,
            symbol_name=None,
            timeframe=timeframe or "1d",
            timeframe_n=1,
            start_date=None,
            end_date=None,
            adjustment=None,
        ),
        backtest_defaults=AIStrategyBacktestSpec(
            initial_cash=100000.0,
            commission=0.001,
            annual_days=252,
            calc_method="simple",
            weight_mode="equal",
        ),
        execution_plan=AIStrategyExecutionPlan(
            workspace_type="research",
            group_name=name,
            run_parallel=False,
        ),
        rationale=rationale,
        next_steps=[
            "补充 entry / exit 条件与风险控制逻辑",
            "根据目标市场调整默认参数与时间框架",
            "在回测工作区中创建单元并验证收益/回撤/交易频率",
        ],
        suggested_symbol=None,
        suggested_timeframe=timeframe,
    )


def render_ai_strategy_draft_answer(draft: AIStrategyDraft) -> str:
    """Render a human-readable chat answer from a strategy draft."""
    params_summary = ", ".join(
        f"{name}={spec.default}" for name, spec in draft.params.items()
    ) or "无"
    next_steps = "\n".join(f"- {step}" for step in draft.next_steps) or "- 无"
    timeframe = draft.suggested_timeframe or "待确认"
    rationale = draft.rationale or "基于自然语言需求自动生成。"
    data_source_type = draft.data_source.type if draft.data_source else "待确认"
    initial_cash = (
        draft.backtest_defaults.initial_cash if draft.backtest_defaults else 100000.0
    )
    commission = draft.backtest_defaults.commission if draft.backtest_defaults else 0.001
    return (
        f"已为你生成一个可继续完善的 Backtrader 策略草案。\n\n"
        f"策略名称：{draft.name}\n"
        f"策略分类：{draft.category}\n"
        f"建议周期：{timeframe}\n"
        f"建议数据源：{data_source_type}\n"
        f"默认回测：初始资金 {initial_cash:.2f} / 手续费 {commission}\n"
        f"关键参数：{params_summary}\n\n"
        f"说明：{rationale}\n\n"
        "代码骨架：\n"
        f"```python\n{draft.code}\n```\n\n"
        f"下一步建议：\n{next_steps}"
    )


def _strategy_param_defaults(params: dict[str, ParamSpec]) -> dict[str, object]:
    return {name: spec.default for name, spec in params.items()}


def _sync_user_strategy_runtime_files(strategy: StrategyResponse) -> None:
    """Persist a user strategy into runtime-consumable files under strategies/."""
    strategy_dir = get_strategy_dir(strategy.id)
    strategy_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "strategy": {
            "name": strategy.name,
            "description": strategy.description or "",
        },
        "params": _strategy_param_defaults(strategy.params),
        "data": {
            "data_type": strategy.category or "custom",
            "category": strategy.category or "custom",
            "symbol": "",
            "symbol_name": "",
            "timeframe": "1d",
            "timeframe_n": 1,
        },
        "backtest": {
            "initial_cash": 100000.0,
            "commission": 0.001,
        },
    }
    with (strategy_dir / "config.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    (strategy_dir / "strategy_generated.py").write_text(strategy.code, encoding="utf-8")


def _scan_strategies_folder(strategy_type: StrategyType) -> list[StrategyTemplate]:
    """Scan strategies/ directory and auto-build strategy template list.

    Args:
        strategy_type: Type of strategy (backtest/simulate/live).

    Returns:
        List of StrategyTemplate objects parsed from strategy directories.
    """
    templates: list[StrategyTemplate] = []

    target_dir = STRATEGIES_DIR / strategy_type.value
    if not target_dir.is_dir():
        logger.warning(f"Strategy directory does not exist: {target_dir}")
        return templates

    for config_path in sorted(target_dir.glob("*/config.yaml")):
        strategy_dir = config_path.parent
        dir_name = strategy_dir.name
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

            strat_info = config.get("strategy", {})
            name = strat_info.get("name", dir_name)
            description = strat_info.get("description", "")
            author = strat_info.get("author", "")

            code_files = list(strategy_dir.glob("strategy_*.py"))
            if not code_files:
                continue
            code = code_files[0].read_text(encoding="utf-8")

            raw_params = config.get("params") or {}
            params: dict[str, ParamSpec] = {}
            for k, v in raw_params.items():
                if isinstance(v, bool):
                    ptype = "bool"
                elif isinstance(v, int):
                    ptype = "int"
                elif isinstance(v, float):
                    ptype = "float"
                else:
                    ptype = "string"
                params[k] = ParamSpec(
                    type=ptype,
                    default=v,
                    min=None,
                    max=None,
                    options=None,
                    description=k,
                )

            category = _infer_category(name, description)

            _bt_config = config.get("backtest", {})
            data_config = config.get("data", {})

            meta_parts = []
            if author:
                meta_parts.append(f"Author: {author}")
            if data_config.get("symbol"):
                meta_parts.append(f"Default Symbol: {data_config['symbol']}")
            full_desc = description
            if meta_parts:
                full_desc += " | " + " | ".join(meta_parts)

            templates.append(
                StrategyTemplate(
                    id=f"{strategy_type.value}/{dir_name}",
                    name=name,
                    description=full_desc,
                    category=category,
                    code=code,
                    params=params,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to scan strategy {dir_name}: {e}")
            continue

    logger.info(f"Loaded {len(templates)} strategy templates from {target_dir}")
    return templates


@lru_cache(maxsize=3)
def _get_templates_for_type(
    strategy_type: StrategyType,
) -> tuple[tuple[StrategyTemplate, ...], dict[str, StrategyTemplate]]:
    """Lazily load and cache strategy templates by type.

    Returns:
        Tuple of (templates list, id->template map).
    """
    templates = _scan_strategies_folder(strategy_type)
    template_map = {t.id: t for t in templates}
    return (tuple(templates), template_map)


def _get_template_map(strategy_type: StrategyType) -> dict[str, StrategyTemplate]:
    """Get cached template map for a strategy type."""
    return _get_templates_for_type(strategy_type)[1]


def get_all_strategy_templates() -> list[StrategyTemplate]:
    """Get all strategy templates (backtest + simulate + live). Lazy-loaded."""
    return (
        list(_get_templates_for_type(StrategyType.backtest)[0])
        + list(_get_templates_for_type(StrategyType.simulate)[0])
        + list(_get_templates_for_type(StrategyType.live)[0])
    )


def get_template_by_id(
    template_id: str, strategy_type: StrategyType | None = None
) -> StrategyTemplate | None:
    """Get strategy template by ID.


    Args:
        template_id: The strategy template identifier.
        strategy_type: Optional strategy type filter.

    Returns:
        StrategyTemplate if found, None otherwise.
    """
    if strategy_type:
        return _get_template_map(strategy_type).get(template_id)

    for st in (StrategyType.backtest, StrategyType.simulate, StrategyType.live):
        tpl = _get_template_map(st).get(template_id)
        if tpl:
            return tpl
    return None


def get_strategy_readme(template_id: str, strategy_type: StrategyType | None = None) -> str | None:
    """Read the strategy's README.md content.

    Args:
        template_id: The strategy template identifier.
        strategy_type: Optional strategy type filter.

    Returns:
        README content as string if found, None otherwise.
    """
    try:
        parts = template_id.split("/", 1)
        if len(parts) == 2:
            readme_path = get_strategy_dir(template_id) / "README.md"
        elif strategy_type:
            readme_path = get_strategy_dir(f"{strategy_type.value}/{template_id}") / "README.md"
        else:
            return None
    except ValueError:
        return None

    if readme_path.is_file():
        return readme_path.read_text(encoding="utf-8")
    return None


class StrategyService:
    """Service for managing user-defined strategies."""

    def __init__(self) -> None:
        """Initialize the StrategyService.

        Attributes:
            strategy_repo: Repository for strategy CRUD operations.
        """
        self.strategy_repo = SQLRepository(Strategy)

    async def create_strategy(
        self, user_id: str, strategy_create: StrategyCreate
    ) -> StrategyResponse:
        """Create a new user strategy.

        Args:
            user_id: The ID of the user creating the strategy.
            strategy_create: Strategy creation data.

        Returns:
            StrategyResponse: The created strategy.
        """
        strategy = Strategy(
            user_id=user_id,
            name=strategy_create.name,
            description=strategy_create.description,
            code=strategy_create.code,
            params={k: v.model_dump() for k, v in strategy_create.params.items()},
            category=strategy_create.category,
        )

        strategy = await self.strategy_repo.create(strategy)
        response = self._to_response(strategy)
        _sync_user_strategy_runtime_files(response)
        await invalidate_cache("strategies")
        return response

    async def generate_copilot_draft(
        self, user_id: str, request: StrategyCopilotDraftRequest
    ) -> StrategyCopilotDraftResponse:
        """Generate a structured strategy draft for the copilot flow."""
        if request.knowledge_base_id:
            from app.services.rag_service import RAGService

            rag_result = await RAGService().ask(
                request.knowledge_base_id,
                user_id,
                request.prompt,
                top_k=10,
                min_similarity=0.0,
                assistant_mode="backtrader_strategy",
                thinking_mode=request.thinking_mode,
            )
            draft_payload = rag_result.get("strategy_draft")
            draft = (
                AIStrategyDraft.model_validate(draft_payload)
                if draft_payload
                else build_ai_strategy_draft(request.prompt)
            )
            answer = rag_result.get("answer") or render_ai_strategy_draft_answer(draft)
            return StrategyCopilotDraftResponse(
                answer=answer,
                strategy_draft=draft,
                citations=rag_result.get("citations") or [],
                context_chunks_used=int(rag_result.get("context_chunks_used") or 0),
                tokens_used=int(rag_result.get("tokens_used") or 0),
                model_id=rag_result.get("model_id"),
                reasoning=rag_result.get("reasoning"),
            )

        draft = build_ai_strategy_draft(request.prompt)
        return StrategyCopilotDraftResponse(
            answer=render_ai_strategy_draft_answer(draft),
            strategy_draft=draft,
            citations=[],
            context_chunks_used=0,
            tokens_used=0,
            model_id=None,
            reasoning=None,
        )

    async def add_copilot_draft_to_workspace(
        self, user_id: str, workspace_id: str, request: StrategyDraftWorkspaceAddRequest
    ) -> StrategyDraftWorkspaceAddResponse | None:
        """Persist a copilot draft and add it into a workspace unit."""
        from app.schemas.workspace import StrategyUnitCreate
        from app.services.workspace_service import WorkspaceService

        workspace_service = WorkspaceService()
        workspace = await workspace_service.get_workspace(workspace_id, user_id)
        if workspace is None:
            return None

        if request.strategy_id:
            strategy = await self.get_strategy(request.strategy_id, user_id)
            if strategy is None:
                return None
            created_strategy = False
        else:
            strategy = await self.create_strategy(
                user_id,
                StrategyCreate(
                    name=request.strategy_draft.name,
                    description=request.strategy_draft.description,
                    code=request.strategy_draft.code,
                    params=request.strategy_draft.params,
                    category=request.strategy_draft.category,
                ),
            )
            created_strategy = True

        _sync_user_strategy_runtime_files(strategy)

        strategy_params = {
            name: spec.default for name, spec in request.strategy_draft.params.items()
        }
        timeframe = (
            request.timeframe
            or request.strategy_draft.data_source.timeframe
            or request.strategy_draft.suggested_timeframe
            or "1d"
        )
        symbol = (
            request.symbol
            or request.strategy_draft.data_source.symbol
            or request.strategy_draft.suggested_symbol
            or ""
        )
        symbol_name = request.symbol_name or symbol
        data_config = {
            "symbol": symbol,
            "symbol_name": symbol_name,
            "timeframe": timeframe,
            "timeframe_n": request.timeframe_n or request.strategy_draft.data_source.timeframe_n,
            "start_date": request.strategy_draft.data_source.start_date,
            "end_date": request.strategy_draft.data_source.end_date,
            "adjustment": request.strategy_draft.data_source.adjustment,
            **request.data_config,
        }

        unit = await workspace_service.create_unit(
            workspace_id,
            user_id,
            StrategyUnitCreate(
                group_name=request.group_name or request.strategy_draft.name,
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                symbol=symbol,
                symbol_name=symbol_name,
                timeframe=timeframe,
                timeframe_n=request.timeframe_n,
                category=request.strategy_draft.category,
                data_config=data_config,
                unit_settings=request.unit_settings,
                params=strategy_params,
                optimization_config=request.optimization_config,
            ),
        )
        if unit is None:
            return None

        return StrategyDraftWorkspaceAddResponse(
            workspace_id=workspace.id,
            created_strategy=created_strategy,
            strategy=strategy,
            unit=unit,
        )

    async def backtest_copilot_draft(
        self, user_id: str, workspace_id: str, request: StrategyCopilotBacktestRequest
    ) -> StrategyCopilotBacktestResponse | None:
        """Persist a copilot draft, add it to workspace, and trigger backtest."""
        from app.schemas.workspace import UnitStatusResponse
        from app.services.workspace_service import WorkspaceService

        workspace_service = WorkspaceService()
        added = await self.add_copilot_draft_to_workspace(user_id, workspace_id, request)
        if added is None:
            return None

        run_results = await workspace_service.run_units(
            workspace_id,
            user_id,
            [added.unit.id],
            parallel=request.parallel,
        )
        run_result_payload = next(
            (item for item in run_results if str(item.get("unit_id")) == added.unit.id),
            None,
        )
        if run_result_payload is None:
            run_result_payload = {
                "unit_id": added.unit.id,
                "task_id": None,
                "status": "failed",
                "error": "Backtest task submission failed",
            }

        unit_status = None
        statuses = await workspace_service.get_units_status(workspace_id, user_id)
        if statuses:
            matched = next((item for item in statuses if str(item.get("id")) == added.unit.id), None)
            if matched:
                unit_status = UnitStatusResponse.model_validate(matched)

        report = None
        report_ready = False
        if (
            request.report_config is not None
            and unit_status is not None
            and str(unit_status.run_status) == "completed"
        ):
            cfg = request.report_config
            report = await workspace_service.get_workspace_report(
                workspace_id,
                user_id,
                start_date=cfg.start_date,
                end_date=cfg.end_date,
                max_cash=cfg.max_cash,
                calc_method=cfg.calc_method,
                annual_days=cfg.annual_days,
                weight_mode=cfg.weight_mode,
                weights=cfg.weights,
            )
            report_ready = report is not None

        return StrategyCopilotBacktestResponse(
            workspace_id=workspace_id,
            created_strategy=added.created_strategy,
            strategy=added.strategy,
            unit=added.unit,
            run_result=StrategyCopilotRunResult.model_validate(run_result_payload),
            unit_status=unit_status,
            report_ready=report_ready,
            report=report,
        )

    async def _get_owned_strategy(self, strategy_id: str, user_id: str) -> Strategy | None:
        strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy or strategy.user_id != user_id:
            return None
        return strategy

    async def get_strategy(
        self, strategy_id: str, user_id: str | None = None
    ) -> StrategyResponse | None:
        """Get strategy details by ID.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: Optional owner identifier used to enforce access control.

        Returns:
            StrategyResponse if found and accessible, None otherwise.
        """
        if user_id is not None:
            strategy = await self._get_owned_strategy(strategy_id, user_id)
        else:
            strategy = await self.strategy_repo.get_by_id(strategy_id)
        if not strategy:
            return None
        return self._to_response(strategy)

    async def update_strategy(
        self, strategy_id: str, user_id: str, strategy_update: StrategyUpdate
    ) -> StrategyResponse | None:
        """Update an existing strategy.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: The ID of the user requesting the update.
            strategy_update: Strategy update data.

        Returns:
            Updated StrategyResponse if successful, None if not found
            or unauthorized.
        """
        strategy = await self._get_owned_strategy(strategy_id, user_id)
        if strategy is None:
            return None

        update_data = {}
        if strategy_update.name is not None:
            update_data["name"] = strategy_update.name
        if strategy_update.description is not None:
            update_data["description"] = strategy_update.description
        if strategy_update.code is not None:
            update_data["code"] = strategy_update.code
        if strategy_update.params is not None:
            update_data["params"] = {k: v.model_dump() for k, v in strategy_update.params.items()}
        if strategy_update.category is not None:
            update_data["category"] = strategy_update.category

        if update_data:
            update_data["updated_at"] = datetime.now(timezone.utc)
            strategy = await self.strategy_repo.update(strategy_id, update_data)
        response = self._to_response(strategy)
        _sync_user_strategy_runtime_files(response)
        await invalidate_cache("strategies")
        return response

    async def delete_strategy(self, strategy_id: str, user_id: str) -> bool:
        """Delete a strategy.

        Args:
            strategy_id: The unique identifier for the strategy.
            user_id: The ID of the user requesting deletion.

        Returns:
            True if deletion succeeded, False if not found or unauthorized.
        """
        strategy = await self._get_owned_strategy(strategy_id, user_id)
        if strategy is None:
            return False

        result = await self.strategy_repo.delete(strategy_id)
        if result:
            await invalidate_cache("strategies")
        return result

    async def list_strategies(
        self, user_id: str, limit: int = 20, offset: int = 0, category: str | None = None
    ) -> StrategyListResponse:
        """List user strategies with optional filtering.

        Args:
            user_id: The ID of the user.
            limit: Maximum number of results to return.
            offset: Number of results to skip.
            category: Optional category filter.

        Returns:
            StrategyListResponse containing total count and list of strategies.
        """
        filters = {"user_id": user_id}
        if category:
            filters["category"] = category

        strategies = await self.strategy_repo.list(filters=filters, skip=offset, limit=limit)
        total = await self.strategy_repo.count(filters=filters)

        items = [self._to_response(s) for s in strategies]

        return StrategyListResponse(total=total, items=items)

    async def get_templates(
        self, strategy_type: StrategyType | None = None
    ) -> list[StrategyTemplate]:
        """Get all available strategy templates.

        Args:
            strategy_type: Optional filter by strategy type.

        Returns:
            List of StrategyTemplate objects.
        """
        if strategy_type == StrategyType.backtest:
            return list(_get_templates_for_type(StrategyType.backtest)[0])
        elif strategy_type == StrategyType.simulate:
            return list(_get_templates_for_type(StrategyType.simulate)[0])
        elif strategy_type == StrategyType.live:
            return list(_get_templates_for_type(StrategyType.live)[0])

        all_templates = (
            list(_get_templates_for_type(StrategyType.backtest)[0])
            + list(_get_templates_for_type(StrategyType.simulate)[0])
            + list(_get_templates_for_type(StrategyType.live)[0])
        )
        return all_templates

    def _to_response(self, strategy: Strategy) -> StrategyResponse:
        """Convert strategy model to response format.

        Args:
            strategy: The Strategy model instance.

        Returns:
            StrategyResponse with formatted data.
        """
        params = {}
        if strategy.params:
            for k, v in strategy.params.items():
                if isinstance(v, ParamSpec):
                    params[k] = v
                elif isinstance(v, dict):
                    params[k] = ParamSpec(**v)
                else:
                    if isinstance(v, bool):
                        ptype = "bool"
                    elif isinstance(v, int):
                        ptype = "int"
                    elif isinstance(v, float):
                        ptype = "float"
                    else:
                        ptype = "string"
                    params[k] = ParamSpec(
                        type=ptype, default=v, min=None, max=None, options=None, description=k
                    )

        return StrategyResponse(
            id=strategy.id,
            user_id=strategy.user_id,
            name=strategy.name,
            description=strategy.description,
            code=strategy.code,
            params=params,
            category=strategy.category,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )
