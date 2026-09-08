from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchDatasetSnapshot,
    ResearchForwardObservationSnapshot,
    ResearchRun,
)
from app.models.user import User
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.forward_observation import ForwardObservationService


@pytest.mark.asyncio
async def test_forward_observation_rejects_pre_freeze_data_and_never_exposes_storage_uri(
    auth_user,
) -> None:
    context = await _candidate_context(auth_user, "forward-main")
    user_id = context["user_id"]
    clock = _MutableClock(datetime.now(timezone.utc))
    service = _passing_service(context, clock)

    with pytest.raises(ValueError, match="FORWARD_OBSERVATION_CANDIDATE_NOT_FROZEN"):
        await service.start_epoch(
            user_id=user_id,
            candidate_id=context["candidate"].id,
            policy_version="forward-v1",
            policy=_policy(minimum_event_count=1),
        )

    frozen = await _freeze_candidate(user_id, context)
    start = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    clock.current = start
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-v1",
        policy=_policy(minimum_event_count=1),
    )

    clock.current = start + timedelta(seconds=1)
    with pytest.raises(ValueError, match="FORWARD_OBSERVATION_BEFORE_CANDIDATE_FREEZE"):
        await service.append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key="before-freeze",
            event_time=_as_utc(frozen.frozen_at),
            as_of_at=start + timedelta(seconds=1),
            **_snapshot_input("forward-observation-before-freeze-receipt-v1"),
        )

    clock.current = start + timedelta(seconds=2)
    with pytest.raises(ValueError, match="DATASET_OBJECT_RECEIPT_NOT_FOUND"):
        await service.append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key="unknown-receipt",
            event_time=start + timedelta(seconds=1),
            as_of_at=start + timedelta(seconds=2),
            **_snapshot_input("forward-observation-missing-receipt-v1"),
        )

    resolverless_receipt = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-observation-resolverless-receipt-v1",
        attested_at=start + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="DATASET_OBJECT_RESOLVER_REQUIRED"):
        await ForwardObservationService(
            clock=lambda: start + timedelta(seconds=2),
            quality_evaluator=_StaticQualityEvaluator({"market_data_complete": "PASS"}),
        ).append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key="resolverless-receipt",
            event_time=start + timedelta(seconds=1),
            as_of_at=start + timedelta(seconds=2),
            **_snapshot_input(resolverless_receipt),
        )

    post_freeze_receipt = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-observation-post-freeze-receipt-v1",
        attested_at=start + timedelta(seconds=1),
    )
    clock.current = start + timedelta(seconds=2)
    view = await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="post-freeze",
        event_time=start + timedelta(seconds=1),
        as_of_at=start + timedelta(seconds=2),
        **_snapshot_input(post_freeze_receipt),
    )

    assert view.quality_status == "PASS"
    assert "controlled://" not in str(view)
    readiness = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )
    assert readiness.status == "READY"
    assert readiness.observed_event_count == 1


@pytest.mark.asyncio
async def test_incomplete_observation_remains_open_for_later_natural_events(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-incomplete")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    start = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    clock = _MutableClock(start)
    service = _passing_service(context, clock)
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-v2",
        policy=_policy(minimum_event_count=2),
    )

    first_receipt = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-observation-event-1-receipt-v1",
        attested_at=start + timedelta(seconds=1),
    )
    clock.current = start + timedelta(seconds=2)
    await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="event-1",
        event_time=start + timedelta(seconds=1),
        as_of_at=start + timedelta(seconds=2),
        **_snapshot_input(first_receipt),
    )
    incomplete = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )
    assert incomplete.status == "BLOCKED"
    assert incomplete.reason_code == "BLOCKED_FORWARD_OBSERVATION_INCOMPLETE"

    second_receipt = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-observation-event-2-receipt-v1",
        attested_at=start + timedelta(seconds=3),
    )
    clock.current = start + timedelta(seconds=4)
    await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="event-2",
        event_time=start + timedelta(seconds=3),
        as_of_at=start + timedelta(seconds=4),
        **_snapshot_input(second_receipt),
    )
    ready = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )
    assert ready.status == "READY"
    assert ready.observed_event_count == 2


@pytest.mark.asyncio
async def test_forward_observation_rejects_legacy_compatibility_freeze(auth_user) -> None:
    from tests.test_ai_research_holdout_authorization import _context as _legacy_context

    user_id = await _user_id(auth_user)
    context = await _legacy_context(user_id)
    with pytest.raises(ValueError, match="^FORWARD_OBSERVATION_STRICT_FREEZE_REQUIRED$"):
        await ForwardObservationService(dataset_registry=_dataset_registry(context)).start_epoch(
            user_id=user_id,
            candidate_id=context["candidate"].id,
            policy_version="forward-legacy-denied-v1",
            policy=_policy(minimum_event_count=1),
        )


