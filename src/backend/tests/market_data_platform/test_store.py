"""Focused behavioral contracts for normalized Iteration 197 local storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.data_governance import DgDataset, DgProvider
from app.models.market_data_platform import (
    MdCalendarEvent,
    MdCalendarSnapshot,
    MdDataSeries,
    MdObservationRevision,
    MdPublication,
    MdSourceSnapshot,
)
from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data import store as store_module
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import CalendarStatus, QueryIdentity, TimeWindow
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)
from app.services.market_data.publication import PUBLICATION_CALENDAR_SNAPSHOT
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import MarketDataStore, MarketDataStoreError

UTC = timezone.utc
DATASET_ID = "dataset-market-stock"
DATASET_CODE = "market.stock_daily"
CANONICAL_ID = "instrument:stock:CN-SSE:600000"
METADATA_VERSION = "stock-v1"
PROVIDER_ID = "akshare:stock"


def _at(hour: int, *, day: int = 8) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=UTC)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
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


def _context(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    required_fields: tuple[str, ...] = ("close",),
) -> ResolvedMarketDataQueryContext:
    start_at = start or _at(9)
    end_at = end or _at(16)
    request = MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "dataset_code": DATASET_CODE,
            "data_kind": "bars",
            "frequency": "1d",
            "start": start_at.isoformat(),
            "end": end_at.isoformat(),
            "required_fields": list(required_fields),
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
        }
    )
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=CANONICAL_ID,
        dataset_code=DATASET_CODE,
        instrument_metadata_version=METADATA_VERSION,
    )
    identity = _identity()
    resolved_identity = ResolvedMarketDataIdentity(
        instrument_id="instrument-stock-v1",
        canonical_id=CANONICAL_ID,
        asset_type="stock",
        metadata_version=METADATA_VERSION,
        venue="CN-SSE",
        identity=identity,
        valid_from=_at(0, day=1),
        valid_to=None,
        known_at=_at(0, day=1),
    )
    return ResolvedMarketDataQueryContext(
        query=query,
        identity=resolved_identity,
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


async def _seed_dataset_and_provider(
    db,
    *,
    provider_id: str = PROVIDER_ID,
    active: bool = True,
) -> None:
    db.add_all(
        [
            DgDataset(
                id=DATASET_ID,
                dataset_code=DATASET_CODE,
                display_name="A 股日线",
                domain="market",
                canonical_schema={"event_at": "timestamp", "close": "decimal"},
                primary_key=["canonical_id", "event_at"],
            ),
            DgProvider(
                id="provider-akshare-stock",
                provider_id=provider_id,
                name="AkShare stock",
                category="market",
                is_active=active,
            ),
        ]
    )
    await db.commit()


def _result(
    *,
    observations: tuple[ProviderMarketObservation, ...],
    retrieved_at: datetime,
    provider_id: str = PROVIDER_ID,
    source_revision: str = "v1",
    raw_payload: dict[str, object] | None = None,
    request: MarketDataProviderRequest | None = None,
    context: ResolvedMarketDataQueryContext | None = None,
) -> ProviderFetchResult:
    context = context or _context()
    return ProviderFetchResult(
        provider_id=provider_id,
        source_revision=source_revision,
        retrieved_at=retrieved_at,
        observations=observations,
        raw_payload=raw_payload
        or {"records": [{"event_at": item.event_at.isoformat()} for item in observations]},
        request=request
        or MarketDataProviderRequest(
            query_fingerprint=context.query.query_fingerprint,
            canonical_id=context.query.canonical_id,
            asset_type=context.identity.asset_type,
            provider_symbol=context.identity.identity.display_symbol,
            market=context.identity.venue or "",
            data_kind=context.query.data_kind,
            frequency=context.query.frequency or "snapshot",
            start_at=context.query.start,
            end_at=context.query.end,
            required_fields=frozenset(context.query.required_fields),
            provider="akshare",
            adjustment=context.query.adjustment,
            price_basis=context.query.price_basis,
            currency=context.query.currency,
            unit=context.query.unit,
            source_policy_id=context.query.source_policy_id,
        ),
    )


def _observation(
    *,
    event_at: datetime,
    available_at: datetime,
    fields: dict[str, object],
) -> ProviderMarketObservation:
    return ProviderMarketObservation(
        event_at=event_at,
        available_at=available_at,
        fields=fields,
    )


@pytest.mark.asyncio
async def test_series_identity_reuses_one_series_across_windows_and_projection_fields() -> None:
    """Windows and required-field projection do not fork the canonical economic series."""
    first_context = _context(required_fields=("close",))
    second_context = _context(
        start=_at(9, day=9),
        end=_at(16, day=9),
        required_fields=("close", "volume"),
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        first = await store.get_or_create_series(first_context)
        second = await store.get_or_create_series(second_context)
        await db.commit()

        count = await db.scalar(select(func.count()).select_from(MdDataSeries))

    assert first.id == second.id
    assert count == 1
    assert "start" not in first.semantic_identity_json
    assert "end" not in first.semantic_identity_json
    assert "required_fields" not in first.semantic_identity_json
    assert first.semantic_identity_json["instrument_metadata_version"] == METADATA_VERSION


@pytest.mark.asyncio
async def test_store_appends_source_provenance_and_normalized_revisions() -> None:
    """Each fetch retains its raw receipt while same-event revisions remain append-only."""
    context = _context()
    event_at = _at(10)
    failed_event_at = _at(11)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        first = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(14),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(12),
                        fields={"close": Decimal("10.50")},
                    ),
                    _observation(
                        event_at=failed_event_at,
                        available_at=_at(12),
                        fields={"open": Decimal("10.00")},
                    ),
                ),
                raw_payload={"records": [{"close": Decimal("10.50")}]},
            ),
            received_at=_at(14),
        )
        await db.commit()

        second = await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(16),
                source_revision="v2",
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(15),
                        fields={"close": Decimal("11.00")},
                    ),
                ),
            ),
            received_at=_at(16),
        )
        await db.commit()

        snapshots = list(
            (await db.execute(select(MdSourceSnapshot).order_by(MdSourceSnapshot.retrieved_at)))
            .scalars()
            .all()
        )
        revisions = list(
            (
                await db.execute(
                    select(MdObservationRevision)
                    .where(MdObservationRevision.event_time == event_at)
                    .order_by(MdObservationRevision.revision_number)
                )
            )
            .scalars()
            .all()
        )
        failed_revision = await db.scalar(
            select(MdObservationRevision).where(MdObservationRevision.event_time == failed_event_at)
        )

    assert first.series_id == second.series_id
    assert first.passing_observation_count == 1
    assert first.failed_observation_count == 1
    assert len(snapshots) == 2
    assert snapshots[0].payload_manifest_json["raw_payload"]["records"][0]["close"] == "10.50"
    expected_fields_hash = _sha(
        json.dumps({"close": "10.50"}, separators=(",", ":"), sort_keys=True)
    )
    assert revisions[0].fields_sha256 == expected_fields_hash
    assert [item.revision_number for item in revisions] == [1, 2]
    assert revisions[0].source_snapshot_id == first.source_snapshot_id
    assert revisions[1].source_snapshot_id == second.source_snapshot_id
    assert failed_revision is not None
    assert failed_revision.quality_status == "failed"
    assert failed_revision.quality_details_json["missing_required_fields"] == ["close"]


@pytest.mark.asyncio
async def test_local_read_uses_availability_and_commit_time_for_point_in_time_selection() -> None:
    """A later correction cannot leak into a cutoff before it was locally committed."""
    context = _context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(12),
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
        )
        await db.commit()
        await store.persist_provider_result(
            context,
            _result(
                retrieved_at=_at(16),
                source_revision="v2",
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(15),
                        fields={"close": "11.00"},
                    ),
                ),
            ),
            received_at=_at(16),
        )
        await db.commit()

        early = await store.read_observations(context, knowledge_cutoff=_at(13))
        late = await store.read_observations(context, knowledge_cutoff=_at(17))

    assert len(early) == 1
    assert early[0].fields["close"] == "10.00"
    assert len(late) == 1
    assert late[0].fields["close"] == "11.00"


@pytest.mark.asyncio
async def test_local_read_keeps_an_older_complete_revision_visible_after_a_narrower_revision() -> None:
    """A field projection must not hide an already cached, broader local fact."""
    broad_context = _context(required_fields=("close", "volume"))
    narrow_context = _context(required_fields=("close",))
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        await store.persist_provider_result(
            broad_context,
            _result(
                retrieved_at=_at(12),
                context=broad_context,
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00", "volume": 1000},
                    ),
                ),
            ),
            received_at=_at(12),
        )
        await db.commit()
        await store.persist_provider_result(
            narrow_context,
            _result(
                retrieved_at=_at(14),
                source_revision="narrow-v2",
                context=narrow_context,
                observations=(
                    _observation(
                        event_at=event_at,
                        available_at=_at(13),
                        fields={"close": "10.25"},
                    ),
                ),
            ),
            received_at=_at(14),
        )
        await db.commit()

        broad_rows = await store.read_observation_revisions(
            broad_context,
            knowledge_cutoff=_at(15),
        )
        narrow_rows = await store.read_observation_revisions(
            narrow_context,
            knowledge_cutoff=_at(15),
        )

    assert len(broad_rows) == 1
    assert broad_rows[0].revision_number == 1
    assert broad_rows[0].fields == {"close": "10.00", "volume": 1000}
    assert len(narrow_rows) == 1
    assert narrow_rows[0].revision_number == 2
    assert narrow_rows[0].fields == {"close": "10.25"}


@pytest.mark.asyncio
async def test_store_rejects_unregistered_out_of_window_and_duplicate_provider_events() -> None:
    """Invalid provider input fails before it can create an evidence receipt."""
    context = _context()
    valid_observation = _observation(
        event_at=_at(10),
        available_at=_at(11),
        fields={"close": "10.00"},
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db)
        with pytest.raises(MarketDataStoreError) as unregistered:
            await store.persist_provider_result(
                context,
                _result(
                    provider_id="unregistered:stock",
                    retrieved_at=_at(12),
                    observations=(valid_observation,),
                ),
                received_at=_at(12),
            )
        with pytest.raises(MarketDataStoreError) as out_of_window:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(17),
                    observations=(
                        _observation(
                            event_at=context.query.end,
                            available_at=_at(16),
                            fields={"close": "10.00"},
                        ),
                    ),
                ),
                received_at=_at(17),
            )
        with pytest.raises(MarketDataStoreError) as duplicate:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(13),
                    observations=(valid_observation, valid_observation),
                ),
                received_at=_at(13),
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert unregistered.value.code == "PROVIDER_UNREGISTERED"
    assert out_of_window.value.code == "PROVIDER_EVENT_OUT_OF_WINDOW"
    assert duplicate.value.code == "DUPLICATE_PROVIDER_EVENT"
    assert count == 0


@pytest.mark.asyncio
async def test_store_bounds_inline_raw_payload_before_writing_source_evidence(monkeypatch) -> None:
    """An adapter cannot exhaust the canonical store with an arbitrarily large raw receipt."""
    context = _context()
    monkeypatch.setattr(store_module, "MAX_SOURCE_PAYLOAD_BYTES", 32)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        with pytest.raises(MarketDataStoreError) as too_large:
            await MarketDataStore(db).persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(12),
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(11),
                            fields={"close": "10.00"},
                        ),
                    ),
                    raw_payload={"payload": "x" * 128},
                ),
                received_at=_at(12),
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert too_large.value.code == "PROVIDER_PAYLOAD_TOO_LARGE"
    assert count == 0


@pytest.mark.asyncio
async def test_store_rejects_a_receipt_bound_to_another_query_before_writing() -> None:
    """Direct store callers cannot persist a valid receipt for a nearby series/window."""
    context = _context()
    observation = _observation(
        event_at=_at(10),
        available_at=_at(11),
        fields={"close": "10.00"},
    )
    base_result = _result(retrieved_at=_at(12), observations=(observation,))
    mismatched_request = replace(base_result.request, canonical_id="instrument:stock:CN-SSE:600001")

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        with pytest.raises(MarketDataStoreError) as mismatch:
            await MarketDataStore(db).persist_provider_result(
                context,
                replace(base_result, request=mismatched_request),
                received_at=_at(12),
            )
        count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert mismatch.value.code == "PROVIDER_REQUEST_MISMATCH"
    assert count == 0


@pytest.mark.asyncio
async def test_store_uses_local_receipt_time_not_provider_claim_for_pit_visibility() -> None:
    """An old provider timestamp cannot backdate when this platform learned the fact."""
    context = _context()
    observation = _observation(
        event_at=_at(10),
        available_at=_at(10),
        fields={"close": "10.00"},
    )

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(retrieved_at=_at(10), observations=(observation,)),
            received_at=_at(14),
        )
        await db.commit()
        before_receipt = await store.read_observations(context, knowledge_cutoff=_at(13))
        at_business_receipt = await store.read_observations(context, knowledge_cutoff=_at(14))
        # The visibility receipt is deliberately later than ``received_at``:
        # transaction A must commit before transaction B publishes it.
        after_receipt = await store.read_observations(
            context,
            knowledge_cutoff=_at(14).replace(microsecond=1),
        )
        snapshot = await db.get(MdSourceSnapshot, persisted.source_snapshot_id)

    assert before_receipt == ()
    assert at_business_receipt == ()
    assert len(after_receipt) == 1
    assert persisted.received_at == _at(14).replace(microsecond=1)
    assert snapshot is not None
    assert store_module._stored_utc(snapshot.retrieved_at, field_name="snapshot retrieved_at") == _at(14)
    assert (
        store_module._stored_utc(snapshot.source_observed_at, field_name="snapshot observed_at")
        == _at(10)
    )
    assert snapshot.provenance_json["provider_retrieved_at"] == _at(10).isoformat()


@pytest.mark.asyncio
async def test_store_fails_closed_on_series_hash_identity_collision() -> None:
    """A SHA collision or corruption can never silently merge economic series."""
    context = _context()
    identity = MarketDataStore.series_identity(context)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        db.add(
            MdDataSeries(
                id="tampered-series",
                dataset_id=DATASET_ID,
                canonical_id=CANONICAL_ID,
                data_kind="bars",
                frequency="1d",
                semantic_key_sha256=identity.semantic_key_sha256,
                semantic_identity_json={"tampered": True},
            )
        )
        await db.commit()

        with pytest.raises(MarketDataStoreError) as collision:
            await MarketDataStore(db).get_series(context)

    assert collision.value.code == "SERIES_SEMANTIC_COLLISION"


@pytest.mark.asyncio
async def test_calendar_reader_returns_typed_unknown_then_explicit_versioned_sessions() -> None:
    """Calendar coverage is known only from a persisted version and explicit window evidence."""
    context = _context()
    window = TimeWindow(start_at=_at(9), end_at=_at(16))

    async with async_session_maker() as db:
        store = MarketDataStore(db)
        unknown = await store.read_calendar(calendar_code="CN-SSE", window=window)

        snapshot = MdCalendarSnapshot(
            id="calendar-cn-sse-2026-09",
            calendar_code="CN-SSE",
            calendar_version="2026.09",
            timezone_name="Asia/Shanghai",
            snapshot_sha256=_sha("calendar-cn-sse-2026-09"),
            definition_json={
                "coverage_start_at": _at(9).isoformat(),
                "coverage_end_at": _at(16).isoformat(),
            },
            effective_from=date(2026, 9, 8),
            effective_to=date(2026, 9, 8),
        )
        db.add_all(
            [
                snapshot,
                MdCalendarEvent(
                    id="calendar-cn-sse-session-am",
                    calendar_snapshot_id=snapshot.id,
                    trading_date=date(2026, 9, 8),
                    event_type="session",
                    session_code="am",
                    is_trading_day=True,
                    event_start=_at(10),
                    event_end=_at(11),
                    event_payload_json={
                        "coverage": {"data_kind": "bars", "frequency": "1d"},
                        "open": "09:30",
                        "close": "11:30",
                    },
                    event_sha256=_sha("calendar-cn-sse-session-am"),
                ),
                MdCalendarEvent(
                    id="calendar-cn-sse-session-pm",
                    calendar_snapshot_id=snapshot.id,
                    trading_date=date(2026, 9, 8),
                    event_type="session",
                    session_code="pm",
                    is_trading_day=True,
                    event_start=_at(14),
                    event_end=_at(15),
                    event_payload_json={
                        "coverage": {"data_kind": "bars", "frequency": "1d"},
                        "open": "13:00",
                        "close": "15:00",
                    },
                    event_sha256=_sha("calendar-cn-sse-session-pm"),
                ),
                MdPublication(
                    entity_type=PUBLICATION_CALENDAR_SNAPSHOT,
                    entity_id=snapshot.id,
                    entity_sha256=snapshot.snapshot_sha256,
                    published_at=_at(8),
                    created_at=_at(8),
                ),
            ]
        )
        await db.commit()

        known = await store.read_calendar_for_context(context)

    assert unknown.status is CalendarStatus.UNKNOWN
    assert unknown.reason == "CALENDAR_VERSION_NOT_FOUND"
    assert known.status is CalendarStatus.KNOWN
    assert known.calendar_version == "2026.09"
    assert [key.event_at.hour for key in known.event_keys] == [10, 14]
