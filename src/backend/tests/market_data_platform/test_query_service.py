"""Behavioral contracts for local-first market-data query orchestration."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any

import pytest

from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.access import (
    MarketDataAccessAuthorizer,
    MarketDataAccessGrant,
    MarketDataAuthorizationError,
    MarketDataPrincipal,
    MarketDataQueryAccess,
    MarketDataSourceAuthorization,
)
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import (
    CalendarSnapshot,
    CalendarStatus,
    EventKey,
    ObservationQuality,
    QueryIdentity,
    TimeWindow,
)
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseHandle,
    market_data_fetch_lease_key,
)
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.query_service import (
    MarketDataQueryService,
    MarketDataQueryServiceError,
)
from app.services.market_data.snapshot_freshness import (
    SnapshotFreshnessPolicy,
    SnapshotFreshnessPolicyRegistry,
)
from app.services.market_data.store import (
    LocalObservationRevision,
    MarketDataStoreError,
    PersistedProviderFetch,
)

UTC = timezone.utc
DATASET_ID = "dataset-market-stock"
DATASET_CODE = "market.stock_daily"
CANONICAL_ID = "instrument:stock:CN-SSE:600000"
METADATA_VERSION = "stock-v1"
_CURSOR_SIGNING_KEY = "test-market-data-cursor-hmac-key-material-0000000000000000000001"
_OTHER_CURSOR_SIGNING_KEY = "test-market-data-cursor-hmac-key-material-0000000000000000000002"


def _at(hour: int, minute: int = 0, *, day: int = 8) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


def _cursor_payload(token: str) -> dict[str, object]:
    encoded, _signature = token.split(".")
    decoded = base64.urlsafe_b64decode((encoded + "=" * (-len(encoded) % 4)).encode("ascii"))
    payload = json.loads(decoded.decode("utf-8"))
    assert isinstance(payload, dict)
    return payload


def _cursor_with_payload(token: str, payload: dict[str, object]) -> str:
    _encoded, signature = token.split(".")
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{encoded}.{signature}"


def _request(
    *,
    mode: str = "local_first",
    knowledge_cutoff: datetime | None = None,
    cursor: str | None = None,
    page_size: int = 500,
) -> MarketDataQueryRequest:
    payload: dict[str, Any] = {
        "identity": {"canonical_id": CANONICAL_ID},
        "dataset_code": DATASET_CODE,
        "data_kind": "bars",
        "frequency": "1d",
        "start": _at(9).isoformat(),
        "end": _at(12).isoformat(),
        "required_fields": ["close"],
        "adjustment": "qfq",
        "price_basis": "close",
        "currency": "CNY",
        "unit": "share",
        "source_policy_id": "market-default-v1",
        "mode": mode,
        "page_size": page_size,
    }
    if cursor is not None:
        payload["cursor"] = cursor
    if knowledge_cutoff is not None:
        payload.update(
            {
                "consistency": "strict",
                "purpose": "research",
                "knowledge_cutoff": knowledge_cutoff.isoformat(),
            }
        )
    return MarketDataQueryRequest.model_validate(payload)


def _context(request: MarketDataQueryRequest | None = None) -> ResolvedMarketDataQueryContext:
    request = request or _request()
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=CANONICAL_ID,
        dataset_code=DATASET_CODE,
        instrument_metadata_version=METADATA_VERSION,
    )
    identity = InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id=CANONICAL_ID,
        display_symbol="600000",
        name="浦发银行",
        venue="CN-SSE",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="600000",
        product_type="EQUITY",
        metadata_version=METADATA_VERSION,
        details=StockIdentityDetails(exchange_symbol="600000.SH"),
    )
    return ResolvedMarketDataQueryContext(
        query=query,
        identity=ResolvedMarketDataIdentity(
            instrument_id="instrument-stock-v1",
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            metadata_version=METADATA_VERSION,
            venue="CN-SSE",
            identity=identity,
            valid_from=_at(0, day=1),
            valid_to=None,
            known_at=_at(0, day=1),
        ),
        storage=DatasetStorageResolution(
            dataset_id=DATASET_ID,
            dataset_code=DATASET_CODE,
            storage_id="canonical-market-data",
            engine="postgresql",
            database_name="market_data",
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
        ),
        coverage_identity=QueryIdentity(
            dataset_code=DATASET_CODE,
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            instrument_metadata_version=METADATA_VERSION,
            data_kind="bars",
            market="CN-SSE",
            frequency="1d",
            source_policy_id="market-default-v1",
            adjustment="qfq",
            price_basis="close",
            currency="CNY",
            unit="share",
        ),
    )


def _snapshot_request(
    *,
    mode: str = "local_first",
    start: datetime | None = None,
    end: datetime | None = None,
) -> MarketDataQueryRequest:
    """Build one current quote request with explicit snapshot semantics."""
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "dataset_code": "market.quote_snapshot",
            "data_kind": "quote_snapshot",
            "frequency": "snapshot",
            "start": (start or _at(11)).isoformat(),
            "end": (end or _at(12, 1)).isoformat(),
            "required_fields": ["price"],
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "mode": mode,
        }
    )


def _snapshot_context(
    request: MarketDataQueryRequest | None = None,
) -> ResolvedMarketDataQueryContext:
    request = request or _snapshot_request()
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=CANONICAL_ID,
        dataset_code="market.quote_snapshot",
        instrument_metadata_version=METADATA_VERSION,
    )
    identity = InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id=CANONICAL_ID,
        display_symbol="600000",
        name="浦发银行",
        venue="CN-SSE",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="600000",
        product_type="EQUITY",
        metadata_version=METADATA_VERSION,
        details=StockIdentityDetails(exchange_symbol="600000.SH"),
    )
    return ResolvedMarketDataQueryContext(
        query=query,
        identity=ResolvedMarketDataIdentity(
            instrument_id="instrument-stock-v1",
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            metadata_version=METADATA_VERSION,
            venue="CN-SSE",
            identity=identity,
            valid_from=_at(0, day=1),
            valid_to=None,
            known_at=_at(0, day=1),
        ),
        storage=DatasetStorageResolution(
            dataset_id="dataset-market-quote-snapshot",
            dataset_code="market.quote_snapshot",
            storage_id="canonical-market-data",
            engine="postgresql",
            database_name="market_data",
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
        ),
        coverage_identity=QueryIdentity(
            dataset_code="market.quote_snapshot",
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            instrument_metadata_version=METADATA_VERSION,
            data_kind="quote_snapshot",
            market="CN-SSE",
            frequency="snapshot",
            source_policy_id="market-default-v1",
            adjustment=None,
            price_basis=None,
            currency="CNY",
            unit="share",
        ),
    )


def _calendar(*, known: bool = True) -> CalendarSnapshot:
    window = TimeWindow(start_at=_at(9), end_at=_at(12))
    if not known:
        return CalendarSnapshot.unknown(
            calendar_id="CN-SSE",
            calendar_version="2026.09",
            timezone_name="Asia/Shanghai",
            reason="CALENDAR_NOT_LOADED",
        )
    return CalendarSnapshot(
        calendar_id="CN-SSE",
        calendar_version="2026.09",
        timezone_name="Asia/Shanghai",
        coverage_window=window,
        event_keys=(EventKey(_at(9)), EventKey(_at(10)), EventKey(_at(11))),
        status=CalendarStatus.KNOWN,
    )


def _revision(event_at: datetime, *, value: float = 10.0) -> LocalObservationRevision:
    return LocalObservationRevision(
        revision_id=f"revision-{event_at.hour}-{value}",
        source_snapshot_id="snapshot-local",
        event_at=event_at,
        available_at=_at(12),
        committed_at=_at(12),
        visible_at=_at(12),
        visibility_sequence=event_at.hour,
        revision_number=1,
        quality=ObservationQuality.PASS,
        fields=MappingProxyType({"close": value}),
    )


class _Resolver:
    def __init__(self, context: ResolvedMarketDataQueryContext) -> None:
        self.context = context
        self.requests: list[MarketDataQueryRequest] = []
        self.identity_cutoffs: list[datetime | None] = []
        self.identity_visibility_anchors: list[MarketDataVisibilityAnchor | None] = []

    async def resolve(
        self,
        request: MarketDataQueryRequest,
        *,
        identity_knowledge_cutoff: datetime | None = None,
        identity_visibility_anchor: MarketDataVisibilityAnchor | None = None,
    ) -> ResolvedMarketDataQueryContext:
        self.requests.append(request)
        self.identity_cutoffs.append(identity_knowledge_cutoff)
        self.identity_visibility_anchors.append(identity_visibility_anchor)
        if identity_knowledge_cutoff is not None:
            assert identity_knowledge_cutoff.tzinfo is not None
        return self.context


class _CurrentIdentityResolver(_Resolver):
    """Model a newly published current identity after a historical cutoff."""

    def __init__(
        self,
        *,
        current_context: ResolvedMarketDataQueryContext,
        cutoff_context: ResolvedMarketDataQueryContext,
    ) -> None:
        super().__init__(current_context)
        self.cutoff_context = cutoff_context

    async def resolve(
        self,
        request: MarketDataQueryRequest,
        *,
        identity_knowledge_cutoff: datetime | None = None,
        identity_visibility_anchor: MarketDataVisibilityAnchor | None = None,
    ) -> ResolvedMarketDataQueryContext:
        self.requests.append(request)
        self.identity_cutoffs.append(identity_knowledge_cutoff)
        self.identity_visibility_anchors.append(identity_visibility_anchor)
        return self.context if identity_knowledge_cutoff is None else self.cutoff_context


class _Store:
    def __init__(
        self,
        *,
        calendar: CalendarSnapshot,
        revisions: list[LocalObservationRevision],
        inactive_provider_ids: frozenset[str] = frozenset(),
    ) -> None:
        self.calendar = calendar
        self.revisions = revisions
        self.inactive_provider_ids = inactive_provider_ids
        self.persisted: list[tuple[ResolvedMarketDataQueryContext, ProviderFetchResult]] = []
        self.read_cutoffs: list[datetime] = []
        self.visibility_anchors: list[MarketDataVisibilityAnchor] = []
        self.read_modes: list[bool] = []
        self.read_source_filters: list[frozenset[str] | None] = []
        self.calendar_source_filters: list[frozenset[str] | None] = []
        self.authorization_checks: list[str] = []
        self.persisted_source_authorizations: list[MarketDataSourceAuthorization | None] = []
        self.persisted_fetch_leases: list[MarketDataFetchLeaseHandle | None] = []
        self.provider_io_boundary_calls = 0
        self.provider_io_transaction_active = False

    async def resolve_visibility_anchor(
        self,
        *,
        knowledge_cutoff: datetime,
    ) -> MarketDataVisibilityAnchor:
        visible_sequences = [
            row.visibility_sequence for row in self.revisions if row.visible_at <= knowledge_cutoff
        ]
        return MarketDataVisibilityAnchor(
            visible_at=knowledge_cutoff,
            max_visibility_sequence=max(visible_sequences, default=0),
        )

    async def read_observation_revisions(
        self,
        _context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        include_unusable_for_coverage: bool = False,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> tuple[LocalObservationRevision, ...]:
        self.read_cutoffs.append(knowledge_cutoff)
        self.read_modes.append(include_unusable_for_coverage)
        self.read_source_filters.append(allowed_source_registry_ids)
        anchor = visibility_anchor or await self.resolve_visibility_anchor(
            knowledge_cutoff=knowledge_cutoff
        )
        self.visibility_anchors.append(anchor)
        return tuple(
            row
            for row in self.revisions
            if _context.query.start <= row.event_at < _context.query.end
            and anchor.permits(
                visible_at=row.visible_at,
                visibility_sequence=row.visibility_sequence,
            )
        )

    async def read_calendar_for_context(
        self,
        _context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> CalendarSnapshot:
        assert knowledge_cutoff.tzinfo is not None
        assert visibility_anchor is not None
        self.visibility_anchors.append(visibility_anchor)
        self.calendar_source_filters.append(allowed_source_registry_ids)
        return self.calendar

    async def ensure_provider_active(self, provider_id: str) -> None:
        self.authorization_checks.append(provider_id)
        if provider_id in self.inactive_provider_ids:
            raise MarketDataStoreError("PROVIDER_INACTIVE")

    async def close_transaction_before_provider_io(self) -> None:
        """Model release of a request-local transaction before adapter I/O."""
        self.provider_io_boundary_calls += 1
        self.provider_io_transaction_active = False

    async def persist_provider_result(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        *,
        received_at: datetime,
        source_authorization: MarketDataSourceAuthorization | None = None,
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
    ) -> PersistedProviderFetch:
        self.persisted.append((context, result))
        self.persisted_source_authorizations.append(source_authorization)
        self.persisted_fetch_leases.append(fetch_lease)
        for item in result.observations:
            self.revisions.append(
                LocalObservationRevision(
                    revision_id=f"revision-network-{item.event_at.isoformat()}",
                    source_snapshot_id=f"snapshot-{result.provider_id}",
                    event_at=item.event_at,
                    available_at=received_at,
                    committed_at=received_at,
                    visible_at=received_at,
                    visibility_sequence=max(
                        (row.visibility_sequence for row in self.revisions),
                        default=0,
                    )
                    + 1,
                    revision_number=1,
                    quality=ObservationQuality.PASS,
                    fields=item.fields,
                )
            )
        return PersistedProviderFetch(
            series_id="series-1",
            source_snapshot_id=f"snapshot-{result.provider_id}",
            observation_revision_ids=tuple(
                f"revision-network-{item.event_at.isoformat()}" for item in result.observations
            ),
            passing_observation_count=len(result.observations),
            failed_observation_count=0,
            received_at=received_at,
        )


class _SnapshotStore(_Store):
    """Make any accidental bar-calendar read fail the quote-snapshot contract."""

    def __init__(self, *, revisions: list[LocalObservationRevision]) -> None:
        super().__init__(calendar=_calendar(known=False), revisions=revisions)
        self.calendar_reads = 0

    async def read_calendar_for_context(
        self,
        _context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> CalendarSnapshot:
        del _context, knowledge_cutoff, visibility_anchor, allowed_source_registry_ids
        self.calendar_reads += 1
        raise AssertionError("quote snapshots must not read a bars calendar")


class _Provider:
    def __init__(
        self, result: ProviderFetchResult | Exception, *, bind_request: bool = True
    ) -> None:
        self.result = result
        self.bind_request = bind_request
        self.requests: list[Any] = []

    async def fetch(self, request: Any) -> ProviderFetchResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        if self.bind_request:
            return replace(self.result, request=request)
        return self.result


class _ProviderTransactionProbe(_Provider):
    """Fail the test if query orchestration calls an adapter under a transaction."""

    def __init__(self, result: ProviderFetchResult | Exception, *, store: _Store) -> None:
        super().__init__(result)
        self._store = store

    async def fetch(self, request: Any) -> ProviderFetchResult:
        assert not self._store.provider_io_transaction_active
        return await super().fetch(request)


class _FirstPersistenceFailureStore(_Store):
    """Leave a simulated auth/write transaction active after the first route."""

    def __init__(self, *, calendar: CalendarSnapshot, revisions: list[LocalObservationRevision]) -> None:
        super().__init__(calendar=calendar, revisions=revisions)
        self._fail_first_persistence = True

    async def persist_provider_result(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        *,
        received_at: datetime,
        source_authorization: MarketDataSourceAuthorization | None = None,
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
    ) -> PersistedProviderFetch:
        if self._fail_first_persistence:
            self._fail_first_persistence = False
            self.provider_io_transaction_active = True
            raise MarketDataStoreError("OBSERVATION_WRITE_FAILED")
        return await super().persist_provider_result(
            context,
            result,
            received_at=received_at,
            source_authorization=source_authorization,
            fetch_lease=fetch_lease,
        )


class _FetchLeases:
    """Observable lease fake for orchestration tests without a real provider call."""

    def __init__(
        self,
        handle: MarketDataFetchLeaseHandle | None,
        *,
        on_acquire: Callable[[], None] | None = None,
    ) -> None:
        self.handle = handle
        self._on_acquire = on_acquire
        self.acquired_keys: list[str] = []
        self.released_handles: list[MarketDataFetchLeaseHandle] = []

    async def acquire(self, lease_key_sha256: str) -> MarketDataFetchLeaseHandle | None:
        self.acquired_keys.append(lease_key_sha256)
        if self._on_acquire is not None:
            self._on_acquire()
        return self.handle

    async def release(self, handle: MarketDataFetchLeaseHandle) -> bool:
        self.released_handles.append(handle)
        return True


def _provider_result(
    *,
    provider_id: str = "akshare",
    events: tuple[datetime, ...] = (_at(9), _at(10), _at(11)),
) -> ProviderFetchResult:
    return ProviderFetchResult(
        provider_id=provider_id,
        source_revision="route-v1",
        retrieved_at=_at(12),
        observations=tuple(
            ProviderMarketObservation(
                event_at=event_at,
                available_at=_at(12),
                fields={"close": 10.0 + event_at.hour},
            )
            for event_at in events
        ),
        raw_payload={"route": provider_id, "events": [item.isoformat() for item in events]},
        request=MarketDataProviderRequest(
            query_fingerprint="a" * 64,
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            provider_symbol="600000",
            market="CN-SSE",
            data_kind="bars",
            frequency="1d",
            start_at=_at(9),
            end_at=_at(12),
            required_fields=frozenset({"close"}),
            provider="akshare",
            adjustment="qfq",
            price_basis="close",
            currency="CNY",
            unit="share",
            source_policy_id="market-default-v1",
        ),
    )


def _snapshot_provider_result(
    *,
    event_at: datetime = _at(12),
) -> ProviderFetchResult:
    """Build a receipt that represents one exact current quote observation."""
    return ProviderFetchResult(
        provider_id="akshare",
        source_revision="quote-route-v1",
        retrieved_at=_at(12),
        observations=(
            ProviderMarketObservation(
                event_at=event_at,
                available_at=_at(12),
                fields={"price": 10.5},
            ),
        ),
        raw_payload={"route": "akshare-quote", "event": event_at.isoformat()},
        request=MarketDataProviderRequest(
            query_fingerprint="a" * 64,
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            provider_symbol="600000",
            market="CN-SSE",
            data_kind="quote_snapshot",
            frequency="snapshot",
            start_at=_at(11),
            end_at=_at(12, 1),
            required_fields=frozenset({"price"}),
            provider="akshare",
            currency="CNY",
            unit="share",
            source_policy_id="market-default-v1",
        ),
    )


def _service(
    *,
    context: ResolvedMarketDataQueryContext,
    store: _Store,
    provider_routes: tuple[Any, ...],
    allow_online_fetch: bool = True,
    cursor_signing_key: str = _CURSOR_SIGNING_KEY,
    cursor_ttl: timedelta = timedelta(minutes=15),
    snapshot_freshness_policies: SnapshotFreshnessPolicyRegistry | None = None,
    fetch_leases: Any | None = None,
):
    from app.services.market_data.source_policy import (
        MarketDataSourcePolicy,
        MarketDataSourcePolicyRegistry,
    )

    return _AuthorizedTestQueryService(
        resolver=_Resolver(context),
        store=store,
        source_policies=MarketDataSourcePolicyRegistry(
            (
                MarketDataSourcePolicy(
                    policy_id="market-default-v1",
                    allowed_purposes=frozenset({"display", "research", "backtest"}),
                    routes=provider_routes,
                ),
            )
        ),
        snapshot_freshness_policies=snapshot_freshness_policies,
        allow_online_fetch=allow_online_fetch,
        clock=lambda: _at(12),
        cursor_signing_key=cursor_signing_key,
        cursor_ttl=cursor_ttl,
        fetch_leases=fetch_leases,
        test_store=store,
    )


def _route(provider: _Provider, *, expected: str = "akshare", request_provider: str = "akshare"):
    from app.services.market_data.source_policy import MarketDataProviderRoute

    return MarketDataProviderRoute(
        route_id=f"route-{request_provider}",
        request_provider=request_provider,
        expected_result_provider_ids=frozenset({expected}),
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=provider,
    )


def _principal() -> MarketDataPrincipal:
    return MarketDataPrincipal(
        principal_id="user-1",
        principal_scope="principal-v1:test-user",
        tenant_scope="default",
        roles=("user",),
        permissions=("data:read",),
        entitlement_revision="e" * 64,
    )


def _source_authorization(
    *,
    source_registry_id: str,
    descriptor_hash: str,
) -> MarketDataSourceAuthorization:
    principal = _principal()
    return MarketDataSourceAuthorization(
        source_registry_id=source_registry_id,
        registry_updated_at=_at(12).isoformat(),
        asset_type="stock",
        market="CN-SSE",
        purpose="display",
        license_status="APPROVED",
        allowed_uses=("DISPLAY",),
        jurisdictions=("CN",),
        effective_from=_at(0, day=1).isoformat(),
        effective_to=None,
        retention_policy="market-data-v1",
        retention_expires_at=None,
        redistribution_policy="NO_REDISTRIBUTION",
        principal_scope=principal.principal_scope,
        tenant_scope=principal.tenant_scope,
        entitlement_revision=principal.entitlement_revision,
        decision="ALLOW",
        descriptor_hash=descriptor_hash,
    )


class _AccessAuthorizer(MarketDataAccessAuthorizer):
    """Service-level authorization fake that preserves the production type boundary."""

    def __init__(
        self,
        *,
        grant: MarketDataAccessGrant,
        store: _Store,
        resolver: _Resolver,
        write_authorization: MarketDataSourceAuthorization | Exception | None = None,
    ) -> None:
        self.grant = grant
        self.store = store
        self.resolver = resolver
        self.write_authorization = write_authorization
        self.read_entitlement_checks = 0
        self.policy_authorizations: list[tuple[str, ...]] = []
        self.local_read_counts_at_authorization: list[int] = []
        self.write_reauthorizations: list[tuple[str, MarketDataSourceAuthorization]] = []
        self.revalidated_principals: list[MarketDataPrincipal] = []
        self.revalidation_result: MarketDataPrincipal | Exception | None = None
        self.refreshed_grant: MarketDataAccessGrant | Exception | None = None

    def require_read_data(self, *, principal: MarketDataPrincipal) -> None:
        self.read_entitlement_checks += 1
        if not principal.can_read_data:
            raise AssertionError("test access principal must have data:read")

    async def authorize_policy(self, **kwargs: object) -> MarketDataAccessGrant:
        # Identity is resolved first, while source-dependent local reads,
        # calendar planning, provider work, and persistence are still absent.
        assert self.resolver.requests
        self.local_read_counts_at_authorization.append(len(self.store.read_cutoffs))
        routes = kwargs["routes"]
        assert isinstance(routes, tuple)
        self.policy_authorizations.append(tuple(route.route_id for route in routes))
        if isinstance(self.refreshed_grant, Exception):
            raise self.refreshed_grant
        if self.refreshed_grant is not None and len(self.policy_authorizations) > 1:
            return self.refreshed_grant
        return self.grant

    async def revalidate_principal(
        self,
        *,
        principal: MarketDataPrincipal,
    ) -> MarketDataPrincipal:
        self.revalidated_principals.append(principal)
        if isinstance(self.revalidation_result, Exception):
            raise self.revalidation_result
        return self.revalidation_result or principal

    async def reauthorize_route_for_write(
        self,
        *,
        principal: MarketDataPrincipal,
        route: Any,
        asset_type: str,
        market: str,
        purpose: str,
        expected_authorization: MarketDataSourceAuthorization,
    ) -> MarketDataSourceAuthorization:
        """Model the production post-fetch write boundary without a real database."""
        del principal, asset_type, market, purpose
        self.write_reauthorizations.append((route.route_id, expected_authorization))
        if isinstance(self.write_authorization, Exception):
            raise self.write_authorization
        return self.write_authorization or expected_authorization


def _access(
    *,
    source_registry_id: str,
    route_id: str,
    grant_hash: str,
    store: _Store,
    resolver: _Resolver,
    write_authorization: MarketDataSourceAuthorization | Exception | None = None,
) -> MarketDataQueryAccess:
    authorization = _source_authorization(
        source_registry_id=source_registry_id,
        descriptor_hash="c" * 64,
    )
    principal = _principal()
    grant = MarketDataAccessGrant(
        principal=principal,
        policy_id="market-default-v1",
        purpose="display",
        route_authorizations=((route_id, authorization),),
        policy_descriptor_hash=grant_hash,
    )
    return MarketDataQueryAccess(
        principal=principal,
        authorizer=_AccessAuthorizer(
            grant=grant,
            store=store,
            resolver=resolver,
            write_authorization=write_authorization,
        ),
    )


def _allow_all_routes_access(
    service: MarketDataQueryService,
    store: _Store,
) -> MarketDataQueryAccess:
    """Build an explicit current grant for ordinary online service tests."""
    resolver = service._resolver
    assert isinstance(resolver, _Resolver)
    policy = service._source_policies.resolve("market-default-v1")
    authorizations = tuple(
        (
            route.route_id,
            _source_authorization(
                source_registry_id=sorted(route.expected_result_provider_ids)[0],
                descriptor_hash=f"{index + 1:064x}",
            ),
        )
        for index, route in enumerate(policy.routes)
    )
    principal = _principal()
    grant = MarketDataAccessGrant(
        principal=principal,
        policy_id=policy.policy_id,
        purpose="display",
        route_authorizations=authorizations,
        policy_descriptor_hash="f" * 64,
    )
    return MarketDataQueryAccess(
        principal=principal,
        authorizer=_AccessAuthorizer(grant=grant, store=store, resolver=resolver),
    )


class _AuthorizedTestQueryService(MarketDataQueryService):
    """Make legacy behavior tests explicit authorized executions by default.

    The production service itself rejects unauthenticated interactive queries.
    This harness supplies a grant only where a test did not choose a narrower
    one; tests for the rejection call ``execute_without_access`` directly.
    """

    def __init__(self, *args: object, test_store: _Store, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._test_store = test_store

    async def execute(
        self,
        request: MarketDataQueryRequest,
        *,
        cursor_binding: object = None,
        access: MarketDataQueryAccess | None = None,
    ) -> Any:
        if access is None and cursor_binding is None:
            access = _allow_all_routes_access(self, self._test_store)
        return await super().execute(
            request,
            cursor_binding=cursor_binding,
            access=access,
        )

    async def execute_without_access(
        self,
        request: MarketDataQueryRequest,
        *,
        cursor_binding: object = None,
    ) -> Any:
        """Exercise the production no-access path without test-harness defaults."""
        return await super().execute(request, cursor_binding=cursor_binding)


def _snapshot_route(provider: _Provider):
    """Route only a reviewed stock quote-snapshot request."""
    from app.services.market_data.source_policy import MarketDataProviderRoute

    return MarketDataProviderRoute(
        route_id="route-akshare-quote",
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"quote_snapshot"}),
        frequencies=frozenset({"snapshot"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({None}),
        price_bases=frozenset({None}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=provider,
    )


@pytest.mark.asyncio
async def test_local_complete_data_does_not_invoke_a_provider() -> None:
    """A fully covered local query remains local and retains no network side effect."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request())

    assert result.coverage.status.value == "complete"
    assert result.observations == tuple(store.revisions)
    assert provider.requests == []
    assert store.persisted == []
    assert result.fetches == ()