@pytest.mark.asyncio
async def test_forward_epoch_blocks_after_its_strict_receipt_drifts(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-receipt-drift")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    start = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    clock = _MutableClock(start)
    service = _passing_service(context, clock)
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-receipt-v1",
        policy=_policy(minimum_event_count=1),
    )
    async with async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == frozen.id
            )
        )
        assert receipt is not None
        receipt.market_trial_count += 1
        await session.commit()
    forward_receipt = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-observation-drifted-freeze-receipt-v1",
        attested_at=start + timedelta(seconds=1),
    )
    clock.current = start + timedelta(seconds=2)
    with pytest.raises(ValueError, match="^FORWARD_OBSERVATION_FREEZE_RECEIPT_INVALID$"):
        await service.append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key="receipt-drift",
            event_time=start + timedelta(seconds=1),
            as_of_at=start + timedelta(seconds=2),
            **_snapshot_input(forward_receipt),
        )
    readiness = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )
    assert readiness.status == "BLOCKED"
    assert readiness.reason_code == "BLOCKED_FORWARD_OBSERVATION_FREEZE_RECEIPT"
    assert readiness.observed_event_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("future_field", ["event_time", "as_of_at"])
async def test_forward_observation_rejects_future_event_or_as_of_time(
    auth_user,
    monkeypatch,
    future_field: str,
) -> None:
    context = await _candidate_context(auth_user, f"forward-future-{future_field}")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    monkeypatch.setattr(
        "app.services.research.forward_observation._now",
        lambda: server_now,
    )
    service = ForwardObservationService(dataset_registry=_dataset_registry(context))
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version=f"forward-future-{future_field}-v1",
        policy=_policy(minimum_event_count=1),
        now=server_now,
    )
    object_receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id=f"forward-future-{future_field}-receipt-v1",
        attested_at=server_now,
    )
    timestamps = {
        "event_time": server_now,
        "ingested_at": server_now + timedelta(seconds=30),
        "as_of_at": server_now,
    }
    timestamps[future_field] = server_now + timedelta(seconds=1)

    with pytest.raises(ValueError, match="^FORWARD_OBSERVATION_TIMESTAMP_IN_FUTURE$"):
        await service.append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key=f"future-{future_field}",
            **timestamps,
            **_snapshot_input(object_receipt_id),
        )


@pytest.mark.asyncio
async def test_forward_observation_rejects_forged_client_ingest_time(
    auth_user,
    monkeypatch,
) -> None:
    context = await _candidate_context(auth_user, "forward-forged-ingest")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    monkeypatch.setattr(
        "app.services.research.forward_observation._now",
        lambda: server_now,
    )
    service = ForwardObservationService(dataset_registry=_dataset_registry(context))
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-forged-ingest-v1",
        policy=_policy(minimum_event_count=1),
        now=server_now,
    )
    object_receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-forged-ingest-receipt-v1",
        attested_at=server_now,
    )

    with pytest.raises(ValueError, match="^FORWARD_OBSERVATION_CLIENT_TIME_MISMATCH$"):
        await service.append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key="forged-ingest",
            event_time=server_now,
            ingested_at=server_now + timedelta(seconds=30),
            as_of_at=server_now,
            **_snapshot_input(object_receipt_id),
        )


@pytest.mark.asyncio
async def test_forward_epoch_and_readiness_reject_client_clock_authority(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-forged-clock")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    service = ForwardObservationService(
        dataset_registry=_dataset_registry(context),
        clock=lambda: server_now,
    )

    with pytest.raises(ValueError, match="^FORWARD_OBSERVATION_CLIENT_TIME_MISMATCH$"):
        await service.start_epoch(
            user_id=user_id,
            candidate_id=frozen.id,
            policy_version="forward-forged-clock-v1",
            policy=_policy(minimum_event_count=1),
            now=server_now + timedelta(days=30),
        )

    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-forged-clock-v1",
        policy=_policy(minimum_event_count=1),
    )
    with pytest.raises(ValueError, match="^FORWARD_OBSERVATION_CLIENT_TIME_MISMATCH$"):
        await service.readiness(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            now=server_now + timedelta(days=30),
        )


