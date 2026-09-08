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
from datetime import datetime, timezone
from typing import Protocol

from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.coverage import (
    CalendarSnapshot,
    CalendarStatus,
    CoveragePlan,
    CoveragePlanner,
    CoverageStatus,
    TimeWindow,
)
from app.services.market_data.identity import MarketDataIdentityResolutionError
from app.services.market_data.providers import MarketDataProviderRequest, ProviderFetchResult
from app.services.market_data.query_resolution import (
    MarketDataQueryResolutionError,
    MarketDataQueryResolver,
    ResolvedMarketDataQueryContext,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
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
_MAX_CURSOR_PAYLOAD_BYTES = 1024
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
    ) -> ResolvedMarketDataQueryContext:
        """Resolve public input to server-owned catalog and master-data facts."""


class _Store(Protocol):
    async def read_observation_revisions(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
    ) -> tuple[LocalObservationRevision, ...]:
        """Read selected local observations at a point-in-time cutoff."""

    async def read_calendar_for_context(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
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
    ) -> PersistedProviderFetch:
        """Append one validated source receipt and observation revisions."""


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
    coverage: CoveragePlan
    observations: tuple[LocalObservationRevision, ...]
    next_cursor: str | None
    fetches: tuple[MarketDataQueryFetch, ...]
    warnings: tuple[MarketDataQueryWarning, ...]
    refresh_status: str | None = None


@dataclass(frozen=True, slots=True)
class _LocalState:
    """Unpaged local rows plus calendar-derived coverage for one full request."""

    observations: tuple[LocalObservationRevision, ...]
    calendar: CalendarSnapshot
    coverage: CoveragePlan


@dataclass(frozen=True, slots=True)
class _Cursor:
    """An authenticated-by-content pagination anchor and frozen local cutoff."""

    query_fingerprint: str
    key: tuple[str, str]
    knowledge_cutoff: datetime
    identity_knowledge_cutoff: datetime


