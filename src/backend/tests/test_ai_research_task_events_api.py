from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchRun, ResearchTask
from app.models.user import User
from app.services.research.task_runner import DurableResearchTaskRunner
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_v2_task_reads_are_owner_scoped_paginated_and_reject_invalid_cursor(
    client, auth_user
) -> None:
    """Task reads expose a safe owner projection behind a validated cursor."""

    user, headers = auth_user
    user_id = await _user_id(user["username"])
    older, newer = await _seed_tasks(user_id)

    first = await client.get(
        "/api/v1/strategy/ai-research/v2/tasks?limit=1",
        headers=headers,
    )

    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert [item["id"] for item in first_payload["items"]] == [newer.id]
    assert first_payload["next_cursor"]
    assert "request_json" not in first_payload["items"][0]
    assert "lease_token" not in first_payload["items"][0]

    second = await client.get(
        "/api/v1/strategy/ai-research/v2/tasks",
        params={"limit": 1, "cursor": first_payload["next_cursor"]},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert [item["id"] for item in second.json()["items"]] == [older.id]
    assert second.json()["next_cursor"] is None

    invalid = await client.get(
        "/api/v1/strategy/ai-research/v2/tasks",
        params={"cursor": "not-a-task-cursor"},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "RESEARCH_TASK_CURSOR_INVALID"

    detail = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{newer.id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == newer.id

    _other, other_headers = await register_and_login(client, username="v2-task-event-other")
    foreign = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{newer.id}",
        headers=other_headers,
    )
    missing = await client.get(
        "/api/v1/strategy/ai-research/v2/tasks/not-a-real-task",
        headers=headers,
    )
    assert foreign.status_code == 404
    assert foreign.json()["message"] == "RESEARCH_TASK_NOT_FOUND"
    assert missing.status_code == 404
    assert missing.json()["message"] == "RESEARCH_TASK_NOT_FOUND"


@pytest.mark.asyncio
async def test_v2_task_event_reads_expose_only_safe_append_only_summaries(
    client, auth_user
) -> None:
    """An empty event stream is resumable and a claim becomes a safe summary event."""

    user, headers = auth_user
    user_id = await _user_id(user["username"])
    task = await _seed_single_task(user_id, suffix="event-read")

    empty = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{task.id}/events",
        headers=headers,
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == []
    assert empty.json()["next_cursor"] is None
    initial_resume_cursor = empty.json()["resume_cursor"]
    assert initial_resume_cursor

    claims = await DurableResearchTaskRunner(lease_seconds=60).claim_due()
    assert len(claims) == 1
    assert claims[0].task_id == task.id

    claimed = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{task.id}/events",
        params={"cursor": initial_resume_cursor},
        headers=headers,
    )
    assert claimed.status_code == 200, claimed.text
    payload = claimed.json()
    assert len(payload["items"]) == 1
    event = payload["items"][0]
    assert event["event_type"] == "TASK_CLAIMED"
    assert event["sequence_no"] == 1
    assert set(event) == {
        "id",
        "task_id",
        "run_id",
        "sequence_no",
        "event_type",
        "stage",
        "status",
        "error_code",
        "stage_attempt_id",
        "trace_id",
        "created_at",
    }
    assert "payload" not in event
    assert payload["next_cursor"] is None
    assert payload["resume_cursor"]

    caught_up = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{task.id}/events",
        params={"cursor": payload["resume_cursor"]},
        headers=headers,
    )
    assert caught_up.status_code == 200, caught_up.text
    assert caught_up.json()["items"] == []
    assert caught_up.json()["resume_cursor"] == payload["resume_cursor"]

    invalid = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{task.id}/events",
        params={"cursor": "not-an-event-cursor"},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "RESEARCH_TASK_CURSOR_INVALID"

    _other, other_headers = await register_and_login(client, username="v2-task-event-read-other")
    foreign = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{task.id}/events",
        headers=other_headers,
    )
    foreign_invalid_cursor = await client.get(
        f"/api/v1/strategy/ai-research/v2/tasks/{task.id}/events",
        params={"cursor": "not-an-event-cursor"},
        headers=other_headers,
    )
    missing = await client.get(
        "/api/v1/strategy/ai-research/v2/tasks/not-a-real-task/events",
        headers=headers,
    )
    assert foreign.status_code == 404
    assert foreign.json()["message"] == "RESEARCH_TASK_NOT_FOUND"
    assert foreign_invalid_cursor.status_code == 404
    assert foreign_invalid_cursor.json()["message"] == "RESEARCH_TASK_NOT_FOUND"
    assert missing.status_code == 404
    assert missing.json()["message"] == "RESEARCH_TASK_NOT_FOUND"


async def _seed_tasks(user_id: str) -> tuple[ResearchTask, ResearchTask]:
    base = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
    older_run = _run(user_id, suffix="older", created_at=base)
    newer_run = _run(user_id, suffix="newer", created_at=base + timedelta(minutes=1))
    async with async_session_maker() as session:
        session.add_all([older_run, newer_run])
        await session.flush()
        older = _task(older_run, suffix="older", created_at=base)
        newer = _task(newer_run, suffix="newer", created_at=base + timedelta(minutes=1))
        session.add_all([older, newer])
        await session.commit()
        await session.refresh(older)
        await session.refresh(newer)
    return older, newer


async def _seed_single_task(user_id: str, *, suffix: str) -> ResearchTask:
    now = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)
    run = _run(user_id, suffix=suffix, created_at=now)
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task = _task(run, suffix=suffix, created_at=now)
        session.add(task)
        await session.commit()
        await session.refresh(task)
    return task


def _run(user_id: str, *, suffix: str, created_at: datetime) -> ResearchRun:
    return ResearchRun(
        user_id=user_id,
        hypothesis_version_id=f"task-read-hypothesis-{suffix}",
        promotion_policy_version="promotion-v1",
        request_hash="a" * 64,
        capability_profile_id="task-read-profile",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id=f"trace-task-read-{suffix}",
        created_at=created_at,
    )


def _task(run: ResearchRun, *, suffix: str, created_at: datetime) -> ResearchTask:
    return ResearchTask(
        user_id=run.user_id,
        run_id=run.id,
        status="QUEUED",
        stage_cursor="CLARIFY",
        request_json={"raw_secret": f"must-not-leak-{suffix}"},
        idempotency_key=f"task-read-{suffix}",
        idempotency_request_hash="c" * 64,
        trace_id=run.trace_id,
        created_at=created_at,
    )


async def _user_id(username: str) -> str:
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == username))
        return str(result.scalar_one())
