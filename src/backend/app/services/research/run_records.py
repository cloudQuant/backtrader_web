"""Research-run record, task snapshot, and asset-contract helpers."""

# Workflow helpers are injected after every stage is loaded; see research.__init__.
# mypy: disable-error-code=name-defined
import sys

# ruff: noqa: F403, F405
from .shared import *


def _run_record_with_live_handoff(
    record: AIStrategyResearchRunRecord,
    package: AIStrategyLiveHandoffPackage,
) -> AIStrategyResearchRunRecord:
    pipeline = _pipeline_with_live_handoff_step(record.pipeline, package)
    next_actions = _live_handoff_next_actions(record, package)
    package = package.model_copy(update={"pipeline": pipeline, "next_actions": next_actions})
    return _research_run_record_with_promotion_audit(
        record.model_copy(
            update={
                "live_handoff": package,
                "live_readiness_checklist": [
                    dict(item)
                    for item in package.live_readiness_checklist
                    if isinstance(item, dict)
                ],
                "live_readiness_expires_at": package.expires_at,
                "pipeline": pipeline,
                "next_actions": next_actions,
            }
        )
    )


def _run_record_with_live_handoff_approval(
    record: AIStrategyResearchRunRecord,
    approval: AIStrategyLiveHandoffApprovalRecord,
) -> AIStrategyResearchRunRecord:
    package = record.live_handoff
    if package is not None:
        package = package.model_copy(
            update={
                "approval_status": approval.decision,
                "approval": approval,
                "status": (
                    "approved_for_live"
                    if approval.approved
                    else "requested_changes"
                    if approval.decision == "requested_changes"
                    else "approval_rejected"
                ),
            }
        )
    pipeline = _pipeline_with_live_handoff_step(record.pipeline, package, approval=approval)
    next_actions = _live_handoff_approval_next_actions(record, approval)
    if package is not None:
        package = package.model_copy(update={"pipeline": pipeline, "next_actions": next_actions})
    return _research_run_record_with_promotion_audit(
        record.model_copy(
            update={
                "live_handoff": package,
                "live_handoff_approval": approval,
                "pipeline": pipeline,
                "next_actions": next_actions,
            }
        )
    )


def _pipeline_with_live_handoff_step(
    pipeline: dict[str, Any] | None,
    package: AIStrategyLiveHandoffPackage | None,
    *,
    approval: AIStrategyLiveHandoffApprovalRecord | None = None,
) -> dict[str, Any]:
    updated = dict(pipeline or {})
    if package is None:
        return updated

    step_status = "running"
    if package.status == "approved_for_live":
        step_status = "completed"
    elif package.status in {"blocked", "approval_rejected"}:
        step_status = "failed"

    live_step = {
        "key": "live_handoff",
        "label": "实盘交接",
        "status": step_status,
        "handoff_status": package.status,
        "approval_status": approval.decision if approval is not None else package.approval_status,
        "blocker_count": len(package.deployment_blockers),
        "generated_at": package.generated_at,
    }
    if approval is not None:
        live_step["approved"] = approval.approved
        live_step["decided_at"] = approval.decided_at

    raw_steps = updated.get("steps")
    steps = (
        [dict(item) for item in raw_steps if isinstance(item, dict)]
        if isinstance(raw_steps, list)
        else []
    )
    replaced = False
    for index, step in enumerate(steps):
        if str(step.get("key") or "") == "live_handoff":
            steps[index] = {**step, **live_step}
            replaced = True
            break
    if not replaced:
        steps.append(live_step)

    updated.update(
        {
            "current_stage": "live_handoff",
            "status": package.status,
            "ready_for_live": package.ready_for_live,
            "live_handoff_status": package.status,
            "live_handoff_generated_at": package.generated_at,
            "live_handoff_ready_for_live": package.ready_for_live,
            "live_handoff_approval_required": package.approval_required,
            "live_handoff_blocker_count": len(package.deployment_blockers),
            "live_readiness_checklist": [
                dict(item) for item in package.live_readiness_checklist if isinstance(item, dict)
            ],
            "live_readiness_expires_at": package.expires_at,
            "steps": steps,
        }
    )
    if approval is not None:
        updated.update(
            {
                "live_handoff_approval_status": approval.decision,
                "live_handoff_approved": approval.approved,
                "live_handoff_approved_at": approval.decided_at if approval.approved else None,
                "live_handoff_rejected_at": None if approval.approved else approval.decided_at,
            }
        )
    if raw_steps:
        updated["progress"] = _pipeline_progress_from_steps(steps)
    return updated


def _pipeline_progress_from_steps(steps: list[dict[str, Any]]) -> float:
    if not steps:
        return 0.0
    completed = sum(1 for step in steps if step.get("status") == "completed")
    return round(completed / len(steps) * 100, 2)


def _pipeline_with_live_trading_prepared(
    pipeline: dict[str, Any] | None,
    *,
    workspace: WorkspaceResponse,
    unit: StrategyUnitResponse,
    prepared_at: str,
) -> dict[str, Any]:
    updated = dict(pipeline or {})
    raw_steps = updated.get("steps")
    steps = (
        [dict(item) for item in raw_steps if isinstance(item, dict)]
        if isinstance(raw_steps, list)
        else []
    )
    live_handoff_step = {
        "key": "live_handoff",
        "label": "实盘交接",
        "status": "completed",
        "handoff_status": "approved_for_live",
    }
    live_prepare_step = {
        "key": "live_trading_prepare",
        "label": "实盘准备",
        "status": "completed",
        "live_trading_prepared": True,
        "live_workspace_id": workspace.id,
        "live_unit_id": unit.id,
        "live_unit_locked": bool(unit.lock_trading or unit.lock_running),
        "prepared_at": prepared_at,
    }
    replaced = False
    for index, step in enumerate(steps):
        if str(step.get("key") or "") == "live_handoff":
            steps[index] = {**step, **live_handoff_step}
            replaced = True
            break
    if not replaced:
        steps.append(live_handoff_step)
    replaced = False
    for index, step in enumerate(steps):
        if str(step.get("key") or "") == "live_trading_prepare":
            steps[index] = {**step, **live_prepare_step}
            replaced = True
            break
    if not replaced:
        steps.append(live_prepare_step)
    updated.update(
        {
            "current_stage": "live_trading_prepare",
            "live_trading_prepared": True,
            "live_trading_prepared_at": prepared_at,
            "live_workspace_id": workspace.id,
            "live_unit_id": unit.id,
            "live_unit_locked": bool(unit.lock_trading or unit.lock_running),
            "steps": steps,
        }
    )
    if raw_steps:
        updated["progress"] = _pipeline_progress_from_steps(steps)
    return updated