@pytest.mark.asyncio
async def test_missing_local_data_is_persisted_then_reread_from_local_store() -> None:
    """The response is reconstructed from the store after a provider fills a precise gap."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(9))])
    provider = _Provider(_provider_result(events=(_at(10), _at(11))))

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request())

    assert result.coverage.status.value == "complete"
    assert [item.event_at for item in result.observations] == [_at(9), _at(10), _at(11)]
    assert len(store.persisted) == 1
    persisted_context, persisted_result = store.persisted[0]
    assert persisted_context.query.start == _at(10)
    assert persisted_context.query.end == _at(12)
    assert persisted_result.request == provider.requests[0]
    assert [(item.start_at, item.end_at) for item in [provider.requests[0]]] == [(_at(10), _at(12))]
    assert result.fetches[0].provider_id == "akshare"


@pytest.mark.asyncio
async def test_cross_worker_fetch_lease_follower_rereads_local_without_calling_a_route() -> None:
    """A remote owner suppresses every primary/fallback adapter call in this worker."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    follower = _FetchLeases(handle=None)
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
        fetch_leases=follower,
    )

    result = await service.execute(_request())

    assert len(follower.acquired_keys) == 1
    assert provider.requests == []
    assert follower.released_handles == []
    assert store.persisted == []
    assert [warning.code for warning in result.warnings] == ["FETCH_LEASE_HELD"]
    # The initial local read is followed by an explicit follower re-read after
    # its failed acquire; it must not return the stale pre-acquire state.
    assert len(store.read_cutoffs) >= 4


