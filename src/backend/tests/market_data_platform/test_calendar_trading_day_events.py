"""RED contracts for an authorized calendar-to-trading-date reader.

The legacy daily-bar importer may use a source ``data_date`` only as a lookup
label.  It needs a narrow local-store read that proves the label belongs to
one authorized, published daily-bars calendar event and supplies its exact
canonical ``EventKey``.  These contracts deliberately exercise only the
in-memory SQLite fixtures shared by the market-data tests.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import update

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import MdCalendarEvent, MdCalendarSnapshot
from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.calendar_importer import (
    MANIFEST_VERSION,
    MarketDataCalendarImporter,
)
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import CalendarStatus, EventKey, QueryIdentity, TimeWindow
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import (
    CalendarTradingDayEvent,
    CalendarTradingDayEvents,
    MarketDataStore,
)

UTC = timezone.utc
CALENDAR_CODE = "CN-SZSE"
CALENDAR_SOURCE_ID = "akshare"
OTHER_APPROVED_SOURCE_ID = "openbb:yfinance"
CANONICAL_ID = "instrument:stock:CN-SZSE:000001"
DATASET_CODE = "market.stock_daily"
METADATA_VERSION = "stock-v1"


def _at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=UTC)


def _visibility_cutoff() -> datetime:
    """Use a cutoff after the importer’s real post-commit visibility receipt."""
    return datetime(2100, 1, 1, tzinfo=UTC)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _context() -> ResolvedMarketDataQueryContext:
    """Build the same resolved daily-bars context that needs calendar proof."""
    request = MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "dataset_code": DATASET_CODE,
            "data_kind": "bars",
            "frequency": "1d",
            "start": _at(6, 16).isoformat(),
            "end": _at(9, 16).isoformat(),
            "required_fields": ["close"],
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "purpose": "research",
            "consistency": "strict",
            "knowledge_cutoff": _visibility_cutoff().isoformat(),
        }
    )
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
        display_symbol="000001",
        name="平安银行",
        venue=CALENDAR_CODE,
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="000001",
        product_type="EQUITY",
        metadata_version=METADATA_VERSION,
        details=StockIdentityDetails(exchange_symbol="000001.SZ"),
    )
    return ResolvedMarketDataQueryContext(
        query=query,
        identity=ResolvedMarketDataIdentity(
            instrument_id="instrument-stock-v1",
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            metadata_version=METADATA_VERSION,
            venue=CALENDAR_CODE,
            identity=identity,
            valid_from=_at(1),
            valid_to=None,
            known_at=_at(1),
        ),
        storage=DatasetStorageResolution(
            dataset_id="dataset-market-stock",
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
            market=CALENDAR_CODE,
            frequency="1d",
            source_policy_id="market-default-v1",
            adjustment="qfq",
            price_basis="close",
            currency="CNY",
            unit="share",
            family_id=query.family_id,
            family_contract_version=query.family_contract_version,
        ),
    )


async def _seed_source_registry(db, *, source_id: str) -> None:
    """Seed a governed calendar source into the shared disposable SQLite DB."""
    db.add(
        AssetDataSourceRegistry(
            source_id=source_id,
            asset_types=["stock"],
            jurisdictions=["CN"],
            license_status="APPROVED",
            allowed_uses=["DISPLAY"],
            redistribution_policy="NO_REDISTRIBUTION",
            derived_data_policy="ALLOWED",
            retention_policy="market-data-v1",
            effective_from=datetime(2020, 1, 1, tzinfo=UTC),
            effective_to=None,
            retention_expires_at=None,
            enabled=True,
            updated_at=_at(1),
        )
    )
    await db.commit()


def _manifest() -> dict[str, object]:
    """Use reverse manifest order so the reader must order by trading date."""
    return {
        "manifest_version": MANIFEST_VERSION,
        "approval_reference": "CAB-197-CALENDAR-EVENT-READER-001",
        "evidence_uri": "file:///approved/calendars/CN-SZSE-2026-09.json",
        "evidence_content_hash": "a" * 64,
        "source_registry_id": CALENDAR_SOURCE_ID,
        "calendar_code": CALENDAR_CODE,
        "calendar_version": "2026.09",
        "timezone_name": "Asia/Shanghai",
        "coverage_start_at": _at(6, 16).isoformat(),
        "coverage_end_at": _at(9, 16).isoformat(),
        "events": [
            {
                "trading_date": "2026-09-08",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": _at(8, 7).isoformat(),
                "event_end": _at(8, 8).isoformat(),
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
            {
                "trading_date": "2026-09-07",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": _at(7, 7).isoformat(),
                "event_end": _at(7, 8).isoformat(),
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
        ],
    }


async def _published_calendar(db) -> str:
    """Persist a published, source-governed daily-bars calendar snapshot."""
    report = await MarketDataCalendarImporter(db, clock=lambda: _at(9)).import_payload(
        payload=_manifest(),
        dry_run=False,
    )
    return report.snapshot_id


async def _read_events(
    store: MarketDataStore,
    *,
    allowed_source_registry_ids: frozenset[str],
    visibility_anchor: MarketDataVisibilityAnchor | None = None,
) -> CalendarTradingDayEvents:
    """Exercise the planned narrow reader with one context, PIT, and anchor."""
    knowledge_cutoff = _visibility_cutoff()
    anchor = visibility_anchor or await store.resolve_visibility_anchor(
        knowledge_cutoff=knowledge_cutoff
    )
    return await store.read_calendar_trading_day_events_for_context(
        _context(),
        knowledge_cutoff=knowledge_cutoff,
        visibility_anchor=anchor,
        allowed_source_registry_ids=allowed_source_registry_ids,
    )


@pytest.mark.asyncio
async def test_calendar_trading_day_events_returns_sorted_one_to_one_daily_event_keys() -> None:
    """A daily importer receives immutable date labels and exact canonical EventKeys."""
    async with async_session_maker() as db:
        await _seed_source_registry(db, source_id=CALENDAR_SOURCE_ID)
        snapshot_id = await _published_calendar(db)
        store = MarketDataStore(db)
        result = await _read_events(
            store,
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )
        expected_anchor = await store.resolve_visibility_anchor(
            knowledge_cutoff=_visibility_cutoff()
        )

    assert result.status is CalendarStatus.KNOWN
    assert result.reason is None
    assert result.calendar_code == CALENDAR_CODE
    assert result.calendar_version == "2026.09"
    assert result.data_kind == "bars"
    assert result.frequency == "1d"
    assert result.calendar_snapshot_id == snapshot_id
    assert result.timezone_name == "Asia/Shanghai"
    assert result.coverage_window == TimeWindow(start_at=_at(6, 16), end_at=_at(9, 16))
    assert result.visibility_anchor == expected_anchor
    assert result.events == (
        CalendarTradingDayEvent(
            trading_date=date(2026, 9, 7),
            event_key=EventKey(_at(7, 7)),
        ),
        CalendarTradingDayEvent(
            trading_date=date(2026, 9, 8),
            event_key=EventKey(_at(8, 7)),
        ),
    )


@pytest.mark.asyncio
async def test_calendar_trading_day_events_never_return_events_from_an_unauthorized_source() -> (
    None
):
    """A different approved source cannot authorize a calendar it did not publish."""
    async with async_session_maker() as db:
        await _seed_source_registry(db, source_id=CALENDAR_SOURCE_ID)
        await _seed_source_registry(db, source_id=OTHER_APPROVED_SOURCE_ID)
        await _published_calendar(db)
        result = await _read_events(
            MarketDataStore(db),
            allowed_source_registry_ids=frozenset({OTHER_APPROVED_SOURCE_ID}),
        )

    assert result.status is CalendarStatus.UNKNOWN
    assert result.reason == "CALENDAR_SOURCE_UNAUTHORIZED"
    assert result.events == ()


@pytest.mark.asyncio
async def test_calendar_trading_day_events_never_return_events_from_an_unverified_source() -> None:
    """Missing frozen source-governance evidence makes the date-to-key map unusable."""
    async with async_session_maker() as db:
        await _seed_source_registry(db, source_id=CALENDAR_SOURCE_ID)
        snapshot_id = await _published_calendar(db)
        await db.execute(
            update(MdCalendarSnapshot)
            .where(MdCalendarSnapshot.id == snapshot_id)
            .values(
                source_governance_state=None,
                source_governance_descriptor_sha256=None,
                source_registry_id=None,
            )
        )
        await db.commit()
        result = await _read_events(
            MarketDataStore(db),
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )

    assert result.status is CalendarStatus.UNKNOWN
    assert result.reason == "CALENDAR_SOURCE_UNVERIFIED"
    assert result.events == ()


@pytest.mark.asyncio
async def test_calendar_trading_day_events_respect_a_prepublication_visibility_anchor() -> None:
    """An old PIT anchor cannot observe a calendar published after it was frozen."""
    async with async_session_maker() as db:
        await _seed_source_registry(db, source_id=CALENDAR_SOURCE_ID)
        store = MarketDataStore(db)
        old_anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_visibility_cutoff())
        assert old_anchor.max_visibility_sequence == 0
        await db.commit()
        await _published_calendar(db)

        old_result = await _read_events(
            store,
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
            visibility_anchor=old_anchor,
        )
        new_result = await _read_events(
            store,
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )

    assert old_result.status is CalendarStatus.UNKNOWN
    assert old_result.events == ()
    assert new_result.status is CalendarStatus.KNOWN
    assert new_result.visibility_anchor.max_visibility_sequence > old_anchor.max_visibility_sequence


@pytest.mark.asyncio
async def test_calendar_trading_day_events_exclude_another_data_family_in_same_snapshot() -> None:
    """A same-day reference-series session cannot alter the daily-bars date map."""
    async with async_session_maker() as db:
        await _seed_source_registry(db, source_id=CALENDAR_SOURCE_ID)
        snapshot_id = await _published_calendar(db)
        db.add(
            MdCalendarEvent(
                id="calendar-cn-szse-reference-series-same-day",
                calendar_snapshot_id=snapshot_id,
                trading_date=date(2026, 9, 7),
                event_type="session",
                session_code="reference-series-close",
                is_trading_day=True,
                event_start=_at(7, 11),
                event_end=_at(7, 12),
                event_payload_json={
                    "coverage": {"data_kind": "reference_series", "frequency": "1d"}
                },
                event_sha256=_sha("calendar-cn-szse-reference-series-same-day"),
            )
        )
        await db.commit()
        result = await _read_events(
            MarketDataStore(db),
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )

    assert result.status is CalendarStatus.KNOWN
    assert result.events == (
        CalendarTradingDayEvent(
            trading_date=date(2026, 9, 7),
            event_key=EventKey(_at(7, 7)),
        ),
        CalendarTradingDayEvent(
            trading_date=date(2026, 9, 8),
            event_key=EventKey(_at(8, 7)),
        ),
    )


@pytest.mark.asyncio
async def test_calendar_trading_day_events_fail_closed_when_one_date_has_two_daily_event_keys() -> (
    None
):
    """A source date may map to exactly one published daily-bars EventKey."""
    async with async_session_maker() as db:
        await _seed_source_registry(db, source_id=CALENDAR_SOURCE_ID)
        snapshot_id = await _published_calendar(db)
        db.add(
            MdCalendarEvent(
                id="calendar-cn-szse-duplicate-daily-key",
                calendar_snapshot_id=snapshot_id,
                trading_date=date(2026, 9, 7),
                event_type="session",
                session_code="daily-close-duplicate",
                is_trading_day=True,
                event_start=_at(7, 9),
                event_end=_at(7, 10),
                event_payload_json={"coverage": {"data_kind": "bars", "frequency": "1d"}},
                event_sha256=_sha("calendar-cn-szse-duplicate-daily-key"),
            )
        )
        await db.commit()
        result = await _read_events(
            MarketDataStore(db),
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )

    assert result.status is CalendarStatus.UNKNOWN
    assert result.reason == "CALENDAR_TRADING_DAY_EVENT_INTEGRITY"
    assert result.events == ()
