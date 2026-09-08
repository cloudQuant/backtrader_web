"""Append-only, post-freeze forward-observation records for protocol-v2 candidates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchForwardObservationEpoch,
    ResearchForwardObservationSnapshot,
)
from app.services.research.candidate_registry import (
    require_strict_freeze_receipt,
    strict_freeze_receipt_fingerprint,
    verify_candidate_integrity,
)
from app.services.research.canonical import content_hash
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)


@dataclass(frozen=True, slots=True)
class ForwardObservationReadiness:
    """The fail-closed readiness state for a candidate's observation window."""

    status: str
    reason_code: str | None
    observed_event_count: int
    observed_days: int


@dataclass(frozen=True, slots=True)
class ForwardObservationSnapshotView:
    """Explorer-safe observation receipt that deliberately omits controlled URIs."""

    id: str
    observation_epoch_id: str
    dataset_snapshot_id: str
    event_time: datetime
    ingested_at: datetime
    as_of_at: datetime
    candidate_frozen_at: datetime
    quality_status: str
    content_hash: str


class ForwardObservationQualityEvaluator(Protocol):
    """Deployment-owned evaluator for the quality gates frozen in an epoch policy."""

    async def evaluate(
        self,
        *,
        policy_version: str,
        quality_gates: dict[str, Any],
        dataset_snapshot: ResearchDatasetSnapshot,
        event_time: datetime,
        ingested_at: datetime,
        as_of_at: datetime,
    ) -> dict[str, Any]:
        """Return one deterministic status for every requested quality gate."""


class _UnavailableQualityEvaluator:
    """Fail-closed production default until a deployment wires a trusted evaluator."""

    async def evaluate(
        self,
        *,
        policy_version: str,
        quality_gates: dict[str, Any],
        dataset_snapshot: ResearchDatasetSnapshot,
        event_time: datetime,
        ingested_at: datetime,
        as_of_at: datetime,
    ) -> dict[str, Any]:
        del policy_version, dataset_snapshot, event_time, ingested_at, as_of_at
        return {
            "evaluator_version": "unavailable-v1",
            "gate_results": dict.fromkeys(quality_gates, "UNKNOWN"),
            "evidence": {"reason_code": "FORWARD_OBSERVATION_QUALITY_EVALUATOR_UNAVAILABLE"},
        }


