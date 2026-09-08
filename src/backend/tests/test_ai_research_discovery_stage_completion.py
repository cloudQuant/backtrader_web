"""A discovery stage can complete only with its atomically published execution."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchDiscoveryExecution,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
    ResearchTrial,
)
from app.services.research.artifact_broker import ArtifactBroker
from app.services.research.discovery_execution_contract import DiscoveryExecutionResult
from app.services.research.discovery_trial_materialization import DiscoveryTrialMaterializer
from app.services.research.stage_attempt import ResearchStageAttemptService
from tests.test_ai_research_discovery_sandbox import _discovery_context, _Remote, _service


@pytest.mark.asyncio
async def test_discovery_checkpoint_rejects_arbitrary_artifact_without_execution(auth_user):
    context = await _discovery_context(auth_user, "stage-unproven-artifact")
    stage_context = context["discovery_context"]
    artifact = await ArtifactBroker().register_stage_output(
        context=stage_context,
        kind="diagnostic",
        content="not a market execution",
        media_type="text/plain",
        schema_version="v1",
        producer_identity="fixture",
    )
    with pytest.raises(ValueError, match="RESEARCH_DISCOVERY_CONTRACT_UNAVAILABLE"):
        await ResearchStageAttemptService().complete(
            task_id=stage_context.task_id,
            lease_token=stage_context.lease_token,
            attempt_id=stage_context.stage_attempt_id,
            status="SUCCEEDED",
            output_artifact_id=artifact.id,
        )


@pytest.mark.asyncio
async def test_new_graph_generation_rejects_generic_success_even_with_correct_successor(auth_user):
    from tests.test_ai_research_generation_materialization import _context

    context = await _context(auth_user, suffix="stage-generic-generate")
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["run"].id)
        run.workflow_version = "discovery-v1"
        await session.commit()
    artifact = await ArtifactBroker().register_stage_output(
        context=context["stage_context"],
        kind="diagnostic",
        content="not generation evidence",
        media_type="text/plain",
        schema_version="v1",
        producer_identity="fixture",
    )
    with pytest.raises(ValueError, match="RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"):
        await ResearchStageAttemptService().complete(
            task_id=context["task"].id,
            lease_token=context["task"].lease_token,
            attempt_id=context["attempt"].id,
            status="SUCCEEDED",
            next_stage="VALIDATE_DISCOVERY",
            output_artifact_id=artifact.id,
        )
    # Recovery must not adopt an old/corrupt generic checkpoint either.
    async with database.async_session_maker() as session:
        attempt = await session.get(ResearchStageAttempt, context["attempt"].id)
        attempt.status = "SUCCEEDED"
        attempt.output_artifact_id = artifact.id
        await session.commit()
    with pytest.raises(ValueError, match="RESEARCH_GENERATION_CONTRACT_UNAVAILABLE"):
        await ResearchStageAttemptService().resume_succeeded_checkpoint(
            task_id=context["task"].id,
            lease_token=context["task"].lease_token,
            stage="GENERATE",
            next_stage="VALIDATE_DISCOVERY",
        )


async def _ready(
    auth_user,
    suffix,
    remote=None,
    *,
    capability_profile_id=None,
    capability_profile_version=None,
    capability_evidence_hash=None,
):
    context = await _discovery_context(auth_user, suffix)
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["discovery_context"].run_id)
        run.workflow_version = "discovery-v1"
        if capability_profile_id is not None:
            run.capability_profile_id = capability_profile_id
        if capability_profile_version is not None:
            run.capability_profile_version = capability_profile_version
        if capability_evidence_hash is not None:
            run.capability_evidence_hash = capability_evidence_hash
        await session.commit()
    dispatch = await _service(context, remote or _Remote()).execute(context["discovery_context"])
    service = ResearchStageAttemptService(
        discovery_materializer=DiscoveryTrialMaterializer(dataset_registry=context["datasets"])
    )
    args = {
        "task_id": context["discovery_context"].task_id,
        "lease_token": context["discovery_context"].lease_token,
        "attempt_id": context["discovery_context"].stage_attempt_id,
        "status": dispatch.result.snapshot["status"],
        "error_code": dispatch.result.snapshot["error_code"],
        "discovery_execution_id": dispatch.journal_id,
    }
    return context, dispatch, service, args


@pytest.mark.asyncio
async def test_discovery_publication_and_checkpoint_commit_once_then_recover(auth_user):
    context, dispatch, service, args = await _ready(auth_user, "stage-atomic")
    first = await service.complete(**args)
    repeated = await service.complete(**args)
    assert first.id == repeated.id
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        trial = await session.get(ResearchTrial, journal.trial_id)
        assert first.status == trial.status == "SUCCEEDED"
        assert first.output_artifact_id == trial.returns_artifact_id
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 1
        assert (
            await session.scalar(
                select(func.count(ResearchTaskEvent.id)).where(
                    ResearchTaskEvent.stage_attempt_id == first.id,
                    ResearchTaskEvent.event_type == "STAGE_ATTEMPT_COMPLETED",
                )
            )
            == 1
        )
        task = await session.get(ResearchTask, args["task_id"])
        task.lease_token = "recovered-discovery-worker"
        await session.commit()
    assert await service.resume_succeeded_checkpoint(
        task_id=args["task_id"],
        lease_token="recovered-discovery-worker",
        stage="VALIDATE_DISCOVERY",
        next_stage=None,
    )
    async with database.async_session_maker() as session:
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 1
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        trial = await session.get(ResearchTrial, journal.trial_id)
        trial.counts_as_market_trial = False
        await session.commit()
    with pytest.raises(ValueError, match="DISCOVERY_PUBLICATION_REPLAY_DENIED"):
        await service.resume_succeeded_checkpoint(
            task_id=args["task_id"],
            lease_token="recovered-discovery-worker",
            stage="VALIDATE_DISCOVERY",
            next_stage=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["event", "status", "expired"])
async def test_failed_checkpoint_commit_leaves_observed_journal_but_no_partial_trial(
    auth_user,
    monkeypatch,
    failure,
):
    context, dispatch, service, args = await _ready(auth_user, f"stage-rollback-{failure}")
    if failure == "event":

        async def unavailable(*args, **kwargs):
            raise RuntimeError("event-storage-unavailable")

        monkeypatch.setattr(
            "app.services.research.stage_attempt.append_research_task_event", unavailable
        )
        expected, message = RuntimeError, "event-storage-unavailable"
    elif failure == "status":
        args["status"] = "FAILED"
        expected, message = ValueError, "RESEARCH_DISCOVERY_RESULT_TRANSITION_CONFLICT"
    else:
        async with database.async_session_maker() as session:
            task = await session.get(ResearchTask, args["task_id"])
            task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await session.commit()
        expected, message = ValueError, "RESEARCH_STAGE_ATTEMPT_LEASE_DENIED"
    with pytest.raises(expected, match=message):
        await service.complete(**args)
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        attempt = await session.get(ResearchStageAttempt, args["attempt_id"])
        assert journal.status == "OBSERVED" and journal.trial_id is None
        assert attempt.status == "RUNNING" and attempt.output_artifact_id is None
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 0
        assert (
            await session.scalar(
                select(func.count(ResearchStageArtifactBinding.id)).where(
                    ResearchStageArtifactBinding.stage_attempt_id == attempt.id
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_cancel_race_closes_stage_without_publishing_market_evidence(auth_user):
    context, dispatch, service, args = await _ready(auth_user, "stage-cancel")
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, args["task_id"])
        task.cancel_requested_at = datetime.now(timezone.utc)
        await session.commit()
    attempt = await service.complete(**args)
    assert attempt.status == "CANCELLED" and attempt.error_code == "TASK_CANCEL_REQUESTED"
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        assert journal.status == "OBSERVED" and journal.trial_id is None
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 0


@pytest.mark.asyncio
async def test_observed_failed_execution_is_counted_before_failed_stage_commits(auth_user):
    class FailedRunner(_Remote):
        async def run(self, command):
            result = await super().run(command)
            return DiscoveryExecutionResult.from_mapping(
                {
                    **result.snapshot,
                    "status": "FAILED",
                    "exit_code": 2,
                    "error_code": "RUNNER_FAILED",
                },
                command=command,
            )

    context, dispatch, service, args = await _ready(auth_user, "stage-failed", FailedRunner())
    attempt = await service.complete(**args)
    repeated = await service.complete(**args)
    assert repeated.id == attempt.id
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        trial = await session.get(ResearchTrial, journal.trial_id)
        assert attempt.status == trial.status == "FAILED"
        assert trial.counts_as_market_trial is True
        assert attempt.output_artifact_id == trial.returns_artifact_id


@pytest.mark.asyncio
async def test_discovery_completion_locks_task_before_run_before_attempt(auth_user):
    from tests.test_ai_research_discovery_trial_materialization import _row_lock_order

    context, dispatch, service, args = await _ready(auth_user, "stage-lock-order")
    async with database.async_session_maker() as session:
        with _row_lock_order(session.bind.sync_engine) as order:
            await service.complete(**args)
    assert order.index("ai_research_tasks") < order.index("ai_research_runs")
    assert order.index("ai_research_runs") < order.index("ai_research_stage_attempts")


@pytest.mark.asyncio
async def test_typed_generation_advances_only_persisted_server_graph(auth_user):
    from app.services.research.generation_materialization import GenerationMaterializationProposal
    from tests.test_ai_research_generation_materialization import _context, _materializer

    context = await _context(auth_user, suffix="stage-generation-discovery")
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["run"].id)
        run.workflow_version = "discovery-v1"
        await session.commit()
    service = ResearchStageAttemptService(generation_materializer=_materializer(context))
    args = {
        "task_id": context["task"].id,
        "lease_token": context["task"].lease_token,
        "attempt_id": context["attempt"].id,
        "status": "SUCCEEDED",
        "generation_proposal": GenerationMaterializationProposal(
            model_invocation_id=context["invocation"].id,
            model_output=context["model_output"],
        ),
    }
    with pytest.raises(ValueError, match="RESEARCH_GENERATION_PROPOSAL_TRANSITION_INVALID"):
        await service.complete(**args, next_stage=None)
    async with database.async_session_maker() as session:
        with _write_lock_order(session.bind.sync_engine) as order:
            attempt = await service.complete(**args, next_stage="VALIDATE_DISCOVERY")
    assert order.index("ai_research_experiment_epochs") < order.index("ai_research_tasks")
    assert attempt.status == "SUCCEEDED"
    assert await service.resume_succeeded_checkpoint(
        task_id=context["task"].id,
        lease_token=context["task"].lease_token,
        stage="GENERATE",
        next_stage="VALIDATE_DISCOVERY",
    )
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        run = await session.get(ResearchRun, context["run"].id)
        assert task.stage_cursor == run.stage_cursor == "VALIDATE_DISCOVERY"


@contextmanager
def _write_lock_order(engine):
    order = []

    def before_execute(connection, clause, multiparams, params, options):
        if getattr(clause, "is_update", False):
            order.append(clause.table.name)
        elif getattr(clause, "_for_update_arg", None) is not None:
            order.extend(
                item["entity"].__tablename__
                for item in clause.column_descriptions
                if item.get("entity") is not None
            )

    event.listen(engine, "before_execute", before_execute)
    try:
        yield order
    finally:
        event.remove(engine, "before_execute", before_execute)
