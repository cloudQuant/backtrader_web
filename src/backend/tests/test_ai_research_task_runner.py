from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects import mysql, postgresql

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchExperimentEpoch,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
)
from app.models.user import User
from app.services.research import task_runner as task_runner_module
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.data_precheck import ResearchDataPrecheckService
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.task_runner import (
    DurableResearchTaskRunner,
    ResearchTaskService,
    append_research_task_event,
)


def test_mysql_dialect_selects_the_non_returning_event_allocator() -> None:
    """The dialect gate cannot emit unsupported UPDATE ... RETURNING for MySQL."""

    class _Session:
        def get_bind(self):
            return type("Bind", (), {"dialect": mysql.dialect()})()

    assert task_runner_module._supports_update_returning(_Session()) is False


def test_recovery_locks_only_task_rows_while_filtering_versioned_runs() -> None:
    """The recovery filter must not invert the established task-then-run lock order."""

    statement = task_runner_module._expired_task_selection(
        workflow_versions=("generation-v1",),
        recovery_time=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "JOIN ai_research_runs" in compiled
    assert "FOR UPDATE OF ai_research_tasks" in compiled
    assert "FOR UPDATE OF ai_research_runs" not in compiled


@pytest.mark.asyncio
async def test_submit_idempotency_creates_one_run_and_one_task_under_concurrency(auth_user) -> None:
    context = await _context(await _user_id(auth_user))
    service = _task_service(context)
    request = {
        "hypothesis_content_hash": context["hypothesis"].content_hash,
        "dataset_snapshot_id": context["dataset"].id,
        "experiment_epoch_id": context["epoch"].id,
    }

    submissions = await asyncio.gather(
        *(
            service.submit(
                user_id=context["user_id"],
                hypothesis_version_id=context["hypothesis"].id,
                dataset_snapshot_id=context["dataset"].id,
                experiment_epoch_id=context["epoch"].id,
                profile_id="dev-single-process",
                profile_version="v1",
                promotion_policy_version="promotion-v1",
                request_json=request,
                precheck_id=context["precheck"].id,
                idempotency_key="same-submit",
            )
            for _ in range(20)
        )
    )

    assert len({submission.task.id for submission in submissions}) == 1
    assert len({submission.run.id for submission in submissions}) == 1
    async with async_session_maker() as session:
        task_count = await session.scalar(select(func.count(ResearchTask.id)))
        run_count = await session.scalar(select(func.count(ResearchRun.id)))
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == submissions[0].task.id)
                    .order_by(ResearchTaskEvent.sequence_no.asc())
                )
            ).scalars()
        )
    assert task_count == 1
    assert run_count == 1
    assert [(event.sequence_no, event.event_type) for event in events] == [(1, "TASK_SUBMITTED")]

    with pytest.raises(ValueError, match="RESEARCH_TASK_IDEMPOTENCY_CONFLICT"):
        await service.submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json={**request, "requested_limit": 99},
            precheck_id=context["precheck"].id,
            idempotency_key="same-submit",
        )


def test_task_service_rejects_an_unknown_server_workflow_version() -> None:
    """A caller cannot create a run for a graph the server does not own."""

    with pytest.raises(ValueError, match="RESEARCH_WORKFLOW_VERSION_INVALID"):
        ResearchTaskService(workflow_version="caller-selected-v999")


@pytest.mark.asyncio
async def test_submit_takes_epoch_write_fence_before_creating_family_work(auth_user) -> None:
    """Freeze and submit must serialize on the same database epoch row."""

    context = await _context(await _user_id(auth_user))
    operations: list[tuple[str, str]] = []

    def record_operation(_conn, clause, _multiparams, _params, _options):
        table = getattr(clause, "table", None)
        table_name = getattr(table, "name", None)
        operation = getattr(clause, "__visit_name__", None)
        if table_name and operation in {"update", "insert"}:
            operations.append((operation, table_name))

    async with async_session_maker() as session:
        engine = session.bind.sync_engine
    event.listen(engine, "before_execute", record_operation)
    try:
        await _task_service(context).submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json={
                "hypothesis_content_hash": context["hypothesis"].content_hash,
                "dataset_snapshot_id": context["dataset"].id,
                "experiment_epoch_id": context["epoch"].id,
            },
            precheck_id=context["precheck"].id,
            idempotency_key="epoch-write-fence",
        )
    finally:
        event.remove(engine, "before_execute", record_operation)

    epoch_fence = operations.index(("update", "ai_research_experiment_epochs"))
    run_insert = operations.index(("insert", "ai_research_runs"))
    assert epoch_fence < run_insert


