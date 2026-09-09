"""Local-first orchestration for the normalized Iteration 197 market-data path.

This service owns the order of operations: resolve exact server-owned facts,
read local evidence, plan coverage against a frozen calendar, optionally fill
bounded gaps through an approved source policy, persist every receipt, and
then read the result back from the local store.  Provider output is never used
as the response directly.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.access import (
    MarketDataQueryAccess,
    MarketDataSourceAuthorization,
)
from app.services.market_data.coverage import (
    CalendarSnapshot,
    CalendarStatus,
    CoveragePlan,
    CoveragePlanner,
    CoverageStatus,
    ObservationQuality,
    SnapshotCoveragePlanner,
    TimeWindow,
)
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseError,
    MarketDataFetchLeaseHandle,
    market_data_fetch_lease_key,
)
from app.services.market_data.field_quality import is_usable_field_value
from app.services.market_data.identity import MarketDataIdentityResolutionError
from app.services.market_data.providers import MarketDataProviderRequest, ProviderFetchResult
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import (
    MarketDataQueryResolutionError,
    MarketDataQueryResolver,
    ResolvedMarketDataQueryContext,
)
from app.services.market_data.snapshot_freshness import (
    DEFAULT_SNAPSHOT_FRESHNESS_POLICY_REGISTRY,
    SnapshotFreshnessPolicyError,
    SnapshotFreshnessPolicyRegistry,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyError,
    MarketDataSourcePolicyRegistry,
)
from app.services.market_data.store import (
    LocalObservationRevision,
    MarketDataStore,
    MarketDataStoreError,
    PersistedProviderFetch,
)

UTC = timezone.utc
MAX_PROVIDER_FETCH_WINDOWS = 32
_CURSOR_HMAC_DIGEST_BYTES = hashlib.sha256().digest_size
_MAX_CURSOR_TOKEN_LENGTH = 2048
# A request accepts cursor tokens up to 2048 characters.  Accounting for the
# fixed HMAC segment leaves 1503 URL-safe payload bytes; retain a small margin
# so a token emitted here is always acceptable to the request schema.
_MAX_CURSOR_PAYLOAD_BYTES = 1500
_CURSOR_VERSION = 3
_DEFAULT_CURSOR_TTL = timedelta(minutes=15)
_UNBOUND_CURSOR_PRINCIPAL_SCOPE = "unbound"
_UNBOUND_CURSOR_TENANT_SCOPE = "unbound"
_UNBOUND_CURSOR_ENTITLEMENT_REVISION = "unbound-v1"
_BASE64URL_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


class MarketDataQueryServiceError(ValueError):
    """Stable error code for a local-first orchestration boundary failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _Resolver(Protocol):
    async def resolve(
        self,
        request: MarketDataQueryRequest,
        *,
        identity_knowledge_cutoff: datetime | None = None,
        identity_visibility_anchor: MarketDataVisibilityAnchor | None = None,
    ) -> ResolvedMarketDataQueryContext:
        """Resolve public input to server-owned catalog and master-data facts."""


class _Store(Protocol):
    async def resolve_visibility_anchor(
        self,
        *,
        knowledge_cutoff: datetime,
    ) -> MarketDataVisibilityAnchor:
        """Freeze the complete receipt anchor before any context lookup."""

    async def read_observation_revisions(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        include_unusable_for_coverage: bool = False,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> tuple[LocalObservationRevision, ...]:
        """Read response-safe rows or diagnostics-only coverage rows at one PIT cutoff."""

    async def read_calendar_for_context(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> CalendarSnapshot:
        """Read frozen calendar evidence for a resolved query."""

    async def ensure_provider_active(self, provider_id: str) -> None:
        """Verify a route's expected receipt provider before external work starts."""

    async def persist_provider_result(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        *,
        received_at: datetime,
        source_authorization: MarketDataSourceAuthorization | None = None,
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
    ) -> PersistedProviderFetch:
        """Append one validated source receipt and observation revisions."""


class _FetchLeases(Protocol):
    """Durable lease operations used by the real local-first request path."""

    async def acquire(self, lease_key_sha256: str) -> MarketDataFetchLeaseHandle | None:
        """Acquire a coverage-gap owner or report a current remote owner."""

    async def release(self, handle: MarketDataFetchLeaseHandle) -> bool:
        """Release an exact owner/fence pair without resetting its generation."""


@dataclass(frozen=True, slots=True)
class MarketDataQueryWarning:
    """A non-sensitive, machine-readable provider or policy diagnostic."""

    code: str
    route_id: str | None = None
    provider_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.code, field_name="warning code", maximum=128)
        if self.route_id is not None:
            _require_text(self.route_id, field_name="warning route_id", maximum=128)
        if self.provider_id is not None:
            _require_text(self.provider_id, field_name="warning provider_id", maximum=255)


@dataclass(frozen=True, slots=True)
class MarketDataQueryFetch:
    """The durable receipt identifiers created by one successful route call."""

    route_id: str
    provider_id: str
    source_snapshot_id: str
    observation_revision_ids: tuple[str, ...]
    passing_observation_count: int
    failed_observation_count: int


@dataclass(frozen=True, slots=True)
class MarketDataQueryExecution:
    """A page of locally read observations and exact coverage evidence."""

    context: ResolvedMarketDataQueryContext
    knowledge_cutoff: datetime
    identity_knowledge_cutoff: datetime
    visibility_anchor: MarketDataVisibilityAnchor
    identity_visibility_anchor: MarketDataVisibilityAnchor
    coverage: CoveragePlan
    observations: tuple[LocalObservationRevision, ...]
    next_cursor: str | None
    fetches: tuple[MarketDataQueryFetch, ...]
    warnings: tuple[MarketDataQueryWarning, ...]
    refresh_status: str | None = None
    historical_status: str | None = None


@dataclass(frozen=True, slots=True)
class MarketDataCursorBinding:
    """Caller-provided auth/policy dimensions signed into a pagination token.

    This module deliberately does not decide authorization.  The API layer can
    provide the currently authenticated principal and entitlement revision, and
    a future immutable policy registry can provide its descriptor hash.  Until
    that integration is enabled, the explicit unbound sentinel preserves the
    disabled v2 compatibility path without silently omitting token fields.
    """

    principal_scope: str = _UNBOUND_CURSOR_PRINCIPAL_SCOPE
    tenant_scope: str = _UNBOUND_CURSOR_TENANT_SCOPE
    entitlement_revision: str = _UNBOUND_CURSOR_ENTITLEMENT_REVISION
    policy_descriptor_hash: str | None = None
    access_grant_descriptor_hash: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.principal_scope, field_name="cursor principal scope", maximum=256)
        _require_text(self.tenant_scope, field_name="cursor tenant scope", maximum=256)
        _require_text(
            self.entitlement_revision,
            field_name="cursor entitlement revision",
            maximum=128,
        )
        if self.policy_descriptor_hash is not None:
            _require_sha256(
                self.policy_descriptor_hash,
                field_name="cursor policy descriptor hash",
            )
        if self.access_grant_descriptor_hash is not None:
            _require_sha256(
                self.access_grant_descriptor_hash,
                field_name="cursor access grant descriptor hash",
            )

    def with_policy_descriptor_hash(self, policy_descriptor_hash: str) -> MarketDataCursorBinding:
        """Bind the caller scope to the resolved immutable policy descriptor."""
        _require_sha256(policy_descriptor_hash, field_name="cursor policy descriptor hash")
        if self.policy_descriptor_hash is not None and self.policy_descriptor_hash != policy_descriptor_hash:
            raise MarketDataQueryServiceError("CURSOR_POLICY_MISMATCH")
        return replace(self, policy_descriptor_hash=policy_descriptor_hash)

    def with_access_grant_descriptor_hash(
        self,
        access_grant_descriptor_hash: str,
    ) -> MarketDataCursorBinding:
        """Bind a cursor to the current principal's source-registry decision.

        The server-owned source-policy hash and the access-grant hash have
        distinct meanings.  The former is available before identity resolution;
        the latter is recomputed only after the exact asset/market and current
        source registry have been evaluated.
        """
        _require_sha256(
            access_grant_descriptor_hash,
            field_name="cursor access grant descriptor hash",
        )
        if (
            self.access_grant_descriptor_hash is not None
            and self.access_grant_descriptor_hash != access_grant_descriptor_hash
        ):
            raise MarketDataQueryServiceError("CURSOR_ACCESS_GRANT_MISMATCH")
        return replace(self, access_grant_descriptor_hash=access_grant_descriptor_hash)


@dataclass(frozen=True, slots=True)
class _CursorBindingDigest:
    """Fixed-size access dimensions stored in an issued cursor payload.

    Raw principal and tenant values can be long or contain Unicode.  Keeping
    their domain-separated SHA-256 digests in a token preserves exact replay
    binding without exposing those identifiers or making a valid authenticated
    scope exceed the public cursor length limit.
    """

    principal_scope_sha256: str
    tenant_scope_sha256: str
    entitlement_revision_sha256: str
    policy_descriptor_hash: str
    access_grant_descriptor_hash: str | None

    def __post_init__(self) -> None:
        _require_sha256(
            self.principal_scope_sha256,
            field_name="cursor principal scope hash",
        )
        _require_sha256(
            self.tenant_scope_sha256,
            field_name="cursor tenant scope hash",
        )
        _require_sha256(
            self.entitlement_revision_sha256,
            field_name="cursor entitlement revision hash",
        )
        _require_sha256(
            self.policy_descriptor_hash,
            field_name="cursor policy descriptor hash",
        )
        if self.access_grant_descriptor_hash is not None:
            _require_sha256(
                self.access_grant_descriptor_hash,
                field_name="cursor access grant descriptor hash",
            )


