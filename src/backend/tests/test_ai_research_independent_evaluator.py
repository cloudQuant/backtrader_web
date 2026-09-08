from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import sqrt

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from app.db.database import async_session_maker
from app.models.ai_research_v2 import (
    ResearchArtifact,
    ResearchArtifactContent,
    ResearchCandidate,
    ResearchCandidateFreezeReceipt,
    ResearchDatasetSnapshot,
    ResearchEvaluation,
    ResearchExperimentEpoch,
    ResearchGateDecision,
    ResearchHoldoutAuthorization,
    ResearchRun,
    ResearchTrial,
)
from app.models.user import User
from app.services.research.candidate_registry import CandidateRegistry
from app.services.research.canonical import canonical_json
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
)
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.holdout_authorization import HoldoutAuthorizationRegistry
from app.services.research.hypothesis_registry import HypothesisRegistry
from app.services.research.independent_evaluator import IndependentEvaluator
from app.services.research.promotion import PromotionGateEngine, PromotionPolicy


@pytest.mark.asyncio
async def test_independent_evaluator_consumes_bound_token_writes_only_evidence_and_closes_epoch(
    auth_user,
) -> None:
    context = await _strict_context(auth_user, "evaluator-success")
    holdout_registry = HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context))
    issued = await holdout_registry.issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )
    before = context["candidate"]
    evidence_artifact = await _create_sealed_evidence_artifact(
        context,
        authorization_id=issued.authorization.id,
    )

    evaluator = IndependentEvaluator(dataset_registry=_dataset_registry(context))
    evaluation = await evaluator.evaluate_holdout(
        authorization_token=issued.token,
        candidate_id=context["candidate"].id,
        candidate_hash=context["candidate"].candidate_hash,
        dataset_snapshot_id=context["sealed"].id,
        policy=PromotionPolicy(version="promotion-v1", min_deflated_sharpe=0.95, max_drawdown=0.2),
        evaluator_identity="ai_research_evaluator",
        evaluator_version="evaluator-image@sha256:test",
        evidence=_evidence(context),
        returns_artifact_id=evidence_artifact.id,
    )

    assert evaluation.status == "PASSED"
    assert evaluation.metrics["promotion_eligible"] is True
    assert evaluation.gate_inputs["strict_freeze_receipt_fingerprint"]
    assert "sealed://" not in str(evaluation.gate_inputs)
    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, before.id)
        epoch = await session.get(ResearchExperimentEpoch, context["epoch"].id)
        stored_evaluation = await session.get(ResearchEvaluation, evaluation.id)
    assert candidate is not None
    assert candidate.candidate_hash == before.candidate_hash
    assert candidate.freeze_status == "FROZEN"
    assert epoch is not None and epoch.status == "CLOSED"
    assert (
        stored_evaluation is not None
        and stored_evaluation.authorization_id == issued.authorization.id
    )

    with pytest.raises(ValueError, match="HOLDOUT_AUTHORIZATION_NOT_ACTIVE"):
        await evaluator.evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=PromotionPolicy(
                version="promotion-v1", min_deflated_sharpe=0.95, max_drawdown=0.2
            ),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence={},
        )


