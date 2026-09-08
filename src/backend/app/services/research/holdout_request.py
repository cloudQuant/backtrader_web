"""Durable server-owned requests for independent sealed-holdout evaluation."""

from __future__ import annotations

import asyncio
import hashlib
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchCandidate,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutRequestAudit,
    ResearchRun,
)
from app.services.research.candidate_registry import (
    require_strict_freeze_receipt,
    strict_freeze_receipt_fingerprint,
    verify_candidate_integrity,
)
from app.services.research.canonical import content_hash
from app.services.research.capabilities import (
    BLOCKED_TOPOLOGY_CAPABILITY,
    CapabilityProfile,
    evaluate_capabilities,
)
from app.services.research.database_clock import database_utc_now
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.discovery_search_budget import lock_experiment_epoch
from app.services.research.promotion import resolve_server_policy

_REQUEST_SCHEMA_VERSION = "holdout-evaluation-request-v1"
_REQUEST_INTENT_SCHEMA_VERSION = "holdout-evaluation-request-intent-v1"
_INVALID_EXPECTED_HASH_SCHEMA_VERSION = "holdout-evaluation-invalid-expected-hash-v1"
_AUDIT_PURPOSE = "HOLDOUT_EVALUATION_REQUEST"
_REQUEST_LOCK_SHARD_COUNT = 64
_REQUEST_LOCK_SHARDS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop,
    tuple[asyncio.Lock, ...],
] = weakref.WeakKeyDictionary()


class _AcceptedAuditInsertError(Exception):
    """Mark failure to atomically append the success audit row."""


@dataclass(frozen=True, slots=True)
class _CommitProbe:
    """Immutable command binding retained across a failed COMMIT acknowledgement."""

    user_id: str
    idempotency_key: str
    command_id: str
    candidate_id: str
    candidate_hash: str
    request_hash: str
    dataset_snapshot_id: str
    trace_id: str


@dataclass(frozen=True, slots=True)
class _SnapshotFailureProbe:
    """Exact sealed identity observed as failed before the request rollback."""

    user_id: str
    snapshot_id: str
    snapshot_identity_hash: str
    checked_at: datetime
    reason_code: str


