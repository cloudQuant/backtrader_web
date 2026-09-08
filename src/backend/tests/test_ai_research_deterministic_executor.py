"""Truth-label contracts for the protocol-v2 deterministic fallback stages."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchModelInvocation,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.models.user import User
from app.research_deployments.explorer import create_worker
from app.services.research.database_clock import database_utc_now
from app.services.research.deterministic_executor import DeterministicClarifyExecutor
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.workflow_worker import StageExecutionContext, StageExecutionOutcome


@pytest.mark.asyncio
async def test_clarify_executor_writes_a_bound_no_model_receipt(auth_user) -> None:
    """A deterministic fallback is durable and explicitly says no model was called."""

    context = await _stage_context(auth_user, stage="CLARIFY")

    outcome = await DeterministicClarifyExecutor().execute(context)

    assert outcome.status == "SUCCEEDED"
    assert outcome.next_stage == "GENERATE"
    assert outcome.output_artifact_id is not None
    async with async_session_maker() as session:
        content = await session.scalar(
            select(ResearchArtifactContent.content).where(
                ResearchArtifactContent.artifact_id == outcome.output_artifact_id
            )
        )
    assert content is not None
    receipt = json.loads(content)
    assert receipt["stage"] == "CLARIFY"
    assert receipt["origin"] == "deterministic_template"
    assert receipt["model_invocation_id"] is None
    assert receipt["model_call"] == "NOT_CALLED"
    assert receipt["execution_state"] == "NOT_EXECUTED"
    assert receipt["transformation_chain"] == ["receipt_persisted"]
    assert receipt["fallback_chain"] == [
        "deterministic_factory_selected",
        "model_provider_not_invoked",
    ]
    assert receipt["run_id"] == context.run_id
    assert receipt["request_hash"] == context.request_hash


@pytest.mark.asyncio
async def test_opt_in_factory_retains_no_model_receipt_but_fails_unmaterialized_generation(
    auth_user,
) -> None:
    """A receipt without a strategy candidate is a failed generation, not a research success."""

    user_id = await _user_id(auth_user)
    task = await _queued_task(user_id)

    results = await create_worker().run_once()

    assert [(result.task_id, result.status, result.error_code) for result in results] == [
        (task.id, "FAILED", "RESEARCH_GENERATION_NOT_EXECUTED")
    ]
    async with async_session_maker() as session:
        attempts = list(
            (
                await session.execute(
                    select(ResearchStageAttempt)
                    .where(ResearchStageAttempt.task_id == task.id)
                    .order_by(ResearchStageAttempt.attempt_no.asc())
                )
            ).scalars()
        )
        bindings = list(
            (
                await session.execute(
                    select(ResearchStageArtifactBinding).where(
                        ResearchStageArtifactBinding.task_id == task.id
                    )
                )
            ).scalars()
        )
        candidates = list(
            (
                await session.execute(
                    select(ResearchCandidate).where(ResearchCandidate.run_id == task.run_id)
                )
            ).scalars()
        )
        invocations = list(
            (
                await session.execute(
                    select(ResearchModelInvocation).where(
                        ResearchModelInvocation.run_id == task.run_id
                    )
                )
            ).scalars()
        )
        trials = list(
            (
                await session.execute(
                    select(ResearchTrial).where(ResearchTrial.run_id == task.run_id)
                )
            ).scalars()
        )
    assert [attempt.stage for attempt in attempts] == ["CLARIFY", "GENERATE"]
    assert [attempt.status for attempt in attempts] == ["SUCCEEDED", "FAILED"]
    assert all(attempt.output_artifact_id for attempt in attempts)
    assert {binding.stage_attempt_id for binding in bindings} == {
        attempt.id for attempt in attempts
    }
    assert candidates == []
    assert invocations == []
    assert trials == []


def test_failed_stage_outcome_can_retain_a_bound_diagnostic_receipt() -> None:
    """Fail-closed terminal status must not force loss of an auditable local receipt."""

    outcome = StageExecutionOutcome.failed(
        "RESEARCH_GENERATION_NOT_EXECUTED",
        output_artifact_id="receipt-artifact-id",
    )

    assert outcome.status == "FAILED"
    assert outcome.error_code == "RESEARCH_GENERATION_NOT_EXECUTED"
    assert outcome.output_artifact_id == "receipt-artifact-id"


async def _stage_context(auth_user, *, stage: str) -> StageExecutionContext:
    user_id = await _user_id(auth_user)
    async with async_session_maker() as session:
        now = await database_utc_now(session)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=f"deterministic-{stage.lower()}-hypothesis",
        dataset_snapshot_id=f"deterministic-{stage.lower()}-dataset",
        experiment_epoch_id=f"deterministic-{stage.lower()}-epoch",
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id="trace-deterministic",
    )
    task = ResearchTask(
        user_id=user_id,
        run_id="",
        status="RUNNING",
        stage_cursor=stage,
        request_json={},
        idempotency_key=f"deterministic-{stage.lower()}-task",
        idempotency_request_hash="r" * 64,
        lease_token=f"deterministic-{stage.lower()}-lease",
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
    attempt = await ResearchStageAttemptService().begin(
        task_id=task.id,
        lease_token=task.lease_token or "",
        stage=stage,
        idempotency_key=f"deterministic-{stage.lower()}-attempt",
        input_payload={"request_hash": "r" * 64},
        now=now,
    )
    return StageExecutionContext(
        task_id=task.id,
        run_id=task.run_id,
        user_id=user_id,
        stage_attempt_id=attempt.id,
        lease_token=task.lease_token or "",
        stage=stage,
        request_hash="r" * 64,
        trace_id="trace-deterministic",
    )


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
    return str(result.scalar_one())


async def _queued_task(user_id: str) -> ResearchTask:
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id="deterministic-hypothesis",
        dataset_snapshot_id="deterministic-dataset",
        experiment_epoch_id="deterministic-epoch",
        promotion_policy_version="promotion-v1",
        request_hash="d" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="e" * 64,
        trace_id="trace-deterministic-worker",
    )
    async with async_session_maker() as session:
        session.add(run)
        await session.flush()
        task = ResearchTask(
            user_id=user_id,
            run_id=run.id,
            status="QUEUED",
            stage_cursor="CLARIFY",
            request_json={"hypothesis_content_hash": "d" * 64},
            idempotency_key=f"deterministic-worker-{run.id}",
            idempotency_request_hash="f" * 64,
            trace_id=run.trace_id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
    return task
