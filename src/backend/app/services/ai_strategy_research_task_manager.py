"""Async task manager for long-running AI strategy research loops."""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.schemas.ai_strategy_research import (
    AIStrategyLiveHandoffApprovalRecord,
    AIStrategyLiveHandoffPackage,
    AIStrategyResearchRunRequest,
    AIStrategyResearchRunResponse,
    AIStrategyResearchTaskResponse,
)

_CANCEL_CLEANUP_TIMEOUT_SECONDS = 1.0
_DEFAULT_MAX_TERMINAL_TASKS_PER_USER = 50
_TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
_SENSITIVE_REQUEST_KEYS = (
    "api_key",
    "apikey",
    "access_key",
    "password",
    "passphrase",
    "auth_code",
    "credential",
    "secret",
    "token",
    "authorization",
)
_SENSITIVE_REQUEST_OMITTED = object()


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _ResearchTaskState:
    user_id: str
    response: AIStrategyResearchTaskResponse
    background_task: asyncio.Task[None] | None = None


class AIStrategyResearchTaskManager:
    """Track in-process AI research loop tasks for API polling."""

    def __init__(
        self,
        *,
        backtest_service_factory: Callable[[], Any] | None = None,
        max_terminal_tasks_per_user: int = _DEFAULT_MAX_TERMINAL_TASKS_PER_USER,
    ) -> None:
        self._tasks: dict[str, _ResearchTaskState] = {}
        self._lock = asyncio.Lock()
        self._backtest_service_factory = backtest_service_factory
        self._max_terminal_tasks_per_user = max(int(max_terminal_tasks_per_user), 0)

    async def submit(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        service: Any | None = None,
    ) -> AIStrategyResearchTaskResponse:
        task_id = str(uuid.uuid4())
        runtime_updates = _research_request_runtime_task_updates(request)
        response = AIStrategyResearchTaskResponse(
            task_id=task_id,
            status="pending",
            submitted_at=_utc_iso_now(),
            request_snapshot=_research_request_snapshot(request),
            current_stage="queued",
            progress=0.0,
            max_iterations=request.max_iterations,
            message="AI research task submitted",
            **runtime_updates,
        )
        async with self._lock:
            self._tasks[task_id] = _ResearchTaskState(user_id=user_id, response=response)

        loop = asyncio.get_running_loop()
        background_task = loop.create_task(
            self._run_task(
                task_id,
                user_id,
                request,
                service=service,
                runtime_updates=runtime_updates,
            )
        )
        background_task.add_done_callback(
            lambda _: loop.create_task(self._prune_terminal_tasks(user_id))
        )
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is not None:
                state.background_task = background_task
        return response

    async def get_task(
        self,
        user_id: str,
        task_id: str,
    ) -> AIStrategyResearchTaskResponse | None:
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None or state.user_id != user_id:
                return None
            return _freshened_task_response_for_read(state.response.model_copy(deep=True))

    async def list_tasks(
        self,
        user_id: str,
        *,
        active_only: bool = False,
        limit: int = 20,
    ) -> list[AIStrategyResearchTaskResponse]:
        async with self._lock:
            items = [
                _freshened_task_response_for_read(state.response.model_copy(deep=True))
                for state in self._tasks.values()
                if state.user_id == user_id
                and (not active_only or state.response.status not in _TERMINAL_TASK_STATUSES)
            ]
        items.sort(key=lambda item: item.submitted_at, reverse=True)
        return items[: max(limit, 0)]

    async def cancel_task(
        self,
        user_id: str,
        task_id: str,
    ) -> AIStrategyResearchTaskResponse | None:
        background_task: asyncio.Task[None] | None = None
        child_task_id: str | None = None
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None or state.user_id != user_id:
                return None
            if state.response.status in _TERMINAL_TASK_STATUSES:
                return state.response.model_copy(deep=True)
            background_task = state.background_task
            child_task_id = state.response.current_backtest_task_id
            state.response = state.response.model_copy(
                update={
                    "status": "cancelled",
                    "completed_at": _utc_iso_now(),
                    "current_stage": "cancelled",
                    "message": "AI research task cancelled",
                }
            )
            response = state.response.model_copy(deep=True)
        child_cancelled = False
        if child_task_id:
            child_cancelled = await self._cancel_child_backtest(child_task_id, user_id)
            await self._update_task(
                task_id,
                cancelled_backtest_task_id=child_task_id,
                child_cancelled=child_cancelled,
            )
        if background_task is not None and not background_task.done():
            background_task.cancel()
            await self._wait_for_cancel_cleanup(background_task)
        latest = await self.get_task(user_id, task_id)
        return latest or response

    async def _run_task(
        self,
        task_id: str,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        service: Any | None,
        runtime_updates: dict[str, Any],
    ) -> None:
        await self._update_task(
            task_id,
            status="running",
            **_research_progress_task_updates(
                {
                    "started_at": _utc_iso_now(),
                    "current_stage": "starting",
                    "progress": 1.0,
                    "max_iterations": request.max_iterations,
                    "message": "AI research task is running",
                },
                request,
                runtime_updates=runtime_updates,
            ),
        )
        try:
            runner = service
            if runner is None:
                from app.services.ai_strategy_research_service import AIStrategyResearchService

                runner = AIStrategyResearchService()

            async def progress_callback(payload: dict[str, Any]) -> None:
                await self._update_task(
                    task_id,
                    status="running",
                    **_research_progress_task_updates(
                        payload,
                        request,
                        runtime_updates=runtime_updates,
                    ),
                )

            if _runner_accepts_progress_callback(runner):
                result = await runner.run(
                    user_id,
                    request,
                    progress_callback=progress_callback,
                )
            else:
                result = await runner.run(user_id, request)
            result = _freshened_research_result_for_task(result)

            latest_iteration = (
                result.iterations[-1].model_dump(mode="json") if result.iterations else None
            )
            paper_updates = _research_result_task_updates(result)
            task_result = _redacted_research_result_for_task(result)
            await self._update_task(
                task_id,
                status="completed",
                completed_at=_utc_iso_now(),
                run_id=result.run_id,
                research_workspace_id=result.research_workspace.id,
                current_stage=str((result.pipeline or {}).get("current_stage") or "completed"),
                progress=100.0,
                iteration_count=len(result.iterations),
                max_iterations=request.max_iterations,
                latest_iteration=latest_iteration,
                current_backtest_task_id=None,
                result=task_result,
                message=result.message,
                **paper_updates,
            )
        except asyncio.CancelledError:
            await self._update_task(
                task_id,
                status="cancelled",
                completed_at=_utc_iso_now(),
                current_stage="cancelled",
                message="AI research task cancelled",
            )
        except Exception as exc:
            await self._update_task(
                task_id,
                status="failed",
                completed_at=_utc_iso_now(),
                current_stage="failed",
                error=str(exc),
                message="AI research task failed",
            )

    async def _update_task(self, task_id: str, **updates: Any) -> None:
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                return
            new_status = updates.get("status")
            if (
                state.response.status in _TERMINAL_TASK_STATUSES
                and new_status is not None
                and new_status != state.response.status
            ):
                return
            state.response = state.response.model_copy(update=updates)
            self._prune_terminal_tasks_locked(state.user_id)

    async def _cancel_child_backtest(self, task_id: str, user_id: str) -> bool:
        try:
            service = self._backtest_service_factory() if self._backtest_service_factory else None
            if service is None:
                from app.services.backtest.service import BacktestService

                service = BacktestService()
            return bool(await service.cancel_task(task_id, user_id))
        except Exception:
            return False

    async def _wait_for_cancel_cleanup(
        self,
        background_task: asyncio.Task[None],
    ) -> None:
        try:
            await asyncio.wait_for(
                asyncio.shield(background_task),
                timeout=_CANCEL_CLEANUP_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise
            return
        except (asyncio.TimeoutError, Exception):
            return

    async def _prune_terminal_tasks(self, user_id: str) -> None:
        async with self._lock:
            self._prune_terminal_tasks_locked(user_id)

    def _prune_terminal_tasks_locked(self, user_id: str) -> None:
        terminal_items: list[tuple[str, str]] = []
        for task_id, state in self._tasks.items():
            if state.user_id != user_id:
                continue
            if state.response.status not in _TERMINAL_TASK_STATUSES:
                continue
            background_task = state.background_task
            if background_task is not None and not background_task.done():
                continue
            terminal_items.append((state.response.submitted_at, task_id))

        if len(terminal_items) <= self._max_terminal_tasks_per_user:
            return

        terminal_items.sort(reverse=True)
        for _, task_id in terminal_items[self._max_terminal_tasks_per_user:]:
            self._tasks.pop(task_id, None)


_manager: AIStrategyResearchTaskManager | None = None


def get_ai_strategy_research_task_manager() -> AIStrategyResearchTaskManager:
    global _manager
    if _manager is None:
        _manager = AIStrategyResearchTaskManager()
    return _manager


def _runner_accepts_progress_callback(runner: Any) -> bool:
    try:
        signature = inspect.signature(runner.run)
    except (TypeError, ValueError):
        return False
    return any(
        name == "progress_callback" or param.kind == inspect.Parameter.VAR_KEYWORD
        for name, param in signature.parameters.items()
    )


def _research_progress_task_updates(
    payload: dict[str, Any],
    request: AIStrategyResearchRunRequest,
    *,
    runtime_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updates = dict(payload)
    for key, value in (runtime_updates or {}).items():
        if isinstance(updates.get(key), dict) and updates[key]:
            continue
        if isinstance(value, dict) and value:
            updates[key] = dict(value)
    if not isinstance(updates.get("pipeline"), dict):
        updates["pipeline"] = _research_progress_pipeline(updates, request)
    return updates


def _research_request_runtime_task_updates(
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    try:
        from app.services.ai_strategy_research_service import (
            _request_backtest_environment,
            _resolve_research_asset_specs,
            _summarize_asset_specs_for_prompt,
        )

        asset_specs = _resolve_research_asset_specs(request)
        backtest_environment = _request_backtest_environment(request, asset_specs)
        updates: dict[str, Any] = {}
        if asset_specs:
            updates["asset_specs"] = _summarize_asset_specs_for_prompt(asset_specs)
        if backtest_environment:
            updates["backtest_environment"] = backtest_environment
        return updates
    except Exception:
        return {
            "backtest_environment": {
                "initial_cash": request.initial_cash,
                "commission": request.commission,
                "commission_source": "request_default",
                "annual_days": request.annual_days,
                "calc_method": request.calc_method,
                "weight_mode": request.weight_mode,
                **({"start_date": request.start_date} if request.start_date else {}),
                **({"end_date": request.end_date} if request.end_date else {}),
            }
        }


def _research_progress_pipeline(
    payload: dict[str, Any],
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    stage = str(payload.get("current_stage") or "running")
    progress = _optional_float(payload.get("progress")) or 0.0
    iteration_count = _optional_int(payload.get("iteration_count")) or 0
    current_iteration = _optional_int(payload.get("current_iteration"))
    max_iterations = _optional_int(payload.get("max_iterations")) or request.max_iterations
    paper_trading_error = _paper_trading_error_from_progress(payload)
    steps = [
        {"key": "draft", "label": "策略生成", "status": _draft_step_status(stage)},
        {
            "key": "backtest_loop",
            "label": "自动回测迭代",
            "status": _backtest_step_status(stage),
            "iteration_count": iteration_count,
            "current_iteration": current_iteration,
            "max_iterations": max_iterations,
        },
        {"key": "quality_gate", "label": "质量门槛", "status": _quality_step_status(stage)},
        {
            "key": "paper_trading",
            "label": "模拟交易",
            "status": _paper_step_status(stage),
            "error": paper_trading_error,
        },
        {"key": "paper_review", "label": "模拟复核", "status": _review_step_status(stage)},
        {"key": "live_handoff", "label": "实盘交接", "status": _live_handoff_step_status(stage)},
        {
            "key": "live_trading_prepare",
            "label": "实盘准备",
            "status": _live_prepare_step_status(stage),
        },
    ]
    return {
        "current_stage": stage,
        "status": "running",
        "progress": progress,
        "paper_trading_error": paper_trading_error,
        "steps": steps,
    }


def _draft_step_status(stage: str) -> str:
    if stage in {"draft_generation_failed"}:
        return "failed"
    if stage in {"drafting", "repairing_code"}:
        return "running"
    if stage in {"queued", "starting", "initializing", "workspace_ready"}:
        return "pending"
    return "completed"


def _backtest_step_status(stage: str) -> str:
    if stage in {"backtest_submission_failed", "backtest_failed", "backtest_timeout"}:
        return "failed"
    if stage in {"backtesting", "validating", "evaluating", "improving"}:
        return "running"
    if stage in {
        "quality_achieved",
        "paper_trading",
        "paper_trading_failed",
        "paper_review",
        "live_candidate",
        "live_handoff",
        "live_trading_prepare",
        "completed",
    }:
        return "completed"
    return "pending"


def _quality_step_status(stage: str) -> str:
    if stage in {
        "quality_achieved",
        "paper_trading",
        "paper_review",
        "live_candidate",
        "live_handoff",
        "live_trading_prepare",
        "completed",
    }:
        return "completed"
    if stage in {"backtest_submission_failed", "backtest_failed", "backtest_timeout"}:
        return "failed"
    if stage in {"backtesting", "validating", "evaluating", "improving"}:
        return "running"
    return "pending"


def _paper_step_status(stage: str) -> str:
    if stage == "paper_trading_failed":
        return "failed"
    if stage == "paper_trading":
        return "running"
    if stage in {
        "paper_review",
        "live_candidate",
        "live_handoff",
        "live_trading_prepare",
        "completed",
    }:
        return "completed"
    return "pending"


def _review_step_status(stage: str) -> str:
    if stage == "paper_review":
        return "running"
    if stage in {"live_candidate", "live_handoff", "live_trading_prepare"}:
        return "completed"
    return "pending"


def _live_handoff_step_status(stage: str) -> str:
    if stage == "live_handoff":
        return "running"
    if stage == "live_trading_prepare":
        return "completed"
    return "pending"


def _live_prepare_step_status(stage: str) -> str:
    if stage == "live_trading_prepare":
        return "completed"
    return "pending"


def _paper_trading_error_from_progress(payload: dict[str, Any]) -> str | None:
    if str(payload.get("current_stage") or "") != "paper_trading_failed":
        return None
    message = str(payload.get("message") or "").strip()
    prefix = "Paper trading start failed:"
    if message.startswith(prefix):
        return message[len(prefix) :].strip() or message
    return message or "Paper trading start failed"


def _research_result_task_updates(result: Any) -> dict[str, Any]:
    """Build task-level paper trading and pipeline summary from a completed run."""

    record = _freshened_research_run_record(getattr(result, "run_record", None))
    paper_trading = getattr(result, "paper_trading", None)
    paper_workspace = getattr(paper_trading, "workspace", None)
    paper_unit = getattr(paper_trading, "unit", None)
    paper_handoff = getattr(paper_trading, "handoff", None)
    best_strategy = getattr(result, "best_strategy", None)

    record_handoff = getattr(record, "paper_handoff", None)
    handoff = _redact_sensitive_values(_first_non_empty_dict(record_handoff, paper_handoff))
    record_monitoring_plan = getattr(record, "paper_monitoring_plan", None)
    result_monitoring_plan = getattr(result, "paper_monitoring_plan", None)
    monitoring_plan = _first_non_empty_list(record_monitoring_plan, result_monitoring_plan)
    record_pipeline = getattr(record, "pipeline", None)
    result_pipeline = getattr(result, "pipeline", None)
    pipeline = _first_non_empty_dict(record_pipeline, result_pipeline)
    record_next_actions = getattr(record, "next_actions", None)
    result_next_actions = getattr(result, "next_actions", None)
    next_actions = _first_non_empty_list(record_next_actions, result_next_actions)
    best_metrics = _first_non_empty_dict(
        getattr(record, "best_metrics", None),
        getattr(result, "best_metrics", None),
    )
    best_quality_gate_evaluations = _first_non_empty_list(
        getattr(record, "best_quality_gate_evaluations", None),
        getattr(result, "best_quality_gate_evaluations", None),
    )
    best_diagnostics = _first_non_empty_dict(
        getattr(record, "best_diagnostics", None),
        getattr(result, "best_diagnostics", None),
    )
    asset_specs = _first_non_empty_dict(
        getattr(record, "asset_specs", None),
        handoff.get("asset_specs"),
    )
    backtest_environment = _first_non_empty_dict(
        getattr(record, "backtest_environment", None),
        handoff.get("backtest_environment"),
    )
    live_handoff = _redacted_model_for_task(
        getattr(record, "live_handoff", None),
        AIStrategyLiveHandoffPackage,
    )
    live_handoff_approval = _redacted_model_for_task(
        getattr(record, "live_handoff_approval", None),
        AIStrategyLiveHandoffApprovalRecord,
    )
    timeout_cancel_updates = _backtest_timeout_cancel_task_updates(record, result)

    updates = {
        "run_status": getattr(record, "status", None) or getattr(result, "status", None),
        "achieved": _optional_bool(
            getattr(record, "achieved", None),
            getattr(result, "achieved", None),
        ),
        "target_sharpe": _optional_float(
            getattr(record, "target_sharpe", None),
            getattr(result, "target_sharpe", None),
        ),
        "best_iteration": _optional_int(
            getattr(record, "best_iteration", None),
            getattr(result, "best_iteration", None),
        ),
        "best_sharpe": _optional_float(
            getattr(record, "best_sharpe", None),
            _metric_float(best_metrics, "sharpe_ratio", "sharpe"),
        ),
        "best_quality_score": _optional_float(
            getattr(record, "best_quality_score", None),
            getattr(result, "best_quality_score", None),
        ),
        "best_quality_gate_evaluations": best_quality_gate_evaluations,
        "best_diagnostics": best_diagnostics,
        "best_metrics": best_metrics,
        "best_strategy_id": getattr(record, "best_strategy_id", None)
        or getattr(best_strategy, "id", None),
        "best_strategy_name": getattr(record, "best_strategy_name", None)
        or getattr(best_strategy, "name", None),
        "asset_specs": asset_specs,
        "backtest_environment": backtest_environment,
        "paper_workspace_id": getattr(record, "paper_workspace_id", None)
        or getattr(paper_workspace, "id", None),
        "paper_workspace_name": getattr(record, "paper_workspace_name", None)
        or getattr(paper_workspace, "name", None)
        or handoff.get("paper_workspace_name"),
        "paper_unit_id": getattr(record, "paper_unit_id", None) or getattr(paper_unit, "id", None),
        "paper_trading_started": bool(
            getattr(record, "paper_trading_started", False)
            or getattr(paper_trading, "started", False)
        ),
        "paper_monitoring_plan": monitoring_plan,
        "paper_handoff": handoff,
        "paper_review_status": getattr(record, "paper_review_status", None),
        "paper_review_ready_for_live": bool(getattr(record, "paper_review_ready_for_live", False)),
        "paper_reviewed_at": getattr(record, "paper_reviewed_at", None),
        "paper_review_evaluations": _first_non_empty_list(
            getattr(record, "paper_review_evaluations", None),
        ),
        "paper_review_next_actions": _first_non_empty_list(
            getattr(record, "paper_review_next_actions", None),
        ),
        "live_readiness_checklist": _first_non_empty_list(
            getattr(record, "live_readiness_checklist", None),
            pipeline.get("live_readiness_checklist"),
            handoff.get("live_readiness_checklist"),
        ),
        "live_readiness_expires_at": getattr(record, "live_readiness_expires_at", None)
        or pipeline.get("live_readiness_expires_at")
        or handoff.get("live_readiness_expires_at"),
        "live_handoff": live_handoff,
        "live_handoff_approval": live_handoff_approval,
        "live_workspace_id": getattr(record, "live_workspace_id", None)
        or pipeline.get("live_workspace_id"),
        "live_workspace_name": getattr(record, "live_workspace_name", None)
        or pipeline.get("live_workspace_name"),
        "live_unit_id": getattr(record, "live_unit_id", None) or pipeline.get("live_unit_id"),
        "live_trading_prepared": bool(
            getattr(record, "live_trading_prepared", False)
            or pipeline.get("live_trading_prepared")
        ),
        "live_trading_prepared_at": getattr(record, "live_trading_prepared_at", None)
        or pipeline.get("live_trading_prepared_at")
        or _live_prepare_step_prepared_at(pipeline),
        "pipeline": pipeline,
        "next_actions": next_actions,
    }
    updates.update(timeout_cancel_updates)
    return updates


def _backtest_timeout_cancel_task_updates(record: Any, result: Any) -> dict[str, Any]:
    for status in _latest_iteration_statuses(record, result):
        snapshot = _status_trading_snapshot(status)
        if not snapshot:
            continue
        task_id = str(snapshot.get("backtest_timeout_task_id") or "").strip()
        if not task_id:
            continue
        return {
            "cancelled_backtest_task_id": task_id,
            "child_cancelled": bool(snapshot.get("backtest_timeout_cancel_requested")),
        }
    return {}


def _latest_iteration_statuses(record: Any, result: Any) -> list[Any]:
    statuses: list[Any] = []
    for source in (getattr(record, "iterations", None), getattr(result, "iterations", None)):
        if not isinstance(source, list):
            continue
        for item in reversed(source):
            for key in ("validation_unit_status", "unit_status"):
                if isinstance(item, dict):
                    status = item.get(key)
                else:
                    status = getattr(item, key, None)
                if status is not None:
                    statuses.append(status)
    return statuses


def _live_prepare_step_prepared_at(pipeline: dict[str, Any]) -> str | None:
    steps = pipeline.get("steps")
    if not isinstance(steps, list):
        return None
    for step in reversed(steps):
        if not isinstance(step, dict):
            continue
        if str(step.get("key") or "") != "live_trading_prepare":
            continue
        prepared_at = step.get("prepared_at")
        if prepared_at is None:
            return None
        return str(prepared_at).strip() or None
    return None


def _status_trading_snapshot(status: Any) -> dict[str, Any]:
    if isinstance(status, dict):
        snapshot = status.get("trading_snapshot")
    else:
        snapshot = getattr(status, "trading_snapshot", None)
    return dict(snapshot) if isinstance(snapshot, dict) else {}


def _freshened_task_response_for_read(
    response: AIStrategyResearchTaskResponse,
) -> AIStrategyResearchTaskResponse:
    result = _freshened_research_result_for_task(response.result)
    if result is None or result is response.result:
        return response
    updates = _research_result_task_updates(result)
    pipeline = updates.get("pipeline")
    current_stage = response.current_stage
    if isinstance(pipeline, dict):
        current_stage = str(pipeline.get("current_stage") or current_stage)
    return response.model_copy(
        update={
            **updates,
            "current_stage": current_stage,
            "result": result,
        }
    )


def _freshened_research_result_for_task(result: Any) -> Any:
    record = _freshened_research_run_record(getattr(result, "run_record", None))
    if record is None or not hasattr(result, "model_copy"):
        return result
    if record == getattr(result, "run_record", None):
        return result
    return result.model_copy(
        update={
            "run_record": record,
            "pipeline": record.pipeline,
            "next_actions": record.next_actions,
        }
    )


def _freshened_research_run_record(record: Any) -> Any:
    if record is None:
        return None
    try:
        from app.services.ai_strategy_research_service import (
            _research_run_record_with_live_readiness_freshness,
        )

        return _research_run_record_with_live_readiness_freshness(record)
    except Exception:
        return record


def _first_non_empty_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _first_non_empty_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list) and value:
            return list(value)
    return []


def _optional_bool(*values: Any) -> bool | None:
    for value in values:
        if value is not None:
            return bool(value)
    return None


def _optional_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number:
            return number
    return None


def _optional_int(*values: Any) -> int | None:
    for value in values:
        number = _optional_float(value)
        if number is not None:
            return int(number)
    return None


def _metric_float(metrics: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(metrics.get(key))
        if value is not None:
            return value
    return None


def _research_request_snapshot(request: AIStrategyResearchRunRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    sanitized = _omit_sensitive_request_values(payload)
    return dict(sanitized) if isinstance(sanitized, dict) else {}


def _redacted_research_result_for_task(result: Any) -> AIStrategyResearchRunResponse | None:
    if not hasattr(result, "model_dump"):
        return None
    try:
        payload = result.model_dump(mode="python")
        redacted = _redact_sensitive_values(payload)
        return AIStrategyResearchRunResponse.model_validate(redacted)
    except Exception:
        return None


def _redacted_model_for_task(value: Any, model_cls: Any) -> Any:
    if value is None:
        return None
    try:
        if hasattr(value, "model_dump"):
            payload = value.model_dump(mode="python")
        elif isinstance(value, dict):
            payload = dict(value)
        else:
            return None
        return model_cls.model_validate(_redact_sensitive_values(payload))
    except Exception:
        return None


def _redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_request_key(str(key)):
                result[key] = "***"
            else:
                result[key] = _redact_sensitive_values(item)
        return result
    if isinstance(value, list):
        return [_redact_sensitive_values(item) for item in value]
    return value


def _omit_sensitive_request_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_request_key(str(key)):
                continue
            cleaned = _omit_sensitive_request_values(item)
            if cleaned is _SENSITIVE_REQUEST_OMITTED:
                continue
            result[key] = cleaned
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            cleaned = _omit_sensitive_request_values(item)
            if cleaned is not _SENSITIVE_REQUEST_OMITTED:
                result.append(cleaned)
        return result
    if value == "***":
        return _SENSITIVE_REQUEST_OMITTED
    return value


def _is_sensitive_request_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(marker in lowered for marker in _SENSITIVE_REQUEST_KEYS)
