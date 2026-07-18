"""Paper-trading review and live-handoff readiness helpers."""

# Workflow helpers are injected after every stage is loaded; see research.__init__.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from .shared import *


def _build_research_run_record(
    *,
    run_id: str,
    request: AIStrategyResearchRunRequest,
    response: AIStrategyResearchRunResponse,
    started_at: str,
    completed_at: str,
) -> AIStrategyResearchRunRecord:
    best_iteration = None
    if response.best_iteration is not None:
        best_iteration = next(
            (item for item in response.iterations if item.iteration == response.best_iteration),
            None,
        )
    unit_settings = dict(best_iteration.unit.unit_settings or {}) if best_iteration else {}
    data_config = dict(best_iteration.unit.data_config or {}) if best_iteration else {}
    asset_specs = (
        _asset_specs_from_unit(best_iteration.unit)
        if best_iteration is not None
        else _summarize_asset_specs_for_prompt(_resolve_research_asset_specs(request))
    )
    backtest_environment = (
        _paper_backtest_environment(request, best_iteration)
        if best_iteration is not None
        else _request_backtest_environment(request, asset_specs)
    )
    best_strategy = response.best_strategy
    paper = response.paper_trading
    record = AIStrategyResearchRunRecord(
        run_id=run_id,
        prompt=request.prompt,
        workflow_mode=request.workflow_mode,
        workflow_steps=list(request.workflow_steps),
        symbol=request.symbol,
        symbol_name=request.symbol_name or request.symbol,
        timeframe=request.timeframe,
        timeframe_n=request.timeframe_n,
        start_date=_runtime_text(data_config.get("start_date"), request.start_date),
        end_date=_runtime_text(data_config.get("end_date"), request.end_date),
        initial_cash=_runtime_float(unit_settings.get("initial_cash"), request.initial_cash),
        commission=_runtime_float(unit_settings.get("commission"), request.commission),
        annual_days=_runtime_int(unit_settings.get("annual_days"), request.annual_days),
        calc_method=_runtime_text(unit_settings.get("calc_method"), request.calc_method),
        weight_mode=_runtime_text(unit_settings.get("weight_mode"), request.weight_mode),
        group_name=request.group_name
        or (best_iteration.unit.group_name if best_iteration is not None else None)
        or (best_strategy.name if best_strategy else None),
        asset_specs=asset_specs,
        backtest_environment=backtest_environment,
        knowledge_base_id=request.knowledge_base_id,
        thinking_mode=request.thinking_mode,
        status=response.status,
        achieved=response.achieved,
        target_sharpe=response.target_sharpe,
        quality_gates=_quality_gates_payload(request),
        min_total_trades=request.min_total_trades,
        max_iterations=request.max_iterations,
        backtest_timeout_seconds=request.backtest_timeout_seconds,
        poll_interval_seconds=request.poll_interval_seconds,
        iteration_count=len(response.iterations),
        best_iteration=response.best_iteration,
        best_sharpe=best_iteration.sharpe_ratio
        if best_iteration is not None
        else _metric_float(response.best_metrics, "sharpe_ratio", "sharpe", "sharpeRatio"),
        best_quality_score=_promotion_quality_score(best_iteration),
        best_quality_gate_evaluations=_promotion_gate_evaluations(best_iteration),
        robustness_validation=_iteration_robustness_payload(best_iteration),
        best_diagnostics=best_iteration.diagnostics
        if best_iteration is not None
        else response.best_diagnostics,
        best_metrics=response.best_metrics,
        best_strategy_id=best_strategy.id if best_strategy else None,
        best_strategy_name=best_strategy.name if best_strategy else None,
        research_workspace_id=response.research_workspace.id,
        mandate_id=request.mandate_id,
        seed_strategy_id=request.seed_strategy_id,
        continued_from_run_id=request.continue_from_run_id,
        continuation_source=_continuation_source_from_context(request.continuation_context),
        continuation_context=_research_record_continuation_context(request.continuation_context),
        paper_workspace_id=paper.workspace.id if paper else None,
        paper_workspace_name=paper.workspace.name if paper else request.paper_workspace_name,
        paper_unit_id=paper.unit.id if paper else None,
        paper_trading_started=bool(paper.started) if paper else False,
        paper_monitoring_plan=response.paper_monitoring_plan,
        paper_handoff=_research_record_handoff_payload(paper.handoff if paper else None),
        pipeline=response.pipeline,
        next_actions=response.next_actions,
        started_at=started_at,
        completed_at=completed_at,
        iterations=[_compact_research_iteration(item) for item in response.iterations],
    )
    return _research_run_record_with_promotion_audit(
        _research_run_record_without_sensitive_handoff(record)
    )


def _apply_initial_paper_review_to_run_record(
    record: AIStrategyResearchRunRecord,
    *,
    paper_trading: AIStrategyPaperTradingStart | None,
) -> AIStrategyResearchRunRecord:
    if paper_trading is None or not paper_trading.started:
        return record

    monitoring_plan = _resolve_paper_monitoring_plan(record, paper_trading.unit)
    evaluations = _evaluate_paper_monitoring_plan(
        monitoring_plan,
        record=record,
        unit=paper_trading.unit,
        unit_status=None,
    )
    ready_for_live = bool(evaluations) and all(item.passed for item in evaluations)
    review_status = _paper_review_status(
        record,
        workspace=paper_trading.workspace,
        unit=paper_trading.unit,
        evaluations=evaluations,
        ready_for_live=ready_for_live,
    )
    reviewed_at = _utc_iso_now()
    live_readiness_expires_at = (
        _utc_iso_add_days(reviewed_at, _LIVE_READINESS_VALID_DAYS) if ready_for_live else None
    )
    live_readiness_checklist = _live_readiness_checklist(
        record,
        status=review_status,
        evaluations=evaluations,
        monitoring_plan=monitoring_plan,
        reviewed_at=reviewed_at,
        expires_at=live_readiness_expires_at,
    )
    pipeline = _pipeline_summary_from_record(
        record,
        paper_trading_started=record.paper_trading_started,
        paper_review_status=review_status,
        paper_review_ready_for_live=ready_for_live,
        live_readiness_checklist=live_readiness_checklist,
        live_readiness_expires_at=live_readiness_expires_at,
    )
    paper_handoff = _research_record_handoff_payload(
        _paper_handoff_with_live_readiness(
            record.paper_handoff,
            live_readiness_checklist,
            expires_at=live_readiness_expires_at,
        )
    )
    return _research_run_record_with_promotion_audit(
        record.model_copy(
            update={
                "paper_monitoring_plan": monitoring_plan,
                "paper_review_status": review_status,
                "paper_review_ready_for_live": ready_for_live,
                "paper_reviewed_at": reviewed_at,
                "paper_review_evaluations": [item.model_dump(mode="json") for item in evaluations],
                "paper_review_next_actions": _paper_review_next_actions(
                    review_status,
                    evaluations=evaluations,
                    monitoring_plan=monitoring_plan,
                    live_readiness_expires_at=live_readiness_expires_at,
                ),
                "live_readiness_checklist": live_readiness_checklist,
                "live_readiness_expires_at": live_readiness_expires_at,
                "paper_handoff": paper_handoff,
                "pipeline": pipeline,
            }
        )
    )


def _apply_initial_live_handoff_to_run_record(
    record: AIStrategyResearchRunRecord,
) -> AIStrategyResearchRunRecord:
    if record.live_handoff is not None:
        return record
    if not (
        record.paper_trading_started
        and record.paper_review_ready_for_live
        and record.paper_review_status == "ready_for_live_candidate"
    ):
        return record
    package = _build_live_handoff_package(record)
    return _run_record_with_live_handoff(record, package)


def _build_paper_trading_handoff(
    *,
    run_id: str,
    research_workspace_id: str,
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
    promoted_at: str,
) -> dict[str, Any]:
    asset_specs = _asset_specs_from_unit(best_iteration.unit)
    for source in (
        dict(request.data_config or {}),
        dict(request.unit_settings or {}),
        _dict_payload(request.gateway_config),
    ):
        _merge_asset_spec_maps(asset_specs, _asset_specs_from_mapping(source))
    gateway_config = _dict_payload(best_iteration.unit.gateway_config)
    gateway_config.update(_dict_payload(request.gateway_config))
    return {
        "run_id": run_id,
        "source": "ai_strategy_research",
        "research_workspace_id": research_workspace_id,
        "research_unit_id": best_iteration.unit.id,
        "research_strategy_id": best_iteration.strategy.id,
        "research_strategy_name": best_iteration.strategy.name,
        "seed_strategy_id": request.seed_strategy_id,
        "continued_from_run_id": request.continue_from_run_id,
        "selected_iteration": best_iteration.iteration,
        "target_sharpe": request.target_sharpe,
        "quality_gates": _quality_gates_payload(request),
        "backtest_timeout_seconds": request.backtest_timeout_seconds,
        "poll_interval_seconds": request.poll_interval_seconds,
        "achieved_sharpe": best_iteration.sharpe_ratio,
        "achieved_quality_score": _promotion_quality_score(best_iteration),
        "achieved_quality_gate_evaluations": _promotion_gate_evaluations(best_iteration),
        "achieved_diagnostics": best_iteration.diagnostics,
        "total_trades": best_iteration.total_trades,
        "best_metrics": best_iteration.metrics,
        "backtest_environment": _paper_backtest_environment(request, best_iteration),
        "asset_specs": asset_specs,
        "gateway_config": gateway_config,
        "out_of_sample_validation": {
            "status": best_iteration.validation_status,
            "window": best_iteration.validation_window,
            "metrics": best_iteration.validation_metrics,
            "gate_evaluations": best_iteration.validation_gate_evaluations,
            "failures": best_iteration.validation_failures,
            "failure_reason": best_iteration.validation_failure_reason,
        },
        "robustness_validation": _iteration_robustness_payload(best_iteration),
        "paper_monitoring_plan": _paper_monitoring_plan(request, best_iteration),
        "symbol": request.symbol,
        "symbol_name": request.symbol_name or request.symbol,
        "timeframe": request.timeframe,
        "timeframe_n": request.timeframe_n,
        "promoted_at": promoted_at,
    }


def _compact_research_iteration(item: AIStrategyResearchIteration) -> dict[str, Any]:
    unit_status = item.unit_status.run_status if item.unit_status is not None else None
    return {
        "iteration": item.iteration,
        "strategy_id": item.strategy.id,
        "strategy_name": item.strategy.name,
        "strategy_snapshot": _compact_strategy_snapshot(item.strategy),
        "unit_id": item.unit.id,
        "unit_snapshot": _compact_unit_snapshot(item.unit),
        "task_id": item.run_result.task_id,
        "run_status": unit_status or item.run_result.status,
        "metrics": item.metrics,
        "sharpe_ratio": item.sharpe_ratio,
        "total_trades": item.total_trades,
        "validation_status": item.validation_status,
        "validation_window": item.validation_window,
        "validation_metrics": item.validation_metrics,
        "validation_gate_evaluations": item.validation_gate_evaluations,
        "validation_failures": item.validation_failures,
        "validation_failure_reason": item.validation_failure_reason,
        "validation_unit_id": item.validation_unit.id if item.validation_unit else None,
        "validation_task_id": item.validation_run_result.task_id
        if item.validation_run_result
        else None,
        "validation_run_status": item.validation_unit_status.run_status
        if item.validation_unit_status
        else None,
        "robustness_status": item.robustness_status,
        "robustness_result": item.robustness_result,
        "robustness_gate_evaluations": item.robustness_gate_evaluations,
        "robustness_failures": item.robustness_failures,
        "robustness_failure_reason": item.robustness_failure_reason,
        "quality_score": item.quality_score,
        "quality_gate_evaluations": item.quality_gate_evaluations,
        "passed": item.passed,
        "failure_reason": item.failure_reason,
        "quality_gate_failures": item.quality_gate_failures,
        "diagnostics": item.diagnostics,
        "improvement_plan": item.improvement_plan,
        "improvement_notes": item.improvement_notes,
        "next_actions": item.next_actions,
    }


