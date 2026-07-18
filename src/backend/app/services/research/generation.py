"""AI generation prompts, response parsing, and workspace naming helpers."""

# Workflow helpers are injected after every stage is loaded; see research.__init__.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from .shared import *


def _research_workflow_payload(request: AIStrategyResearchRunRequest | None) -> dict[str, Any]:
    if request is None:
        return {}
    return {
        "mode": request.workflow_mode,
        "steps": [
            {
                "key": step,
                "label": _research_workflow_step_label(step),
            }
            for step in request.workflow_steps
        ],
        "review_to_optimization_loop": [
            "策略构思",
            "策略生成",
            "策略回测",
            "策略审查",
            "根据优化建议继续优化策略",
        ],
    }


def _build_research_draft_prompt(request: AIStrategyResearchRunRequest) -> str:
    """Add research-loop constraints to the initial draft prompt."""

    asset_specs = _resolve_research_asset_specs(request)
    context: dict[str, Any] = {
        "objective": request.prompt,
        "workflow": _research_workflow_payload(request),
        "symbol": request.symbol,
        "symbol_name": request.symbol_name or request.symbol,
        "timeframe": request.timeframe,
        "timeframe_n": request.timeframe_n,
        "date_range": {
            "start_date": request.start_date,
            "end_date": request.end_date,
            "out_of_sample_validation": request.out_of_sample_validation,
            "out_of_sample_ratio": request.out_of_sample_ratio,
        },
        "quality_gates": _quality_gates_payload(request),
        "backtest_environment": _request_backtest_environment(request, asset_specs),
        "asset_specs": _summarize_asset_specs_for_prompt(asset_specs),
        "paper_trading_handoff": {
            "enabled_after_success": request.start_paper_trading,
            "monitoring_metrics": [
                "rolling_sharpe",
                "max_drawdown",
                "closed_trades",
                "slippage_and_commission_delta",
                "valuation_confidence",
            ],
        },
        "strategy_requirements": [
            "生成完整可运行的 Backtrader Strategy 代码",
            "包含明确入场、出场、仓位和止损/止盈逻辑",
            "next 方法必须包含真实 self.buy/self.sell/self.close 或 order_target_* 调用",
            "参数默认值必须与 params 描述一致，方便后续自动改进",
            "避免未来函数、不可执行交易假设和只依赖单一样本内收益",
            "若资产规格包含合约乘数、保证金或手续费，策略说明中必须提示对应风险",
        ],
    }
    return (
        f"{request.prompt.strip()}\n\n"
        "AI策略投研上下文(JSON):\n"
        f"{json.dumps(context, ensure_ascii=False, sort_keys=True)}\n\n"
        "请按上述上下文生成第一版策略草案；后续系统会自动回测、评估质量门槛、"
        "审查失败原因、根据优化建议继续改进，并在达标后进入模拟交易。"
    )


