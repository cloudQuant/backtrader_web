"""Behavioral contracts for local-first market-data query orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any

import pytest

from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import (
    CalendarSnapshot,
    CalendarStatus,
    EventKey,
    ObservationQuality,
    QueryIdentity,
    TimeWindow,
)
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.snapshot_freshness import (
    SnapshotFreshnessPolicy,
    SnapshotFreshnessPolicyRegistry,
)
from app.services.market_data.store import LocalObservationRevision, PersistedProviderFetch

UTC = timezone.utc
DATASET_ID = "dataset-market-stock"
DATASET_CODE = "market.stock_daily"
CANONICAL_ID = "instrument:stock:CN-SSE:600000"
METADATA_VERSION = "stock-v1"
_CURSOR_SIGNING_KEY = "test-market-data-cursor-hmac-key-material-0000000000000000000001"
_OTHER_CURSOR_SIGNING_KEY = "test-market-data-cursor-hmac-key-material-0000000000000000000002"


def _at(hour: int, minute: int = 0, *, day: int = 8) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


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
        revision_number=1,
        quality=ObservationQuality.PASS,
        fields=MappingProxyType({"close": value}),
    )


class _Resolver:
    def __init__(self, context: ResolvedMarketDataQueryContext) -> None:
        self.context = context
        self.requests: list[MarketDataQueryRequest] = []
        self.identity_cutoffs: list[datetime | None] = []

    async def resolve(
        self,
        request: MarketDataQueryRequest,
        *,
        identity_knowledge_cutoff: datetime | None = None,
    ) -> ResolvedMarketDataQueryContext:
        self.requests.append(request)
        self.identity_cutoffs.append(identity_knowledge_cutoff)
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
    ) -> ResolvedMarketDataQueryContext:
        self.requests.append(request)
        self.identity_cutoffs.append(identity_knowledge_cutoff)
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
        self.read_modes: list[bool] = []
        self.authorization_checks: list[str] = []

    async def read_observation_revisions(
        self,
        _context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        include_unusable_for_coverage: bool = False,
    ) -> tuple[LocalObservationRevision, ...]:
        self.read_cutoffs.append(knowledge_cutoff)
        self.read_modes.append(include_unusable_for_coverage)
        return tuple(
            row
            for row in self.revisions
            if _context.query.start <= row.event_at < _context.query.end
            and row.available_at <= knowledge_cutoff
            and row.committed_at <= knowledge_cutoff
        )

    async def read_calendar_for_context(
        self,
        _context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
    ) -> CalendarSnapshot:
        assert knowledge_cutoff.tzinfo is not None
        return self.calendar

    async def ensure_provider_active(self, provider_id: str) -> None:
        from app.services.market_data.store import MarketDataStoreError

        self.authorization_checks.append(provider_id)
        if provider_id in self.inactive_provider_ids:
            raise MarketDataStoreError("PROVIDER_INACTIVE")

    async def persist_provider_result(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        *,
        received_at: datetime,
    ) -> PersistedProviderFetch:
        self.persisted.append((context, result))
        for item in result.observations:
            self.revisions.append(
                LocalObservationRevision(
                    revision_id=f"revision-network-{item.event_at.isoformat()}",
                    source_snapshot_id=f"snapshot-{result.provider_id}",
                    event_at=item.event_at,
                    available_at=received_at,
                    committed_at=received_at,
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
    ) -> CalendarSnapshot:
        del _context, knowledge_cutoff
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
    snapshot_freshness_policies: SnapshotFreshnessPolicyRegistry | None = None,
):
    from app.services.market_data.query_service import MarketDataQueryService
    from app.services.market_data.source_policy import (
        MarketDataSourcePolicy,
        MarketDataSourcePolicyRegistry,
    )

    return MarketDataQueryService(
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
    assert [warning.code for warning in result.warnings] == ["STRICT_ONLINE_FETCH_INELIGIBLE"]


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
    payload, signature = first.next_cursor.split(".")
    replacement = "A" if payload[0] != "A" else "B"
    tampered_cursor = f"{replacement}{payload[1:]}.{signature}"
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
async def test_cursor_freezes_the_local_snapshot_and_never_refetches() -> None:
    """The second page remains on the first page's receipt boundary after newer rows arrive."""
    first_request = _request(page_size=1)
    context = _context(first_request)
    store = _Store(calendar=_calendar(), revisions=[_revision(_at(hour)) for hour in (9, 10, 11)])
    provider = _Provider(_provider_result())
    service = _service(context=context, store=store, provider_routes=(_route(provider),))
    resolver = service._resolver

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    store.revisions.append(
        LocalObservationRevision(
            revision_id="revision-later-correction",
            source_snapshot_id="snapshot-later",
            event_at=_at(10),
            available_at=_at(13),
            committed_at=_at(13),
            revision_number=2,
            quality=ObservationQuality.PASS,
            fields=MappingProxyType({"close": 99.0}),
        )
    )

    second = await service.execute(_request(page_size=1, cursor=first.next_cursor))

    assert [item.event_at for item in second.observations] == [_at(10)]
    assert second.observations[0].fields["close"] == 10.0
    assert provider.requests == []
    assert [warning.code for warning in second.warnings] == ["CURSOR_FROZEN_LOCAL_ONLY"]
    assert set(store.read_cutoffs) == {_at(12)}
    assert resolver.identity_cutoffs == [_at(12), _at(12)]


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
    clock_values = iter((_at(12), _at(13)))
    service._clock = lambda: next(clock_values)

    first = await service.execute(first_request)
    assert first.next_cursor is not None
    second = await service.execute(_request(page_size=1, cursor=first.next_cursor))

    assert first.knowledge_cutoff == _at(13)
    assert first.identity_knowledge_cutoff == _at(12)
    assert second.knowledge_cutoff == _at(13)
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
