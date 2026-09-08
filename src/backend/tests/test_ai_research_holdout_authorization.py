from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchHoldoutAuthorization,
    ResearchRun,
    ResearchTrial,
)
from app.models.user import User
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_authorization import HoldoutAuthorizationRegistry
from app.services.research.hypothesis_registry import HypothesisRegistry

_TRUSTED_STAGE_IMAGES = {
    "evaluator": "evaluator-image@sha256:test",
    "scanner": f"sha256:{'5' * 64}",
}


@pytest.mark.asyncio
async def test_holdout_authorization_is_frozen_candidate_bound_and_single_use(auth_user) -> None:
    profile = CapabilityProfile(
        profile_id="single-node-isolated-services",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        "holdout-single-use",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    with pytest.raises(ValueError, match="DATASET_OBJECT_RESOLVER_REQUIRED"):
        await HoldoutAuthorizationRegistry().issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id=profile.profile_id,
            profile_version=profile.version,
        )

    registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))

    issued = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )

    assert issued.authorization.status == "ISSUED"
    assert issued.token != issued.authorization.token_hash
    assert issued.authorization.candidate_id == context["candidate"].id
    assert issued.authorization.candidate_hash == context["candidate"].candidate_hash

    with pytest.raises(ValueError, match="HOLDOUT_AUTHORIZATION_EVALUATOR_DENIED"):
        await registry.consume(
            issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_explorer",
        )

    with pytest.raises(ValueError, match="HOLDOUT_AUTHORIZATION_BINDING_MISMATCH"):
        await registry.consume(
            issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash="0" * 64,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
        )

    consumed = await registry.consume(
        issued.token,
        candidate_id=context["candidate"].id,
        candidate_hash=context["candidate"].candidate_hash,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
    )
    assert consumed.status == "CONSUMED"
    assert consumed.consumed_at is not None
    async with async_session_maker() as session:
        disclosed_epoch = await session.get(
            ResearchExperimentEpoch,
            context["candidate"].experiment_epoch_id,
        )
    assert disclosed_epoch is not None
    assert disclosed_epoch.status == "DISCLOSED"
    assert disclosed_epoch.disclosed_at == consumed.consumed_at
    assert disclosed_epoch.closed_at is None

    with pytest.raises(ValueError, match="HOLDOUT_AUTHORIZATION_NOT_ACTIVE"):
        await registry.consume(
            issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
        )


@pytest.mark.asyncio
async def test_public_consume_persists_expired_status_without_disclosing_epoch(auth_user) -> None:
    """The session-aware consume refactor preserves the public expiry contract."""

    profile = CapabilityProfile(
        profile_id="expired-holdout-authorization",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        "holdout-expired",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))
    issued = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )
    async with async_session_maker() as session:
        authorization = await session.get(ResearchHoldoutAuthorization, issued.authorization.id)
        assert authorization is not None
        authorization.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    with pytest.raises(ValueError, match="^HOLDOUT_AUTHORIZATION_NOT_ACTIVE$"):
        await registry.consume(
            issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchHoldoutAuthorization, issued.authorization.id)
        epoch = await session.get(ResearchExperimentEpoch, context["candidate"].experiment_epoch_id)
        assert stored is not None and stored.status == "EXPIRED"
        assert stored.consumed_at is None
        assert epoch is not None and epoch.status == "SELECTED"
        assert epoch.disclosed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_binding", ["policy", "sealed_snapshot"])
