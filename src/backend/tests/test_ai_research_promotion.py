from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import sqrt
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import async_session_maker
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
from app.services.research.promotion import (
    PromotionGateEngine,
    PromotionPolicy,
    promotion_policy_material_hash,
)

_POLICY = PromotionPolicy(
    version="promotion-v1",
    min_deflated_sharpe=0.95,
    max_drawdown=0.2,
)
_EVALUATOR_IMAGE_DIGEST = f"sha256:{'4' * 64}"
_SCANNER_IMAGE_DIGEST = f"sha256:{'5' * 64}"

_NEW_HARD_GATES = {
    "ROBUSTNESS": ("robustness_score", 0.1),
    "COST": ("cost_bps", 6.0),
    "SLIPPAGE": ("slippage_bps", 3.0),
    "TURNOVER": ("turnover", 5.0),
    "CAPACITY": ("capacity_notional", 99_999.0),
    "EXTREME_PATH": ("extreme_path_loss", 0.3),
    "EXECUTION_SEMANTICS": ("execution_semantics_match", False),
    "SECURITY_SCAN": ("security_critical_findings", 1),
}


@pytest.mark.asyncio
async def test_promotion_gate_fails_closed_when_evidence_is_missing(auth_user) -> None:
    context = await _strict_context(auth_user, "promotion-missing-evidence")
    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["SEALED_HOLDOUT"].status == "BLOCKED"
    assert result.by_code["SEALED_HOLDOUT"].reason == "evaluation_required"
    assert result.by_code["EVIDENCE_BINDING"].status == "UNKNOWN"
    assert result.by_code["DEFLATED_SHARPE"].status == "UNKNOWN"
    assert result.by_code["MAX_DRAWDOWN"].status == "UNKNOWN"
    assert all(result.by_code[code].status == "UNKNOWN" for code in _NEW_HARD_GATES)


@pytest.mark.asyncio
async def test_ai_review_can_never_override_hard_gate_failure(auth_user) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        "promotion-ai-review",
        measurement_overrides={"max_drawdown": 0.31},
    )
    engine = PromotionGateEngine()

    failed = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={"max_drawdown": 0.0, "disable_hard_gates": True},
        ai_review={"recommendation": "PROMOTE", "score": 1.0},
    )

    assert failed.eligible is False
    assert failed.by_code["MAX_DRAWDOWN"].status == "FAIL"
    assert failed.by_code["SEALED_HOLDOUT"].status == "PASS"


@pytest.mark.asyncio
async def test_policy_or_evidence_hash_change_expires_prior_eligibility(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-hash-expiry")
    engine = PromotionGateEngine()
    first = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={"client_spoof": "ignored"},
    )
    await _finalize_evaluation(context, first)

    assert await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version="promotion-v1",
        input_evidence_hash=first.input_evidence_hash,
    )
    assert not await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version="promotion-v2",
        input_evidence_hash=first.input_evidence_hash,
    )
    assert not await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version="promotion-v1",
        input_evidence_hash="f" * 64,
    )


@pytest.mark.asyncio
async def test_legacy_four_pass_decisions_without_strict_receipt_are_never_eligible(
    auth_user,
) -> None:
    context = await _context(await _user_id(auth_user))
    engine = PromotionGateEngine()
    evaluated = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        policy=_POLICY,
        evidence=_evidence(context, max_drawdown=0.10),
    )
    assert evaluated.eligible is False
    assert evaluated.strict_freeze_receipt_fingerprint is None
    assert evaluated.by_code["CANDIDATE_FROZEN"].status == "FAIL"
    assert evaluated.by_code["CANDIDATE_FROZEN"].reason == "strict_freeze_receipt_required"

    input_evidence_hash = "9" * 64
    async with async_session_maker() as session:
        session.add_all(
            [
                ResearchGateDecision(
                    candidate_id=context["candidate"].id,
                    gate_code=code,
                    policy_version="promotion-v1",
                    input_evidence_hash=input_evidence_hash,
                    status="PASS",
                    reason="legacy_fixture_pass",
                    executor_version="promotion-gate-v1",
                )
                for code in (
                    "CANDIDATE_FROZEN",
                    "EVIDENCE_BINDING",
                    "DEFLATED_SHARPE",
                    "MAX_DRAWDOWN",
                )
            ]
        )
        await session.commit()

    assert not await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version="promotion-v1",
        input_evidence_hash=input_evidence_hash,
    )


@pytest.mark.asyncio
async def test_strict_receipt_drift_invalidates_prior_promotion_eligibility(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-receipt-drift")
    engine = PromotionGateEngine()
    result = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    assert result.eligible is True
    await _finalize_evaluation(context, result)

    async with async_session_maker() as session:
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == context["candidate"].id
            )
        )
        assert receipt is not None
        receipt.ledger_hash = "0" * 64
        await session.commit()

    assert not await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version="promotion-v1",
        input_evidence_hash=result.input_evidence_hash,
    )