@pytest.mark.asyncio
async def test_cross_worker_fetch_lease_follower_rejects_revoked_principal_before_reread() -> None:
    """A lease wait cannot expose local facts under a revoked user grant."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    )
    resolver = service._resolver
    assert isinstance(resolver, _Resolver)
    access = _access(
        source_registry_id="akshare",
        route_id="route-akshare",
        grant_hash="a" * 64,
        store=store,
        resolver=resolver,
    )
    follower = _FetchLeases(
        handle=None,
        on_acquire=lambda: setattr(
            access.authorizer,
            "revalidation_result",
            MarketDataAuthorizationError("MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"),
        ),
    )
    service._fetch_leases = follower

    with pytest.raises(MarketDataAuthorizationError) as rejected:
        await service.execute(_request(), access=access)

    assert rejected.value.code == "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"
    assert access.authorizer.revalidated_principals == [access.principal]
    assert provider.requests == []
    # The initial authorized state is read, but the follower performs no
    # post-lease local re-read after current authorization is rejected.
    assert len(store.read_cutoffs) == 2


@pytest.mark.asyncio
async def test_cross_worker_fetch_lease_follower_rejects_changed_source_grant_before_reread() -> None:
    """A source-registry descriptor change fails closed before local evidence reads."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    )
    resolver = service._resolver
    assert isinstance(resolver, _Resolver)
    access = _access(
        source_registry_id="akshare",
        route_id="route-akshare",
        grant_hash="a" * 64,
        store=store,
        resolver=resolver,
    )
    follower = _FetchLeases(
        handle=None,
        on_acquire=lambda: setattr(
            access.authorizer,
            "refreshed_grant",
            replace(access.authorizer.grant, policy_descriptor_hash="b" * 64),
        ),
    )
    service._fetch_leases = follower

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await service.execute(_request(), access=access)

    assert rejected.value.code == "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"
    assert access.authorizer.revalidated_principals == [access.principal]
    assert provider.requests == []
    assert len(store.read_cutoffs) == 2


