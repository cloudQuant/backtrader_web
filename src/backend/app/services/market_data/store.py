"""Canonical local persistence for the Iteration 197 market-data path.

The store is intentionally provider-neutral and append-only.  It writes only
the normalized ``md_*`` evidence tables, never a legacy AkShare warehouse
table, and it makes every local read explicit about its point-in-time cutoff.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import MappingProxyType

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_governance import DgProvider
from app.models.market_data_platform import (
    MdCalendarEvent,
    MdCalendarSnapshot,
    MdDataSeries,
    MdObservationRevision,
    MdPublication,
    MdSourceSnapshot,
    calendar_coverage_descriptor,
    calendar_coverage_event_key,
)
from app.services.market_data.coverage import (
    CalendarSnapshot,
    CalendarStatus,
    EventKey,
    Observation,
    ObservationQuality,
    TimeWindow,
)
from app.services.market_data.providers import ProviderFetchResult, ProviderMarketObservation
from app.services.market_data.publication import (
    PUBLICATION_CALENDAR_SNAPSHOT,
    PUBLICATION_SOURCE_SNAPSHOT,
    MarketDataPublicationError,
    MarketDataPublicationManager,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext

UTC = timezone.utc
SERIES_SEMANTIC_VERSION = "market-data-series-v1"
QUALITY_POLICY_VERSION = "required-fields-v1"
NORMALIZATION_VERSION = "market-data-store-v1"
_MAX_PROVIDER_OBSERVATIONS = 50_000
_REVISION_EVENT_QUERY_CHUNK_SIZE = 500
MAX_SOURCE_PAYLOAD_BYTES = 10 * 1024 * 1024
_MAX_NORMALIZED_FIELDS_BYTES = 10 * 1024 * 1024


def _utc_now() -> datetime:
    """Return the trusted local receipt clock used for point-in-time evidence."""
    return datetime.now(UTC)


class MarketDataStoreError(ValueError):
    """Stable failure code for canonical local market-data persistence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SeriesIdentity:
    """Server-derived content identity of a generic normalized data series."""

    semantic_key_sha256: str
    semantic_identity: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PersistedProviderFetch:
    """Identifiers and quality counts created for one immutable provider receipt."""

    series_id: str
    source_snapshot_id: str
    observation_revision_ids: tuple[str, ...]
    passing_observation_count: int
    failed_observation_count: int
    received_at: datetime


@dataclass(frozen=True, slots=True)
class LocalObservationRevision:
    """One selected local observation revision with source provenance."""

    revision_id: str
    source_snapshot_id: str
    event_at: datetime
    available_at: datetime
    committed_at: datetime
    revision_number: int
    quality: ObservationQuality
    fields: Mapping[str, object]

    def as_coverage_observation(self, context: ResolvedMarketDataQueryContext) -> Observation:
        """Convert the persisted row to the pure DTO consumed by coverage planning."""
        return Observation(
            identity=context.coverage_identity,
            event_key=EventKey(self.event_at),
            fields=self.fields,
            quality=self.quality,
            available_at=self.available_at,
        )


@dataclass(frozen=True, slots=True)
class _ValidatedProviderObservation:
    """Validated, JSON-safe provider record prepared before any database write."""

    event_at: datetime
    available_at: datetime
    source_available_at: datetime
    fields: Mapping[str, object]
    fields_sha256: str
    quality: ObservationQuality
    quality_details: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _ValidatedProviderFetch:
    """Validated source receipt data prepared before opening a write savepoint."""

    raw_payload: Mapping[str, object]
    payload_sha256: str
    observations: tuple[_ValidatedProviderObservation, ...]


