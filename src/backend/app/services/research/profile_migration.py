"""Safe quarantine-and-claim migration for legacy YAML research profiles."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import database
from app.models.ai_research_v2 import ResearchConfigProfile
from app.services.research.canonical import content_hash

_MAX_DEPTH = 12
_METADATA_KEYS = frozenset({"id", "name", "description", "created_at", "updated_at"})
_REFERENCE_KEYS = frozenset({"credentialref", "gatewayprofileid", "credentialrefs"})
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|credential|password|private[_-]?key|secret|token|access[_-]?key)",
    re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{8,}|\bBearer\s+\S+|\b(?:api[_-]?key|token|secret|password)\s*[=:])",
    re.IGNORECASE,
)
_DROP = object()


class ProfileMigrationService:
    """Convert legacy profile YAML into ownerless, secret-free quarantine rows."""

    async def migrate_yaml(
        self,
        raw_yaml: str,
        *,
        source_label: str,
    ) -> list[ResearchConfigProfile]:
        """Store no legacy profile as active until a user explicitly claims it."""

        candidates = _parse_profiles(raw_yaml)
        if not source_label.strip():
            raise ValueError("PROFILE_MIGRATION_SOURCE_LABEL_REQUIRED")
        migrated: list[ResearchConfigProfile] = []
        async with database.async_session_maker() as session:
            for index, raw in enumerate(candidates):
                raw_hash = content_hash(
                    {"source_label": source_label, "index": index, "legacy_profile": raw}
                )
                existing_result = await session.execute(
                    select(ResearchConfigProfile).where(
                        ResearchConfigProfile.legacy_source_hash == raw_hash
                    )
                )
                existing = existing_result.scalar_one_or_none()
                if existing is not None:
                    migrated.append(existing)
                    continue
                name = str(
                    raw.get("name") or raw.get("id") or f"Imported profile {index + 1}"
                ).strip()
                if not name:
                    raise ValueError("PROFILE_MIGRATION_NAME_REQUIRED")
                config = raw.get("config")
                if config is None:
                    config = {key: value for key, value in raw.items() if key not in _METADATA_KEYS}
                if not isinstance(config, dict):
                    raise ValueError("PROFILE_MIGRATION_CONFIG_INVALID")
                safe_config, credential_refs, dropped_paths = _sanitize_config(config)
                reasons = ["OWNER_UNRESOLVED"]
                if dropped_paths:
                    reasons.append("SECRET_FIELDS_DROPPED")
                model = ResearchConfigProfile(
                    legacy_source_id=str(raw.get("id") or "").strip() or None,
                    legacy_source_hash=raw_hash,
                    name=name,
                    description=str(raw.get("description") or "").strip(),
                    config=safe_config,
                    credential_refs=credential_refs,
                    status="QUARANTINED",
                    quarantine_reason=";".join(reasons),
                )
                session.add(model)
                migrated.append(model)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise ValueError("PROFILE_MIGRATION_IDEMPOTENCY_CONFLICT") from None
            for model in migrated:
                await session.refresh(model)
        return migrated

    async def claim(
        self,
        *,
        user_id: str,
        profile_id: str,
        workspace_id: str | None = None,
        now: datetime | None = None,
    ) -> ResearchConfigProfile:
        """Assign an isolated profile only through an explicit authenticated claim."""

        claim_time = _as_utc(now or _now())
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchConfigProfile)
                .where(ResearchConfigProfile.id == profile_id)
                .with_for_update()
            )
            profile = result.scalar_one_or_none()
            if profile is None:
                raise ValueError("RESEARCH_CONFIG_PROFILE_NOT_FOUND")
            if profile.status == "RETIRED":
                raise ValueError("RESEARCH_CONFIG_PROFILE_RETIRED")
            if profile.owner_user_id is not None and profile.owner_user_id != user_id:
                raise ValueError("RESEARCH_CONFIG_PROFILE_OWNER_DENIED")
            profile.owner_user_id = user_id
            profile.workspace_id = workspace_id
            profile.claimed_by = user_id
            profile.claimed_at = claim_time
            profile.status = "ACTIVE"
            profile.quarantine_reason = None
            await session.commit()
            await session.refresh(profile)
            return profile

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        config: dict[str, Any],
        workspace_id: str | None = None,
        description: str = "",
    ) -> ResearchConfigProfile:
        """Create a directly owned v2 profile and refuse values that look secret-bearing."""

        if not name.strip() or not isinstance(config, dict):
            raise ValueError("RESEARCH_CONFIG_PROFILE_INVALID")
        safe_config, credential_refs, dropped_paths = _sanitize_config(config)
        if dropped_paths:
            raise ValueError("RESEARCH_CONFIG_PROFILE_SECRET_FIELD_DENIED")
        model = ResearchConfigProfile(
            owner_user_id=user_id,
            workspace_id=workspace_id,
            name=name.strip(),
            description=description.strip(),
            config=safe_config,
            credential_refs=credential_refs,
            status="ACTIVE",
            claimed_by=user_id,
            claimed_at=_now(),
        )
        async with database.async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return model

    async def list_for_user(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ) -> list[ResearchConfigProfile]:
        """Return only active profiles owned by the authenticated user."""

        async with database.async_session_maker() as session:
            statement = select(ResearchConfigProfile).where(
                ResearchConfigProfile.owner_user_id == user_id,
                ResearchConfigProfile.status == "ACTIVE",
            )
            if workspace_id is not None:
                statement = statement.where(ResearchConfigProfile.workspace_id == workspace_id)
            result = await session.execute(
                statement.order_by(ResearchConfigProfile.updated_at.desc())
            )
            return list(result.scalars())

    async def get_for_user(self, *, user_id: str, profile_id: str) -> ResearchConfigProfile | None:
        """Read one active owner-scoped profile without enumerating another user's data."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchConfigProfile).where(
                    ResearchConfigProfile.id == profile_id,
                    ResearchConfigProfile.owner_user_id == user_id,
                    ResearchConfigProfile.status == "ACTIVE",
                )
            )
            return result.scalar_one_or_none()


