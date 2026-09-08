"""Fail-closed capability checks for the trusted research protocol."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

BLOCKED_TOPOLOGY_CAPABILITY = "BLOCKED_TOPOLOGY_CAPABILITY"


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    """Server-owned, versioned evidence about one deployment topology."""

    profile_id: str
    version: str
    service_identities: Mapping[str, str]
    queue_isolation: bool
    storage_isolation: bool
    network_isolation: bool
    sandbox_runner: bool
    approval_mode: str
    evidence_hash: str
    verified_at: datetime
    expires_at: datetime
    stage_image_digests: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """The deterministic result of requesting one or more protocol capabilities."""

    allowed: bool
    code: str | None
    required_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    profile_id: str
    profile_version: str


def evaluate_capabilities(
    profile: CapabilityProfile,
    *,
    required: Iterable[str],
    now: datetime | None = None,
) -> CapabilityDecision:
    """Evaluate a server-loaded profile without trusting client declarations."""

    required_capabilities = tuple(dict.fromkeys(required))
    evaluation_time = _as_utc(now or datetime.now(timezone.utc))
    if not _profile_is_current(profile, evaluation_time):
        return CapabilityDecision(
            allowed=False,
            code=BLOCKED_TOPOLOGY_CAPABILITY,
            required_capabilities=required_capabilities,
            missing_capabilities=("profile_not_current", *required_capabilities),
            profile_id=profile.profile_id,
            profile_version=profile.version,
        )
    available = _available_capabilities(profile, evaluation_time)
    missing = tuple(
        capability for capability in required_capabilities if capability not in available
    )
    return CapabilityDecision(
        allowed=not missing,
        code=None if not missing else BLOCKED_TOPOLOGY_CAPABILITY,
        required_capabilities=required_capabilities,
        missing_capabilities=missing,
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )


def _available_capabilities(profile: CapabilityProfile, now: datetime) -> frozenset[str]:
    if not _profile_is_current(profile, now):
        return frozenset()

    capabilities = {"protocol_v2"}
    if profile.sandbox_runner:
        capabilities.add("sandbox")
    if _has_sealed_evaluator_boundary(profile):
        capabilities.add("sealed_evaluation")
    if profile.approval_mode == "multi_actor":
        capabilities.add("multi_actor_approval")
    return frozenset(capabilities)


def _profile_is_current(profile: CapabilityProfile, now: datetime) -> bool:
    if not profile.version or len(profile.evidence_hash) != 64:
        return False
    try:
        int(profile.evidence_hash, 16)
    except ValueError:
        return False
    return _as_utc(profile.expires_at) > now and _as_utc(profile.verified_at) <= now


def _has_sealed_evaluator_boundary(profile: CapabilityProfile) -> bool:
    if profile.profile_id == "dev-single-process":
        return False
    explorer = profile.service_identities.get("explorer", "")
    evaluator = profile.service_identities.get("evaluator", "")
    return bool(
        explorer
        and evaluator
        and explorer != evaluator
        and _has_stage_image_digest(profile, "evaluator")
        and profile.queue_isolation
        and profile.storage_isolation
        and profile.network_isolation
    )


def _has_stage_image_digest(profile: CapabilityProfile, stage: str) -> bool:
    if not isinstance(profile.stage_image_digests, Mapping):
        return False
    digest = profile.stage_image_digests.get(stage)
    return isinstance(digest, str) and bool(digest.strip())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CAPABILITY_PROFILE_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)
