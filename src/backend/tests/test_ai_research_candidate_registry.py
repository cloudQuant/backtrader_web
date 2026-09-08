from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchCandidate,
    ResearchExperimentEpoch,
    ResearchRun,
    ResearchTrial,
)
from app.models.user import User
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.hypothesis_registry import HypothesisRegistry


@pytest.mark.asyncio
async def test_freeze_requires_completed_market_trial_and_locks_epoch(auth_user) -> None:
    user_id = await _user_id(auth_user)
    context = await _context(user_id)
    registry = CandidateRegistry(dataset_registry=_dataset_registry(context))
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

    with pytest.raises(ValueError, match="CANDIDATE_FREEZE_REQUIRES_COMPLETED_TRIAL"):
        await registry.freeze(
            user_id,
            candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash=candidate.candidate_hash,
        )

    async with async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=context["run"].id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="trial-1",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="i" * 64,
                metrics={"sharpe": 1.2},
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="candidate validation completed",
            )
        )
        await session.commit()

    with pytest.raises(ValueError, match="CANDIDATE_FREEZE_HASH_MISMATCH"):
        await registry.freeze(
            user_id,
            candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash="0" * 64,
        )

    frozen = await registry.freeze(
        user_id,
        candidate.id,
        frozen_by="ai_research_explorer",
        expected_candidate_hash=candidate.candidate_hash,
    )
    epoch = await _load_epoch(context["epoch"].id)

    assert frozen.freeze_status == "FROZEN"
    assert frozen.frozen_at is not None
    assert epoch.selected_candidate_id == candidate.id
    assert epoch.status == "SELECTED"

    with pytest.raises(ValueError, match="EXPERIMENT_EPOCH_CANDIDATE_LOCKED"):
        await registry.create_mutable(
            user_id=user_id,
            run_id=context["run"].id,
            experiment_epoch_id=context["epoch"].id,
            dataset_snapshot_id=context["dataset"].id,
            code_artifact_id=context["code_artifact"].id,
            dependency_artifact_id=context["dependency_artifact"].id,
            environment_hash="e" * 64,
            cost_model_hash="c" * 64,
            params={"lookback": 30},
        )


@pytest.mark.asyncio
async def test_freeze_rejects_market_trial_bound_to_a_different_run(auth_user) -> None:
    """A foreign run cannot lend market evidence to this candidate identity."""

    user_id = await _user_id(auth_user)
    context = await _context(user_id)
    registry = CandidateRegistry(dataset_registry=_dataset_registry(context))
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
    foreign_run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=context["run"].hypothesis_version_id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        promotion_policy_version="promotion-v1",
        request_hash="x" * 64,
        capability_profile_id="profile-v1",
        capability_profile_version="v1",
        capability_evidence_hash="p" * 64,
        trace_id="trace-foreign-market-evidence",
    )
    async with async_session_maker() as session:
        session.add(foreign_run)
        await session.flush()
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=foreign_run.id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="foreign-run-trial",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="i" * 64,
                metrics={"sharpe": 9.9},
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="must not satisfy another run",
            )
        )
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_FREEZE_REQUIRES_COMPLETED_TRIAL$"):
        await registry.freeze(
            user_id,
            candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash=candidate.candidate_hash,
        )


@pytest.mark.asyncio
async def test_freeze_rejects_candidate_with_changed_content_even_when_caller_replays_hash(
    auth_user,
) -> None:
    user_id = await _user_id(auth_user)
    context = await _context(user_id)
    registry = CandidateRegistry(dataset_registry=_dataset_registry(context))
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
    async with async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=context["run"].id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="trial-integrity",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="i" * 64,
                metrics={"sharpe": 1.2},
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="candidate validation completed",
            )
        )
        await session.commit()

    async with async_session_maker() as session:
        await session.execute(
            update(ResearchCandidate)
            .where(ResearchCandidate.id == candidate.id)
            .values(params={"lookback": 999})
        )
        await session.commit()

    with pytest.raises(ValueError, match="CANDIDATE_CONTENT_HASH_MISMATCH"):
        await registry.freeze(
            user_id,
            candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash=candidate.candidate_hash,
        )