@pytest.mark.asyncio
async def test_strict_receipt_fingerprint_changes_gate_input_hash_and_is_persisted(
    auth_user,
) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-receipt-fingerprint")
    engine = PromotionGateEngine()
    first = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    assert first.eligible is True
    assert first.strict_freeze_receipt_fingerprint is not None
    spoofed_evidence = {"strict_freeze_receipt_fingerprint": "0" * 64}
    spoofed = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence=spoofed_evidence,
    )
    assert spoofed.strict_freeze_receipt_fingerprint == first.strict_freeze_receipt_fingerprint
    assert spoofed.input_evidence_hash == first.input_evidence_hash

    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, context["candidate"].id)
        receipt = await session.scalar(
            select(ResearchCandidateFreezeReceipt).where(
                ResearchCandidateFreezeReceipt.candidate_id == context["candidate"].id
            )
        )
        assert candidate is not None and candidate.frozen_at is not None
        assert receipt is not None
        rotated_frozen_at = candidate.frozen_at + timedelta(microseconds=1)
        candidate.frozen_at = rotated_frozen_at
        receipt.frozen_at = rotated_frozen_at
        await session.commit()

    second = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    assert second.eligible is True
    assert second.strict_freeze_receipt_fingerprint is not None
    assert second.strict_freeze_receipt_fingerprint != first.strict_freeze_receipt_fingerprint
    assert second.input_evidence_hash != first.input_evidence_hash

    async with async_session_maker() as session:
        decision = await session.scalar(
            select(ResearchGateDecision).where(
                ResearchGateDecision.candidate_id == context["candidate"].id,
                ResearchGateDecision.policy_version == _POLICY.version,
                ResearchGateDecision.input_evidence_hash == second.input_evidence_hash,
                ResearchGateDecision.gate_code == "CANDIDATE_FROZEN",
            )
        )
        assert decision is not None
        assert decision.reason == (
            f"strict_freeze_receipt_fingerprint={second.strict_freeze_receipt_fingerprint}"
        )


@pytest.mark.asyncio
async def test_promotion_rejects_client_relaxed_server_policy(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-relaxed-policy")

    with pytest.raises(ValueError, match="^PROMOTION_POLICY_CONFIGURATION_MISMATCH$"):
        await PromotionGateEngine().evaluate_and_record(
            candidate_id=context["candidate"].id,
            evaluation_id=context["evaluation"].id,
            policy=PromotionPolicy(
                version="promotion-v1",
                min_deflated_sharpe=0.10,
                max_drawdown=1.0,
            ),
            evidence={"disable_security_scan": True},
        )


def test_promotion_policy_rejects_non_probability_dsr_threshold() -> None:
    with pytest.raises(ValueError, match="^PROMOTION_POLICY_INVALID$"):
        PromotionPolicy(
            version="promotion-v1",
            min_deflated_sharpe=-0.01,
            max_drawdown=0.2,
        ).validate()


@pytest.mark.asyncio
async def test_claimed_trial_sharpe_subset_cannot_weaken_dsr(auth_user) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        "promotion-trial-sharpe-subset",
        measurement_overrides={"trial_sharpes": []},
    )

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence=_pretty_client_spoof(),
    )

    assert result.eligible is False
    assert result.by_code["SEALED_HOLDOUT"].status == "BLOCKED"
    assert result.by_code["SEALED_HOLDOUT"].reason == "trial_sharpes_ledger_mismatch"
    assert result.by_code["DEFLATED_SHARPE"].status == "UNKNOWN"


@pytest.mark.asyncio
async def test_dsr_probability_threshold_is_an_independent_hard_gate(auth_user) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        "promotion-dsr-failure",
        measurement_overrides={"returns": [0.01, -0.004, 0.015, 0.002, -0.003, 0.008]},
    )

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["DEFLATED_SHARPE"].status == "FAIL"
    assert all(
        outcome.status == "PASS"
        for outcome in result.decisions
        if outcome.code != "DEFLATED_SHARPE"
    )
    await _finalize_evaluation(context, result)
    async with async_session_maker() as session:
        replayed = await PromotionGateEngine().read_result_in_session(
            session,
            candidate_id=context["candidate"].id,
            evaluation_id=context["evaluation"].id,
            policy_version=_POLICY.version,
            input_evidence_hash=result.input_evidence_hash,
        )
    assert replayed == result