@pytest.mark.asyncio
async def test_submit_persists_only_the_server_selected_workflow_version(auth_user) -> None:
    """A request payload and a later idempotency replay cannot rewrite a run graph."""

    context = await _context(await _user_id(auth_user))
    request = {
        "hypothesis_content_hash": context["hypothesis"].content_hash,
        "dataset_snapshot_id": context["dataset"].id,
        "experiment_epoch_id": context["epoch"].id,
        # It is ordinary request evidence, never authority for the server graph.
        "workflow_version": "discovery-v1",
    }
    precheck = await context["prechecks"].create(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request,
    )
    precheck_input_hash = precheck.input_hash
    generation = ResearchTaskService(
        data_prechecks=context["prechecks"], workflow_version="generation-v1"
    )
    original = await generation.submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request,
        precheck_id=precheck.id,
        idempotency_key="server-selected-workflow",
    )

    replay = await ResearchTaskService(
        data_prechecks=context["prechecks"], workflow_version="discovery-v1"
    ).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request,
        precheck_id=precheck.id,
        idempotency_key="server-selected-workflow",
    )

    assert original.run.workflow_version == "generation-v1"
    assert original.task.request_json == request
    assert replay.run.id == original.run.id
    assert replay.task.id == original.task.id
    assert replay.run.workflow_version == "generation-v1"
    assert precheck.input_hash == precheck_input_hash


@pytest.mark.asyncio
async def test_task_runner_claims_and_recovers_only_its_protocol_v2_workflow_versions(
    auth_user,
) -> None:
    """A generation worker cannot lease or recover discovery or legacy work."""

    context = await _context(await _user_id(auth_user))
    request = {
        "hypothesis_content_hash": context["hypothesis"].content_hash,
        "dataset_snapshot_id": context["dataset"].id,
        "experiment_epoch_id": context["epoch"].id,
    }

    async def submit(version: str, idempotency_key: str):
        return await ResearchTaskService(
            data_prechecks=context["prechecks"], workflow_version=version
        ).submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json=request,
            precheck_id=context["precheck"].id,
            idempotency_key=idempotency_key,
        )

    generation = await submit("generation-v1", "generation-only-task")
    discovery = await submit("discovery-v1", "discovery-only-task")
    legacy = await submit("generation-v1", "legacy-protocol-task")
    async with async_session_maker() as session:
        legacy_run = await session.get(ResearchRun, legacy.run.id)
        assert legacy_run is not None
        legacy_run.protocol_version = "v1"
        await session.commit()

    start = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    generation_runner = DurableResearchTaskRunner(lease_seconds=60)
    discovery_runner = DurableResearchTaskRunner(
        lease_seconds=60,
        workflow_versions=("discovery-v1",),
    )
    generation_claims = await generation_runner.claim_due(now=start)
    discovery_claims = await discovery_runner.claim_due(now=start)

    assert [claim.task_id for claim in generation_claims] == [generation.task.id]
    assert [claim.task_id for claim in discovery_claims] == [discovery.task.id]
    async with async_session_maker() as session:
        legacy_task = await session.get(ResearchTask, legacy.task.id)
        assert legacy_task is not None
        assert legacy_task.status == "QUEUED"
        assert legacy_task.lease_token is None

    recovery_time = start + timedelta(seconds=61)
    assert await generation_runner.recover_expired_leases(now=recovery_time) == 1
    async with async_session_maker() as session:
        stored_generation = await session.get(ResearchTask, generation.task.id)
        stored_discovery = await session.get(ResearchTask, discovery.task.id)
    assert stored_generation is not None
    assert stored_discovery is not None
    assert stored_generation.status == "QUEUED"
    assert stored_discovery.status == "RUNNING"
    assert await discovery_runner.recover_expired_leases(now=recovery_time) == 1


