"""Server-owned, expiry-bound data prechecks for protocol-v2 submissions.

The browser may display a precheck receipt, but it never decides whether that
receipt is still valid.  The same canonical launch binding is calculated when
the receipt is created and again in the task-creation transaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchDataPrecheck,
    ResearchDatasetSnapshot,
    ResearchExperimentEpoch,
    ResearchHypothesisVersion,
)
from app.services.research.canonical import content_hash
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)

DEFAULT_PRECHECK_TTL_SECONDS = 15 * 60
MAX_PRECHECK_TTL_SECONDS = 60 * 60


class ResearchDataPrecheckService:
    """Produce and validate immutable evidence for one launch binding."""

    def __init__(self, *, dataset_registry: DatasetRegistry | None = None) -> None:
        """Use one deployment-owned resolver for both precheck and submission fences."""

        self._datasets = dataset_registry or DatasetRegistry()

    async def create(
        self,
        *,
        user_id: str,
        hypothesis_version_id: str,
        dataset_snapshot_id: str,
        experiment_epoch_id: str,
        profile_id: str,
        profile_version: str,
        promotion_policy_version: str,
        request_json: dict[str, Any],
        workspace_id: str | None = None,
        ttl_seconds: int = DEFAULT_PRECHECK_TTL_SECONDS,
        now: datetime | None = None,
    ) -> ResearchDataPrecheck:
        """Persist a server-evaluated precheck without trusting a client flag."""

        if ttl_seconds < 1 or ttl_seconds > MAX_PRECHECK_TTL_SECONDS:
            raise ValueError("RESEARCH_DATA_PRECHECK_TTL_INVALID")
        checked_at = _as_utc(now or _now())
        expires_at = checked_at + timedelta(seconds=ttl_seconds)
        profile = await CapabilityRegistry().get(profile_id, profile_version)
        decision = await CapabilityRegistry().evaluate(
            profile_id,
            profile_version,
            required=("protocol_v2",),
        )
        integrity_error: str | None = None
        try:
            await self._datasets.revalidate_snapshot(user_id, dataset_snapshot_id)
        except ValueError as exc:
            # A precheck remains a durable, explainable BLOCKED/FAIL result
            # rather than trusting an unverified browser-side data assertion.
            integrity_error = str(exc)

        async with database.async_session_maker() as session:
            hypothesis = await _owner_hypothesis(session, user_id, hypothesis_version_id)
            dataset = await _owner_explorer_dataset(session, user_id, dataset_snapshot_id)
            epoch = await _owner_epoch(session, user_id, experiment_epoch_id)
            errors = _binding_errors(
                hypothesis=hypothesis,
                dataset=dataset,
                epoch=epoch,
                request_json=request_json,
            )
            if integrity_error is not None:
                errors.append(integrity_error)
            if profile is None or not decision.allowed:
                errors.append(
                    f"{decision.code or 'BLOCKED_TOPOLOGY_CAPABILITY'}:"
                    f"{','.join(decision.missing_capabilities)}"
                )
            status = (
                "PASS"
                if not errors
                else (
                    "BLOCKED"
                    if profile is None
                    or not decision.allowed
                    or integrity_error
                    in {
                        "DATASET_OBJECT_RESOLVER_REQUIRED",
                        "DATASET_OBJECT_REVALIDATION_UNAVAILABLE",
                    }
                    else "FAIL"
                )
            )
            reason_code = errors[0] if errors else None
            input_hash = launch_input_hash(
                hypothesis=hypothesis,
                dataset=dataset,
                epoch=epoch,
                profile=profile,
                profile_id=profile_id,
                profile_version=profile_version,
                promotion_policy_version=promotion_policy_version,
                request_json=request_json,
                workspace_id=workspace_id,
            )
            details = _details(
                hypothesis=hypothesis,
                dataset=dataset,
                epoch=epoch,
                profile=profile,
                errors=errors,
            )
            model = ResearchDataPrecheck(
                user_id=user_id,
                hypothesis_version_id=hypothesis.id,
                dataset_snapshot_id=dataset.id,
                experiment_epoch_id=epoch.id,
                profile_id=profile_id,
                profile_version=profile_version,
                promotion_policy_version=promotion_policy_version,
                input_hash=input_hash,
                evidence_hash=precheck_evidence_hash(
                    input_hash=input_hash,
                    status=status,
                    reason_code=reason_code,
                    details=details,
                    checked_at=checked_at,
                    expires_at=expires_at,
                ),
                status=status,
                reason_code=reason_code,
                details=details,
                checked_at=checked_at,
                expires_at=expires_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model

    async def require_current(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        precheck_id: str | None,
        hypothesis: ResearchHypothesisVersion,
        dataset: ResearchDatasetSnapshot,
        epoch: ResearchExperimentEpoch,
        profile: CapabilityProfile,
        profile_id: str,
        profile_version: str,
        promotion_policy_version: str,
        request_json: dict[str, Any],
        workspace_id: str | None,
        now: datetime | None = None,
    ) -> ResearchDataPrecheck:
        """Return only a PASS receipt that exactly matches this current launch."""

        if precheck_id is None or not precheck_id.strip():
            raise ValueError("RESEARCH_TASK_PRECHECK_REQUIRED")
        result = await session.execute(
            select(ResearchDataPrecheck).where(
                ResearchDataPrecheck.id == precheck_id,
                ResearchDataPrecheck.user_id == user_id,
            )
        )
        precheck = result.scalar_one_or_none()
        if precheck is None:
            raise ValueError("RESEARCH_TASK_PRECHECK_NOT_FOUND")

        expected_evidence_hash = precheck_evidence_hash(
            input_hash=precheck.input_hash,
            status=precheck.status,
            reason_code=precheck.reason_code,
            details=dict(precheck.details or {}),
            checked_at=_stored_utc(precheck.checked_at),
            expires_at=_stored_utc(precheck.expires_at),
        )
        if precheck.evidence_hash != expected_evidence_hash:
            raise ValueError("RESEARCH_TASK_PRECHECK_EVIDENCE_CORRUPT")
        if _stored_utc(precheck.expires_at) <= _as_utc(now or _now()):
            raise ValueError("RESEARCH_TASK_PRECHECK_EXPIRED")
        if precheck.status != "PASS":
            raise ValueError("RESEARCH_TASK_PRECHECK_NOT_PASSED")
        await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
        require_verified_snapshot_integrity(dataset)

        expected_input_hash = launch_input_hash(
            hypothesis=hypothesis,
            dataset=dataset,
            epoch=epoch,
            profile=profile,
            profile_id=profile_id,
            profile_version=profile_version,
            promotion_policy_version=promotion_policy_version,
            request_json=request_json,
            workspace_id=workspace_id,
        )
        if precheck.input_hash != expected_input_hash:
            raise ValueError("RESEARCH_TASK_PRECHECK_MISMATCH")
        return precheck


def launch_input_hash(
    *,
    hypothesis: ResearchHypothesisVersion,
    dataset: ResearchDatasetSnapshot,
    epoch: ResearchExperimentEpoch,
    profile: CapabilityProfile | None,
    profile_id: str,
    profile_version: str,
    promotion_policy_version: str,
    request_json: dict[str, Any],
    workspace_id: str | None,
) -> str:
    """Canonical identity for every field that can alter launch semantics."""

    return content_hash(
        {
            "hypothesis": {
                "id": hypothesis.id,
                "content_hash": hypothesis.content_hash,
            },
            "dataset": {
                "id": dataset.id,
                "snapshot_identity_hash": dataset.snapshot_identity_hash,
                "dataset_policy_version": dataset.dataset_policy_version,
                "execution_policy": dataset.execution_policy,
                "point_in_time_cutoff": _stored_utc(dataset.point_in_time_cutoff),
            },
            "epoch": {
                "id": epoch.id,
                "family_hash": epoch.family_hash,
                "dataset_policy_version": epoch.dataset_policy_version,
                "search_budget": epoch.search_budget,
            },
            "profile": {
                "id": profile_id,
                "version": profile_version,
                "evidence_hash": profile.evidence_hash if profile is not None else None,
            },
            "promotion_policy_version": promotion_policy_version,
            "request_json": request_json,
            "workspace_id": workspace_id,
        }
    )


def precheck_evidence_hash(
    *,
    input_hash: str,
    status: str,
    reason_code: str | None,
    details: dict[str, Any],
    checked_at: datetime,
    expires_at: datetime,
) -> str:
    """Bind the precheck verdict, its server evidence and its validity window."""

    return content_hash(
        {
            "input_hash": input_hash,
            "status": status,
            "reason_code": reason_code,
            "details": details,
            "checked_at": _stored_utc(checked_at),
            "expires_at": _stored_utc(expires_at),
        }
    )


async def _owner_hypothesis(
    session: AsyncSession,
    user_id: str,
    hypothesis_version_id: str,
) -> ResearchHypothesisVersion:
    result = await session.execute(
        select(ResearchHypothesisVersion).where(
            ResearchHypothesisVersion.id == hypothesis_version_id,
            ResearchHypothesisVersion.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("RESEARCH_DATA_PRECHECK_HYPOTHESIS_NOT_FOUND")
    return model


async def _owner_explorer_dataset(
    session: AsyncSession,
    user_id: str,
    dataset_snapshot_id: str,
) -> ResearchDatasetSnapshot:
    result = await session.execute(
        select(ResearchDatasetSnapshot).where(
            ResearchDatasetSnapshot.id == dataset_snapshot_id,
            ResearchDatasetSnapshot.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("RESEARCH_DATA_PRECHECK_DATASET_NOT_FOUND")
    if model.partition_kind == "SEALED_HOLDOUT":
        raise ValueError("SEALED_DATA_ACCESS_DENIED")
    return model


async def _owner_epoch(
    session: AsyncSession,
    user_id: str,
    experiment_epoch_id: str,
) -> ResearchExperimentEpoch:
    result = await session.execute(
        select(ResearchExperimentEpoch).where(
            ResearchExperimentEpoch.id == experiment_epoch_id,
            ResearchExperimentEpoch.user_id == user_id,
        )
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise ValueError("RESEARCH_DATA_PRECHECK_EPOCH_NOT_FOUND")
    return model


def _binding_errors(
    *,
    hypothesis: ResearchHypothesisVersion,
    dataset: ResearchDatasetSnapshot,
    epoch: ResearchExperimentEpoch,
    request_json: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if hypothesis.status != "CONFIRMED":
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_UNCONFIRMED")
    if epoch.status != "OPEN":
        errors.append("RESEARCH_DATA_PRECHECK_EPOCH_NOT_OPEN")
    if epoch.hypothesis_version_id != hypothesis.id:
        errors.append("RESEARCH_DATA_PRECHECK_EPOCH_HYPOTHESIS_MISMATCH")
    policy_version = hypothesis.canonical_payload.get("dataset_policy_version")
    if (
        not isinstance(policy_version, str)
        or policy_version != dataset.dataset_policy_version
        or policy_version != epoch.dataset_policy_version
    ):
        errors.append("RESEARCH_DATA_PRECHECK_POLICY_MISMATCH")
    if not isinstance(request_json, dict):
        errors.append("RESEARCH_DATA_PRECHECK_REQUEST_INVALID")
    elif (
        request_json.get("hypothesis_content_hash") != hypothesis.content_hash
        or request_json.get("dataset_snapshot_id") != dataset.id
        or request_json.get("experiment_epoch_id") != epoch.id
    ):
        errors.append("RESEARCH_DATA_PRECHECK_REQUEST_BINDING_MISMATCH")
    try:
        require_verified_snapshot_integrity(dataset)
    except ValueError as exc:
        errors.append(str(exc))
    metadata_errors = _snapshot_metadata_errors(dataset)
    if metadata_errors:
        errors.append("RESEARCH_DATA_PRECHECK_SNAPSHOT_METADATA_INCOMPLETE")
        errors.extend(metadata_errors)
    errors.extend(_hypothesis_dataset_binding_errors(hypothesis, dataset))
    return errors


def _details(
    *,
    hypothesis: ResearchHypothesisVersion,
    dataset: ResearchDatasetSnapshot,
    epoch: ResearchExperimentEpoch,
    profile: CapabilityProfile | None,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "hypothesis_content_hash": hypothesis.content_hash,
        "dataset_content_hash": dataset.content_hash,
        "dataset_snapshot_identity_hash": dataset.snapshot_identity_hash,
        "dataset_integrity_status": dataset.integrity_status,
        "dataset_policy_version": dataset.dataset_policy_version,
        "epoch_family_hash": epoch.family_hash,
        "profile_evidence_hash": profile.evidence_hash if profile is not None else None,
        "errors": list(errors),
    }


def _has_non_empty_sequence(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def _has_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _snapshot_metadata_errors(dataset: ResearchDatasetSnapshot) -> list[str]:
    """Return explicit reasons when a stored/imported snapshot is not research-ready."""

    errors: list[str] = []
    instruments = dataset.instrument_manifest or {}
    source = dataset.source_manifest or {}
    split = dataset.split_manifest or {}
    execution = dataset.execution_policy or {}

    if not _has_non_empty_sequence(instruments.get("symbols")):
        errors.append("RESEARCH_DATA_PRECHECK_INSTRUMENTS_MISSING")
    for key in ("asset_class", "identity_scheme"):
        if not _has_known_text(instruments.get(key)):
            errors.append(f"RESEARCH_DATA_PRECHECK_INSTRUMENT_{key.upper()}_MISSING")

    for key in (
        "provider",
        "frequency",
        "timezone",
        "adjustment_rule",
        "event_time_basis",
        "vintage",
    ):
        if not _has_known_text(source.get(key)):
            errors.append(f"RESEARCH_DATA_PRECHECK_SOURCE_{key.upper()}_MISSING")
    for key in ("ingested_at", "as_of_at"):
        if _parse_timestamp(source.get(key)) is None:
            errors.append(f"RESEARCH_DATA_PRECHECK_SOURCE_{key.upper()}_INVALID")

    split_start = _parse_timestamp(split.get("start"))
    split_end = _parse_timestamp(split.get("end"))
    if split_start is None or split_end is None or split_start >= split_end:
        errors.append("RESEARCH_DATA_PRECHECK_SPLIT_RANGE_INVALID")
    if not isinstance(split.get("walk_forward"), bool):
        errors.append("RESEARCH_DATA_PRECHECK_SPLIT_WALK_FORWARD_MISSING")
    for key in ("purge_bars", "embargo_bars"):
        value = split.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"RESEARCH_DATA_PRECHECK_SPLIT_{key.upper()}_INVALID")
    folds = split.get("folds")
    if not isinstance(folds, list) or not folds:
        errors.append("RESEARCH_DATA_PRECHECK_SPLIT_FOLDS_MISSING")
    elif not _folds_are_valid(folds, split_start, split_end):
        errors.append("RESEARCH_DATA_PRECHECK_SPLIT_FOLDS_INVALID")

    if not _has_known_text(execution.get("fill")):
        errors.append("RESEARCH_DATA_PRECHECK_EXECUTION_MODEL_MISSING")
    for key in ("commission_bps", "slippage_bps"):
        if not _is_nonnegative_number(execution.get(key)):
            errors.append(f"RESEARCH_DATA_PRECHECK_EXECUTION_{key.upper()}_INVALID")
    volume_limit = execution.get("volume_limit")
    if (
        not _is_nonnegative_number(volume_limit)
        or float(volume_limit) <= 0
        or float(volume_limit) > 1
    ):
        errors.append("RESEARCH_DATA_PRECHECK_EXECUTION_VOLUME_LIMIT_INVALID")
    for key in ("suspension", "price_limit", "market_impact"):
        # UNKNOWN/BLOCKED is an honest declared execution limitation.  It is
        # valid metadata and remains visible to downstream hard gates; only a
        # missing field would silently imply a zero-cost/fully-supported path.
        if not _has_non_empty_text(execution.get(key)):
            errors.append(f"RESEARCH_DATA_PRECHECK_EXECUTION_{key.upper()}_MISSING")
    if not isinstance(dataset.license_tags, list) or not any(
        _has_known_text(tag) for tag in dataset.license_tags
    ):
        errors.append("RESEARCH_DATA_PRECHECK_LICENSE_TAGS_MISSING")
    return errors


def _hypothesis_dataset_binding_errors(
    hypothesis: ResearchHypothesisVersion,
    dataset: ResearchDatasetSnapshot,
) -> list[str]:
    """Reject a formally complete snapshot if it does not match the preregistration."""

    payload = hypothesis.canonical_payload or {}
    errors: list[str] = []
    scope = payload.get("asset_scope")
    hypothesis_symbols = scope.get("symbols") if isinstance(scope, dict) else None
    dataset_symbols = (dataset.instrument_manifest or {}).get("symbols")
    if (
        not _has_non_empty_sequence(hypothesis_symbols)
        or not _has_non_empty_sequence(dataset_symbols)
        or set(hypothesis_symbols) != set(dataset_symbols)
    ):
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_INSTRUMENT_MISMATCH")
    if (dataset.source_manifest or {}).get("frequency") != payload.get("frequency"):
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_FREQUENCY_MISMATCH")

    time_window = payload.get("time_window")
    start = _parse_timestamp(time_window.get("start")) if isinstance(time_window, dict) else None
    end = _parse_timestamp(time_window.get("end")) if isinstance(time_window, dict) else None
    split = dataset.split_manifest or {}
    split_start = _parse_timestamp(split.get("start"))
    split_end = _parse_timestamp(split.get("end"))
    if (
        start is None
        or end is None
        or split_start is None
        or split_end is None
        or split_start < start
        or split_end > end
    ):
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_TIME_WINDOW_MISMATCH")
    information_cutoff = _parse_timestamp(payload.get("information_cutoff"))
    source_as_of = _parse_timestamp((dataset.source_manifest or {}).get("as_of_at"))
    if (
        information_cutoff is None
        or source_as_of is None
        or _stored_utc(dataset.point_in_time_cutoff) > information_cutoff
        or source_as_of > information_cutoff
    ):
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_INFORMATION_CUTOFF_MISMATCH")

    cost_model = payload.get("cost_model")
    execution = dataset.execution_policy or {}
    if not isinstance(cost_model, dict) or any(
        not _same_number(cost_model.get(key), execution.get(key))
        for key in ("commission_bps", "slippage_bps")
    ):
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_COST_MODEL_MISMATCH")
    capacity = payload.get("capacity_assumptions")
    if not isinstance(capacity, dict) or not _same_number(
        capacity.get("max_participation_rate"), execution.get("volume_limit")
    ):
        errors.append("RESEARCH_DATA_PRECHECK_HYPOTHESIS_CAPACITY_MISMATCH")
    return errors


def _folds_are_valid(
    folds: list[Any],
    split_start: datetime | None,
    split_end: datetime | None,
) -> bool:
    if split_start is None or split_end is None:
        return False
    for fold in folds:
        if not isinstance(fold, dict):
            return False
        train_start = _parse_timestamp(fold.get("train_start"))
        train_end = _parse_timestamp(fold.get("train_end"))
        validation_start = _parse_timestamp(fold.get("validation_start"))
        validation_end = _parse_timestamp(fold.get("validation_end"))
        if (
            train_start is None
            or train_end is None
            or validation_start is None
            or validation_end is None
            or train_start >= train_end
            or train_end >= validation_start
            or validation_start >= validation_end
            or train_start < split_start
            or validation_end > split_end
        ):
            return False
    return True


def _has_known_text(value: Any) -> bool:
    return _has_non_empty_text(value) and value.strip().upper() not in {"UNKNOWN", "BLOCKED", "N/A"}


def _is_nonnegative_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) >= 0


def _same_number(left: Any, right: Any) -> bool:
    return (
        _is_nonnegative_number(left)
        and _is_nonnegative_number(right)
        and float(left) == float(right)
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{candidate}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("RESEARCH_DATA_PRECHECK_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-less round trip without using local time."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
