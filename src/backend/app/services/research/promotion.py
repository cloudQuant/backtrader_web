"""Server-authoritative, evidence-bound hard gates for research promotion.

The public method deliberately accepts a compatibility ``evidence`` mapping,
but that mapping is never promotion authority. Gate inputs are read back from
one retained, canonical sealed-evaluator artifact whose database bindings are
validated against a consumed one-time authorization.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from math import isfinite, sqrt
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchCapabilityProfile,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchGateDecision,
    ResearchHoldoutAccessAudit,
    ResearchHoldoutArtifactBinding,
    ResearchHoldoutAuthorization,
    ResearchHoldoutEvaluationCommand,
    ResearchHoldoutExecution,
    ResearchRun,
    ResearchTrial,
)
from app.services.research.candidate_registry import (
    require_strict_freeze_receipt,
    strict_freeze_receipt_fingerprint,
)
from app.services.research.canonical import canonical_json, content_hash
from app.services.research.database_clock import database_utc_now
from app.services.research.dataset_registry import require_verified_snapshot_integrity
from app.services.research.holdout_execution_contract import (
    REQUIRED_HOLDOUT_GATE_CODES,
    HoldoutExecutionCommand,
    HoldoutExecutionResult,
)
from app.services.research.statistics import calculate_deflated_sharpe

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SEALED_EVIDENCE_SCHEMA = "sealed-holdout-evidence-v1"
_SEALED_EVIDENCE_KIND = "sealed_holdout_evidence"
_SEALED_RECEIPT_KIND = "sealed_holdout_artifact_receipt"
_SEALED_RECEIPT_SCHEMA = "sealed-holdout-artifact-receipt-v1"
_SEALED_RECEIPT_MEDIA_TYPE = "application/vnd.ai-research.sealed-holdout-receipt+json"
_SEALED_RECEIPT_EXECUTOR = "sealed-evaluator-receipt-v1"
_PROMOTION_INPUT_SCHEMA = "promotion-input-v2"
_SECURITY_SCAN_KIND = "security_scan_evidence"
_SECURITY_SCAN_SCHEMA = "security-scan-evidence-v1"
_SECURITY_SCAN_POLICY_VERSION = "security-scan-policy-v1"
_SECURITY_SCANNER_IDENTITY = "research-security-scanner"
_SECURITY_SCANNER_IMAGE_DIGEST = f"sha256:{'5' * 64}"
_SECURITY_SCAN_ERROR_KEY = "_security_scan_authority_error"
_HOLDOUT_BINDING_SCHEMA = "holdout-artifact-binding-v1"
_RECONCILIATION_FENCE_ACTIONS = (
    "LEASE_EXPIRED_RECONCILING",
    "EXECUTION_OBSERVED_RECONCILING",
    "CHECKPOINT_UNKNOWN",
    "FINALIZE_UNKNOWN",
)
_RECONCILIATION_FENCE_CONTRACTS = {
    "LEASE_EXPIRED_RECONCILING": ("ACCEPTED", "HOLDOUT_CLAIM_LEASE_EXPIRED"),
    "EXECUTION_OBSERVED_RECONCILING": (
        "ACCEPTED",
        "HOLDOUT_EXECUTION_OBSERVED_RECOVERY",
    ),
    "CHECKPOINT_UNKNOWN": (
        "UNKNOWN",
        "HOLDOUT_FINALIZE_CHECKPOINT_COMMIT_OUTCOME_UNKNOWN",
    ),
    "FINALIZE_UNKNOWN": ("UNKNOWN", "HOLDOUT_FINALIZE_COMMIT_OUTCOME_UNKNOWN"),
}
_SEALED_PAYLOAD_KEYS = frozenset(
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
_DISCOVERY_TRIAL_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "execution_id",
        "command_hash",
        "candidate_id",
        "candidate_hash",
        "dataset",
        "result",
    }
)
_DISCOVERY_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "command_hash",
        "runner_identity",
        "image_digest",
        "status",
        "exit_code",
        "elapsed_milliseconds",
        "observed_market_performance",
        "returns",
        "error_code",
    }
)
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
_REQUIRED_GATE_CODES = (
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
)


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """A versioned server policy; caller-supplied threshold changes are rejected."""

    version: str
    min_deflated_sharpe: float
    max_drawdown: float
    bars_per_year: int = 252
    min_robustness_score: float = 0.80
    max_cost_bps: float = 5.0
    max_slippage_bps: float = 2.0
    max_turnover: float = 4.0
    min_capacity_notional: float = 100_000.0
    max_extreme_path_loss: float = 0.25
    executor_version: str = "promotion-gate-v2"

    def validate(self) -> None:
        """Reject unknown versions and any attempt to relax the server catalog."""

        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("PROMOTION_POLICY_INVALID")
        expected = _SERVER_POLICY_CATALOG.get(self.version)
        if expected is None:
            raise ValueError("PROMOTION_POLICY_UNSUPPORTED")
        numeric_values = (
            self.min_deflated_sharpe,
            self.max_drawdown,
            self.min_robustness_score,
            self.max_cost_bps,
            self.max_slippage_bps,
            self.max_turnover,
            self.min_capacity_notional,
            self.max_extreme_path_loss,
        )
        if (
            not isinstance(self.bars_per_year, int)
            or isinstance(self.bars_per_year, bool)
            or self.bars_per_year < 1
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
                for value in numeric_values
            )
            or self.max_drawdown < 0
            or not 0 <= self.min_deflated_sharpe <= 1
            or not 0 <= self.min_robustness_score <= 1
            or any(
                value < 0
                for value in (
                    self.max_cost_bps,
                    self.max_slippage_bps,
                    self.max_turnover,
                    self.min_capacity_notional,
                    self.max_extreme_path_loss,
                )
            )
        ):
            raise ValueError("PROMOTION_POLICY_INVALID")
        if asdict(self) != expected:
            raise ValueError("PROMOTION_POLICY_CONFIGURATION_MISMATCH")


_SERVER_POLICY_CATALOG: dict[str, dict[str, Any]] = {
    "promotion-v1": {
        "version": "promotion-v1",
        "min_deflated_sharpe": 0.95,
        "max_drawdown": 0.2,
        "bars_per_year": 252,
        "min_robustness_score": 0.80,
        "max_cost_bps": 5.0,
        "max_slippage_bps": 2.0,
        "max_turnover": 4.0,
        "min_capacity_notional": 100_000.0,
        "max_extreme_path_loss": 0.25,
        "executor_version": "promotion-gate-v2",
    }
}


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """One non-waivable hard-gate result."""

    code: str
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Result of one deterministic gate evaluation and append operation."""

    candidate_id: str
    policy_version: str
    input_evidence_hash: str
    decisions: tuple[GateOutcome, ...]
    eligible: bool
    strict_freeze_receipt_fingerprint: str | None = None

    @property
    def by_code(self) -> dict[str, GateOutcome]:
        return {decision.code: decision for decision in self.decisions}


class CommandPromotionMode(str, Enum):
    """Explicit command state the promotion transaction must re-authorize."""

    ACTIVE = "ACTIVE"
    RECONCILING = "RECONCILING"


@dataclass(frozen=True, slots=True)
class CommandPromotionAuthority:
    """Narrow, structured input whose fields are all rechecked under DB locks."""

    command_id: str
    candidate_id: str
    evaluation_id: str
    actor_identity: str
    evaluator_identity: str
    evaluator_version: str
    lease_generation: int
    mode: CommandPromotionMode
    lease_token_hash: str | None = None

    def __post_init__(self) -> None:
        text_values = (
            self.command_id,
            self.candidate_id,
            self.evaluation_id,
            self.actor_identity,
            self.evaluator_identity,
            self.evaluator_version,
        )
        active_token_valid = bool(
            self.mode is CommandPromotionMode.ACTIVE
            and isinstance(self.lease_token_hash, str)
            and _SHA256_HEX.fullmatch(self.lease_token_hash)
        )
        reconciling_token_valid = bool(
            self.mode is CommandPromotionMode.RECONCILING and self.lease_token_hash is None
        )
        if (
            not all(isinstance(value, str) and bool(value.strip()) for value in text_values)
            or type(self.lease_generation) is not int
            or self.lease_generation < 1
            or not isinstance(self.mode, CommandPromotionMode)
            or not (active_token_valid or reconciling_token_valid)
        ):
            raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")


@dataclass(frozen=True, slots=True)
class _EvaluationAuthority:
    outcome: GateOutcome
    decision_evaluation_id: str | None
    evaluation: ResearchEvaluation | None
    measurements: Mapping[str, Any]
    artifact_hash: str | None
    binding_fingerprint: str


