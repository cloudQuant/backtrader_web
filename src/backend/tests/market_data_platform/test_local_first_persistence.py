"""End-to-end persistence contracts for the local-first market-data path.

These tests use the real catalog, versioned identity materializer, calendar
importer, store, resolver, and query service.  The only double is a bounded
provider adapter so no test reaches AkShare or OpenBB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

import pytest
from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.queries import (
    get_market_data_capability_evaluation,
    get_market_data_query_service,
)
from app.db.database import async_session_maker, get_db
from app.main import app
from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import MdObservationRevision, MdSourceSnapshot
from app.models.permission import Role, user_roles
from app.models.user import User
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import (
    MarketDataCapabilitiesResponse,
    MarketDataQueryRequest,
)
from app.services.market_data.access import MarketDataAccessAuthorizer, MarketDataQueryAccess
from app.services.market_data.bootstrap import (
    CanonicalStorageSpec,
    MarketDataBootstrapSpec,
    MarketDataPlatformBootstrapper,
)
from app.services.market_data.calendar_importer import (
    MANIFEST_VERSION,
    MarketDataCalendarImporter,
)
from app.services.market_data.capability_ledger import MarketDataCapabilityEvaluation
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.identity import MarketDataIdentityResolver
from app.services.market_data.master_data import MarketDataIdentityWriter
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)
from app.services.market_data.query_resolution import MarketDataQueryResolver
from app.services.market_data.query_service import MarketDataQueryService
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)
from app.services.market_data.store import MarketDataStore

UTC: Final = timezone.utc
CANONICAL_ID: Final = "instrument:stock:CN-SSE:600000"
FUND_NAV_CANONICAL_ID: Final = "instrument:fund:CN-SZSE:159915"
WINDOW_START: Final = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW_END: Final = datetime(2026, 9, 3, tzinfo=UTC)
# Identity publication deliberately samples a post-commit real clock.  The
# local-first test query must therefore use a visibility cutoff safely after
# setup, even when the entire market-data suite takes longer than a minute.
RECEIPT_AT: Final = datetime.now(UTC) + timedelta(days=1)


class _RecordingProvider:
    """Return deterministic exact rows while recording every external fetch attempt."""

    def __init__(self) -> None:
        self.calls: list[MarketDataProviderRequest] = []

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        self.calls.append(request)
        rows = tuple(
            ProviderMarketObservation(
                event_at=event_at,
                available_at=event_at + timedelta(hours=6),
                fields={
                    field_name: {
                        "close": 10.0,
                        "nav": 1.2345,
                        "cumulative_nav": 1.4567,
                        "daily_growth_rate": 0.98,
                    }.get(field_name, 1000)
                    for field_name in request.required_fields
                },
            )
            for event_at in (WINDOW_START, WINDOW_START + timedelta(days=1))
        )
        return ProviderFetchResult(
            provider_id="akshare",
            source_revision=f"fixture-{len(self.calls)}",
            retrieved_at=RECEIPT_AT,
            observations=rows,
            raw_payload={
                "fixture": "local-first-persistence",
                "request_number": len(self.calls),
                "records": [
                    {
                        "event_at": row.event_at.isoformat(),
                        "fields": dict(row.fields),
                    }
                    for row in rows
                ],
            },
            request=request,
        )


class _RangeRecordingProvider:
    """Return only the exact requested fixture events and record every fetch."""

    def __init__(self) -> None:
        self.calls: list[MarketDataProviderRequest] = []

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        self.calls.append(request)
        rows = tuple(
            ProviderMarketObservation(
                event_at=event_at,
                available_at=event_at + timedelta(hours=6),
                fields={
                    field_name: {"close": 10.0}.get(field_name, 1000)
                    for field_name in request.required_fields
                },
            )
            for event_at in (WINDOW_START, WINDOW_START + timedelta(days=1))
            if request.start_at <= event_at < request.end_at
        )
        return ProviderFetchResult(
            provider_id="akshare",
            source_revision=f"range-fixture-{len(self.calls)}",
            retrieved_at=RECEIPT_AT,
            observations=rows,
            raw_payload={
                "fixture": "local-first-http-persistence",
                "request_number": len(self.calls),
                "records": [
                    {
                        "event_at": row.event_at.isoformat(),
                        "fields": dict(row.fields),
                    }
                    for row in rows
                ],
            },
            request=request,
        )


def _request(
    *,
    required_fields: list[str],
    mode: str = "local_first",
) -> MarketDataQueryRequest:
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "required_fields": required_fields,
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "mode": mode,
        }
    )


def _public_bars_payload(
    *,
    start: datetime,
    end: datetime,
    mode: str,
) -> dict[str, object]:
    """Return the exact public stock-realtime request used by the HTTP acceptance flow."""
    return {
        "identity": {"canonical_id": CANONICAL_ID},
        "family_id": "stock.realtime",
        "family_contract_version": "market-data-family-v1",
        "dataset_code": "market.bars",
        "data_kind": "bars",
        "frequency": "1d",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "required_fields": ["close"],
        "adjustment": "qfq",
        "price_basis": "close",
        "currency": "CNY",
        "unit": "share",
        "source_policy_id": "market-default-v1",
        "consistency": "display",
        "purpose": "display",
        "mode": mode,
    }


def _liquidity_request() -> MarketDataQueryRequest:
    """Build the public B1 stock-liquidity request bound to its daily grid."""
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "family_id": "stock.liquidity",
            "family_contract_version": "market-data-family-v1",
            "dataset_code": "market.liquidity",
            "data_kind": "reference_series",
            "frequency": "1d",
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "required_fields": ["volume", "turnover", "turnover_rate"],
            "adjustment": "unadjusted",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "mode": "local_first",
        }
    )


def _fund_nav_request() -> MarketDataQueryRequest:
    """Build the public ETF NAV contract with its own source semantics."""
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": FUND_NAV_CANONICAL_ID},
            "family_id": "fund.nav",
            "family_contract_version": "market-data-family-v1",
            "dataset_code": "market.fund_nav",
            "data_kind": "reference_series",
            "frequency": "1d",
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "required_fields": ["nav", "cumulative_nav", "daily_growth_rate"],
            "adjustment": "source_reported",
            "price_basis": "nav",
            "currency": "CNY",
            "unit": "fund_share",
            "source_policy_id": "market-default-v1",
            "mode": "local_first",
        }
    )


def _policy(
    provider: _RecordingProvider,
    *,
    data_kind: str = "bars",
    adjustment: str = "qfq",
    asset_type: str = "stock",
    market: str = "CN-SSE",
    price_basis: str = "close",
    unit: str = "share",
    route_id: str = "fixture-akshare-stock-v1",
    family_id: str | None = None,
    family_contract_version: str | None = None,
    product_types: frozenset[str] | None = None,
    fund_identity_kinds: frozenset[str] | None = None,
) -> MarketDataSourcePolicyRegistry:
    route = MarketDataProviderRoute(
        route_id=route_id,
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=frozenset({asset_type}),
        data_kinds=frozenset({data_kind}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({market}),
        adjustments=frozenset({adjustment}),
        price_bases=frozenset({price_basis}),
        currencies=frozenset({"CNY"}),
        units=frozenset({unit}),
        adapter=provider,
        family_id=family_id,
        family_contract_version=family_contract_version,
        product_types=product_types,
        fund_identity_kinds=fund_identity_kinds,
    )
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id="market-default-v1",
                allowed_purposes=frozenset({"display"}),
                routes=(route,),
            ),
        )
    )


def _service(
    session,
    provider: _RecordingProvider,
    *,
    now: datetime = RECEIPT_AT,
    source_policies: MarketDataSourcePolicyRegistry | None = None,
    allow_unbound_internal_requests: bool = True,
) -> MarketDataQueryService:
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(session),
            identities=MarketDataIdentityResolver(session),
            # Lower-level revision tests deliberately exercise a broad
            # internal field projection. HTTP acceptance keeps this disabled
            # so the public route preserves its family-binding requirement.
            allow_unbound_internal_requests=allow_unbound_internal_requests,
        ),
        store=MarketDataStore(session, clock=lambda: now),
        source_policies=source_policies or _policy(provider),
        allow_online_fetch=True,
        clock=lambda: now,
        cursor_signing_key="test-market-data-cursor-hmac-key-material-0000000000000000000001",
    )


async def _seed_authoritative_prerequisites(
    *,
    calendar_data_kind: str = "bars",
    identity: InstrumentIdentity | None = None,
    calendar_code: str = "CN-SSE",
    user_id: str | None = None,
) -> str:
    """Create only operator-owned prerequisites before a public query begins."""
    identity = identity or InstrumentIdentity.model_validate(
        {
            "asset_type": "stock",
            "identity_level": "ASSET",
            "canonical_id": CANONICAL_ID,
            "display_symbol": "600000",
            "name": "测试股票",
            "venue": "CN-SSE",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "EXCHANGE_SYMBOL",
            "identifier_value": "600000.SH",
            "product_type": "EQUITY",
            "metadata_version": "market-v1",
            "details": {"kind": "STOCK", "exchange_symbol": "600000.SH"},
        }
    )
    assert identity.venue == calendar_code
    calendar = {
        "manifest_version": MANIFEST_VERSION,
        "approval_reference": "CAB-197-E2E-001",
        "evidence_uri": f"file:///approved/calendars/{calendar_code}-2026-09.json",
        "evidence_content_hash": "a" * 64,
        "source_registry_id": "akshare",
        "calendar_code": calendar_code,
        "calendar_version": "2026.09",
        "timezone_name": "Asia/Shanghai",
        "coverage_start_at": WINDOW_START.isoformat(),
        "coverage_end_at": WINDOW_END.isoformat(),
        "events": [
            {
                "trading_date": "2026-09-01",
                "event_type": "session",
                "session_code": f"{calendar_data_kind}-daily-close",
                "is_trading_day": True,
                "event_start": WINDOW_START.isoformat(),
                "event_end": (WINDOW_START + timedelta(hours=6)).isoformat(),
                "coverage": {"data_kind": calendar_data_kind, "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
            {
                "trading_date": "2026-09-02",
                "event_type": "session",
                "session_code": f"{calendar_data_kind}-daily-close",
                "is_trading_day": True,
                "event_start": (WINDOW_START + timedelta(days=1)).isoformat(),
                "event_end": (WINDOW_START + timedelta(days=1, hours=6)).isoformat(),
                "coverage": {"data_kind": calendar_data_kind, "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
        ],
    }
    spec = MarketDataBootstrapSpec(
        storage=CanonicalStorageSpec.from_database_url("sqlite+aiosqlite://"),
    )
    async with async_session_maker() as session:
        await MarketDataPlatformBootstrapper(session).bootstrap(spec)
        await session.commit()

        if user_id is None:
            user = User(
                username="market-data-local-first-fixture",
                email="market-data-local-first-fixture@example.test",
                hashed_password="not-used",
                is_active=True,
            )
            session.add(user)
        else:
            user = await session.get(User, user_id)
            assert user is not None
        session.add(
            AssetDataSourceRegistry(
                source_id="akshare",
                asset_types=[identity.asset_type],
                jurisdictions=["CN"],
                license_status="APPROVED",
                allowed_uses=["DISPLAY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="market-data-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=UTC),
                enabled=True,
                updated_at=RECEIPT_AT,
            )
        )
        await session.flush()
        has_user_role = await session.scalar(
            select(user_roles.c.user_id).where(
                user_roles.c.user_id == user.id,
                user_roles.c.role == Role.USER.value,
            )
        )
        if has_user_role is None:
            await session.execute(user_roles.insert().values(user_id=user.id, role=Role.USER.value))
        seeded_user_id = str(user.id)
        await session.commit()

        identity_writer = MarketDataIdentityWriter(session)
        await identity_writer.persist_identity(
            identity,
            valid_from=datetime(2026, 8, 1, tzinfo=UTC),
        )
        await session.commit()
        await identity_writer.publish_staged()
        await MarketDataCalendarImporter(session).import_payload(
            payload=calendar,
            dry_run=False,
        )
        await session.commit()
        return seeded_user_id


async def _access_for_session(
    session,
    *,
    user_id: str,
    now: datetime,
) -> MarketDataQueryAccess:
    """Build a real current user/source-registry grant for a query execution."""
    user = await session.get(User, user_id)
    assert user is not None
    authorizer = MarketDataAccessAuthorizer(session, clock=lambda: now)
    principal = await authorizer.principal_for_user(user)
    return MarketDataQueryAccess(principal=principal, authorizer=authorizer)


@pytest.mark.asyncio
async def test_local_first_persists_once_then_reuses_complete_older_revision_without_network() -> (
    None
):
    """A completed cache serves later broad requests even after a narrower refresh revision."""
    user_id = await _seed_authoritative_prerequisites()
    provider = _RecordingProvider()

    async with async_session_maker() as first_session:
        first = await _service(first_session, provider, now=RECEIPT_AT).execute(
            _request(required_fields=["close", "volume"]),
            access=await _access_for_session(
                first_session,
                user_id=user_id,
                now=RECEIPT_AT,
            ),
        )
        await first_session.commit()

    async with async_session_maker() as narrow_refresh_session:
        narrow_refresh = await _service(
            narrow_refresh_session,
            provider,
            now=RECEIPT_AT + timedelta(microseconds=2),
        ).execute(
            _request(required_fields=["close"], mode="refresh"),
            access=await _access_for_session(
                narrow_refresh_session,
                user_id=user_id,
                now=RECEIPT_AT + timedelta(microseconds=2),
            ),
        )
        await narrow_refresh_session.commit()

    async with async_session_maker() as reused_session:
        reused = await _service(
            reused_session,
            provider,
            now=RECEIPT_AT + timedelta(microseconds=4),
        ).execute(
            _request(required_fields=["close", "volume"]),
            access=await _access_for_session(
                reused_session,
                user_id=user_id,
                now=RECEIPT_AT + timedelta(microseconds=4),
            ),
        )
        source_snapshot_count = await reused_session.scalar(
            select(func.count()).select_from(MdSourceSnapshot)
        )
        revision_count = await reused_session.scalar(
            select(func.count()).select_from(MdObservationRevision)
        )

    assert len(first.fetches) == 1
    assert len(narrow_refresh.fetches) == 1
    assert len(provider.calls) == 2
    assert reused.coverage.status.value == "complete"
    assert reused.fetches == ()
    assert len(reused.observations) == 2
    assert all({"close", "volume"} <= set(row.fields) for row in reused.observations)
    assert source_snapshot_count == 2
    assert revision_count == 4


@pytest.mark.asyncio
async def test_public_http_local_first_persists_exact_gap_then_independent_local_only_rereads(
    client: AsyncClient,
    auth_user: tuple[dict[str, str], dict[str, str]],
) -> None:
    """Exercise the public route, real Store, and fresh request sessions without network I/O.

    The narrow local result is seeded through the normal service so the first
    HTTP read proves a completed local cache is not fetched again. The wider
    HTTP request then fills only its missing event with a deterministic
    provider fixture. Its following HTTP ``local_only`` request must enter a
    new FastAPI database session and return the persisted revisions, rather
    than reusing the prior provider result in memory.
    """
    user_data, auth_headers = auth_user
    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(User.username == user_data["username"]))
        ).scalar_one()
        authenticated_user_id = str(user.id)

    user_id = await _seed_authoritative_prerequisites(user_id=authenticated_user_id)
    provider = _RangeRecordingProvider()
    route_id = "fixture-http-stock-realtime-v1"
    source_policies = _policy(
        provider,
        route_id=route_id,
        family_id="stock.realtime",
        family_contract_version="market-data-family-v1",
    )

    async with async_session_maker() as seed_session:
        seed_service = _service(
            seed_session,
            provider,
            now=RECEIPT_AT,
            source_policies=source_policies,
            allow_unbound_internal_requests=False,
        )
        seeded = await seed_service.execute(
            MarketDataQueryRequest.model_validate(
                _public_bars_payload(
                    start=WINDOW_START,
                    end=WINDOW_START + timedelta(days=1),
                    mode="local_first",
                )
            ),
            access=await _access_for_session(
                seed_session,
                user_id=user_id,
                now=RECEIPT_AT,
            ),
        )
        await seed_session.commit()

    assert seeded.coverage.status.value == "complete"
    assert len(seeded.fetches) == 1
    assert len(provider.calls) == 1
    assert provider.calls[0].route_id == route_id
    assert provider.calls[0].family_id == "stock.realtime"
    assert provider.calls[0].family_contract_version == "market-data-family-v1"

    capabilities = MarketDataCapabilityEvaluation(
        response=MarketDataCapabilitiesResponse(
            query_v2_enabled=True,
            online_fetch_enabled=True,
            research_cache_fill_enabled=False,
            research_backtest_bridge_enabled=False,
        ),
        effective_source_policies=source_policies,
        effective_route_ids=frozenset({route_id}),
    )
    # Publication allocation deliberately advances the visibility instant
    # beyond receipt time. Give each HTTP request a new deterministic clock
    # value so the final independent local-only read can see the prior
    # request's post-commit publication receipt.
    request_times = iter(
        (
            RECEIPT_AT + timedelta(microseconds=2),
            RECEIPT_AT + timedelta(microseconds=4),
            RECEIPT_AT + timedelta(microseconds=6),
        )
    )

    async def request_db():
        async with async_session_maker() as session:
            yield session

    async def request_service(
        db: AsyncSession = Depends(get_db),
    ) -> MarketDataQueryService:
        return _service(
            db,
            provider,
            now=next(request_times),
            source_policies=source_policies,
            allow_unbound_internal_requests=False,
        )

    original_dependency_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = request_db
    app.dependency_overrides[get_market_data_capability_evaluation] = lambda: capabilities
    app.dependency_overrides[get_market_data_query_service] = request_service
    try:
        local_hit = await client.post(
            "/api/v1/data/queries",
            json=_public_bars_payload(
                start=WINDOW_START,
                end=WINDOW_START + timedelta(days=1),
                mode="local_only",
            ),
            headers=auth_headers,
        )
        assert local_hit.status_code == 200, local_hit.text
        local_hit_body = local_hit.json()
        assert local_hit_body["coverage"]["status"] == "complete"
        assert local_hit_body["fetches"] == []
        assert len(local_hit_body["observations"]) == 1
        assert len(provider.calls) == 1

        filled = await client.post(
            "/api/v1/data/queries",
            json=_public_bars_payload(
                start=WINDOW_START,
                end=WINDOW_END,
                mode="local_first",
            ),
            headers=auth_headers,
        )
        assert filled.status_code == 200, filled.text
        filled_body = filled.json()
        assert filled_body["coverage"]["status"] == "complete"
        assert len(filled_body["fetches"]) == 1
        assert len(provider.calls) == 2
        fill_receipt = filled_body["fetches"][0]
        assert fill_receipt["route_id"] == route_id
        assert fill_receipt["provider_id"] == "akshare"
        assert fill_receipt["passing_observation_count"] == 1
        assert fill_receipt["failed_observation_count"] == 0
        assert len(fill_receipt["observation_revision_ids"]) == 1
        filled_provider_request = provider.calls[1]
        assert filled_provider_request.route_id == route_id
        assert filled_provider_request.family_id == "stock.realtime"
        assert filled_provider_request.family_contract_version == "market-data-family-v1"
        assert filled_provider_request.start_at == WINDOW_START + timedelta(days=1)
        assert filled_provider_request.end_at == WINDOW_END
        assert filled_provider_request.required_fields == frozenset({"close"})
        filled_pairs = {
            (observation["revision_id"], observation["source_snapshot_id"])
            for observation in filled_body["observations"]
        }
        assert len(filled_pairs) == 2
        assert set(fill_receipt["observation_revision_ids"]) <= {
            revision_id for revision_id, _snapshot_id in filled_pairs
        }
        assert fill_receipt["source_snapshot_id"] in {
            snapshot_id for _revision_id, snapshot_id in filled_pairs
        }

        reread = await client.post(
            "/api/v1/data/queries",
            json=_public_bars_payload(
                start=WINDOW_START,
                end=WINDOW_END,
                mode="local_only",
            ),
            headers=auth_headers,
        )
        assert reread.status_code == 200, reread.text
        reread_body = reread.json()
        assert reread_body["coverage"]["status"] == "complete"
        assert reread_body["fetches"] == []
        assert len(provider.calls) == 2
        reread_pairs = {
            (observation["revision_id"], observation["source_snapshot_id"])
            for observation in reread_body["observations"]
        }
        assert reread_pairs == filled_pairs
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_dependency_overrides)


@pytest.mark.asyncio
async def test_imported_reference_series_grid_supports_local_first_reread_without_network() -> None:
    """A published B1 liquidity grid lets a second public request reuse local facts."""
    user_id = await _seed_authoritative_prerequisites(calendar_data_kind="reference_series")
    provider = _RecordingProvider()
    source_policies = _policy(
        provider,
        data_kind="reference_series",
        adjustment="unadjusted",
    )
    request = _liquidity_request()

    async with async_session_maker() as first_session:
        first = await _service(
            first_session,
            provider,
            now=RECEIPT_AT,
            source_policies=source_policies,
        ).execute(
            request,
            access=await _access_for_session(
                first_session,
                user_id=user_id,
                now=RECEIPT_AT,
            ),
        )
        await first_session.commit()

    async with async_session_maker() as reread_session:
        reread = await _service(
            reread_session,
            provider,
            now=RECEIPT_AT + timedelta(microseconds=2),
            source_policies=source_policies,
        ).execute(
            request,
            access=await _access_for_session(
                reread_session,
                user_id=user_id,
                now=RECEIPT_AT + timedelta(microseconds=2),
            ),
        )

    assert first.coverage.status.value == "complete"
    assert len(first.fetches) == 1
    assert reread.coverage.status.value == "complete"
    assert reread.fetches == ()
    assert len(provider.calls) == 1
    assert all(
        {"volume", "turnover", "turnover_rate"} <= set(observation.fields)
        for observation in reread.observations
    )


@pytest.mark.asyncio
async def test_imported_etf_nav_grid_persists_then_rereads_the_source_reported_facts() -> None:
    """ETF NAV uses the canonical reference series store and never reuses price bars."""
    fund_identity = InstrumentIdentity.model_validate(
        {
            "asset_type": "fund",
            "identity_level": "PRODUCT",
            "canonical_id": FUND_NAV_CANONICAL_ID,
            "display_symbol": "159915",
            "name": "创业板 ETF",
            "venue": "CN-SZSE",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "EXCHANGE_SYMBOL",
            "identifier_value": "159915",
            "product_type": "ETF",
            "metadata_version": "fund-nav-v1",
            "details": {
                "kind": "FUND",
                "fund_identity_kind": "LISTING",
                "fund_id": "fund:cn-etf:159915",
                "share_class_id": "share-class:cn-etf:159915",
                "nav_calendar_id": "CN-SZSE",
            },
        }
    )
    user_id = await _seed_authoritative_prerequisites(
        calendar_data_kind="reference_series",
        identity=fund_identity,
        calendar_code="CN-SZSE",
    )
    provider = _RecordingProvider()
    source_policies = _policy(
        provider,
        data_kind="reference_series",
        adjustment="source_reported",
        asset_type="fund",
        market="CN-SZSE",
        price_basis="nav",
        unit="fund_share",
        route_id="akshare-fund-nav-primary-v1",
        family_id="fund.nav",
        family_contract_version="market-data-family-v1",
        product_types=frozenset({"ETF"}),
        fund_identity_kinds=frozenset({"LISTING"}),
    )
    request = _fund_nav_request()

    async with async_session_maker() as first_session:
        first = await _service(
            first_session,
            provider,
            now=RECEIPT_AT,
            source_policies=source_policies,
        ).execute(
            request,
            access=await _access_for_session(
                first_session,
                user_id=user_id,
                now=RECEIPT_AT,
            ),
        )
        await first_session.commit()

    async with async_session_maker() as reread_session:
        reread = await _service(
            reread_session,
            provider,
            now=RECEIPT_AT + timedelta(microseconds=2),
            source_policies=source_policies,
        ).execute(
            request,
            access=await _access_for_session(
                reread_session,
                user_id=user_id,
                now=RECEIPT_AT + timedelta(microseconds=2),
            ),
        )

    assert first.coverage.status.value == "complete"
    assert len(first.fetches) == 1
    assert first.fetches[0].route_id == "akshare-fund-nav-primary-v1"
    assert provider.calls[0].product_type == "ETF"
    assert provider.calls[0].fund_identity_kind == "LISTING"
    assert reread.coverage.status.value == "complete"
    assert reread.fetches == ()
    assert len(provider.calls) == 1
    assert all(
        observation.fields
        == {
            "nav": 1.2345,
            "cumulative_nav": 1.4567,
            "daily_growth_rate": 0.98,
        }
        for observation in reread.observations
    )
