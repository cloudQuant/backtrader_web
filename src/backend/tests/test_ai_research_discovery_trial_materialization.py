from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchDiscoveryExecution,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageArtifactBinding,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTrial,
)
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.discovery_execution_contract import DiscoveryExecutionResult
from app.services.research.discovery_trial_materialization import (
    DiscoveryTrialMaterializer,
    replay_discovery_publication,
)
from tests.test_ai_research_discovery_sandbox import (
    _discovery_context,
    _Remote,
    _service,
)


async def _publish(context, execution_id):
    async with database.async_session_maker() as session:
        publication = await DiscoveryTrialMaterializer(
            dataset_registry=context["datasets"]
        ).publish_in_session(
            session, context=context["discovery_context"], execution_id=execution_id
        )
        await session.commit()
        return publication


async def _completed_publication(auth_user, suffix):
    context = await _discovery_context(auth_user, suffix)
    dispatch = await _service(context, _Remote()).execute(context["discovery_context"])
    publication = await _publish(context, dispatch.journal_id)
    async with database.async_session_maker() as session:
        attempt = await session.get(
            ResearchStageAttempt, context["discovery_context"].stage_attempt_id
        )
        attempt.status = publication.status
        attempt.error_code = publication.error_code
        attempt.output_artifact_id = publication.output_artifact_id
        await session.commit()
    return context, dispatch, publication


async def _assert_replay_denied_without_publication(context, publication):
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["discovery_context"].task_id)
        run = await session.get(ResearchRun, context["discovery_context"].run_id)
        attempt = await session.get(
            ResearchStageAttempt, context["discovery_context"].stage_attempt_id
        )
        with pytest.raises(ValueError, match="^DISCOVERY_PUBLICATION_REPLAY_DENIED$"):
            await replay_discovery_publication(
                session,
                task=task,
                run=run,
                attempt=attempt,
                execution_id=publication.execution_id,
            )
    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        assert candidate.freeze_status == "MUTABLE"
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 1


@pytest.mark.asyncio
async def test_replay_rejects_current_run_capability_evidence_drift(auth_user):
    context, _, publication = await _completed_publication(
        auth_user, "replay-capability-drift"
    )
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["discovery_context"].run_id)
        run.capability_evidence_hash = "a" * 64
        await session.commit()

    await _assert_replay_denied_without_publication(context, publication)


@pytest.mark.asyncio
async def test_replay_rejects_current_candidate_hash_drift(auth_user):
    context, _, publication = await _completed_publication(
        auth_user, "replay-candidate-hash-drift"
    )
    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        candidate.candidate_hash = "d" * 64
        await session.commit()

    await _assert_replay_denied_without_publication(context, publication)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "drifted_value"),
    [
        ("snapshot_identity_hash", "a" * 64),
        ("object_receipt_id", "drifted-object-receipt"),
        ("object_digest", "b" * 64),
        ("object_size_bytes", 987654),
        ("execution_policy", {"price_adjustment": "drifted"}),
    ],
)
async def test_replay_rejects_current_dataset_identity_or_policy_drift(
    auth_user, field_name, drifted_value
):
    context, _, publication = await _completed_publication(
        auth_user, f"replay-dataset-{field_name}"
    )
    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
        setattr(dataset, field_name, drifted_value)
        await session.commit()

    await _assert_replay_denied_without_publication(context, publication)


@pytest.mark.asyncio
async def test_replay_rejects_attempt_bound_to_a_different_task(auth_user):
    context, _, publication = await _completed_publication(auth_user, "replay-attempt-task")
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["discovery_context"].task_id)
        other_task = ResearchTask(
            user_id=task.user_id,
            run_id=task.run_id,
            status="SUCCEEDED",
            stage_cursor="VALIDATE_DISCOVERY",
            request_json={},
            idempotency_key="replay-attempt-other-task",
            idempotency_request_hash="c" * 64,
        )
        session.add(other_task)
        await session.flush()
        attempt = await session.get(
            ResearchStageAttempt, context["discovery_context"].stage_attempt_id
        )
        attempt.task_id = other_task.id
        await session.commit()

    await _assert_replay_denied_without_publication(context, publication)


@pytest.mark.asyncio
async def test_journal_trial_and_retained_returns_are_linked_idempotently(auth_user):
    context = await _discovery_context(auth_user, "publish-success")
    remote = _Remote()
    dispatch = await _service(context, remote).execute(context["discovery_context"])
    publication = await _publish(context, dispatch.journal_id)
    repeated = await _publish(context, dispatch.journal_id)
    assert publication == repeated
    async with database.async_session_maker() as session:
        trial = await session.get(ResearchTrial, publication.trial_id)
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        content = await session.get(ResearchArtifactContent, publication.output_artifact_id)
        payload = json.loads(content.content)
        assert journal.trial_id == trial.id
        assert trial.status == "SUCCEEDED"
        assert trial.observed_market_performance is True
        assert trial.counts_as_market_trial is True
        assert trial.returns_artifact_id == publication.output_artifact_id
        assert payload["result"] == dispatch.result.snapshot
        assert payload["command_hash"] == dispatch.command.request_hash
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 1
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        assert candidate.freeze_status == "MUTABLE"
    assert len(remote.commands) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revocation", ["owner", "lease", "cancel", "quota", "fence", "result", "code", "allocation"]
)
async def test_publication_rejects_untrusted_or_revoked_evidence(auth_user, revocation):
    context = await _discovery_context(auth_user, f"publish-{revocation}")
    dispatch = await _service(context, _Remote()).execute(context["discovery_context"])
    if revocation == "owner":
        context["discovery_context"] = replace(context["discovery_context"], user_id="another-user")
    else:
        async with database.async_session_maker() as session:
            journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
            if revocation in {"lease", "cancel"}:
                task = await session.get(ResearchTask, journal.task_id)
                if revocation == "lease":
                    task.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                else:
                    task.cancel_requested_at = datetime.now(timezone.utc)
            elif revocation in {"quota", "fence"}:
                quota = await session.get(ResearchQuotaReservation, journal.quota_reservation_id)
                if revocation == "quota":
                    quota.status = "IN_FLIGHT"
                else:
                    quota.fencing_token += 1
            elif revocation == "result":
                journal.result_json = {**journal.result_json, "command_hash": "f" * 64}
            elif revocation == "allocation":
                journal.search_epoch_id = journal.search_ordinal = journal.search_budget_hash = None
            else:
                candidate = await session.get(ResearchCandidate, journal.candidate_id)
                content = await session.get(ResearchArtifactContent, candidate.code_artifact_id)
                content.content = b"tampered"
            await session.commit()
    with pytest.raises(ValueError):
        await _publish(context, dispatch.journal_id)
    async with database.async_session_maker() as session:
        assert await session.scalar(select(func.count(ResearchTrial.id))) == 0
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        assert journal.trial_id is None
        assert journal.status == "OBSERVED"


