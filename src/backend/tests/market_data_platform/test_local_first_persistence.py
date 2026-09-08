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
from app.models.market_data_platform import MdObservationRevision, MdSourceSnapshot
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import MarketDataQueryRequest
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
WINDOW_START: Final = datetime(2026, 9, 1, tzinfo=UTC)
WINDOW_END: Final = datetime(2026, 9, 3, tzinfo=UTC)
RECEIPT_AT: Final = datetime.now(UTC) + timedelta(minutes=1)


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
                    field_name: (10.0 if field_name == "close" else 1000)
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


def _policy(provider: _RecordingProvider) -> MarketDataSourcePolicyRegistry:
    route = MarketDataProviderRoute(
        route_id="fixture-akshare-stock-v1",
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
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
) -> MarketDataQueryService:
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(session),
            identities=MarketDataIdentityResolver(session),
        ),
        store=MarketDataStore(session, clock=lambda: now),
        source_policies=_policy(provider),
        allow_online_fetch=True,
        clock=lambda: now,
        cursor_signing_key="test-market-data-cursor-hmac-key-material-0000000000000000000001",
    )


async def _seed_authoritative_prerequisites() -> None:
    """Create only operator-owned prerequisites before a public query begins."""
    identity = InstrumentIdentity.model_validate(
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
    calendar = {
        "manifest_version": MANIFEST_VERSION,
        "approval_reference": "CAB-197-E2E-001",
        "evidence_uri": "file:///approved/calendars/CN-SSE-2026-09.json",
        "evidence_content_hash": "a" * 64,
        "calendar_code": "CN-SSE",
        "calendar_version": "2026.09",
        "timezone_name": "Asia/Shanghai",
        "coverage_start_at": WINDOW_START.isoformat(),
        "coverage_end_at": WINDOW_END.isoformat(),
        "events": [
            {
                "trading_date": "2026-09-01",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": WINDOW_START.isoformat(),
                "event_end": (WINDOW_START + timedelta(hours=6)).isoformat(),
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
            {
                "trading_date": "2026-09-02",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": (WINDOW_START + timedelta(days=1)).isoformat(),
                "event_end": (WINDOW_START + timedelta(days=1, hours=6)).isoformat(),
                "coverage": {"data_kind": "bars", "frequency": "1d"},
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


@pytest.mark.asyncio
async def test_local_first_persists_once_then_reuses_complete_older_revision_without_network() -> None:
    """A completed cache serves later broad requests even after a narrower refresh revision."""
    await _seed_authoritative_prerequisites()
    provider = _RecordingProvider()

    async with async_session_maker() as first_session:
        first = await _service(first_session, provider, now=RECEIPT_AT).execute(
            _request(required_fields=["close", "volume"])
        )
        await first_session.commit()

    async with async_session_maker() as narrow_refresh_session:
        narrow_refresh = await _service(
            narrow_refresh_session,
            provider,
            now=RECEIPT_AT + timedelta(microseconds=2),
        ).execute(
            _request(required_fields=["close"], mode="refresh")
        )
        await narrow_refresh_session.commit()

    async with async_session_maker() as reused_session:
        reused = await _service(
            reused_session,
            provider,
            now=RECEIPT_AT + timedelta(microseconds=4),
        ).execute(
            _request(required_fields=["close", "volume"])
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
