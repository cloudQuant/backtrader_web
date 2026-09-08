"""Offline contracts for explicit Iteration 197 trading-calendar imports."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry
from app.models.market_data_platform import (
    MdCalendarEvent,
    MdCalendarImportLock,
    MdCalendarSnapshot,
)
from app.services.market_data.calendar_importer import (
    MANIFEST_VERSION,
    MarketDataCalendarImporter,
    MarketDataCalendarImportError,
    load_market_data_calendar_manifest,
)
from app.services.market_data.coverage import CalendarStatus, TimeWindow
from app.services.market_data.store import MarketDataStore

CALENDAR_SOURCE_ID = "akshare"


@pytest_asyncio.fixture(autouse=True)
async def seed_calendar_source_registry() -> None:
    """Every reviewed calendar fixture names an explicit governed source."""
    async with async_session_maker() as session:
        session.add(
            AssetDataSourceRegistry(
                source_id=CALENDAR_SOURCE_ID,
                asset_types=["stock"],
                jurisdictions=["CN"],
                license_status="APPROVED",
                allowed_uses=["DISPLAY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="market-data-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                effective_to=None,
                retention_expires_at=None,
                enabled=True,
                updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        await session.commit()


def _manifest(
    *,
    calendar_version: str = "2026.09",
    start: str = "2026-09-01T00:00:00Z",
    end: str = "2026-09-04T00:00:00Z",
    evidence_hash: str = "a" * 64,
) -> dict:
    return {
        "manifest_version": MANIFEST_VERSION,
        "approval_reference": "CAB-197-CALENDAR-001",
        "evidence_uri": "file:///approved/calendars/CN-SSE-2026-09.json",
        "evidence_content_hash": evidence_hash,
        "source_registry_id": CALENDAR_SOURCE_ID,
        "calendar_code": "CN-SSE",
        "calendar_version": calendar_version,
        "timezone_name": "Asia/Shanghai",
        "coverage_start_at": start,
        "coverage_end_at": end,
        "events": [
            {
                "trading_date": "2026-09-01",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": "2026-09-01T00:00:00Z",
                "event_end": "2026-09-01T06:00:00Z",
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
            {
                "trading_date": "2026-09-02",
                "event_type": "session",
                "session_code": "daily-close",
                "is_trading_day": True,
                "event_start": "2026-09-02T00:00:00Z",
                "event_end": "2026-09-02T06:00:00Z",
                "coverage": {"data_kind": "bars", "frequency": "1d"},
                "event_payload": {"provider_observation_key": "daily-close"},
            },
        ],
    }


def _daily_event(day: int) -> dict[str, object]:
    """Build one exact daily grid event for a rolling calendar segment."""
    stamp = f"2026-09-{day:02d}"
    return {
        "trading_date": stamp,
        "event_type": "session",
        "session_code": "daily-close",
        "is_trading_day": True,
        "event_start": f"{stamp}T00:00:00Z",
        "event_end": f"{stamp}T06:00:00Z",
        "coverage": {"data_kind": "bars", "frequency": "1d"},
        "event_payload": {"provider_observation_key": "daily-close"},
    }


@pytest.mark.asyncio
async def test_calendar_dry_run_exercises_insert_path_and_leaves_no_snapshot_or_events() -> None:
    """The default operator path must not make a calendar reusable by accident."""
    async with async_session_maker() as session:
        result = await MarketDataCalendarImporter(session).import_payload(payload=_manifest())
        pending_snapshots = await session.scalar(
            select(func.count()).select_from(MdCalendarSnapshot)
        )
        pending_events = await session.scalar(select(func.count()).select_from(MdCalendarEvent))
        await session.rollback()
        persisted_snapshots = await session.scalar(
            select(func.count()).select_from(MdCalendarSnapshot)
        )
        persisted_events = await session.scalar(select(func.count()).select_from(MdCalendarEvent))

    assert result.dry_run is True
    assert result.action == "would_create"
    assert result.event_count == 2
    assert pending_snapshots == 1
    assert pending_events == 2
    assert persisted_snapshots == 0
    assert persisted_events == 0


@pytest.mark.asyncio
async def test_calendar_import_is_idempotent_and_serves_exact_persisted_event_keys() -> None:
    """A repeated reviewed payload reuses a version and lets coverage avoid re-fetching."""
    payload = _manifest()
    async with async_session_maker() as session:
        importer = MarketDataCalendarImporter(session)
        first = await importer.import_payload(payload=payload, dry_run=False)
        await session.commit()
        second = await importer.import_payload(payload=payload, dry_run=False)
        await session.commit()
        calendar = await MarketDataStore(session).read_calendar(
            calendar_code="CN-SSE",
            window=TimeWindow(
                start_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                end_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            ),
        )
        snapshot_count = await session.scalar(select(func.count()).select_from(MdCalendarSnapshot))
        event_count = await session.scalar(select(func.count()).select_from(MdCalendarEvent))

    assert first.action == "created"
    assert second.action == "reused"
    assert second.snapshot_id == first.snapshot_id
    assert snapshot_count == 1
    assert event_count == 2
    assert calendar.status is CalendarStatus.KNOWN
    assert calendar.calendar_version == "2026.09"
    assert [event.event_at.isoformat() for event in calendar.event_keys] == [
        "2026-09-01T00:00:00+00:00",
        "2026-09-02T00:00:00+00:00",
    ]


@pytest.mark.asyncio
async def test_calendar_import_composes_adjacent_published_segments_and_keeps_one_lock() -> None:
    """Rolling manifests may meet at a boundary but cannot invent a missing grid."""
    first = _manifest(
        calendar_version="2026.09-a",
        end="2026-09-03T00:00:00Z",
    )
    second = _manifest(
        calendar_version="2026.09-b",
        start="2026-09-03T00:00:00Z",
        end="2026-09-05T00:00:00Z",
        evidence_hash="b" * 64,
    )
    second["events"] = [_daily_event(3), _daily_event(4)]

    async with async_session_maker() as session:
        importer = MarketDataCalendarImporter(session)
        await importer.import_payload(payload=first, dry_run=False)
        await importer.import_payload(payload=second, dry_run=False)
        calendar = await MarketDataStore(session).read_calendar(
            calendar_code="CN-SSE",
            window=TimeWindow(
                start_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                end_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            ),
        )
        lock_count = await session.scalar(select(func.count()).select_from(MdCalendarImportLock))

    assert lock_count == 1
    assert calendar.status is CalendarStatus.KNOWN
    assert calendar.calendar_version.startswith("composed:")
    assert [event.event_at.day for event in calendar.event_keys] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_calendar_read_limits_event_grid_to_the_requested_window_intersection() -> None:
    """A small query must not return or scan its whole published calendar segment."""
    payload = _manifest(end="2026-09-05T00:00:00Z")
    payload["events"].extend([_daily_event(3), _daily_event(4)])

    async with async_session_maker() as session:
        await MarketDataCalendarImporter(session).import_payload(payload=payload, dry_run=False)
        calendar = await MarketDataStore(session).read_calendar(
            calendar_code="CN-SSE",
            window=TimeWindow(
                start_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
                end_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            ),
            data_kind="bars",
            frequency="1d",
        )

    assert calendar.status is CalendarStatus.KNOWN
    assert [event.event_at.day for event in calendar.event_keys] == [2]


@pytest.mark.asyncio
async def test_calendar_read_keeps_a_declared_grid_known_when_window_has_no_event() -> None:
    """A holiday-like empty subwindow is known when its segment declares the grid."""
    payload = _manifest(end="2026-09-05T00:00:00Z")
    payload["events"].extend([_daily_event(3), _daily_event(4)])

    async with async_session_maker() as session:
        await MarketDataCalendarImporter(session).import_payload(payload=payload, dry_run=False)
        calendar = await MarketDataStore(session).read_calendar(
            calendar_code="CN-SSE",
            window=TimeWindow(
                start_at=datetime(2026, 9, 4, 6, tzinfo=timezone.utc),
                end_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
            ),
            data_kind="bars",
            frequency="1d",
        )

    assert calendar.status is CalendarStatus.KNOWN
    assert calendar.event_keys == ()


@pytest.mark.asyncio
async def test_calendar_import_rejects_conflicting_version_and_overlapping_windows() -> None:
    """The query API has no version selector, so overlapping versions are unsafe."""
    async with async_session_maker() as session:
        importer = MarketDataCalendarImporter(session)
        await importer.import_payload(payload=_manifest(), dry_run=False)
        await session.commit()

        with pytest.raises(MarketDataCalendarImportError) as same_version:
            await importer.import_payload(payload=_manifest(evidence_hash="b" * 64), dry_run=False)
        with pytest.raises(MarketDataCalendarImportError) as overlapping:
            overlapping_payload = _manifest(
                calendar_version="2026.09-corrected",
                start="2026-09-03T00:00:00Z",
                end="2026-09-06T00:00:00Z",
                evidence_hash="c" * 64,
            )
            overlapping_payload["events"] = []
            await importer.import_payload(
                payload=overlapping_payload,
                dry_run=False,
            )
        snapshots = await session.scalar(select(func.count()).select_from(MdCalendarSnapshot))

    assert same_version.value.code == "CALENDAR_VERSION_CONFLICT"
    assert overlapping.value.code == "CALENDAR_COVERAGE_OVERLAP"
    assert snapshots == 1


@pytest.mark.asyncio
async def test_calendar_import_converts_database_lock_errors_to_a_retryable_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first-writer SQLite race must not leak a driver exception to callers."""
    async with async_session_maker() as session:
        importer = MarketDataCalendarImporter(session)

        async def locked(_: str) -> None:
            raise OperationalError("SELECT", {}, RuntimeError("database is locked"))

        monkeypatch.setattr(importer, "_lock_calendar_code", locked)
        with pytest.raises(MarketDataCalendarImportError) as rejected:
            await importer.import_payload(payload=_manifest(), dry_run=False)

        assert not session.in_transaction()

    assert rejected.value.code == "CALENDAR_IMPORT_LOCK_UNAVAILABLE"