class MarketDataStore:
    """Write and read normalized market observations through one async session.

    Read-only methods use the request session normally. A provider receipt is
    different: it owns a two-transaction visibility protocol so a strict
    cutoff can never treat a pre-commit flush timestamp as durable evidence.
    The receipt and its pending publication are committed first, then a
    separate transaction publishes their post-commit visibility instant.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or _utc_now
        self._publications = MarketDataPublicationManager(db, clock=self._clock)

    @staticmethod
    def series_identity(context: ResolvedMarketDataQueryContext) -> SeriesIdentity:
        """Derive the stable identity shared by every window of one series.

        Request bounds, pagination, projection fields, consistency mode and
        knowledge cutoff are deliberately excluded.  Those describe one read
        or fetch operation, not the economic content of the resulting series.
        """
        _assert_context_integrity(context)
        coverage = context.coverage_identity
        semantic_identity: dict[str, object] = {
            "series_contract_version": SERIES_SEMANTIC_VERSION,
            "dataset_id": context.storage.dataset_id,
            "dataset_code": coverage.dataset_code,
            "canonical_id": coverage.canonical_id,
            "asset_type": coverage.asset_type,
            "instrument_metadata_version": coverage.instrument_metadata_version,
            "data_kind": coverage.data_kind,
            "frequency": coverage.frequency,
            "market": coverage.market,
            "source_policy_id": coverage.source_policy_id,
            "adjustment": coverage.adjustment,
            "price_basis": coverage.price_basis,
            "currency": coverage.currency,
            "unit": coverage.unit,
        }
        canonical_identity = _canonical_json(semantic_identity, field_name="series identity")
        return SeriesIdentity(
            semantic_key_sha256=_sha256(canonical_identity),
            semantic_identity=MappingProxyType(semantic_identity),
        )

    async def get_series(self, context: ResolvedMarketDataQueryContext) -> MdDataSeries | None:
        """Return an existing exact series, failing closed on a hash collision."""
        identity = self.series_identity(context)
        return await self._find_series(identity, context)

    async def get_or_create_series(self, context: ResolvedMarketDataQueryContext) -> MdDataSeries:
        """Find or create an exact series without trusting a hash by itself."""
        _assert_writable_context(context)
        identity = self.series_identity(context)
        existing = await self._find_series(identity, context)
        if existing is not None:
            return existing

        candidate = MdDataSeries(
            dataset_id=context.storage.dataset_id,
            canonical_id=context.query.canonical_id,
            data_kind=context.query.data_kind,
            frequency=context.query.frequency,
            semantic_key_sha256=identity.semantic_key_sha256,
            semantic_identity_json=dict(identity.semantic_identity),
        )
        try:
            async with self._db.begin_nested():
                self._db.add(candidate)
                await self._db.flush()
        except IntegrityError as exc:
            existing = await self._find_series(identity, context)
            if existing is None:
                raise MarketDataStoreError("SERIES_WRITE_FAILED") from exc
            return existing
        except OperationalError as exc:
            # SQLite has no row-level FOR UPDATE.  Its write lock can reject a
            # concurrent insert rather than wait, so expose a retryable typed
            # conflict instead of leaking a driver-specific exception.
            raise MarketDataStoreError("SERIES_WRITE_CONFLICT") from exc
        return candidate

    async def persist_provider_result(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        *,
        received_at: datetime | None = None,
    ) -> PersistedProviderFetch:
        """Append one provider receipt and its normalized observation revisions.

        Input validation completes before any evidence row is added. The
        source snapshot, revisions and a pending publication receipt share a
        savepoint. After that transaction commits, a second transaction records
        a trusted visibility instant; an interrupted publication stays hidden.
        """
        _assert_writable_context(context)
        local_received_at = _require_aware_utc(
            received_at or self._clock(),
            field_name="local receipt timestamp",
        )
        validated = _validate_provider_fetch(
            context,
            result,
            local_received_at=local_received_at,
        )
        provider = await self._require_active_provider(result.provider_id)

        try:
            async with self._db.begin_nested():
                series = await self.get_or_create_series(context)
                series = await self._lock_series_for_revision(series, context)
                source_snapshot = self._make_source_snapshot(
                    context,
                    provider,
                    result,
                    validated,
                    local_received_at=local_received_at,
                )
                self._db.add(source_snapshot)
                await self._db.flush()
                publication = await self._publications.stage(
                    entity_type=PUBLICATION_SOURCE_SNAPSHOT,
                    entity_id=source_snapshot.id,
                    entity_sha256=source_snapshot.payload_sha256,
                )

                revision_numbers = await self._next_revision_numbers(
                    series_id=series.id,
                    event_times=tuple(item.event_at for item in validated.observations),
                )
                revisions = [
                    self._make_observation_revision(
                        series=series,
                        source_snapshot=source_snapshot,
                        result=result,
                        observation=observation,
                        revision_number=revision_numbers[observation.event_at],
                        local_received_at=local_received_at,
                    )
                    for observation in validated.observations
                ]
                self._db.add_all(revisions)
                await self._db.flush()
        except IntegrityError as exc:
            raise MarketDataStoreError("OBSERVATION_WRITE_FAILED") from exc
        except OperationalError as exc:
            raise MarketDataStoreError("OBSERVATION_WRITE_CONFLICT") from exc

        try:
            # The actual data transaction must finish before a trusted local
            # visibility instant is sampled.  Query-service callers never mix
            # unrelated writes into this session; a separate API transaction
            # remains the boundary for any future mixed workflow.
            await self._db.commit()
            published_at = await self._publications.publish_staged(
                (publication.id,),
                not_before=local_received_at,
            )
        except (MarketDataPublicationError, OperationalError) as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError("OBSERVATION_PUBLICATION_FAILED") from exc

        return PersistedProviderFetch(
            series_id=series.id,
            source_snapshot_id=source_snapshot.id,
            observation_revision_ids=tuple(revision.id for revision in revisions),
            passing_observation_count=sum(
                item.quality is ObservationQuality.PASS for item in validated.observations
            ),
            failed_observation_count=sum(
                item.quality is ObservationQuality.FAILED for item in validated.observations
            ),
            received_at=published_at,
        )

    async def read_observation_revisions(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
    ) -> tuple[LocalObservationRevision, ...]:
        """Select the newest locally usable revision per event at a PIT cutoff.

        A series deliberately does not include a field projection. A later,
        narrower request can therefore append a revision that has fewer fields
        than an older revision for the same event. Selecting that row
        unconditionally would hide a complete local fact and make a broader
        follow-up request fetch the network again. Prefer the newest revision
        that is PASS and satisfies this request's required fields; retain the
        newest fallback only when no usable revision exists so coverage can
        still report the rejection deterministically.
        """
        _assert_context_integrity(context)
        cutoff = _require_aware_utc(knowledge_cutoff, field_name="knowledge_cutoff")
        series = await self.get_series(context)
        if series is None:
            return ()

        query = context.query
        rows = list(
            (
                await self._db.execute(
                    select(MdObservationRevision, MdPublication.published_at)
                    .join(
                        MdSourceSnapshot,
                        MdSourceSnapshot.id == MdObservationRevision.source_snapshot_id,
                    )
                    .join(
                        MdPublication,
                        and_(
                            MdPublication.entity_type == PUBLICATION_SOURCE_SNAPSHOT,
                            MdPublication.entity_id == MdSourceSnapshot.id,
                        ),
                    )
                    .where(
                        MdObservationRevision.series_id == series.id,
                        MdObservationRevision.event_time >= query.start,
                        MdObservationRevision.event_time < query.end,
                        MdObservationRevision.available_at <= cutoff,
                        MdPublication.entity_sha256 == MdSourceSnapshot.payload_sha256,
                        MdPublication.published_at.is_not(None),
                        MdPublication.published_at <= cutoff,
                    )
                    .order_by(
                        MdObservationRevision.event_time,
                        MdObservationRevision.available_at,
                        MdPublication.published_at,
                        MdObservationRevision.revision_number,
                        MdObservationRevision.id,
                    )
                )
            )
            .all()
        )

        selected_usable: dict[datetime, LocalObservationRevision] = {}
        selected_fallback: dict[datetime, LocalObservationRevision] = {}
        for row, published_at in rows:
            if published_at is None:
                raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
            local = _decode_local_revision(
                row,
                context=context,
                cutoff=cutoff,
                published_at=_stored_utc(published_at, field_name="publication published_at"),
            )
            current_fallback = selected_fallback.get(local.event_at)
            if current_fallback is None or _revision_sort_key(local) > _revision_sort_key(
                current_fallback
            ):
                selected_fallback[local.event_at] = local
            if not _revision_is_usable_for_fields(local, context.query.required_fields):
                continue
            current_usable = selected_usable.get(local.event_at)
            if current_usable is None or _revision_sort_key(local) > _revision_sort_key(
                current_usable
            ):
                selected_usable[local.event_at] = local
        return tuple(
            selected_usable.get(event_at, selected_fallback[event_at])
            for event_at in sorted(selected_fallback)
        )

    async def read_observations(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
    ) -> tuple[Observation, ...]:
        """Return local observations in the pure shape expected by coverage planning."""
        revisions = await self.read_observation_revisions(
            context,
            knowledge_cutoff=knowledge_cutoff,
        )
        return tuple(item.as_coverage_observation(context) for item in revisions)

    async def read_calendar(
        self,
        *,
        calendar_code: str,
        window: TimeWindow,
        calendar_version: str | None = None,
        knowledge_cutoff: datetime | None = None,
        data_kind: str = "bars",
        frequency: str = "1d",
    ) -> CalendarSnapshot:
        """Return one explicit calendar version or a typed unknown result.

        A calendar becomes ``KNOWN`` only when its persisted definition carries
        an explicit ``coverage_start_at``/``coverage_end_at`` pair (or the
        equivalent nested ``coverage_window`` mapping).  Weekdays, holidays,
        and missing sessions are never inferred by this reader.
        """
        code = _require_text(calendar_code, field_name="calendar_code", maximum=128)
        requested_data_kind = _require_text(data_kind, field_name="calendar data_kind", maximum=64)
        requested_frequency = _require_text(
            frequency,
            field_name="calendar frequency",
            maximum=16,
        )
        if not isinstance(window, TimeWindow):
            raise TypeError("window must be a TimeWindow")
        version = (
            _require_text(calendar_version, field_name="calendar_version", maximum=128)
            if calendar_version is not None
            else None
        )
        cutoff = (
            _require_aware_utc(knowledge_cutoff, field_name="knowledge_cutoff")
            if knowledge_cutoff is not None
            else None
        )

        statement = (
            select(MdCalendarSnapshot, MdPublication.published_at)
            .join(
                MdPublication,
                and_(
                    MdPublication.entity_type == PUBLICATION_CALENDAR_SNAPSHOT,
                    MdPublication.entity_id == MdCalendarSnapshot.id,
                ),
            )
            .where(
                MdCalendarSnapshot.calendar_code == code,
                MdPublication.entity_sha256 == MdCalendarSnapshot.snapshot_sha256,
                MdPublication.published_at.is_not(None),
            )
        )
        if version is not None:
            statement = statement.where(MdCalendarSnapshot.calendar_version == version)
        raw_rows = list((await self._db.execute(statement)).all())
        rows: list[tuple[MdCalendarSnapshot, datetime]] = []
        for row, published_at in raw_rows:
            if published_at is None:
                continue
            visible_at = _stored_utc(published_at, field_name="calendar publication")
            if cutoff is not None and visible_at > cutoff:
                continue
            rows.append((row, visible_at))

        usable: list[tuple[MdCalendarSnapshot, TimeWindow, datetime]] = []
        saw_integrity_error = False
        for row, published_at in rows:
            try:
                coverage_window = _calendar_coverage_window(row)
            except MarketDataStoreError:
                saw_integrity_error = True
                continue
            if coverage_window.end_at > window.start_at and coverage_window.start_at < window.end_at:
                usable.append((row, coverage_window, published_at))

        unknown_timezone = _unknown_timezone([row for row, _published_at in rows])
        unknown_version = version or "unresolved"
        if not usable:
            if not rows:
                reason = "CALENDAR_VERSION_NOT_FOUND"
            elif saw_integrity_error:
                reason = "CALENDAR_INTEGRITY"
            else:
                reason = "CALENDAR_WINDOW_NOT_COVERED"
            return CalendarSnapshot.unknown(
                calendar_id=code,
                calendar_version=unknown_version,
                timezone_name=unknown_timezone,
                reason=reason,
            )
        if version is not None:
            exact = [item for item in usable if _window_covers(item[1], window)]
            if len(exact) != 1:
                return CalendarSnapshot.unknown(
                    calendar_id=code,
                    calendar_version=version,
                    timezone_name=unknown_timezone,
                    reason=(
                        "CALENDAR_AMBIGUOUS_VERSION"
                        if len(exact) > 1
                        else "CALENDAR_WINDOW_NOT_COVERED"
                    ),
                )
            selected = exact
        else:
            selected = _compose_calendar_segments(usable, window)
        if selected is None:
            return CalendarSnapshot.unknown(
                calendar_id=code,
                calendar_version=unknown_version,
                timezone_name=unknown_timezone,
                reason="CALENDAR_WINDOW_NOT_COVERED",
            )
        try:
            snapshots = [item[0] for item in selected]
            if len({snapshot.timezone_name for snapshot in snapshots}) != 1:
                raise MarketDataStoreError("CALENDAR_INTEGRITY")
            event_keys: list[EventKey] = []
            for snapshot, coverage_window, _published_at in selected:
                event_keys.extend(
                    await self._calendar_event_keys(
                        snapshot,
                        coverage_window,
                        requested_window=window,
                        data_kind=requested_data_kind,
                        frequency=requested_frequency,
                    )
                )
            deduplicated = tuple(sorted(set(event_keys)))
            if len(deduplicated) != len(event_keys):
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            return CalendarSnapshot(
                calendar_id=code,
                calendar_version=_composed_calendar_version(selected),
                timezone_name=snapshots[0].timezone_name,
                coverage_window=window,
                event_keys=deduplicated,
                status=CalendarStatus.KNOWN,
            )
        except MarketDataStoreError as exc:
            return CalendarSnapshot.unknown(
                calendar_id=code,
                calendar_version=_composed_calendar_version(selected),
                timezone_name=_unknown_timezone([item[0] for item in selected]),
                reason=exc.code,
            )
        except (TypeError, ValueError):
            return CalendarSnapshot.unknown(
                calendar_id=code,
                calendar_version=_composed_calendar_version(selected),
                timezone_name=_unknown_timezone([item[0] for item in selected]),
                reason="CALENDAR_EVENT_INTEGRITY",
            )

    async def read_calendar_for_context(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        calendar_version: str | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> CalendarSnapshot:
        """Load calendar evidence for a resolved query's exact market and window."""
        _assert_context_integrity(context)
        return await self.read_calendar(
            calendar_code=context.coverage_identity.market,
            window=TimeWindow(start_at=context.query.start, end_at=context.query.end),
            calendar_version=calendar_version,
            knowledge_cutoff=knowledge_cutoff,
            data_kind=context.query.data_kind,
            frequency=context.query.frequency or "snapshot",
        )

    async def _find_series(
        self,
        identity: SeriesIdentity,
        context: ResolvedMarketDataQueryContext,
    ) -> MdDataSeries | None:
        rows = list(
            (
                await self._db.execute(
                    select(MdDataSeries).where(
                        MdDataSeries.semantic_key_sha256 == identity.semantic_key_sha256
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(rows) > 1:
            raise MarketDataStoreError("SERIES_INTEGRITY")
        if not rows:
            return None
        series = rows[0]
        _assert_series_matches_context(series, identity, context)
        return series

    async def _require_active_provider(self, provider_id: str) -> DgProvider:
        rows = list(
            (
                await self._db.execute(
                    select(DgProvider).where(DgProvider.provider_id == provider_id)
                )
            )
            .scalars()
            .all()
        )
        exact = [row for row in rows if row.provider_id == provider_id]
        if len(exact) != 1:
            raise MarketDataStoreError("PROVIDER_UNREGISTERED")
        if not exact[0].is_active:
            raise MarketDataStoreError("PROVIDER_INACTIVE")
        return exact[0]

    async def ensure_provider_active(self, provider_id: str) -> None:
        """Authorize an expected receipt provider before a route invokes it.

        ``persist_provider_result`` repeats this check for the actual receipt,
        but performing it here prevents a revoked or unregistered paid source
        from receiving an outbound request merely to be rejected afterwards.
        """
        normalized = _require_text(provider_id, field_name="provider_id", maximum=255)
        await self._require_active_provider(normalized)

    def _make_source_snapshot(
        self,
        context: ResolvedMarketDataQueryContext,
        provider: DgProvider,
        result: ProviderFetchResult,
        validated: _ValidatedProviderFetch,
        *,
        local_received_at: datetime,
    ) -> MdSourceSnapshot:
        provider_id = _require_text(result.provider_id, field_name="provider_id", maximum=255)
        platform = _require_text(
            provider_id.split(":", maxsplit=1)[0],
            field_name="provider platform",
            maximum=64,
        )
        source_revision = _require_text(
            result.source_revision,
            field_name="source_revision",
            maximum=128,
        )
        adapter_id = _require_text(f"{platform}.market-data", field_name="adapter_id", maximum=128)
        request_json = _json_safe_mapping(
            {
                "provider_request": result.request.dto_payload,
                "resolved_query": context.query.semantic_payload(),
            },
            field_name="source request",
        )
        payload_manifest = {
            "format": "inline-json",
            "raw_payload": dict(validated.raw_payload),
            "observation_count": len(validated.observations),
        }
        provenance = {
            "provider_id": provider.provider_id,
            "source_revision": source_revision,
            "provider_retrieved_at": result.retrieved_at.isoformat(),
            "local_received_at": local_received_at.isoformat(),
            "warnings": list(result.warnings),
            "normalization_version": NORMALIZATION_VERSION,
        }
        return MdSourceSnapshot(
            provider_id=provider.id,
            platform=platform,
            source_id=provider_id,
            adapter_id=adapter_id,
            endpoint_version=source_revision,
            request_fingerprint_sha256=context.query.query_fingerprint,
            payload_sha256=validated.payload_sha256,
            request_json=request_json,
            payload_manifest_json=_json_safe_mapping(
                payload_manifest, field_name="payload manifest"
            ),
            provenance_json=_json_safe_mapping(provenance, field_name="source provenance"),
            source_observed_at=result.retrieved_at,
            retrieved_at=local_received_at,
        )

    async def _next_revision_numbers(
        self,
        *,
        series_id: str,
        event_times: Sequence[datetime],
    ) -> dict[datetime, int]:
        if not event_times:
            return {}
        existing_maximums: dict[datetime, int] = {}
        for event_time_chunk in _chunks(tuple(event_times), _REVISION_EVENT_QUERY_CHUNK_SIZE):
            rows = (
                await self._db.execute(
                    select(
                        MdObservationRevision.event_time,
                        func.max(MdObservationRevision.revision_number),
                    )
                    .where(
                        MdObservationRevision.series_id == series_id,
                        MdObservationRevision.event_time.in_(event_time_chunk),
                    )
                    .group_by(MdObservationRevision.event_time)
                )
            ).all()
            for event_time, maximum in rows:
                existing_maximums[_stored_utc(event_time, field_name="revision event_time")] = int(
                    maximum or 0
                )
        return {event_time: existing_maximums.get(event_time, 0) + 1 for event_time in event_times}

    async def _lock_series_for_revision(
        self,
        series: MdDataSeries,
        context: ResolvedMarketDataQueryContext,
    ) -> MdDataSeries:
        """Serialize per-series revision-number allocation on engines with row locks.

        PostgreSQL and MySQL honour ``FOR UPDATE`` here, so concurrent source
        receipts cannot both allocate the same next revision number for an
        event.  SQLite serializes writes at database level; the explicit lock
        remains a harmless no-op there while keeping the service contract
        uniform across the supported engines.
        """
        locked = await self._db.scalar(
            select(MdDataSeries).where(MdDataSeries.id == series.id).with_for_update()
        )
        if locked is None:
            raise MarketDataStoreError("SERIES_WRITE_CONFLICT")
        _assert_series_matches_context(
            locked,
            self.series_identity(context),
            context,
        )
        return locked

    @staticmethod
    def _make_observation_revision(
        *,
        series: MdDataSeries,
        source_snapshot: MdSourceSnapshot,
        result: ProviderFetchResult,
        observation: _ValidatedProviderObservation,
        revision_number: int,
        local_received_at: datetime,
    ) -> MdObservationRevision:
        revision_payload = {
            "revision_contract_version": "market-data-observation-revision-v1",
            "series_semantic_key_sha256": series.semantic_key_sha256,
            "source_snapshot_id": source_snapshot.id,
            "event_at": observation.event_at.isoformat(),
            "available_at": observation.available_at.isoformat(),
            "fields_sha256": observation.fields_sha256,
            "quality_status": observation.quality.value,
            "revision_number": revision_number,
        }
        provenance = {
            "provider_id": result.provider_id,
            "source_revision": result.source_revision,
            "source_snapshot_id": source_snapshot.id,
            "provider_available_at": observation.source_available_at.isoformat(),
            "local_received_at": local_received_at.isoformat(),
        }
        return MdObservationRevision(
            series_id=series.id,
            event_time=observation.event_at,
            available_at=observation.available_at,
            source_snapshot_id=source_snapshot.id,
            quality_status=observation.quality.value,
            quality_policy_version=QUALITY_POLICY_VERSION,
            quality_details_json=dict(observation.quality_details),
            fields_json=dict(observation.fields),
            fields_sha256=observation.fields_sha256,
            revision_number=revision_number,
            revision_key_sha256=_sha256(
                _canonical_json(revision_payload, field_name="revision identity")
            ),
            normalization_version=NORMALIZATION_VERSION,
            provenance_json=_json_safe_mapping(provenance, field_name="revision provenance"),
            committed_at=local_received_at,
        )

    async def _calendar_event_keys(
        self,
        snapshot: MdCalendarSnapshot,
        coverage_window: TimeWindow,
        *,
        requested_window: TimeWindow,
        data_kind: str,
        frequency: str,
    ) -> tuple[EventKey, ...]:
        event_window = _window_intersection(coverage_window, requested_window)
        await self._assert_calendar_grid_declared(
            snapshot,
            coverage_window,
            data_kind=data_kind,
            frequency=frequency,
        )
        rows = list(
            (
                await self._db.execute(
                    select(MdCalendarEvent)
                    .where(
                        MdCalendarEvent.calendar_snapshot_id == snapshot.id,
                        MdCalendarEvent.event_start.is_not(None),
                        MdCalendarEvent.event_start >= event_window.start_at,
                        MdCalendarEvent.event_start < event_window.end_at,
                    )
                    .order_by(MdCalendarEvent.event_start, MdCalendarEvent.id)
                )
            )
            .scalars()
            .all()
        )
        event_keys: list[EventKey] = []
        seen: set[datetime] = set()
        for row in rows:
            if not row.is_trading_day or row.event_type != "session":
                if calendar_coverage_descriptor(row.event_payload_json) is not None:
                    raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
                continue
            try:
                descriptor = calendar_coverage_descriptor(row.event_payload_json)
            except ValueError as exc:
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY") from exc
            if descriptor is None:
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            if descriptor != (data_kind, frequency):
                continue
            if row.event_start is None:
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            event_at = _stored_utc(row.event_start, field_name="calendar event_start")
            try:
                expected_coverage_key = calendar_coverage_event_key(
                    event_start=event_at,
                    data_kind=data_kind,
                    frequency=frequency,
                )
            except ValueError as exc:
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY") from exc
            if row.coverage_event_key != expected_coverage_key:
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            if not coverage_window.contains(EventKey(event_at)):
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            if not event_window.contains(EventKey(event_at)):
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            if event_at in seen:
                raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
            seen.add(event_at)
            event_keys.append(EventKey(event_at))
        return tuple(sorted(event_keys))

    async def _assert_calendar_grid_declared(
        self,
        snapshot: MdCalendarSnapshot,
        coverage_window: TimeWindow,
        *,
        data_kind: str,
        frequency: str,
    ) -> None:
        """Prove a frequency grid exists without loading the whole snapshot.

        A holiday or weekend request can legitimately contain no expected
        event.  It is still known only if the snapshot declares the requested
        grid elsewhere.  The materialized coverage key gives that proof in one
        indexed, bounded witness query rather than scanning every event in a
        long-lived calendar segment.
        """
        key_prefix = f"{data_kind}:{frequency}@"
        witness = await self._db.scalar(
            select(MdCalendarEvent)
            .where(
                MdCalendarEvent.calendar_snapshot_id == snapshot.id,
                MdCalendarEvent.coverage_event_key.startswith(key_prefix, autoescape=True),
            )
            .order_by(MdCalendarEvent.event_start, MdCalendarEvent.id)
            .limit(1)
        )
        if witness is None:
            raise MarketDataStoreError("CALENDAR_GRID_UNAVAILABLE")
        if not witness.is_trading_day or witness.event_type != "session" or witness.event_start is None:
            raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")
        try:
            descriptor = calendar_coverage_descriptor(witness.event_payload_json)
            event_at = _stored_utc(witness.event_start, field_name="calendar event_start")
            expected_coverage_key = calendar_coverage_event_key(
                event_start=event_at,
                data_kind=data_kind,
                frequency=frequency,
            )
        except ValueError as exc:
            raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY") from exc
        if (
            descriptor != (data_kind, frequency)
            or witness.coverage_event_key != expected_coverage_key
            or not coverage_window.contains(EventKey(event_at))
        ):
            raise MarketDataStoreError("CALENDAR_EVENT_INTEGRITY")


def _assert_context_integrity(context: ResolvedMarketDataQueryContext) -> None:
    """Ensure a manually assembled context cannot cross-wire series dimensions."""
    if not isinstance(context, ResolvedMarketDataQueryContext):
        raise TypeError("context must be a ResolvedMarketDataQueryContext")
    query = context.query
    identity = context.identity
    coverage = context.coverage_identity
    if (
        query.dataset_code != context.storage.dataset_code
        or query.dataset_code != coverage.dataset_code
        or query.canonical_id != identity.canonical_id
        or query.canonical_id != coverage.canonical_id
        or query.instrument_metadata_version != identity.metadata_version
        or query.instrument_metadata_version != coverage.instrument_metadata_version
        or identity.asset_type != coverage.asset_type
        or identity.venue != coverage.market
        or query.data_kind != coverage.data_kind
        or (query.frequency or "snapshot") != coverage.frequency
        or query.source_policy_id != coverage.source_policy_id
        or query.adjustment != coverage.adjustment
        or query.price_basis != coverage.price_basis
        or query.currency != coverage.currency
        or query.unit != coverage.unit
    ):
        raise MarketDataStoreError("QUERY_CONTEXT_INTEGRITY")
    _require_text(context.storage.dataset_id, field_name="dataset_id", maximum=36)


def _assert_writable_context(context: ResolvedMarketDataQueryContext) -> None:
    """Reject a catalog binding that has not opted into canonical writes."""
    _assert_context_integrity(context)
    if context.storage.write_mode not in {"canonical_read_write", "canonical_append_only"}:
        raise MarketDataStoreError("DATASET_STORAGE_NOT_WRITABLE")


def _assert_series_matches_context(
    series: MdDataSeries,
    identity: SeriesIdentity,
    context: ResolvedMarketDataQueryContext,
) -> None:
    """Detect a persisted structured-identity mismatch behind the same hash."""
    try:
        stored_identity = _json_safe_mapping(
            series.semantic_identity_json,
            field_name="persisted series identity",
        )
    except MarketDataStoreError as exc:
        raise MarketDataStoreError("SERIES_SEMANTIC_COLLISION") from exc
    if (
        series.semantic_key_sha256 != identity.semantic_key_sha256
        or _canonical_json(stored_identity, field_name="persisted series identity")
        != _canonical_json(identity.semantic_identity, field_name="series identity")
        or series.dataset_id != context.storage.dataset_id
        or series.canonical_id != context.query.canonical_id
        or series.data_kind != context.query.data_kind
        or series.frequency != context.query.frequency
    ):
        raise MarketDataStoreError("SERIES_SEMANTIC_COLLISION")


def _validate_provider_fetch(
    context: ResolvedMarketDataQueryContext,
    result: ProviderFetchResult,
    *,
    local_received_at: datetime,
) -> _ValidatedProviderFetch:
    """Validate all provider facts before the store creates a source receipt."""
    _assert_context_integrity(context)
    if not isinstance(result, ProviderFetchResult):
        raise TypeError("result must be a ProviderFetchResult")
    if not _provider_request_matches_context(context, result.request):
        raise MarketDataStoreError("PROVIDER_REQUEST_MISMATCH")
    received_at = _require_aware_utc(
        local_received_at,
        field_name="local receipt timestamp",
    )
    if result.retrieved_at > received_at:
        raise MarketDataStoreError("PROVIDER_RETRIEVED_AT_FUTURE")
    if len(result.observations) > _MAX_PROVIDER_OBSERVATIONS:
        raise MarketDataStoreError("PROVIDER_OBSERVATION_LIMIT_EXCEEDED")
    raw_payload = _json_safe_mapping(result.raw_payload, field_name="provider raw_payload")
    canonical_raw_payload = _canonical_json(raw_payload, field_name="provider raw_payload")
    if len(canonical_raw_payload.encode("utf-8")) > MAX_SOURCE_PAYLOAD_BYTES:
        raise MarketDataStoreError("PROVIDER_PAYLOAD_TOO_LARGE")
    observations: list[_ValidatedProviderObservation] = []
    seen_events: set[datetime] = set()
    required_fields = frozenset(context.query.required_fields)
    normalized_fields_bytes = 0
    for observation in result.observations:
        if not isinstance(observation, ProviderMarketObservation):
            raise TypeError("provider observations must be ProviderMarketObservation values")
        event_at = _require_aware_utc(observation.event_at, field_name="provider event_at")
        available_at = _require_aware_utc(
            observation.available_at,
            field_name="provider available_at",
        )
        if not context.query.start <= event_at < context.query.end:
            raise MarketDataStoreError("PROVIDER_EVENT_OUT_OF_WINDOW")
        if event_at in seen_events:
            raise MarketDataStoreError("DUPLICATE_PROVIDER_EVENT")
        if available_at > result.retrieved_at:
            raise MarketDataStoreError("PROVIDER_AVAILABILITY_AFTER_RETRIEVAL")
        seen_events.add(event_at)
        fields = _json_safe_mapping(observation.fields, field_name="provider observation fields")
        canonical_fields = _canonical_json(fields, field_name="provider observation fields")
        normalized_fields_bytes += len(canonical_fields.encode("utf-8"))
        if normalized_fields_bytes > _MAX_NORMALIZED_FIELDS_BYTES:
            raise MarketDataStoreError("PROVIDER_NORMALIZED_FIELDS_TOO_LARGE")
        missing_required_fields = tuple(
            field_name
            for field_name in sorted(required_fields)
            if not _has_usable_value(observation.fields.get(field_name))
        )
        quality = (
            ObservationQuality.PASS if not missing_required_fields else ObservationQuality.FAILED
        )
        quality_details: dict[str, object] = {
            "required_fields": sorted(required_fields),
            "missing_required_fields": list(missing_required_fields),
        }
        observations.append(
            _ValidatedProviderObservation(
                event_at=event_at,
                # A provider may state that a value was published earlier,
                # but an interactive collection only becomes locally knowable
                # once this process has received its receipt.  Persist the
                # trusted local timestamp for PIT eligibility and retain the
                # upstream claim in revision provenance below.
                available_at=received_at,
                source_available_at=available_at,
                fields=MappingProxyType(fields),
                fields_sha256=_sha256(canonical_fields),
                quality=quality,
                quality_details=MappingProxyType(quality_details),
            )
        )
    return _ValidatedProviderFetch(
        raw_payload=MappingProxyType(raw_payload),
        payload_sha256=_sha256(canonical_raw_payload),
        observations=tuple(observations),
    )


def _provider_request_matches_context(
    context: ResolvedMarketDataQueryContext,
    request: object,
) -> bool:
    """Bind a receipt's immutable request to every resolved query dimension.

    The query service also compares a receipt to the exact route request,
    including the provider adapter name.  This independent store check keeps
    direct writers from persisting a receipt for another identity, time window,
    semantic series, or source policy.
    """
    from app.services.market_data.providers import MarketDataProviderRequest

    if not isinstance(request, MarketDataProviderRequest):
        return False
    venue = context.identity.venue
    return (
        venue is not None
        and request.query_fingerprint == context.query.query_fingerprint
        and request.canonical_id == context.query.canonical_id
        and request.asset_type == context.identity.asset_type
        and request.provider_symbol == context.identity.identity.display_symbol
        and request.market == venue
        and request.data_kind == context.query.data_kind
        and request.frequency == (context.query.frequency or "snapshot")
        and request.start_at == context.query.start
        and request.end_at == context.query.end
        and request.required_fields == frozenset(context.query.required_fields)
        and request.adjustment == context.query.adjustment
        and request.price_basis == context.query.price_basis
        and request.currency == context.query.currency
        and request.unit == context.query.unit
        and request.source_policy_id == context.query.source_policy_id
    )


def _decode_local_revision(
    row: MdObservationRevision,
    *,
    context: ResolvedMarketDataQueryContext,
    cutoff: datetime,
    published_at: datetime,
) -> LocalObservationRevision:
    """Validate a persisted row before it can contribute local coverage."""
    event_at = _stored_utc(row.event_time, field_name="observation event_time")
    available_at = _stored_utc(row.available_at, field_name="observation available_at")
    # ``row.committed_at`` records receipt processing time from the legacy
    # immutable evidence shape. The publication receipt is the only trusted
    # local visibility boundary for a strict replay.
    committed_at = _stored_utc(published_at, field_name="publication published_at")
    if not context.query.start <= event_at < context.query.end:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    if available_at > cutoff or committed_at > cutoff:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    try:
        quality = ObservationQuality(row.quality_status)
        fields = _json_safe_mapping(row.fields_json, field_name="persisted observation fields")
    except (MarketDataStoreError, ValueError) as exc:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY") from exc
    if (
        _sha256(_canonical_json(fields, field_name="persisted observation fields"))
        != row.fields_sha256
    ):
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    if not isinstance(row.revision_number, int) or row.revision_number < 1:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    return LocalObservationRevision(
        revision_id=row.id,
        source_snapshot_id=row.source_snapshot_id,
        event_at=event_at,
        available_at=available_at,
        committed_at=committed_at,
        revision_number=row.revision_number,
        quality=quality,
        fields=MappingProxyType(fields),
    )


def _calendar_coverage_window(snapshot: MdCalendarSnapshot) -> TimeWindow:
    """Read explicit calendar coverage metadata without deriving a weekday rule."""
    definition = _json_safe_mapping(snapshot.definition_json, field_name="calendar definition")
    raw_window = definition.get("coverage_window")
    if raw_window is not None:
        if not isinstance(raw_window, Mapping):
            raise MarketDataStoreError("CALENDAR_INTEGRITY")
        start_value = raw_window.get("start_at")
        end_value = raw_window.get("end_at")
    else:
        start_value = definition.get("coverage_start_at")
        end_value = definition.get("coverage_end_at")
    if not isinstance(start_value, str) or not isinstance(end_value, str):
        raise MarketDataStoreError("CALENDAR_INTEGRITY")
    try:
        return TimeWindow(
            start_at=_parse_timestamp(start_value, field_name="calendar coverage_start_at"),
            end_at=_parse_timestamp(end_value, field_name="calendar coverage_end_at"),
        )
    except (TypeError, ValueError) as exc:
        raise MarketDataStoreError("CALENDAR_INTEGRITY") from exc


def _window_covers(coverage_window: TimeWindow, requested_window: TimeWindow) -> bool:
    """Return whether explicitly advertised calendar evidence covers a request."""
    return (
        coverage_window.start_at <= requested_window.start_at
        and requested_window.end_at <= coverage_window.end_at
    )


def _window_intersection(left: TimeWindow, right: TimeWindow) -> TimeWindow:
    """Return a non-empty half-open overlap without widening either evidence window."""
    start_at = max(left.start_at, right.start_at)
    end_at = min(left.end_at, right.end_at)
    if end_at <= start_at:
        raise MarketDataStoreError("CALENDAR_WINDOW_NOT_COVERED")
    return TimeWindow(start_at=start_at, end_at=end_at)


def _compose_calendar_segments(
    candidates: Sequence[tuple[MdCalendarSnapshot, TimeWindow, datetime]],
    requested: TimeWindow,
) -> list[tuple[MdCalendarSnapshot, TimeWindow, datetime]] | None:
    """Select contiguous immutable blocks that prove one full calendar window.

    Import serialization rejects overlaps. This reader repeats that invariant
    defensively and concatenates adjacent rolling manifests without inventing
    weekday or holiday behavior. A gap remains an unknown calendar.
    """
    selected: list[tuple[MdCalendarSnapshot, TimeWindow, datetime]] = []
    cursor = requested.start_at
    ordered = sorted(candidates, key=lambda item: (item[1].start_at, item[1].end_at, item[0].id))
    for candidate in ordered:
        _snapshot, coverage, _published_at = candidate
        if coverage.end_at <= cursor:
            continue
        if coverage.start_at > cursor:
            break
        if selected and coverage.start_at < cursor:
            return None
        selected.append(candidate)
        cursor = coverage.end_at
        if cursor >= requested.end_at:
            return selected
    return None


def _composed_calendar_version(
    segments: Sequence[tuple[MdCalendarSnapshot, TimeWindow, datetime]],
) -> str:
    """Return a bounded audit label for one or more immutable calendar blocks."""
    versions = tuple(item[0].calendar_version for item in segments)
    if len(versions) == 1:
        return versions[0]
    digest = hashlib.sha256("|".join(versions).encode("utf-8")).hexdigest()[:24]
    return f"composed:{digest}"


def _unknown_timezone(rows: Sequence[MdCalendarSnapshot]) -> str:
    """Select a valid declared timezone when possible, otherwise use UTC for unknown DTOs."""
    for row in rows:
        try:
            CalendarSnapshot.unknown(
                calendar_id="unknown",
                calendar_version="unknown",
                timezone_name=row.timezone_name,
                reason="unknown",
            )
        except (TypeError, ValueError):
            continue
        return row.timezone_name
    return "UTC"


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    """Parse an explicit JSON timestamp while requiring an offset."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return _require_aware_utc(parsed, field_name=field_name)


def _require_aware_utc(value: datetime, *, field_name: str) -> datetime:
    """Validate a public/provider timestamp instead of assuming its timezone."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataStoreError("TIMESTAMP_INVALID")
    return value.astimezone(UTC)


def _stored_utc(value: datetime, *, field_name: str) -> datetime:
    """Read a timestamp stored by this service, treating SQLite naive values as UTC."""
    if not isinstance(value, datetime):
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_text(value: object, *, field_name: str, maximum: int) -> str:
    """Require a bounded non-empty string before it reaches a relational column."""
    if not isinstance(value, str):
        raise MarketDataStoreError("TEXT_VALUE_INVALID")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise MarketDataStoreError("TEXT_VALUE_INVALID")
    return normalized


def _json_safe_mapping(value: object, *, field_name: str) -> dict[str, object]:
    """Return a recursively JSON-safe mapping with deterministic primitive values."""
    normalized = _json_safe(value, field_name=field_name)
    if not isinstance(normalized, dict):
        raise MarketDataStoreError("JSON_VALUE_UNSAFE")
    return normalized


def _json_safe(value: object, *, field_name: str) -> object:
    """Normalize only values that can be stored and hashed without Python repr fallbacks."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MarketDataStoreError("JSON_VALUE_UNSAFE")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise MarketDataStoreError("JSON_VALUE_UNSAFE")
        return format(value, "f")
    if isinstance(value, datetime):
        return _require_aware_utc(value, field_name=field_name).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        normalized_mapping: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise MarketDataStoreError("JSON_VALUE_UNSAFE")
            normalized_mapping[key] = _json_safe(item, field_name=field_name)
        return normalized_mapping
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, field_name=field_name) for item in value]
    raise MarketDataStoreError("JSON_VALUE_UNSAFE")


def _canonical_json(value: object, *, field_name: str) -> str:
    """Serialize a JSON-safe value once, with stable ordering for SHA-256 identities."""
    try:
        return json.dumps(
            _json_safe(value, field_name=field_name),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise MarketDataStoreError("JSON_VALUE_UNSAFE") from exc


def _sha256(value: str) -> str:
    """Return a lowercase SHA-256 digest for a canonical JSON representation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _has_usable_value(value: object) -> bool:
    """Apply the same basic missing-value semantics used by coverage planning."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return True


def _revision_is_usable_for_fields(
    revision: LocalObservationRevision,
    required_fields: Sequence[str],
) -> bool:
    """Return whether a persisted revision can satisfy this field projection."""
    return revision.quality is ObservationQuality.PASS and all(
        _has_usable_value(revision.fields.get(field_name)) for field_name in required_fields
    )


def _chunks(values: Sequence[datetime], size: int) -> tuple[tuple[datetime, ...], ...]:
    """Split an ``IN`` list so SQLite and other engines retain bounded parameters."""
    return tuple(tuple(values[index : index + size]) for index in range(0, len(values), size))


def _revision_sort_key(revision: LocalObservationRevision) -> tuple[datetime, datetime, int, str]:
    """Order revisions deterministically after their local PIT eligibility check."""
    return (
        revision.available_at,
        revision.committed_at,
        revision.revision_number,
        revision.revision_id,
    )
