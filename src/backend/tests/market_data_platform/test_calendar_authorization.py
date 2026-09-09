"""Current-source governance contracts for imported trading calendars."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import update

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import MdCalendarSnapshot
from app.services.market_data.calendar_importer import (
    MANIFEST_VERSION,
    MarketDataCalendarImporter,
    MarketDataCalendarImportError,
)
from app.services.market_data.coverage import CalendarStatus, TimeWindow
from app.services.market_data.store import MarketDataStore

UTC = timezone.utc
CALENDAR_SOURCE_ID = "akshare"
OTHER_APPROVED_SOURCE_ID = "openbb:yfinance"


def _at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=UTC)


def _manifest(*, source_registry_id: str = CALENDAR_SOURCE_ID) -> dict[str, object]:
    return {
        "manifest_version": MANIFEST_VERSION,
        "approval_reference": "CAB-197-CALENDAR-GOVERNANCE-001",
        "evidence_uri": "file:///approved/calendars/CN-SSE-2026-09.json",
        "evidence_content_hash": "a" * 64,
        "source_registry_id": source_registry_id,
        "calendar_code": "CN-SSE",
        "calendar_version": "2026.09",
        "timezone_name": "Asia/Shanghai",
        "coverage_start_at": _at(1).isoformat(),
        "coverage_end_at": _at(3).isoformat(),
        "events": [
            {
                "trading_date": "2026-09-01",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": _at(1).isoformat(),
                "event_end": _at(1, 6).isoformat(),
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
            {
                "trading_date": "2026-09-02",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": _at(2).isoformat(),
                "event_end": _at(2, 6).isoformat(),
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
        ],
    }


async def _seed_registry(
    db,
    *,
    source_id: str,
    enabled: bool = True,
) -> None:
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
            enabled=enabled,
            updated_at=_at(1),
        )
    )
    await db.commit()


def _window() -> TimeWindow:
    return TimeWindow(start_at=_at(1), end_at=_at(3))


@pytest.mark.asyncio
async def test_calendar_import_requires_a_registered_governed_source() -> None:
    """Operator approval prose alone cannot create a calendar source of record."""
    malformed = _manifest()
    malformed.pop("source_registry_id")

    async with async_session_maker() as db:
        with pytest.raises(MarketDataCalendarImportError) as missing_source:
            await MarketDataCalendarImporter(db).import_payload(payload=malformed, dry_run=False)

        await _seed_registry(db, source_id=CALENDAR_SOURCE_ID, enabled=False)
        with pytest.raises(MarketDataCalendarImportError) as disabled_source:
            await MarketDataCalendarImporter(db).import_payload(
                payload=_manifest(),
                dry_run=False,
            )

    assert missing_source.value.code == "CALENDAR_MANIFEST_INVALID"
    assert disabled_source.value.code == "CALENDAR_SOURCE_REGISTRY_DENIED"


@pytest.mark.asyncio
async def test_calendar_known_requires_the_same_currently_authorized_source() -> None:
    """A different approved source cannot authorize another source's calendar."""
    async with async_session_maker() as db:
        await _seed_registry(db, source_id=CALENDAR_SOURCE_ID)
        await _seed_registry(db, source_id=OTHER_APPROVED_SOURCE_ID)
        report = await MarketDataCalendarImporter(db, clock=lambda: _at(2)).import_payload(
            payload=_manifest(),
            dry_run=False,
        )
        snapshot = await db.get(MdCalendarSnapshot, report.snapshot_id)
        store = MarketDataStore(db)
        matching = await store.read_calendar(
            calendar_code="CN-SSE",
            window=_window(),
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )
        different_approved = await store.read_calendar(
            calendar_code="CN-SSE",
            window=_window(),
            allowed_source_registry_ids=frozenset({OTHER_APPROVED_SOURCE_ID}),
        )
        revoked = await store.read_calendar(
            calendar_code="CN-SSE",
            window=_window(),
            allowed_source_registry_ids=frozenset(),
        )

    assert snapshot is not None
    assert snapshot.source_registry_id == CALENDAR_SOURCE_ID
    assert snapshot.source_governance_state == "VERIFIED"
    assert snapshot.source_governance_descriptor_sha256 is not None
    assert snapshot.definition_json["source_governance"]["descriptor_hash"] == (
        snapshot.source_governance_descriptor_sha256
    )
    assert matching.status is CalendarStatus.KNOWN
    assert different_approved.status is CalendarStatus.UNKNOWN
    assert different_approved.reason == "CALENDAR_SOURCE_UNAUTHORIZED"
    assert revoked.status is CalendarStatus.UNKNOWN
    assert revoked.reason == "CALENDAR_SOURCE_UNAUTHORIZED"


@pytest.mark.asyncio
async def test_legacy_or_unverified_calendar_never_proves_known_coverage() -> None:
    """Rows without an importer-validated governance anchor stay typed unknown."""
    async with async_session_maker() as db:
        await _seed_registry(db, source_id=CALENDAR_SOURCE_ID)
        report = await MarketDataCalendarImporter(db, clock=lambda: _at(2)).import_payload(
            payload=_manifest(),
            dry_run=False,
        )
        await db.execute(
            update(MdCalendarSnapshot)
            .where(MdCalendarSnapshot.id == report.snapshot_id)
            .values(
                source_governance_state=None,
                source_governance_descriptor_sha256=None,
                source_registry_id=None,
            )
        )
        await db.commit()
        calendar = await MarketDataStore(db).read_calendar(
            calendar_code="CN-SSE",
            window=_window(),
            allowed_source_registry_ids=frozenset({CALENDAR_SOURCE_ID}),
        )

    assert calendar.status is CalendarStatus.UNKNOWN
    assert calendar.reason == "CALENDAR_SOURCE_UNVERIFIED"