@pytest.mark.asyncio
async def test_resume_evaluation_recovers_finish_crash_without_duplicate_gate_decisions(
    auth_user,
    monkeypatch,
) -> None:
    stranded = await _stranded_evaluation(auth_user, "resume-success", monkeypatch)
    evaluator = stranded["evaluator"]
    evaluation = stranded["evaluation"]
    before_decision_ids = stranded["decision_ids"]
    assert isinstance(evaluator, IndependentEvaluator)
    assert isinstance(evaluation, ResearchEvaluation)

    with pytest.raises(ValueError, match="^PROMOTION_POLICY_CONFIGURATION_MISMATCH$"):
        await evaluator.resume_evaluation(
            evaluation_id=evaluation.id,
            policy=PromotionPolicy(
                version="promotion-v1",
                min_deflated_sharpe=0.95,
                max_drawdown=0.9,
            ),
            evaluator_identity="ai_research_evaluator",
        )

    with pytest.raises(ValueError, match="^INDEPENDENT_EVALUATOR_IDENTITY_MISMATCH$"):
        await evaluator.resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="untrusted-recovery-worker",
        )

    resumed, concurrent = await asyncio.gather(
        evaluator.resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
        ),
        IndependentEvaluator(dataset_registry=stranded["datasets"]).resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
        ),
    )
    repeated = await IndependentEvaluator(
        dataset_registry=stranded["datasets"]
    ).resume_evaluation(
        evaluation_id=evaluation.id,
        policy=_promotion_policy(),
        evaluator_identity="ai_research_evaluator",
    )

    assert resumed.id == concurrent.id == repeated.id == evaluation.id
    assert resumed.status == concurrent.status == repeated.status == "PASSED"
    assert resumed.metrics == {"promotion_eligible": True}
    async with async_session_maker() as session:
        epoch = await session.get(ResearchExperimentEpoch, evaluation.experiment_epoch_id)
        decision_ids = set(
            await session.scalars(
                select(ResearchGateDecision.id).where(
                    ResearchGateDecision.evaluation_id == evaluation.id
                )
            )
        )
        assert epoch is not None and epoch.status == "CLOSED"
        assert epoch.closed_at is not None
    assert decision_ids == before_decision_ids
    assert len(decision_ids) == 13


@pytest.mark.asyncio
async def test_resume_evaluation_rejects_coordinated_terminal_hash_tampering(
    auth_user,
    monkeypatch,
) -> None:
    """Terminal replay derives its hash instead of trusting mutually consistent rows."""

    stranded = await _stranded_evaluation(auth_user, "resume-terminal-tamper", monkeypatch)
    evaluator = stranded["evaluator"]
    evaluation = stranded["evaluation"]
    assert isinstance(evaluator, IndependentEvaluator)
    assert isinstance(evaluation, ResearchEvaluation)
    completed = await evaluator.resume_evaluation(
        evaluation_id=evaluation.id,
        policy=_promotion_policy(),
        evaluator_identity="ai_research_evaluator",
    )
    forged_hash = "f" * 64
    async with async_session_maker() as session:
        stored = await session.get(ResearchEvaluation, completed.id)
        decisions = list(
            await session.scalars(
                select(ResearchGateDecision).where(
                    ResearchGateDecision.evaluation_id == completed.id
                )
            )
        )
        assert stored is not None and len(decisions) == 13
        stored.gate_inputs = {**stored.gate_inputs, "input_evidence_hash": forged_hash}
        for decision in decisions:
            decision.input_evidence_hash = forged_hash
        await session.commit()

    with pytest.raises(ValueError, match="^PROMOTION_RESULT_INVALID$"):
        await IndependentEvaluator(
            dataset_registry=stranded["datasets"]
        ).resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("residue", "error_code"),
    [
        ("partial", "PROMOTION_DECISION_SET_PARTIAL"),
        ("conflict", "PROMOTION_DECISION_SET_CONFLICT"),
    ],
)
async def test_resume_evaluation_fails_closed_for_invalid_gate_residue(
    auth_user,
    monkeypatch,
    residue: str,
    error_code: str,
) -> None:
    stranded = await _stranded_evaluation(auth_user, f"resume-{residue}", monkeypatch)
    evaluator = stranded["evaluator"]
    evaluation = stranded["evaluation"]
    assert isinstance(evaluator, IndependentEvaluator)
    assert isinstance(evaluation, ResearchEvaluation)
    async with async_session_maker() as session:
        decisions = list(
            await session.scalars(
                select(ResearchGateDecision).where(
                    ResearchGateDecision.evaluation_id == evaluation.id
                )
            )
        )
        assert len(decisions) == 13
        if residue == "partial":
            await session.delete(decisions[-1])
        else:
            decisions[-1].reason = "forged-resume-residue"
        await session.commit()

    with pytest.raises(ValueError, match=f"^{error_code}$"):
        await evaluator.resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchEvaluation, evaluation.id)
        epoch = await session.get(ResearchExperimentEpoch, evaluation.experiment_epoch_id)
        decision_count = len(
            list(
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == evaluation.id
                    )
                )
            )
        )
        assert stored is not None and stored.status == "FAILED"
        assert stored.completed_at is not None
        assert stored.metrics == {"promotion_eligible": False, "error_code": error_code}
        assert epoch is not None and epoch.status == "CLOSED"
        assert epoch.closed_at is not None
    assert decision_count == (12 if residue == "partial" else 13)

    repeated = await evaluator.resume_evaluation(
        evaluation_id=evaluation.id,
        policy=_promotion_policy(),
        evaluator_identity="ai_research_evaluator",
    )
    assert repeated.status == "FAILED"
    assert repeated.metrics["error_code"] == error_code