class PromotionGateEngine:
    """Evaluate server-owned evidence and append immutable-intent decisions."""

    async def evaluate_and_record(
        self,
        *,
        candidate_id: str,
        policy: PromotionPolicy,
        evidence: Mapping[str, Any],
        evaluation_id: str | None = None,
        ai_review: Mapping[str, Any] | None = None,
    ) -> PromotionResult:
        """Append hard gates; caller evidence and AI commentary have no authority."""

        async with database.async_session_maker() as session:
            result = await self.evaluate_and_record_in_session(
                session,
                candidate_id=candidate_id,
                policy=policy,
                evidence=evidence,
                evaluation_id=evaluation_id,
                ai_review=ai_review,
            )
            await session.commit()
        return result

    async def evaluate_and_record_in_session(
        self,
        session: AsyncSession,
        *,
        candidate_id: str,
        policy: PromotionPolicy,
        evidence: Mapping[str, Any],
        evaluation_id: str | None = None,
        ai_review: Mapping[str, Any] | None = None,
    ) -> PromotionResult:
        """Stage only legacy non-command gates in the caller transaction."""

        del evidence, ai_review
        policy.validate()
        candidate = await _lock_promotion_candidate(session, candidate_id)
        # The epoch/candidate lock above preserves the shared
        # epoch -> candidate -> command order and prevents a request from
        # appearing between this fence and the decision writes.
        command_id = await session.scalar(
            select(ResearchHoldoutEvaluationCommand.id)
            .where(
                ResearchHoldoutEvaluationCommand.experiment_epoch_id
                == candidate.experiment_epoch_id,
                ResearchHoldoutEvaluationCommand.candidate_id == candidate.id,
            )
            .with_for_update()
        )
        if command_id is not None:
            raise ValueError("PROMOTION_CLAIM_FENCE_REQUIRED")
        return await self._evaluate_locked_and_record(
            session,
            candidate=candidate,
            policy=policy,
            evaluation_id=evaluation_id,
        )

    async def evaluate_command_and_record_in_session(
        self,
        session: AsyncSession,
        *,
        authority: CommandPromotionAuthority,
        policy: PromotionPolicy,
    ) -> PromotionResult:
        """Stage command-backed gates only after an independent locked lease check."""

        if not isinstance(authority, CommandPromotionAuthority):
            raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
        policy.validate()
        candidate = await _lock_promotion_candidate(session, authority.candidate_id)
        await _require_command_promotion_authority(
            session,
            candidate=candidate,
            authority=authority,
            policy=policy,
        )
        return await self._evaluate_locked_and_record(
            session,
            candidate=candidate,
            policy=policy,
            evaluation_id=authority.evaluation_id,
        )

    async def record_evaluator_receipt_in_session(
        self,
        session: AsyncSession,
        *,
        candidate_id: str,
        evaluation_id: str,
        policy: PromotionPolicy,
        result: HoldoutExecutionResult,
        strict_freeze_fingerprint: str,
    ) -> PromotionResult:
        """Record gates already evaluated inside the sealed deployment.

        The result contract contains no raw returns or trial paths.  This method
        only accepts the exact, command-bound 13-gate terminal receipt and never
        loads a database-backed sealed artifact body.
        """

        policy.validate()
        if type(result) is not HoldoutExecutionResult:
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        candidate = await _lock_promotion_candidate(session, candidate_id)
        freeze_receipt = await require_strict_freeze_receipt(session, candidate)
        evaluation = await session.get(ResearchEvaluation, evaluation_id, with_for_update=True)
        snapshot = result.snapshot
        terminal = snapshot.get("terminal_receipt")
        if (
            evaluation is None
            or evaluation.candidate_id != candidate.id
            or evaluation.policy_version != policy.version
            or evaluation.status != "RUNNING"
            or not isinstance(terminal, dict)
            or terminal.get("policy_version") != policy.version
            or strict_freeze_fingerprint != strict_freeze_receipt_fingerprint(freeze_receipt)
        ):
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        gate_values = terminal.get("gate_results")
        if not isinstance(gate_values, list):
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        outcomes = tuple(
            GateOutcome(
                code=str(gate["code"]),
                status=str(gate["status"]),
                reason=str(gate["reason_code"]),
            )
            for gate in gate_values
            if isinstance(gate, dict)
        )
        if (
            len(outcomes) != len(REQUIRED_HOLDOUT_GATE_CODES)
            or tuple(outcome.code for outcome in outcomes) != REQUIRED_HOLDOUT_GATE_CODES
        ):
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        input_evidence_hash = terminal.get("input_evidence_hash")
        if (
            not isinstance(input_evidence_hash, str)
            or not _SHA256_HEX.fullmatch(input_evidence_hash)
            or terminal.get("promotion_policy_hash") != promotion_policy_material_hash(policy)
        ):
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        safe_metrics = terminal.get("safe_metrics")
        if not isinstance(safe_metrics, dict):
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        await _require_safe_receipt_record_authority(
            session,
            candidate=candidate,
            evaluation=evaluation,
            policy=policy,
            result=result,
            safe_metrics=safe_metrics,
        )
        expected_outcomes = await _recomputed_safe_receipt_outcomes(
            session,
            candidate=candidate,
            evaluation=evaluation,
            policy=policy,
            safe_metrics=safe_metrics,
        )
        if outcomes != expected_outcomes:
            raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
        reused = await _reuse_existing_decision_set(
            session,
            candidate_id=candidate.id,
            evaluation_id=evaluation.id,
            policy=policy,
            input_evidence_hash=input_evidence_hash,
            outcomes=outcomes,
            executor_version=_SEALED_RECEIPT_EXECUTOR,
        )
        if not reused:
            for outcome in outcomes:
                session.add(
                    ResearchGateDecision(
                        candidate_id=candidate.id,
                        evaluation_id=evaluation.id,
                        gate_code=outcome.code,
                        policy_version=policy.version,
                        input_evidence_hash=input_evidence_hash,
                        status=outcome.status,
                        reason=outcome.reason,
                        executor_version=_SEALED_RECEIPT_EXECUTOR,
                    )
                )
            await session.flush()
        return PromotionResult(
            candidate_id=candidate.id,
            policy_version=policy.version,
            input_evidence_hash=input_evidence_hash,
            decisions=outcomes,
            eligible=all(outcome.status == "PASS" for outcome in outcomes),
            strict_freeze_receipt_fingerprint=strict_freeze_fingerprint,
        )

    async def _evaluate_locked_and_record(
        self,
        session: AsyncSession,
        *,
        candidate: ResearchCandidate,
        policy: PromotionPolicy,
        evaluation_id: str | None,
    ) -> PromotionResult:
        """Evaluate one already-locked candidate without owning transaction outcome."""

        freeze_receipt, receipt_fingerprint = await _strict_receipt_authority(
            session,
            candidate,
        )
        run = await session.get(ResearchRun, candidate.run_id)
        discovery_dataset = await session.get(
            ResearchDatasetSnapshot,
            candidate.dataset_snapshot_id,
        )
        authority = await _load_evaluation_authority(
            session,
            candidate=candidate,
            run=run,
            policy=policy,
            evaluation_id=evaluation_id,
            phase="RECORD",
            freeze_receipt=freeze_receipt,
        )
        input_evidence_hash = _input_evidence_hash(
            policy=policy,
            candidate=candidate,
            receipt_fingerprint=receipt_fingerprint,
            authority=authority,
        )
        outcomes = _evaluate(
            candidate,
            discovery_dataset,
            run,
            policy,
            authority,
            receipt_fingerprint=receipt_fingerprint,
        )
        reused = await _reuse_existing_decision_set(
            session,
            candidate_id=candidate.id,
            evaluation_id=authority.decision_evaluation_id,
            policy=policy,
            input_evidence_hash=input_evidence_hash,
            outcomes=outcomes,
        )
        if not reused:
            for outcome in outcomes:
                session.add(
                    ResearchGateDecision(
                        candidate_id=candidate.id,
                        evaluation_id=authority.decision_evaluation_id,
                        gate_code=outcome.code,
                        policy_version=policy.version,
                        input_evidence_hash=input_evidence_hash,
                        status=outcome.status,
                        reason=outcome.reason,
                        executor_version=policy.executor_version,
                    )
                )
            await session.flush()
        return PromotionResult(
            candidate_id=candidate.id,
            policy_version=policy.version,
            input_evidence_hash=input_evidence_hash,
            decisions=outcomes,
            eligible=all(outcome.status == "PASS" for outcome in outcomes),
            strict_freeze_receipt_fingerprint=receipt_fingerprint,
        )

    async def is_eligible(
        self,
        *,
        candidate_id: str,
        policy_version: str,
        input_evidence_hash: str,
    ) -> bool:
        """Recompute eligibility in a service-owned read transaction."""

        async with database.async_session_maker() as session:
            return await self.is_eligible_in_session(
                session,
                candidate_id=candidate_id,
                policy_version=policy_version,
                input_evidence_hash=input_evidence_hash,
            )

    async def is_eligible_in_session(
        self,
        session: AsyncSession,
        *,
        candidate_id: str,
        policy_version: str,
        input_evidence_hash: str,
    ) -> bool:
        """Lock and revalidate promotion authority inside the caller's transaction."""

        try:
            # This first snapshot only discovers an evaluation id.  The
            # authoritative read below re-queries and locks in the global
            # ledger -> evaluation -> decision order.
            decision_rows = tuple(
                (
                    await session.scalars(
                        select(ResearchGateDecision).where(
                            ResearchGateDecision.candidate_id == candidate_id,
                            ResearchGateDecision.policy_version == policy_version,
                            ResearchGateDecision.input_evidence_hash == input_evidence_hash,
                        )
                    )
                ).all()
            )
            evaluation_ids = {decision.evaluation_id for decision in decision_rows}
            if (
                len(decision_rows) != len(_REQUIRED_GATE_CODES)
                or len(evaluation_ids) != 1
                or None in evaluation_ids
            ):
                return False
            result = await self.read_result_in_session(
                session,
                candidate_id=candidate_id,
                evaluation_id=next(iter(evaluation_ids)),
                policy_version=policy_version,
                input_evidence_hash=input_evidence_hash,
            )
        except ValueError:
            return False
        return result.eligible

    async def read_result_in_session(
        self,
        session: AsyncSession,
        *,
        candidate_id: str,
        evaluation_id: str,
        policy_version: str,
        input_evidence_hash: str,
    ) -> PromotionResult:
        """Return one terminal result only after replaying every authority and gate."""

        try:
            policy = resolve_server_policy(policy_version)
        except ValueError:
            raise ValueError("PROMOTION_RESULT_INVALID") from None
        try:
            candidate = await _lock_promotion_candidate(session, candidate_id)
        except ValueError:
            raise ValueError("PROMOTION_RESULT_INVALID") from None
        freeze_receipt, receipt_fingerprint = await _strict_receipt_authority(
            session,
            candidate,
        )
        if receipt_fingerprint is None:
            raise ValueError("PROMOTION_RESULT_INVALID")
        evaluation = await session.get(ResearchEvaluation, evaluation_id, with_for_update=True)
        receipt_artifact = (
            await session.get(
                ResearchArtifact,
                evaluation.returns_artifact_id,
                with_for_update=True,
            )
            if evaluation is not None and evaluation.returns_artifact_id is not None
            else None
        )
        if receipt_artifact is not None and receipt_artifact.kind == _SEALED_RECEIPT_KIND:
            return await _read_evaluator_receipt_result(
                session,
                candidate=candidate,
                evaluation=evaluation,
                artifact=receipt_artifact,
                policy=policy,
                receipt_fingerprint=receipt_fingerprint,
                input_evidence_hash=input_evidence_hash,
            )
        run = await session.get(ResearchRun, candidate.run_id)
        discovery_dataset = await session.get(
            ResearchDatasetSnapshot,
            candidate.dataset_snapshot_id,
        )
        authority = await _load_evaluation_authority(
            session,
            candidate=candidate,
            run=run,
            policy=policy,
            evaluation_id=evaluation_id,
            phase="TERMINAL_READ",
            freeze_receipt=freeze_receipt,
        )
        if authority.outcome.status != "PASS" or authority.evaluation is None:
            raise ValueError("PROMOTION_RESULT_INVALID")
        persisted = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision)
                    .where(
                        ResearchGateDecision.candidate_id == candidate_id,
                        ResearchGateDecision.policy_version == policy_version,
                        ResearchGateDecision.input_evidence_hash == input_evidence_hash,
                    )
                    .with_for_update()
                )
            ).all()
        )
        if len(persisted) != len(_REQUIRED_GATE_CODES):
            raise ValueError("PROMOTION_RESULT_INVALID")
        decisions: dict[str, ResearchGateDecision] = {}
        for decision in persisted:
            if (
                decision.gate_code in decisions
                or decision.gate_code not in _REQUIRED_GATE_CODES
                or decision.evaluation_id != evaluation_id
            ):
                raise ValueError("PROMOTION_RESULT_INVALID")
            decisions[decision.gate_code] = decision
        if set(decisions) != set(_REQUIRED_GATE_CODES):
            raise ValueError("PROMOTION_RESULT_INVALID")
        expected_hash = _input_evidence_hash(
            policy=policy,
            candidate=candidate,
            receipt_fingerprint=receipt_fingerprint,
            authority=authority,
        )
        if expected_hash != input_evidence_hash:
            raise ValueError("PROMOTION_RESULT_INVALID")
        outcomes = _evaluate(
            candidate,
            discovery_dataset,
            run,
            policy,
            authority,
            receipt_fingerprint=receipt_fingerprint,
        )
        expected = {outcome.code: outcome for outcome in outcomes}
        for code in _REQUIRED_GATE_CODES:
            decision = decisions[code]
            outcome = expected[code]
            if (
                decision.evaluation_id != evaluation_id
                or decision.executor_version != policy.executor_version
                or decision.status != outcome.status
                or decision.reason != outcome.reason
            ):
                raise ValueError("PROMOTION_RESULT_INVALID")
        evaluation = authority.evaluation
        gate_inputs = dict(evaluation.gate_inputs or {})
        metrics = dict(evaluation.metrics or {})
        eligible = all(outcome.status == "PASS" for outcome in outcomes)
        if (
            evaluation.completed_at is None
            or evaluation.status != ("PASSED" if eligible else "REJECTED")
            or gate_inputs.get("input_evidence_hash") != input_evidence_hash
            or gate_inputs.get("strict_freeze_receipt_fingerprint") != receipt_fingerprint
            or gate_inputs.get("promotion_policy_hash") != promotion_policy_material_hash(policy)
            or gate_inputs.get("gate_statuses")
            != {outcome.code: outcome.status for outcome in outcomes}
            or metrics.get("promotion_eligible") is not eligible
        ):
            raise ValueError("PROMOTION_RESULT_INVALID")
        return PromotionResult(
            candidate_id=candidate_id,
            policy_version=policy_version,
            input_evidence_hash=input_evidence_hash,
            decisions=outcomes,
            eligible=eligible,
            strict_freeze_receipt_fingerprint=receipt_fingerprint,
        )


