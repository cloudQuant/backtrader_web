"""Strict candidate-freeze boundary for the versioned discovery workflow."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.api.strategy import research as research_api
from app.config import get_settings
from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchDiscoveryExecution,
    ResearchExperimentEpoch,
    ResearchGenerationMaterialization,
    ResearchQuotaReservation,
    ResearchRun,
    ResearchStageAttempt,
    ResearchTask,
    ResearchTaskEvent,
    ResearchTrial,
)
from app.services.research.candidate_registry import (
    CandidateRegistry,
    require_strict_freeze_receipt,
)
from app.services.research.task_runner import DurableResearchTaskRunner
from tests.conftest import app, register_and_login
from tests.test_ai_research_candidate_registry import (
    _context as _legacy_context,
)
from tests.test_ai_research_candidate_registry import (
    _dataset_registry as _legacy_dataset_registry,
)
from tests.test_ai_research_discovery_stage_completion import _ready


@pytest.fixture(autouse=True)
def enable_protocol_v2_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public mutation remains behind the deployment-owned rollout flag."""

    monkeypatch.setattr(get_settings(), "AI_RESEARCH_PROTOCOL_V2_ENABLED", True)


async def _published_candidate(
    auth_user,
    suffix: str,
    *,
    capability_profile_id: str | None = None,
    capability_profile_version: str | None = None,
    capability_evidence_hash: str | None = None,
):
    context, dispatch, service, args = await _ready(
        auth_user,
        suffix,
        capability_profile_id=capability_profile_id,
        capability_profile_version=capability_profile_version,
        capability_evidence_hash=capability_evidence_hash,
    )
    attempt = await service.complete(**args)
    task = await DurableResearchTaskRunner().finalize(
        args["task_id"],
        context["discovery_context"].lease_token,
        status="SUCCEEDED",
    )
    assert task is not None
    return context, dispatch, attempt


@pytest.mark.asyncio
async def test_discovery_freeze_requires_the_published_success_checkpoint(auth_user) -> None:
    context, _dispatch, _attempt = await _published_candidate(auth_user, "freeze-published")
    registry = CandidateRegistry(dataset_registry=context["datasets"])

    frozen = await registry.freeze_discovery(
        user_id=context["task"].user_id,
        candidate_id=context["candidate_id"],
        frozen_by=context["task"].user_id,
        expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
    )

    assert frozen.freeze_status == "FROZEN"
    assert frozen.frozen_by == context["task"].user_id
    assert frozen.frozen_at is not None
    repeated = await registry.freeze_discovery(
        user_id=context["task"].user_id,
        candidate_id=context["candidate_id"],
        frozen_by=context["task"].user_id,
        expected_candidate_hash=frozen.candidate_hash,
    )
    assert repeated.id == frozen.id
    assert repeated.frozen_at == frozen.frozen_at
    async with database.async_session_maker() as session:
        receipts = list(
            (
                await session.scalars(
                    select(ResearchCandidateFreezeReceipt).where(
                        ResearchCandidateFreezeReceipt.candidate_id == frozen.id
                    )
                )
            ).all()
        )
        assert len(receipts) == 1
        receipt = receipts[0]
        candidate = await session.get(ResearchCandidate, frozen.id)
        run = await session.get(ResearchRun, frozen.run_id)
        assert candidate is not None and run is not None
        assert receipt.user_id == candidate.user_id
        assert receipt.run_id == candidate.run_id
        assert receipt.experiment_epoch_id == candidate.experiment_epoch_id
        assert receipt.candidate_hash == candidate.candidate_hash
        assert receipt.workflow_version == "discovery-v1"
        assert receipt.checker_version == "candidate-freeze-v1"
        assert receipt.generation_materialization_hash
        assert receipt.ledger_hash
        assert receipt.attempt_count_total >= 1
        assert receipt.market_trial_count >= 1
        assert receipt.search_budget_hash
        assert receipt.dataset_snapshot_hash
        assert receipt.dataset_snapshot_identity_hash == context["dataset"].snapshot_identity_hash
        assert receipt.code_hash
        assert receipt.dependency_hash
        assert receipt.hypothesis_hash
        assert receipt.environment_hash == candidate.environment_hash
        assert receipt.cost_model_hash == candidate.cost_model_hash
        assert receipt.frozen_by == candidate.frozen_by
        assert receipt.frozen_at == candidate.frozen_at