@pytest.mark.asyncio
async def test_resume_evaluation_keeps_running_after_transient_gate_failure(
    auth_user,
    monkeypatch,
) -> None:
    """An unknown infrastructure failure remains retryable instead of consuming recovery."""

    stranded = await _stranded_evaluation(auth_user, "resume-transient", monkeypatch)
    evaluation = stranded["evaluation"]
    assert isinstance(evaluation, ResearchEvaluation)

    async def raise_timeout(_engine, **_kwargs):
        raise TimeoutError("temporary promotion database timeout")

    monkeypatch.setattr(PromotionGateEngine, "evaluate_and_record", raise_timeout)
    with pytest.raises(TimeoutError, match="temporary promotion database timeout"):
        await IndependentEvaluator(
            dataset_registry=stranded["datasets"]
        ).resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchEvaluation, evaluation.id)
        epoch = await session.get(ResearchExperimentEpoch, evaluation.experiment_epoch_id)
        decision_count = len(
            list(
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == evaluation.id
                    )
                )
            )
        )
    assert stored is not None and stored.status == "RUNNING"
    assert stored.completed_at is None and not stored.gate_inputs and not stored.metrics
    assert epoch is not None and epoch.status == "DISCLOSED" and epoch.closed_at is None
    assert decision_count == 13


@pytest.mark.asyncio
async def test_resume_evaluation_fails_closed_when_final_gate_replay_detects_tampering(
    auth_user,
    monkeypatch,
) -> None:
    """The closing transaction replays canonical gates after the external gate commit."""

    stranded = await _stranded_evaluation(auth_user, "resume-final-replay", monkeypatch)
    evaluation = stranded["evaluation"]
    assert isinstance(evaluation, ResearchEvaluation)
    original_evaluate = PromotionGateEngine.evaluate_and_record

    async def evaluate_then_tamper(engine, **kwargs):
        result = await original_evaluate(engine, **kwargs)
        async with async_session_maker() as session:
            decision = await session.scalar(
                select(ResearchGateDecision).where(
                    ResearchGateDecision.evaluation_id == evaluation.id
                )
            )
            assert decision is not None
            decision.reason = "forged-between-gate-commit-and-finalization"
            await session.commit()
        return result

    monkeypatch.setattr(PromotionGateEngine, "evaluate_and_record", evaluate_then_tamper)
    with pytest.raises(ValueError, match="^PROMOTION_RESULT_INVALID$"):
        await IndependentEvaluator(
            dataset_registry=stranded["datasets"]
        ).resume_evaluation(
            evaluation_id=evaluation.id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
        )

    async with async_session_maker() as session:
        stored = await session.get(ResearchEvaluation, evaluation.id)
        epoch = await session.get(ResearchExperimentEpoch, evaluation.experiment_epoch_id)
    assert stored is not None and stored.status == "FAILED"
    assert stored.metrics == {
        "promotion_eligible": False,
        "error_code": "PROMOTION_RESULT_INVALID",
    }
    assert epoch is not None and epoch.status == "CLOSED" and epoch.closed_at is not None


@pytest.mark.asyncio
async def test_independent_evaluator_requires_an_injected_live_dataset_registry(auth_user) -> None:
    """A default evaluator cannot consume a valid sealed token without a resolver."""

    context = await _strict_context(auth_user, "evaluator-resolver")
    issued = await HoldoutAuthorizationRegistry(dataset_registry=_dataset_registry(context)).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )

    with pytest.raises(ValueError, match="DATASET_OBJECT_RESOLVER_REQUIRED"):
        await IndependentEvaluator().evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=PromotionPolicy(
                version="promotion-v1", min_deflated_sharpe=0.95, max_drawdown=0.2
            ),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence=_evidence(context),
        )


