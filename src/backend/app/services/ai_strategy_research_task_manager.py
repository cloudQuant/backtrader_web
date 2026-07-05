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


class AIStrategyResearchWorkspaceTaskSnapshotStore:
    """Persist completed/recoverable task snapshots in research workspace settings."""

    def __init__(
        self,
        *,
        workspace_service: Any | None = None,
        max_tasks_per_workspace: int = _DEFAULT_MAX_TERMINAL_TASKS_PER_USER,
    ) -> None:
        self._workspace_service = workspace_service
        self._max_tasks_per_workspace = max(int(max_tasks_per_workspace), 1)

    async def save_task(
        self,
        user_id: str,
        response: AIStrategyResearchTaskResponse,
    ) -> None:
        workspace_id = _task_response_research_workspace_id(response)
        if not workspace_id:
            return
        workspace_service = self._get_workspace_service()
        try:
            workspace = await workspace_service.get_workspace(workspace_id, user_id)
        except Exception:
            return
        if workspace is None:
            return

        settings = dict(getattr(workspace, "settings", None) or {})
        ai_research = dict(settings.get("ai_research") or {})
        task_payload = _task_snapshot_payload(response)
        raw_tasks = ai_research.get("tasks")
        existing_tasks = (
            [dict(item) for item in raw_tasks if isinstance(item, dict)]
            if isinstance(raw_tasks, list)
            else []
        )
        tasks = [
            task_payload,
            *[
                item
                for item in existing_tasks
                if str(item.get("task_id") or "") != response.task_id
            ],
        ][: self._max_tasks_per_workspace]
        ai_research["last_task"] = task_payload
        ai_research["tasks"] = tasks

        try:
            from app.schemas.workspace import WorkspaceUpdate

            updated = await workspace_service.update_workspace(
                workspace_id,
                user_id,
                WorkspaceUpdate(settings={"ai_research": ai_research}),
            )
        except Exception:
            updated = None
        if updated is not None:
            return
        settings["ai_research"] = ai_research
        try:
            workspace.settings = settings
        except Exception:
            return

    async def get_task(
        self,
        user_id: str,
        task_id: str,
    ) -> AIStrategyResearchTaskResponse | None:
        task_id = str(task_id or "").strip()
        if not task_id:
            return None
        for workspace in await self._research_workspaces(user_id):
            response = _find_task_snapshot_in_workspace(workspace, task_id)
            if response is not None:
                return _recovered_task_response_for_read(response)
        return None

    async def list_tasks(
        self,
        user_id: str,
        *,
        active_only: bool = False,
        limit: int = 20,
    ) -> list[AIStrategyResearchTaskResponse]:
        responses: dict[str, AIStrategyResearchTaskResponse] = {}
        for workspace in await self._research_workspaces(user_id):
            for response in _task_snapshots_from_workspace(workspace):
                recovered = _recovered_task_response_for_read(response)
                if active_only and recovered.status in _TERMINAL_TASK_STATUSES:
                    continue
                current = responses.get(recovered.task_id)
                if current is None or _task_response_history_rank(
                    recovered
                ) > _task_response_history_rank(current):
                    responses[recovered.task_id] = recovered
        items = list(responses.values())
        items.sort(key=lambda item: item.submitted_at, reverse=True)
        return items[: max(limit, 0)]

    async def _research_workspaces(self, user_id: str) -> list[Any]:
        workspace_service = self._get_workspace_service()
        try:
            _, workspaces = await workspace_service.list_workspaces(
                user_id,
                skip=0,
                limit=100,
                workspace_type="research",
            )
        except Exception:
            return []
        return list(workspaces)

    def _get_workspace_service(self) -> Any:
        if self._workspace_service is None:
            from app.services.workspace_service import WorkspaceService

            self._workspace_service = WorkspaceService()
        return self._workspace_service