@pytest.mark.asyncio
async def test_candidate_creation_and_freeze_reject_legacy_unverified_snapshot(auth_user) -> None:
    """Metadata-only snapshots cannot enter or advance the executable candidate path."""

    user_id = await _user_id(auth_user)
    context = await _context(user_id, attested=False)
    registry = CandidateRegistry()

    with pytest.raises(ValueError, match="DATASET_SNAPSHOT_LEGACY_UNVERIFIED"):
        await registry.create_mutable(
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

    legacy_candidate = ResearchCandidate(
        user_id=user_id,
        run_id=context["run"].id,
        experiment_epoch_id=context["epoch"].id,
        dataset_snapshot_id=context["dataset"].id,
        code_artifact_id=context["code_artifact"].id,
        dependency_artifact_id=context["dependency_artifact"].id,
        candidate_hash="f" * 64,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    async with async_session_maker() as session:
        session.add(legacy_candidate)
        await session.commit()
        await session.refresh(legacy_candidate)

    with pytest.raises(ValueError, match="DATASET_SNAPSHOT_LEGACY_UNVERIFIED"):
        await registry.freeze(
            user_id=user_id,
            candidate_id=legacy_candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash=legacy_candidate.candidate_hash,
        )


@pytest.mark.asyncio
async def test_freeze_requires_a_live_resolver_and_rejects_drifted_attestation(auth_user) -> None:
    """Freeze is fenced by a fresh server object check, not stored metadata alone."""

    user_id = await _user_id(auth_user)
    context = await _context(user_id)
    trusted_registry = CandidateRegistry(dataset_registry=_dataset_registry(context))
    candidate = await trusted_registry.create_mutable(
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
    async with async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=context["run"].id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="trial-live-attestation",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="i" * 64,
                metrics={"sharpe": 1.2},
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="candidate validation completed",
            )
        )
        await session.commit()

    with pytest.raises(ValueError, match="DATASET_OBJECT_RESOLVER_REQUIRED"):
        await CandidateRegistry().freeze(
            user_id,
            candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash=candidate.candidate_hash,
        )

    _drift_discovery_object(context, user_id)
    with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
        await trusted_registry.freeze(
            user_id,
            candidate.id,
            frozen_by="ai_research_explorer",
            expected_candidate_hash=candidate.candidate_hash,
        )

    async with async_session_maker() as session:
        stored_candidate = await session.get(ResearchCandidate, candidate.id)
        stored_epoch = await session.get(ResearchExperimentEpoch, context["epoch"].id)
    assert stored_candidate is not None
    assert stored_candidate.freeze_status == "MUTABLE"
    assert stored_epoch is not None
    assert stored_epoch.status == "OPEN"


async def _context(user_id: str, *, attested: bool = True) -> dict[str, object]:
    hypothesis_registry = HypothesisRegistry()
    hypothesis = await hypothesis_registry.create_draft(user_id, _payload())
    hypothesis = await hypothesis_registry.confirm(
        user_id,
        hypothesis.id,
        request_hash=hypothesis.content_hash,
    )
    dataset_metadata = {
        "dataset_policy_version": "policy-v1",
        "partition_kind": "DISCOVERY",
        "instrument_manifest": {"symbols": ["RB0"]},
        "split_manifest": {"start": "2022-01-01", "end": "2023-12-31"},
        "source_manifest": {"provider": "fixture"},
        "execution_policy": {"fill": "next_bar_open"},
        "point_in_time_cutoff": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "license_tags": ["fixture-license"],
    }
    if attested:
        resolver = InMemoryDatasetObjectResolver()
        receipt = resolver.register(
            DatasetObjectAttestation(
                receipt_id="candidate-registry-fixture-receipt-v1",
                user_id=user_id,
                logical_object_id="candidate-registry-fixture-object",
                object_version="version-1",
                object_digest="d" * 64,
                object_size_bytes=1024,
                storage_uri="controlled://candidate-registry/discovery.parquet",
                attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            )
        )
        datasets = DatasetRegistry(object_resolver=resolver)
        dataset = await datasets.create_attested_snapshot(
            user_id=user_id,
            object_receipt_id=receipt.receipt_id,
            **dataset_metadata,
        )
    else:
        resolver = None
        datasets = DatasetRegistry()
        dataset = await datasets.create_snapshot(
            user_id=user_id,
            storage_uri="controlled://candidate-registry/legacy-discovery.parquet",
            **dataset_metadata,
        )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="policy-v1",
        status="OPEN",
    )
    async with async_session_maker() as session:
        session.add(epoch)
        await session.commit()
        await session.refresh(epoch)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id=epoch.id,
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="dev-single-process",
        capability_profile_version="v1",
        capability_evidence_hash="p" * 64,
        trace_id="trace-1",
    )
    code_artifact = ResearchArtifact(
        kind="strategy_code",
        content_hash="a" * 64,
        storage_uri="controlled://code.py",
        size_bytes=10,
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="test",
    )
    dependency_artifact = ResearchArtifact(
        kind="dependency_lock",
        content_hash="b" * 64,
        storage_uri="controlled://requirements.lock",
        size_bytes=10,
        media_type="text/plain",
        schema_version="v1",
        producer_identity="test",
    )
    async with async_session_maker() as session:
        session.add_all([run, code_artifact, dependency_artifact])
        await session.commit()
        await session.refresh(run)
        await session.refresh(code_artifact)
        await session.refresh(dependency_artifact)
    return {
        "epoch": epoch,
        "run": run,
        "dataset": dataset,
        "datasets": datasets,
        "resolver": resolver,
        "code_artifact": code_artifact,
        "dependency_artifact": dependency_artifact,
    }


def _dataset_registry(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


def _drift_discovery_object(context: dict[str, object], user_id: str) -> None:
    resolver = context["resolver"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    resolver.register(
        DatasetObjectAttestation(
            receipt_id="candidate-registry-fixture-receipt-v2",
            user_id=user_id,
            logical_object_id="candidate-registry-fixture-object",
            object_version="version-2",
            object_digest="e" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://candidate-registry/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())


async def _load_epoch(epoch_id: str) -> ResearchExperimentEpoch:
    async with async_session_maker() as session:
        return await session.get(ResearchExperimentEpoch, epoch_id)


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
