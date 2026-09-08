from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchConfigProfile
from app.models.user import User
from app.services.research.profile_migration import ProfileMigrationService
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_legacy_yaml_profiles_are_quarantined_secret_free_and_explicitly_claimed(
    client,
    auth_user,
) -> None:
    user_id = await _user_id(auth_user)
    service = ProfileMigrationService()

    migrated = await service.migrate_yaml(
        """
profiles:
  - id: legacy-futures
    name: Legacy Futures
    description: profile imported from local disk
    config:
      symbol: RB0
      api_key: should-never-persist
      nested:
        bearer_token: should-never-persist
      credential_ref: vault://research/provider
      gateway_profile_id: gateway-profile-1
""",
        source_label="config/ai_research_profiles.yaml",
    )

    assert len(migrated) == 1
    profile = migrated[0]
    assert profile.status == "QUARANTINED"
    assert profile.owner_user_id is None
    assert profile.config == {"symbol": "RB0", "nested": {}}
    assert profile.credential_refs == {
        "config.credential_ref": "vault://research/provider",
        "config.gateway_profile_id": "gateway-profile-1",
    }
    assert profile.quarantine_reason == "OWNER_UNRESOLVED;SECRET_FIELDS_DROPPED"
    assert await service.list_for_user(user_id=user_id) == []

    claimed = await service.claim(user_id=user_id, profile_id=profile.id)
    assert claimed.status == "ACTIVE"
    assert claimed.owner_user_id == user_id
    assert claimed.claimed_by == user_id
    assert (await service.get_for_user(user_id=user_id, profile_id=profile.id)) is not None

    _, other_headers = await register_and_login(client, username="profile-migration-other")
    other_id = await _user_id(({"username": "profile-migration-other"}, other_headers))
    assert await service.get_for_user(user_id=other_id, profile_id=profile.id) is None
    with pytest.raises(ValueError, match="RESEARCH_CONFIG_PROFILE_OWNER_DENIED"):
        await service.claim(user_id=other_id, profile_id=profile.id)

    async with async_session_maker() as session:
        stored = await session.get(ResearchConfigProfile, profile.id)
    assert stored is not None
    assert "should-never-persist" not in str(stored.config)


@pytest.mark.asyncio
async def test_v2_profile_creation_refuses_secret_values_and_migration_rejects_deep_yaml(
    auth_user,
) -> None:
    user_id = await _user_id(auth_user)
    service = ProfileMigrationService()

    with pytest.raises(ValueError, match="RESEARCH_CONFIG_PROFILE_SECRET_FIELD_DENIED"):
        await service.create(
            user_id=user_id,
            name="unsafe",
            config={"provider_token": "secret"},
        )

    nested: object = "leaf"
    for _ in range(14):
        nested = {"next": nested}
    with pytest.raises(ValueError, match="PROFILE_MIGRATION_DEPTH_EXCEEDED"):
        await service.migrate_yaml(
            "profiles:\n  - id: too-deep\n    config:\n      nested: " + _yaml_nested(nested, 8),
            source_label="deep.yaml",
        )


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())


def _yaml_nested(value: object, indent: int) -> str:
    if not isinstance(value, dict):
        return "leaf\n"
    key, child = next(iter(value.items()))
    prefix = " " * indent
    return f"\n{prefix}{key}: " + _yaml_nested(child, indent + 2)