@pytest.mark.asyncio
async def test_cross_worker_fetch_lease_owner_releases_only_its_exact_fence() -> None:
    """The orchestration leader passes its handle to persistence and releases it in finally."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    handle = MarketDataFetchLeaseHandle(
        lease_key_sha256="a" * 64,
        owner_token="owner-1",
        fence_token=7,
        expires_at=_at(12) + timedelta(minutes=5),
    )
    owner = _FetchLeases(handle=handle)
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
        fetch_leases=owner,
    )

    result = await service.execute(_request())

    assert len(owner.acquired_keys) == 1
    assert owner.released_handles == [handle]
    assert len(provider.requests) == 1
    assert store.persisted_fetch_leases == [handle]
    assert result.fetches[0].provider_id == "akshare"


@pytest.mark.asyncio
async def test_cross_worker_lease_winner_rereads_after_prior_owner_publishes() -> None:
    """A newly acquired local-first lease never refetches a just-published gap."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    handle = MarketDataFetchLeaseHandle(
        lease_key_sha256="b" * 64,
        owner_token="owner-after-release",
        fence_token=8,
        expires_at=_at(12) + timedelta(minutes=5),
    )

    def publish_from_previous_owner() -> None:
        store.revisions.extend(_revision(_at(hour)) for hour in (9, 10, 11))

    winner = _FetchLeases(handle=handle, on_acquire=publish_from_previous_owner)
    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
        fetch_leases=winner,
    ).execute(_request())

    assert provider.requests == []
    assert store.persisted == []
    assert winner.released_handles == [handle]
    assert result.coverage.status.value == "complete"
    assert [item.event_at for item in result.observations] == [_at(9), _at(10), _at(11)]


@pytest.mark.asyncio
async def test_fallback_provider_starts_after_prior_route_transaction_is_closed() -> None:
    """Fallback adapter calls never retain a failed route's auth/write transaction."""
    context = _context()
    store = _FirstPersistenceFailureStore(calendar=_calendar(), revisions=[])
    primary = _ProviderTransactionProbe(_provider_result(), store=store)
    fallback = _ProviderTransactionProbe(_provider_result(), store=store)

    result = await _service(
        context=context,
        store=store,
        provider_routes=(
            _route(primary),
            _route(fallback, request_provider="akshare-fallback"),
        ),
    ).execute(_request())

    assert len(primary.requests) == 1
    assert len(fallback.requests) == 1
    assert store.provider_io_boundary_calls == 2
    assert not store.provider_io_transaction_active
    assert result.coverage.status.value == "complete"


def test_fetch_lease_key_is_stable_for_one_resolved_gap_and_changes_with_semantics() -> None:
    """A lease never relies on a process-local request object identity."""
    context = _context()
    family_bound_context = replace(
        context,
        query=context.query.model_copy(
            update={
                "family_id": "stock.realtime",
                "family_contract_version": "market-data-family-v1",
            }
        ),
    )
    common = {
        "mode": "local_first",
        "policy_descriptor_hash": "b" * 64,
        "access_grant_descriptor_hash": "c" * 64,
    }

    first = market_data_fetch_lease_key(
        **common,
        context=family_bound_context,
        coverage_gap=TimeWindow(start_at=_at(9), end_at=_at(12)),
    )
    same = market_data_fetch_lease_key(
        **common,
        context=family_bound_context,
        coverage_gap=TimeWindow(start_at=_at(9), end_at=_at(12)),
    )
    different_gap = market_data_fetch_lease_key(
        **common,
        context=family_bound_context,
        coverage_gap=TimeWindow(start_at=_at(10), end_at=_at(12)),
    )
    different_family = market_data_fetch_lease_key(
        **common,
        context=replace(
            family_bound_context,
            query=family_bound_context.query.model_copy(update={"family_id": "stock.valuation"}),
        ),
        coverage_gap=TimeWindow(start_at=_at(9), end_at=_at(12)),
    )
    different_contract_version = market_data_fetch_lease_key(
        **common,
        context=replace(
            family_bound_context,
            query=family_bound_context.query.model_copy(
                update={"family_contract_version": "market-data-family-v2"}
            ),
        ),
        coverage_gap=TimeWindow(start_at=_at(9), end_at=_at(12)),
    )

    assert first == same
    assert first != different_gap
    assert first != different_family
    assert first != different_contract_version