class AIStrategyResearchTaskManager:
    """Track in-process AI research loop tasks for API polling."""

    def __init__(
        self,
        *,
        backtest_service_factory: Callable[[], Any] | None = None,
        task_snapshot_store: Any | None = None,
        max_terminal_tasks_per_user: int = _DEFAULT_MAX_TERMINAL_TASKS_PER_USER,
    ) -> None:
        self._tasks: dict[str, _ResearchTaskState] = {}
        self._lock = asyncio.Lock()
        self._backtest_service_factory = backtest_service_factory
        self._task_snapshot_store = task_snapshot_store
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
        runtime_updates.update(
            await _service_continuation_task_updates(
                service,
                user_id,
                request,
            )
        )
        response = AIStrategyResearchTaskResponse(
            task_id=task_id,
            status="pending",
            submitted_at=_utc_iso_now(),
            request_snapshot=_research_request_snapshot(request),
            request_explicit_fields=_research_request_explicit_fields(request),
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
                response = state.response.model_copy(deep=True)
        await self._save_task_snapshot(user_id, response)
        return response

    async def get_task(
        self,
        user_id: str,
        task_id: str,
    ) -> AIStrategyResearchTaskResponse | None:
        memory_response: AIStrategyResearchTaskResponse | None = None
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is not None and state.user_id == user_id:
                memory_response = _freshened_task_response_for_read(
                    state.response.model_copy(deep=True)
                )
        if memory_response is not None:
            return memory_response
        return await self._load_task_snapshot(user_id, task_id)

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
        persisted_items = await self._list_task_snapshots(
            user_id,
            active_only=active_only,
            limit=max(limit, 0),
        )
        items_by_id = {item.task_id: item for item in persisted_items}
        for item in items:
            items_by_id[item.task_id] = item
        items = list(items_by_id.values())
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
        await self._save_task_snapshot(user_id, response)
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

    async def continue_task(
        self,
        user_id: str,
        task_id: str,
        *,
        overrides: dict[str, Any] | None = None,
        service: Any | None = None,
    ) -> AIStrategyResearchTaskResponse | None:
        source_task = await self.get_task(user_id, task_id)
        if source_task is None:
            return None
        request = _continuation_request_from_task(source_task, overrides or {})
        return await self.submit(user_id, request, service=service)

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

            latest_iteration = _latest_iteration_for_task(result)
            best_iteration_payload = _best_iteration_for_task(result)
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
                best_iteration_payload=best_iteration_payload,
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
        snapshot_user_id: str | None = None
        snapshot_response: AIStrategyResearchTaskResponse | None = None
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                return
            updates = _task_updates_with_best_iteration(state.response, updates)
            new_status = updates.get("status")
            if (
                state.response.status in _TERMINAL_TASK_STATUSES
                and new_status is not None
                and new_status != state.response.status
            ):
                return
            state.response = state.response.model_copy(update=updates)
            self._prune_terminal_tasks_locked(state.user_id)
            snapshot_user_id = state.user_id
            snapshot_response = state.response.model_copy(deep=True)
        if snapshot_user_id is not None and snapshot_response is not None:
            await self._save_task_snapshot(snapshot_user_id, snapshot_response)

    async def _save_task_snapshot(
        self,
        user_id: str,
        response: AIStrategyResearchTaskResponse,
    ) -> None:
        store = self._task_snapshot_store
        if store is None:
            return
        saver = getattr(store, "save_task", None)
        if not callable(saver):
            return
        try:
            result = saver(user_id, response)
            if inspect.isawaitable(result):
                await result
        except Exception:
            return

    async def _load_task_snapshot(
        self,
        user_id: str,
        task_id: str,
    ) -> AIStrategyResearchTaskResponse | None:
        store = self._task_snapshot_store
        if store is None:
            return None
        getter = getattr(store, "get_task", None)
        if not callable(getter):
            return None
        try:
            result = getter(user_id, task_id)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            return None
        if isinstance(result, AIStrategyResearchTaskResponse):
            return _freshened_task_response_for_read(result.model_copy(deep=True))
        return None

    async def _list_task_snapshots(
        self,
        user_id: str,
        *,
        active_only: bool,
        limit: int,
    ) -> list[AIStrategyResearchTaskResponse]:
        store = self._task_snapshot_store
        if store is None:
            return []
        lister = getattr(store, "list_tasks", None)
        if not callable(lister):
            return []
        try:
            result = lister(user_id, active_only=active_only, limit=limit)
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            return []
        if not isinstance(result, list):
            return []
        return [
            _freshened_task_response_for_read(item.model_copy(deep=True))
            for item in result
            if isinstance(item, AIStrategyResearchTaskResponse)
        ]

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
        _manager = AIStrategyResearchTaskManager(
            task_snapshot_store=AIStrategyResearchWorkspaceTaskSnapshotStore()
        )
    return _manager


def _continuation_request_from_task(
    task: AIStrategyResearchTaskResponse,
    overrides: dict[str, Any],
) -> AIStrategyResearchRunRequest:
    snapshot = task.request_snapshot if isinstance(task.request_snapshot, dict) else {}
    cleaned = _omit_sensitive_request_values(dict(snapshot))
    payload = dict(cleaned) if isinstance(cleaned, dict) else {}
    # Saved task snapshots only contain redacted gateway credentials, so they
    # cannot be safely reused. Fresh overrides may still provide a gateway_config.
    payload.pop("gateway_config", None)
    continuation_context = _task_continuation_context_for_submit(task)
    existing_context = payload.get("continuation_context")
    if isinstance(existing_context, dict):
        continuation_context = {**existing_context, **continuation_context}

    run_id = _task_continuation_run_id(task)
    if run_id and not payload.get("continue_from_run_id"):
        payload["continue_from_run_id"] = run_id
    if task.research_workspace_id and not payload.get("research_workspace_id"):
        payload["research_workspace_id"] = task.research_workspace_id
    if task.best_strategy_id and not payload.get("seed_strategy_id"):
        payload["seed_strategy_id"] = task.best_strategy_id
    payload_data_config = payload.get("data_config")
    data_config = dict(payload_data_config) if isinstance(payload_data_config, dict) else {}
    if task.asset_specs and "asset_specs" not in data_config:
        data_config["asset_specs"] = dict(task.asset_specs)
        payload["data_config"] = data_config
    if task.backtest_environment:
        unit_settings = dict(payload.get("unit_settings") or {})
        for key, value in dict(task.backtest_environment).items():
            unit_settings.setdefault(key, value)
        payload["unit_settings"] = unit_settings

    if continuation_context:
        payload["continuation_context"] = continuation_context
        source = str(continuation_context.get("source") or "").strip()
        if source:
            payload.setdefault("continuation_source", source)

    if not str(payload.get("symbol") or "").strip():
        symbol = _task_iteration_symbol(task)
        if symbol:
            payload["symbol"] = symbol
    if not str(payload.get("prompt") or "").strip():
        payload["prompt"] = _task_continuation_prompt(task)

    for key, value in (overrides or {}).items():
        if value is not None:
            payload[key] = value
    if isinstance(overrides.get("continuation_context"), dict):
        payload["continuation_context"] = {
            **continuation_context,
            **dict(overrides["continuation_context"]),
        }

    request = AIStrategyResearchRunRequest.model_validate(payload)
    if not request.continue_from_run_id and not request.seed_strategy_id:
        raise ValueError("AI research task has no run or strategy snapshot to continue")
    return request


def _task_continuation_run_id(task: AIStrategyResearchTaskResponse) -> str:
    for value in (
        task.run_id,
        task.continued_from_run_id,
        task.continuation_context.get("run_id")
        if isinstance(task.continuation_context, dict)
        else None,
        task.request_snapshot.get("continue_from_run_id")
        if isinstance(task.request_snapshot, dict)
        else None,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _task_continuation_context_for_submit(
    task: AIStrategyResearchTaskResponse,
) -> dict[str, Any]:
    context = (
        dict(task.continuation_context)
        if isinstance(task.continuation_context, dict)
        else {}
    )
    source = str(context.get("source") or task.continuation_source or "").strip()
    if not source:
        source = _task_continuation_source(task)
    context.update(
        {
            "source": source,
            "task_id": task.task_id,
            "run_id": _task_continuation_run_id(task) or task.run_id,
            "task_status": task.status,
            "task_stage": task.current_stage,
            "quality_gate_failures": _task_continuation_failures(task, context),
            "metrics": _task_continuation_metrics(task),
        }
    )
    if task.current_backtest_task_id:
        context["current_backtest_task_id"] = task.current_backtest_task_id
    if task.cancelled_backtest_task_id:
        context["cancelled_backtest_task_id"] = task.cancelled_backtest_task_id
    if task.pipeline:
        context["pipeline"] = dict(task.pipeline)
    return dict(_redact_sensitive_values(context))


def _task_continuation_source(task: AIStrategyResearchTaskResponse) -> str:
    stage = str(task.current_stage or "").strip()
    status = str(task.status or "").strip()
    if stage == "interrupted":
        return "research_interrupted"
    if status == "cancelled" or stage == "cancelled":
        return "research_cancelled"
    if stage == "paper_trading_failed":
        return "paper_trading_failed"
    return "research_failure"


def _task_continuation_failures(
    task: AIStrategyResearchTaskResponse,
    context: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    for source in (
        context.get("quality_gate_failures"),
        _task_iteration_list(task.best_iteration_payload, "quality_gate_failures"),
        _task_iteration_list(task.latest_iteration, "quality_gate_failures"),
        [task.error, task.message],
        task.next_actions,
    ):
        for item in source if isinstance(source, list) else [source]:
            text = str(item or "").strip()
            if text and text not in failures:
                failures.append(text)
    if not failures:
        failures.append(f"Previous AI research task ended with status {task.status}")
    return failures


def _task_continuation_metrics(task: AIStrategyResearchTaskResponse) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for value in (
        task.best_metrics,
        _task_iteration_mapping(task.best_iteration_payload, "metrics"),
        _task_iteration_mapping(task.latest_iteration, "metrics"),
    ):
        if isinstance(value, dict):
            metrics.update(value)
    return metrics


def _task_iteration_list(value: Any, key: str) -> list[Any]:
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return list(value[key])
    return []


def _task_iteration_mapping(value: Any, key: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get(key), dict):
        return dict(value[key])
    return {}


def _task_iteration_symbol(task: AIStrategyResearchTaskResponse) -> str:
    for payload in (task.best_iteration_payload, task.latest_iteration):
        if not isinstance(payload, dict):
            continue
        for container_key in ("unit_snapshot", "unit"):
            container = payload.get(container_key)
            if isinstance(container, dict):
                symbol = str(container.get("symbol") or "").strip()
                if symbol:
                    return symbol
    return ""


def _task_continuation_prompt(task: AIStrategyResearchTaskResponse) -> str:
    symbol = _task_iteration_symbol(task)
    suffix = f"（{symbol}）" if symbol else ""
    return f"继续优化中断或未完成的 AI 策略投研任务{suffix}"


def _task_snapshot_payload(response: AIStrategyResearchTaskResponse) -> dict[str, Any]:
    payload = response.model_dump(mode="json")
    redacted = _redact_sensitive_values(payload)
    return dict(redacted) if isinstance(redacted, dict) else {}


def _task_response_research_workspace_id(
    response: AIStrategyResearchTaskResponse,
) -> str | None:
    for value in (
        response.research_workspace_id,
        response.request_snapshot.get("research_workspace_id"),
    ):
        text = str(value or "").strip()
        if text:
            return text

    result = response.result
    if result is None:
        return None
    workspace = getattr(result, "research_workspace", None)
    workspace_id = str(getattr(workspace, "id", "") or "").strip()
    if workspace_id:
        return workspace_id
    record = getattr(result, "run_record", None)
    workspace_id = str(getattr(record, "research_workspace_id", "") or "").strip()
    return workspace_id or None


def _task_snapshots_from_workspace(workspace: Any) -> list[AIStrategyResearchTaskResponse]:
    settings = dict(getattr(workspace, "settings", None) or {})
    ai_research = settings.get("ai_research")
    if not isinstance(ai_research, dict):
        return []

    raw_tasks = ai_research.get("tasks")
    tasks = raw_tasks if isinstance(raw_tasks, list) else []
    responses_by_task_id: dict[str, AIStrategyResearchTaskResponse] = {}
    ordered_task_ids: list[str] = []
    for raw in [*tasks, ai_research.get("last_task")]:
        response = _coerce_task_snapshot(raw)
        if response is None:
            continue
        current = responses_by_task_id.get(response.task_id)
        if current is None:
            ordered_task_ids.append(response.task_id)
            responses_by_task_id[response.task_id] = response
            continue
        if _task_response_history_rank(response) > _task_response_history_rank(current):
            responses_by_task_id[response.task_id] = response

    responses = [responses_by_task_id[task_id] for task_id in ordered_task_ids]
    responses.sort(key=lambda item: item.submitted_at, reverse=True)
    return responses


def _find_task_snapshot_in_workspace(
    workspace: Any,
    task_id: str,
) -> AIStrategyResearchTaskResponse | None:
    target = str(task_id or "").strip()
    if not target:
        return None
    return next(
        (
            response
            for response in _task_snapshots_from_workspace(workspace)
            if response.task_id == target
        ),
        None,
    )


def _coerce_task_snapshot(raw: Any) -> AIStrategyResearchTaskResponse | None:
    if not isinstance(raw, dict):
        return None
    try:
        return AIStrategyResearchTaskResponse.model_validate(raw)
    except Exception:
        return None


def _recovered_task_response_for_read(
    response: AIStrategyResearchTaskResponse,
) -> AIStrategyResearchTaskResponse:
    response = _freshened_task_response_for_read(response.model_copy(deep=True))
    if response.status in _TERMINAL_TASK_STATUSES:
        return response
    continuation_context = _interrupted_task_continuation_context(response)
    has_strategy_snapshot = _task_has_reusable_strategy_snapshot(response)
    next_actions = list(response.next_actions or [])
    if not next_actions:
        if has_strategy_snapshot:
            next_actions = [
                "AI research task was interrupted before completion; continue research from the latest saved strategy snapshot."
            ]
        else:
            next_actions = [
                "AI research task was interrupted before the first reusable strategy snapshot; restart research from the saved request."
            ]
    message = (
        "AI research task interrupted before completion; submit a continuation task "
        "from the latest run record."
        if has_strategy_snapshot
        else (
            "AI research task interrupted before a reusable strategy snapshot was saved; "
            "restart research from the saved request."
        )
    )
    return response.model_copy(
        update={
            "status": "failed",
            "completed_at": response.completed_at or _utc_iso_now(),
            "current_stage": "interrupted",
            "current_backtest_task_id": None,
            "continuation_source": "research_interrupted",
            "continuation_context": continuation_context,
            "error": response.error or "AI research task interrupted before completion",
            "message": message,
            "pipeline": _interrupted_task_pipeline(response),
            "next_actions": next_actions,
        }
    )


def _task_has_reusable_strategy_snapshot(response: AIStrategyResearchTaskResponse) -> bool:
    return bool(
        response.best_strategy_id
        or response.best_iteration_payload
        or response.latest_iteration
    )


def _interrupted_task_pipeline(response: AIStrategyResearchTaskResponse) -> dict[str, Any]:
    pipeline = dict(response.pipeline or {})
    pipeline["current_stage"] = "interrupted"
    pipeline["status"] = "failed"
    pipeline["progress"] = response.progress
    pipeline["interrupted_task_id"] = response.task_id
    if response.run_id:
        pipeline["interrupted_run_id"] = response.run_id
    if response.current_backtest_task_id:
        pipeline["interrupted_backtest_task_id"] = response.current_backtest_task_id
    return pipeline


def _interrupted_task_continuation_context(
    response: AIStrategyResearchTaskResponse,
) -> dict[str, Any]:
    context = dict(response.continuation_context or {})
    pipeline = _interrupted_task_pipeline(response)
    failures = []
    for value in (
        response.error,
        response.message,
        "AI research task interrupted before completion",
    ):
        text = str(value or "").strip()
        if text and text not in failures:
            failures.append(text)
    context.update(
        {
            "source": "research_interrupted",
            "run_id": response.run_id,
            "task_id": response.task_id,
            "interrupted_stage": str(response.current_stage or "").strip() or None,
            "interrupted_backtest_task_id": response.current_backtest_task_id,
            "quality_gate_failures": failures,
            "pipeline": pipeline,
        }
    )
    return _redact_sensitive_values(context)


def _task_response_history_rank(response: AIStrategyResearchTaskResponse) -> tuple[Any, ...]:
    status_rank = {
        "completed": 5,
        "cancelled": 4,
        "failed": 3,
        "running": 2,
        "pending": 1,
    }.get(response.status, 0)
    return (
        status_rank,
        1 if response.result is not None else 0,
        response.completed_at or "",
        response.started_at or "",
        response.submitted_at,
    )


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
    redacted = _redact_sensitive_values(updates)
    return dict(redacted) if isinstance(redacted, dict) else updates


def _research_request_runtime_task_updates(
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    continuation_updates = _research_request_continuation_task_updates(request)
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
        updates.update(continuation_updates)
        return updates
    except Exception:
        return {
            **continuation_updates,
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


async def _service_continuation_task_updates(
    service: Any | None,
    user_id: str,
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    if service is None:
        return {}
    provider = getattr(service, "continuation_task_updates", None)
    if not callable(provider):
        return {}
    try:
        result = provider(user_id, request)
        if inspect.isawaitable(result):
            result = await result
    except Exception:
        return {}
    if not isinstance(result, dict) or not result:
        return {}
    redacted = _redact_sensitive_values(result)
    return dict(redacted) if isinstance(redacted, dict) else {}


def _research_request_continuation_task_updates(
    request: AIStrategyResearchRunRequest,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    continued_from = str(request.continue_from_run_id or "").strip()
    if continued_from:
        updates["continued_from_run_id"] = continued_from
    if isinstance(request.continuation_context, dict) and request.continuation_context:
        redacted = _redact_sensitive_values(dict(request.continuation_context))
        if isinstance(redacted, dict) and redacted:
            updates["continuation_context"] = redacted
            source = str(redacted.get("source") or "").strip()
            if source:
                updates["continuation_source"] = source
    return updates


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
    validation_status = _progress_validation_status(payload)
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
        {
            "key": "validation",
            "label": "样本外验证",
            "status": _validation_step_status(
                stage,
                request=request,
                validation_status=validation_status,
                iteration_count=iteration_count,
            ),
            "validation_status": validation_status,
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
        "status": "configuration_invalid" if stage == "configuration_invalid" else "running",
        "progress": progress,
        "paper_trading_error": paper_trading_error,
        "steps": steps,
    }


def _progress_validation_status(payload: dict[str, Any]) -> str | None:
    latest = payload.get("latest_iteration")
    if not isinstance(latest, dict):
        return None
    status = str(latest.get("validation_status") or "").strip()
    return status or None


def _draft_step_status(stage: str) -> str:
    if stage in {"draft_generation_failed"}:
        return "failed"
    if stage in {"drafting", "repairing_code"}:
        return "running"
    if stage in {"queued", "starting", "initializing", "workspace_ready", "configuration_invalid"}:
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


def _validation_step_status(
    stage: str,
    *,
    request: AIStrategyResearchRunRequest,
    validation_status: str | None,
    iteration_count: int,
) -> str:
    if not request.out_of_sample_validation:
        return "skipped"
    normalized = str(validation_status or "").strip()
    if normalized == "passed":
        return "completed"
    if normalized == "failed":
        return "failed"
    if normalized in {"skipped", "not_required"}:
        return "skipped"
    if stage == "configuration_invalid":
        return "failed"
    if stage == "validating":
        return "running"
    if stage == "cancelled":
        return "cancelled"
    if iteration_count <= 0 or stage in {"queued", "starting", "initializing", "workspace_ready"}:
        return "pending"
    return "pending"


def _quality_step_status(stage: str) -> str:
    if stage == "configuration_invalid":
        return "failed"
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
    handoff = _redact_sensitive_values(_merged_non_empty_dict(record_handoff, paper_handoff))
    record_monitoring_plan = getattr(record, "paper_monitoring_plan", None)
    result_monitoring_plan = getattr(result, "paper_monitoring_plan", None)
    monitoring_plan = _first_non_empty_list(record_monitoring_plan, result_monitoring_plan)
    record_pipeline = getattr(record, "pipeline", None)
    result_pipeline = getattr(result, "pipeline", None)
    pipeline = _first_non_empty_dict(record_pipeline, result_pipeline)
    record_next_actions = getattr(record, "next_actions", None)
    result_next_actions = getattr(result, "next_actions", None)
    next_actions = _first_non_empty_list(record_next_actions, result_next_actions)
    promotion_audit = _first_non_empty_list(
        getattr(record, "promotion_audit", None),
        getattr(result, "promotion_audit", None),
    )
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
    asset_specs = _merged_non_empty_dict(
        getattr(record, "asset_specs", None),
        handoff.get("asset_specs"),
    )
    backtest_environment = _merged_non_empty_dict(
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
    continuation_updates = _research_record_continuation_task_updates(record)
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
        "paper_trading_started": _paper_trading_started_for_task(
            record,
            paper_trading,
            pipeline,
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
        "promotion_audit": promotion_audit,
        "next_actions": next_actions,
    }
    updates.update(timeout_cancel_updates)
    updates.update(continuation_updates)
    return updates


def _task_updates_with_best_iteration(
    response: AIStrategyResearchTaskResponse,
    updates: dict[str, Any],
) -> dict[str, Any]:
    if "best_iteration_payload" in updates:
        return updates
    latest_iteration = updates.get("latest_iteration")
    if not isinstance(latest_iteration, dict):
        return updates
    candidate = _redact_sensitive_values(dict(latest_iteration))
    if not isinstance(candidate, dict):
        return updates
    current = (
        dict(response.best_iteration_payload)
        if isinstance(response.best_iteration_payload, dict)
        else None
    )
    if current is None or _task_iteration_payload_rank(candidate) > _task_iteration_payload_rank(
        current
    ):
        updates = dict(updates)
        updates["best_iteration_payload"] = candidate
    return updates


def _task_iteration_payload_rank(payload: dict[str, Any]) -> tuple[int, float, float, int, int]:
    metrics = payload.get("metrics")
    metric_payload = dict(metrics) if isinstance(metrics, dict) else {}
    passed = _payload_truthy(payload.get("passed"))
    quality_score = _optional_float(payload.get("quality_score")) or 0.0
    sharpe = _optional_float(payload.get("sharpe_ratio"))
    if sharpe is None:
        sharpe = _metric_float(metric_payload, "sharpe_ratio", "sharpe", "sharpeRatio")
    total_trades = _optional_int(payload.get("total_trades"))
    if total_trades is None:
        total_trades = _optional_int(metric_payload.get("total_trades"))
    if total_trades is None:
        total_trades = _optional_int(metric_payload.get("trades"))
    iteration = _optional_int(payload.get("iteration")) or 0
    return (
        1 if passed else 0,
        quality_score,
        sharpe or 0.0,
        total_trades or 0,
        -iteration,
    )


def _payload_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed"}
    return bool(value)


def _latest_iteration_for_task(result: AIStrategyResearchRunResponse) -> dict[str, Any] | None:
    if not result.iterations:
        return None
    payload = result.iterations[-1].model_dump(mode="json")
    redacted = _redact_sensitive_values(payload)
    return dict(redacted) if isinstance(redacted, dict) else None


def _best_iteration_for_task(result: AIStrategyResearchRunResponse) -> dict[str, Any] | None:
    if not result.iterations:
        return None
    best_iteration = result.best_iteration
    matched = next(
        (item for item in result.iterations if item.iteration == best_iteration),
        None,
    )
    item = matched or max(
        result.iterations,
        key=lambda iteration: (
            bool(iteration.passed),
            float(iteration.quality_score or 0.0),
            float(iteration.sharpe_ratio or 0.0),
            int(iteration.total_trades or 0),
            -int(iteration.iteration or 0),
        ),
    )
    payload = item.model_dump(mode="json")
    redacted = _redact_sensitive_values(payload)
    return dict(redacted) if isinstance(redacted, dict) else None


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


def _paper_trading_started_for_task(
    record: Any,
    paper_trading: Any,
    pipeline: dict[str, Any],
) -> bool:
    stage = str(pipeline.get("current_stage") or "").strip()
    error = str(pipeline.get("paper_trading_error") or "").strip()
    if stage == "paper_trading_failed" or error:
        return False
    return bool(
        getattr(record, "paper_trading_started", False)
        or getattr(paper_trading, "started", False)
    )


def _research_record_continuation_task_updates(record: Any) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if record is None:
        return updates

    continued_from = str(getattr(record, "continued_from_run_id", None) or "").strip()
    if continued_from:
        updates["continued_from_run_id"] = continued_from

    source = str(getattr(record, "continuation_source", None) or "").strip()
    context = getattr(record, "continuation_context", None)
    if isinstance(context, dict) and context:
        redacted = _redact_sensitive_values(dict(context))
        if isinstance(redacted, dict) and redacted:
            updates["continuation_context"] = redacted
            if not source:
                source = str(redacted.get("source") or "").strip()
            if not continued_from:
                context_run_id = str(redacted.get("run_id") or "").strip()
                if context_run_id:
                    updates["continued_from_run_id"] = context_run_id
    if source:
        updates["continuation_source"] = source
    return updates


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


def _merged_non_empty_dict(*values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if not isinstance(value, dict) or not value:
            continue
        for key, item in value.items():
            if isinstance(item, dict) and isinstance(merged.get(key), dict):
                nested = dict(merged[key])
                nested.update(item)
                merged[key] = nested
            else:
                merged[key] = item
    return merged


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
    if not isinstance(sanitized, dict):
        return {}
    explicit_fields = set(_research_request_explicit_fields(request))
    for key in (
        "data_config",
        "unit_settings",
        "optimization_config",
        "gateway_config",
        "continuation_context",
    ):
        if key not in explicit_fields and sanitized.get(key) == {}:
            sanitized.pop(key, None)
    return dict(sanitized)


def _research_request_explicit_fields(request: AIStrategyResearchRunRequest) -> list[str]:
    fields = getattr(request, "model_fields_set", None)
    if fields is None:
        fields = getattr(request, "__fields_set__", set())
    return sorted(str(field).strip() for field in fields if str(field).strip())


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