@pytest.mark.asyncio
async def test_independent_evaluator_rejects_a_drifted_sealed_object_before_evaluation(
    auth_user,
) -> None:
    """A live object mismatch prevents evaluation evidence from being persisted."""

    context = await _strict_context(auth_user, "evaluator-drift")
    datasets = _dataset_registry(context)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )
    _drift_sealed_object(context)
    with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
        await IndependentEvaluator(dataset_registry=datasets).evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=PromotionPolicy(
                version="promotion-v1", min_deflated_sharpe=0.95, max_drawdown=0.2
            ),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence=_evidence(context),
        )

    async with async_session_maker() as session:
        evaluations = await session.execute(
            select(ResearchEvaluation).where(
                ResearchEvaluation.experiment_epoch_id == context["epoch"].id
            )
        )
    assert list(evaluations.scalars()) == []
    await _assert_authorization_not_consumed(context, issued.authorization.id)


@pytest.mark.asyncio
async def test_independent_evaluator_requires_retained_evidence_before_consumption(
    auth_user,
) -> None:
    """A missing authoritative artifact cannot consume the holdout budget."""

    context = await _strict_context(auth_user, "evaluator-evidence-required")
    datasets = _dataset_registry(context)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )

    with pytest.raises(
        ValueError,
        match="^INDEPENDENT_EVALUATOR_EVIDENCE_ARTIFACT_REQUIRED$",
    ):
        await IndependentEvaluator(dataset_registry=datasets).evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=PromotionPolicy(
                version="promotion-v1",
                min_deflated_sharpe=0.95,
                max_drawdown=0.2,
            ),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence=_evidence(context),
        )

    await _assert_authorization_not_consumed(context, issued.authorization.id)
    async with async_session_maker() as session:
        evaluations = await session.scalars(
            select(ResearchEvaluation).where(
                ResearchEvaluation.experiment_epoch_id == context["epoch"].id
            )
        )
        assert list(evaluations) == []


@pytest.mark.asyncio
async def test_independent_evaluator_rejects_unretained_security_scan_before_consumption(
    auth_user,
) -> None:
    """A syntactically valid scan hash is not authority without retained canonical bytes."""

    context = await _strict_context(auth_user, "evaluator-security-scan-required")
    datasets = _dataset_registry(context)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )
    evidence_artifact = await _create_sealed_evidence_artifact(
        context,
        authorization_id=issued.authorization.id,
    )
    async with async_session_maker() as session:
        artifact = await session.get(ResearchArtifact, evidence_artifact.id)
        retained = await session.get(ResearchArtifactContent, evidence_artifact.id)
        assert artifact is not None and retained is not None
        payload = json.loads(bytes(retained.content))
        payload["measurements"]["security_scan_hash"] = "8" * 64
        content = canonical_json(payload).encode("utf-8")
        artifact.content_hash = sha256(content).hexdigest()
        artifact.size_bytes = len(content)
        retained.content = content
        await session.commit()

    with pytest.raises(
        ValueError,
        match="^INDEPENDENT_EVALUATOR_SECURITY_SCAN_ARTIFACT_INVALID$",
    ):
        await IndependentEvaluator(dataset_registry=datasets).evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence={},
            returns_artifact_id=evidence_artifact.id,
        )

    await _assert_authorization_not_consumed(context, issued.authorization.id)
    async with async_session_maker() as session:
        evaluations = list(
            await session.scalars(
                select(ResearchEvaluation).where(
                    ResearchEvaluation.experiment_epoch_id == context["epoch"].id
                )
            )
        )
    assert evaluations == []


