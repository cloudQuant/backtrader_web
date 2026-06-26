"""AI-driven strategy research loop orchestration."""

from __future__ import annotations

import ast
import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas.ai_strategy_research import (
    AIStrategyPaperTradingReview,
    AIStrategyPaperTradingRuleEvaluation,
    AIStrategyPaperTradingStart,
    AIStrategyPaperTradingStartRequest,
    AIStrategyResearchIteration,
    AIStrategyResearchRunListResponse,
    AIStrategyResearchRunRecord,
    AIStrategyResearchRunRequest,
    AIStrategyResearchRunResponse,
)
from app.schemas.strategy import (
    AIStrategyBacktestSpec,
    AIStrategyDataSourceSpec,
    AIStrategyDraft,
    AIStrategyExecutionPlan,
    ParamSpec,
    StrategyCopilotBacktestRequest,
    StrategyCopilotDraftRequest,
    StrategyCopilotRunResult,
    StrategyResponse,
)
from app.schemas.workspace import (
    StrategyUnitCreate,
    StrategyUnitResponse,
    StrategyUnitUpdate,
    UnitStatusResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.ai_router.preferences import (
    AIModelPreferenceService,
    ResolvedAIModelPreference,
)
from app.services.ai_router.router import AIChatRouter, get_ai_chat_router
from app.services.strategy.ai_draft import build_ai_strategy_draft
from app.services.strategy.inference import render_param_default
from app.services.strategy_service import StrategyService
from app.services.trading_asset_info_service import resolve_asset_specs
from app.services.workspace_service import WorkspaceService
from app.utils.sandbox import StrategySandbox

_TERMINAL_UNIT_STATUSES = {"completed", "failed", "cancelled", "timeout"}


@dataclass(frozen=True)
class StrategyImprovement:
    draft: AIStrategyDraft
    notes: list[str]


@dataclass(frozen=True)
class OutOfSampleWindow:
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str

    def as_dict(self) -> dict[str, str]:
        return {
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
        }


class LocalStrategyImprover:
    """Deterministic fallback strategy improver.

    The research loop must be runnable in local/test environments without an
    external model. This improver keeps the contract AI-ready while providing a
    conservative baseline: react to weak backtest metrics by adjusting common
    Backtrader parameters that the existing copilot generator emits.
    """

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        improved = draft.model_copy(deep=True)
        notes: list[str] = []
        failures = [str(item) for item in quality_gate_failures or []]
        sharpe = _metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
        max_drawdown = _metric_float(metrics, "max_drawdown", "maxDrawdown", default=0.0)
        total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
        drawdown_failed = any("drawdown" in item.lower() or "回撤" in item for item in failures)

        suffix = f" v{iteration + 1}"
        base_name = re.sub(r"\s+v\d+$", "", improved.name).strip()
        improved.name = f"{base_name}{suffix}"[:100]
        improved.description = (
            f"{improved.description or ''}\n"
            f"AI research revision {iteration + 1}: previous Sharpe {sharpe:.3f}, "
            f"target {target_sharpe:.3f}."
        ).strip()

        params = improved.params
        if "risk_pct" in params:
            current = _param_float(params["risk_pct"], 0.01)
            next_value = max(round(current * 0.8, 5), 0.001)
            _set_param_default(params, "risk_pct", next_value)
            notes.append(f"将单笔风险从 {current:g} 下调到 {next_value:g}")

        if "stop_loss_pct" in params and (max_drawdown < -10 or drawdown_failed):
            current = _param_float(params["stop_loss_pct"], 0.05)
            next_value = max(round(current * 0.8, 4), 0.01)
            _set_param_default(params, "stop_loss_pct", next_value)
            notes.append(f"最大回撤偏大，止损比例从 {current:g} 收紧到 {next_value:g}")

        if "take_profit_pct" in params and sharpe < target_sharpe:
            current = _param_float(params["take_profit_pct"], 0.1)
            next_value = round(current * 1.1, 4)
            _set_param_default(params, "take_profit_pct", next_value)
            notes.append(f"盈亏比不足，止盈比例从 {current:g} 提高到 {next_value:g}")

        if "atr_stop_multiplier" in params:
            current = _param_float(params["atr_stop_multiplier"], 2.0)
            next_value = round(max(current * 0.9, 1.0), 3)
            _set_param_default(params, "atr_stop_multiplier", next_value)
            notes.append(f"ATR 止损倍数从 {current:g} 调整到 {next_value:g}")

        if "fast_period" in params and "slow_period" in params:
            fast = _param_int(params["fast_period"], 10)
            slow = _param_int(params["slow_period"], 30)
            next_fast = max(fast - 1, 2) if total_trades < 3 else fast
            next_slow = max(slow + 2, next_fast + 2)
            if next_fast != fast or next_slow != slow:
                _set_param_default(params, "fast_period", next_fast)
                _set_param_default(params, "slow_period", next_slow)
                notes.append(f"调整均线窗口为 fast={next_fast}, slow={next_slow}")

        if "rsi_period" in params and sharpe < target_sharpe:
            current = _param_int(params["rsi_period"], 14)
            next_value = max(current - 1, 5) if total_trades < 3 else current + 1
            _set_param_default(params, "rsi_period", next_value)
            notes.append(f"RSI 周期从 {current} 调整到 {next_value}")

        if failures:
            notes.append("本轮未通过验收门槛：" + "；".join(failures))

        if not notes:
            notes.append("上一轮指标未达标，保留策略结构并创建新版本继续验证")

        improved.code = _rewrite_code_param_defaults(improved.code, improved.params)
        improved.risk_points = list(
            dict.fromkeys(
                [
                    *improved.risk_points,
                    "该版本由自动投研循环基于上一轮回测指标生成，需要继续做样本外验证。",
                ]
            )
        )
        improved.next_steps = [
            "继续回测新版本并比较 Sharpe、回撤和交易次数",
            "达标后进入 paper 模拟交易并观察实盘风控指标",
        ]
        return StrategyImprovement(draft=improved, notes=notes)


class AIStrategyImprover:
    """Use configured AI models to improve strategy drafts, with local fallback."""

    def __init__(
        self,
        *,
        local_improver: LocalStrategyImprover | None = None,
        ai_router: AIChatRouter | None = None,
        preference_service: AIModelPreferenceService | None = None,
        settings: Any | None = None,
    ) -> None:
        self.local_improver = local_improver or LocalStrategyImprover()
        self.ai_router = ai_router or get_ai_chat_router()
        self.preference_service = preference_service or AIModelPreferenceService()
        self.settings = settings or get_settings()

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        preference = await self._resolve_preference(user_id)
        if preference is None:
            return await self.local_improver.improve(
                draft,
                iteration=iteration,
                metrics=metrics,
                target_sharpe=target_sharpe,
                quality_gate_failures=quality_gate_failures,
                user_id=user_id,
                request=request,
            )

        try:
            response = await self.ai_router.chat_completion(
                messages=_build_improvement_messages(
                    draft,
                    iteration=iteration,
                    metrics=metrics,
                    target_sharpe=target_sharpe,
                    quality_gate_failures=quality_gate_failures,
                    request=request,
                ),
                model=preference.model,
                provider=preference.provider,
                base_url=preference.base_url,
                api_key=preference.api_key,
                timeout=float(getattr(self.settings, "AI_CHAT_TIMEOUT", 120.0) or 120.0),
                temperature=min(
                    float(getattr(self.settings, "AI_CHAT_TEMPERATURE", 0.2) or 0.2),
                    0.3,
                ),
            )
            improved = _merge_ai_improvement(
                draft,
                _parse_ai_improvement_payload(response.content),
                iteration=iteration,
                model_id=response.model,
            )
            return improved
        except Exception as exc:
            fallback = await self.local_improver.improve(
                draft,
                iteration=iteration,
                metrics=metrics,
                target_sharpe=target_sharpe,
                quality_gate_failures=quality_gate_failures,
                user_id=user_id,
                request=request,
            )
            return StrategyImprovement(
                draft=fallback.draft,
                notes=[
                    f"AI模型改稿不可用，已使用本地规则回退：{exc}",
                    *fallback.notes,
                ],
            )

    async def _resolve_preference(
        self,
        user_id: str | None,
    ) -> ResolvedAIModelPreference | None:
        preference = await self.preference_service.resolve_for_user(user_id)
        if preference is not None:
            return preference if preference.configured else None

        if not bool(getattr(self.settings, "AI_CHAT_ENABLED", False)):
            return None
        model = str(getattr(self.settings, "AI_CHAT_MODEL", "") or "").strip()
        base_url = str(getattr(self.settings, "AI_CHAT_BASE_URL", "") or "").strip()
        api_key = str(getattr(self.settings, "AI_CHAT_API_KEY", "") or "").strip()
        if not (model and base_url and api_key):
            return None
        return ResolvedAIModelPreference(
            provider="openai_compatible",
            model=model,
            base_url=base_url,
            api_key=api_key,
            configured=True,
        )


class AIStrategyResearchService:
    """Orchestrate generate -> backtest -> improve -> paper trading."""

    def __init__(
        self,
        *,
        strategy_service: StrategyService | None = None,
        workspace_service: WorkspaceService | None = None,
        improver: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.strategy_service = strategy_service or StrategyService()
        self.workspace_service = workspace_service or WorkspaceService()
        self.improver = improver or AIStrategyImprover()
        self.sleep = sleep or asyncio.sleep

    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> AIStrategyResearchRunResponse:
        run_id = str(uuid.uuid4())
        started_at = _utc_iso_now()
        await _emit_research_progress(
            progress_callback,
            {
                "current_stage": "initializing",
                "progress": 2.0,
                "iteration_count": 0,
                "max_iterations": request.max_iterations,
                "message": "AI research loop is initializing",
            },
        )
        request, draft = await self._prepare_initial_draft(user_id, request)
        research_workspace = await self._ensure_research_workspace(user_id, request)
        initial_draft_notes: list[str] = []
        if draft is None:
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "drafting",
                    "progress": 5.0,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "message": "Generating initial strategy draft",
                },
            )
            draft_response = await self.strategy_service.generate_copilot_draft(
                user_id,
                StrategyCopilotDraftRequest(
                    prompt=_build_research_draft_prompt(request),
                    knowledge_base_id=request.knowledge_base_id,
                    thinking_mode=request.thinking_mode,
                ),
            )
            draft = _normalize_research_draft(draft_response.strategy_draft, request)
            draft, initial_draft_notes = _ensure_runnable_initial_draft(draft, request)

        iterations: list[AIStrategyResearchIteration] = []
        best_iteration: AIStrategyResearchIteration | None = None
        selected_iteration: AIStrategyResearchIteration | None = None
        pending_improvement_notes: list[str] = initial_draft_notes
        continuation_failures = _continuation_quality_gate_failures(request.continuation_context)
        validation_window = _out_of_sample_window(request)
        if continuation_failures:
            improvement = await self.improver.improve(
                draft,
                iteration=0,
                metrics=dict(request.continuation_context.get("metrics") or {}),
                target_sharpe=request.target_sharpe,
                quality_gate_failures=continuation_failures,
                user_id=user_id,
                request=request,
            )
            draft = _normalize_research_draft(improvement.draft, request)
            continuation_source = str(request.continuation_context.get("source") or "")
            continuation_note = (
                "基于上一轮模拟交易启动失败原因生成 continuation 改进版。"
                if continuation_source == "paper_trading_failed"
                else "基于上一轮模拟交易复核结果生成 continuation 改进版。"
            )
            pending_improvement_notes = [
                continuation_note,
                *improvement.notes,
            ]
        achieved = False

        for iteration in range(1, request.max_iterations + 1):
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "backtesting",
                    "progress": _research_loop_progress(iteration - 1, request.max_iterations),
                    "current_iteration": iteration,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "message": f"Running AI research backtest iteration {iteration}",
                },
            )
            try:
                _validate_strategy_code_draft(draft.code)
            except ValueError as exc:
                raise ValueError(
                    f"Generated strategy code validation failed before iteration {iteration}: {exc}"
                ) from exc
            backtest_request = self._build_backtest_request(
                draft,
                request,
                start_date=validation_window.train_start if validation_window else None,
                end_date=validation_window.train_end if validation_window else None,
                group_name_suffix=" 训练样本" if validation_window else "",
            )
            backtest_response = await self.strategy_service.backtest_copilot_draft(
                user_id,
                research_workspace.id,
                backtest_request,
            )
            if backtest_response is None:
                raise ValueError("Research workspace or generated strategy was not found")
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "backtesting",
                    "progress": min(
                        _research_loop_progress(iteration - 1, request.max_iterations) + 4.0,
                        80.0,
                    ),
                    "current_iteration": iteration,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "current_backtest_task_id": backtest_response.run_result.task_id,
                    "message": f"Backtest task submitted for iteration {iteration}",
                },
            )

            unit_status, failure_reason = await self._wait_for_unit_status(
                research_workspace.id,
                user_id,
                backtest_response.unit.id,
                initial_status=backtest_response.unit_status,
                timeout_seconds=request.backtest_timeout_seconds,
                poll_interval_seconds=request.poll_interval_seconds,
            )
            metrics = dict(unit_status.metrics_snapshot if unit_status else {})
            sharpe = _metric_float(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
            total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
            quality_gate_failures = _quality_gate_failures(request, metrics)
            passed = (
                unit_status is not None
                and unit_status.run_status == "completed"
                and not quality_gate_failures
            )
            quality_score = _quality_score(
                request,
                metrics,
                run_status=unit_status.run_status if unit_status else None,
            )
            quality_gate_evaluations = _quality_gate_evaluations(
                request,
                metrics,
                run_status=unit_status.run_status if unit_status else None,
            )
            if not failure_reason and unit_status is not None and unit_status.run_status != "completed":
                failure_reason = f"Backtest finished with status {unit_status.run_status}"
            if not failure_reason and quality_gate_failures:
                failure_reason = "; ".join(quality_gate_failures)

            validation_unit: StrategyUnitResponse | None = None
            validation_run_result: StrategyCopilotRunResult | None = None
            validation_unit_status: UnitStatusResponse | None = None
            validation_status: str | None = None
            validation_metrics: dict[str, Any] = {}
            validation_gate_evaluations: list[dict[str, Any]] = []
            validation_failures: list[str] = []
            validation_failure_reason: str | None = None
            validation_window_payload = validation_window.as_dict() if validation_window else None

            if passed and request.out_of_sample_validation:
                if validation_window is None:
                    validation_status = "skipped"
                    validation_failure_reason = (
                        "Out-of-sample validation skipped because start_date/end_date "
                        "do not define a splittable range"
                    )
                else:
                    await _emit_research_progress(
                        progress_callback,
                        {
                            "current_stage": "validating",
                            "progress": min(
                                _research_loop_progress(iteration, request.max_iterations) + 1.0,
                                83.0,
                            ),
                            "current_iteration": iteration,
                            "iteration_count": len(iterations),
                            "max_iterations": request.max_iterations,
                            "latest_iteration": {
                                "iteration": iteration,
                                "validation_window": validation_window_payload,
                            },
                            "message": f"Running out-of-sample validation for iteration {iteration}",
                        },
                    )
                    validation_request = self._build_backtest_request(
                        draft,
                        request,
                        start_date=validation_window.validation_start,
                        end_date=validation_window.validation_end,
                        group_name_suffix=" 样本外验证",
                    )
                    validation_response = await self.strategy_service.backtest_copilot_draft(
                        user_id,
                        research_workspace.id,
                        validation_request,
                    )
                    if validation_response is None:
                        raise ValueError(
                            "Research workspace or generated validation strategy was not found"
                        )
                    validation_unit = validation_response.unit
                    validation_run_result = validation_response.run_result
                    await _emit_research_progress(
                        progress_callback,
                        {
                            "current_stage": "validating",
                            "progress": min(
                                _research_loop_progress(iteration, request.max_iterations) + 2.0,
                                84.0,
                            ),
                            "current_iteration": iteration,
                            "iteration_count": len(iterations),
                            "max_iterations": request.max_iterations,
                            "current_backtest_task_id": validation_response.run_result.task_id,
                            "latest_iteration": {
                                "iteration": iteration,
                                "validation_window": validation_window_payload,
                            },
                            "message": (
                                f"Out-of-sample validation task submitted for iteration {iteration}"
                            ),
                        },
                    )
                    validation_unit_status, validation_wait_failure = await self._wait_for_unit_status(
                        research_workspace.id,
                        user_id,
                        validation_response.unit.id,
                        initial_status=validation_response.unit_status,
                        timeout_seconds=request.backtest_timeout_seconds,
                        poll_interval_seconds=request.poll_interval_seconds,
                    )
                    validation_metrics = dict(
                        validation_unit_status.metrics_snapshot if validation_unit_status else {}
                    )
                    validation_run_status = (
                        validation_unit_status.run_status if validation_unit_status else None
                    )
                    validation_gate_evaluations = _out_of_sample_gate_evaluations(
                        request,
                        validation_metrics,
                        run_status=validation_run_status,
                    )
                    validation_failures = _out_of_sample_failures(
                        request,
                        validation_metrics,
                        run_status=validation_run_status,
                    )
                    validation_status = "passed" if not validation_failures else "failed"
                    if validation_wait_failure and validation_run_status != "completed":
                        validation_failure_reason = validation_wait_failure
                    if validation_failures:
                        validation_failure_reason = "; ".join(validation_failures)
                        quality_gate_failures = [*quality_gate_failures, *validation_failures]
                        failure_reason = validation_failure_reason
                        passed = False
            diagnostics = _iteration_diagnostics(
                request,
                iteration=iteration,
                metrics=metrics,
                run_status=unit_status.run_status if unit_status else None,
                quality_gate_failures=quality_gate_failures,
                quality_gate_evaluations=quality_gate_evaluations,
                failure_reason=failure_reason,
            )
            if request.out_of_sample_validation:
                diagnostics["out_of_sample_validation"] = {
                    "status": validation_status or "not_required",
                    "window": validation_window_payload,
                    "metrics": validation_metrics,
                    "gate_evaluations": validation_gate_evaluations,
                    "failures": validation_failures,
                    "failure_reason": validation_failure_reason,
                }
                if validation_failures:
                    diagnostics["promotion_ready"] = False
                    diagnostics["summary"] = (
                        f"第 {iteration} 轮训练样本达标，但样本外验证未通过："
                        + "；".join(validation_failures)
                    )
            improvement_plan = list(diagnostics.get("improvement_plan") or [])

            item = AIStrategyResearchIteration(
                iteration=iteration,
                strategy=backtest_response.strategy,
                unit=backtest_response.unit,
                run_result=backtest_response.run_result,
                unit_status=unit_status,
                metrics=metrics,
                sharpe_ratio=sharpe,
                total_trades=total_trades,
                validation_unit=validation_unit,
                validation_run_result=validation_run_result,
                validation_unit_status=validation_unit_status,
                validation_status=validation_status,
                validation_window=validation_window_payload,
                validation_metrics=validation_metrics,
                validation_gate_evaluations=validation_gate_evaluations,
                validation_failures=validation_failures,
                validation_failure_reason=validation_failure_reason,
                quality_score=quality_score,
                quality_gate_evaluations=quality_gate_evaluations,
                passed=passed,
                failure_reason=None if passed else failure_reason,
                quality_gate_failures=quality_gate_failures,
                diagnostics=diagnostics,
                improvement_plan=improvement_plan,
                improvement_notes=pending_improvement_notes,
                next_actions=_iteration_next_actions(
                    iteration=iteration,
                    max_iterations=request.max_iterations,
                    passed=passed,
                    run_status=unit_status.run_status if unit_status else None,
                    quality_gate_failures=quality_gate_failures,
                    failure_reason=failure_reason,
                ),
            )
            iterations.append(item)
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "evaluating",
                    "progress": _research_loop_progress(iteration, request.max_iterations),
                    "current_iteration": iteration,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "latest_iteration": _compact_research_iteration(item),
                    "message": f"Completed AI research iteration {iteration}",
                },
            )
            if best_iteration is None or _is_better_research_candidate(item, best_iteration):
                best_iteration = item
            if passed:
                achieved = True
                selected_iteration = item
                break

            if iteration < request.max_iterations:
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "improving",
                        "progress": min(
                            _research_loop_progress(iteration, request.max_iterations) + 2.0,
                            82.0,
                        ),
                        "current_iteration": iteration + 1,
                        "iteration_count": len(iterations),
                        "max_iterations": request.max_iterations,
                        "latest_iteration": _compact_research_iteration(item),
                        "message": f"Improving strategy for iteration {iteration + 1}",
                    },
                )
                improvement = await self.improver.improve(
                    draft,
                    iteration=iteration,
                    metrics=_improvement_metrics(metrics, validation_metrics),
                    target_sharpe=request.target_sharpe,
                    quality_gate_failures=quality_gate_failures,
                    user_id=user_id,
                    request=request,
                )
                draft = _normalize_research_draft(improvement.draft, request)
                pending_improvement_notes = improvement.notes

        paper_trading = None
        paper_trading_error = None
        result_iteration = selected_iteration or best_iteration
        if achieved and request.start_paper_trading and result_iteration is not None:
            await _emit_research_progress(
                progress_callback,
                {
                    "current_stage": "paper_trading",
                    "progress": 88.0,
                    "iteration_count": len(iterations),
                    "max_iterations": request.max_iterations,
                    "latest_iteration": _compact_research_iteration(result_iteration),
                    "message": "Starting paper trading for achieved strategy",
                },
            )
            try:
                paper_trading = await self._start_paper_trading(
                    user_id,
                    request,
                    result_iteration,
                    run_id=run_id,
                    research_workspace_id=research_workspace.id,
                )
            except Exception as exc:
                paper_trading_error = str(exc)
                await _emit_research_progress(
                    progress_callback,
                    {
                        "current_stage": "paper_trading_failed",
                        "progress": 92.0,
                        "iteration_count": len(iterations),
                        "max_iterations": request.max_iterations,
                        "latest_iteration": _compact_research_iteration(result_iteration),
                        "message": f"Paper trading start failed: {paper_trading_error}",
                    },
                )

        status = "achieved" if achieved else "max_iterations_reached"
        if iterations and iterations[-1].unit_status and iterations[-1].unit_status.run_status == "timeout":
            status = "timeout"
        best_metrics = dict(result_iteration.metrics) if result_iteration else {}
        paper_monitoring_plan = (
            _paper_monitoring_plan(request, result_iteration)
            if achieved and result_iteration is not None
            else []
        )
        message = (
            f"Target Sharpe {request.target_sharpe:.3f} achieved"
            if achieved
            else f"Target Sharpe {request.target_sharpe:.3f} not achieved"
        )
        completed_at = _utc_iso_now()
        next_actions = _run_next_actions(
            status=status,
            achieved=achieved,
            request=request,
            result_iteration=result_iteration,
            paper_trading=paper_trading,
            paper_trading_error=paper_trading_error,
        )
        pipeline = _pipeline_summary(
            status=status,
            achieved=achieved,
            iteration_count=len(iterations),
            max_iterations=request.max_iterations,
            paper_trading_started=bool(paper_trading.started) if paper_trading else False,
            paper_trading_error=paper_trading_error,
            paper_review_status=None,
            paper_review_ready_for_live=False,
        )
        response = AIStrategyResearchRunResponse(
            run_id=run_id,
            status=status,
            achieved=achieved,
            target_sharpe=request.target_sharpe,
            started_at=started_at,
            completed_at=completed_at,
            best_iteration=result_iteration.iteration if result_iteration else None,
            best_quality_score=result_iteration.quality_score if result_iteration else 0.0,
            best_quality_gate_evaluations=result_iteration.quality_gate_evaluations
            if result_iteration
            else [],
            best_diagnostics=result_iteration.diagnostics if result_iteration else {},
            best_metrics=best_metrics,
            research_workspace=research_workspace,
            iterations=iterations,
            best_strategy=result_iteration.strategy if result_iteration else None,
            paper_trading=paper_trading,
            paper_monitoring_plan=paper_monitoring_plan,
            pipeline=pipeline,
            next_actions=next_actions,
            message=message,
        )
        run_record = _build_research_run_record(
            run_id=run_id,
            request=request,
            response=response,
            started_at=started_at,
            completed_at=completed_at,
        )
        research_workspace = await self._persist_research_run_record(
            user_id,
            research_workspace,
            run_record,
        )
        return response.model_copy(
            update={
                "research_workspace": research_workspace,
                "run_record": run_record,
            }
        )

    async def list_run_records(
        self,
        user_id: str,
        *,
        research_workspace_id: str | None = None,
        limit: int = 20,
    ) -> AIStrategyResearchRunListResponse:
        limit = max(min(int(limit or 20), 100), 1)
        if research_workspace_id:
            workspace = await self.workspace_service.get_workspace(research_workspace_id, user_id)
            if workspace is None:
                raise ValueError("Research workspace not found")
            records = _research_run_records_from_workspace(workspace)
            return AIStrategyResearchRunListResponse(total=len(records), items=records[:limit])

        _, workspaces = await self.workspace_service.list_workspaces(
            user_id,
            skip=0,
            limit=100,
            workspace_type="research",
        )
        records: list[AIStrategyResearchRunRecord] = []
        for workspace in workspaces:
            records.extend(_research_run_records_from_workspace(workspace))
        records.sort(key=lambda item: item.completed_at, reverse=True)
        return AIStrategyResearchRunListResponse(total=len(records), items=records[:limit])

    async def start_paper_trading_from_run(
        self,
        user_id: str,
        run_id: str,
        request: AIStrategyPaperTradingStartRequest,
    ) -> AIStrategyPaperTradingStart:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=request.research_workspace_id,
        )
        if record is None:
            raise ValueError("AI research run record not found")
        if not record.achieved:
            raise ValueError("AI research run has not achieved its quality gates")
        if record.paper_trading_started:
            raise ValueError("AI research run has already started paper trading")

        iteration_payload = _best_iteration_payload(record)
        if iteration_payload is None:
            raise ValueError("AI research run record has no best iteration to promote")
        if not record.best_strategy_id:
            raise ValueError("AI research run record has no best strategy to promote")

        strategy = await self.strategy_service.get_strategy(record.best_strategy_id, user_id)
        if strategy is None:
            raise ValueError("Best strategy not found")

        unit_id = str(iteration_payload.get("unit_id") or "").strip()
        if not unit_id:
            raise ValueError("AI research run record has no research unit to promote")
        unit = await self.workspace_service.get_unit(record.research_workspace_id, unit_id, user_id)
        if unit is None:
            raise ValueError("Research unit not found")

        run_request = _paper_start_request_from_record(record, request)
        iteration = _iteration_from_record_payload(
            record,
            strategy=strategy,
            unit=unit,
            payload=iteration_payload,
        )
        try:
            paper_trading = await self._start_paper_trading(
                user_id,
                run_request,
                iteration,
                run_id=record.run_id,
                research_workspace_id=record.research_workspace_id,
            )
        except Exception as exc:
            await self._mark_run_record_paper_start_failed(user_id, record, str(exc))
            raise ValueError(str(exc)) from exc
        await self._mark_run_record_paper_started(user_id, record, paper_trading)
        return paper_trading

    async def review_paper_trading_run(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyPaperTradingReview:
        record = await self._find_research_run_record(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
        )
        if record is None:
            raise ValueError("AI research run record not found")

        workspace = None
        unit = None
        unit_status = None
        if record.paper_workspace_id:
            workspace = await self.workspace_service.get_workspace(record.paper_workspace_id, user_id)
        if workspace is not None and record.paper_unit_id:
            unit = await self.workspace_service.get_unit(workspace.id, record.paper_unit_id, user_id)
            statuses = await self.workspace_service.get_units_status(workspace.id, user_id)
            unit_status = _find_unit_status(statuses or [], record.paper_unit_id)

        monitoring_plan = _resolve_paper_monitoring_plan(record, unit)
        evaluations = _evaluate_paper_monitoring_plan(
            monitoring_plan,
            unit=unit,
            unit_status=unit_status,
        )
        ready_for_live = bool(evaluations) and all(item.passed for item in evaluations)
        review_status = _paper_review_status(
            record,
            workspace=workspace,
            unit=unit,
            evaluations=evaluations,
            ready_for_live=ready_for_live,
        )
        pipeline = _pipeline_summary_from_record(
            record,
            paper_trading_started=record.paper_trading_started,
            paper_review_status=review_status,
            paper_review_ready_for_live=ready_for_live,
        )
        reviewed_at = _utc_iso_now()
        review = AIStrategyPaperTradingReview(
            run_id=record.run_id,
            research_workspace_id=record.research_workspace_id,
            paper_workspace_id=record.paper_workspace_id,
            paper_unit_id=record.paper_unit_id,
            paper_trading_started=record.paper_trading_started,
            workspace=workspace,
            unit=unit,
            unit_status=unit_status,
            monitoring_plan=monitoring_plan,
            evaluations=evaluations,
            ready_for_live=ready_for_live,
            status=review_status,
            reviewed_at=reviewed_at,
            pipeline=pipeline,
            next_actions=_paper_review_next_actions(
                review_status,
                evaluations=evaluations,
                monitoring_plan=monitoring_plan,
            ),
        )
        await self._mark_run_record_paper_reviewed(user_id, record, review)
        return review

    async def _ensure_research_workspace(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> WorkspaceResponse:
        if request.research_workspace_id:
            workspace = await self.workspace_service.get_workspace(
                request.research_workspace_id, user_id
            )
            if workspace is None:
                raise ValueError("Research workspace not found")
            return workspace
        name = _bounded_name(f"AI投研 - {request.symbol} - {request.prompt}", 200)
        return await self.workspace_service.create_workspace(
            user_id,
            WorkspaceCreate(
                name=name,
                description="AI generated strategy research loop",
                workspace_type="research",
            ),
        )

    async def _prepare_initial_draft(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
    ) -> tuple[AIStrategyResearchRunRequest, AIStrategyDraft | None]:
        seed_strategy_id = request.seed_strategy_id
        update: dict[str, Any] = {}
        explicit_fields = _request_explicit_fields(request)
        if request.continue_from_run_id:
            record = await self._find_research_run_record(
                user_id,
                request.continue_from_run_id,
                research_workspace_id=request.research_workspace_id,
            )
            if record is None:
                raise ValueError("AI research run record not found")
            if not seed_strategy_id:
                seed_strategy_id = record.best_strategy_id
            if not seed_strategy_id:
                raise ValueError("AI research run record has no best strategy to continue")
            if not request.research_workspace_id:
                update["research_workspace_id"] = record.research_workspace_id
            if not request.symbol_name and record.symbol_name:
                update["symbol_name"] = record.symbol_name
            if not request.knowledge_base_id and record.knowledge_base_id:
                update["knowledge_base_id"] = record.knowledge_base_id
            if "start_date" not in explicit_fields and record.start_date:
                update["start_date"] = record.start_date
            if "end_date" not in explicit_fields and record.end_date:
                update["end_date"] = record.end_date
            if "initial_cash" not in explicit_fields:
                update["initial_cash"] = record.initial_cash
            if "commission" not in explicit_fields:
                update["commission"] = record.commission
            if "annual_days" not in explicit_fields:
                update["annual_days"] = record.annual_days
            if "calc_method" not in explicit_fields and record.calc_method:
                update["calc_method"] = record.calc_method
            if "weight_mode" not in explicit_fields and record.weight_mode:
                update["weight_mode"] = record.weight_mode
            if record.thinking_mode and "thinking_mode" not in explicit_fields:
                update["thinking_mode"] = record.thinking_mode
            continuation_context = _continuation_context_from_record(record)
            if continuation_context:
                update["continuation_context"] = {
                    **dict(request.continuation_context or {}),
                    **continuation_context,
                }

        if seed_strategy_id:
            update["seed_strategy_id"] = seed_strategy_id
            effective_request = request.model_copy(update=update) if update else request
            strategy = await self.strategy_service.get_strategy(seed_strategy_id, user_id)
            if strategy is None:
                raise ValueError("Seed strategy not found")
            return effective_request, _draft_from_strategy(strategy, effective_request)

        effective_request = request.model_copy(update=update) if update else request
        return effective_request, None

    async def _find_research_run_record(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ) -> AIStrategyResearchRunRecord | None:
        records = await self.list_run_records(
            user_id,
            research_workspace_id=research_workspace_id,
            limit=100,
        )
        return next((item for item in records.items if item.run_id == run_id), None)

    def _build_backtest_request(
        self,
        draft: AIStrategyDraft,
        request: AIStrategyResearchRunRequest,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        group_name_suffix: str = "",
    ) -> StrategyCopilotBacktestRequest:
        asset_specs = _resolve_research_asset_specs(request)
        effective_start_date = start_date if start_date is not None else request.start_date
        effective_end_date = end_date if end_date is not None else request.end_date
        data_config = {
            **request.data_config,
            "symbol": request.symbol,
            "symbol_name": request.symbol_name or request.symbol,
            "timeframe": request.timeframe,
            "timeframe_n": request.timeframe_n,
        }
        if effective_start_date:
            data_config["start_date"] = effective_start_date
        if effective_end_date:
            data_config["end_date"] = effective_end_date

        unit_settings = {
            **request.unit_settings,
            "initial_cash": request.initial_cash,
            "commission": request.commission,
            "annual_days": request.annual_days,
            "calc_method": request.calc_method,
            "weight_mode": request.weight_mode,
        }
        if asset_specs:
            _merge_contract_metadata(data_config, asset_specs)
            _merge_contract_metadata(unit_settings, asset_specs)
            _apply_primary_asset_spec_settings(
                unit_settings,
                asset_specs,
                override_commission=not _request_has_explicit_commission(request),
            )

        return StrategyCopilotBacktestRequest(
            strategy_draft=draft,
            symbol=request.symbol,
            symbol_name=request.symbol_name or request.symbol,
            timeframe=request.timeframe,
            timeframe_n=request.timeframe_n,
            group_name=_bounded_name(
                f"{request.group_name or draft.execution_plan.group_name or draft.name}{group_name_suffix}",
                200,
            ),
            data_config=data_config,
            unit_settings=unit_settings,
            optimization_config=request.optimization_config,
            parallel=False,
            report_config=None,
        )

    async def _wait_for_unit_status(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        *,
        initial_status: UnitStatusResponse | None,
        timeout_seconds: float,
        poll_interval_seconds: float,
    ) -> tuple[UnitStatusResponse | None, str | None]:
        status = _coerce_unit_status(initial_status)
        if status is not None and status.run_status in _TERMINAL_UNIT_STATUSES:
            return status, None if status.run_status == "completed" else status.run_status

        deadline = time.monotonic() + timeout_seconds
        last_status = status
        while time.monotonic() < deadline:
            statuses = await self.workspace_service.get_units_status(workspace_id, user_id)
            matched = _find_unit_status(statuses or [], unit_id)
            if matched is not None:
                last_status = matched
                if matched.run_status in _TERMINAL_UNIT_STATUSES:
                    return matched, None if matched.run_status == "completed" else matched.run_status
            await self.sleep(poll_interval_seconds)

        timeout_status = UnitStatusResponse(
            id=unit_id,
            run_status="timeout",
            last_task_id=last_status.last_task_id if last_status else None,
            metrics_snapshot=dict(last_status.metrics_snapshot if last_status else {}),
            run_count=last_status.run_count if last_status else 0,
            last_run_time=last_status.last_run_time if last_status else None,
            bar_count=last_status.bar_count if last_status else None,
            trading_instance_id=last_status.trading_instance_id if last_status else None,
            trading_snapshot=dict(last_status.trading_snapshot if last_status else {}),
            trading_mode=last_status.trading_mode if last_status else "paper",
            lock_trading=last_status.lock_trading if last_status else False,
            lock_running=last_status.lock_running if last_status else False,
        )
        return timeout_status, "Backtest timed out"

    async def _start_paper_trading(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        best_iteration: AIStrategyResearchIteration,
        *,
        run_id: str,
        research_workspace_id: str,
    ) -> AIStrategyPaperTradingStart:
        workspace = None
        if request.trading_workspace_id:
            workspace = await self.workspace_service.get_workspace(request.trading_workspace_id, user_id)
            if workspace is None:
                raise ValueError("Trading workspace not found")
        if workspace is None:
            workspace = await self.workspace_service.create_workspace(
                user_id,
                WorkspaceCreate(
                    name=request.paper_workspace_name
                    or _bounded_name(f"AI模拟交易 - {best_iteration.strategy.name}", 200),
                    description="AI research loop paper trading workspace",
                    workspace_type="trading",
                ),
            )

        handoff = _build_paper_trading_handoff(
            run_id=run_id,
            research_workspace_id=research_workspace_id,
            request=request,
            best_iteration=best_iteration,
            promoted_at=_utc_iso_now(),
        )
        unit_data_config = {
            **best_iteration.unit.data_config,
            "ai_research_run_id": run_id,
            "ai_research_workspace_id": research_workspace_id,
        }
        unit_settings = {
            **best_iteration.unit.unit_settings,
            "ai_research_handoff": handoff,
        }
        unit_payload = StrategyUnitCreate(
            group_name=best_iteration.unit.group_name or best_iteration.strategy.name,
            strategy_id=best_iteration.strategy.id,
            strategy_name=best_iteration.strategy.name,
            symbol=request.symbol,
            symbol_name=request.symbol_name or request.symbol,
            timeframe=request.timeframe,
            timeframe_n=request.timeframe_n,
            category=best_iteration.strategy.category,
            data_config=unit_data_config,
            unit_settings=unit_settings,
            params=best_iteration.unit.params,
            optimization_config=best_iteration.unit.optimization_config,
            trading_mode="paper",
            gateway_config=request.gateway_config,
            lock_trading=False,
            lock_running=False,
        )
        created_unit = await self.workspace_service.create_unit(workspace.id, user_id, unit_payload)
        if created_unit is None:
            raise ValueError("Failed to create paper trading unit")
        unit = StrategyUnitResponse.model_validate(created_unit)

        run_result = None
        run_results = await self.workspace_service.run_units(
            workspace.id, user_id, [unit.id], parallel=False
        )
        if run_results:
            run_result = StrategyCopilotRunResult.model_validate(run_results[0])

        handoff = {
            **handoff,
            "paper_workspace_id": workspace.id,
            "paper_unit_id": unit.id,
            "paper_task_id": run_result.task_id if run_result else None,
            "paper_run_status": run_result.status if run_result else None,
        }
        unit = unit.model_copy(
            update={
                "data_config": {
                    **unit.data_config,
                    "ai_research_run_id": run_id,
                    "ai_research_workspace_id": research_workspace_id,
                },
                "unit_settings": {
                    **unit.unit_settings,
                    "ai_research_handoff": handoff,
                },
            }
        )
        persisted_unit = await self.workspace_service.update_unit(
            workspace.id,
            unit.id,
            user_id,
            StrategyUnitUpdate(
                data_config=unit.data_config,
                unit_settings=unit.unit_settings,
            ),
        )
        if persisted_unit is not None:
            unit = StrategyUnitResponse.model_validate(persisted_unit)
        workspace = await self._persist_paper_trading_handoff(user_id, workspace, handoff)

        return AIStrategyPaperTradingStart(
            workspace=workspace,
            unit=unit,
            run_result=run_result,
            started=run_result is not None and run_result.status not in {"failed", "cancelled"},
            handoff=handoff,
        )

    async def _persist_paper_trading_handoff(
        self,
        user_id: str,
        workspace: WorkspaceResponse,
        handoff: dict[str, Any],
    ) -> WorkspaceResponse:
        settings = dict(workspace.settings or {})
        ai_handoff = dict(settings.get("ai_research_handoff") or {})
        handoff_payload = dict(handoff)

        existing: list[dict[str, Any]] = []
        raw_handoffs = ai_handoff.get("handoffs")
        if isinstance(raw_handoffs, list):
            existing = [dict(item) for item in raw_handoffs if isinstance(item, dict)]
        ai_handoff["last_handoff"] = handoff_payload
        ai_handoff["handoffs"] = [
            handoff_payload,
            *[
                item
                for item in existing
                if str(item.get("run_id") or "") != str(handoff_payload.get("run_id") or "")
            ],
        ][:20]

        updated = await self.workspace_service.update_workspace(
            workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research_handoff": ai_handoff}),
        )
        if updated is not None:
            return updated

        settings["ai_research_handoff"] = ai_handoff
        return workspace.model_copy(update={"settings": settings})

    async def _persist_research_run_record(
        self,
        user_id: str,
        research_workspace: WorkspaceResponse,
        run_record: AIStrategyResearchRunRecord,
    ) -> WorkspaceResponse:
        settings = dict(research_workspace.settings or {})
        ai_research = dict(settings.get("ai_research") or {})
        record_payload = run_record.model_dump(mode="json")

        existing_runs: list[dict[str, Any]] = []
        raw_runs = ai_research.get("runs")
        if isinstance(raw_runs, list):
            existing_runs = [dict(item) for item in raw_runs if isinstance(item, dict)]
        runs = [
            record_payload,
            *[
                item
                for item in existing_runs
                if str(item.get("run_id") or "") != run_record.run_id
            ],
        ][:20]
        ai_research["last_run"] = record_payload
        ai_research["runs"] = runs

        updated_workspace = await self.workspace_service.update_workspace(
            research_workspace.id,
            user_id,
            WorkspaceUpdate(settings={"ai_research": ai_research}),
        )
        if updated_workspace is not None:
            return updated_workspace

        settings["ai_research"] = ai_research
        return research_workspace.model_copy(update={"settings": settings})

    async def _mark_run_record_paper_started(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        paper_trading: AIStrategyPaperTradingStart,
    ) -> WorkspaceResponse | None:
        workspace = await self.workspace_service.get_workspace(record.research_workspace_id, user_id)
        if workspace is None:
            return None
        updated_record = record.model_copy(
            update={
                "paper_workspace_id": paper_trading.workspace.id,
                "paper_unit_id": paper_trading.unit.id,
                "paper_trading_started": paper_trading.started,
                "paper_monitoring_plan": _paper_monitoring_plan_from_handoff(
                    paper_trading.handoff
                ),
                "paper_handoff": dict(paper_trading.handoff or {}),
                "pipeline": _pipeline_summary_from_record(
                    record,
                    paper_trading_started=paper_trading.started,
                ),
                "next_actions": [
                    "已从历史投研结果启动模拟交易，下一步跟踪模拟账户成交、持仓和风控指标。",
                    "保留研究工作区记录，用于后续继续投研或样本外验证。",
                ],
            }
        )
        return await self._persist_research_run_record(user_id, workspace, updated_record)

    async def _mark_run_record_paper_start_failed(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        error: str,
    ) -> WorkspaceResponse | None:
        workspace = await self.workspace_service.get_workspace(record.research_workspace_id, user_id)
        if workspace is None:
            return None
        paper_trading_error = str(error or "Paper trading start failed").strip()
        updated_record = record.model_copy(
            update={
                "paper_trading_started": False,
                "paper_review_status": None,
                "paper_review_ready_for_live": False,
                "paper_reviewed_at": None,
                "paper_review_evaluations": [],
                "paper_review_next_actions": [],
                "pipeline": _pipeline_summary(
                    status=record.status,
                    achieved=record.achieved,
                    iteration_count=record.iteration_count,
                    max_iterations=record.max_iterations,
                    paper_trading_started=False,
                    paper_trading_error=paper_trading_error,
                    paper_review_status=None,
                    paper_review_ready_for_live=False,
                ),
                "next_actions": [
                    f"模拟交易启动错误：{paper_trading_error}",
                    "检查交易工作区、网关配置、策略脚本依赖和资产参数后可重试模拟。",
                    "如果启动问题来自策略脚本或交易环境假设，可从该记录继续投研。",
                ],
            }
        )
        return await self._persist_research_run_record(user_id, workspace, updated_record)

    async def _mark_run_record_paper_reviewed(
        self,
        user_id: str,
        record: AIStrategyResearchRunRecord,
        review: AIStrategyPaperTradingReview,
    ) -> WorkspaceResponse | None:
        workspace = await self.workspace_service.get_workspace(record.research_workspace_id, user_id)
        if workspace is None:
            return None
        updated_record = record.model_copy(
            update={
                "paper_review_status": review.status,
                "paper_review_ready_for_live": review.ready_for_live,
                "paper_reviewed_at": review.reviewed_at,
                "paper_review_evaluations": [
                    item.model_dump(mode="json") for item in review.evaluations
                ],
                "paper_review_next_actions": review.next_actions,
                "pipeline": review.pipeline,
            }
        )
        return await self._persist_research_run_record(user_id, workspace, updated_record)


def _coerce_unit_status(value: Any) -> UnitStatusResponse | None:
    if value is None:
        return None
    if isinstance(value, UnitStatusResponse):
        return value
    if isinstance(value, dict):
        return UnitStatusResponse.model_validate(value)
    return None


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
    params = {
        "symbol": request.symbol,
        "data_config": dict(request.data_config or {}),
    }
    for key, value in _existing_contract_metadata(request).items():
        if value:
            params[key] = value
    try:
        return resolve_asset_specs(
            {"params": params},
            Path(),
            gateway=request.gateway_config or None,
            symbols=symbols,
        )
    except Exception:
        return {}


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
                merged.update({
                    str(item_key): dict(item_value)
                    for item_key, item_value in value.items()
                    if isinstance(item_value, dict)
                })
                metadata[key] = merged
    return metadata


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
            "commission_rate",
            "open_commission_rate",
            "taker_commission_rate",
            "maker_commission_rate",
        )
        if commission is not None:
            unit_settings["commission"] = max(commission, 0.0)
    source = str(primary.get("source") or primary.get("fee_source") or "").strip()
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


def _research_run_records_from_workspace(
    workspace: WorkspaceResponse,
) -> list[AIStrategyResearchRunRecord]:
    settings = dict(workspace.settings or {})
    ai_research = settings.get("ai_research")
    if not isinstance(ai_research, dict):
        return []

    raw_runs = ai_research.get("runs")
    runs = raw_runs if isinstance(raw_runs, list) else []
    records: list[AIStrategyResearchRunRecord] = []
    seen: set[str] = set()
    for raw in runs:
        record = _coerce_research_run_record(raw)
        if record is None or record.run_id in seen:
            continue
        seen.add(record.run_id)
        records.append(record)

    if not records:
        record = _coerce_research_run_record(ai_research.get("last_run"))
        if record is not None:
            records.append(record)
    records.sort(key=lambda item: item.completed_at, reverse=True)
    return records


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
    if record.pipeline:
        return record
    return record.model_copy(update={"pipeline": _pipeline_summary_from_record(record)})


def _validate_strategy_code_draft(code: str) -> None:
    text = str(code or "").strip()
    if not text:
        raise ValueError("strategy code is empty")
    try:
        StrategySandbox._check_code_safety(text)
        tree = ast.parse(text, filename="<ai_strategy_draft>")
    except SyntaxError as exc:
        raise ValueError(f"strategy code syntax error: {exc}") from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"strategy code safety check failed: {exc}") from exc

    if not any(_is_backtrader_strategy_class(node) for node in ast.walk(tree)):
        raise ValueError("strategy code must define a class inheriting from bt.Strategy")


