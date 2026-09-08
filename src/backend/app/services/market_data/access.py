"""Current-principal and source-registry authorization for market-data reads.

The market-data query service deliberately has no knowledge of user tables or
licence registry persistence.  This module builds a compact, immutable access
context at the API boundary and evaluates the *current* source registry before
any local read, coverage calculation, or provider request is allowed.

It is intentionally separate from the asset-research source policy.  Research
permission frozen into a historical snapshot proves how a fact was collected;
it does not grant a principal a permanent right to read or redistribute that
fact later.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetDataSourceRegistry
from app.models.permission import ROLE_PERMISSIONS, Permission, Role, user_roles
from app.models.user import User
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
)

UTC = timezone.utc
_SINGLE_TENANT_SCOPE = "default"
_APPROVED_LICENSES = frozenset(
    {
        "APPROVED",
        "LICENSED",
        "MARKET_DATA_APPROVED",
        "PUBLIC",
        "RESEARCH_APPROVED",
    }
)
_PURPOSE_ALLOWED_USES: Mapping[str, frozenset[str]] = {
    "display": frozenset({"DISPLAY", "MARKET_DATA_DISPLAY", "MARKET_DATA_READ"}),
    "research": frozenset({"RESEARCH", "RESEARCH_ONLY", "DERIVED_RESEARCH"}),
    "backtest": frozenset({"BACKTEST", "BACKTEST_ONLY"}),
}
_READABLE_REDISTRIBUTION_POLICIES = frozenset({"ALLOWED", "INTERNAL_ONLY", "NO_REDISTRIBUTION"})
_PROHIBITED_RETENTION_POLICIES = frozenset({"", "DENIED", "EXPIRED", "PROHIBITED", "UNKNOWN"})


class MarketDataAuthorizationError(ValueError):
    """Stable authorization rejection at the market-data boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical_sha256(payload: object) -> str:
    """Return the stable digest used for non-secret authorization bindings."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive test datetimes and production UTC values."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalized_text(value: object) -> str:
    """Return a normalized registry token without treating arbitrary objects as text."""
    return value.strip().upper() if isinstance(value, str) else ""


@dataclass(frozen=True, slots=True)
class MarketDataPrincipal:
    """Current authenticated scope signed into query pagination state.

    The application currently has no tenant table.  ``tenant_scope`` is still
    explicit and versioned so a later tenancy implementation cannot silently
    turn a single-tenant cursor into a cross-tenant token.
    """

    principal_id: str
    principal_scope: str
    tenant_scope: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    entitlement_revision: str

    @property
    def can_read_data(self) -> bool:
        """Return whether the current entitlement includes the data-read grant."""
        return Permission.READ_DATA.value in self.permissions


@dataclass(frozen=True, slots=True)
class MarketDataSourceAuthorization:
    """Current source decision frozen into a provider receipt when collected."""

    source_registry_id: str
    registry_updated_at: str
    asset_type: str
    market: str
    purpose: str
    license_status: str
    allowed_uses: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    effective_from: str
    effective_to: str | None
    retention_policy: str
    retention_expires_at: str | None
    redistribution_policy: str
    principal_scope: str
    tenant_scope: str
    entitlement_revision: str
    decision: str
    descriptor_hash: str

    def as_provenance(self) -> dict[str, object]:
        """Return only structured, persistence-safe authorization evidence."""
        return {
            "source_registry_id": self.source_registry_id,
            "registry_updated_at": self.registry_updated_at,
            "asset_type": self.asset_type,
            "market": self.market,
            "purpose": self.purpose,
            "license_status": self.license_status,
            "allowed_uses": list(self.allowed_uses),
            "jurisdictions": list(self.jurisdictions),
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "retention_policy": self.retention_policy,
            "retention_expires_at": self.retention_expires_at,
            "redistribution_policy": self.redistribution_policy,
            "principal_scope": self.principal_scope,
            "tenant_scope": self.tenant_scope,
            "entitlement_revision": self.entitlement_revision,
            "decision": self.decision,
            "descriptor_hash": self.descriptor_hash,
        }


@dataclass(frozen=True, slots=True)
class MarketDataAccessGrant:
    """Authorized routes and the descriptor hash used by the execution/cursor."""

    principal: MarketDataPrincipal
    policy_id: str
    purpose: str
    route_authorizations: tuple[tuple[str, MarketDataSourceAuthorization], ...]
    policy_descriptor_hash: str

    @property
    def authorized_route_ids(self) -> frozenset[str]:
        """Return the exact route IDs that passed current authorization."""
        return frozenset(route_id for route_id, _ in self.route_authorizations)

    @property
    def authorized_source_registry_ids(self) -> frozenset[str]:
        """Return only current-registry sources that may satisfy a local read.

        A route authorization is deliberately more specific than a provider
        name: it records the source-registry record that was evaluated for this
        principal, purpose, asset type, and market.  The query store uses this
        set as a SQL filter before it reads observation revisions, so a fact
        collected under a now-disabled or otherwise unauthorized source cannot
        be exposed merely because it is already local.
        """
        return frozenset(
            authorization.source_registry_id
            for _route_id, authorization in self.route_authorizations
        )

    def authorization_for_route(self, route_id: str) -> MarketDataSourceAuthorization:
        """Return one route's immutable authorization evidence or fail closed."""
        for candidate_route_id, authorization in self.route_authorizations:
            if candidate_route_id == route_id:
                return authorization
        raise MarketDataAuthorizationError("SOURCE_ROUTE_AUTHORIZATION_DENIED")


