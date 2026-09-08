from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry


@pytest.mark.asyncio
async def test_registry_binds_evidence_backed_profile_version_to_a_v2_decision() -> None:
    registry = CapabilityRegistry()
    profile = CapabilityProfile(
        profile_id="single-node-isolated-services",
        version="2026-09-04.1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        stage_image_digests={
            "evaluator": f"sha256:{'1' * 64}",
            "scanner": f"sha256:{'2' * 64}",
        },
    )

    await registry.register(profile)
    stored = await registry.get(profile.profile_id, profile.version)
    decision = await registry.evaluate(
        profile.profile_id,
        profile.version,
        required=("sealed_evaluation", "sandbox", "multi_actor_approval"),
    )

    assert stored is not None
    assert stored == profile
    assert stored.stage_image_digests == profile.stage_image_digests
    assert decision.allowed is True
    assert decision.profile_id == profile.profile_id
    assert decision.profile_version == profile.version


@pytest.mark.asyncio
async def test_unknown_profile_fails_closed_without_implicit_development_fallback() -> None:
    decision = await CapabilityRegistry().evaluate(
        "missing-profile",
        "missing-version",
        required=("sealed_evaluation",),
    )

    assert decision.allowed is False
    assert decision.code == "BLOCKED_TOPOLOGY_CAPABILITY"
    assert decision.missing_capabilities == ("profile_not_found", "sealed_evaluation")


@pytest.mark.asyncio
async def test_same_profile_version_rejects_stage_image_mapping_change() -> None:
    registry = CapabilityRegistry()
    now = datetime.now(timezone.utc)
    profile = CapabilityProfile(
        profile_id="isolated-image-version-conflict",
        version="2026-09-07.1",
        service_identities={
            "explorer": "ai_research_explorer",
            "evaluator": "ai_research_evaluator",
        },
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="e" * 64,
        verified_at=now,
        expires_at=now + timedelta(days=1),
        stage_image_digests={
            "evaluator": f"sha256:{'1' * 64}",
            "scanner": f"sha256:{'2' * 64}",
        },
    )
    await registry.register(profile)
    changed = CapabilityProfile(
        profile_id=profile.profile_id,
        version=profile.version,
        service_identities=profile.service_identities,
        queue_isolation=profile.queue_isolation,
        storage_isolation=profile.storage_isolation,
        network_isolation=profile.network_isolation,
        sandbox_runner=profile.sandbox_runner,
        approval_mode=profile.approval_mode,
        evidence_hash=profile.evidence_hash,
        verified_at=profile.verified_at,
        expires_at=profile.expires_at,
        stage_image_digests={
            "evaluator": f"sha256:{'3' * 64}",
            "scanner": f"sha256:{'2' * 64}",
        },
    )

    with pytest.raises(ValueError, match="CAPABILITY_PROFILE_VERSION_CONFLICT"):
        await registry.register(changed)