class _CommitOutcomeUncertain(Exception):
    """Carry a safe probe when the database did not acknowledge COMMIT."""

    def __init__(self, probe: _CommitProbe) -> None:
        super().__init__("HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class _SnapshotRevalidationFailure(ValueError):
    """Defer FAILED persistence until the authority transaction has rolled back."""

    def __init__(self, probe: _SnapshotFailureProbe) -> None:
        super().__init__(probe.reason_code)
        self.probe = probe


class HoldoutRequestCapabilityError(ValueError):
    """Carry stable capability denial fields across the service/API boundary."""

    def __init__(self, code: str, missing_capabilities: tuple[str, ...]) -> None:
        super().__init__(code)
        self.code = code
        self.missing_capabilities = tuple(dict.fromkeys(missing_capabilities))


class HoldoutRequestService:
    """Validate frozen authority and enqueue one immutable holdout intent."""

    def __init__(self, *, dataset_registry: DatasetRegistry | None = None) -> None:
        """Use the deployment-owned resolver for every sealed-object check."""

        self._datasets = dataset_registry or DatasetRegistry()

    async def get(
        self,
        *,
        user_id: str,
        command_id: str,
    ) -> ResearchHoldoutEvaluationCommand | None:
        """Read one safe command state without exposing another owner's identifier."""

        async with database.async_session_maker() as session:
            return await session.scalar(
                select(ResearchHoldoutEvaluationCommand).where(
                    ResearchHoldoutEvaluationCommand.id == command_id,
                    ResearchHoldoutEvaluationCommand.user_id == user_id,
                )
            )

    async def request(
        self,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: str,
        idempotency_key: str,
    ) -> ResearchHoldoutEvaluationCommand:
        """Queue one server-bound command without issuing or exposing a token."""

        normalized_key = idempotency_key.strip()
        intent_hash = _request_intent_hash(
            user_id=user_id,
            candidate_id=candidate_id,
            expected_candidate_hash=expected_candidate_hash,
        )
        if not normalized_key or len(normalized_key) > 128:
            error = ValueError("HOLDOUT_REQUEST_IDEMPOTENCY_KEY_INVALID")
            await self.record_rejected_request(
                user_id=user_id,
                candidate_id=candidate_id,
                expected_candidate_hash=expected_candidate_hash,
                reason_code=str(error),
            )
            raise error

        async with _request_lock(user_id, normalized_key):
            try:
                try:
                    return await self._request_once(
                        user_id=user_id,
                        candidate_id=candidate_id,
                        expected_candidate_hash=expected_candidate_hash,
                        idempotency_key=normalized_key,
                    )
                except IntegrityError:
                    # Database uniqueness is the cross-process authority. Re-run
                    # validation so the committed winner can be replayed safely.
                    return await self._request_once(
                        user_id=user_id,
                        candidate_id=candidate_id,
                        expected_candidate_hash=expected_candidate_hash,
                        idempotency_key=normalized_key,
                    )
            except _CommitOutcomeUncertain as exc:
                return await self._reconcile_commit_or_raise_unknown(
                    probe=exc.probe,
                    expected_candidate_hash=expected_candidate_hash,
                    intent_hash=intent_hash,
                )
            except _SnapshotRevalidationFailure as exc:
                return await self._persist_snapshot_failure_and_raise(
                    probe=exc.probe,
                    candidate_id=candidate_id,
                    expected_candidate_hash=expected_candidate_hash,
                    intent_hash=intent_hash,
                )
            except _AcceptedAuditInsertError as exc:
                await self._record_rejection_or_fail(
                    user_id=user_id,
                    candidate_id=candidate_id,
                    expected_candidate_hash=expected_candidate_hash,
                    request_hash=intent_hash,
                    reason_code="HOLDOUT_REQUEST_AUDIT_UNAVAILABLE",
                )
                raise ValueError("HOLDOUT_REQUEST_AUDIT_UNAVAILABLE") from exc
            except ValueError as exc:
                await self._record_rejection_or_fail(
                    user_id=user_id,
                    candidate_id=candidate_id,
                    expected_candidate_hash=expected_candidate_hash,
                    request_hash=intent_hash,
                    reason_code=str(exc),
                )
                raise
            except SQLAlchemyError as exc:
                await self._record_rejection_or_fail(
                    user_id=user_id,
                    candidate_id=candidate_id,
                    expected_candidate_hash=expected_candidate_hash,
                    request_hash=intent_hash,
                    reason_code="HOLDOUT_REQUEST_PERSISTENCE_FAILED",
                )
                raise ValueError("HOLDOUT_REQUEST_PERSISTENCE_FAILED") from exc

    async def record_rejected_request(
        self,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: object,
        reason_code: str,
    ) -> None:
        """Persist a safe rejection generated before authority validation starts."""

        safe_expected_hash = _safe_expected_candidate_hash(
            user_id=user_id,
            candidate_id=candidate_id,
            value=expected_candidate_hash,
        )
        await self._record_rejection_or_fail(
            user_id=user_id,
            candidate_id=candidate_id,
            expected_candidate_hash=safe_expected_hash,
            request_hash=_request_intent_hash(
                user_id=user_id,
                candidate_id=candidate_id,
                expected_candidate_hash=safe_expected_hash,
            ),
            reason_code=reason_code,
        )

    async def _request_once(
        self,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: str,
        idempotency_key: str,
    ) -> ResearchHoldoutEvaluationCommand:
        # Imported lazily so the compatibility registry remains independent of
        # the durable command service at module initialization time.
        from app.services.research.holdout_authorization import (
            _public_holdout_authority_lock,
        )

        async with _public_holdout_authority_lock(candidate_id):
            return await self._request_once_serialized(
                user_id=user_id,
                candidate_id=candidate_id,
                expected_candidate_hash=expected_candidate_hash,
                idempotency_key=idempotency_key,
            )

    async def _request_once_serialized(
        self,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: str,
        idempotency_key: str,
    ) -> ResearchHoldoutEvaluationCommand:
        async with database.async_session_maker() as session:
            try:
                command = await self._request_in_session(
                    session,
                    user_id=user_id,
                    candidate_id=candidate_id,
                    expected_candidate_hash=expected_candidate_hash,
                    idempotency_key=idempotency_key,
                )
                await session.refresh(command)
            except Exception:
                await session.rollback()
                raise
            probe = _commit_probe(command)
            try:
                await self._commit(session)
            except Exception as exc:
                try:
                    await session.rollback()
                except Exception:
                    # A broken connection cannot change the classification:
                    # COMMIT was sent, so only primary readback can resolve it.
                    pass
                raise _CommitOutcomeUncertain(probe) from exc
            return command

    async def _commit(self, session: AsyncSession) -> None:
        """Commit through a narrow seam so acknowledgement loss is testable."""

        await session.commit()

    async def _reconcile_commit_or_raise_unknown(
        self,
        *,
        probe: _CommitProbe,
        expected_candidate_hash: str,
        intent_hash: str,
    ) -> ResearchHoldoutEvaluationCommand:
        """Return an exact durable winner or append an uncertainty outcome."""

        try:
            winner = await self._reconcile_commit_outcome(probe)
        except Exception:
            winner = None
        if winner is not None:
            return winner
        await self._record_audit_or_fail(
            user_id=probe.user_id,
            candidate_id=probe.candidate_id,
            expected_candidate_hash=expected_candidate_hash,
            request_hash=intent_hash,
            reason_code="HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN",
            result="UNKNOWN",
        )
        raise ValueError("HOLDOUT_REQUEST_COMMIT_OUTCOME_UNKNOWN")

    async def _reconcile_commit_outcome(
        self,
        probe: _CommitProbe,
    ) -> ResearchHoldoutEvaluationCommand | None:
        """Read the writer database and validate both command and accepted audit."""

        async with database.async_session_maker() as session:
            command = await _command_by_idempotency_key(
                session,
                probe.user_id,
                probe.idempotency_key,
            )
            if command is None:
                return None
            if (
                command.id != probe.command_id
                or command.candidate_id != probe.candidate_id
                or command.candidate_hash != probe.candidate_hash
                or command.request_hash != probe.request_hash
                or command.dataset_snapshot_id != probe.dataset_snapshot_id
                or command.trace_id != probe.trace_id
            ):
                return None
            audit = await session.scalar(
                select(ResearchHoldoutRequestAudit).where(
                    ResearchHoldoutRequestAudit.command_id == command.id,
                    ResearchHoldoutRequestAudit.result == "ACCEPTED",
                )
            )
            if (
                audit is None
                or audit.actor_user_id != probe.user_id
                or audit.candidate_id != probe.candidate_id
                or audit.expected_candidate_hash != probe.candidate_hash
                or audit.resolved_snapshot_id != probe.dataset_snapshot_id
                or audit.request_hash != probe.request_hash
                or audit.trace_id != probe.trace_id
            ):
                return None
            return command

    async def _persist_snapshot_failure_and_raise(
        self,
        *,
        probe: _SnapshotFailureProbe,
        candidate_id: str,
        expected_candidate_hash: str,
        intent_hash: str,
    ) -> ResearchHoldoutEvaluationCommand:
        """Quarantine the exact failed object in an independent transaction."""

        try:
            await self._datasets.persist_failed_snapshot(
                user_id=probe.user_id,
                snapshot_id=probe.snapshot_id,
                expected_snapshot_identity_hash=probe.snapshot_identity_hash,
                checked_at=probe.checked_at,
            )
        except Exception as exc:
            code = "HOLDOUT_REQUEST_SNAPSHOT_FAILURE_PERSISTENCE_FAILED"
            await self._record_audit_or_fail(
                user_id=probe.user_id,
                candidate_id=candidate_id,
                expected_candidate_hash=expected_candidate_hash,
                request_hash=intent_hash,
                reason_code=code,
                result="UNKNOWN",
            )
            raise ValueError(code) from exc
        await self._record_rejection_or_fail(
            user_id=probe.user_id,
            candidate_id=candidate_id,
            expected_candidate_hash=expected_candidate_hash,
            request_hash=intent_hash,
            reason_code=probe.reason_code,
        )
        raise ValueError(probe.reason_code)

    async def _record_rejection_or_fail(
        self,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: str,
        request_hash: str,
        reason_code: str,
    ) -> None:
        """Append rejection evidence after the authority transaction rolled back."""

        await self._record_audit_or_fail(
            user_id=user_id,
            candidate_id=candidate_id,
            expected_candidate_hash=expected_candidate_hash,
            request_hash=request_hash,
            reason_code=reason_code,
            result="REJECTED",
        )

    async def _record_audit_or_fail(
        self,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: str,
        request_hash: str,
        reason_code: str,
        result: str,
    ) -> None:
        """Append one non-accepted outcome without authority identifiers."""

        try:
            async with database.async_session_maker() as session:
                now = await database_utc_now(session)
                session.add(
                    ResearchHoldoutRequestAudit(
                        actor_user_id=user_id,
                        candidate_id=candidate_id,
                        expected_candidate_hash=expected_candidate_hash,
                        resolved_snapshot_id=None,
                        purpose=_AUDIT_PURPOSE,
                        result=result,
                        reason_code=reason_code,
                        command_id=None,
                        request_hash=request_hash,
                        trace_id=None,
                        created_at=now,
                    )
                )
                await session.commit()
        except Exception as exc:
            raise ValueError("HOLDOUT_REQUEST_AUDIT_UNAVAILABLE") from exc

    async def _request_in_session(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        candidate_id: str,
        expected_candidate_hash: str,
        idempotency_key: str,
    ) -> ResearchHoldoutEvaluationCommand:
        existing_hint = await _command_by_idempotency_key(session, user_id, idempotency_key)
        if existing_hint is not None:
            if (
                existing_hint.candidate_id != candidate_id
                or existing_hint.candidate_hash != expected_candidate_hash
            ):
                raise ValueError("HOLDOUT_REQUEST_IDEMPOTENCY_CONFLICT")
            # This is a read of an already accepted intent, not a new grant.
            # Returning it remains idempotent after a worker advances the epoch.
            return existing_hint

        epoch_id = await session.scalar(
            select(ResearchCandidate.experiment_epoch_id).where(
                ResearchCandidate.id == candidate_id,
                ResearchCandidate.user_id == user_id,
            )
        )
        if epoch_id is None:
            raise ValueError("CANDIDATE_NOT_FOUND")
        epoch = await lock_experiment_epoch(
            session,
            user_id=user_id,
            epoch_id=epoch_id,
            require_open=False,
            denied_code="HOLDOUT_REQUEST_EPOCH_NOT_SELECTED",
        )
        authorization_id = await session.scalar(
            select(ResearchHoldoutAuthorization.id)
            .where(ResearchHoldoutAuthorization.experiment_epoch_id == epoch.id)
            .with_for_update()
        )
        if authorization_id is not None:
            raise ValueError("HOLDOUT_REQUEST_AUTHORIZATION_ALREADY_EXISTS")
        candidate = await session.scalar(
            select(ResearchCandidate)
            .where(
                ResearchCandidate.id == candidate_id,
                ResearchCandidate.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if candidate is None:
            raise ValueError("CANDIDATE_NOT_FOUND")
        if candidate.experiment_epoch_id != epoch.id:
            raise ValueError("HOLDOUT_REQUEST_CANDIDATE_BINDING_MISMATCH")
        if candidate.freeze_status != "FROZEN":
            raise ValueError("CANDIDATE_NOT_FROZEN")
        await verify_candidate_integrity(session, candidate)
        if candidate.candidate_hash != expected_candidate_hash:
            raise ValueError("HOLDOUT_REQUEST_CANDIDATE_HASH_MISMATCH")
        if (
            epoch.status != "SELECTED"
            or epoch.selected_candidate_id != candidate.id
            or epoch.disclosed_at is not None
            or epoch.closed_at is not None
        ):
            raise ValueError("HOLDOUT_REQUEST_EPOCH_NOT_SELECTED")
        receipt = await require_strict_freeze_receipt(session, candidate)
        receipt_fingerprint = strict_freeze_receipt_fingerprint(receipt)

        run = await session.scalar(
            select(ResearchRun)
            .where(
                ResearchRun.id == candidate.run_id,
                ResearchRun.user_id == user_id,
                ResearchRun.experiment_epoch_id == epoch.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise ValueError("HOLDOUT_REQUEST_RUN_BINDING_MISMATCH")
        policy = resolve_server_policy(run.promotion_policy_version)
        profile = await _run_profile(session, run)
        now = await database_utc_now(session)
        capability = evaluate_capabilities(profile, required=("sealed_evaluation",), now=now)
        if not capability.allowed:
            raise HoldoutRequestCapabilityError(
                capability.code or BLOCKED_TOPOLOGY_CAPABILITY,
                capability.missing_capabilities,
            )
        evaluator_identity = profile.service_identities.get("evaluator")
        evaluator_version = profile.stage_image_digests.get("evaluator")
        if (
            not isinstance(evaluator_identity, str)
            or not evaluator_identity.strip()
            or not isinstance(evaluator_version, str)
            or not evaluator_version.strip()
        ):
            raise HoldoutRequestCapabilityError(
                BLOCKED_TOPOLOGY_CAPABILITY,
                ("sealed_evaluation",),
            )
        evaluator_identity = evaluator_identity.strip()
        evaluator_version = evaluator_version.strip()

        sealed = await _select_owner_sealed_snapshot(
            session,
            user_id=user_id,
            dataset_policy_version=epoch.dataset_policy_version,
        )
        try:
            await self._datasets.revalidate_snapshot_in_session(session, snapshot=sealed)
        except ValueError as exc:
            reason_code = str(exc)
            if reason_code not in {
                "DATASET_OBJECT_REVALIDATION_UNAVAILABLE",
                "DATASET_OBJECT_ATTESTATION_MISMATCH",
            }:
                raise
            if sealed.snapshot_identity_hash is None or sealed.integrity_checked_at is None:
                raise ValueError("DATASET_SNAPSHOT_IDENTITY_HASH_REQUIRED") from exc
            raise _SnapshotRevalidationFailure(
                _SnapshotFailureProbe(
                    user_id=user_id,
                    snapshot_id=sealed.id,
                    snapshot_identity_hash=sealed.snapshot_identity_hash,
                    checked_at=_stored_utc(sealed.integrity_checked_at),
                    reason_code=reason_code,
                )
            ) from exc
        require_verified_snapshot_integrity(sealed)
        if sealed.snapshot_identity_hash is None:
            raise ValueError("DATASET_SNAPSHOT_IDENTITY_HASH_REQUIRED")

        request_hash = holdout_request_binding_hash(
            user_id=user_id,
            run_id=run.id,
            experiment_epoch_id=epoch.id,
            candidate_id=candidate.id,
            candidate_hash=candidate.candidate_hash,
            freeze_receipt_id=receipt.id,
            freeze_receipt_fingerprint=receipt_fingerprint,
            dataset_snapshot_id=sealed.id,
            dataset_policy_version=sealed.dataset_policy_version,
            sealed_dataset_hash=sealed.content_hash,
            sealed_dataset_identity_hash=sealed.snapshot_identity_hash,
            policy_version=policy.version,
            evaluator_identity=evaluator_identity,
            evaluator_version=evaluator_version,
            capability_profile_id=profile.profile_id,
            capability_profile_version=profile.version,
            capability_evidence_hash=profile.evidence_hash,
        )
        existing = await _command_by_idempotency_key(
            session,
            user_id,
            idempotency_key,
            lock=True,
        )
        if existing is not None:
            return _resolve_existing(existing, request_hash)
        epoch_command = await session.scalar(
            select(ResearchHoldoutEvaluationCommand)
            .where(ResearchHoldoutEvaluationCommand.experiment_epoch_id == epoch.id)
            .with_for_update()
        )
        if epoch_command is not None:
            raise ValueError("HOLDOUT_REQUEST_ALREADY_QUEUED")

        command = ResearchHoldoutEvaluationCommand(
            user_id=user_id,
            run_id=run.id,
            workspace_id=run.workspace_id,
            experiment_epoch_id=epoch.id,
            candidate_id=candidate.id,
            candidate_hash=candidate.candidate_hash,
            expected_candidate_state="FROZEN",
            freeze_receipt_id=receipt.id,
            freeze_receipt_fingerprint=receipt_fingerprint,
            dataset_snapshot_id=sealed.id,
            dataset_policy_version=sealed.dataset_policy_version,
            sealed_dataset_hash=sealed.content_hash,
            sealed_dataset_identity_hash=sealed.snapshot_identity_hash,
            policy_version=policy.version,
            evaluator_identity=evaluator_identity,
            evaluator_version=evaluator_version,
            capability_profile_id=profile.profile_id,
            capability_profile_version=profile.version,
            capability_evidence_hash=profile.evidence_hash,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            trace_id=run.trace_id,
            status="QUEUED",
            stage="REQUEST_HOLDOUT",
            created_at=now,
            updated_at=now,
        )
        session.add(command)
        await session.flush()
        session.add(
            ResearchHoldoutRequestAudit(
                actor_user_id=user_id,
                candidate_id=candidate.id,
                expected_candidate_hash=expected_candidate_hash,
                resolved_snapshot_id=sealed.id,
                purpose=_AUDIT_PURPOSE,
                result="ACCEPTED",
                reason_code="HOLDOUT_REQUEST_QUEUED",
                command_id=command.id,
                request_hash=request_hash,
                trace_id=run.trace_id,
                created_at=now,
            )
        )
        try:
            await session.flush()
        except SQLAlchemyError as exc:
            raise _AcceptedAuditInsertError from exc
        return command


async def _command_by_idempotency_key(
    session: AsyncSession,
    user_id: str,
    idempotency_key: str,
    *,
    lock: bool = False,
) -> ResearchHoldoutEvaluationCommand | None:
    statement = select(ResearchHoldoutEvaluationCommand).where(
        ResearchHoldoutEvaluationCommand.user_id == user_id,
        ResearchHoldoutEvaluationCommand.idempotency_key == idempotency_key,
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement.execution_options(populate_existing=True))


def _commit_probe(command: ResearchHoldoutEvaluationCommand) -> _CommitProbe:
    """Copy every reconciliation field before rollback can expire ORM state."""

    return _CommitProbe(
        user_id=command.user_id,
        idempotency_key=command.idempotency_key,
        command_id=command.id,
        candidate_id=command.candidate_id,
        candidate_hash=command.candidate_hash,
        request_hash=command.request_hash,
        dataset_snapshot_id=command.dataset_snapshot_id,
        trace_id=command.trace_id,
    )


def _resolve_existing(
    command: ResearchHoldoutEvaluationCommand,
    request_hash: str,
) -> ResearchHoldoutEvaluationCommand:
    if command.request_hash != request_hash:
        raise ValueError("HOLDOUT_REQUEST_IDEMPOTENCY_CONFLICT")
    return command


async def _run_profile(session: AsyncSession, run: ResearchRun) -> CapabilityProfile:
    model = await session.scalar(
        select(ResearchCapabilityProfile)
        .where(
            ResearchCapabilityProfile.profile_id == run.capability_profile_id,
            ResearchCapabilityProfile.version == run.capability_profile_version,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if model is None or model.evidence_hash != run.capability_evidence_hash:
        raise ValueError("HOLDOUT_REQUEST_RUN_PROFILE_MISMATCH")
    sandbox_capabilities = model.sandbox_capabilities or {}
    stage_image_digests = sandbox_capabilities.get("stage_image_digests")
    if not isinstance(stage_image_digests, dict):
        stage_image_digests = {}
    return CapabilityProfile(
        profile_id=model.profile_id,
        version=model.version,
        service_identities=dict(model.service_identities or {}),
        queue_isolation=bool((model.queue_capabilities or {}).get("isolated")),
        storage_isolation=bool((model.storage_boundaries or {}).get("isolated")),
        network_isolation=bool((model.network_capabilities or {}).get("isolated")),
        sandbox_runner=bool(sandbox_capabilities.get("runner")),
        approval_mode=str((model.approval_capabilities or {}).get("mode") or model.actor_mode),
        evidence_hash=model.evidence_hash,
        verified_at=_stored_utc(model.verified_at),
        expires_at=_stored_utc(model.expires_at),
        stage_image_digests={
            key: value
            for key, value in stage_image_digests.items()
            if isinstance(key, str) and isinstance(value, str)
        },
    )


async def _select_owner_sealed_snapshot(
    session: AsyncSession,
    *,
    user_id: str,
    dataset_policy_version: str,
) -> ResearchDatasetSnapshot:
    eligible = (
        ResearchDatasetSnapshot.user_id == user_id,
        ResearchDatasetSnapshot.partition_kind == "SEALED_HOLDOUT",
        ResearchDatasetSnapshot.dataset_policy_version == dataset_policy_version,
        ResearchDatasetSnapshot.integrity_status == "VERIFIED",
    )
    snapshot_ids = list(
        (
            await session.scalars(
                select(ResearchDatasetSnapshot.id)
                .where(*eligible)
                .order_by(ResearchDatasetSnapshot.id)
                .limit(2)
            )
        ).all()
    )
    if not snapshot_ids:
        raise ValueError("HOLDOUT_SNAPSHOT_NOT_FOUND")
    if len(snapshot_ids) != 1:
        raise ValueError("HOLDOUT_SNAPSHOT_SELECTION_AMBIGUOUS")
    snapshot = await session.scalar(
        select(ResearchDatasetSnapshot)
        .where(ResearchDatasetSnapshot.id == snapshot_ids[0], *eligible)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if snapshot is None:
        raise ValueError("HOLDOUT_SNAPSHOT_NOT_FOUND")
    require_verified_snapshot_integrity(snapshot)
    return snapshot


def _request_intent_hash(
    *,
    user_id: str,
    candidate_id: str,
    expected_candidate_hash: str,
) -> str:
    return content_hash(
        {
            "schema_version": _REQUEST_INTENT_SCHEMA_VERSION,
            "user_id": user_id,
            "candidate_id": candidate_id,
            "expected_candidate_hash": expected_candidate_hash,
            "purpose": _AUDIT_PURPOSE,
        }
    )


def holdout_request_binding_hash(
    *,
    user_id: str,
    run_id: str,
    experiment_epoch_id: str,
    candidate_id: str,
    candidate_hash: str,
    freeze_receipt_id: str,
    freeze_receipt_fingerprint: str,
    dataset_snapshot_id: str,
    dataset_policy_version: str,
    sealed_dataset_hash: str,
    sealed_dataset_identity_hash: str,
    policy_version: str,
    evaluator_identity: str,
    evaluator_version: str,
    capability_profile_id: str,
    capability_profile_version: str,
    capability_evidence_hash: str,
) -> str:
    """Return the canonical server-owned command binding hash."""

    return content_hash(
        {
            "schema_version": _REQUEST_SCHEMA_VERSION,
            "user_id": user_id,
            "run_id": run_id,
            "experiment_epoch_id": experiment_epoch_id,
            "candidate_id": candidate_id,
            "candidate_hash": candidate_hash,
            "freeze_receipt_id": freeze_receipt_id,
            "freeze_receipt_fingerprint": freeze_receipt_fingerprint,
            "dataset_snapshot_id": dataset_snapshot_id,
            "dataset_policy_version": dataset_policy_version,
            "sealed_dataset_hash": sealed_dataset_hash,
            "sealed_dataset_identity_hash": sealed_dataset_identity_hash,
            "policy_version": policy_version,
            "evaluator_identity": evaluator_identity,
            "evaluator_version": evaluator_version,
            "capability_profile_id": capability_profile_id,
            "capability_profile_version": capability_profile_version,
            "capability_evidence_hash": capability_evidence_hash,
        }
    )


def _safe_expected_candidate_hash(
    *,
    user_id: str,
    candidate_id: str,
    value: object,
) -> str:
    if isinstance(value, str) and len(value) == 64 and value == value.lower():
        try:
            int(value, 16)
        except ValueError:
            pass
        else:
            return value
    provided_length = len(value) if isinstance(value, (str, bytes, list, dict)) else None
    return content_hash(
        {
            "schema_version": _INVALID_EXPECTED_HASH_SCHEMA_VERSION,
            "user_id": user_id,
            "candidate_id": candidate_id,
            "provided_type": type(value).__name__,
            "provided_length": provided_length,
        }
    )


def _request_lock(user_id: str, idempotency_key: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    shards = _REQUEST_LOCK_SHARDS_BY_LOOP.get(loop)
    if shards is None:
        shards = tuple(asyncio.Lock() for _ in range(_REQUEST_LOCK_SHARD_COUNT))
        _REQUEST_LOCK_SHARDS_BY_LOOP[loop] = shards
    identity = f"{user_id}\0{idempotency_key}".encode()
    shard = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big")
    return shards[shard % _REQUEST_LOCK_SHARD_COUNT]


def _stored_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
