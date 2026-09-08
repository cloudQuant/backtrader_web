"""Worker orchestration tests for durable protocol-v2 research tasks."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import database
from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchExperimentEpoch,
    ResearchGenerationMaterialization,
    ResearchModelInvocation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
)
from app.models.user import User
from app.services.research.artifact_broker import ArtifactBroker
from app.services.research.canonical import content_hash
from app.services.research.database_clock import database_utc_now
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.generation_materialization import (
    GenerationMaterializationPolicy,
    GenerationMaterializationProposal,
    ResearchGenerationMaterializer,
)
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.task_runner import DurableResearchTaskRunner
from app.services.research.workflow_worker import (
    ResearchProtocolWorker,
    StageExecutionContext,
    StageExecutionOutcome,
    run_research_protocol_worker,
)


@pytest.mark.asyncio
async def test_worker_rejects_terminal_success_without_candidate_contract(auth_user) -> None:
    """A generic bound receipt cannot make GENERATE look like a valid strategy."""

    task = await _queued_task(await _user_id(auth_user))
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(lease_seconds=60),
        executors={
            "CLARIFY": _StageExecutor(next_stage="GENERATE"),
            "GENERATE": _StageExecutor(next_stage=None),
        },
    )

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].status == "FAILED"
    assert results[0].error_code == "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
        attempts = list(
            (
                await session.execute(
                    select(ResearchStageAttempt)
                    .where(ResearchStageAttempt.task_id == task.id)
                    .order_by(ResearchStageAttempt.attempt_no.asc())
                )
            ).scalars()
        )
    assert stored_task is not None
    assert stored_run is not None
    assert stored_task.status == "FAILED"
    assert stored_task.stage_cursor == "GENERATE"
    assert stored_task.error_code == "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"
    assert stored_run.status == "FAILED"
    assert [attempt.stage for attempt in attempts] == ["CLARIFY", "GENERATE"]
    assert [attempt.status for attempt in attempts] == ["SUCCEEDED", "FAILED"]
    assert attempts[-1].error_code == "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"
    assert all(attempt.lease_token is not None for attempt in attempts)


@pytest.mark.asyncio
async def test_worker_atomically_materializes_a_typed_generate_proposal(auth_user) -> None:
    """Only a fenced model invocation can make terminal GENERATE succeed."""

    user_id = await _user_id(auth_user)
    task, invocation, model_output, datasets = await _generation_queued_task(user_id)
    materializer = ResearchGenerationMaterializer(
        policy=GenerationMaterializationPolicy(
            version="workflow-generation-policy-v1",
            environment_manifest={
                "runtime": "python-3.10",
                "strategy_api": "backtrader-v1",
                "base_image": "sha256:" + "a" * 64,
            },
        ),
        dataset_registry=datasets,
    )
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(lease_seconds=60),
        stage_attempts=ResearchStageAttemptService(generation_materializer=materializer),
        executors={
            "CLARIFY": _StageExecutor(next_stage="GENERATE"),
            "GENERATE": _TypedGenerateExecutor(
                GenerationMaterializationProposal(
                    model_invocation_id=invocation.id,
                    model_output=model_output,
                )
            ),
        },
    )

    results = await worker.run_once()

    assert [(result.status, result.error_code) for result in results] == [("SUCCEEDED", None)]
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
        attempts = list(
            (
                await session.execute(
                    select(ResearchStageAttempt)
                    .where(ResearchStageAttempt.task_id == task.id)
                    .order_by(ResearchStageAttempt.attempt_no.asc())
                )
            ).scalars()
        )
        materialization = await session.scalar(
            select(ResearchGenerationMaterialization).where(
                ResearchGenerationMaterialization.task_id == task.id
            )
        )
        candidate = (
            await session.get(ResearchCandidate, materialization.candidate_id)
            if materialization is not None
            else None
        )

    assert stored_task is not None
    assert stored_run is not None
    assert stored_task.status == "SUCCEEDED"
    assert stored_run.status == "SUCCEEDED"
    assert [attempt.stage for attempt in attempts] == ["CLARIFY", "GENERATE"]
    assert [attempt.status for attempt in attempts] == ["SUCCEEDED", "SUCCEEDED"]
    assert materialization is not None
    assert materialization.model_invocation_id == invocation.id
    assert candidate is not None
    assert candidate.freeze_status == "MUTABLE"
    assert attempts[-1].output_artifact_id == materialization.manifest_artifact_id


@pytest.mark.asyncio
async def test_worker_fails_closed_when_no_stage_executor_is_registered(auth_user) -> None:
    """Queued research cannot silently become a successful generated strategy."""

    task = await _queued_task(await _user_id(auth_user))
    worker = ResearchProtocolWorker(task_runner=DurableResearchTaskRunner(lease_seconds=60))

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].status == "FAILED"
    assert results[0].error_code == "RESEARCH_STAGE_EXECUTOR_UNAVAILABLE"
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
        attempt = await session.scalar(
            select(ResearchStageAttempt).where(ResearchStageAttempt.task_id == task.id)
        )
    assert stored_task is not None
    assert stored_run is not None
    assert attempt is not None
    assert stored_task.status == "FAILED"
    assert stored_task.error_code == "RESEARCH_STAGE_EXECUTOR_UNAVAILABLE"
    assert stored_run.status == "FAILED"
    assert attempt.status == "FAILED"
    assert attempt.error_code == "RESEARCH_STAGE_EXECUTOR_UNAVAILABLE"


def test_successful_stage_outcome_requires_a_controlled_output_artifact() -> None:
    """An executor cannot label a stage successful without a durable receipt."""

    with pytest.raises(ValueError, match="RESEARCH_STAGE_OUTCOME_OUTPUT_ARTIFACT_REQUIRED"):
        StageExecutionOutcome.succeeded(next_stage="GENERATE").validate()


@pytest.mark.asyncio
async def test_worker_rejects_success_without_a_controlled_output_artifact(auth_user) -> None:
    """A missing receipt must fail the task rather than synthesize research success."""

    task = await _queued_task(await _user_id(auth_user))
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(lease_seconds=60),
        executors={
            "CLARIFY": _UnboundSuccessExecutor(next_stage="GENERATE"),
            "GENERATE": _StageExecutor(next_stage=None),
        },
    )

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].status == "FAILED"
    assert results[0].error_code == "RESEARCH_STAGE_OUTPUT_ARTIFACT_REQUIRED"
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
    assert stored_task is not None
    assert stored_run is not None
    assert stored_task.status == "FAILED"
    assert stored_task.error_code == "RESEARCH_STAGE_OUTPUT_ARTIFACT_REQUIRED"
    assert stored_run.status == "FAILED"


@pytest.mark.asyncio
async def test_worker_closes_an_inflight_stage_as_cancelled_when_cancel_arrives_after_execution(
    auth_user,
) -> None:
    """Cancellation wins without leaving a completed stage attempt RUNNING."""

    user_id = await _user_id(auth_user)
    task = await _queued_task(user_id)
    runner = DurableResearchTaskRunner(lease_seconds=60)
    worker = ResearchProtocolWorker(
        task_runner=runner,
        executors={"CLARIFY": _CancellingExecutor(runner=runner, user_id=user_id)},
    )

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].status == "CANCELLED"
    assert results[0].error_code == "TASK_CANCEL_REQUESTED"
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
        attempt = await session.scalar(
            select(ResearchStageAttempt).where(ResearchStageAttempt.task_id == task.id)
        )
    assert stored_task is not None
    assert stored_run is not None
    assert attempt is not None
    assert stored_task.status == "CANCELLED"
    assert stored_run.status == "CANCELLED"
    assert attempt.status == "CANCELLED"
    assert attempt.error_code == "TASK_CANCEL_REQUESTED"


@pytest.mark.asyncio
async def test_worker_recovery_does_not_replay_a_completed_stage(auth_user) -> None:
    """A replacement lease continues after a durable successful checkpoint."""

    task = await _queued_task(await _user_id(auth_user))
    runner = DurableResearchTaskRunner(lease_seconds=60)
    async with async_session_maker() as session:
        start = await database_utc_now(session)
    claim = (await runner.claim_due(now=start))[0]
    attempts = ResearchStageAttemptService()
    completed = await attempts.begin(
        task_id=task.id,
        lease_token=claim.lease_token,
        stage="CLARIFY",
        idempotency_key="completed-before-crash",
        input_payload={"stage": "CLARIFY"},
    )
    receipt = await _test_stage_artifact(
        StageExecutionContext(
            task_id=task.id,
            run_id=task.run_id,
            user_id=task.user_id,
            stage_attempt_id=completed.id,
            lease_token=claim.lease_token,
            stage="CLARIFY",
            request_hash="a" * 64,
            trace_id=task.trace_id,
        )
    )
    await attempts.complete(
        task_id=task.id,
        lease_token=claim.lease_token,
        attempt_id=completed.id,
        status="SUCCEEDED",
        output_artifact_id=receipt.id,
    )
    assert await runner.recover_expired_leases(now=start + timedelta(seconds=61)) == 1

    calls: list[str] = []
    worker = ResearchProtocolWorker(
        task_runner=runner,
        executors={
            "CLARIFY": _RecordingStageExecutor(calls, next_stage="GENERATE"),
            "GENERATE": _RecordingStageExecutor(calls, next_stage=None),
        },
    )

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].error_code == "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"
    assert results[0].status == "FAILED"
    assert calls == ["GENERATE"]
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
    assert stored_task is not None
    assert stored_run is not None
    assert stored_task.stage_cursor == "GENERATE"
    assert stored_run.stage_cursor == "GENERATE"


@pytest.mark.asyncio
async def test_worker_recovery_rejects_a_legacy_success_checkpoint_without_receipt(
    auth_user,
) -> None:
    """Lease takeover must not advance an old success row that has no bound output."""

    task = await _queued_task(await _user_id(auth_user))
    runner = DurableResearchTaskRunner(lease_seconds=60)
    async with async_session_maker() as session:
        start = await database_utc_now(session)
    claim = (await runner.claim_due(now=start))[0]
    attempts = ResearchStageAttemptService()
    checkpoint = await attempts.begin(
        task_id=task.id,
        lease_token=claim.lease_token,
        stage="CLARIFY",
        idempotency_key="legacy-unbound-checkpoint",
        input_payload={"stage": "CLARIFY"},
    )
    async with async_session_maker() as session:
        stored_checkpoint = await session.get(ResearchStageAttempt, checkpoint.id)
        assert stored_checkpoint is not None
        stored_checkpoint.status = "SUCCEEDED"
        stored_checkpoint.completed_at = start + timedelta(seconds=1)
        await session.commit()
    assert await runner.recover_expired_leases(now=start + timedelta(seconds=61)) == 1

    calls: list[str] = []
    worker = ResearchProtocolWorker(
        task_runner=runner,
        executors={
            "CLARIFY": _RecordingStageExecutor(calls, next_stage="GENERATE"),
            "GENERATE": _RecordingStageExecutor(calls, next_stage=None),
        },
    )

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].status == "FAILED"
    assert results[0].error_code == "RESEARCH_STAGE_CHECKPOINT_FAILED"
    assert calls == []


@pytest.mark.asyncio
async def test_worker_rejects_an_unapproved_stage_transition(auth_user) -> None:
    """An executor cannot bypass the server-owned v2 workflow graph."""

    task = await _queued_task(await _user_id(auth_user))
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(lease_seconds=60),
        executors={"CLARIFY": _StageExecutor(next_stage="SEALED_EVALUATE")},
    )

    results = await worker.run_once()

    assert len(results) == 1
    assert results[0].status == "FAILED"
    assert results[0].error_code == "RESEARCH_STAGE_TRANSITION_INVALID"
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
        stored_run = await session.get(ResearchRun, task.run_id)
    assert stored_task is not None
    assert stored_run is not None
    assert stored_task.status == "FAILED"
    assert stored_run.status == "FAILED"


def test_discovery_execution_outcome_is_an_id_only_typed_proposal() -> None:
    """A discovery executor cannot smuggle an artifact or a graph transition."""

    succeeded = StageExecutionOutcome.discovered("discovery-execution-id")
    succeeded.validate()
    assert succeeded.status == "SUCCEEDED"
    assert succeeded.discovery_execution_id == "discovery-execution-id"
    assert succeeded.next_stage is None
    assert succeeded.output_artifact_id is None
    assert succeeded.generation_proposal is None

    timed_out = StageExecutionOutcome.discovered(
        "discovery-execution-id",
        status="TIMED_OUT",
    )
    timed_out.validate()
    assert timed_out.error_code == "RESEARCH_DISCOVERY_EXECUTION_TIMED_OUT"

    with pytest.raises(ValueError, match="RESEARCH_DISCOVERY_PROPOSAL_ARTIFACT_FORBIDDEN"):
        StageExecutionOutcome(
            status="SUCCEEDED",
            discovery_execution_id="discovery-execution-id",
            output_artifact_id="forged-artifact",
        ).validate()


@pytest.mark.asyncio
async def test_generation_only_worker_does_not_claim_a_discovery_workflow_task(auth_user) -> None:
    """An older deployment leaves a newer run queued for its compatible worker."""

    task = await _queued_task(
        await _user_id(auth_user),
        workflow_version="discovery-v1",
    )
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(lease_seconds=60),
        executors={
            "CLARIFY": _StageExecutor(next_stage="GENERATE"),
            "GENERATE": _StageExecutor(next_stage=None),
        },
    )

    assert await worker.run_once() == []
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)
    assert stored_task is not None
    assert stored_task.status == "QUEUED"
    assert stored_task.lease_token is None


@pytest.mark.asyncio
async def test_discovery_worker_routes_only_by_the_persisted_server_workflow(auth_user) -> None:
    """Typed GENERATE and discovery receipts cannot choose their own successor."""

    await _queued_task(
        await _user_id(auth_user),
        workflow_version="discovery-v1",
    )
    checkpoints = _WorkflowCheckpointRecorder()
    generated = GenerationMaterializationProposal(
        model_invocation_id="workflow-generated-invocation",
        model_output='{"schema_version":"research-generation-v1"}',
    )
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(
            lease_seconds=60,
            workflow_versions=("discovery-v1",),
        ),
        stage_attempts=checkpoints,
        workflow_versions=("discovery-v1",),
        executors={
            "CLARIFY": _FixedOutcomeExecutor(
                StageExecutionOutcome.succeeded(
                    next_stage="GENERATE",
                    output_artifact_id="clarify-receipt",
                )
            ),
            "GENERATE": _FixedOutcomeExecutor(StageExecutionOutcome.generated(proposal=generated)),
            "VALIDATE_DISCOVERY": _FixedOutcomeExecutor(
                StageExecutionOutcome.discovered("discovery-execution-id")
            ),
        },
    )

    results = await worker.run_once()

    assert [(result.status, result.error_code) for result in results] == [("SUCCEEDED", None)]
    assert [item["stage"] for item in checkpoints.inputs] == [
        "CLARIFY",
        "GENERATE",
        "VALIDATE_DISCOVERY",
    ]
    assert {item["workflow_version"] for item in checkpoints.inputs} == {"discovery-v1"}
    assert [item["next_stage"] for item in checkpoints.completions] == [
        "GENERATE",
        "VALIDATE_DISCOVERY",
        None,
    ]
    assert checkpoints.completions[1]["generation_proposal"] == generated
    assert checkpoints.completions[2]["discovery_execution_id"] == "discovery-execution-id"


@pytest.mark.asyncio
async def test_discovery_worker_persists_an_observed_terminal_failure_before_failing_task(
    auth_user,
) -> None:
    """A timeout receipt remains available for trial accounting before task finalization."""

    await _queued_task(
        await _user_id(auth_user),
        workflow_version="discovery-v1",
    )
    checkpoints = _WorkflowCheckpointRecorder()
    generated = GenerationMaterializationProposal(
        model_invocation_id="workflow-generated-invocation",
        model_output='{"schema_version":"research-generation-v1"}',
    )
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(
            lease_seconds=60,
            workflow_versions=("discovery-v1",),
        ),
        stage_attempts=checkpoints,
        workflow_versions=("discovery-v1",),
        executors={
            "CLARIFY": _FixedOutcomeExecutor(
                StageExecutionOutcome.succeeded(
                    next_stage="GENERATE",
                    output_artifact_id="clarify-receipt",
                )
            ),
            "GENERATE": _FixedOutcomeExecutor(StageExecutionOutcome.generated(proposal=generated)),
            "VALIDATE_DISCOVERY": _FixedOutcomeExecutor(
                StageExecutionOutcome.discovered(
                    "discovery-execution-id",
                    status="TIMED_OUT",
                    error_code="RUNNER_TIMEOUT",
                )
            ),
        },
    )

    results = await worker.run_once()

    assert [(result.status, result.error_code) for result in results] == [
        ("FAILED", "RUNNER_TIMEOUT")
    ]
    assert checkpoints.completions[-1]["status"] == "TIMED_OUT"
    assert checkpoints.completions[-1]["discovery_execution_id"] == "discovery-execution-id"


@pytest.mark.asyncio
async def test_discovery_worker_rejects_a_generic_generate_success(auth_user) -> None:
    """A discovery graph may not replace typed generation provenance with an artifact."""

    await _queued_task(
        await _user_id(auth_user),
        workflow_version="discovery-v1",
    )
    checkpoints = _WorkflowCheckpointRecorder()
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(
            lease_seconds=60,
            workflow_versions=("discovery-v1",),
        ),
        stage_attempts=checkpoints,
        workflow_versions=("discovery-v1",),
        executors={
            "CLARIFY": _FixedOutcomeExecutor(
                StageExecutionOutcome.succeeded(
                    next_stage="GENERATE",
                    output_artifact_id="clarify-receipt",
                )
            ),
            "GENERATE": _FixedOutcomeExecutor(
                StageExecutionOutcome.succeeded(
                    next_stage="VALIDATE_DISCOVERY",
                    output_artifact_id="unproven-generated-artifact",
                )
            ),
            "VALIDATE_DISCOVERY": _FixedOutcomeExecutor(
                StageExecutionOutcome.discovered("discovery-execution-id")
            ),
        },
    )

    results = await worker.run_once()

    assert [(result.status, result.error_code) for result in results] == [
        ("FAILED", "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE")
    ]
    assert [item["stage"] for item in checkpoints.inputs] == ["CLARIFY", "GENERATE"]
    assert checkpoints.completions[-1]["status"] == "FAILED"
    assert checkpoints.completions[-1]["output_artifact_id"] == "unproven-generated-artifact"


@pytest.mark.asyncio
async def test_discovery_worker_rejects_a_generic_validation_success(auth_user) -> None:
    """A final discovery artifact cannot stand in for a verified journal execution ID."""

    await _queued_task(
        await _user_id(auth_user),
        workflow_version="discovery-v1",
    )
    checkpoints = _WorkflowCheckpointRecorder()
    generated = GenerationMaterializationProposal(
        model_invocation_id="workflow-generated-invocation",
        model_output='{"schema_version":"research-generation-v1"}',
    )
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(
            lease_seconds=60,
            workflow_versions=("discovery-v1",),
        ),
        stage_attempts=checkpoints,
        workflow_versions=("discovery-v1",),
        executors={
            "CLARIFY": _FixedOutcomeExecutor(
                StageExecutionOutcome.succeeded(
                    next_stage="GENERATE",
                    output_artifact_id="clarify-receipt",
                )
            ),
            "GENERATE": _FixedOutcomeExecutor(StageExecutionOutcome.generated(proposal=generated)),
            "VALIDATE_DISCOVERY": _FixedOutcomeExecutor(
                StageExecutionOutcome.succeeded(
                    output_artifact_id="unverified-discovery-artifact",
                )
            ),
        },
    )

    results = await worker.run_once()

    assert [(result.status, result.error_code) for result in results] == [
        ("FAILED", "RESEARCH_DISCOVERY_CONTRACT_UNAVAILABLE")
    ]
    assert [item["stage"] for item in checkpoints.inputs] == [
        "CLARIFY",
        "GENERATE",
        "VALIDATE_DISCOVERY",
    ]
    assert checkpoints.completions[-1]["status"] == "FAILED"
    assert checkpoints.completions[-1]["output_artifact_id"] == "unverified-discovery-artifact"


@pytest.mark.asyncio
async def test_worker_heartbeats_a_live_lease_until_stage_execution_finishes(
    independent_worker_database, monkeypatch
) -> None:
    """A slow, valid executor cannot silently let its task lease expire."""

    user_id, sessions = independent_worker_database
    task = await _queued_task(user_id, sessions=sessions)
    runner = DurableResearchTaskRunner(lease_seconds=60)
    heartbeats: list[tuple[str, str]] = []
    heartbeat_completed = asyncio.Event()
    original_heartbeat = runner.heartbeat

    async def record_heartbeat(task_id: str, lease_token: str, **kwargs) -> bool:
        renewed = await original_heartbeat(task_id, lease_token, **kwargs)
        if renewed:
            heartbeats.append((task_id, lease_token))
            heartbeat_completed.set()
        return renewed

    monkeypatch.setattr(runner, "heartbeat", record_heartbeat)
    executor = _BlockingStageExecutor()
    worker = ResearchProtocolWorker(
        task_runner=runner,
        executors={"CLARIFY": executor, "GENERATE": executor},
        heartbeat_interval_seconds=0.01,
    )

    running = asyncio.create_task(worker.run_once())
    try:
        await asyncio.wait_for(executor.started.wait(), timeout=5)
        await asyncio.wait_for(heartbeat_completed.wait(), timeout=5)
        assert heartbeats
    finally:
        executor.release.set()
    results = await asyncio.wait_for(running, timeout=5)

    assert results[0].status == "FAILED"
    assert results[0].error_code == "RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"
    assert {task_id for task_id, _lease_token in heartbeats} == {task.id}
    async with sessions() as session:
        stored_task = await session.get(ResearchTask, task.id)
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == task.id)
                    .order_by(ResearchTaskEvent.sequence_no)
                )
            ).scalars()
        )
    assert stored_task is not None
    assert stored_task.event_sequence == 6
    assert [event.sequence_no for event in events] == list(range(1, 7))
    assert [event.event_type for event in events] == [
        "TASK_CLAIMED",
        "STAGE_ATTEMPT_STARTED",
        "STAGE_ATTEMPT_COMPLETED",
        "STAGE_ATTEMPT_STARTED",
        "STAGE_ATTEMPT_COMPLETED",
        "TASK_FINALIZED",
    ]


@pytest.fixture
async def independent_worker_database(
    auth_user, monkeypatch, tmp_path
) -> AsyncIterator[tuple[str, async_sessionmaker[AsyncSession]]]:
    """Give concurrent heartbeats and checkpoints independent DB transactions.

    The shared test StaticPool lends the same in-memory connection to every
    AsyncSession. One session's rollback can then undo another's allocation,
    or its commit can persist another's partial write. A file database with
    NullPool preserves transaction isolation while retaining real SQL writes.
    """

    user_id = await _user_id(auth_user)
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        session.expunge(user)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'worker-heartbeat.db'}",
        poolclass=NullPool,
        connect_args={"timeout": 30},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(database.Base.metadata.create_all)
        async with sessions() as session:
            await session.merge(user)
            await session.commit()
        with monkeypatch.context() as local_patch:
            local_patch.setattr(database, "async_session_maker", sessions)
            yield user_id, sessions
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_external_worker_loop_polls_until_its_deployment_stop_signal() -> None:
    """The API process can delegate lifecycle control to a separate worker host."""

    worker = _PollingWorker()
    stop = asyncio.Event()
    running = asyncio.create_task(
        run_research_protocol_worker(
            worker,
            stop_event=stop,
            poll_interval_seconds=0.01,
        )
    )

    await asyncio.wait_for(worker.second_poll.wait(), timeout=1)
    stop.set()
    await asyncio.wait_for(running, timeout=1)

    assert worker.calls == 2


@pytest.mark.asyncio
async def test_external_worker_loop_rejects_incomplete_executor_registration(auth_user) -> None:
    """A deployment mistake must not convert queued work into synthetic failures."""

    task = await _queued_task(await _user_id(auth_user))
    worker = ResearchProtocolWorker(
        task_runner=DurableResearchTaskRunner(lease_seconds=60),
        executors={"CLARIFY": _StageExecutor(next_stage="GENERATE")},
    )

    with pytest.raises(ValueError, match="RESEARCH_WORKER_EXECUTORS_INCOMPLETE"):
        await asyncio.wait_for(
            run_research_protocol_worker(
                worker,
                stop_event=asyncio.Event(),
                poll_interval_seconds=0.01,
            ),
            timeout=0.05,
        )
    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, task.id)

    assert stored_task is not None
    assert stored_task.status == "QUEUED"
    assert stored_task.lease_token is None


@dataclass(frozen=True, slots=True)
class _StageExecutor:
    next_stage: str | None

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        assert context.stage in {"CLARIFY", "GENERATE"}
        assert context.task_id
        assert context.lease_token
        return await _test_succeeded_outcome(context, next_stage=self.next_stage)


@dataclass(frozen=True, slots=True)
class _UnboundSuccessExecutor:
    next_stage: str | None

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        del context
        return StageExecutionOutcome.succeeded(next_stage=self.next_stage)


class _RecordingStageExecutor:
    def __init__(self, calls: list[str], *, next_stage: str | None) -> None:
        self._calls = calls
        self._next_stage = next_stage

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        self._calls.append(context.stage)
        return await _test_succeeded_outcome(context, next_stage=self._next_stage)


@dataclass(frozen=True, slots=True)
class _FixedOutcomeExecutor:
    outcome: StageExecutionOutcome

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        del context
        return self.outcome


class _WorkflowCheckpointRecorder:
    """In-memory stage boundary double for graph routing only.

    Root-owned stage-attempt integration separately verifies the journal/trial
    transaction.  This double makes the worker's graph selection observable
    without weakening those persistence fences.
    """

    def __init__(self) -> None:
        self.inputs: list[dict[str, object]] = []
        self.completions: list[dict[str, object]] = []

    async def begin(self, **kwargs):
        self.inputs.append(dict(kwargs["input_payload"]))
        return SimpleNamespace(id=f"checkpoint-{len(self.inputs)}")

    async def complete(self, **kwargs):
        self.completions.append(dict(kwargs))
        return SimpleNamespace(status=kwargs["status"], error_code=kwargs.get("error_code"))

    async def resume_succeeded_checkpoint(self, **kwargs) -> bool:
        del kwargs
        return False


@dataclass(frozen=True, slots=True)
class _TypedGenerateExecutor:
    """A test-only executor that cannot pick the persisted output artifact."""

    proposal: GenerationMaterializationProposal

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        assert context.stage == "GENERATE"
        return StageExecutionOutcome.generated(proposal=self.proposal)


class _BlockingStageExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        if context.stage == "CLARIFY":
            self.started.set()
            await self.release.wait()
            return await _test_succeeded_outcome(context, next_stage="GENERATE")
        return await _test_succeeded_outcome(context, next_stage=None)


class _PollingWorker:
    def __init__(self) -> None:
        self.calls = 0
        self.second_poll = asyncio.Event()

    async def run_once(self) -> list[object]:
        self.calls += 1
        if self.calls == 2:
            self.second_poll.set()
        return []


@dataclass(frozen=True, slots=True)
class _CancellingExecutor:
    runner: DurableResearchTaskRunner
    user_id: str

    async def execute(self, context: StageExecutionContext) -> StageExecutionOutcome:
        assert await self.runner.request_cancel(self.user_id, context.task_id)
        return StageExecutionOutcome.failed("TASK_CANCEL_REQUESTED")


async def _test_succeeded_outcome(
    context: StageExecutionContext,
    *,
    next_stage: str | None,
) -> StageExecutionOutcome:
    artifact = await _test_stage_artifact(context)
    return StageExecutionOutcome.succeeded(
        next_stage=next_stage,
        output_artifact_id=artifact.id,
    )


async def _test_stage_artifact(context: StageExecutionContext):
    return await ArtifactBroker().register_stage_output(
        context=context,
        kind=f"test_{context.stage.lower()}_receipt",
        content=(
            '{"attempt_id":"' + context.stage_attempt_id + '","stage":"' + context.stage + '"}'
        ),
        media_type="application/json",
        schema_version="test-v1",
        producer_identity="test-stage-executor",
    )


async def _queued_task(
    user_id: str,
    *,
    sessions: async_sessionmaker[AsyncSession] | None = None,
    workflow_version: str = "generation-v1",
) -> ResearchTask:
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id="workflow-hypothesis",
        dataset_snapshot_id="workflow-dataset",
        experiment_epoch_id="workflow-epoch",
        workflow_version=workflow_version,
        promotion_policy_version="promotion-v1",
        request_hash="a" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="b" * 64,
        trace_id="trace-workflow-worker",
    )
    async with (sessions or async_session_maker)() as session:
        session.add(run)
        await session.flush()
        task = ResearchTask(
            user_id=user_id,
            run_id=run.id,
            status="QUEUED",
            stage_cursor="CLARIFY",
            request_json={"hypothesis_content_hash": "a" * 64},
            idempotency_key=f"workflow-worker-{run.id}",
            idempotency_request_hash="c" * 64,
            trace_id=run.trace_id,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


async def _generation_queued_task(
    user_id: str,
) -> tuple[ResearchTask, ResearchModelInvocation, str, DatasetRegistry]:
    """Build server-bound inputs required by typed terminal generation."""

    hypothesis = await HypothesisRegistry().create_draft(user_id, _generation_hypothesis_payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id,
        hypothesis.id,
        request_hash=hypothesis.content_hash,
    )
    resolver = InMemoryDatasetObjectResolver()
    attestation = resolver.register(
        DatasetObjectAttestation(
            receipt_id="workflow-generation-dataset-receipt",
            user_id=user_id,
            logical_object_id="workflow-generation-dataset",
            object_version="v1",
            object_digest="d" * 64,
            object_size_bytes=4096,
            storage_uri="controlled://workflow-generation/discovery.parquet",
            attested_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
    )
    datasets = DatasetRegistry(object_resolver=resolver)
    dataset = await datasets.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=attestation.receipt_id,
        dataset_policy_version="generation-policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2024-01-01", "end": "2024-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open", "commission_bps": 2.0, "slippage_bps": 1.0},
        point_in_time_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    model_output = json.dumps(
        {
            "schema_version": "research-generation-v1",
            "strategy_code": "class Strategy:\n    def next(self):\n        return None\n",
            "dependency_lock": "backtrader==1.9.78.123\n",
            "params": {"lookback": 20},
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="generation-policy-v1",
        status="OPEN",
    )
    async with async_session_maker() as session:
        session.add(epoch)
        await session.flush()
        run = ResearchRun(
            user_id=user_id,
            hypothesis_version_id=hypothesis.id,
            dataset_snapshot_id=dataset.id,
            experiment_epoch_id=epoch.id,
            promotion_policy_version="promotion-v1",
            request_hash="g" * 64,
            capability_profile_id="dev-single-process",
            capability_profile_version="v1",
            capability_evidence_hash="e" * 64,
            trace_id="trace-workflow-generation",
        )
        session.add(run)
        await session.flush()
        task = ResearchTask(
            user_id=user_id,
            run_id=run.id,
            status="QUEUED",
            stage_cursor="CLARIFY",
            request_json={"hypothesis_content_hash": hypothesis.content_hash},
            idempotency_key=f"workflow-generation-{run.id}",
            idempotency_request_hash="i" * 64,
            trace_id=run.trace_id,
        )
        invocation = ResearchModelInvocation(
            run_id=run.id,
            provider="test-provider",
            requested_model="research-default",
            resolved_model="test-model-v1",
            provider_request_id="workflow-generation-provider-id",
            prompt_template_version="generation-v1",
            system_input_hash="s" * 64,
            input_hash="i" * 64,
            output_hash=content_hash({"output": model_output}),
            sampling_params={"temperature": 0.1},
            tool_manifest=[],
            origin="LLM",
            transformation_chain=["typed_gateway"],
            fallback_chain=[],
            token_usage={"total": 10},
            cost={"usd": 0.001},
        )
        session.add_all([task, invocation])
        await session.commit()
        await session.refresh(task)
        await session.refresh(invocation)
        return task, invocation, model_output, datasets


def _generation_hypothesis_payload() -> dict[str, object]:
    return {
        "research_question": "成本与滑点后，趋势信号是否仍有可检验优势？",
        "economic_mechanism": "趋势持续由信息扩散与风险补偿共同驱动。",
        "asset_scope": {"symbols": ["RB0"], "asset_class": "futures"},
        "frequency": "1d",
        "time_window": {"start": "2022-01-01", "end": "2025-12-31"},
        "information_cutoff": "2025-12-31T00:00:00Z",
        "cost_model": {"commission_bps": 2.0, "slippage_bps": 1.0},
        "execution_model": {"fill": "next_bar_open"},
        "primary_metric": "deflated_sharpe",
        "secondary_metrics": ["max_drawdown", "turnover"],
        "capacity_assumptions": {"max_participation_rate": 0.1},
        "falsification_criteria": {"max_drawdown": 0.2},
        "search_space": {"lookback": [10, 20]},
        "max_budget": {"max_trials": 20},
        "dataset_policy_version": "generation-policy-v1",
    }


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())