@pytest.mark.asyncio
async def test_independent_evaluator_rolls_back_consumption_when_evaluation_insert_fails(
    auth_user,
) -> None:
    """The authorization and epoch move only if the RUNNING receipt is durable."""

    context = await _strict_context(auth_user, "evaluator-insert-rollback")
    datasets = _dataset_registry(context)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )
    evidence_artifact = await _create_sealed_evidence_artifact(
        context,
        authorization_id=issued.authorization.id,
    )

    def reject_evaluation_insert(_mapper, _connection, _target) -> None:
        raise IntegrityError("INSERT ai_research_evaluations", {}, RuntimeError("injected"))

    event.listen(ResearchEvaluation, "before_insert", reject_evaluation_insert)
    try:
        with pytest.raises(
            ValueError,
            match="^INDEPENDENT_EVALUATOR_BUDGET_ALREADY_CONSUMED$",
        ):
            await IndependentEvaluator(dataset_registry=datasets).evaluate_holdout(
                authorization_token=issued.token,
                candidate_id=context["candidate"].id,
                candidate_hash=context["candidate"].candidate_hash,
                dataset_snapshot_id=context["sealed"].id,
                policy=PromotionPolicy(
                    version="promotion-v1",
                    min_deflated_sharpe=0.95,
                    max_drawdown=0.2,
                ),
                evaluator_identity="ai_research_evaluator",
                evaluator_version="evaluator-image@sha256:test",
                evidence=_evidence(context),
                returns_artifact_id=evidence_artifact.id,
            )
    finally:
        event.remove(ResearchEvaluation, "before_insert", reject_evaluation_insert)

    await _assert_authorization_not_consumed(context, issued.authorization.id)
    async with async_session_maker() as session:
        evaluations = await session.scalars(
            select(ResearchEvaluation).where(
                ResearchEvaluation.experiment_epoch_id == context["epoch"].id
            )
        )
        assert list(evaluations) == []


@pytest.mark.asyncio
async def test_independent_evaluator_rolls_back_if_strict_freeze_receipt_is_invalid(
    auth_user,
) -> None:
    """Receipt drift cannot burn a one-time sealed-holdout authorization."""

    context = await _strict_context(auth_user, "evaluator-receipt-rollback")
    datasets = _dataset_registry(context)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )
    async with async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == context["candidate"].id
            )
        )
        assert receipt is not None
        receipt.ledger_hash = "0" * 64
        await session.commit()

    with pytest.raises(ValueError, match="^CANDIDATE_STRICT_FREEZE_RECEIPT_REQUIRED$"):
        await IndependentEvaluator(dataset_registry=datasets).evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=PromotionPolicy(
                version="promotion-v1",
                min_deflated_sharpe=0.95,
                max_drawdown=0.2,
            ),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence=_evidence(context),
        )

    await _assert_authorization_not_consumed(context, issued.authorization.id)
    async with async_session_maker() as session:
        evaluations = await session.scalars(
            select(ResearchEvaluation).where(
                ResearchEvaluation.experiment_epoch_id == context["epoch"].id
            )
        )
        assert list(evaluations) == []


async def _stranded_evaluation(auth_user, suffix: str, monkeypatch) -> dict[str, object]:
    """Persist a full gate set, then inject the crash before finalization."""

    context = await _strict_context(auth_user, suffix)
    datasets = _dataset_registry(context)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=context["user_id"],
        candidate_id=context["candidate"].id,
        dataset_snapshot_id=context["sealed"].id,
        policy_version="promotion-v1",
        evaluator_identity="ai_research_evaluator",
        profile_id=context["profile"].profile_id,
        profile_version=context["profile"].version,
    )
    evidence_artifact = await _create_sealed_evidence_artifact(
        context,
        authorization_id=issued.authorization.id,
    )
    evaluator = IndependentEvaluator(dataset_registry=datasets)
    original_finish = evaluator._finish
    crash_pending = True

    async def crash_once(**kwargs):
        nonlocal crash_pending
        if crash_pending:
            crash_pending = False
            raise RuntimeError("injected evaluation finalization crash")
        return await original_finish(**kwargs)

    monkeypatch.setattr(evaluator, "_finish", crash_once)
    with pytest.raises(RuntimeError, match="^injected evaluation finalization crash$"):
        await evaluator.evaluate_holdout(
            authorization_token=issued.token,
            candidate_id=context["candidate"].id,
            candidate_hash=context["candidate"].candidate_hash,
            dataset_snapshot_id=context["sealed"].id,
            policy=_promotion_policy(),
            evaluator_identity="ai_research_evaluator",
            evaluator_version="evaluator-image@sha256:test",
            evidence={},
            returns_artifact_id=evidence_artifact.id,
        )

    async with async_session_maker() as session:
        evaluation = await session.scalar(
            select(ResearchEvaluation).where(
                ResearchEvaluation.experiment_epoch_id == context["epoch"].id
            )
        )
        authorization = await session.get(ResearchHoldoutAuthorization, issued.authorization.id)
        epoch = await session.get(ResearchExperimentEpoch, context["epoch"].id)
        assert evaluation is not None and evaluation.status == "RUNNING"
        assert evaluation.completed_at is None
        assert authorization is not None and authorization.status == "CONSUMED"
        assert authorization.consumed_at is not None
        assert epoch is not None and epoch.status == "DISCLOSED"
        decision_ids = set(
            await session.scalars(
                select(ResearchGateDecision.id).where(
                    ResearchGateDecision.evaluation_id == evaluation.id
                )
            )
        )
        assert len(decision_ids) == 13
    return {
        **context,
        "evaluator": evaluator,
        "evaluation": evaluation,
        "decision_ids": decision_ids,
    }