class MarketDataQueryService:
    """Execute exact local-first queries without exposing provider output directly."""

    def __init__(
        self,
        *,
        resolver: _Resolver | MarketDataQueryResolver,
        store: _Store | MarketDataStore,
        source_policies: MarketDataSourcePolicyRegistry,
        coverage_planner: CoveragePlanner | None = None,
        allow_online_fetch: bool = True,
        clock: Callable[[], datetime] | None = None,
        cursor_signing_key: str | bytes | None = None,
    ) -> None:
        if not hasattr(resolver, "resolve"):
            raise TypeError("resolver must implement resolve")
        if not all(
            hasattr(store, method)
            for method in (
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
        if not isinstance(allow_online_fetch, bool):
            raise TypeError("allow_online_fetch must be a bool")
        self._resolver = resolver
        self._store = store
        self._source_policies = source_policies
        self._coverage_planner = coverage_planner or CoveragePlanner()
        self._allow_online_fetch = allow_online_fetch
        self._clock = clock or _utc_now
        self._cursor_signing_key_override = (
            _coerce_cursor_signing_key(cursor_signing_key)
            if cursor_signing_key is not None
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

    async def execute(self, request: MarketDataQueryRequest) -> MarketDataQueryExecution:
        """Resolve, serve locally, and conditionally persist bounded provider fills.

        A cursor is parsed before any local or external work, then fixes both
        master-data visibility and local observation visibility to its original
        receipt boundary.  A failed, malformed, mismatched, or unauthorized
        provider receipt becomes a stable warning and is never returned as data.
        """
        if not isinstance(request, MarketDataQueryRequest):
            raise TypeError("request must be a MarketDataQueryRequest")

        cursor = (
            _decode_cursor(request.cursor, signing_key=self._cursor_signing_key())
            if request.cursor is not None
            else None
        )
        # Freeze identity selection before any resolver/database work.  The
        # identity cutoff stays distinct from the observation cutoff because
        # a current local-first request can write observations after its
        # identity was resolved; a continuation must replay both boundaries.
        knowledge_cutoff = _resolve_knowledge_cutoff(request, self._clock, cursor)
        identity_cutoff = _identity_knowledge_cutoff_for(knowledge_cutoff, cursor)
        try:
            context = await self._resolver.resolve(
                request,
                identity_knowledge_cutoff=identity_cutoff,
            )
        except (MarketDataIdentityResolutionError, MarketDataQueryResolutionError):
            raise
        except ValueError as exc:
            raise MarketDataQueryServiceError("QUERY_RESOLUTION_FAILED") from exc

        if not isinstance(context, ResolvedMarketDataQueryContext):
            raise MarketDataQueryServiceError("QUERY_CONTEXT_INVALID")
        if cursor is not None and cursor.query_fingerprint != context.query.query_fingerprint:
            raise MarketDataQueryServiceError("CURSOR_QUERY_MISMATCH")

        try:
            policy = self._source_policies.resolve(context.query.source_policy_id)
        except MarketDataSourcePolicyError:
            raise
        if not policy.allows_purpose(context.query.purpose):
            raise MarketDataSourcePolicyError("SOURCE_POLICY_PURPOSE_DENIED")

        state = await self._read_local_state(context, knowledge_cutoff)
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
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                state=state,
                cursor=cursor,
                fetches=fetches,
                warnings=warnings,
            )

        if request.mode == "local_only":
            return self._execution(
                context=context,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
            )

        # Current online adapters timestamp availability at collection time.
        # They cannot safely contribute to a research/backtest result whose
        # knowledge cutoff is already fixed in the past.  A historical import
        # with independently evidenced availability may populate the store
        # beforehand, but an interactive provider call cannot smuggle a later
        # fact into a strict replay.
        if request.knowledge_cutoff is not None:
            warnings.append(MarketDataQueryWarning(code="STRICT_ONLINE_FETCH_INELIGIBLE"))
            return self._execution(
                context=context,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
                state=state,
                cursor=None,
                fetches=fetches,
                warnings=warnings,
            )

        if not self._allow_online_fetch:
            warnings.append(MarketDataQueryWarning(code="ONLINE_FETCH_DISABLED"))
            return self._execution(
                context=context,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
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
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
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

        policy_routes = policy.routes_for(context)
        if not policy_routes:
            warnings.append(MarketDataQueryWarning(code="SOURCE_POLICY_NO_ELIGIBLE_PROVIDER"))
            return self._execution(
                context=context,
                knowledge_cutoff=knowledge_cutoff,
                identity_knowledge_cutoff=identity_cutoff,
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
            for route in routes:
                provider_request = _provider_request_for(fetch_context, route)
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

                local_received_at = _trusted_receipt_time(self._clock)
                try:
                    persisted = await self._store.persist_provider_result(
                        fetch_context,
                        result,
                        received_at=local_received_at,
                    )
                except MarketDataStoreError as exc:
                    warnings.append(
                        MarketDataQueryWarning(
                            code=exc.code,
                            route_id=route.route_id,
                            provider_id=result.provider_id,
                        )
                    )
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
                # knowledge boundary.  Advance the local read cutoff only after
                # the receipt was durably flushed by the store.
                knowledge_cutoff = max(knowledge_cutoff, persisted.received_at, local_received_at)
                window_state = await self._read_local_state(fetch_context, knowledge_cutoff)
                if self._route_satisfied_window(
                    mode=request.mode,
                    state=window_state,
                    context=fetch_context,
                    fresh_revision_ids=frozenset(window_fresh_revision_ids),
                    passing_observation_count=persisted.passing_observation_count,
                    knowledge_cutoff=knowledge_cutoff,
                ):
                    break

        state = await self._read_local_state(context, knowledge_cutoff)
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
            knowledge_cutoff=knowledge_cutoff,
            identity_knowledge_cutoff=identity_cutoff,
            state=state,
            cursor=None,
            fetches=fetches,
            warnings=warnings,
            refresh_status=refresh_status,
        )

    async def _read_local_state(
        self,
        context: ResolvedMarketDataQueryContext,
        knowledge_cutoff: datetime,
    ) -> _LocalState:
        observations = await self._store.read_observation_revisions(
            context,
            knowledge_cutoff=knowledge_cutoff,
        )
        calendar = await self._store.read_calendar_for_context(
            context,
            knowledge_cutoff=knowledge_cutoff,
        )
        coverage = self._coverage_planner.plan(
            query=context.coverage_identity,
            window=TimeWindow(start_at=context.query.start, end_at=context.query.end),
            calendar=calendar,
            observations=tuple(item.as_coverage_observation(context) for item in observations),
            required_fields=frozenset(context.query.required_fields),
            as_of=knowledge_cutoff,
        )
        return _LocalState(
            observations=_sort_observations(observations),
            calendar=calendar,
            coverage=coverage,
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
        if state.calendar.status is CalendarStatus.UNKNOWN:
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
        knowledge_cutoff: datetime,
        identity_knowledge_cutoff: datetime,
        state: _LocalState,
        cursor: _Cursor | None,
        fetches: Sequence[MarketDataQueryFetch],
        warnings: Sequence[MarketDataQueryWarning],
        refresh_status: str | None = None,
    ) -> MarketDataQueryExecution:
        observations, next_cursor = _paginate_observations(
            state.observations,
            cursor=cursor,
            page_size=context.query.page_size,
            query_fingerprint=context.query.query_fingerprint,
            knowledge_cutoff=knowledge_cutoff,
            identity_knowledge_cutoff=identity_knowledge_cutoff,
            signing_key_supplier=self._cursor_signing_key,
        )
        return MarketDataQueryExecution(
            context=context,
            knowledge_cutoff=knowledge_cutoff,
            identity_knowledge_cutoff=identity_knowledge_cutoff,
            coverage=state.coverage,
            observations=observations,
            next_cursor=next_cursor,
            fetches=tuple(fetches),
            warnings=tuple(warnings),
            refresh_status=refresh_status,
        )


def _identity_knowledge_cutoff_for(
    knowledge_cutoff: datetime,
    cursor: _Cursor | None,
) -> datetime:
    """Keep identity replay fixed even when a first page publishes new observations."""
    if cursor is not None:
        return cursor.identity_knowledge_cutoff
    return knowledge_cutoff


def _resolve_knowledge_cutoff(
    request: MarketDataQueryRequest,
    clock: Callable[[], datetime],
    cursor: _Cursor | None,
) -> datetime:
    if cursor is not None:
        cutoff = cursor.knowledge_cutoff
    else:
        cutoff = request.knowledge_cutoff or clock()
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


def _provider_request_for(
    context: ResolvedMarketDataQueryContext,
    route: MarketDataProviderRoute,
) -> MarketDataProviderRequest:
    venue = context.identity.venue
    if venue is None:
        raise MarketDataQueryServiceError("IDENTITY_MARKET_UNSUPPORTED")
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
        for item in state.observations
        if item.revision_id in fresh_revision_ids
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
    if state.calendar.status is CalendarStatus.UNKNOWN:
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
                item.available_at,
                item.committed_at,
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
    knowledge_cutoff: datetime,
    identity_knowledge_cutoff: datetime,
    signing_key_supplier: Callable[[], bytes],
) -> tuple[tuple[LocalObservationRevision, ...], str | None]:
    start_index = 0
    if cursor is not None:
        if cursor.query_fingerprint != query_fingerprint:
            raise MarketDataQueryServiceError("CURSOR_QUERY_MISMATCH")
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
        knowledge_cutoff=knowledge_cutoff,
        identity_knowledge_cutoff=identity_knowledge_cutoff,
        signing_key=signing_key_supplier(),
    )


def _observation_cursor_key(item: LocalObservationRevision) -> tuple[str, str]:
    return item.event_at.isoformat(), item.revision_id


def _encode_cursor(
    key: tuple[str, str],
    *,
    query_fingerprint: str,
    knowledge_cutoff: datetime,
    identity_knowledge_cutoff: datetime,
    signing_key: bytes,
) -> str:
    payload = json.dumps(
        {
            "query_fingerprint": query_fingerprint,
            "event_at": key[0],
            "revision_id": key[1],
            "knowledge_cutoff": knowledge_cutoff.astimezone(UTC).isoformat(),
            "identity_knowledge_cutoff": identity_knowledge_cutoff.astimezone(UTC).isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(signing_key, payload, hashlib.sha256).digest()
    return f"{_base64url_encode(payload)}.{_base64url_encode(signature)}"


def _decode_cursor(
    cursor: str,
    *,
    signing_key: bytes,
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
        "query_fingerprint",
        "event_at",
        "revision_id",
        "knowledge_cutoff",
        "identity_knowledge_cutoff",
    }:
        raise MarketDataQueryServiceError("CURSOR_INVALID")
    fingerprint = payload.get("query_fingerprint")
    event_at = payload.get("event_at")
    revision_id = payload.get("revision_id")
    cutoff_value = payload.get("knowledge_cutoff")
    identity_cutoff_value = payload.get("identity_knowledge_cutoff")
    if (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint.lower())
        or not isinstance(event_at, str)
        or not isinstance(revision_id, str)
        or not isinstance(cutoff_value, str)
        or not isinstance(identity_cutoff_value, str)
    ):
        raise MarketDataQueryServiceError("CURSOR_INVALID")
    if query_fingerprint is not None and fingerprint != query_fingerprint:
        raise MarketDataQueryServiceError("CURSOR_QUERY_MISMATCH")
    try:
        parsed_event = datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        parsed_cutoff = datetime.fromisoformat(cutoff_value.replace("Z", "+00:00"))
        parsed_identity_cutoff = datetime.fromisoformat(
            identity_cutoff_value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise MarketDataQueryServiceError("CURSOR_INVALID") from exc
    if (
        parsed_event.tzinfo is None
        or parsed_event.utcoffset() is None
        or parsed_cutoff.tzinfo is None
        or parsed_cutoff.utcoffset() is None
        or parsed_identity_cutoff.tzinfo is None
        or parsed_identity_cutoff.utcoffset() is None
    ):
        raise MarketDataQueryServiceError("CURSOR_INVALID")
    _require_text(revision_id, field_name="cursor revision_id", maximum=255)
    return _Cursor(
        query_fingerprint=fingerprint,
        key=(parsed_event.astimezone(UTC).isoformat(), revision_id),
        knowledge_cutoff=parsed_cutoff.astimezone(UTC),
        identity_knowledge_cutoff=parsed_identity_cutoff.astimezone(UTC),
    )


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


def _utc_now() -> datetime:
    return datetime.now(UTC)