@pytest.mark.asyncio
async def test_trial_ledger_drift_blocks_sealed_authority(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-ledger-drift")
    async with async_session_maker() as session:
        trial = await session.scalar(
            select(ResearchTrial).where(
                ResearchTrial.candidate_id == context["candidate"].id,
                ResearchTrial.run_id == context["run"].id,
            )
        )
        assert trial is not None
        trial.metrics = {**trial.metrics, "sample_count": 999}
        await session.commit()

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["CANDIDATE_FROZEN"].status == "FAIL"
    assert result.by_code["SEALED_HOLDOUT"].status == "BLOCKED"
    assert result.by_code["SEALED_HOLDOUT"].reason == "strict_freeze_receipt_required"


@pytest.mark.asyncio
async def test_fake_security_scan_hash_is_independently_unknown(auth_user) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        "promotion-security-fake-hash",
        measurement_overrides={"security_scan_hash": "8" * 64},
    )

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["SECURITY_SCAN"].status == "UNKNOWN"
    assert result.by_code["SECURITY_SCAN"].reason == "security_scan_artifact_not_retained"
    assert all(
        outcome.status == "PASS" for outcome in result.decisions if outcome.code != "SECURITY_SCAN"
    )


@pytest.mark.asyncio
async def test_misbound_security_scan_artifact_is_independently_unknown(auth_user) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        "promotion-security-misbound",
        scan_payload_overrides={"candidate_hash": "f" * 64},
    )

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["SECURITY_SCAN"].status == "UNKNOWN"
    assert result.by_code["SECURITY_SCAN"].reason == "security_scan_artifact_binding_mismatch"
    assert all(
        outcome.status == "PASS" for outcome in result.decisions if outcome.code != "SECURITY_SCAN"
    )


@pytest.mark.asyncio
async def test_tampered_security_scan_artifact_is_independently_unknown(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-security-tamper")
    async with async_session_maker() as session:
        retained = await session.get(
            ResearchArtifactContent,
            context["security_scan_artifact"].id,
        )
        assert retained is not None
        retained.content = bytes(retained.content) + b" "
        await session.commit()

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["SECURITY_SCAN"].status == "UNKNOWN"
    assert result.by_code["SECURITY_SCAN"].reason == "security_scan_artifact_invalid"
    assert all(
        outcome.status == "PASS" for outcome in result.decisions if outcome.code != "SECURITY_SCAN"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scanner_digest", [None, f"sha256:{'6' * 64}"])
async def test_security_scan_requires_bound_capability_profile_image(
    auth_user,
    scanner_digest: str | None,
) -> None:
    context = await _authorized_evaluation_context(
        auth_user,
        f"promotion-security-profile-{scanner_digest is None}",
    )
    run = context["run"]
    async with async_session_maker() as session:
        profile = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == run.capability_profile_id,
                ResearchCapabilityProfile.version == run.capability_profile_version,
            )
        )
        assert profile is not None
        sandbox = dict(profile.sandbox_capabilities or {})
        stage_images = dict(sandbox.get("stage_image_digests") or {})
        if scanner_digest is None:
            stage_images.pop("scanner", None)
        else:
            stage_images["scanner"] = scanner_digest
        profile.sandbox_capabilities = {**sandbox, "stage_image_digests": stage_images}
        await session.commit()

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["SECURITY_SCAN"].status == "UNKNOWN"
    assert result.by_code["SECURITY_SCAN"].reason == "security_scan_capability_binding_mismatch"
    assert all(
        outcome.status == "PASS" for outcome in result.decisions if outcome.code != "SECURITY_SCAN"
    )


@pytest.mark.asyncio
async def test_evaluation_timeline_mismatch_blocks_sealed_authority(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-timeline-record")
    async with async_session_maker() as session:
        authorization = await session.get(
            ResearchHoldoutAuthorization,
            context["authorization"].id,
        )
        evaluation = await session.get(ResearchEvaluation, context["evaluation"].id)
        assert authorization is not None and evaluation is not None
        authorization.consumed_at = evaluation.started_at + timedelta(seconds=1)
        await session.commit()

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )

    assert result.eligible is False
    assert result.by_code["SEALED_HOLDOUT"].status == "BLOCKED"
    assert result.by_code["SEALED_HOLDOUT"].reason == "evaluation_timeline_invalid"


@pytest.mark.asyncio
async def test_terminal_timeline_drift_invalidates_replayed_result(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-timeline-read")
    engine = PromotionGateEngine()
    result = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    await _finalize_evaluation(context, result)
    async with async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, context["evaluation"].id)
        assert evaluation is not None and evaluation.started_at is not None
        evaluation.completed_at = evaluation.started_at - timedelta(seconds=1)
        await session.commit()

    assert not await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version=_POLICY.version,
        input_evidence_hash=result.input_evidence_hash,
    )
    async with async_session_maker() as session:
        with pytest.raises(ValueError, match="^PROMOTION_RESULT_INVALID$"):
            await engine.read_result_in_session(
                session,
                candidate_id=context["candidate"].id,
                evaluation_id=context["evaluation"].id,
                policy_version=_POLICY.version,
                input_evidence_hash=result.input_evidence_hash,
            )