@pytest.mark.asyncio
@pytest.mark.parametrize("observed", [True, False])
async def test_failed_execution_counts_only_actual_observed_market_result(auth_user, observed):
    class FailedRunner(_Remote):
        async def run(self, command):
            result = await super().run(command)
            return DiscoveryExecutionResult.from_mapping(
                {
                    **result.snapshot,
                    "status": "FAILED",
                    "exit_code": 2,
                    "observed_market_performance": observed,
                    "returns": [-1.1, 0.01] if observed else [],
                    "error_code": "RUNNER_FAILED",
                },
                command=command,
            )

    context = await _discovery_context(auth_user, f"publish-failure-{observed}")
    dispatch = await _service(context, FailedRunner()).execute(context["discovery_context"])
    publication = await _publish(context, dispatch.journal_id)
    async with database.async_session_maker() as session:
        trial = await session.get(ResearchTrial, publication.trial_id)
        assert trial.status == "FAILED"
        assert trial.counts_as_market_trial is observed
        assert trial.observed_market_performance is observed
        assert publication.error_code == "RUNNER_FAILED"


@pytest.mark.asyncio
async def test_trial_artifact_and_journal_link_rollback_together(auth_user):
    context = await _discovery_context(auth_user, "publish-rollback")
    dispatch = await _service(context, _Remote()).execute(context["discovery_context"])
    async with database.async_session_maker() as session:
        publication = await DiscoveryTrialMaterializer(
            dataset_registry=context["datasets"]
        ).publish_in_session(
            session, context=context["discovery_context"], execution_id=dispatch.journal_id
        )
        await session.flush()
        assert await session.get(ResearchTrial, publication.trial_id) is not None
        await session.rollback()
    async with database.async_session_maker() as session:
        assert await session.get(ResearchTrial, publication.trial_id) is None
        assert await session.get(ResearchArtifactContent, publication.output_artifact_id) is None
        assert (
            await session.scalar(
                select(ResearchStageArtifactBinding).where(
                    ResearchStageArtifactBinding.stage_attempt_id
                    == context["discovery_context"].stage_attempt_id
                )
            )
            is None
        )
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        assert journal.trial_id is None
        assert journal.status == "OBSERVED"


@contextmanager
def _row_lock_order(engine):
    """Observe actual executed SQLAlchemy row-lock intent (SQLite omits SQL FOR UPDATE)."""
    tables = []

    def before_execute(connection, clause, multiparams, params, options):
        if getattr(clause, "_for_update_arg", None) is not None:
            tables.extend(
                description["entity"].__tablename__
                for description in clause.column_descriptions
                if description.get("entity") is not None
            )

    event.listen(engine, "before_execute", before_execute)
    try:
        yield tables
    finally:
        event.remove(engine, "before_execute", before_execute)


@pytest.mark.asyncio
async def test_publication_preserves_existing_broker_task_before_run_lock_order(auth_user):
    context = await _discovery_context(auth_user, "publish-lock-order")
    dispatch = await _service(context, _Remote()).execute(context["discovery_context"])
    async with database.async_session_maker() as session:
        with _row_lock_order(session.bind.sync_engine) as order:
            await DiscoveryTrialMaterializer(
                dataset_registry=context["datasets"]
            ).publish_in_session(
                session, context=context["discovery_context"], execution_id=dispatch.journal_id
            )
        assert order.index("ai_research_tasks") < order.index("ai_research_runs")
        await session.rollback()


@pytest.mark.asyncio
async def test_freeze_takes_epoch_before_candidate_to_match_publication(auth_user):
    context = await _discovery_context(auth_user, "freeze-lock-order")
    dispatch = await _service(context, _Remote()).execute(context["discovery_context"])
    await _publish(context, dispatch.journal_id)
    async with database.async_session_maker() as session:
        with _row_lock_order(session.bind.sync_engine) as order:
            await CandidateRegistry(dataset_registry=context["datasets"]).freeze(
                context["discovery_context"].user_id,
                context["candidate_id"],
                frozen_by="researcher",
                expected_candidate_hash=dispatch.command.snapshot["candidate_hash"],
            )
        assert order.index("ai_research_experiment_epochs") < order.index("ai_research_candidates")