@pytest.mark.asyncio
async def test_current_source_grant_filters_local_reads_and_freezes_provider_receipt_evidence() -> None:
    """Only currently allowed routes/source IDs participate in a data execution."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(9))])
    denied_primary = _Provider(_provider_result(events=(_at(10), _at(11))))
    allowed_fallback = _Provider(
        _provider_result(
            provider_id="openbb:yfinance",
            events=(_at(10), _at(11)),
        )
    )
    service = _service(
        context=context,
        store=store,
        provider_routes=(
            _route(denied_primary),
            _route(
                allowed_fallback,
                expected="openbb:yfinance",
                request_provider="yfinance",
            ),
        ),
    )
    resolver = service._resolver
    assert isinstance(resolver, _Resolver)
    access = _access(
        source_registry_id="openbb:yfinance",
        route_id="route-yfinance",
        grant_hash="a" * 64,
        store=store,
        resolver=resolver,
    )

    result = await service.execute(_request(), access=access)

    assert result.coverage.status.value == "complete"
    assert denied_primary.requests == []
    assert len(allowed_fallback.requests) == 1
    from app.services.market_data.query_service import _policy_descriptor_hash

    static_policy_hash = _policy_descriptor_hash(
        service._source_policies.resolve("market-default-v1")
    )
    assert allowed_fallback.requests[0].policy_descriptor_hash == static_policy_hash
    assert allowed_fallback.requests[0].policy_descriptor_hash != "a" * 64
    assert allowed_fallback.requests[0].access_grant_descriptor_hash == "a" * 64
    assert store.read_source_filters
    assert all(item == frozenset({"openbb:yfinance"}) for item in store.read_source_filters)
    assert store.calendar_source_filters
    assert all(
        item == frozenset({"openbb:yfinance"}) for item in store.calendar_source_filters
    )
    assert len(store.persisted_source_authorizations) == 1
    persisted_authorization = store.persisted_source_authorizations[0]
    assert persisted_authorization is not None
    assert persisted_authorization.source_registry_id == "openbb:yfinance"
    assert persisted_authorization.decision == "ALLOW"
    assert access.authorizer.read_entitlement_checks == 1
    assert access.authorizer.policy_authorizations == [("route-akshare", "route-yfinance")]
    assert access.authorizer.local_read_counts_at_authorization == [0]
    assert access.authorizer.write_reauthorizations == [("route-yfinance", persisted_authorization)]


@pytest.mark.asyncio
async def test_post_fetch_access_change_rejects_the_receipt_before_persistence() -> None:
    """A provider response cannot write when its in-flight grant has changed."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    )
    resolver = service._resolver
    assert isinstance(resolver, _Resolver)
    access = _access(
        source_registry_id="akshare",
        route_id="route-akshare",
        grant_hash="a" * 64,
        store=store,
        resolver=resolver,
        write_authorization=MarketDataAuthorizationError("MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"),
    )

    with pytest.raises(MarketDataAuthorizationError) as rejected:
        await service.execute(_request(), access=access)

    assert rejected.value.code == "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"
    assert len(provider.requests) == 1
    assert access.authorizer.write_reauthorizations
    assert store.persisted == []


@pytest.mark.asyncio
async def test_online_execution_requires_authenticated_access_before_local_or_provider_work() -> None:
    """The service cannot be used as a direct unaudited online importer."""
    from app.services.market_data.query_service import MarketDataQueryServiceError

    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    )

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await service.execute_without_access(_request())

    assert rejected.value.code == "MARKET_DATA_ACCESS_REQUIRED"
    assert service._resolver.requests == []
    assert store.read_cutoffs == []
    assert provider.requests == []
    assert store.persisted == []


@pytest.mark.asyncio
async def test_cursor_rejects_changed_source_grant_before_any_local_data_read() -> None:
    """A cursor cannot replay local facts after the current source decision changes."""
    first_request = _request(page_size=1)
    context = _context(first_request)
    store = _Store(
        calendar=_calendar(),
        revisions=[_revision(_at(hour)) for hour in (9, 10, 11)],
    )
    provider = _Provider(_provider_result())
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    )
    resolver = service._resolver
    assert isinstance(resolver, _Resolver)
    first_access = _access(
        source_registry_id="akshare",
        route_id="route-akshare",
        grant_hash="a" * 64,
        store=store,
        resolver=resolver,
    )
    first = await service.execute(first_request, access=first_access)
    assert first.next_cursor is not None
    reads_before = len(store.read_cutoffs)

    changed_access = _access(
        source_registry_id="akshare",
        route_id="route-akshare",
        grant_hash="b" * 64,
        store=store,
        resolver=resolver,
    )
    from app.services.market_data.query_service import MarketDataQueryServiceError

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await service.execute(
            _request(page_size=1, cursor=first.next_cursor),
            access=changed_access,
        )

    assert rejected.value.code == "CURSOR_ACCESS_GRANT_MISMATCH"
    assert len(store.read_cutoffs) == reads_before
    assert provider.requests == []


@pytest.mark.asyncio
async def test_local_only_never_requests_provider_when_coverage_is_incomplete() -> None:
    """Local-only mode returns a typed gap instead of making a hidden online call."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request(mode="local_only"))

    assert result.coverage.status.value == "incomplete"
    assert provider.requests == []
    assert result.fetches == ()


@pytest.mark.asyncio
async def test_response_excludes_legacy_pass_placeholders_but_coverage_retains_rejection() -> None:
    """A diagnostics-only legacy row must never escape through the product result."""
    request = _request(mode="local_only")
    context = _context(request)
    rejected = LocalObservationRevision(
        revision_id="legacy-pass-placeholder",
        source_snapshot_id="source-legacy",
        event_at=_at(10),
        available_at=_at(12),
        committed_at=_at(12),
        visible_at=_at(12),
        visibility_sequence=10,
        revision_number=1,
        quality=ObservationQuality.PASS,
        fields=MappingProxyType({"close": "--"}),
    )
    store = _Store(
        calendar=_calendar(),
        revisions=[_revision(_at(9)), rejected, _revision(_at(11))],
    )
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "incomplete"
    assert result.coverage.rejection_counts == {"missing_required_fields": 1}
    assert [item.revision_id for item in result.observations] == [
        "revision-9-10.0",
        "revision-11-10.0",
    ]
    assert store.read_modes == [True, False]
    assert provider.requests == []


@pytest.mark.asyncio
async def test_known_empty_calendar_window_does_not_trigger_a_provider_fetch() -> None:
    """A declared grid with no event in this window is complete local evidence."""
    empty_calendar = CalendarSnapshot(
        calendar_id="CN-SSE",
        calendar_version="2026.09",
        timezone_name="Asia/Shanghai",
        coverage_window=TimeWindow(start_at=_at(9), end_at=_at(12)),
        event_keys=(),
        status=CalendarStatus.KNOWN,
    )
    store = _Store(calendar=empty_calendar, revisions=[])
    provider = _Provider(_provider_result())

    result = await _service(
        context=_context(),
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request())

    assert result.coverage.status.value == "complete"
    assert result.observations == ()
    assert provider.requests == []


@pytest.mark.asyncio
async def test_mismatched_provider_receipt_is_not_persisted_and_next_route_can_fill_gap() -> None:
    """A provider cannot substitute another registered source into a policy route."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    mismatched = _Provider(_provider_result(provider_id="openbb:yfinance"))
    approved = _Provider(_provider_result(provider_id="akshare"))

    result = await _service(
        context=context,
        store=store,
        provider_routes=(
            _route(mismatched, expected="akshare", request_provider="akshare"),
            _route(approved, expected="akshare", request_provider="akshare-fallback"),
        ),
    ).execute(_request())

    assert result.coverage.status.value == "complete"
    assert len(store.persisted) == 1
    assert store.persisted[0][1].provider_id == "akshare"
    assert [warning.code for warning in result.warnings] == ["PROVIDER_RECEIPT_MISMATCH"]


@pytest.mark.asyncio
async def test_unknown_calendar_triggers_one_bounded_fetch_but_never_claims_complete() -> None:
    """Fetching observations cannot turn missing calendar evidence into completion."""
    context = _context()
    store = _Store(calendar=_calendar(known=False), revisions=[])
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request())

    assert len(provider.requests) == 1
    assert result.coverage.status.value == "unknown_calendar"
    assert [warning.code for warning in result.warnings] == []