async def test_holdout_authorization_allows_only_one_issue_per_epoch(
    auth_user,
    changed_binding: str,
) -> None:
    """Changing policy or sealed data cannot mint a second token for an epoch."""

    profile = CapabilityProfile(
        profile_id=f"one-holdout-per-epoch-{changed_binding}",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        f"holdout-one-per-epoch-{changed_binding}",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))
    first = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )
    second_dataset_id = context["sealed"].id
    second_policy_version = "holdout-policy-v2"
    if changed_binding == "sealed_snapshot":
        second_dataset = await _create_additional_sealed_snapshot(
            context,
            suffix="second",
        )
        second_dataset_id = second_dataset.id
        second_policy_version = "holdout-policy-v1"

    with pytest.raises(ValueError, match="^HOLDOUT_AUTHORIZATION_ALREADY_ISSUED$"):
        await registry.issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=second_dataset_id,
            policy_version=second_policy_version,
            evaluator_identity="ai_research_evaluator",
            profile_id=profile.profile_id,
            profile_version=profile.version,
        )

    async with async_session_maker() as session:
        authorizations = list(
            await session.scalars(
                select(ResearchHoldoutAuthorization).where(
                    ResearchHoldoutAuthorization.experiment_epoch_id
                    == context["candidate"].experiment_epoch_id
                )
            )
        )
        epoch = await session.get(ResearchExperimentEpoch, context["candidate"].experiment_epoch_id)
        evaluations = list(
            await session.scalars(
                select(ResearchEvaluation).where(
                    ResearchEvaluation.experiment_epoch_id
                    == context["candidate"].experiment_epoch_id
                )
            )
        )
        assert len(authorizations) == 1
        assert authorizations[0].id == first.authorization.id
        assert authorizations[0].status == "ISSUED"
        assert epoch is not None and epoch.status == "SELECTED"
        assert evaluations == []


@pytest.mark.asyncio
async def test_database_rejects_any_second_token_for_the_epoch(
    auth_user,
) -> None:
    """The database authority permits only one authorization for an epoch."""

    profile = CapabilityProfile(
        profile_id="duplicate-token-epoch-defense",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        "holdout-duplicate-token-defense",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))
    first = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )
    second_token = "legacy-preexisting-second-token"
    second = ResearchHoldoutAuthorization(
        experiment_epoch_id=context["candidate"].experiment_epoch_id,
        candidate_id=context["candidate"].id,
        candidate_hash=context["candidate"].candidate_hash,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v2",
        token_hash=sha256(second_token.encode("utf-8")).hexdigest(),
        status="ISSUED",
        evaluator_identity="ai_research_evaluator",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
        issued_by=context["user_id"],
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    async with async_session_maker() as session:
        session.add(second)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with async_session_maker() as session:
        stored_first = await session.get(ResearchHoldoutAuthorization, first.authorization.id)
        epoch = await session.get(ResearchExperimentEpoch, context["candidate"].experiment_epoch_id)
        evaluations = list(
            await session.scalars(
                select(ResearchEvaluation).where(
                    ResearchEvaluation.experiment_epoch_id
                    == context["candidate"].experiment_epoch_id
                )
            )
        )
        assert stored_first is not None and stored_first.status == "ISSUED"
        assert stored_first.consumed_at is None
        assert epoch is not None and epoch.status == "SELECTED"
        assert evaluations == []


@pytest.mark.asyncio
async def test_holdout_authorization_fails_closed_for_dev_profile(auth_user) -> None:
    context = await _context(await _user_id(auth_user))

    with pytest.raises(ValueError, match="BLOCKED_TOPOLOGY_CAPABILITY"):
        await HoldoutAuthorizationRegistry().issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id="dev-single-process",
            profile_version="v1",
        )


@pytest.mark.asyncio
async def test_holdout_authorization_rejects_profile_that_does_not_match_frozen_run(
    auth_user,
) -> None:
    context = await _context(await _user_id(auth_user))
    profile = CapabilityProfile(
        profile_id="single-node-isolated-services",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)

    with pytest.raises(ValueError, match="HOLDOUT_AUTHORIZATION_RUN_PROFILE_MISMATCH"):
        await HoldoutAuthorizationRegistry().issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id=profile.profile_id,
            profile_version=profile.version,
        )