@pytest.mark.asyncio
async def test_event_append_allocates_sequence_from_database_not_a_stale_task_snapshot(
    auth_user,
) -> None:
    """A stale task object cannot reuse an already committed event sequence."""

    context = await _context(await _user_id(auth_user))
    submission = await _task_service(context).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json={
            "hypothesis_content_hash": context["hypothesis"].content_hash,
            "dataset_snapshot_id": context["dataset"].id,
            "experiment_epoch_id": context["epoch"].id,
        },
        precheck_id=context["precheck"].id,
        idempotency_key="stale-event-sequence",
    )
    async with async_session_maker() as session:
        stale_task = await session.get(ResearchTask, submission.task.id)
        assert stale_task is not None
        session.expunge(stale_task)

    async with async_session_maker() as session:
        current_task = await session.get(ResearchTask, submission.task.id)
        assert current_task is not None
        await append_research_task_event(session, current_task, event_type="CURRENT_EVENT")
        await session.commit()

    async with async_session_maker() as session:
        await append_research_task_event(session, stale_task, event_type="STALE_EVENT")
        await session.commit()

    async with async_session_maker() as session:
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == submission.task.id)
                    .order_by(ResearchTaskEvent.sequence_no.asc())
                )
            ).scalars()
        )
        stored_task = await session.get(ResearchTask, submission.task.id)
    assert stored_task is not None
    assert stored_task.event_sequence == 3
    assert [(event.sequence_no, event.event_type) for event in events] == [
        (1, "TASK_SUBMITTED"),
        (2, "CURRENT_EVENT"),
        (3, "STALE_EVENT"),
    ]


@pytest.mark.asyncio
async def test_event_append_uses_locking_fallback_without_update_returning(
    auth_user, monkeypatch
) -> None:
    """A MySQL-style dialect keeps event allocation safe without RETURNING."""

    monkeypatch.setattr(task_runner_module, "_supports_update_returning", lambda _session: False)
    context = await _context(await _user_id(auth_user))
    submission = await _task_service(context).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json={
            "hypothesis_content_hash": context["hypothesis"].content_hash,
            "dataset_snapshot_id": context["dataset"].id,
            "experiment_epoch_id": context["epoch"].id,
        },
        precheck_id=context["precheck"].id,
        idempotency_key="locking-event-sequence",
    )
    async with async_session_maker() as session:
        task = await session.get(ResearchTask, submission.task.id)
        assert task is not None
        await append_research_task_event(session, task, event_type="LOCKING_EVENT")
        await session.commit()

    async with async_session_maker() as session:
        stored_task = await session.get(ResearchTask, submission.task.id)
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == submission.task.id)
                    .order_by(ResearchTaskEvent.sequence_no.asc())
                )
            ).scalars()
        )
    assert stored_task is not None
    assert stored_task.event_sequence == 2
    assert [(event.sequence_no, event.event_type) for event in events] == [
        (1, "TASK_SUBMITTED"),
        (2, "LOCKING_EVENT"),
    ]


@pytest.mark.asyncio
async def test_two_workers_claim_once_and_cancel_wins_terminal_transition(auth_user) -> None:
    context = await _context(await _user_id(auth_user))
    submission = await _task_service(context).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json={
            "hypothesis_content_hash": context["hypothesis"].content_hash,
            "dataset_snapshot_id": context["dataset"].id,
            "experiment_epoch_id": context["epoch"].id,
        },
        precheck_id=context["precheck"].id,
        idempotency_key="claim-once",
    )
    first = DurableResearchTaskRunner(lease_seconds=60)
    second = DurableResearchTaskRunner(lease_seconds=60)

    claims = await first.claim_due()
    assert len(claims) == 1
    assert await second.claim_due() == []
    claim = claims[0]
    async with async_session_maker() as session:
        run = await session.get(ResearchRun, submission.run.id)
        task = await session.get(ResearchTask, claim.task_id)
    assert run is not None
    assert task is not None
    assert task.run_id == run.id
    assert task.status == "RUNNING"
    assert run.status == "RUNNING"
    assert run.started_at is not None
    assert await first.heartbeat(claim.task_id, claim.lease_token) is True
    assert await first.request_cancel(context["user_id"], claim.task_id) is True
    completed = await first.finalize(claim.task_id, claim.lease_token, status="SUCCEEDED")

    assert completed is not None
    assert completed.status == "CANCELLED"
    async with async_session_maker() as session:
        run = await session.get(ResearchRun, submission.run.id)
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == submission.task.id)
                    .order_by(ResearchTaskEvent.sequence_no.asc())
                )
            ).scalars()
        )
    assert run is not None
    assert run.status == "CANCELLED"
    assert run.completed_at is not None
    assert [event.sequence_no for event in events] == [1, 2, 3, 4]
    assert [event.event_type for event in events] == [
        "TASK_SUBMITTED",
        "TASK_CLAIMED",
        "TASK_CANCEL_REQUESTED",
        "TASK_FINALIZED",
    ]
    assert events[-1].status == "CANCELLED"
    assert await second.finalize(claim.task_id, "wrong-token", status="SUCCEEDED") is None