async def _require_safe_receipt_record_authority(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    evaluation: ResearchEvaluation,
    policy: PromotionPolicy,
    result: HoldoutExecutionResult,
    safe_metrics: Mapping[str, Any],
) -> None:
    """Rebind a safe terminal receipt to the locked control-plane authority graph."""

    command = await session.scalar(
        select(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.evaluation_id == evaluation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    execution = await session.scalar(
        select(ResearchHoldoutExecution)
        .where(ResearchHoldoutExecution.evaluation_id == evaluation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    binding = await session.scalar(
        select(ResearchHoldoutArtifactBinding)
        .where(ResearchHoldoutArtifactBinding.evaluation_id == evaluation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if command is None or execution is None or binding is None:
        raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
    artifact = await session.get(ResearchArtifact, binding.artifact_id, with_for_update=True)
    retained = await session.get(
        ResearchArtifactContent,
        binding.artifact_id,
        with_for_update=True,
    )
    claim_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == command.lease_generation,
                    ResearchHoldoutAccessAudit.action == "CLAIM_STARTED",
                )
                .with_for_update()
            )
        ).all()
    )
    if artifact is None or retained is not None or len(claim_audits) != 1:
        raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
    claim_audit = claim_audits[0]
    try:
        wire_command = HoldoutExecutionCommand.from_mapping(dict(execution.command_json))
        verified_result = HoldoutExecutionResult(payload=result.payload, _command=wire_command)
        terminal = verified_result.snapshot["terminal_receipt"]
        artifact_receipt = terminal["artifact_receipt"]
        expected_binding_hash = _command_checkpoint_binding_hash(
            command,
            artifact=artifact,
            claim_audit=claim_audit,
            binding=binding,
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID") from None
    if (
        command.status not in {"RUNNING", "RECONCILING"}
        or command.stage != "HOLDOUT_PENDING"
        or command.candidate_id != candidate.id
        or command.candidate_hash != candidate.candidate_hash
        or command.evaluation_id != evaluation.id
        or command.policy_version != policy.version
        or wire_command.snapshot.get("promotion_policy_hash")
        != promotion_policy_material_hash(policy)
        or execution.command_id != command.id
        or execution.operation_id != wire_command.snapshot["operation_id"]
        or execution.command_hash != wire_command.command_hash
        or execution.lease_owner != binding.lease_owner
        or execution.lease_generation != binding.lease_generation
        or execution.state != "OBSERVED"
        or execution.result_hash != sha256(verified_result.payload).hexdigest()
        or execution.result_json != verified_result.snapshot
        or binding.command_id != command.id
        or binding.evaluation_id != evaluation.id
        or binding.authorization_id != command.authorization_id
        or binding.lease_owner != claim_audit.actor_identity
        or binding.lease_generation != command.lease_generation
        or binding.authority_binding_hash != expected_binding_hash
        or artifact.kind != _SEALED_RECEIPT_KIND
        or artifact.schema_version != _SEALED_RECEIPT_SCHEMA
        or artifact.media_type != _SEALED_RECEIPT_MEDIA_TYPE
        or artifact.producer_identity != command.evaluator_identity
        or artifact.container_image_digest != command.evaluator_version
        or artifact.content_hash != artifact_receipt["artifact_hash"]
        or artifact.size_bytes != artifact_receipt["artifact_size_bytes"]
        or artifact.storage_uri
        != (f"controlled://sealed-holdout-artifact-receipt/{artifact_receipt['receipt_id']}")
        or terminal["safe_metrics"] != dict(safe_metrics)
    ):
        raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")


async def _recomputed_safe_receipt_outcomes(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    evaluation: ResearchEvaluation,
    policy: PromotionPolicy,
    safe_metrics: Mapping[str, Any],
) -> tuple[GateOutcome, ...]:
    """Cross-check every safe evaluator gate against the deployment policy catalog."""

    run = await session.get(ResearchRun, candidate.run_id, with_for_update=True)
    if run is None:
        raise ValueError("PROMOTION_EVALUATOR_RECEIPT_INVALID")
    findings, scan_error = await _authoritative_security_scan(
        session,
        candidate=candidate,
        evaluation=evaluation,
        run=run,
        scan_hash=str(safe_metrics["security_scan_hash"]),
    )
    gate_passes = {
        "CANDIDATE_FROZEN": True,
        "SEALED_HOLDOUT": True,
        "EVIDENCE_BINDING": True,
        "DEFLATED_SHARPE": float(safe_metrics["deflated_sharpe_probability"])
        >= policy.min_deflated_sharpe,
        "MAX_DRAWDOWN": float(safe_metrics["max_drawdown"]) <= policy.max_drawdown,
        "ROBUSTNESS": float(safe_metrics["robustness_score"]) >= policy.min_robustness_score,
        "COST": float(safe_metrics["cost_bps"]) <= policy.max_cost_bps,
        "SLIPPAGE": float(safe_metrics["slippage_bps"]) <= policy.max_slippage_bps,
        "TURNOVER": float(safe_metrics["turnover"]) <= policy.max_turnover,
        "CAPACITY": float(safe_metrics["capacity_notional"]) >= policy.min_capacity_notional,
        "EXTREME_PATH": float(safe_metrics["extreme_path_loss"]) <= policy.max_extreme_path_loss,
        "EXECUTION_SEMANTICS": safe_metrics["execution_semantics_match"] is True,
        "SECURITY_SCAN": scan_error is None
        and findings == safe_metrics["security_critical_findings"]
        and findings == 0,
    }
    return tuple(
        GateOutcome(
            code=code,
            status="PASS" if gate_passes[code] else "FAIL",
            reason=f"HOLDOUT_{code}_{'PASSED' if gate_passes[code] else 'FAILED'}",
        )
        for code in REQUIRED_HOLDOUT_GATE_CODES
    )


async def _read_evaluator_receipt_result(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    evaluation: ResearchEvaluation,
    artifact: ResearchArtifact,
    policy: PromotionPolicy,
    receipt_fingerprint: str,
    input_evidence_hash: str,
) -> PromotionResult:
    """Replay a safe evaluator result without retrieving sealed observations."""

    command = await session.scalar(
        select(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.evaluation_id == evaluation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    execution = await session.scalar(
        select(ResearchHoldoutExecution)
        .where(ResearchHoldoutExecution.evaluation_id == evaluation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    binding = await session.scalar(
        select(ResearchHoldoutArtifactBinding)
        .where(ResearchHoldoutArtifactBinding.evaluation_id == evaluation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    retained = await session.get(
        ResearchArtifactContent,
        artifact.id,
        with_for_update=True,
    )
    if (
        command is None
        or execution is None
        or binding is None
        or retained is not None
        or command.authorization_id is None
    ):
        raise ValueError("PROMOTION_RESULT_INVALID")
    authorization = await session.get(
        ResearchHoldoutAuthorization,
        command.authorization_id,
        with_for_update=True,
    )
    epoch = await session.get(
        ResearchExperimentEpoch,
        command.experiment_epoch_id,
        with_for_update=True,
    )
    claim_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == command.lease_generation,
                    ResearchHoldoutAccessAudit.action == "CLAIM_STARTED",
                )
                .with_for_update()
            )
        ).all()
    )
    checkpoint_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == command.lease_generation,
                    ResearchHoldoutAccessAudit.action == "CHECKPOINT_RECORDED",
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
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == command.lease_generation,
                    ResearchHoldoutAccessAudit.action == "EXECUTION_OBSERVED_RECONCILING",
                )
                .with_for_update()
            )
        ).all()
    )
    if (
        authorization is None
        or epoch is None
        or len(claim_audits) != 1
        or len(checkpoint_audits) != 1
        or len(recovery_audits) > 1
    ):
        raise ValueError("PROMOTION_RESULT_INVALID")
    claim_audit = claim_audits[0]
    checkpoint_audit = checkpoint_audits[0]
    checkpoint_actor = recovery_audits[0].actor_identity if recovery_audits else binding.lease_owner

    expected_command = {
        "schema_version": "holdout-execution-command-v2",
        "operation_id": execution.operation_id,
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
        "promotion_policy_hash": promotion_policy_material_hash(policy),
        "evaluator_identity": command.evaluator_identity,
        "evaluator_image_digest": command.evaluator_version,
        "lease_generation": command.lease_generation,
    }
    try:
        wire_command = HoldoutExecutionCommand.from_mapping(expected_command)
        result = HoldoutExecutionResult.from_mapping(
            dict(execution.result_json or {}),
            command=wire_command,
        )
        terminal = result.snapshot["terminal_receipt"]
        artifact_receipt = terminal["artifact_receipt"]
        gate_values = terminal["gate_results"]
        expected_binding_hash = _command_checkpoint_binding_hash(
            command,
            artifact=artifact,
            claim_audit=claim_audit,
            binding=binding,
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("PROMOTION_RESULT_INVALID") from None

    started_at = _utc_datetime(command.started_at)
    completed_at = _utc_datetime(evaluation.completed_at)
    if (
        command.status != "SUCCEEDED"
        or command.stage != "HOLDOUT_PENDING"
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
        or command.candidate_id != candidate.id
        or command.candidate_hash != candidate.candidate_hash
        or command.freeze_receipt_fingerprint != receipt_fingerprint
        or command.policy_version != policy.version
        or candidate.freeze_status != "FROZEN"
        or evaluation.candidate_id != candidate.id
        or evaluation.authorization_id != authorization.id
        or evaluation.experiment_epoch_id != command.experiment_epoch_id
        or evaluation.dataset_snapshot_id != command.dataset_snapshot_id
        or evaluation.evaluator_identity != command.evaluator_identity
        or evaluation.evaluator_version != command.evaluator_version
        or evaluation.policy_version != policy.version
        or evaluation.evaluation_type != "SEALED_HOLDOUT"
        or evaluation.returns_artifact_id != artifact.id
        or evaluation.status not in {"PASSED", "REJECTED"}
        or started_at is None
        or completed_at is None
        or epoch.status != "CLOSED"
        or epoch.selected_candidate_id != candidate.id
        or _utc_datetime(epoch.closed_at) != completed_at
        or authorization.status != "CONSUMED"
        or authorization.experiment_epoch_id != command.experiment_epoch_id
        or authorization.candidate_id != candidate.id
        or authorization.candidate_hash != command.candidate_hash
        or authorization.dataset_snapshot_id != command.dataset_snapshot_id
        or authorization.policy_version != policy.version
        or authorization.evaluator_identity != command.evaluator_identity
        or authorization.capability_profile_id != command.capability_profile_id
        or authorization.capability_profile_version != command.capability_profile_version
        or authorization.capability_evidence_hash != command.capability_evidence_hash
        or authorization.issued_by != binding.lease_owner
        or claim_audit.actor_identity != binding.lease_owner
        or claim_audit.result != "ACCEPTED"
        or claim_audit.reason_code != "HOLDOUT_CLAIM_STARTED"
        or claim_audit.evaluation_id != evaluation.id
        or claim_audit.authorization_id != authorization.id
        or checkpoint_audit.actor_identity != checkpoint_actor
        or checkpoint_audit.result != "ACCEPTED"
        or checkpoint_audit.reason_code != "HOLDOUT_FINALIZE_CHECKPOINT_RECORDED"
        or binding.command_id != command.id
        or binding.authorization_id != authorization.id
        or binding.evaluation_id != evaluation.id
        or binding.artifact_id != artifact.id
        or binding.lease_owner != claim_audit.actor_identity
        or binding.lease_generation != command.lease_generation
        or binding.authority_binding_hash != expected_binding_hash
        or execution.command_id != command.id
        or execution.evaluation_id != evaluation.id
        or execution.lease_owner != binding.lease_owner
        or execution.lease_generation != command.lease_generation
        or execution.command_hash != wire_command.command_hash
        or execution.command_json != wire_command.snapshot
        or execution.state not in {"OBSERVED", "SETTLED"}
        or execution.result_hash != sha256(result.payload).hexdigest()
        or execution.error_code is not None
        or execution.observed_at is None
        or (execution.state == "OBSERVED" and execution.settled_at is not None)
        or (execution.state == "SETTLED" and execution.settled_at is None)
        or result.snapshot["status"] != "SUCCEEDED"
        or terminal["policy_version"] != policy.version
        or terminal["promotion_policy_hash"] != promotion_policy_material_hash(policy)
        or terminal["input_evidence_hash"] != input_evidence_hash
        or artifact_receipt["artifact_hash"] != artifact.content_hash
        or artifact_receipt["artifact_size_bytes"] != artifact.size_bytes
        or artifact.kind != _SEALED_RECEIPT_KIND
        or artifact.schema_version != _SEALED_RECEIPT_SCHEMA
        or artifact.media_type != _SEALED_RECEIPT_MEDIA_TYPE
        or artifact.producer_identity != command.evaluator_identity
        or artifact.container_image_digest != command.evaluator_version
        or artifact.storage_uri
        != (f"controlled://sealed-holdout-artifact-receipt/{artifact_receipt['receipt_id']}")
    ):
        raise ValueError("PROMOTION_RESULT_INVALID")

    outcomes = tuple(
        GateOutcome(
            code=str(gate["code"]),
            status=str(gate["status"]),
            reason=str(gate["reason_code"]),
        )
        for gate in gate_values
    )
    persisted = tuple(
        (
            await session.scalars(
                select(ResearchGateDecision)
                .where(
                    ResearchGateDecision.candidate_id == candidate.id,
                    ResearchGateDecision.policy_version == policy.version,
                    ResearchGateDecision.input_evidence_hash == input_evidence_hash,
                )
                .with_for_update()
            )
        ).all()
    )
    decisions = {decision.gate_code: decision for decision in persisted}
    eligible = all(outcome.status == "PASS" for outcome in outcomes)
    gate_inputs = dict(evaluation.gate_inputs or {})
    metrics = dict(evaluation.metrics or {})
    if (
        len(outcomes) != len(REQUIRED_HOLDOUT_GATE_CODES)
        or tuple(outcome.code for outcome in outcomes) != REQUIRED_HOLDOUT_GATE_CODES
        or len(persisted) != len(REQUIRED_HOLDOUT_GATE_CODES)
        or set(decisions) != set(REQUIRED_HOLDOUT_GATE_CODES)
        or any(
            decisions[outcome.code].evaluation_id != evaluation.id
            or decisions[outcome.code].executor_version != _SEALED_RECEIPT_EXECUTOR
            or decisions[outcome.code].status != outcome.status
            or decisions[outcome.code].reason != outcome.reason
            for outcome in outcomes
        )
        or evaluation.status != ("PASSED" if eligible else "REJECTED")
        or metrics != {"promotion_eligible": eligible}
        or gate_inputs
        != {
            "input_evidence_hash": input_evidence_hash,
            "sealed_dataset_hash": command.sealed_dataset_hash,
            "strict_freeze_receipt_fingerprint": receipt_fingerprint,
            "promotion_policy_hash": promotion_policy_material_hash(policy),
            "gate_statuses": {outcome.code: outcome.status for outcome in outcomes},
        }
    ):
        raise ValueError("PROMOTION_RESULT_INVALID")
    return PromotionResult(
        candidate_id=candidate.id,
        policy_version=policy.version,
        input_evidence_hash=input_evidence_hash,
        decisions=outcomes,
        eligible=eligible,
        strict_freeze_receipt_fingerprint=receipt_fingerprint,
    )


async def _reuse_existing_decision_set(
    session: AsyncSession,
    *,
    candidate_id: str,
    evaluation_id: str | None,
    policy: PromotionPolicy,
    input_evidence_hash: str,
    outcomes: tuple[GateOutcome, ...],
    executor_version: str | None = None,
) -> bool:
    """Reuse only one exact, complete decision set; reject crash residue or tampering."""

    result = await session.execute(
        select(ResearchGateDecision)
        .where(
            ResearchGateDecision.candidate_id == candidate_id,
            ResearchGateDecision.policy_version == policy.version,
            ResearchGateDecision.input_evidence_hash == input_evidence_hash,
        )
        .with_for_update()
    )
    persisted = tuple(result.scalars())
    if not persisted:
        return False

    expected = {outcome.code: outcome for outcome in outcomes}
    exact_codes: set[str] = set()
    all_rows_exact = True
    for decision in persisted:
        outcome = expected.get(decision.gate_code)
        if (
            outcome is None
            or decision.gate_code in exact_codes
            or decision.evaluation_id != evaluation_id
            or decision.status != outcome.status
            or decision.reason != outcome.reason
            or decision.executor_version != (executor_version or policy.executor_version)
        ):
            all_rows_exact = False
            break
        exact_codes.add(decision.gate_code)

    if all_rows_exact and exact_codes == set(_REQUIRED_GATE_CODES):
        return True
    if all_rows_exact and exact_codes < set(_REQUIRED_GATE_CODES):
        raise ValueError("PROMOTION_DECISION_SET_PARTIAL")
    raise ValueError("PROMOTION_DECISION_SET_CONFLICT")


def resolve_server_policy(version: str) -> PromotionPolicy:
    """Return the immutable deployment-owned policy for a supported version."""

    configured = _SERVER_POLICY_CATALOG.get(version)
    if configured is None:
        raise ValueError("PROMOTION_POLICY_UNSUPPORTED")
    policy = PromotionPolicy(**configured)
    policy.validate()
    return policy


def promotion_policy_material_hash(policy: PromotionPolicy) -> str:
    """Hash every immutable policy parameter used by the sealed evaluator gates."""

    if not isinstance(policy, PromotionPolicy):
        raise ValueError("PROMOTION_POLICY_INVALID")
    policy.validate()
    return content_hash(
        {
            "schema_version": "promotion-policy-material-v1",
            "policy": asdict(policy),
        }
    )


async def _lock_promotion_candidate(
    session: AsyncSession,
    candidate_id: str,
) -> ResearchCandidate:
    """Lock epoch before candidate, then revalidate the untrusted epoch lookup."""

    epoch_id = await session.scalar(
        select(ResearchCandidate.experiment_epoch_id).where(ResearchCandidate.id == candidate_id)
    )
    if epoch_id is None:
        raise ValueError("PROMOTION_CANDIDATE_NOT_FOUND")
    epoch = await session.scalar(
        select(ResearchExperimentEpoch)
        .where(ResearchExperimentEpoch.id == epoch_id)
        .with_for_update()
    )
    candidate = await session.scalar(
        select(ResearchCandidate)
        .where(ResearchCandidate.id == candidate_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if candidate is None:
        raise ValueError("PROMOTION_CANDIDATE_NOT_FOUND")
    if epoch is None or candidate.experiment_epoch_id != epoch.id:
        raise ValueError("PROMOTION_CANDIDATE_EPOCH_CONFLICT")
    return candidate


async def _require_command_promotion_authority(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    authority: CommandPromotionAuthority,
    policy: PromotionPolicy,
) -> None:
    """Re-lock every command authority row and fail closed on any mismatch."""

    command = await session.scalar(
        select(ResearchHoldoutEvaluationCommand)
        .where(ResearchHoldoutEvaluationCommand.id == authority.command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if command is None or command.authorization_id is None:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
    authorization = await session.scalar(
        select(ResearchHoldoutAuthorization)
        .where(ResearchHoldoutAuthorization.id == command.authorization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    evaluation = await session.scalar(
        select(ResearchEvaluation)
        .where(ResearchEvaluation.id == authority.evaluation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    claim_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == authority.lease_generation,
                    ResearchHoldoutAccessAudit.action == "CLAIM_STARTED",
                )
                .with_for_update()
            )
        ).all()
    )
    binding = await session.scalar(
        select(ResearchHoldoutArtifactBinding)
        .where(ResearchHoldoutArtifactBinding.command_id == authority.command_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if authorization is None or evaluation is None or len(claim_audits) != 1 or binding is None:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
    claim_audit = claim_audits[0]
    artifact = await session.scalar(
        select(ResearchArtifact)
        .where(ResearchArtifact.id == binding.artifact_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    retained = await session.scalar(
        select(ResearchArtifactContent)
        .where(ResearchArtifactContent.artifact_id == binding.artifact_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    checkpoint_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.command_id == command.id,
                    ResearchHoldoutAccessAudit.lease_generation == authority.lease_generation,
                    ResearchHoldoutAccessAudit.action == "CHECKPOINT_RECORDED",
                )
                .with_for_update()
            )
        ).all()
    )
    transition_audits = tuple(
        (
            await session.scalars(
                select(ResearchHoldoutAccessAudit)
                .where(
                    ResearchHoldoutAccessAudit.requested_command_id == command.id,
                    ResearchHoldoutAccessAudit.action.in_(_RECONCILIATION_FENCE_ACTIONS),
                )
                .with_for_update()
            )
        ).all()
    )
    epoch = await session.scalar(
        select(ResearchExperimentEpoch)
        .where(ResearchExperimentEpoch.id == command.experiment_epoch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if artifact is None or retained is None or len(checkpoint_audits) != 1 or epoch is None:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
    checkpoint_audit = checkpoint_audits[0]
    try:
        content = bytes(retained.content)
        digest = sha256(content).hexdigest()
        decoded = json.loads(content)
        binding_expiry = _utc_datetime(binding.lease_expires_at)
        expected_binding_hash = _command_checkpoint_binding_hash(
            command,
            artifact=artifact,
            claim_audit=claim_audit,
            binding=binding,
        )
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID") from exc
    if not isinstance(decoded, dict):
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
    measurements = decoded.get("measurements")
    expected_payload = {
        "schema_version": _SEALED_EVIDENCE_SCHEMA,
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
    started_at = _utc_datetime(command.started_at)
    issued_at = _utc_datetime(authorization.issued_at)
    consumed_at = _utc_datetime(authorization.consumed_at)
    authorization_expiry = _utc_datetime(authorization.expires_at)
    evaluation_started_at = _utc_datetime(evaluation.started_at)
    disclosed_at = _utc_datetime(epoch.disclosed_at)
    binding_created_at = _utc_datetime(binding.created_at)
    checkpoint_actor = binding.lease_owner
    if len(transition_audits) == 1 and transition_audits[0].action == (
        "EXECUTION_OBSERVED_RECONCILING"
    ):
        checkpoint_actor = transition_audits[0].actor_identity
    base_matches = bool(
        command.user_id == candidate.user_id
        and command.run_id == candidate.run_id
        and command.candidate_id == candidate.id == authority.candidate_id
        and command.candidate_hash == candidate.candidate_hash
        and command.expected_candidate_state == "FROZEN"
        and candidate.freeze_status == "FROZEN"
        and command.experiment_epoch_id == candidate.experiment_epoch_id
        and command.evaluation_id == evaluation.id == authority.evaluation_id
        and command.authorization_id == evaluation.authorization_id
        and command.policy_version == policy.version
        and command.stage == "HOLDOUT_PENDING"
        and command.lease_generation == authority.lease_generation
        and command.attempt_count == authority.lease_generation
        and started_at is not None
        and command.evaluator_identity == authority.evaluator_identity
        and command.evaluator_version == authority.evaluator_version
        and authorization.id == command.authorization_id
        and authorization.status == "CONSUMED"
        and authorization.experiment_epoch_id == command.experiment_epoch_id
        and authorization.candidate_id == command.candidate_id
        and authorization.candidate_hash == command.candidate_hash
        and authorization.dataset_snapshot_id == command.dataset_snapshot_id
        and authorization.policy_version == command.policy_version
        and authorization.evaluator_identity == command.evaluator_identity
        and authorization.capability_profile_id == command.capability_profile_id
        and authorization.capability_profile_version == command.capability_profile_version
        and authorization.capability_evidence_hash == command.capability_evidence_hash
        and authorization.issued_by == binding.lease_owner
        and bool(_SHA256_HEX.fullmatch(authorization.token_hash))
        and authorization.token_hash != authority.lease_token_hash
        and issued_at == started_at
        and consumed_at == started_at
        and authorization_expiry is not None
        and authorization_expiry > started_at
        and binding.command_id == command.id
        and binding.user_id == command.user_id
        and binding.run_id == command.run_id
        and binding.authorization_id == command.authorization_id
        and binding.evaluation_id == evaluation.id
        and binding.experiment_epoch_id == command.experiment_epoch_id
        and binding.candidate_id == command.candidate_id
        and binding.dataset_snapshot_id == command.dataset_snapshot_id
        and binding.artifact_id == evaluation.returns_artifact_id
        and binding.claim_access_audit_id == claim_audit.id
        and binding.request_hash == command.request_hash
        and binding.lease_generation == authority.lease_generation
        and binding.binding_schema_version == _HOLDOUT_BINDING_SCHEMA
        and binding.authority_binding_hash == expected_binding_hash
        and binding_expiry is not None
        and evaluation.experiment_epoch_id == command.experiment_epoch_id
        and evaluation.candidate_id == command.candidate_id
        and evaluation.dataset_snapshot_id == command.dataset_snapshot_id
        and evaluation.evaluation_type == "SEALED_HOLDOUT"
        and evaluation.evaluator_identity == authority.evaluator_identity
        and evaluation.evaluator_version == authority.evaluator_version
        and evaluation.policy_version == command.policy_version
        and evaluation.returns_artifact_id == binding.artifact_id
        and (evaluation.metrics or {}) == {}
        and (evaluation.gate_inputs or {}) == {}
        and evaluation.status == "RUNNING"
        and evaluation_started_at == started_at
        and evaluation.completed_at is None
        and epoch.status == "DISCLOSED"
        and epoch.selected_candidate_id == command.candidate_id
        and disclosed_at == started_at
        and epoch.closed_at is None
        and claim_audit.action == "CLAIM_STARTED"
        and claim_audit.result == "ACCEPTED"
        and claim_audit.reason_code == "HOLDOUT_CLAIM_STARTED"
        and claim_audit.actor_identity == binding.lease_owner
        and claim_audit.evaluator_version == command.evaluator_version
        and claim_audit.requested_command_id == command.id
        and claim_audit.command_id == command.id
        and claim_audit.authorization_id == authorization.id
        and claim_audit.evaluation_id == evaluation.id
        and claim_audit.experiment_epoch_id == command.experiment_epoch_id
        and claim_audit.candidate_id == command.candidate_id
        and claim_audit.dataset_snapshot_id == command.dataset_snapshot_id
        and claim_audit.lease_generation == authority.lease_generation
        and claim_audit.trace_id == command.trace_id
        and _utc_datetime(claim_audit.created_at) == started_at
        and artifact.kind == _SEALED_EVIDENCE_KIND
        and artifact.content_hash == digest
        and artifact.size_bytes == len(content)
        and artifact.media_type == "application/json"
        and artifact.schema_version == _SEALED_EVIDENCE_SCHEMA
        and artifact.producer_identity == command.evaluator_identity
        and artifact.container_image_digest == command.evaluator_version
        and artifact.storage_uri == f"controlled://sealed-holdout-evidence/{digest}"
        and retained.artifact_id == artifact.id
        and _utc_datetime(artifact.created_at) == binding_created_at
        and _utc_datetime(retained.created_at) == binding_created_at
        and checkpoint_audit.action == "CHECKPOINT_RECORDED"
        and checkpoint_audit.result == "ACCEPTED"
        and checkpoint_audit.reason_code == "HOLDOUT_FINALIZE_CHECKPOINT_RECORDED"
        and checkpoint_audit.actor_identity == checkpoint_actor
        and checkpoint_audit.evaluator_version == command.evaluator_version
        and checkpoint_audit.requested_command_id == command.id
        and checkpoint_audit.command_id == command.id
        and checkpoint_audit.authorization_id == authorization.id
        and checkpoint_audit.evaluation_id == evaluation.id
        and checkpoint_audit.experiment_epoch_id == command.experiment_epoch_id
        and checkpoint_audit.candidate_id == command.candidate_id
        and checkpoint_audit.dataset_snapshot_id == command.dataset_snapshot_id
        and checkpoint_audit.lease_generation == authority.lease_generation
        and checkpoint_audit.trace_id == command.trace_id
        and _utc_datetime(checkpoint_audit.created_at) == binding_created_at
        and isinstance(measurements, dict)
        and set(decoded) == _SEALED_PAYLOAD_KEYS
        and set(measurements).issubset(_MEASUREMENT_KEYS)
        and decoded == expected_payload
        and canonical_json(decoded).encode("utf-8") == content
    )
    if not base_matches:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")

    if authority.mode is CommandPromotionMode.ACTIVE:
        now = await database_utc_now(session)
        expires_at = _utc_datetime(command.lease_expires_at)
        active_matches = bool(
            command.status == "RUNNING"
            and command.error_code is None
            and command.lease_owner == authority.actor_identity
            and binding.lease_owner == authority.actor_identity
            and command.lease_token_hash == authority.lease_token_hash
            and command.lease_heartbeat_at is not None
            and expires_at is not None
            and expires_at > now
            and not transition_audits
        )
        if not active_matches:
            raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
        return

    reconciling_matches = bool(
        authority.mode is CommandPromotionMode.RECONCILING
        and command.status == "RECONCILING"
        and bool(command.error_code)
        and command.lease_owner is None
        and command.lease_token_hash is None
        and command.lease_expires_at is None
        and command.lease_heartbeat_at is None
        and _reconciliation_fence_matches(
            command,
            binding=binding,
            audits=transition_audits,
        )
    )
    if not reconciling_matches:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")


def _command_checkpoint_binding_hash(
    command: ResearchHoldoutEvaluationCommand,
    *,
    artifact: ResearchArtifact,
    claim_audit: ResearchHoldoutAccessAudit,
    binding: ResearchHoldoutArtifactBinding,
) -> str:
    lease_expires_at = _utc_datetime(binding.lease_expires_at)
    if lease_expires_at is None:
        raise ValueError("PROMOTION_CLAIM_AUTHORITY_INVALID")
    return content_hash(
        {
            "schema_version": _HOLDOUT_BINDING_SCHEMA,
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
            "lease_owner": binding.lease_owner,
            "lease_generation": binding.lease_generation,
            "lease_expires_at": lease_expires_at,
        }
    )


def _reconciliation_fence_matches(
    command: ResearchHoldoutEvaluationCommand,
    *,
    binding: ResearchHoldoutArtifactBinding,
    audits: tuple[ResearchHoldoutAccessAudit, ...],
) -> bool:
    if len(audits) != 1:
        return False
    audit = audits[0]
    contract = _RECONCILIATION_FENCE_CONTRACTS.get(audit.action)
    if contract is None:
        return False
    expected_result, expected_reason = contract
    actor_matches = (
        isinstance(audit.actor_identity, str) and bool(audit.actor_identity.strip())
        if audit.action in {"LEASE_EXPIRED_RECONCILING", "EXECUTION_OBSERVED_RECONCILING"}
        else audit.actor_identity == binding.lease_owner
    )
    if (
        audit.result != expected_result
        or audit.reason_code != expected_reason
        or command.error_code != expected_reason
        or not actor_matches
        or audit.evaluator_version != command.evaluator_version
        or audit.requested_command_id != command.id
        or _utc_datetime(audit.created_at) != _utc_datetime(command.updated_at)
    ):
        return False
    if audit.action in {"LEASE_EXPIRED_RECONCILING", "EXECUTION_OBSERVED_RECONCILING"}:
        return bool(
            audit.command_id == command.id
            and audit.authorization_id == command.authorization_id
            and audit.evaluation_id == command.evaluation_id
            and audit.experiment_epoch_id == command.experiment_epoch_id
            and audit.candidate_id == command.candidate_id
            and audit.dataset_snapshot_id == command.dataset_snapshot_id
            and audit.lease_generation == binding.lease_generation
            and audit.trace_id == command.trace_id
        )
    return bool(
        audit.command_id is None
        and audit.authorization_id is None
        and audit.evaluation_id is None
        and audit.experiment_epoch_id is None
        and audit.candidate_id is None
        and audit.dataset_snapshot_id is None
        and audit.lease_generation is None
        and audit.trace_id is None
    )


async def _strict_receipt_authority(
    session: AsyncSession,
    candidate: ResearchCandidate,
) -> tuple[ResearchCandidateFreezeReceipt | None, str | None]:
    """Return the fully replayed strict receipt and fingerprint or fail closed."""

    try:
        receipt = await require_strict_freeze_receipt(session, candidate)
    except ValueError:
        return None, None
    return receipt, strict_freeze_receipt_fingerprint(receipt)


async def _load_evaluation_authority(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    run: ResearchRun | None,
    policy: PromotionPolicy,
    evaluation_id: str | None,
    phase: str,
    freeze_receipt: ResearchCandidateFreezeReceipt | None,
) -> _EvaluationAuthority:
    if evaluation_id is None:
        return _blocked_authority("evaluation_required", None)
    evaluation = await session.get(ResearchEvaluation, evaluation_id, with_for_update=True)
    if evaluation is None:
        return _blocked_authority("evaluation_not_found", evaluation_id)
    decision_evaluation_id = evaluation.id if evaluation.candidate_id == candidate.id else None
    if evaluation.candidate_id != candidate.id:
        return _blocked_authority(
            "evaluation_candidate_mismatch",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    authorization = (
        await session.get(
            ResearchHoldoutAuthorization,
            evaluation.authorization_id,
            with_for_update=True,
        )
        if evaluation.authorization_id is not None
        else None
    )
    if authorization is None:
        return _blocked_authority(
            "authorization_required",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    if authorization.status != "CONSUMED" or authorization.consumed_at is None:
        return _blocked_authority(
            "authorization_not_consumed",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    if run is None:
        return _blocked_authority(
            "candidate_run_missing",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    if phase == "RECORD":
        valid_evaluation_status = evaluation.status == "RUNNING"
        valid_epoch_status = "DISCLOSED"
    elif phase == "TERMINAL_READ":
        valid_evaluation_status = evaluation.status in {"PASSED", "REJECTED"}
        valid_epoch_status = "CLOSED"
    else:
        raise ValueError("PROMOTION_AUTHORITY_PHASE_INVALID")
    if not valid_evaluation_status:
        return _blocked_authority(
            "evaluation_status_invalid",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    if (
        run.id != candidate.run_id
        or run.user_id != candidate.user_id
        or run.experiment_epoch_id != candidate.experiment_epoch_id
        or run.dataset_snapshot_id != candidate.dataset_snapshot_id
        or run.promotion_policy_version != policy.version
        or evaluation.experiment_epoch_id != candidate.experiment_epoch_id
        or evaluation.evaluation_type != "SEALED_HOLDOUT"
        or evaluation.policy_version != policy.version
        or not evaluation.evaluator_identity.strip()
        or not evaluation.evaluator_version.strip()
        or evaluation.started_at is None
    ):
        return _blocked_authority(
            "evaluation_binding_mismatch",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    if (
        authorization.id != evaluation.authorization_id
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
        return _blocked_authority(
            "authorization_binding_mismatch",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    epoch = await session.get(
        ResearchExperimentEpoch,
        candidate.experiment_epoch_id,
        with_for_update=True,
    )
    if (
        epoch is None
        or epoch.selected_candidate_id != candidate.id
        or epoch.status != valid_epoch_status
    ):
        return _blocked_authority(
            "epoch_binding_mismatch",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    if not _valid_evaluation_timeline(
        authorization=authorization,
        evaluation=evaluation,
        epoch=epoch,
        phase=phase,
    ):
        return _blocked_authority(
            "evaluation_timeline_invalid",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    sealed_dataset = await session.get(
        ResearchDatasetSnapshot,
        evaluation.dataset_snapshot_id,
    )
    if (
        sealed_dataset is None
        or sealed_dataset.user_id != candidate.user_id
        or sealed_dataset.partition_kind != "SEALED_HOLDOUT"
    ):
        return _blocked_authority(
            "sealed_dataset_binding_mismatch",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    try:
        require_verified_snapshot_integrity(sealed_dataset)
    except ValueError:
        return _blocked_authority(
            "sealed_dataset_integrity_invalid",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
        )
    measurements, artifact_hash, artifact_error = await _sealed_artifact_measurements(
        session,
        candidate=candidate,
        evaluation=evaluation,
        authorization=authorization,
        sealed_dataset=sealed_dataset,
        policy=policy,
    )
    if artifact_error is not None:
        return _blocked_authority(
            artifact_error,
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
            artifact_hash=artifact_hash,
        )
    if freeze_receipt is None:
        return _blocked_authority(
            "strict_freeze_receipt_required",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
            artifact_hash=artifact_hash,
        )
    trial_sharpes, ledger_error = await _authoritative_trial_sharpes(
        session,
        candidate=candidate,
        receipt=freeze_receipt,
        policy=policy,
    )
    if ledger_error is not None:
        return _blocked_authority(
            ledger_error,
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
            artifact_hash=artifact_hash,
        )
    claimed_trial_sharpes = measurements.get("trial_sharpes")
    if type(claimed_trial_sharpes) is not list or claimed_trial_sharpes != trial_sharpes:
        return _blocked_authority(
            "trial_sharpes_ledger_mismatch",
            evaluation_id,
            decision_evaluation_id=decision_evaluation_id,
            artifact_hash=artifact_hash,
        )
    measurements = {**measurements, "trial_sharpes": trial_sharpes}
    measurements = await _bind_security_scan_measurements(
        session,
        candidate=candidate,
        evaluation=evaluation,
        run=run,
        measurements=measurements,
    )
    binding = {
        "schema_version": _SEALED_EVIDENCE_SCHEMA,
        "evaluation_id": evaluation.id,
        "authorization_id": authorization.id,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "experiment_epoch_id": candidate.experiment_epoch_id,
        "dataset_snapshot_id": sealed_dataset.id,
        "sealed_dataset_hash": sealed_dataset.content_hash,
        "policy_version": policy.version,
        "evaluator_identity": evaluation.evaluator_identity,
        "evaluator_version": evaluation.evaluator_version,
        "artifact_hash": artifact_hash,
    }
    fingerprint = content_hash(binding)
    return _EvaluationAuthority(
        outcome=GateOutcome(
            "SEALED_HOLDOUT",
            "PASS",
            f"authority_fingerprint={fingerprint}",
        ),
        decision_evaluation_id=evaluation.id,
        evaluation=evaluation,
        measurements=measurements,
        artifact_hash=artifact_hash,
        binding_fingerprint=fingerprint,
    )


def _blocked_authority(
    reason: str,
    requested_evaluation_id: str | None,
    *,
    decision_evaluation_id: str | None = None,
    artifact_hash: str | None = None,
) -> _EvaluationAuthority:
    binding = {
        "schema_version": _SEALED_EVIDENCE_SCHEMA,
        "requested_evaluation_id": requested_evaluation_id,
        "status": "BLOCKED",
        "reason": reason,
        "artifact_hash": artifact_hash,
    }
    return _EvaluationAuthority(
        outcome=GateOutcome("SEALED_HOLDOUT", "BLOCKED", reason),
        decision_evaluation_id=decision_evaluation_id,
        evaluation=None,
        measurements={},
        artifact_hash=artifact_hash,
        binding_fingerprint=content_hash(binding),
    )


def _valid_evaluation_timeline(
    *,
    authorization: ResearchHoldoutAuthorization,
    evaluation: ResearchEvaluation,
    epoch: ResearchExperimentEpoch,
    phase: str,
) -> bool:
    issued_at = _utc_datetime(authorization.issued_at)
    consumed_at = _utc_datetime(authorization.consumed_at)
    disclosed_at = _utc_datetime(epoch.disclosed_at)
    started_at = _utc_datetime(evaluation.started_at)
    if None in {issued_at, consumed_at, disclosed_at, started_at}:
        return False
    if not issued_at <= consumed_at == disclosed_at <= started_at:
        return False
    completed_at = _utc_datetime(evaluation.completed_at)
    closed_at = _utc_datetime(epoch.closed_at)
    if phase == "RECORD":
        return completed_at is None and closed_at is None
    if phase == "TERMINAL_READ":
        return (
            completed_at is not None
            and closed_at is not None
            and started_at <= completed_at <= closed_at
        )
    return False


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _sealed_artifact_measurements(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    evaluation: ResearchEvaluation,
    authorization: ResearchHoldoutAuthorization,
    sealed_dataset: ResearchDatasetSnapshot,
    policy: PromotionPolicy,
) -> tuple[Mapping[str, Any], str | None, str | None]:
    if evaluation.returns_artifact_id is None:
        return {}, None, "sealed_evidence_artifact_required"
    artifact = await session.get(
        ResearchArtifact,
        evaluation.returns_artifact_id,
        with_for_update=True,
    )
    blob = await session.get(
        ResearchArtifactContent,
        evaluation.returns_artifact_id,
        with_for_update=True,
    )
    if artifact is None or blob is None:
        return {}, None, "sealed_evidence_artifact_not_retained"
    content = bytes(blob.content)
    digest = sha256(content).hexdigest()
    storage = urlsplit(artifact.storage_uri)
    if (
        artifact.kind != _SEALED_EVIDENCE_KIND
        or artifact.schema_version != _SEALED_EVIDENCE_SCHEMA
        or artifact.media_type != "application/json"
        or artifact.producer_identity != evaluation.evaluator_identity
        or artifact.container_image_digest != evaluation.evaluator_version
        or storage.scheme != "controlled"
        or not storage.netloc
        or storage.query
        or storage.fragment
        or artifact.content_hash != digest
        or artifact.size_bytes != len(content)
    ):
        return {}, digest, "sealed_evidence_artifact_invalid"
    try:
        payload = json.loads(content.decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or set(payload) != _SEALED_PAYLOAD_KEYS
            or canonical_json(payload).encode("utf-8") != content
        ):
            raise ValueError
        measurements = payload["measurements"]
        if not isinstance(measurements, dict) or not set(measurements).issubset(_MEASUREMENT_KEYS):
            raise ValueError
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, digest, "sealed_evidence_payload_invalid"
    expected = {
        "schema_version": _SEALED_EVIDENCE_SCHEMA,
        "authorization_id": authorization.id,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "experiment_epoch_id": candidate.experiment_epoch_id,
        "dataset_snapshot_id": sealed_dataset.id,
        "sealed_dataset_hash": sealed_dataset.content_hash,
        "policy_version": policy.version,
        "evaluator_identity": evaluation.evaluator_identity,
        "evaluator_version": evaluation.evaluator_version,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return {}, digest, "sealed_evidence_payload_binding_mismatch"
    return dict(measurements), digest, None


async def _authoritative_trial_sharpes(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    receipt: ResearchCandidateFreezeReceipt,
    policy: PromotionPolicy,
) -> tuple[list[float], str | None]:
    """Derive the full cross-trial Sharpe distribution from the frozen ledger."""

    result = await session.execute(
        select(ResearchTrial)
        .where(
            ResearchTrial.user_id == candidate.user_id,
            ResearchTrial.run_id == candidate.run_id,
            ResearchTrial.candidate_id == candidate.id,
            ResearchTrial.counts_as_market_trial.is_(True),
        )
        .order_by(ResearchTrial.ordinal.asc(), ResearchTrial.id.asc())
        .with_for_update()
    )
    trials = tuple(result.scalars())
    if len(trials) != receipt.market_trial_count or not trials:
        return [], "trial_ledger_count_mismatch"

    sharpes: list[float] = []
    for trial in trials:
        returns = await _retained_trial_returns(session, candidate=candidate, trial=trial)
        if returns is None:
            return [], "trial_ledger_evidence_invalid"
        sharpe = _annualized_trial_sharpe(returns, bars_per_year=policy.bars_per_year)
        if sharpe is None:
            return [], "trial_sharpe_derivation_invalid"
        sharpes.append(sharpe)
    return sharpes, None


async def _retained_trial_returns(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    trial: ResearchTrial,
) -> list[float] | None:
    """Read one ledger trial's canonical retained returns without trusting metrics JSON."""

    if (
        trial.status != "SUCCEEDED"
        or not trial.observed_market_performance
        or trial.returns_artifact_id is None
    ):
        return None
    artifact = await session.get(
        ResearchArtifact,
        trial.returns_artifact_id,
        with_for_update=True,
    )
    retained = await session.get(
        ResearchArtifactContent,
        trial.returns_artifact_id,
        with_for_update=True,
    )
    if artifact is None or retained is None:
        return None
    content = bytes(retained.content)
    if (
        artifact.kind != "discovery_trial_evidence"
        or artifact.schema_version != "discovery-trial-evidence-v1"
        or artifact.media_type != "application/json"
        or artifact.size_bytes != len(content)
        or artifact.content_hash != sha256(content).hexdigest()
    ):
        return None
    try:
        payload = json.loads(content.decode("utf-8"))
        result = payload["result"]
        metrics = dict(trial.metrics or {})
        returns = result["returns"]
        if (
            not isinstance(payload, dict)
            or set(payload) != _DISCOVERY_TRIAL_PAYLOAD_KEYS
            or canonical_json(payload).encode("utf-8") != content
            or payload["schema_version"] != "discovery-trial-evidence-v1"
            or payload["execution_id"] != metrics.get("execution_id")
            or payload["command_hash"] != trial.input_hash
            or payload["candidate_id"] != candidate.id
            or payload["candidate_hash"] != candidate.candidate_hash
            or not isinstance(result, dict)
            or set(result) != _DISCOVERY_RESULT_KEYS
            or result["schema_version"] != "discovery-execution-result-v1"
            or result["command_hash"] != trial.input_hash
            or result["status"] != trial.status
            or result["observed_market_performance"] is not True
            or metrics.get("sample_count") != len(returns)
            or not _finite_sequence(returns)
        ):
            return None
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return [float(value) for value in returns]


def _annualized_trial_sharpe(
    returns: Sequence[float],
    *,
    bars_per_year: int,
) -> float | None:
    """Return a deterministic annualized sample Sharpe for ledger comparison."""

    if not _finite_sequence(returns) or len(returns) < 2:
        return None
    try:
        values = [float(value) for value in returns]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        if variance <= 0:
            return None
        value = mean / sqrt(variance) * sqrt(bars_per_year)
    except (OverflowError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not isfinite(value):
        return None
    return round(value, 12)


async def _bind_security_scan_measurements(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    evaluation: ResearchEvaluation,
    run: ResearchRun,
    measurements: Mapping[str, Any],
) -> dict[str, Any]:
    """Replace self-reported scan claims only after retained-artifact verification."""

    bound = dict(measurements)
    scan_hash = bound.get("security_scan_hash")
    claimed_findings = bound.get("security_critical_findings")
    if scan_hash is None or claimed_findings is None:
        return bound
    if not isinstance(scan_hash, str) or _SHA256_HEX.fullmatch(scan_hash) is None:
        return bound
    findings, error = await _authoritative_security_scan(
        session,
        candidate=candidate,
        evaluation=evaluation,
        run=run,
        scan_hash=scan_hash,
    )
    if error is not None:
        bound[_SECURITY_SCAN_ERROR_KEY] = error
    elif claimed_findings != findings:
        bound[_SECURITY_SCAN_ERROR_KEY] = "security_scan_artifact_claim_mismatch"
    else:
        bound["security_critical_findings"] = findings
    return bound


async def _authoritative_security_scan(
    session: AsyncSession,
    *,
    candidate: ResearchCandidate,
    evaluation: ResearchEvaluation,
    run: ResearchRun,
    scan_hash: str,
) -> tuple[int | None, str | None]:
    artifact = await session.scalar(
        select(ResearchArtifact)
        .where(
            ResearchArtifact.kind == _SECURITY_SCAN_KIND,
            ResearchArtifact.content_hash == scan_hash,
        )
        .with_for_update()
    )
    if artifact is None:
        return None, "security_scan_artifact_not_retained"
    retained = await session.get(
        ResearchArtifactContent,
        artifact.id,
        with_for_update=True,
    )
    if retained is None:
        return None, "security_scan_artifact_not_retained"
    profile = await session.scalar(
        select(ResearchCapabilityProfile)
        .where(
            ResearchCapabilityProfile.profile_id == run.capability_profile_id,
            ResearchCapabilityProfile.version == run.capability_profile_version,
        )
        .with_for_update()
    )
    sandbox = profile.sandbox_capabilities if profile is not None else None
    stage_images = sandbox.get("stage_image_digests") if isinstance(sandbox, Mapping) else None
    scanner_image = stage_images.get("scanner") if isinstance(stage_images, Mapping) else None
    evaluation_started_at = _utc_datetime(evaluation.started_at)
    profile_verified_at = _utc_datetime(profile.verified_at) if profile is not None else None
    profile_expires_at = _utc_datetime(profile.expires_at) if profile is not None else None
    if (
        profile is None
        or profile.evidence_hash != run.capability_evidence_hash
        or _SHA256_HEX.fullmatch(profile.evidence_hash) is None
        or evaluation_started_at is None
        or profile_verified_at is None
        or profile_expires_at is None
        or not profile_verified_at <= evaluation_started_at < profile_expires_at
        or scanner_image != _SECURITY_SCANNER_IMAGE_DIGEST
    ):
        return None, "security_scan_capability_binding_mismatch"
    content = bytes(retained.content)
    storage = urlsplit(artifact.storage_uri)
    if (
        artifact.schema_version != _SECURITY_SCAN_SCHEMA
        or artifact.media_type != "application/json"
        or artifact.producer_identity != _SECURITY_SCANNER_IDENTITY
        or artifact.container_image_digest != scanner_image
        or storage.scheme != "controlled"
        or not storage.netloc
        or storage.query
        or storage.fragment
        or artifact.size_bytes != len(content)
        or artifact.content_hash != sha256(content).hexdigest()
    ):
        return None, "security_scan_artifact_invalid"
    try:
        payload = json.loads(content.decode("utf-8"))
        findings = payload["critical_findings"]
        if (
            not isinstance(payload, dict)
            or set(payload) != _SECURITY_SCAN_PAYLOAD_KEYS
            or canonical_json(payload).encode("utf-8") != content
            or isinstance(findings, bool)
            or not isinstance(findings, int)
            or findings < 0
        ):
            return None, "security_scan_artifact_invalid"
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "security_scan_artifact_invalid"

    code = await session.get(ResearchArtifact, candidate.code_artifact_id, with_for_update=True)
    dependency = await session.get(
        ResearchArtifact,
        candidate.dependency_artifact_id,
        with_for_update=True,
    )
    if code is None or dependency is None:
        return None, "security_scan_artifact_binding_mismatch"
    expected = {
        "schema_version": _SECURITY_SCAN_SCHEMA,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "code_artifact_id": code.id,
        "code_hash": code.content_hash,
        "dependency_artifact_id": dependency.id,
        "dependency_hash": dependency.content_hash,
        "evaluator_identity": evaluation.evaluator_identity,
        "evaluator_version": evaluation.evaluator_version,
        "scan_policy_version": _SECURITY_SCAN_POLICY_VERSION,
        "scanner_identity": _SECURITY_SCANNER_IDENTITY,
        "scanner_image_digest": scanner_image,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return None, "security_scan_artifact_binding_mismatch"
    return findings, None


def _input_evidence_hash(
    *,
    policy: PromotionPolicy,
    candidate: ResearchCandidate,
    receipt_fingerprint: str | None,
    authority: _EvaluationAuthority,
) -> str:
    return content_hash(
        {
            "schema_version": _PROMOTION_INPUT_SCHEMA,
            "policy": asdict(policy),
            "candidate_id": candidate.id,
            "candidate_hash": candidate.candidate_hash,
            "strict_freeze_receipt_fingerprint": receipt_fingerprint,
            "sealed_evaluation_authority_fingerprint": authority.binding_fingerprint,
            "sealed_evidence_artifact_hash": authority.artifact_hash,
        }
    )


def _evaluate(
    candidate: ResearchCandidate,
    discovery_dataset: ResearchDatasetSnapshot | None,
    run: ResearchRun | None,
    policy: PromotionPolicy,
    authority: _EvaluationAuthority,
    *,
    receipt_fingerprint: str | None,
) -> tuple[GateOutcome, ...]:
    frozen = GateOutcome(
        code="CANDIDATE_FROZEN",
        status="PASS" if receipt_fingerprint is not None else "FAIL",
        reason=f"strict_freeze_receipt_fingerprint={receipt_fingerprint}"
        if receipt_fingerprint is not None
        else "strict_freeze_receipt_required",
    )
    if authority.outcome.status != "PASS":
        unknown = tuple(
            GateOutcome(code, "UNKNOWN", "sealed_holdout_not_passed")
            for code in _REQUIRED_GATE_CODES
            if code not in {"CANDIDATE_FROZEN", "SEALED_HOLDOUT"}
        )
        return (frozen, authority.outcome, *unknown)
    evidence = authority.measurements
    binding = _binding_outcome(candidate, discovery_dataset, run, evidence)
    return (
        frozen,
        authority.outcome,
        binding,
        _dsr_outcome(binding, policy, evidence),
        _maximum_outcome("MAX_DRAWDOWN", "max_drawdown", policy.max_drawdown, evidence),
        _minimum_outcome(
            "ROBUSTNESS",
            "robustness_score",
            policy.min_robustness_score,
            evidence,
            upper_bound=1.0,
        ),
        _maximum_outcome("COST", "cost_bps", policy.max_cost_bps, evidence),
        _maximum_outcome("SLIPPAGE", "slippage_bps", policy.max_slippage_bps, evidence),
        _maximum_outcome("TURNOVER", "turnover", policy.max_turnover, evidence),
        _minimum_outcome(
            "CAPACITY",
            "capacity_notional",
            policy.min_capacity_notional,
            evidence,
        ),
        _maximum_outcome(
            "EXTREME_PATH",
            "extreme_path_loss",
            policy.max_extreme_path_loss,
            evidence,
        ),
        _execution_semantics_outcome(evidence),
        _security_scan_outcome(evidence),
    )


def _binding_outcome(
    candidate: ResearchCandidate,
    dataset: ResearchDatasetSnapshot | None,
    run: ResearchRun | None,
    evidence: Mapping[str, Any],
) -> GateOutcome:
    required = (
        "returns",
        "trial_sharpes",
        "discovery_dataset_snapshot_hash",
        "cost_model_hash",
        "environment_hash",
        "capability_evidence_hash",
    )
    missing = tuple(key for key in required if key not in evidence or evidence[key] is None)
    if missing:
        return GateOutcome("EVIDENCE_BINDING", "UNKNOWN", f"missing:{','.join(missing)}")
    if dataset is None or run is None:
        return GateOutcome("EVIDENCE_BINDING", "UNKNOWN", "candidate_dependency_missing")
    expected = {
        "discovery_dataset_snapshot_hash": dataset.content_hash,
        "cost_model_hash": candidate.cost_model_hash,
        "environment_hash": candidate.environment_hash,
        "capability_evidence_hash": run.capability_evidence_hash,
    }
    mismatched = tuple(key for key, value in expected.items() if evidence.get(key) != value)
    if mismatched:
        return GateOutcome("EVIDENCE_BINDING", "FAIL", f"mismatch:{','.join(mismatched)}")
    if not _finite_sequence(evidence["returns"]) or not _finite_sequence(evidence["trial_sharpes"]):
        return GateOutcome("EVIDENCE_BINDING", "UNKNOWN", "returns_or_trial_sharpes_invalid")
    return GateOutcome("EVIDENCE_BINDING", "PASS", "candidate_data_cost_environment_profile_bound")


def _dsr_outcome(
    binding: GateOutcome,
    policy: PromotionPolicy,
    evidence: Mapping[str, Any],
) -> GateOutcome:
    if binding.status != "PASS":
        return GateOutcome("DEFLATED_SHARPE", "UNKNOWN", "evidence_binding_not_passed")
    try:
        value = calculate_deflated_sharpe(
            evidence["returns"],
            trial_sharpes=evidence["trial_sharpes"],
            bars_per_year=policy.bars_per_year,
        )
    except (TypeError, ValueError):
        return GateOutcome("DEFLATED_SHARPE", "UNKNOWN", "deflated_sharpe_inputs_invalid")
    if value >= policy.min_deflated_sharpe:
        return GateOutcome("DEFLATED_SHARPE", "PASS", f"value={value:.8f}")
    return GateOutcome("DEFLATED_SHARPE", "FAIL", f"value={value:.8f}")


def _maximum_outcome(
    code: str,
    key: str,
    threshold: float,
    evidence: Mapping[str, Any],
) -> GateOutcome:
    value = _gate_number(evidence, key)
    if value is None:
        return GateOutcome(code, "UNKNOWN", _missing_or_invalid_reason(evidence, key))
    reason = f"value={value:.8f};threshold={threshold:.8f};operator=lte"
    return GateOutcome(code, "PASS" if value <= threshold else "FAIL", reason)


def _minimum_outcome(
    code: str,
    key: str,
    threshold: float,
    evidence: Mapping[str, Any],
    *,
    upper_bound: float | None = None,
) -> GateOutcome:
    value = _gate_number(evidence, key)
    if value is None or (upper_bound is not None and value > upper_bound):
        return GateOutcome(code, "UNKNOWN", _missing_or_invalid_reason(evidence, key))
    reason = f"value={value:.8f};threshold={threshold:.8f};operator=gte"
    return GateOutcome(code, "PASS" if value >= threshold else "FAIL", reason)


def _execution_semantics_outcome(evidence: Mapping[str, Any]) -> GateOutcome:
    key = "execution_semantics_match"
    if key not in evidence or evidence[key] is None:
        return GateOutcome("EXECUTION_SEMANTICS", "UNKNOWN", f"missing:{key}")
    if not isinstance(evidence[key], bool):
        return GateOutcome("EXECUTION_SEMANTICS", "UNKNOWN", f"invalid:{key}")
    return GateOutcome(
        "EXECUTION_SEMANTICS",
        "PASS" if evidence[key] else "FAIL",
        f"match={str(evidence[key]).lower()}",
    )


def _security_scan_outcome(evidence: Mapping[str, Any]) -> GateOutcome:
    authority_error = evidence.get(_SECURITY_SCAN_ERROR_KEY)
    if isinstance(authority_error, str):
        return GateOutcome("SECURITY_SCAN", "UNKNOWN", authority_error)
    findings_key = "security_critical_findings"
    hash_key = "security_scan_hash"
    missing = tuple(key for key in (findings_key, hash_key) if evidence.get(key) is None)
    if missing:
        return GateOutcome("SECURITY_SCAN", "UNKNOWN", f"missing:{','.join(missing)}")
    findings = evidence[findings_key]
    scan_hash = evidence[hash_key]
    if (
        isinstance(findings, bool)
        or not isinstance(findings, int)
        or findings < 0
        or not isinstance(scan_hash, str)
        or _SHA256_HEX.fullmatch(scan_hash) is None
    ):
        return GateOutcome("SECURITY_SCAN", "UNKNOWN", "security_scan_evidence_invalid")
    return GateOutcome(
        "SECURITY_SCAN",
        "PASS" if findings == 0 else "FAIL",
        f"critical_findings={findings};scan_hash={scan_hash}",
    )


def _gate_number(evidence: Mapping[str, Any], key: str) -> float | None:
    value = evidence.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or float(value) < 0
    ):
        return None
    return float(value)


def _missing_or_invalid_reason(evidence: Mapping[str, Any], key: str) -> str:
    return f"missing:{key}" if key not in evidence or evidence[key] is None else f"invalid:{key}"


def _finite_sequence(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return False
    try:
        return all(not isinstance(item, bool) and isfinite(float(item)) for item in value)
    except (TypeError, ValueError):
        return False