def _compact_strategy_snapshot(strategy: StrategyResponse) -> dict[str, Any]:
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "code": strategy.code,
        "params": {
            key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            for key, value in dict(strategy.params or {}).items()
        },
        "category": strategy.category,
        "created_at": strategy.created_at.isoformat()
        if hasattr(strategy.created_at, "isoformat")
        else strategy.created_at,
        "updated_at": strategy.updated_at.isoformat()
        if hasattr(strategy.updated_at, "isoformat")
        else strategy.updated_at,
    }


def _compact_unit_snapshot(unit: StrategyUnitResponse) -> dict[str, Any]:
    return {
        "id": unit.id,
        "workspace_id": unit.workspace_id,
        "group_name": unit.group_name,
        "strategy_id": unit.strategy_id,
        "strategy_name": unit.strategy_name,
        "symbol": unit.symbol,
        "symbol_name": unit.symbol_name,
        "timeframe": unit.timeframe,
        "timeframe_n": unit.timeframe_n,
        "category": unit.category,
        "data_config": dict(unit.data_config or {}),
        "unit_settings": dict(unit.unit_settings or {}),
        "params": dict(unit.params or {}),
        "optimization_config": dict(unit.optimization_config or {}),
        "gateway_config": _dict_payload(unit.gateway_config),
        "trading_mode": unit.trading_mode,
        "lock_trading": unit.lock_trading,
        "lock_running": unit.lock_running,
    }


