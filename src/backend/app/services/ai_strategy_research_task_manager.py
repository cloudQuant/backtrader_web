"""Async task manager for long-running AI strategy research loops."""

from __future__ import annotations

import asyncio
import uuid
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


class AIStrategyResearchTaskManager:
    """Track in-process AI research loop tasks for API polling."""

    def __init__(self) -> None:
        self._tasks: dict[str, _ResearchTaskState] = {}
        self._lock = asyncio.Lock()

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
            message="AI research task submitted",
        )
        async with self._lock:
            self._tasks[task_id] = _ResearchTaskState(user_id=user_id, response=response)

        loop = asyncio.get_running_loop()
        loop.create_task(self._run_task(task_id, user_id, request, service=service))
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
            message="AI research task is running",
        )
        try:
            runner = service
            if runner is None:
                from app.services.ai_strategy_research_service import AIStrategyResearchService

                runner = AIStrategyResearchService()
            result = await runner.run(user_id, request)
            await self._update_task(
                task_id,
                status="completed",
                completed_at=_utc_iso_now(),
                run_id=result.run_id,
                result=result,
                message=result.message,
            )
        except Exception as exc:
            await self._update_task(
                task_id,
                status="failed",
                completed_at=_utc_iso_now(),
                error=str(exc),
                message="AI research task failed",
            )

    async def _update_task(self, task_id: str, **updates: Any) -> None:
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                return
            state.response = state.response.model_copy(update=updates)


_manager: AIStrategyResearchTaskManager | None = None


def get_ai_strategy_research_task_manager() -> AIStrategyResearchTaskManager:
    global _manager
    if _manager is None:
        _manager = AIStrategyResearchTaskManager()
    return _manager
