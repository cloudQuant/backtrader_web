"""Tests for AI observability sink and helpers."""

from __future__ import annotations

from sqlalchemy import select

from app.db.session_provider import unit_of_work
from app.models.ai_call_log import AICallLog
from app.schemas.ai_observability import AICallLogCreate, AICallStatus


def _payload(**overrides) -> AICallLogCreate:
    base = {
        "user_id": "user-1",
        "request_id": "req-1",
        "service_name": "ai_chat",
        "mode": "knowledge_qa",
        "model_name": "gpt-4o-mini",
        "provider": "openai",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "estimated_cost_usd": 0.0001,
        "latency_ms": 25,
        "status": AICallStatus.SUCCESS,
        "response_chars": 32,
        "prompt_hash": "a" * 64,
    }
    base.update(overrides)
    return AICallLogCreate(**base)


async def _logs() -> list[AICallLog]:
    async with unit_of_work() as session:
        result = await session.execute(select(AICallLog).order_by(AICallLog.created_at.asc()))
        return list(result.scalars().all())


def test_hash_prompt_is_deterministic_sha256() -> None:
    from app.services.ai_observability.logger import hash_prompt

    assert hash_prompt("hello") == hash_prompt("hello")
    assert hash_prompt("hello") != hash_prompt("world")
    assert len(hash_prompt("hello")) == 64


def test_calculate_estimated_cost_usd_uses_model_pricing() -> None:
    from app.services.ai_observability.cost_calculator import calculate_estimated_cost_usd

    assert calculate_estimated_cost_usd("gpt-4o", 1_000_000, 1_000_000) > 0
    assert calculate_estimated_cost_usd("ollama-local", 1_000_000, 1_000_000) == 0
    assert calculate_estimated_cost_usd("unknown-model", 1_000_000, 1_000_000) == 0


async def test_ai_call_log_sink_persists_enqueued_record() -> None:
    from app.services.ai_observability.logger import AICallLogSink

    sink = AICallLogSink(queue_maxsize=4)
    try:
        accepted = await sink.enqueue(_payload())
        await sink.flush()
    finally:
        await sink.shutdown()

    assert accepted is True
    records = await _logs()
    assert len(records) == 1
    assert records[0].service_name == "ai_chat"
    assert records[0].total_tokens == 150


async def test_ai_call_log_sink_drops_when_queue_is_full_without_raising() -> None:
    from app.services.ai_observability.logger import AICallLogSink

    sink = AICallLogSink(queue_maxsize=1)
    sink._queue.put_nowait(_payload(request_id="existing"))

    accepted = await sink.enqueue(_payload(request_id="dropped"), autostart=False)

    assert accepted is False


async def test_log_ai_call_decorator_records_success() -> None:
    from app.services.ai_observability.logger import AICallLogSink, log_ai_call

    sink = AICallLogSink(queue_maxsize=4)

    @log_ai_call("ai_chat", mode="knowledge_qa", sink=sink)
    async def call_provider():
        return {
            "answer": "ok",
            "tokens_used": 25,
            "model_id": "gpt-4o-mini",
        }

    try:
        result = await call_provider(
            user_id="user-1",
            request_id="req-1",
            prompt="hello",
            provider="openai",
        )
        await sink.flush()
    finally:
        await sink.shutdown()

    assert result["answer"] == "ok"
    records = await _logs()
    assert len(records) == 1
    assert records[0].status == AICallStatus.SUCCESS.value
    assert records[0].total_tokens == 25
    assert records[0].response_chars == 2


async def test_log_ai_call_decorator_records_failure_and_reraises() -> None:
    from app.services.ai_observability.logger import AICallLogSink, log_ai_call

    sink = AICallLogSink(queue_maxsize=4)

    @log_ai_call("strategy_explainer", mode="strategy_review", sink=sink)
    async def call_provider():
        raise TimeoutError("provider timeout")

    try:
        try:
            await call_provider(user_id="user-1", request_id="req-2", prompt="hello")
        except TimeoutError:
            pass
        await sink.flush()
    finally:
        await sink.shutdown()

    records = await _logs()
    assert len(records) == 1
    assert records[0].status == AICallStatus.TIMEOUT.value
    assert records[0].error_code == "TimeoutError"
    assert "provider timeout" in records[0].error_message