@pytest.mark.asyncio
async def test_client_quality_pass_is_unknown_without_server_evaluator(
    auth_user,
    monkeypatch,
) -> None:
    context = await _candidate_context(auth_user, "forward-forged-quality")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    monkeypatch.setattr(
        "app.services.research.forward_observation._now",
        lambda: server_now,
    )
    service = ForwardObservationService(dataset_registry=_dataset_registry(context))
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-forged-quality-v1",
        policy=_policy(minimum_event_count=1),
        now=server_now,
    )
    object_receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-forged-quality-receipt-v1",
        attested_at=server_now,
    )

    view = await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="forged-quality",
        event_time=server_now,
        ingested_at=server_now,
        as_of_at=server_now,
        **_snapshot_input(object_receipt_id),
    )
    readiness = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        now=server_now,
    )

    assert view.quality_status == "UNKNOWN"
    assert readiness.status == "BLOCKED"
    assert readiness.reason_code == "BLOCKED_FORWARD_OBSERVATION_QUALITY"


@pytest.mark.asyncio
async def test_forward_quality_evaluator_executes_every_required_gate(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-quality-gates")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    service = ForwardObservationService(
        dataset_registry=_dataset_registry(context),
        clock=lambda: server_now,
        quality_evaluator=_StaticQualityEvaluator(
            {
                "market_data_complete": "PASS",
                "risk_limits_satisfied": "FAIL",
            }
        ),
    )
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-quality-gates-v1",
        policy=_policy(
            minimum_event_count=1,
            quality_gates={
                "market_data_complete": True,
                "risk_limits_satisfied": True,
            },
        ),
    )
    object_receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-quality-gates-receipt-v1",
        attested_at=server_now,
    )

    view = await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="unmet-quality-gate",
        event_time=server_now,
        as_of_at=server_now,
        **_snapshot_input(object_receipt_id),
    )
    readiness = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )

    assert view.quality_status == "FAIL"
    assert readiness.status == "BLOCKED"
    assert readiness.reason_code == "BLOCKED_FORWARD_OBSERVATION_QUALITY"


@pytest.mark.asyncio
async def test_forward_duration_begins_at_observation_epoch_start(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-duration-start")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(days=30)
    service = ForwardObservationService(
        dataset_registry=_dataset_registry(context),
        clock=lambda: server_now,
        quality_evaluator=_StaticQualityEvaluator({"market_data_complete": "PASS"}),
    )
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-duration-start-v1",
        policy=_policy(minimum_event_count=1, minimum_duration_days=1),
    )
    object_receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-duration-start-receipt-v1",
        attested_at=server_now,
    )
    await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="duration-event",
        event_time=server_now,
        as_of_at=server_now,
        **_snapshot_input(object_receipt_id),
    )

    readiness = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )

    assert readiness.status == "BLOCKED"
    assert readiness.reason_code == "BLOCKED_FORWARD_OBSERVATION_INCOMPLETE"
    assert readiness.observed_days == 0