def _live_handoff_next_actions(
    record: AIStrategyResearchRunRecord,
    package: AIStrategyLiveHandoffPackage,
) -> list[str]:
    if package.ready_for_live:
        actions = [
            "实盘交接包已生成，等待人工审批账户权限、风险限额和上线窗口。",
            "审批通过后再切换实盘账户，切换前继续监控模拟交易表现。",
        ]
        if package.expires_at:
            actions.append(f"实盘候选有效期至 {package.expires_at}，过期后需重新复核模拟交易。")
        return actions
    if package.deployment_blockers:
        return [
            "实盘交接包存在阻塞项，需处理后重新生成交接包。",
            *package.deployment_blockers,
        ]
    return list(record.next_actions or [])


def _live_handoff_approval_next_actions(
    record: AIStrategyResearchRunRecord,
    approval: AIStrategyLiveHandoffApprovalRecord,
) -> list[str]:
    if approval.approved:
        actions = [
            "实盘交接包已通过人工审批，可在上线窗口内执行实盘切换前检查。",
            "切换实盘前需再次确认网关凭据、账户权限、风险限额和当前模拟交易状态。",
        ]
        if approval.deployment_window:
            actions.append(f"计划上线窗口：{approval.deployment_window}")
        return actions
    if approval.decision == "requested_changes":
        actions = [
            "实盘交接需要修改，实盘锁定保持生效；请根据审批意见继续优化并重新完成模拟复核。",
        ]
        if approval.comment:
            actions.append(f"修改意见：{approval.comment}")
        return actions
    actions = [
        "实盘交接包已被人工驳回，需处理审批意见后重新进入模拟复核或继续投研。",
    ]
    if approval.comment:
        actions.append(f"驳回意见：{approval.comment}")
    return actions or list(record.next_actions or [])


def _live_trading_prepare_next_actions(unit: StrategyUnitResponse) -> list[str]:
    return [
        "已创建锁定的实盘交易单元，需人工核对网关凭据、账户权限和风控限额后再解锁运行。",
        f"实盘单元 {unit.id} 当前默认锁定交易/运行，不会自动下单。",
    ]


def _build_live_handoff_approval_record(
    *,
    user_id: str,
    record: AIStrategyResearchRunRecord,
    package: AIStrategyLiveHandoffPackage,
    request: AIStrategyLiveHandoffApprovalRequest,
) -> AIStrategyLiveHandoffApprovalRecord:
    decision = str(request.decision or "").strip().lower()
    if decision not in {"approved", "rejected", "requested_changes"}:
        raise ValueError(
            "Live handoff approval decision must be approved, rejected, or requested_changes"
        )
    approved = decision == "approved"
    blockers = list(package.deployment_blockers or [])
    if approved and not package.ready_for_live:
        if not blockers:
            blockers.append("实盘交接包尚未达到可审批状态。")
        raise ValueError("Cannot approve blocked live handoff: " + "；".join(blockers))
    if approved and not request.account_confirmed:
        raise ValueError("Live account and permissions must be confirmed before approval")
    if approved and not request.risk_limit_confirmed:
        raise ValueError("Live risk limits must be confirmed before approval")
    approver = str(request.approver or user_id or "unknown").strip() or "unknown"
    return AIStrategyLiveHandoffApprovalRecord(
        run_id=record.run_id,
        research_workspace_id=record.research_workspace_id,
        decision=decision,
        approved=approved,
        decided_at=_utc_iso_now(),
        decided_by=approver,
        comment=request.comment,
        account_confirmed=request.account_confirmed,
        risk_limit_confirmed=request.risk_limit_confirmed,
        deployment_window=request.deployment_window,
        handoff_status_at_decision=package.status,
        blockers=blockers,
    )


def _research_run_record_without_sensitive_handoff(
    record: AIStrategyResearchRunRecord,
) -> AIStrategyResearchRunRecord:
    redacted = _redact_sensitive_handoff(record.model_dump(mode="python"))
    try:
        return AIStrategyResearchRunRecord.model_validate(redacted)
    except Exception:
        return record


def _research_record_handoff_payload(handoff: Any) -> dict[str, Any]:
    return _redact_sensitive_handoff(_dict_payload(handoff))


def _research_record_continuation_context(context: Any) -> dict[str, Any]:
    return _redact_sensitive_handoff(_dict_payload(context))


def _continuation_source_from_context(context: Any) -> str | None:
    payload = _dict_payload(context)
    source = str(payload.get("source") or "").strip()
    return source or None


def _coerce_unit_status(value: Any) -> UnitStatusResponse | None:
    if value is None:
        return None
    if isinstance(value, UnitStatusResponse):
        return value
    if isinstance(value, dict):
        return UnitStatusResponse.model_validate(value)
    return None


def _coerce_strategy_unit_response(value: Any) -> StrategyUnitResponse | None:
    if value is None:
        return None
    if isinstance(value, StrategyUnitResponse):
        return value
    if isinstance(value, dict):
        return StrategyUnitResponse.model_validate(value)
    return None


def _cancelled_submitted_iteration(
    *,
    request: AIStrategyResearchRunRequest,
    iteration: int,
    backtest_response: Any,
    pending_improvement_notes: list[str],
) -> AIStrategyResearchIteration:
    failure_reason = f"AI research cancelled while waiting for backtest iteration {iteration}"
    run_result = backtest_response.run_result
    if hasattr(run_result, "model_copy"):
        run_result = run_result.model_copy(update={"status": "cancelled"})
    unit_status = UnitStatusResponse(
        id=backtest_response.unit.id,
        run_status="cancelled",
        last_task_id=backtest_response.run_result.task_id,
        metrics_snapshot={},
        run_count=0,
        trading_mode="paper",
    )
    quality_gate_failures = [failure_reason]
    quality_gate_evaluations = _quality_gate_evaluations(
        request,
        {},
        run_status=unit_status.run_status,
    )
    diagnostics = _iteration_diagnostics(
        request,
        iteration=iteration,
        metrics={},
        run_status=unit_status.run_status,
        quality_gate_failures=quality_gate_failures,
        quality_gate_evaluations=quality_gate_evaluations,
        failure_reason=failure_reason,
    )
    improvement_notes = [
        "任务取消时已保存当前已提交的回测策略，后续可从该策略继续投研。",
        *pending_improvement_notes,
    ]
    return AIStrategyResearchIteration(
        iteration=iteration,
        strategy=backtest_response.strategy,
        unit=backtest_response.unit,
        run_result=run_result,
        unit_status=unit_status,
        metrics={},
        sharpe_ratio=0.0,
        total_trades=0,
        quality_score=0.0,
        quality_gate_evaluations=quality_gate_evaluations,
        passed=False,
        failure_reason=failure_reason,
        quality_gate_failures=quality_gate_failures,
        diagnostics=diagnostics,
        improvement_plan=list(diagnostics.get("improvement_plan") or []),
        improvement_notes=improvement_notes,
        next_actions=_iteration_next_actions(
            iteration=iteration,
            max_iterations=request.max_iterations,
            passed=False,
            run_status=unit_status.run_status,
            quality_gate_failures=quality_gate_failures,
            failure_reason=failure_reason,
        ),
    )