@dataclass(frozen=True, slots=True)
class _LocalState:
    """Response-safe rows, coverage diagnostics, and frozen local evidence."""

    observations: tuple[LocalObservationRevision, ...]
    coverage_observations: tuple[LocalObservationRevision, ...]
    calendar: CalendarSnapshot
    coverage: CoveragePlan
    snapshot_max_age: timedelta | None = None


@dataclass(frozen=True, slots=True)
class _Cursor:
    """An authenticated-by-content pagination anchor and frozen local cutoff."""

    query_fingerprint: str
    key: tuple[str, str]
    visibility_anchor: MarketDataVisibilityAnchor
    identity_visibility_anchor: MarketDataVisibilityAnchor
    binding: _CursorBindingDigest
    issued_at: datetime
    expires_at: datetime


class MarketDataQueryService:
    """Execute exact local-first queries without exposing provider output directly."""

    def __init__(
        self,
        *,
        resolver: _Resolver | MarketDataQueryResolver,
        store: _Store | MarketDataStore,
        source_policies: MarketDataSourcePolicyRegistry,
        coverage_planner: CoveragePlanner | None = None,
        snapshot_freshness_policies: SnapshotFreshnessPolicyRegistry | None = None,
        allow_online_fetch: bool = True,
        clock: Callable[[], datetime] | None = None,
        cursor_signing_key: str | bytes | None = None,
        cursor_ttl: timedelta = _DEFAULT_CURSOR_TTL,
        fetch_leases: _FetchLeases | None = None,
    ) -> None:
        if not hasattr(resolver, "resolve"):
            raise TypeError("resolver must implement resolve")
        if not all(
            hasattr(store, method)
            for method in (
                "resolve_visibility_anchor",
                "read_observation_revisions",
                "read_calendar_for_context",
                "ensure_provider_active",
                "persist_provider_result",
            )
        ):
            raise TypeError("store does not implement the required local-first methods")
        if not isinstance(source_policies, MarketDataSourcePolicyRegistry):
            raise TypeError("source_policies must be MarketDataSourcePolicyRegistry")
        if coverage_planner is not None and not isinstance(coverage_planner, CoveragePlanner):
            raise TypeError("coverage_planner must be CoveragePlanner")
        if snapshot_freshness_policies is not None and not isinstance(
            snapshot_freshness_policies,
            SnapshotFreshnessPolicyRegistry,
        ):
            raise TypeError("snapshot_freshness_policies must be SnapshotFreshnessPolicyRegistry")
        if not isinstance(allow_online_fetch, bool):
            raise TypeError("allow_online_fetch must be a bool")
        if fetch_leases is not None and not all(
            hasattr(fetch_leases, method) for method in ("acquire", "release")
        ):
            raise TypeError("fetch_leases must implement acquire and release")
        if (
            not isinstance(cursor_ttl, timedelta)
            or cursor_ttl <= timedelta(0)
            or cursor_ttl > timedelta(days=1)
        ):
            raise ValueError("cursor_ttl must be greater than zero and no more than one day")
        self._resolver = resolver
        self._store = store
        self._source_policies = source_policies
        self._coverage_planner = coverage_planner or CoveragePlanner()
        self._snapshot_coverage_planner = SnapshotCoveragePlanner()
        self._snapshot_freshness_policies = (
            snapshot_freshness_policies or DEFAULT_SNAPSHOT_FRESHNESS_POLICY_REGISTRY
        )
        self._allow_online_fetch = allow_online_fetch
        self._clock = clock or _utc_now
        self._cursor_ttl = cursor_ttl
        self._cursor_signing_key_override = (
            _coerce_cursor_signing_key(cursor_signing_key)
            if cursor_signing_key is not None
            else None
        )
        # Production API composition passes a real ``MarketDataStore``.  The
        # database-backed manager is therefore enabled without relying on a
        # process-local route singleton; pure in-memory contract tests retain
        # an explicit ``None`` unless they inject a lease fake.
        self._fetch_leases: _FetchLeases | None = (
            fetch_leases
            if fetch_leases is not None
            else store.fetch_lease_manager()
            if isinstance(store, MarketDataStore)
            else None
        )

    def _cursor_signing_key(self) -> bytes:
        """Resolve the configured HMAC key only when pagination needs it.

        Deferring the lookup preserves the disabled-by-default endpoint: FastAPI
        resolves its service dependency before the endpoint checks the v2 flag.
        Once v2 is enabled, ``Settings`` requires a nonempty configured key, so
        emitted pagination tokens never depend on a source-code default.
        """
        if self._cursor_signing_key_override is not None:
            return self._cursor_signing_key_override
        from app.config import get_settings

        return _coerce_cursor_signing_key(get_settings().MARKET_DATA_CURSOR_SIGNING_KEY)

    def _snapshot_max_age_for(
        self,
        context: ResolvedMarketDataQueryContext,
    ) -> timedelta | None:
        """Resolve the reviewed SLA once for a quote product execution."""
        if not _uses_snapshot_freshness(context):
            return None
        return self._snapshot_freshness_policies.resolve(context).max_age

    async def execute(
        self,
        request: MarketDataQueryRequest,
        *,
        cursor_binding: MarketDataCursorBinding | None = None,
        access: MarketDataQueryAccess | None = None,
    ) -> MarketDataQueryExecution:
        """Resolve, serve locally, and conditionally persist bounded provider fills.

        A cursor is parsed before any local or external work, then fixes both
        master-data visibility and local observation visibility to its original
        receipt boundary.  A failed, malformed, mismatched, or unauthorized
        provider receipt becomes a stable warning and is never returned as data.
        """
        if not isinstance(request, MarketDataQueryRequest):
            raise TypeError("request must be a MarketDataQueryRequest")
        if cursor_binding is not None and not isinstance(cursor_binding, MarketDataCursorBinding):
            raise TypeError("cursor_binding must be a MarketDataCursorBinding")
        if access is not None and not isinstance(access, MarketDataQueryAccess):
            raise TypeError("access must be a MarketDataQueryAccess")
        if access is not None:
            access.authorizer.require_read_data(principal=access.principal)

        # A strict refresh is categorically an interactive attempt to rewrite
        # a frozen historical view.  Reject it before resolving a policy,
        # cursor, identity, local evidence, or provider route.
        if request.consistency == "strict" and request.mode == "refresh":
            raise MarketDataQueryServiceError("STRICT_FETCH_FORBIDDEN")
        # Online collection is an authenticated write path.  Direct callers
        # may still perform explicitly local-only or strict historical reads,
        # but cannot use this orchestration service as an unaudited importer.
        if (
            access is None
            and request.mode != "local_only"
            and request.consistency != "strict"
        ):
            raise MarketDataQueryServiceError("MARKET_DATA_ACCESS_REQUIRED")

        try:
            policy = self._source_policies.resolve(request.source_policy_id)
        except MarketDataSourcePolicyError:
            raise
        if not policy.allows_purpose(request.purpose):
            raise MarketDataSourcePolicyError("SOURCE_POLICY_PURPOSE_DENIED")
        binding = _binding_for_access(cursor_binding=cursor_binding, access=access)
        binding = binding.with_policy_descriptor_hash(_policy_descriptor_hash(policy))

        request_started_at = _trusted_receipt_time(self._clock)

        cursor = (
            _decode_cursor(
                request.cursor,
                signing_key=self._cursor_signing_key(),
                now=request_started_at,
                expected_binding=binding,
                query_fingerprint=request.query_fingerprint,
            )
            if request.cursor is not None
            else None
        )
        # Freeze identity selection before any resolver/database work.  The
        # identity cutoff stays distinct from the observation cutoff because
        # a current local-first request can write observations after its
        # identity was resolved; a continuation must replay both boundaries.
        knowledge_cutoff = _resolve_knowledge_cutoff(request, request_started_at, cursor)
        visibility_anchor = (
            cursor.visibility_anchor
            if cursor is not None
            else await self._store.resolve_visibility_anchor(knowledge_cutoff=knowledge_cutoff)
        )
        identity_visibility_anchor = (
            cursor.identity_visibility_anchor if cursor is not None else visibility_anchor
        )
        identity_cutoff = _identity_knowledge_cutoff_for(
            knowledge_cutoff,
            identity_visibility_anchor,
        )
        try:
            context = await self._resolver.resolve(
                request,
                identity_knowledge_cutoff=identity_cutoff,
                identity_visibility_anchor=identity_visibility_anchor,
            )
        except (MarketDataIdentityResolutionError, MarketDataQueryResolutionError):
            raise
        except ValueError as exc:
            raise MarketDataQueryServiceError("QUERY_RESOLUTION_FAILED") from exc

        if not isinstance(context, ResolvedMarketDataQueryContext):
            raise MarketDataQueryServiceError("QUERY_CONTEXT_INVALID")

        candidate_policy_routes = policy.routes_for(context)
        policy_routes = candidate_policy_routes
        allowed_source_registry_ids: frozenset[str] | None = None
        source_authorizations: dict[str, MarketDataSourceAuthorization] = {}
        if access is not None:
            venue = context.identity.venue
            if venue is None:
                raise MarketDataQueryServiceError("IDENTITY_MARKET_UNSUPPORTED")
            grant = await access.authorizer.authorize_policy(
                principal=access.principal,
                policy=policy,
                routes=policy_routes,
                asset_type=context.identity.asset_type,
                market=venue,
                purpose=context.query.purpose,
            )
            binding = binding.with_access_grant_descriptor_hash(grant.policy_descriptor_hash)
            if cursor is not None:
                _assert_cursor_access_grant_matches(cursor.binding, binding)
            policy_routes = tuple(
                route for route in policy_routes if route.route_id in grant.authorized_route_ids
            )
            allowed_source_registry_ids = grant.authorized_source_registry_ids
            source_authorizations = dict(grant.route_authorizations)

        try:
            snapshot_max_age = self._snapshot_max_age_for(context)
        except SnapshotFreshnessPolicyError as exc:
            raise MarketDataQueryServiceError(exc.code) from exc

        state = await self._read_local_state(
            context,
            knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            snapshot_max_age=snapshot_max_age,
            allowed_source_registry_ids=allowed_source_registry_ids,
        )
        warnings: list[MarketDataQueryWarning] = []
        fetches: list[MarketDataQueryFetch] = []

        # Pagination always replays the first page's local snapshot.  A current
        # provider call would create facts after that snapshot and cannot appear
        # on this page, so it is deliberately excluded before route selection.
        if cursor is not None:
            if request.mode == "local_first":
                warnings.append(MarketDataQueryWarning(code="CURSOR_FROZEN_LOCAL_ONLY"))
            return self._execution(
                context=context,
                cursor_query_fingerprint=request.query_fingerprint,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                visibility_anchor=visibility_anchor,
                identity_visibility_anchor=identity_visibility_anchor,
                cursor_binding=binding,
                cursor_issued_at=request_started_at,
                state=state,
                cursor=cursor,
                fetches=fetches,
                warnings=warnings,
                historical_status=_historical_status_for(
                    state,
                    strict=request.consistency == "strict",
                ),
            )

        if request.mode == "local_only":
            return self._execution(
                context=context,
                cursor_query_fingerprint=request.query_fingerprint,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                visibility_anchor=visibility_anchor,
                identity_visibility_anchor=identity_visibility_anchor,
                cursor_binding=binding,
                cursor_issued_at=request_started_at,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
                historical_status=_historical_status_for(
                    state,
                    strict=request.consistency == "strict",
                ),
            )

        # Strict local-first queries are a read of their signed initial
        # visibility anchor. A missing calendar remains a typed calendar state;
        # every other incomplete result has one stable historical status.
        if request.consistency == "strict":
            return self._execution(
                context=context,
                cursor_query_fingerprint=request.query_fingerprint,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                visibility_anchor=visibility_anchor,
                identity_visibility_anchor=identity_visibility_anchor,
                cursor_binding=binding,
                cursor_issued_at=request_started_at,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
                historical_status=_historical_status_for(state, strict=True),
            )

        if not self._allow_online_fetch:
            warnings.append(MarketDataQueryWarning(code="ONLINE_FETCH_DISABLED"))
            return self._execution(
                context=context,
                cursor_query_fingerprint=request.query_fingerprint,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                visibility_anchor=visibility_anchor,
                identity_visibility_anchor=identity_visibility_anchor,
                cursor_binding=binding,
                cursor_issued_at=request_started_at,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
                refresh_status=_refresh_status_for(
                    request.mode,
                    state,
                    fresh_revision_ids=frozenset(),
                    context=context,
                    planner=self._coverage_planner,
                    knowledge_cutoff=knowledge_cutoff,
                ),
            )

        # A current quote is evidence about collection time, never a way to
        # rewrite an older display window. Strict/PIT reads returned above are
        # already local-only. For a non-strict request whose end is older than
        # the reviewed quote freshness budget, retain the exact local miss and
        # require an explicitly imported historical fact instead of fetching a
        # present-day snapshot and assigning it a past event time.
        if _uses_snapshot_freshness(context):
            if context.query.end <= knowledge_cutoff - _require_snapshot_max_age(state):
                warnings.append(MarketDataQueryWarning(code="SNAPSHOT_HISTORICAL_FETCH_FORBIDDEN"))
                return self._execution(
                    context=context,
                    cursor_query_fingerprint=request.query_fingerprint,
                    knowledge_cutoff=knowledge_cutoff,
                    identity_knowledge_cutoff=identity_cutoff,
                    visibility_anchor=visibility_anchor,
                    identity_visibility_anchor=identity_visibility_anchor,
                    cursor_binding=binding,
                    cursor_issued_at=request_started_at,
                    state=state,
                    cursor=None,
                    fetches=fetches,
                    warnings=warnings,
                    refresh_status=_refresh_status_for(
                        request.mode,
                        state,
                        fresh_revision_ids=frozenset(),
                        context=context,
                        planner=self._coverage_planner,
                        knowledge_cutoff=knowledge_cutoff,
                    ),
                )

        fetch_windows, window_warning = _fetch_windows_for(
            context=context,
            coverage=state.coverage,
            mode=request.mode,
        )
        if window_warning is not None:
            warnings.append(window_warning)
        if not fetch_windows:
            return self._execution(
                context=context,
                cursor_query_fingerprint=request.query_fingerprint,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                visibility_anchor=visibility_anchor,
                identity_visibility_anchor=identity_visibility_anchor,
                cursor_binding=binding,
                cursor_issued_at=request_started_at,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
                refresh_status=_refresh_status_for(
                    request.mode,
                    state,
                    fresh_revision_ids=frozenset(),
                    context=context,
                    planner=self._coverage_planner,
                    knowledge_cutoff=knowledge_cutoff,
                ),
            )

        if not policy_routes:
            warnings.append(MarketDataQueryWarning(code="SOURCE_POLICY_NO_ELIGIBLE_PROVIDER"))
            return self._execution(
                context=context,
                cursor_query_fingerprint=request.query_fingerprint,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                visibility_anchor=visibility_anchor,
                identity_visibility_anchor=identity_visibility_anchor,
                cursor_binding=binding,
                cursor_issued_at=request_started_at,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
                refresh_status=_refresh_status_for(
                    request.mode,
                    state,
                    fresh_revision_ids=frozenset(),
                    context=context,
                    planner=self._coverage_planner,
                    knowledge_cutoff=knowledge_cutoff,
                ),
            )

        routes = await self._active_routes(policy_routes, warnings)
        fresh_revision_ids: set[str] = set()
        for window in fetch_windows:
            fetch_context = _with_fetch_window(context, window)
            window_fresh_revision_ids: set[str] = set()
            policy_descriptor_hash = binding.policy_descriptor_hash
            if policy_descriptor_hash is None:
                raise MarketDataQueryServiceError("PROVIDER_POLICY_DESCRIPTOR_UNBOUND")
            access_grant_descriptor_hash = binding.access_grant_descriptor_hash
            if access_grant_descriptor_hash is None:
                raise MarketDataQueryServiceError("PROVIDER_ACCESS_GRANT_UNBOUND")

            fetch_lease: MarketDataFetchLeaseHandle | None = None
            if self._fetch_leases is not None:
                lease_acquire_failed = False
                lease_key = market_data_fetch_lease_key(
                    fetch_context,
                    coverage_gap=window,
                    mode=request.mode,
                    policy_descriptor_hash=policy_descriptor_hash,
                    access_grant_descriptor_hash=access_grant_descriptor_hash,
                )
                try:
                    fetch_lease = await self._fetch_leases.acquire(lease_key)
                except MarketDataFetchLeaseError as exc:
                    warnings.append(MarketDataQueryWarning(code=exc.code))
                    lease_acquire_failed = True
                    fetch_lease = None
                if fetch_lease is None:
                    # The acquire loser has already rolled back its read-only
                    # lease attempt. Re-read the shared local facts before
                    # returning; it never invokes a primary or fallback route
                    # while a different worker owns this exact coverage gap.
                    if not lease_acquire_failed:
                        warnings.append(MarketDataQueryWarning(code="FETCH_LEASE_HELD"))
                    (
                        policy_routes,
                        allowed_source_registry_ids,
                        source_authorizations,
                    ) = await self._refresh_lease_read_authorization(
                        access=access,
                        policy=policy,
                        candidate_policy_routes=candidate_policy_routes,
                        context=context,
                        expected_access_grant_descriptor_hash=access_grant_descriptor_hash,
                    )
                    routes = await self._active_routes(policy_routes, warnings)
                    knowledge_cutoff = max(knowledge_cutoff, _trusted_receipt_time(self._clock))
                    visibility_anchor = await self._store.resolve_visibility_anchor(
                        knowledge_cutoff=knowledge_cutoff
                    )
                    state = await self._read_local_state(
                        context,
                        knowledge_cutoff,
                        visibility_anchor=visibility_anchor,
                        snapshot_max_age=snapshot_max_age,
                        allowed_source_registry_ids=allowed_source_registry_ids,
                    )
                    continue

            try:
                # A prior owner can publish and release after this request's
                # first local read but before this worker wins the next fence.
                # Re-read after acquisition so local-first never fetches that
                # now-complete gap from the network a second time.
                if request.mode == "local_first" and fetch_lease is not None:
                    (
                        policy_routes,
                        allowed_source_registry_ids,
                        source_authorizations,
                    ) = await self._refresh_lease_read_authorization(
                        access=access,
                        policy=policy,
                        candidate_policy_routes=candidate_policy_routes,
                        context=fetch_context,
                        expected_access_grant_descriptor_hash=access_grant_descriptor_hash,
                    )
                    routes = await self._active_routes(policy_routes, warnings)
                    knowledge_cutoff = max(knowledge_cutoff, _trusted_receipt_time(self._clock))
                    visibility_anchor = await self._store.resolve_visibility_anchor(
                        knowledge_cutoff=knowledge_cutoff
                    )
                    post_acquire_state = await self._read_local_state(
                        fetch_context,
                        knowledge_cutoff,
                        visibility_anchor=visibility_anchor,
                        snapshot_max_age=snapshot_max_age,
                        allowed_source_registry_ids=allowed_source_registry_ids,
                    )
                    if self._route_satisfied_window(
                        mode=request.mode,
                        state=post_acquire_state,
                        context=fetch_context,
                        fresh_revision_ids=frozenset(),
                        passing_observation_count=0,
                        knowledge_cutoff=knowledge_cutoff,
                    ):
                        continue

                for route in routes:
                    source_authorization = source_authorizations.get(route.route_id)
                    if access is not None and source_authorization is None:
                        raise MarketDataQueryServiceError("SOURCE_ROUTE_AUTHORIZATION_DENIED")
                    provider_request = _provider_request_for(
                        fetch_context,
                        route,
                        policy_descriptor_hash=policy_descriptor_hash,
                        access_grant_descriptor_hash=access_grant_descriptor_hash,
                    )
                    # Every route, including a fallback after a failed receipt
                    # or an unsatisfied local re-read, enters its adapter with
                    # no request-session database transaction or registry lock.
                    await self._close_transaction_before_provider_io()
                    result = await self._fetch_route(route, provider_request, warnings)
                    if result is None:
                        continue
                    if result.request != provider_request:
                        warnings.append(
                            MarketDataQueryWarning(
                                code="PROVIDER_REQUEST_MISMATCH",
                                route_id=route.route_id,
                                provider_id=result.provider_id,
                            )
                        )
                        continue
                    if result.provider_id not in route.expected_result_provider_ids:
                        warnings.append(
                            MarketDataQueryWarning(
                                code="PROVIDER_RECEIPT_MISMATCH",
                                route_id=route.route_id,
                                provider_id=result.provider_id,
                            )
                        )
                        continue

                    # Provider I/O happens after durable acquisition and outside
                    # any lease/write transaction. Revalidate the exact route
                    # under access locks before the fenced persistence boundary.
                    if access is None:
                        raise MarketDataQueryServiceError("MARKET_DATA_ACCESS_REQUIRED")
                    if source_authorization is None:
                        raise MarketDataQueryServiceError("SOURCE_ROUTE_AUTHORIZATION_DENIED")
                    venue = fetch_context.identity.venue
                    if venue is None:
                        raise MarketDataQueryServiceError("IDENTITY_MARKET_UNSUPPORTED")
                    write_authorization = await access.authorizer.reauthorize_route_for_write(
                        principal=access.principal,
                        route=route,
                        asset_type=fetch_context.identity.asset_type,
                        market=venue,
                        purpose=fetch_context.query.purpose,
                        expected_authorization=source_authorization,
                    )

                    local_received_at = _trusted_receipt_time(self._clock)
                    try:
                        if fetch_lease is None:
                            persisted = await self._store.persist_provider_result(
                                fetch_context,
                                result,
                                received_at=local_received_at,
                                source_authorization=write_authorization,
                            )
                        else:
                            persisted = await self._store.persist_provider_result(
                                fetch_context,
                                result,
                                received_at=local_received_at,
                                source_authorization=write_authorization,
                                fetch_lease=fetch_lease,
                            )
                    except MarketDataStoreError as exc:
                        warnings.append(
                            MarketDataQueryWarning(
                                code=exc.code,
                                route_id=route.route_id,
                                provider_id=result.provider_id,
                            )
                        )
                        if fetch_lease is not None and exc.code.startswith("FETCH_LEASE_"):
                            break
                        continue
                    except ValueError:
                        warnings.append(
                            MarketDataQueryWarning(
                                code="PROVIDER_RECEIPT_REJECTED",
                                route_id=route.route_id,
                                provider_id=result.provider_id,
                            )
                        )
                        continue

                    fetches.append(_fetch_receipt(route, result, persisted))
                    fresh_revision_ids.update(persisted.observation_revision_ids)
                    window_fresh_revision_ids.update(persisted.observation_revision_ids)
                    # Display/refresh queries have no frozen user-provided
                    # knowledge boundary. Advance the local read cutoff only
                    # after the receipt was durably flushed by the store.
                    knowledge_cutoff = max(
                        knowledge_cutoff,
                        persisted.received_at,
                        local_received_at,
                    )
                    visibility_anchor = await self._store.resolve_visibility_anchor(
                        knowledge_cutoff=knowledge_cutoff
                    )
                    if fetch_lease is not None:
                        (
                            policy_routes,
                            allowed_source_registry_ids,
                            source_authorizations,
                        ) = await self._refresh_lease_read_authorization(
                            access=access,
                            policy=policy,
                            candidate_policy_routes=candidate_policy_routes,
                            context=fetch_context,
                            expected_access_grant_descriptor_hash=access_grant_descriptor_hash,
                        )
                        routes = await self._active_routes(policy_routes, warnings)
                    window_state = await self._read_local_state(
                        fetch_context,
                        knowledge_cutoff,
                        visibility_anchor=visibility_anchor,
                        snapshot_max_age=snapshot_max_age,
                        allowed_source_registry_ids=allowed_source_registry_ids,
                    )
                    if self._route_satisfied_window(
                        mode=request.mode,
                        state=window_state,
                        context=fetch_context,
                        fresh_revision_ids=frozenset(window_fresh_revision_ids),
                        passing_observation_count=persisted.passing_observation_count,
                        knowledge_cutoff=knowledge_cutoff,
                    ):
                        break
            finally:
                if fetch_lease is not None:
                    try:
                        released = await self._fetch_leases.release(fetch_lease)
                    except MarketDataFetchLeaseError as exc:
                        warnings.append(MarketDataQueryWarning(code=exc.code))
                    else:
                        if not released:
                            warnings.append(MarketDataQueryWarning(code="FETCH_LEASE_RELEASE_LOST"))

        if self._fetch_leases is not None:
            expected_access_grant_descriptor_hash = binding.access_grant_descriptor_hash
            if expected_access_grant_descriptor_hash is None:
                raise MarketDataQueryServiceError("PROVIDER_ACCESS_GRANT_UNBOUND")
            (
                policy_routes,
                allowed_source_registry_ids,
                source_authorizations,
            ) = await self._refresh_lease_read_authorization(
                access=access,
                policy=policy,
                candidate_policy_routes=candidate_policy_routes,
                context=context,
                expected_access_grant_descriptor_hash=expected_access_grant_descriptor_hash,
            )

        state = await self._read_local_state(
            context,
            knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            snapshot_max_age=snapshot_max_age,
            allowed_source_registry_ids=allowed_source_registry_ids,
        )
        refresh_status = _refresh_status_for(
            request.mode,
            state,
            fresh_revision_ids=frozenset(fresh_revision_ids),
            context=context,
            planner=self._coverage_planner,
            knowledge_cutoff=knowledge_cutoff,
        )
        if refresh_status == "fresh_incomplete":
            warnings.append(MarketDataQueryWarning(code="REFRESH_FRESHNESS_INCOMPLETE"))
        elif refresh_status == "fresh_unknown_calendar":
            warnings.append(MarketDataQueryWarning(code="REFRESH_FRESHNESS_UNKNOWN_CALENDAR"))
        return self._execution(
            context=context,
            cursor_query_fingerprint=request.query_fingerprint,
            knowledge_cutoff=knowledge_cutoff,
            identity_knowledge_cutoff=identity_cutoff,
            visibility_anchor=visibility_anchor,
            identity_visibility_anchor=identity_visibility_anchor,
            cursor_binding=binding,
            cursor_issued_at=request_started_at,
            state=state,
            cursor=None,
            fetches=fetches,
            warnings=warnings,
            refresh_status=refresh_status,
        )

    async def _refresh_lease_read_authorization(
        self,
        *,
        access: MarketDataQueryAccess | None,
        policy: MarketDataSourcePolicy,
        candidate_policy_routes: tuple[MarketDataProviderRoute, ...],
        context: ResolvedMarketDataQueryContext,
        expected_access_grant_descriptor_hash: str,
    ) -> tuple[
        tuple[MarketDataProviderRoute, ...],
        frozenset[str] | None,
        dict[str, MarketDataSourceAuthorization],
    ]:
        """Re-authorize every local re-read after a durable-lease boundary.

        A separate worker can hold a lease while user roles or source-registry
        policy changes. The follower or owner must not reuse its initial grant
        merely because the data is now local. A changed principal or grant
        descriptor fails closed rather than returning rows under an obsolete
        access decision.
        """
        if access is None:
            # Lower-level offline imports do not enter an interactive lease
            # path. Preserve the internal no-access seam without inventing an
            # authorization grant for it.
            return candidate_policy_routes, None, {}
        venue = context.identity.venue
        if venue is None:
            raise MarketDataQueryServiceError("IDENTITY_MARKET_UNSUPPORTED")
        current_principal = await access.authorizer.revalidate_principal(
            principal=access.principal
        )
        grant = await access.authorizer.authorize_policy(
            principal=current_principal,
            policy=policy,
            routes=candidate_policy_routes,
            asset_type=context.identity.asset_type,
            market=venue,
            purpose=context.query.purpose,
        )
        if grant.policy_descriptor_hash != expected_access_grant_descriptor_hash:
            raise MarketDataQueryServiceError("MARKET_DATA_ACCESS_CHANGED_DURING_FETCH")
        authorized_routes = tuple(
            route
            for route in candidate_policy_routes
            if route.route_id in grant.authorized_route_ids
        )
        return (
            authorized_routes,
            grant.authorized_source_registry_ids,
            dict(grant.route_authorizations),
        )

    async def _read_local_state(
        self,
        context: ResolvedMarketDataQueryContext,
        knowledge_cutoff: datetime,
        *,
        visibility_anchor: MarketDataVisibilityAnchor,
        snapshot_max_age: timedelta | None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> _LocalState:
        coverage_kwargs: dict[str, object] = {
            "knowledge_cutoff": knowledge_cutoff,
            "visibility_anchor": visibility_anchor,
            "include_unusable_for_coverage": True,
        }
        response_kwargs: dict[str, object] = {
            "knowledge_cutoff": knowledge_cutoff,
            "visibility_anchor": visibility_anchor,
        }
        # Keep compatibility with the pure in-memory stores used by legacy
        # query-service tests.  Production access calls always carry a
        # nonempty, current registry allow-list and therefore invoke the SQL
        # source filter added to MarketDataStore.
        if allowed_source_registry_ids is not None:
            coverage_kwargs["allowed_source_registry_ids"] = allowed_source_registry_ids
            response_kwargs["allowed_source_registry_ids"] = allowed_source_registry_ids
        coverage_revisions = await self._store.read_observation_revisions(
            context,
            **coverage_kwargs,
        )
        response_revisions = await self._store.read_observation_revisions(
            context,
            **response_kwargs,
        )
        window = TimeWindow(start_at=context.query.start, end_at=context.query.end)
        coverage_observations = tuple(
            item.as_coverage_observation(context) for item in coverage_revisions
        )
        if _uses_snapshot_freshness(context):
            if snapshot_max_age is None:
                raise MarketDataQueryServiceError("SNAPSHOT_FRESHNESS_POLICY_UNAVAILABLE")
            # Snapshot freshness is independent of a session grid. Skipping
            # the calendar read prevents a quote from being falsely blocked by
            # a missing bar calendar or being represented as a synthetic bar.
            calendar = CalendarSnapshot.unknown(
                calendar_id=context.coverage_identity.market,
                calendar_version="snapshot-freshness-v1",
                timezone_name="UTC",
                reason="SNAPSHOT_FRESHNESS",
            )
            coverage = self._snapshot_coverage_planner.plan(
                query=context.coverage_identity,
                window=window,
                observations=coverage_observations,
                required_fields=frozenset(context.query.required_fields),
                as_of=knowledge_cutoff,
                max_age=snapshot_max_age,
            )
        else:
            calendar_kwargs: dict[str, object] = {
                "knowledge_cutoff": knowledge_cutoff,
                "visibility_anchor": visibility_anchor,
            }
            if allowed_source_registry_ids is not None:
                calendar_kwargs["allowed_source_registry_ids"] = allowed_source_registry_ids
            calendar = await self._store.read_calendar_for_context(context, **calendar_kwargs)
            coverage = self._coverage_planner.plan(
                query=context.coverage_identity,
                window=window,
                calendar=calendar,
                observations=coverage_observations,
                required_fields=frozenset(context.query.required_fields),
                as_of=knowledge_cutoff,
            )
        return _LocalState(
            observations=_sort_observations(response_revisions),
            coverage_observations=_sort_observations(coverage_revisions),
            calendar=calendar,
            coverage=coverage,
            snapshot_max_age=snapshot_max_age,
        )

    async def _active_routes(
        self,
        routes: Sequence[MarketDataProviderRoute],
        warnings: list[MarketDataQueryWarning],
    ) -> tuple[MarketDataProviderRoute, ...]:
        """Prevent an inactive/unregistered source from making an external call."""
        active_routes: list[MarketDataProviderRoute] = []
        for route in routes:
            route_active = True
            for provider_id in sorted(route.expected_result_provider_ids):
                try:
                    await self._store.ensure_provider_active(provider_id)
                except MarketDataStoreError as exc:
                    warnings.append(
                        MarketDataQueryWarning(
                            code=exc.code,
                            route_id=route.route_id,
                            provider_id=provider_id,
                        )
                    )
                    route_active = False
                    break
                except ValueError:
                    warnings.append(
                        MarketDataQueryWarning(
                            code="PROVIDER_AUTHORIZATION_UNAVAILABLE",
                            route_id=route.route_id,
                            provider_id=provider_id,
                        )
                    )
                    route_active = False
                    break
            if route_active:
                active_routes.append(route)
        return tuple(active_routes)

    def _route_satisfied_window(
        self,
        *,
        mode: str,
        state: _LocalState,
        context: ResolvedMarketDataQueryContext,
        fresh_revision_ids: frozenset[str],
        passing_observation_count: int,
        knowledge_cutoff: datetime,
    ) -> bool:
        """Decide route fallback from the current window, never global coverage."""
        if (
            not _uses_snapshot_freshness(context)
            and state.calendar.status is CalendarStatus.UNKNOWN
        ):
            # With no frozen calendar, no provider can prove full coverage.
            # One passing primary receipt is retained, but a zero/failed receipt
            # may still fall through to the next approved source.
            return passing_observation_count > 0
        if mode == "local_first":
            return state.coverage.status is CoverageStatus.COMPLETE
        if mode == "refresh":
            fresh_coverage = _coverage_for_fresh_revisions(
                planner=self._coverage_planner,
                context=context,
                state=state,
                fresh_revision_ids=fresh_revision_ids,
                knowledge_cutoff=knowledge_cutoff,
            )
            return fresh_coverage.status is CoverageStatus.COMPLETE
        raise MarketDataQueryServiceError("QUERY_MODE_INVALID")

    async def _close_transaction_before_provider_io(self) -> None:
        """Release local DB state before any provider adapter can block on I/O.

        Production ``MarketDataStore`` exposes this boundary because ordinary
        reads and source reauthorization auto-begin a SQLAlchemy transaction.
        Lightweight in-memory stores used by contract tests have no database
        transaction to close and intentionally omit the optional method.
        """
        closer = getattr(self._store, "close_transaction_before_provider_io", None)
        if closer is None:
            return
        if not callable(closer):
            raise MarketDataQueryServiceError("PROVIDER_IO_TRANSACTION_BOUNDARY_INVALID")
        try:
            await closer()
        except MarketDataStoreError as exc:
            raise MarketDataQueryServiceError(exc.code) from exc

    async def _fetch_route(
        self,
        route: MarketDataProviderRoute,
        request: MarketDataProviderRequest,
        warnings: list[MarketDataQueryWarning],
    ) -> ProviderFetchResult | None:
        try:
            result = await route.adapter.fetch(request)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Provider boundary: no SDK traceback reaches an API response.
            code = _provider_error_code(exc)
            warnings.append(
                MarketDataQueryWarning(
                    code=code,
                    route_id=route.route_id,
                    provider_id=route.request_provider,
                )
            )
            return None
        if not isinstance(result, ProviderFetchResult):
            warnings.append(
                MarketDataQueryWarning(
                    code="PROVIDER_RECEIPT_INVALID",
                    route_id=route.route_id,
                    provider_id=route.request_provider,
                )
            )
            return None
        return result

    def _execution(
        self,
        *,
        context: ResolvedMarketDataQueryContext,
        cursor_query_fingerprint: str,
        knowledge_cutoff: datetime,
        identity_knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor,
        identity_visibility_anchor: MarketDataVisibilityAnchor,
        cursor_binding: MarketDataCursorBinding,
        cursor_issued_at: datetime,
        state: _LocalState,
        cursor: _Cursor | None,
        fetches: Sequence[MarketDataQueryFetch],
        warnings: Sequence[MarketDataQueryWarning],
        refresh_status: str | None = None,
        historical_status: str | None = None,
    ) -> MarketDataQueryExecution:
        issued_at = cursor.issued_at if cursor is not None else cursor_issued_at
        expires_at = cursor.expires_at if cursor is not None else issued_at + self._cursor_ttl
        observations, next_cursor = _paginate_observations(
            _response_observations_for(context, state),
            cursor=cursor,
            page_size=context.query.page_size,
            query_fingerprint=cursor_query_fingerprint,
            visibility_anchor=visibility_anchor,
            identity_visibility_anchor=identity_visibility_anchor,
            binding=cursor_binding,
            issued_at=issued_at,
            expires_at=expires_at,
            signing_key_supplier=self._cursor_signing_key,
        )
        return MarketDataQueryExecution(
            context=context,
            knowledge_cutoff=knowledge_cutoff,
            identity_knowledge_cutoff=identity_knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            identity_visibility_anchor=identity_visibility_anchor,
            coverage=state.coverage,
            observations=observations,
            next_cursor=next_cursor,
            fetches=tuple(fetches),
            warnings=tuple(warnings),
            refresh_status=refresh_status,
            historical_status=historical_status,
        )


def _identity_knowledge_cutoff_for(
    knowledge_cutoff: datetime,
    identity_visibility_anchor: MarketDataVisibilityAnchor,
) -> datetime:
    """Keep identity replay fixed even when a first page publishes new observations."""
    if identity_visibility_anchor.visible_at > knowledge_cutoff:
        raise MarketDataQueryServiceError("IDENTITY_VISIBILITY_ANCHOR_INVALID")
    return identity_visibility_anchor.visible_at


def _resolve_knowledge_cutoff(
    request: MarketDataQueryRequest,
    request_started_at: datetime,
    cursor: _Cursor | None,
) -> datetime:
    if cursor is not None:
        cutoff = cursor.visibility_anchor.visible_at
        if request.knowledge_cutoff is not None and request.knowledge_cutoff != cutoff:
            raise MarketDataQueryServiceError("CURSOR_CUTOFF_MISMATCH")
    else:
        cutoff = request.knowledge_cutoff or request_started_at
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise MarketDataQueryServiceError("KNOWLEDGE_CUTOFF_INVALID")
    return cutoff.astimezone(UTC)


def _trusted_receipt_time(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataQueryServiceError("LOCAL_RECEIPT_CLOCK_INVALID")
    return value.astimezone(UTC)


def _fetch_windows_for(
    *,
    context: ResolvedMarketDataQueryContext,
    coverage: CoveragePlan,
    mode: str,
) -> tuple[tuple[TimeWindow, ...], MarketDataQueryWarning | None]:
    full_window = TimeWindow(start_at=context.query.start, end_at=context.query.end)
    if mode == "refresh":
        return (full_window,), None
    if mode != "local_first":
        raise MarketDataQueryServiceError("QUERY_MODE_INVALID")
    if coverage.status is CoverageStatus.COMPLETE:
        return (), None
    if coverage.status is CoverageStatus.UNKNOWN_CALENDAR:
        return (full_window,), None
    windows = tuple(gap.fetch_window for gap in coverage.gaps)
    if not windows:
        # Coverage planner only returns INCOMPLETE when an expected event is
        # missing.  Treat any contrary state as a safe full-window refresh,
        # rather than inventing a zero-gap completion.
        return (full_window,), MarketDataQueryWarning(code="COVERAGE_GAP_INTEGRITY")
    if len(windows) > MAX_PROVIDER_FETCH_WINDOWS:
        return (full_window,), MarketDataQueryWarning(code="FETCH_GAPS_COALESCED")
    return windows, None


def _with_fetch_window(
    context: ResolvedMarketDataQueryContext,
    window: TimeWindow,
) -> ResolvedMarketDataQueryContext:
    """Create a window-specific provenance context without changing series identity."""
    query = context.query.model_copy(update={"start": window.start_at, "end": window.end_at})
    if not isinstance(query, ResolvedMarketDataQuery):
        raise MarketDataQueryServiceError("QUERY_CONTEXT_INVALID")
    return replace(context, query=query)


def _uses_snapshot_freshness(context: ResolvedMarketDataQueryContext) -> bool:
    """Select one reviewed single-record coverage strategy for a query.

    The calendar planner is valid for bars and reference-series facts because
    their contracts define a complete grid of expected events.  Quote snapshots
    instead use an explicit freshness policy.  Other record shapes (chains,
    surfaces, and reports) cannot safely inherit either rule: they need their
    own server-owned slice or reporting-completeness evaluator.  Fail before a
    local read or provider call so an internal caller cannot accidentally make
    an unconfigured product executable by bypassing the public family bridge.
    """
    if context.query.data_kind == "quote_snapshot":
        return True
    if context.query.data_kind in {"bars", "reference_series"}:
        return False
    raise MarketDataQueryServiceError("DATA_KIND_COVERAGE_UNSUPPORTED")


def _require_snapshot_max_age(state: _LocalState) -> timedelta:
    """Return the execution's reviewed quote SLA or fail closed."""
    if state.snapshot_max_age is None:
        raise MarketDataQueryServiceError("SNAPSHOT_FRESHNESS_POLICY_UNAVAILABLE")
    return state.snapshot_max_age


def _response_observations_for(
    context: ResolvedMarketDataQueryContext,
    state: _LocalState,
) -> tuple[LocalObservationRevision, ...]:
    """Return the same local facts that the product coverage can actually claim.

    The store returns one selected revision per event time.  A current quote
    product may still contain older event times in its requested display
    window, so return only the one event chosen by snapshot freshness coverage.
    This prevents a page from rendering a stale quote as if it were current.
    """
    response_observations = tuple(
        item for item in state.observations if _revision_is_response_usable(item, context=context)
    )
    if not _uses_snapshot_freshness(context):
        return response_observations
    accepted_event_times = {event.event_at for event in state.coverage.accepted_event_keys}
    return tuple(item for item in response_observations if item.event_at in accepted_event_times)


def _revision_is_response_usable(
    revision: LocalObservationRevision,
    *,
    context: ResolvedMarketDataQueryContext,
) -> bool:
    """Defend the product boundary even if a store implementation is stale."""
    return revision.quality is ObservationQuality.PASS and all(
        is_usable_field_value(field_name, revision.fields.get(field_name))
        for field_name in context.query.required_fields
    )


def _provider_request_for(
    context: ResolvedMarketDataQueryContext,
    route: MarketDataProviderRoute,
    *,
    policy_descriptor_hash: str,
    access_grant_descriptor_hash: str,
) -> MarketDataProviderRequest:
    venue = context.identity.venue
    if venue is None:
        raise MarketDataQueryServiceError("IDENTITY_MARKET_UNSUPPORTED")
    if route.family_id is not None and route.family_id != context.query.family_id:
        # ``routes_for`` normally makes this impossible. Keep the check at the
        # provider boundary as well so a future orchestration refactor cannot
        # send a permit-derived endpoint under a sibling family binding.
        raise MarketDataQueryServiceError("SOURCE_POLICY_ROUTE_FAMILY_MISMATCH")
    return MarketDataProviderRequest(
        query_fingerprint=context.query.query_fingerprint,
        canonical_id=context.query.canonical_id,
        asset_type=context.identity.asset_type,
        provider_symbol=context.identity.identity.display_symbol,
        market=venue,
        data_kind=context.query.data_kind,
        frequency=context.query.frequency or "snapshot",
        start_at=context.query.start,
        end_at=context.query.end,
        required_fields=frozenset(context.query.required_fields),
        provider=route.request_provider,
        adjustment=context.query.adjustment,
        price_basis=context.query.price_basis,
        currency=context.query.currency,
        unit=context.query.unit,
        source_policy_id=context.query.source_policy_id,
        route_id=route.route_id,
        family_id=context.query.family_id,
        provider_endpoint=route.provider_endpoint,
        product_type=context.identity.identity.product_type,
        fund_identity_kind=getattr(
            context.identity.identity.details,
            "fund_identity_kind",
            None,
        ),
        policy_descriptor_hash=policy_descriptor_hash,
        access_grant_descriptor_hash=access_grant_descriptor_hash,
    )


def _coverage_for_fresh_revisions(
    *,
    planner: CoveragePlanner,
    context: ResolvedMarketDataQueryContext,
    state: _LocalState,
    fresh_revision_ids: frozenset[str],
    knowledge_cutoff: datetime,
) -> CoveragePlan:
    fresh_observations = tuple(
        item.as_coverage_observation(context)
        for item in state.coverage_observations
        if item.revision_id in fresh_revision_ids
    )
    if _uses_snapshot_freshness(context):
        return SnapshotCoveragePlanner().plan(
            query=context.coverage_identity,
            window=TimeWindow(start_at=context.query.start, end_at=context.query.end),
            observations=fresh_observations,
            required_fields=frozenset(context.query.required_fields),
            as_of=knowledge_cutoff,
            max_age=_require_snapshot_max_age(state),
        )
    return planner.plan(
        query=context.coverage_identity,
        window=TimeWindow(start_at=context.query.start, end_at=context.query.end),
        calendar=state.calendar,
        observations=fresh_observations,
        required_fields=frozenset(context.query.required_fields),
        as_of=knowledge_cutoff,
    )


def _refresh_status_for(
    mode: str,
    state: _LocalState,
    *,
    fresh_revision_ids: frozenset[str],
    context: ResolvedMarketDataQueryContext,
    planner: CoveragePlanner,
    knowledge_cutoff: datetime,
) -> str | None:
    if mode != "refresh":
        return None
    if not _uses_snapshot_freshness(context) and state.calendar.status is CalendarStatus.UNKNOWN:
        return "fresh_unknown_calendar"
    fresh_coverage = _coverage_for_fresh_revisions(
        planner=planner,
        context=context,
        state=state,
        fresh_revision_ids=fresh_revision_ids,
        knowledge_cutoff=knowledge_cutoff,
    )
    if fresh_coverage.status is CoverageStatus.COMPLETE:
        return "fresh_complete"
    return "fresh_incomplete"


def _fetch_receipt(
    route: MarketDataProviderRoute,
    result: ProviderFetchResult,
    persisted: PersistedProviderFetch,
) -> MarketDataQueryFetch:
    return MarketDataQueryFetch(
        route_id=route.route_id,
        provider_id=result.provider_id,
        source_snapshot_id=persisted.source_snapshot_id,
        observation_revision_ids=persisted.observation_revision_ids,
        passing_observation_count=persisted.passing_observation_count,
        failed_observation_count=persisted.failed_observation_count,
    )


def _sort_observations(
    observations: Sequence[LocalObservationRevision],
) -> tuple[LocalObservationRevision, ...]:
    return tuple(
        sorted(
            observations,
            key=lambda item: (
                item.event_at,
                item.visibility_sequence,
                item.revision_number,
                item.revision_id,
            ),
        )
    )


def _paginate_observations(
    observations: tuple[LocalObservationRevision, ...],
    *,
    cursor: _Cursor | None,
    page_size: int,
    query_fingerprint: str,
    visibility_anchor: MarketDataVisibilityAnchor,
    identity_visibility_anchor: MarketDataVisibilityAnchor,
    binding: MarketDataCursorBinding,
    issued_at: datetime,
    expires_at: datetime,
    signing_key_supplier: Callable[[], bytes],
) -> tuple[tuple[LocalObservationRevision, ...], str | None]:
    start_index = 0
    if cursor is not None:
        if cursor.query_fingerprint != query_fingerprint:
            raise MarketDataQueryServiceError("CURSOR_QUERY_MISMATCH")
        if cursor.visibility_anchor != visibility_anchor:
            raise MarketDataQueryServiceError("CURSOR_VISIBILITY_ANCHOR_MISMATCH")
        if cursor.identity_visibility_anchor != identity_visibility_anchor:
            raise MarketDataQueryServiceError("CURSOR_IDENTITY_ANCHOR_MISMATCH")
        if cursor.binding != _cursor_binding_digest(binding):
            raise MarketDataQueryServiceError("CURSOR_ACCESS_MISMATCH")
        for index, item in enumerate(observations):
            if _observation_cursor_key(item) == cursor.key:
                start_index = index + 1
                break
        else:
            raise MarketDataQueryServiceError("CURSOR_NOT_FOUND")
    page = observations[start_index : start_index + page_size]
    if start_index + len(page) >= len(observations) or not page:
        return page, None
    return page, _encode_cursor(
        _observation_cursor_key(page[-1]),
        query_fingerprint=query_fingerprint,
        visibility_anchor=visibility_anchor,
        identity_visibility_anchor=identity_visibility_anchor,
        binding=binding,
        issued_at=issued_at,
        expires_at=expires_at,
        signing_key=signing_key_supplier(),
    )


def _observation_cursor_key(item: LocalObservationRevision) -> tuple[str, str]:
    return item.event_at.isoformat(), item.revision_id


def _encode_cursor(
    key: tuple[str, str],
    *,
    query_fingerprint: str,
    visibility_anchor: MarketDataVisibilityAnchor,
    identity_visibility_anchor: MarketDataVisibilityAnchor,
    binding: MarketDataCursorBinding,
    issued_at: datetime,
    expires_at: datetime,
    signing_key: bytes,
) -> str:
    _require_sha256(query_fingerprint, field_name="cursor query fingerprint")
    _require_text(key[1], field_name="cursor revision_id", maximum=255)
    parsed_event_at = _parse_cursor_datetime(key[0], field_name="cursor event_at")
    normalized_issued_at = _normalize_cursor_datetime(issued_at, field_name="cursor issued_at")
    normalized_expires_at = _normalize_cursor_datetime(expires_at, field_name="cursor expires_at")
    if normalized_expires_at <= normalized_issued_at:
        raise MarketDataQueryServiceError("CURSOR_EXPIRY_INVALID")
    if binding.policy_descriptor_hash is None:
        raise MarketDataQueryServiceError("CURSOR_POLICY_UNBOUND")
    binding_digest = _cursor_binding_digest(binding)
    payload = _canonical_cursor_payload(
        {
            "version": _CURSOR_VERSION,
            "query_fingerprint": query_fingerprint,
            "policy_descriptor_hash": binding_digest.policy_descriptor_hash,
            "access_grant_descriptor_hash": binding_digest.access_grant_descriptor_hash,
            "principal_scope_sha256": binding_digest.principal_scope_sha256,
            "tenant_scope_sha256": binding_digest.tenant_scope_sha256,
            "entitlement_revision_sha256": binding_digest.entitlement_revision_sha256,
            "visibility_anchor": _cursor_anchor_payload(visibility_anchor),
            "identity_visibility_anchor": _cursor_anchor_payload(identity_visibility_anchor),
            "event_at": parsed_event_at.isoformat(),
            "revision_id": key[1],
            "issued_at": normalized_issued_at.isoformat(),
            "expires_at": normalized_expires_at.isoformat(),
        }
    )
    signature = hmac.new(signing_key, payload, hashlib.sha256).digest()
    token = f"{_base64url_encode(payload)}.{_base64url_encode(signature)}"
    if len(token) > _MAX_CURSOR_TOKEN_LENGTH:
        raise MarketDataQueryServiceError("CURSOR_PAYLOAD_TOO_LARGE")
    return token


def _decode_cursor(
    cursor: str,
    *,
    signing_key: bytes,
    now: datetime,
    expected_binding: MarketDataCursorBinding | None = None,
    query_fingerprint: str | None = None,
) -> _Cursor:
    try:
        encoded_payload, encoded_signature = _split_cursor_token(cursor)
        decoded = _base64url_decode(encoded_payload)
        signature = _base64url_decode(encoded_signature)
        if len(decoded) > _MAX_CURSOR_PAYLOAD_BYTES or len(signature) != _CURSOR_HMAC_DIGEST_BYTES:
            raise ValueError("invalid cursor segment length")
        expected_signature = hmac.new(signing_key, decoded, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_signature, signature):
            raise MarketDataQueryServiceError("CURSOR_SIGNATURE_INVALID")
        payload = json.loads(decoded.decode("utf-8"))
    except MarketDataQueryServiceError:
        raise
    except (
        UnicodeEncodeError,
        UnicodeDecodeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
    ) as exc:
        raise MarketDataQueryServiceError("CURSOR_INVALID") from exc
    if not isinstance(payload, Mapping) or set(payload) != {
        "version",
        "query_fingerprint",
        "policy_descriptor_hash",
        "access_grant_descriptor_hash",
        "principal_scope_sha256",
        "tenant_scope_sha256",
        "entitlement_revision_sha256",
        "visibility_anchor",
        "identity_visibility_anchor",
        "event_at",
        "revision_id",
        "issued_at",
        "expires_at",
    }:
        raise MarketDataQueryServiceError("CURSOR_INVALID")
    if payload.get("version") != _CURSOR_VERSION:
        raise MarketDataQueryServiceError("CURSOR_VERSION_UNSUPPORTED")
    fingerprint = payload.get("query_fingerprint")
    event_at = payload.get("event_at")
    revision_id = payload.get("revision_id")
    if not isinstance(fingerprint, str) or not isinstance(event_at, str) or not isinstance(
        revision_id, str
    ):
        raise MarketDataQueryServiceError("CURSOR_INVALID")
    try:
        _require_sha256(fingerprint, field_name="cursor query fingerprint")
        binding = _CursorBindingDigest(
            principal_scope_sha256=payload.get("principal_scope_sha256"),
            tenant_scope_sha256=payload.get("tenant_scope_sha256"),
            entitlement_revision_sha256=payload.get("entitlement_revision_sha256"),
            policy_descriptor_hash=payload.get("policy_descriptor_hash"),
            access_grant_descriptor_hash=payload.get("access_grant_descriptor_hash"),
        )
        visibility_anchor = _decode_cursor_anchor(
            payload.get("visibility_anchor"),
            field_name="cursor visibility_anchor",
        )
        identity_visibility_anchor = _decode_cursor_anchor(
            payload.get("identity_visibility_anchor"),
            field_name="cursor identity_visibility_anchor",
        )
        parsed_event = _parse_cursor_datetime(event_at, field_name="cursor event_at")
        parsed_issued_at = _parse_cursor_datetime(
            payload.get("issued_at"),
            field_name="cursor issued_at",
        )
        parsed_expires_at = _parse_cursor_datetime(
            payload.get("expires_at"),
            field_name="cursor expires_at",
        )
    except (TypeError, ValueError) as exc:
        raise MarketDataQueryServiceError("CURSOR_INVALID") from exc
    if parsed_expires_at <= parsed_issued_at:
        raise MarketDataQueryServiceError("CURSOR_INVALID")
    try:
        normalized_now = _normalize_cursor_datetime(now, field_name="cursor verification time")
    except (TypeError, ValueError) as exc:
        raise MarketDataQueryServiceError("CURSOR_INVALID") from exc
    if normalized_now >= parsed_expires_at:
        raise MarketDataQueryServiceError("CURSOR_EXPIRED")
    if query_fingerprint is not None and fingerprint != query_fingerprint:
        raise MarketDataQueryServiceError("CURSOR_QUERY_MISMATCH")
    if expected_binding is not None:
        _assert_cursor_binding_matches(binding, expected_binding)
    try:
        normalized_revision_id = _require_text(
            revision_id,
            field_name="cursor revision_id",
            maximum=255,
        )
    except (TypeError, ValueError) as exc:
        raise MarketDataQueryServiceError("CURSOR_INVALID") from exc
    return _Cursor(
        query_fingerprint=fingerprint,
        key=(parsed_event.isoformat(), normalized_revision_id),
        visibility_anchor=visibility_anchor,
        identity_visibility_anchor=identity_visibility_anchor,
        binding=binding,
        issued_at=parsed_issued_at,
        expires_at=parsed_expires_at,
    )


def _historical_status_for(
    state: _LocalState,
    *,
    strict: bool,
) -> str | None:
    """Return the stable strict-read result without treating a gap as a fetch cue."""
    if not strict or state.coverage.status is CoverageStatus.COMPLETE:
        return None
    if state.coverage.status is CoverageStatus.UNKNOWN_CALENDAR:
        return "unknown_calendar"
    return "HISTORICAL_COVERAGE_UNAVAILABLE"


def _binding_for_access(
    *,
    cursor_binding: MarketDataCursorBinding | None,
    access: MarketDataQueryAccess | None,
) -> MarketDataCursorBinding:
    """Build one cursor binding from the current authenticated execution.

    A public caller must not be able to supply a cursor scope for another
    principal. When access is present, the only accepted unbound dimensions
    are the exact values derived from the principal that the API just
    authenticated. Policy and grant hashes remain server-owned and are set
    later in this execution.
    """
    if access is None:
        return cursor_binding or MarketDataCursorBinding()
    expected = MarketDataCursorBinding(
        principal_scope=access.principal.principal_scope,
        tenant_scope=access.principal.tenant_scope,
        entitlement_revision=access.principal.entitlement_revision,
    )
    if cursor_binding is None:
        return expected
    if (
        cursor_binding.principal_scope != expected.principal_scope
        or cursor_binding.tenant_scope != expected.tenant_scope
        or cursor_binding.entitlement_revision != expected.entitlement_revision
        or cursor_binding.policy_descriptor_hash is not None
        or cursor_binding.access_grant_descriptor_hash is not None
    ):
        raise MarketDataQueryServiceError("CURSOR_ACCESS_CONTEXT_MISMATCH")
    return expected


def _policy_descriptor_hash(policy: MarketDataSourcePolicy) -> str:
    """Hash only the immutable, reviewed policy dimensions a cursor must replay.

    Provider adapters deliberately stay out of this document because they are
    process objects. Their registered route capability and priority are what
    determine whether a request was authorized for a route.
    """
    descriptor = {
        "policy_id": policy.policy_id,
        "allowed_purposes": sorted(policy.allowed_purposes),
        "routes": [
            {
                "route_id": route.route_id,
                "request_provider": route.request_provider,
                "expected_result_provider_ids": sorted(route.expected_result_provider_ids),
                "asset_types": sorted(route.asset_types),
                "data_kinds": sorted(route.data_kinds),
                "frequencies": sorted(route.frequencies),
                "markets": sorted(route.markets),
                "adjustments": _policy_axis_payload(route.adjustments),
                "price_bases": _policy_axis_payload(route.price_bases),
                "currencies": _policy_axis_payload(route.currencies),
                "units": _policy_axis_payload(route.units),
                "family_id": route.family_id,
                "provider_endpoint": route.provider_endpoint,
                "product_types": (
                    sorted(route.product_types) if route.product_types is not None else None
                ),
                "fund_identity_kinds": (
                    sorted(route.fund_identity_kinds)
                    if route.fund_identity_kinds is not None
                    else None
                ),
            }
            for route in policy.routes
        ],
    }
    # A reviewed policy may legitimately have several routes.  It is hashed
    # before it becomes the fixed-size cursor field, so policy canonicalization
    # must not inherit the much smaller transport-token size limit.
    return hashlib.sha256(_canonical_json_bytes(descriptor)).hexdigest()


def _policy_axis_payload(values: frozenset[str | None]) -> list[str | None]:
    """Canonicalize capability axes which intentionally permit an explicit null."""
    return sorted(values, key=lambda item: (item is not None, item or ""))


def _cursor_anchor_payload(anchor: MarketDataVisibilityAnchor) -> dict[str, object]:
    return {
        "visible_at": anchor.visible_at.isoformat(),
        "max_visibility_sequence": anchor.max_visibility_sequence,
    }


def _decode_cursor_anchor(value: object, *, field_name: str) -> MarketDataVisibilityAnchor:
    if not isinstance(value, Mapping) or set(value) != {
        "visible_at",
        "max_visibility_sequence",
    }:
        raise ValueError(f"{field_name} must have the complete anchor shape")
    return MarketDataVisibilityAnchor(
        visible_at=_parse_cursor_datetime(value.get("visible_at"), field_name=f"{field_name} visible_at"),
        max_visibility_sequence=value.get("max_visibility_sequence"),
    )


def _assert_cursor_binding_matches(
    cursor_binding: _CursorBindingDigest,
    expected_binding: MarketDataCursorBinding,
) -> None:
    """Reject a token replayed under a different authenticated access context."""
    expected = _cursor_binding_digest(expected_binding)
    if cursor_binding.principal_scope_sha256 != expected.principal_scope_sha256:
        raise MarketDataQueryServiceError("CURSOR_PRINCIPAL_MISMATCH")
    if cursor_binding.tenant_scope_sha256 != expected.tenant_scope_sha256:
        raise MarketDataQueryServiceError("CURSOR_TENANT_MISMATCH")
    if cursor_binding.entitlement_revision_sha256 != expected.entitlement_revision_sha256:
        raise MarketDataQueryServiceError("CURSOR_ENTITLEMENT_MISMATCH")
    if cursor_binding.policy_descriptor_hash != expected.policy_descriptor_hash:
        raise MarketDataQueryServiceError("CURSOR_POLICY_MISMATCH")
    if (
        expected.access_grant_descriptor_hash is not None
        and cursor_binding.access_grant_descriptor_hash
        != expected.access_grant_descriptor_hash
    ):
        raise MarketDataQueryServiceError("CURSOR_ACCESS_GRANT_MISMATCH")


def _assert_cursor_access_grant_matches(
    cursor_binding: _CursorBindingDigest,
    expected_binding: MarketDataCursorBinding,
) -> None:
    """Recheck the source decision once identity/context becomes available."""
    expected_hash = expected_binding.access_grant_descriptor_hash
    if expected_hash is None:
        raise MarketDataQueryServiceError("CURSOR_ACCESS_GRANT_UNBOUND")
    if cursor_binding.access_grant_descriptor_hash != expected_hash:
        raise MarketDataQueryServiceError("CURSOR_ACCESS_GRANT_MISMATCH")


def _cursor_binding_digest(binding: MarketDataCursorBinding) -> _CursorBindingDigest:
    """Hash every caller-supplied access dimension with a field domain tag."""
    if binding.policy_descriptor_hash is None:
        raise MarketDataQueryServiceError("CURSOR_POLICY_UNBOUND")
    return _CursorBindingDigest(
        principal_scope_sha256=_cursor_binding_value_hash(
            "principal_scope",
            binding.principal_scope,
        ),
        tenant_scope_sha256=_cursor_binding_value_hash(
            "tenant_scope",
            binding.tenant_scope,
        ),
        entitlement_revision_sha256=_cursor_binding_value_hash(
            "entitlement_revision",
            binding.entitlement_revision,
        ),
        policy_descriptor_hash=binding.policy_descriptor_hash,
        access_grant_descriptor_hash=binding.access_grant_descriptor_hash,
    )


def _cursor_binding_value_hash(field_name: str, value: str) -> str:
    """Return a non-secret fixed-size digest for one cursor access field."""
    normalized_name = _require_text(field_name, field_name="cursor binding field", maximum=64)
    normalized_value = _require_text(value, field_name=f"cursor {normalized_name}", maximum=256)
    return hashlib.sha256(
        b"market-data-cursor-access-binding-v1\x00"
        + normalized_name.encode("utf-8")
        + b"\x00"
        + normalized_value.encode("utf-8")
    ).hexdigest()


def _canonical_cursor_payload(value: Mapping[str, object]) -> bytes:
    """Encode one bounded deterministic HMAC message without JSON whitespace."""
    payload = _canonical_json_bytes(value)
    if len(payload) > _MAX_CURSOR_PAYLOAD_BYTES:
        raise MarketDataQueryServiceError("CURSOR_PAYLOAD_TOO_LARGE")
    return payload


def _canonical_json_bytes(value: object) -> bytes:
    """Canonicalize hash inputs independently from cursor transport limits."""
    try:
        return json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MarketDataQueryServiceError("CURSOR_CANONICALIZATION_INVALID") from exc


def _normalize_cursor_datetime(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _parse_cursor_datetime(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return _normalize_cursor_datetime(parsed, field_name=field_name)


def _coerce_cursor_signing_key(value: str | bytes) -> bytes:
    """Validate an operator-supplied cursor HMAC key without logging it."""
    if isinstance(value, str):
        key = value.encode("utf-8")
    elif isinstance(value, bytes):
        key = value
    else:
        raise MarketDataQueryServiceError("CURSOR_SIGNING_KEY_INVALID")
    if not key:
        raise MarketDataQueryServiceError("CURSOR_SIGNING_KEY_UNAVAILABLE")
    if len(key) < 32:
        raise MarketDataQueryServiceError("CURSOR_SIGNING_KEY_INVALID")
    return key


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    if not value or any(character not in _BASE64URL_CHARACTERS for character in value):
        raise ValueError("invalid base64url segment")
    decoded = base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))
    if _base64url_encode(decoded) != value:
        raise ValueError("non-canonical base64url segment")
    return decoded


def _split_cursor_token(cursor: str) -> tuple[str, str]:
    if not isinstance(cursor, str) or not cursor or len(cursor) > _MAX_CURSOR_TOKEN_LENGTH:
        raise ValueError("invalid cursor token")
    parts = cursor.split(".")
    if len(parts) != 2:
        raise ValueError("invalid cursor token")
    return parts[0], parts[1]


def _provider_error_code(exc: Exception) -> str:
    candidate = getattr(exc, "code", None)
    if isinstance(candidate, str):
        try:
            return _require_text(candidate, field_name="provider error code", maximum=128)
        except (TypeError, ValueError):
            pass
    return "PROVIDER_FETCH_FAILED"


def _require_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must be non-empty and no longer than {maximum} characters")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    normalized = _require_text(value, field_name=field_name, maximum=64)
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _utc_now() -> datetime:
    return datetime.now(UTC)