@dataclass(frozen=True, slots=True)
class MarketDataQueryAccess:
    """Authenticated execution context passed across the query boundary.

    The API constructs this only after it has loaded the current user and role
    rows.  Passing the principal and its authorizer together prevents a caller
    from accidentally signing a cursor for one principal while evaluating the
    source registry through an unrelated session or authorization context.
    """

    principal: MarketDataPrincipal
    authorizer: MarketDataAccessAuthorizer

    def __post_init__(self) -> None:
        if not isinstance(self.principal, MarketDataPrincipal):
            raise TypeError("principal must be a MarketDataPrincipal")
        if not isinstance(self.authorizer, MarketDataAccessAuthorizer):
            raise TypeError("authorizer must be a MarketDataAccessAuthorizer")


class MarketDataAccessAuthorizer:
    """Evaluate current principal and source-registry permissions.

    This object does not select a provider and never grants a wildcard source.
    The caller gives it the resolved asset/market and the server-owned policy;
    every route is then linked to exactly one registry source ID through its
    expected receipt provider identifier.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
        tenant_scope: str = _SINGLE_TENANT_SCOPE,
    ) -> None:
        normalized_tenant_scope = tenant_scope.strip()
        if not normalized_tenant_scope or len(normalized_tenant_scope) > 256:
            raise ValueError("tenant_scope must be a non-empty string up to 256 characters")
        self._db = db
        self._clock = clock or _utc_now
        self._tenant_scope = normalized_tenant_scope

    async def principal_for_user(self, user: object) -> MarketDataPrincipal:
        """Build a current entitlement for an authenticated user or token payload.

        Legacy compatibility routes authenticate with the signed token payload,
        while the v2 routes already materialize a ``User`` row.  Both carry the
        same authenticated subject, and this method always re-reads the user
        and role rows from the authoritative database before returning a
        principal.
        """
        principal_id = str(getattr(user, "id", "") or getattr(user, "sub", "")).strip()
        if not principal_id:
            raise MarketDataAuthorizationError("MARKET_DATA_PRINCIPAL_INVALID")
        current_user = (
            await self._db.execute(
                select(User)
                .where(User.id == principal_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if current_user is None or not current_user.is_active:
            raise MarketDataAuthorizationError("MARKET_DATA_PRINCIPAL_REVOKED")
        return await self._principal_for_id(principal_id)

    async def revalidate_principal_for_write(
        self,
        *,
        principal: MarketDataPrincipal,
    ) -> MarketDataPrincipal:
        """Take a current authorization decision immediately before a fact write.

        Provider I/O deliberately happens outside this critical section.  Once
        a provider has returned, this method performs locking/current reads of
        the user and role rows before a receipt can be persisted.  A changed
        entitlement makes the in-flight fetch fail closed instead of allowing
        a stale request-scoped principal to authorise a new immutable fact.
        """
        if not isinstance(principal, MarketDataPrincipal):
            raise TypeError("principal must be a MarketDataPrincipal")
        return await self._revalidate_principal(principal=principal, lock_current=True)

    async def revalidate_principal(
        self,
        *,
        principal: MarketDataPrincipal,
    ) -> MarketDataPrincipal:
        """Refresh a principal after a follower ends its old read transaction."""
        if not isinstance(principal, MarketDataPrincipal):
            raise TypeError("principal must be a MarketDataPrincipal")
        return await self._revalidate_principal(principal=principal, lock_current=False)

    async def _revalidate_principal(
        self,
        *,
        principal: MarketDataPrincipal,
        lock_current: bool,
    ) -> MarketDataPrincipal:
        """Read the current account and role state, optionally under a write lock."""
        user_statement = (
            select(User)
            .where(User.id == principal.principal_id)
            .execution_options(populate_existing=True)
        )
        if lock_current:
            user_statement = user_statement.with_for_update()
        user = (await self._db.execute(user_statement)).scalar_one_or_none()
        if user is None or not user.is_active:
            raise MarketDataAuthorizationError("MARKET_DATA_PRINCIPAL_REVOKED")
        current = await self._principal_for_id(
            principal.principal_id,
            lock_current=lock_current,
        )
        self.require_read_data(principal=current)
        if (
            current.principal_scope != principal.principal_scope
            or current.tenant_scope != principal.tenant_scope
            or current.entitlement_revision != principal.entitlement_revision
        ):
            raise MarketDataAuthorizationError("MARKET_DATA_ACCESS_CHANGED_DURING_FETCH")
        return current

    async def _principal_for_id(
        self,
        principal_id: str,
        *,
        lock_current: bool = False,
    ) -> MarketDataPrincipal:
        """Read role grants, optionally as a locking current read for a write."""
        statement = select(user_roles.c.role).where(user_roles.c.user_id == principal_id)
        if lock_current:
            statement = statement.with_for_update()
        rows = await self._db.execute(statement)
        role_values = tuple(
            sorted({str(value).strip().lower() for value in rows.scalars() if value})
        )
        recognized_roles: list[Role] = []
        for role_value in role_values:
            try:
                recognized_roles.append(Role(role_value))
            except ValueError:
                # Unknown persisted role strings are never permission grants,
                # but remain part of the entitlement revision so correcting the
                # row invalidates any earlier cursor.
                continue
        permissions = tuple(
            sorted(
                {
                    permission.value
                    for role in recognized_roles
                    for permission in ROLE_PERMISSIONS[role]
                }
            )
        )
        principal_scope = f"principal-v1:{_canonical_sha256({'principal_id': principal_id})}"
        entitlement_revision = _canonical_sha256(
            {
                "version": "market-data-entitlement-v1",
                "principal_scope": principal_scope,
                "tenant_scope": self._tenant_scope,
                "roles": role_values,
                "permissions": permissions,
            }
        )
        return MarketDataPrincipal(
            principal_id=principal_id,
            principal_scope=principal_scope,
            tenant_scope=self._tenant_scope,
            roles=role_values,
            permissions=permissions,
            entitlement_revision=entitlement_revision,
        )

    @staticmethod
    def require_read_data(*, principal: MarketDataPrincipal) -> None:
        """Reject an unauthorised caller before any market-data control lookup.

        Source authorization still runs later, once an exact asset and market
        are resolved.  This early entitlement gate avoids even the visibility
        anchor or identity-control reads for users who cannot read data at all.
        """
        if not isinstance(principal, MarketDataPrincipal):
            raise TypeError("principal must be a MarketDataPrincipal")
        if not principal.can_read_data:
            raise MarketDataAuthorizationError("MARKET_DATA_READ_ENTITLEMENT_DENIED")

    async def authorize_policy(
        self,
        *,
        principal: MarketDataPrincipal,
        policy: MarketDataSourcePolicy,
        routes: Sequence[MarketDataProviderRoute],
        asset_type: str,
        market: str,
        purpose: str,
    ) -> MarketDataAccessGrant:
        """Authorize candidate routes before any local store or adapter interaction."""
        normalized_asset_type = _required_lower(asset_type, field_name="asset_type", maximum=32)
        normalized_market = _required_upper(market, field_name="market", maximum=128)
        normalized_purpose = _required_lower(purpose, field_name="purpose", maximum=32)
        if normalized_purpose not in _PURPOSE_ALLOWED_USES:
            raise MarketDataAuthorizationError("MARKET_DATA_PURPOSE_UNSUPPORTED")
        if not principal.can_read_data:
            raise MarketDataAuthorizationError("MARKET_DATA_READ_ENTITLEMENT_DENIED")
        if not policy.allows_purpose(normalized_purpose):
            raise MarketDataAuthorizationError("SOURCE_POLICY_PURPOSE_DENIED")
        if not routes:
            raise MarketDataAuthorizationError("SOURCE_POLICY_NO_ELIGIBLE_PROVIDER")

        authorizations: list[tuple[str, MarketDataSourceAuthorization]] = []
        denials: list[str] = []
        for route in routes:
            try:
                authorization = await self.authorize_route(
                    principal=principal,
                    route=route,
                    asset_type=normalized_asset_type,
                    market=normalized_market,
                    purpose=normalized_purpose,
                )
            except MarketDataAuthorizationError as exc:
                denials.append(exc.code)
                continue
            authorizations.append((route.route_id, authorization))
        if not authorizations:
            # The first route follows policy priority, making denial responses
            # deterministic without disclosing a source catalog beyond what the
            # caller already selected through a server-owned policy.
            raise MarketDataAuthorizationError(
                denials[0] if denials else "SOURCE_ROUTE_AUTHORIZATION_DENIED"
            )
        descriptor_payload = {
            "version": "market-data-policy-access-v1",
            "policy_id": policy.policy_id,
            "asset_type": normalized_asset_type,
            "market": normalized_market,
            "purpose": normalized_purpose,
            "principal_scope": principal.principal_scope,
            "tenant_scope": principal.tenant_scope,
            "entitlement_revision": principal.entitlement_revision,
            "routes": [
                {
                    "route_id": route_id,
                    "source_descriptor_hash": authorization.descriptor_hash,
                }
                for route_id, authorization in authorizations
            ],
        }
        return MarketDataAccessGrant(
            principal=principal,
            policy_id=policy.policy_id,
            purpose=normalized_purpose,
            route_authorizations=tuple(authorizations),
            policy_descriptor_hash=_canonical_sha256(descriptor_payload),
        )

    async def authorize_route(
        self,
        *,
        principal: MarketDataPrincipal,
        route: MarketDataProviderRoute,
        asset_type: str,
        market: str,
        purpose: str,
        lock_current: bool = False,
    ) -> MarketDataSourceAuthorization:
        """Authorize one exact route for local read or a new provider request."""
        if not principal.can_read_data:
            raise MarketDataAuthorizationError("MARKET_DATA_READ_ENTITLEMENT_DENIED")
        source_registry_id = _source_registry_id_for_route(route)
        registry = await self._load_registry(source_registry_id, lock_current=lock_current)
        if registry is None:
            raise MarketDataAuthorizationError("SOURCE_REGISTRY_UNREGISTERED")
        return self._authorize_registry(
            principal=principal,
            registry=registry,
            asset_type=asset_type,
            market=market,
            purpose=purpose,
            at=_trusted_now(self._clock),
        )

    async def reauthorize_route_for_write(
        self,
        *,
        principal: MarketDataPrincipal,
        route: MarketDataProviderRoute,
        asset_type: str,
        market: str,
        purpose: str,
        expected_authorization: MarketDataSourceAuthorization,
    ) -> MarketDataSourceAuthorization:
        """Lock and recheck a route after provider I/O but before persistence.

        The source registry and entitlement are linearized at this short write
        boundary.  A revocation is rejected by the normal stable code; any
        other decision change also rejects rather than storing a receipt whose
        fetch and persistence authorizations disagree.
        """
        if not isinstance(expected_authorization, MarketDataSourceAuthorization):
            raise TypeError("expected_authorization must be a MarketDataSourceAuthorization")
        current_principal = await self.revalidate_principal_for_write(principal=principal)
        current = await self.authorize_route(
            principal=current_principal,
            route=route,
            asset_type=asset_type,
            market=market,
            purpose=purpose,
            lock_current=True,
        )
        if current.descriptor_hash != expected_authorization.descriptor_hash:
            raise MarketDataAuthorizationError("MARKET_DATA_ACCESS_CHANGED_DURING_FETCH")
        return current

    async def authorize_local_source(
        self,
        *,
        principal: MarketDataPrincipal,
        source_registry_id: str,
        asset_type: str,
        market: str,
        purpose: str,
    ) -> MarketDataSourceAuthorization:
        """Recheck an observed source before exposing a local sealed fact."""
        if not principal.can_read_data:
            raise MarketDataAuthorizationError("MARKET_DATA_READ_ENTITLEMENT_DENIED")
        normalized_source_id = _required_text(
            source_registry_id,
            field_name="source_registry_id",
            maximum=255,
        )
        registry = await self._load_registry(normalized_source_id)
        if registry is None:
            raise MarketDataAuthorizationError("SOURCE_REGISTRY_UNREGISTERED")
        return self._authorize_registry(
            principal=principal,
            registry=registry,
            asset_type=_required_lower(asset_type, field_name="asset_type", maximum=32),
            market=_required_upper(market, field_name="market", maximum=128),
            purpose=_required_lower(purpose, field_name="purpose", maximum=32),
            at=_trusted_now(self._clock),
        )

    async def _load_registry(
        self,
        source_registry_id: str,
        *,
        lock_current: bool = False,
    ) -> AssetDataSourceRegistry | None:
        """Load a registry row without reusing a stale session identity-map value."""
        statement = (
            select(AssetDataSourceRegistry)
            .where(AssetDataSourceRegistry.source_id == source_registry_id)
            .execution_options(populate_existing=True)
        )
        if lock_current:
            # InnoDB treats a locking read as a current read under REPEATABLE
            # READ.  The lock is acquired only after network I/O and remains
            # until the request write transaction commits or rolls back.
            statement = statement.with_for_update()
        return (await self._db.execute(statement)).scalar_one_or_none()

    @staticmethod
    def _authorize_registry(
        *,
        principal: MarketDataPrincipal,
        registry: AssetDataSourceRegistry,
        asset_type: str,
        market: str,
        purpose: str,
        at: datetime,
    ) -> MarketDataSourceAuthorization:
        if purpose not in _PURPOSE_ALLOWED_USES:
            raise MarketDataAuthorizationError("MARKET_DATA_PURPOSE_UNSUPPORTED")
        effective_from = _as_utc(registry.effective_from)
        effective_to = _as_utc(registry.effective_to) if registry.effective_to is not None else None
        retention_expires_at = (
            _as_utc(registry.retention_expires_at)
            if registry.retention_expires_at is not None
            else None
        )
        allowed_uses = tuple(
            sorted({_normalized_text(value) for value in (registry.allowed_uses or [])} - {""})
        )
        jurisdictions = tuple(
            sorted({_normalized_text(value) for value in (registry.jurisdictions or [])} - {""})
        )
        license_status = _normalized_text(registry.license_status)
        retention_policy = _normalized_text(registry.retention_policy)
        redistribution_policy = _normalized_text(registry.redistribution_policy)

        if not registry.enabled:
            raise MarketDataAuthorizationError("SOURCE_REGISTRY_DISABLED")
        if asset_type.upper() not in {
            _normalized_text(value) for value in (registry.asset_types or [])
        }:
            raise MarketDataAuthorizationError("SOURCE_REGISTRY_ASSET_TYPE_DENIED")
        if license_status not in _APPROVED_LICENSES:
            raise MarketDataAuthorizationError("SOURCE_LICENSE_DENIED")
        if not (_PURPOSE_ALLOWED_USES[purpose] & set(allowed_uses)):
            raise MarketDataAuthorizationError("SOURCE_USE_DENIED")
        if effective_from > at or (effective_to is not None and effective_to < at):
            raise MarketDataAuthorizationError("SOURCE_EFFECTIVE_WINDOW_DENIED")
        if not _jurisdiction_allows(jurisdictions, market):
            raise MarketDataAuthorizationError("SOURCE_JURISDICTION_DENIED")
        if retention_policy in _PROHIBITED_RETENTION_POLICIES:
            raise MarketDataAuthorizationError("SOURCE_RETENTION_DENIED")
        if retention_expires_at is not None and retention_expires_at < at:
            raise MarketDataAuthorizationError("SOURCE_RETENTION_DENIED")
        if redistribution_policy not in _READABLE_REDISTRIBUTION_POLICIES:
            raise MarketDataAuthorizationError("SOURCE_REDISTRIBUTION_DENIED")

        registry_updated_at = _as_utc(registry.updated_at)
        descriptor_payload = {
            "version": "market-data-source-authorization-v1",
            "source_registry_id": registry.source_id,
            "registry_updated_at": registry_updated_at.isoformat(),
            "asset_type": asset_type,
            "market": market,
            "purpose": purpose,
            "license_status": license_status,
            "allowed_uses": list(allowed_uses),
            "jurisdictions": list(jurisdictions),
            "effective_from": effective_from.isoformat(),
            "effective_to": effective_to.isoformat() if effective_to is not None else None,
            "retention_policy": retention_policy,
            "retention_expires_at": (
                retention_expires_at.isoformat() if retention_expires_at is not None else None
            ),
            "redistribution_policy": redistribution_policy,
            "principal_scope": principal.principal_scope,
            "tenant_scope": principal.tenant_scope,
            "entitlement_revision": principal.entitlement_revision,
            "decision": "ALLOW",
        }
        return MarketDataSourceAuthorization(
            source_registry_id=registry.source_id,
            registry_updated_at=registry_updated_at.isoformat(),
            asset_type=asset_type,
            market=market,
            purpose=purpose,
            license_status=license_status,
            allowed_uses=allowed_uses,
            jurisdictions=jurisdictions,
            effective_from=effective_from.isoformat(),
            effective_to=effective_to.isoformat() if effective_to is not None else None,
            retention_policy=retention_policy,
            retention_expires_at=(
                retention_expires_at.isoformat() if retention_expires_at is not None else None
            ),
            redistribution_policy=redistribution_policy,
            principal_scope=principal.principal_scope,
            tenant_scope=principal.tenant_scope,
            entitlement_revision=principal.entitlement_revision,
            decision="ALLOW",
            descriptor_hash=_canonical_sha256(descriptor_payload),
        )


def _source_registry_id_for_route(route: MarketDataProviderRoute) -> str:
    """Map a route to its sole source registry without guessing a provider."""
    source_ids = tuple(sorted(route.expected_result_provider_ids))
    if len(source_ids) != 1:
        raise MarketDataAuthorizationError("SOURCE_REGISTRY_ROUTE_AMBIGUOUS")
    return _required_text(source_ids[0], field_name="source_registry_id", maximum=255)


def _jurisdiction_allows(jurisdictions: tuple[str, ...], market: str) -> bool:
    """Accept a global, exact-venue, or country-prefix registry declaration."""
    if "GLOBAL" in jurisdictions:
        return True
    market_prefix = market.split("-", 1)[0]
    return market in jurisdictions or market_prefix in jurisdictions


def _required_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise MarketDataAuthorizationError("MARKET_DATA_AUTHORIZATION_INPUT_INVALID")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise MarketDataAuthorizationError("MARKET_DATA_AUTHORIZATION_INPUT_INVALID")
    return normalized


def _required_lower(value: object, *, field_name: str, maximum: int) -> str:
    return _required_text(value, field_name=field_name, maximum=maximum).lower()


def _required_upper(value: object, *, field_name: str, maximum: int) -> str:
    return _required_text(value, field_name=field_name, maximum=maximum).upper()


def _trusted_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataAuthorizationError("MARKET_DATA_AUTHORIZATION_CLOCK_INVALID")
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