@pytest.mark.asyncio
async def test_discovery_freeze_rejects_an_unpublished_or_unknown_execution(auth_user) -> None:
    context, dispatch, _attempt = await _published_candidate(auth_user, "freeze-unknown")
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        assert journal is not None
        trial = await session.get(ResearchTrial, journal.trial_id)
        assert trial is not None
        journal.trial_id = None
        journal.status = "UNKNOWN"
        journal.result_json = None
        journal.error_code = "DISCOVERY_REMOTE_OUTCOME_UNKNOWN"
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_DISCOVERY_UNRECONCILED$"):
        await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
        )
    await _assert_no_freeze_side_effects(context["candidate_id"])


@pytest.mark.asyncio
async def test_discovery_freeze_rejects_active_family_work(auth_user) -> None:
    context, _dispatch, _attempt = await _published_candidate(auth_user, "freeze-active")
    async with database.async_session_maker() as session:
        task = await session.scalar(
            select(ResearchTask).where(ResearchTask.id == context["task"].id)
        )
        assert task is not None
        task.status = "RUNNING"
        task.lease_token = "active-freeze-lease"
        task.lease_heartbeat_at = datetime.now(timezone.utc)
        task.lease_expires_at = datetime.now(timezone.utc)
        task.completed_at = None
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_FAMILY_TASK_ACTIVE$"):
        await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
        )


@pytest.mark.asyncio
async def test_discovery_freeze_rejects_tampered_published_trial(auth_user) -> None:
    context, dispatch, _attempt = await _published_candidate(auth_user, "freeze-tampered-trial")
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        assert journal is not None
        trial = await session.get(ResearchTrial, journal.trial_id)
        assert trial is not None
        trial.counts_as_market_trial = False
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_LEDGER_INTEGRITY_DENIED$"):
        await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["generation", "terminal_event"])
async def test_discovery_freeze_requires_complete_generation_and_task_provenance(
    auth_user,
    missing: str,
) -> None:
    context, _dispatch, _attempt = await _published_candidate(
        auth_user, f"freeze-missing-{missing}"
    )
    async with database.async_session_maker() as session:
        if missing == "generation":
            model = await session.scalar(
                select(ResearchGenerationMaterialization).where(
                    ResearchGenerationMaterialization.candidate_id == context["candidate_id"]
                )
            )
        else:
            model = await session.scalar(
                select(ResearchTaskEvent).where(
                    ResearchTaskEvent.task_id == context["task"].id,
                    ResearchTaskEvent.event_type == "TASK_FINALIZED",
                )
            )
        assert model is not None
        await session.delete(model)
        await session.commit()

    expected = (
        "CANDIDATE_FREEZE_GENERATION_PROVENANCE_INVALID"
        if missing == "generation"
        else "CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE"
    )
    with pytest.raises(ValueError, match=f"^{expected}$"):
        await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
        )


@pytest.mark.asyncio
async def test_discovery_freeze_rejects_unsettled_discovery_quota(auth_user) -> None:
    context, dispatch, _attempt = await _published_candidate(auth_user, "freeze-quota")
    async with database.async_session_maker() as session:
        journal = await session.get(ResearchDiscoveryExecution, dispatch.journal_id)
        assert journal is not None
        reservation = await session.get(ResearchQuotaReservation, journal.quota_reservation_id)
        assert reservation is not None
        reservation.status = "RECONCILING"
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_QUOTA_UNRECONCILED$"):
        await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
        )
    await _assert_no_freeze_side_effects(context["candidate_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("selected_candidate_id", None), ("status", "OPEN")],
)
async def test_strict_receipt_requires_the_persisted_epoch_selection(
    auth_user,
    field: str,
    value: object,
) -> None:
    context, _dispatch, _attempt = await _published_candidate(
        auth_user, f"freeze-epoch-binding-{field}"
    )
    frozen = await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
        user_id=context["task"].user_id,
        candidate_id=context["candidate_id"],
        frozen_by=context["task"].user_id,
        expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
    )
    async with database.async_session_maker() as session:
        epoch = await session.get(ResearchExperimentEpoch, frozen.experiment_epoch_id)
        assert epoch is not None
        setattr(epoch, field, value)
        await session.commit()

    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, frozen.id)
        assert candidate is not None
        with pytest.raises(ValueError, match="^CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED$"):
            await require_strict_freeze_receipt(session, candidate)