def _is_backtrader_strategy_class(node: ast.AST) -> bool:
    if not isinstance(node, ast.ClassDef):
        return False
    return any(_is_backtrader_strategy_base(base) for base in node.bases)


def _is_backtrader_strategy_base(base: ast.AST) -> bool:
    if isinstance(base, ast.Attribute) and base.attr == "Strategy":
        return _ast_name(base.value) in {"bt", "backtrader"}
    if isinstance(base, ast.Name):
        return base.id == "Strategy"
    return False


def _ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _quality_gate_failures(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    if sharpe is None:
        failures.append("Sharpe metric unavailable")
    elif sharpe < request.target_sharpe:
        failures.append(f"Sharpe {sharpe:.3f} below target {request.target_sharpe:.3f}")
    if total_trades < request.min_total_trades:
        failures.append(f"Only {total_trades} trades, below minimum {request.min_total_trades}")

    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        if max_drawdown is None:
            failures.append("Max drawdown metric unavailable")
        else:
            comparable = abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if comparable > abs(request.max_drawdown_limit):
                failures.append(
                    f"Max drawdown {comparable:.3f} exceeds limit "
                    f"{abs(request.max_drawdown_limit):.3f}"
                )

    if request.min_total_return is not None:
        total_return = _quality_metric(metrics, "total_return", "totalReturn", "return")
        if total_return is None:
            failures.append("Total return metric unavailable")
        else:
            comparable = _align_metric_scale(total_return, request.min_total_return)
            if comparable < request.min_total_return:
                failures.append(
                    f"Total return {comparable:.3f} below minimum "
                    f"{request.min_total_return:.3f}"
                )

    if request.min_annual_return is not None:
        annual_return = _quality_metric(metrics, "annual_return", "annualReturn")
        if annual_return is None:
            failures.append("Annual return metric unavailable")
        else:
            comparable = _align_metric_scale(annual_return, request.min_annual_return)
            if comparable < request.min_annual_return:
                failures.append(
                    f"Annual return {comparable:.3f} below minimum "
                    f"{request.min_annual_return:.3f}"
                )

    if request.min_win_rate is not None:
        win_rate = _quality_metric(metrics, "win_rate", "winRate")
        if win_rate is None:
            failures.append("Win rate metric unavailable")
        else:
            comparable = _align_metric_scale(win_rate, request.min_win_rate)
            if comparable < request.min_win_rate:
                failures.append(
                    f"Win rate {comparable:.3f} below minimum {request.min_win_rate:.3f}"
                )

    return failures


def _parse_iso_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _out_of_sample_window(request: AIStrategyResearchRunRequest) -> OutOfSampleWindow | None:
    if not request.out_of_sample_validation:
        return None
    start = _parse_iso_date(request.start_date)
    end = _parse_iso_date(request.end_date)
    if start is None or end is None or end <= start:
        return None
    total_days = (end - start).days + 1
    if total_days < 8:
        return None
    validation_days = max(int(total_days * request.out_of_sample_ratio), 1)
    validation_days = min(validation_days, total_days - 2)
    validation_start = end - timedelta(days=validation_days - 1)
    train_end = validation_start - timedelta(days=1)
    if train_end <= start or validation_start > end:
        return None
    return OutOfSampleWindow(
        train_start=start.isoformat(),
        train_end=train_end.isoformat(),
        validation_start=validation_start.isoformat(),
        validation_end=end.isoformat(),
    )


def _out_of_sample_min_sharpe(request: AIStrategyResearchRunRequest) -> float:
    if request.min_out_of_sample_sharpe is not None:
        return request.min_out_of_sample_sharpe
    return round(request.target_sharpe * 0.6, 6)


def _out_of_sample_min_trades(request: AIStrategyResearchRunRequest) -> int:
    if request.min_out_of_sample_trades is not None:
        return request.min_out_of_sample_trades
    if request.min_total_trades <= 0:
        return 0
    return max(1, int(round(request.min_total_trades * request.out_of_sample_ratio)))


def _out_of_sample_failures(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> list[str]:
    failures: list[str] = []
    if run_status != "completed":
        failures.append(f"Out-of-sample backtest finished with status {run_status or 'unknown'}")
        return failures

    min_sharpe = _out_of_sample_min_sharpe(request)
    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    if sharpe is None:
        failures.append("Out-of-sample Sharpe metric unavailable")
    elif sharpe < min_sharpe:
        failures.append(
            f"Out-of-sample Sharpe {sharpe:.3f} below minimum {min_sharpe:.3f}"
        )

    min_trades = _out_of_sample_min_trades(request)
    total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    if total_trades < min_trades:
        failures.append(
            f"Out-of-sample only {total_trades} trades, below minimum {min_trades}"
        )

    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        if max_drawdown is None:
            failures.append("Out-of-sample max drawdown metric unavailable")
        else:
            comparable = abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if comparable > abs(request.max_drawdown_limit):
                failures.append(
                    f"Out-of-sample max drawdown {comparable:.3f} exceeds limit "
                    f"{abs(request.max_drawdown_limit):.3f}"
                )

    return failures


def _out_of_sample_gate_evaluations(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> list[dict[str, Any]]:
    if run_status != "completed":
        return []
    evaluations = [
        _minimum_gate_evaluation(
            "out_of_sample_sharpe",
            "Out-of-sample Sharpe",
            _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio"),
            _out_of_sample_min_sharpe(request),
        ),
        _minimum_gate_evaluation(
            "out_of_sample_total_trades",
            "Out-of-sample total trades",
            float(_metric_int(metrics, "total_trades", "totalTrades", "trades")),
            float(_out_of_sample_min_trades(request)),
        ),
    ]
    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        comparable = (
            abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if max_drawdown is not None
            else None
        )
        evaluations.append(
            _maximum_gate_evaluation(
                "out_of_sample_max_drawdown",
                "Out-of-sample max drawdown",
                comparable,
                abs(request.max_drawdown_limit),
            )
        )
    return evaluations


def _improvement_metrics(
    metrics: dict[str, Any],
    validation_metrics: dict[str, Any],
) -> dict[str, Any]:
    if not validation_metrics:
        return metrics
    merged = dict(metrics)
    merged["out_of_sample"] = dict(validation_metrics)
    for source_key, target_key in (
        ("sharpe_ratio", "out_of_sample_sharpe"),
        ("total_trades", "out_of_sample_total_trades"),
        ("max_drawdown", "out_of_sample_max_drawdown"),
        ("total_return", "out_of_sample_total_return"),
    ):
        if source_key in validation_metrics:
            merged[target_key] = validation_metrics[source_key]
    return merged


def _is_better_research_candidate(
    candidate: AIStrategyResearchIteration,
    current: AIStrategyResearchIteration,
) -> bool:
    candidate_key = (
        1 if candidate.passed else 0,
        candidate.quality_score,
        candidate.sharpe_ratio,
        candidate.total_trades,
        -candidate.iteration,
    )
    current_key = (
        1 if current.passed else 0,
        current.quality_score,
        current.sharpe_ratio,
        current.total_trades,
        -current.iteration,
    )
    return candidate_key > current_key


def _quality_score(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> float:
    evaluations = _quality_gate_evaluations(request, metrics, run_status=run_status)
    if not evaluations:
        return 0.0
    return round(
        sum(float(item.get("score", 0.0) or 0.0) for item in evaluations)
        / len(evaluations)
        * 100,
        3,
    )


def _quality_gate_evaluations(
    request: AIStrategyResearchRunRequest,
    metrics: dict[str, Any],
    *,
    run_status: str | None,
) -> list[dict[str, Any]]:
    if run_status != "completed":
        return []

    evaluations: list[dict[str, Any]] = []
    sharpe = _quality_metric(metrics, "sharpe_ratio", "sharpe", "sharpeRatio")
    evaluations.append(
        _minimum_gate_evaluation("sharpe", "Sharpe", sharpe, request.target_sharpe)
    )

    total_trades = _metric_int(metrics, "total_trades", "totalTrades", "trades")
    evaluations.append(
        _minimum_gate_evaluation(
            "total_trades",
            "Total trades",
            float(total_trades),
            float(request.min_total_trades),
        )
    )

    if request.max_drawdown_limit is not None:
        max_drawdown = _quality_metric(
            metrics,
            "max_drawdown",
            "maxDrawdown",
            "drawdown",
            "max_dd",
            "maxDD",
        )
        comparable = (
            abs(_align_metric_scale(max_drawdown, request.max_drawdown_limit))
            if max_drawdown is not None
            else None
        )
        evaluations.append(
            _maximum_gate_evaluation(
                "max_drawdown",
                "Max drawdown",
                comparable,
                abs(request.max_drawdown_limit),
            )
        )

    if request.min_total_return is not None:
        total_return = _quality_metric(metrics, "total_return", "totalReturn", "return")
        comparable = (
            _align_metric_scale(total_return, request.min_total_return)
            if total_return is not None
            else None
        )
        evaluations.append(
            _minimum_gate_evaluation(
                "total_return",
                "Total return",
                comparable,
                request.min_total_return,
            )
        )

    if request.min_annual_return is not None:
        annual_return = _quality_metric(metrics, "annual_return", "annualReturn")
        comparable = (
            _align_metric_scale(annual_return, request.min_annual_return)
            if annual_return is not None
            else None
        )
        evaluations.append(
            _minimum_gate_evaluation(
                "annual_return",
                "Annual return",
                comparable,
                request.min_annual_return,
            )
        )

    if request.min_win_rate is not None:
        win_rate = _quality_metric(metrics, "win_rate", "winRate")
        comparable = (
            _align_metric_scale(win_rate, request.min_win_rate) if win_rate is not None else None
        )
        evaluations.append(
            _minimum_gate_evaluation(
                "win_rate",
                "Win rate",
                comparable,
                request.min_win_rate,
            )
        )

    return evaluations


def _minimum_gate_evaluation(
    key: str,
    label: str,
    actual: float | None,
    target: float,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "actual": actual,
        "target": target,
        "direction": "min",
        "passed": actual is not None and _minimum_gate_score(actual, target) >= 1.0,
        "score": _minimum_gate_score(actual, target),
    }


def _maximum_gate_evaluation(
    key: str,
    label: str,
    actual: float | None,
    target: float,
) -> dict[str, Any]:
    score = 0.0 if actual is None else 1.0 if actual <= target else max(min(target / actual, 1.0), 0.0)
    return {
        "key": key,
        "label": label,
        "actual": actual,
        "target": target,
        "direction": "max",
        "passed": actual is not None and actual <= target,
        "score": score,
    }


def _minimum_gate_score(value: float | None, threshold: float) -> float:
    if value is None:
        return 0.0
    if threshold <= 0:
        return 1.0 if value >= threshold else 0.0
    return max(min(value / threshold, 1.0), 0.0)


def _quality_gates_payload(request: AIStrategyResearchRunRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target_sharpe": request.target_sharpe,
        "min_total_trades": request.min_total_trades,
        "out_of_sample_validation": request.out_of_sample_validation,
        "out_of_sample_ratio": request.out_of_sample_ratio,
    }
    if request.out_of_sample_validation:
        payload["min_out_of_sample_sharpe"] = _out_of_sample_min_sharpe(request)
        payload["min_out_of_sample_trades"] = _out_of_sample_min_trades(request)
    for key in (
        "max_drawdown_limit",
        "min_total_return",
        "min_annual_return",
        "min_win_rate",
        "min_out_of_sample_sharpe",
        "min_out_of_sample_trades",
    ):
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    return payload


def _pipeline_summary_from_record(
    record: AIStrategyResearchRunRecord,
    *,
    paper_trading_started: bool | None = None,
    paper_trading_error: str | None = None,
    paper_review_status: str | None = None,
    paper_review_ready_for_live: bool | None = None,
) -> dict[str, Any]:
    return _pipeline_summary(
        status=record.status,
        achieved=record.achieved,
        iteration_count=record.iteration_count,
        max_iterations=record.max_iterations,
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
    )


def _pipeline_summary(
    *,
    status: str,
    achieved: bool,
    iteration_count: int,
    max_iterations: int,
    paper_trading_started: bool,
    paper_trading_error: str | None,
    paper_review_status: str | None,
    paper_review_ready_for_live: bool,
) -> dict[str, Any]:
    draft_status = "completed"
    backtest_status = "completed" if iteration_count > 0 else "pending"
    gate_status = "completed" if achieved else "failed" if iteration_count >= max_iterations else "running"
    paper_status = "completed" if paper_trading_started else "failed" if paper_trading_error else "pending"
    review_status = (
        "completed"
        if paper_review_ready_for_live
        else "failed"
        if paper_review_status == "needs_research_review"
        else "running"
        if paper_review_status
        else "pending"
    )

    steps = [
        {"key": "draft", "label": "策略生成", "status": draft_status},
        {
            "key": "backtest_loop",
            "label": "自动回测迭代",
            "status": backtest_status,
            "iteration_count": iteration_count,
            "max_iterations": max_iterations,
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
            "status": review_status,
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
    completed_count = sum(1 for item in steps if item["status"] == "completed")
    return {
        "current_stage": current_stage,
        "status": status,
        "progress": round(completed_count / len(steps) * 100, 2),
        "ready_for_live": paper_review_ready_for_live,
        "paper_trading_error": paper_trading_error,
        "steps": steps,
    }


def _pipeline_current_stage(
    *,
    achieved: bool,
    paper_trading_started: bool,
    paper_trading_error: str | None,
    paper_review_status: str | None,
    paper_review_ready_for_live: bool,
    status: str,
) -> str:
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
    return "research_iteration"


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


def _ensure_runnable_initial_draft(
    draft: AIStrategyDraft,
    request: AIStrategyResearchRunRequest,
) -> tuple[AIStrategyDraft, list[str]]:
    try:
        _validate_strategy_code_draft(draft.code)
        return draft, []
    except ValueError as exc:
        fallback = _normalize_research_draft(build_ai_strategy_draft(request.prompt), request)
        return fallback, [
            f"AI初始策略代码不可运行，已使用本地可运行草案继续投研：{exc}",
        ]


def _research_backtest_defaults(request: AIStrategyResearchRunRequest) -> AIStrategyBacktestSpec:
    commission = request.commission
    if not _request_has_explicit_commission(request):
        asset_specs = _resolve_research_asset_specs(request)
        primary = next((value for value in asset_specs.values() if isinstance(value, dict)), None)
        if primary:
            asset_commission = _first_asset_spec_number(
                primary,
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
    if record.iterations:
        return dict(record.iterations[0])
    return None


def _paper_start_request_from_record(
    record: AIStrategyResearchRunRecord,
    request: AIStrategyPaperTradingStartRequest,
) -> AIStrategyResearchRunRequest:
    gates = dict(record.quality_gates or {})
    return AIStrategyResearchRunRequest(
        prompt=record.prompt,
        symbol=record.symbol,
        symbol_name=record.symbol_name,
        timeframe=record.timeframe,
        timeframe_n=record.timeframe_n,
        start_date=record.start_date,
        end_date=record.end_date,
        initial_cash=record.initial_cash,
        commission=record.commission,
        annual_days=record.annual_days,
        calc_method=record.calc_method,
        weight_mode=record.weight_mode,
        knowledge_base_id=record.knowledge_base_id,
        thinking_mode=record.thinking_mode,
        target_sharpe=record.target_sharpe,
        min_total_trades=record.min_total_trades,
        max_drawdown_limit=_optional_gate_number(gates.get("max_drawdown_limit")),
        min_total_return=_optional_gate_number(gates.get("min_total_return")),
        min_annual_return=_optional_gate_number(gates.get("min_annual_return")),
        min_win_rate=_optional_gate_number(gates.get("min_win_rate")),
        out_of_sample_validation=bool(gates.get("out_of_sample_validation", True)),
        out_of_sample_ratio=float(gates.get("out_of_sample_ratio") or 0.25),
        min_out_of_sample_sharpe=_optional_gate_number(gates.get("min_out_of_sample_sharpe")),
        min_out_of_sample_trades=_optional_gate_int(gates.get("min_out_of_sample_trades")),
        max_iterations=max(int(record.max_iterations or 1), 1),
        research_workspace_id=record.research_workspace_id,
        trading_workspace_id=request.trading_workspace_id,
        seed_strategy_id=record.best_strategy_id,
        continue_from_run_id=record.run_id,
        start_paper_trading=True,
        paper_workspace_name=request.paper_workspace_name,
        gateway_config=request.gateway_config,
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
        quality_score=float(payload.get("quality_score") or record.best_quality_score or 0.0),
        quality_gate_evaluations=list(
            payload.get("quality_gate_evaluations")
            or record.best_quality_gate_evaluations
            or []
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
    failed_evaluations = [
        dict(item)
        for item in record.paper_review_evaluations
        if isinstance(item, dict) and str(item.get("status") or "") == "failed"
    ]
    if not failed_evaluations and record.paper_review_status != "needs_research_review":
        paper_trading_error = _paper_trading_start_failure_from_record(record)
        if not paper_trading_error:
            return {}
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
        }

    failures = [_paper_review_failure_text(item) for item in failed_evaluations]
    if not failures and record.paper_review_status:
        failures = [f"Paper review status {record.paper_review_status} requires research review"]
    metrics = dict(record.best_metrics or {})
    for item in failed_evaluations:
        metric = str(item.get("metric") or item.get("key") or "").strip()
        actual = _optional_gate_number(item.get("actual"))
        if metric and actual is not None:
            metrics[metric] = actual

    return {
        "source": "paper_review",
        "run_id": record.run_id,
        "paper_review_status": record.paper_review_status,
        "paper_reviewed_at": record.paper_reviewed_at,
        "quality_gate_failures": failures,
        "paper_review_evaluations": failed_evaluations,
        "paper_review_next_actions": list(record.paper_review_next_actions or []),
        "metrics": metrics,
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
    if action:
        detail = f"{detail}; action: {action}"
    return detail


def _continuation_quality_gate_failures(context: dict[str, Any]) -> list[str]:
    failures = context.get("quality_gate_failures") if isinstance(context, dict) else None
    if not isinstance(failures, list):
        return []
    return [str(item).strip() for item in failures if str(item or "").strip()]


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
    best_strategy = response.best_strategy
    paper = response.paper_trading
    return AIStrategyResearchRunRecord(
        run_id=run_id,
        prompt=request.prompt,
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
        knowledge_base_id=request.knowledge_base_id,
        thinking_mode=request.thinking_mode,
        status=response.status,
        achieved=response.achieved,
        target_sharpe=response.target_sharpe,
        quality_gates=_quality_gates_payload(request),
        min_total_trades=request.min_total_trades,
        max_iterations=request.max_iterations,
        iteration_count=len(response.iterations),
        best_iteration=response.best_iteration,
        best_sharpe=best_iteration.sharpe_ratio
        if best_iteration is not None
        else _metric_float(response.best_metrics, "sharpe_ratio", "sharpe", "sharpeRatio"),
        best_quality_score=best_iteration.quality_score if best_iteration is not None else 0.0,
        best_quality_gate_evaluations=best_iteration.quality_gate_evaluations
        if best_iteration is not None
        else [],
        best_diagnostics=best_iteration.diagnostics if best_iteration is not None else {},
        best_metrics=response.best_metrics,
        best_strategy_id=best_strategy.id if best_strategy else None,
        best_strategy_name=best_strategy.name if best_strategy else None,
        research_workspace_id=response.research_workspace.id,
        seed_strategy_id=request.seed_strategy_id,
        continued_from_run_id=request.continue_from_run_id,
        paper_workspace_id=paper.workspace.id if paper else None,
        paper_unit_id=paper.unit.id if paper else None,
        paper_trading_started=bool(paper.started) if paper else False,
        paper_monitoring_plan=response.paper_monitoring_plan,
        paper_handoff=dict(paper.handoff or {}) if paper else {},
        pipeline=response.pipeline,
        next_actions=response.next_actions,
        started_at=started_at,
        completed_at=completed_at,
        iterations=[_compact_research_iteration(item) for item in response.iterations],
    )


def _build_paper_trading_handoff(
    *,
    run_id: str,
    research_workspace_id: str,
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
    promoted_at: str,
) -> dict[str, Any]:
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
        "achieved_sharpe": best_iteration.sharpe_ratio,
        "achieved_quality_score": best_iteration.quality_score,
        "achieved_quality_gate_evaluations": best_iteration.quality_gate_evaluations,
        "achieved_diagnostics": best_iteration.diagnostics,
        "total_trades": best_iteration.total_trades,
        "best_metrics": best_iteration.metrics,
        "backtest_environment": _paper_backtest_environment(request, best_iteration),
        "out_of_sample_validation": {
            "status": best_iteration.validation_status,
            "window": best_iteration.validation_window,
            "metrics": best_iteration.validation_metrics,
            "gate_evaluations": best_iteration.validation_gate_evaluations,
            "failures": best_iteration.validation_failures,
            "failure_reason": best_iteration.validation_failure_reason,
        },
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
        "unit_id": item.unit.id,
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


def _iteration_diagnostics(
    request: AIStrategyResearchRunRequest,
    *,
    iteration: int,
    metrics: dict[str, Any],
    run_status: str | None,
    quality_gate_failures: list[str],
    quality_gate_evaluations: list[dict[str, Any]],
    failure_reason: str | None,
) -> dict[str, Any]:
    metric_snapshot = _research_metric_snapshot(metrics, request)
    failure_categories = _failure_categories(quality_gate_failures, run_status, failure_reason)
    strengths = _gate_strengths(quality_gate_evaluations)
    weaknesses = _gate_weaknesses(quality_gate_evaluations, quality_gate_failures, failure_reason)
    improvement_plan = _improvement_plan_from_failures(
        request,
        metrics=metrics,
        run_status=run_status,
        quality_gate_failures=quality_gate_failures,
        failure_categories=failure_categories,
    )
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
        "improvement_plan": improvement_plan,
        "promotion_ready": passed,
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
        if _is_paper_trading_start_failure(failure):
            categories.append("paper_trading_start")
        elif "sharpe" in lowered:
            categories.append("sharpe")
        elif "trade" in lowered or "trades" in lowered or "交易" in failure:
            categories.append("trade_count")
        elif "drawdown" in lowered or "回撤" in failure:
            categories.append("drawdown")
        elif "annual" in lowered or "年化" in failure:
            categories.append("annual_return")
        elif "return" in lowered or "收益" in failure:
            categories.append("total_return")
        elif "win rate" in lowered or "胜率" in failure:
            categories.append("win_rate")
        elif "cost" in lowered or "slippage" in lowered or "费用" in failure or "滑点" in failure:
            categories.append("execution_cost")
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
        strengths.append(f"{label} 已达标：{_format_gate_value(actual)} / {_format_gate_value(target)}")
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
) -> list[str]:
    if run_status == "completed" and not quality_gate_failures:
        return [
            "冻结当前策略版本作为候选，不再自动改稿。",
            "进入模拟交易后优先验证成交、滑点、费用和样本外收益稳定性。",
        ]

    plan: list[str] = []
    categories = set(failure_categories)
    if "backtest_runtime" in categories:
        plan.append("先修复策略运行错误、数据源缺口或超时问题，再继续生成下一版。")
    if "paper_trading_start" in categories:
        plan.append("优先复核模拟交易单元创建、网关配置、策略脚本依赖和资产参数后再重试。")
    if "trade_count" in categories:
        plan.append("放宽入场过滤、缩短慢速指标窗口或降低确认条件，优先提高有效交易样本数。")
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
    return [
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
            "threshold": max(int(request.min_total_trades), 1),
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


def _paper_effective_commission(
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
) -> float:
    unit_settings = dict(best_iteration.unit.unit_settings or {})
    return _runtime_float(unit_settings.get("commission"), request.commission)


def _paper_backtest_environment(
    request: AIStrategyResearchRunRequest,
    best_iteration: AIStrategyResearchIteration,
) -> dict[str, Any]:
    unit_settings = dict(best_iteration.unit.unit_settings or {})
    data_config = dict(best_iteration.unit.data_config or {})
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
    observed = _quality_metric(metrics, "max_drawdown", "maxDrawdown", "drawdown", "max_dd", "maxDD")
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
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
) -> list[AIStrategyPaperTradingRuleEvaluation]:
    evaluations: list[AIStrategyPaperTradingRuleEvaluation] = []
    for raw_rule in monitoring_plan:
        metric = str(raw_rule.get("metric") or "").strip()
        threshold = _optional_gate_number(raw_rule.get("threshold"))
        if not metric or threshold is None:
            continue
        actual, source = _lookup_paper_metric(metric, unit=unit, unit_status=unit_status)
        direction = str(raw_rule.get("direction") or "min").strip().lower()
        passed = _paper_rule_passed(actual, threshold, direction)
        status = "pending" if actual is None else "passed" if passed else "failed"
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
                action=str(raw_rule.get("action") or ""),
            )
        )
    return evaluations


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


def _lookup_paper_metric(
    metric: str,
    *,
    unit: StrategyUnitResponse | None,
    unit_status: UnitStatusResponse | None,
) -> tuple[float | None, str | None]:
    if metric == "valuation_confidence":
        return _lookup_paper_valuation_confidence(unit=unit, unit_status=unit_status)

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
    return None, None


def _lookup_paper_valuation_confidence(
    *,
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
        if status in {"estimated", "stale_fallback", "unknown"}:
            return 0.0, source_name

        row_statuses = _paper_position_row_statuses(payload)
        if row_statuses:
            if row_statuses <= {"confirmed", "gateway_confirmed"}:
                return 1.0, f"{source_name}.positions"
            if row_statuses & {"estimated", "stale_fallback", "unknown"}:
                return 0.0, f"{source_name}.positions"

    if unit is not None:
        source = _unit_contract_metadata_source(unit)
        if source:
            return 1.0, source

    return None, None


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
            if isinstance(metadata, dict) and _contract_metadata_has_asset_specs(metadata):
                return f"{source_name}.{key}"
    return None


def _contract_metadata_has_asset_specs(metadata: dict[str, Any]) -> bool:
    for value in metadata.values():
        if not isinstance(value, dict):
            continue
        if any(
            value.get(key) not in (None, "")
            for key in (
                "multiplier",
                "contract_multiplier",
                "contract_size",
                "margin_rate",
                "commission_rate",
                "open_commission_rate",
                "close_commission_rate",
                "commission_amount",
                "source",
            )
        ):
            return True
    return False


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
) -> list[str]:
    if status == "paper_not_started":
        return ["该投研结果尚未启动模拟交易，先从历史记录发起 paper 运行。"]
    if status == "paper_workspace_missing":
        return ["未找到模拟交易工作区，检查 handoff 记录或重新启动模拟交易。"]
    if status == "paper_unit_missing":
        return ["未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。"]
    if status == "monitoring_plan_missing" or not monitoring_plan:
        return ["缺少模拟交易监控计划，重新保存投研 run record 或用当前最佳策略重启 paper。"]
    if status == "ready_for_live_candidate":
        return [
            "模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。",
            "实盘前仍需确认账户权限、合约乘数、手续费、滑点和最大风险预算。",
        ]

    failed = [item for item in evaluations if item.status == "failed"]
    if failed:
        return list(dict.fromkeys([item.action for item in failed if item.action]))

    pending = [item.label for item in evaluations if item.status == "pending"]
    if pending:
        return [
            "继续收集模拟交易数据，等待以下指标形成有效样本：" + "、".join(pending),
        ]
    return ["继续观察模拟交易表现，并定期回到投研记录复核监控指标。"]


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
) -> list[str]:
    if status == "timeout":
        return [
            "回测等待超时，先打开研究工作区查看任务是否仍在运行。",
            "如数据量较大，可提高 backtest_timeout_seconds 后继续投研。",
        ]

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
    return actions


def _build_research_draft_prompt(request: AIStrategyResearchRunRequest) -> str:
    """Add research-loop constraints to the initial draft prompt."""

    asset_specs = _resolve_research_asset_specs(request)
    context: dict[str, Any] = {
        "objective": request.prompt,
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
        "backtest_environment": {
            "initial_cash": request.initial_cash,
            "commission": request.commission,
            "commission_source": "user_override"
            if _request_has_explicit_commission(request)
            else "asset_specs_or_default",
            "annual_days": request.annual_days,
            "calc_method": request.calc_method,
            "weight_mode": request.weight_mode,
        },
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
        "基于失败原因继续改进，并在达标后进入模拟交易。"
    )


def _summarize_asset_specs_for_prompt(
    asset_specs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    keys = (
        "symbol",
        "exchange",
        "product",
        "multiplier",
        "contract_multiplier",
        "contract_size",
        "margin_rate",
        "margin",
        "long_margin_rate",
        "short_margin_rate",
        "commission_rate",
        "open_commission_rate",
        "close_commission_rate",
        "close_today_commission_rate",
        "commission_amount",
        "source",
        "fee_source",
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
    return [
        {
            "role": "system",
            "content": (
                "你是 AI for Trader 的量化策略研究员。你只输出 JSON，不输出 Markdown。"
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
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "iteration_to_create": iteration + 1,
                    "target_sharpe": target_sharpe,
                    "quality_gates": _quality_gates_payload(request) if request else {},
                    "quality_gate_failures": failures,
                    "continuation_context": dict(request.continuation_context or {})
                    if request is not None
                    else {},
                    "previous_metrics": metrics,
                    "suggested_improvement_plan": _improvement_plan_from_failures(
                        request,
                        metrics=metrics,
                        run_status="completed",
                        quality_gate_failures=failures,
                        failure_categories=_failure_categories(failures, "completed", None),
                    )
                    if request is not None
                    else [],
                    "current_draft": draft.model_dump(mode="json"),
                    "rules": [
                        "不要删除风控逻辑；如果调整参数，请同步 params 和 code 中 params 默认值。",
                        "如果新增指标或状态变量，必须保证 Backtrader Strategy 类可独立运行。",
                        "优先执行 suggested_improvement_plan 中的具体改进方向。",
                        "优先针对 quality_gate_failures 中列出的失败原因改进策略。",
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

    params = _coerce_param_specs(payload.get("params"))
    if params:
        improved.params = params
        improved.code = _rewrite_code_param_defaults(improved.code, improved.params)

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
    return StrategyImprovement(draft=improved, notes=notes)


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


def _bounded_name(value: str, max_length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_length:
        return text or "AI策略投研"
    return text[: max_length - 1].rstrip() + "…"
