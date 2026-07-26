"""Research draft construction and continuation-state helpers."""

# Workflow helpers are injected after every stage is loaded; see research.__init__.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from .shared import *


def _draft_from_strategy(
    strategy: StrategyResponse,
    request: AIStrategyResearchRunRequest,
) -> AIStrategyDraft:
    return AIStrategyDraft(
        name=strategy.name,
        description=strategy.description or f"继续投研已有策略 {strategy.name}",
        code=strategy.code,
        params=strategy.params,
        category=strategy.category,
        assumptions=[
            "本轮从已有策略继续自动投研，保留上一版策略代码作为初始候选。",
        ],
        risk_points=[
            "继续投研会复用上一版策略结构，仍需关注样本内过拟合和样本外稳定性。",
        ],
        data_source=AIStrategyDataSourceSpec(
            type="workspace",
            symbol=request.symbol,
            symbol_name=request.symbol_name or request.symbol,
            timeframe=request.timeframe,
            timeframe_n=request.timeframe_n,
            start_date=request.start_date,
            end_date=request.end_date,
        ),
        backtest_defaults=AIStrategyBacktestSpec(
            initial_cash=request.initial_cash,
            commission=request.commission,
            annual_days=request.annual_days,
            calc_method=request.calc_method,
            weight_mode=request.weight_mode,
        ),
        execution_plan=AIStrategyExecutionPlan(
            workspace_type="research",
            group_name=request.group_name or strategy.name,
            run_parallel=False,
        ),
        rationale=f"Seeded from strategy {strategy.id}",
        next_steps=[
            "先回测上一版最佳策略作为 continuation baseline",
            "如未通过质量门槛，再基于失败原因继续自动改稿",
        ],
        suggested_symbol=request.symbol,
        suggested_timeframe=request.timeframe,
    )


def _normalize_research_draft(
    draft: AIStrategyDraft,
    request: AIStrategyResearchRunRequest,
) -> AIStrategyDraft:
    """Keep generated/improved drafts aligned with the active research run."""

    draft = _apply_asset_sizing_params_to_draft(draft, request)
    return draft.model_copy(
        update={
            "data_source": AIStrategyDataSourceSpec(
                type=draft.data_source.type if draft.data_source else "workspace",
                symbol=request.symbol,
                symbol_name=request.symbol_name or request.symbol,
                timeframe=request.timeframe,
                timeframe_n=request.timeframe_n,
                start_date=request.start_date,
                end_date=request.end_date,
                adjustment=draft.data_source.adjustment if draft.data_source else None,
            ),
            "backtest_defaults": _research_backtest_defaults(request),
            "execution_plan": AIStrategyExecutionPlan(
                workspace_type="research",
                group_name=request.group_name
                or (draft.execution_plan.group_name if draft.execution_plan else None)
                or draft.name,
                run_parallel=False,
            ),
            "assumptions": list(
                dict.fromkeys(
                    [
                        *list(draft.assumptions or []),
                        (
                            f"本轮投研固定使用 {request.symbol}"
                            f"（{request.symbol_name or request.symbol}）"
                            f" / {request.timeframe_n}{request.timeframe} 数据。"
                        ),
                    ]
                )
            ),
            "risk_points": list(
                dict.fromkeys(
                    [
                        *list(draft.risk_points or []),
                        "策略评估必须使用本轮投研配置的资金、手续费、合约规格和质量门槛。",
                    ]
                )
            ),
            "next_steps": list(
                dict.fromkeys(
                    [
                        "运行投研回测并检查 Sharpe、回撤、交易次数和样本外验证。",
                        "未达标时按质量门槛失败原因自动生成下一版策略。",
                        "达标后进入模拟交易并复核成交成本、持仓估值和资产规格。",
                        *list(draft.next_steps or []),
                    ]
                )
            ),
            "suggested_symbol": request.symbol,
            "suggested_timeframe": request.timeframe,
        }
    )


def _apply_asset_sizing_params_to_draft(
    draft: AIStrategyDraft,
    request: AIStrategyResearchRunRequest,
) -> AIStrategyDraft:
    asset_specs = _resolve_research_asset_specs(request)
    primary = next((value for value in asset_specs.values() if isinstance(value, dict)), None)
    if not primary:
        return draft

    sizing_params: dict[str, ParamSpec] = {}
    multiplier = _first_asset_spec_number(
        primary,
        "multiplier",
        "contract_multiplier",
        "contract_size",
        "contract_value",
        "ctVal",
        "ctMult",
    )
    margin_rate = _first_asset_spec_number(
        primary,
        "margin_rate",
        "margin",
        "long_margin_rate",
        "short_margin_rate",
        "margin_initial",
    )
    if multiplier is not None and multiplier > 0:
        sizing_params["contract_multiplier"] = ParamSpec(
            type="float",
            default=float(multiplier),
            min=0.000001,
            max=max(float(multiplier) * 10.0, 1000000.0),
            description="Contract multiplier resolved from asset metadata",
        )
    if margin_rate is not None and margin_rate >= 0:
        sizing_params["margin_rate"] = ParamSpec(
            type="float",
            default=float(margin_rate),
            min=0.0,
            max=max(float(margin_rate) * 10.0, 10.0),
            description="Initial margin rate resolved from asset metadata",
        )
    if not sizing_params:
        return draft

    code, code_param_names = _ensure_code_param_defaults(draft.code, sizing_params)
    params = {key: value.model_copy(deep=True) for key, value in draft.params.items()}
    for key, spec in sizing_params.items():
        if key in code_param_names:
            params[key] = spec
    if params == draft.params and code == draft.code:
        return draft
    return draft.model_copy(update={"params": params, "code": code})


def _ensure_runnable_initial_draft(
    draft: AIStrategyDraft,
    request: AIStrategyResearchRunRequest,
) -> tuple[AIStrategyDraft, list[str]]:
    return _ensure_runnable_research_draft(
        draft,
        request,
        failure_note_prefix="AI初始策略代码不可运行",
    )


