from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
)
from app.models.user import User
from app.services.research.artifact_broker import ArtifactBroker, ArtifactDescriptor
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.task_runner import DurableResearchTaskRunner
from app.services.research.workflow_worker import StageExecutionContext


@pytest.mark.asyncio
async def test_stage_attempt_is_lease_bound_idempotent_and_terminal_once(auth_user) -> None:
    user_id = await _user_id(auth_user)
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id="stage-attempt-hypothesis",
        dataset_snapshot_id="stage-attempt-dataset",
        experiment_epoch_id="stage-attempt-epoch",
        promotion_policy_version="promotion-v1",
        request_hash="p" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id="trace-stage-attempt",
    )
    task = ResearchTask(
        user_id=user_id,
        run_id="",
        status="RUNNING",
        stage_cursor="CLARIFY",
        request_json={},
        idempotency_key="task-stage-attempt",
        idempotency_request_hash="r" * 64,
        lease_token="lease-a",
        lease_expires_at=now + timedelta(minutes=5),
        lease_heartbeat_at=now,
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task.run_id = run.id
        session.add(task)
        await session.commit()
        await session.refresh(task)

    service = ResearchStageAttemptService()
    started = await service.begin(
        task_id=task.id,
        lease_token="lease-a",
        stage="GENERATE",
        idempotency_key="generate-1",
        input_payload={"prompt_hash": "p" * 64},
        now=now,
    )
    repeated = await service.begin(
        task_id=task.id,
        lease_token="lease-a",
        stage="GENERATE",
        idempotency_key="generate-1",
        input_payload={"prompt_hash": "p" * 64},
        now=now,
    )
    assert repeated.id == started.id
    assert started.attempt_no == 1
    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_IDEMPOTENCY_CONFLICT"):
        await service.begin(
            task_id=task.id,
            lease_token="lease-a",
            stage="GENERATE",
            idempotency_key="generate-1",
            input_payload={"prompt_hash": "q" * 64},
        )
    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_LEASE_DENIED"):
        await service.complete(
            task_id=task.id,
            lease_token="wrong",
            attempt_id=started.id,
            status="SUCCEEDED",
        )

    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_SUCCESS_ARTIFACT_REQUIRED"):
        await service.complete(
            task_id=task.id,
            lease_token="lease-a",
            attempt_id=started.id,
            status="SUCCEEDED",
        )
    output = await _bound_stage_output(
        task=task,
        attempt=started,
        lease_token="lease-a",
        request_hash=run.request_hash,
    )

    completed = await service.complete(
        task_id=task.id,
        lease_token="lease-a",
        attempt_id=started.id,
        status="SUCCEEDED",
        output_artifact_id=output.id,
        now=now + timedelta(seconds=2),
    )
    assert completed.status == "SUCCEEDED"
    assert completed.completed_at is not None
    same_terminal = await service.complete(
        task_id=task.id,
        lease_token="lease-a",
        attempt_id=started.id,
        status="SUCCEEDED",
        output_artifact_id=output.id,
    )
    assert same_terminal.id == started.id
    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_TERMINAL_CONFLICT"):
        await service.complete(
            task_id=task.id,
            lease_token="lease-a",
            attempt_id=started.id,
            status="FAILED",
        )

    async with async_session_maker() as session:
        stored = await session.scalar(
            select(ResearchStageAttempt).where(ResearchStageAttempt.id == started.id)
        )
        stored_task = await session.get(ResearchTask, task.id)
    assert stored is not None
    assert stored_task is not None
    assert stored_task.stage_cursor == "GENERATE"


@pytest.mark.asyncio
async def test_stage_attempt_refuses_new_side_effect_after_cancel_intent(auth_user) -> None:
    user_id = await _user_id(auth_user)
    now = datetime.now(timezone.utc)
    task = ResearchTask(
        user_id=user_id,
        run_id="run-cancelled-stage",
        status="RUNNING",
        stage_cursor="CLARIFY",
        request_json={},
        idempotency_key="task-cancelled-stage",
        idempotency_request_hash="r" * 64,
        cancel_requested_at=now,
        lease_token="lease-b",
        lease_expires_at=now + timedelta(minutes=5),
        lease_heartbeat_at=now,
    )
    async with async_session_maker() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)

    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_CANCEL_REQUESTED"):
        await ResearchStageAttemptService().begin(
            task_id=task.id,
            lease_token="lease-b",
            stage="SANDBOX",
            idempotency_key="cancelled-stage",
            input_payload={},
        )


