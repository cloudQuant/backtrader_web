from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.research.capabilities import CapabilityProfile, evaluate_capabilities


def _profile(**overrides: object) -> CapabilityProfile:
    values: dict[str, object] = {
        "profile_id": "dev-single-process",
        "version": "2026-09-04",
        "service_identities": {"explorer": "shared", "evaluator": "shared"},
        "queue_isolation": False,
        "storage_isolation": False,
        "network_isolation": False,
        "sandbox_runner": False,
        "approval_mode": "single_actor",
        "evidence_hash": "e" * 64,
        "verified_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "stage_image_digests": {
            "evaluator": f"sha256:{'1' * 64}",
            "scanner": f"sha256:{'2' * 64}",
        },
    }
    values.update(overrides)
    return CapabilityProfile(**values)


def test_dev_single_process_profile_blocks_sealed_holdout_authorization() -> None:
    decision = evaluate_capabilities(_profile(), required=("sealed_evaluation",))

    assert decision.allowed is False
    assert decision.code == "BLOCKED_TOPOLOGY_CAPABILITY"
    assert "sealed_evaluation" in decision.missing_capabilities


def test_expired_profile_blocks_even_when_all_runtime_capabilities_exist() -> None:
    profile = _profile(
        profile_id="single-node-isolated-services",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    decision = evaluate_capabilities(profile, required=("sealed_evaluation", "sandbox"))

    assert decision.allowed is False
    assert decision.code == "BLOCKED_TOPOLOGY_CAPABILITY"
    assert "profile_not_current" in decision.missing_capabilities


def test_isolated_profile_allows_only_evidence_backed_capabilities() -> None:
    profile = _profile(
        profile_id="single-node-isolated-services",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
    )

    decision = evaluate_capabilities(profile, required=("sealed_evaluation", "sandbox"))

    assert decision.allowed is True
    assert decision.missing_capabilities == ()


def test_isolated_profile_without_evaluator_image_digest_blocks_sealed_evaluation() -> None:
    profile = _profile(
        profile_id="single-node-isolated-services",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        stage_image_digests={"scanner": f"sha256:{'2' * 64}"},
    )

    decision = evaluate_capabilities(profile, required=("sealed_evaluation",))

    assert decision.allowed is False
    assert decision.code == "BLOCKED_TOPOLOGY_CAPABILITY"
    assert decision.missing_capabilities == ("sealed_evaluation",)


def test_legacy_profile_without_stage_image_mapping_fails_closed() -> None:
    profile = _profile(
        profile_id="single-node-isolated-services",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        stage_image_digests={},
    )

    decision = evaluate_capabilities(profile, required=("sealed_evaluation",))

    assert decision.allowed is False
    assert decision.code == "BLOCKED_TOPOLOGY_CAPABILITY"