@pytest.mark.asyncio
async def test_queued_cancel_is_terminal_before_a_worker_can_claim(auth_user) -> None:
    context = await _context(await _user_id(auth_user))
    submission = await _task_service(context).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json={
            "hypothesis_content_hash": context["hypothesis"].content_hash,
            "dataset_snapshot_id": context["dataset"].id,
            "experiment_epoch_id": context["epoch"].id,
        },
        precheck_id=context["precheck"].id,
        idempotency_key="cancel-queued",
    )
    runner = DurableResearchTaskRunner()

    assert await runner.request_cancel(context["user_id"], submission.task.id) is True
    assert await runner.claim_due() == []
    async with async_session_maker() as session:
        task = await session.get(ResearchTask, submission.task.id)
        run = await session.get(ResearchRun, submission.run.id)
    assert task is not None
    assert run is not None
    assert task.status == "CANCELLED"
    assert task.completed_at is not None
    assert run.status == "CANCELLED"
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_expired_lease_requeues_an_unstarted_task_for_a_new_fenced_worker(auth_user) -> None:
    context = await _context(await _user_id(auth_user))
    submission = await _task_service(context).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json={
            "hypothesis_content_hash": context["hypothesis"].content_hash,
            "dataset_snapshot_id": context["dataset"].id,
            "experiment_epoch_id": context["epoch"].id,
        },
        precheck_id=context["precheck"].id,
        idempotency_key="expired-lease",
    )
    start = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
    runner = DurableResearchTaskRunner(lease_seconds=60)
    claim = (await runner.claim_due(now=start))[0]

    recovery_time = start + timedelta(seconds=61)
    assert await runner.recover_expired_leases(now=recovery_time) == 1
    async with async_session_maker() as session:
        task = await session.get(ResearchTask, claim.task_id)
        run = await session.get(ResearchRun, submission.run.id)
    assert task is not None
    assert run is not None
    assert task.status == "QUEUED"
    assert task.error_code == "TASK_LEASE_RECOVERED"
    assert task.lease_token is None
    assert run.status == "QUEUED"
    assert run.completed_at is None

    reclaimed = (await runner.claim_due(now=recovery_time + timedelta(seconds=1)))[0]
    assert reclaimed.task_id == claim.task_id
    assert reclaimed.lease_token != claim.lease_token
    assert await runner.finalize(claim.task_id, claim.lease_token, status="SUCCEEDED") is None
    completed = await runner.finalize(reclaimed.task_id, reclaimed.lease_token, status="SUCCEEDED")
    assert completed is not None
    assert completed.status == "SUCCEEDED"
    async with async_session_maker() as session:
        run = await session.get(ResearchRun, submission.run.id)
        events = list(
            (
                await session.execute(
                    select(ResearchTaskEvent)
                    .where(ResearchTaskEvent.task_id == submission.task.id)
                    .order_by(ResearchTaskEvent.sequence_no.asc())
                )
            ).scalars()
        )
    assert run is not None
    assert run.status == "SUCCEEDED"
    assert [event.event_type for event in events] == [
        "TASK_SUBMITTED",
        "TASK_CLAIMED",
        "TASK_LEASE_RECOVERED",
        "TASK_CLAIMED",
        "TASK_FINALIZED",
    ]
    assert [event.sequence_no for event in events] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("checkpoint_status", "checkpoint_error"),
    [
        ("FAILED", "DISCOVERY_EXECUTION_FAILED"),
        ("TIMED_OUT", "DISCOVERY_EXECUTION_TIMED_OUT"),
        ("CANCELLED", "DISCOVERY_EXECUTION_CANCELLED"),
    ],
)
async def test_expired_lease_closes_a_current_terminal_checkpoint_without_requeueing(
    auth_user,
    checkpoint_status: str,
    checkpoint_error: str,
) -> None:
    """A crash after durable external evidence cannot make that stage dispatchable again."""

    context = await _context(await _user_id(auth_user))
    submission = await _task_service(context).submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json={
            "hypothesis_content_hash": context["hypothesis"].content_hash,
            "dataset_snapshot_id": context["dataset"].id,
            "experiment_epoch_id": context["epoch"].id,
        },
        precheck_id=context["precheck"].id,
        idempotency_key=f"terminal-checkpoint-{checkpoint_status.lower()}",
    )
    runner = DurableResearchTaskRunner(lease_seconds=60)
    async with async_session_maker() as session:
        start = await task_runner_module.database_utc_now(session)
    claim = (await runner.claim_due(now=start))[0]
    attempts = ResearchStageAttemptService()
    started = await attempts.begin(
        task_id=claim.task_id,
        lease_token=claim.lease_token,
        stage="CLARIFY",
        idempotency_key=f"observed-terminal-{checkpoint_status.lower()}",
        input_payload={"stage": "CLARIFY", "receipt": checkpoint_status},
    )
    checkpoint = await attempts.complete(
        task_id=claim.task_id,
        lease_token=claim.lease_token,
        attempt_id=started.id,
        status=checkpoint_status,
        error_code=checkpoint_error,
    )

    recovery_time = start + timedelta(seconds=61)
    assert await runner.recover_expired_leases(now=recovery_time) == 1

    async with async_session_maker() as session:
        task = await session.get(ResearchTask, claim.task_id)
        run = await session.get(ResearchRun, submission.run.id)
        retained_checkpoint = await session.get(ResearchStageAttempt, checkpoint.id)
    assert task is not None
    assert run is not None
    assert retained_checkpoint is not None
    assert task.status == checkpoint_status
    assert task.error_code == checkpoint_error
    assert task.lease_token is None
    assert run.status == checkpoint_status
    assert retained_checkpoint.status == checkpoint_status
    assert retained_checkpoint.error_code == checkpoint_error
    assert await runner.claim_due(now=recovery_time + timedelta(seconds=1)) == []