def _promotion_policy() -> PromotionPolicy:
    return PromotionPolicy(
        version="promotion-v1",
        min_deflated_sharpe=0.95,
        max_drawdown=0.2,
    )


async def _assert_authorization_not_consumed(
    context: dict[str, object],
    authorization_id: str,
) -> None:
    async with async_session_maker() as session:
        authorization = await session.get(ResearchHoldoutAuthorization, authorization_id)
        epoch = await session.get(ResearchExperimentEpoch, context["epoch"].id)
        assert authorization is not None
        assert authorization.status == "ISSUED"
        assert authorization.consumed_at is None
        assert epoch is not None
        assert epoch.status == "SELECTED"


async def _create_sealed_evidence_artifact(
    context: dict[str, object],
    *,
    authorization_id: str,
    policy_version: str = "promotion-v1",
    evaluator_identity: str = "ai_research_evaluator",
    evaluator_version: str = "evaluator-image@sha256:test",
) -> ResearchArtifact:
    candidate = context["candidate"]
    epoch = context["epoch"]
    discovery = context["discovery"]
    sealed = context["sealed"]
    profile = context["profile"]
    assert isinstance(candidate, ResearchCandidate)
    assert isinstance(epoch, ResearchExperimentEpoch)
    assert isinstance(discovery, ResearchDatasetSnapshot)
    assert isinstance(sealed, ResearchDatasetSnapshot)
    assert isinstance(profile, CapabilityProfile)
    async with async_session_maker() as session:
        trial = await session.scalar(
            select(ResearchTrial).where(
                ResearchTrial.candidate_id == candidate.id,
                ResearchTrial.run_id == candidate.run_id,
                ResearchTrial.counts_as_market_trial.is_(True),
            )
        )
        assert trial is not None and trial.returns_artifact_id is not None
        discovery_content = await session.get(
            ResearchArtifactContent,
            trial.returns_artifact_id,
        )
        assert discovery_content is not None
        discovery_payload = json.loads(bytes(discovery_content.content))
    discovery_returns = [float(value) for value in discovery_payload["result"]["returns"]]
    mean = sum(discovery_returns) / len(discovery_returns)
    variance = sum((value - mean) ** 2 for value in discovery_returns) / (
        len(discovery_returns) - 1
    )
    trial_sharpes = [round(mean / sqrt(variance) * sqrt(252), 12)]
    async with async_session_maker() as session:
        code = await session.get(ResearchArtifact, candidate.code_artifact_id)
        dependency = await session.get(ResearchArtifact, candidate.dependency_artifact_id)
        assert code is not None and dependency is not None
    scan_payload = {
        "schema_version": "security-scan-evidence-v1",
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "code_artifact_id": code.id,
        "code_hash": code.content_hash,
        "dependency_artifact_id": dependency.id,
        "dependency_hash": dependency.content_hash,
        "evaluator_identity": evaluator_identity,
        "evaluator_version": evaluator_version,
        "scan_policy_version": "security-scan-policy-v1",
        "scanner_identity": "research-security-scanner",
        "scanner_image_digest": f"sha256:{'5' * 64}",
        "critical_findings": 0,
    }
    security_scan_artifact = await _persist_security_scan_artifact(scan_payload)
    payload = {
        "schema_version": "sealed-holdout-evidence-v1",
        "authorization_id": authorization_id,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "experiment_epoch_id": epoch.id,
        "dataset_snapshot_id": sealed.id,
        "sealed_dataset_hash": sealed.content_hash,
        "policy_version": policy_version,
        "evaluator_identity": evaluator_identity,
        "evaluator_version": evaluator_version,
        "measurements": {
            "returns": [0.01, 0.005, 0.015, 0.002, 0.003, 0.008],
            "trial_sharpes": trial_sharpes,
            "discovery_dataset_snapshot_hash": discovery.content_hash,
            "cost_model_hash": candidate.cost_model_hash,
            "environment_hash": candidate.environment_hash,
            "capability_evidence_hash": profile.evidence_hash,
            "max_drawdown": 0.10,
            "robustness_score": 0.95,
            "cost_bps": 2.0,
            "slippage_bps": 1.0,
            "turnover": 1.5,
            "capacity_notional": 200_000.0,
            "extreme_path_loss": 0.10,
            "execution_semantics_match": True,
            "security_critical_findings": 0,
            "security_scan_hash": security_scan_artifact.content_hash,
        },
    }
    retained = canonical_json(payload).encode("utf-8")
    digest = sha256(retained).hexdigest()
    artifact = ResearchArtifact(
        kind="sealed_holdout_evidence",
        content_hash=digest,
        storage_uri=f"controlled://sealed-holdout-evidence/{digest}",
        size_bytes=len(retained),
        media_type="application/json",
        schema_version="sealed-holdout-evidence-v1",
        producer_identity=evaluator_identity,
        container_image_digest=evaluator_version,
    )
    async with async_session_maker() as session:
        session.add(artifact)
        await session.flush()
        session.add(ResearchArtifactContent(artifact_id=artifact.id, content=retained))
        await session.commit()
        await session.refresh(artifact)
    return artifact


