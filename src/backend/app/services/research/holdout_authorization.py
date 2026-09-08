"""One-time opaque authorization for independent sealed-holdout evaluation."""

from __future__ import annotations

import asyncio
import secrets
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchDatasetSnapshot,
    ResearchExperimentEpoch,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchRun,
)
from app.services.research.candidate_registry import (
    require_strict_freeze_receipt,
    verify_candidate_integrity,
)
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.discovery_search_budget import lock_experiment_epoch

_PUBLIC_AUTHORITY_LOCK_SHARD_COUNT = 64
_PUBLIC_AUTHORITY_LOCK_SHARDS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    tuple[asyncio.Lock, ...],
] = weakref.WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class IssuedHoldoutAuthorization:
    """Internal issue result; the raw token must never enter ordinary logs."""

    authorization: ResearchHoldoutAuthorization
    token: str = field(repr=False)


class _HoldoutAuthorizationExpired(ValueError):
    """Signal an expiry mutation that only the public consume path persists."""


class HoldoutAuthorizationRegistry:
    """Issue and consume candidate-bound sealed data permissions exactly once."""

    def __init__(self, *, dataset_registry: DatasetRegistry | None = None) -> None:
        """Use a resolver-backed registry at each sealed-data state transition."""

        self._datasets = dataset_registry or DatasetRegistry()

    async def issue(
        self,
        *,
        user_id: str,
        candidate_id: str,
        dataset_snapshot_id: str,
        policy_version: str,
        evaluator_identity: str,
        profile_id: str,
        profile_version: str,
        expires_in_seconds: int = 900,
    ) -> IssuedHoldoutAuthorization:
        """Serialize the public compatibility path with command creation locally."""

        async with _public_holdout_authority_lock(candidate_id):
            return await self._issue_once(
                user_id=user_id,
                candidate_id=candidate_id,
                dataset_snapshot_id=dataset_snapshot_id,
                policy_version=policy_version,
                evaluator_identity=evaluator_identity,
                profile_id=profile_id,
                profile_version=profile_version,
                expires_in_seconds=expires_in_seconds,
            )

    async def _issue_once(
        self,
        *,
        user_id: str,
        candidate_id: str,
        dataset_snapshot_id: str,
        policy_version: str,
        evaluator_identity: str,
        profile_id: str,
        profile_version: str,
        expires_in_seconds: int = 900,
    ) -> IssuedHoldoutAuthorization:
        """Issue one opaque token after freeze and topology checks pass."""

        profile = await CapabilityRegistry().get(profile_id, profile_version)
        decision = await CapabilityRegistry().evaluate(
            profile_id,
            profile_version,
            required=("sealed_evaluation",),
        )
        if not decision.allowed or profile is None:
            raise ValueError(f"{decision.code}:{','.join(decision.missing_capabilities)}")
        if profile.service_identities.get("evaluator") != evaluator_identity:
            raise ValueError("HOLDOUT_AUTHORIZATION_EVALUATOR_DENIED")
        if expires_in_seconds < 1:
            raise ValueError("HOLDOUT_AUTHORIZATION_EXPIRY_INVALID")

        token = secrets.token_urlsafe(32)
        token_hash = _token_hash(token)
        issued_at = _now()
        async with database.async_session_maker() as session:
            candidate_epoch_id = await session.scalar(
                select(ResearchCandidate.experiment_epoch_id).where(
                    ResearchCandidate.id == candidate_id,
                    ResearchCandidate.user_id == user_id,
                )
            )
            if candidate_epoch_id is None:
                raise ValueError("CANDIDATE_NOT_FOUND")
            epoch = await lock_experiment_epoch(
                session,
                user_id=user_id,
                epoch_id=candidate_epoch_id,
                require_open=False,
                denied_code="HOLDOUT_AUTHORIZATION_CANDIDATE_NOT_SELECTED",
            )
            candidate = await _owner_candidate(session, user_id, candidate_id)
            if candidate.freeze_status != "FROZEN":
                raise ValueError("HOLDOUT_AUTHORIZATION_REQUIRES_FROZEN_CANDIDATE")
            await verify_candidate_integrity(session, candidate)
            run = await session.get(ResearchRun, candidate.run_id)
            if (
                run is None
                or run.capability_profile_id != profile.profile_id
                or run.capability_profile_version != profile.version
                or run.capability_evidence_hash != profile.evidence_hash
            ):
                raise ValueError("HOLDOUT_AUTHORIZATION_RUN_PROFILE_MISMATCH")
            await require_strict_freeze_receipt(session, candidate)
            dataset = await _owner_sealed_snapshot(session, user_id, dataset_snapshot_id)
            candidate_dataset = await _candidate_snapshot(session, candidate)
            await self._datasets.revalidate_snapshot_in_session(
                session,
                snapshot=candidate_dataset,
            )
            await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
            require_verified_snapshot_integrity(candidate_dataset)
            require_verified_snapshot_integrity(dataset)
            # Lock command last, after the epoch/candidate authority graph, to
            # match request/claim ordering.  Holding the epoch lock prevents a
            # new request from slipping in before this final write fence.
            command_id = await session.scalar(
                select(ResearchHoldoutEvaluationCommand.id)
                .where(ResearchHoldoutEvaluationCommand.experiment_epoch_id == epoch.id)
                .with_for_update()
            )
            if command_id is not None:
                raise ValueError("HOLDOUT_AUTHORIZATION_CLAIM_FENCE_REQUIRED")
            if epoch.status != "SELECTED" or epoch.selected_candidate_id != candidate.id:
                raise ValueError("HOLDOUT_AUTHORIZATION_CANDIDATE_NOT_SELECTED")
            existing_authorization_id = await session.scalar(
                select(ResearchHoldoutAuthorization.id)
                .where(ResearchHoldoutAuthorization.experiment_epoch_id == epoch.id)
                .limit(1)
            )
            if existing_authorization_id is not None:
                raise ValueError("HOLDOUT_AUTHORIZATION_ALREADY_ISSUED")
            authorization = ResearchHoldoutAuthorization(
                experiment_epoch_id=epoch.id,
                candidate_id=candidate.id,
                candidate_hash=candidate.candidate_hash,
                dataset_snapshot_id=dataset.id,
                policy_version=policy_version,
                token_hash=token_hash,
                status="ISSUED",
                evaluator_identity=evaluator_identity,
                capability_profile_id=profile.profile_id,
                capability_profile_version=profile.version,
                capability_evidence_hash=profile.evidence_hash,
                issued_by=user_id,
                issued_at=issued_at,
                expires_at=issued_at + timedelta(seconds=expires_in_seconds),
            )
            session.add(authorization)
            await session.commit()
            await session.refresh(authorization)
            return IssuedHoldoutAuthorization(authorization=authorization, token=token)

    async def consume(
        self,
        token: str,
        *,
        candidate_id: str,
        candidate_hash: str,
        dataset_snapshot_id: str,
        policy_version: str,
        evaluator_identity: str,
    ) -> ResearchHoldoutAuthorization:
        """Consume a matching token once from the independent evaluator path."""

        async with database.async_session_maker() as session:
            try:
                authorization = await self.consume_in_session(
                    session,
                    token,
                    candidate_id=candidate_id,
                    candidate_hash=candidate_hash,
                    dataset_snapshot_id=dataset_snapshot_id,
                    policy_version=policy_version,
                    evaluator_identity=evaluator_identity,
                )
            except _HoldoutAuthorizationExpired:
                # Expiry is itself durable state in the public compatibility path.
                await session.commit()
                raise ValueError("HOLDOUT_AUTHORIZATION_NOT_ACTIVE") from None
            await session.commit()
            await session.refresh(authorization)
            return authorization

    async def issue_consumed_in_session(
        self,
        session: AsyncSession,
        *,
        epoch: ResearchExperimentEpoch,
        candidate: ResearchCandidate,
        dataset_snapshot_id: str,
        policy_version: str,
        evaluator_identity: str,
        capability_profile_id: str,
        capability_profile_version: str,
        capability_evidence_hash: str,
        issued_by: str,
        occurred_at: datetime,
        expires_in_seconds: int = 900,
    ) -> ResearchHoldoutAuthorization:
        """JIT issue and consume authority inside a caller-owned claim transaction.

        The raw authorization token never crosses this method boundary.  Only
        its one-way digest is persisted, and the caller remains responsible for
        the transaction's eventual commit or rollback.
        """

        if expires_in_seconds < 1:
            raise ValueError("HOLDOUT_AUTHORIZATION_EXPIRY_INVALID")
        if (
            epoch.status != "SELECTED"
            or epoch.selected_candidate_id != candidate.id
            or candidate.experiment_epoch_id != epoch.id
            or candidate.freeze_status != "FROZEN"
        ):
            raise ValueError("HOLDOUT_AUTHORIZATION_CANDIDATE_NOT_SELECTED")
        existing_authorization_id = await session.scalar(
            select(ResearchHoldoutAuthorization.id)
            .where(ResearchHoldoutAuthorization.experiment_epoch_id == epoch.id)
            .limit(1)
        )
        if existing_authorization_id is not None:
            raise ValueError("HOLDOUT_AUTHORIZATION_ALREADY_ISSUED")

        raw_token = secrets.token_urlsafe(32)
        authorization = ResearchHoldoutAuthorization(
            experiment_epoch_id=epoch.id,
            candidate_id=candidate.id,
            candidate_hash=candidate.candidate_hash,
            dataset_snapshot_id=dataset_snapshot_id,
            policy_version=policy_version,
            token_hash=_token_hash(raw_token),
            status="CONSUMED",
            evaluator_identity=evaluator_identity,
            capability_profile_id=capability_profile_id,
            capability_profile_version=capability_profile_version,
            capability_evidence_hash=capability_evidence_hash,
            issued_by=issued_by,
            issued_at=occurred_at,
            consumed_at=occurred_at,
            expires_at=occurred_at + timedelta(seconds=expires_in_seconds),
        )
        session.add(authorization)
        await session.flush()
        epoch.status = "DISCLOSED"
        epoch.disclosed_at = occurred_at
        return authorization

    async def consume_in_session(
        self,
        session: AsyncSession,
        token: str,
        *,
        candidate_id: str,
        candidate_hash: str,
        dataset_snapshot_id: str,
        policy_version: str,
        evaluator_identity: str,
    ) -> ResearchHoldoutAuthorization:
        """Validate and stage consumption without committing the caller's transaction.

        The caller owns commit/rollback. This lets the evaluator persist the
        consumption, epoch disclosure, and initial evaluation receipt atomically.
        """

        token_hash = _token_hash(token)
        authorization_identity = (
            await session.execute(
                select(
                    ResearchHoldoutAuthorization.id,
                    ResearchHoldoutAuthorization.experiment_epoch_id,
                    ResearchHoldoutAuthorization.candidate_id,
                ).where(ResearchHoldoutAuthorization.token_hash == token_hash)
            )
        ).one_or_none()
        if authorization_identity is None:
            raise ValueError("HOLDOUT_AUTHORIZATION_NOT_FOUND")
        authorization_id, authorization_epoch_id, authorization_candidate_id = (
            authorization_identity
        )
        candidate_identity = (
            await session.execute(
                select(
                    ResearchCandidate.user_id,
                    ResearchCandidate.experiment_epoch_id,
                ).where(ResearchCandidate.id == candidate_id)
            )
        ).one_or_none()
        if candidate_identity is None:
            raise ValueError("HOLDOUT_AUTHORIZATION_CANDIDATE_NOT_FROZEN")
        candidate_user_id, candidate_epoch_id = candidate_identity
        if (
            authorization_candidate_id != candidate_id
            or authorization_epoch_id != candidate_epoch_id
        ):
            raise ValueError("HOLDOUT_AUTHORIZATION_BINDING_MISMATCH")
        epoch = await lock_experiment_epoch(
            session,
            user_id=candidate_user_id,
            epoch_id=candidate_epoch_id,
            require_open=False,
            denied_code="HOLDOUT_AUTHORIZATION_EPOCH_INCONSISTENT",
        )
        command_id = await session.scalar(
            select(ResearchHoldoutEvaluationCommand.id)
            .where(ResearchHoldoutEvaluationCommand.experiment_epoch_id == epoch.id)
            .with_for_update()
        )
        if command_id is not None:
            raise ValueError("HOLDOUT_AUTHORIZATION_CLAIM_FENCE_REQUIRED")
        candidate_result = await session.execute(
            select(ResearchCandidate).where(ResearchCandidate.id == candidate_id).with_for_update()
        )
        candidate = candidate_result.scalar_one_or_none()
        authorization = await session.scalar(
            select(ResearchHoldoutAuthorization)
            .where(
                ResearchHoldoutAuthorization.id == authorization_id,
                ResearchHoldoutAuthorization.token_hash == token_hash,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if authorization is None:
            raise ValueError("HOLDOUT_AUTHORIZATION_NOT_FOUND")
        if authorization.status != "ISSUED":
            raise ValueError("HOLDOUT_AUTHORIZATION_NOT_ACTIVE")
        if authorization.expires_at is not None and _as_utc(authorization.expires_at) <= _now():
            authorization.status = "EXPIRED"
            raise _HoldoutAuthorizationExpired("HOLDOUT_AUTHORIZATION_NOT_ACTIVE")
        if authorization.evaluator_identity != evaluator_identity:
            raise ValueError("HOLDOUT_AUTHORIZATION_EVALUATOR_DENIED")
        if (
            authorization.candidate_id != candidate_id
            or authorization.candidate_hash != candidate_hash
            or authorization.dataset_snapshot_id != dataset_snapshot_id
            or authorization.policy_version != policy_version
        ):
            raise ValueError("HOLDOUT_AUTHORIZATION_BINDING_MISMATCH")
        if candidate is None or candidate.freeze_status != "FROZEN":
            raise ValueError("HOLDOUT_AUTHORIZATION_CANDIDATE_NOT_FROZEN")
        await verify_candidate_integrity(session, candidate)
        if candidate.candidate_hash != authorization.candidate_hash:
            raise ValueError("HOLDOUT_AUTHORIZATION_CANDIDATE_HASH_STALE")
        await require_strict_freeze_receipt(session, candidate)
        profile = await CapabilityRegistry().get(
            authorization.capability_profile_id,
            authorization.capability_profile_version,
        )
        decision = await CapabilityRegistry().evaluate(
            authorization.capability_profile_id,
            authorization.capability_profile_version,
            required=("sealed_evaluation",),
        )
        if (
            profile is None
            or profile.evidence_hash != authorization.capability_evidence_hash
            or not decision.allowed
        ):
            raise ValueError("HOLDOUT_AUTHORIZATION_PROFILE_NOT_CURRENT")

        if (
            epoch.status != "SELECTED"
            or epoch.selected_candidate_id != authorization.candidate_id
            or authorization.experiment_epoch_id != epoch.id
            or epoch.disclosed_at is not None
            or epoch.closed_at is not None
        ):
            raise ValueError("HOLDOUT_AUTHORIZATION_EPOCH_INCONSISTENT")
        candidate_dataset = await _candidate_snapshot(session, candidate)
        dataset = await _owner_sealed_snapshot(
            session,
            candidate.user_id,
            authorization.dataset_snapshot_id,
        )
        await self._datasets.revalidate_snapshot_in_session(
            session,
            snapshot=candidate_dataset,
        )
        await self._datasets.revalidate_snapshot_in_session(session, snapshot=dataset)
        require_verified_snapshot_integrity(candidate_dataset)
        require_verified_snapshot_integrity(dataset)
        consumed_at = _now()
        authorization.status = "CONSUMED"
        authorization.consumed_at = consumed_at
        epoch.status = "DISCLOSED"
        epoch.disclosed_at = consumed_at
        return authorization


async def _owner_candidate(session, user_id: str, candidate_id: str) -> ResearchCandidate:
    result = await session.execute(
        select(ResearchCandidate)
        .where(ResearchCandidate.id == candidate_id, ResearchCandidate.user_id == user_id)
        .with_for_update()
    )
    candidate = result.scalar_one_or_none()
    if candidate is None:
        raise ValueError("CANDIDATE_NOT_FOUND")
    return candidate


async def _owner_epoch(session, user_id: str, epoch_id: str) -> ResearchExperimentEpoch:
    result = await session.execute(
        select(ResearchExperimentEpoch)
        .where(ResearchExperimentEpoch.id == epoch_id, ResearchExperimentEpoch.user_id == user_id)
        .with_for_update()
    )
    epoch = result.scalar_one_or_none()
    if epoch is None:
        raise ValueError("EXPERIMENT_EPOCH_NOT_FOUND")
    return epoch


async def _owner_sealed_snapshot(
    session,
    user_id: str,
    snapshot_id: str,
) -> ResearchDatasetSnapshot:
    result = await session.execute(
        select(ResearchDatasetSnapshot).where(
            ResearchDatasetSnapshot.id == snapshot_id,
            ResearchDatasetSnapshot.user_id == user_id,
            ResearchDatasetSnapshot.partition_kind == "SEALED_HOLDOUT",
        )
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        raise ValueError("SEALED_DATASET_NOT_FOUND")
    require_verified_snapshot_integrity(snapshot)
    return snapshot


async def _candidate_snapshot(session, candidate: ResearchCandidate) -> ResearchDatasetSnapshot:
    """Load the selected candidate's server-attested discovery snapshot."""

    snapshot = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
    if snapshot is None or snapshot.user_id != candidate.user_id:
        raise ValueError("CANDIDATE_BINDING_NOT_FOUND")
    return snapshot


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _public_holdout_authority_lock(candidate_id: str) -> asyncio.Lock:
    """Coordinate public request/issue writers inside one worker process.

    The database epoch row remains the cross-process authority.  This bounded
    lock only makes the same invariant deterministic on SQLite and avoids
    needless local write-contention failures before the database fence runs.
    """

    loop = asyncio.get_running_loop()
    shards = _PUBLIC_AUTHORITY_LOCK_SHARDS_BY_LOOP.get(loop)
    if shards is None:
        shards = tuple(asyncio.Lock() for _ in range(_PUBLIC_AUTHORITY_LOCK_SHARD_COUNT))
        _PUBLIC_AUTHORITY_LOCK_SHARDS_BY_LOOP[loop] = shards
    index = int(sha256(candidate_id.encode("utf-8")).hexdigest(), 16) % len(shards)
    return shards[index]
