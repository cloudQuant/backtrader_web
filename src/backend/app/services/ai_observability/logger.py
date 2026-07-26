"""Async AI call logging sink and decorator helpers."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from app.config import get_settings
from app.db.session_provider import unit_of_work
from app.models.ai_call_log import AICallLog
from app.schemas.ai_observability import AICallLogCreate, AICallStatus
from app.services.ai_observability.budget import AIBudgetService
from app.services.ai_observability.cost_calculator import calculate_estimated_cost_usd
from app.utils.logger import get_logger

logger = get_logger(__name__)
_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])
_BudgetChecker = Callable[..., Awaitable[None]]
_OBSERVABILITY_KWARGS = {
    "completion_tokens",
    "model_name",
    "prompt",
    "prompt_template_id",
    "prompt_template_version",
    "prompt_tokens",
    "provider",
    "request_id",
    "user_id",
}


def hash_prompt(prompt: str) -> str:
    """Return a SHA-256 digest for prompt text without storing the prompt."""
    return hashlib.sha256(str(prompt or "").encode("utf-8")).hexdigest()


class AICallLogSink:
    """Bounded asynchronous sink for AI call log persistence."""

    def __init__(self, queue_maxsize: int | None = None) -> None:
        settings = get_settings()
        self._queue_maxsize = queue_maxsize or getattr(settings, "AI_CALL_LOG_QUEUE_MAXSIZE", 1000)
        self._queue: asyncio.Queue[AICallLogCreate | None] = asyncio.Queue(
            maxsize=self._queue_maxsize
        )
        self._worker_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._worker_task is not None and not self._worker_task.done():
                return
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def enqueue(self, payload: AICallLogCreate, *, autostart: bool = True) -> bool:
        if autostart:
            await self.start()
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning(
                "AI call log sink queue is full, dropping record. "
                f"service_name={payload.service_name} mode={payload.mode}"
            )
            return False
        return True

    async def flush(self) -> None:
        if self._worker_task is None:
            return
        await self._queue.join()

    async def shutdown(self) -> None:
        async with self._lifecycle_lock:
            worker_task = self._worker_task
            if worker_task is None:
                return
            await self._queue.join()
            await self._queue.put(None)
            await worker_task
            self._worker_task = None
            self._queue = asyncio.Queue(maxsize=self._queue_maxsize)

    async def _worker_loop(self) -> None:
        while True:
            payload = await self._queue.get()
            try:
                if payload is None:
                    return
                try:
                    await self._persist(payload)
                except Exception as exc:
                    logger.error(
                        "AI call log async sink failed. "
                        f"service_name={payload.service_name} mode={payload.mode} error={exc}"
                    )
            finally:
                self._queue.task_done()

    async def _persist(self, payload: AICallLogCreate) -> None:
        async with unit_of_work() as session:
            session.add(AICallLog(**payload.model_dump(mode="json")))
            await session.flush()


_default_sink: AICallLogSink | None = None


def get_ai_call_log_sink() -> AICallLogSink:
    """Return process-wide AI call log sink singleton."""
    global _default_sink
    if _default_sink is None:
        _default_sink = AICallLogSink()
    return _default_sink


def _extract_total_tokens(result: Any) -> int:
    if isinstance(result, dict):
        return int(result.get("tokens_used") or result.get("total_tokens") or 0)
    return 0


def _extract_model_name(result: Any, default: str) -> str:
    if isinstance(result, dict):
        return str(result.get("model_id") or result.get("model_name") or default)
    return default


def _extract_response_chars(result: Any) -> int:
    if isinstance(result, dict):
        answer = result.get("answer")
        if isinstance(answer, str):
            return len(answer)
    return len(str(result or ""))


def _build_payload(
    *,
    kwargs: dict[str, Any],
    service_name: str,
    mode: str,
    status: AICallStatus,
    latency_ms: int,
    result: Any = None,
    exc: BaseException | None = None,
) -> AICallLogCreate:
    total_tokens = _extract_total_tokens(result)
    model_name = _extract_model_name(result, str(kwargs.get("model_name") or "unknown"))
    prompt_tokens = int(kwargs.get("prompt_tokens") or 0)
    completion_tokens = int(kwargs.get("completion_tokens") or max(total_tokens - prompt_tokens, 0))
    if prompt_tokens == 0 and completion_tokens == total_tokens:
        completion_tokens = 0
    provider = str(kwargs.get("provider") or "unknown")
    return AICallLogCreate(
        user_id=kwargs.get("user_id"),
        request_id=kwargs.get("request_id"),
        service_name=service_name,
        mode=mode,
        model_name=model_name,
        provider=provider,
        prompt_template_id=kwargs.get("prompt_template_id"),
        prompt_template_version=kwargs.get("prompt_template_version"),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=calculate_estimated_cost_usd(
            model_name,
            prompt_tokens,
            completion_tokens,
        ),
        latency_ms=latency_ms,
        status=status,
        error_code=type(exc).__name__ if exc else None,
        error_message=str(exc)[:1000] if exc else None,
        response_chars=_extract_response_chars(result) if exc is None else 0,
        prompt_hash=hash_prompt(str(kwargs.get("prompt") or "")),
    )


def log_ai_call(
    service_name: str,
    *,
    mode: str,
    sink: AICallLogSink | None = None,
    budget_checker: _BudgetChecker | None = None,
) -> Callable[[_F], _F]:
    """Decorate async AI provider calls with fail-open metadata logging."""

    def decorator(func: _F) -> _F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            active_sink = sink or get_ai_call_log_sink()
            call_kwargs = dict(kwargs)
            metadata = {
                key: call_kwargs.pop(key) for key in _OBSERVABILITY_KWARGS if key in call_kwargs
            }
            checker = budget_checker or AIBudgetService().ensure_budget_available
            await checker(user_id=metadata.get("user_id"))
            try:
                result = await func(*args, **call_kwargs)
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                status = (
                    AICallStatus.TIMEOUT if isinstance(exc, TimeoutError) else AICallStatus.FAILED
                )
                payload = _build_payload(
                    kwargs=metadata,
                    service_name=service_name,
                    mode=mode,
                    status=status,
                    latency_ms=latency_ms,
                    exc=exc,
                )
                await active_sink.enqueue(payload)
                raise
            latency_ms = int((time.perf_counter() - started) * 1000)
            payload = _build_payload(
                kwargs=metadata,
                service_name=service_name,
                mode=mode,
                status=AICallStatus.SUCCESS,
                latency_ms=latency_ms,
                result=result,
            )
            await active_sink.enqueue(payload)
            return result

        return cast(_F, wrapper)

    return decorator