@pytest.mark.asyncio
async def test_forward_readiness_revalidates_current_object_attestation(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-object-drift")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    clock = _MutableClock(server_now)
    service = _passing_service(context, clock)
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-object-drift-v1",
        policy=_policy(minimum_event_count=1),
    )
    receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-object-drift-receipt-v1",
        attested_at=server_now,
    )
    view = await service.append_snapshot(
        user_id=user_id,
        observation_epoch_id=epoch.id,
        idempotency_key="object-before-drift",
        event_time=server_now,
        as_of_at=server_now,
        **_snapshot_input(receipt_id),
    )
    resolver = context["resolver"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    resolver.register(
        DatasetObjectAttestation(
            receipt_id="forward-object-drift-receipt-v2",
            user_id=user_id,
            logical_object_id=f"{receipt_id}-object",
            object_version="version-2",
            object_digest="e" * 64,
            object_size_bytes=2048,
            storage_uri=f"controlled://forward-observation-fixtures/{receipt_id}.parquet",
            attested_at=server_now,
        )
    )

    readiness = await service.readiness(
        user_id=user_id,
        observation_epoch_id=epoch.id,
    )

    assert readiness.status == "BLOCKED"
    assert readiness.reason_code == "BLOCKED_FORWARD_OBSERVATION_DATA_INTEGRITY"
    async with async_session_maker() as session:
        snapshot = await session.get(ResearchForwardObservationSnapshot, view.id)
        assert snapshot is not None
        dataset = await session.get(ResearchDatasetSnapshot, view.dataset_snapshot_id)
        assert dataset is not None
        assert dataset.integrity_status == "FAILED"


@pytest.mark.asyncio
async def test_forward_quality_evaluator_must_return_every_policy_gate(auth_user) -> None:
    context = await _candidate_context(auth_user, "forward-quality-missing-gate")
    user_id = context["user_id"]
    frozen = await _freeze_candidate(user_id, context)
    server_now = _as_utc(frozen.frozen_at) + timedelta(seconds=10)
    service = ForwardObservationService(
        dataset_registry=_dataset_registry(context),
        clock=lambda: server_now,
        quality_evaluator=_StaticQualityEvaluator({"market_data_complete": "PASS"}),
    )
    epoch = await service.start_epoch(
        user_id=user_id,
        candidate_id=frozen.id,
        policy_version="forward-quality-missing-gate-v1",
        policy=_policy(
            minimum_event_count=1,
            quality_gates={
                "market_data_complete": True,
                "risk_limits_satisfied": True,
            },
        ),
    )
    receipt_id = _register_forward_receipt(
        context,
        user_id=user_id,
        receipt_id="forward-quality-missing-gate-receipt-v1",
        attested_at=server_now,
    )

    with pytest.raises(
        ValueError,
        match="^FORWARD_OBSERVATION_QUALITY_EVALUATION_INVALID$",
    ):
        await service.append_snapshot(
            user_id=user_id,
            observation_epoch_id=epoch.id,
            idempotency_key="missing-quality-gate",
            event_time=server_now,
            as_of_at=server_now,
            **_snapshot_input(receipt_id),
        )

    async with async_session_maker() as session:
        snapshot_count = len(
            list(
                await session.scalars(
                    select(ResearchForwardObservationSnapshot).where(
                        ResearchForwardObservationSnapshot.observation_epoch_id == epoch.id
                    )
                )
            )
        )
    assert snapshot_count == 0


async def _candidate_context(auth_user, suffix: str) -> dict[str, object]:
    from tests.test_ai_research_candidate_freeze_v2 import _published_candidate

    context, _dispatch, _attempt = await _published_candidate(auth_user, suffix)
    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate_id"])
        run = await session.get(ResearchRun, context["task"].run_id)
        assert candidate is not None and run is not None
    return {
        "user_id": context["task"].user_id,
        "candidate": candidate,
        "run": run,
        "resolver": context["resolver"],
        "datasets": context["datasets"],
    }


async def _freeze_candidate(user_id: str, context: dict[str, object]):
    candidate = context["candidate"]
    assert isinstance(candidate, ResearchCandidate)
    return await CandidateRegistry(dataset_registry=_dataset_registry(context)).freeze_discovery(
        user_id,
        candidate.id,
        frozen_by="researcher",
        expected_candidate_hash=candidate.candidate_hash,
    )


class _MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class _StaticQualityEvaluator:
    def __init__(self, gate_results: dict[str, str]) -> None:
        self._gate_results = gate_results

    async def evaluate(self, **_context: object) -> dict[str, object]:
        return {
            "evaluator_version": "fixture-forward-quality-v1",
            "gate_results": dict(self._gate_results),
            "evidence": {"source": "deterministic-test-evaluator"},
        }


def _passing_service(context: dict[str, object], clock: _MutableClock) -> ForwardObservationService:
    return ForwardObservationService(
        dataset_registry=_dataset_registry(context),
        clock=clock,
        quality_evaluator=_StaticQualityEvaluator({"market_data_complete": "PASS"}),
    )


def _policy(
    *,
    minimum_event_count: int,
    minimum_duration_days: int = 0,
    quality_gates: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "source": "fixture",
        "start_condition": "candidate_frozen",
        "minimum_duration_days": minimum_duration_days,
        "minimum_event_count": minimum_event_count,
        "max_ingest_delay_seconds": 60,
        "quality_gates": quality_gates or {"market_data_complete": True},
    }


def _dataset_registry(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


def _register_forward_receipt(
    context: dict[str, object],
    *,
    user_id: str,
    receipt_id: str,
    attested_at: datetime,
) -> str:
    resolver = context["resolver"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    resolver.register(
        DatasetObjectAttestation(
            receipt_id=receipt_id,
            user_id=user_id,
            logical_object_id=f"{receipt_id}-object",
            object_version="version-1",
            object_digest="f" * 64,
            object_size_bytes=1024,
            storage_uri=f"controlled://forward-observation-fixtures/{receipt_id}.parquet",
            attested_at=attested_at,
        )
    )
    return receipt_id


def _snapshot_input(object_receipt_id: str) -> dict[str, object]:
    return {
        "instrument_manifest": {"symbols": ["RB0"]},
        "split_manifest": {"kind": "natural-forward-event"},
        "source_manifest": {"provider": "fixture", "vintage": "2026-09-04"},
        "execution_policy": {"fill": "next_bar_open"},
        "object_receipt_id": object_receipt_id,
        "license_tags": ["test-license"],
        "quality_status": "PASS",
        "quality_evidence": {"coverage": "complete"},
    }


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())


def _hypothesis_payload() -> dict[str, object]:
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


def _as_utc(value: datetime | None) -> datetime:
    assert value is not None
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
