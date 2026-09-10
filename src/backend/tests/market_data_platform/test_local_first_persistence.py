"""End-to-end persistence contracts for the local-first market-data path.

These tests use the real catalog, versioned identity materializer, calendar
importer, store, resolver, and query service.  The only double is a bounded
provider adapter so no test reaches AkShare or OpenBB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import MdObservationRevision, MdSourceSnapshot
from app.models.permission import Role, user_roles
from app.models.user import User
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest
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
) -> MarketDataQueryService:
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(session),
            identities=MarketDataIdentityResolver(session),
            # This lower-level revision test deliberately exercises a broad
            # internal field projection. Public v2 routes retain the default
            # fail-closed family binding requirement.
            allow_unbound_internal_requests=True,
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

        user = User(
            username="market-data-local-first-fixture",
            email="market-data-local-first-fixture@example.test",
            hashed_password="not-used",
            is_active=True,
        )
        session.add(user)
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
        await session.execute(user_roles.insert().values(user_id=user.id, role=Role.USER.value))
        user_id = str(user.id)
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
        return user_id


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
        observation.fields == {
            "nav": 1.2345,
            "cumulative_nav": 1.4567,
            "daily_growth_rate": 0.98,
        }
        for observation in reread.observations
    )