@pytest.mark.asyncio
async def test_holdout_authorization_revalidates_the_sealed_object_before_consuming_token(
    auth_user,
) -> None:
    """A token remains unconsumed if its sealed object has drifted since issuance."""

    profile = CapabilityProfile(
        profile_id="single-node-isolated-services",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        "holdout-object-drift",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))
    issued = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )

    _drift_sealed_object(context)
    with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
        await registry.consume(
            issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchHoldoutAuthorization, issued.authorization.id)
        epoch = await session.get(ResearchExperimentEpoch, context["candidate"].experiment_epoch_id)
    assert stored is not None
    assert stored.status == "ISSUED"
    assert epoch is not None
    assert epoch.status == "SELECTED"


@pytest.mark.asyncio
async def test_holdout_authorization_rejects_legacy_freeze_without_strict_receipt(
    auth_user,
) -> None:
    profile = CapabilityProfile(
        profile_id="legacy-freeze-isolated",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _context(
        await _user_id(auth_user),
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )

    with pytest.raises(ValueError, match="^CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED$"):
        await HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context)).issue(
            user_id=context["user_id"],
            candidate_id=context["candidate"].id,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
            profile_id=profile.profile_id,
            profile_version=profile.version,
        )


@pytest.mark.asyncio
async def test_holdout_consume_fails_closed_if_strict_receipt_drifts(auth_user) -> None:
    profile = CapabilityProfile(
        profile_id="receipt-drift-isolated",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests=_TRUSTED_STAGE_IMAGES,
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_context(
        auth_user,
        "holdout-receipt-drift",
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))
    issued = await registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="holdout-policy-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )
    async with async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == context["candidate"].id
            )
        )
        assert receipt is not None
        receipt.ledger_hash = "0" * 64
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED$"):
        await registry.consume(
            issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy_version="holdout-policy-v1",
            evaluator_identity="ai_research_evaluator",
        )
    async with async_session_maker() as session:
        stored = await session.get(ResearchHoldoutAuthorization, issued.authorization.id)
        epoch = await session.get(ResearchExperimentEpoch, context["candidate"].experiment_epoch_id)
        assert stored is not None and stored.status == "ISSUED"
        assert epoch is not None and epoch.status == "SELECTED"