class ForwardObservationService:
    """Own forward policy windows and reject pre-existing data masquerading as forward evidence."""

    def __init__(
        self,
        *,
        dataset_registry: DatasetRegistry | None = None,
        clock: Callable[[], datetime] | None = None,
        quality_evaluator: ForwardObservationQualityEvaluator | None = None,
    ) -> None:
        """Use server-attested objects for every post-freeze observation snapshot."""

        self._datasets = dataset_registry or DatasetRegistry()
        self._clock = clock or _now
        self._quality_evaluator = quality_evaluator or _UnavailableQualityEvaluator()

    async def start_epoch(
        self,
        *,
        user_id: str,
        candidate_id: str,
        policy_version: str,
        policy: dict[str, Any],
        now: datetime | None = None,
    ) -> ResearchForwardObservationEpoch:
        """Freeze an observation policy after, and only after, candidate freeze."""

        start_time = self._server_time(client_time=now)
        normalized_policy = _validate_policy(policy_version, policy)
        policy_hash = content_hash(normalized_policy)
        async with database.async_session_maker() as session:
            candidate = await _frozen_candidate(session, user_id, candidate_id)
            await verify_candidate_integrity(session, candidate)
            try:
                freeze_receipt = await require_strict_freeze_receipt(session, candidate)
            except ValueError:
                raise ValueError("FORWARD_OBSERVATION_STRICT_FREEZE_REQUIRED") from None
            freeze_receipt_fingerprint = strict_freeze_receipt_fingerprint(freeze_receipt)
            existing_result = await session.execute(
                select(ResearchForwardObservationEpoch).where(
                    ResearchForwardObservationEpoch.candidate_id == candidate.id,
                    ResearchForwardObservationEpoch.policy_version == policy_version,
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                if (
                    existing.policy_hash != policy_hash
                    or existing.freeze_receipt_id != freeze_receipt.id
                    or existing.freeze_receipt_fingerprint != freeze_receipt_fingerprint
                ):
                    raise ValueError("FORWARD_OBSERVATION_POLICY_VERSION_CONFLICT")
                return existing
            model = ResearchForwardObservationEpoch(
                user_id=user_id,
                run_id=candidate.run_id,
                candidate_id=candidate.id,
                policy_version=policy_version,
                policy=normalized_policy,
                policy_hash=policy_hash,
                candidate_frozen_at=_stored_utc(candidate.frozen_at),
                freeze_receipt_id=freeze_receipt.id,
                freeze_receipt_fingerprint=freeze_receipt_fingerprint,
                status="OPEN",
                started_at=start_time,
            )
            session.add(model)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing_result = await session.execute(
                    select(ResearchForwardObservationEpoch).where(
                        ResearchForwardObservationEpoch.candidate_id == candidate.id,
                        ResearchForwardObservationEpoch.policy_version == policy_version,
                    )
                )
                existing = existing_result.scalar_one_or_none()
                if (
                    existing is None
                    or existing.policy_hash != policy_hash
                    or existing.freeze_receipt_id != freeze_receipt.id
                    or existing.freeze_receipt_fingerprint != freeze_receipt_fingerprint
                ):
                    raise ValueError("FORWARD_OBSERVATION_POLICY_VERSION_CONFLICT") from None
                return existing
            await session.refresh(model)
            return model

    async def append_snapshot(
        self,
        *,
        user_id: str,
        observation_epoch_id: str,
        idempotency_key: str,
        event_time: datetime,
        as_of_at: datetime,
        instrument_manifest: dict[str, Any],
        split_manifest: dict[str, Any],
        source_manifest: dict[str, Any],
        execution_policy: dict[str, Any],
        object_receipt_id: str,
        license_tags: list[str],
        quality_status: str | None = None,
        quality_evidence: dict[str, Any] | None = None,
        ingested_at: datetime | None = None,
    ) -> ForwardObservationSnapshotView:
        """Append a source-bound observation that arrived after the frozen policy began."""

        if not idempotency_key.strip():
            raise ValueError("FORWARD_OBSERVATION_IDEMPOTENCY_KEY_REQUIRED")
        if not isinstance(object_receipt_id, str) or not object_receipt_id.strip():
            raise ValueError("DATASET_OBJECT_RECEIPT_REQUIRED")
        event_at = _as_utc(event_time)
        cutoff_at = _as_utc(as_of_at)
        server_ingest_at = self._server_time()
        if max(event_at, cutoff_at) > server_ingest_at:
            raise ValueError("FORWARD_OBSERVATION_TIMESTAMP_IN_FUTURE")
        if ingested_at is not None and _as_utc(ingested_at) != server_ingest_at:
            raise ValueError("FORWARD_OBSERVATION_CLIENT_TIME_MISMATCH")
        # Compatibility-only inputs are never accepted as quality authority.
        del quality_status, quality_evidence
        if (
            not isinstance(source_manifest, dict)
            or not str(source_manifest.get("provider") or "").strip()
        ):
            raise ValueError("FORWARD_OBSERVATION_SOURCE_REQUIRED")

        async with database.async_session_maker() as session:
            epoch = await _owner_epoch(session, user_id, observation_epoch_id)
            await _require_epoch_freeze_receipt(session, epoch)
            frozen_at = _stored_utc(epoch.candidate_frozen_at)
            started_at = _stored_utc(epoch.started_at)
            if min(event_at, server_ingest_at, cutoff_at) <= frozen_at:
                raise ValueError("FORWARD_OBSERVATION_BEFORE_CANDIDATE_FREEZE")
            if min(event_at, server_ingest_at, cutoff_at) < started_at:
                raise ValueError("FORWARD_OBSERVATION_BEFORE_POLICY_START")
            if cutoff_at < event_at:
                raise ValueError("FORWARD_OBSERVATION_AS_OF_BEFORE_EVENT")
            policy = _validate_policy(epoch.policy_version, dict(epoch.policy or {}))
            if str(source_manifest["provider"]).strip() != policy["source"]:
                raise ValueError("FORWARD_OBSERVATION_SOURCE_POLICY_MISMATCH")
            existing_result = await session.execute(
                select(ResearchForwardObservationSnapshot, ResearchDatasetSnapshot)
                .join(
                    ResearchDatasetSnapshot,
                    ResearchDatasetSnapshot.id
                    == ResearchForwardObservationSnapshot.dataset_snapshot_id,
                )
                .where(
                    ResearchForwardObservationSnapshot.observation_epoch_id == epoch.id,
                    ResearchForwardObservationSnapshot.idempotency_key == idempotency_key,
                )
            )
            existing_row = existing_result.one_or_none()
            if existing_row is not None:
                existing, existing_dataset = existing_row
                await self._datasets.revalidate_snapshot_in_session(
                    session,
                    snapshot=existing_dataset,
                )
                _require_existing_request_match(
                    existing,
                    existing_dataset,
                    epoch=epoch,
                    event_time=event_at,
                    as_of_at=cutoff_at,
                    instrument_manifest=instrument_manifest,
                    split_manifest=split_manifest,
                    source_manifest=source_manifest,
                    execution_policy=execution_policy,
                    object_receipt_id=object_receipt_id,
                    license_tags=license_tags,
                )
                return _snapshot_view(existing)

            if epoch.status not in {"OPEN", "READY"}:
                raise ValueError("FORWARD_OBSERVATION_EPOCH_NOT_OPEN")
            if server_ingest_at - event_at > timedelta(seconds=policy["max_ingest_delay_seconds"]):
                raise ValueError("FORWARD_OBSERVATION_INGEST_DELAY_EXCEEDED")

            dataset = await self._datasets.create_attested_snapshot_in_session(
                session,
                user_id=user_id,
                dataset_policy_version=epoch.policy_version,
                partition_kind="FORWARD_OBSERVATION",
                instrument_manifest=dict(instrument_manifest),
                split_manifest=dict(split_manifest),
                source_manifest=dict(source_manifest),
                execution_policy=dict(execution_policy),
                point_in_time_cutoff=cutoff_at,
                license_tags=list(license_tags),
                candidate_frozen_at=frozen_at,
                object_receipt_id=object_receipt_id,
            )
            require_verified_snapshot_integrity(dataset)
            if _stored_utc(dataset.integrity_checked_at) > server_ingest_at:
                raise ValueError("FORWARD_OBSERVATION_ATTESTATION_IN_FUTURE")
            evaluated_status, evaluated_evidence = await self._evaluate_quality(
                epoch=epoch,
                policy=policy,
                dataset=dataset,
                event_time=event_at,
                ingested_at=server_ingest_at,
                as_of_at=cutoff_at,
            )
            snapshot_hash = _observation_content_hash(
                policy_version=epoch.policy_version,
                dataset=dataset,
                event_time=event_at,
                ingested_at=server_ingest_at,
                as_of_at=cutoff_at,
                quality_status=evaluated_status,
                quality_evidence=evaluated_evidence,
            )
            observation = ResearchForwardObservationSnapshot(
                user_id=user_id,
                observation_epoch_id=epoch.id,
                dataset_snapshot_id=dataset.id,
                idempotency_key=idempotency_key,
                event_time=event_at,
                ingested_at=server_ingest_at,
                as_of_at=cutoff_at,
                candidate_frozen_at=frozen_at,
                quality_status=evaluated_status,
                quality_evidence=evaluated_evidence,
                content_hash=snapshot_hash,
            )
            session.add(observation)
            await session.flush()
            await _refresh_epoch_readiness(
                session,
                epoch,
                now=server_ingest_at,
                datasets=self._datasets,
            )
            await session.commit()
            await session.refresh(observation)
            return _snapshot_view(observation)

    async def readiness(
        self,
        *,
        user_id: str,
        observation_epoch_id: str,
        now: datetime | None = None,
    ) -> ForwardObservationReadiness:
        """Return a fail-closed readiness receipt without treating historical data as forward proof."""

        server_now = self._server_time(client_time=now)
        async with database.async_session_maker() as session:
            epoch = await _owner_epoch(session, user_id, observation_epoch_id)
            try:
                await _require_epoch_freeze_receipt(session, epoch)
            except ValueError:
                epoch.status = "BLOCKED"
                await session.commit()
                return ForwardObservationReadiness(
                    status="BLOCKED",
                    reason_code="BLOCKED_FORWARD_OBSERVATION_FREEZE_RECEIPT",
                    observed_event_count=0,
                    observed_days=0,
                )
            return await _refresh_epoch_readiness(
                session,
                epoch,
                now=server_now,
                datasets=self._datasets,
                persist=True,
            )

    def _server_time(self, *, client_time: datetime | None = None) -> datetime:
        server_time = _as_utc(self._clock())
        if client_time is not None and _as_utc(client_time) != server_time:
            raise ValueError("FORWARD_OBSERVATION_CLIENT_TIME_MISMATCH")
        return server_time

    async def _evaluate_quality(
        self,
        *,
        epoch: ResearchForwardObservationEpoch,
        policy: dict[str, Any],
        dataset: ResearchDatasetSnapshot,
        event_time: datetime,
        ingested_at: datetime,
        as_of_at: datetime,
    ) -> tuple[str, dict[str, Any]]:
        try:
            raw_result = await self._quality_evaluator.evaluate(
                policy_version=epoch.policy_version,
                quality_gates=dict(policy["quality_gates"]),
                dataset_snapshot=dataset,
                event_time=event_time,
                ingested_at=ingested_at,
                as_of_at=as_of_at,
            )
        except Exception as exc:
            raise ValueError("FORWARD_OBSERVATION_QUALITY_EVALUATION_FAILED") from exc
        return _normalize_quality_evaluation(raw_result, policy["quality_gates"])


async def _frozen_candidate(
    session: Any,
    user_id: str,
    candidate_id: str,
) -> ResearchCandidate:
    result = await session.execute(
        select(ResearchCandidate)
        .where(ResearchCandidate.id == candidate_id, ResearchCandidate.user_id == user_id)
        .with_for_update()
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise ValueError("FORWARD_OBSERVATION_CANDIDATE_NOT_FOUND")
    if candidate.freeze_status != "FROZEN" or candidate.frozen_at is None:
        raise ValueError("FORWARD_OBSERVATION_CANDIDATE_NOT_FROZEN")
    return candidate


async def _owner_epoch(
    session: Any,
    user_id: str,
    observation_epoch_id: str,
) -> ResearchForwardObservationEpoch:
    result = await session.execute(
        select(ResearchForwardObservationEpoch)
        .where(
            ResearchForwardObservationEpoch.id == observation_epoch_id,
            ResearchForwardObservationEpoch.user_id == user_id,
        )
        .with_for_update()
    )
    epoch = result.scalar_one_or_none()
    if epoch is None:
        raise ValueError("FORWARD_OBSERVATION_EPOCH_NOT_FOUND")
    return epoch


async def _require_epoch_freeze_receipt(
    session: Any,
    epoch: ResearchForwardObservationEpoch,
) -> None:
    """Re-prove the epoch's original strict candidate-freeze binding."""

    candidate = await session.get(ResearchCandidate, epoch.candidate_id)
    if candidate is None or candidate.user_id != epoch.user_id or candidate.run_id != epoch.run_id:
        raise ValueError("FORWARD_OBSERVATION_FREEZE_RECEIPT_INVALID")
    try:
        receipt = await require_strict_freeze_receipt(session, candidate)
    except ValueError:
        raise ValueError("FORWARD_OBSERVATION_FREEZE_RECEIPT_INVALID") from None
    if (
        epoch.freeze_receipt_id != receipt.id
        or epoch.freeze_receipt_fingerprint != strict_freeze_receipt_fingerprint(receipt)
    ):
        raise ValueError("FORWARD_OBSERVATION_FREEZE_RECEIPT_INVALID")


async def _refresh_epoch_readiness(
    session: Any,
    epoch: ResearchForwardObservationEpoch,
    *,
    now: datetime,
    datasets: DatasetRegistry,
    persist: bool = False,
) -> ForwardObservationReadiness:
    policy = _validate_policy(epoch.policy_version, dict(epoch.policy or {}))
    observations_result = await session.execute(
        select(ResearchForwardObservationSnapshot, ResearchDatasetSnapshot)
        .join(
            ResearchDatasetSnapshot,
            ResearchDatasetSnapshot.id == ResearchForwardObservationSnapshot.dataset_snapshot_id,
        )
        .where(ResearchForwardObservationSnapshot.observation_epoch_id == epoch.id)
    )
    rows = list(observations_result.all())
    statuses: list[str] = []
    integrity_error: str | None = None
    started_at = _stored_utc(epoch.started_at)
    server_now = _as_utc(now)
    for observation, dataset in rows:
        try:
            await datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
            require_verified_snapshot_integrity(dataset)
            _verify_observation_integrity(
                observation,
                dataset,
                epoch=epoch,
                policy=policy,
                now=server_now,
            )
        except ValueError as exc:
            integrity_error = str(exc)
            break
        statuses.append(observation.quality_status)
    observed_days = max(
        0,
        int((server_now - started_at).total_seconds() // 86_400),
    )
    if integrity_error is not None:
        receipt = ForwardObservationReadiness(
            status="BLOCKED",
            reason_code="BLOCKED_FORWARD_OBSERVATION_DATA_INTEGRITY",
            observed_event_count=0,
            observed_days=observed_days,
        )
    elif any(status != "PASS" for status in statuses):
        receipt = ForwardObservationReadiness(
            status="BLOCKED",
            reason_code="BLOCKED_FORWARD_OBSERVATION_QUALITY",
            observed_event_count=sum(status == "PASS" for status in statuses),
            observed_days=observed_days,
        )
    elif (
        sum(status == "PASS" for status in statuses) < policy["minimum_event_count"]
        or observed_days < policy["minimum_duration_days"]
    ):
        receipt = ForwardObservationReadiness(
            status="BLOCKED",
            reason_code="BLOCKED_FORWARD_OBSERVATION_INCOMPLETE",
            observed_event_count=sum(status == "PASS" for status in statuses),
            observed_days=observed_days,
        )
    else:
        receipt = ForwardObservationReadiness(
            status="READY",
            reason_code=None,
            observed_event_count=sum(status == "PASS" for status in statuses),
            observed_days=observed_days,
        )
    if persist:
        if receipt.status == "READY" and epoch.ready_at is None:
            epoch.status = "READY"
            epoch.ready_at = server_now
        elif receipt.reason_code in {
            "BLOCKED_FORWARD_OBSERVATION_QUALITY",
            "BLOCKED_FORWARD_OBSERVATION_DATA_INTEGRITY",
        }:
            epoch.status = "BLOCKED"
        await session.commit()
    elif receipt.status == "READY" and epoch.status == "OPEN":
        epoch.status = "READY"
        epoch.ready_at = server_now
    elif receipt.status == "BLOCKED" and receipt.reason_code in {
        "BLOCKED_FORWARD_OBSERVATION_QUALITY",
        "BLOCKED_FORWARD_OBSERVATION_DATA_INTEGRITY",
    }:
        epoch.status = "BLOCKED"
    return receipt


def _validate_policy(policy_version: str, policy: dict[str, Any]) -> dict[str, Any]:
    if not policy_version.strip() or not isinstance(policy, dict):
        raise ValueError("FORWARD_OBSERVATION_POLICY_INVALID")
    source = str(policy.get("source") or "").strip()
    start_condition = str(policy.get("start_condition") or "").strip()
    try:
        minimum_duration_days = int(policy["minimum_duration_days"])
        minimum_event_count = int(policy["minimum_event_count"])
        max_ingest_delay_seconds = int(policy["max_ingest_delay_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("FORWARD_OBSERVATION_POLICY_INVALID") from exc
    if (
        not source
        or not start_condition
        or minimum_duration_days < 0
        or minimum_event_count < 1
        or max_ingest_delay_seconds < 0
    ):
        raise ValueError("FORWARD_OBSERVATION_POLICY_INVALID")
    quality_gates = policy.get("quality_gates", {})
    if (
        not isinstance(quality_gates, dict)
        or not quality_gates
        or any(not isinstance(name, str) or not name.strip() for name in quality_gates)
    ):
        raise ValueError("FORWARD_OBSERVATION_POLICY_INVALID")
    return {
        "source": source,
        "start_condition": start_condition,
        "minimum_duration_days": minimum_duration_days,
        "minimum_event_count": minimum_event_count,
        "max_ingest_delay_seconds": max_ingest_delay_seconds,
        "quality_gates": dict(quality_gates),
    }


def _normalize_quality_evaluation(
    raw_result: object,
    quality_gates: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not isinstance(raw_result, dict):
        raise ValueError("FORWARD_OBSERVATION_QUALITY_EVALUATION_INVALID")
    evaluator_version = raw_result.get("evaluator_version")
    gate_results = raw_result.get("gate_results")
    evidence = raw_result.get("evidence", {})
    required_gates = set(quality_gates)
    if (
        not isinstance(evaluator_version, str)
        or not evaluator_version.strip()
        or not isinstance(gate_results, dict)
        or set(gate_results) != required_gates
        or not isinstance(evidence, dict)
    ):
        raise ValueError("FORWARD_OBSERVATION_QUALITY_EVALUATION_INVALID")
    normalized_results: dict[str, str] = {}
    for gate_name in quality_gates:
        status = gate_results[gate_name]
        if status not in {"PASS", "FAIL", "UNKNOWN"}:
            raise ValueError("FORWARD_OBSERVATION_QUALITY_EVALUATION_INVALID")
        normalized_results[gate_name] = status
    if any(status == "FAIL" for status in normalized_results.values()):
        aggregate_status = "FAIL"
    elif all(status == "PASS" for status in normalized_results.values()):
        aggregate_status = "PASS"
    else:
        aggregate_status = "UNKNOWN"
    return aggregate_status, {
        "schema_version": "forward-observation-quality-v1",
        "evaluator_version": evaluator_version,
        "gate_results": normalized_results,
        "evidence": dict(evidence),
    }


def _verify_quality_record(
    quality_status: str,
    quality_evidence: dict[str, Any],
    quality_gates: dict[str, Any],
) -> None:
    if not isinstance(quality_evidence, dict):
        raise ValueError("FORWARD_OBSERVATION_QUALITY_EVIDENCE_INVALID")
    stored_result = {
        "evaluator_version": quality_evidence.get("evaluator_version"),
        "gate_results": quality_evidence.get("gate_results"),
        "evidence": quality_evidence.get("evidence", {}),
    }
    expected_status, _normalized = _normalize_quality_evaluation(stored_result, quality_gates)
    if (
        quality_evidence.get("schema_version") != "forward-observation-quality-v1"
        or quality_status != expected_status
    ):
        raise ValueError("FORWARD_OBSERVATION_QUALITY_EVIDENCE_INVALID")


def _observation_content_hash(
    *,
    policy_version: str,
    dataset: ResearchDatasetSnapshot,
    event_time: datetime,
    ingested_at: datetime,
    as_of_at: datetime,
    quality_status: str,
    quality_evidence: dict[str, Any],
) -> str:
    return content_hash(
        {
            "policy_version": policy_version,
            "instrument_manifest": dict(dataset.instrument_manifest or {}),
            "split_manifest": dict(dataset.split_manifest or {}),
            "source_manifest": dict(dataset.source_manifest or {}),
            "execution_policy": dict(dataset.execution_policy or {}),
            "event_time": _stored_utc(event_time),
            "ingested_at": _stored_utc(ingested_at),
            "as_of_at": _stored_utc(as_of_at),
            "object_receipt_id": dataset.object_receipt_id,
            "license_tags": list(dataset.license_tags or []),
            "quality_status": quality_status,
            "quality_evidence": dict(quality_evidence),
        }
    )


def _verify_observation_integrity(
    observation: ResearchForwardObservationSnapshot,
    dataset: ResearchDatasetSnapshot,
    *,
    epoch: ResearchForwardObservationEpoch,
    policy: dict[str, Any],
    now: datetime,
) -> None:
    event_at = _stored_utc(observation.event_time)
    ingest_at = _stored_utc(observation.ingested_at)
    cutoff_at = _stored_utc(observation.as_of_at)
    frozen_at = _stored_utc(epoch.candidate_frozen_at)
    started_at = _stored_utc(epoch.started_at)
    if (
        observation.user_id != epoch.user_id
        or observation.observation_epoch_id != epoch.id
        or observation.dataset_snapshot_id != dataset.id
        or dataset.user_id != epoch.user_id
        or dataset.dataset_policy_version != epoch.policy_version
        or dataset.partition_kind != "FORWARD_OBSERVATION"
        or _stored_utc(dataset.point_in_time_cutoff) != cutoff_at
    ):
        raise ValueError("FORWARD_OBSERVATION_IDENTITY_MISMATCH")
    if _stored_utc(dataset.integrity_checked_at) > now:
        raise ValueError("FORWARD_OBSERVATION_ATTESTATION_IN_FUTURE")
    if observation.candidate_frozen_at != epoch.candidate_frozen_at:
        if _stored_utc(observation.candidate_frozen_at) != frozen_at:
            raise ValueError("FORWARD_OBSERVATION_FREEZE_TIME_MISMATCH")
    if max(event_at, ingest_at, cutoff_at) > now:
        raise ValueError("FORWARD_OBSERVATION_TIMESTAMP_IN_FUTURE")
    if min(event_at, ingest_at, cutoff_at) <= frozen_at:
        raise ValueError("FORWARD_OBSERVATION_BEFORE_CANDIDATE_FREEZE")
    if min(event_at, ingest_at, cutoff_at) < started_at:
        raise ValueError("FORWARD_OBSERVATION_BEFORE_POLICY_START")
    if cutoff_at < event_at:
        raise ValueError("FORWARD_OBSERVATION_AS_OF_BEFORE_EVENT")
    if ingest_at - event_at > timedelta(seconds=policy["max_ingest_delay_seconds"]):
        raise ValueError("FORWARD_OBSERVATION_INGEST_DELAY_EXCEEDED")
    _verify_quality_record(
        observation.quality_status,
        dict(observation.quality_evidence or {}),
        policy["quality_gates"],
    )
    expected_hash = _observation_content_hash(
        policy_version=epoch.policy_version,
        dataset=dataset,
        event_time=event_at,
        ingested_at=ingest_at,
        as_of_at=cutoff_at,
        quality_status=observation.quality_status,
        quality_evidence=dict(observation.quality_evidence or {}),
    )
    if observation.content_hash != expected_hash:
        raise ValueError("FORWARD_OBSERVATION_CONTENT_HASH_MISMATCH")


def _require_existing_request_match(
    observation: ResearchForwardObservationSnapshot,
    dataset: ResearchDatasetSnapshot,
    *,
    epoch: ResearchForwardObservationEpoch,
    event_time: datetime,
    as_of_at: datetime,
    instrument_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    source_manifest: dict[str, Any],
    execution_policy: dict[str, Any],
    object_receipt_id: str,
    license_tags: list[str],
) -> None:
    policy = _validate_policy(epoch.policy_version, dict(epoch.policy or {}))
    _verify_observation_integrity(
        observation,
        dataset,
        epoch=epoch,
        policy=policy,
        now=_stored_utc(observation.ingested_at),
    )
    if (
        _stored_utc(observation.event_time) != event_time
        or _stored_utc(observation.as_of_at) != as_of_at
        or dict(dataset.instrument_manifest or {}) != instrument_manifest
        or dict(dataset.split_manifest or {}) != split_manifest
        or dict(dataset.source_manifest or {}) != source_manifest
        or dict(dataset.execution_policy or {}) != execution_policy
        or dataset.object_receipt_id != object_receipt_id
        or list(dataset.license_tags or []) != license_tags
    ):
        raise ValueError("FORWARD_OBSERVATION_IDEMPOTENCY_CONFLICT")


def _snapshot_view(model: ResearchForwardObservationSnapshot) -> ForwardObservationSnapshotView:
    return ForwardObservationSnapshotView(
        id=model.id,
        observation_epoch_id=model.observation_epoch_id,
        dataset_snapshot_id=model.dataset_snapshot_id,
        event_time=model.event_time,
        ingested_at=model.ingested_at,
        as_of_at=model.as_of_at,
        candidate_frozen_at=model.candidate_frozen_at,
        quality_status=model.quality_status,
        content_hash=model.content_hash,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("FORWARD_OBSERVATION_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime | None) -> datetime:
    """Normalize ORM timestamps from engines that do not preserve tzinfo."""

    if value is None:
        raise ValueError("FORWARD_OBSERVATION_STORED_TIMESTAMP_MISSING")
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