@pytest.mark.asyncio
async def test_strict_receipt_rejects_capability_profile_drift(auth_user) -> None:
    context, _dispatch, _attempt = await _published_candidate(auth_user, "freeze-capability-drift")
    frozen = await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
        user_id=context["task"].user_id,
        candidate_id=context["candidate_id"],
        frozen_by=context["task"].user_id,
        expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
    )
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, frozen.run_id)
        assert run is not None
        run.capability_evidence_hash = "0" * 64
        await session.commit()

    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, frozen.id)
        assert candidate is not None
        with pytest.raises(ValueError, match="^CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED$"):
            await require_strict_freeze_receipt(session, candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["attempt_task", "event_run"])
async def test_discovery_freeze_rejects_cross_aggregate_attempt_or_event_binding(
    auth_user,
    tamper: str,
) -> None:
    context, _dispatch, _attempt = await _published_candidate(
        auth_user, f"freeze-cross-aggregate-{tamper}"
    )
    source_run = context["run"]
    foreign_run = ResearchRun(
        user_id=context["task"].user_id,
        hypothesis_version_id=source_run.hypothesis_version_id,
        dataset_snapshot_id=source_run.dataset_snapshot_id,
        experiment_epoch_id=None,
        promotion_policy_version=source_run.promotion_policy_version,
        request_hash="x" * 64,
        capability_profile_id=source_run.capability_profile_id,
        capability_profile_version=source_run.capability_profile_version,
        capability_evidence_hash=source_run.capability_evidence_hash,
        trace_id=f"trace-cross-aggregate-{tamper}",
    )
    foreign_task = ResearchTask(
        user_id=context["task"].user_id,
        run_id="pending",
        status="SUCCEEDED",
        stage_cursor="TERMINAL",
        request_json={},
        idempotency_key=f"foreign-task-{tamper}",
        idempotency_request_hash="y" * 64,
    )
    async with database.async_session_maker() as session:
        session.add(foreign_run)
        await session.flush()
        foreign_task.run_id = foreign_run.id
        session.add(foreign_task)
        await session.flush()
        if tamper == "attempt_task":
            attempt = await session.scalar(
                select(ResearchStageAttempt).where(
                    ResearchStageAttempt.run_id == source_run.id,
                    ResearchStageAttempt.stage == "VALIDATE_DISCOVERY",
                )
            )
            assert attempt is not None
            attempt.task_id = foreign_task.id
        else:
            event = await session.scalar(
                select(ResearchTaskEvent).where(
                    ResearchTaskEvent.task_id == context["task"].id,
                    ResearchTaskEvent.event_type == "TASK_FINALIZED",
                )
            )
            assert event is not None
            event.run_id = foreign_run.id
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_ATTEMPT_LEDGER_INCOMPLETE$"):
        await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ledger_hash", "0" * 64),
        ("attempt_count_total", 999),
        ("generation_materialization_hash", "1" * 64),
        ("dataset_snapshot_hash", "2" * 64),
        ("dataset_snapshot_identity_hash", "3" * 64),
    ],
)
async def test_repeated_discovery_freeze_rejects_receipt_drift(
    auth_user,
    field: str,
    value: object,
) -> None:
    context, _dispatch, _attempt = await _published_candidate(
        auth_user, f"freeze-receipt-drift-{field}"
    )
    registry = CandidateRegistry(dataset_registry=context["datasets"])
    frozen = await registry.freeze_discovery(
        user_id=context["task"].user_id,
        candidate_id=context["candidate_id"],
        frozen_by=context["task"].user_id,
        expected_candidate_hash=await _candidate_hash(context["candidate_id"]),
    )
    async with database.async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == frozen.id
            )
        )
        assert receipt is not None
        setattr(receipt, field, value)
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_RECEIPT_INVALID$"):
        await registry.freeze_discovery(
            user_id=context["task"].user_id,
            candidate_id=context["candidate_id"],
            frozen_by=context["task"].user_id,
            expected_candidate_hash=frozen.candidate_hash,
        )