async def _strict_context(
    auth_user,
    suffix: str,
    *,
    capability_profile_id: str,
    capability_profile_version: str,
    capability_evidence_hash: str,
) -> dict[str, object]:
    """Build a candidate exclusively through the published discovery freeze gate."""

    from tests.test_ai_research_candidate_freeze_v2 import _published_candidate

    context, _dispatch, _attempt = await _published_candidate(
        auth_user,
        suffix,
        capability_profile_id=capability_profile_id,
        capability_profile_version=capability_profile_version,
        capability_evidence_hash=capability_evidence_hash,
    )
    resolver = context["resolver"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    sealed_receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"{suffix}-sealed-receipt-v1",
            user_id=context["task"].user_id,
            logical_object_id=f"{suffix}-sealed-object",
            object_version="version-1",
            object_digest="e" * 64,
            object_size_bytes=2048,
            storage_uri=f"sealed://{suffix}/holdout.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    sealed = await datasets.create_attested_snapshot(
        user_id=context["task"].user_id,
        object_receipt_id=sealed_receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="SEALED_HOLDOUT",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2024-01-01", "end": "2024-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        assert candidate is not None
        candidate_hash = candidate.candidate_hash
    candidate = await CandidateRegistry(dataset_registry=datasets).freeze_discovery(
        context["task"].user_id,
        context["candidate_id"],
        frozen_by="ai_research_explorer",
        expected_candidate_hash=candidate_hash,
    )
    return {
        "user_id": context["task"].user_id,
        "candidate": candidate,
        "sealed": sealed,
        "datasets": datasets,
        "resolver": resolver,
    }


async def _context(
    user_id: str,
    *,
    capability_profile_id: str = "dev-single-process",
    capability_profile_version: str = "v1",
    capability_evidence_hash: str = "p" * 64,
) -> dict[str, object]:
    hypothesis = await HypothesisRegistry().create_draft(user_id, _payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id, hypothesis.id, request_hash=hypothesis.content_hash
    )
    resolver = InMemoryDatasetObjectResolver()
    receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id="holdout-authorization-discovery-receipt-v1",
            user_id=user_id,
            logical_object_id="holdout-authorization-discovery-object",
            object_version="version-1",
            object_digest="d" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://holdout-authorization-fixtures/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    data_registry = DatasetRegistry(object_resolver=resolver)
    discovery = await data_registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    sealed_receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id="holdout-authorization-holdout-receipt-v1",
            user_id=user_id,
            logical_object_id="holdout-authorization-holdout-object",
            object_version="version-1",
            object_digest="e" * 64,
            object_size_bytes=2048,
            storage_uri="sealed://holdout-authorization-fixtures/holdout.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    sealed = await data_registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=sealed_receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="SEALED_HOLDOUT",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2024-01-01", "end": "2024-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="policy-v1",
    )
    async with async_session_maker() as session:
        session.add(epoch)
        await session.commit()
        await session.refresh(epoch)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=discovery.id,
        experiment_epoch_id=epoch.id,
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id=capability_profile_id,
        capability_profile_version=capability_profile_version,
        capability_evidence_hash=capability_evidence_hash,
        trace_id="trace-holdout",
    )
    code = ResearchArtifact(
        kind="strategy_code",
        content_hash="a" * 64,
        storage_uri="controlled://code.py",
        size_bytes=10,
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="test",
    )
    dependencies = ResearchArtifact(
        kind="dependency_lock",
        content_hash="b" * 64,
        storage_uri="controlled://requirements.lock",
        size_bytes=10,
        media_type="text/plain",
        schema_version="v1",
        producer_identity="test",
    )
    async with async_session_maker() as session:
        session.add_all([run, code, dependencies])
        await session.commit()
        await session.refresh(run)
        await session.refresh(code)
        await session.refresh(dependencies)
    candidate_registry = CandidateRegistry(dataset_registry=data_registry)
    candidate = await candidate_registry.create_mutable(
        user_id=user_id,
        run_id=run.id,
        experiment_epoch_id=epoch.id,
        dataset_snapshot_id=discovery.id,
        code_artifact_id=code.id,
        dependency_artifact_id=dependencies.id,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    async with async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=run.id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="trial-holdout",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="i" * 64,
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="completed discovery validation",
            )
        )
        await session.commit()
    candidate = await candidate_registry.freeze(
        user_id,
        candidate.id,
        frozen_by="ai_research_explorer",
        expected_candidate_hash=candidate.candidate_hash,
    )
    return {
        "user_id": user_id,
        "candidate": candidate,
        "sealed": sealed,
        "datasets": data_registry,
        "resolver": resolver,
    }


def _dataset_registry(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


async def _create_additional_sealed_snapshot(
    context: dict[str, object],
    *,
    suffix: str,
) -> ResearchDatasetSnapshot:
    resolver = context["resolver"]
    datasets = _dataset_registry(context)
    candidate = context["candidate"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    assert isinstance(candidate, ResearchCandidate)
    receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"{candidate.id}-{suffix}-sealed-receipt",
            user_id=candidate.user_id,
            logical_object_id=f"{candidate.id}-{suffix}-sealed-object",
            object_version="version-1",
            object_digest="9" * 64,
            object_size_bytes=2048,
            storage_uri=f"sealed://{candidate.id}/{suffix}.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    return await datasets.create_attested_snapshot(
        user_id=candidate.user_id,
        object_receipt_id=receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="SEALED_HOLDOUT",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2025-01-01", "end": "2025-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )


def _drift_sealed_object(context: dict[str, object]) -> None:
    resolver = context["resolver"]
    sealed = context["sealed"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    assert isinstance(sealed, ResearchDatasetSnapshot)
    assert sealed.object_logical_id is not None and sealed.storage_uri is not None
    resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"{sealed.object_receipt_id}-drift",
            user_id=context["user_id"],
            logical_object_id=sealed.object_logical_id,
            object_version="version-2",
            object_digest="f" * 64,
            object_size_bytes=2048,
            storage_uri=sealed.storage_uri,
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )


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