def _ensure_runnable_seed_draft(
    draft: AIStrategyDraft,
    request: AIStrategyResearchRunRequest,
) -> tuple[AIStrategyDraft, list[str]]:
    return _ensure_runnable_research_draft(
        draft,
        request,
        failure_note_prefix="种子策略代码不可运行",
    )


def _ensure_runnable_research_draft(
    draft: AIStrategyDraft,
    request: AIStrategyResearchRunRequest,
    *,
    failure_note_prefix: str,
) -> tuple[AIStrategyDraft, list[str]]:
    try:
        _validate_strategy_code_draft(draft.code)
        return draft, []
    except ValueError as exc:
        fallback = _normalize_research_draft(build_ai_strategy_draft(request.prompt), request)
        return fallback, [
            f"{failure_note_prefix}，已使用本地可运行草案继续投研：{exc}",
        ]


def _research_backtest_defaults(request: AIStrategyResearchRunRequest) -> AIStrategyBacktestSpec:
    commission = request.commission
    if not _request_has_explicit_commission(request):
        asset_specs = _resolve_research_asset_specs(request)
        primary = next((value for value in asset_specs.values() if isinstance(value, dict)), None)
        if primary:
            asset_commission = _first_asset_spec_number(
                primary,
                "commission",
                "commission_rate",
                "open_commission_rate",
                "taker_commission_rate",
                "maker_commission_rate",
            )
            if asset_commission is not None:
                commission = max(asset_commission, 0.0)
    return AIStrategyBacktestSpec(
        initial_cash=request.initial_cash,
        commission=commission,
        annual_days=request.annual_days,
        calc_method=request.calc_method,
        weight_mode=request.weight_mode,
    )


def _best_iteration_payload(record: AIStrategyResearchRunRecord) -> dict[str, Any] | None:
    for item in record.iterations:
        if int(item.get("iteration") or 0) == int(record.best_iteration or 0):
            return dict(item)
    candidates = [
        dict(item)
        for item in record.iterations
        if isinstance(item, dict) and _iteration_payload_has_strategy_snapshot(item)
    ]
    if not candidates:
        candidates = [dict(item) for item in record.iterations if isinstance(item, dict)]
    if not candidates:
        return None
    return max(candidates, key=_iteration_payload_rank)


def _iteration_payload_has_strategy_snapshot(payload: dict[str, Any]) -> bool:
    if _strategy_id_from_iteration_payload(payload):
        return True
    snapshot = payload.get("strategy_snapshot")
    if isinstance(snapshot, dict) and str(snapshot.get("code") or "").strip():
        return True
    return bool(str(payload.get("strategy_code") or payload.get("code") or "").strip())


def _iteration_payload_rank(payload: dict[str, Any]) -> tuple[int, float, float, int, int]:
    metrics = dict(payload.get("metrics") or {}) if isinstance(payload.get("metrics"), dict) else {}
    passed = _payload_flag(payload.get("passed"))
    quality_score = _optional_gate_number(payload.get("quality_score")) or 0.0
    sharpe = _optional_gate_number(payload.get("sharpe_ratio"))
    if sharpe is None:
        sharpe = _metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    total_trades = _optional_gate_int(payload.get("total_trades"))
    if total_trades is None:
        total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    iteration = _optional_gate_int(payload.get("iteration")) or 0
    return (
        1 if passed else 0,
        quality_score,
        sharpe,
        total_trades,
        -iteration,
    )


def _payload_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed"}
    return bool(value)


def _continuation_runtime_updates(
    record: AIStrategyResearchRunRecord,
    request: AIStrategyResearchRunRequest,
    explicit_fields: set[str],
) -> dict[str, Any]:
    """Restore runtime assumptions from a previous run unless the caller overrides them."""

    runtime_context = _record_runtime_context(record)
    asset_specs = _dict_payload(runtime_context.get("asset_specs"))
    backtest_environment = _dict_payload(runtime_context.get("backtest_environment"))
    payload = _best_iteration_payload(record) or {}
    unit_snapshot = _dict_payload(payload.get("unit_snapshot"))
    updates: dict[str, Any] = {}

    if "data_config" not in explicit_fields:
        data_config = _runtime_mapping_from_snapshot(unit_snapshot, "data_config")
        data_config.update(dict(request.data_config or {}))
        if asset_specs:
            _merge_contract_metadata(data_config, asset_specs)
        if data_config:
            updates["data_config"] = data_config

    if "unit_settings" not in explicit_fields:
        unit_settings = _runtime_mapping_from_snapshot(unit_snapshot, "unit_settings")
        unit_settings.update(dict(request.unit_settings or {}))
        if asset_specs:
            _merge_contract_metadata(unit_settings, asset_specs)
        if backtest_environment:
            for key in (
                "initial_cash",
                "commission",
                "annual_days",
                "calc_method",
                "weight_mode",
                "multiplier",
                "margin",
                "asset_spec_source",
            ):
                value = backtest_environment.get(key)
                if value not in (None, ""):
                    unit_settings[key] = value
        if unit_settings:
            updates["unit_settings"] = unit_settings

    if "optimization_config" not in explicit_fields:
        optimization_config = _runtime_mapping_from_snapshot(unit_snapshot, "optimization_config")
        optimization_config.update(dict(request.optimization_config or {}))
        if optimization_config:
            updates["optimization_config"] = optimization_config

    if "gateway_config" not in explicit_fields:
        gateway_config = _dict_payload(_omit_sensitive_handoff(unit_snapshot.get("gateway_config")))
        gateway_config.update(_dict_payload(runtime_context.get("gateway_config")))
        gateway_config.update(_dict_payload(request.gateway_config))
        if gateway_config:
            updates["gateway_config"] = gateway_config

    return updates


def _runtime_mapping_from_snapshot(unit_snapshot: dict[str, Any], key: str) -> dict[str, Any]:
    value = unit_snapshot.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _strategy_id_from_iteration_payload(payload: dict[str, Any]) -> str:
    direct = str(payload.get("strategy_id") or "").strip()
    if direct:
        return direct
    snapshot = payload.get("strategy_snapshot")
    if isinstance(snapshot, dict):
        return str(snapshot.get("id") or "").strip()
    return ""