@pytest.mark.asyncio
async def test_unconsumed_or_misbound_authorization_blocks_sealed_gate(auth_user) -> None:
    unconsumed = await _authorized_evaluation_context(
        auth_user,
        "a-unconsumed",
        consume_authorization=False,
    )
    unconsumed_result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=unconsumed["candidate"].id,
        evaluation_id=unconsumed["evaluation"].id,
        policy=_POLICY,
        evidence=_pretty_client_spoof(),
    )
    assert unconsumed_result.eligible is False
    assert unconsumed_result.by_code["SEALED_HOLDOUT"].status == "BLOCKED"
    assert unconsumed_result.by_code["SEALED_HOLDOUT"].reason == "authorization_not_consumed"

    consumed = await HoldoutAuthorizationRegistry(dataset_registry=unconsumed["datasets"]).consume(
        unconsumed["authorization_token"],
        candidate_id=unconsumed["candidate"].id,
        candidate_hash=unconsumed["candidate"].candidate_hash,
        dataset_snapshot_id=unconsumed["sealed"].id,
        policy_version=_POLICY.version,
        evaluator_identity="evaluator",
    )
    assert consumed.status == "CONSUMED"
    async with async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, unconsumed["evaluation"].id)
        assert evaluation is not None
        evaluation.dataset_snapshot_id = unconsumed["discovery"].id
        await session.commit()
    misbound_result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=unconsumed["candidate"].id,
        evaluation_id=unconsumed["evaluation"].id,
        policy=_POLICY,
        evidence=_pretty_client_spoof(),
    )
    assert misbound_result.eligible is False
    assert misbound_result.by_code["SEALED_HOLDOUT"].status == "BLOCKED"
    assert misbound_result.by_code["SEALED_HOLDOUT"].reason == "authorization_binding_mismatch"


@pytest.mark.parametrize(("gate_code", "measurement_key"), _NEW_HARD_GATES.items())
@pytest.mark.asyncio
async def test_each_new_hard_gate_missing_evidence_is_independently_unknown(
    auth_user,
    gate_code: str,
    measurement_key: tuple[str, Any],
) -> None:
    key, _failed_value = measurement_key
    context = await _authorized_evaluation_context(
        auth_user,
        f"promotion-missing-{gate_code.lower()}",
        missing_measurement=key,
    )

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence=_pretty_client_spoof(),
        ai_review={"recommendation": "PROMOTE", "gates": {gate_code: "PASS"}},
    )

    assert result.eligible is False
    assert result.by_code[gate_code].status == "UNKNOWN"
    assert result.by_code[gate_code].reason == f"missing:{key}"
    assert all(
        outcome.status == "PASS" for outcome in result.decisions if outcome.code != gate_code
    )


@pytest.mark.parametrize(("gate_code", "measurement_key"), _NEW_HARD_GATES.items())
@pytest.mark.asyncio
async def test_each_new_hard_gate_failure_is_independently_non_waivable(
    auth_user,
    gate_code: str,
    measurement_key: tuple[str, Any],
) -> None:
    key, failed_value = measurement_key
    context = await _authorized_evaluation_context(
        auth_user,
        f"promotion-fail-{gate_code.lower()}",
        measurement_overrides={key: failed_value},
    )

    result = await PromotionGateEngine().evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence=_pretty_client_spoof(),
        ai_review={"recommendation": "PROMOTE", "gates": {gate_code: "PASS"}},
    )

    assert result.eligible is False
    assert result.by_code[gate_code].status == "FAIL"
    assert all(
        outcome.status == "PASS" for outcome in result.decisions if outcome.code != gate_code
    )


@pytest.mark.asyncio
async def test_complete_bound_sealed_evaluation_passes_and_client_spoof_is_ignored(
    auth_user,
) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-complete-pass")
    engine = PromotionGateEngine()

    first = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence=_pretty_client_spoof(),
        ai_review={"recommendation": "REJECT", "score": 0.0},
    )
    second = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
        ai_review={"recommendation": "PROMOTE", "score": 1.0},
    )

    assert first.eligible is True
    assert all(outcome.status == "PASS" for outcome in first.decisions)
    assert first.input_evidence_hash == second.input_evidence_hash
    assert first.decisions == second.decisions
    async with async_session_maker() as session:
        persisted = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == context["evaluation"].id,
                        ResearchGateDecision.input_evidence_hash == first.input_evidence_hash,
                    )
                )
            ).all()
        )
    assert len(persisted) == len(first.decisions) == 13

    await _finalize_evaluation(context, first)
    assert await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version=_POLICY.version,
        input_evidence_hash=first.input_evidence_hash,
    )
    async with async_session_maker() as session:
        assert await engine.is_eligible_in_session(
            session,
            candidate_id=context["candidate"].id,
            policy_version=_POLICY.version,
            input_evidence_hash=first.input_evidence_hash,
        )