@pytest.mark.asyncio
async def test_calendar_import_rejects_naive_events_and_malformed_manifest() -> None:
    """Calendar evidence cannot silently reinterpret a naive timestamp or empty coverage."""
    naive = _manifest()
    naive["events"][0]["event_start"] = "2026-09-01T00:00:00"
    malformed = _manifest()
    malformed["coverage_end_at"] = malformed["coverage_start_at"]

    async with async_session_maker() as session:
        importer = MarketDataCalendarImporter(session)
        with pytest.raises(MarketDataCalendarImportError) as naive_rejected:
            await importer.import_payload(payload=naive)
        with pytest.raises(MarketDataCalendarImportError) as malformed_rejected:
            await importer.import_payload(payload=malformed)

    assert naive_rejected.value.code == "CALENDAR_MANIFEST_INVALID"
    assert malformed_rejected.value.code == "CALENDAR_MANIFEST_INVALID"


@pytest.mark.asyncio
async def test_calendar_import_rejects_two_sessions_with_the_same_coverage_event_key() -> None:
    """Different session labels must not make one expected observation ambiguous."""
    duplicated = _manifest()
    duplicate_event = dict(duplicated["events"][0])
    duplicate_event["session_code"] = "different-label-same-event"
    duplicated["events"].append(duplicate_event)

    async with async_session_maker() as session:
        with pytest.raises(MarketDataCalendarImportError) as rejected:
            await MarketDataCalendarImporter(session).import_payload(payload=duplicated)

    assert rejected.value.code == "CALENDAR_MANIFEST_INVALID"