def _summarize_asset_specs_for_prompt(
    asset_specs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    keys = (
        "symbol",
        "exchange",
        "asset_type",
        "instrument_type",
        "product",
        "multiplier",
        "contract_multiplier",
        "contract_size",
        "contract_value",
        "ctVal",
        "ctMult",
        "margin_rate",
        "margin",
        "long_margin_rate",
        "short_margin_rate",
        "margin_initial",
        "margin_maintenance",
        "leverage",
        "max_leverage",
        "commission_rate",
        "commission",
        "open_commission_rate",
        "close_commission_rate",
        "close_today_commission_rate",
        "commission_amount",
        "maker_commission_rate",
        "taker_commission_rate",
        "tick_size",
        "lot_size",
        "min_order_size",
        "base_asset",
        "quote_asset",
        "last_price",
        "latest_price",
        "settlement_price",
        "asset_spec_source",
        "source",
        "fee_source",
        "margin_source",
    )
    for symbol, spec in asset_specs.items():
        if not isinstance(spec, dict):
            continue
        selected = {key: spec[key] for key in keys if spec.get(key) not in (None, "")}
        if selected:
            summary[str(symbol)] = selected
    return summary


def _build_improvement_messages(
    draft: AIStrategyDraft,
    *,
    iteration: int,
    metrics: dict[str, Any],
    target_sharpe: float,
    quality_gate_failures: list[str] | None,
    request: AIStrategyResearchRunRequest | None,
) -> list[dict[str, str]]:
    objective = request.prompt if request is not None else ""
    symbol = request.symbol if request is not None else draft.suggested_symbol or ""
    timeframe = request.timeframe if request is not None else draft.suggested_timeframe or ""
    failures = [str(item) for item in quality_gate_failures or []]
    asset_specs = _resolve_research_asset_specs(request) if request is not None else {}
    research_feedback = _dict_payload(metrics.get("research_feedback"))
    suggested_plan = _string_list(metrics.get("improvement_plan"))
    if not suggested_plan:
        suggested_plan = _string_list(research_feedback.get("improvement_plan"))
    if not suggested_plan and request is not None:
        suggested_plan = _improvement_plan_from_failures(
            request,
            metrics=metrics,
            run_status="completed",
            quality_gate_failures=failures,
            failure_categories=_failure_categories(failures, "completed", None),
        )
    return [
        {
            "role": "system",
            "content": (
                "你是 AI for Investor 的量化策略研究员。你只输出 JSON，不输出 Markdown。"
                "你需要基于上一轮回测指标改进 Backtrader 策略脚本，目标是提高样本内 Sharpe，"
                "同时降低过拟合和不可执行风险。返回字段必须是："
                "name, description, code, params, category, assumptions, risk_points, "
                "next_steps, notes。code 必须是完整 Python Backtrader 策略代码。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "objective": objective,
                    "workflow": _research_workflow_payload(request) if request is not None else {},
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "iteration_to_create": iteration + 1,
                    "target_sharpe": target_sharpe,
                    "quality_gates": _quality_gates_payload(request) if request else {},
                    "quality_gate_failures": failures,
                    "asset_specs": _summarize_asset_specs_for_prompt(asset_specs),
                    "backtest_environment": _request_backtest_environment(request, asset_specs)
                    if request is not None
                    else {},
                    "continuation_context": dict(request.continuation_context or {})
                    if request is not None
                    else {},
                    "previous_metrics": metrics,
                    "research_feedback": research_feedback,
                    "suggested_improvement_plan": suggested_plan,
                    "current_draft": draft.model_dump(mode="json"),
                    "rules": [
                        "不要删除风控逻辑；如果调整参数，请同步 params 和 code 中 params 默认值。",
                        "如果新增指标或状态变量，必须保证 Backtrader Strategy 类可独立运行。",
                        "优先执行 suggested_improvement_plan 中的具体改进方向。",
                        "research_feedback 是服务端结构化诊断，优先级高于自由文本指标。",
                        "优先针对 quality_gate_failures 中列出的失败原因改进策略。",
                        "本轮必须体现策略审查后的优化建议，并输出下一轮可回测的完整策略。",
                        "如果失败原因是代码校验失败，必须先修复语法、安全检查和 bt.Strategy 类定义。",
                        "如果 total_trades/closed trades 不达标，必须加入能触发 self.close() 的止损、止盈、"
                        "反向信号或最长持仓 bars 退出，不能只依赖未平仓浮盈。",
                        "若 asset_specs 包含合约乘数、保证金、杠杆或手续费，改稿必须保留这些交易约束。",
                        "notes 用中文说明具体改动和为什么可能改善 Sharpe/回撤/交易次数。",
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ]


def _parse_ai_improvement_payload(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        raise ValueError("AI provider returned empty strategy improvement")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI provider did not return a JSON object")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI strategy improvement payload is not an object")
    return payload


def _merge_ai_improvement(
    draft: AIStrategyDraft,
    payload: dict[str, Any],
    *,
    iteration: int,
    model_id: str,
    provider: str | None = None,
    total_tokens: int | None = None,
) -> StrategyImprovement:
    improved = draft.model_copy(deep=True)
    name = _optional_text(payload.get("name"))
    if name:
        improved.name = _bounded_name(name, 100)
    else:
        base_name = re.sub(r"\s+v\d+$", "", improved.name).strip()
        improved.name = f"{base_name} v{iteration + 1}"[:100]

    description = _optional_text(payload.get("description"))
    if description:
        improved.description = description

    code = _optional_text(payload.get("code"))
    if code:
        _validate_strategy_code_draft(code)
        improved.code = code

    incoming_params = _coerce_param_specs(payload.get("params"))
    if incoming_params:
        params = _merge_param_specs(improved.params, incoming_params)
        improved.params = params
        improved.code = _rewrite_code_param_defaults(improved.code, improved.params)
        _validate_strategy_code_draft(improved.code)

    category = _optional_text(payload.get("category"))
    if category:
        improved.category = category

    assumptions = _coerce_text_list(payload.get("assumptions"))
    if assumptions:
        improved.assumptions = assumptions

    risk_points = _coerce_text_list(payload.get("risk_points"))
    if risk_points:
        improved.risk_points = risk_points

    next_steps = _coerce_text_list(payload.get("next_steps"))
    if next_steps:
        improved.next_steps = next_steps

    notes = _coerce_text_list(payload.get("notes"))
    if not notes:
        notes = [f"AI模型 {model_id} 已生成第 {iteration + 1} 版策略改稿"]
    else:
        notes = [f"AI模型 {model_id} 改稿", *notes]
    metadata = {
        "source": "ai_model",
        "provider": provider or "unknown",
        "model_id": model_id,
    }
    if total_tokens is not None:
        metadata["total_tokens"] = int(total_tokens)
    return StrategyImprovement(draft=improved, notes=notes, metadata=metadata)


def _initial_generation_metadata_from_response(
    response: Any,
    *,
    source: str,
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": source,
        "provider": "strategy_copilot",
        "knowledge_base_id": request.knowledge_base_id,
        "thinking_mode": bool(request.thinking_mode),
    }
    model_id = str(getattr(response, "model_id", "") or "").strip()
    if model_id:
        metadata["model_id"] = model_id
    tokens_used = _optional_gate_int(getattr(response, "tokens_used", None))
    if tokens_used is not None:
        metadata["total_tokens"] = tokens_used
    return _strategy_generation_metadata(metadata)


def _seed_generation_metadata(request: AIStrategyResearchRunRequest) -> dict[str, Any]:
    if request.continue_from_run_id:
        return _strategy_generation_metadata(
            {
                "source": "continued_run_seed",
                "provider": "history",
                "run_id": request.continue_from_run_id,
                "strategy_id": request.seed_strategy_id,
            }
        )
    if request.seed_strategy_id:
        return _strategy_generation_metadata(
            {
                "source": "seed_strategy",
                "provider": "strategy_store",
                "strategy_id": request.seed_strategy_id,
            }
        )
    return _strategy_generation_metadata({"source": "local_seed", "provider": "local"})


def _strategy_generation_metadata(
    metadata: dict[str, Any] | None,
    *,
    phase: str | None = None,
    iteration: int | None = None,
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        metadata = {}
    allowed = {
        "source",
        "provider",
        "model_id",
        "total_tokens",
        "fallback_reason",
        "failed_ai_provider",
        "failed_ai_model",
        "knowledge_base_id",
        "thinking_mode",
        "run_id",
        "strategy_id",
        "phase",
    }
    result: dict[str, Any] = {}
    for key in allowed:
        value = metadata.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, bool):
            result[key] = value
        elif isinstance(value, (int, float)):
            result[key] = value
        else:
            result[key] = str(value)
    if phase:
        result["phase"] = phase
    if iteration is not None:
        result["iteration"] = int(iteration)
    return result


def _coerce_param_specs(value: Any) -> dict[str, ParamSpec]:
    if not isinstance(value, dict):
        return {}
    params: dict[str, ParamSpec] = {}
    for name, raw in value.items():
        key = str(name or "").strip()
        if not key:
            continue
        if isinstance(raw, ParamSpec):
            params[key] = raw
        elif isinstance(raw, dict):
            try:
                params[key] = ParamSpec.model_validate(raw)
            except Exception:
                if "default" in raw:
                    params[key] = ParamSpec(default=raw.get("default"))
        else:
            params[key] = ParamSpec(default=raw)
    return params


def _merge_param_specs(
    base: dict[str, ParamSpec],
    incoming: dict[str, ParamSpec],
) -> dict[str, ParamSpec]:
    merged = {key: spec.model_copy(deep=True) for key, spec in base.items()}
    for key, spec in incoming.items():
        next_spec = spec.model_copy(deep=True)
        if _param_default_missing(next_spec.default):
            existing = merged.get(key)
            if existing is None or _param_default_missing(existing.default):
                continue
            next_spec.default = existing.default
        merged[key] = next_spec
    return merged


def _param_default_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _coerce_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _metric_float(metrics: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in metrics and metrics[key] not in (None, ""):
            try:
                return float(metrics[key])
            except (TypeError, ValueError):
                continue
    return default


def _metric_int(metrics: dict[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in metrics and metrics[key] not in (None, ""):
            try:
                return int(float(metrics[key]))
            except (TypeError, ValueError):
                continue
    return default


def _param_float(spec: ParamSpec, default: float) -> float:
    try:
        return float(spec.default)
    except (TypeError, ValueError):
        return default


def _param_int(spec: ParamSpec, default: int) -> int:
    try:
        return int(float(spec.default))
    except (TypeError, ValueError):
        return default


def _set_param_default(params: dict[str, ParamSpec], key: str, value: Any) -> None:
    spec = params.get(key)
    if spec is not None:
        spec.default = value


def _rewrite_code_param_defaults(code: str, params: dict[str, ParamSpec]) -> str:
    text = str(code or "")
    for key, spec in params.items():
        rendered = render_param_default(spec.default)
        pattern = re.compile(rf"\('{re.escape(key)}'\s*,\s*[^)]+\)")
        text = pattern.sub(f"('{key}', {rendered})", text)
    return text


def _ensure_code_param_defaults(
    code: str,
    params: dict[str, ParamSpec],
) -> tuple[str, set[str]]:
    text = _rewrite_code_param_defaults(code, params)
    available = {key for key in params if re.search(rf"\('{re.escape(key)}'\s*,", text)}
    missing = [key for key in params if key not in available]
    if not missing:
        return text, available

    multiline = re.search(r"(?m)^([ \t]*)params\s*=\s*\(\s*$", text)
    if multiline:
        indent = multiline.group(1)
        entries = "".join(
            f"{indent}    ('{key}', {render_param_default(params[key].default)}),\n"
            for key in missing
        )
        text = f"{text[: multiline.end()]}\n{entries}{text[multiline.end() :]}"
        return text, {key for key in params if re.search(rf"\('{re.escape(key)}'\s*,", text)}

    single_line = re.search(r"(?m)^([ \t]*)params\s*=\s*\((.*)\)\s*$", text)
    if single_line:
        indent = single_line.group(1)
        existing = single_line.group(2).strip()
        existing_lines = f"{indent}    {existing}\n" if existing else ""
        entries = "".join(
            f"{indent}    ('{key}', {render_param_default(params[key].default)}),\n"
            for key in missing
        )
        replacement = f"{indent}params = (\n{existing_lines}{entries}{indent})"
        text = f"{text[: single_line.start()]}{replacement}{text[single_line.end() :]}"
        return text, {key for key in params if re.search(rf"\('{re.escape(key)}'\s*,", text)}

    return text, available


def _bounded_name(value: str, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_length:
        return text or "AI策略投研"
    return text[: max_length - 1].rstrip() + "…"


def _workspace_symbol_label(request: AIStrategyResearchRunRequest) -> str:
    symbol = str(request.symbol or "").strip()
    symbol_name = str(request.symbol_name or "").strip()
    display_symbol = symbol.upper() if re.search(r"[A-Za-z]", symbol) else symbol
    if symbol_name and symbol and symbol_name.lower() != symbol.lower():
        return f"{symbol_name}({display_symbol})"
    return (
        symbol_name.upper()
        if symbol_name and symbol_name.lower() == symbol.lower()
        else (symbol_name or display_symbol or "未指定标的")
    )


def _workspace_timeframe_label(request: AIStrategyResearchRunRequest) -> str:
    timeframe = str(request.timeframe or "").strip() or "1d"
    timeframe_n = int(request.timeframe_n or 1)
    if timeframe_n <= 1:
        return timeframe
    if timeframe[:1].isdigit():
        return f"{timeframe_n}x{timeframe}"
    return f"{timeframe_n}{timeframe}"


def _workspace_objective_label(prompt: str | None) -> str:
    text = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not text:
        return "自动策略研究"
    text = re.split(r"专业流水线[:：]", text, maxsplit=1)[0].strip()
    text = re.split(r"运行口径[:：]", text, maxsplit=1)[0].strip()
    text = re.sub(
        r"^请为\s*.+?生成一套\s*.+?级别的可执行\s*Backtrader\s*策略[，,。.]?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(r"并自动迭代回测直到达到质量门槛[，,。.]?", "", text).strip()
    text = re.sub(r"^请(生成|设计|构建|实现)", "", text).strip()
    text = text.strip(" -_，,。.")
    if not text or len(text) < 4:
        return "自动策略研究"
    first_sentence = re.split(r"[。；;]", text, maxsplit=1)[0].strip()
    return _bounded_name(first_sentence or text, 24)


def _research_workspace_name(request: AIStrategyResearchRunRequest) -> str:
    return _bounded_name(
        " - ".join(
            [
                "AI投研",
                _workspace_symbol_label(request),
                _workspace_timeframe_label(request),
                _workspace_objective_label(request.prompt),
            ]
        ),
        80,
    )


def _paper_workspace_name(
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
) -> str:
    strategy_name = _bounded_name(best_iteration.strategy.name, 24)
    return _bounded_name(
        " - ".join(
            [
                "AI模拟",
                _workspace_symbol_label(request),
                _workspace_timeframe_label(request),
                strategy_name,
            ]
        ),
        80,
    )


__all__ = tuple(
    name
    for name, value in globals().items()
    if callable(value) and getattr(value, "__module__", None) == __name__
)
