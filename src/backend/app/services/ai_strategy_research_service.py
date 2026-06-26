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
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.schemas.ai_strategy_research import (
    AIStrategyPaperTradingStart,
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
from app.services.strategy.inference import render_param_default
from app.services.strategy_service import StrategyService
from app.services.workspace_service import WorkspaceService
from app.utils.sandbox import StrategySandbox

_TERMINAL_UNIT_STATUSES = {"completed", "failed", "cancelled", "timeout"}


@dataclass(frozen=True)
class StrategyImprovement:
    draft: AIStrategyDraft
    notes: list[str]


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
    ) -> AIStrategyResearchRunResponse:
        run_id = str(uuid.uuid4())
        started_at = _utc_iso_now()
        request, draft = await self._prepare_initial_draft(user_id, request)
        research_workspace = await self._ensure_research_workspace(user_id, request)
        if draft is None:
            draft_response = await self.strategy_service.generate_copilot_draft(
                user_id,
                StrategyCopilotDraftRequest(
                    prompt=request.prompt,
                    knowledge_base_id=request.knowledge_base_id,
                    thinking_mode=request.thinking_mode,
                ),
            )
            draft = draft_response.strategy_draft

        iterations: list[AIStrategyResearchIteration] = []
        best_iteration: AIStrategyResearchIteration | None = None
        selected_iteration: AIStrategyResearchIteration | None = None
        pending_improvement_notes: list[str] = []
        achieved = False

        for iteration in range(1, request.max_iterations + 1):
            try:
                _validate_strategy_code_draft(draft.code)
            except ValueError as exc:
                raise ValueError(
                    f"Generated strategy code validation failed before iteration {iteration}: {exc}"
                ) from exc
            backtest_request = self._build_backtest_request(draft, request)
            backtest_response = await self.strategy_service.backtest_copilot_draft(
                user_id,
                research_workspace.id,
                backtest_request,
            )
            if backtest_response is None:
                raise ValueError("Research workspace or generated strategy was not found")

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
            if not failure_reason and unit_status is not None and unit_status.run_status != "completed":
                failure_reason = f"Backtest finished with status {unit_status.run_status}"
            if not failure_reason and quality_gate_failures:
                failure_reason = "; ".join(quality_gate_failures)

            item = AIStrategyResearchIteration(
                iteration=iteration,
                strategy=backtest_response.strategy,
                unit=backtest_response.unit,
                run_result=backtest_response.run_result,
                unit_status=unit_status,
                metrics=metrics,
                sharpe_ratio=sharpe,
                total_trades=total_trades,
                passed=passed,
                failure_reason=None if passed else failure_reason,
                quality_gate_failures=quality_gate_failures,
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
            if best_iteration is None or item.sharpe_ratio > best_iteration.sharpe_ratio:
                best_iteration = item
            if passed:
                achieved = True
                selected_iteration = item
                break

            if iteration < request.max_iterations:
                improvement = await self.improver.improve(
                    draft,
                    iteration=iteration,
                    metrics=metrics,
                    target_sharpe=request.target_sharpe,
                    quality_gate_failures=quality_gate_failures,
                    user_id=user_id,
                    request=request,
                )
                draft = improvement.draft
                pending_improvement_notes = improvement.notes

        paper_trading = None
        result_iteration = selected_iteration or best_iteration
        if achieved and request.start_paper_trading and result_iteration is not None:
            paper_trading = await self._start_paper_trading(
                user_id,
                request,
                result_iteration,
                run_id=run_id,
                research_workspace_id=research_workspace.id,
            )

        status = "achieved" if achieved else "max_iterations_reached"
        if iterations and iterations[-1].unit_status and iterations[-1].unit_status.run_status == "timeout":
            status = "timeout"
        best_metrics = dict(result_iteration.metrics) if result_iteration else {}
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
        )
        response = AIStrategyResearchRunResponse(
            run_id=run_id,
            status=status,
            achieved=achieved,
            target_sharpe=request.target_sharpe,
            started_at=started_at,
            completed_at=completed_at,
            best_iteration=result_iteration.iteration if result_iteration else None,
            best_metrics=best_metrics,
            research_workspace=research_workspace,
            iterations=iterations,
            best_strategy=result_iteration.strategy if result_iteration else None,
            paper_trading=paper_trading,
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
    ) -> StrategyCopilotBacktestRequest:
        data_config = {
            **request.data_config,
            "symbol": request.symbol,
            "symbol_name": request.symbol_name or request.symbol,
            "timeframe": request.timeframe,
            "timeframe_n": request.timeframe_n,
        }
        if request.start_date:
            data_config["start_date"] = request.start_date
        if request.end_date:
            data_config["end_date"] = request.end_date

        unit_settings = {
            **request.unit_settings,
            "initial_cash": request.initial_cash,
            "commission": request.commission,
            "annual_days": request.annual_days,
            "calc_method": request.calc_method,
            "weight_mode": request.weight_mode,
        }

        return StrategyCopilotBacktestRequest(
            strategy_draft=draft,
            symbol=request.symbol,
            symbol_name=request.symbol_name or request.symbol,
            timeframe=request.timeframe,
            timeframe_n=request.timeframe_n,
            group_name=request.group_name or draft.execution_plan.group_name or draft.name,
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


def _coerce_unit_status(value: Any) -> UnitStatusResponse | None:
    if value is None:
        return None
    if isinstance(value, UnitStatusResponse):
        return value
    if isinstance(value, dict):
        return UnitStatusResponse.model_validate(value)
    return None


def _find_unit_status(items: list[Any], unit_id: str) -> UnitStatusResponse | None:
    for item in items:
        status = _coerce_unit_status(item)
        if status is not None and status.id == unit_id:
            return status
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
        return value
    if not isinstance(value, dict):
        return None
    try:
        return AIStrategyResearchRunRecord.model_validate(value)
    except Exception:
        return None


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


def _quality_gates_payload(request: AIStrategyResearchRunRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "target_sharpe": request.target_sharpe,
        "min_total_trades": request.min_total_trades,
    }
    for key in (
        "max_drawdown_limit",
        "min_total_return",
        "min_annual_return",
        "min_win_rate",
    ):
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    return payload


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
    best_strategy = response.best_strategy
    paper = response.paper_trading
    return AIStrategyResearchRunRecord(
        run_id=run_id,
        prompt=request.prompt,
        symbol=request.symbol,
        symbol_name=request.symbol_name or request.symbol,
        timeframe=request.timeframe,
        timeframe_n=request.timeframe_n,
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
        best_metrics=response.best_metrics,
        best_strategy_id=best_strategy.id if best_strategy else None,
        best_strategy_name=best_strategy.name if best_strategy else None,
        research_workspace_id=response.research_workspace.id,
        seed_strategy_id=request.seed_strategy_id,
        continued_from_run_id=request.continue_from_run_id,
        paper_workspace_id=paper.workspace.id if paper else None,
        paper_unit_id=paper.unit.id if paper else None,
        paper_trading_started=bool(paper.started) if paper else False,
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
        "total_trades": best_iteration.total_trades,
        "best_metrics": best_iteration.metrics,
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
        "passed": item.passed,
        "failure_reason": item.failure_reason,
        "quality_gate_failures": item.quality_gate_failures,
        "improvement_notes": item.improvement_notes,
        "next_actions": item.next_actions,
    }


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
        elif "trade" in lowered or "trades" in lowered or "交易" in failure:
            actions.append("放宽入场过滤或缩短信号窗口，先保证样本内有足够交易次数。")
        elif "drawdown" in lowered or "回撤" in failure:
            actions.append("收紧止损、单笔风险和仓位暴露，优先压低最大回撤。")
        elif "return" in lowered or "收益" in failure:
            actions.append("优化出场和持仓周期，提升总收益或年化收益。")
        elif "win rate" in lowered or "胜率" in failure:
            actions.append("增加趋势/波动过滤，减少低质量信号以提升胜率。")

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
            return [
                "策略已通过验收，但模拟交易未成功启动，先检查交易工作区和网关配置。",
                "修复启动问题后，可从本次最佳策略手动创建模拟交易单元。",
            ]
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
                    "previous_metrics": metrics,
                    "current_draft": draft.model_dump(mode="json"),
                    "rules": [
                        "不要删除风控逻辑；如果调整参数，请同步 params 和 code 中 params 默认值。",
                        "如果新增指标或状态变量，必须保证 Backtrader Strategy 类可独立运行。",
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
