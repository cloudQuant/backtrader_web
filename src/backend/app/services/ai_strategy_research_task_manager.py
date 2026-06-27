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
    AIStrategyResearchRunRequest,
    AIStrategyResearchTaskResponse,
)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _ResearchTaskState:
    user_id: str
    response: AIStrategyResearchTaskResponse
    background_task: asyncio.Task[None] | None = None


class AIStrategyResearchTaskManager:
    """Track in-process AI research loop tasks for API polling."""

    def __init__(self, *, backtest_service_factory: Callable[[], Any] | None = None) -> None:
        self._tasks: dict[str, _ResearchTaskState] = {}
        self._lock = asyncio.Lock()
        self._backtest_service_factory = backtest_service_factory

    async def submit(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        service: Any | None = None,
    ) -> AIStrategyResearchTaskResponse:
        task_id = str(uuid.uuid4())
        response = AIStrategyResearchTaskResponse(
            task_id=task_id,
            status="pending",
            submitted_at=_utc_iso_now(),
            current_stage="queued",
            progress=0.0,
            max_iterations=request.max_iterations,
            message="AI research task submitted",
        )
        async with self._lock:
            self._tasks[task_id] = _ResearchTaskState(user_id=user_id, response=response)

        loop = asyncio.get_running_loop()
        background_task = loop.create_task(
            self._run_task(task_id, user_id, request, service=service)
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
            return state.response.model_copy(deep=True)

    async def list_tasks(
        self,
        user_id: str,
        *,
        active_only: bool = False,
        limit: int = 20,
    ) -> list[AIStrategyResearchTaskResponse]:
        terminal_statuses = {"completed", "failed", "cancelled"}
        async with self._lock:
            items = [
                state.response.model_copy(deep=True)
                for state in self._tasks.values()
                if state.user_id == user_id
                and (not active_only or state.response.status not in terminal_statuses)
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
            if state.response.status in {"completed", "failed", "cancelled"}:
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
        latest = await self.get_task(user_id, task_id)
        return latest or response

    async def _run_task(
        self,
        task_id: str,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        service: Any | None,
    ) -> None:
        await self._update_task(
            task_id,
            status="running",
            started_at=_utc_iso_now(),
            current_stage="starting",
            progress=1.0,
            max_iterations=request.max_iterations,
            message="AI research task is running",
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
                    **payload,
                )

            if _runner_accepts_progress_callback(runner):
                result = await runner.run(
                    user_id,
                    request,
                    progress_callback=progress_callback,
                )
            else:
                result = await runner.run(user_id, request)

            latest_iteration = (
                result.iterations[-1].model_dump(mode="json") if result.iterations else None
            )
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
                result=result,
                message=result.message,
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
                state.response.status in {"completed", "failed", "cancelled"}
                and new_status is not None
                and new_status != state.response.status
            ):
                return
            state.response = state.response.model_copy(update=updates)

    async def _cancel_child_backtest(self, task_id: str, user_id: str) -> bool:
        try:
            service = self._backtest_service_factory() if self._backtest_service_factory else None
            if service is None:
                from app.services.backtest.service import BacktestService

                service = BacktestService()
            return bool(await service.cancel_task(task_id, user_id))
        except Exception:
            return False


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
