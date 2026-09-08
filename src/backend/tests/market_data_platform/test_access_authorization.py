"""Current-principal and registry authorization contracts for market-data reads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.permission import Role, user_roles
from app.models.user import User
from app.services.market_data.access import (
    MarketDataAccessAuthorizer,
    MarketDataAuthorizationError,
    MarketDataQueryAccess,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


class _Provider:
    async def fetch(self, _request: object) -> object:
        raise AssertionError("authorization tests must not call providers")


def _route(
    *, route_id: str = "akshare-stock-v1", provider_id: str = "akshare"
) -> MarketDataProviderRoute:
    return MarketDataProviderRoute(
        route_id=route_id,
        request_provider=provider_id.removeprefix("openbb:"),
        expected_result_provider_ids=frozenset({provider_id}),
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=_Provider(),
    )


def _policy(*routes: MarketDataProviderRoute) -> MarketDataSourcePolicy:
    return MarketDataSourcePolicy(
        policy_id="market-public-v1",
        allowed_purposes=frozenset({"display", "research", "backtest"}),
        routes=routes,
    )


def _registry(
    *,
    source_id: str = "akshare",
    enabled: bool = True,
    license_status: str = "APPROVED",
    allowed_uses: list[str] | None = None,
    jurisdictions: list[str] | None = None,
    effective_from: datetime = datetime(2020, 1, 1, tzinfo=UTC),
    effective_to: datetime | None = None,
    retention_policy: str = "market-data-v1",
    retention_expires_at: datetime | None = None,
    redistribution_policy: str = "NO_REDISTRIBUTION",
) -> AssetDataSourceRegistry:
    return AssetDataSourceRegistry(
        source_id=source_id,
        asset_types=["stock"],
        jurisdictions=jurisdictions or ["CN"],
        license_status=license_status,
        allowed_uses=allowed_uses or ["DISPLAY"],
        redistribution_policy=redistribution_policy,
        derived_data_policy="ALLOWED",
        retention_policy=retention_policy,
        retention_expires_at=retention_expires_at,
        effective_from=effective_from,
        effective_to=effective_to,
        enabled=enabled,
        updated_at=NOW,
    )


async def _user_with_roles(*roles: Role | str) -> User:
    async with async_session_maker() as session:
        user = User(
            username=f"market-access-{len(roles)}-{datetime.now(UTC).timestamp()}",
            email=f"market-access-{datetime.now(UTC).timestamp()}@example.test",
            hashed_password="not-used",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        for role in roles:
            await session.execute(
                user_roles.insert().values(user_id=user.id, role=str(getattr(role, "value", role)))
            )
        await session.commit()
        return user


@pytest.mark.asyncio
async def test_current_principal_requires_explicit_read_data_entitlement() -> None:
    """An authenticated user with no role cannot enter a local market-data read."""
    user = await _user_with_roles()
    async with async_session_maker() as session:
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)

        assert principal.can_read_data is False
        with pytest.raises(MarketDataAuthorizationError) as early_denied:
            authorizer.require_read_data(principal=principal)
        with pytest.raises(MarketDataAuthorizationError) as denied:
            await authorizer.authorize_policy(
                principal=principal,
                policy=_policy(_route()),
                routes=(_route(),),
                asset_type="stock",
                market="CN-SSE",
                purpose="display",
            )

    assert early_denied.value.code == "MARKET_DATA_READ_ENTITLEMENT_DENIED"
    assert denied.value.code == "MARKET_DATA_READ_ENTITLEMENT_DENIED"


@pytest.mark.asyncio
async def test_registry_grant_binds_principal_entitlement_and_source_descriptor() -> None:
    """A permitted source produces immutable, non-secret evidence for persistence."""
    user = await _user_with_roles(Role.USER)
    route = _route()
    async with async_session_maker() as session:
        session.add(_registry())
        await session.commit()
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)
        grant = await authorizer.authorize_policy(
            principal=principal,
            policy=_policy(route),
            routes=(route,),
            asset_type="stock",
            market="CN-SSE",
            purpose="display",
        )

    assert grant.authorized_route_ids == {"akshare-stock-v1"}
    assert grant.authorized_source_registry_ids == {"akshare"}
    assert len(grant.policy_descriptor_hash) == 64
    authorization = grant.authorization_for_route("akshare-stock-v1")
    assert authorization.decision == "ALLOW"
    assert authorization.source_registry_id == "akshare"
    assert authorization.principal_scope == principal.principal_scope
    assert authorization.entitlement_revision == principal.entitlement_revision
    assert authorization.as_provenance()["descriptor_hash"] == authorization.descriptor_hash
    access = MarketDataQueryAccess(principal=principal, authorizer=authorizer)
    assert access.principal == principal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("registry_changes", "expected_code"),
    [
        ({"enabled": False}, "SOURCE_REGISTRY_DISABLED"),
        ({"license_status": "UNKNOWN"}, "SOURCE_LICENSE_DENIED"),
        ({"allowed_uses": ["RESEARCH_ONLY"]}, "SOURCE_USE_DENIED"),
        ({"jurisdictions": ["US"]}, "SOURCE_JURISDICTION_DENIED"),
        ({"effective_from": NOW + timedelta(seconds=1)}, "SOURCE_EFFECTIVE_WINDOW_DENIED"),
        ({"effective_to": NOW - timedelta(seconds=1)}, "SOURCE_EFFECTIVE_WINDOW_DENIED"),
        ({"retention_policy": "EXPIRED"}, "SOURCE_RETENTION_DENIED"),
        ({"retention_expires_at": NOW - timedelta(seconds=1)}, "SOURCE_RETENTION_DENIED"),
        ({"redistribution_policy": "UNKNOWN"}, "SOURCE_REDISTRIBUTION_DENIED"),
    ],
)
async def test_source_registry_denials_happen_before_any_provider_route_is_authorized(
    registry_changes: dict[str, object],
    expected_code: str,
) -> None:
    """Every current licence/read restriction has a deterministic denial code."""
    user = await _user_with_roles(Role.USER)
    route = _route()
    async with async_session_maker() as session:
        session.add(_registry(**registry_changes))
        await session.commit()
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)
        with pytest.raises(MarketDataAuthorizationError) as denied:
            await authorizer.authorize_route(
                principal=principal,
                route=route,
                asset_type="stock",
                market="CN-SSE",
                purpose="display",
            )

    assert denied.value.code == expected_code


@pytest.mark.asyncio
async def test_policy_preflight_can_select_only_currently_authorized_fallback_routes() -> None:
    """A disabled primary source cannot receive a call when an approved fallback exists."""
    user = await _user_with_roles(Role.USER)
    primary = _route(route_id="primary", provider_id="akshare")
    fallback = _route(route_id="fallback", provider_id="openbb:yfinance")
    async with async_session_maker() as session:
        session.add(_registry(source_id="akshare", enabled=False))
        session.add(_registry(source_id="openbb:yfinance", enabled=True))
        await session.commit()
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)
        grant = await authorizer.authorize_policy(
            principal=principal,
            policy=_policy(primary, fallback),
            routes=(primary, fallback),
            asset_type="stock",
            market="CN-SSE",
            purpose="display",
        )

    assert grant.authorized_route_ids == {"fallback"}
    assert grant.authorized_source_registry_ids == {"openbb:yfinance"}
    with pytest.raises(MarketDataAuthorizationError, match="SOURCE_ROUTE_AUTHORIZATION_DENIED"):
        grant.authorization_for_route("primary")


@pytest.mark.asyncio
async def test_local_read_rechecks_current_source_and_entitlement_after_collection() -> None:
    """A past collection approval cannot bypass a later source or role revocation."""
    user = await _user_with_roles(Role.USER)
    async with async_session_maker() as session:
        registry = _registry()
        session.add(registry)
        await session.commit()
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)
        allowed = await authorizer.authorize_local_source(
            principal=principal,
            source_registry_id="akshare",
            asset_type="stock",
            market="CN-SSE",
            purpose="display",
        )
        registry.enabled = False
        await session.commit()
        with pytest.raises(MarketDataAuthorizationError) as revoked:
            await authorizer.authorize_local_source(
                principal=principal,
                source_registry_id="akshare",
                asset_type="stock",
                market="CN-SSE",
                purpose="display",
            )

    assert allowed.decision == "ALLOW"
    assert revoked.value.code == "SOURCE_REGISTRY_DISABLED"


@pytest.mark.asyncio
async def test_entitlement_revision_changes_when_role_grants_change() -> None:
    """A cursor cannot retain the earlier entitlement after the role set changes."""
    user = await _user_with_roles(Role.USER)
    async with async_session_maker() as session:
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        before = await authorizer.principal_for_user(user)
        await session.execute(user_roles.insert().values(user_id=user.id, role=Role.PREMIUM.value))
        await session.commit()
        after = await authorizer.principal_for_user(user)

    assert before.entitlement_revision != after.entitlement_revision
    assert before.principal_scope == after.principal_scope
    assert after.can_read_data is True


@pytest.mark.asyncio
async def test_write_reauthorization_uses_a_current_registry_read_after_provider_io() -> None:
    """A registry revoked after preflight cannot authorize the subsequent receipt write."""
    user = await _user_with_roles(Role.USER)
    route = _route()
    async with async_session_maker() as session:
        session.add(_registry())
        await session.commit()
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)
        preflight = await authorizer.authorize_route(
            principal=principal,
            route=route,
            asset_type="stock",
            market="CN-SSE",
            purpose="display",
        )

        async with async_session_maker() as revoker:
            registry = await revoker.get(AssetDataSourceRegistry, "akshare")
            assert registry is not None
            registry.enabled = False
            registry.updated_at = NOW + timedelta(seconds=1)
            await revoker.commit()

        with pytest.raises(MarketDataAuthorizationError) as rejected:
            await authorizer.reauthorize_route_for_write(
                principal=principal,
                route=route,
                asset_type="stock",
                market="CN-SSE",
                purpose="display",
                expected_authorization=preflight,
            )

    assert rejected.value.code == "SOURCE_REGISTRY_DISABLED"


@pytest.mark.asyncio
async def test_write_reauthorization_rejects_a_changed_entitlement_revision() -> None:
    """A still-readable role change cannot silently authorise an in-flight fetch."""
    user = await _user_with_roles(Role.USER)
    route = _route()
    async with async_session_maker() as session:
        session.add(_registry())
        await session.commit()
        authorizer = MarketDataAccessAuthorizer(session, clock=lambda: NOW)
        principal = await authorizer.principal_for_user(user)
        preflight = await authorizer.authorize_route(
            principal=principal,
            route=route,
            asset_type="stock",
            market="CN-SSE",
            purpose="display",
        )

        async with async_session_maker() as role_granter:
            await role_granter.execute(
                user_roles.insert().values(user_id=user.id, role=Role.PREMIUM.value)
            )
            await role_granter.commit()

        with pytest.raises(MarketDataAuthorizationError) as rejected:
            await authorizer.reauthorize_route_for_write(
                principal=principal,
                route=route,
                asset_type="stock",
                market="CN-SSE",
                purpose="display",
                expected_authorization=preflight,
            )

    assert rejected.value.code == "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"
