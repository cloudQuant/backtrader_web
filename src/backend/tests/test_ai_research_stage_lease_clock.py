"""Database-clock fencing for stage checkpoints and local artifacts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchRun, ResearchStageAttempt, ResearchTask
from app.services.research import stage_attempt as stage_attempt_module
from app.services.research.artifact_broker import ArtifactBroker
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.workflow_worker import StageExecutionContext


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("application_skew", "lease_delta", "should_start"),
    (
        pytest.param(
            timedelta(minutes=10),
            timedelta(minutes=5),
            True,
            id="application-clock-fast-by-ten-minutes",
        ),
        pytest.param(
            timedelta(minutes=-10),
            timedelta(seconds=-1),
            False,
            id="application-clock-slow-by-ten-minutes",
        ),
    ),
)
async def test_stage_begin_uses_database_utc_lease_clock_despite_application_skew(
    monkeypatch: pytest.MonkeyPatch,
    application_skew: timedelta,
    lease_delta: timedelta,
    should_start: bool,
) -> None:
    """A stage checkpoint cannot be created using the worker host's wall clock."""

    task, _run = await _leased_context("begin", lease_delta=lease_delta)
    database_like_now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        stage_attempt_module,
        "_now",
        lambda: database_like_now + application_skew,
    )
    service = ResearchStageAttemptService()
    call = service.begin(
        task_id=task.id,
        lease_token=task.lease_token or "",
        stage="GENERATE",
        idempotency_key=f"database-clock-begin-{int(application_skew.total_seconds())}",
        input_payload={"request_hash": "p" * 64},
    )

    if should_start:
        attempt = await call
        assert attempt.task_id == task.id
    else:
        with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_LEASE_DENIED"):
            await call
        async with async_session_maker() as session:
            assert (
                await session.scalar(
                    select(ResearchStageAttempt).where(ResearchStageAttempt.task_id == task.id)
                )
                is None
            )


@pytest.mark.asyncio
async def test_stage_completion_rechecks_lease_after_output_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lease expiring mid-completion rolls the receipt update back."""

    task, run = await _leased_context("complete-race", lease_delta=timedelta(minutes=5))
    attempts = ResearchStageAttemptService()
    attempt = await attempts.begin(
        task_id=task.id,
        lease_token=task.lease_token or "",
        stage="GENERATE",
        idempotency_key="complete-race",
        input_payload={"request_hash": run.request_hash},
    )
    output = await _bound_output(task, run, attempt)
    original_require_output = stage_attempt_module._require_bound_output_artifact

    async def expire_after_output_validation(session, current_task, current_attempt, artifact_id):
        await original_require_output(session, current_task, current_attempt, artifact_id)
        current_task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    monkeypatch.setattr(
        stage_attempt_module,
        "_require_bound_output_artifact",
        expire_after_output_validation,
    )

    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_LEASE_DENIED"):
        await attempts.complete(
            task_id=task.id,
            lease_token=task.lease_token or "",
            attempt_id=attempt.id,
            status="SUCCEEDED",
            output_artifact_id=output.id,
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchStageAttempt, attempt.id)
    assert stored is not None
    assert stored.status == "RUNNING"
    assert stored.output_artifact_id is None


@pytest.mark.asyncio
async def test_terminal_checkpoint_replay_remains_a_read_after_lease_expiry() -> None:
    """A completed receipt can be read idempotently without reviving the lease."""

    task, run = await _leased_context("terminal-replay", lease_delta=timedelta(minutes=5))
    attempts = ResearchStageAttemptService()
    attempt = await attempts.begin(
        task_id=task.id,
        lease_token=task.lease_token or "",
        stage="GENERATE",
        idempotency_key="terminal-replay",
        input_payload={"request_hash": run.request_hash},
    )
    output = await _bound_output(task, run, attempt)
    completed = await attempts.complete(
        task_id=task.id,
        lease_token=task.lease_token or "",
        attempt_id=attempt.id,
        status="SUCCEEDED",
        output_artifact_id=output.id,
    )
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        assert stored_task is not None
        stored_task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    replayed = await attempts.complete(
        task_id=task.id,
        lease_token=task.lease_token or "",
        attempt_id=attempt.id,
        status="SUCCEEDED",
        output_artifact_id=output.id,
    )

    assert replayed.id == completed.id
    assert replayed.status == "SUCCEEDED"


async def _leased_context(
    label: str, *, lease_delta: timedelta
) -> tuple[ResearchTask, ResearchRun]:
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id=f"stage-lease-clock-{label}",
        hypothesis_version_id=f"stage-lease-clock-hypothesis-{label}",
        promotion_policy_version="promotion-v1",
        request_hash="p" * 64,
        capability_profile_id="stage-lease-clock-profile",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id=f"stage-lease-clock-{label}",
    )
    task = ResearchTask(
        user_id=run.user_id,
        run_id="",
        status="RUNNING",
        stage_cursor="GENERATE",
        request_json={},
        idempotency_key=f"stage-lease-clock-{label}",
        idempotency_request_hash="i" * 64,
        lease_token=f"stage-lease-clock-token-{label}",
        lease_expires_at=now + lease_delta,
        lease_heartbeat_at=now,
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task.run_id = run.id
        session.add(task)
        await session.commit()
        await session.refresh(task)
        await session.refresh(run)
    return task, run


async def _bound_output(
    task: ResearchTask,
    run: ResearchRun,
    attempt: ResearchStageAttempt,
):
    return await ArtifactBroker().register_stage_output(
        context=StageExecutionContext(
            task_id=task.id,
            run_id=run.id,
            user_id=task.user_id,
            stage_attempt_id=attempt.id,
            lease_token=task.lease_token or "",
            stage=attempt.stage,
            request_hash=run.request_hash,
            trace_id=task.trace_id,
        ),
        kind="stage_lease_clock_receipt",
        content=f'{{"attempt_id":"{attempt.id}"}}',
        media_type="application/json",
        schema_version="test-v1",
        producer_identity="stage-lease-clock-test",
    )
