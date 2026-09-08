"""Internal, fenced claim boundary for queued sealed-holdout evaluations."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchRun,
)
from app.services.research.candidate_registry import (
    require_strict_freeze_receipt,
    strict_freeze_receipt_fingerprint,
    verify_candidate_integrity,
)
from app.services.research.capabilities import CapabilityProfile, evaluate_capabilities
from app.services.research.database_clock import (
    DatabaseUtcAfter,
    DatabaseUtcNow,
    database_utc_now,
)
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.discovery_search_budget import lock_experiment_epoch
from app.services.research.holdout_authorization import HoldoutAuthorizationRegistry
from app.services.research.holdout_request import holdout_request_binding_hash
from app.services.research.promotion import resolve_server_policy

_CLAIM_LOCK_SHARD_COUNT = 64
_CLAIM_LOCK_SHARDS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    tuple[asyncio.Lock, ...],
] = weakref.WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class HoldoutEvaluatorRuntimeIdentity:
    """Deployment-bootstrap identity passed directly by the internal worker."""

    worker_identity: str
    evaluator_identity: str
    evaluator_image_digest: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                self.worker_identity,
                self.evaluator_identity,
                self.evaluator_image_digest,
            )
        ):
            raise ValueError("HOLDOUT_CLAIM_RUNTIME_IDENTITY_INVALID")


@dataclass(frozen=True, slots=True)
class ClaimedHoldoutEvaluation:
    """Internal claim receipt; the bearer lease is deliberately hidden from repr."""

    command_id: str
    evaluation_id: str
    candidate_id: str
    lease_owner: str
    lease_generation: int
    lease_expires_at: datetime
    lease_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class HoldoutLeaseHeartbeat:
    """Safe heartbeat receipt without bearer material."""

    command_id: str
    lease_generation: int
    lease_expires_at: datetime
    lease_heartbeat_at: datetime


@dataclass(frozen=True, slots=True)
class ReconciledHoldoutEvaluation:
    """Safe receipt for an expired lease moved out of active execution."""

    command_id: str
    status: str
    stage: str
    lease_generation: int


@dataclass(frozen=True, slots=True)
class _CommandSeed:
    user_id: str
    run_id: str
    experiment_epoch_id: str
    candidate_id: str
    freeze_receipt_id: str
    dataset_snapshot_id: str


@dataclass(frozen=True, slots=True)
class _SnapshotFailureProbe:
    user_id: str
    snapshot_id: str
    snapshot_identity_hash: str
    checked_at: datetime
    reason_code: str


@dataclass(frozen=True, slots=True)
class _CommitProbe:
    command_id: str
    authorization_id: str
    evaluation_id: str
    experiment_epoch_id: str
    candidate_id: str
    dataset_snapshot_id: str
    request_hash: str
    evaluator_identity: str
    evaluator_version: str
    lease_owner: str
    lease_token_hash: str
    lease_generation: int
    lease_expires_at: datetime
    command_state: tuple[object, ...]
    authorization_state: tuple[object, ...]
    evaluation_state: tuple[object, ...]
    epoch_state: tuple[object, ...]
    audit_state: tuple[object, ...]
    locked_authority_state: tuple[object, ...]
    lease_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _LockedClaimGraph:
    epoch: ResearchExperimentEpoch
    candidate: ResearchCandidate
    receipt: ResearchCandidateFreezeReceipt
    run: ResearchRun
    profile: ResearchCapabilityProfile
    discovery: ResearchDatasetSnapshot
    sealed: ResearchDatasetSnapshot
    command: ResearchHoldoutEvaluationCommand


class _SnapshotRevalidationFailure(ValueError):
    def __init__(self, probe: _SnapshotFailureProbe) -> None:
        super().__init__(probe.reason_code)
        self.probe = probe


class _AcceptedAccessAuditInsertError(Exception):
    pass


class _CommitOutcomeUncertain(Exception):
    def __init__(self, probe: _CommitProbe) -> None:
        super().__init__("HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class HoldoutClaimService:
    """Claim one server-authored command without exposing authority over HTTP."""

    def __init__(
        self,
        *,
        dataset_registry: DatasetRegistry | None = None,
        lease_seconds: int = 300,
    ) -> None:
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 7200:
            raise ValueError("HOLDOUT_CLAIM_LEASE_DURATION_INVALID")
        self._datasets = dataset_registry or DatasetRegistry()
        self._authorizations = HoldoutAuthorizationRegistry(dataset_registry=self._datasets)
        self._lease_seconds = lease_seconds

    async def claim(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> ClaimedHoldoutEvaluation:
        """Atomically consume holdout authority and establish a fenced lease."""

        async with _claim_lock(command_id):
            try:
                return await self._claim_once(command_id=command_id, runtime=runtime)
            except _CommitOutcomeUncertain as exc:
                committed = await self._read_committed_claim(exc.probe)
                if committed is not None:
                    return committed
                raise ValueError("HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN") from None
            except _SnapshotRevalidationFailure as exc:
                await self._persist_failed_snapshot_or_fail(exc.probe)
                await self._record_non_authoritative_audit_or_fail(
                    command_id=command_id,
                    runtime=runtime,
                    action="CLAIM_REJECTED",
                    result="REJECTED",
                    reason_code=exc.probe.reason_code,
                )
                raise ValueError(exc.probe.reason_code) from None
            except _AcceptedAccessAuditInsertError:
                # The accepted authority graph was rolled back.  Failure to
                # append its mandatory audit is itself the stable outcome.
                try:
                    await self._record_non_authoritative_audit(
                        command_id=command_id,
                        runtime=runtime,
                        action="CLAIM_REJECTED",
                        result="REJECTED",
                        reason_code="HOLDOUT_CLAIM_AUDIT_UNAVAILABLE",
                    )
                except Exception:
                    pass
                raise ValueError("HOLDOUT_CLAIM_AUDIT_UNAVAILABLE") from None
            except ValueError as exc:
                await self._record_non_authoritative_audit_or_fail(
                    command_id=command_id,
                    runtime=runtime,
                    action="CLAIM_REJECTED",
                    result="REJECTED",
                    reason_code=_safe_reason_code(exc),
                )
                raise
            except SQLAlchemyError:
                await self._record_non_authoritative_audit_or_fail(
                    command_id=command_id,
                    runtime=runtime,
                    action="CLAIM_REJECTED",
                    result="REJECTED",
                    reason_code="HOLDOUT_CLAIM_PERSISTENCE_FAILED",
                )
                raise ValueError("HOLDOUT_CLAIM_PERSISTENCE_FAILED") from None

    async def heartbeat(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token: str,
        lease_generation: int,
    ) -> HoldoutLeaseHeartbeat:
        """Renew exactly one live lease using a database-time CAS fence."""

        if type(lease_generation) is not int or lease_generation < 1:
            raise ValueError("HOLDOUT_CLAIM_LEASE_STALE")
        token_hash = _secret_hash(lease_token)
        async with database.async_session_maker() as session:
            updated = await session.execute(
                update(ResearchHoldoutEvaluationCommand)
                .where(
                    ResearchHoldoutEvaluationCommand.id == command_id,
                    ResearchHoldoutEvaluationCommand.status == "RUNNING",
                    ResearchHoldoutEvaluationCommand.stage == "HOLDOUT_PENDING",
                    ResearchHoldoutEvaluationCommand.lease_owner == runtime.worker_identity,
                    ResearchHoldoutEvaluationCommand.lease_token_hash == token_hash,
                    ResearchHoldoutEvaluationCommand.lease_generation == lease_generation,
                    ResearchHoldoutEvaluationCommand.evaluator_identity
                    == runtime.evaluator_identity,
                    ResearchHoldoutEvaluationCommand.evaluator_version
                    == runtime.evaluator_image_digest,
                    ResearchHoldoutEvaluationCommand.lease_expires_at > DatabaseUtcNow(),
                )
                .values(
                    lease_heartbeat_at=DatabaseUtcNow(),
                    lease_expires_at=DatabaseUtcAfter(self._lease_seconds),
                    updated_at=DatabaseUtcNow(),
                )
                .execution_options(synchronize_session=False)
            )
            if updated.rowcount != 1:
                now = await database_utc_now(session)
                command = await session.get(
                    ResearchHoldoutEvaluationCommand,
                    command_id,
                    populate_existing=True,
                )
                command_status = command.status if command is not None else None
                command_expiry = command.lease_expires_at if command is not None else None
                await session.rollback()
                if command_status != "RUNNING":
                    raise ValueError("HOLDOUT_CLAIM_NOT_RUNNING")
                if command_expiry is not None and _as_utc(command_expiry) <= now:
                    raise ValueError("HOLDOUT_CLAIM_LEASE_EXPIRED")
                raise ValueError("HOLDOUT_CLAIM_LEASE_STALE")
            command = await session.get(
                ResearchHoldoutEvaluationCommand,
                command_id,
                populate_existing=True,
            )
            if command is None:
                await session.rollback()
                raise ValueError("HOLDOUT_CLAIM_NOT_RUNNING")
            heartbeat_at = _required_time(command.lease_heartbeat_at)
            expires_at = _required_time(command.lease_expires_at)
            await session.commit()
        return HoldoutLeaseHeartbeat(
            command_id=command_id,
            lease_generation=lease_generation,
            lease_expires_at=expires_at,
            lease_heartbeat_at=heartbeat_at,
        )

    async def recover_expired(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> ReconciledHoldoutEvaluation:
        """Move an expired active lease to RECONCILING without new authority."""

        async with _claim_lock(command_id):
            async with database.async_session_maker() as session:
                try:
                    graph = await self._lock_claim_graph(session, command_id=command_id)
                    command = graph.command
                    now = await database_utc_now(session)
                    if command.status != "RUNNING" or command.stage != "HOLDOUT_PENDING":
                        raise ValueError("HOLDOUT_CLAIM_NOT_RUNNING")
                    if command.lease_generation < 1:
                        raise ValueError("HOLDOUT_CLAIM_LEASE_STALE")
                    if command.lease_expires_at is None or _as_utc(command.lease_expires_at) > now:
                        raise ValueError("HOLDOUT_CLAIM_LEASE_NOT_EXPIRED")
                    await _validate_static_locked_authority(session, graph, runtime=runtime)
                    await _require_recoverable_started_authority(session, graph)
                    generation = command.lease_generation
                    command.status = "RECONCILING"
                    command.error_code = "HOLDOUT_CLAIM_LEASE_EXPIRED"
                    command.lease_owner = None
                    command.lease_token_hash = None
                    command.lease_expires_at = None
                    command.lease_heartbeat_at = None
                    command.updated_at = now
                    session.add(
                        _accepted_access_audit(
                            graph,
                            runtime=runtime,
                            action="LEASE_EXPIRED_RECONCILING",
                            reason_code="HOLDOUT_CLAIM_LEASE_EXPIRED",
                            generation=generation,
                            occurred_at=now,
                        )
                    )
                    try:
                        await session.flush()
                    except SQLAlchemyError as exc:
                        raise ValueError("HOLDOUT_CLAIM_AUDIT_UNAVAILABLE") from exc
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
        return ReconciledHoldoutEvaluation(
            command_id=command_id,
            status="RECONCILING",
            stage="HOLDOUT_PENDING",
            lease_generation=generation,
        )

    async def _claim_once(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> ClaimedHoldoutEvaluation:
        raw_lease_token = secrets.token_urlsafe(32)
        lease_token_hash = _secret_hash(raw_lease_token)
        async with database.async_session_maker() as session:
            try:
                graph = await self._lock_claim_graph(session, command_id=command_id)
                self._validate_queued_graph(graph, runtime=runtime)
                await _validate_locked_authority(self, session, graph, runtime=runtime)
                existing_evaluation_id = await session.scalar(
                    select(ResearchEvaluation.id)
                    .where(ResearchEvaluation.experiment_epoch_id == graph.epoch.id)
                    .limit(1)
                )
                if existing_evaluation_id is not None:
                    raise ValueError("HOLDOUT_CLAIM_EVALUATION_ALREADY_EXISTS")
                now = await database_utc_now(session)
                lease_expires_at = _as_utc(
                    (
                        await session.execute(select(DatabaseUtcAfter(self._lease_seconds)))
                    ).scalar_one()
                )
                authorization = await self._authorizations.issue_consumed_in_session(
                    session,
                    epoch=graph.epoch,
                    candidate=graph.candidate,
                    dataset_snapshot_id=graph.sealed.id,
                    policy_version=graph.command.policy_version,
                    evaluator_identity=runtime.evaluator_identity,
                    capability_profile_id=graph.profile.profile_id,
                    capability_profile_version=graph.profile.version,
                    capability_evidence_hash=graph.profile.evidence_hash,
                    issued_by=runtime.worker_identity,
                    occurred_at=now,
                )
                evaluation = ResearchEvaluation(
                    experiment_epoch_id=graph.epoch.id,
                    candidate_id=graph.candidate.id,
                    dataset_snapshot_id=graph.sealed.id,
                    evaluation_type="SEALED_HOLDOUT",
                    evaluator_identity=runtime.evaluator_identity,
                    evaluator_version=runtime.evaluator_image_digest,
                    authorization_id=authorization.id,
                    returns_artifact_id=None,
                    metrics={},
                    gate_inputs={},
                    policy_version=graph.command.policy_version,
                    status="RUNNING",
                    started_at=now,
                )
                session.add(evaluation)
                await session.flush()

                command = graph.command
                command.authorization_id = authorization.id
                command.evaluation_id = evaluation.id
                command.status = "RUNNING"
                command.stage = "HOLDOUT_PENDING"
                command.lease_owner = runtime.worker_identity
                command.lease_token_hash = lease_token_hash
                command.lease_generation = command.lease_generation + 1
                command.lease_expires_at = lease_expires_at
                command.lease_heartbeat_at = now
                command.attempt_count = command.attempt_count + 1
                command.started_at = now
                command.updated_at = now
                await session.flush()
                audit = _accepted_access_audit(
                    graph,
                    runtime=runtime,
                    action="CLAIM_STARTED",
                    reason_code="HOLDOUT_CLAIM_STARTED",
                    generation=command.lease_generation,
                    occurred_at=now,
                )
                session.add(audit)
                try:
                    await session.flush()
                except SQLAlchemyError as exc:
                    raise _AcceptedAccessAuditInsertError from exc

                probe = _CommitProbe(
                    command_id=command.id,
                    authorization_id=authorization.id,
                    evaluation_id=evaluation.id,
                    experiment_epoch_id=graph.epoch.id,
                    candidate_id=graph.candidate.id,
                    dataset_snapshot_id=graph.sealed.id,
                    request_hash=command.request_hash,
                    evaluator_identity=runtime.evaluator_identity,
                    evaluator_version=runtime.evaluator_image_digest,
                    lease_owner=runtime.worker_identity,
                    lease_token_hash=lease_token_hash,
                    lease_generation=command.lease_generation,
                    lease_expires_at=lease_expires_at,
                    command_state=_command_commit_state(command),
                    authorization_state=_authorization_commit_state(authorization),
                    evaluation_state=_evaluation_commit_state(evaluation),
                    epoch_state=_epoch_commit_state(graph.epoch),
                    audit_state=_access_audit_commit_state(audit),
                    locked_authority_state=_locked_authority_commit_state(graph),
                    lease_token=raw_lease_token,
                )
                try:
                    await session.commit()
                except Exception as exc:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    raise _CommitOutcomeUncertain(probe) from exc
            except (_CommitOutcomeUncertain, _SnapshotRevalidationFailure):
                raise
            except Exception:
                await session.rollback()
                raise
        return _claimed_from_probe(probe)

    async def _lock_claim_graph(
        self,
        session: AsyncSession,
        *,
        command_id: str,
    ) -> _LockedClaimGraph:
        seed = await _command_seed(session, command_id)
        epoch = await lock_experiment_epoch(
            session,
            user_id=seed.user_id,
            epoch_id=seed.experiment_epoch_id,
            require_open=False,
            denied_code="HOLDOUT_CLAIM_EPOCH_NOT_FOUND",
        )
        candidate = await _lock_owned(
            session,
            ResearchCandidate,
            seed.candidate_id,
            seed.user_id,
            "HOLDOUT_CLAIM_CANDIDATE_NOT_FOUND",
        )
        receipt = await _lock_owned(
            session,
            ResearchCandidateFreezeReceipt,
            seed.freeze_receipt_id,
            seed.user_id,
            "HOLDOUT_CLAIM_FREEZE_RECEIPT_INVALID",
        )
        run = await _lock_owned(
            session,
            ResearchRun,
            seed.run_id,
            seed.user_id,
            "HOLDOUT_CLAIM_RUN_NOT_FOUND",
        )
        profile = await session.scalar(
            select(ResearchCapabilityProfile)
            .where(
                ResearchCapabilityProfile.profile_id == run.capability_profile_id,
                ResearchCapabilityProfile.version == run.capability_profile_version,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if profile is None:
            raise ValueError("HOLDOUT_CLAIM_PROFILE_INVALID")
        discovery = await _lock_owned_snapshot(
            session,
            candidate.dataset_snapshot_id,
            seed.user_id,
            "HOLDOUT_CLAIM_DISCOVERY_SNAPSHOT_INVALID",
        )
        sealed = await _lock_owned_snapshot(
            session,
            seed.dataset_snapshot_id,
            seed.user_id,
            "HOLDOUT_CLAIM_SEALED_SNAPSHOT_INVALID",
        )
        command = await session.scalar(
            select(ResearchHoldoutEvaluationCommand)
            .where(ResearchHoldoutEvaluationCommand.id == command_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if command is None or not _command_matches_seed(command, seed):
            raise ValueError("HOLDOUT_CLAIM_COMMAND_BINDING_MISMATCH")
        return _LockedClaimGraph(
            epoch=epoch,
            candidate=candidate,
            receipt=receipt,
            run=run,
            profile=profile,
            discovery=discovery,
            sealed=sealed,
            command=command,
        )

    def _validate_queued_graph(
        self,
        graph: _LockedClaimGraph,
        *,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> None:
        command = graph.command
        if command.status != "QUEUED" or command.stage != "REQUEST_HOLDOUT":
            raise ValueError("HOLDOUT_CLAIM_ALREADY_STARTED")
        if (
            any(
                value is not None
                for value in (
                    command.authorization_id,
                    command.evaluation_id,
                    command.lease_owner,
                    command.lease_token_hash,
                    command.lease_expires_at,
                    command.lease_heartbeat_at,
                    command.started_at,
                )
            )
            or command.lease_generation != 0
            or command.attempt_count != 0
        ):
            raise ValueError("HOLDOUT_CLAIM_COMMAND_BINDING_MISMATCH")
        if command.error_code is not None:
            raise ValueError("HOLDOUT_CLAIM_COMMAND_BINDING_MISMATCH")
        if command.expected_candidate_state != "FROZEN":
            raise ValueError("HOLDOUT_CLAIM_COMMAND_BINDING_MISMATCH")
        if (
            graph.epoch.status != "SELECTED"
            or graph.epoch.selected_candidate_id != graph.candidate.id
            or graph.epoch.disclosed_at is not None
            or graph.epoch.closed_at is not None
        ):
            raise ValueError("HOLDOUT_CLAIM_EPOCH_INCONSISTENT")
        if (
            graph.candidate.freeze_status != "FROZEN"
            or graph.candidate.candidate_hash != command.candidate_hash
            or graph.candidate.run_id != graph.run.id
            or graph.candidate.experiment_epoch_id != graph.epoch.id
        ):
            raise ValueError("HOLDOUT_CLAIM_CANDIDATE_BINDING_MISMATCH")
        if (
            graph.run.workspace_id != command.workspace_id
            or graph.run.experiment_epoch_id != graph.epoch.id
            or graph.run.promotion_policy_version != command.policy_version
            or graph.run.capability_profile_id != command.capability_profile_id
            or graph.run.capability_profile_version != command.capability_profile_version
            or graph.run.capability_evidence_hash != command.capability_evidence_hash
        ):
            raise ValueError("HOLDOUT_CLAIM_RUN_BINDING_MISMATCH")

    async def _read_committed_claim(
        self,
        probe: _CommitProbe,
    ) -> ClaimedHoldoutEvaluation | None:
        """Return an exact commit or fence an unconfirmed outcome before unlock."""

        runtime = HoldoutEvaluatorRuntimeIdentity(
            worker_identity=probe.lease_owner,
            evaluator_identity=probe.evaluator_identity,
            evaluator_image_digest=probe.evaluator_version,
        )
        try:
            async with database.async_session_maker() as session:
                try:
                    graph: _LockedClaimGraph | None = None
                    command: ResearchHoldoutEvaluationCommand | None = None
                    try:
                        graph = await self._lock_claim_graph(
                            session,
                            command_id=probe.command_id,
                        )
                        command = graph.command
                        await _validate_static_locked_authority(
                            session,
                            graph,
                            runtime=runtime,
                        )
                        authorization, evaluation, audit = await _load_started_authority(
                            session,
                            graph,
                        )
                        if _committed_claim_matches(
                            probe,
                            graph=graph,
                            authorization=authorization,
                            evaluation=evaluation,
                            audit=audit,
                        ):
                            await session.rollback()
                            return _claimed_from_probe(probe)
                    except ValueError:
                        # Deterministic mismatch is fenced below while retaining
                        # every lock already acquired in the canonical order.
                        pass
                    if command is None:
                        command = await session.scalar(
                            select(ResearchHoldoutEvaluationCommand)
                            .where(ResearchHoldoutEvaluationCommand.id == probe.command_id)
                            .with_for_update()
                            .execution_options(populate_existing=True)
                        )
                    now = await database_utc_now(session)
                    _fence_unknown_command(command, occurred_at=now)
                    session.add(
                        _non_authoritative_access_audit(
                            command_id=probe.command_id,
                            runtime=runtime,
                            action="CLAIM_UNKNOWN",
                            result="UNKNOWN",
                            reason_code="HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN",
                            occurred_at=now,
                        )
                    )
                    await session.flush()
                    await session.commit()
                    return None
                except Exception:
                    await session.rollback()
                    raise
        except Exception:
            raise ValueError("HOLDOUT_CLAIM_AUDIT_UNAVAILABLE") from None

    async def _persist_failed_snapshot_or_fail(self, probe: _SnapshotFailureProbe) -> None:
        try:
            await self._datasets.persist_failed_snapshot(
                user_id=probe.user_id,
                snapshot_id=probe.snapshot_id,
                expected_snapshot_identity_hash=probe.snapshot_identity_hash,
                checked_at=probe.checked_at,
            )
        except Exception:
            raise ValueError("HOLDOUT_CLAIM_SNAPSHOT_FAILURE_PERSISTENCE_FAILED") from None

    async def _record_non_authoritative_audit_or_fail(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        action: str,
        result: str,
        reason_code: str,
    ) -> None:
        try:
            await self._record_non_authoritative_audit(
                command_id=command_id,
                runtime=runtime,
                action=action,
                result=result,
                reason_code=reason_code,
            )
        except Exception:
            raise ValueError("HOLDOUT_CLAIM_AUDIT_UNAVAILABLE") from None

    async def _record_non_authoritative_audit(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        action: str,
        result: str,
        reason_code: str,
    ) -> None:
        async with database.async_session_maker() as session:
            now = await database_utc_now(session)
            session.add(
                _non_authoritative_access_audit(
                    command_id=command_id,
                    runtime=runtime,
                    action=action,
                    result=result,
                    reason_code=reason_code,
                    occurred_at=now,
                )
            )
            await session.commit()


async def _command_seed(session: AsyncSession, command_id: str) -> _CommandSeed:
    row = (
        await session.execute(
            select(
                ResearchHoldoutEvaluationCommand.user_id,
                ResearchHoldoutEvaluationCommand.run_id,
                ResearchHoldoutEvaluationCommand.experiment_epoch_id,
                ResearchHoldoutEvaluationCommand.candidate_id,
                ResearchHoldoutEvaluationCommand.freeze_receipt_id,
                ResearchHoldoutEvaluationCommand.dataset_snapshot_id,
            ).where(ResearchHoldoutEvaluationCommand.id == command_id)
        )
    ).one_or_none()
    if row is None:
        raise ValueError("HOLDOUT_CLAIM_COMMAND_NOT_FOUND")
    return _CommandSeed(*row)


async def _lock_owned(
    session: AsyncSession,
    model: type[ResearchCandidate] | type[ResearchCandidateFreezeReceipt] | type[ResearchRun],
    row_id: str,
    user_id: str,
    error_code: str,
):
    value = await session.scalar(
        select(model)
        .where(model.id == row_id, model.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if value is None:
        raise ValueError(error_code)
    return value


async def _lock_owned_snapshot(
    session: AsyncSession,
    snapshot_id: str,
    user_id: str,
    error_code: str,
) -> ResearchDatasetSnapshot:
    snapshot = await session.scalar(
        select(ResearchDatasetSnapshot)
        .where(
            ResearchDatasetSnapshot.id == snapshot_id,
            ResearchDatasetSnapshot.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if snapshot is None:
        raise ValueError(error_code)
    return snapshot


def _command_matches_seed(
    command: ResearchHoldoutEvaluationCommand,
    seed: _CommandSeed,
) -> bool:
    return (
        command.user_id == seed.user_id
        and command.run_id == seed.run_id
        and command.experiment_epoch_id == seed.experiment_epoch_id
        and command.candidate_id == seed.candidate_id
        and command.freeze_receipt_id == seed.freeze_receipt_id
        and command.dataset_snapshot_id == seed.dataset_snapshot_id
    )


def _profile_contract(model: ResearchCapabilityProfile) -> CapabilityProfile:
    sandbox = model.sandbox_capabilities or {}
    stage_images = sandbox.get("stage_image_digests")
    if not isinstance(stage_images, dict):
        stage_images = {}
    return CapabilityProfile(
        profile_id=model.profile_id,
        version=model.version,
        service_identities=dict(model.service_identities or {}),
        queue_isolation=bool((model.queue_capabilities or {}).get("isolated")),
        storage_isolation=bool((model.storage_boundaries or {}).get("isolated")),
        network_isolation=bool((model.network_capabilities or {}).get("isolated")),
        sandbox_runner=bool(sandbox.get("runner")),
        approval_mode=str((model.approval_capabilities or {}).get("mode") or model.actor_mode),
        evidence_hash=model.evidence_hash,
        verified_at=_as_utc(model.verified_at),
        expires_at=_as_utc(model.expires_at),
        stage_image_digests={
            key: value
            for key, value in stage_images.items()
            if isinstance(key, str) and isinstance(value, str)
        },
    )


async def _validate_locked_authority(
    service: HoldoutClaimService,
    session: AsyncSession,
    graph: _LockedClaimGraph,
    *,
    runtime: HoldoutEvaluatorRuntimeIdentity,
) -> None:
    await _validate_static_locked_authority(session, graph, runtime=runtime)
    profile = _profile_contract(graph.profile)
    now = await database_utc_now(session)
    capability = evaluate_capabilities(profile, required=("sealed_evaluation",), now=now)
    if not capability.allowed:
        raise ValueError("HOLDOUT_CLAIM_PROFILE_INVALID")
    await _revalidate_or_defer_failure(service, session, graph.discovery)
    await _revalidate_or_defer_failure(service, session, graph.sealed)
    require_verified_snapshot_integrity(graph.discovery)
    require_verified_snapshot_integrity(graph.sealed)


async def _validate_static_locked_authority(
    session: AsyncSession,
    graph: _LockedClaimGraph,
    *,
    runtime: HoldoutEvaluatorRuntimeIdentity,
) -> None:
    """Validate frozen authority without live capability or object availability.

    Recovery never reads sealed bytes or creates authority, so an expired
    capability profile or temporarily unavailable object resolver cannot keep
    an already-started lease active indefinitely.
    """

    command = graph.command
    try:
        await verify_candidate_integrity(session, graph.candidate)
        receipt = await require_strict_freeze_receipt(session, graph.candidate)
    except ValueError as exc:
        raise ValueError("HOLDOUT_CLAIM_FREEZE_RECEIPT_INVALID") from exc
    if (
        receipt.id != graph.receipt.id
        or strict_freeze_receipt_fingerprint(receipt) != command.freeze_receipt_fingerprint
    ):
        raise ValueError("HOLDOUT_CLAIM_FREEZE_RECEIPT_INVALID")
    profile = _profile_contract(graph.profile)
    if (
        graph.candidate.freeze_status != "FROZEN"
        or graph.candidate.candidate_hash != command.candidate_hash
        or graph.candidate.run_id != graph.run.id
        or graph.candidate.experiment_epoch_id != graph.epoch.id
        or graph.epoch.selected_candidate_id != graph.candidate.id
        or graph.run.workspace_id != command.workspace_id
        or graph.run.experiment_epoch_id != graph.epoch.id
        or graph.run.promotion_policy_version != command.policy_version
        or graph.run.capability_profile_id != command.capability_profile_id
        or graph.run.capability_profile_version != command.capability_profile_version
        or graph.run.capability_evidence_hash != command.capability_evidence_hash
        or graph.profile.profile_id != command.capability_profile_id
        or graph.profile.version != command.capability_profile_version
        or graph.profile.evidence_hash != command.capability_evidence_hash
        or profile.service_identities.get("evaluator") != command.evaluator_identity
        or profile.stage_image_digests.get("evaluator") != command.evaluator_version
        or runtime.evaluator_identity != command.evaluator_identity
        or runtime.evaluator_image_digest != command.evaluator_version
    ):
        raise ValueError("HOLDOUT_CLAIM_RUNTIME_IDENTITY_MISMATCH")
    try:
        policy = resolve_server_policy(command.policy_version)
    except ValueError as exc:
        raise ValueError("HOLDOUT_CLAIM_POLICY_INVALID") from exc
    if policy.version != command.policy_version:
        raise ValueError("HOLDOUT_CLAIM_POLICY_INVALID")
    if (
        graph.discovery.id != graph.candidate.dataset_snapshot_id
        or graph.discovery.partition_kind != "DISCOVERY"
        or graph.sealed.partition_kind != "SEALED_HOLDOUT"
        or graph.sealed.dataset_policy_version != graph.epoch.dataset_policy_version
        or graph.sealed.dataset_policy_version != command.dataset_policy_version
        or graph.sealed.content_hash != command.sealed_dataset_hash
        or graph.sealed.snapshot_identity_hash != command.sealed_dataset_identity_hash
    ):
        raise ValueError("HOLDOUT_CLAIM_SNAPSHOT_BINDING_MISMATCH")
    require_verified_snapshot_integrity(graph.discovery)
    require_verified_snapshot_integrity(graph.sealed)
    expected_request_hash = holdout_request_binding_hash(
        user_id=command.user_id,
        run_id=command.run_id,
        experiment_epoch_id=command.experiment_epoch_id,
        candidate_id=command.candidate_id,
        candidate_hash=command.candidate_hash,
        freeze_receipt_id=command.freeze_receipt_id,
        freeze_receipt_fingerprint=command.freeze_receipt_fingerprint,
        dataset_snapshot_id=command.dataset_snapshot_id,
        dataset_policy_version=command.dataset_policy_version,
        sealed_dataset_hash=command.sealed_dataset_hash,
        sealed_dataset_identity_hash=command.sealed_dataset_identity_hash,
        policy_version=command.policy_version,
        evaluator_identity=command.evaluator_identity,
        evaluator_version=command.evaluator_version,
        capability_profile_id=command.capability_profile_id,
        capability_profile_version=command.capability_profile_version,
        capability_evidence_hash=command.capability_evidence_hash,
    )
    if expected_request_hash != command.request_hash:
        raise ValueError("HOLDOUT_CLAIM_REQUEST_HASH_MISMATCH")


async def _revalidate_or_defer_failure(
    service: HoldoutClaimService,
    session: AsyncSession,
    snapshot: ResearchDatasetSnapshot,
) -> None:
    try:
        await service._datasets.revalidate_snapshot_in_session(session, snapshot=snapshot)
    except ValueError as exc:
        reason_code = str(exc)
        if reason_code not in {
            "DATASET_OBJECT_REVALIDATION_UNAVAILABLE",
            "DATASET_OBJECT_ATTESTATION_MISMATCH",
        }:
            raise
        if snapshot.snapshot_identity_hash is None or snapshot.integrity_checked_at is None:
            raise ValueError("HOLDOUT_CLAIM_SNAPSHOT_BINDING_MISMATCH") from exc
        raise _SnapshotRevalidationFailure(
            _SnapshotFailureProbe(
                user_id=snapshot.user_id,
                snapshot_id=snapshot.id,
                snapshot_identity_hash=snapshot.snapshot_identity_hash,
                checked_at=_as_utc(snapshot.integrity_checked_at),
                reason_code=reason_code,
            )
        ) from exc


def _accepted_access_audit(
    graph: _LockedClaimGraph,
    *,
    runtime: HoldoutEvaluatorRuntimeIdentity,
    action: str,
    reason_code: str,
    generation: int,
    occurred_at: datetime,
) -> ResearchHoldoutAccessAudit:
    command = graph.command
    if command.authorization_id is None or command.evaluation_id is None:
        raise ValueError("HOLDOUT_CLAIM_COMMAND_BINDING_MISMATCH")
    return ResearchHoldoutAccessAudit(
        actor_identity=runtime.worker_identity,
        evaluator_version=runtime.evaluator_image_digest,
        requested_command_id=command.id,
        action=action,
        result="ACCEPTED",
        reason_code=reason_code,
        command_id=command.id,
        authorization_id=command.authorization_id,
        evaluation_id=command.evaluation_id,
        experiment_epoch_id=command.experiment_epoch_id,
        candidate_id=command.candidate_id,
        dataset_snapshot_id=command.dataset_snapshot_id,
        lease_generation=generation,
        trace_id=command.trace_id,
        created_at=occurred_at,
    )


def _non_authoritative_access_audit(
    *,
    command_id: str,
    runtime: HoldoutEvaluatorRuntimeIdentity,
    action: str,
    result: str,
    reason_code: str,
    occurred_at: datetime,
) -> ResearchHoldoutAccessAudit:
    return ResearchHoldoutAccessAudit(
        actor_identity=runtime.worker_identity,
        evaluator_version=runtime.evaluator_image_digest,
        requested_command_id=command_id,
        action=action,
        result=result,
        reason_code=reason_code[:128],
        command_id=None,
        authorization_id=None,
        evaluation_id=None,
        experiment_epoch_id=None,
        candidate_id=None,
        dataset_snapshot_id=None,
        lease_generation=None,
        trace_id=None,
        created_at=occurred_at,
    )


async def _require_started_authority(
    session: AsyncSession,
    graph: _LockedClaimGraph,
) -> None:
    command = graph.command
    if command.authorization_id is None or command.evaluation_id is None:
        raise ValueError("HOLDOUT_CLAIM_COMMAND_BINDING_MISMATCH")
    authorization, evaluation, audit = await _load_started_authority(session, graph)
    if not _started_authority_matches(
        graph,
        authorization=authorization,
        evaluation=evaluation,
        audit=audit,
    ):
        raise ValueError("HOLDOUT_CLAIM_AUTHORITY_INCONSISTENT")


async def _require_recoverable_started_authority(
    session: AsyncSession,
    graph: _LockedClaimGraph,
) -> None:
    """Validate either the pristine start graph or its immutable checkpoint."""

    authorization, evaluation, audit = await _load_started_authority(session, graph)
    # Keep the no-checkpoint path on the narrower claim invariant.
    if evaluation is None or evaluation.returns_artifact_id is None:
        if not _started_authority_matches(
            graph,
            authorization=authorization,
            evaluation=evaluation,
            audit=audit,
        ):
            raise ValueError("HOLDOUT_CLAIM_AUTHORITY_INCONSISTENT")
        return

    # The finalizer owns the canonical immutable binding validator.  Importing
    # it here avoids duplicating the artifact contract and avoids a module-load
    # cycle because holdout_finalize itself imports this claim module.
    from app.services.research.holdout_finalize import (
        _load_binding,
        _require_checkpoint_binding,
        _require_started_graph,
    )

    try:
        binding = await _load_binding(session, command_id=graph.command.id)
        _require_started_graph(
            graph,
            authorization=authorization,
            evaluation=evaluation,
            claim_audit=audit,
            binding=binding,
        )
        if authorization is None or evaluation is None or binding is None:
            raise ValueError("HOLDOUT_CLAIM_AUTHORITY_INCONSISTENT")
        await _require_checkpoint_binding(
            session,
            graph=graph,
            authorization=authorization,
            evaluation=evaluation,
            claim_audit=audit,
            binding=binding,
        )
    except ValueError as exc:
        raise ValueError("HOLDOUT_CLAIM_AUTHORITY_INCONSISTENT") from exc


async def _load_started_authority(
    session: AsyncSession,
    graph: _LockedClaimGraph,
) -> tuple[
    ResearchHoldoutAuthorization | None,
    ResearchEvaluation | None,
    ResearchHoldoutAccessAudit | None,
]:
    command = graph.command
    if command.authorization_id is None or command.evaluation_id is None:
        return None, None, None
    authorization = await session.scalar(
        select(ResearchHoldoutAuthorization)
        .where(ResearchHoldoutAuthorization.id == command.authorization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    evaluation = await session.scalar(
        select(ResearchEvaluation)
        .where(ResearchEvaluation.id == command.evaluation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    audit = await session.scalar(
        select(ResearchHoldoutAccessAudit)
        .where(
            ResearchHoldoutAccessAudit.action == "CLAIM_STARTED",
            ResearchHoldoutAccessAudit.command_id == command.id,
            ResearchHoldoutAccessAudit.lease_generation == command.lease_generation,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return authorization, evaluation, audit


def _started_authority_matches(
    graph: _LockedClaimGraph,
    *,
    authorization: ResearchHoldoutAuthorization | None,
    evaluation: ResearchEvaluation | None,
    audit: ResearchHoldoutAccessAudit | None,
) -> bool:
    command = graph.command
    if authorization is None or evaluation is None or audit is None:
        return False
    started_at = _optional_time(command.started_at)
    issued_at = _optional_time(authorization.issued_at)
    consumed_at = _optional_time(authorization.consumed_at)
    authorization_expires_at = _optional_time(authorization.expires_at)
    evaluation_started_at = _optional_time(evaluation.started_at)
    disclosed_at = _optional_time(graph.epoch.disclosed_at)
    audit_created_at = _optional_time(audit.created_at)
    lease_heartbeat_at = _optional_time(command.lease_heartbeat_at)
    lease_expires_at = _optional_time(command.lease_expires_at)
    return bool(
        command.status == "RUNNING"
        and command.stage == "HOLDOUT_PENDING"
        and command.error_code is None
        and command.authorization_id == authorization.id
        and command.evaluation_id == evaluation.id
        and command.lease_owner is not None
        and command.lease_token_hash is not None
        and _is_sha256(command.lease_token_hash)
        and command.lease_generation >= 1
        and command.attempt_count >= 1
        and started_at is not None
        and lease_heartbeat_at is not None
        and lease_heartbeat_at >= started_at
        and lease_expires_at is not None
        and authorization.status == "CONSUMED"
        and authorization.experiment_epoch_id == command.experiment_epoch_id
        and authorization.candidate_id == command.candidate_id
        and authorization.candidate_hash == command.candidate_hash
        and authorization.dataset_snapshot_id == command.dataset_snapshot_id
        and authorization.policy_version == command.policy_version
        and authorization.token_hash != command.lease_token_hash
        and _is_sha256(authorization.token_hash)
        and authorization.evaluator_identity == command.evaluator_identity
        and authorization.capability_profile_id == command.capability_profile_id
        and authorization.capability_profile_version == command.capability_profile_version
        and authorization.capability_evidence_hash == command.capability_evidence_hash
        and authorization.issued_by == command.lease_owner
        and issued_at == started_at
        and consumed_at == started_at
        and authorization_expires_at is not None
        and authorization_expires_at > started_at
        and evaluation.experiment_epoch_id == command.experiment_epoch_id
        and evaluation.candidate_id == command.candidate_id
        and evaluation.dataset_snapshot_id == command.dataset_snapshot_id
        and evaluation.evaluation_type == "SEALED_HOLDOUT"
        and evaluation.evaluator_identity == command.evaluator_identity
        and evaluation.evaluator_version == command.evaluator_version
        and evaluation.authorization_id == authorization.id
        and evaluation.returns_artifact_id is None
        and (evaluation.metrics or {}) == {}
        and (evaluation.gate_inputs or {}) == {}
        and evaluation.policy_version == command.policy_version
        and evaluation.status == "RUNNING"
        and evaluation_started_at == started_at
        and evaluation.completed_at is None
        and graph.epoch.status == "DISCLOSED"
        and graph.epoch.selected_candidate_id == command.candidate_id
        and disclosed_at == started_at
        and graph.epoch.closed_at is None
        and audit.actor_identity == command.lease_owner
        and audit.evaluator_version == command.evaluator_version
        and audit.requested_command_id == command.id
        and audit.action == "CLAIM_STARTED"
        and audit.result == "ACCEPTED"
        and audit.reason_code == "HOLDOUT_CLAIM_STARTED"
        and audit.command_id == command.id
        and audit.authorization_id == authorization.id
        and audit.evaluation_id == evaluation.id
        and audit.experiment_epoch_id == command.experiment_epoch_id
        and audit.candidate_id == command.candidate_id
        and audit.dataset_snapshot_id == command.dataset_snapshot_id
        and audit.lease_generation == command.lease_generation
        and audit.trace_id == command.trace_id
        and audit_created_at == started_at
    )


def _command_commit_state(command: ResearchHoldoutEvaluationCommand) -> tuple[object, ...]:
    return _model_commit_state(command)


def _authorization_commit_state(
    authorization: ResearchHoldoutAuthorization,
) -> tuple[object, ...]:
    return _model_commit_state(authorization)


def _evaluation_commit_state(evaluation: ResearchEvaluation) -> tuple[object, ...]:
    return _model_commit_state(evaluation)


def _epoch_commit_state(epoch: ResearchExperimentEpoch) -> tuple[object, ...]:
    return _model_commit_state(epoch)


def _access_audit_commit_state(audit: ResearchHoldoutAccessAudit) -> tuple[object, ...]:
    return _model_commit_state(audit)


def _locked_authority_commit_state(graph: _LockedClaimGraph) -> tuple[object, ...]:
    return (
        ("candidate", _model_commit_state(graph.candidate)),
        ("freeze_receipt", _model_commit_state(graph.receipt)),
        ("run", _model_commit_state(graph.run)),
        ("capability_profile", _model_commit_state(graph.profile)),
        ("discovery_snapshot", _model_commit_state(graph.discovery)),
        ("sealed_snapshot", _model_commit_state(graph.sealed)),
    )


def _model_commit_state(model: object) -> tuple[object, ...]:
    table = model.__table__  # type: ignore[attr-defined]
    return tuple(
        (column.key, _normalize_state_value(getattr(model, column.key))) for column in table.columns
    )


def _normalize_state_value(value: object) -> object:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, dict):
        return tuple(
            (str(key), _normalize_state_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_normalize_state_value(item) for item in value)
    return value


def _command_request_hash_matches(command: ResearchHoldoutEvaluationCommand) -> bool:
    return command.request_hash == holdout_request_binding_hash(
        user_id=command.user_id,
        run_id=command.run_id,
        experiment_epoch_id=command.experiment_epoch_id,
        candidate_id=command.candidate_id,
        candidate_hash=command.candidate_hash,
        freeze_receipt_id=command.freeze_receipt_id,
        freeze_receipt_fingerprint=command.freeze_receipt_fingerprint,
        dataset_snapshot_id=command.dataset_snapshot_id,
        dataset_policy_version=command.dataset_policy_version,
        sealed_dataset_hash=command.sealed_dataset_hash,
        sealed_dataset_identity_hash=command.sealed_dataset_identity_hash,
        policy_version=command.policy_version,
        evaluator_identity=command.evaluator_identity,
        evaluator_version=command.evaluator_version,
        capability_profile_id=command.capability_profile_id,
        capability_profile_version=command.capability_profile_version,
        capability_evidence_hash=command.capability_evidence_hash,
    )


def _can_fence_pre_authority_command(command: ResearchHoldoutEvaluationCommand) -> bool:
    return bool(
        command.status == "QUEUED"
        and command.stage == "REQUEST_HOLDOUT"
        and command.authorization_id is None
        and command.evaluation_id is None
        and command.lease_owner is None
        and command.lease_token_hash is None
        and command.lease_generation == 0
        and command.lease_expires_at is None
        and command.lease_heartbeat_at is None
        and command.started_at is None
    )


def _can_fence_started_command(command: ResearchHoldoutEvaluationCommand) -> bool:
    return bool(
        command.status in {"RUNNING", "RECONCILING"}
        and command.stage == "HOLDOUT_PENDING"
        and command.authorization_id is not None
        and command.evaluation_id is not None
        and command.lease_generation >= 1
        and command.started_at is not None
    )


def _has_active_lease_fragment(command: ResearchHoldoutEvaluationCommand) -> bool:
    return any(
        value is not None
        for value in (
            command.lease_owner,
            command.lease_token_hash,
            command.lease_expires_at,
            command.lease_heartbeat_at,
        )
    )


def _fence_unknown_command(
    command: ResearchHoldoutEvaluationCommand | None,
    *,
    occurred_at: datetime,
) -> None:
    if command is None:
        return
    if _can_fence_pre_authority_command(command):
        command.status = "RECONCILING"
        command.stage = "REQUEST_HOLDOUT"
        command.error_code = "HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN"
        command.attempt_count = 0
        command.updated_at = occurred_at
        return
    if _can_fence_started_command(command):
        command.status = "RECONCILING"
        command.stage = "HOLDOUT_PENDING"
        command.error_code = "HOLDOUT_CLAIM_COMMIT_OUTCOME_UNKNOWN"
        command.attempt_count = command.lease_generation
        command.lease_owner = None
        command.lease_token_hash = None
        command.lease_expires_at = None
        command.lease_heartbeat_at = None
        command.updated_at = occurred_at
        return
    if command.status == "QUEUED" or _has_active_lease_fragment(command):
        raise ValueError("HOLDOUT_CLAIM_UNKNOWN_STATE_UNFENCEABLE")


def _committed_claim_matches(
    probe: _CommitProbe,
    *,
    graph: _LockedClaimGraph,
    authorization: ResearchHoldoutAuthorization | None,
    evaluation: ResearchEvaluation | None,
    audit: ResearchHoldoutAccessAudit | None,
) -> bool:
    command = graph.command
    return bool(
        authorization is not None
        and evaluation is not None
        and audit is not None
        and command.id == probe.command_id
        and command.authorization_id == probe.authorization_id
        and command.evaluation_id == probe.evaluation_id
        and command.experiment_epoch_id == probe.experiment_epoch_id
        and command.candidate_id == probe.candidate_id
        and command.dataset_snapshot_id == probe.dataset_snapshot_id
        and command.request_hash == probe.request_hash
        and command.evaluator_identity == probe.evaluator_identity
        and command.evaluator_version == probe.evaluator_version
        and command.lease_owner == probe.lease_owner
        and command.lease_token_hash == probe.lease_token_hash
        and command.lease_generation == probe.lease_generation
        and _optional_time(command.lease_expires_at) == _as_utc(probe.lease_expires_at)
        and _secret_hash(probe.lease_token) == probe.lease_token_hash
        and _command_request_hash_matches(command)
        and _command_commit_state(command) == probe.command_state
        and _authorization_commit_state(authorization) == probe.authorization_state
        and _evaluation_commit_state(evaluation) == probe.evaluation_state
        and _epoch_commit_state(graph.epoch) == probe.epoch_state
        and _access_audit_commit_state(audit) == probe.audit_state
        and _locked_authority_commit_state(graph) == probe.locked_authority_state
        and _started_authority_matches(
            graph,
            authorization=authorization,
            evaluation=evaluation,
            audit=audit,
        )
    )


def _claimed_from_probe(probe: _CommitProbe) -> ClaimedHoldoutEvaluation:
    return ClaimedHoldoutEvaluation(
        command_id=probe.command_id,
        evaluation_id=probe.evaluation_id,
        candidate_id=probe.candidate_id,
        lease_owner=probe.lease_owner,
        lease_generation=probe.lease_generation,
        lease_expires_at=probe.lease_expires_at,
        lease_token=probe.lease_token,
    )


def _claim_lock(command_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    shards = _CLAIM_LOCK_SHARDS_BY_LOOP.get(loop)
    if shards is None:
        shards = tuple(asyncio.Lock() for _ in range(_CLAIM_LOCK_SHARD_COUNT))
        _CLAIM_LOCK_SHARDS_BY_LOOP[loop] = shards
    index = int.from_bytes(hashlib.sha256(command_id.encode()).digest()[:8], "big") % len(shards)
    return shards[index]


def _secret_hash(value: str) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return hashlib.sha256(value.encode()).hexdigest()


def _required_time(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("HOLDOUT_CLAIM_LEASE_STALE")
    return _as_utc(value)


def _optional_time(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _safe_reason_code(exc: ValueError) -> str:
    reason = str(exc)
    if reason.startswith("HOLDOUT_") or reason.startswith("DATASET_"):
        return reason[:128]
    return "HOLDOUT_CLAIM_REJECTED"