async def _emit_research_progress(
    progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
    payload: dict[str, Any],
) -> None:
    if progress_callback is None:
        return
    result = progress_callback(payload)
    if result is not None:
        await result


def _research_loop_progress(iteration_count: int, max_iterations: int) -> float:
    if max_iterations <= 0:
        return 12.0
    return round(10.0 + (min(iteration_count, max_iterations) / max_iterations) * 72.0, 2)


def _find_unit_status(items: list[Any], unit_id: str) -> UnitStatusResponse | None:
    for item in items:
        status = _coerce_unit_status(item)
        if status is not None and status.id == unit_id:
            return status
    return None


def _resolve_research_asset_specs(
    request: AIStrategyResearchRunRequest,
) -> dict[str, dict[str, Any]]:
    symbols = _research_asset_symbols(request)
    if not symbols:
        return {}
    existing_metadata = _existing_contract_metadata(request)
    metadata_specs = _asset_specs_from_metadata(existing_metadata)
    params = {
        "symbol": request.symbol,
        "data_config": dict(request.data_config or {}),
    }
    for key, value in existing_metadata.items():
        if value:
            params[key] = value
    try:
        # The facade historically exposed this dependency at module scope, and
        # existing integrations patch it there. Resolve that facade override at
        # call time while keeping the stage module independently importable.
        facade = sys.modules.get("app.services.ai_strategy_research_service")
        resolver = getattr(facade, "resolve_asset_specs", resolve_asset_specs)
        resolved = resolver(
            {"params": params},
            Path(),
            gateway=request.gateway_config or None,
            symbols=symbols,
        )
        return resolved or metadata_specs
    except Exception:
        return metadata_specs


def _research_asset_symbols(request: AIStrategyResearchRunRequest) -> list[str]:
    candidates: list[Any] = [
        request.symbol,
        (request.data_config or {}).get("symbol"),
    ]
    for key in ("symbols", "symbol_list"):
        value = (request.data_config or {}).get(key)
        if isinstance(value, (list, tuple, set)):
            candidates.extend(value)
    for container in _existing_contract_metadata(request).values():
        if isinstance(container, dict):
            candidates.extend(container.keys())

    symbols: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = str(item or "").strip()
        if text and text not in seen:
            symbols.append(text)
            seen.add(text)
    return symbols


def _existing_contract_metadata(
    request: AIStrategyResearchRunRequest,
) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for source in (request.data_config, request.unit_settings):
        if not isinstance(source, dict):
            continue
        for key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
            value = source.get(key)
            if isinstance(value, dict):
                merged = dict(metadata.get(key) or {})
                merged.update(
                    {
                        str(item_key): dict(item_value)
                        for item_key, item_value in value.items()
                        if isinstance(item_value, dict)
                    }
                )
                metadata[key] = merged
    continuation_specs = _continuation_asset_specs(request)
    if continuation_specs:
        merged_contract_metadata = dict(continuation_specs)
        merged_contract_metadata.update(dict(metadata.get("contract_metadata") or {}))
        metadata["contract_metadata"] = merged_contract_metadata
    return metadata


def _continuation_asset_specs(
    request: AIStrategyResearchRunRequest,
) -> dict[str, dict[str, Any]]:
    context = request.continuation_context
    if not isinstance(context, dict) or not context:
        return {}
    specs: dict[str, dict[str, Any]] = {}
    for source in (
        context.get("asset_specs"),
        context.get("contract_metadata"),
        context.get("contracts"),
        context.get("contract_specs"),
        context.get("instrument_specs"),
        context,
    ):
        if not isinstance(source, dict):
            continue
        _merge_asset_spec_maps(specs, _asset_specs_from_mapping(source))
        if source is context:
            continue
        nested_specs = {
            str(symbol): dict(spec)
            for symbol, spec in source.items()
            if isinstance(spec, dict) and spec
        }
        if nested_specs:
            _merge_asset_spec_maps(specs, nested_specs)
        elif source is not context:
            symbol = str(source.get("symbol") or request.symbol or "").strip()
            if symbol:
                _merge_asset_spec_maps(specs, {symbol: dict(source)})
    return specs