@pytest.mark.asyncio
async def test_stage_attempt_success_rejects_existing_but_unbound_artifact(auth_user) -> None:
    """A successful output needs its exact durable stage binding, not just an ID."""

    user_id = await _user_id(auth_user)
    now = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id="bound-output-hypothesis",
        dataset_snapshot_id="bound-output-dataset",
        experiment_epoch_id="bound-output-epoch",
        promotion_policy_version="promotion-v1",
        request_hash="p" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id="trace-bound-output",
    )
    task = ResearchTask(
        user_id=user_id,
        run_id="",
        status="RUNNING",
        stage_cursor="CLARIFY",
        request_json={},
        idempotency_key="task-bound-output",
        idempotency_request_hash="r" * 64,
        lease_token="lease-bound-output",
        lease_expires_at=now + timedelta(minutes=5),
        lease_heartbeat_at=now,
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task.run_id = run.id
        session.add(task)
        await session.commit()
        await session.refresh(task)

    service = ResearchStageAttemptService()
    attempt = await service.begin(
        task_id=task.id,
        lease_token="lease-bound-output",
        stage="GENERATE",
        idempotency_key="bound-output-stage",
        input_payload={"request_hash": "p" * 64},
        now=now,
    )
    merely_registered = await ArtifactBroker().register(
        ArtifactDescriptor(
            kind="strategy_source",
            content_hash="a" * 64,
            storage_uri="controlled://remote-fixture/strategy.py",
            size_bytes=24,
            media_type="text/x-python",
            schema_version="v1",
            producer_identity="remote-fixture",
        )
    )

    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_ARTIFACT_BINDING_REQUIRED"):
        await service.complete(
            task_id=task.id,
            lease_token="lease-bound-output",
            attempt_id=attempt.id,
            status="SUCCEEDED",
            output_artifact_id=merely_registered.id,
            now=now + timedelta(seconds=1),
        )

    bound = await ArtifactBroker().register_stage_output(
        context=StageExecutionContext(
            task_id=task.id,
            run_id=task.run_id,
            user_id=user_id,
            stage_attempt_id=attempt.id,
            lease_token="lease-bound-output",
            stage="GENERATE",
            request_hash="p" * 64,
            trace_id=None,
        ),
        kind="strategy_source",
        content="def next(self):\n    pass\n",
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="deterministic-executor",
    )
    completed = await service.complete(
        task_id=task.id,
        lease_token="lease-bound-output",
        attempt_id=attempt.id,
        status="SUCCEEDED",
        output_artifact_id=bound.id,
        now=now + timedelta(seconds=2),
    )

    assert completed.status == "SUCCEEDED"
    assert completed.output_artifact_id == bound.id


@pytest.mark.asyncio
async def test_stage_attempt_failure_also_requires_a_bound_diagnostic_artifact(auth_user) -> None:
    """A failed receipt cannot attach an arbitrary descriptor merely for audit display."""

    user_id = await _user_id(auth_user)
    now = datetime.now(timezone.utc)
    task = ResearchTask(
        user_id=user_id,
        run_id="run-failed-diagnostic",
        status="RUNNING",
        stage_cursor="GENERATE",
        request_json={},
        idempotency_key="task-failed-diagnostic",
        idempotency_request_hash="r" * 64,
        lease_token="lease-failed-diagnostic",
        lease_expires_at=now + timedelta(minutes=5),
        lease_heartbeat_at=now,
    )
    async with async_session_maker() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)
    attempt = await ResearchStageAttemptService().begin(
        task_id=task.id,
        lease_token="lease-failed-diagnostic",
        stage="GENERATE",
        idempotency_key="failed-diagnostic-stage",
        input_payload={"request_hash": "p" * 64},
        now=now,
    )
    unbound = await ArtifactBroker().register(
        ArtifactDescriptor(
            kind="deterministic_generate_receipt",
            content_hash="d" * 64,
            storage_uri="controlled://remote-fixture/diagnostic.json",
            size_bytes=24,
            media_type="application/json",
            schema_version="v1",
            producer_identity="remote-fixture",
        )
    )

    with pytest.raises(ValueError, match="RESEARCH_STAGE_ATTEMPT_ARTIFACT_BINDING_REQUIRED"):
        await ResearchStageAttemptService().complete(
            task_id=task.id,
            lease_token="lease-failed-diagnostic",
            attempt_id=attempt.id,
            status="FAILED",
            output_artifact_id=unbound.id,
            error_code="RESEARCH_GENERATION_NOT_EXECUTED",
            now=now + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_stage_attempt_transitions_append_ordered_safe_events(auth_user) -> None:
    """Begin, complete, recovery, claim, and checkpoint resume share one event sequence."""

    user_id = await _user_id(auth_user)
    started_at = datetime.now(timezone.utc)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id="stage-event-hypothesis",
        promotion_policy_version="promotion-v1",
        request_hash="a" * 64,
        capability_profile_id="stage-event-profile",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id="trace-stage-events",
        status="RUNNING",
        started_at=started_at,
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task = ResearchTask(
            user_id=user_id,
            run_id=run.id,
            status="RUNNING",
            stage_cursor="CLARIFY",
            request_json={"raw": "not-in-event"},
            idempotency_key="task-stage-events",
            idempotency_request_hash="r" * 64,
            trace_id=run.trace_id,
            lease_token="lease-stage-events-1",
            lease_expires_at=started_at + timedelta(minutes=5),
            lease_heartbeat_at=started_at,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

    attempts = ResearchStageAttemptService()
    started = await attempts.begin(
        task_id=task.id,
        lease_token="lease-stage-events-1",
        stage="CLARIFY",
        idempotency_key="clarify-stage-events",
        input_payload={"question_hash": "q" * 64},
        now=started_at,
    )
    output = await _bound_stage_output(
        task=task,
        attempt=started,
        lease_token="lease-stage-events-1",
        request_hash=run.request_hash,
    )
    await attempts.complete(
        task_id=task.id,
        lease_token="lease-stage-events-1",
        attempt_id=started.id,
        status="SUCCEEDED",
        output_artifact_id=output.id,
        next_stage="GENERATE",
        now=started_at + timedelta(seconds=1),
    )
    same_terminal = await attempts.complete(
        task_id=task.id,
        lease_token="lease-stage-events-1",
        attempt_id=started.id,
        status="SUCCEEDED",
        output_artifact_id=output.id,
        next_stage="UNAPPROVED_CURSOR_CHANGE",
    )
    assert same_terminal.id == started.id
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
    assert stored_task is not None
    assert stored_run is not None
    assert stored_task.stage_cursor == "GENERATE"
    assert stored_run.stage_cursor == "GENERATE"

    recovery_time = started_at + timedelta(minutes=5, seconds=1)
    runner = DurableResearchTaskRunner(lease_seconds=60)
    assert await runner.recover_expired_leases(now=recovery_time) == 1
    claim = (await runner.claim_due(now=recovery_time + timedelta(seconds=1)))[0]
    assert claim.task_id == task.id
    assert await attempts.resume_succeeded_checkpoint(
        task_id=task.id,
        lease_token=claim.lease_token,
        stage="CLARIFY",
        next_stage="GENERATE",
    )

    async with async_session_maker() as session:
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == task.id)
                    .order_by(ResearchTaskEvent.sequence_no.asc())
                )
            ).scalars()
        )
    assert [event.sequence_no for event in events] == [1, 2, 3, 4, 5]
    assert [event.event_type for event in events] == [
        "STAGE_ATTEMPT_STARTED",
        "STAGE_ATTEMPT_COMPLETED",
        "TASK_LEASE_RECOVERED",
        "TASK_CLAIMED",
        "STAGE_CHECKPOINT_RESUMED",
    ]
    assert events[0].stage_attempt_id == started.id
    assert events[1].stage_attempt_id == started.id
    assert events[-1].stage_attempt_id == started.id


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())


async def _bound_stage_output(
    *,
    task: ResearchTask,
    attempt: ResearchStageAttempt,
    lease_token: str,
    request_hash: str,
):
    return await ArtifactBroker().register_stage_output(
        context=StageExecutionContext(
            task_id=task.id,
            run_id=task.run_id,
            user_id=task.user_id,
            stage_attempt_id=attempt.id,
            lease_token=lease_token,
            stage=attempt.stage,
            request_hash=request_hash,
            trace_id=task.trace_id,
        ),
        kind=f"test_{attempt.stage.lower()}_receipt",
        content=f'{{"attempt_id":"{attempt.id}","stage":"{attempt.stage}"}}',
        media_type="application/json",
        schema_version="test-v1",
        producer_identity="test-stage-executor",
    )
