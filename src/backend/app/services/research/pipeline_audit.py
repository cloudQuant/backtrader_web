"""Research pipeline progress and promotion-audit helpers."""

# Workflow helpers are injected after every stage is loaded; see research.__init__.
# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405
from .shared import *


def _pipeline_summary_from_record(
    record: AIStrategyResearchRunRecord,
    *,
    paper_trading_started: bool | None = None,
    paper_trading_error: str | None = None,
    paper_review_status: str | None = None,
    paper_review_ready_for_live: bool | None = None,
    live_readiness_checklist: list[dict[str, Any]] | None = None,
    live_readiness_expires_at: str | None = None,
) -> dict[str, Any]:
    return _pipeline_summary(
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
        paper_trading_started=record.paper_trading_started
        if paper_trading_started is None
        else paper_trading_started,
        paper_trading_error=paper_trading_error,
        paper_review_status=paper_review_status
        if paper_review_status is not None
        else record.paper_review_status,
        paper_review_ready_for_live=record.paper_review_ready_for_live
        if paper_review_ready_for_live is None
        else paper_review_ready_for_live,
        live_readiness_checklist=record.live_readiness_checklist
        if live_readiness_checklist is None
        else live_readiness_checklist,
        live_readiness_expires_at=record.live_readiness_expires_at
        if live_readiness_expires_at is None
        else live_readiness_expires_at,
        workflow_mode=record.workflow_mode,
        workflow_steps=record.workflow_steps,
    )


