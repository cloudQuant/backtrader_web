"""Sealed-holdout evaluator that may write evidence but never candidate state."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchRun,
)
from app.services.research.candidate_registry import (
    require_strict_freeze_receipt,
    strict_freeze_receipt_fingerprint,
)
from app.services.research.canonical import canonical_json
from app.services.research.capabilities import CapabilityProfile, evaluate_capabilities
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)
from app.services.research.holdout_authorization import HoldoutAuthorizationRegistry
from app.services.research.promotion import (
    PromotionGateEngine,
    PromotionPolicy,
    PromotionResult,
    promotion_policy_material_hash,
    resolve_server_policy,
)

_EVIDENCE_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "authorization_id",
        "candidate_id",
        "candidate_hash",
        "experiment_epoch_id",
        "dataset_snapshot_id",
        "sealed_dataset_hash",
        "policy_version",
        "evaluator_identity",
        "evaluator_version",
        "measurements",
    }
)
_EVIDENCE_MEASUREMENT_KEYS = frozenset(
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
_SECURITY_SCAN_KIND = "security_scan_evidence"
_SECURITY_SCAN_SCHEMA = "security-scan-evidence-v1"
_SECURITY_SCAN_POLICY_VERSION = "security-scan-policy-v1"
_SECURITY_SCANNER_IDENTITY = "research-security-scanner"
_SECURITY_SCANNER_IMAGE_DIGEST = f"sha256:{'5' * 64}"
_SECURITY_SCAN_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "candidate_hash",
        "code_artifact_id",
        "code_hash",
        "dependency_artifact_id",
        "dependency_hash",
        "evaluator_identity",
        "evaluator_version",
        "scan_policy_version",
        "scanner_identity",
        "scanner_image_digest",
        "critical_findings",
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
_TERMINAL_EVALUATION_STATUSES = frozenset({"PASSED", "REJECTED", "FAILED"})
_PROMOTION_RESIDUE_ERRORS = frozenset(
    {"PROMOTION_DECISION_SET_PARTIAL", "PROMOTION_DECISION_SET_CONFLICT"}
)
_DETERMINISTIC_FAILURE_CODES = frozenset({*_PROMOTION_RESIDUE_ERRORS, "PROMOTION_RESULT_INVALID"})


class IndependentEvaluator:
    """Execute a single opaque sealed evaluation receipt path.

    The evaluator consumes a one-time authorization and only appends an
    evaluation plus gate evidence.  It deliberately has no candidate registry
    dependency, so it cannot mutate code, prompts, search queues, or frozen
    identity after disclosure.
    """

    def __init__(self, *, dataset_registry: DatasetRegistry | None = None) -> None:
        """Use one resolver-backed registry for token consumption and evaluation."""

        self._datasets = dataset_registry or DatasetRegistry()
        self._holdout_authorizations = HoldoutAuthorizationRegistry(
            dataset_registry=self._datasets,
        )

    async def evaluate_holdout(
        self,
        *,
        authorization_token: str,
        candidate_id: str,
        candidate_hash: str,
        dataset_snapshot_id: str,
        policy: PromotionPolicy,
        evaluator_identity: str,
        evaluator_version: str,
        evidence: Mapping[str, Any],
        returns_artifact_id: str | None = None,
    ) -> ResearchEvaluation:
        """Consume an opaque token, record result evidence, and close the epoch."""

        policy.validate()
        evidence_dict = dict(evidence)
        async with database.async_session_maker() as session:
            try:
                await _reject_command_authority_for_candidate(
                    session,
                    candidate_id=candidate_id,
                )
                authorization = await self._holdout_authorizations.consume_in_session(
                    session,
                    authorization_token,
                    candidate_id=candidate_id,
                    candidate_hash=candidate_hash,
                    dataset_snapshot_id=dataset_snapshot_id,
                    policy_version=policy.version,
                    evaluator_identity=evaluator_identity,
                )
                candidate = await session.get(ResearchCandidate, candidate_id)
                if candidate is None:
                    raise ValueError("INDEPENDENT_EVALUATOR_CANDIDATE_NOT_FOUND")
                await require_strict_freeze_receipt(session, candidate)
                run = await session.get(ResearchRun, candidate.run_id)
                if run is None:
                    raise ValueError("INDEPENDENT_EVALUATOR_BINDING_INCONSISTENT")
                await _require_current_evaluator_profile(
                    session,
                    run=run,
                    evaluator_identity=evaluator_identity,
                    evaluator_version=evaluator_version,
                )
                snapshot = await session.get(ResearchDatasetSnapshot, dataset_snapshot_id)
                if snapshot is None or snapshot.partition_kind != "SEALED_HOLDOUT":
                    raise ValueError("INDEPENDENT_EVALUATOR_SEALED_DATASET_NOT_FOUND")
                require_verified_snapshot_integrity(snapshot)
                epoch = await session.get(
                    ResearchExperimentEpoch,
                    authorization.experiment_epoch_id,
                )
                if (
                    epoch is None
                    or epoch.selected_candidate_id != candidate_id
                    or epoch.status != "DISCLOSED"
                ):
                    raise ValueError("INDEPENDENT_EVALUATOR_EPOCH_INCONSISTENT")
                await self._datasets.revalidate_snapshot_in_session(session, snapshot=snapshot)
                require_verified_snapshot_integrity(snapshot)
                evidence_artifact = await _require_retained_evidence_artifact(
                    session,
                    artifact_id=returns_artifact_id,
                    authorization_id=authorization.id,
                    candidate_id=candidate.id,
                    candidate_hash=candidate.candidate_hash,
                    experiment_epoch_id=epoch.id,
                    dataset_snapshot_id=snapshot.id,
                    sealed_dataset_hash=snapshot.content_hash,
                    policy_version=policy.version,
                    evaluator_identity=evaluator_identity,
                    evaluator_version=evaluator_version,
                )
                evaluation = ResearchEvaluation(
                    experiment_epoch_id=epoch.id,
                    candidate_id=candidate_id,
                    dataset_snapshot_id=dataset_snapshot_id,
                    evaluation_type="SEALED_HOLDOUT",
                    evaluator_identity=evaluator_identity,
                    evaluator_version=evaluator_version,
                    authorization_id=authorization.id,
                    returns_artifact_id=evidence_artifact.id,
                    metrics={},
                    gate_inputs={},
                    policy_version=policy.version,
                    status="RUNNING",
                    started_at=_now(),
                )
                session.add(evaluation)
                await session.flush()
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("INDEPENDENT_EVALUATOR_BUDGET_ALREADY_CONSUMED") from exc
            await session.refresh(evaluation)

        try:
            promotion = await PromotionGateEngine().evaluate_and_record(
                candidate_id=candidate_id,
                evaluation_id=evaluation.id,
                policy=policy,
                evidence=evidence_dict,
            )
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc) in _PROMOTION_RESIDUE_ERRORS:
                await self._finish(
                    evaluation_id=evaluation.id,
                    policy=policy,
                    eligible=False,
                    gate_inputs={
                        "sealed_evidence_artifact_hash": evidence_artifact.content_hash,
                        "promotion_resume_error_code": str(exc),
                    },
                    metrics={"promotion_eligible": False, "error_code": str(exc)},
                    status="FAILED",
                )
            raise
        return await self._finish(
            evaluation_id=evaluation.id,
            policy=policy,
            eligible=promotion.eligible,
            gate_inputs={
                "input_evidence_hash": promotion.input_evidence_hash,
                "sealed_dataset_hash": snapshot.content_hash,
                "strict_freeze_receipt_fingerprint": (promotion.strict_freeze_receipt_fingerprint),
                "promotion_policy_hash": promotion_policy_material_hash(policy),
                "gate_statuses": {outcome.code: outcome.status for outcome in promotion.decisions},
            },
            metrics={"promotion_eligible": promotion.eligible},
            status="PASSED" if promotion.eligible else "REJECTED",
            promotion=promotion,
        )

    async def resume_evaluation(
        self,
        *,
        evaluation_id: str,
        policy: PromotionPolicy,
        evaluator_identity: str,
    ) -> ResearchEvaluation:
        """Resume one deployment-owned RUNNING evaluation after a process crash."""

        policy.validate()
        if not isinstance(evaluator_identity, str) or not evaluator_identity.strip():
            raise ValueError("INDEPENDENT_EVALUATOR_IDENTITY_REQUIRED")
        terminal = await self._read_terminal_evaluation(
            evaluation_id=evaluation_id,
            policy=policy,
            evaluator_identity=evaluator_identity,
        )
        if terminal is not None:
            return terminal

        async with database.async_session_maker() as session:
            (
                evaluation,
                receipt_fingerprint,
                artifact,
                snapshot_hash,
            ) = await self._validate_resume_authority(
                session,
                evaluation_id=evaluation_id,
                policy=policy,
                evaluator_identity=evaluator_identity,
            )
            if evaluation.status in _TERMINAL_EVALUATION_STATUSES:
                raced_terminal = True
            else:
                raced_terminal = False
                candidate_id = evaluation.candidate_id
                artifact_hash = artifact.content_hash

        if raced_terminal:
            terminal = await self._read_terminal_evaluation(
                evaluation_id=evaluation_id,
                policy=policy,
                evaluator_identity=evaluator_identity,
            )
            if terminal is None:
                raise ValueError("INDEPENDENT_EVALUATOR_STATE_INVALID")
            return terminal

        try:
            promotion = await PromotionGateEngine().evaluate_and_record(
                candidate_id=candidate_id,
                evaluation_id=evaluation_id,
                policy=policy,
                evidence={},
            )
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc) in _PROMOTION_RESIDUE_ERRORS:
                await self._finish(
                    evaluation_id=evaluation_id,
                    policy=policy,
                    eligible=False,
                    gate_inputs={
                        "sealed_evidence_artifact_hash": artifact_hash,
                        "promotion_resume_error_code": str(exc),
                    },
                    metrics={"promotion_eligible": False, "error_code": str(exc)},
                    status="FAILED",
                )
            raise
        return await self._finish(
            evaluation_id=evaluation_id,
            policy=policy,
            eligible=promotion.eligible,
            gate_inputs={
                "input_evidence_hash": promotion.input_evidence_hash,
                "sealed_dataset_hash": snapshot_hash,
                "strict_freeze_receipt_fingerprint": receipt_fingerprint,
                "promotion_policy_hash": promotion_policy_material_hash(policy),
                "gate_statuses": {outcome.code: outcome.status for outcome in promotion.decisions},
            },
            metrics={"promotion_eligible": promotion.eligible},
            status="PASSED" if promotion.eligible else "REJECTED",
            promotion=promotion,
        )

    async def _read_terminal_evaluation(
        self,
        *,
        evaluation_id: str,
        policy: PromotionPolicy,
        evaluator_identity: str | None = None,
    ) -> ResearchEvaluation | None:
        """Return a terminal evaluation only after authoritative promotion replay."""

        async with database.async_session_maker() as session:
            seed = await session.get(ResearchEvaluation, evaluation_id)
            if seed is None:
                raise ValueError("INDEPENDENT_EVALUATOR_EVALUATION_NOT_FOUND")
            if seed.policy_version != policy.version:
                raise ValueError("INDEPENDENT_EVALUATOR_POLICY_MISMATCH")
            if evaluator_identity is not None and seed.evaluator_identity != evaluator_identity:
                raise ValueError("INDEPENDENT_EVALUATOR_IDENTITY_MISMATCH")
            await _reject_command_authority_for_epoch(
                session,
                experiment_epoch_id=seed.experiment_epoch_id,
            )
            if seed.status not in _TERMINAL_EVALUATION_STATUSES:
                return None

            promotion: PromotionResult | None = None
            if seed.status in {"PASSED", "REJECTED"}:
                input_evidence_hash = dict(seed.gate_inputs or {}).get("input_evidence_hash")
                if not _is_sha256(input_evidence_hash):
                    raise ValueError("PROMOTION_RESULT_INVALID")
                promotion = await PromotionGateEngine().read_result_in_session(
                    session,
                    candidate_id=seed.candidate_id,
                    evaluation_id=seed.id,
                    policy_version=policy.version,
                    input_evidence_hash=input_evidence_hash,
                )

            (
                evaluation,
                receipt_fingerprint,
                artifact,
                snapshot_hash,
            ) = await self._validate_resume_authority(
                session,
                evaluation_id=evaluation_id,
                policy=policy,
                evaluator_identity=evaluator_identity,
            )
            await _require_terminal_consistency(
                evaluation=evaluation,
                receipt_fingerprint=receipt_fingerprint,
                artifact=artifact,
                snapshot_hash=snapshot_hash,
                promotion=promotion,
            )
            return evaluation

    async def _validate_resume_authority(
        self,
        session: AsyncSession,
        *,
        evaluation_id: str,
        policy: PromotionPolicy,
        evaluator_identity: str | None = None,
    ) -> tuple[ResearchEvaluation, str, ResearchArtifact, str]:
        """Re-read every sealed authority binding before replay or terminal read."""

        seed = await session.get(ResearchEvaluation, evaluation_id)
        if seed is None:
            raise ValueError("INDEPENDENT_EVALUATOR_EVALUATION_NOT_FOUND")
        if seed.policy_version != policy.version:
            raise ValueError("INDEPENDENT_EVALUATOR_POLICY_MISMATCH")
        if evaluator_identity is not None and seed.evaluator_identity != evaluator_identity:
            raise ValueError("INDEPENDENT_EVALUATOR_IDENTITY_MISMATCH")
        epoch = await session.scalar(
            select(ResearchExperimentEpoch)
            .where(ResearchExperimentEpoch.id == seed.experiment_epoch_id)
            .with_for_update()
        )
        if epoch is None:
            raise ValueError("INDEPENDENT_EVALUATOR_EPOCH_INCONSISTENT")
        await _reject_command_authority_for_epoch(
            session,
            experiment_epoch_id=epoch.id,
        )
        candidate = await session.scalar(
            select(ResearchCandidate)
            .where(ResearchCandidate.id == seed.candidate_id)
            .with_for_update()
        )
        if candidate is None:
            raise ValueError("INDEPENDENT_EVALUATOR_CANDIDATE_NOT_FOUND")
        receipt = await require_strict_freeze_receipt(session, candidate)
        evaluation = await session.scalar(
            select(ResearchEvaluation)
            .where(ResearchEvaluation.id == evaluation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if evaluation is None:
            raise ValueError("INDEPENDENT_EVALUATOR_EVALUATION_NOT_FOUND")
        run = await session.get(ResearchRun, candidate.run_id)
        authorization = (
            await session.scalar(
                select(ResearchHoldoutAuthorization)
                .where(ResearchHoldoutAuthorization.id == evaluation.authorization_id)
                .with_for_update()
            )
            if evaluation.authorization_id is not None
            else None
        )
        if (
            run is None
            or authorization is None
            or evaluation.candidate_id != candidate.id
            or evaluation.experiment_epoch_id != epoch.id
            or candidate.experiment_epoch_id != epoch.id
            or authorization.status != "CONSUMED"
            or authorization.consumed_at is None
            or authorization.experiment_epoch_id != candidate.experiment_epoch_id
            or authorization.candidate_id != candidate.id
            or authorization.candidate_hash != candidate.candidate_hash
            or authorization.dataset_snapshot_id != evaluation.dataset_snapshot_id
            or authorization.policy_version != policy.version
            or authorization.evaluator_identity != evaluation.evaluator_identity
            or authorization.capability_profile_id != run.capability_profile_id
            or authorization.capability_profile_version != run.capability_profile_version
            or authorization.capability_evidence_hash != run.capability_evidence_hash
        ):
            raise ValueError("INDEPENDENT_EVALUATOR_AUTHORIZATION_INCONSISTENT")
        if (
            evaluation.experiment_epoch_id != candidate.experiment_epoch_id
            or evaluation.evaluation_type != "SEALED_HOLDOUT"
            or evaluation.policy_version != policy.version
            or run.user_id != candidate.user_id
            or run.experiment_epoch_id != candidate.experiment_epoch_id
            or run.dataset_snapshot_id != candidate.dataset_snapshot_id
            or run.promotion_policy_version != policy.version
            or not evaluation.evaluator_identity.strip()
            or not evaluation.evaluator_version.strip()
            or evaluation.started_at is None
        ):
            raise ValueError("INDEPENDENT_EVALUATOR_BINDING_INCONSISTENT")
        await _require_current_evaluator_profile(
            session,
            run=run,
            evaluator_identity=evaluation.evaluator_identity,
            evaluator_version=evaluation.evaluator_version,
        )
        if evaluation.status == "RUNNING":
            expected_epoch_status = "DISCLOSED"
            if evaluation.completed_at is not None or evaluation.metrics or evaluation.gate_inputs:
                raise ValueError("INDEPENDENT_EVALUATOR_STATE_INVALID")
        elif evaluation.status in _TERMINAL_EVALUATION_STATUSES:
            expected_epoch_status = "CLOSED"
            if evaluation.completed_at is None:
                raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")
        else:
            raise ValueError("INDEPENDENT_EVALUATOR_STATE_INVALID")
        if (
            epoch is None
            or epoch.selected_candidate_id != candidate.id
            or epoch.status != expected_epoch_status
            or (expected_epoch_status == "CLOSED" and epoch.closed_at is None)
            or (expected_epoch_status == "DISCLOSED" and epoch.closed_at is not None)
        ):
            raise ValueError("INDEPENDENT_EVALUATOR_EPOCH_INCONSISTENT")
        snapshot = await session.get(ResearchDatasetSnapshot, evaluation.dataset_snapshot_id)
        if (
            snapshot is None
            or snapshot.user_id != candidate.user_id
            or snapshot.partition_kind != "SEALED_HOLDOUT"
        ):
            raise ValueError("INDEPENDENT_EVALUATOR_SEALED_DATASET_NOT_FOUND")
        require_verified_snapshot_integrity(snapshot)
        await self._datasets.revalidate_snapshot_in_session(session, snapshot=snapshot)
        require_verified_snapshot_integrity(snapshot)
        artifact = await _require_retained_evidence_artifact(
            session,
            artifact_id=evaluation.returns_artifact_id,
            authorization_id=authorization.id,
            candidate_id=candidate.id,
            candidate_hash=candidate.candidate_hash,
            experiment_epoch_id=epoch.id,
            dataset_snapshot_id=snapshot.id,
            sealed_dataset_hash=snapshot.content_hash,
            policy_version=policy.version,
            evaluator_identity=evaluation.evaluator_identity,
            evaluator_version=evaluation.evaluator_version,
        )
        return (
            evaluation,
            strict_freeze_receipt_fingerprint(receipt),
            artifact,
            snapshot.content_hash,
        )

    async def _finish(
        self,
        *,
        evaluation_id: str,
        policy: PromotionPolicy,
        eligible: bool,
        gate_inputs: dict[str, Any],
        metrics: dict[str, Any],
        status: str,
        promotion: PromotionResult | None = None,
    ) -> ResearchEvaluation:
        """Finalize evaluation and close its disclosed epoch without touching candidate."""

        policy.validate()
        if status not in _TERMINAL_EVALUATION_STATUSES or eligible != (status == "PASSED"):
            raise ValueError("INDEPENDENT_EVALUATOR_FINALIZATION_INVALID")
        if (status in {"PASSED", "REJECTED"}) != (promotion is not None):
            raise ValueError("INDEPENDENT_EVALUATOR_FINALIZATION_INVALID")

        terminal = await self._read_terminal_evaluation(
            evaluation_id=evaluation_id,
            policy=policy,
        )
        if terminal is not None:
            _require_requested_terminal_match(
                terminal,
                gate_inputs=gate_inputs,
                metrics=metrics,
                status=status,
            )
            return terminal

        replay_error: ValueError | None = None
        artifact_hash_for_failure: str | None = None
        async with database.async_session_maker() as session:
            (
                evaluation,
                receipt_fingerprint,
                artifact,
                snapshot_hash,
            ) = await self._validate_resume_authority(
                session,
                evaluation_id=evaluation_id,
                policy=policy,
            )
            if evaluation.status in _TERMINAL_EVALUATION_STATUSES:
                raced_terminal = True
            else:
                raced_terminal = False
                epoch = await session.get(
                    ResearchExperimentEpoch,
                    evaluation.experiment_epoch_id,
                    with_for_update=True,
                )
                if epoch is None:
                    raise ValueError("INDEPENDENT_EVALUATOR_EPOCH_INCONSISTENT")
                if promotion is not None:
                    _require_promotion_finalization_request(
                        evaluation=evaluation,
                        policy=policy,
                        promotion=promotion,
                        receipt_fingerprint=receipt_fingerprint,
                        snapshot_hash=snapshot_hash,
                        gate_inputs=gate_inputs,
                        metrics=metrics,
                        status=status,
                    )
                else:
                    _require_failed_payload(
                        gate_inputs=gate_inputs,
                        metrics=metrics,
                        artifact_hash=artifact.content_hash,
                    )
                evaluation.gate_inputs = gate_inputs
                evaluation.metrics = metrics
                evaluation.status = status
                evaluation.completed_at = _now()
                epoch.status = "CLOSED"
                epoch.closed_at = _now()
                await session.flush()
                if promotion is not None:
                    try:
                        replayed = await PromotionGateEngine().read_result_in_session(
                            session,
                            candidate_id=evaluation.candidate_id,
                            evaluation_id=evaluation.id,
                            policy_version=policy.version,
                            input_evidence_hash=promotion.input_evidence_hash,
                        )
                        if replayed != promotion:
                            raise ValueError("PROMOTION_RESULT_INVALID")
                        await _require_terminal_consistency(
                            evaluation=evaluation,
                            receipt_fingerprint=receipt_fingerprint,
                            artifact=artifact,
                            snapshot_hash=snapshot_hash,
                            promotion=replayed,
                        )
                    except ValueError as exc:
                        if str(exc) != "PROMOTION_RESULT_INVALID":
                            raise
                        replay_error = exc
                        artifact_hash_for_failure = artifact.content_hash
                        await session.rollback()
                if replay_error is None:
                    await session.commit()
                    await session.refresh(evaluation)
                    return evaluation

        if replay_error is not None:
            if artifact_hash_for_failure is None:
                raise replay_error
            await self._finish(
                evaluation_id=evaluation_id,
                policy=policy,
                eligible=False,
                gate_inputs={
                    "sealed_evidence_artifact_hash": artifact_hash_for_failure,
                    "promotion_resume_error_code": "PROMOTION_RESULT_INVALID",
                },
                metrics={
                    "promotion_eligible": False,
                    "error_code": "PROMOTION_RESULT_INVALID",
                },
                status="FAILED",
            )
            raise replay_error

        if raced_terminal:
            terminal = await self._read_terminal_evaluation(
                evaluation_id=evaluation_id,
                policy=policy,
            )
            if terminal is None:
                raise ValueError("INDEPENDENT_EVALUATOR_STATE_INVALID")
            _require_requested_terminal_match(
                terminal,
                gate_inputs=gate_inputs,
                metrics=metrics,
                status=status,
            )
            return terminal


async def _reject_command_authority_for_candidate(
    session: AsyncSession,
    *,
    candidate_id: str,
) -> None:
    """Serialize with request/claim and keep raw-token evaluation commandless."""

    candidate_identity = (
        await session.execute(
            select(
                ResearchCandidate.user_id,
                ResearchCandidate.experiment_epoch_id,
            ).where(ResearchCandidate.id == candidate_id)
        )
    ).one_or_none()
    if candidate_identity is None:
        return
    user_id, experiment_epoch_id = candidate_identity
    epoch = await session.scalar(
        select(ResearchExperimentEpoch)
        .where(
            ResearchExperimentEpoch.id == experiment_epoch_id,
            ResearchExperimentEpoch.user_id == user_id,
        )
        .with_for_update()
    )
    if epoch is None:
        return
    await _reject_command_authority_for_epoch(
        session,
        experiment_epoch_id=epoch.id,
    )


async def _reject_command_authority_for_epoch(
    session: AsyncSession,
    *,
    experiment_epoch_id: str,
) -> None:
    command_id = await session.scalar(
        select(ResearchHoldoutEvaluationCommand.id)
        .where(ResearchHoldoutEvaluationCommand.experiment_epoch_id == experiment_epoch_id)
        .with_for_update()
    )
    if command_id is not None:
        raise ValueError("INDEPENDENT_EVALUATOR_CLAIM_FENCE_REQUIRED")


async def _require_terminal_consistency(
    *,
    evaluation: ResearchEvaluation,
    receipt_fingerprint: str,
    artifact: ResearchArtifact,
    snapshot_hash: str,
    promotion: PromotionResult | None,
) -> None:
    """Require terminal fields to match the independently replayed authority."""

    gate_inputs = dict(evaluation.gate_inputs or {})
    metrics = dict(evaluation.metrics or {})
    if evaluation.completed_at is None:
        raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")
    if evaluation.status == "FAILED":
        if promotion is not None:
            raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")
        _require_failed_payload(
            gate_inputs=gate_inputs,
            metrics=metrics,
            artifact_hash=artifact.content_hash,
        )
        return

    if promotion is None:
        raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")
    expected_gate_inputs = {
        "input_evidence_hash": promotion.input_evidence_hash,
        "sealed_dataset_hash": snapshot_hash,
        "strict_freeze_receipt_fingerprint": receipt_fingerprint,
        "promotion_policy_hash": promotion_policy_material_hash(
            resolve_server_policy(evaluation.policy_version)
        ),
        "gate_statuses": {outcome.code: outcome.status for outcome in promotion.decisions},
    }
    expected_metrics = {"promotion_eligible": promotion.eligible}
    if (
        promotion.candidate_id != evaluation.candidate_id
        or promotion.policy_version != evaluation.policy_version
        or promotion.strict_freeze_receipt_fingerprint != receipt_fingerprint
        or gate_inputs != expected_gate_inputs
        or metrics != expected_metrics
        or evaluation.status != ("PASSED" if promotion.eligible else "REJECTED")
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")


def _require_promotion_finalization_request(
    *,
    evaluation: ResearchEvaluation,
    policy: PromotionPolicy,
    promotion: PromotionResult,
    receipt_fingerprint: str,
    snapshot_hash: str,
    gate_inputs: dict[str, Any],
    metrics: dict[str, Any],
    status: str,
) -> None:
    """Require finalization fields to be the exact PromotionResult projection."""

    expected_status = "PASSED" if promotion.eligible else "REJECTED"
    expected_gate_inputs = {
        "input_evidence_hash": promotion.input_evidence_hash,
        "sealed_dataset_hash": snapshot_hash,
        "strict_freeze_receipt_fingerprint": receipt_fingerprint,
        "promotion_policy_hash": promotion_policy_material_hash(policy),
        "gate_statuses": {outcome.code: outcome.status for outcome in promotion.decisions},
    }
    if (
        status != expected_status
        or promotion.candidate_id != evaluation.candidate_id
        or promotion.policy_version != policy.version
        or promotion.strict_freeze_receipt_fingerprint != receipt_fingerprint
        or not _is_sha256(promotion.input_evidence_hash)
        or len(promotion.decisions) != len(_REQUIRED_GATE_CODES)
        or {outcome.code for outcome in promotion.decisions} != _REQUIRED_GATE_CODES
        or gate_inputs != expected_gate_inputs
        or metrics != {"promotion_eligible": promotion.eligible}
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_FINALIZATION_INVALID")


def _require_failed_payload(
    *,
    gate_inputs: dict[str, Any],
    metrics: dict[str, Any],
    artifact_hash: str,
) -> None:
    """Validate the narrow fail-closed record written after gate execution errors."""

    error_code = metrics.get("error_code")
    resume_error = gate_inputs.get("promotion_resume_error_code")
    if (
        set(metrics) != {"promotion_eligible", "error_code"}
        or metrics.get("promotion_eligible") is not False
        or error_code not in _DETERMINISTIC_FAILURE_CODES
        or set(gate_inputs)
        not in (
            {"sealed_evidence_artifact_hash"},
            {"sealed_evidence_artifact_hash", "promotion_resume_error_code"},
        )
        or gate_inputs.get("sealed_evidence_artifact_hash") != artifact_hash
        or (resume_error is not None and resume_error != error_code)
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")


def _require_requested_terminal_match(
    evaluation: ResearchEvaluation,
    *,
    gate_inputs: dict[str, Any],
    metrics: dict[str, Any],
    status: str,
) -> None:
    """Make concurrent/repeated finalization return only the identical result."""

    if (
        evaluation.status != status
        or dict(evaluation.gate_inputs or {}) != gate_inputs
        or dict(evaluation.metrics or {}) != metrics
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_TERMINAL_INCONSISTENT")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _require_current_evaluator_profile(
    session: AsyncSession,
    *,
    run: ResearchRun,
    evaluator_identity: str,
    evaluator_version: str,
) -> None:
    """Revalidate the run-bound deployment identity and immutable stage images."""

    model = await session.scalar(
        select(ResearchCapabilityProfile)
        .where(
            ResearchCapabilityProfile.profile_id == run.capability_profile_id,
            ResearchCapabilityProfile.version == run.capability_profile_version,
        )
        .with_for_update()
    )
    if model is None:
        raise ValueError("INDEPENDENT_EVALUATOR_PROFILE_NOT_CURRENT")
    sandbox_capabilities = model.sandbox_capabilities or {}
    stage_image_digests = sandbox_capabilities.get("stage_image_digests")
    if not isinstance(stage_image_digests, dict):
        raise ValueError("INDEPENDENT_EVALUATOR_PROFILE_NOT_CURRENT")
    profile = CapabilityProfile(
        profile_id=model.profile_id,
        version=model.version,
        service_identities=dict(model.service_identities or {}),
        queue_isolation=bool((model.queue_capabilities or {}).get("isolated")),
        storage_isolation=bool((model.storage_boundaries or {}).get("isolated")),
        network_isolation=bool((model.network_capabilities or {}).get("isolated")),
        sandbox_runner=bool(sandbox_capabilities.get("runner")),
        approval_mode=str((model.approval_capabilities or {}).get("mode") or model.actor_mode),
        evidence_hash=model.evidence_hash,
        verified_at=_as_utc(model.verified_at),
        expires_at=_as_utc(model.expires_at),
        stage_image_digests=dict(stage_image_digests),
    )
    decision = evaluate_capabilities(profile, required=("sealed_evaluation",))
    if (
        model.evidence_hash != run.capability_evidence_hash
        or not decision.allowed
        or profile.service_identities.get("evaluator") != evaluator_identity
        or profile.stage_image_digests.get("evaluator") != evaluator_version
        or profile.stage_image_digests.get("scanner") != _SECURITY_SCANNER_IMAGE_DIGEST
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_PROFILE_NOT_CURRENT")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _require_retained_evidence_artifact(
    session: AsyncSession,
    *,
    artifact_id: str | None,
    authorization_id: str,
    candidate_id: str,
    candidate_hash: str,
    experiment_epoch_id: str,
    dataset_snapshot_id: str,
    sealed_dataset_hash: str,
    policy_version: str,
    evaluator_identity: str,
    evaluator_version: str,
) -> ResearchArtifact:
    """Require a canonical, retained evaluator artifact before budget consumption."""

    if artifact_id is None:
        raise ValueError("INDEPENDENT_EVALUATOR_EVIDENCE_ARTIFACT_REQUIRED")
    artifact = await session.get(ResearchArtifact, artifact_id)
    retained = await session.get(ResearchArtifactContent, artifact_id)
    if artifact is None or retained is None:
        raise ValueError("INDEPENDENT_EVALUATOR_EVIDENCE_ARTIFACT_REQUIRED")
    storage = urlsplit(artifact.storage_uri)
    payload = bytes(retained.content)
    if (
        artifact.kind != "sealed_holdout_evidence"
        or artifact.schema_version != "sealed-holdout-evidence-v1"
        or artifact.media_type != "application/json"
        or artifact.producer_identity != evaluator_identity
        or artifact.container_image_digest != evaluator_version
        or storage.scheme != "controlled"
        or not storage.netloc
        or storage.query
        or storage.fragment
        or artifact.size_bytes != len(payload)
        or artifact.content_hash != sha256(payload).hexdigest()
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_EVIDENCE_ARTIFACT_INVALID")
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("INDEPENDENT_EVALUATOR_EVIDENCE_ARTIFACT_INVALID") from exc
    expected_binding = {
        "schema_version": "sealed-holdout-evidence-v1",
        "authorization_id": authorization_id,
        "candidate_id": candidate_id,
        "candidate_hash": candidate_hash,
        "experiment_epoch_id": experiment_epoch_id,
        "dataset_snapshot_id": dataset_snapshot_id,
        "sealed_dataset_hash": sealed_dataset_hash,
        "policy_version": policy_version,
        "evaluator_identity": evaluator_identity,
        "evaluator_version": evaluator_version,
    }
    if (
        not isinstance(decoded, dict)
        or canonical_json(decoded).encode("utf-8") != payload
        or set(decoded) != _EVIDENCE_TOP_LEVEL_KEYS
        or any(decoded.get(key) != value for key, value in expected_binding.items())
        or not isinstance(decoded.get("measurements"), dict)
        or not set(decoded["measurements"]).issubset(_EVIDENCE_MEASUREMENT_KEYS)
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_EVIDENCE_ARTIFACT_INVALID")
    measurements = decoded["measurements"]
    if (
        measurements.get("security_scan_hash") is not None
        and measurements.get("security_critical_findings") is not None
    ):
        await _require_retained_security_scan_artifact(
            session,
            candidate_id=candidate_id,
            candidate_hash=candidate_hash,
            evaluator_identity=evaluator_identity,
            evaluator_version=evaluator_version,
            scan_hash=measurements["security_scan_hash"],
            claimed_findings=measurements["security_critical_findings"],
        )
    return artifact


async def _require_retained_security_scan_artifact(
    session: AsyncSession,
    *,
    candidate_id: str,
    candidate_hash: str,
    evaluator_identity: str,
    evaluator_version: str,
    scan_hash: object,
    claimed_findings: object,
) -> None:
    """Bind a security gate claim to retained canonical scanner output."""

    if (
        not _is_sha256(scan_hash)
        or isinstance(claimed_findings, bool)
        or not isinstance(claimed_findings, int)
        or claimed_findings < 0
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID")
    artifact = await session.scalar(
        select(ResearchArtifact)
        .where(
            ResearchArtifact.kind == _SECURITY_SCAN_KIND,
            ResearchArtifact.content_hash == scan_hash,
        )
        .with_for_update()
    )
    if artifact is None:
        raise ValueError("INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID")
    retained = await session.get(ResearchArtifactContent, artifact.id, with_for_update=True)
    candidate = await session.get(ResearchCandidate, candidate_id)
    code = (
        await session.get(ResearchArtifact, candidate.code_artifact_id, with_for_update=True)
        if candidate is not None
        else None
    )
    dependency = (
        await session.get(
            ResearchArtifact,
            candidate.dependency_artifact_id,
            with_for_update=True,
        )
        if candidate is not None
        else None
    )
    if retained is None or candidate is None or code is None or dependency is None:
        raise ValueError("INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID")
    content = bytes(retained.content)
    storage = urlsplit(artifact.storage_uri)
    if (
        artifact.schema_version != _SECURITY_SCAN_SCHEMA
        or artifact.media_type != "application/json"
        or artifact.producer_identity != _SECURITY_SCANNER_IDENTITY
        or artifact.container_image_digest != _SECURITY_SCANNER_IMAGE_DIGEST
        or storage.scheme != "controlled"
        or not storage.netloc
        or storage.query
        or storage.fragment
        or artifact.size_bytes != len(content)
        or artifact.content_hash != sha256(content).hexdigest()
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID") from exc
    expected = {
        "schema_version": _SECURITY_SCAN_SCHEMA,
        "candidate_id": candidate_id,
        "candidate_hash": candidate_hash,
        "code_artifact_id": code.id,
        "code_hash": code.content_hash,
        "dependency_artifact_id": dependency.id,
        "dependency_hash": dependency.content_hash,
        "evaluator_identity": evaluator_identity,
        "evaluator_version": evaluator_version,
        "scan_policy_version": _SECURITY_SCAN_POLICY_VERSION,
        "scanner_identity": _SECURITY_SCANNER_IDENTITY,
        "scanner_image_digest": _SECURITY_SCANNER_IMAGE_DIGEST,
        "critical_findings": claimed_findings,
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != _SECURITY_SCAN_PAYLOAD_KEYS
        or canonical_json(payload).encode("utf-8") != content
        or payload != expected
    ):
        raise ValueError("INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID")