@pytest.mark.asyncio
async def test_public_freeze_rejects_generation_only_compatibility_evidence(
    client,
    auth_user,
) -> None:
    user_id = await _user_id(auth_user[0]["username"])
    context = await _legacy_context(user_id)
    registry = CandidateRegistry(dataset_registry=_legacy_dataset_registry(context))
    candidate = await registry.create_mutable(
        user_id=user_id,
        run_id=context["run"].id,
        experiment_epoch_id=context["epoch"].id,
        dataset_snapshot_id=context["dataset"].id,
        code_artifact_id=context["code_artifact"].id,
        dependency_artifact_id=context["dependency_artifact"].id,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    async with database.async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=context["run"].id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="legacy-success-is-not-discovery-publication",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="a" * 64,
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="legacy fixture",
            )
        )
        await session.commit()
    app.dependency_overrides[research_api.get_candidate_registry] = lambda: registry
    try:
        response = await client.post(
            f"/api/v1/strategy/ai-research/v2/candidates/{candidate.id}/freeze",
            headers=auth_user[1],
            json={"expected_candidate_hash": candidate.candidate_hash},
        )
    finally:
        app.dependency_overrides.pop(research_api.get_candidate_registry, None)

    assert response.status_code == 409
    assert response.json()["message"] == "CANDIDATE_FREEZE_DISCOVERY_WORKFLOW_REQUIRED"


@pytest.mark.asyncio
async def test_freeze_api_is_owner_scoped_hash_bound_and_returns_no_controlled_content(
    client,
    auth_user,
) -> None:
    context, _dispatch, _attempt = await _published_candidate(auth_user, "freeze-api")
    _user, headers = auth_user
    expected_hash = await _candidate_hash(context["candidate_id"])
    app.dependency_overrides[research_api.get_candidate_registry] = lambda: CandidateRegistry(
        dataset_registry=context["datasets"]
    )
    try:
        stale = await client.post(
            f"/api/v1/strategy/ai-research/v2/candidates/{context['candidate_id']}/freeze",
            headers=headers,
            json={"expected_candidate_hash": "0" * 64},
        )
        assert stale.status_code == 409
        assert stale.json()["message"] == "CANDIDATE_FREEZE_HASH_MISMATCH"
        assert stale.json()["details"] == {
            "code": "CANDIDATE_FREEZE_HASH_MISMATCH",
            "message": "CANDIDATE_FREEZE_HASH_MISMATCH",
            "retryable": False,
        }

        _other, other_headers = await register_and_login(client, username="freeze-v2-other")
        foreign = await client.post(
            f"/api/v1/strategy/ai-research/v2/candidates/{context['candidate_id']}/freeze",
            headers=other_headers,
            json={"expected_candidate_hash": expected_hash},
        )
        assert foreign.status_code == 404

        response = await client.post(
            f"/api/v1/strategy/ai-research/v2/candidates/{context['candidate_id']}/freeze",
            headers=headers,
            json={"expected_candidate_hash": expected_hash},
        )
    finally:
        app.dependency_overrides.pop(research_api.get_candidate_registry, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == context["candidate_id"]
    assert payload["candidate_hash"] == expected_hash
    assert payload["freeze_status"] == "FROZEN"
    assert payload["frozen_at"] is not None
    assert "storage_uri" not in str(payload)
    assert "content" not in payload


async def _candidate_hash(candidate_id: str) -> str:
    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, candidate_id)
        assert candidate is not None
        return candidate.candidate_hash


async def _assert_no_freeze_side_effects(candidate_id: str) -> None:
    """A denied gate cannot partially select an epoch or persist a receipt."""

    async with database.async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, candidate_id)
        assert candidate is not None
        epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
        assert epoch is not None
        receipt_count = await session.scalar(
            select(func.count(ResearchCandidateFreezeReceipt.id)).where(
                ResearchCandidateFreezeReceipt.candidate_id == candidate_id
            )
        )
        assert candidate.freeze_status == "MUTABLE"
        assert candidate.frozen_at is None and candidate.frozen_by is None
        assert epoch.status == "OPEN" and epoch.selected_candidate_id is None
        assert receipt_count == 0


async def _user_id(username: str) -> str:
    from app.models.user import User

    async with database.async_session_maker() as session:
        value = await session.scalar(select(User.id).where(User.username == username))
        assert value is not None
        return str(value)
