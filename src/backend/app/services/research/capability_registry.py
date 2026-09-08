"""Database-backed registry for deployment capability evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db import database
from app.models.ai_research_v2 import ResearchCapabilityProfile
from app.services.research.approval_authority import server_approval_capabilities
from app.services.research.capabilities import (
    BLOCKED_TOPOLOGY_CAPABILITY,
    CapabilityDecision,
    CapabilityProfile,
    evaluate_capabilities,
)


class CapabilityRegistry:
    """Persist and resolve server-owned capability profile versions."""

    async def register(self, profile: CapabilityProfile) -> ResearchCapabilityProfile:
        """Register an immutable evidence-backed profile version idempotently."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchCapabilityProfile).where(
                    ResearchCapabilityProfile.profile_id == profile.profile_id,
                    ResearchCapabilityProfile.version == profile.version,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                if _as_profile(existing) != profile:
                    raise ValueError("CAPABILITY_PROFILE_VERSION_CONFLICT")
                return existing

            model = ResearchCapabilityProfile(
                profile_id=profile.profile_id,
                version=profile.version,
                topology=profile.profile_id,
                actor_mode=profile.approval_mode,
                service_identities=dict(profile.service_identities),
                queue_capabilities={"isolated": profile.queue_isolation},
                storage_boundaries={"isolated": profile.storage_isolation},
                network_capabilities={"isolated": profile.network_isolation},
                sandbox_capabilities={
                    "runner": profile.sandbox_runner,
                    "stage_image_digests": dict(profile.stage_image_digests),
                },
                approval_capabilities=server_approval_capabilities(profile.approval_mode),
                evidence_hash=profile.evidence_hash,
                verified_at=profile.verified_at,
                expires_at=profile.expires_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model

    async def get(
        self,
        profile_id: str,
        version: str,
    ) -> CapabilityProfile | None:
        """Get exactly one profile version; no implicit development fallback."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchCapabilityProfile).where(
                    ResearchCapabilityProfile.profile_id == profile_id,
                    ResearchCapabilityProfile.version == version,
                )
            )
            model = result.scalar_one_or_none()
        return _as_profile(model) if model is not None else None

    async def evaluate(
        self,
        profile_id: str,
        version: str,
        *,
        required: tuple[str, ...],
    ) -> CapabilityDecision:
        """Fail closed if deployment evidence cannot be resolved and verified."""

        profile = await self.get(profile_id, version)
        if profile is None:
            return CapabilityDecision(
                allowed=False,
                code=BLOCKED_TOPOLOGY_CAPABILITY,
                required_capabilities=required,
                missing_capabilities=("profile_not_found", *required),
                profile_id=profile_id,
                profile_version=version,
            )
        return evaluate_capabilities(profile, required=required)


def _as_profile(model: ResearchCapabilityProfile) -> CapabilityProfile:
    return CapabilityProfile(
        profile_id=model.profile_id,
        version=model.version,
        service_identities=dict(model.service_identities or {}),
        queue_isolation=bool((model.queue_capabilities or {}).get("isolated")),
        storage_isolation=bool((model.storage_boundaries or {}).get("isolated")),
        network_isolation=bool((model.network_capabilities or {}).get("isolated")),
        sandbox_runner=bool((model.sandbox_capabilities or {}).get("runner")),
        approval_mode=str((model.approval_capabilities or {}).get("mode") or model.actor_mode),
        evidence_hash=model.evidence_hash,
        verified_at=_from_storage_time(model.verified_at),
        expires_at=_from_storage_time(model.expires_at),
        stage_image_digests=_stage_image_digests(model),
    )


def _stage_image_digests(model: ResearchCapabilityProfile) -> dict[str, str]:
    sandbox_capabilities = model.sandbox_capabilities or {}
    value = sandbox_capabilities.get("stage_image_digests")
    if not isinstance(value, dict):
        return {}
    return {
        key: digest
        for key, digest in value.items()
        if isinstance(key, str) and isinstance(digest, str)
    }


def _from_storage_time(value: datetime) -> datetime:
    """Normalize SQLite's timezone-less storage round-trip as UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
