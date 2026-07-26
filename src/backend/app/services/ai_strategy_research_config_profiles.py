"""Local YAML-backed configuration profiles for AI strategy research."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from app.schemas.ai_strategy_research import (
    AIStrategyResearchConfigProfile,
    AIStrategyResearchConfigProfileCreate,
    AIStrategyResearchConfigProfileImportResponse,
    AIStrategyResearchConfigProfileListResponse,
    AIStrategyResearchConfigProfileUpdate,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "ai_research_profiles.yaml"
_PROFILE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class AIStrategyResearchConfigProfileService:
    """Persist reusable AI research form profiles in a local YAML file."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or _DEFAULT_CONFIG_PATH

    async def list_profiles(self) -> AIStrategyResearchConfigProfileListResponse:
        """Return all local configuration profiles."""
        profiles = self._read_profiles()
        return AIStrategyResearchConfigProfileListResponse(
            file_path=str(self.config_path),
            total=len(profiles),
            items=profiles,
        )

    async def get_profile(self, profile_id: str) -> AIStrategyResearchConfigProfile | None:
        """Return one profile by id."""
        return self._profile_by_id(profile_id)

    async def create_profile(
        self, data: AIStrategyResearchConfigProfileCreate
    ) -> AIStrategyResearchConfigProfile:
        """Create a profile and write the YAML file."""
        profiles = self._read_profiles()
        profile_id = data.id or self._generate_profile_id(data.name, profiles)
        if any(profile.id == profile_id for profile in profiles):
            raise ValueError("AI research config profile already exists")
        now = self._now()
        profile = AIStrategyResearchConfigProfile(
            id=profile_id,
            name=data.name.strip(),
            description=(data.description or "").strip(),
            config=self._yaml_safe_value(data.config),
            created_at=now,
            updated_at=now,
        )
        profiles.append(profile)
        self._write_profiles(profiles)
        return profile

    async def update_profile(
        self,
        profile_id: str,
        data: AIStrategyResearchConfigProfileUpdate,
    ) -> AIStrategyResearchConfigProfile | None:
        """Update an existing profile and write the YAML file."""
        profiles = self._read_profiles()
        updated: AIStrategyResearchConfigProfile | None = None
        now = self._now()
        next_profiles: list[AIStrategyResearchConfigProfile] = []
        for profile in profiles:
            if profile.id != profile_id:
                next_profiles.append(profile)
                continue
            payload: dict[str, Any] = {"updated_at": now}
            if data.name is not None:
                payload["name"] = data.name.strip()
            if data.description is not None:
                payload["description"] = data.description.strip()
            if data.config is not None:
                payload["config"] = self._yaml_safe_value(data.config)
            updated = profile.model_copy(update=payload)
            next_profiles.append(updated)
        if updated is None:
            return None
        self._write_profiles(next_profiles)
        return updated

    async def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile from the local YAML file."""
        profiles = self._read_profiles()
        next_profiles = [profile for profile in profiles if profile.id != profile_id]
        if len(next_profiles) == len(profiles):
            return False
        self._write_profiles(next_profiles)
        return True

    async def import_profiles(
        self,
        raw_yaml: str,
        *,
        fallback_name: str | None = None,
        fallback_profile_id: str | None = None,
    ) -> AIStrategyResearchConfigProfileImportResponse:
        """Import one or more profiles from YAML text and upsert them."""
        imported_profiles = self._profiles_from_yaml_text(
            raw_yaml,
            fallback_name=fallback_name,
            fallback_profile_id=fallback_profile_id,
        )
        existing = self._read_profiles()
        existing_by_id = {profile.id: profile for profile in existing}
        ordered_ids = [profile.id for profile in existing]
        now = self._now()
        saved: list[AIStrategyResearchConfigProfile] = []
        for profile in imported_profiles:
            previous = existing_by_id.get(profile.id)
            created_at = (
                profile.created_at or previous.created_at if previous else profile.created_at
            )
            next_profile = profile.model_copy(
                update={
                    "created_at": created_at or now,
                    "updated_at": now,
                    "config": self._yaml_safe_value(profile.config),
                }
            )
            existing_by_id[profile.id] = next_profile
            if profile.id not in ordered_ids:
                ordered_ids.append(profile.id)
            saved.append(next_profile)
        self._write_profiles([existing_by_id[profile_id] for profile_id in ordered_ids])
        return AIStrategyResearchConfigProfileImportResponse(
            file_path=str(self.config_path),
            total=len(saved),
            items=saved,
        )

    def _profile_by_id(self, profile_id: str) -> AIStrategyResearchConfigProfile | None:
        return next(
            (profile for profile in self._read_profiles() if profile.id == profile_id), None
        )

    def _read_profiles(self) -> list[AIStrategyResearchConfigProfile]:
        document = self._read_yaml_document()
        raw_profiles = document.get("profiles", [])
        if raw_profiles is None:
            raw_profiles = []
        if isinstance(raw_profiles, dict):
            raw_profiles = [
                {"id": str(profile_id), **dict(profile or {})}
                for profile_id, profile in raw_profiles.items()
                if isinstance(profile, dict)
            ]
        if not isinstance(raw_profiles, list):
            raise ValueError("AI research config YAML field 'profiles' must be a list or mapping")
        profiles: list[AIStrategyResearchConfigProfile] = []
        for index, raw_profile in enumerate(raw_profiles):
            if not isinstance(raw_profile, dict):
                raise ValueError(f"AI research config profile at index {index} must be a mapping")
            profile_data = deepcopy(raw_profile)
            profile_data["id"] = str(profile_data.get("id") or "").strip()
            profile_data["name"] = str(profile_data.get("name") or profile_data["id"]).strip()
            profile_data["description"] = str(profile_data.get("description") or "").strip()
            config = profile_data.get("config")
            if config is None:
                config = self._extract_inline_config(profile_data)
            if not isinstance(config, dict):
                raise ValueError(
                    f"AI research config profile {profile_data['id']!r} config must be a mapping"
                )
            profile_data["config"] = self._yaml_safe_value(config)
            profiles.append(AIStrategyResearchConfigProfile.model_validate(profile_data))
        return profiles

    def _read_yaml_document(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"version": 1, "profiles": []}
        try:
            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse AI research config YAML: {exc}") from exc
        except OSError as exc:
            raise ValueError(f"Failed to read AI research config YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("AI research config YAML must contain a mapping")
        return raw

    def _write_profiles(self, profiles: list[AIStrategyResearchConfigProfile]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "version": 1,
            "profiles": [
                profile.model_dump(mode="json", exclude_none=True)
                for profile in sorted(profiles, key=lambda item: item.name.lower())
            ],
        }
        text = yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
        self.config_path.write_text(text, encoding="utf-8")

    def _profiles_from_yaml_text(
        self,
        raw_yaml: str,
        *,
        fallback_name: str | None,
        fallback_profile_id: str | None,
    ) -> list[AIStrategyResearchConfigProfile]:
        try:
            raw = yaml.safe_load(raw_yaml) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse selected YAML file: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("Selected YAML file must contain a mapping")
        if isinstance(raw.get("profiles"), list):
            candidates = raw["profiles"]
        elif isinstance(raw.get("profiles"), dict):
            candidates = [
                {"id": str(profile_id), **dict(profile or {})}
                for profile_id, profile in raw["profiles"].items()
                if isinstance(profile, dict)
            ]
        else:
            candidates = [raw]
        profiles: list[AIStrategyResearchConfigProfile] = []
        existing_ids: set[str] = set()
        now = self._now()
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ValueError(f"Selected YAML profile at index {index} must be a mapping")
            profile = self._profile_from_yaml_mapping(
                candidate,
                fallback_name=fallback_name,
                fallback_profile_id=fallback_profile_id,
                existing_ids=existing_ids,
                now=now,
            )
            existing_ids.add(profile.id)
            profiles.append(profile)
        if not profiles:
            raise ValueError("Selected YAML file did not contain any AI research config profiles")
        return profiles

    def _profile_from_yaml_mapping(
        self,
        data: dict[str, Any],
        *,
        fallback_name: str | None,
        fallback_profile_id: str | None,
        existing_ids: set[str],
        now: str,
    ) -> AIStrategyResearchConfigProfile:
        config = data.get("config")
        if config is None:
            config = self._extract_inline_config(data)
        if not isinstance(config, dict):
            raise ValueError("Selected YAML profile config must be a mapping")
        name = str(data.get("name") or fallback_name or "导入配置").strip()
        profile_id = str(data.get("id") or fallback_profile_id or "").strip()
        if not profile_id:
            profile_id = self._generate_profile_id(name, self._read_profiles(), existing_ids)
        elif profile_id in existing_ids:
            profile_id = self._generate_profile_id(profile_id, self._read_profiles(), existing_ids)
        return AIStrategyResearchConfigProfile(
            id=profile_id,
            name=name,
            description=str(data.get("description") or "").strip(),
            config=self._yaml_safe_value(config),
            created_at=str(data.get("created_at") or now),
            updated_at=str(data.get("updated_at") or now),
        )

    @staticmethod
    def _extract_inline_config(data: dict[str, Any]) -> dict[str, Any]:
        metadata_keys = {"id", "name", "description", "created_at", "updated_at"}
        return {key: deepcopy(value) for key, value in data.items() if key not in metadata_keys}

    def _generate_profile_id(
        self,
        seed: str,
        profiles: list[AIStrategyResearchConfigProfile],
        extra_ids: set[str] | None = None,
    ) -> str:
        base = _PROFILE_ID_PATTERN.sub("-", seed.strip().lower()).strip(".-_") or "profile"
        used_ids = {profile.id for profile in profiles}
        if extra_ids:
            used_ids.update(extra_ids)
        if base not in used_ids:
            return base[:80]
        for suffix in range(2, 1000):
            candidate = f"{base}-{suffix}"[:80]
            if candidate not in used_ids:
                return candidate
        return f"{base[:67]}-{uuid4().hex[:12]}"

    @staticmethod
    def _yaml_safe_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): AIStrategyResearchConfigProfileService._yaml_safe_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [AIStrategyResearchConfigProfileService._yaml_safe_value(item) for item in value]
        if isinstance(value, tuple):
            return [AIStrategyResearchConfigProfileService._yaml_safe_value(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