@pytest.mark.asyncio
async def test_online_fetch_switch_reports_disabled_without_touching_provider() -> None:
    """A deployment gate prevents live fetches while preserving inspected local state."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
        allow_online_fetch=False,
    ).execute(_request())

    assert provider.requests == []
    assert result.coverage.status.value == "incomplete"
    assert [warning.code for warning in result.warnings] == ["ONLINE_FETCH_DISABLED"]


@pytest.mark.asyncio
async def test_strict_query_uses_the_supplied_knowledge_cutoff_for_every_local_read() -> None:
    """Research/strategy callers cannot accidentally read facts learned after the cutoff."""
    cutoff = _at(12)
    request = _request(mode="local_only", knowledge_cutoff=cutoff)
    context = _context(request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(9))])
    provider = _Provider(_provider_result())

    await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(request)

    assert store.read_cutoffs
    assert set(store.read_cutoffs) == {cutoff}


@pytest.mark.asyncio
async def test_strict_query_does_not_fetch_facts_after_its_fixed_cutoff() -> None:
    """A research cutoff turns online filling into a typed local-only outcome."""
    cutoff = _at(12)
    request = _request(mode="local_first", knowledge_cutoff=cutoff)
    context = _context(request)
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(request)

    assert provider.requests == []
    assert result.coverage.status.value == "incomplete"
    assert result.historical_status == "HISTORICAL_COVERAGE_UNAVAILABLE"
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_strict_query_returns_unknown_calendar_without_a_provider_call() -> None:
    """A frozen view retains unknown calendar evidence instead of trying a live fill."""
    cutoff = _at(12)
    request = _request(mode="local_first", knowledge_cutoff=cutoff)
    context = _context(request)
    store = _Store(calendar=_calendar(known=False), revisions=[])
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "unknown_calendar"
    assert result.historical_status == "unknown_calendar"
    assert provider.requests == []
    assert store.persisted == []


@pytest.mark.asyncio
async def test_strict_refresh_is_rejected_before_resolver_store_or_provider_work() -> None:
    """Interactive refresh cannot mutate a strict historical visibility anchor."""
    from app.services.market_data.query_service import MarketDataQueryServiceError

    request = _request(mode="refresh", knowledge_cutoff=_at(12))
    context = _context(request)
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await service.execute(request)

    assert rejected.value.code == "STRICT_FETCH_FORBIDDEN"
    assert service._resolver.requests == []
    assert store.read_cutoffs == []
    assert store.persisted == []
    assert provider.requests == []


@pytest.mark.asyncio
async def test_mismatched_receipt_request_is_rejected_before_persistence_and_fallback() -> None:
    """A valid-looking receipt cannot be replayed from a different provider request."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    mismatched = _Provider(_provider_result(), bind_request=False)
    approved = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(mismatched), _route(approved, request_provider="akshare-fallback")),
    ).execute(_request())

    assert len(mismatched.requests) == 1
    assert len(approved.requests) == 1
    assert len(store.persisted) == 1
    assert store.persisted[0][1].request == approved.requests[0]
    assert [warning.code for warning in result.warnings] == ["PROVIDER_REQUEST_MISMATCH"]


@pytest.mark.asyncio
async def test_invalid_cursor_is_rejected_before_a_provider_or_store_write() -> None:
    """Malformed pagination input cannot create a hidden online cache side effect."""
    from app.services.market_data.query_service import MarketDataQueryServiceError

    context = _context()
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())

    with pytest.raises(MarketDataQueryServiceError) as invalid:
        await _service(
            context=context,
            store=store,
            provider_routes=(_route(provider),),
        ).execute(_request(cursor="not-a-valid-cursor"))

    assert invalid.value.code == "CURSOR_INVALID"
    assert provider.requests == []
    assert store.persisted == []


@pytest.mark.asyncio
async def test_tampered_signed_cursor_is_rejected_before_local_or_provider_work() -> None:
    """Changing an issued cursor cannot alter its frozen local replay boundary."""
    first_request = _request(page_size=1)
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    payload = _cursor_payload(first.next_cursor)
    anchor = payload["visibility_anchor"]
    assert isinstance(anchor, dict)
    anchor["max_visibility_sequence"] = 0
    tampered_cursor = _cursor_with_payload(first.next_cursor, payload)
    reads_before = len(store.read_cutoffs)
    resolver_requests_before = len(service._resolver.requests)

    from app.services.market_data.query_service import MarketDataQueryServiceError

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await service.execute(_request(page_size=1, cursor=tampered_cursor))

    assert rejected.value.code == "CURSOR_SIGNATURE_INVALID"
    assert len(store.read_cutoffs) == reads_before
    assert len(service._resolver.requests) == resolver_requests_before
    assert provider.requests == []
    assert store.persisted == []


@pytest.mark.asyncio
async def test_cursor_binds_complete_visibility_anchor_and_expires_without_local_work() -> None:
    """A page token has both anchor coordinates plus a finite immutable lifetime."""
    from app.services.market_data.query_service import MarketDataQueryServiceError

    first_request = _request(page_size=1)
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
        cursor_ttl=timedelta(minutes=1),
    )

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    payload = _cursor_payload(first.next_cursor)
    assert payload["version"] == 3
    assert payload["visibility_anchor"] == {
        "visible_at": _at(12).isoformat(),
        "max_visibility_sequence": 11,
    }
    assert payload["identity_visibility_anchor"] == payload["visibility_anchor"]
    assert payload["issued_at"] == _at(12).isoformat()
    assert payload["expires_at"] == _at(12, 1).isoformat()
    assert isinstance(payload["policy_descriptor_hash"], str)
    assert payload["access_grant_descriptor_hash"] == "f" * 64
    assert "principal_scope" not in payload
    assert "tenant_scope" not in payload
    assert "entitlement_revision" not in payload
    for field_name in (
        "principal_scope_sha256",
        "tenant_scope_sha256",
        "entitlement_revision_sha256",
    ):
        assert isinstance(payload[field_name], str)
        assert len(payload[field_name]) == 64

    reads_before = len(store.read_cutoffs)
    resolver_requests_before = len(service._resolver.requests)
    service._clock = lambda: _at(12, 1)
    with pytest.raises(MarketDataQueryServiceError) as expired:
        await service.execute(_request(page_size=1, cursor=first.next_cursor))

    assert expired.value.code == "CURSOR_EXPIRED"
    assert len(store.read_cutoffs) == reads_before
    assert len(service._resolver.requests) == resolver_requests_before
    assert provider.requests == []


@pytest.mark.asyncio
async def test_cursor_rejects_cross_principal_replay_before_resolver_or_store_work() -> None:
    """The access-binding seam prevents a signed token crossing principals or tenants."""
    from app.services.market_data.query_service import (
        MarketDataCursorBinding,
        MarketDataQueryServiceError,
    )

    first_request = _request(page_size=1, mode="local_only")
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))
    owner_binding = MarketDataCursorBinding(
        principal_scope="principal-a",
        tenant_scope="tenant-a",
        entitlement_revision="entitlement-v1",
    )
    first = await service.execute(first_request, cursor_binding=owner_binding)
    assert first.next_cursor is not None
    reads_before = len(store.read_cutoffs)
    resolver_requests_before = len(service._resolver.requests)

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await service.execute_without_access(
            _request(page_size=1, mode="local_only", cursor=first.next_cursor),
            cursor_binding=MarketDataCursorBinding(
                principal_scope="principal-b",
                tenant_scope="tenant-a",
                entitlement_revision="entitlement-v1",
            ),
        )

    assert rejected.value.code == "CURSOR_PRINCIPAL_MISMATCH"
    assert len(store.read_cutoffs) == reads_before
    assert len(service._resolver.requests) == resolver_requests_before
    assert provider.requests == []


@pytest.mark.asyncio
async def test_cursor_hashes_long_unicode_access_scopes_without_exceeding_transport_limit() -> None:
    """Access binding remains exact even when its raw values cannot fit in a token."""
    from app.services.market_data.query_service import MarketDataCursorBinding

    first_request = _request(page_size=1, mode="local_only")
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))
    binding = MarketDataCursorBinding(
        principal_scope="用户" * 128,
        tenant_scope="租户" * 128,
        entitlement_revision="e" * 128,
    )

    first = await service.execute_without_access(first_request, cursor_binding=binding)

    assert first.next_cursor is not None
    assert len(first.next_cursor) <= 2048
    payload = _cursor_payload(first.next_cursor)
    assert payload["principal_scope_sha256"] != binding.principal_scope
    assert payload["tenant_scope_sha256"] != binding.tenant_scope
    second = await service.execute_without_access(
        _request(page_size=1, mode="local_only", cursor=first.next_cursor),
        cursor_binding=binding,
    )
    assert [item.event_at for item in second.observations] == [_at(10)]