def _pipeline_summary(
    *,
    status: str,
    achieved: bool,
    iteration_count: int,
    max_iterations: int,
    out_of_sample_validation: bool,
    validation_status: str | None,
    paper_trading_started: bool,
    paper_trading_error: str | None,
    paper_review_status: str | None,
    paper_review_ready_for_live: bool,
    robustness_validation: bool = False,
    robustness_status: str | None = None,
    live_readiness_checklist: list[dict[str, Any]] | None = None,
    live_readiness_expires_at: str | None = None,
    workflow_mode: str = "auto",
    workflow_steps: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    configuration_invalid = status == "configuration_invalid"
    workflow_step_keys = _research_workflow_steps_for_summary(workflow_steps)
    draft_status = "pending" if configuration_invalid else "completed"
    if status == "draft_generation_failed":
        draft_status = "failed"
    if configuration_invalid:
        backtest_status = "pending"
    elif status == "cancelled":
        backtest_status = "cancelled"
    elif status == "backtest_submission_failed":
        backtest_status = "failed"
    elif iteration_count > 0:
        backtest_status = "completed"
    else:
        backtest_status = "pending"
    validation_step_status = _validation_step_status(
        status=status,
        out_of_sample_validation=out_of_sample_validation,
        validation_status=validation_status,
        iteration_count=iteration_count,
    )
    robustness_step_status = _robustness_step_status(
        status=status,
        robustness_validation=robustness_validation,
        robustness_status=robustness_status,
        iteration_count=iteration_count,
    )

    if configuration_invalid:
        gate_status = "failed"
    elif status == "cancelled":
        gate_status = "cancelled"
    elif achieved:
        gate_status = "completed"
    elif iteration_count >= max_iterations:
        gate_status = "failed"
    else:
        gate_status = "running"
    review_status = _strategy_review_step_status(
        status=status,
        configuration_invalid=configuration_invalid,
        iteration_count=iteration_count,
    )
    optimization_status = _strategy_optimization_step_status(
        status=status,
        achieved=achieved,
        configuration_invalid=configuration_invalid,
        iteration_count=iteration_count,
        max_iterations=max_iterations,
    )
    paper_status = (
        "completed" if paper_trading_started else "failed" if paper_trading_error else "pending"
    )
    paper_review_step_status = (
        "completed"
        if paper_review_ready_for_live
        else "failed"
        if paper_review_status in {"needs_research_review", "live_readiness_expired"}
        else "running"
        if paper_review_status
        else "pending"
    )

    steps: list[dict[str, Any]] = [
        {
            "key": "strategy_idea",
            "label": _research_workflow_step_label("ideation"),
            "status": "pending" if configuration_invalid else "completed",
        },
        {
            "key": "draft",
            "label": _research_workflow_step_label("generation"),
            "status": draft_status,
        },
        {
            "key": "backtest_loop",
            "label": _research_workflow_step_label("backtest"),
            "status": backtest_status,
            "iteration_count": iteration_count,
            "max_iterations": max_iterations,
        },
        {
            "key": "strategy_review",
            "label": _research_workflow_step_label("review"),
            "status": review_status,
            "iteration_count": iteration_count,
        },
        {
            "key": "optimization_loop",
            "label": _research_workflow_step_label("optimization"),
            "status": optimization_status,
            "iteration_count": iteration_count,
            "max_iterations": max_iterations,
        },
        {
            "key": "validation",
            "label": "样本外验证",
            "status": validation_step_status,
            "validation_status": validation_status,
        },
        {
            "key": "robustness_validation",
            "label": "稳健性验证",
            "status": robustness_step_status,
            "robustness_status": robustness_status,
        },
        {"key": "quality_gate", "label": "质量门槛", "status": gate_status},
        {
            "key": "paper_trading",
            "label": "模拟交易",
            "status": paper_status,
            "error": paper_trading_error,
        },
        {
            "key": "paper_review",
            "label": "模拟复核",
            "status": paper_review_step_status,
            "review_status": paper_review_status,
        },
    ]
    current_stage = _pipeline_current_stage(
        achieved=achieved,
        paper_trading_started=paper_trading_started,
        paper_trading_error=paper_trading_error,
        paper_review_status=paper_review_status,
        paper_review_ready_for_live=paper_review_ready_for_live,
        status=status,
    )
    completed_count = sum(
        1 for item in steps if str(item.get("status") or "") in {"completed", "skipped"}
    )
    return {
        "current_stage": current_stage,
        "status": status,
        "progress": round(completed_count / len(steps) * 100, 2),
        "ready_for_live": paper_review_ready_for_live,
        "paper_trading_error": paper_trading_error,
        "live_readiness_checklist": list(live_readiness_checklist or []),
        "live_readiness_expires_at": live_readiness_expires_at,
        "workflow_mode": workflow_mode,
        "workflow_steps": workflow_step_keys,
        "steps": steps,
    }


def _research_workflow_steps_for_summary(
    workflow_steps: list[str] | tuple[str, ...] | None,
) -> list[str]:
    allowed = set(AI_STRATEGY_RESEARCH_WORKFLOW_STEP_LABELS)
    steps = [str(item) for item in workflow_steps or () if str(item) in allowed]
    if not steps:
        steps = list(AI_STRATEGY_RESEARCH_DEFAULT_WORKFLOW_STEPS)
    return steps


def _research_workflow_step_label(step: str) -> str:
    return AI_STRATEGY_RESEARCH_WORKFLOW_STEP_LABELS.get(step, step.replace("_", " "))


def _strategy_review_step_status(
    *,
    status: str,
    configuration_invalid: bool,
    iteration_count: int,
) -> str:
    if configuration_invalid:
        return "pending"
    if iteration_count > 0:
        return "completed"
    if status == "cancelled":
        return "cancelled"
    if status in {"draft_generation_failed", "backtest_submission_failed"}:
        return "pending"
    return "pending"


def _strategy_optimization_step_status(
    *,
    status: str,
    achieved: bool,
    configuration_invalid: bool,
    iteration_count: int,
    max_iterations: int,
) -> str:
    if configuration_invalid:
        return "pending"
    if status == "cancelled":
        return "cancelled"
    if iteration_count <= 0:
        return "pending"
    if iteration_count > 1:
        return "completed"
    if achieved:
        return "skipped"
    if iteration_count >= max_iterations:
        return "failed"
    return "running"


def _record_best_validation_status(record: AIStrategyResearchRunRecord) -> str | None:
    payload = _best_iteration_payload(record)
    if not isinstance(payload, dict):
        return None
    status = str(payload.get("validation_status") or "").strip()
    return status or None


def _record_best_robustness_status(record: AIStrategyResearchRunRecord) -> str | None:
    robustness = _record_robustness_validation_payload(record)
    if robustness:
        status = str(robustness.get("status") or "").strip()
        if status:
            return status
    payload = _best_iteration_payload(record)
    if not isinstance(payload, dict):
        return None
    status = str(payload.get("robustness_status") or "").strip()
    return status or None


def _validation_step_status(
    *,
    status: str,
    out_of_sample_validation: bool,
    validation_status: str | None,
    iteration_count: int,
) -> str:
    if not out_of_sample_validation:
        return "skipped"
    normalized = str(validation_status or "").strip()
    if normalized == "passed":
        return "completed"
    if normalized == "failed":
        return "failed"
    if normalized in {"skipped", "not_required"}:
        return "skipped"
    if status == "configuration_invalid":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if iteration_count <= 0 or status == "backtest_submission_failed":
        return "pending"
    return "pending"


def _robustness_step_status(
    *,
    status: str,
    robustness_validation: bool,
    robustness_status: str | None,
    iteration_count: int,
) -> str:
    if not robustness_validation:
        return "skipped"
    normalized = str(robustness_status or "").strip()
    if normalized == "passed":
        return "completed"
    if normalized == "failed":
        return "failed"
    if status == "configuration_invalid":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if iteration_count <= 0 or status == "backtest_submission_failed":
        return "pending"
    return "pending"


def _pipeline_current_stage(
    *,
    achieved: bool,
    paper_trading_started: bool,
    paper_trading_error: str | None,
    paper_review_status: str | None,
    paper_review_ready_for_live: bool,
    status: str,
) -> str:
    if status == "configuration_invalid":
        return "configuration_invalid"
    if status == "cancelled":
        return "cancelled"
    if paper_review_ready_for_live:
        return "live_candidate"
    if paper_review_status:
        return "paper_review"
    if paper_trading_started:
        return "paper_trading"
    if paper_trading_error:
        return "paper_trading_failed"
    if achieved:
        return "quality_achieved"
    if status == "timeout":
        return "backtest_timeout"
    if status == "backtest_submission_failed":
        return "backtest_failed"
    return "research_iteration"


def _research_run_record_with_promotion_audit(
    record: AIStrategyResearchRunRecord,
) -> AIStrategyResearchRunRecord:
    audit = _promotion_audit_from_record(record)
    if record.promotion_audit == audit:
        return record
    return record.model_copy(update={"promotion_audit": audit})


def _promotion_audit_from_record(record: AIStrategyResearchRunRecord) -> list[dict[str, Any]]:
    pipeline = record.pipeline if isinstance(record.pipeline, dict) else {}
    return [
        _audit_strategy_generation_item(record),
        _audit_backtest_loop_item(record),
        _audit_quality_gate_item(record),
        _audit_out_of_sample_item(record),
        _audit_robustness_item(record),
        _audit_paper_trading_item(record, pipeline),
        _audit_paper_review_item(record),
        _audit_live_handoff_item(record, pipeline),
        _audit_live_trading_prepare_item(record, pipeline),
    ]


def _audit_item(
    *,
    key: str,
    label: str,
    status: str,
    evidence: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "evidence": evidence,
        "action": action,
        "details": dict(details or {}),
    }


def _audit_strategy_generation_item(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    generation_metadata = _record_strategy_generation_metadata(record)
    generation_evidence = _strategy_generation_audit_text(generation_metadata)
    if record.best_strategy_id:
        evidence = f"已保存候选策略 {record.best_strategy_name or record.best_strategy_id}。"
        if generation_evidence:
            evidence = f"{evidence} {generation_evidence}"
        return _audit_item(
            key="strategy_generation",
            label="策略脚本生成",
            status="completed",
            evidence=evidence,
            action="保留该策略快照用于回测复现、继续投研或模拟交易。",
            details={
                "strategy_id": record.best_strategy_id,
                "strategy_name": record.best_strategy_name,
                "strategy_generation": generation_metadata,
            },
        )
    if record.iteration_count > 0:
        evidence = f"已完成 {record.iteration_count} 轮策略脚本生成/回测。"
        if generation_evidence:
            evidence = f"{evidence} {generation_evidence}"
        return _audit_item(
            key="strategy_generation",
            label="策略脚本生成",
            status="completed",
            evidence=evidence,
            action="从最佳迭代快照恢复策略后再继续投研。",
            details={
                "iteration_count": record.iteration_count,
                "strategy_generation": generation_metadata,
            },
        )
    status = "cancelled" if record.status == "cancelled" else "failed"
    return _audit_item(
        key="strategy_generation",
        label="策略脚本生成",
        status=status,
        evidence=record.best_diagnostics.get("summary") or "尚未产生可回测策略脚本。",
        action="重新提交 AI 投研任务或检查策略生成配置。",
        details={"run_status": record.status, "strategy_generation": generation_metadata},
    )


def _record_strategy_generation_metadata(
    record: AIStrategyResearchRunRecord,
) -> dict[str, Any]:
    diagnostics = dict(record.best_diagnostics or {})
    generation = diagnostics.get("strategy_generation")
    if isinstance(generation, dict):
        return _strategy_generation_metadata(generation)
    payload = _best_iteration_payload(record) or {}
    payload_diagnostics = _dict_payload(payload.get("diagnostics"))
    generation = payload_diagnostics.get("strategy_generation")
    if isinstance(generation, dict):
        return _strategy_generation_metadata(generation)
    return {}


def _strategy_generation_audit_text(metadata: dict[str, Any]) -> str:
    if not metadata:
        return ""
    source = str(metadata.get("source") or "").strip()
    provider = str(metadata.get("provider") or "").strip()
    model_id = str(metadata.get("model_id") or "").strip()
    fallback_reason = str(metadata.get("fallback_reason") or "").strip()
    labels = {
        "ai_initial_draft": "AI 初稿",
        "ai_model": "AI 模型改稿",
        "local_rules": "本地规则改稿",
        "local_fallback": "本地回退改稿",
        "local_initial_fallback": "本地初稿回退",
        "local_code_repair_fallback": "本地代码修复",
        "seed_strategy": "种子策略",
        "continued_run_seed": "历史记录种子",
        "local_seed": "本地种子",
    }
    parts = [labels.get(source, source or "未知来源")]
    if model_id:
        parts.append(f"模型 {model_id}")
    elif provider and provider != "local":
        parts.append(provider)
    text = "草案来源：" + " / ".join(parts) + "。"
    if fallback_reason:
        text += f" 回退原因：{fallback_reason}。"
    return text


def _audit_backtest_loop_item(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    if record.iteration_count > 0:
        return _audit_item(
            key="backtest_loop",
            label="自动回测迭代",
            status="completed" if record.status != "cancelled" else "cancelled",
            evidence=(
                f"已完成 {record.iteration_count}/{record.max_iterations} 轮，"
                f"最佳 Sharpe {_format_gate_value(record.best_sharpe)}，"
                f"质量分 {_format_gate_value(record.best_quality_score)}。"
            ),
            action="使用最佳迭代作为后续晋级、模拟或继续投研的依据。",
            details={
                "iteration_count": record.iteration_count,
                "max_iterations": record.max_iterations,
                "best_iteration": record.best_iteration,
                "best_sharpe": record.best_sharpe,
                "best_quality_score": record.best_quality_score,
            },
        )
    status = "failed"
    if record.status == "cancelled":
        status = "cancelled"
    elif record.status == "configuration_invalid":
        status = "pending"
    return _audit_item(
        key="backtest_loop",
        label="自动回测迭代",
        status=status,
        evidence=record.best_diagnostics.get("summary") or "尚未完成回测迭代。",
        action="修正配置、数据或策略脚本后重新启动投研。",
        details={"run_status": record.status, "max_iterations": record.max_iterations},
    )


def _audit_quality_gate_item(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    evaluations = [item for item in record.best_quality_gate_evaluations if isinstance(item, dict)]
    passed_count = sum(1 for item in evaluations if bool(item.get("passed")))
    evidence = (
        f"最佳 Sharpe {_format_gate_value(record.best_sharpe)} / 目标 "
        f"{_format_gate_value(record.target_sharpe)}；"
        f"{passed_count}/{len(evaluations)} 项质量门槛通过。"
    )
    if not evaluations:
        evidence = record.best_diagnostics.get("summary") or evidence
    return _audit_item(
        key="quality_gate",
        label="质量门槛",
        status="completed" if record.achieved else "failed",
        evidence=evidence,
        action=(
            "质量门槛已达成，可进入模拟交易/复核。"
            if record.achieved
            else "按失败门槛继续自动改稿并重新回测。"
        ),
        details={
            "target_sharpe": record.target_sharpe,
            "best_sharpe": record.best_sharpe,
            "best_quality_score": record.best_quality_score,
            "quality_gate_evaluations": evaluations,
        },
    )


def _audit_out_of_sample_item(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    gates = record.quality_gates or {}
    if not bool(gates.get("out_of_sample_validation", False)):
        return _audit_item(
            key="out_of_sample_validation",
            label="样本外验证",
            status="skipped",
            evidence="本轮未启用样本外验证。",
            action="进入模拟前仍需人工关注过拟合风险。",
            details={"enabled": False},
        )
    payload = _best_iteration_payload(record) or {}
    validation_status = str(payload.get("validation_status") or "").strip()
    failures = [
        str(item).strip()
        for item in payload.get("validation_failures") or []
        if str(item or "").strip()
    ]
    if validation_status == "passed":
        status = "completed"
    elif validation_status in {"skipped", "not_required"}:
        status = "skipped"
    elif validation_status == "failed" or failures:
        status = "failed"
    else:
        status = "pending"
    if validation_status:
        evidence = f"样本外验证状态：{validation_status}。"
    elif failures:
        evidence = "样本外验证失败：" + "；".join(failures)
    else:
        evidence = "尚未形成样本外验证结果。"
    return _audit_item(
        key="out_of_sample_validation",
        label="样本外验证",
        status=status,
        evidence=evidence,
        action=(
            "样本外验证已通过，可作为晋级证据。"
            if status == "completed"
            else "样本外未通过或缺失时，需继续改进或延长验证区间。"
        ),
        details={
            "enabled": True,
            "status": validation_status or None,
            "window": payload.get("validation_window"),
            "metrics": payload.get("validation_metrics") or {},
            "failures": failures,
        },
    )


def _audit_robustness_item(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    gates = record.quality_gates or {}
    if not bool(gates.get("robustness_validation", False)):
        return _audit_item(
            key="robustness_validation",
            label="稳健性验证",
            status="skipped",
            evidence="本轮未启用稳健性验证。",
            action="进入模拟前建议补跑稳健性验证，尤其关注过拟合和参数敏感性。",
            details={"enabled": False},
        )
    payload = _record_robustness_validation_payload(record)
    status_text = str(payload.get("status") or "").strip()
    failures = [
        str(item).strip() for item in payload.get("failures") or [] if str(item or "").strip()
    ]
    failure_reason = str(payload.get("failure_reason") or "").strip()
    if failure_reason and failure_reason not in failures:
        failures.append(failure_reason)
    if status_text == "passed":
        status = "completed"
    elif status_text == "failed" or failures:
        status = "failed"
    else:
        status = "pending"
    metrics = dict((payload.get("result") or {}).get("metrics") or {})
    robustness_score = metrics.get("robustness_score")
    evidence = (
        f"稳健性状态：{status_text or 'pending'}；"
        f"得分 {_format_gate_value(robustness_score)} / "
        f"{_format_gate_value(gates.get('min_robustness_score'))}。"
    )
    if failures:
        evidence += " 失败原因：" + "；".join(failures)
    return _audit_item(
        key="robustness_validation",
        label="稳健性验证",
        status=status,
        evidence=evidence,
        action=(
            "稳健性验证已通过，可作为晋级证据。"
            if status == "completed"
            else "稳健性未通过或缺失时，需继续降低过拟合/参数敏感性风险后重跑验证。"
        ),
        details={
            "enabled": True,
            "required": bool(gates.get("require_robustness_validation", True)),
            "methods": list(gates.get("robustness_methods") or []),
            "min_robustness_score": gates.get("min_robustness_score"),
            "validation": payload,
        },
    )


def _audit_paper_trading_item(
    record: AIStrategyResearchRunRecord,
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    error = str(pipeline.get("paper_trading_error") or "").strip()
    if record.paper_trading_started:
        status = "completed"
        evidence = (
            f"模拟工作区 {record.paper_workspace_id or '-'}，"
            f"模拟单元 {record.paper_unit_id or '-'}。"
        )
        action = "继续采集模拟成交、持仓、费用和估值指标。"
    elif error:
        status = "failed"
        evidence = f"模拟交易启动失败：{error}"
        action = "检查交易工作区、网关、策略脚本依赖和资产规格后重试。"
    elif record.achieved:
        status = "pending"
        evidence = "策略已达标，但尚未启动模拟交易。"
        action = "启动模拟交易并绑定资产规格、费用和网关配置。"
    else:
        status = "pending"
        evidence = "质量门槛未达成前不启动模拟交易。"
        action = "继续投研直到满足晋级条件。"
    return _audit_item(
        key="paper_trading",
        label="模拟交易",
        status=status,
        evidence=evidence,
        action=action,
        details={
            "paper_workspace_id": record.paper_workspace_id,
            "paper_unit_id": record.paper_unit_id,
            "paper_trading_started": record.paper_trading_started,
            "paper_trading_error": error or None,
        },
    )


def _audit_paper_review_item(record: AIStrategyResearchRunRecord) -> dict[str, Any]:
    review_status = str(record.paper_review_status or "").strip()
    if record.paper_review_ready_for_live:
        status = "completed"
    elif review_status in {"needs_research_review", "live_readiness_expired"}:
        status = "failed"
    elif review_status:
        status = "running"
    else:
        status = "pending"
    if review_status:
        evidence = f"模拟复核状态：{review_status}。"
    elif record.paper_trading_started:
        evidence = "模拟交易已启动，等待模拟复核。"
    else:
        evidence = "模拟交易未启动，暂无模拟复核。"
    return _audit_item(
        key="paper_review",
        label="模拟复核",
        status=status,
        evidence=evidence,
        action=(
            "模拟复核通过，可进入实盘交接审批。"
            if record.paper_review_ready_for_live
            else "按监控计划继续观察，未通过时回到投研改进。"
        ),
        details={
            "paper_review_status": review_status or None,
            "paper_review_ready_for_live": record.paper_review_ready_for_live,
            "paper_reviewed_at": record.paper_reviewed_at,
            "evaluations": [
                dict(item) for item in record.paper_review_evaluations if isinstance(item, dict)
            ],
        },
    )


def _audit_live_handoff_item(
    record: AIStrategyResearchRunRecord,
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    handoff = record.live_handoff
    handoff_status = str(
        getattr(handoff, "status", None) or pipeline.get("live_handoff_status") or ""
    ).strip()
    if record.live_handoff_approval is not None and record.live_handoff_approval.approved:
        status = "completed"
    elif handoff_status in {"blocked", "approval_rejected"}:
        status = "failed"
    elif handoff_status:
        status = "running"
    else:
        status = "pending"
    evidence = f"实盘交接状态：{handoff_status}。" if handoff_status else "尚未生成实盘交接包。"
    return _audit_item(
        key="live_handoff",
        label="实盘交接",
        status=status,
        evidence=evidence,
        action=(
            "实盘交接已通过审批，可准备锁定实盘单元。"
            if status == "completed"
            else "等待模拟复核通过并完成人工审批。"
        ),
        details={
            "handoff_status": handoff_status or None,
            "approval": _object_payload(record.live_handoff_approval)
            if record.live_handoff_approval is not None
            else None,
            "expires_at": getattr(handoff, "expires_at", None) if handoff else None,
        },
    )


def _audit_live_trading_prepare_item(
    record: AIStrategyResearchRunRecord,
    pipeline: dict[str, Any],
) -> dict[str, Any]:
    prepared = bool(record.live_trading_prepared or pipeline.get("live_trading_prepared"))
    evidence = (
        f"实盘工作区 {record.live_workspace_id or pipeline.get('live_workspace_id') or '-'}，"
        f"实盘单元 {record.live_unit_id or pipeline.get('live_unit_id') or '-'}。"
        if prepared
        else "尚未创建锁定实盘交易单元。"
    )
    return _audit_item(
        key="live_trading_prepare",
        label="实盘准备",
        status="completed" if prepared else "pending",
        evidence=evidence,
        action=(
            "实盘单元默认锁定，人工核验后再解锁运行。"
            if prepared
            else "审批通过后创建锁定实盘单元。"
        ),
        details={
            "live_workspace_id": record.live_workspace_id or pipeline.get("live_workspace_id"),
            "live_unit_id": record.live_unit_id or pipeline.get("live_unit_id"),
            "prepared_at": record.live_trading_prepared_at
            or pipeline.get("live_trading_prepared_at"),
        },
    )


def _paper_trading_start_error(paper_trading: AIStrategyPaperTradingStart | None) -> str | None:
    if paper_trading is None or paper_trading.started:
        return None
    run_status = str(paper_trading.run_result.status if paper_trading.run_result else "").strip()
    if run_status:
        return f"Paper trading run finished with status {run_status}"
    return "Paper trading run did not return a runnable task"


def _paper_trading_run_started(run_result: StrategyCopilotRunResult | None) -> bool:
    if run_result is None:
        return False
    status = str(run_result.status or "").strip().lower()
    return status in _PAPER_TRADING_STARTED_STATUSES


def _quality_metric(metrics: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in metrics or metrics[key] in (None, ""):
            continue
        try:
            return float(metrics[key])
        except (TypeError, ValueError):
            continue
    return None


def _align_metric_scale(value: float, threshold: float) -> float:
    if abs(threshold) <= 1 and abs(value) > 1:
        return value / 100
    if abs(threshold) > 1 and abs(value) <= 1:
        return value * 100
    return value


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _utc_iso_add_days(value: str, days: int) -> str:
    base = _parse_utc_datetime(value) or datetime.now(timezone.utc).replace(microsecond=0)
    return (base + timedelta(days=days)).replace(microsecond=0).isoformat()


def _parse_utc_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