def _fallback_snapshot_strategy_id(record: AIStrategyResearchRunRecord) -> str:
    return f"{record.run_id}-strategy"


def _strategy_from_iteration_snapshot(
    record: AIStrategyResearchRunRecord,
    payload: dict[str, Any],
    *,
    user_id: str,
) -> StrategyResponse | None:
    snapshot = payload.get("strategy_snapshot")
    snapshot_payload = dict(snapshot) if isinstance(snapshot, dict) else {}
    code = str(
        snapshot_payload.get("code") or payload.get("strategy_code") or payload.get("code") or ""
    ).strip()
    if not code:
        return None

    now = datetime.now(timezone.utc)
    created_at = _parse_utc_datetime(str(snapshot_payload.get("created_at") or "")) or now
    updated_at = _parse_utc_datetime(str(snapshot_payload.get("updated_at") or "")) or created_at
    strategy_payload = {
        "id": _strategy_id_from_iteration_payload(payload)
        or record.best_strategy_id
        or _fallback_snapshot_strategy_id(record),
        "user_id": user_id,
        "name": str(
            snapshot_payload.get("name")
            or payload.get("strategy_name")
            or record.best_strategy_name
            or "AI research strategy snapshot"
        ),
        "description": snapshot_payload.get("description") or record.prompt,
        "code": code,
        "params": dict(snapshot_payload.get("params") or {}),
        "category": str(snapshot_payload.get("category") or payload.get("category") or "custom"),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return StrategyResponse.model_validate(strategy_payload)


def _continuation_request_from_run_record(
    record: AIStrategyResearchRunRecord,
    overrides: dict[str, Any],
) -> AIStrategyResearchRunRequest:
    base_request = _paper_start_request_from_record(
        record,
        AIStrategyPaperTradingStartRequest(),
    )
    payload = base_request.model_dump(mode="python")
    continuation_context = _continuation_context_from_record(record)
    if continuation_context:
        payload["continuation_context"] = continuation_context

    for key, value in dict(overrides or {}).items():
        if value is not None:
            payload[key] = value
    if isinstance((overrides or {}).get("continuation_context"), dict):
        payload["continuation_context"] = {
            **continuation_context,
            **dict(overrides["continuation_context"]),
        }

    payload["continue_from_run_id"] = record.run_id
    payload["research_workspace_id"] = record.research_workspace_id
    if not str(payload.get("seed_strategy_id") or "").strip():
        raise ValueError("AI research run record has no best strategy to continue")

    request = AIStrategyResearchRunRequest.model_validate(payload)
    context = dict(request.continuation_context or {})
    if context:
        request = request.model_copy(
            update={
                "continuation_context": _enriched_continuation_context(
                    context,
                    request,
                )
            }
        )
    return request


def _paper_start_request_from_record(
    record: AIStrategyResearchRunRecord,
    request: AIStrategyPaperTradingStartRequest,
) -> AIStrategyResearchRunRequest:
    gates = dict(record.quality_gates or {})
    runtime_context = _record_runtime_context(record)
    asset_specs = _dict_payload(runtime_context.get("asset_specs"))
    backtest_environment = _dict_payload(runtime_context.get("backtest_environment"))
    iteration_payload = _best_iteration_payload(record) or {}
    unit_snapshot = _dict_payload(iteration_payload.get("unit_snapshot"))
    data_config = dict(unit_snapshot.get("data_config") or {})
    unit_settings = dict(unit_snapshot.get("unit_settings") or {})
    if asset_specs:
        _merge_contract_metadata(data_config, asset_specs)
        _merge_contract_metadata(unit_settings, asset_specs)
    if backtest_environment:
        for key in (
            "initial_cash",
            "commission",
            "annual_days",
            "calc_method",
            "weight_mode",
            "multiplier",
            "margin",
            "asset_spec_source",
        ):
            if backtest_environment.get(key) not in (None, ""):
                unit_settings[key] = backtest_environment[key]
    gateway_config = _dict_payload(_omit_sensitive_handoff(unit_snapshot.get("gateway_config")))
    gateway_config.update(_dict_payload(runtime_context.get("gateway_config")))
    gateway_config.update(_dict_payload(request.gateway_config))
    return AIStrategyResearchRunRequest(
        prompt=record.prompt,
        symbol=record.symbol,
        symbol_name=record.symbol_name,
        timeframe=record.timeframe,
        timeframe_n=record.timeframe_n,
        start_date=record.start_date,
        end_date=record.end_date,
        initial_cash=_runtime_float(backtest_environment.get("initial_cash"), record.initial_cash),
        commission=_runtime_float(backtest_environment.get("commission"), record.commission),
        annual_days=_runtime_int(backtest_environment.get("annual_days"), record.annual_days),
        calc_method=_runtime_text(backtest_environment.get("calc_method"), record.calc_method),
        weight_mode=_runtime_text(backtest_environment.get("weight_mode"), record.weight_mode),
        group_name=record.group_name or record.best_strategy_name,
        knowledge_base_id=record.knowledge_base_id,
        thinking_mode=record.thinking_mode,
        target_sharpe=record.target_sharpe,
        min_total_trades=record.min_total_trades,
        max_drawdown_limit=_optional_gate_number(gates.get("max_drawdown_limit")),
        min_total_return=_optional_gate_number(gates.get("min_total_return")),
        min_annual_return=_optional_gate_number(gates.get("min_annual_return")),
        min_win_rate=_optional_gate_number(gates.get("min_win_rate")),
        out_of_sample_validation=bool(gates.get("out_of_sample_validation", True)),
        require_out_of_sample_validation=bool(gates.get("require_out_of_sample_validation", False)),
        out_of_sample_ratio=float(gates.get("out_of_sample_ratio") or 0.25),
        min_out_of_sample_sharpe=_optional_gate_number(gates.get("min_out_of_sample_sharpe")),
        min_out_of_sample_trades=_optional_gate_int(gates.get("min_out_of_sample_trades")),
        robustness_validation=bool(gates.get("robustness_validation", False)),
        require_robustness_validation=bool(gates.get("require_robustness_validation", False)),
        robustness_methods=list(gates.get("robustness_methods") or ["monte_carlo"]),
        min_robustness_score=float(gates.get("min_robustness_score") or 55.0),
        robustness_monte_carlo_iterations=int(
            gates.get("robustness_monte_carlo_iterations") or 300
        ),
        max_iterations=max(int(record.max_iterations or 1), 1),
        backtest_timeout_seconds=record.backtest_timeout_seconds,
        poll_interval_seconds=record.poll_interval_seconds,
        research_workspace_id=record.research_workspace_id,
        mandate_id=record.mandate_id,
        trading_workspace_id=request.trading_workspace_id,
        seed_strategy_id=record.best_strategy_id
        or _strategy_id_from_iteration_payload(iteration_payload)
        or (
            _fallback_snapshot_strategy_id(record)
            if _iteration_payload_has_strategy_snapshot(iteration_payload)
            else None
        ),
        continue_from_run_id=record.run_id,
        start_paper_trading=True,
        min_paper_trading_days=max(int(gates.get("min_paper_trading_days") or 0), 0),
        paper_workspace_name=request.paper_workspace_name or record.paper_workspace_name,
        gateway_config=gateway_config,
        data_config=data_config,
        unit_settings=unit_settings,
    )


def _live_trading_unit_payload_from_record(
    record: AIStrategyResearchRunRecord,
    *,
    package: AIStrategyLiveHandoffPackage,
    strategy: StrategyResponse,
    source_unit: StrategyUnitResponse,
    request: AIStrategyLiveTradingPrepareRequest,
    risk_gate: dict[str, Any] | None = None,
) -> StrategyUnitCreate:
    runtime_context = _record_runtime_context(record)
    asset_specs = _dict_payload(runtime_context.get("asset_specs"))
    backtest_environment = _dict_payload(runtime_context.get("backtest_environment"))
    data_config = {
        **dict(source_unit.data_config or {}),
        "ai_research_run_id": record.run_id,
        "ai_research_workspace_id": record.research_workspace_id,
        "ai_research_live_handoff_status": package.status,
    }
    unit_settings = {
        **dict(source_unit.unit_settings or {}),
        "ai_research_live_handoff": _redact_sensitive_handoff(
            {
                "run_id": record.run_id,
                "research_workspace_id": record.research_workspace_id,
                "live_handoff_status": package.status,
                "approval": package.approval.model_dump(mode="json")
                if package.approval is not None
                else None,
                "asset_specs": asset_specs,
                "backtest_environment": backtest_environment,
            }
        ),
    }
    if risk_gate:
        unit_settings["live_risk_gate"] = dict(risk_gate)
        unit_settings["risk_limits"] = dict(risk_gate.get("risk_limits") or {})
    if asset_specs:
        _merge_contract_metadata(data_config, asset_specs)
        _merge_contract_metadata(unit_settings, asset_specs)
    for key in (
        "initial_cash",
        "commission",
        "annual_days",
        "calc_method",
        "weight_mode",
        "multiplier",
        "margin",
        "asset_spec_source",
    ):
        value = backtest_environment.get(key)
        if value not in (None, ""):
            unit_settings[key] = value
    gateway_config = _dict_payload(source_unit.gateway_config)
    gateway_config.update(_dict_payload(runtime_context.get("gateway_config")))
    gateway_config.update(_dict_payload(request.gateway_config))
    gateway_config = _dict_payload(_omit_sensitive_handoff(gateway_config))
    return StrategyUnitCreate(
        group_name=record.group_name or source_unit.group_name or strategy.name,
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        symbol=record.symbol,
        symbol_name=record.symbol_name or record.symbol,
        timeframe=record.timeframe,
        timeframe_n=record.timeframe_n,
        category=strategy.category,
        data_config=data_config,
        unit_settings=unit_settings,
        params=dict(source_unit.params or {}),
        optimization_config=dict(source_unit.optimization_config or {}),
        trading_mode="live",
        gateway_config=gateway_config,
        lock_trading=True,
        lock_running=True,
    )


def _live_trading_prepare_handoff(
    record: AIStrategyResearchRunRecord,
    package: AIStrategyLiveHandoffPackage,
    workspace: WorkspaceResponse,
    unit: StrategyUnitResponse,
    *,
    risk_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prepared_at = _utc_iso_now()
    return _redact_sensitive_handoff(
        {
            "run_id": record.run_id,
            "research_workspace_id": record.research_workspace_id,
            "live_handoff_status": package.status,
            "live_handoff_approved_at": package.approval.decided_at
            if package.approval is not None
            else None,
            "live_trading_prepared_at": prepared_at,
            "live_workspace_id": workspace.id,
            "live_workspace_name": workspace.name,
            "live_unit_id": unit.id,
            "live_unit_locked": bool(unit.lock_trading or unit.lock_running),
            "paper_workspace_id": record.paper_workspace_id,
            "paper_unit_id": record.paper_unit_id,
            "asset_specs": dict(record.asset_specs or {}),
            "backtest_environment": dict(record.backtest_environment or {}),
            "live_risk_gate": dict(risk_gate or {}),
            "next_actions": _live_trading_prepare_next_actions(unit),
            "reason": "Approved AI live handoff materialized as a locked live trading unit.",
        }
    )


def _unit_from_iteration_snapshot(
    record: AIStrategyResearchRunRecord,
    *,
    strategy: StrategyResponse,
    payload: dict[str, Any],
) -> StrategyUnitResponse | None:
    snapshot = payload.get("unit_snapshot")
    if not isinstance(snapshot, dict):
        return None
    unit_id = str(payload.get("unit_id") or snapshot.get("id") or "").strip()
    if not unit_id:
        return None
    now = datetime.now(timezone.utc)
    return StrategyUnitResponse(
        id=unit_id,
        workspace_id=str(snapshot.get("workspace_id") or record.research_workspace_id),
        group_name=str(record.group_name or snapshot.get("group_name") or strategy.name),
        strategy_id=str(snapshot.get("strategy_id") or strategy.id),
        strategy_name=str(snapshot.get("strategy_name") or strategy.name),
        symbol=str(snapshot.get("symbol") or record.symbol),
        symbol_name=str(snapshot.get("symbol_name") or record.symbol_name or record.symbol),
        timeframe=str(snapshot.get("timeframe") or record.timeframe),
        timeframe_n=_runtime_int(snapshot.get("timeframe_n"), record.timeframe_n),
        category=str(snapshot.get("category") or strategy.category),
        data_config=dict(snapshot.get("data_config") or {}),
        unit_settings=dict(snapshot.get("unit_settings") or {}),
        params=dict(snapshot.get("params") or {}),
        optimization_config=dict(snapshot.get("optimization_config") or {}),
        gateway_config=(
            _dict_payload(_omit_sensitive_handoff(snapshot.get("gateway_config")))
            or _dict_payload(
                _omit_sensitive_handoff(
                    record.paper_handoff.get("gateway_config") if record.paper_handoff else None
                )
            )
        ),
        trading_mode=str(snapshot.get("trading_mode") or "paper"),
        lock_trading=bool(snapshot.get("lock_trading", False)),
        lock_running=bool(snapshot.get("lock_running", False)),
        run_status=str(payload.get("run_status") or "completed"),
        run_count=1,
        last_task_id=str(payload.get("task_id") or "") or None,
        metrics_snapshot=dict(payload.get("metrics") or record.best_metrics or {}),
        created_at=now,
        updated_at=now,
    )


def _unit_from_run_record(
    record: AIStrategyResearchRunRecord,
    *,
    strategy: StrategyResponse,
) -> StrategyUnitResponse:
    runtime_context = _record_runtime_context(record)
    asset_specs = _dict_payload(runtime_context.get("asset_specs"))
    backtest_environment = _dict_payload(runtime_context.get("backtest_environment"))
    data_config: dict[str, Any] = {"symbol": record.symbol}
    unit_settings: dict[str, Any] = {}
    if asset_specs:
        _merge_contract_metadata(data_config, asset_specs)
        _merge_contract_metadata(unit_settings, asset_specs)
    for key in (
        "initial_cash",
        "commission",
        "annual_days",
        "calc_method",
        "weight_mode",
        "multiplier",
        "margin",
        "asset_spec_source",
    ):
        value = backtest_environment.get(key)
        if value not in (None, ""):
            unit_settings[key] = value
    if "initial_cash" not in unit_settings:
        unit_settings["initial_cash"] = record.initial_cash
    if "commission" not in unit_settings:
        unit_settings["commission"] = record.commission
    if "annual_days" not in unit_settings:
        unit_settings["annual_days"] = record.annual_days
    if "calc_method" not in unit_settings:
        unit_settings["calc_method"] = record.calc_method
    if "weight_mode" not in unit_settings:
        unit_settings["weight_mode"] = record.weight_mode
    now = datetime.now(timezone.utc)
    return StrategyUnitResponse(
        id=f"{record.run_id}-unit",
        workspace_id=record.research_workspace_id,
        group_name=record.group_name or record.best_strategy_name or strategy.name,
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        symbol=record.symbol,
        symbol_name=record.symbol_name or record.symbol,
        timeframe=record.timeframe,
        timeframe_n=record.timeframe_n,
        category=strategy.category,
        data_config=data_config,
        unit_settings=unit_settings,
        params={name: spec.default for name, spec in strategy.params.items()},
        optimization_config={},
        gateway_config=_dict_payload(runtime_context.get("gateway_config")),
        trading_mode="paper",
        lock_trading=False,
        lock_running=False,
        run_status="completed",
        run_count=max(int(record.iteration_count or 1), 1),
        metrics_snapshot=dict(record.best_metrics or {}),
        created_at=now,
        updated_at=now,
    )


def _iteration_from_record_payload(
    record: AIStrategyResearchRunRecord,
    *,
    strategy: StrategyResponse,
    unit: StrategyUnitResponse,
    payload: dict[str, Any],
) -> AIStrategyResearchIteration:
    metrics = dict(payload.get("metrics") or record.best_metrics or {})
    run_status = str(payload.get("run_status") or "completed")
    task_id = payload.get("task_id")
    return AIStrategyResearchIteration(
        iteration=int(payload.get("iteration") or record.best_iteration or 1),
        strategy=strategy,
        unit=unit,
        run_result=StrategyCopilotRunResult(
            unit_id=unit.id,
            task_id=str(task_id) if task_id else None,
            status=run_status,
        ),
        unit_status=UnitStatusResponse(
            id=unit.id,
            run_status=run_status,
            last_task_id=str(task_id) if task_id else None,
            metrics_snapshot=metrics,
            run_count=unit.run_count,
            trading_mode=unit.trading_mode,
        ),
        metrics=metrics,
        sharpe_ratio=_metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio"),
        total_trades=_metric_int(metrics, "total_trades", "totalTrades", "trades"),
        validation_status=payload.get("validation_status"),
        validation_window=dict(payload.get("validation_window") or {})
        if payload.get("validation_window")
        else None,
        validation_metrics=dict(payload.get("validation_metrics") or {}),
        validation_gate_evaluations=list(payload.get("validation_gate_evaluations") or []),
        validation_failures=list(payload.get("validation_failures") or []),
        validation_failure_reason=payload.get("validation_failure_reason"),
        robustness_status=payload.get("robustness_status"),
        robustness_result=dict(payload.get("robustness_result") or {}),
        robustness_gate_evaluations=list(payload.get("robustness_gate_evaluations") or []),
        robustness_failures=list(payload.get("robustness_failures") or []),
        robustness_failure_reason=payload.get("robustness_failure_reason"),
        quality_score=float(payload.get("quality_score") or record.best_quality_score or 0.0),
        quality_gate_evaluations=list(
            payload.get("quality_gate_evaluations") or record.best_quality_gate_evaluations or []
        ),
        passed=bool(payload.get("passed", record.achieved)),
        failure_reason=payload.get("failure_reason"),
        quality_gate_failures=list(payload.get("quality_gate_failures") or []),
        diagnostics=dict(payload.get("diagnostics") or record.best_diagnostics or {}),
        improvement_plan=list(payload.get("improvement_plan") or []),
        improvement_notes=list(payload.get("improvement_notes") or []),
        next_actions=list(payload.get("next_actions") or []),
    )


def _optional_gate_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_gate_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _runtime_text(value: Any, fallback: str | None) -> str | None:
    text = str(value or "").strip()
    if text:
        return text
    return fallback


def _runtime_float(value: Any, fallback: float) -> float:
    parsed = _optional_gate_number(value)
    return float(parsed) if parsed is not None else fallback


def _runtime_int(value: Any, fallback: int) -> int:
    parsed = _optional_gate_int(value)
    return int(parsed) if parsed is not None else fallback


def _continuation_context_from_record(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any]:
    runtime_context = _record_runtime_context(record)
    live_rejection_context = _live_handoff_rejection_context_from_record(record, runtime_context)
    if live_rejection_context:
        return live_rejection_context
    paper_review_requires_research = _paper_review_requires_research(record)
    review_evaluations = [
        dict(item) for item in record.paper_review_evaluations if isinstance(item, dict)
    ]
    failed_evaluations = [
        dict(item) for item in review_evaluations if str(item.get("status") or "") == "failed"
    ]
    if not failed_evaluations and not paper_review_requires_research:
        paper_trading_error = _paper_trading_start_failure_from_record(record)
        if not paper_trading_error:
            return _research_failure_context_from_record(record)
        failure = "模拟交易启动失败"
        if paper_trading_error:
            failure = f"{failure}：{paper_trading_error}"
        return {
            "source": "paper_trading_failed",
            "run_id": record.run_id,
            "paper_trading_error": paper_trading_error,
            "quality_gate_failures": [failure],
            "pipeline": dict(record.pipeline or {}),
            "next_actions": list(record.next_actions or []),
            "metrics": dict(record.best_metrics or {}),
            **runtime_context,
        }

    context_evaluations = failed_evaluations or review_evaluations
    failures = [_paper_review_failure_text(item) for item in failed_evaluations]
    if not failures:
        failures = _paper_review_status_failures(record)
    metrics = dict(record.best_metrics or {})
    paper_review_rule_gaps = _paper_review_gap_summary(context_evaluations)
    for item in context_evaluations:
        metric = str(item.get("metric") or item.get("key") or "").strip()
        actual = _optional_gate_number(item.get("actual"))
        if metric and actual is not None:
            metrics[metric] = actual
        gap = _optional_gate_number(item.get("distance_to_pass") or item.get("gap"))
        if metric and gap is not None:
            metrics[f"{metric}_gap"] = gap
        gap_ratio = _optional_gate_number(item.get("gap_ratio"))
        if metric and gap_ratio is not None:
            metrics[f"{metric}_gap_ratio"] = gap_ratio

    return {
        "source": "paper_review",
        "run_id": record.run_id,
        "paper_review_status": record.paper_review_status,
        "paper_reviewed_at": record.paper_reviewed_at,
        "quality_gate_failures": failures,
        "paper_review_evaluations": context_evaluations,
        "paper_review_rule_gaps": paper_review_rule_gaps,
        "paper_review_next_actions": list(record.paper_review_next_actions or []),
        "metrics": metrics,
        **runtime_context,
    }


def _live_handoff_rejection_context_from_record(
    record: AIStrategyResearchRunRecord,
    runtime_context: dict[str, Any],
) -> dict[str, Any]:
    approval = record.live_handoff_approval
    handoff = record.live_handoff
    approval_decision = _object_field_text(approval, "decision")
    handoff_status = _object_field_text(handoff, "status")
    approval_status = _object_field_text(handoff, "approval_status")
    if not (
        approval_decision == "rejected"
        or approval_status == "rejected"
        or handoff_status == "approval_rejected"
    ):
        return {}

    comment = _object_field_text(approval, "comment")
    failures = [
        "实盘交接审批被驳回，需要处理审批意见后重新投研并重新进入模拟复核。",
    ]
    if comment:
        failures.append(f"实盘交接驳回意见：{comment}")
    failures.extend(str(item).strip() for item in record.next_actions or [])
    failures = list(dict.fromkeys(item for item in failures if item))

    return {
        "source": "live_handoff_rejected",
        "run_id": record.run_id,
        "live_handoff_status": handoff_status or "approval_rejected",
        "live_handoff_approval": _object_payload(approval),
        "live_handoff": _object_payload(handoff),
        "quality_gate_failures": failures,
        "paper_review_status": record.paper_review_status,
        "paper_reviewed_at": record.paper_reviewed_at,
        "paper_review_evaluations": [
            dict(item) for item in record.paper_review_evaluations if isinstance(item, dict)
        ],
        "paper_review_next_actions": list(record.paper_review_next_actions or []),
        "live_readiness_checklist": [
            dict(item) for item in record.live_readiness_checklist if isinstance(item, dict)
        ],
        "metrics": dict(record.best_metrics or {}),
        "next_actions": list(record.next_actions or []),
        **runtime_context,
    }


def _enriched_continuation_context(
    context: dict[str, Any],
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    payload = dict(context)
    metrics = _dict_payload(payload.get("metrics"))
    diagnostics = _dict_payload(payload.get("diagnostics"))
    feedback = _improvement_feedback_payload(diagnostics)
    failures = _continuation_quality_gate_failures(payload)
    categories = [
        *_string_list(payload.get("failure_categories")),
        *_string_list(feedback.get("failure_categories")),
        *_failure_categories(failures, "completed", None),
    ]
    categories = list(dict.fromkeys(item for item in categories if item))
    if categories:
        payload["failure_categories"] = categories

    weaknesses = [
        *_string_list(payload.get("weaknesses")),
        *_string_list(feedback.get("weaknesses")),
        *failures,
    ]
    weaknesses = list(dict.fromkeys(item for item in weaknesses if item))
    if weaknesses:
        payload["weaknesses"] = weaknesses

    plan = [
        *_string_list(payload.get("improvement_plan")),
        *_string_list(feedback.get("improvement_plan")),
        *_string_list(payload.get("paper_review_next_actions")),
        *_string_list(payload.get("next_actions")),
    ]
    if failures or categories:
        plan.extend(
            _improvement_plan_from_failures(
                request,
                metrics=metrics,
                run_status="completed",
                quality_gate_failures=failures,
                failure_categories=categories,
            )
        )
    plan = list(dict.fromkeys(item for item in plan if item))
    if plan:
        payload["improvement_plan"] = plan

    rule_gaps = _paper_review_gap_summary(
        [
            dict(item)
            for item in payload.get("paper_review_evaluations") or []
            if isinstance(item, dict)
        ]
    )
    if rule_gaps and not isinstance(payload.get("paper_review_rule_gaps"), list):
        payload["paper_review_rule_gaps"] = rule_gaps

    return payload


def _continuation_improvement_metrics(
    context: dict[str, Any],
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    context = _enriched_continuation_context(context, request)
    metrics = _dict_payload(context.get("metrics"))
    diagnostics = _dict_payload(context.get("diagnostics"))
    feedback = _improvement_feedback_payload(diagnostics)
    failures = _continuation_quality_gate_failures(context)
    categories = [
        *_string_list(feedback.get("failure_categories")),
        *_failure_categories(failures, "completed", None),
    ]
    categories = list(dict.fromkeys(item for item in categories if item))
    weaknesses = [
        *_string_list(feedback.get("weaknesses")),
        *failures,
    ]
    weaknesses = list(dict.fromkeys(item for item in weaknesses if item))
    plan = [
        *_string_list(context.get("improvement_plan")),
        *_string_list(feedback.get("improvement_plan")),
        *_string_list(context.get("paper_review_next_actions")),
        *_string_list(context.get("next_actions")),
    ]
    generated_plan = _improvement_plan_from_failures(
        request,
        metrics=metrics,
        run_status="completed",
        quality_gate_failures=failures,
        failure_categories=categories,
    )
    plan = list(dict.fromkeys([*plan, *generated_plan]))
    source = str(context.get("source") or "").strip()
    feedback.update(
        {
            "source": source,
            "run_id": context.get("run_id"),
            "failure_categories": categories,
            "weaknesses": weaknesses,
            "improvement_plan": plan,
            "promotion_ready": False,
        }
    )
    rule_gaps = context.get("paper_review_rule_gaps")
    if isinstance(rule_gaps, list):
        feedback["paper_review_rule_gaps"] = [
            dict(item) for item in rule_gaps if isinstance(item, dict)
        ]
    for key in (
        "paper_review_status",
        "paper_reviewed_at",
        "paper_review_evaluations",
        "paper_review_rule_gaps",
        "paper_review_next_actions",
        "paper_trading_error",
        "live_handoff_status",
        "live_handoff_approval",
        "live_handoff",
        "live_readiness_checklist",
        "pipeline",
        "next_actions",
    ):
        value = context.get(key)
        if isinstance(value, dict):
            feedback[key] = dict(value)
        elif isinstance(value, list):
            feedback[key] = list(value)
        elif value not in (None, ""):
            feedback[key] = value
    if diagnostics:
        feedback["diagnostics"] = diagnostics

    metrics["research_feedback"] = feedback
    metrics["failure_categories"] = categories
    metrics["weaknesses"] = weaknesses
    metrics["improvement_plan"] = plan
    metrics["promotion_ready"] = False
    return metrics


def _object_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
        return dict(payload) if isinstance(payload, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _object_field_text(value: Any, key: str) -> str:
    if value is None:
        return ""
    raw = value.get(key) if isinstance(value, dict) else getattr(value, key, "")
    return str(raw or "").strip()


def _paper_review_requires_research(record: AIStrategyResearchRunRecord) -> bool:
    return (
        str(record.paper_review_status or "") in {"needs_research_review", "live_readiness_expired"}
        and not record.paper_review_ready_for_live
    )


def _paper_review_status_failures(record: AIStrategyResearchRunRecord) -> list[str]:
    status = str(record.paper_review_status or "").strip()
    if status == "live_readiness_expired":
        failures = ["实盘候选复核已过期，需要重新复核模拟交易并刷新投研假设。"]
        failures.extend(str(item).strip() for item in record.paper_review_next_actions or [])
        failures.extend(
            str(item.get("action") or item.get("evidence") or "").strip()
            for item in record.live_readiness_checklist
            if isinstance(item, dict)
        )
        return list(dict.fromkeys(item for item in failures if item))
    if status:
        return [f"Paper review status {status} requires research review"]
    return ["Paper review requires research review"]


def _record_runtime_context(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    asset_specs: dict[str, Any] = {}
    backtest_environment: dict[str, Any] = {}
    gateway_config: dict[str, Any] = {}
    if record.asset_specs:
        asset_specs = _merge_runtime_context_mapping(asset_specs, record.asset_specs)
    if record.backtest_environment:
        backtest_environment = _merge_runtime_context_mapping(
            backtest_environment,
            record.backtest_environment,
        )
    if record.paper_handoff:
        paper_asset_specs = record.paper_handoff.get("asset_specs")
        asset_specs = _merge_runtime_context_mapping(asset_specs, paper_asset_specs)
        paper_environment = record.paper_handoff.get("backtest_environment")
        backtest_environment = _merge_runtime_context_mapping(
            backtest_environment,
            paper_environment,
        )
        gateway_config.update(
            _dict_payload(_omit_sensitive_handoff(record.paper_handoff.get("gateway_config")))
        )
    context: dict[str, Any] = {}
    if asset_specs:
        context["asset_specs"] = asset_specs
    if backtest_environment:
        context["backtest_environment"] = backtest_environment
    if gateway_config:
        context["gateway_config"] = gateway_config
    return context


def _merge_runtime_context_mapping(
    base: dict[str, Any],
    override: Any,
) -> dict[str, Any]:
    if not isinstance(override, dict):
        return base
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _research_failure_context_from_record(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any]:
    if record.achieved:
        return {}
    pipeline = record.pipeline if isinstance(record.pipeline, dict) else {}
    if str(pipeline.get("current_stage") or record.status or "").strip() == "interrupted":
        source = "research_interrupted"
    else:
        source = "research_cancelled" if record.status == "cancelled" else "research_failure"
    base_context = (
        dict(record.continuation_context) if isinstance(record.continuation_context, dict) else {}
    )
    payload = _best_iteration_payload(record)
    if not payload:
        diagnostics = dict(record.best_diagnostics or {})
        failures = [
            str(item).strip()
            for item in [
                *_string_list(base_context.get("quality_gate_failures")),
                *list(diagnostics.get("weaknesses") or []),
                diagnostics.get("summary"),
                *(record.next_actions or []),
            ]
            if str(item or "").strip()
        ]
        if not failures:
            failures.append(
                f"Previous research run finished without backtest iterations: {record.status}"
            )
        return {
            **base_context,
            "source": source,
            "run_id": record.run_id,
            "quality_gate_failures": failures,
            "metrics": {},
            "diagnostics": diagnostics,
            "improvement_plan": list(diagnostics.get("improvement_plan") or []),
            "next_actions": list(record.next_actions or []),
            **_record_runtime_context(record),
        }

    failures = [
        str(item).strip()
        for item in [
            *_string_list(base_context.get("quality_gate_failures")),
            *list(payload.get("quality_gate_failures") or []),
            *list(payload.get("validation_failures") or []),
        ]
        if str(item or "").strip()
    ]
    failure_reason = str(payload.get("failure_reason") or "").strip()
    validation_failure_reason = str(payload.get("validation_failure_reason") or "").strip()
    for reason in (failure_reason, validation_failure_reason):
        if reason and reason not in failures:
            failures.append(reason)
    if not failures:
        status = str(record.status or "not achieved").strip()
        failures.append(f"Previous research run finished without achieving target: {status}")

    metrics = dict(record.best_metrics or {})
    metrics.update(dict(payload.get("metrics") or {}))
    validation_metrics = dict(payload.get("validation_metrics") or {})
    for key, value in validation_metrics.items():
        metrics[f"validation_{key}"] = value

    return {
        **base_context,
        "source": source,
        "run_id": record.run_id,
        "iteration": payload.get("iteration"),
        "quality_gate_failures": failures,
        "metrics": metrics,
        "diagnostics": dict(payload.get("diagnostics") or {}),
        "improvement_plan": list(payload.get("improvement_plan") or []),
        "next_actions": list(record.next_actions or []),
        **_record_runtime_context(record),
    }


def _paper_trading_start_failure_from_record(record: AIStrategyResearchRunRecord) -> str:
    pipeline = record.pipeline if isinstance(record.pipeline, dict) else {}
    error = str(pipeline.get("paper_trading_error") or "").strip()
    if error:
        return error

    steps = pipeline.get("steps")
    if isinstance(steps, list):
        for item in steps:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            status = str(item.get("status") or "").strip()
            if key != "paper_trading" or status != "failed":
                continue
            return str(item.get("error") or item.get("message") or "").strip()

    if str(pipeline.get("current_stage") or "").strip() == "paper_trading_failed":
        return "unknown paper trading start failure"
    return ""


def _paper_review_failure_text(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("key") or item.get("metric") or "Paper metric")
    actual = _format_gate_value(item.get("actual"))
    threshold = _format_gate_value(item.get("threshold"))
    direction = str(item.get("direction") or "").strip()
    action = str(item.get("action") or "").strip()
    detail = f"{label} paper review failed: {actual} / {threshold}"
    if direction:
        detail = f"{detail} ({direction})"
    gap = _optional_gate_number(item.get("distance_to_pass") or item.get("gap"))
    if gap is not None:
        detail = f"{detail}; gap: {_format_gate_value(gap)}"
    if action:
        detail = f"{detail}; action: {action}"
    return detail


def _paper_review_gap_summary(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in evaluations:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        if bool(item.get("passed")) or status == "passed":
            continue
        metric = str(item.get("metric") or item.get("key") or "").strip()
        threshold = _optional_gate_number(item.get("threshold"))
        actual = _optional_gate_number(item.get("actual"))
        direction = str(item.get("direction") or "min").strip().lower()
        gap = _optional_gate_number(item.get("distance_to_pass") or item.get("gap"))
        gap_ratio = _optional_gate_number(item.get("gap_ratio"))
        margin = _optional_gate_number(item.get("margin"))
        if gap is None and threshold is not None:
            computed = _paper_rule_gap_fields(actual, float(threshold), direction)
            gap = computed.get("gap")
            gap_ratio = computed.get("gap_ratio")
            margin = computed.get("margin")
        gaps.append(
            {
                "key": item.get("key") or metric,
                "label": item.get("label") or metric,
                "metric": metric,
                "status": status or "pending",
                "direction": direction if direction in {"min", "max"} else "min",
                "actual": actual,
                "threshold": threshold,
                "margin": margin,
                "gap": gap,
                "gap_ratio": gap_ratio,
                "distance_to_pass": gap,
                "action": item.get("action"),
            }
        )
    gaps.sort(
        key=lambda item: (
            float(item.get("gap_ratio") or -1.0),
            float(item.get("gap") or -1.0),
        ),
        reverse=True,
    )
    return gaps


def _continuation_quality_gate_failures(context: dict[str, Any]) -> list[str]:
    failures = context.get("quality_gate_failures") if isinstance(context, dict) else None
    if not isinstance(failures, list):
        return []
    return [str(item).strip() for item in failures if str(item or "").strip()]


def _iteration_robustness_payload(
    iteration: AIStrategyResearchIteration | None,
) -> dict[str, Any]:
    if iteration is None:
        return {}
    return {
        "status": iteration.robustness_status,
        "result": dict(iteration.robustness_result or {}),
        "gate_evaluations": [
            dict(item) for item in iteration.robustness_gate_evaluations if isinstance(item, dict)
        ],
        "failures": list(iteration.robustness_failures or []),
        "failure_reason": iteration.robustness_failure_reason,
    }