def test_policy_descriptor_hash_is_independent_of_cursor_transport_size() -> None:
    """The six reviewed default routes fit through a fixed-size hash field."""
    from app.api.data.queries import _default_source_policy_registry
    from app.services.market_data.query_service import _policy_descriptor_hash

    policy = _default_source_policy_registry("", ()).resolve("market-default-v1")

    assert len(_policy_descriptor_hash(policy)) == 64


@pytest.mark.asyncio
async def test_signed_cursor_rejects_a_different_hmac_key_before_local_or_provider_work() -> None:
    """A token from another deployment key cannot be replayed after key rotation."""
    first_request = _request(page_size=1)
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    issuing_service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    )
    first = await issuing_service.execute(first_request)
    assert first.next_cursor is not None
    verifying_service = _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
        cursor_signing_key=_OTHER_CURSOR_SIGNING_KEY,
    )
    reads_before = len(store.read_cutoffs)

    from app.services.market_data.query_service import MarketDataQueryServiceError

    with pytest.raises(MarketDataQueryServiceError) as rejected:
        await verifying_service.execute(_request(page_size=1, cursor=first.next_cursor))

    assert rejected.value.code == "CURSOR_SIGNATURE_INVALID"
    assert len(store.read_cutoffs) == reads_before
    assert verifying_service._resolver.requests == []
    assert provider.requests == []
    assert store.persisted == []


@pytest.mark.asyncio
async def test_strict_cursor_excludes_a_later_receipt_with_the_same_visible_at() -> None:
    """A strict continuation uses both anchor coordinates for same-time receipts."""
    first_request = _request(page_size=1, knowledge_cutoff=_at(12))
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 11)])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))
    resolver = service._resolver

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    assert first.visibility_anchor == MarketDataVisibilityAnchor(
        visible_at=_at(12),
        max_visibility_sequence=11,
    )
    store.revisions.append(
        LocalObservationRevision(
            revision_id="revision-later-correction",
            source_snapshot_id="snapshot-later",
            event_at=_at(10),
            available_at=_at(12),
            committed_at=_at(12),
            visible_at=_at(12),
            visibility_sequence=12,
            revision_number=1,
            quality=ObservationQuality.PASS,
            fields=MappingProxyType({"close": 99.0}),
        )
    )

    second = await service.execute(
        _request(page_size=1, knowledge_cutoff=_at(12), cursor=first.next_cursor)
    )

    assert [item.event_at for item in second.observations] == [_at(11)]
    assert second.observations[0].fields["close"] == 10.0
    assert second.visibility_anchor == first.visibility_anchor
    assert second.historical_status == "HISTORICAL_COVERAGE_UNAVAILABLE"
    assert provider.requests == []
    assert [warning.code for warning in second.warnings] == ["CURSOR_FROZEN_LOCAL_ONLY"]
    assert set(store.read_cutoffs) == {_at(12)}
    assert resolver.identity_cutoffs == [_at(12), _at(12)]


@pytest.mark.asyncio
async def test_strict_cursor_excludes_later_sequence_below_a_future_cutoff() -> None:
    """A future historical cutoff cannot make a later receipt retroactively visible."""
    first_request = _request(page_size=1, knowledge_cutoff=_at(13))
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 11)])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    assert first.visibility_anchor == MarketDataVisibilityAnchor(
        visible_at=_at(13),
        max_visibility_sequence=11,
    )
    store.revisions.append(
        LocalObservationRevision(
            revision_id="revision-later-but-earlier-time",
            source_snapshot_id="snapshot-later",
            event_at=_at(10),
            available_at=_at(12),
            committed_at=_at(12),
            # This remains below the caller's explicit future cutoff, but
            # its larger global sequence proves it was sealed after page one.
            visible_at=_at(12),
            visibility_sequence=12,
            revision_number=1,
            quality=ObservationQuality.PASS,
            fields=MappingProxyType({"close": 99.0}),
        )
    )

    second = await service.execute(
        _request(page_size=1, knowledge_cutoff=_at(13), cursor=first.next_cursor)
    )

    assert [item.event_at for item in second.observations] == [_at(11)]
    assert second.observations[0].fields["close"] == 10.0
    assert second.visibility_anchor == first.visibility_anchor
    assert provider.requests == []


@pytest.mark.asyncio
async def test_first_and_continuation_pages_share_one_identity_pit_boundary() -> None:
    """A current identity published after cutoff cannot change a cursor's context."""
    first_request = _request(page_size=1)
    cutoff_context = _context(first_request)
    current_query = ResolvedMarketDataQuery.from_request(
        first_request,
        canonical_id=CANONICAL_ID,
        dataset_code=DATASET_CODE,
        instrument_metadata_version="stock-v2",
    )
    current_identity = cutoff_context.identity.identity.model_copy(
        update={"metadata_version": "stock-v2"}
    )
    current_context = replace(
        cutoff_context,
        query=current_query,
        identity=replace(
            cutoff_context.identity,
            metadata_version="stock-v2",
            identity=current_identity,
        ),
        coverage_identity=replace(
            cutoff_context.coverage_identity,
            instrument_metadata_version="stock-v2",
        ),
    )
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    service = _service(
        context=cutoff_context,
        store=store,
        provider_routes=(_route(provider),),
    )
    resolver = _CurrentIdentityResolver(
        current_context=current_context,
        cutoff_context=cutoff_context,
    )
    service._resolver = resolver

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    second = await service.execute(_request(page_size=1, cursor=first.next_cursor))

    assert [item.event_at for item in second.observations] == [_at(10)]
    assert first.context.query.instrument_metadata_version == "stock-v1"
    assert resolver.identity_cutoffs == [_at(12), _at(12)]


@pytest.mark.asyncio
async def test_cursor_keeps_identity_cutoff_when_current_fetch_advances_observation_cutoff() -> (
    None
):
    """A provider receipt cannot move a continuation's identity PIT boundary."""
    first_request = _request(page_size=1)
    cutoff_context = _context(first_request)
    current_query = ResolvedMarketDataQuery.from_request(
        first_request,
        canonical_id=CANONICAL_ID,
        dataset_code=DATASET_CODE,
        instrument_metadata_version="stock-v2",
    )
    current_identity = cutoff_context.identity.identity.model_copy(
        update={"metadata_version": "stock-v2"}
    )
    current_context = replace(
        cutoff_context,
        query=current_query,
        identity=replace(
            cutoff_context.identity,
            metadata_version="stock-v2",
            identity=current_identity,
        ),
        coverage_identity=replace(
            cutoff_context.coverage_identity,
            instrument_metadata_version="stock-v2",
        ),
    )
    store = _Store(calendar=_calendar(), revisions=[])
    provider = _Provider(_provider_result())
    service = _service(
        context=cutoff_context,
        store=store,
        provider_routes=(_route(provider),),
    )
    resolver = _CurrentIdentityResolver(
        current_context=current_context,
        cutoff_context=cutoff_context,
    )
    service._resolver = resolver
    # A continuation must retain its identity boundary while its first-page
    # provider receipt advances the observation cutoff.  Keep the synthetic
    # times inside the production cursor TTL so this remains a PIT test rather
    # than accidentally exercising expiry.
    clock_values = iter((_at(12), _at(12, 1), _at(12, 2)))
    service._clock = lambda: next(clock_values)

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    second = await service.execute(_request(page_size=1, cursor=first.next_cursor))

    assert first.knowledge_cutoff == _at(12, 1)
    assert first.identity_knowledge_cutoff == _at(12)
    assert second.knowledge_cutoff == _at(12, 1)
    assert second.identity_knowledge_cutoff == _at(12)
    assert [item.event_at for item in second.observations] == [_at(10)]
    assert resolver.identity_cutoffs == [_at(12), _at(12)]


@pytest.mark.asyncio
async def test_inactive_provider_is_rejected_before_external_fetch() -> None:
    """A retired source policy route cannot emit a network request before store validation."""
    context = _context()
    store = _Store(
        calendar=_calendar(),
        revisions=[],
        inactive_provider_ids=frozenset({"akshare"}),
    )
    provider = _Provider(_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request())

    assert provider.requests == []
    assert store.authorization_checks == ["akshare"]
    assert [warning.code for warning in result.warnings] == ["PROVIDER_INACTIVE"]


@pytest.mark.asyncio
async def test_refresh_discloses_when_only_old_local_coverage_exists() -> None:
    """Refresh cannot call cached historical coverage fresh when its receipt has no rows."""
    context = _context()
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result(events=()))

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_route(provider),),
    ).execute(_request(mode="refresh"))

    assert len(provider.requests) == 1
    assert result.coverage.status.value == "complete"
    assert result.refresh_status == "fresh_incomplete"
    assert [warning.code for warning in result.warnings] == ["REFRESH_FRESHNESS_INCOMPLETE"]


