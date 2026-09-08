"""Lease-fenced checkpoint and finalization for claimed holdout evaluations.

This module is an internal worker boundary.  It never accepts caller-authored
artifact bindings, policies, gate outcomes, or terminal states.  The durable
holdout command remains the only lease authority throughout the transaction.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchEvaluation,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.database_clock import DatabaseUtcNow, database_utc_now
from app.services.research.holdout_claim import (
    HoldoutClaimService,
    HoldoutEvaluatorRuntimeIdentity,
    _accepted_access_audit,
    _claim_lock,
    _load_started_authority,
    _non_authoritative_access_audit,
    _validate_static_locked_authority,
)
from app.services.research.holdout_execution_contract import (
    HoldoutExecutionCommand,
    HoldoutExecutionResult,
)
from app.services.research.promotion import (
    CommandPromotionAuthority,
    CommandPromotionMode,
    PromotionGateEngine,
    PromotionResult,
    promotion_policy_material_hash,
    resolve_server_policy,
)

_BINDING_SCHEMA_VERSION = "holdout-artifact-binding-v1"
_EVIDENCE_SCHEMA_VERSION = "sealed-holdout-evidence-v1"
_EVIDENCE_KIND = "sealed_holdout_evidence"
_RECEIPT_KIND = "sealed_holdout_artifact_receipt"
_RECEIPT_SCHEMA_VERSION = "sealed-holdout-artifact-receipt-v1"
_RECEIPT_MEDIA_TYPE = "application/vnd.ai-research.sealed-holdout-receipt+json"
_MAX_EVIDENCE_BYTES = 10_000_000
_MEASUREMENT_KEYS = frozenset(
    {
        "returns",
        "trial_sharpes",
        "discovery_dataset_snapshot_hash",
        "cost_model_hash",
        "environment_hash",
        "capability_evidence_hash",
        "max_drawdown",
        "robustness_score",
        "cost_bps",
        "slippage_bps",
        "turnover",
        "capacity_notional",
        "extreme_path_loss",
        "execution_semantics_match",
        "security_critical_findings",
        "security_scan_hash",
    }
)
_REQUIRED_GATE_CODES = frozenset(
    {
        "CANDIDATE_FROZEN",
        "SEALED_HOLDOUT",
        "EVIDENCE_BINDING",
        "DEFLATED_SHARPE",
        "MAX_DRAWDOWN",
        "ROBUSTNESS",
        "COST",
        "SLIPPAGE",
        "TURNOVER",
        "CAPACITY",
        "EXTREME_PATH",
        "EXECUTION_SEMANTICS",
        "SECURITY_SCAN",
    }
)


@dataclass(frozen=True, slots=True)
class CheckpointedHoldoutEvidence:
    """Safe receipt for one immutable server-authored evidence checkpoint."""

    command_id: str
    evaluation_id: str
    artifact_id: str
    artifact_hash: str
    authority_binding_hash: str
    lease_generation: int


@dataclass(frozen=True, slots=True)
class FinalizedHoldoutEvaluation:
    """Safe terminal receipt without lease, authorization, or storage secrets."""

    command_id: str
    evaluation_id: str
    command_status: str
    evaluation_status: str
    input_evidence_hash: str
    eligible: bool
    gate_statuses: dict[str, str]


@dataclass(frozen=True, slots=True)
class _CheckpointProbe:
    receipt: CheckpointedHoldoutEvidence
    retained_content: bytes
    runtime: HoldoutEvaluatorRuntimeIdentity
    lease_token_hash: str


@dataclass(frozen=True, slots=True)
class _FinalizeProbe:
    receipt: FinalizedHoldoutEvaluation
    runtime: HoldoutEvaluatorRuntimeIdentity
    lease_generation: int
    terminal_action: str


@dataclass(frozen=True, slots=True)
class _ObservedCheckpointProbe:
    receipt: CheckpointedHoldoutEvidence
    operation_id: str
    result_hash: str
    runtime: HoldoutEvaluatorRuntimeIdentity
    lease_token_hash: str | None
    recovery: bool


class _CheckpointCommitOutcomeUncertain(Exception):
    def __init__(self, probe: _CheckpointProbe) -> None:
        super().__init__("HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class _FinalizeCommitOutcomeUncertain(Exception):
    def __init__(self, probe: _FinalizeProbe) -> None:
        super().__init__("HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class _ObservedCheckpointCommitOutcomeUncertain(Exception):
    def __init__(self, probe: _ObservedCheckpointProbe) -> None:
        super().__init__("HOLDOUT_FINALIZE_EXECUTION_COMMIT_OUTCOME_UNKNOWN")
        self.probe = probe


class HoldoutFinalizeService:
    """Checkpoint and finalize one already-claimed sealed evaluation."""

    def __init__(
        self,
        *,
        promotion_engine: PromotionGateEngine | None = None,
        allow_inline_test_measurements: bool = False,
    ) -> None:
        self._claims = HoldoutClaimService()
        self._promotion = promotion_engine or PromotionGateEngine()
        self._allow_inline_test_measurements = allow_inline_test_measurements

    @classmethod
    def _for_test_only_inline_measurements(cls) -> HoldoutFinalizeService:
        """Construct the legacy inline harness; production factories must not call this."""

        return cls(allow_inline_test_measurements=True)

    async def checkpoint_claimed_evidence(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token: str,
        lease_generation: int,
        measurements: Mapping[str, Any],
    ) -> CheckpointedHoldoutEvidence:
        """Persist legacy inline measurements only in an explicit test harness."""

        if not self._allow_inline_test_measurements:
            raise ValueError("HOLDOUT_FINALIZE_INLINE_MEASUREMENTS_DISABLED")

        async with _claim_lock(command_id):
            try:
                normalized_measurements = _canonical_measurements(measurements)
                return await self._checkpoint_once(
                    command_id=command_id,
                    runtime=runtime,
                    lease_token=lease_token,
                    lease_generation=lease_generation,
                    measurements=normalized_measurements,
                )
            except _CheckpointCommitOutcomeUncertain as exc:
                committed = await self._read_committed_checkpoint(exc.probe)
                if committed is not None:
                    return committed
                await self._fence_unknown(
                    command_id=command_id,
                    runtime=runtime,
                    action="CHECKPOINT_UNKNOWN",
                    reason_code="HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN",
                )
                raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN") from None
            except ValueError as exc:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="CHECKPOINT_REJECTED",
                    reason_code=_safe_reason_code(exc),
                )
                raise
            except SQLAlchemyError:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="CHECKPOINT_REJECTED",
                    reason_code="HOLDOUT_FINALIZE_PERSISTENCE_FAILED",
                )
                raise ValueError("HOLDOUT_FINALIZE_PERSISTENCE_FAILED") from None

    async def checkpoint_observed_execution(
        self,
        *,
        command_id: str,
        operation_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> CheckpointedHoldoutEvidence:
        """Recover an expired claim from one exact, durable evaluator receipt.

        This path deliberately accepts no lease token.  Authority comes from the
        locked claim graph plus the immutable OBSERVED execution journal row; the
        original claim owner remains recorded in the artifact binding.
        """

        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
        async with _claim_lock(command_id):
            try:
                return await self._checkpoint_observed_once(
                    command_id=command_id,
                    operation_id=operation_id,
                    runtime=runtime,
                )
            except _ObservedCheckpointCommitOutcomeUncertain as exc:
                committed = await self._read_committed_observed_checkpoint(exc.probe)
                if committed is not None:
                    return committed
                # A pre-commit/ACK-unapplied failure is safe to retry because the
                # same operation id, journal result hash, and command generation
                # are revalidated under the canonical graph locks.
                try:
                    return await self._checkpoint_observed_once(
                        command_id=command_id,
                        operation_id=operation_id,
                        runtime=runtime,
                    )
                except _ObservedCheckpointCommitOutcomeUncertain as retry_exc:
                    committed = await self._read_committed_observed_checkpoint(retry_exc.probe)
                    if committed is not None:
                        return committed
                raise ValueError("HOLDOUT_FINALIZE_EXECUTION_COMMIT_OUTCOME_UNKNOWN") from None
            except ValueError:
                raise
            except SQLAlchemyError:
                raise ValueError("HOLDOUT_FINALIZE_PERSISTENCE_FAILED") from None

    async def checkpoint_execution_receipt(
        self,
        *,
        command_id: str,
        operation_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token: str,
        lease_generation: int,
    ) -> CheckpointedHoldoutEvidence:
        """Checkpoint a safe evaluator receipt under the still-live claim lease."""

        token_hash = _lease_token_hash(lease_token)
        _require_generation(lease_generation)
        async with _claim_lock(command_id):
            try:
                return await self._checkpoint_execution_once(
                    command_id=command_id,
                    operation_id=operation_id,
                    runtime=runtime,
                    lease_token_hash=token_hash,
                    lease_generation=lease_generation,
                    recovery=False,
                )
            except _ObservedCheckpointCommitOutcomeUncertain as exc:
                committed = await self._read_committed_observed_checkpoint(exc.probe)
                if committed is not None:
                    return committed
                await self._fence_unknown(
                    command_id=command_id,
                    runtime=runtime,
                    action="CHECKPOINT_UNKNOWN",
                    reason_code="HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN",
                )
                raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN") from None
            except ValueError as exc:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="CHECKPOINT_REJECTED",
                    reason_code=_safe_reason_code(exc),
                )
                raise
            except SQLAlchemyError:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="CHECKPOINT_REJECTED",
                    reason_code="HOLDOUT_FINALIZE_PERSISTENCE_FAILED",
                )
                raise ValueError("HOLDOUT_FINALIZE_PERSISTENCE_FAILED") from None

    async def finalize_claimed_evaluation(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token: str,
        lease_generation: int,
    ) -> FinalizedHoldoutEvaluation:
        """Evaluate gates and close command/evaluation/epoch in one transaction."""

        async with _claim_lock(command_id):
            try:
                token_hash = _lease_token_hash(lease_token)
                _require_generation(lease_generation)
                return await self._finalize_once(
                    command_id=command_id,
                    runtime=runtime,
                    lease_token_hash=token_hash,
                    lease_generation=lease_generation,
                    reconcile=False,
                )
            except _FinalizeCommitOutcomeUncertain as exc:
                committed = await self._read_committed_finalization(exc.probe)
                if committed is not None:
                    return committed
                await self._fence_unknown(
                    command_id=command_id,
                    runtime=runtime,
                    action="FINALIZE_UNKNOWN",
                    reason_code="HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN",
                )
                raise ValueError("HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN") from None
            except ValueError as exc:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="FINALIZE_REJECTED",
                    reason_code=_safe_reason_code(exc),
                )
                raise
            except SQLAlchemyError:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="FINALIZE_REJECTED",
                    reason_code="HOLDOUT_FINALIZE_PERSISTENCE_FAILED",
                )
                raise ValueError("HOLDOUT_FINALIZE_PERSISTENCE_FAILED") from None

    async def reconcile_checkpointed_evaluation(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> FinalizedHoldoutEvaluation:
        """Finalize only an existing checkpoint after the lease was fenced unknown."""

        async with _claim_lock(command_id):
            try:
                return await self._finalize_once(
                    command_id=command_id,
                    runtime=runtime,
                    lease_token_hash=None,
                    lease_generation=None,
                    reconcile=True,
                )
            except _FinalizeCommitOutcomeUncertain as exc:
                committed = await self._read_committed_finalization(exc.probe)
                if committed is not None:
                    return committed
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="RECONCILE_REJECTED",
                    reason_code="HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN",
                )
                raise ValueError("HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN") from None
            except ValueError as exc:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="RECONCILE_REJECTED",
                    reason_code=_safe_reason_code(exc),
                )
                raise
            except SQLAlchemyError:
                await self._record_rejection(
                    command_id=command_id,
                    runtime=runtime,
                    action="RECONCILE_REJECTED",
                    reason_code="HOLDOUT_FINALIZE_PERSISTENCE_FAILED",
                )
                raise ValueError("HOLDOUT_FINALIZE_PERSISTENCE_FAILED") from None

    async def _checkpoint_once(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token: str,
        lease_generation: int,
        measurements: dict[str, Any],
    ) -> CheckpointedHoldoutEvidence:
        token_hash = _lease_token_hash(lease_token)
        _require_generation(lease_generation)
        async with database.async_session_maker() as session:
            try:
                graph = await self._claims._lock_claim_graph(session, command_id=command_id)
                now = await database_utc_now(session)
                _require_live_lease(
                    graph.command,
                    runtime=runtime,
                    lease_token_hash=token_hash,
                    lease_generation=lease_generation,
                    now=now,
                )
                await _validate_static_locked_authority(session, graph, runtime=runtime)
                authorization, evaluation, claim_audit = await _load_started_authority(
                    session, graph
                )
                binding = await _load_binding(session, command_id=command_id)
                _require_started_graph(
                    graph,
                    authorization=authorization,
                    evaluation=evaluation,
                    claim_audit=claim_audit,
                    binding=binding,
                )
                assert authorization is not None
                assert evaluation is not None
                assert claim_audit is not None
                payload = _evidence_payload(
                    graph.command,
                    authorization=authorization,
                    measurements=measurements,
                )
                retained = canonical_json(payload).encode("utf-8")
                if len(retained) > _MAX_EVIDENCE_BYTES:
                    raise ValueError("HOLDOUT_FINALIZE_ARTIFACT_SIZE_EXCEEDED")
                digest = sha256(retained).hexdigest()
                if binding is not None:
                    receipt = await _require_checkpoint_binding(
                        session,
                        graph=graph,
                        authorization=authorization,
                        evaluation=evaluation,
                        claim_audit=claim_audit,
                        binding=binding,
                    )
                    artifact_content = await session.get(
                        ResearchArtifactContent,
                        receipt.artifact_id,
                        with_for_update=True,
                    )
                    if (
                        artifact_content is None
                        or receipt.artifact_hash != digest
                        or bytes(artifact_content.content) != retained
                    ):
                        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_CONFLICT")
                    await session.rollback()
                    return receipt
                if evaluation.returns_artifact_id is not None:
                    raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_CONFLICT")

                artifact = ResearchArtifact(
                    kind=_EVIDENCE_KIND,
                    content_hash=digest,
                    storage_uri=f"controlled://sealed-holdout-evidence/{digest}",
                    size_bytes=len(retained),
                    media_type="application/json",
                    schema_version=_EVIDENCE_SCHEMA_VERSION,
                    producer_identity=runtime.evaluator_identity,
                    container_image_digest=runtime.evaluator_image_digest,
                    created_at=now,
                )
                session.add(artifact)
                await session.flush()
                session.add(
                    ResearchArtifactContent(
                        artifact_id=artifact.id,
                        content=retained,
                        created_at=now,
                    )
                )
                authority_hash = _authority_binding_hash(
                    graph.command,
                    artifact=artifact,
                    claim_audit=claim_audit,
                    lease_expires_at=_required_time(graph.command.lease_expires_at),
                )
                binding = ResearchHoldoutArtifactBinding(
                    user_id=graph.command.user_id,
                    run_id=graph.command.run_id,
                    command_id=graph.command.id,
                    authorization_id=authorization.id,
                    evaluation_id=evaluation.id,
                    experiment_epoch_id=graph.command.experiment_epoch_id,
                    candidate_id=graph.command.candidate_id,
                    dataset_snapshot_id=graph.command.dataset_snapshot_id,
                    artifact_id=artifact.id,
                    claim_access_audit_id=claim_audit.id,
                    request_hash=graph.command.request_hash,
                    lease_owner=runtime.worker_identity,
                    lease_generation=lease_generation,
                    lease_expires_at=_required_time(graph.command.lease_expires_at),
                    binding_schema_version=_BINDING_SCHEMA_VERSION,
                    authority_binding_hash=authority_hash,
                    created_at=now,
                )
                evaluation.returns_artifact_id = artifact.id
                session.add(binding)
                checkpoint_audit = _accepted_access_audit(
                    graph,
                    runtime=runtime,
                    action="CHECKPOINT_RECORDED",
                    reason_code="HOLDOUT_FINALIZE_CHECKPOINT_RECORDED",
                    generation=lease_generation,
                    occurred_at=now,
                )
                session.add(checkpoint_audit)
                await session.flush()
                # Artifact bytes, immutable binding, evaluation pointer, and
                # accepted audit are still provisional until the same live
                # command lease passes a second database-time CAS fence.
                await _second_authority_fence(
                    session,
                    graph.command,
                    runtime=runtime,
                    lease_token_hash=token_hash,
                    lease_generation=lease_generation,
                    reconcile=False,
                )
                receipt = CheckpointedHoldoutEvidence(
                    command_id=graph.command.id,
                    evaluation_id=evaluation.id,
                    artifact_id=artifact.id,
                    artifact_hash=digest,
                    authority_binding_hash=authority_hash,
                    lease_generation=lease_generation,
                )
                probe = _CheckpointProbe(
                    receipt=receipt,
                    retained_content=retained,
                    runtime=runtime,
                    lease_token_hash=token_hash,
                )
                try:
                    await session.commit()
                except Exception as exc:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    raise _CheckpointCommitOutcomeUncertain(probe) from exc
                return receipt
            except _CheckpointCommitOutcomeUncertain:
                raise
            except Exception:
                await session.rollback()
                raise

    async def _checkpoint_observed_once(
        self,
        *,
        command_id: str,
        operation_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
    ) -> CheckpointedHoldoutEvidence:
        return await self._checkpoint_execution_once(
            command_id=command_id,
            operation_id=operation_id,
            runtime=runtime,
            lease_token_hash=None,
            lease_generation=None,
            recovery=True,
        )

    async def _checkpoint_execution_once(
        self,
        *,
        command_id: str,
        operation_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token_hash: str | None,
        lease_generation: int | None,
        recovery: bool,
    ) -> CheckpointedHoldoutEvidence:
        """Persist only an opaque external-artifact receipt and safe gate result."""

        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
        async with database.async_session_maker() as session:
            try:
                graph = await self._claims._lock_claim_graph(session, command_id=command_id)
                await _validate_static_locked_authority(session, graph, runtime=runtime)
                authorization, evaluation, claim_audit = await _load_started_authority(
                    session, graph
                )
                binding = await _load_binding(session, command_id=command_id)
                _require_started_graph(
                    graph,
                    authorization=authorization,
                    evaluation=evaluation,
                    claim_audit=claim_audit,
                    binding=binding,
                )
                if authorization is None or evaluation is None or claim_audit is None:
                    raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")

                execution, execution_result = await _require_observed_execution(
                    session,
                    command=graph.command,
                    operation_id=operation_id,
                    expected_owner=claim_audit.actor_identity,
                    allowed_states=("OBSERVED",),
                )
                terminal_receipt = execution_result.snapshot["terminal_receipt"]
                if not isinstance(terminal_receipt, dict):
                    raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
                artifact_receipt = terminal_receipt.get("artifact_receipt")
                if not isinstance(artifact_receipt, dict):
                    raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")

                if binding is not None:
                    receipt = await _require_checkpoint_binding(
                        session,
                        graph=graph,
                        authorization=authorization,
                        evaluation=evaluation,
                        claim_audit=claim_audit,
                        binding=binding,
                    )
                    artifact = await session.get(
                        ResearchArtifact, receipt.artifact_id, with_for_update=True
                    )
                    if artifact is None or not _artifact_matches_receipt(
                        artifact,
                        artifact_receipt=artifact_receipt,
                        command=graph.command,
                    ):
                        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
                    if recovery:
                        if (
                            graph.command.status != "RECONCILING"
                            or graph.command.error_code != "HOLDOUT_EXECUTION_OBSERVED_RECOVERY"
                        ):
                            raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
                    else:
                        assert lease_token_hash is not None
                        assert lease_generation is not None
                        now = await database_utc_now(session)
                        _require_live_lease(
                            graph.command,
                            runtime=runtime,
                            lease_token_hash=lease_token_hash,
                            lease_generation=lease_generation,
                            now=now,
                        )
                    await session.rollback()
                    return receipt

                now = await database_utc_now(session)
                if recovery:
                    original_owner, original_expiry = _require_expired_observed_lease(
                        graph.command,
                        execution=execution,
                        now=now,
                    )
                else:
                    if lease_token_hash is None or lease_generation is None:
                        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
                    _require_live_lease(
                        graph.command,
                        runtime=runtime,
                        lease_token_hash=lease_token_hash,
                        lease_generation=lease_generation,
                        now=now,
                    )
                    original_owner = _required_identity(execution.lease_owner)
                    original_expiry = _required_time(graph.command.lease_expires_at)
                if evaluation.returns_artifact_id is not None:
                    raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")

                digest = _required_hash(artifact_receipt.get("artifact_hash"))
                receipt_id = _required_identity(artifact_receipt.get("receipt_id"))
                size_bytes = artifact_receipt.get("artifact_size_bytes")
                if type(size_bytes) is not int or size_bytes < 1:
                    raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
                generation = execution.lease_generation

                artifact = ResearchArtifact(
                    kind=_RECEIPT_KIND,
                    content_hash=digest,
                    storage_uri=f"controlled://sealed-holdout-artifact-receipt/{receipt_id}",
                    size_bytes=size_bytes,
                    media_type=_RECEIPT_MEDIA_TYPE,
                    schema_version=_RECEIPT_SCHEMA_VERSION,
                    producer_identity=runtime.evaluator_identity,
                    container_image_digest=runtime.evaluator_image_digest,
                    created_at=now,
                )
                session.add(artifact)
                await session.flush()
                authority_hash = _authority_binding_hash(
                    graph.command,
                    artifact=artifact,
                    claim_audit=claim_audit,
                    lease_owner=original_owner,
                    lease_generation=generation,
                    lease_expires_at=original_expiry,
                )
                binding = ResearchHoldoutArtifactBinding(
                    user_id=graph.command.user_id,
                    run_id=graph.command.run_id,
                    command_id=graph.command.id,
                    authorization_id=authorization.id,
                    evaluation_id=evaluation.id,
                    experiment_epoch_id=graph.command.experiment_epoch_id,
                    candidate_id=graph.command.candidate_id,
                    dataset_snapshot_id=graph.command.dataset_snapshot_id,
                    artifact_id=artifact.id,
                    claim_access_audit_id=claim_audit.id,
                    request_hash=graph.command.request_hash,
                    lease_owner=original_owner,
                    lease_generation=generation,
                    lease_expires_at=original_expiry,
                    binding_schema_version=_BINDING_SCHEMA_VERSION,
                    authority_binding_hash=authority_hash,
                    created_at=now,
                )
                evaluation.returns_artifact_id = artifact.id
                session.add(binding)
                if recovery:
                    session.add(
                        _accepted_access_audit(
                            graph,
                            runtime=runtime,
                            action="EXECUTION_OBSERVED_RECONCILING",
                            reason_code="HOLDOUT_EXECUTION_OBSERVED_RECOVERY",
                            generation=generation,
                            occurred_at=now,
                        )
                    )
                session.add(
                    _accepted_access_audit(
                        graph,
                        runtime=runtime,
                        action="CHECKPOINT_RECORDED",
                        reason_code="HOLDOUT_FINALIZE_CHECKPOINT_RECORDED",
                        generation=generation,
                        occurred_at=now,
                    )
                )
                await session.flush()
                if recovery:
                    await _fence_observed_recovery(
                        session,
                        graph.command,
                        execution=execution,
                        original_owner=original_owner,
                        original_expiry=original_expiry,
                        recovered_at=now,
                    )
                else:
                    await _second_authority_fence(
                        session,
                        graph.command,
                        runtime=runtime,
                        lease_token_hash=lease_token_hash,
                        lease_generation=generation,
                        reconcile=False,
                    )
                receipt = CheckpointedHoldoutEvidence(
                    command_id=graph.command.id,
                    evaluation_id=evaluation.id,
                    artifact_id=artifact.id,
                    artifact_hash=digest,
                    authority_binding_hash=authority_hash,
                    lease_generation=generation,
                )
                probe = _ObservedCheckpointProbe(
                    receipt=receipt,
                    operation_id=operation_id,
                    result_hash=_required_hash(execution.result_hash),
                    runtime=runtime,
                    lease_token_hash=lease_token_hash,
                    recovery=recovery,
                )
                try:
                    await session.commit()
                except Exception as exc:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    raise _ObservedCheckpointCommitOutcomeUncertain(probe) from exc
                return receipt
            except _ObservedCheckpointCommitOutcomeUncertain:
                raise
            except Exception:
                await session.rollback()
                raise

    async def _finalize_once(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        lease_token_hash: str | None,
        lease_generation: int | None,
        reconcile: bool,
    ) -> FinalizedHoldoutEvaluation:
        terminal_action = "RECONCILE_COMPLETED" if reconcile else "FINALIZE_COMPLETED"
        async with database.async_session_maker() as session:
            try:
                graph = await self._claims._lock_claim_graph(session, command_id=command_id)
                await _validate_static_locked_authority(session, graph, runtime=runtime)
                terminal = await self._terminal_result_if_exact(
                    session,
                    graph=graph,
                    runtime=runtime,
                    requested_generation=lease_generation,
                    expected_action=terminal_action,
                )
                if terminal is not None:
                    await session.rollback()
                    return terminal

                authorization, evaluation, claim_audit = await _load_started_authority(
                    session, graph
                )
                binding = await _load_binding(session, command_id=command_id)
                _require_started_graph(
                    graph,
                    authorization=authorization,
                    evaluation=evaluation,
                    claim_audit=claim_audit,
                    binding=binding,
                )
                if binding is None or authorization is None or evaluation is None:
                    raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_REQUIRED")
                checkpoint = await _require_checkpoint_binding(
                    session,
                    graph=graph,
                    authorization=authorization,
                    evaluation=evaluation,
                    claim_audit=claim_audit,
                    binding=binding,
                )
                expected_reconciliation_error_code: str | None = None
                if reconcile:
                    expected_reconciliation_error_code = _require_reconciling_command(
                        graph.command,
                        binding=binding,
                    )
                    generation = binding.lease_generation
                else:
                    assert lease_token_hash is not None
                    assert lease_generation is not None
                    now = await database_utc_now(session)
                    _require_live_lease(
                        graph.command,
                        runtime=runtime,
                        lease_token_hash=lease_token_hash,
                        lease_generation=lease_generation,
                        now=now,
                    )
                    if (
                        binding.lease_generation != lease_generation
                        or binding.lease_owner != runtime.worker_identity
                    ):
                        raise ValueError("HOLDOUT_FINALIZE_LEASE_STALE")
                    generation = lease_generation

                policy = resolve_server_policy(graph.command.policy_version)
                artifact = await session.get(
                    ResearchArtifact,
                    checkpoint.artifact_id,
                    with_for_update=True,
                )
                if artifact is not None and artifact.kind == _RECEIPT_KIND:
                    execution = await session.scalar(
                        select(ResearchHoldoutExecution)
                        .where(ResearchHoldoutExecution.command_id == graph.command.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    if execution is None:
                        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
                    _execution, safe_result = await _require_observed_execution(
                        session,
                        command=graph.command,
                        operation_id=execution.operation_id,
                        expected_owner=binding.lease_owner,
                        allowed_states=("OBSERVED",),
                    )
                    promotion = await self._promotion.record_evaluator_receipt_in_session(
                        session,
                        candidate_id=graph.command.candidate_id,
                        evaluation_id=evaluation.id,
                        policy=policy,
                        result=safe_result,
                        strict_freeze_fingerprint=graph.command.freeze_receipt_fingerprint,
                    )
                else:
                    if not self._allow_inline_test_measurements:
                        raise ValueError("HOLDOUT_FINALIZE_INLINE_MEASUREMENTS_DISABLED")
                    promotion = await self._promotion.evaluate_command_and_record_in_session(
                        session,
                        authority=CommandPromotionAuthority(
                            command_id=graph.command.id,
                            candidate_id=graph.command.candidate_id,
                            evaluation_id=evaluation.id,
                            actor_identity=runtime.worker_identity,
                            evaluator_identity=runtime.evaluator_identity,
                            evaluator_version=runtime.evaluator_image_digest,
                            lease_generation=generation,
                            mode=(
                                CommandPromotionMode.RECONCILING
                                if reconcile
                                else CommandPromotionMode.ACTIVE
                            ),
                            lease_token_hash=lease_token_hash,
                        ),
                        policy=policy,
                    )
                _require_complete_promotion(promotion, command=graph.command)
                await session.flush()
                await _second_authority_fence(
                    session,
                    graph.command,
                    runtime=runtime,
                    lease_token_hash=lease_token_hash,
                    lease_generation=generation,
                    reconcile=reconcile,
                    expected_reconciliation_error_code=expected_reconciliation_error_code,
                )
                now = await database_utc_now(session)
                receipt = _apply_terminal_graph(
                    graph,
                    evaluation=evaluation,
                    promotion=promotion,
                    completed_at=now,
                )
                final_audit = _accepted_access_audit(
                    graph,
                    runtime=runtime,
                    action=terminal_action,
                    reason_code=(
                        "HOLDOUT_FINALIZE_RECONCILED" if reconcile else "HOLDOUT_FINALIZE_COMPLETED"
                    ),
                    generation=generation,
                    occurred_at=now,
                )
                session.add(final_audit)
                await session.flush()
                probe = _FinalizeProbe(
                    receipt=receipt,
                    runtime=runtime,
                    lease_generation=generation,
                    terminal_action=terminal_action,
                )
                try:
                    await session.commit()
                except Exception as exc:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    raise _FinalizeCommitOutcomeUncertain(probe) from exc
                return receipt
            except _FinalizeCommitOutcomeUncertain:
                raise
            except Exception:
                await session.rollback()
                raise

    async def _terminal_result_if_exact(
        self,
        session: AsyncSession,
        *,
        graph: Any,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        requested_generation: int | None,
        expected_action: str,
    ) -> FinalizedHoldoutEvaluation | None:
        command = graph.command
        if command.status != "SUCCEEDED":
            return None
        if (
            command.stage != "HOLDOUT_PENDING"
            or command.error_code is not None
            or any(
                value is not None
                for value in (
                    command.lease_owner,
                    command.lease_token_hash,
                    command.lease_expires_at,
                    command.lease_heartbeat_at,
                )
            )
        ):
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        if requested_generation is not None and requested_generation != command.lease_generation:
            raise ValueError("HOLDOUT_FINALIZE_LEASE_STALE")
        authorization, evaluation, claim_audit = await _load_started_authority(session, graph)
        binding = await _load_binding(session, command_id=command.id)
        if binding is None or authorization is None or evaluation is None or claim_audit is None:
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        if binding.lease_generation != command.lease_generation:
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        if (
            expected_action == "FINALIZE_COMPLETED"
            and binding.lease_owner != runtime.worker_identity
        ):
            raise ValueError("HOLDOUT_FINALIZE_RUNTIME_IDENTITY_MISMATCH")
        if expected_action not in {"FINALIZE_COMPLETED", "RECONCILE_COMPLETED"}:
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        await _require_checkpoint_binding(
            session,
            graph=graph,
            authorization=authorization,
            evaluation=evaluation,
            claim_audit=claim_audit,
            binding=binding,
        )
        gate_inputs = dict(evaluation.gate_inputs or {})
        input_hash = gate_inputs.get("input_evidence_hash")
        if not _is_sha256(input_hash):
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        promotion = await self._promotion.read_result_in_session(
            session,
            candidate_id=command.candidate_id,
            evaluation_id=evaluation.id,
            policy_version=command.policy_version,
            input_evidence_hash=input_hash,
        )
        _require_complete_promotion(promotion, command=command)
        terminal_audits = tuple(
            (
                await session.scalars(
                    select(ResearchHoldoutAccessAudit)
                    .where(
                        ResearchHoldoutAccessAudit.command_id == command.id,
                        ResearchHoldoutAccessAudit.lease_generation == command.lease_generation,
                        ResearchHoldoutAccessAudit.action.in_(
                            ("FINALIZE_COMPLETED", "RECONCILE_COMPLETED")
                        ),
                    )
                    .with_for_update()
                )
            ).all()
        )
        if len(terminal_audits) != 1:
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        terminal_audit = terminal_audits[0]
        expected_reason = {
            "FINALIZE_COMPLETED": "HOLDOUT_FINALIZE_COMPLETED",
            "RECONCILE_COMPLETED": "HOLDOUT_FINALIZE_RECONCILED",
        }.get(terminal_audit.action)
        if (
            terminal_audit.action != expected_action
            or expected_reason is None
            or terminal_audit.actor_identity != runtime.worker_identity
            or terminal_audit.evaluator_version != command.evaluator_version
            or terminal_audit.requested_command_id != command.id
            or terminal_audit.result != "ACCEPTED"
            or terminal_audit.reason_code != expected_reason
            or terminal_audit.command_id != command.id
            or terminal_audit.authorization_id != authorization.id
            or terminal_audit.evaluation_id != evaluation.id
            or terminal_audit.experiment_epoch_id != command.experiment_epoch_id
            or terminal_audit.candidate_id != command.candidate_id
            or terminal_audit.dataset_snapshot_id != command.dataset_snapshot_id
            or terminal_audit.lease_generation != command.lease_generation
            or terminal_audit.trace_id != command.trace_id
            or evaluation.completed_at is None
            or _optional_time(terminal_audit.created_at) != _optional_time(evaluation.completed_at)
            or graph.epoch.closed_at is None
            or _optional_time(graph.epoch.closed_at) != _optional_time(evaluation.completed_at)
        ):
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        receipt = _terminal_receipt(command, evaluation=evaluation, promotion=promotion)
        if receipt.command_status != "SUCCEEDED":
            raise ValueError("HOLDOUT_FINALIZE_TERMINAL_INCONSISTENT")
        return receipt

    async def _read_committed_observed_checkpoint(
        self,
        probe: _ObservedCheckpointProbe,
    ) -> CheckpointedHoldoutEvidence | None:
        try:
            async with database.async_session_maker() as session:
                graph = await self._claims._lock_claim_graph(
                    session,
                    command_id=probe.receipt.command_id,
                )
                await _validate_static_locked_authority(
                    session,
                    graph,
                    runtime=probe.runtime,
                )
                recovery_matches = bool(
                    probe.recovery
                    and graph.command.status == "RECONCILING"
                    and graph.command.error_code == "HOLDOUT_EXECUTION_OBSERVED_RECOVERY"
                    and graph.command.lease_owner is None
                    and graph.command.lease_token_hash is None
                )
                active_matches = bool(
                    not probe.recovery
                    and graph.command.status == "RUNNING"
                    and graph.command.error_code is None
                    and graph.command.lease_owner == probe.runtime.worker_identity
                    and graph.command.lease_token_hash == probe.lease_token_hash
                    and graph.command.lease_generation == probe.receipt.lease_generation
                )
                if not (recovery_matches or active_matches):
                    await session.rollback()
                    return None
                authorization, evaluation, claim_audit = await _load_started_authority(
                    session, graph
                )
                binding = await _load_binding(
                    session,
                    command_id=probe.receipt.command_id,
                )
                if binding is None or authorization is None or evaluation is None:
                    await session.rollback()
                    return None
                execution, _result = await _require_observed_execution(
                    session,
                    command=graph.command,
                    operation_id=probe.operation_id,
                    expected_owner=_required_identity(authorization.issued_by),
                    allowed_states=("OBSERVED",),
                )
                receipt = await _require_checkpoint_binding(
                    session,
                    graph=graph,
                    authorization=authorization,
                    evaluation=evaluation,
                    claim_audit=claim_audit,
                    binding=binding,
                )
                exact = receipt == probe.receipt and execution.result_hash == probe.result_hash
                await session.rollback()
                return receipt if exact else None
        except Exception:
            return None

    async def _read_committed_checkpoint(
        self,
        probe: _CheckpointProbe,
    ) -> CheckpointedHoldoutEvidence | None:
        try:
            async with database.async_session_maker() as session:
                graph = await self._claims._lock_claim_graph(
                    session,
                    command_id=probe.receipt.command_id,
                )
                await _validate_static_locked_authority(
                    session,
                    graph,
                    runtime=probe.runtime,
                )
                if (
                    graph.command.stage != "HOLDOUT_PENDING"
                    or graph.command.lease_generation != probe.receipt.lease_generation
                    or graph.command.evaluator_identity != probe.runtime.evaluator_identity
                    or graph.command.evaluator_version != probe.runtime.evaluator_image_digest
                ):
                    await session.rollback()
                    return None
                active_matches = bool(
                    graph.command.status == "RUNNING"
                    and graph.command.error_code is None
                    and graph.command.lease_owner == probe.runtime.worker_identity
                    and graph.command.lease_token_hash == probe.lease_token_hash
                    and graph.command.lease_expires_at is not None
                    and graph.command.lease_heartbeat_at is not None
                )
                reconciling_matches = bool(
                    graph.command.status == "RECONCILING"
                    and bool(graph.command.error_code)
                    and graph.command.lease_owner is None
                    and graph.command.lease_token_hash is None
                    and graph.command.lease_expires_at is None
                    and graph.command.lease_heartbeat_at is None
                )
                succeeded_matches = bool(
                    graph.command.status == "SUCCEEDED"
                    and graph.command.error_code is None
                    and graph.command.lease_owner is None
                    and graph.command.lease_token_hash is None
                    and graph.command.lease_expires_at is None
                    and graph.command.lease_heartbeat_at is None
                )
                if not (active_matches or reconciling_matches or succeeded_matches):
                    await session.rollback()
                    return None
                authorization, evaluation, claim_audit = await _load_started_authority(
                    session, graph
                )
                binding = await _load_binding(
                    session,
                    command_id=probe.receipt.command_id,
                )
                if binding is None or authorization is None or evaluation is None:
                    await session.rollback()
                    return None
                receipt = await _require_checkpoint_binding(
                    session,
                    graph=graph,
                    authorization=authorization,
                    evaluation=evaluation,
                    claim_audit=claim_audit,
                    binding=binding,
                )
                retained = await session.get(
                    ResearchArtifactContent,
                    receipt.artifact_id,
                    with_for_update=True,
                )
                exact = (
                    receipt == probe.receipt
                    and retained is not None
                    and bytes(retained.content) == probe.retained_content
                )
                await session.rollback()
                return receipt if exact else None
        except Exception:
            return None

    async def _read_committed_finalization(
        self,
        probe: _FinalizeProbe,
    ) -> FinalizedHoldoutEvaluation | None:
        try:
            async with database.async_session_maker() as session:
                graph = await self._claims._lock_claim_graph(
                    session,
                    command_id=probe.receipt.command_id,
                )
                await _validate_static_locked_authority(
                    session,
                    graph,
                    runtime=probe.runtime,
                )
                receipt = await self._terminal_result_if_exact(
                    session,
                    graph=graph,
                    runtime=probe.runtime,
                    requested_generation=probe.lease_generation,
                    expected_action=probe.terminal_action,
                )
                await session.rollback()
                return receipt if receipt == probe.receipt else None
        except Exception:
            return None

    async def _record_rejection(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        action: str,
        reason_code: str,
    ) -> None:
        try:
            async with database.async_session_maker() as session:
                now = await database_utc_now(session)
                session.add(
                    _non_authoritative_access_audit(
                        command_id=command_id,
                        runtime=runtime,
                        action=action,
                        result="REJECTED",
                        reason_code=reason_code,
                        occurred_at=now,
                    )
                )
                await session.commit()
        except Exception:
            raise ValueError("HOLDOUT_FINALIZE_AUDIT_UNAVAILABLE") from None

    async def _fence_unknown(
        self,
        *,
        command_id: str,
        runtime: HoldoutEvaluatorRuntimeIdentity,
        action: str,
        reason_code: str,
    ) -> None:
        try:
            async with database.async_session_maker() as session:
                command = await session.scalar(
                    select(ResearchHoldoutEvaluationCommand)
                    .where(ResearchHoldoutEvaluationCommand.id == command_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                now = await database_utc_now(session)
                if command is not None and command.status in {"RUNNING", "RECONCILING"}:
                    command.status = "RECONCILING"
                    command.error_code = reason_code
                    command.lease_owner = None
                    command.lease_token_hash = None
                    command.lease_expires_at = None
                    command.lease_heartbeat_at = None
                    command.updated_at = now
                session.add(
                    _non_authoritative_access_audit(
                        command_id=command_id,
                        runtime=runtime,
                        action=action,
                        result="UNKNOWN",
                        reason_code=reason_code,
                        occurred_at=now,
                    )
                )
                await session.commit()
        except Exception:
            raise ValueError("HOLDOUT_FINALIZE_AUDIT_UNAVAILABLE") from None


def _canonical_measurements(measurements: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(measurements, Mapping):
        raise ValueError("HOLDOUT_FINALIZE_MEASUREMENTS_INVALID")
    copied = dict(measurements)
    if not set(copied).issubset(_MEASUREMENT_KEYS):
        raise ValueError("HOLDOUT_FINALIZE_MEASUREMENTS_INVALID")
    try:
        normalized = json.loads(canonical_json(copied))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("HOLDOUT_FINALIZE_MEASUREMENTS_INVALID") from exc
    if not isinstance(normalized, dict):
        raise ValueError("HOLDOUT_FINALIZE_MEASUREMENTS_INVALID")
    return normalized


def _evidence_payload(
    command: ResearchHoldoutEvaluationCommand,
    *,
    authorization: ResearchHoldoutAuthorization,
    measurements: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": _EVIDENCE_SCHEMA_VERSION,
        "authorization_id": authorization.id,
        "candidate_id": command.candidate_id,
        "candidate_hash": command.candidate_hash,
        "experiment_epoch_id": command.experiment_epoch_id,
        "dataset_snapshot_id": command.dataset_snapshot_id,
        "sealed_dataset_hash": command.sealed_dataset_hash,
        "policy_version": command.policy_version,
        "evaluator_identity": command.evaluator_identity,
        "evaluator_version": command.evaluator_version,
        "measurements": measurements,
    }


async def _load_binding(
    session: AsyncSession,
    *,
    command_id: str,
) -> ResearchHoldoutArtifactBinding | None:
    return await session.scalar(
        select(ResearchHoldoutArtifactBinding)
        .where(ResearchHoldoutArtifactBinding.command_id == command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _require_observed_execution(
    session: AsyncSession,
    *,
    command: ResearchHoldoutEvaluationCommand,
    operation_id: str,
    expected_owner: str,
    allowed_states: tuple[str, ...],
) -> tuple[ResearchHoldoutExecution, HoldoutExecutionResult]:
    execution = await session.scalar(
        select(ResearchHoldoutExecution)
        .where(
            ResearchHoldoutExecution.command_id == command.id,
            ResearchHoldoutExecution.operation_id == operation_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    try:
        if execution is None or execution.state not in allowed_states:
            raise ValueError
        expected_command = {
            "schema_version": "holdout-execution-command-v2",
            "operation_id": operation_id,
            "command_id": command.id,
            "evaluation_id": command.evaluation_id,
            "authorization_id": command.authorization_id,
            "experiment_epoch_id": command.experiment_epoch_id,
            "request_hash": command.request_hash,
            "candidate_id": command.candidate_id,
            "candidate_hash": command.candidate_hash,
            "dataset_snapshot_id": command.dataset_snapshot_id,
            "sealed_dataset_hash": command.sealed_dataset_hash,
            "sealed_dataset_identity_hash": command.sealed_dataset_identity_hash,
            "freeze_receipt_fingerprint": command.freeze_receipt_fingerprint,
            "capability_evidence_hash": command.capability_evidence_hash,
            "policy_version": command.policy_version,
            "promotion_policy_hash": promotion_policy_material_hash(
                resolve_server_policy(command.policy_version)
            ),
            "evaluator_identity": command.evaluator_identity,
            "evaluator_image_digest": command.evaluator_version,
            "lease_generation": command.lease_generation,
        }
        wire_command = HoldoutExecutionCommand.from_mapping(expected_command)
        if (
            execution.user_id != command.user_id
            or execution.command_id != command.id
            or execution.evaluation_id != command.evaluation_id
            or execution.command_hash != wire_command.command_hash
            or execution.command_json != wire_command.snapshot
            or execution.lease_owner != expected_owner
            or execution.lease_generation != command.lease_generation
            or execution.result_json is None
            or not _is_sha256(execution.result_hash)
            or execution.error_code is not None
            or execution.prepared_at is None
            or execution.lease_expires_at is None
            or execution.dispatched_at is None
            or execution.observed_at is None
            or (execution.state == "OBSERVED" and execution.settled_at is not None)
            or (execution.state == "SETTLED" and execution.settled_at is None)
        ):
            raise ValueError
        result = HoldoutExecutionResult.from_mapping(
            dict(execution.result_json),
            command=wire_command,
        )
        if (
            sha256(result.payload).hexdigest() != execution.result_hash
            or result.snapshot["status"] != "SUCCEEDED"
            or result.snapshot["error_code"] is not None
        ):
            raise ValueError
        return execution, result
    except Exception:
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID") from None


def _require_expired_observed_lease(
    command: ResearchHoldoutEvaluationCommand,
    *,
    execution: ResearchHoldoutExecution,
    now: datetime,
) -> tuple[str, datetime]:
    original_owner = _required_identity(execution.lease_owner)
    journal_expiry = _required_time(execution.lease_expires_at)
    if command.stage != "HOLDOUT_PENDING" or command.lease_generation != execution.lease_generation:
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
    if command.status == "RECONCILING":
        if (
            command.error_code != "HOLDOUT_EXECUTION_OUTCOME_UNKNOWN"
            or command.lease_owner is not None
            or command.lease_token_hash is not None
            or command.lease_expires_at is not None
            or command.lease_heartbeat_at is not None
        ):
            raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
        return original_owner, journal_expiry
    if (
        command.status != "RUNNING"
        or command.error_code is not None
        or command.lease_owner != original_owner
        or command.lease_token_hash is None
        or command.lease_heartbeat_at is None
        or command.lease_expires_at is None
    ):
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
    command_expiry = _required_time(command.lease_expires_at)
    if command_expiry < journal_expiry or journal_expiry > now or command_expiry > now:
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_LEASE_ACTIVE")
    return original_owner, command_expiry


async def _fence_observed_recovery(
    session: AsyncSession,
    command: ResearchHoldoutEvaluationCommand,
    *,
    execution: ResearchHoldoutExecution,
    original_owner: str,
    original_expiry: datetime,
    recovered_at: datetime,
) -> None:
    common_conditions = [
        ResearchHoldoutEvaluationCommand.id == command.id,
        ResearchHoldoutEvaluationCommand.stage == "HOLDOUT_PENDING",
        ResearchHoldoutEvaluationCommand.evaluator_identity
        == execution.command_json["evaluator_identity"],
        ResearchHoldoutEvaluationCommand.evaluator_version
        == execution.command_json["evaluator_image_digest"],
        ResearchHoldoutEvaluationCommand.lease_generation == execution.lease_generation,
        ResearchHoldoutEvaluationCommand.attempt_count == execution.lease_generation,
    ]
    if command.status == "RUNNING":
        state_conditions = [
            ResearchHoldoutEvaluationCommand.status == "RUNNING",
            ResearchHoldoutEvaluationCommand.error_code.is_(None),
            ResearchHoldoutEvaluationCommand.lease_owner == original_owner,
            ResearchHoldoutEvaluationCommand.lease_token_hash == command.lease_token_hash,
            ResearchHoldoutEvaluationCommand.lease_expires_at == original_expiry,
            ResearchHoldoutEvaluationCommand.lease_expires_at <= DatabaseUtcNow(),
            ResearchHoldoutEvaluationCommand.lease_heartbeat_at == command.lease_heartbeat_at,
        ]
    elif command.status == "RECONCILING":
        state_conditions = [
            ResearchHoldoutEvaluationCommand.status == "RECONCILING",
            ResearchHoldoutEvaluationCommand.error_code == "HOLDOUT_EXECUTION_OUTCOME_UNKNOWN",
            ResearchHoldoutEvaluationCommand.lease_owner.is_(None),
            ResearchHoldoutEvaluationCommand.lease_token_hash.is_(None),
            ResearchHoldoutEvaluationCommand.lease_expires_at.is_(None),
            ResearchHoldoutEvaluationCommand.lease_heartbeat_at.is_(None),
        ]
    else:
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
    updated = await session.execute(
        update(ResearchHoldoutEvaluationCommand)
        .where(*common_conditions, *state_conditions)
        .values(
            status="RECONCILING",
            error_code="HOLDOUT_EXECUTION_OBSERVED_RECOVERY",
            lease_owner=None,
            lease_token_hash=None,
            lease_expires_at=None,
            lease_heartbeat_at=None,
            updated_at=recovered_at,
        )
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
    await session.refresh(command)


def _require_started_graph(
    graph: Any,
    *,
    authorization: ResearchHoldoutAuthorization | None,
    evaluation: ResearchEvaluation | None,
    claim_audit: ResearchHoldoutAccessAudit | None,
    binding: ResearchHoldoutArtifactBinding | None,
) -> None:
    command = graph.command
    expected_artifact_id = binding.artifact_id if binding is not None else None
    expected_owner = (
        binding.lease_owner
        if binding is not None
        else (claim_audit.actor_identity if claim_audit is not None else command.lease_owner)
    )
    running_state_valid = bool(
        command.status != "RUNNING"
        or (
            command.error_code is None
            and command.lease_owner is not None
            and command.lease_token_hash is not None
            and command.lease_expires_at is not None
            and command.lease_heartbeat_at is not None
        )
    )
    reconciling_state_valid = bool(
        command.status != "RECONCILING"
        or (
            command.error_code is not None
            and command.lease_owner is None
            and command.lease_token_hash is None
            and command.lease_expires_at is None
            and command.lease_heartbeat_at is None
        )
    )
    started_at = _optional_time(command.started_at)
    issued_at = _optional_time(authorization.issued_at) if authorization is not None else None
    consumed_at = _optional_time(authorization.consumed_at) if authorization is not None else None
    authorization_expires_at = (
        _optional_time(authorization.expires_at) if authorization is not None else None
    )
    evaluation_started_at = (
        _optional_time(evaluation.started_at) if evaluation is not None else None
    )
    disclosed_at = _optional_time(graph.epoch.disclosed_at)
    audit_created_at = _optional_time(claim_audit.created_at) if claim_audit is not None else None
    if (
        authorization is None
        or evaluation is None
        or claim_audit is None
        or command.status not in {"RUNNING", "RECONCILING"}
        or command.stage != "HOLDOUT_PENDING"
        or not running_state_valid
        or not reconciling_state_valid
        or command.lease_generation < 1
        or command.attempt_count != command.lease_generation
        or started_at is None
        or command.authorization_id != authorization.id
        or command.evaluation_id != evaluation.id
        or authorization.status != "CONSUMED"
        or authorization.experiment_epoch_id != command.experiment_epoch_id
        or authorization.candidate_id != command.candidate_id
        or authorization.candidate_hash != command.candidate_hash
        or authorization.dataset_snapshot_id != command.dataset_snapshot_id
        or authorization.policy_version != command.policy_version
        or authorization.evaluator_identity != command.evaluator_identity
        or authorization.capability_profile_id != command.capability_profile_id
        or authorization.capability_profile_version != command.capability_profile_version
        or authorization.capability_evidence_hash != command.capability_evidence_hash
        or authorization.issued_by != expected_owner
        or not _is_sha256(authorization.token_hash)
        or authorization.token_hash == command.lease_token_hash
        or issued_at != started_at
        or consumed_at != started_at
        or authorization_expires_at is None
        or authorization_expires_at <= started_at
        or evaluation.experiment_epoch_id != command.experiment_epoch_id
        or evaluation.candidate_id != command.candidate_id
        or evaluation.dataset_snapshot_id != command.dataset_snapshot_id
        or evaluation.evaluation_type != "SEALED_HOLDOUT"
        or evaluation.evaluator_identity != command.evaluator_identity
        or evaluation.evaluator_version != command.evaluator_version
        or evaluation.authorization_id != authorization.id
        or evaluation.returns_artifact_id != expected_artifact_id
        or (evaluation.metrics or {}) != {}
        or (evaluation.gate_inputs or {}) != {}
        or evaluation.policy_version != command.policy_version
        or evaluation.status != "RUNNING"
        or evaluation_started_at != started_at
        or evaluation.completed_at is not None
        or graph.epoch.status != "DISCLOSED"
        or graph.epoch.selected_candidate_id != command.candidate_id
        or disclosed_at != started_at
        or graph.epoch.closed_at is not None
        or claim_audit.action != "CLAIM_STARTED"
        or claim_audit.result != "ACCEPTED"
        or claim_audit.reason_code != "HOLDOUT_CLAIM_STARTED"
        or claim_audit.actor_identity != expected_owner
        or claim_audit.evaluator_version != command.evaluator_version
        or claim_audit.requested_command_id != command.id
        or claim_audit.command_id != command.id
        or claim_audit.authorization_id != authorization.id
        or claim_audit.evaluation_id != evaluation.id
        or claim_audit.experiment_epoch_id != command.experiment_epoch_id
        or claim_audit.candidate_id != command.candidate_id
        or claim_audit.dataset_snapshot_id != command.dataset_snapshot_id
        or claim_audit.lease_generation != command.lease_generation
        or claim_audit.trace_id != command.trace_id
        or audit_created_at != started_at
    ):
        raise ValueError("HOLDOUT_FINALIZE_AUTHORITY_INCONSISTENT")


async def _require_checkpoint_binding(
    session: AsyncSession,
    *,
    graph: Any,
    authorization: ResearchHoldoutAuthorization,
    evaluation: ResearchEvaluation,
    claim_audit: ResearchHoldoutAccessAudit | None,
    binding: ResearchHoldoutArtifactBinding,
) -> CheckpointedHoldoutEvidence:
    command = graph.command
    if claim_audit is None:
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
    artifact = await session.get(ResearchArtifact, binding.artifact_id, with_for_update=True)
    retained = await session.get(
        ResearchArtifactContent,
        binding.artifact_id,
        with_for_update=True,
    )
    checkpoint_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.action == "CHECKPOINT_RECORDED",
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == binding.lease_generation,
                )
                .with_for_update()
            )
        ).all()
    )
    recovery_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.action == "EXECUTION_OBSERVED_RECONCILING",
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == binding.lease_generation,
                )
                .with_for_update()
            )
        ).all()
    )
    if artifact is None or len(checkpoint_audits) != 1:
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
    expected_hash = _authority_binding_hash(
        command,
        artifact=artifact,
        claim_audit=claim_audit,
        lease_owner=binding.lease_owner,
        lease_generation=binding.lease_generation,
        lease_expires_at=_required_time(binding.lease_expires_at),
    )
    checkpoint_audit = checkpoint_audits[0]
    checkpoint_actor = binding.lease_owner
    if recovery_audits:
        if len(recovery_audits) != 1:
            raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
        recovery_audit = recovery_audits[0]
        if (
            recovery_audit.result != "ACCEPTED"
            or recovery_audit.reason_code != "HOLDOUT_EXECUTION_OBSERVED_RECOVERY"
            or not recovery_audit.actor_identity
            or recovery_audit.evaluator_version != command.evaluator_version
            or recovery_audit.requested_command_id != command.id
            or recovery_audit.command_id != command.id
            or recovery_audit.authorization_id != authorization.id
            or recovery_audit.evaluation_id != evaluation.id
            or recovery_audit.experiment_epoch_id != command.experiment_epoch_id
            or recovery_audit.candidate_id != command.candidate_id
            or recovery_audit.dataset_snapshot_id != command.dataset_snapshot_id
            or recovery_audit.lease_generation != binding.lease_generation
            or recovery_audit.trace_id != command.trace_id
            or _optional_time(recovery_audit.created_at) != _optional_time(binding.created_at)
        ):
            raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
        checkpoint_actor = recovery_audit.actor_identity
    active_lease_matches = bool(
        command.status != "RUNNING" or binding.lease_owner == command.lease_owner
    )
    if (
        binding.user_id != command.user_id
        or binding.run_id != command.run_id
        or binding.command_id != command.id
        or binding.authorization_id != authorization.id
        or binding.evaluation_id != evaluation.id
        or binding.experiment_epoch_id != command.experiment_epoch_id
        or binding.candidate_id != command.candidate_id
        or binding.dataset_snapshot_id != command.dataset_snapshot_id
        or binding.artifact_id != evaluation.returns_artifact_id
        or binding.claim_access_audit_id != claim_audit.id
        or binding.request_hash != command.request_hash
        or binding.lease_generation != command.lease_generation
        or not active_lease_matches
        or binding.binding_schema_version != _BINDING_SCHEMA_VERSION
        or binding.authority_binding_hash != expected_hash
        or checkpoint_audit.result != "ACCEPTED"
        or checkpoint_audit.reason_code != "HOLDOUT_FINALIZE_CHECKPOINT_RECORDED"
        or checkpoint_audit.actor_identity != checkpoint_actor
        or checkpoint_audit.evaluator_version != command.evaluator_version
        or checkpoint_audit.requested_command_id != command.id
        or checkpoint_audit.command_id != command.id
        or checkpoint_audit.authorization_id != authorization.id
        or checkpoint_audit.evaluation_id != evaluation.id
        or checkpoint_audit.experiment_epoch_id != command.experiment_epoch_id
        or checkpoint_audit.candidate_id != command.candidate_id
        or checkpoint_audit.dataset_snapshot_id != command.dataset_snapshot_id
        or checkpoint_audit.lease_generation != binding.lease_generation
        or checkpoint_audit.trace_id != command.trace_id
        or _optional_time(checkpoint_audit.created_at) != _optional_time(binding.created_at)
    ):
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")

    if artifact.kind == _RECEIPT_KIND:
        if retained is not None:
            raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
        execution = await session.scalar(
            select(ResearchHoldoutExecution)
            .where(ResearchHoldoutExecution.command_id == command.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if execution is None:
            raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
        try:
            _execution, result = await _require_observed_execution(
                session,
                command=command,
                operation_id=execution.operation_id,
                expected_owner=binding.lease_owner,
                allowed_states=("OBSERVED", "SETTLED"),
            )
            terminal_receipt = result.snapshot["terminal_receipt"]
            artifact_receipt = terminal_receipt["artifact_receipt"]
        except (KeyError, TypeError, ValueError):
            raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID") from None
        if not _artifact_matches_receipt(
            artifact,
            artifact_receipt=artifact_receipt,
            command=command,
        ):
            raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
        return CheckpointedHoldoutEvidence(
            command_id=command.id,
            evaluation_id=evaluation.id,
            artifact_id=artifact.id,
            artifact_hash=artifact.content_hash,
            authority_binding_hash=expected_hash,
            lease_generation=binding.lease_generation,
        )

    if retained is None:
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
    content = bytes(retained.content)
    digest = sha256(content).hexdigest()
    if (
        artifact.kind != _EVIDENCE_KIND
        or artifact.content_hash != digest
        or artifact.size_bytes != len(content)
        or artifact.media_type != "application/json"
        or artifact.schema_version != _EVIDENCE_SCHEMA_VERSION
        or artifact.producer_identity != command.evaluator_identity
        or artifact.container_image_digest != command.evaluator_version
        or artifact.storage_uri != f"controlled://sealed-holdout-evidence/{digest}"
    ):
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID") from exc
    expected_payload = _evidence_payload(
        command,
        authorization=authorization,
        measurements=dict(decoded.get("measurements", {})) if isinstance(decoded, dict) else {},
    )
    if (
        not isinstance(decoded, dict)
        or set(decoded) != set(expected_payload)
        or decoded != expected_payload
        or canonical_json(decoded).encode("utf-8") != content
        or not isinstance(decoded.get("measurements"), dict)
        or not set(decoded["measurements"]).issubset(_MEASUREMENT_KEYS)
    ):
        raise ValueError("HOLDOUT_FINALIZE_CHECKPOINT_INVALID")
    return CheckpointedHoldoutEvidence(
        command_id=command.id,
        evaluation_id=evaluation.id,
        artifact_id=artifact.id,
        artifact_hash=digest,
        authority_binding_hash=expected_hash,
        lease_generation=binding.lease_generation,
    )


def _artifact_matches_receipt(
    artifact: ResearchArtifact,
    *,
    artifact_receipt: Mapping[str, Any],
    command: ResearchHoldoutEvaluationCommand,
) -> bool:
    """Verify an opaque external artifact receipt without loading sealed bytes."""

    receipt_id = artifact_receipt.get("receipt_id")
    artifact_hash = artifact_receipt.get("artifact_hash")
    size_bytes = artifact_receipt.get("artifact_size_bytes")
    return bool(
        artifact_receipt.get("schema_version") == _RECEIPT_SCHEMA_VERSION
        and isinstance(receipt_id, str)
        and receipt_id
        and "/" not in receipt_id
        and "\\" not in receipt_id
        and "://" not in receipt_id
        and _is_sha256(artifact_hash)
        and type(size_bytes) is int
        and 1 <= size_bytes <= 10_000_000_000
        and artifact.kind == _RECEIPT_KIND
        and artifact.content_hash == artifact_hash
        and artifact.size_bytes == size_bytes
        and artifact.media_type == _RECEIPT_MEDIA_TYPE
        and artifact.schema_version == _RECEIPT_SCHEMA_VERSION
        and artifact.producer_identity == command.evaluator_identity
        and artifact.container_image_digest == command.evaluator_version
        and artifact.storage_uri == f"controlled://sealed-holdout-artifact-receipt/{receipt_id}"
    )


def _authority_binding_hash(
    command: ResearchHoldoutEvaluationCommand,
    *,
    artifact: ResearchArtifact,
    claim_audit: ResearchHoldoutAccessAudit,
    lease_owner: str | None = None,
    lease_generation: int | None = None,
    lease_expires_at: datetime,
) -> str:
    return content_hash(
        {
            "schema_version": _BINDING_SCHEMA_VERSION,
            "user_id": command.user_id,
            "run_id": command.run_id,
            "command_id": command.id,
            "authorization_id": command.authorization_id,
            "evaluation_id": command.evaluation_id,
            "experiment_epoch_id": command.experiment_epoch_id,
            "candidate_id": command.candidate_id,
            "candidate_hash": command.candidate_hash,
            "freeze_receipt_id": command.freeze_receipt_id,
            "freeze_receipt_fingerprint": command.freeze_receipt_fingerprint,
            "dataset_snapshot_id": command.dataset_snapshot_id,
            "sealed_dataset_hash": command.sealed_dataset_hash,
            "sealed_dataset_identity_hash": command.sealed_dataset_identity_hash,
            "policy_version": command.policy_version,
            "evaluator_identity": command.evaluator_identity,
            "evaluator_version": command.evaluator_version,
            "capability_profile_id": command.capability_profile_id,
            "capability_profile_version": command.capability_profile_version,
            "capability_evidence_hash": command.capability_evidence_hash,
            "artifact_id": artifact.id,
            "artifact_hash": artifact.content_hash,
            "claim_access_audit_id": claim_audit.id,
            "request_hash": command.request_hash,
            "lease_owner": lease_owner or command.lease_owner,
            "lease_generation": lease_generation or command.lease_generation,
            "lease_expires_at": _as_utc(lease_expires_at),
        }
    )


def _require_live_lease(
    command: ResearchHoldoutEvaluationCommand,
    *,
    runtime: HoldoutEvaluatorRuntimeIdentity,
    lease_token_hash: str,
    lease_generation: int,
    now: datetime,
) -> None:
    if command.status != "RUNNING" or command.stage != "HOLDOUT_PENDING":
        raise ValueError("HOLDOUT_FINALIZE_NOT_RUNNING")
    if (
        command.evaluator_identity != runtime.evaluator_identity
        or command.evaluator_version != runtime.evaluator_image_digest
        or command.lease_owner != runtime.worker_identity
    ):
        raise ValueError("HOLDOUT_FINALIZE_RUNTIME_IDENTITY_MISMATCH")
    if command.lease_token_hash != lease_token_hash or command.lease_generation != lease_generation:
        raise ValueError("HOLDOUT_FINALIZE_LEASE_STALE")
    if command.lease_expires_at is None or _as_utc(command.lease_expires_at) <= now:
        raise ValueError("HOLDOUT_FINALIZE_LEASE_EXPIRED")


def _require_reconciling_command(
    command: ResearchHoldoutEvaluationCommand,
    *,
    binding: ResearchHoldoutArtifactBinding,
) -> str:
    if (
        command.status != "RECONCILING"
        or command.stage != "HOLDOUT_PENDING"
        or command.error_code is None
        or command.lease_owner is not None
        or command.lease_token_hash is not None
        or command.lease_expires_at is not None
        or command.lease_heartbeat_at is not None
        or command.lease_generation != binding.lease_generation
    ):
        raise ValueError("HOLDOUT_FINALIZE_RECONCILE_NOT_ALLOWED")
    return command.error_code


async def _second_authority_fence(
    session: AsyncSession,
    command: ResearchHoldoutEvaluationCommand,
    *,
    runtime: HoldoutEvaluatorRuntimeIdentity,
    lease_token_hash: str | None,
    lease_generation: int,
    reconcile: bool,
    expected_reconciliation_error_code: str | None = None,
) -> None:
    conditions = [
        ResearchHoldoutEvaluationCommand.id == command.id,
        ResearchHoldoutEvaluationCommand.stage == "HOLDOUT_PENDING",
        ResearchHoldoutEvaluationCommand.evaluator_identity == runtime.evaluator_identity,
        ResearchHoldoutEvaluationCommand.evaluator_version == runtime.evaluator_image_digest,
        ResearchHoldoutEvaluationCommand.lease_generation == lease_generation,
        ResearchHoldoutEvaluationCommand.attempt_count
        == ResearchHoldoutEvaluationCommand.lease_generation,
    ]
    if reconcile:
        if not expected_reconciliation_error_code:
            raise ValueError("HOLDOUT_FINALIZE_RECONCILE_NOT_ALLOWED")
        conditions.extend(
            [
                ResearchHoldoutEvaluationCommand.status == "RECONCILING",
                ResearchHoldoutEvaluationCommand.error_code == expected_reconciliation_error_code,
                ResearchHoldoutEvaluationCommand.lease_owner.is_(None),
                ResearchHoldoutEvaluationCommand.lease_token_hash.is_(None),
                ResearchHoldoutEvaluationCommand.lease_expires_at.is_(None),
                ResearchHoldoutEvaluationCommand.lease_heartbeat_at.is_(None),
            ]
        )
    else:
        conditions.extend(
            [
                ResearchHoldoutEvaluationCommand.status == "RUNNING",
                ResearchHoldoutEvaluationCommand.error_code.is_(None),
                ResearchHoldoutEvaluationCommand.lease_owner == runtime.worker_identity,
                ResearchHoldoutEvaluationCommand.lease_token_hash == lease_token_hash,
                ResearchHoldoutEvaluationCommand.lease_heartbeat_at.is_not(None),
                ResearchHoldoutEvaluationCommand.lease_expires_at > DatabaseUtcNow(),
            ]
        )
    updated = await session.execute(
        update(ResearchHoldoutEvaluationCommand)
        .where(*conditions)
        .values(updated_at=DatabaseUtcNow())
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        raise ValueError("HOLDOUT_FINALIZE_LEASE_STALE")
    await session.refresh(command)


def _apply_terminal_graph(
    graph: Any,
    *,
    evaluation: ResearchEvaluation,
    promotion: PromotionResult,
    completed_at: datetime,
) -> FinalizedHoldoutEvaluation:
    gate_statuses = {outcome.code: outcome.status for outcome in promotion.decisions}
    evaluation.status = "PASSED" if promotion.eligible else "REJECTED"
    evaluation.metrics = {"promotion_eligible": promotion.eligible}
    evaluation.gate_inputs = {
        "input_evidence_hash": promotion.input_evidence_hash,
        "sealed_dataset_hash": graph.command.sealed_dataset_hash,
        "strict_freeze_receipt_fingerprint": promotion.strict_freeze_receipt_fingerprint,
        "promotion_policy_hash": promotion_policy_material_hash(
            resolve_server_policy(graph.command.policy_version)
        ),
        "gate_statuses": gate_statuses,
    }
    evaluation.completed_at = completed_at
    graph.epoch.status = "CLOSED"
    graph.epoch.closed_at = completed_at
    command = graph.command
    command.status = "SUCCEEDED"
    command.error_code = None
    command.lease_owner = None
    command.lease_token_hash = None
    command.lease_expires_at = None
    command.lease_heartbeat_at = None
    command.updated_at = completed_at
    return _terminal_receipt(command, evaluation=evaluation, promotion=promotion)


def _terminal_receipt(
    command: ResearchHoldoutEvaluationCommand,
    *,
    evaluation: ResearchEvaluation,
    promotion: PromotionResult,
) -> FinalizedHoldoutEvaluation:
    return FinalizedHoldoutEvaluation(
        command_id=command.id,
        evaluation_id=evaluation.id,
        command_status=command.status,
        evaluation_status=evaluation.status,
        input_evidence_hash=promotion.input_evidence_hash,
        eligible=promotion.eligible,
        gate_statuses={outcome.code: outcome.status for outcome in promotion.decisions},
    )


def _require_complete_promotion(
    promotion: PromotionResult,
    *,
    command: ResearchHoldoutEvaluationCommand,
) -> None:
    codes = {outcome.code for outcome in promotion.decisions}
    by_code = {outcome.code: outcome for outcome in promotion.decisions}
    if (
        promotion.candidate_id != command.candidate_id
        or promotion.policy_version != command.policy_version
        or len(promotion.decisions) != len(_REQUIRED_GATE_CODES)
        or codes != _REQUIRED_GATE_CODES
        or by_code["SEALED_HOLDOUT"].status != "PASS"
        or promotion.eligible != all(outcome.status == "PASS" for outcome in promotion.decisions)
    ):
        raise ValueError("HOLDOUT_FINALIZE_PROMOTION_INCOMPLETE")
    if not _is_sha256(promotion.input_evidence_hash):
        raise ValueError("HOLDOUT_FINALIZE_PROMOTION_INCOMPLETE")
    if promotion.strict_freeze_receipt_fingerprint != command.freeze_receipt_fingerprint:
        raise ValueError("HOLDOUT_FINALIZE_PROMOTION_INCOMPLETE")


def _require_generation(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("HOLDOUT_FINALIZE_LEASE_STALE")


def _lease_token_hash(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("HOLDOUT_FINALIZE_LEASE_STALE")
    return sha256(value.encode()).hexdigest()


def _required_time(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("HOLDOUT_FINALIZE_AUTHORITY_INCONSISTENT")
    return _as_utc(value)


def _required_identity(value: str | None) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
    return value


def _required_hash(value: str | None) -> str:
    if not _is_sha256(value):
        raise ValueError("HOLDOUT_FINALIZE_EXECUTION_INVALID")
    assert isinstance(value, str)
    return value


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
    if reason.startswith(("HOLDOUT_", "PROMOTION_", "DATASET_")):
        return reason[:128]
    return "HOLDOUT_FINALIZE_REJECTED"