@pytest.mark.asyncio
async def test_promotion_lock_order_is_epoch_candidate_evaluation_decisions(auth_user) -> None:
    from tests.test_ai_research_discovery_trial_materialization import _row_lock_order

    context = await _authorized_evaluation_context(auth_user, "promotion-lock-order")
    async with async_session_maker() as observer_session:
        with _row_lock_order(observer_session.bind.sync_engine) as order:
            result = await PromotionGateEngine().evaluate_and_record(
                candidate_id=context["candidate"].id,
                evaluation_id=context["evaluation"].id,
                policy=_POLICY,
                evidence={},
            )

    assert result.eligible is True
    assert order.index("ai_research_experiment_epochs") < order.index("ai_research_candidates")
    assert order.index("ai_research_candidates") < order.index("ai_research_evaluations")
    assert order.index("ai_research_evaluations") < order.index("ai_research_gate_decisions")


@pytest.mark.asyncio
async def test_partial_decision_set_fails_closed_without_appending(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-partial-replay")
    engine = PromotionGateEngine()
    first = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    async with async_session_maker() as session:
        persisted = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == context["evaluation"].id,
                        ResearchGateDecision.input_evidence_hash == first.input_evidence_hash,
                    )
                )
            ).all()
        )
        assert len(persisted) == 13
        for decision in persisted[1:]:
            await session.delete(decision)
        await session.commit()

    with pytest.raises(ValueError, match="^PROMOTION_DECISION_SET_PARTIAL$"):
        await engine.evaluate_and_record(
            candidate_id=context["candidate"].id,
            evaluation_id=context["evaluation"].id,
            policy=_POLICY,
            evidence=_pretty_client_spoof(),
        )

    async with async_session_maker() as session:
        remaining = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == context["evaluation"].id,
                        ResearchGateDecision.input_evidence_hash == first.input_evidence_hash,
                    )
                )
            ).all()
        )
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_conflicting_complete_decision_set_fails_closed_without_appending(
    auth_user,
) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-conflict-replay")
    engine = PromotionGateEngine()
    first = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    async with async_session_maker() as session:
        decision = await session.scalar(
            select(ResearchGateDecision).where(
                ResearchGateDecision.evaluation_id == context["evaluation"].id,
                ResearchGateDecision.input_evidence_hash == first.input_evidence_hash,
                ResearchGateDecision.gate_code == "ROBUSTNESS",
            )
        )
        assert decision is not None
        decision.reason = "forged_reason"
        await session.commit()

    with pytest.raises(ValueError, match="^PROMOTION_DECISION_SET_CONFLICT$"):
        await engine.evaluate_and_record(
            candidate_id=context["candidate"].id,
            evaluation_id=context["evaluation"].id,
            policy=_POLICY,
            evidence={},
        )

    async with async_session_maker() as session:
        persisted = tuple(
            (
                await session.scalars(
                    select(ResearchGateDecision).where(
                        ResearchGateDecision.evaluation_id == context["evaluation"].id,
                        ResearchGateDecision.input_evidence_hash == first.input_evidence_hash,
                    )
                )
            ).all()
        )
    assert len(persisted) == 13
    await _finalize_evaluation(context, first)
    async with async_session_maker() as session:
        with pytest.raises(ValueError, match="^PROMOTION_RESULT_INVALID$"):
            await engine.read_result_in_session(
                session,
                candidate_id=context["candidate"].id,
                evaluation_id=context["evaluation"].id,
                policy_version=_POLICY.version,
                input_evidence_hash=first.input_evidence_hash,
            )


@pytest.mark.asyncio
async def test_is_eligible_revalidates_final_evaluation_authorization_and_artifact(
    auth_user,
) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-read-revalidation")
    engine = PromotionGateEngine()
    result = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    await _finalize_evaluation(context, result)
    assert await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version=_POLICY.version,
        input_evidence_hash=result.input_evidence_hash,
    )

    async with async_session_maker() as session:
        authorization = await session.get(
            ResearchHoldoutAuthorization,
            context["authorization"].id,
        )
        assert authorization is not None
        authorization.status = "REVOKED"
        await session.commit()

    assert not await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version=_POLICY.version,
        input_evidence_hash=result.input_evidence_hash,
    )