def _continuation_backtest_environment(
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    context = request.continuation_context
    if not isinstance(context, dict):
        return {}
    environment = context.get("backtest_environment")
    return dict(environment) if isinstance(environment, dict) else {}


def _asset_specs_from_metadata(
    metadata: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for container in metadata.values():
        if isinstance(container, dict):
            _merge_asset_spec_maps(
                specs,
                {
                    str(symbol): dict(spec)
                    for symbol, spec in container.items()
                    if isinstance(spec, dict) and spec
                },
            )
    return specs


def _merge_contract_metadata(
    target: dict[str, Any],
    asset_specs: dict[str, dict[str, Any]],
) -> None:
    specs = {
        str(key): dict(value)
        for key, value in asset_specs.items()
        if isinstance(value, dict) and value
    }
    if not specs:
        return
    contract_metadata = dict(target.get("contract_metadata") or {})
    contract_metadata.update(specs)
    target["contract_metadata"] = contract_metadata


def _apply_primary_asset_spec_settings(
    unit_settings: dict[str, Any],
    asset_specs: dict[str, dict[str, Any]],
    *,
    override_commission: bool,
) -> None:
    primary = next((value for value in asset_specs.values() if isinstance(value, dict)), None)
    if not primary:
        return
    if "multiplier" not in unit_settings:
        multiplier = _optional_gate_number(primary.get("multiplier"))
        if multiplier is not None:
            unit_settings["multiplier"] = multiplier
    if "margin" not in unit_settings:
        margin = _first_asset_spec_number(
            primary,
            "margin_rate",
            "margin",
            "long_margin_rate",
            "short_margin_rate",
        )
        if margin is not None:
            unit_settings["margin"] = margin
    if override_commission:
        commission = _first_asset_spec_number(
            primary,
            "commission",
            "commission_rate",
            "open_commission_rate",
            "taker_commission_rate",
            "maker_commission_rate",
        )
        if commission is not None:
            unit_settings["commission"] = max(commission, 0.0)
    source = str(
        primary.get("source") or primary.get("fee_source") or primary.get("asset_spec_source") or ""
    ).strip()
    if source and not unit_settings.get("asset_spec_source"):
        unit_settings["asset_spec_source"] = source


def _request_has_explicit_commission(request: AIStrategyResearchRunRequest) -> bool:
    fields_set = _request_explicit_fields(request)
    return "commission" in fields_set or "commission" in (request.unit_settings or {})


def _request_explicit_fields(request: AIStrategyResearchRunRequest) -> set[str]:
    return set(
        getattr(request, "model_fields_set", None)
        or getattr(request, "__fields_set__", set())
        or set()
    )


def _first_asset_spec_number(spec: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_gate_number(spec.get(key))
        if value is not None:
            return value
    return None


def _asset_specs_from_unit(unit: StrategyUnitResponse | None) -> dict[str, dict[str, Any]]:
    if unit is None:
        return {}
    specs: dict[str, dict[str, Any]] = {}
    for source in (
        dict(unit.data_config or {}),
        dict(unit.unit_settings or {}),
        dict(unit.params or {}),
        _dict_payload(unit.gateway_config),
    ):
        specs.update(_asset_specs_from_mapping(source))

    symbol = str(unit.symbol or "").strip()
    primary = next((dict(item) for item in specs.values() if isinstance(item, dict)), None)
    unit_settings = dict(unit.unit_settings or {})
    unit_setting_spec = {
        key: unit_settings[key]
        for key in (
            "multiplier",
            "margin",
            "margin_rate",
            "commission",
            "commission_rate",
            "asset_spec_source",
        )
        if unit_settings.get(key) not in (None, "")
    }
    if symbol:
        merged = dict(specs.get(symbol) or primary or {})
        merged.update(unit_setting_spec)
        if merged:
            specs[symbol] = merged
    return _summarize_asset_specs_for_prompt(specs)


def _asset_specs_from_mapping(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for key in ("contract_metadata", "contracts", "contract_specs", "instrument_specs"):
        value = payload.get(key)
        if not isinstance(value, dict):
            continue
        for symbol, spec in value.items():
            if not isinstance(spec, dict):
                continue
            text = str(symbol or "").strip()
            if not text:
                continue
            merged = dict(specs.get(text) or {})
            merged.update(dict(spec))
            specs[text] = merged
    return specs


def _merge_asset_spec_maps(
    target: dict[str, dict[str, Any]],
    source: dict[str, dict[str, Any]],
) -> None:
    for symbol, spec in source.items():
        if not isinstance(spec, dict):
            continue
        merged = dict(target.get(symbol) or {})
        merged.update(dict(spec))
        target[symbol] = merged


def _request_backtest_environment(
    request: AIStrategyResearchRunRequest,
    asset_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    specs = asset_specs or _resolve_research_asset_specs(request)
    commission = request.commission
    primary = next((value for value in specs.values() if isinstance(value, dict)), None)
    continuation_environment = _continuation_backtest_environment(request)
    if primary and not _request_has_explicit_commission(request):
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
    elif not _request_has_explicit_commission(request):
        continuation_commission = _first_asset_spec_number(
            continuation_environment,
            "commission",
            "commission_rate",
        )
        if continuation_commission is not None:
            commission = max(continuation_commission, 0.0)
    environment: dict[str, Any] = {
        "initial_cash": request.initial_cash,
        "commission": commission,
        "commission_source": "user_override"
        if _request_has_explicit_commission(request)
        else "asset_specs_or_default",
        "annual_days": request.annual_days,
        "calc_method": request.calc_method,
        "weight_mode": request.weight_mode,
        "start_date": request.start_date,
        "end_date": request.end_date,
    }
    explicit_fields = _request_explicit_fields(request)
    for key in ("initial_cash", "annual_days", "calc_method", "weight_mode"):
        if key in explicit_fields:
            continue
        value = continuation_environment.get(key)
        if value not in (None, ""):
            environment[key] = value
    if primary:
        multiplier = _optional_gate_number(primary.get("multiplier"))
        margin = _first_asset_spec_number(
            primary,
            "margin_rate",
            "margin",
            "long_margin_rate",
            "short_margin_rate",
        )
        source = str(
            primary.get("source")
            or primary.get("fee_source")
            or primary.get("asset_spec_source")
            or ""
        ).strip()
        if multiplier is not None:
            environment["multiplier"] = multiplier
        if margin is not None:
            environment["margin"] = margin
        if source:
            environment["asset_spec_source"] = source
    for key in ("multiplier", "margin", "asset_spec_source"):
        if environment.get(key) in (None, "") and continuation_environment.get(key) not in (
            None,
            "",
        ):
            environment[key] = continuation_environment[key]
    return {key: value for key, value in environment.items() if value not in (None, "")}


def _apply_backtest_environment_defaults(
    unit_settings: dict[str, Any],
    request: AIStrategyResearchRunRequest,
    asset_specs: dict[str, dict[str, Any]],
) -> None:
    environment = _request_backtest_environment(request, asset_specs)
    explicit_fields = _request_explicit_fields(request)
    request_unit_settings = request.unit_settings or {}
    for key in ("initial_cash", "commission", "annual_days", "calc_method", "weight_mode"):
        if key in explicit_fields or key in request_unit_settings:
            continue
        value = environment.get(key)
        if value not in (None, ""):
            unit_settings[key] = value
    for key in ("multiplier", "margin", "asset_spec_source"):
        if key in request_unit_settings:
            continue
        value = environment.get(key)
        if value not in (None, ""):
            unit_settings[key] = value


def _research_run_records_from_workspace(
    workspace: WorkspaceResponse,
) -> list[AIStrategyResearchRunRecord]:
    settings = dict(workspace.settings or {})
    ai_research = settings.get("ai_research")
    if not isinstance(ai_research, dict):
        return []

    raw_runs = ai_research.get("runs")
    runs = raw_runs if isinstance(raw_runs, list) else []
    records_by_run_id: dict[str, AIStrategyResearchRunRecord] = {}
    ordered_run_ids: list[str] = []
    for raw in [*runs, ai_research.get("last_run")]:
        record = _coerce_research_run_record(raw)
        if record is None:
            continue
        current = records_by_run_id.get(record.run_id)
        if current is None:
            ordered_run_ids.append(record.run_id)
            records_by_run_id[record.run_id] = record
            continue
        if _research_run_record_history_rank(record) > _research_run_record_history_rank(current):
            records_by_run_id[record.run_id] = record
    records = [records_by_run_id[run_id] for run_id in ordered_run_ids]
    records.sort(key=lambda item: item.completed_at, reverse=True)
    return records


def _find_run_record_in_workspace(
    workspace: WorkspaceResponse,
    run_id: str,
) -> AIStrategyResearchRunRecord | None:
    target = str(run_id or "").strip()
    if not target:
        return None
    record = next(
        (
            record
            for record in _research_run_records_from_workspace(workspace)
            if record.run_id == target
        ),
        None,
    )
    if record is not None:
        return record
    return _find_task_snapshot_run_record_in_workspace(workspace, target)


def _find_task_snapshot_run_record_in_workspace(
    workspace: WorkspaceResponse,
    run_id: str,
) -> AIStrategyResearchRunRecord | None:
    settings = dict(workspace.settings or {})
    ai_research = settings.get("ai_research")
    if not isinstance(ai_research, dict):
        return None
    raw_tasks = ai_research.get("tasks")
    tasks = raw_tasks if isinstance(raw_tasks, list) else []
    candidates: list[AIStrategyResearchRunRecord] = []
    for raw in [*tasks, ai_research.get("last_task")]:
        record = _research_run_record_from_task_snapshot(raw, workspace, run_id)
        if record is not None:
            candidates.append(record)
    if not candidates:
        return None
    return max(candidates, key=_research_run_record_history_rank)


def _research_run_record_from_task_snapshot(
    raw: Any,
    workspace: WorkspaceResponse,
    run_id: str,
) -> AIStrategyResearchRunRecord | None:
    if not isinstance(raw, dict):
        return None
    try:
        task = AIStrategyResearchTaskResponse.model_validate(raw)
    except Exception:
        return None
    if str(task.run_id or "").strip() != run_id:
        return None
    if str(task.research_workspace_id or "").strip() != str(workspace.id):
        return None
    request = dict(task.request_snapshot or {})
    iterations = _task_snapshot_iterations_for_run_record(task)
    best_iteration = (
        task.best_iteration
        or _task_snapshot_best_iteration(iterations)
        or _optional_gate_int(task.current_iteration)
    )
    best_payload = (
        next(
            (
                dict(item)
                for item in iterations
                if _optional_gate_int(item.get("iteration")) == _optional_gate_int(best_iteration)
            ),
            dict(iterations[0]),
        )
        if iterations
        else {}
    )
    best_metrics = _merged_task_metrics(task.best_metrics, best_payload.get("metrics"))
    pipeline = dict(task.pipeline or {})
    stage = str(pipeline.get("current_stage") or task.current_stage or task.status).strip()
    status = str(task.run_status or task.status or "failed").strip()
    if task.status not in {"completed", "failed", "cancelled"}:
        pipeline.update(
            {
                "current_stage": "interrupted",
                "status": "failed",
                "progress": task.progress,
                "interrupted_task_id": task.task_id,
            }
        )
        if task.run_id:
            pipeline["interrupted_run_id"] = task.run_id
        if task.current_backtest_task_id:
            pipeline["interrupted_backtest_task_id"] = task.current_backtest_task_id
        stage = "interrupted"
        status = "interrupted"
    elif stage == "interrupted":
        status = "interrupted"
    continuation_context = _task_snapshot_continuation_context(task, pipeline)
    quality_gates = {
        "target_sharpe": _runtime_float(
            request.get("target_sharpe"),
            float(task.target_sharpe or 0.0),
        ),
        "min_total_trades": _runtime_int(request.get("min_total_trades"), 0),
        "max_drawdown_limit": request.get("max_drawdown_limit"),
        "min_total_return": request.get("min_total_return"),
        "min_annual_return": request.get("min_annual_return"),
        "min_win_rate": request.get("min_win_rate"),
        "out_of_sample_validation": bool(request.get("out_of_sample_validation", True)),
        "require_out_of_sample_validation": bool(
            request.get("require_out_of_sample_validation", False)
        ),
        "out_of_sample_ratio": _runtime_float(request.get("out_of_sample_ratio"), 0.25),
        "min_out_of_sample_sharpe": request.get("min_out_of_sample_sharpe"),
        "min_out_of_sample_trades": request.get("min_out_of_sample_trades"),
        "min_paper_trading_days": _runtime_int(request.get("min_paper_trading_days"), 7),
    }
    if bool(request.get("robustness_validation", False)) or bool(
        request.get("require_robustness_validation", False)
    ):
        quality_gates.update(
            {
                "robustness_validation": bool(request.get("robustness_validation", False)),
                "require_robustness_validation": bool(
                    request.get("require_robustness_validation", False)
                ),
                "robustness_methods": list(request.get("robustness_methods") or ["monte_carlo"]),
                "min_robustness_score": _runtime_float(
                    request.get("min_robustness_score"),
                    55.0,
                ),
                "robustness_monte_carlo_iterations": _runtime_int(
                    request.get("robustness_monte_carlo_iterations"),
                    300,
                ),
            }
        )

    record = AIStrategyResearchRunRecord(
        run_id=run_id,
        prompt=str(request.get("prompt") or task.message or "AI research task snapshot"),
        symbol=str(request.get("symbol") or ""),
        symbol_name=str(request.get("symbol_name") or request.get("symbol") or ""),
        timeframe=str(request.get("timeframe") or "1d"),
        timeframe_n=_runtime_int(request.get("timeframe_n"), 1),
        start_date=_runtime_text(request.get("start_date"), None),
        end_date=_runtime_text(request.get("end_date"), None),
        initial_cash=_runtime_float(
            task.backtest_environment.get("initial_cash")
            if isinstance(task.backtest_environment, dict)
            else None,
            _runtime_float(request.get("initial_cash"), 100000.0),
        ),
        commission=_runtime_float(
            task.backtest_environment.get("commission")
            if isinstance(task.backtest_environment, dict)
            else None,
            _runtime_float(request.get("commission"), 0.001),
        ),
        annual_days=_runtime_int(
            task.backtest_environment.get("annual_days")
            if isinstance(task.backtest_environment, dict)
            else None,
            _runtime_int(request.get("annual_days"), 252),
        ),
        calc_method=_runtime_text(
            task.backtest_environment.get("calc_method")
            if isinstance(task.backtest_environment, dict)
            else None,
            _runtime_text(request.get("calc_method"), "simple"),
        )
        or "simple",
        weight_mode=_runtime_text(
            task.backtest_environment.get("weight_mode")
            if isinstance(task.backtest_environment, dict)
            else None,
            _runtime_text(request.get("weight_mode"), "equal"),
        )
        or "equal",
        group_name=_runtime_text(request.get("group_name"), None),
        asset_specs=dict(task.asset_specs or {}),
        backtest_environment=dict(task.backtest_environment or {}),
        knowledge_base_id=_runtime_text(request.get("knowledge_base_id"), None),
        thinking_mode=bool(request.get("thinking_mode", False)),
        status=status,
        achieved=bool(task.achieved),
        target_sharpe=_runtime_float(
            request.get("target_sharpe"), float(task.target_sharpe or 0.0)
        ),
        quality_gates=quality_gates,
        min_total_trades=_runtime_int(request.get("min_total_trades"), 0),
        max_iterations=_runtime_int(
            task.max_iterations, _runtime_int(request.get("max_iterations"), 1)
        ),
        backtest_timeout_seconds=_runtime_float(request.get("backtest_timeout_seconds"), 600.0),
        poll_interval_seconds=_runtime_float(request.get("poll_interval_seconds"), 2.0),
        iteration_count=max(_runtime_int(task.iteration_count, 0), len(iterations)),
        best_iteration=_optional_gate_int(best_iteration),
        best_sharpe=_runtime_float(
            task.best_sharpe,
            _runtime_float(best_payload.get("sharpe_ratio"), 0.0),
        ),
        best_quality_score=_runtime_float(task.best_quality_score, 0.0),
        best_quality_gate_evaluations=list(task.best_quality_gate_evaluations or []),
        robustness_validation=_task_snapshot_robustness_payload(task, best_payload),
        best_diagnostics=dict(task.best_diagnostics or {}),
        best_metrics=best_metrics,
        best_strategy_id=task.best_strategy_id
        or _strategy_id_from_iteration_payload(best_payload)
        or None,
        best_strategy_name=task.best_strategy_name,
        research_workspace_id=str(workspace.id),
        mandate_id=_runtime_text(request.get("mandate_id"), None),
        seed_strategy_id=_runtime_text(request.get("seed_strategy_id"), None),
        continued_from_run_id=_runtime_text(
            task.continued_from_run_id,
            _runtime_text(request.get("continue_from_run_id"), None),
        ),
        continuation_source=str(continuation_context.get("source") or ""),
        continuation_context=continuation_context,
        pipeline=pipeline,
        promotion_audit=list(task.promotion_audit or []),
        next_actions=_task_snapshot_next_actions(task, stage),
        started_at=task.started_at or task.submitted_at,
        completed_at=task.completed_at or task.started_at or task.submitted_at,
        iterations=iterations,
    )
    return _research_run_record_with_promotion_audit(
        _research_run_record_without_sensitive_handoff(record)
    )


def _task_snapshot_iterations_for_run_record(
    task: AIStrategyResearchTaskResponse,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for payload in (task.best_iteration_payload, task.latest_iteration):
        if isinstance(payload, dict):
            candidates.append(_task_iteration_payload_for_run_record(payload))
    result: list[dict[str, Any]] = []
    seen_iterations: set[int] = set()
    for payload in candidates:
        iteration = _optional_gate_int(payload.get("iteration"))
        if iteration is not None and iteration in seen_iterations:
            continue
        if iteration is not None:
            seen_iterations.add(iteration)
        result.append(payload)
    return result


def _task_snapshot_robustness_payload(
    task: AIStrategyResearchTaskResponse,
    best_payload: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(task.robustness_validation, dict) and task.robustness_validation:
        return dict(task.robustness_validation)
    status = best_payload.get("robustness_status")
    result = best_payload.get("robustness_result")
    gates = best_payload.get("robustness_gate_evaluations")
    failures = best_payload.get("robustness_failures")
    failure_reason = best_payload.get("robustness_failure_reason")
    if not any(value not in (None, "", [], {}) for value in (status, result, gates, failures)):
        return {}
    return {
        "status": status,
        "result": dict(result) if isinstance(result, dict) else {},
        "gate_evaluations": list(gates) if isinstance(gates, list) else [],
        "failures": list(failures) if isinstance(failures, list) else [],
        "failure_reason": failure_reason,
    }


def _task_iteration_payload_for_run_record(payload: dict[str, Any]) -> dict[str, Any]:
    item = dict(payload)
    strategy = item.get("strategy")
    if isinstance(strategy, dict) and not isinstance(item.get("strategy_snapshot"), dict):
        item["strategy_snapshot"] = _task_strategy_snapshot(strategy)
    unit = item.get("unit")
    if isinstance(unit, dict) and not isinstance(item.get("unit_snapshot"), dict):
        item["unit_snapshot"] = _task_unit_snapshot(unit)
    run_result = item.get("run_result")
    if isinstance(run_result, dict):
        if "task_id" not in item and run_result.get("task_id"):
            item["task_id"] = run_result.get("task_id")
        if "run_status" not in item and run_result.get("status"):
            item["run_status"] = run_result.get("status")
    unit_status = item.get("unit_status")
    if isinstance(unit_status, dict):
        if "run_status" not in item and unit_status.get("run_status"):
            item["run_status"] = unit_status.get("run_status")
        if "task_id" not in item and unit_status.get("last_task_id"):
            item["task_id"] = unit_status.get("last_task_id")
        metrics = unit_status.get("metrics_snapshot")
        if isinstance(metrics, dict) and not isinstance(item.get("metrics"), dict):
            item["metrics"] = dict(metrics)
    return _omit_sensitive_handoff(item)


def _task_strategy_snapshot(strategy: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "id": strategy.get("id"),
            "name": strategy.get("name"),
            "description": strategy.get("description"),
            "code": strategy.get("code"),
            "params": dict(strategy.get("params") or {})
            if isinstance(strategy.get("params"), dict)
            else {},
            "category": strategy.get("category"),
            "created_at": strategy.get("created_at"),
            "updated_at": strategy.get("updated_at"),
        }.items()
        if value not in (None, "")
    }


def _task_unit_snapshot(unit: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        key: value
        for key, value in {
            "id": unit.get("id"),
            "workspace_id": unit.get("workspace_id"),
            "group_name": unit.get("group_name"),
            "strategy_id": unit.get("strategy_id"),
            "strategy_name": unit.get("strategy_name"),
            "symbol": unit.get("symbol"),
            "symbol_name": unit.get("symbol_name"),
            "timeframe": unit.get("timeframe"),
            "timeframe_n": unit.get("timeframe_n"),
            "category": unit.get("category"),
            "data_config": dict(unit.get("data_config") or {})
            if isinstance(unit.get("data_config"), dict)
            else {},
            "unit_settings": dict(unit.get("unit_settings") or {})
            if isinstance(unit.get("unit_settings"), dict)
            else {},
            "params": dict(unit.get("params") or {})
            if isinstance(unit.get("params"), dict)
            else {},
            "optimization_config": dict(unit.get("optimization_config") or {})
            if isinstance(unit.get("optimization_config"), dict)
            else {},
            "gateway_config": _dict_payload(_omit_sensitive_handoff(unit.get("gateway_config"))),
            "trading_mode": unit.get("trading_mode"),
            "lock_trading": unit.get("lock_trading"),
            "lock_running": unit.get("lock_running"),
        }.items()
        if value not in (None, "")
    }
    return snapshot


def _task_snapshot_best_iteration(iterations: list[dict[str, Any]]) -> int | None:
    if not iterations:
        return None
    best = max(iterations, key=_iteration_payload_rank)
    return _optional_gate_int(best.get("iteration"))


def _merged_task_metrics(*values: Any) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for value in values:
        if isinstance(value, dict):
            metrics.update(value)
    return metrics


def _task_snapshot_continuation_context(
    task: AIStrategyResearchTaskResponse,
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    context = dict(task.continuation_context or {})
    source = str(context.get("source") or task.continuation_source or "").strip()
    stage = str(pipeline.get("current_stage") or task.current_stage or "").strip()
    if stage == "interrupted":
        source = "research_interrupted"
        context.update(
            {
                "source": source,
                "run_id": task.run_id,
                "task_id": task.task_id,
                "interrupted_stage": stage,
                "interrupted_backtest_task_id": pipeline.get("interrupted_backtest_task_id"),
                "quality_gate_failures": [
                    task.error or task.message or "AI research task interrupted before completion"
                ],
                "pipeline": pipeline,
            }
        )
    elif source:
        context["source"] = source
    if task.run_id and not context.get("run_id"):
        context["run_id"] = task.run_id
    return _research_record_continuation_context(context)


def _task_snapshot_next_actions(
    task: AIStrategyResearchTaskResponse,
    stage: str,
) -> list[str]:
    actions = [str(item).strip() for item in task.next_actions or [] if str(item or "").strip()]
    if stage == "interrupted":
        has_strategy_snapshot = bool(
            task.best_strategy_id or task.best_iteration_payload or task.latest_iteration
        )
        if has_strategy_snapshot:
            actions.append("AI投研任务在服务重启或进程中断前未完成，可从当前最佳策略快照继续投研。")
        else:
            actions.append(
                "AI投研任务在服务重启或进程中断前未完成，且尚未形成可复用策略快照；请用原请求重新启动投研。"
            )
    if not actions and task.message:
        actions.append(str(task.message).strip())
    return list(dict.fromkeys(item for item in actions if item))


def _research_run_record_history_rank(record: AIStrategyResearchRunRecord) -> tuple[Any, ...]:
    return (
        _research_run_record_stage_rank(record),
        1 if record.live_trading_prepared else 0,
        1 if record.live_handoff_approval is not None else 0,
        1 if record.live_handoff is not None else 0,
        1 if record.paper_review_ready_for_live else 0,
        1 if record.paper_review_status else 0,
        1 if record.paper_trading_started else 0,
        1 if record.paper_handoff else 0,
        len(record.paper_review_evaluations or []),
        len(record.live_readiness_checklist or []),
        len(record.promotion_audit or []),
        len(record.iterations or []),
        str(record.completed_at or ""),
        str(record.started_at or ""),
    )


def _research_run_record_stage_rank(record: AIStrategyResearchRunRecord) -> int:
    pipeline = record.pipeline if isinstance(record.pipeline, dict) else {}
    stage = str(pipeline.get("current_stage") or "").strip()
    order = {
        "configuration_invalid": 0,
        "cancelled": 1,
        "interrupted": 2,
        "research_iteration": 2,
        "backtest_failed": 2,
        "backtest_timeout": 2,
        "quality_achieved": 3,
        "paper_trading": 4,
        "paper_trading_failed": 5,
        "paper_review": 6,
        "live_candidate": 7,
        "live_handoff": 8,
        "live_trading_prepare": 9,
    }
    return order.get(stage, 0)


def _coerce_research_run_record(value: Any) -> AIStrategyResearchRunRecord | None:
    if isinstance(value, AIStrategyResearchRunRecord):
        return _research_run_record_with_pipeline(value)
    if not isinstance(value, dict):
        return None
    try:
        return _research_run_record_with_pipeline(AIStrategyResearchRunRecord.model_validate(value))
    except Exception:
        return None


def _research_run_record_with_pipeline(
    record: AIStrategyResearchRunRecord,
) -> AIStrategyResearchRunRecord:
    record = _research_run_record_without_sensitive_handoff(record)
    record = _research_run_record_with_live_readiness_freshness(record)
    if not record.pipeline:
        record = record.model_copy(update={"pipeline": _pipeline_summary_from_record(record)})
    return _research_run_record_with_promotion_audit(record)


def _run_record_with_missing_paper_target(
    record: AIStrategyResearchRunRecord,
    *,
    reason: str,
) -> AIStrategyResearchRunRecord:
    paper_trading_error = str(reason or "Paper trading target is missing").strip()
    handoff = _research_record_handoff_payload(
        {
            **dict(record.paper_handoff or {}),
            "paper_target_missing": {
                "reason": paper_trading_error,
                "paper_workspace_id": record.paper_workspace_id,
                "paper_unit_id": record.paper_unit_id,
            },
        }
    )
    pipeline = _pipeline_summary(
        status=record.status,
        achieved=record.achieved,
        iteration_count=record.iteration_count,
        max_iterations=record.max_iterations,
        out_of_sample_validation=bool(
            (record.quality_gates or {}).get("out_of_sample_validation", False)
        ),
        validation_status=_record_best_validation_status(record),
        robustness_validation=bool(
            (record.quality_gates or {}).get("robustness_validation", False)
        ),
        robustness_status=_record_best_robustness_status(record),
        paper_trading_started=False,
        paper_trading_error=paper_trading_error,
        paper_review_status=None,
        paper_review_ready_for_live=False,
        workflow_mode=record.workflow_mode,
        workflow_steps=record.workflow_steps,
    )
    return _research_run_record_with_promotion_audit(
        record.model_copy(
            update={
                "paper_trading_started": False,
                "paper_review_status": None,
                "paper_review_ready_for_live": False,
                "paper_reviewed_at": None,
                "paper_review_evaluations": [],
                "paper_review_next_actions": [],
                "live_readiness_checklist": [],
                "live_readiness_expires_at": None,
                "live_handoff": None,
                "live_handoff_approval": None,
                "live_workspace_id": None,
                "live_workspace_name": None,
                "live_unit_id": None,
                "live_trading_prepared": False,
                "live_trading_prepared_at": None,
                "paper_handoff": handoff,
                "pipeline": pipeline,
                "next_actions": [
                    f"模拟交易目标缺失：{paper_trading_error}",
                    "重新创建或选择模拟交易工作区后，可从该投研记录重新启动模拟交易。",
                    "如目标缺失由策略脚本或资产参数导致，可从该记录继续自动投研。",
                ],
            }
        )
    )


def _research_run_record_with_live_readiness_freshness(
    record: AIStrategyResearchRunRecord,
) -> AIStrategyResearchRunRecord:
    if (
        not record.paper_review_ready_for_live
        or record.paper_review_status != "ready_for_live_candidate"
        or not record.live_readiness_expires_at
    ):
        return record

    expires_at = _parse_utc_datetime(record.live_readiness_expires_at)
    if expires_at is None or expires_at > datetime.now(timezone.utc):
        return record

    checklist = _expired_live_readiness_checklist(record)
    next_actions = [
        "实盘候选复核已过期，重新复核模拟交易指标后再进入实盘审批。",
        "过期不会删除历史模拟交易证据，但不能直接作为当前实盘候选使用。",
    ]
    pipeline = _pipeline_summary_from_record(
        record,
        paper_review_status="live_readiness_expired",
        paper_review_ready_for_live=False,
        live_readiness_checklist=checklist,
        live_readiness_expires_at=record.live_readiness_expires_at,
    )
    paper_handoff = _research_record_handoff_payload(
        _paper_handoff_with_live_readiness(
            record.paper_handoff,
            checklist,
            expires_at=record.live_readiness_expires_at,
        )
    )
    expired_record = record.model_copy(
        update={
            "paper_review_status": "live_readiness_expired",
            "paper_review_ready_for_live": False,
            "live_readiness_checklist": checklist,
            "paper_handoff": paper_handoff,
            "pipeline": pipeline,
            "next_actions": next_actions,
        }
    )
    if record.live_handoff is None:
        return expired_record
    return _run_record_with_live_handoff(
        expired_record,
        _build_live_handoff_package(expired_record),
    )


def _freshened_run_record_needs_persist(record: AIStrategyResearchRunRecord) -> bool:
    return (
        record.paper_review_status == "live_readiness_expired"
        and not record.paper_review_ready_for_live
        and bool(record.live_readiness_expires_at)
    )


def _raw_run_record_needs_freshness_persist(raw: dict[str, Any], *, force: bool = False) -> bool:
    if force:
        return True
    pipeline = raw.get("pipeline") if isinstance(raw.get("pipeline"), dict) else {}
    return (
        str(raw.get("paper_review_status") or "") != "live_readiness_expired"
        or bool(raw.get("paper_review_ready_for_live"))
        or str(pipeline.get("current_stage") or "") == "live_candidate"
    )


def _run_record_should_auto_refresh_paper_review(record: AIStrategyResearchRunRecord) -> bool:
    if not record.achieved or not record.paper_trading_started:
        return False
    if not record.paper_workspace_id:
        return False
    if record.live_handoff_approval is not None and record.live_handoff_approval.approved:
        return False
    return True


def _run_record_should_invalidate_missing_paper_target(
    record: AIStrategyResearchRunRecord,
) -> bool:
    handoff = dict(record.paper_handoff or {})
    return any(
        handoff.get(key) not in (None, "")
        for key in ("paper_task_id", "paper_run_status", "paper_started_at")
    )


def _paper_review_refresh_has_meaningful_change(
    record: AIStrategyResearchRunRecord,
    *,
    monitoring_plan: list[dict[str, Any]],
    review_status: str,
    ready_for_live: bool,
    evaluation_payload: list[dict[str, Any]],
    next_actions: list[str],
) -> bool:
    if [dict(item) for item in monitoring_plan] != [
        dict(item) for item in record.paper_monitoring_plan
    ]:
        return True
    if review_status != record.paper_review_status:
        return True
    if ready_for_live != record.paper_review_ready_for_live:
        return True
    if evaluation_payload != [dict(item) for item in record.paper_review_evaluations]:
        return True
    return next_actions != list(record.paper_review_next_actions or [])


def _paper_review_status_requires_unit_lock(status: str | None) -> bool:
    return str(status or "").strip() in {"needs_research_review", "live_readiness_expired"}


def _paper_unit_needs_review_lock(
    unit: StrategyUnitResponse | None,
    review_status: str | None,
) -> bool:
    if unit is None or not _paper_review_status_requires_unit_lock(review_status):
        return False
    settings = dict(unit.unit_settings or {})
    return not (
        unit.lock_trading
        and unit.lock_running
        and isinstance(settings.get("ai_research_review_lock"), dict)
    )


def _paper_review_unit_lock_payload(
    record: AIStrategyResearchRunRecord,
    *,
    review_status: str,
    reviewed_at: str,
    evaluations: list[AIStrategyPaperTradingRuleEvaluation],
    next_actions: list[str],
    stop_results: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_rules = [item.model_dump(mode="json") for item in evaluations if item.status == "failed"]
    return {
        "run_id": record.run_id,
        "research_workspace_id": record.research_workspace_id,
        "paper_workspace_id": record.paper_workspace_id,
        "paper_unit_id": record.paper_unit_id,
        "status": review_status,
        "reviewed_at": reviewed_at,
        "failed_rules": failed_rules,
        "stop_results": [dict(item) for item in stop_results],
        "next_actions": list(next_actions),
        "reason": "AI paper review failed; trading and running are locked until research review.",
    }


def _paper_review_lock_payload_for_record(
    payload: Any,
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    lock_payload = dict(payload)
    lock_payload.setdefault("run_id", record.run_id)
    lock_payload.setdefault("research_workspace_id", record.research_workspace_id)
    lock_payload.setdefault("paper_workspace_id", record.paper_workspace_id)
    lock_payload.setdefault("paper_unit_id", record.paper_unit_id)
    return lock_payload


def _paper_review_lock_from_pipeline(pipeline: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(pipeline, dict):
        return None
    return _dict_payload(pipeline.get("paper_review_lock")) or None


def _pipeline_with_paper_review_lock(
    pipeline: dict[str, Any] | None,
    review_lock: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(pipeline or {})
    if review_lock:
        lock_payload = dict(review_lock)
        payload["paper_review_lock"] = lock_payload
        payload["paper_unit_locked"] = True
        payload["paper_unit_stopped"] = bool(lock_payload.get("stop_results"))
        return payload

    payload.pop("paper_review_lock", None)
    payload.pop("paper_unit_locked", None)
    payload.pop("paper_unit_stopped", None)
    return payload


def _paper_handoff_with_review_lock(
    handoff: dict[str, Any] | None,
    review_lock: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(handoff or {})
    if review_lock:
        payload["paper_review_lock"] = dict(review_lock)
    else:
        payload.pop("paper_review_lock", None)
    return payload


def _append_unique_text(items: list[str], value: str) -> list[str]:
    texts = [str(item).strip() for item in items if str(item or "").strip()]
    text = str(value or "").strip()
    if text:
        texts.append(text)
    return list(dict.fromkeys(texts))