async def _persist_security_scan_artifact(payload: dict[str, object]) -> ResearchArtifact:
    retained = canonical_json(payload).encode("utf-8")
    digest = sha256(retained).hexdigest()
    artifact = ResearchArtifact(
        kind="security_scan_evidence",
        content_hash=digest,
        storage_uri=f"controlled://security-scan-evidence/{digest}",
        size_bytes=len(retained),
        media_type="application/json",
        schema_version="security-scan-evidence-v1",
        producer_identity="research-security-scanner",
        container_image_digest=f"sha256:{'5' * 64}",
    )
    async with async_session_maker() as session:
        session.add(artifact)
        await session.flush()
        session.add(ResearchArtifactContent(artifact_id=artifact.id, content=retained))
        await session.commit()
        await session.refresh(artifact)
    return artifact


async def _strict_context(auth_user, suffix: str) -> dict[str, object]:
    """Build evaluator evidence from a real published discovery freeze."""

    from tests.test_ai_research_holdout_authorization import (
        _strict_context as _strict_holdout_context,
    )

    profile = CapabilityProfile(
        profile_id=f"evaluator-isolated-{suffix}",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests={
            "evaluator": "evaluator-image@sha256:test",
            "scanner": f"sha256:{'5' * 64}",
        },
    )
    await CapabilityRegistry().register(profile)
    context = await _strict_holdout_context(
        auth_user,
        suffix,
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    candidate = context["candidate"]
    assert isinstance(candidate, ResearchCandidate)
    async with async_session_maker() as session:
        run = await session.get(ResearchRun, candidate.run_id)
        epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
        assert run is not None and epoch is not None
        discovery = await session.get(ResearchDatasetSnapshot, run.dataset_snapshot_id)
        assert discovery is not None
    return {
        **context,
        "profile": profile,
        "discovery": discovery,
        "epoch": epoch,
    }


async def _context(user_id: str) -> dict[str, object]:
    profile = CapabilityProfile(
        profile_id="single-node-isolated-services",
        version="v1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        stage_image_digests={
            "evaluator": "evaluator-image@sha256:test",
            "scanner": f"sha256:{'5' * 64}",
        },
    )
    await CapabilityRegistry().register(profile)
    hypothesis = await HypothesisRegistry().create_draft(user_id, _payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id, hypothesis.id, request_hash=hypothesis.content_hash
    )
    resolver = InMemoryDatasetObjectResolver()
    receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id="independent-evaluator-discovery-receipt-v1",
            user_id=user_id,
            logical_object_id="independent-evaluator-discovery-object",
            object_version="version-1",
            object_digest="d" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://independent-evaluator-fixtures/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    registry = DatasetRegistry(object_resolver=resolver)
    discovery = await registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    sealed_receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id="independent-evaluator-holdout-receipt-v1",
            user_id=user_id,
            logical_object_id="independent-evaluator-holdout-object",
            object_version="version-1",
            object_digest="e" * 64,
            object_size_bytes=2048,
            storage_uri="sealed://independent-evaluator-fixtures/holdout.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    sealed = await registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=sealed_receipt.receipt_id,
        dataset_policy_version="policy-v1",
        partition_kind="SEALED_HOLDOUT",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2024-01-01", "end": "2024-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
        license_tags=["fixture-license"],
    )
    epoch = ResearchExperimentEpoch(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        family_hash="f" * 64,
        search_budget={"max_trials": 3},
        dataset_policy_version="policy-v1",
    )
    async with async_session_maker() as session:
        session.add(epoch)
        await session.commit()
        await session.refresh(epoch)
    run = ResearchRun(
        user_id=user_id,
        hypothesis_version_id=hypothesis.id,
        dataset_snapshot_id=discovery.id,
        experiment_epoch_id=epoch.id,
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
        trace_id="trace-evaluator",
    )
    code = ResearchArtifact(
        kind="strategy_code",
        content_hash="a" * 64,
        storage_uri="controlled://code.py",
        size_bytes=10,
        media_type="text/x-python",
        schema_version="v1",
        producer_identity="test",
    )
    dependencies = ResearchArtifact(
        kind="dependency_lock",
        content_hash="b" * 64,
        storage_uri="controlled://requirements.lock",
        size_bytes=10,
        media_type="text/plain",
        schema_version="v1",
        producer_identity="test",
    )
    async with async_session_maker() as session:
        session.add_all([run, code, dependencies])
        await session.commit()
        for model in (run, code, dependencies):
            await session.refresh(model)
    candidate_registry = CandidateRegistry(dataset_registry=registry)
    candidate = await candidate_registry.create_mutable(
        user_id=user_id,
        run_id=run.id,
        experiment_epoch_id=epoch.id,
        dataset_snapshot_id=discovery.id,
        code_artifact_id=code.id,
        dependency_artifact_id=dependencies.id,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    async with async_session_maker() as session:
        session.add(
            ResearchTrial(
                user_id=user_id,
                run_id=run.id,
                candidate_id=candidate.id,
                ordinal=1,
                idempotency_key="trial-evaluator",
                stage="VALIDATE",
                status="SUCCEEDED",
                input_hash="i" * 64,
                observed_market_performance=True,
                counts_as_market_trial=True,
                counting_reason="completed discovery validation",
            )
        )
        await session.commit()
    candidate = await candidate_registry.freeze(
        user_id,
        candidate.id,
        frozen_by="ai_research_explorer",
        expected_candidate_hash=candidate.candidate_hash,
    )
    return {
        "user_id": user_id,
        "profile": profile,
        "candidate": candidate,
        "discovery": discovery,
        "sealed": sealed,
        "epoch": epoch,
        "datasets": registry,
        "resolver": resolver,
    }


def _dataset_registry(context: dict[str, object]) -> DatasetRegistry:
    datasets = context["datasets"]
    assert isinstance(datasets, DatasetRegistry)
    return datasets


def _evidence(context: dict[str, object]) -> dict[str, object]:
    return {
        "returns": [0.01, -0.004, 0.015, 0.002, -0.003, 0.008],
        "trial_sharpes": [0.1, 0.3, 0.45, 0.2],
        "dataset_snapshot_hash": context["discovery"].content_hash,
        "sealed_dataset_hash": context["sealed"].content_hash,
        "cost_model_hash": context["candidate"].cost_model_hash,
        "environment_hash": context["candidate"].environment_hash,
        "capability_evidence_hash": context["profile"].evidence_hash,
        "max_drawdown": 0.10,
    }


def _drift_sealed_object(context: dict[str, object]) -> None:
    resolver = context["resolver"]
    sealed = context["sealed"]
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    assert isinstance(sealed, ResearchDatasetSnapshot)
    assert sealed.object_logical_id is not None and sealed.storage_uri is not None
    resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"{sealed.object_receipt_id}-drift",
            user_id=context["user_id"],
            logical_object_id=sealed.object_logical_id,
            object_version="version-2",
            object_digest="f" * 64,
            object_size_bytes=2048,
            storage_uri=sealed.storage_uri,
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )


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
