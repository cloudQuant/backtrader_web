"""Tests for AI token and cost budget controls."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.session_provider import unit_of_work
from app.models.ai_call_log import AICallLog
from app.models.user import User


async def _insert_ai_log(**overrides) -> AICallLog:
    values = {
        "user_id": "user-1",
        "request_id": None,
        "service_name": "ai_chat",
        "mode": "knowledge_qa",
        "model_name": "gpt-4o-mini",
        "provider": "openai_compatible",
        "prompt_template_id": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 10,
        "estimated_cost_usd": 0.002,
        "latency_ms": 100,
        "status": "success",
        "error_code": None,
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "response_chars": 20,
        "prompt_hash": "a" * 64,
    }
    values.update(overrides)
    record = AICallLog(**values)
    async with unit_of_work() as session:
        session.add(record)
        await session.flush()
    return record


async def _insert_user(**overrides) -> User:
    values = {
        "id": "user-1",
        "username": "budget_user",
        "email": "budget_user@example.com",
        "hashed_password": "hashed",
        "is_active": True,
    }
    values.update(overrides)
    user = User(**values)
    async with unit_of_work() as session:
        session.add(user)
        await session.flush()
    return user


@pytest.mark.asyncio
async def test_budget_service_reports_remaining_daily_global_budget() -> None:
    from app.services.ai_observability.budget import AIBudgetService, AIBudgetSettings

    await _insert_ai_log(
        user_id="user-1",
        estimated_cost_usd=0.003,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    await _insert_ai_log(
        user_id="user-1",
        estimated_cost_usd=0.5,
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
        prompt_hash="b" * 64,
    )

    snapshot = await AIBudgetService(
        settings=AIBudgetSettings(global_daily_usd=0.01, global_mode="soft")
    ).get_daily_budget_snapshot(user_id="user-1")

    assert snapshot.limit_usd == pytest.approx(0.01)
    assert snapshot.used_usd == pytest.approx(0.003)
    assert snapshot.remaining_usd == pytest.approx(0.007)
    assert snapshot.mode == "soft"
    assert snapshot.exceeded is False
    assert snapshot.reset_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_budget_service_user_limit_and_mode_override_global_settings() -> None:
    from app.services.ai_observability.budget import AIBudgetService, AIBudgetSettings

    await _insert_user(ai_budget_daily_usd=0.002, ai_budget_mode="hard")
    await _insert_ai_log(user_id="user-1", estimated_cost_usd=0.003)

    snapshot = await AIBudgetService(
        settings=AIBudgetSettings(global_daily_usd=1.0, global_mode="soft")
    ).get_daily_budget_snapshot(user_id="user-1")

    assert snapshot.limit_usd == pytest.approx(0.002)
    assert snapshot.used_usd == pytest.approx(0.003)
    assert snapshot.mode == "hard"
    assert snapshot.exceeded is True


@pytest.mark.asyncio
async def test_budget_service_hard_budget_raises_structured_error() -> None:
    from app.services.ai_observability.budget import (
        AIBudgetExceededError,
        AIBudgetService,
        AIBudgetSettings,
    )

    await _insert_ai_log(user_id="user-1", estimated_cost_usd=0.02)
    service = AIBudgetService(settings=AIBudgetSettings(global_daily_usd=0.01, global_mode="hard"))

    with pytest.raises(AIBudgetExceededError) as exc_info:
        await service.ensure_budget_available(user_id="user-1")

    assert exc_info.value.detail["reason_code"] == "budget_exceeded"
    assert exc_info.value.detail["limit_usd"] == pytest.approx(0.01)
    assert exc_info.value.detail["used_usd"] == pytest.approx(0.02)
    assert "reset_at" in exc_info.value.detail


@pytest.mark.asyncio
async def test_log_ai_call_blocks_provider_when_hard_budget_exceeded() -> None:
    from app.services.ai_observability.budget import AIBudgetExceededError
    from app.services.ai_observability.logger import AICallLogSink, log_ai_call

    sink = AICallLogSink(queue_maxsize=4)
    provider_called = False

    async def deny_budget(*, user_id: str | None) -> None:
        assert user_id == "user-1"
        raise AIBudgetExceededError(
            reason_code="budget_exceeded",
            limit_usd=0.01,
            used_usd=0.02,
            reset_at=datetime.now(timezone.utc),
        )

    @log_ai_call("ai_chat", mode="knowledge_qa", sink=sink, budget_checker=deny_budget)
    async def call_provider():
        nonlocal provider_called
        provider_called = True
        return {"answer": "ok", "tokens_used": 1, "model_id": "gpt-4o-mini"}

    try:
        with pytest.raises(AIBudgetExceededError):
            await call_provider(user_id="user-1", request_id="req-1", prompt="hello")
        await sink.flush()
    finally:
        await sink.shutdown()

    assert provider_called is False