@pytest.mark.asyncio
async def test_recent_local_quote_snapshot_never_reads_a_bar_calendar_or_provider() -> None:
    """A current exact quote is local-first complete by freshness, not by bars."""
    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(
        revisions=[
            LocalObservationRevision(
                revision_id="snapshot-local",
                source_snapshot_id="source-local",
                event_at=_at(12),
                available_at=_at(12),
                committed_at=_at(12),
                visible_at=_at(12),
                visibility_sequence=12,
                revision_number=1,
                quality=ObservationQuality.PASS,
                fields=MappingProxyType({"price": 10.5}),
            )
        ]
    )
    provider = _Provider(_snapshot_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "complete"
    assert [item.fields for item in result.observations] == [{"price": 10.5}]
    assert store.calendar_reads == 0
    assert provider.requests == []


@pytest.mark.asyncio
async def test_quote_response_hides_stale_local_snapshots_from_the_display() -> None:
    """Coverage and returned quote rows must agree about which value is current."""
    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(
        revisions=[
            LocalObservationRevision(
                revision_id="snapshot-stale",
                source_snapshot_id="source-stale",
                event_at=_at(11),
                available_at=_at(11),
                committed_at=_at(11),
                visible_at=_at(11),
                visibility_sequence=11,
                revision_number=1,
                quality=ObservationQuality.PASS,
                fields=MappingProxyType({"price": 9.5}),
            ),
            LocalObservationRevision(
                revision_id="snapshot-current",
                source_snapshot_id="source-current",
                event_at=_at(12),
                available_at=_at(12),
                committed_at=_at(12),
                visible_at=_at(12),
                visibility_sequence=12,
                revision_number=1,
                quality=ObservationQuality.PASS,
                fields=MappingProxyType({"price": 10.5}),
            ),
        ]
    )
    provider = _Provider(_snapshot_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "complete"
    assert result.coverage.rejection_counts == {"stale": 1}
    assert [item.revision_id for item in result.observations] == ["snapshot-current"]
    assert provider.requests == []
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_missing_quote_snapshot_is_persisted_then_reread_without_a_calendar() -> None:
    """A quote miss follows the same durable receipt and local reread invariant as bars."""
    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(revisions=[])
    provider = _Provider(_snapshot_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "complete"
    assert [item.fields for item in result.observations] == [{"price": 10.5}]
    assert len(store.persisted) == 1
    assert store.persisted[0][1].request == provider.requests[0]
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_stale_quote_snapshot_fetches_one_current_replacement() -> None:
    """A stale quote cannot suppress the bounded local-first refresh."""
    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(
        revisions=[
            LocalObservationRevision(
                revision_id="snapshot-stale",
                source_snapshot_id="source-stale",
                event_at=_at(11),
                available_at=_at(11),
                committed_at=_at(11),
                visible_at=_at(11),
                visibility_sequence=11,
                revision_number=1,
                quality=ObservationQuality.PASS,
                fields=MappingProxyType({"price": 9.5}),
            )
        ]
    )
    provider = _Provider(_snapshot_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "complete"
    assert len(provider.requests) == 1
    assert provider.requests[0].data_kind == "quote_snapshot"
    assert provider.requests[0].frequency == "snapshot"
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_quote_snapshot_uses_its_injected_product_freshness_policy() -> None:
    """A product policy, rather than a query-service constant, controls staleness."""
    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(
        revisions=[
            LocalObservationRevision(
                revision_id="snapshot-six-minutes-old",
                source_snapshot_id="source-six-minutes-old",
                event_at=_at(11, 54),
                available_at=_at(11, 54),
                committed_at=_at(11, 54),
                visible_at=_at(11, 54),
                visibility_sequence=11,
                revision_number=1,
                quality=ObservationQuality.PASS,
                fields=MappingProxyType({"price": 10.0}),
            )
        ]
    )
    provider = _Provider(_snapshot_provider_result())
    policies = SnapshotFreshnessPolicyRegistry(
        (
            SnapshotFreshnessPolicy(
                policy_id="test-stock-quote-five-minute-v1",
                dataset_code="market.quote_snapshot",
                asset_types=frozenset({"stock"}),
                source_policy_ids=frozenset({"market-default-v1"}),
                max_age=timedelta(minutes=5),
            ),
        )
    )

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
        snapshot_freshness_policies=policies,
    ).execute(request)

    assert result.coverage.status.value == "complete"
    assert len(provider.requests) == 1
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_quote_refresh_uses_the_same_injected_freshness_policy() -> None:
    """Refresh evidence cannot use a looser default SLA than the display read."""
    request = _snapshot_request(mode="refresh")
    context = _snapshot_context(request)
    store = _SnapshotStore(revisions=[])
    provider = _Provider(_snapshot_provider_result(event_at=_at(11, 54)))
    policies = SnapshotFreshnessPolicyRegistry(
        (
            SnapshotFreshnessPolicy(
                policy_id="test-stock-quote-five-minute-v1",
                dataset_code="market.quote_snapshot",
                asset_types=frozenset({"stock"}),
                source_policy_ids=frozenset({"market-default-v1"}),
                max_age=timedelta(minutes=5),
            ),
        )
    )

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
        snapshot_freshness_policies=policies,
    ).execute(request)

    assert result.coverage.status.value == "incomplete"
    assert result.observations == ()
    assert len(provider.requests) == 1
    assert result.refresh_status == "fresh_incomplete"
    assert [warning.code for warning in result.warnings] == ["REFRESH_FRESHNESS_INCOMPLETE"]
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_quote_snapshot_without_an_exact_product_policy_fails_before_local_read() -> None:
    """A quote cannot inherit another product's SLA or silently fetch online."""
    from app.services.market_data.query_service import MarketDataQueryServiceError

    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(revisions=[])
    provider = _Provider(_snapshot_provider_result())
    policies = SnapshotFreshnessPolicyRegistry(
        (
            SnapshotFreshnessPolicy(
                policy_id="test-fund-quote-v1",
                dataset_code="market.quote_snapshot",
                asset_types=frozenset({"fund"}),
                source_policy_ids=frozenset({"market-default-v1"}),
                max_age=timedelta(minutes=5),
            ),
        )
    )

    with pytest.raises(MarketDataQueryServiceError, match="SNAPSHOT_FRESHNESS_POLICY_UNAVAILABLE"):
        await _service(
            context=context,
            store=store,
            provider_routes=(_snapshot_route(provider),),
            snapshot_freshness_policies=policies,
        ).execute(request)

    assert store.read_cutoffs == []
    assert provider.requests == []
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_quote_snapshot_policy_must_match_the_versioned_source_policy() -> None:
    """Changing a source-policy ID cannot reuse an SLA from another policy version."""
    from app.services.market_data.query_service import MarketDataQueryServiceError

    request = _snapshot_request()
    context = _snapshot_context(request)
    store = _SnapshotStore(revisions=[])
    provider = _Provider(_snapshot_provider_result())
    policies = SnapshotFreshnessPolicyRegistry(
        (
            SnapshotFreshnessPolicy(
                policy_id="test-stock-other-source-v1",
                dataset_code="market.quote_snapshot",
                asset_types=frozenset({"stock"}),
                source_policy_ids=frozenset({"market-other-v1"}),
                max_age=timedelta(minutes=5),
            ),
        )
    )

    with pytest.raises(MarketDataQueryServiceError, match="SNAPSHOT_FRESHNESS_POLICY_UNAVAILABLE"):
        await _service(
            context=context,
            store=store,
            provider_routes=(_snapshot_route(provider),),
            snapshot_freshness_policies=policies,
        ).execute(request)

    assert store.read_cutoffs == []
    assert provider.requests == []
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_historical_quote_snapshot_miss_never_fetches_a_present_value() -> None:
    """A present quote must not be relabelled as evidence for a past time window."""
    request = _snapshot_request(start=_at(9), end=_at(10))
    context = _snapshot_context(request)
    store = _SnapshotStore(revisions=[])
    provider = _Provider(_snapshot_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "incomplete"
    assert provider.requests == []
    assert [warning.code for warning in result.warnings] == ["SNAPSHOT_HISTORICAL_FETCH_FORBIDDEN"]
    assert store.calendar_reads == 0


@pytest.mark.asyncio
async def test_quote_at_the_historical_freshness_boundary_never_fetches_a_present_value() -> None:
    """The half-open historical guard includes the exact freshness-floor endpoint."""
    request = _snapshot_request(start=_at(11, 44), end=_at(11, 45))
    context = _snapshot_context(request)
    store = _SnapshotStore(revisions=[])
    provider = _Provider(_snapshot_provider_result())

    result = await _service(
        context=context,
        store=store,
        provider_routes=(_snapshot_route(provider),),
    ).execute(request)

    assert result.coverage.status.value == "incomplete"
    assert result.observations == ()
    assert provider.requests == []
    assert [warning.code for warning in result.warnings] == ["SNAPSHOT_HISTORICAL_FETCH_FORBIDDEN"]
    assert store.calendar_reads == 0
