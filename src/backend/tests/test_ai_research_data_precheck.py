from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchDatasetSnapshot, ResearchExperimentEpoch
from app.models.user import User
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.data_precheck import ResearchDataPrecheckService
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.task_runner import ResearchTaskService


@pytest.mark.asyncio
async def test_submission_requires_a_current_server_bound_data_precheck(auth_user) -> None:
    """A client cannot claim that a stale or absent precheck passed."""

    context = await _context(await _user_id(auth_user))
    request_json = _request_json(context)
    task_service = _task_service(context)

    with pytest.raises(ValueError, match="RESEARCH_TASK_PRECHECK_REQUIRED"):
        await task_service.submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json=request_json,
            precheck_id=None,
            idempotency_key="precheck-required",
        )

    precheck = await context["prechecks"].create(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
    )

    assert precheck.status == "PASS", precheck.details["errors"]
    assert len(precheck.input_hash) == 64
    assert len(precheck.evidence_hash) == 64
    assert precheck.expires_at > precheck.checked_at

    submitted = await task_service.submit(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
        precheck_id=precheck.id,
        idempotency_key="precheck-current",
    )
    assert submitted.run.id

    with pytest.raises(ValueError, match="RESEARCH_TASK_PRECHECK_MISMATCH"):
        await task_service.submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json={**request_json, "execution_variant": "changed-after-precheck"},
            precheck_id=precheck.id,
            idempotency_key="precheck-mismatch",
        )


@pytest.mark.asyncio
async def test_expired_data_precheck_cannot_be_used_to_submit(auth_user) -> None:
    """Expiry is evaluated by the server at task submission, not the browser."""

    context = await _context(await _user_id(auth_user))
    request_json = _request_json(context)
    checked_at = datetime.now(timezone.utc)
    precheck = await context["prechecks"].create(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
        ttl_seconds=1,
        now=checked_at,
    )

    with pytest.raises(ValueError, match="RESEARCH_TASK_PRECHECK_EXPIRED"):
        await _task_service(context).submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json=request_json,
            precheck_id=precheck.id,
            idempotency_key="precheck-expired",
            now=checked_at + timedelta(seconds=2),
        )


@pytest.mark.asyncio
async def test_data_precheck_blocks_a_snapshot_without_complete_data_lineage(auth_user) -> None:
    """Imported/legacy metadata may be stored, but it cannot start a trusted run."""

    context = await _context(await _user_id(auth_user))
    incomplete = await DatasetRegistry().create_snapshot(
        user_id=context["user_id"],
        dataset_policy_version="dataset-policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        storage_uri="controlled://incomplete-discovery.parquet",
    )
    request_json = {
        **_request_json(context),
        "dataset_snapshot_id": incomplete.id,
    }

    precheck = await context["prechecks"].create(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=incomplete.id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
    )

    assert precheck.status == "FAIL"
    assert "RESEARCH_DATA_PRECHECK_SNAPSHOT_METADATA_INCOMPLETE" in precheck.details["errors"]
    assert "DATASET_SNAPSHOT_LEGACY_UNVERIFIED" in precheck.details["errors"]


@pytest.mark.asyncio
async def test_submission_revalidates_the_server_attested_object_before_creating_a_task(
    auth_user,
) -> None:
    """A passed receipt cannot launch after its logical dataset object drifts."""

    context = await _context(await _user_id(auth_user))
    request_json = _request_json(context)
    precheck = await context["prechecks"].create(
        user_id=context["user_id"],
        hypothesis_version_id=context["hypothesis"].id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["epoch"].id,
        profile_id="dev-single-process",
        profile_version="v1",
        promotion_policy_version="promotion-v1",
        request_json=request_json,
    )
    assert precheck.status == "PASS", precheck.details

    attestation = context["attestation"]
    context["resolver"].register(
        DatasetObjectAttestation(
            receipt_id="precheck-discovery-receipt-v2",
            user_id=context["user_id"],
            logical_object_id=attestation.logical_object_id,
            object_version="fixture-v2",
            object_digest="e" * 64,
            object_size_bytes=8192,
            storage_uri=attestation.storage_uri,
            attested_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
        await _task_service(context).submit(
            user_id=context["user_id"],
            hypothesis_version_id=context["hypothesis"].id,
            dataset_snapshot_id=context["dataset"].id,
            experiment_epoch_id=context["epoch"].id,
            profile_id="dev-single-process",
            profile_version="v1",
            promotion_policy_version="promotion-v1",
            request_json=request_json,
            precheck_id=precheck.id,
            idempotency_key="precheck-object-drift",
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchDatasetSnapshot, context["dataset"].id)
    assert stored is not None
    assert stored.integrity_status == "FAILED"


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
            receipt_id="precheck-discovery-receipt",
            user_id=user_id,
            logical_object_id="precheck-discovery-object",
            object_version="fixture-v1",
            object_digest="d" * 64,
            object_size_bytes=4096,
            storage_uri="controlled://precheck/discovery.parquet",
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
    prechecks = ResearchDataPrecheckService(dataset_registry=datasets)
    return {
        "user_id": user_id,
        "hypothesis": hypothesis,
        "dataset": dataset,
        "epoch": epoch,
        "prechecks": prechecks,
        "resolver": resolver,
        "attestation": attestation,
    }


def _task_service(context: dict[str, object]) -> ResearchTaskService:
    return ResearchTaskService(data_prechecks=context["prechecks"])


def _request_json(context: dict[str, object]) -> dict[str, object]:
    hypothesis = context["hypothesis"]
    dataset = context["dataset"]
    epoch = context["epoch"]
    return {
        "hypothesis_content_hash": hypothesis.content_hash,
        "dataset_snapshot_id": dataset.id,
        "experiment_epoch_id": epoch.id,
    }


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