@pytest.mark.asyncio
async def test_database_rejects_duplicate_gate_decision_rows(auth_user) -> None:
    context = await _authorized_evaluation_context(auth_user, "promotion-read-duplicate")
    engine = PromotionGateEngine()
    result = await engine.evaluate_and_record(
        candidate_id=context["candidate"].id,
        evaluation_id=context["evaluation"].id,
        policy=_POLICY,
        evidence={},
    )
    await _finalize_evaluation(context, result)
    robustness = result.by_code["ROBUSTNESS"]
    async with async_session_maker() as session:
        session.add(
            ResearchGateDecision(
                candidate_id=context["candidate"].id,
                evaluation_id=context["evaluation"].id,
                gate_code=robustness.code,
                policy_version=_POLICY.version,
                input_evidence_hash=result.input_evidence_hash,
                status=robustness.status,
                reason=robustness.reason,
                executor_version=_POLICY.executor_version,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    assert await engine.is_eligible(
        candidate_id=context["candidate"].id,
        policy_version=_POLICY.version,
        input_evidence_hash=result.input_evidence_hash,
    )


async def _authorized_evaluation_context(
    auth_user,
    suffix: str,
    *,
    consume_authorization: bool = True,
    measurement_overrides: dict[str, Any] | None = None,
    missing_measurement: str | None = None,
    scan_payload_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the real strict-freeze, sealed authorization, artifact, and evaluation chain."""

    context = await _strict_context(auth_user, suffix)
    datasets = context["datasets"]
    resolver = context["resolver"]
    assert isinstance(datasets, DatasetRegistry)
    assert isinstance(resolver, InMemoryDatasetObjectResolver)
    candidate = context["candidate"]
    run = context["run"]
    assert isinstance(candidate, ResearchCandidate)
    assert isinstance(run, ResearchRun)
    sealed_receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id=f"{suffix}-promotion-sealed-receipt",
            user_id=candidate.user_id,
            logical_object_id=f"{suffix}-promotion-sealed-object",
            object_version="version-1",
            object_digest="e" * 64,
            object_size_bytes=2048,
            storage_uri=f"sealed://promotion/{suffix}.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    sealed = await datasets.create_attested_snapshot(
        user_id=candidate.user_id,
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
    assert isinstance(sealed, ResearchDatasetSnapshot)
    issued = await HoldoutAuthorizationRegistry(dataset_registry=datasets).issue(
        user_id=candidate.user_id,
        candidate_id=candidate.id,
        dataset_snapshot_id=sealed.id,
        policy_version=_POLICY.version,
        evaluator_identity="evaluator",
        profile_id=run.capability_profile_id,
        profile_version=run.capability_profile_version,
    )
    authorization = issued.authorization
    if consume_authorization:
        authorization = await HoldoutAuthorizationRegistry(dataset_registry=datasets).consume(
            issued.token,
            candidate_id=candidate.id,
            candidate_hash=candidate.candidate_hash,
            dataset_snapshot_id=sealed.id,
            policy_version=_POLICY.version,
            evaluator_identity="evaluator",
        )

    measurements = await _measurements(context)
    overrides = measurement_overrides or {}
    measurements.update(overrides)
    evaluator_version = _EVALUATOR_IMAGE_DIGEST
    async with async_session_maker() as session:
        code = await session.get(ResearchArtifact, candidate.code_artifact_id)
        dependency = await session.get(
            ResearchArtifact,
            candidate.dependency_artifact_id,
        )
        assert code is not None and dependency is not None
    scan_payload = {
        "schema_version": "security-scan-evidence-v1",
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "code_artifact_id": code.id,
        "code_hash": code.content_hash,
        "dependency_artifact_id": dependency.id,
        "dependency_hash": dependency.content_hash,
        "evaluator_identity": "evaluator",
        "evaluator_version": evaluator_version,
        "scan_policy_version": "security-scan-policy-v1",
        "scanner_identity": "research-security-scanner",
        "scanner_image_digest": _SCANNER_IMAGE_DIGEST,
        "critical_findings": measurements.get("security_critical_findings"),
    }
    scan_payload.update(scan_payload_overrides or {})
    security_scan_artifact = await _persist_security_scan_artifact(scan_payload)
    if "security_scan_hash" not in overrides:
        measurements["security_scan_hash"] = security_scan_artifact.content_hash
    if missing_measurement is not None:
        measurements.pop(missing_measurement)
    payload = {
        "schema_version": "sealed-holdout-evidence-v1",
        "authorization_id": authorization.id,
        "candidate_id": candidate.id,
        "candidate_hash": candidate.candidate_hash,
        "experiment_epoch_id": candidate.experiment_epoch_id,
        "dataset_snapshot_id": sealed.id,
        "sealed_dataset_hash": sealed.content_hash,
        "policy_version": _POLICY.version,
        "evaluator_identity": "evaluator",
        "evaluator_version": evaluator_version,
        "measurements": measurements,
    }
    artifact = await _persist_sealed_evidence_artifact(payload)
    evaluation = ResearchEvaluation(
        experiment_epoch_id=candidate.experiment_epoch_id,
        candidate_id=candidate.id,
        dataset_snapshot_id=sealed.id,
        evaluation_type="SEALED_HOLDOUT",
        evaluator_identity="evaluator",
        evaluator_version=evaluator_version,
        authorization_id=authorization.id,
        returns_artifact_id=artifact.id,
        metrics={},
        gate_inputs={},
        policy_version=_POLICY.version,
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
    )
    async with async_session_maker() as session:
        session.add(evaluation)
        await session.commit()
        await session.refresh(evaluation)
    return {
        **context,
        "sealed": sealed,
        "authorization": authorization,
        "authorization_token": issued.token,
        "artifact": artifact,
        "security_scan_artifact": security_scan_artifact,
        "evaluation": evaluation,
        "measurements": measurements,
    }


async def _persist_sealed_evidence_artifact(payload: dict[str, Any]) -> ResearchArtifact:
    content = canonical_json(payload).encode("utf-8")
    digest = sha256(content).hexdigest()
    artifact = ResearchArtifact(
        kind="sealed_holdout_evidence",
        content_hash=digest,
        storage_uri=f"controlled://sealed-holdout-evidence/{digest}",
        size_bytes=len(content),
        media_type="application/json",
        schema_version="sealed-holdout-evidence-v1",
        producer_identity=str(payload["evaluator_identity"]),
        container_image_digest=str(payload["evaluator_version"]),
    )
    async with async_session_maker() as session:
        session.add(artifact)
        await session.flush()
        session.add(ResearchArtifactContent(artifact_id=artifact.id, content=content))
        await session.commit()
        await session.refresh(artifact)
        return artifact


async def _persist_security_scan_artifact(payload: dict[str, Any]) -> ResearchArtifact:
    content = canonical_json(payload).encode("utf-8")
    digest = sha256(content).hexdigest()
    artifact = ResearchArtifact(
        kind="security_scan_evidence",
        content_hash=digest,
        storage_uri=f"controlled://security-scan-evidence/{digest}",
        size_bytes=len(content),
        media_type="application/json",
        schema_version="security-scan-evidence-v1",
        producer_identity="research-security-scanner",
        container_image_digest=f"sha256:{'5' * 64}",
    )
    async with async_session_maker() as session:
        session.add(artifact)
        await session.flush()
        session.add(ResearchArtifactContent(artifact_id=artifact.id, content=content))
        await session.commit()
        await session.refresh(artifact)
        return artifact


async def _measurements(context: dict[str, Any]) -> dict[str, Any]:
    candidate = context["candidate"]
    discovery = context["discovery"]
    run = context["run"]
    assert isinstance(candidate, ResearchCandidate)
    assert isinstance(discovery, ResearchDatasetSnapshot)
    assert isinstance(run, ResearchRun)
    async with async_session_maker() as session:
        trial = await session.scalar(
            select(ResearchTrial).where(
                ResearchTrial.candidate_id == candidate.id,
                ResearchTrial.run_id == run.id,
                ResearchTrial.counts_as_market_trial.is_(True),
            )
        )
        assert trial is not None and trial.returns_artifact_id is not None
        retained = await session.get(ResearchArtifactContent, trial.returns_artifact_id)
        assert retained is not None
        discovery_payload = json.loads(bytes(retained.content))
    discovery_returns = [float(value) for value in discovery_payload["result"]["returns"]]
    mean = sum(discovery_returns) / len(discovery_returns)
    variance = sum((value - mean) ** 2 for value in discovery_returns) / (
        len(discovery_returns) - 1
    )
    ledger_trial_sharpes = [round(mean / sqrt(variance) * sqrt(252), 12)]
    return {
        "returns": [0.01, 0.005, 0.015, 0.002, 0.003, 0.008],
        "trial_sharpes": ledger_trial_sharpes,
        "discovery_dataset_snapshot_hash": discovery.content_hash,
        "cost_model_hash": candidate.cost_model_hash,
        "environment_hash": candidate.environment_hash,
        "capability_evidence_hash": run.capability_evidence_hash,
        "max_drawdown": 0.10,
        "robustness_score": 0.90,
        "cost_bps": 4.0,
        "slippage_bps": 1.0,
        "turnover": 2.0,
        "capacity_notional": 1_000_000.0,
        "extreme_path_loss": 0.18,
        "execution_semantics_match": True,
        "security_critical_findings": 0,
    }


async def _finalize_evaluation(context: dict[str, Any], result) -> None:
    async with async_session_maker() as session:
        evaluation = await session.get(ResearchEvaluation, context["evaluation"].id)
        epoch = await session.get(ResearchExperimentEpoch, context["epoch"].id)
        assert evaluation is not None and epoch is not None
        evaluation.gate_inputs = {
            "input_evidence_hash": result.input_evidence_hash,
            "strict_freeze_receipt_fingerprint": (result.strict_freeze_receipt_fingerprint),
            "promotion_policy_hash": promotion_policy_material_hash(_POLICY),
            "gate_statuses": {outcome.code: outcome.status for outcome in result.decisions},
        }
        evaluation.metrics = {"promotion_eligible": result.eligible}
        evaluation.status = "PASSED" if result.eligible else "REJECTED"
        evaluation.completed_at = datetime.now(timezone.utc)
        epoch.status = "CLOSED"
        epoch.closed_at = datetime.now(timezone.utc)
        await session.commit()


def _pretty_client_spoof() -> dict[str, Any]:
    return {
        "returns": [1.0, 1.0, 1.0],
        "trial_sharpes": [100.0],
        "max_drawdown": 0.0,
        "robustness_score": 1.0,
        "cost_bps": 0.0,
        "slippage_bps": 0.0,
        "turnover": 0.0,
        "capacity_notional": 10**18,
        "extreme_path_loss": 0.0,
        "execution_semantics_match": True,
        "security_critical_findings": 0,
        "require_robustness": False,
        "require_security_scan": False,
        "sealed_holdout": "PASS",
    }


async def _strict_context(auth_user, suffix: str) -> dict[str, object]:
    from tests.test_ai_research_candidate_freeze_v2 import _published_candidate

    now = datetime.now(timezone.utc)
    profile = CapabilityProfile(
        profile_id=f"promotion-isolated-{sha256(suffix.encode()).hexdigest()[:16]}",
        version="v1",
        service_identities={
            "explorer": "explorer",
            "evaluator": "evaluator",
            "runner": "discovery-runner",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash=sha256(f"promotion-profile:{suffix}".encode()).hexdigest(),
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        stage_image_digests={
            "evaluator": _EVALUATOR_IMAGE_DIGEST,
            "scanner": _SCANNER_IMAGE_DIGEST,
        },
    )
    await CapabilityRegistry().register(profile)
    context, _dispatch, _attempt = await _published_candidate(
        auth_user,
        suffix,
        capability_profile_id=profile.profile_id,
        capability_profile_version=profile.version,
        capability_evidence_hash=profile.evidence_hash,
    )
    candidate_hash = await _candidate_hash(context["candidate_id"])
    candidate = await CandidateRegistry(dataset_registry=context["datasets"]).freeze_discovery(
        user_id=context["task"].user_id,
        candidate_id=context["candidate_id"],
        frozen_by=context["task"].user_id,
        expected_candidate_hash=candidate_hash,
    )
    async with async_session_maker() as session:
        dataset = await session.get(ResearchDatasetSnapshot, candidate.dataset_snapshot_id)
        run = await session.get(ResearchRun, candidate.run_id)
        epoch = await session.get(ResearchExperimentEpoch, candidate.experiment_epoch_id)
        assert dataset is not None and run is not None and epoch is not None
    return {
        "candidate": candidate,
        "dataset": dataset,
        "discovery": dataset,
        "run": run,
        "epoch": epoch,
        "datasets": context["datasets"],
        "resolver": context["resolver"],
        "user_id": context["task"].user_id,
    }


async def _candidate_hash(candidate_id: str) -> str:
    async with async_session_maker() as session:
        candidate = await session.get(ResearchCandidate, candidate_id)
        assert candidate is not None
        return candidate.candidate_hash


async def _context(user_id: str) -> dict[str, object]:
    hypothesis = await HypothesisRegistry().create_draft(user_id, _payload())
    hypothesis = await HypothesisRegistry().confirm(
        user_id, hypothesis.id, request_hash=hypothesis.content_hash
    )
    resolver = InMemoryDatasetObjectResolver()
    receipt = resolver.register(
        DatasetObjectAttestation(
            receipt_id="promotion-discovery-receipt-v1",
            user_id=user_id,
            logical_object_id="promotion-discovery-object",
            object_version="version-1",
            object_digest="d" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://promotion-fixtures/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    dataset = await DatasetRegistry(object_resolver=resolver).create_attested_snapshot(
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
        dataset_snapshot_id=dataset.id,
        experiment_epoch_id=epoch.id,
        promotion_policy_version="promotion-v1",
        request_hash="r" * 64,
        capability_profile_id="profile-v1",
        capability_profile_version="v1",
        capability_evidence_hash="p" * 64,
        trace_id="trace-promotion",
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
    candidate = await CandidateRegistry().create_mutable(
        user_id=user_id,
        run_id=run.id,
        experiment_epoch_id=epoch.id,
        dataset_snapshot_id=dataset.id,
        code_artifact_id=code.id,
        dependency_artifact_id=dependencies.id,
        environment_hash="e" * 64,
        cost_model_hash="c" * 64,
        params={"lookback": 20},
    )
    async with async_session_maker() as session:
        stored_candidate = await session.get(ResearchCandidate, candidate.id)
        assert stored_candidate is not None
        stored_candidate.freeze_status = "FROZEN"
        await session.commit()
        await session.refresh(stored_candidate)
    return {"candidate": stored_candidate, "dataset": dataset, "run": run}


def _evidence(context: dict[str, object], *, max_drawdown: float) -> dict[str, object]:
    candidate = context["candidate"]
    dataset = context["dataset"]
    run = context["run"]
    assert isinstance(candidate, ResearchCandidate)
    assert isinstance(dataset, ResearchDatasetSnapshot)
    assert isinstance(run, ResearchRun)
    return {
        "returns": [0.01, -0.004, 0.015, 0.002, -0.003, 0.008],
        "trial_sharpes": [0.1, 0.3, 0.45, 0.2],
        "dataset_snapshot_hash": dataset.content_hash,
        "cost_model_hash": candidate.cost_model_hash,
        "environment_hash": candidate.environment_hash,
        "capability_evidence_hash": run.capability_evidence_hash,
        "max_drawdown": max_drawdown,
    }


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