async def _context(user_id: str) -> dict[str, object]:
    profile = CapabilityProfile(
        profile_id="dev-single-process",
        version="v1",
        service_identities={"explorer": "shared", "evaluator": "shared"},
        queue_isolation=False,
        storage_isolation=False,
        network_isolation=False,
        sandbox_runner=False,
        approval_mode="single_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    await CapabilityRegistry().register(profile)
    hypothesis = await HypothesisRegistry().create_draft(user_id, _payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id, hypothesis.id, request_hash=hypothesis.content_hash
    )
    resolver = InMemoryDatasetObjectResolver()
    attestation = resolver.register(
        DatasetObjectAttestation(
            receipt_id="task-runner-discovery-receipt",
            user_id=user_id,
            logical_object_id="task-runner-discovery-object",
            object_version="fixture-v1",
            object_digest="d" * 64,
            object_size_bytes=4096,
            storage_uri="controlled://task-runner/discovery.parquet",
            attested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
    )
    datasets = DatasetRegistry(object_resolver=resolver)
    dataset = await datasets.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=attestation.receipt_id,
        dataset_policy_version="dataset-policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={
            "symbols": ["RB0"],
            "asset_class": "futures",
            "identity_scheme": "exchange_symbol",
        },
        split_manifest={
            "start": "2022-01-01",
            "end": "2023-12-31",
            "walk_forward": True,
            "purge_bars": 5,
            "embargo_bars": 5,
            "folds": [
                {
                    "train_start": "2022-01-01",
                    "train_end": "2022-12-31",
                    "validation_start": "2023-01-01",
                    "validation_end": "2023-12-31",
                }
            ],
        },
        source_manifest={
            "provider": "fixture",
            "frequency": "1d",
            "timezone": "UTC",
            "adjustment_rule": "none",
            "event_time_basis": "bar_close",
            "ingested_at": "2024-01-01T00:00:00Z",
            "as_of_at": "2024-01-01T00:00:00Z",
            "vintage": "fixture-v1",
        },
        execution_policy={
            "fill": "next_bar_open",
            "commission_bps": 2.0,
            "slippage_bps": 1.0,
            "volume_limit": 0.1,
            "suspension": "BLOCKED",
            "price_limit": "BLOCKED",
            "market_impact": "UNKNOWN",
        },
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-permitted"],
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="dataset-policy-v1",
    )
    async with async_session_maker() as session:
        session.add(epoch)
        await session.commit()
        await session.refresh(epoch)
    request_json = {
        "hypothesis_content_hash": hypothesis.content_hash,
        "dataset_snapshot_id": dataset.id,
        "experiment_epoch_id": epoch.id,
    }
    prechecks = ResearchDataPrecheckService(dataset_registry=datasets)
    precheck = await prechecks.create(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id=epoch.id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
    )
    assert precheck.status == "PASS", precheck.details
    return {
        "user_id": user_id,
        "hypothesis": hypothesis,
        "dataset": dataset,
        "epoch": epoch,
        "precheck": precheck,
        "prechecks": prechecks,
    }


def _task_service(context: dict[str, object]) -> ResearchTaskService:
    return ResearchTaskService(data_prechecks=context["prechecks"])


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())


def _payload() -> dict[str, object]:
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
        "dataset_policy_version": "dataset-policy-v1",
    }