def _parse_profiles(raw_yaml: str) -> list[dict[str, Any]]:
    try:
        raw = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise ValueError("PROFILE_MIGRATION_YAML_INVALID") from exc
    if not isinstance(raw, dict):
        raise ValueError("PROFILE_MIGRATION_YAML_ROOT_INVALID")
    profiles = raw.get("profiles", raw)
    if isinstance(profiles, dict) and "profiles" in raw:
        candidates = [
            {"id": str(profile_id), **dict(profile or {})}
            for profile_id, profile in profiles.items()
            if isinstance(profile, dict)
        ]
    elif isinstance(profiles, list):
        candidates = profiles
    else:
        candidates = [raw]
    if not candidates or any(not isinstance(candidate, dict) for candidate in candidates):
        raise ValueError("PROFILE_MIGRATION_PROFILE_INVALID")
    return [deepcopy(candidate) for candidate in candidates]


def _sanitize_config(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    credential_refs: dict[str, str] = {}
    dropped_paths: list[str] = []
    safe = _sanitize_value(config, "config", credential_refs, dropped_paths, depth=0)
    assert isinstance(safe, dict)
    return safe, credential_refs, dropped_paths


def _sanitize_value(
    value: Any,
    path: str,
    credential_refs: dict[str, str],
    dropped_paths: list[str],
    *,
    depth: int,
) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError("PROFILE_MIGRATION_DEPTH_EXCEEDED")
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("PROFILE_MIGRATION_CONFIG_KEY_INVALID")
            child_path = f"{path}.{key}"
            normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized_key in _REFERENCE_KEYS:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("RESEARCH_CONFIG_PROFILE_CREDENTIAL_REF_INVALID")
                credential_refs[child_path] = item.strip()
                continue
            if _SENSITIVE_KEY.search(key):
                dropped_paths.append(child_path)
                continue
            next_value = _sanitize_value(
                item, child_path, credential_refs, dropped_paths, depth=depth + 1
            )
            if next_value is not _DROP:
                sanitized[key] = next_value
        return sanitized
    if isinstance(value, list):
        sanitized_items = []
        for index, item in enumerate(value):
            next_value = _sanitize_value(
                item,
                f"{path}[{index}]",
                credential_refs,
                dropped_paths,
                depth=depth + 1,
            )
            if next_value is not _DROP:
                sanitized_items.append(next_value)
        return sanitized_items
    if isinstance(value, str) and _SENSITIVE_VALUE.search(value):
        dropped_paths.append(path)
        return _DROP
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("PROFILE_MIGRATION_CONFIG_VALUE_INVALID")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("PROFILE_MIGRATION_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)