@pytest.mark.asyncio
async def test_calendar_import_keeps_independent_explicit_grids_per_bar_frequency() -> None:
    """Daily, weekly, and monthly bars never reuse one ambiguous session key."""
    payload = _manifest()
    payload["events"].extend(
        [
            {
                "trading_date": "2026-09-02",
                "event_type": "session",
                "session_code": "weekly-close",
                "is_trading_day": True,
                "event_start": "2026-09-02T00:00:00Z",
                "event_end": "2026-09-02T06:00:00Z",
                "coverage": {"data_kind": "bars", "frequency": "1w"},
                "event_payload": {"provider_observation_key": "weekly-close"},
            },
            {
                "trading_date": "2026-09-02",
                "event_type": "session",
                "session_code": "monthly-close",
                "is_trading_day": True,
                "event_start": "2026-09-02T00:00:00Z",
                "event_end": "2026-09-02T06:00:00Z",
                "coverage": {"data_kind": "bars", "frequency": "1mo"},
                "event_payload": {"provider_observation_key": "monthly-close"},
            },
        ]
    )

    async with async_session_maker() as session:
        await MarketDataCalendarImporter(session).import_payload(payload=payload, dry_run=False)
        await session.commit()
        store = MarketDataStore(session)
        window = TimeWindow(
            start_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            end_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )
        daily = await store.read_calendar(
            calendar_code="CN-SSE",
            window=window,
            data_kind="bars",
            frequency="1d",
        )
        weekly = await store.read_calendar(
            calendar_code="CN-SSE",
            window=window,
            data_kind="bars",
            frequency="1w",
        )
        monthly = await store.read_calendar(
            calendar_code="CN-SSE",
            window=window,
            data_kind="bars",
            frequency="1mo",
        )
        missing_intraday = await store.read_calendar(
            calendar_code="CN-SSE",
            window=window,
            data_kind="bars",
            frequency="5min",
        )

    assert [event.event_at.day for event in daily.event_keys] == [1, 2]
    assert [event.event_at.day for event in weekly.event_keys] == [2]
    assert [event.event_at.day for event in monthly.event_keys] == [2]
    assert missing_intraday.status is CalendarStatus.UNKNOWN
    assert missing_intraday.reason == "CALENDAR_GRID_UNAVAILABLE"


def test_calendar_manifest_loader_is_bounded_and_returns_only_mapping_payload(tmp_path) -> None:
    """CLI file handling supplies stable errors without rendering manifest content."""
    manifest_path = tmp_path / "calendar.json"
    payload = _manifest()
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_market_data_calendar_manifest(manifest_path) == payload

    manifest_path.write_text("[]", encoding="utf-8")
    with pytest.raises(MarketDataCalendarImportError) as rejected:
        load_market_data_calendar_manifest(manifest_path)

    assert rejected.value.code == "CALENDAR_MANIFEST_INVALID"