def _dict_payload(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="python", exclude_none=True)
        return dict(payload) if isinstance(payload, dict) else {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _iteration_diagnostics(
    request: AIStrategyResearchRunRequest,
    *,
    iteration: int,
    metrics: dict[str, Any],
    run_status: str | None,
    quality_gate_failures: list[str],
    quality_gate_evaluations: list[dict[str, Any]],
    failure_reason: str | None,
    previous_iteration: AIStrategyResearchIteration | None = None,
    quality_score: float | None = None,
) -> dict[str, Any]:
    metric_snapshot = _research_metric_snapshot(metrics, request)
    failure_categories = _failure_categories(quality_gate_failures, run_status, failure_reason)
    strengths = _gate_strengths(quality_gate_evaluations)
    weaknesses = _gate_weaknesses(quality_gate_evaluations, quality_gate_failures, failure_reason)
    iteration_progress = _iteration_progress_diagnostics(
        previous_iteration,
        metrics=metrics,
        metric_snapshot=metric_snapshot,
        quality_score=float(quality_score or 0.0),
    )
    improvement_plan = _improvement_plan_from_failures(
        request,
        metrics=metrics,
        run_status=run_status,
        quality_gate_failures=quality_gate_failures,
        failure_categories=failure_categories,
        iteration_progress=iteration_progress,
    )
    gate_gaps = _gate_gap_summary(quality_gate_evaluations)
    passed = bool(run_status == "completed" and not quality_gate_failures)
    summary = (
        f"第 {iteration} 轮已通过全部质量门槛，可进入模拟交易候选。"
        if passed
        else f"第 {iteration} 轮未通过质量门槛，主要问题："
        + ("、".join(failure_categories) if failure_categories else (failure_reason or "指标不足"))
        + "。"
    )
    return {
        "summary": summary,
        "metric_snapshot": metric_snapshot,
        "failure_categories": failure_categories,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "gate_gaps": gate_gaps,
        "iteration_progress": iteration_progress,
        "improvement_plan": improvement_plan,
        "promotion_ready": passed,
    }


def _iteration_progress_diagnostics(
    previous_iteration: AIStrategyResearchIteration | None,
    *,
    metrics: dict[str, Any],
    metric_snapshot: dict[str, Any],
    quality_score: float,
) -> dict[str, Any]:
    if previous_iteration is None:
        return {
            "status": "baseline",
            "previous_iteration": None,
            "summary": "首轮回测作为后续自动改进的基准。",
        }

    previous_metrics = dict(previous_iteration.metrics or {})
    current_sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    previous_sharpe = _quality_metric(
        previous_metrics,
        "sharpe_ratio",
        "sharpe",
        "sharpeRatio",
    )
    current_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    previous_trades = previous_iteration.total_trades
    current_drawdown = metric_snapshot.get("max_drawdown")
    previous_drawdown = _optional_gate_number(
        dict(previous_iteration.diagnostics or {}).get("metric_snapshot", {}).get("max_drawdown")
        if isinstance(dict(previous_iteration.diagnostics or {}).get("metric_snapshot"), dict)
        else None
    )
    quality_delta = round(quality_score - float(previous_iteration.quality_score or 0.0), 6)
    sharpe_delta = (
        round(float(current_sharpe) - float(previous_sharpe), 6)
        if current_sharpe is not None and previous_sharpe is not None
        else None
    )
    trade_delta = int(current_trades - previous_trades)
    drawdown_delta = (
        round(float(current_drawdown) - float(previous_drawdown), 6)
        if current_drawdown is not None and previous_drawdown is not None
        else None
    )

    status = "stalled"
    if quality_delta > 1e-6 or (sharpe_delta is not None and sharpe_delta > 1e-6):
        status = "improved"
    if quality_delta < -1e-6 or (sharpe_delta is not None and sharpe_delta < -1e-6):
        status = "regressed"

    summary_map = {
        "improved": "本轮自动改稿相对上一轮有改善，可继续沿当前方向微调。",
        "regressed": "本轮自动改稿相对上一轮退化，下一轮应回退激进改动并缩小参数搜索步长。",
        "stalled": "本轮自动改稿相对上一轮基本停滞，下一轮需要改变信号结构或风险约束。",
    }
    return {
        "status": status,
        "previous_iteration": previous_iteration.iteration,
        "quality_score_delta": quality_delta,
        "sharpe_delta": sharpe_delta,
        "total_trades_delta": trade_delta,
        "max_drawdown_delta": drawdown_delta,
        "summary": summary_map[status],
    }


def _research_metric_snapshot(
    metrics: dict[str, Any],
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "sharpe": _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio"),
        "total_trades": float(_metric_int(metrics, "total_trades", "totalTrades", "trades")),
    }
    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        snapshot["max_drawdown"] = (
            abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if max_drawdown is not None
            else None
        )
    if request.min_total_return is not None:
        total_return = _quality_metric(metrics, "total_return", "totalReturn", "return")
        snapshot["total_return"] = (
            _align_metric_scale(total_return, request.min_total_return)
            if total_return is not None
            else None
        )
    if request.min_annual_return is not None:
        annual_return = _quality_metric(metrics, "annual_return", "annualReturn")
        snapshot["annual_return"] = (
            _align_metric_scale(annual_return, request.min_annual_return)
            if annual_return is not None
            else None
        )
    if request.min_win_rate is not None:
        win_rate = _quality_metric(metrics, "win_rate", "winRate")
        snapshot["win_rate"] = (
            _align_metric_scale(win_rate, request.min_win_rate) if win_rate is not None else None
        )
    return snapshot


def _failure_categories(
    quality_gate_failures: list[str],
    run_status: str | None,
    failure_reason: str | None,
) -> list[str]:
    categories: list[str] = []
    status = str(run_status or "").strip()
    if status and status != "completed":
        categories.append("backtest_runtime")
    for failure in quality_gate_failures:
        lowered = failure.lower()
        if "out-of-sample" in lowered or "out of sample" in lowered or "样本外" in failure:
            categories.append("out_of_sample")
        if (
            "robustness" in lowered
            or "overfitting" in lowered
            or "monte carlo" in lowered
            or "稳健" in failure
            or "过拟合" in failure
        ):
            categories.append("robustness")
        if _is_paper_trading_start_failure(failure):
            categories.append("paper_trading_start")
        elif "drawdown" in lowered or "回撤" in failure:
            categories.append("drawdown")
        elif "sharpe" in lowered:
            categories.append("sharpe")
        elif "annual" in lowered or "年化" in failure:
            categories.append("annual_return")
        elif "return" in lowered or "收益" in failure:
            categories.append("total_return")
        elif "win rate" in lowered or "胜率" in failure:
            categories.append("win_rate")
        elif "trade" in lowered or "trades" in lowered or "交易" in failure:
            categories.append("trade_count")
        elif "cost" in lowered or "slippage" in lowered or "费用" in failure or "滑点" in failure:
            categories.append("execution_cost")
        elif (
            "valuation" in lowered
            or "asset spec" in lowered
            or "asset_specs" in lowered
            or "margin" in lowered
            or "multiplier" in lowered
            or "估值" in failure
            or "资产规格" in failure
            or "合约乘数" in failure
            or "保证金" in failure
        ):
            categories.append("valuation_context")
        elif (
            "live handoff" in lowered
            or "approval" in lowered
            or "实盘交接" in failure
            or "审批" in failure
            or "驳回" in failure
        ):
            categories.append("live_handoff_rejected")
    if not categories and failure_reason:
        categories.append("unknown")
    return list(dict.fromkeys(categories))


def _is_paper_trading_start_failure(failure: str) -> bool:
    lowered = failure.lower()
    return (
        "paper trading start" in lowered
        or "paper_trading_failed" in lowered
        or "模拟交易启动" in failure
    )


def _gate_strengths(evaluations: list[dict[str, Any]]) -> list[str]:
    strengths: list[str] = []
    for item in evaluations:
        if not bool(item.get("passed")):
            continue
        label = str(item.get("label") or item.get("key") or "metric")
        actual = item.get("actual")
        target = item.get("target")
        strengths.append(
            f"{label} 已达标：{_format_gate_value(actual)} / {_format_gate_value(target)}"
        )
    return strengths


def _gate_weaknesses(
    evaluations: list[dict[str, Any]],
    quality_gate_failures: list[str],
    failure_reason: str | None,
) -> list[str]:
    weaknesses: list[str] = []
    for item in evaluations:
        if bool(item.get("passed")):
            continue
        label = str(item.get("label") or item.get("key") or "metric")
        actual = item.get("actual")
        target = item.get("target")
        weaknesses.append(
            f"{label} 未达标：{_format_gate_value(actual)} / {_format_gate_value(target)}"
        )
    if not weaknesses:
        weaknesses.extend(str(item) for item in quality_gate_failures if str(item or "").strip())
    if failure_reason and failure_reason not in weaknesses:
        weaknesses.append(str(failure_reason))
    return weaknesses


def _format_gate_value(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def _improvement_plan_from_failures(
    request: AIStrategyResearchRunRequest,
    *,
    metrics: dict[str, Any],
    run_status: str | None,
    quality_gate_failures: list[str],
    failure_categories: list[str],
    iteration_progress: dict[str, Any] | None = None,
) -> list[str]:
    if run_status == "completed" and not quality_gate_failures:
        return [
            "冻结当前策略版本作为候选，不再自动改稿。",
            "进入模拟交易后优先验证成交、滑点、费用和样本外收益稳定性。",
        ]

    plan: list[str] = []
    categories = set(failure_categories)
    progress_status = str((iteration_progress or {}).get("status") or "").strip()
    if progress_status == "regressed":
        plan.append("本轮自动改稿相对上一轮退化，优先回退激进参数变化并保留上一轮有效结构。")
    elif progress_status == "stalled":
        plan.append(
            "连续改稿改善有限，下一版需要改变信号组合、过滤条件或风控结构，而不是只微调参数。"
        )
    if "backtest_runtime" in categories:
        plan.append("先修复策略运行错误、数据源缺口或超时问题，再继续生成下一版。")
    if "paper_trading_start" in categories:
        plan.append("优先复核模拟交易单元创建、网关配置、策略脚本依赖和资产参数后再重试。")
    if "out_of_sample" in categories:
        plan.append(
            "样本外验证未通过，降低过拟合风险，优先保留稳健信号、减少参数敏感度并扩大验证样本。"
        )
    if "robustness" in categories:
        plan.append(
            "稳健性验证未通过，减少参数自由度、降低换手和信号噪声，优先通过 Monte Carlo/参数扰动复核。"
        )
    if "trade_count" in categories:
        plan.append(
            "有效交易样本数不足，放宽入场过滤、缩短慢速指标窗口或降低确认条件，"
            "并加入止损、止盈、反向信号或最长持仓 bars 退出，确保至少产生闭合交易。"
        )
    if "sharpe" in categories:
        plan.append("减少低质量入场，增加趋势/波动过滤，并优化止盈止损以提升收益波动比。")
    if "drawdown" in categories:
        plan.append("收紧单笔风险、止损距离和最大持仓暴露，必要时增加冷却期。")
    if "total_return" in categories or "annual_return" in categories:
        plan.append("优化出场和持仓周期，避免过早止盈，同时保持回撤约束。")
    if "win_rate" in categories:
        plan.append("增加信号确认条件或行情状态过滤，降低震荡行情中的错误入场。")
    if "execution_cost" in categories:
        plan.append("降低换手率和无效交易，按模拟成交费用/滑点重新校准手续费与出入场阈值。")
    if "valuation_context" in categories:
        plan.append(
            "先修正交易所/本地资产规格上下文，确保合约乘数、保证金、手续费和持仓估值口径一致后再改稿。"
        )
    if "live_handoff_rejected" in categories:
        plan.append(
            "针对实盘交接驳回意见降低上线风险，重新校准仓位、止损、成交成本和审批清单后再进入模拟复核。"
        )

    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    if sharpe is not None and sharpe < request.target_sharpe and "sharpe" not in categories:
        plan.append("Sharpe 接近但未达目标，优先做参数微调而不是重写策略结构。")

    if not plan:
        plan.append("保留现有策略主体，针对失败指标生成小步参数调整版本继续回测。")
    return list(dict.fromkeys(plan))


def _paper_monitoring_plan(
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
) -> list[dict[str, Any]]:
    return _paper_monitoring_plan_from_metrics(
        request,
        best_iteration.metrics,
        commission=_paper_effective_commission(request, best_iteration),
    )


def _paper_monitoring_plan_from_metrics(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    commission: float | None = None,
) -> list[dict[str, Any]]:
    drawdown_limit = _paper_drawdown_limit(request, metrics)
    execution_commission = request.commission if commission is None else commission
    plan = [
        {
            "key": "rolling_sharpe",
            "label": "模拟交易滚动 Sharpe",
            "metric": "rolling_sharpe",
            "window": "30 trading days or 20 closed trades",
            "direction": "min",
            "threshold": round(max(request.target_sharpe * 0.6, 0.3), 3),
            "action": "低于阈值时暂停放大资金，回到研究工作区做样本外复核。",
        },
        {
            "key": "drawdown_guard",
            "label": "模拟交易最大回撤",
            "metric": "max_drawdown",
            "window": "since paper start",
            "direction": "max",
            "threshold": drawdown_limit,
            "action": "超过阈值时停止自动交易，并检查止损、仓位和市场状态过滤。",
        },
        {
            "key": "trade_sample",
            "label": "最小成交样本",
            "metric": "closed_trades",
            "window": "paper validation period",
            "direction": "min",
            "threshold": max(int(request.min_total_trades), 20),
            "action": "成交样本不足时延长模拟观察期，不进入实盘。",
        },
        {
            "key": "execution_cost",
            "label": "成交成本偏离",
            "metric": "slippage_and_commission_delta",
            "window": "each review",
            "direction": "max",
            "threshold": round(max(float(execution_commission or 0.0) * 2, 0.001), 6),
            "action": "费用或滑点明显高于回测假设时，更新手续费/滑点配置后重新回测。",
        },
        {
            "key": "valuation_confidence",
            "label": "估值与资产规格确认",
            "metric": "valuation_confidence",
            "window": "each review",
            "direction": "min",
            "threshold": 1.0,
            "action": "持仓估值、合约乘数、保证金或手续费未确认时，先修正交易所/本地资产信息后再复核。",
        },
    ]
    if request.min_paper_trading_days > 0:
        plan.append(
            {
                "key": "paper_observation_period",
                "label": "最小模拟观察期",
                "metric": "paper_elapsed_days",
                "window": "since paper start",
                "direction": "min",
                "threshold": float(request.min_paper_trading_days),
                "action": "模拟运行观察期不足时继续 paper，不进入实盘交接。",
            }
        )
    return plan


def _paper_effective_commission(
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
) -> float:
    unit_settings = {
        **dict(best_iteration.unit.unit_settings or {}),
        **dict(request.unit_settings or {}),
    }
    return _runtime_float(unit_settings.get("commission"), request.commission)


def _paper_backtest_environment(
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
) -> dict[str, Any]:
    unit_settings = {
        **dict(best_iteration.unit.unit_settings or {}),
        **dict(request.unit_settings or {}),
    }
    data_config = {
        **dict(best_iteration.unit.data_config or {}),
        **dict(request.data_config or {}),
    }
    environment: dict[str, Any] = {
        "initial_cash": _runtime_float(unit_settings.get("initial_cash"), request.initial_cash),
        "commission": _runtime_float(unit_settings.get("commission"), request.commission),
        "annual_days": _runtime_int(unit_settings.get("annual_days"), request.annual_days),
        "calc_method": _runtime_text(unit_settings.get("calc_method"), request.calc_method),
        "weight_mode": _runtime_text(unit_settings.get("weight_mode"), request.weight_mode),
        "start_date": _runtime_text(data_config.get("start_date"), request.start_date),
        "end_date": _runtime_text(data_config.get("end_date"), request.end_date),
    }
    for key in ("multiplier", "margin", "asset_spec_source"):
        if unit_settings.get(key) not in (None, ""):
            environment[key] = unit_settings[key]
    return environment


def _paper_drawdown_limit(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
) -> float:
    if request.max_drawdown_limit is not None:
        return round(abs(float(request.max_drawdown_limit)), 3)
    observed = _quality_metric(
        metrics, "max_drawdown", "maxDrawdown", "drawdown", "max_dd", "maxDD"
    )
    if observed is not None:
        comparable = abs(_align_metric_scale(observed, 10.0))
        return round(max(comparable * 1.25, 5.0), 3)
    return 15.0


def _resolve_paper_monitoring_plan(
    record: AIStrategyResearchRunRecord,
    unit: StrategyUnitResponse | None,
) -> list[dict[str, Any]]:
    if record.paper_monitoring_plan:
        return [dict(item) for item in record.paper_monitoring_plan]

    if record.paper_handoff:
        handoff_plan = _paper_monitoring_plan_from_handoff(record.paper_handoff)
        if handoff_plan:
            return handoff_plan

    handoff = _unit_ai_research_handoff(unit)
    raw_plan = handoff.get("paper_monitoring_plan")
    if isinstance(raw_plan, list):
        return [dict(item) for item in raw_plan if isinstance(item, dict)]

    request = _paper_start_request_from_record(record, AIStrategyPaperTradingStartRequest())
    return _paper_monitoring_plan_from_metrics(request, dict(record.best_metrics or {}))


def _paper_monitoring_plan_from_handoff(handoff: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(handoff, dict):
        return []
    raw_plan = handoff.get("paper_monitoring_plan")
    if not isinstance(raw_plan, list):
        return []
    return [dict(item) for item in raw_plan if isinstance(item, dict)]


def _unit_ai_research_handoff(unit: StrategyUnitResponse | None) -> dict[str, Any]:
    if unit is None:
        return {}
    settings = dict(unit.unit_settings or {})
    handoff = settings.get("ai_research_handoff")
    return dict(handoff) if isinstance(handoff, dict) else {}


def _evaluate_paper_monitoring_plan(
    monitoring_plan: list[dict[str, Any]],
    *,
    record: AIStrategyResearchRunRecord | None = None,
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
) -> list[AIStrategyPaperTradingRuleEvaluation]:
    evaluations: list[AIStrategyPaperTradingRuleEvaluation] = []
    for raw_rule in monitoring_plan:
        metric = str(raw_rule.get("metric") or "").strip()
        threshold = _optional_gate_number(raw_rule.get("threshold"))
        if not metric or threshold is None:
            continue
        actual, source = _lookup_paper_metric(
            metric,
            record=record,
            unit=unit,
            unit_status=unit_status,
        )
        actual = _normalize_paper_metric_value(metric, actual, float(threshold))
        direction = str(raw_rule.get("direction") or "min").strip().lower()
        passed = _paper_rule_passed(actual, threshold, direction)
        status = _paper_rule_status(
            key=str(raw_rule.get("key") or metric),
            actual=actual,
            passed=passed,
        )
        gap_fields = _paper_rule_gap_fields(actual, float(threshold), direction)
        evaluations.append(
            AIStrategyPaperTradingRuleEvaluation(
                key=str(raw_rule.get("key") or metric),
                label=str(raw_rule.get("label") or metric),
                metric=metric,
                window=str(raw_rule.get("window") or ""),
                direction=direction if direction in {"min", "max"} else "min",
                threshold=float(threshold),
                actual=actual,
                source=source,
                status=status,
                passed=passed,
                **gap_fields,
                action=str(raw_rule.get("action") or ""),
            )
        )
    return evaluations


def _normalize_paper_metric_value(
    metric: str,
    actual: float | None,
    threshold: float,
) -> float | None:
    if actual is None:
        return None
    if metric == "max_drawdown":
        return abs(_align_metric_scale(actual, threshold))
    return actual


def _paper_rule_status(
    *,
    key: str,
    actual: float | None,
    passed: bool,
) -> str:
    if actual is None:
        return "pending"
    if passed:
        return "passed"
    if key in {"trade_sample", "paper_observation_period"}:
        return "pending"
    return "failed"


_PAPER_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "rolling_sharpe": ("rolling_sharpe", "paper_sharpe", "sharpe_ratio", "sharpe"),
    "max_drawdown": ("max_drawdown", "maxDrawdown", "drawdown", "max_dd", "maxDD"),
    "closed_trades": ("closed_trades", "total_trades", "totalTrades", "trades"),
    "slippage_and_commission_delta": (
        "slippage_and_commission_delta",
        "execution_cost_delta",
        "cost_delta",
        "commission_delta",
    ),
}


_EXECUTION_COST_RATE_ALIASES = (
    "actual_slippage_and_commission_rate",
    "slippage_and_commission_rate",
    "actual_execution_cost_rate",
    "execution_cost_rate",
    "actual_cost_rate",
    "cost_rate",
)
_COMMISSION_RATE_ALIASES = (
    "actual_commission_rate",
    "actual_fee_rate",
    "commission_rate",
    "fee_rate",
    "taker_commission_rate",
    "taker_fee_rate",
)
_SLIPPAGE_RATE_ALIASES = (
    "actual_slippage_rate",
    "slippage_rate",
    "slippage",
)
_EXPECTED_EXECUTION_COST_RATE_ALIASES = (
    "expected_slippage_and_commission_rate",
    "expected_execution_cost_rate",
    "backtest_execution_cost_rate",
    "assumed_execution_cost_rate",
)
_EXPECTED_COMMISSION_RATE_ALIASES = (
    "expected_commission_rate",
    "backtest_commission_rate",
    "assumed_commission_rate",
    "commission_assumption",
)
_EXPECTED_SLIPPAGE_RATE_ALIASES = (
    "expected_slippage_rate",
    "backtest_slippage_rate",
    "assumed_slippage_rate",
)


def _lookup_paper_metric(
    metric: str,
    *,
    record: AIStrategyResearchRunRecord | None = None,
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
) -> tuple[float | None, str | None]:
    if metric == "valuation_confidence":
        return _lookup_paper_valuation_confidence(
            record=record,
            unit=unit,
            unit_status=unit_status,
        )
    if metric == "paper_elapsed_days":
        return _lookup_paper_elapsed_days(record=record, unit=unit, unit_status=unit_status)

    aliases = _PAPER_METRIC_ALIASES.get(metric, (metric,))
    sources: list[tuple[str, dict[str, Any]]] = []
    if unit_status is not None:
        sources.extend(
            [
                ("unit_status.metrics_snapshot", dict(unit_status.metrics_snapshot or {})),
                ("unit_status.trading_snapshot", dict(unit_status.trading_snapshot or {})),
            ]
        )
    if unit is not None:
        sources.extend(
            [
                ("unit.metrics_snapshot", dict(unit.metrics_snapshot or {})),
                ("unit.trading_snapshot", dict(unit.trading_snapshot or {})),
            ]
        )

    for source_name, payload in sources:
        value = _lookup_nested_metric(payload, aliases)
        if value is not None:
            return value, source_name
    if metric == "slippage_and_commission_delta":
        return _lookup_paper_execution_cost_delta(record=record, sources=sources)
    return None, None


def _lookup_paper_execution_cost_delta(
    *,
    record: AIStrategyResearchRunRecord | None,
    sources: list[tuple[str, dict[str, Any]]],
) -> tuple[float | None, str | None]:
    expected_total = _expected_execution_cost_rate(record)
    if expected_total is None:
        return None, None

    for source_name, payload in sources:
        actual_total, actual_source = _actual_execution_cost_rate(payload)
        if actual_total is None:
            continue
        expected_from_payload = _execution_cost_rate_from_payload(
            payload,
            total_aliases=_EXPECTED_EXECUTION_COST_RATE_ALIASES,
            commission_aliases=_EXPECTED_COMMISSION_RATE_ALIASES,
            slippage_aliases=_EXPECTED_SLIPPAGE_RATE_ALIASES,
        )
        baseline = expected_from_payload if expected_from_payload is not None else expected_total
        return round(abs(actual_total - baseline), 8), f"{source_name}.{actual_source}"
    return None, None


def _expected_execution_cost_rate(
    record: AIStrategyResearchRunRecord | None,
) -> float | None:
    if record is None:
        return None
    environment = dict(record.backtest_environment or {})
    expected = _execution_cost_rate_from_payload(
        environment,
        total_aliases=_EXPECTED_EXECUTION_COST_RATE_ALIASES,
        commission_aliases=_EXPECTED_COMMISSION_RATE_ALIASES,
        slippage_aliases=_EXPECTED_SLIPPAGE_RATE_ALIASES,
    )
    if expected is not None:
        return expected
    commission = _optional_gate_number(environment.get("commission"))
    if commission is None:
        commission = _optional_gate_number(record.commission)
    slippage = _optional_gate_number(environment.get("slippage"))
    return float(commission or 0.0) + float(slippage or 0.0)


def _actual_execution_cost_rate(payload: dict[str, Any]) -> tuple[float | None, str | None]:
    actual_total = _lookup_nested_metric(payload, _EXECUTION_COST_RATE_ALIASES)
    if actual_total is not None:
        return actual_total, "execution_cost_rate"
    commission = _lookup_nested_metric(payload, _COMMISSION_RATE_ALIASES)
    slippage = _lookup_nested_metric(payload, _SLIPPAGE_RATE_ALIASES)
    if commission is None and slippage is None:
        return None, None
    parts = []
    if commission is not None:
        parts.append("commission_rate")
    if slippage is not None:
        parts.append("slippage_rate")
    return float(commission or 0.0) + float(slippage or 0.0), "+".join(parts)


def _execution_cost_rate_from_payload(
    payload: dict[str, Any],
    *,
    total_aliases: tuple[str, ...],
    commission_aliases: tuple[str, ...],
    slippage_aliases: tuple[str, ...],
) -> float | None:
    total = _lookup_nested_metric(payload, total_aliases)
    if total is not None:
        return total
    commission = _lookup_nested_metric(payload, commission_aliases)
    slippage = _lookup_nested_metric(payload, slippage_aliases)
    if commission is None and slippage is None:
        return None
    return float(commission or 0.0) + float(slippage or 0.0)


def _lookup_paper_elapsed_days(
    *,
    record: AIStrategyResearchRunRecord | None,
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
) -> tuple[float | None, str | None]:
    candidates: list[tuple[str, Any]] = []
    if record is not None:
        candidates.extend(
            [
                (
                    "record.paper_handoff.paper_started_at",
                    record.paper_handoff.get("paper_started_at"),
                ),
                ("record.paper_handoff.promoted_at", record.paper_handoff.get("promoted_at")),
            ]
        )
    if unit_status is not None:
        trading_snapshot = dict(unit_status.trading_snapshot or {})
        handoff = _dict_payload(trading_snapshot.get("ai_research_handoff"))
        candidates.extend(
            [
                (
                    "unit_status.trading_snapshot.paper_started_at",
                    trading_snapshot.get("paper_started_at"),
                ),
                (
                    "unit_status.trading_snapshot.ai_research_handoff.paper_started_at",
                    handoff.get("paper_started_at"),
                ),
                (
                    "unit_status.trading_snapshot.ai_research_handoff.promoted_at",
                    handoff.get("promoted_at"),
                ),
            ]
        )
    if unit is not None:
        unit_handoff = _unit_ai_research_handoff(unit)
        trading_snapshot = dict(unit.trading_snapshot or {})
        snapshot_handoff = _dict_payload(trading_snapshot.get("ai_research_handoff"))
        candidates.extend(
            [
                (
                    "unit.unit_settings.ai_research_handoff.paper_started_at",
                    unit_handoff.get("paper_started_at"),
                ),
                (
                    "unit.unit_settings.ai_research_handoff.promoted_at",
                    unit_handoff.get("promoted_at"),
                ),
                (
                    "unit.trading_snapshot.paper_started_at",
                    trading_snapshot.get("paper_started_at"),
                ),
                (
                    "unit.trading_snapshot.ai_research_handoff.paper_started_at",
                    snapshot_handoff.get("paper_started_at"),
                ),
                (
                    "unit.trading_snapshot.ai_research_handoff.promoted_at",
                    snapshot_handoff.get("promoted_at"),
                ),
            ]
        )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    for source, value in candidates:
        started_at = _parse_utc_datetime(str(value)) if value not in (None, "") else None
        if started_at is None:
            continue
        elapsed_days = max((now - started_at).total_seconds() / 86400.0, 0.0)
        return round(elapsed_days, 6), source
    return None, None


def _lookup_paper_valuation_confidence(
    *,
    record: AIStrategyResearchRunRecord | None,
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
) -> tuple[float | None, str | None]:
    snapshots: list[tuple[str, dict[str, Any]]] = []
    if unit_status is not None:
        snapshots.append(("unit_status.trading_snapshot", dict(unit_status.trading_snapshot or {})))
    if unit is not None:
        snapshots.append(("unit.trading_snapshot", dict(unit.trading_snapshot or {})))

    for source_name, payload in snapshots:
        if not payload:
            continue
        warnings = _paper_valuation_warnings(payload)
        if warnings:
            return 0.0, source_name

        status = str(payload.get("valuation_status") or "").strip().lower()
        if status in {"confirmed", "gateway_confirmed"}:
            return 1.0, source_name

        row_statuses = _paper_position_row_statuses(payload)
        if row_statuses:
            if row_statuses <= {"confirmed", "gateway_confirmed"}:
                return 1.0, f"{source_name}.positions"
            if row_statuses & {"estimated", "stale_fallback", "unknown"}:
                return 0.0, f"{source_name}.positions"

        if status in {"estimated", "stale_fallback", "unknown"}:
            return 0.0, source_name

    if unit is not None:
        source = _unit_contract_metadata_source(unit)
        if source:
            return 1.0, source

    if record is not None:
        source = _record_asset_specs_source(record)
        if source:
            return 1.0, source

    return None, None


def _record_asset_specs_source(record: AIStrategyResearchRunRecord) -> str | None:
    if _contract_metadata_has_complete_asset_specs(
        dict(record.asset_specs or {}),
        fallback_symbol=record.symbol,
        backtest_environment=dict(record.backtest_environment or {}),
    ):
        return "record.asset_specs"
    paper_handoff = dict(record.paper_handoff or {})
    handoff_specs = paper_handoff.get("asset_specs")
    handoff_environment = paper_handoff.get("backtest_environment")
    if isinstance(handoff_specs, dict) and _contract_metadata_has_complete_asset_specs(
        handoff_specs,
        fallback_symbol=record.symbol,
        backtest_environment=handoff_environment if isinstance(handoff_environment, dict) else {},
    ):
        return "record.paper_handoff.asset_specs"
    backtest_environment = dict(record.backtest_environment or {})
    if _payload_has_complete_asset_spec_fields(
        backtest_environment,
        symbol=record.symbol,
        backtest_environment=backtest_environment,
    ):
        return "record.backtest_environment"
    if isinstance(handoff_environment, dict) and _payload_has_complete_asset_spec_fields(
        handoff_environment,
        symbol=record.symbol,
        backtest_environment=handoff_environment,
    ):
        return "record.paper_handoff.backtest_environment"
    return None


def _paper_valuation_warnings(payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = [
        str(item).strip() for item in payload.get("valuation_warnings") or [] if str(item).strip()
    ]
    positions = payload.get("positions")
    if isinstance(positions, list):
        for row in positions:
            if not isinstance(row, dict):
                continue
            warnings.extend(
                str(item).strip()
                for item in row.get("valuation_warnings") or []
                if str(item).strip()
            )
    return warnings


def _paper_position_row_statuses(payload: dict[str, Any]) -> set[str]:
    positions = payload.get("positions")
    if not isinstance(positions, list):
        return set()
    statuses: set[str] = set()
    for row in positions:
        if not isinstance(row, dict):
            continue
        status = str(row.get("valuation_status") or "").strip().lower()
        if status:
            statuses.add(status)
    return statuses


def _unit_contract_metadata_source(unit: StrategyUnitResponse) -> str | None:
    sources = (
        ("unit.unit_settings", dict(unit.unit_settings or {})),
        ("unit.data_config", dict(unit.data_config or {})),
        ("unit.params", dict(unit.params or {})),
        ("unit.gateway_config", dict(unit.gateway_config or {})),
    )
    metadata_keys = ("contract_metadata", "contracts", "contract_specs", "instrument_specs")
    for source_name, payload in sources:
        for key in metadata_keys:
            metadata = payload.get(key)
            if isinstance(metadata, dict) and _contract_metadata_has_complete_asset_specs(
                metadata,
                fallback_symbol=str(unit.symbol or ""),
                backtest_environment=dict(unit.unit_settings or {}),
            ):
                return f"{source_name}.{key}"
    return None


_ASSET_SPEC_MULTIPLIER_KEYS = (
    "multiplier",
    "mult",
    "contract_multiplier",
    "contractMultiplier",
    "contract_size",
    "contractSize",
    "contract_notional_value",
    "okx_contract_value",
    "ctVal",
    "ctMult",
    "volume_multiple",
    "VolumeMultiple",
    "CONTRACT_MULTIPLIER",
)
_ASSET_SPEC_MARGIN_KEYS = (
    "margin",
    "margin_rate",
    "marginRate",
    "margin_ratio",
    "marginRatio",
    "long_margin_rate",
    "longMarginRatio",
    "short_margin_rate",
    "shortMarginRatio",
    "LongMarginRatio",
    "ShortMarginRatio",
    "LongMarginRatioByMoney",
    "ShortMarginRatioByMoney",
    "leverage",
    "lever",
    "max_leverage",
    "margin_amount",
    "marginAmount",
    "initial_margin_per_lot",
    "margin_initial",
    "marginInitial",
    "initial_margin_amount",
    "initialMargin",
    "initialMarginRatio",
    "MARGIN_RATIO",
    "MARGIN_PER_LOT",
    "LONG_MARGIN_AMOUNT",
    "SHORT_MARGIN_AMOUNT",
)
_ASSET_SPEC_COMMISSION_KEYS = (
    "commission",
    "commission_rate",
    "commissionRate",
    "open_commission_rate",
    "openCommissionRate",
    "close_commission_rate",
    "closeCommissionRate",
    "close_today_commission_rate",
    "closeTodayCommissionRate",
    "maker_commission_rate",
    "maker_fee_rate",
    "makerFeeRate",
    "taker_commission_rate",
    "taker_fee_rate",
    "takerFeeRate",
    "fee_rate",
    "commission_amount",
    "commissionAmount",
    "open_fee_amount",
    "open_commission_amount",
    "close_fee_amount",
    "close_commission_amount",
    "close_today_fee_amount",
    "close_today_commission_amount",
    "OPEN_FEE_RATE",
    "CLOSE_FEE_RATE",
    "CLOSE_TODAY_FEE_RATE",
    "OPEN_FEE_AMOUNT",
    "CLOSE_FEE_AMOUNT",
    "CLOSE_TODAY_FEE_AMOUNT",
)
_DERIVATIVE_ASSET_TYPE_MARKERS = (
    "future",
    "futures",
    "fut",
    "swap",
    "perp",
    "perpetual",
    "option",
    "options",
    "contract",
    "margin",
    "cfd",
)
_CASH_ASSET_TYPE_MARKERS = (
    "stock",
    "equity",
    "spot",
    "cash",
    "fund",
    "etf",
    "index",
)


def _contract_metadata_has_asset_specs(metadata: dict[str, Any]) -> bool:
    for value in metadata.values():
        if not isinstance(value, dict):
            continue
        if _payload_has_asset_spec_fields(value):
            return True
    return False


def _contract_metadata_has_complete_asset_specs(
    metadata: dict[str, Any],
    *,
    fallback_symbol: str = "",
    backtest_environment: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(metadata, dict):
        return False
    environment = dict(backtest_environment or {})
    for symbol, value in metadata.items():
        if not isinstance(value, dict):
            continue
        if _payload_has_complete_asset_spec_fields(
            value,
            symbol=str(symbol or fallback_symbol or ""),
            backtest_environment=environment,
        ):
            return True
    return False


def _payload_has_complete_asset_spec_fields(
    payload: dict[str, Any],
    *,
    symbol: str = "",
    backtest_environment: dict[str, Any] | None = None,
) -> bool:
    missing = _asset_spec_missing_requirements(
        payload,
        symbol=symbol,
        backtest_environment=backtest_environment,
    )
    return bool(payload) and not missing


def _asset_spec_missing_requirements(
    payload: dict[str, Any],
    *,
    symbol: str = "",
    backtest_environment: dict[str, Any] | None = None,
) -> list[str]:
    spec = dict(payload or {})
    environment = dict(backtest_environment or {})
    missing: list[str] = []
    requires_margin = _asset_spec_requires_margin(spec, symbol=symbol)
    if requires_margin and not _asset_spec_has_number(spec, *_ASSET_SPEC_MULTIPLIER_KEYS):
        missing.append("合约乘数")
    if not _asset_spec_has_commission(spec, environment):
        missing.append("手续费")
    if requires_margin and not _asset_spec_has_number(
        spec,
        *_ASSET_SPEC_MARGIN_KEYS,
        extra=environment,
    ):
        missing.append("保证金/杠杆")
    return missing


def _asset_spec_has_commission(
    spec: dict[str, Any],
    environment: dict[str, Any],
) -> bool:
    if _asset_spec_has_number(spec, *_ASSET_SPEC_COMMISSION_KEYS):
        return True
    if _optional_gate_number(environment.get("commission")) is not None:
        return True
    commission_source = str(environment.get("commission_source") or "").strip().lower()
    if commission_source == "user_override":
        return _optional_gate_number(environment.get("commission")) is not None
    return False


def _asset_spec_has_number(
    payload: dict[str, Any],
    *keys: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    for source in (payload, extra or {}):
        for key in keys:
            if _optional_gate_number(source.get(key)) is not None:
                return True
    return False


def _asset_spec_requires_margin(spec: dict[str, Any], *, symbol: str = "") -> bool:
    type_text = " ".join(
        str(spec.get(key) or "")
        for key in (
            "asset_type",
            "instType",
            "contract_type",
            "ctType",
            "type",
        )
    ).lower()
    if any(marker in type_text for marker in _DERIVATIVE_ASSET_TYPE_MARKERS):
        return True
    source_text = " ".join(
        str(spec.get(key) or "")
        for key in (
            "source",
            "asset_spec_source",
        )
    ).lower()
    if any(
        marker in source_text
        for marker in ("future", "futures", "ctp", "swap", "perp", "option", "margin", "cfd")
    ):
        return True
    if any(marker in type_text for marker in _CASH_ASSET_TYPE_MARKERS):
        return False
    multiplier = _first_asset_spec_number(spec, *_ASSET_SPEC_MULTIPLIER_KEYS)
    if multiplier is not None and abs(multiplier - 1.0) > 1e-12:
        return True
    text = str(symbol or spec.get("symbol") or "").strip()
    if re.fullmatch(r"[A-Za-z]{1,4}\d{3,5}(?:\.[A-Za-z]+)?", text):
        return True
    return False


def _payload_has_asset_spec_fields(payload: dict[str, Any]) -> bool:
    return any(
        payload.get(key) not in (None, "")
        for key in (
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
            "commission",
            "commission_rate",
            "open_commission_rate",
            "close_commission_rate",
            "close_today_commission_rate",
            "commission_amount",
            "maker_commission_rate",
            "taker_commission_rate",
            "maker_fee_rate",
            "taker_fee_rate",
            "fee_rate",
            "tick_size",
            "lot_size",
            "min_order_size",
        )
    )


def _lookup_nested_metric(payload: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        if alias in payload:
            value = _optional_gate_number(payload.get(alias))
            if value is not None:
                return float(value)
    for nested_key in ("metrics", "risk", "summary", "paper", "trading"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            value = _lookup_nested_metric(nested, aliases)
            if value is not None:
                return value
    return None


def _paper_rule_passed(actual: float | None, threshold: float, direction: str) -> bool:
    if actual is None:
        return False
    if direction == "max":
        return actual <= threshold
    return actual >= threshold


def _paper_rule_gap_fields(
    actual: float | None,
    threshold: float,
    direction: str,
) -> dict[str, float | None]:
    if actual is None:
        return {
            "margin": None,
            "gap": None,
            "gap_ratio": None,
            "distance_to_pass": None,
        }
    if direction == "max":
        margin = float(threshold) - float(actual)
        gap = max(float(actual) - float(threshold), 0.0)
    else:
        margin = float(actual) - float(threshold)
        gap = max(float(threshold) - float(actual), 0.0)
    return {
        "margin": _rounded_gate_delta(margin),
        "gap": _rounded_gate_delta(gap),
        "gap_ratio": _gate_gap_ratio(gap, threshold),
        "distance_to_pass": _rounded_gate_delta(gap),
    }


def _paper_review_status(
    record: AIStrategyResearchRunRecord,
    *,
    workspace: WorkspaceResponse | None,
    unit: StrategyUnitResponse | None,
    evaluations: list[AIStrategyPaperTradingRuleEvaluation],
    ready_for_live: bool,
) -> str:
    if not record.paper_trading_started:
        return "paper_not_started"
    if workspace is None:
        return "paper_workspace_missing"
    if unit is None:
        return "paper_unit_missing"
    if not evaluations:
        return "monitoring_plan_missing"
    if ready_for_live:
        return "ready_for_live_candidate"
    if any(item.status == "failed" for item in evaluations):
        return "needs_research_review"
    return "monitoring"


def _paper_review_next_actions(
    status: str,
    *,
    evaluations: list[AIStrategyPaperTradingRuleEvaluation],
    monitoring_plan: list[dict[str, Any]],
    live_readiness_expires_at: str | None = None,
) -> list[str]:
    if status == "paper_not_started":
        return ["该投研结果尚未启动模拟交易，先从历史记录发起 paper 运行。"]
    if status == "paper_workspace_missing":
        return ["未找到模拟交易工作区，检查 handoff 记录或重新启动模拟交易。"]
    if status == "paper_unit_missing":
        return ["未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。"]
    if status == "monitoring_plan_missing" or not monitoring_plan:
        return ["缺少模拟交易监控计划，重新保存投研 run record 或用当前最佳策略重启 paper。"]
    if status == "live_readiness_expired":
        return ["实盘候选复核已过期，重新复核模拟交易指标后再进入实盘审批。"]
    if status == "ready_for_live_candidate":
        actions = [
            "模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。",
            "实盘前仍需确认账户权限、合约乘数、手续费、滑点和最大风险预算。",
        ]
        if live_readiness_expires_at:
            actions.append(
                f"实盘候选有效期至 {live_readiness_expires_at}，过期后需重新复核模拟交易。"
            )
        return actions

    failed = [item for item in evaluations if item.status == "failed"]
    if failed:
        return list(dict.fromkeys([item.action for item in failed if item.action]))

    pending = [item.label for item in evaluations if item.status == "pending"]
    if pending:
        return [
            "继续收集模拟交易数据，等待以下指标形成有效样本：" + "、".join(pending),
        ]
    return ["继续观察模拟交易表现，并定期回到投研记录复核监控指标。"]


def _build_live_handoff_package(
    record: AIStrategyResearchRunRecord,
) -> AIStrategyLiveHandoffPackage:
    checklist = [dict(item) for item in record.live_readiness_checklist if isinstance(item, dict)]
    if not checklist and isinstance(record.pipeline, dict):
        checklist = [
            dict(item)
            for item in record.pipeline.get("live_readiness_checklist") or []
            if isinstance(item, dict)
        ]
    if not checklist and isinstance(record.paper_handoff, dict):
        checklist = [
            dict(item)
            for item in record.paper_handoff.get("live_readiness_checklist") or []
            if isinstance(item, dict)
        ]
    if not checklist:
        checklist = _live_readiness_checklist_from_record_review(record)
    checklist = _ensure_live_readiness_research_evidence(record, checklist)

    approvals_required = [
        item
        for item in checklist
        if str(item.get("status") or "").strip() == "pending_manual_confirmation"
    ]
    deployment_blockers = _live_handoff_deployment_blockers(record, checklist)
    ready_for_live = (
        record.achieved
        and record.paper_trading_started
        and record.paper_review_ready_for_live
        and record.paper_review_status == "ready_for_live_candidate"
        and not deployment_blockers
    )
    approval = record.live_handoff_approval
    approval_status = approval.decision if approval is not None else None
    package_status = "ready_for_approval" if ready_for_live else "blocked"
    if approval is not None:
        package_status = "approved_for_live" if approval.approved else "approval_rejected"
    handoff = _redact_sensitive_handoff(
        {
            **dict(record.paper_handoff or {}),
            "robustness_validation": _record_robustness_validation_payload(record),
            "live_handoff_generated_at": _utc_iso_now(),
            "live_handoff_ready_for_live": ready_for_live,
            "approval_required": True,
            "approval_status": approval_status,
            "approvals_required": approvals_required,
            "deployment_blockers": deployment_blockers,
        }
    )
    return AIStrategyLiveHandoffPackage(
        run_id=record.run_id,
        research_workspace_id=record.research_workspace_id,
        generated_at=str(handoff.get("live_handoff_generated_at") or _utc_iso_now()),
        ready_for_live=ready_for_live,
        status=package_status,
        approval_required=True,
        expires_at=record.live_readiness_expires_at,
        paper_workspace_id=record.paper_workspace_id,
        paper_unit_id=record.paper_unit_id,
        best_strategy_id=record.best_strategy_id,
        best_strategy_name=record.best_strategy_name,
        symbol=record.symbol,
        symbol_name=record.symbol_name,
        timeframe=record.timeframe,
        timeframe_n=record.timeframe_n,
        target_sharpe=record.target_sharpe,
        best_sharpe=record.best_sharpe,
        best_metrics=dict(record.best_metrics or {}),
        asset_specs=dict(record.asset_specs or {}),
        backtest_environment=dict(record.backtest_environment or {}),
        robustness_validation=_record_robustness_validation_payload(record),
        paper_review_status=record.paper_review_status,
        paper_reviewed_at=record.paper_reviewed_at,
        paper_review_evaluations=[
            dict(item) for item in record.paper_review_evaluations if isinstance(item, dict)
        ],
        paper_monitoring_plan=[
            dict(item) for item in record.paper_monitoring_plan if isinstance(item, dict)
        ],
        live_readiness_checklist=checklist,
        approvals_required=approvals_required,
        deployment_blockers=deployment_blockers,
        approval_status=approval_status,
        approval=approval,
        handoff=handoff,
        pipeline=dict(record.pipeline or {}),
        next_actions=list(record.next_actions or []),
    )


def _live_handoff_deployment_blockers(
    record: AIStrategyResearchRunRecord,
    checklist: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if not record.achieved:
        blockers.append("策略尚未通过投研质量门槛，不能进入实盘交接。")
    if not record.paper_trading_started:
        blockers.append("尚未启动模拟交易，不能进入实盘交接。")
    if record.paper_review_status == "live_readiness_expired":
        blockers.append("实盘候选复核已过期，需要重新复核模拟交易。")
    elif record.paper_review_status != "ready_for_live_candidate":
        status = record.paper_review_status or "paper_not_reviewed"
        blockers.append(f"模拟交易复核状态为 {status}，尚未达到实盘候选。")
    if not record.paper_review_ready_for_live:
        blockers.append("模拟交易监控计划尚未全部通过。")
    if (
        not checklist
        and record.paper_review_status == "ready_for_live_candidate"
        and record.paper_review_ready_for_live
    ):
        blockers.append("实盘交接检查清单缺失，需要重新复核模拟交易并生成审批证据。")

    for item in checklist:
        key = str(item.get("key") or "").strip()
        status = str(item.get("status") or "").strip()
        if status in {"passed", "pending_manual_confirmation"}:
            continue
        if key == "out_of_sample_validation_confirmed" and status == "skipped":
            continue
        label = str(item.get("label") or item.get("key") or "实盘检查项")
        evidence = str(item.get("evidence") or item.get("action") or "").strip()
        blockers.append(f"{label} 未满足" + (f"：{evidence}" if evidence else "。"))

    if not blockers and not record.paper_review_ready_for_live:
        blockers.extend(str(item).strip() for item in record.next_actions if str(item).strip())
    return list(dict.fromkeys(blockers))


def redact_ai_strategy_research_payload(value: Any) -> Any:
    """Return an API-safe copy of AI research payloads without credentials."""
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="python")
        redacted = _redact_sensitive_handoff(payload)
        try:
            return value.__class__.model_validate(redacted)
        except Exception:
            return redacted
    return _redact_sensitive_handoff(value)


def _redact_sensitive_handoff(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_handoff_key(str(key)):
                result[key] = "***"
            else:
                result[key] = _redact_sensitive_handoff(item)
        return result
    if isinstance(value, list):
        return [_redact_sensitive_handoff(item) for item in value]
    return value


def _omit_sensitive_handoff(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_handoff_key(str(key)):
                continue
            cleaned = _omit_sensitive_handoff(item)
            if cleaned is _SENSITIVE_OMITTED:
                continue
            result[key] = cleaned
        return result
    if isinstance(value, list):
        result_list: list[Any] = []
        for item in value:
            cleaned = _omit_sensitive_handoff(item)
            if cleaned is not _SENSITIVE_OMITTED:
                result_list.append(cleaned)
        return result_list
    if value == "***":
        return _SENSITIVE_OMITTED
    return value


def _is_sensitive_handoff_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")
    return any(part in normalized for part in _SENSITIVE_HANDOFF_KEYS)


def _live_readiness_checklist(
    record: AIStrategyResearchRunRecord,
    *,
    status: str,
    evaluations: list[AIStrategyPaperTradingRuleEvaluation],
    monitoring_plan: list[dict[str, Any]],
    reviewed_at: str,
    expires_at: str | None,
) -> list[dict[str, Any]]:
    if status != "ready_for_live_candidate":
        return []

    by_key = {item.key: item for item in evaluations}
    passed_rules = [item.key for item in evaluations if item.passed]
    performance_items = [
        item
        for key in ("rolling_sharpe", "trade_sample", "paper_observation_period")
        if (item := by_key.get(key)) is not None
    ]
    performance_evidence = "；".join(
        _live_readiness_evaluation_evidence(item) for item in performance_items
    )
    if not performance_evidence:
        performance_evidence = f"{len(passed_rules)}/{len(evaluations)} 项模拟监控规则已通过"

    checklist = [
        {
            "key": "paper_monitoring_passed",
            "label": "模拟监控通过",
            "status": "passed",
            "evidence": performance_evidence,
            "action": "保留模拟监控计划，进入人工实盘复核前继续监控同一组指标。",
            "details": {
                "reviewed_at": reviewed_at,
                "expires_at": expires_at,
                "monitoring_rule_count": len(monitoring_plan),
                "passed_rules": passed_rules,
            },
        },
        _live_readiness_research_quality_item(record),
        _live_readiness_valuation_item(record, by_key.get("valuation_confidence")),
        {
            "key": "execution_costs_confirmed",
            "label": "执行成本可接受",
            "status": _live_readiness_status_from_evaluation(by_key.get("execution_cost")),
            "evidence": _live_readiness_evaluation_evidence(
                by_key.get("execution_cost"),
                fallback="模拟交易手续费和滑点偏差在监控阈值内。",
            ),
            "action": "实盘前用券商或交易所费率重新确认佣金、滑点和最小价格变动。",
            "details": {
                "commission": record.commission,
                "symbol": record.symbol,
                "timeframe": record.timeframe,
            },
        },
        {
            "key": "risk_budget_confirmed",
            "label": "风险预算可控",
            "status": _live_readiness_status_from_evaluation(by_key.get("drawdown_guard")),
            "evidence": _live_readiness_evaluation_evidence(
                by_key.get("drawdown_guard"),
                fallback="模拟交易回撤约束在监控阈值内。",
            ),
            "action": "实盘前设置最大资金占用、单品种仓位上限、最大回撤止损和人工熔断规则。",
            "details": {
                "initial_cash": record.initial_cash,
                "quality_gates": record.quality_gates,
                "best_metrics": record.best_metrics,
            },
        },
        {
            "key": "human_approval_required",
            "label": "人工实盘审批",
            "status": "pending_manual_confirmation",
            "evidence": (
                f"模拟复核已在 {reviewed_at} 达到实盘候选状态"
                + (f"，有效期至 {expires_at}。" if expires_at else "。")
            ),
            "action": "由负责人确认账户权限、交易时段、实盘资金、应急预案和上线窗口后再切换实盘。",
            "details": {
                "run_id": record.run_id,
                "research_workspace_id": record.research_workspace_id,
                "paper_workspace_id": record.paper_workspace_id,
                "paper_unit_id": record.paper_unit_id,
                "expires_at": expires_at,
            },
        },
    ]
    out_of_sample_item = _live_readiness_out_of_sample_item(record)
    if out_of_sample_item is not None:
        checklist.insert(2, out_of_sample_item)
    robustness_item = _live_readiness_robustness_item(record)
    if robustness_item is not None:
        insert_at = 3 if out_of_sample_item is not None else 2
        checklist.insert(insert_at, robustness_item)
    return checklist


def _live_readiness_checklist_from_record_review(
    record: AIStrategyResearchRunRecord,
) -> list[dict[str, Any]]:
    if record.paper_review_status != "ready_for_live_candidate":
        return []

    evaluations: list[AIStrategyPaperTradingRuleEvaluation] = []
    for item in record.paper_review_evaluations:
        if not isinstance(item, dict):
            continue
        try:
            evaluations.append(AIStrategyPaperTradingRuleEvaluation.model_validate(item))
        except Exception:
            continue
    if not evaluations:
        return []

    return _live_readiness_checklist(
        record,
        status=record.paper_review_status,
        evaluations=evaluations,
        monitoring_plan=[
            dict(item) for item in record.paper_monitoring_plan if isinstance(item, dict)
        ],
        reviewed_at=record.paper_reviewed_at or _utc_iso_now(),
        expires_at=record.live_readiness_expires_at,
    )


def _ensure_live_readiness_research_evidence(
    record: AIStrategyResearchRunRecord,
    checklist: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not checklist:
        return checklist

    valuation_item = _live_readiness_valuation_item(record, None)
    valuation_required = bool(
        dict(valuation_item.get("details") or {}).get("asset_spec_completeness", {}).get("required")
    )
    if valuation_required:
        updated_checklist: list[dict[str, Any]] = []
        for item in checklist:
            if str(item.get("key") or "").strip() == "valuation_confirmed":
                if valuation_item["status"] != "passed":
                    updated_checklist.append(valuation_item)
                else:
                    merged = dict(item)
                    merged["details"] = {
                        **dict(item.get("details") or {}),
                        **dict(valuation_item.get("details") or {}),
                    }
                    updated_checklist.append(merged)
            else:
                updated_checklist.append(item)
        checklist = updated_checklist

    existing_keys = {str(item.get("key") or "").strip() for item in checklist}
    additions: list[dict[str, Any]] = []
    if "research_quality_confirmed" not in existing_keys:
        additions.append(_live_readiness_research_quality_item(record))
    if valuation_required and "valuation_confirmed" not in existing_keys:
        additions.append(valuation_item)
    if "out_of_sample_validation_confirmed" not in existing_keys:
        out_of_sample_item = _live_readiness_out_of_sample_item(record)
        if out_of_sample_item is not None:
            additions.append(out_of_sample_item)
    if "robustness_validation_confirmed" not in existing_keys:
        robustness_item = _live_readiness_robustness_item(record)
        if robustness_item is not None:
            additions.append(robustness_item)
    if not additions:
        return checklist

    enriched: list[dict[str, Any]] = []
    inserted = False
    for item in checklist:
        enriched.append(item)
        if not inserted and str(item.get("key") or "").strip() == "paper_monitoring_passed":
            enriched.extend(additions)
            inserted = True
    if inserted:
        return enriched
    return [*additions, *checklist]


def _live_readiness_valuation_item(
    record: AIStrategyResearchRunRecord,
    evaluation: AIStrategyPaperTradingRuleEvaluation | None,
) -> dict[str, Any]:
    completeness = _record_asset_spec_completeness(record)
    status = _live_readiness_status_from_evaluation(evaluation)
    evidence = _live_readiness_evaluation_evidence(
        evaluation,
        fallback="模拟交易估值、持仓来源、资产规格来源已确认。",
    )
    if completeness["required"] and completeness["status"] != "passed":
        status = "failed" if completeness["missing"] else "pending"
        evidence = "资产参数不完整：" + "；".join(completeness["missing"]) + "。"
    elif evaluation is None and completeness["required"] and completeness["status"] == "passed":
        status = "passed"
        evidence = "交易资产合约乘数、手续费和必要保证金/杠杆参数已确认。"

    return {
        "key": "valuation_confirmed",
        "label": "估值与资产参数确认",
        "status": status,
        "evidence": evidence,
        "action": "实盘前再次核对交易所合约乘数、保证金、手续费、持仓来源和账户估值口径。",
        "details": {
            "asset_spec_source": record.backtest_environment.get("asset_spec_source"),
            "asset_specs": record.asset_specs,
            "backtest_environment": record.backtest_environment,
            "asset_spec_completeness": completeness,
        },
    }


def _record_asset_spec_completeness(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    runtime_context = _record_runtime_context(record)
    asset_specs = (
        dict(runtime_context.get("asset_specs"))
        if isinstance(runtime_context.get("asset_specs"), dict)
        else {}
    )
    backtest_environment = (
        dict(runtime_context.get("backtest_environment"))
        if isinstance(runtime_context.get("backtest_environment"), dict)
        else {}
    )
    required = bool(asset_specs) or _asset_spec_requires_margin(
        {
            "symbol": record.symbol,
            "source": backtest_environment.get("asset_spec_source"),
            "multiplier": backtest_environment.get("multiplier"),
        },
        symbol=record.symbol,
    )
    symbols: dict[str, Any] = {}
    missing: list[str] = []

    if not asset_specs:
        if required:
            missing.append(f"{record.symbol or '交易资产'} 缺少交易所或本地资产规格")
        return {
            "required": required,
            "status": "failed" if missing else "skipped",
            "missing": missing,
            "symbols": symbols,
        }

    for symbol, spec in asset_specs.items():
        if not isinstance(spec, dict):
            continue
        text_symbol = str(symbol or record.symbol or "").strip()
        item_missing = _asset_spec_missing_requirements(
            spec,
            symbol=text_symbol,
            backtest_environment=backtest_environment,
        )
        symbols[text_symbol] = {
            "has_multiplier": "合约乘数" not in item_missing,
            "has_commission": "手续费" not in item_missing,
            "requires_margin": _asset_spec_requires_margin(spec, symbol=text_symbol),
            "has_margin_or_leverage": "保证金/杠杆" not in item_missing,
            "missing": item_missing,
            "source": spec.get("source")
            or spec.get("asset_spec_source")
            or backtest_environment.get("asset_spec_source"),
        }
        if item_missing:
            missing.append(f"{text_symbol} 缺少" + "、".join(item_missing))

    return {
        "required": True,
        "status": "passed" if not missing else "failed",
        "missing": missing,
        "symbols": symbols,
    }


def _live_readiness_research_quality_item(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any]:
    gate_evaluations = [
        dict(item) for item in record.best_quality_gate_evaluations if isinstance(item, dict)
    ]
    passed_gate_count = sum(1 for item in gate_evaluations if bool(item.get("passed")))
    total_gate_count = len(gate_evaluations)
    gate_text = (
        f"，{passed_gate_count}/{total_gate_count} 项质量门槛通过" if total_gate_count else ""
    )
    best_iteration = record.best_iteration if record.best_iteration is not None else "-"
    evidence = (
        f"最佳第 {best_iteration} 轮 Sharpe "
        f"{_format_live_readiness_value(record.best_sharpe)} / 目标 "
        f"{_format_live_readiness_value(record.target_sharpe)}，质量分 "
        f"{_format_live_readiness_value(record.best_quality_score)}{gate_text}。"
    )
    return {
        "key": "research_quality_confirmed",
        "label": "投研质量达标",
        "status": "passed" if record.achieved else "failed",
        "evidence": evidence,
        "action": "保留最佳策略、质量门槛、回测环境和参数快照，实盘前不要绕过投研验收结论。",
        "details": {
            "run_id": record.run_id,
            "best_iteration": record.best_iteration,
            "target_sharpe": record.target_sharpe,
            "best_sharpe": record.best_sharpe,
            "best_quality_score": record.best_quality_score,
            "quality_gate_evaluations": gate_evaluations,
            "best_metrics": record.best_metrics,
        },
    }


def _live_readiness_out_of_sample_item(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any] | None:
    payload = _record_out_of_sample_validation_payload(record)
    gates = dict(record.quality_gates or {})
    enabled = bool(gates.get("out_of_sample_validation")) or bool(payload)
    required = bool(gates.get("require_out_of_sample_validation"))
    if not enabled:
        return None

    raw_status = str(payload.get("status") or "").strip() if payload else ""
    normalized = raw_status or "pending"
    if normalized == "passed":
        status = "passed"
    elif normalized in {"skipped", "not_required"} and not required:
        status = "skipped"
    elif normalized == "failed" or required:
        status = "failed"
    else:
        status = "pending"

    evidence = _live_readiness_out_of_sample_evidence(
        normalized,
        payload=payload,
        gates=gates,
    )
    return {
        "key": "out_of_sample_validation_confirmed",
        "label": "样本外验证",
        "status": status,
        "evidence": evidence,
        "action": (
            "样本外未通过或缺少证据时，先回到研究工作区补跑样本外验证或继续自动改稿。"
            if status not in {"passed", "skipped"}
            else "保留样本外验证窗口、指标和失败阈值，作为实盘审批证据。"
        ),
        "details": {
            "required": required,
            "quality_gates": gates,
            "validation": payload,
        },
    }


def _live_readiness_robustness_item(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any] | None:
    gates = dict(record.quality_gates or {})
    required = bool(gates.get("require_robustness_validation", False))
    enabled = bool(gates.get("robustness_validation", False)) or required
    if not enabled:
        return None
    payload = _record_robustness_validation_payload(record)
    raw_status = str(payload.get("status") or "").strip()
    if raw_status == "passed":
        status = "passed"
    elif raw_status == "failed" or required:
        status = "failed"
    else:
        status = "pending"
    result = dict(payload.get("result") or {})
    metrics = dict(result.get("metrics") or {})
    robustness_score = metrics.get("robustness_score")
    failures = [
        str(item).strip() for item in payload.get("failures") or [] if str(item or "").strip()
    ]
    failure_reason = str(payload.get("failure_reason") or "").strip()
    if failure_reason and failure_reason not in failures:
        failures.append(failure_reason)
    evidence = (
        f"稳健性状态 {raw_status or 'pending'}，得分 "
        f"{_format_live_readiness_value(robustness_score)} / "
        f"{_format_live_readiness_value(gates.get('min_robustness_score'))}。"
    )
    if failures:
        evidence += " 失败原因：" + "；".join(failures)
    return {
        "key": "robustness_validation_confirmed",
        "label": "稳健性验证",
        "status": status,
        "evidence": evidence,
        "action": (
            "稳健性未通过或缺少证据时，先回到研究工作区补跑稳健性验证，不能直接进入实盘。"
            if status != "passed"
            else "保留稳健性验证报告，作为实盘审批证据。"
        ),
        "details": {
            "required": required,
            "quality_gates": gates,
            "robustness_validation": payload,
        },
    }


def _record_out_of_sample_validation_payload(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any]:
    handoff_validation = record.paper_handoff.get("out_of_sample_validation")
    if isinstance(handoff_validation, dict) and handoff_validation:
        return dict(handoff_validation)

    diagnostics = dict(record.best_diagnostics or {})
    diagnostics_validation = diagnostics.get("out_of_sample_validation")
    if isinstance(diagnostics_validation, dict) and diagnostics_validation:
        return dict(diagnostics_validation)

    payload = _best_iteration_payload(record)
    if not payload:
        return {}
    status = payload.get("validation_status")
    window = payload.get("validation_window")
    metrics = payload.get("validation_metrics")
    gate_evaluations = payload.get("validation_gate_evaluations")
    failures = payload.get("validation_failures")
    failure_reason = payload.get("validation_failure_reason")
    if not any(
        value not in (None, "", [], {})
        for value in (
            status,
            window,
            metrics,
            gate_evaluations,
            failures,
            failure_reason,
        )
    ):
        return {}
    return {
        "status": status,
        "window": dict(window) if isinstance(window, dict) else window,
        "metrics": dict(metrics) if isinstance(metrics, dict) else {},
        "gate_evaluations": list(gate_evaluations) if isinstance(gate_evaluations, list) else [],
        "failures": list(failures) if isinstance(failures, list) else [],
        "failure_reason": failure_reason,
    }


def _record_robustness_validation_payload(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any]:
    if isinstance(record.robustness_validation, dict) and record.robustness_validation:
        return dict(record.robustness_validation)

    handoff_payload = record.paper_handoff.get("robustness_validation")
    if isinstance(handoff_payload, dict) and handoff_payload:
        return dict(handoff_payload)

    diagnostics = dict(record.best_diagnostics or {})
    diagnostics_payload = diagnostics.get("robustness_validation")
    if isinstance(diagnostics_payload, dict) and diagnostics_payload:
        return dict(diagnostics_payload)

    payload = _best_iteration_payload(record)
    if not payload:
        return {}
    status = payload.get("robustness_status")
    result = payload.get("robustness_result")
    gate_evaluations = payload.get("robustness_gate_evaluations")
    failures = payload.get("robustness_failures")
    failure_reason = payload.get("robustness_failure_reason")
    if not any(
        value not in (None, "", [], {})
        for value in (status, result, gate_evaluations, failures, failure_reason)
    ):
        return {}
    return {
        "status": status,
        "result": dict(result) if isinstance(result, dict) else {},
        "gate_evaluations": list(gate_evaluations) if isinstance(gate_evaluations, list) else [],
        "failures": list(failures) if isinstance(failures, list) else [],
        "failure_reason": failure_reason,
    }


def _record_robustness_promotion_failure(record: AIStrategyResearchRunRecord) -> str | None:
    gates = dict(record.quality_gates or {})
    if not bool(gates.get("require_robustness_validation", False)):
        return None
    if not bool(gates.get("robustness_validation", False)):
        return "Robustness validation is required before paper trading"
    payload = _record_robustness_validation_payload(record)
    status = str(payload.get("status") or "").strip()
    if status == "passed":
        return None
    failures = [
        str(item).strip() for item in payload.get("failures") or [] if str(item or "").strip()
    ]
    failure_reason = str(payload.get("failure_reason") or "").strip()
    if failure_reason and failure_reason not in failures:
        failures.append(failure_reason)
    suffix = ": " + "；".join(failures) if failures else ""
    return f"Robustness validation has not passed{suffix}"


def _live_readiness_out_of_sample_evidence(
    status: str,
    *,
    payload: dict[str, Any],
    gates: dict[str, Any],
) -> str:
    parts = [f"状态 {status or 'pending'}"]
    window = payload.get("window") if isinstance(payload, dict) else None
    if isinstance(window, dict):
        validation_start = str(window.get("validation_start") or "").strip()
        validation_end = str(window.get("validation_end") or "").strip()
        if validation_start or validation_end:
            parts.append(f"样本外区间 {validation_start or '?'} - {validation_end or '?'}")
    metrics = dict(payload.get("metrics") or {}) if isinstance(payload, dict) else {}
    sharpe = _metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    if sharpe is not None:
        threshold = _optional_gate_number(gates.get("min_out_of_sample_sharpe"))
        if threshold is None:
            target = _optional_gate_number(gates.get("target_sharpe"))
            threshold = max(float(target or 0.0) * 0.6, 0.3)
        parts.append(
            "Sharpe "
            f"{_format_live_readiness_value(sharpe)} / "
            f"{_format_live_readiness_value(threshold)}"
        )
    failures = [str(item).strip() for item in payload.get("failures") or [] if str(item).strip()]
    failure_reason = str(payload.get("failure_reason") or "").strip()
    if failure_reason and failure_reason not in failures:
        failures.append(failure_reason)
    if failures:
        parts.append("失败原因：" + "；".join(failures))
    return "；".join(parts)


def _live_readiness_status_from_evaluation(
    item: AIStrategyPaperTradingRuleEvaluation | None,
) -> str:
    if item is None:
        return "pending"
    return "passed" if item.passed else item.status or "pending"


def _live_readiness_evaluation_evidence(
    item: AIStrategyPaperTradingRuleEvaluation | None,
    *,
    fallback: str = "",
) -> str:
    if item is None:
        return fallback or "缺少对应的模拟监控评估。"
    actual = _format_live_readiness_value(item.actual)
    threshold = _format_live_readiness_value(item.threshold)
    source = item.source or "unknown"
    return f"{item.label} {actual} / {threshold}，来源 {source}"


def _format_live_readiness_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.6g}"
    return str(value)


def _expired_live_readiness_checklist(record: AIStrategyResearchRunRecord) -> list[dict[str, Any]]:
    items = [dict(item) for item in record.live_readiness_checklist if isinstance(item, dict)]
    items = [item for item in items if item.get("key") != "live_candidate_expired"]
    items.append(
        {
            "key": "live_candidate_expired",
            "label": "候选有效期",
            "status": "expired",
            "evidence": f"实盘候选有效期已在 {record.live_readiness_expires_at} 截止。",
            "action": "重新复核模拟交易，生成新的实盘候选有效期后再进入人工审批。",
            "details": {
                "expires_at": record.live_readiness_expires_at,
                "reviewed_at": record.paper_reviewed_at,
            },
        }
    )
    return items


def _paper_handoff_with_live_readiness(
    handoff: dict[str, Any] | None,
    checklist: list[dict[str, Any]],
    *,
    expires_at: str | None = None,
) -> dict[str, Any]:
    payload = dict(handoff or {})
    if checklist:
        payload["live_readiness_checklist"] = [dict(item) for item in checklist]
    else:
        payload.pop("live_readiness_checklist", None)
    if expires_at:
        payload["live_readiness_expires_at"] = expires_at
    else:
        payload.pop("live_readiness_expires_at", None)
    return payload


def _iteration_next_actions(
    *,
    iteration: int,
    max_iterations: int,
    passed: bool,
    run_status: str | None,
    quality_gate_failures: list[str],
    failure_reason: str | None,
) -> list[str]:
    if passed:
        return ["该轮已通过全部验收门槛，可作为进入模拟交易的候选版本。"]

    actions: list[str] = []
    status = str(run_status or "").strip()
    if status and status != "completed":
        actions.append(f"先处理本轮回测状态 {status}，确认任务日志、数据源和策略运行错误。")

    failures = [str(item).strip() for item in quality_gate_failures if str(item or "").strip()]
    for failure in failures:
        lowered = failure.lower()
        if "sharpe" in lowered:
            actions.append("提高信号质量和盈亏比，优先减少低胜率或低收益质量的入场。")
        elif _is_paper_trading_start_failure(failure):
            actions.append("优先复核模拟交易单元创建、网关配置、策略脚本依赖和资产参数。")
        elif "out-of-sample" in lowered or "out of sample" in lowered or "样本外" in failure:
            actions.append("样本外验证未通过，优先降低过拟合、减少参数敏感度并扩大验证样本。")
        elif (
            "robustness" in lowered
            or "overfitting" in lowered
            or "稳健" in failure
            or "过拟合" in failure
        ):
            actions.append("稳健性验证未通过，优先减少参数自由度和信号噪声后重新验证。")
        elif "trade" in lowered or "trades" in lowered or "交易" in failure:
            actions.append("放宽入场过滤或缩短信号窗口，先保证样本内有足够交易次数。")
        elif "drawdown" in lowered or "回撤" in failure:
            actions.append("收紧止损、单笔风险和仓位暴露，优先压低最大回撤。")
        elif "return" in lowered or "收益" in failure:
            actions.append("优化出场和持仓周期，提升总收益或年化收益。")
        elif "win rate" in lowered or "胜率" in failure:
            actions.append("增加趋势/波动过滤，减少低质量信号以提升胜率。")
        elif "cost" in lowered or "slippage" in lowered or "费用" in failure or "滑点" in failure:
            actions.append("降低换手率和无效交易，并用模拟成交成本重新校准手续费与入场阈值。")
        elif (
            "valuation" in lowered
            or "asset spec" in lowered
            or "asset_specs" in lowered
            or "margin" in lowered
            or "multiplier" in lowered
            or "估值" in failure
            or "资产规格" in failure
            or "合约乘数" in failure
            or "保证金" in failure
        ):
            actions.append("先修正资产规格、合约乘数、保证金和持仓估值口径，再继续生成下一版策略。")

    if failure_reason and not failures:
        actions.append(f"复核失败原因：{failure_reason}")

    if iteration < max_iterations:
        actions.append("系统将基于本轮失败原因生成下一版策略，并继续回测验证。")
    else:
        actions.append("已达到最大迭代次数，建议复用本次记录继续投研或人工复核策略逻辑。")

    return list(dict.fromkeys(actions))


def _run_next_actions(
    *,
    status: str,
    achieved: bool,
    request: AIStrategyResearchRunRequest,
    result_iteration: AIStrategyResearchIteration | None,
    paper_trading: AIStrategyPaperTradingStart | None,
    paper_trading_error: str | None = None,
    run_failures: list[str] | None = None,
) -> list[str]:
    if status == "configuration_invalid":
        actions = [
            "投研请求配置未通过，尚未生成策略或提交回测。",
            "填写可切分的开始/结束日期，或关闭“晋级必须通过样本外”后重新启动。",
        ]
        failures = [str(item).strip() for item in run_failures or [] if str(item or "").strip()]
        if failures:
            actions.append("配置问题：" + failures[-1])
        return actions
    if status == "timeout":
        return [
            "回测等待超时，先打开研究工作区查看任务是否仍在运行。",
            "如数据量较大，可提高 backtest_timeout_seconds 后继续投研。",
        ]
    if status == "backtest_submission_failed":
        actions = [
            "回测任务未能成功提交，先检查研究工作区、策略脚本保存、数据源和任务队列配置。",
            "修复提交问题后，可从本次记录继续自动投研。",
        ]
        failures = [str(item).strip() for item in run_failures or [] if str(item or "").strip()]
        if failures:
            actions.append("最近一次提交失败：" + failures[-1])
        return actions

    if achieved:
        if paper_trading is not None and paper_trading.started:
            return [
                "策略已通过验收并进入模拟交易，下一步跟踪模拟账户成交、持仓和风控指标。",
                "保留当前研究工作区，后续用样本外区间复核策略稳定性。",
            ]
        if request.start_paper_trading:
            actions = [
                "策略已通过验收，但模拟交易未成功启动，先检查交易工作区和网关配置。",
                "修复启动问题后，可从本次最佳策略手动创建模拟交易单元。",
            ]
            if paper_trading_error:
                actions.append(f"模拟交易启动错误：{paper_trading_error}")
            return actions
        return [
            "策略已通过验收，可手动进入模拟交易或安排样本外验证。",
            "进入模拟交易前确认标的、周期、手续费和网关配置。",
        ]

    actions = [
        "目标未达成，优先查看最后一轮质量门槛失败原因和改稿说明。",
        "可增加 max_iterations 或调整样本区间后继续自动投研。",
    ]
    if result_iteration is not None and result_iteration.quality_gate_failures:
        actions.append("下一轮改稿应直接针对：" + "；".join(result_iteration.quality_gate_failures))
    failures = [str(item).strip() for item in run_failures or [] if str(item or "").strip()]
    if failures:
        actions.append("最近一次回测提交失败：" + failures[-1])
    return actions


def _run_failure_diagnostics(run_failures: list[str]) -> dict[str, Any]:
    failures = [str(item).strip() for item in run_failures if str(item or "").strip()]
    if not failures:
        return {}
    return {
        "summary": "投研循环在提交回测任务时失败，尚未产生可评估的回测结果。",
        "failure_categories": ["backtest_submission"],
        "weaknesses": failures,
        "improvement_plan": [
            "检查研究工作区是否可用，确认策略脚本保存、数据源和回测任务队列配置。",
            "修复提交问题后，从该记录继续投研，让系统重新提交回测并进入质量门槛评估。",
        ],
        "promotion_ready": False,
    }


def _configuration_failure_diagnostics(failure: str) -> dict[str, Any]:
    return {
        "summary": "投研请求配置未通过，尚未生成策略或提交回测。",
        "failure_categories": ["configuration", "out_of_sample"],
        "weaknesses": [failure],
        "improvement_plan": [
            "填写至少 8 天以上、可切分训练/样本外区间的开始日期和结束日期。",
            "如果只是快速试跑，可关闭强制样本外验证，但进入模拟交易前仍建议补跑样本外验证。",
        ],
        "promotion_ready": False,
    }


def _cancelled_draft_diagnostics(
    run_failures: list[str],
    *,
    strategy_saved: bool,
) -> dict[str, Any]:
    failures = [str(item).strip() for item in run_failures if str(item or "").strip()]
    if not failures:
        failures = ["AI research cancelled before any completed backtest iteration"]
    return {
        "summary": (
            "AI投研任务在首轮回测产生结果前取消，已保存待回测策略草案。"
            if strategy_saved
            else "AI投研任务在首轮回测产生结果前取消，且策略草案未能保存。"
        ),
        "failure_categories": ["cancelled", "draft_only"],
        "weaknesses": failures,
        "improvement_plan": [
            "从该记录继续投研，重新提交首轮回测并生成可评估的质量门槛结果。",
            "继续前确认研究工作区、数据源、手续费和合约规格配置仍然有效。",
        ],
        "promotion_ready": False,
    }
