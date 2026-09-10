"""Canonical local persistence for the Iteration 197 market-data path.

The store is intentionally provider-neutral and append-only.  It writes only
the normalized ``md_*`` evidence tables, never a legacy AkShare warehouse
table, and it makes every local read explicit about its point-in-time cutoff.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import MappingProxyType

from sqlalchemy import Select, and_, func, select, tuple_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetDataSourceRegistry
from app.models.data_governance import DgProvider
from app.models.market_data_platform import (
    CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED,
    SOURCE_AUTHORIZATION_STATE_UNVERIFIED_COMPATIBILITY,
    SOURCE_AUTHORIZATION_STATE_VERIFIED,
    MdCalendarEvent,
    MdCalendarSnapshot,
    MdDataSeries,
    MdObservationRevision,
    MdPublication,
    MdSourcePayload,
    MdSourceSnapshot,
    MdSourceSnapshotPayloadRef,
    calendar_coverage_descriptor,
    calendar_coverage_event_key,
)
from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.coverage import (
    CalendarSnapshot,
    CalendarStatus,
    EventKey,
    Observation,
    ObservationQuality,
    TimeWindow,
)
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseError,
    MarketDataFetchLeaseHandle,
    MarketDataFetchLeaseManager,
    assert_fetch_lease_held_in_transaction,
)
from app.services.market_data.field_quality import (
    FIELD_QUALITY_POLICY_VERSION,
    is_usable_field_value,
    normalize_provider_fields,
)
from app.services.market_data.multi_record import (
    SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
    SINGLE_RECORD_SEMANTIC_KEY_SHA256,
    SemanticRecordKey,
    normalize_semantic_record_key,
    single_record_semantic_key,
)
from app.services.market_data.multi_record_contracts import (
    B2FamilyContractError,
    normalize_b2_record_dimensions,
)
from app.services.market_data.providers import (
    ProviderFetchResult,
    ProviderMarketObservation,
    SharedSourcePayloadSegment,
)
from app.services.market_data.publication import (
    PUBLICATION_CALENDAR_SNAPSHOT,
    PUBLICATION_SOURCE_SNAPSHOT,
    MarketDataDeferredPublicationIntent,
    MarketDataDeferredPublicationPromotion,
    MarketDataPublicationError,
    MarketDataPublicationManager,
    MarketDataVisibilityAnchor,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext

UTC = timezone.utc
SERIES_SEMANTIC_VERSION = "market-data-series-v1"
QUALITY_POLICY_VERSION = FIELD_QUALITY_POLICY_VERSION
NORMALIZATION_VERSION = "market-data-store-v1"
_OBSERVATION_REVISION_CONTRACT_V1 = "market-data-observation-revision-v1"
_OBSERVATION_REVISION_CONTRACT_V2 = "market-data-observation-revision-v2"
_OBSERVATION_REVISION_CONTRACT_V3 = "market-data-observation-revision-v3"
_MAX_PROVIDER_OBSERVATIONS = 50_000
_REVISION_COORDINATE_QUERY_CHUNK_SIZE = 400
_MAX_CURRENT_REVISION_ROWS_PER_CHUNK = 10_000
MAX_SOURCE_PAYLOAD_BYTES = 10 * 1024 * 1024
_MAX_NORMALIZED_FIELDS_BYTES = 10 * 1024 * 1024
_MAX_NORMALIZED_RECORD_IDENTITIES_BYTES = 10 * 1024 * 1024
_SOURCE_AUTHORIZATION_VERSION = "market-data-source-authorization-v1"
_SOURCE_AUTHORIZATION_APPROVED_LICENSES = frozenset(
    {
        "APPROVED",
        "LICENSED",
        "MARKET_DATA_APPROVED",
        "PUBLIC",
        "RESEARCH_APPROVED",
    }
)
_SOURCE_AUTHORIZATION_ALLOWED_USES: Mapping[str, frozenset[str]] = {
    "display": frozenset({"DISPLAY", "MARKET_DATA_DISPLAY", "MARKET_DATA_READ"}),
    "research": frozenset({"RESEARCH", "RESEARCH_ONLY", "DERIVED_RESEARCH"}),
    "research_cache_fill": frozenset({"RESEARCH", "RESEARCH_ONLY", "DERIVED_RESEARCH"}),
    "backtest": frozenset({"BACKTEST", "BACKTEST_ONLY"}),
}
# A cache-fill receipt records the narrowly scoped authorization that allowed
# collection.  It may subsequently satisfy a strict research *read* only when
# the caller has independently passed current research authorization.  It is
# deliberately not reusable for display, backtest, or binding purposes.
_SOURCE_AUTHORIZATION_RECEIPT_PURPOSES_BY_QUERY_PURPOSE: Mapping[str, frozenset[str]] = {
    "display": frozenset({"display"}),
    "research": frozenset({"research", "research_cache_fill"}),
    "research_cache_fill": frozenset({"research_cache_fill"}),
    "backtest": frozenset({"backtest"}),
}
_SOURCE_AUTHORIZATION_READABLE_REDISTRIBUTION_POLICIES = frozenset(
    {"ALLOWED", "INTERNAL_ONLY", "NO_REDISTRIBUTION"}
)
_SOURCE_AUTHORIZATION_PROHIBITED_RETENTION_POLICIES = frozenset(
    {"", "DENIED", "EXPIRED", "PROHIBITED", "UNKNOWN"}
)
_SOURCE_AUTHORIZATION_PROVENANCE_FIELDS = frozenset(
    {
        "source_registry_id",
        "registry_updated_at",
        "asset_type",
        "market",
        "purpose",
        "license_status",
        "allowed_uses",
        "jurisdictions",
        "effective_from",
        "effective_to",
        "retention_policy",
        "retention_expires_at",
        "redistribution_policy",
        "principal_scope",
        "tenant_scope",
        "entitlement_revision",
        "decision",
        "descriptor_hash",
    }
)
UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT = "legacy_import"
UNVERIFIED_COMPATIBILITY_REASON_OPERATOR_RECOVERY = "operator_recovery"
_UNVERIFIED_COMPATIBILITY_REASONS = frozenset(
    {
        UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        UNVERIFIED_COMPATIBILITY_REASON_OPERATOR_RECOVERY,
    }
)
_UNVERIFIED_COMPATIBILITY_PROVENANCE_VERSION = "market-data-unverified-source-write-v1"
_CALENDAR_SOURCE_GOVERNANCE_VERSION = "market-data-calendar-source-governance-v1"
# These contracts remain unconfigured at every public/API/provider boundary.
# The lower-level Store nevertheless knows that a future approved writer for
# one of them must carry a record dimension set; silently persisting a
# singleton would make an incomplete B2 receipt look like a complete fact.
_MULTI_RECORD_FAMILY_IDS = frozenset(
    {
        "futures.inventory",
        "option.derivative",
        "option.risk_surface",
        "crypto.cme_position",
    }
)


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
class DeferredProviderFetch:
    """A durable-but-hidden provider write awaiting explicit attestation.

    This DTO intentionally does not expose a publication/visibility time.  A
    future legacy adapter must validate the staged candidate and ask the
    publication manager for a guarded promotion before it can obtain a normal
    ``PersistedProviderFetch`` usable by any local-first query path.
    """

    series_id: str
    source_snapshot_id: str
    publication_id: str
    observation_revision_ids: tuple[str, ...]
    passing_observation_count: int
    failed_observation_count: int
    local_received_at: datetime
    intent: MarketDataDeferredPublicationIntent


@dataclass(frozen=True, slots=True)
class LocalObservationRevision:
    """One selected local observation revision with source provenance.

    ``source_available_at`` is the upstream provider's declared availability,
    distinct from ``available_at``: the latter is the locally trusted receipt
    time used for PIT eligibility.  Store reads populate and validate the
    former only when a V2 or V3 revision identity seals it. Historical V1 rows and
    older synthetic DTO callers expose ``None`` instead; provenance-sensitive
    consumers must reject that value rather than infer it from local receipt
    time.
    """

    revision_id: str
    source_snapshot_id: str
    event_at: datetime
    available_at: datetime
    committed_at: datetime
    visible_at: datetime
    visibility_sequence: int
    revision_number: int
    quality: ObservationQuality
    fields: Mapping[str, object]
    source_available_at: datetime | None = None
    # Synthetic legacy test callers and pre-B2 compatibility adapters retain
    # the fixed singleton unless an actual Store read supplies a validated key.
    semantic_record_key: str = SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON
    semantic_record_key_sha256: str = SINGLE_RECORD_SEMANTIC_KEY_SHA256

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
class CalendarTradingDayEvent:
    """One exact published daily-grid EventKey with its source trading date."""

    trading_date: date
    event_key: EventKey

    def __post_init__(self) -> None:
        if not isinstance(self.trading_date, date) or isinstance(self.trading_date, datetime):
            raise TypeError("trading_date must be a date")
        if not isinstance(self.event_key, EventKey):
            raise TypeError("event_key must be an EventKey")


@dataclass(frozen=True, slots=True)
class CalendarTradingDayEvents:
    """A source-authorized, PIT-frozen date-to-EventKey calendar projection.

    A legacy importer may use ``trading_date`` only as a label.  The exact
    EventKey, snapshot identity, visibility anchor, and coverage evidence stay
    attached so a later writer cannot replace calendar semantics by a local
    date/time conversion.
    """

    calendar_code: str
    calendar_version: str
    data_kind: str
    frequency: str
    calendar_snapshot_id: str | None
    timezone_name: str
    coverage_window: TimeWindow | None
    visibility_anchor: MarketDataVisibilityAnchor
    status: CalendarStatus
    reason: str | None
    events: tuple[CalendarTradingDayEvent, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.calendar_code, field_name="calendar_code", maximum=128)
        _require_text(self.calendar_version, field_name="calendar_version", maximum=128)
        _require_text(self.data_kind, field_name="data_kind", maximum=64)
        _require_text(self.frequency, field_name="frequency", maximum=16)
        _require_text(self.timezone_name, field_name="timezone_name", maximum=128)
        if not isinstance(self.visibility_anchor, MarketDataVisibilityAnchor):
            raise TypeError("visibility_anchor must be a MarketDataVisibilityAnchor")
        status = CalendarStatus(self.status)
        if self.coverage_window is not None and not isinstance(self.coverage_window, TimeWindow):
            raise TypeError("coverage_window must be a TimeWindow")
        if self.calendar_snapshot_id is not None:
            _require_text(
                self.calendar_snapshot_id,
                field_name="calendar_snapshot_id",
                maximum=36,
            )
        if self.reason is not None:
            _require_text(self.reason, field_name="reason", maximum=128)
        events = tuple(self.events)
        if any(not isinstance(item, CalendarTradingDayEvent) for item in events):
            raise TypeError("events must contain CalendarTradingDayEvent values")
        ordered_events = tuple(sorted(events, key=lambda item: item.trading_date))
        if len({item.trading_date for item in ordered_events}) != len(ordered_events):
            raise ValueError("trading dates must map one-to-one to EventKeys")
        if len({item.event_key for item in ordered_events}) != len(ordered_events):
            raise ValueError("EventKeys must map one-to-one to trading dates")
        if status is CalendarStatus.KNOWN:
            if (
                self.calendar_snapshot_id is None
                or self.coverage_window is None
                or self.reason is not None
            ):
                raise ValueError("known trading-day evidence requires snapshot and coverage")
        elif (
            ordered_events
            or self.calendar_snapshot_id is not None
            or self.coverage_window is not None
        ):
            raise ValueError("unknown trading-day evidence cannot expose partial calendar data")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "events", ordered_events)


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
    semantic_record_key: SemanticRecordKey


@dataclass(frozen=True, slots=True)
class _ValidatedProviderFetch:
    """Validated source receipt data prepared before opening a write savepoint."""

    raw_payload: Mapping[str, object]
    payload_sha256: str
    observations: tuple[_ValidatedProviderObservation, ...]
    provider_request_id: str
    provider_request_fingerprint_sha256: str
    query_fingerprint_sha256: str
    shared_source_payload: _ValidatedSharedSourcePayload | None


@dataclass(frozen=True, slots=True)
class _ValidatedSharedSourcePayload:
    """An integrity-checked content-addressed wide-provider response."""

    content_sha256: str
    payload_format: str
    payload_role: str
    payload_bytes: int
    canonical_payload_bytes: bytes
    receipt_payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _ValidatedSourceAuthorization:
    """Persistence-ready source trust state detached from caller prose."""

    state: str
    descriptor_sha256: str | None
    provenance: Mapping[str, object]


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
        self._clock_is_test_override = clock is not None
        self._publications = MarketDataPublicationManager(
            db,
            clock=self._clock,
            fetch_lease_clock=self._clock if self._clock_is_test_override else None,
        )

    def fetch_lease_manager(self) -> MarketDataFetchLeaseManager:
        """Return a request-session lease manager for real local-first fills."""
        return MarketDataFetchLeaseManager(
            self._db,
            # Lease takeover must use a shared database clock in production;
            # deterministic store clocks remain an explicit test seam.
            clock=self._clock if self._clock_is_test_override else None,
        )

    async def close_transaction_before_provider_io(self) -> None:
        """End request-local database work before an adapter can use the network.

        Local reads and post-fetch authorization checks auto-begin SQLAlchemy
        transactions, including ``FOR UPDATE`` source-registry checks.  The
        query service owns this session and its persistence protocol commits
        every supported write itself, so an outstanding transaction here is
        only a read/authorization boundary that must be released before a
        fallback provider call.  Refuse to discard caller-staged ORM changes
        rather than silently rolling them back.
        """
        if not self._db.in_transaction():
            return
        if self._db.new or self._db.dirty or self._db.deleted:
            raise MarketDataStoreError("PROVIDER_IO_TRANSACTION_DIRTY")
        try:
            await self._db.rollback()
        except OperationalError as exc:
            raise MarketDataStoreError("PROVIDER_IO_TRANSACTION_RESET_FAILED") from exc

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
            "family_id": coverage.family_id,
            "family_contract_version": coverage.family_contract_version,
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
            # A competing writer may have committed while this session waited
            # on the unique index. The first ordinary lookup can be frozen at
            # an older MySQL REPEATABLE READ snapshot, so recovery must use a
            # locking/current read rather than repeat that stale lookup.
            existing = await self._find_series(identity, context, for_update=True)
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
        source_authorization: MarketDataSourceAuthorization | None = None,
        unverified_compatibility_reason: str | None = None,
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
        deferred_intent: MarketDataDeferredPublicationIntent | None = None,
    ) -> PersistedProviderFetch | DeferredProviderFetch:
        """Append one provider receipt and its normalized observation revisions.

        Input validation completes before any evidence row is added. The
        source snapshot, revisions and a pending publication receipt share a
        savepoint. After that transaction commits, a second transaction records
        a trusted visibility instant; an interrupted publication stays hidden.

        V2 provider writes require a registry-validated structured source
        authorization.  Controlled historical import/recovery callers may
        instead provide one of the explicit compatibility reasons; their
        receipt is durably tagged as unverified and is excluded from every
        current-authorized local read.

        When a cross-worker fetch lease is supplied, the owner/fence predicate
        is renewed in both the immutable-fact transaction and the separate
        publication transaction.  The provider call has already completed by
        this point, so neither short database transaction spans external I/O.

        ``deferred_intent`` is a deliberately narrow legacy-import seam.  It
        stores the facts and a durable release hold in transaction A, then
        returns without creating a visibility receipt.  Generic recovery and
        generic publishing reject the held receipt; callers must use the
        explicit guarded promotion API after their private verification.
        """
        _assert_writable_context(context)
        if fetch_lease is not None and not isinstance(fetch_lease, MarketDataFetchLeaseHandle):
            raise TypeError("fetch_lease must be a MarketDataFetchLeaseHandle")
        if deferred_intent is not None and not isinstance(
            deferred_intent, MarketDataDeferredPublicationIntent
        ):
            raise TypeError("deferred_intent must be a MarketDataDeferredPublicationIntent")
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
        authorization = await self._validate_source_authorization(
            context,
            result,
            source_authorization,
            local_received_at=local_received_at,
            unverified_compatibility_reason=unverified_compatibility_reason,
        )

        try:
            # Renew the owner row before staging facts, but within the same
            # short outer transaction that will commit them. This makes a
            # stale owner fail before it can even flush a pending receipt, and
            # the conditional row update prevents a takeover until the fact
            # transaction commits or rolls back.
            if fetch_lease is not None:
                await assert_fetch_lease_held_in_transaction(
                    self._db,
                    fetch_lease,
                    clock=self._clock if self._clock_is_test_override else None,
                )
            async with self._db.begin_nested():
                series = await self.get_or_create_series(context)
                series = await self._lock_series_for_revision(series, context)
                shared_source_payload = await self._get_or_create_shared_source_payload(
                    validated.shared_source_payload
                )
                source_snapshot = self._make_source_snapshot(
                    context,
                    provider,
                    result,
                    validated,
                    source_authorization=authorization,
                    local_received_at=local_received_at,
                    fetch_lease=fetch_lease,
                    shared_source_payload=shared_source_payload,
                )
                self._db.add(source_snapshot)
                await self._db.flush()
                if shared_source_payload is not None:
                    self._db.add(
                        MdSourceSnapshotPayloadRef(
                            source_snapshot_id=source_snapshot.id,
                            content_sha256=shared_source_payload.content_sha256,
                            payload_role=validated.shared_source_payload.payload_role,
                        )
                    )
                    await self._db.flush()
                publication = await self._publications.stage(
                    entity_type=PUBLICATION_SOURCE_SNAPSHOT,
                    entity_id=source_snapshot.id,
                    entity_sha256=source_snapshot.payload_sha256,
                )

                revision_numbers = await self._next_revision_numbers(
                    series_id=series.id,
                    record_coordinates=tuple(
                        (item.event_at, item.semantic_record_key.sha256)
                        for item in validated.observations
                    ),
                )
                revisions = [
                    self._make_observation_revision(
                        series=series,
                        source_snapshot=source_snapshot,
                        result=result,
                        observation=observation,
                        revision_number=revision_numbers[
                            (observation.event_at, observation.semantic_record_key.sha256)
                        ],
                        local_received_at=local_received_at,
                    )
                    for observation in validated.observations
                ]
                self._db.add_all(revisions)
                await self._db.flush()
                if deferred_intent is not None:
                    await self._publications.hold_staged_source_snapshot(
                        publication=publication,
                        source_snapshot_id=source_snapshot.id,
                        intent=deferred_intent,
                    )
        except MarketDataFetchLeaseError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError(exc.code) from exc
        except IntegrityError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError("OBSERVATION_WRITE_FAILED") from exc
        except OperationalError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError("OBSERVATION_WRITE_CONFLICT") from exc

        try:
            # The actual data transaction must finish before a trusted local
            # visibility instant is sampled.  Query-service callers never mix
            # unrelated writes into this session; a separate API transaction
            # remains the boundary for any future mixed workflow.
            await self._db.commit()
        except MarketDataFetchLeaseError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError(exc.code) from exc
        except OperationalError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError("OBSERVATION_PUBLICATION_FAILED") from exc

        if deferred_intent is not None:
            return DeferredProviderFetch(
                series_id=series.id,
                source_snapshot_id=source_snapshot.id,
                publication_id=publication.id,
                observation_revision_ids=tuple(revision.id for revision in revisions),
                passing_observation_count=sum(
                    item.quality is ObservationQuality.PASS for item in validated.observations
                ),
                failed_observation_count=sum(
                    item.quality is ObservationQuality.FAILED for item in validated.observations
                ),
                local_received_at=local_received_at,
                intent=deferred_intent,
            )

        async def assert_publish_fence() -> None:
            if fetch_lease is not None:
                await assert_fetch_lease_held_in_transaction(
                    self._db,
                    fetch_lease,
                    clock=self._clock if self._clock_is_test_override else None,
                )

        try:
            published_at = await self._publications.publish_staged(
                (publication.id,),
                not_before=local_received_at,
                pre_publish_guard=assert_publish_fence if fetch_lease is not None else None,
                fetch_lease=fetch_lease,
            )
        except MarketDataFetchLeaseError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError(exc.code) from exc
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

    async def stage_provider_result_for_deferred_release(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        *,
        deferred_intent: MarketDataDeferredPublicationIntent,
        received_at: datetime | None = None,
        source_authorization: MarketDataSourceAuthorization | None = None,
        unverified_compatibility_reason: str | None = None,
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
    ) -> DeferredProviderFetch:
        """Persist one legacy-import candidate without making it query-visible."""
        staged = await self.persist_provider_result(
            context,
            result,
            received_at=received_at,
            source_authorization=source_authorization,
            unverified_compatibility_reason=unverified_compatibility_reason,
            fetch_lease=fetch_lease,
            deferred_intent=deferred_intent,
        )
        if not isinstance(staged, DeferredProviderFetch):
            raise AssertionError("deferred provider write returned a visible receipt")
        return staged

    async def promote_deferred_provider_result(
        self,
        staged: DeferredProviderFetch,
        *,
        promotion_evidence_sha256: str,
        pre_publish_guard: Callable[[], Awaitable[None]],
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
    ) -> PersistedProviderFetch:
        """Turn one verified staged candidate into an ordinary sealed receipt.

        The caller must provide the private verification/reauthorization guard.
        This Store method deliberately has no default guard and never offers a
        route-level shortcut for promotion.
        """
        if not isinstance(staged, DeferredProviderFetch):
            raise TypeError("staged must be a DeferredProviderFetch")
        if not callable(pre_publish_guard):
            raise TypeError("pre_publish_guard must be callable")
        promotion = MarketDataDeferredPublicationPromotion(
            publication_id=staged.publication_id,
            source_snapshot_id=staged.source_snapshot_id,
            workflow_kind=staged.intent.workflow_kind,
            intent_sha256=staged.intent.intent_sha256,
            promotion_evidence_sha256=promotion_evidence_sha256,
        )
        try:
            published_at = await self._publications.promote_deferred_after_attestation(
                (promotion,),
                not_before=staged.local_received_at,
                pre_publish_guard=pre_publish_guard,
                fetch_lease=fetch_lease,
            )
        except MarketDataFetchLeaseError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError(exc.code) from exc
        except (MarketDataPublicationError, OperationalError) as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            code = (
                exc.code
                if isinstance(exc, MarketDataPublicationError)
                else "OBSERVATION_PUBLICATION_FAILED"
            )
            raise MarketDataStoreError(code) from exc
        return PersistedProviderFetch(
            series_id=staged.series_id,
            source_snapshot_id=staged.source_snapshot_id,
            observation_revision_ids=staged.observation_revision_ids,
            passing_observation_count=staged.passing_observation_count,
            failed_observation_count=staged.failed_observation_count,
            received_at=published_at,
        )

    async def quarantine_deferred_provider_result(
        self,
        staged: DeferredProviderFetch,
        *,
        quarantine_code: str,
    ) -> None:
        """Record that a staged candidate failed verification without exposing it."""
        if not isinstance(staged, DeferredProviderFetch):
            raise TypeError("staged must be a DeferredProviderFetch")
        try:
            await self._publications.quarantine_deferred(
                publication_id=staged.publication_id,
                source_snapshot_id=staged.source_snapshot_id,
                intent=staged.intent,
                quarantine_code=quarantine_code,
            )
        except MarketDataPublicationError as exc:
            if self._db.in_transaction():
                await self._db.rollback()
            raise MarketDataStoreError(exc.code) from exc

    async def resolve_visibility_anchor(
        self,
        *,
        knowledge_cutoff: datetime,
    ) -> MarketDataVisibilityAnchor:
        """Freeze the complete sealed-receipt boundary at one UTC cutoff.

        The maximum sequence is sampled before identity, calendar, coverage, or
        observation reads.  A later receipt with the same visible timestamp is
        therefore excluded from a continuation even on engines that retain only
        microsecond timestamp precision.
        """
        cutoff = _require_aware_utc(knowledge_cutoff, field_name="knowledge_cutoff")
        missing_sequence = await self._db.scalar(
            select(MdPublication.id)
            .where(
                MdPublication.published_at.is_not(None),
                MdPublication.published_at <= cutoff,
                MdPublication.visibility_sequence.is_(None),
            )
            .limit(1)
        )
        if missing_sequence is not None:
            raise MarketDataStoreError("PUBLICATION_VISIBILITY_INTEGRITY")
        max_sequence = await self._db.scalar(
            select(func.max(MdPublication.visibility_sequence)).where(
                MdPublication.published_at.is_not(None),
                MdPublication.published_at <= cutoff,
                MdPublication.visibility_sequence.is_not(None),
            )
        )
        if max_sequence is None:
            return MarketDataVisibilityAnchor(
                visible_at=cutoff,
                max_visibility_sequence=0,
            )
        if not isinstance(max_sequence, int) or isinstance(max_sequence, bool) or max_sequence < 1:
            raise MarketDataStoreError("PUBLICATION_VISIBILITY_INTEGRITY")
        return MarketDataVisibilityAnchor(
            visible_at=cutoff,
            max_visibility_sequence=max_sequence,
        )

    async def read_observation_revisions(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        include_unusable_for_coverage: bool = False,
        allowed_source_registry_ids: frozenset[str] | None = None,
        exact_event_at: datetime | None = None,
    ) -> tuple[LocalObservationRevision, ...]:
        """Select the newest response-safe revision per event/record at PIT cutoff.

        A series deliberately does not include a field projection. A later,
        narrower request can therefore append a revision that has fewer fields
        than an older revision for the same event. Selecting that row
        unconditionally would hide a complete local fact and make a broader
        follow-up request fetch the network again. Prefer the newest revision
        that is PASS and satisfies this request's required fields. By default,
        unusable revisions are excluded because this method feeds product
        responses. Coverage planning may explicitly request the newest
        unusable fallback so it can report a deterministic rejection; that
        diagnostics-only result must never be rendered as market data.
        """
        _assert_context_integrity(context)
        allowed_source_ids = _normalize_allowed_source_registry_ids(allowed_source_registry_ids)
        if allowed_source_ids is not None and not allowed_source_ids:
            return ()
        requested_event_at = (
            _require_aware_utc(exact_event_at, field_name="exact local observation event time")
            if exact_event_at is not None
            else None
        )
        if requested_event_at is not None and not (
            context.query.start <= requested_event_at < context.query.end
        ):
            raise MarketDataStoreError("LOCAL_OBSERVATION_EVENT_OUT_OF_WINDOW")
        anchor = await self._resolve_visibility_anchor(
            knowledge_cutoff=knowledge_cutoff,
            visibility_anchor=visibility_anchor,
        )
        series = await self.get_series(context)
        if series is None:
            return ()

        query = context.query
        event_predicates = (
            (MdObservationRevision.event_time == requested_event_at,)
            if requested_event_at is not None
            else (
                MdObservationRevision.event_time >= query.start,
                MdObservationRevision.event_time < query.end,
            )
        )
        statement = (
            select(
                MdObservationRevision,
                MdSourceSnapshot,
                MdPublication.published_at,
                MdPublication.visibility_sequence,
            )
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
                *event_predicates,
                MdPublication.entity_sha256 == MdSourceSnapshot.payload_sha256,
                MdPublication.published_at.is_not(None),
                MdPublication.visibility_sequence.is_not(None),
                _publication_is_visible_at_anchor(anchor),
            )
            .order_by(
                MdObservationRevision.event_time,
                MdObservationRevision.semantic_record_key,
                MdPublication.published_at,
                MdPublication.visibility_sequence,
                MdObservationRevision.revision_number,
                MdObservationRevision.id,
            )
        )
        if allowed_source_ids is not None:
            # A valid source ID alone is not enough: rows imported through an
            # explicit compatibility path and rows written before authorization
            # receipts existed cannot become v2 facts merely because a current
            # provider happens to use the same identifier.
            statement = statement.where(
                MdSourceSnapshot.source_id.in_(sorted(allowed_source_ids)),
                MdSourceSnapshot.source_authorization_state == SOURCE_AUTHORIZATION_STATE_VERIFIED,
            ).execution_options(populate_existing=True)
        rows = list((await self._db.execute(statement)).all())

        selected_usable: dict[tuple[datetime, str], LocalObservationRevision] = {}
        selected_fallback: dict[tuple[datetime, str], LocalObservationRevision] = {}
        verified_source_registry_ids: dict[str, str | None] = {}
        for row, source_snapshot, published_at, visibility_sequence in rows:
            if published_at is None or not _is_visibility_sequence(visibility_sequence):
                raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
            if allowed_source_ids is not None:
                source_registry_id = verified_source_registry_ids.get(source_snapshot.id)
                if source_snapshot.id not in verified_source_registry_ids:
                    try:
                        source_registry_id = _verified_source_authorization_registry_id(
                            source_snapshot,
                            context=context,
                        )
                    except MarketDataStoreError:
                        # A raw/internal write must not turn a syntactically
                        # populated state column into a v2 fact. Compatibility,
                        # legacy, and structurally forged receipts remain absent
                        # from the authorization-filtered local response.
                        source_registry_id = None
                    verified_source_registry_ids[source_snapshot.id] = source_registry_id
                if source_registry_id not in allowed_source_ids:
                    continue
            local = _decode_local_revision(
                row,
                context=context,
                visibility_anchor=anchor,
                published_at=_stored_utc(published_at, field_name="publication published_at"),
                visibility_sequence=visibility_sequence,
            )
            record_coordinate = (local.event_at, local.semantic_record_key_sha256)
            current_fallback = selected_fallback.get(record_coordinate)
            if current_fallback is None or _revision_sort_key(local) > _revision_sort_key(
                current_fallback
            ):
                selected_fallback[record_coordinate] = local
            if not _revision_is_usable_for_fields(local, context.query.required_fields):
                continue
            current_usable = selected_usable.get(record_coordinate)
            if current_usable is None or _revision_sort_key(local) > _revision_sort_key(
                current_usable
            ):
                selected_usable[record_coordinate] = local
        if include_unusable_for_coverage:
            return tuple(
                sorted(
                    (
                        selected_usable.get(coordinate, selected_fallback[coordinate])
                        for coordinate in selected_fallback
                    ),
                    key=_record_revision_output_sort_key,
                )
            )
        return tuple(sorted(selected_usable.values(), key=_record_revision_output_sort_key))

    async def _resolve_visibility_anchor(
        self,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None,
    ) -> MarketDataVisibilityAnchor:
        """Use a cursor's signed anchor or resolve one exactly once for a read."""
        cutoff = _require_aware_utc(knowledge_cutoff, field_name="knowledge_cutoff")
        if visibility_anchor is None:
            return await self.resolve_visibility_anchor(knowledge_cutoff=cutoff)
        if not isinstance(visibility_anchor, MarketDataVisibilityAnchor):
            raise TypeError("visibility_anchor must be a MarketDataVisibilityAnchor")
        if visibility_anchor.visible_at != cutoff:
            raise MarketDataStoreError("VISIBILITY_ANCHOR_CUTOFF_MISMATCH")
        return visibility_anchor

    async def read_observations(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> tuple[Observation, ...]:
        """Return local observations in the pure shape expected by coverage planning."""
        revisions = await self.read_observation_revisions(
            context,
            knowledge_cutoff=knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            include_unusable_for_coverage=True,
            allowed_source_registry_ids=allowed_source_registry_ids,
        )
        return tuple(item.as_coverage_observation(context) for item in revisions)

    async def read_calendar(
        self,
        *,
        calendar_code: str,
        window: TimeWindow,
        calendar_version: str | None = None,
        knowledge_cutoff: datetime | None = None,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        data_kind: str = "bars",
        frequency: str = "1d",
        allowed_source_registry_ids: frozenset[str] | None = None,
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
        allowed_source_ids = _normalize_allowed_source_registry_ids(allowed_source_registry_ids)
        if not isinstance(window, TimeWindow):
            raise TypeError("window must be a TimeWindow")
        version = (
            _require_text(calendar_version, field_name="calendar_version", maximum=128)
            if calendar_version is not None
            else None
        )
        if knowledge_cutoff is None:
            if visibility_anchor is not None:
                raise MarketDataStoreError("VISIBILITY_ANCHOR_CUTOFF_MISMATCH")
            anchor = None
        else:
            anchor = await self._resolve_visibility_anchor(
                knowledge_cutoff=knowledge_cutoff,
                visibility_anchor=visibility_anchor,
            )

        statement = (
            select(
                MdCalendarSnapshot,
                MdPublication.published_at,
                MdPublication.visibility_sequence,
            )
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
                MdPublication.visibility_sequence.is_not(None),
            )
        )
        if anchor is not None:
            statement = statement.where(_publication_is_visible_at_anchor(anchor))
        if version is not None:
            statement = statement.where(MdCalendarSnapshot.calendar_version == version)
        raw_rows = list((await self._db.execute(statement)).all())
        rows: list[tuple[MdCalendarSnapshot, datetime, int]] = []
        saw_unverified_source = False
        saw_unauthorized_source = False
        for row, published_at, visibility_sequence in raw_rows:
            if published_at is None or not _is_visibility_sequence(visibility_sequence):
                continue
            visible_at = _stored_utc(published_at, field_name="calendar publication")
            if anchor is not None and not anchor.permits(
                visible_at=visible_at,
                visibility_sequence=visibility_sequence,
            ):
                continue
            try:
                source_registry_id = _verified_calendar_source_registry_id(row)
            except MarketDataStoreError:
                saw_unverified_source = True
                continue
            if allowed_source_ids is not None and source_registry_id not in allowed_source_ids:
                saw_unauthorized_source = True
                continue
            rows.append((row, visible_at, visibility_sequence))

        usable: list[tuple[MdCalendarSnapshot, TimeWindow, datetime, int]] = []
        saw_integrity_error = False
        for row, published_at, visibility_sequence in rows:
            try:
                coverage_window = _calendar_coverage_window(row)
            except MarketDataStoreError:
                saw_integrity_error = True
                continue
            if (
                coverage_window.end_at > window.start_at
                and coverage_window.start_at < window.end_at
            ):
                usable.append((row, coverage_window, published_at, visibility_sequence))

        unknown_timezone = _unknown_timezone([row for row, _published_at, _sequence in rows])
        unknown_version = version or "unresolved"
        if not usable:
            if saw_unauthorized_source:
                reason = "CALENDAR_SOURCE_UNAUTHORIZED"
            elif saw_unverified_source:
                reason = "CALENDAR_SOURCE_UNVERIFIED"
            elif not rows:
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
            for snapshot, coverage_window, _published_at, _visibility_sequence in selected:
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
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> CalendarSnapshot:
        """Load calendar evidence for a resolved query's exact market and window."""
        _assert_context_integrity(context)
        return await self.read_calendar(
            calendar_code=context.coverage_identity.market,
            window=TimeWindow(start_at=context.query.start, end_at=context.query.end),
            calendar_version=calendar_version,
            knowledge_cutoff=knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            data_kind=context.query.data_kind,
            frequency=context.query.frequency or "snapshot",
            allowed_source_registry_ids=allowed_source_registry_ids,
        )

    async def read_calendar_trading_day_events_for_context(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor | None = None,
        allowed_source_registry_ids: frozenset[str] | None = None,
    ) -> CalendarTradingDayEvents:
        """Return a one-to-one daily source-date map from one governed snapshot.

        This is deliberately narrower than :meth:`read_calendar_for_context`.
        It is for controlled legacy imports that must preserve the source table's
        ``DATE`` label while using the exact published EventKey.  It reuses the
        regular calendar read first, then requires that its proof comes from one
        visible snapshot; composed rolling segments remain unavailable here
        because no importer may erase their snapshot boundary.
        """
        _assert_context_integrity(context)
        anchor = await self._resolve_visibility_anchor(
            knowledge_cutoff=knowledge_cutoff,
            visibility_anchor=visibility_anchor,
        )
        code = context.coverage_identity.market
        window = TimeWindow(start_at=context.query.start, end_at=context.query.end)
        calendar = await self.read_calendar_for_context(
            context,
            knowledge_cutoff=knowledge_cutoff,
            visibility_anchor=anchor,
            allowed_source_registry_ids=allowed_source_registry_ids,
        )
        if calendar.status is not CalendarStatus.KNOWN:
            return _unknown_calendar_trading_day_events(
                calendar=calendar,
                visibility_anchor=anchor,
                data_kind=context.query.data_kind,
                frequency=context.query.frequency or "snapshot",
                reason=calendar.reason or "CALENDAR_INTEGRITY",
            )
        if calendar.calendar_version.startswith("composed:"):
            return _unknown_calendar_trading_day_events(
                calendar=calendar,
                visibility_anchor=anchor,
                data_kind=context.query.data_kind,
                frequency=context.query.frequency or "snapshot",
                reason="CALENDAR_TRADING_DAY_SNAPSHOT_AMBIGUOUS",
            )

        snapshot, source_reason = await self._read_visible_calendar_snapshot_for_trading_days(
            calendar_code=code,
            calendar_version=calendar.calendar_version,
            visibility_anchor=anchor,
            allowed_source_registry_ids=allowed_source_registry_ids,
        )
        if snapshot is None:
            return _unknown_calendar_trading_day_events(
                calendar=calendar,
                visibility_anchor=anchor,
                data_kind=context.query.data_kind,
                frequency=context.query.frequency or "snapshot",
                reason=source_reason or "CALENDAR_VERSION_NOT_FOUND",
            )
        try:
            events = await self._read_calendar_trading_day_events(
                snapshot=snapshot,
                window=window,
                data_kind=context.query.data_kind,
                frequency=context.query.frequency or "snapshot",
                expected_event_keys=calendar.event_keys,
            )
        except MarketDataStoreError as exc:
            return _unknown_calendar_trading_day_events(
                calendar=calendar,
                visibility_anchor=anchor,
                data_kind=context.query.data_kind,
                frequency=context.query.frequency or "snapshot",
                reason=exc.code,
            )
        return CalendarTradingDayEvents(
            calendar_code=calendar.calendar_id,
            calendar_version=calendar.calendar_version,
            data_kind=context.query.data_kind,
            frequency=context.query.frequency or "snapshot",
            calendar_snapshot_id=snapshot.id,
            timezone_name=calendar.timezone_name,
            coverage_window=calendar.coverage_window,
            visibility_anchor=anchor,
            status=CalendarStatus.KNOWN,
            reason=None,
            events=events,
        )

    async def _read_visible_calendar_snapshot_for_trading_days(
        self,
        *,
        calendar_code: str,
        calendar_version: str,
        visibility_anchor: MarketDataVisibilityAnchor,
        allowed_source_registry_ids: frozenset[str] | None,
    ) -> tuple[MdCalendarSnapshot | None, str | None]:
        """Revalidate the single snapshot boundary retained by a known calendar."""
        allowed_source_ids = _normalize_allowed_source_registry_ids(allowed_source_registry_ids)
        rows = list(
            (
                await self._db.execute(
                    select(
                        MdCalendarSnapshot,
                        MdPublication.published_at,
                        MdPublication.visibility_sequence,
                    )
                    .join(
                        MdPublication,
                        and_(
                            MdPublication.entity_type == PUBLICATION_CALENDAR_SNAPSHOT,
                            MdPublication.entity_id == MdCalendarSnapshot.id,
                        ),
                    )
                    .where(
                        MdCalendarSnapshot.calendar_code == calendar_code,
                        MdCalendarSnapshot.calendar_version == calendar_version,
                        MdPublication.entity_sha256 == MdCalendarSnapshot.snapshot_sha256,
                        MdPublication.published_at.is_not(None),
                        MdPublication.visibility_sequence.is_not(None),
                        _publication_is_visible_at_anchor(visibility_anchor),
                    )
                )
            ).all()
        )
        saw_unverified = False
        saw_unauthorized = False
        verified: list[MdCalendarSnapshot] = []
        for snapshot, published_at, visibility_sequence in rows:
            if published_at is None or not _is_visibility_sequence(visibility_sequence):
                continue
            visible_at = _stored_utc(published_at, field_name="calendar publication")
            if not visibility_anchor.permits(
                visible_at=visible_at,
                visibility_sequence=visibility_sequence,
            ):
                continue
            try:
                source_registry_id = _verified_calendar_source_registry_id(snapshot)
            except MarketDataStoreError:
                saw_unverified = True
                continue
            if allowed_source_ids is not None and source_registry_id not in allowed_source_ids:
                saw_unauthorized = True
                continue
            verified.append(snapshot)
        if len(verified) == 1:
            return verified[0], None
        if saw_unauthorized:
            return None, "CALENDAR_SOURCE_UNAUTHORIZED"
        if saw_unverified:
            return None, "CALENDAR_SOURCE_UNVERIFIED"
        if len(verified) > 1:
            return None, "CALENDAR_TRADING_DAY_SNAPSHOT_AMBIGUOUS"
        return None, "CALENDAR_VERSION_NOT_FOUND"

    async def _read_calendar_trading_day_events(
        self,
        *,
        snapshot: MdCalendarSnapshot,
        window: TimeWindow,
        data_kind: str,
        frequency: str,
        expected_event_keys: Sequence[EventKey],
    ) -> tuple[CalendarTradingDayEvent, ...]:
        """Bind each selected daily EventKey to exactly one persisted date label."""
        expected = tuple(expected_event_keys)
        if len(set(expected)) != len(expected):
            raise MarketDataStoreError("CALENDAR_TRADING_DAY_EVENT_INTEGRITY")
        expected_set = frozenset(expected)
        rows = list(
            (
                await self._db.execute(
                    select(MdCalendarEvent)
                    .where(
                        MdCalendarEvent.calendar_snapshot_id == snapshot.id,
                        MdCalendarEvent.event_start.is_not(None),
                        MdCalendarEvent.event_start >= window.start_at,
                        MdCalendarEvent.event_start < window.end_at,
                    )
                    .order_by(
                        MdCalendarEvent.trading_date,
                        MdCalendarEvent.event_start,
                        MdCalendarEvent.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        mapped: list[CalendarTradingDayEvent] = []
        for row in rows:
            if not row.is_trading_day or row.event_type != "session":
                continue
            try:
                descriptor = calendar_coverage_descriptor(row.event_payload_json)
            except ValueError as exc:
                raise MarketDataStoreError("CALENDAR_TRADING_DAY_EVENT_INTEGRITY") from exc
            if descriptor != (data_kind, frequency):
                continue
            if row.event_start is None or not isinstance(row.trading_date, date):
                raise MarketDataStoreError("CALENDAR_TRADING_DAY_EVENT_INTEGRITY")
            event_key = EventKey(_stored_utc(row.event_start, field_name="calendar event_start"))
            try:
                expected_coverage_key = calendar_coverage_event_key(
                    event_start=event_key.event_at,
                    data_kind=data_kind,
                    frequency=frequency,
                )
            except ValueError as exc:
                raise MarketDataStoreError("CALENDAR_TRADING_DAY_EVENT_INTEGRITY") from exc
            if row.coverage_event_key != expected_coverage_key or event_key not in expected_set:
                raise MarketDataStoreError("CALENDAR_TRADING_DAY_EVENT_INTEGRITY")
            mapped.append(
                CalendarTradingDayEvent(
                    trading_date=row.trading_date,
                    event_key=event_key,
                )
            )
        try:
            result = tuple(mapped)
            by_date = {item.trading_date: item.event_key for item in result}
            if len(by_date) != len(result):
                raise ValueError("duplicate trading date")
            if frozenset(by_date.values()) != expected_set:
                raise ValueError("expected EventKey set mismatch")
            return tuple(
                CalendarTradingDayEvent(trading_date=trading_date, event_key=by_date[trading_date])
                for trading_date in sorted(by_date)
            )
        except (TypeError, ValueError) as exc:
            raise MarketDataStoreError("CALENDAR_TRADING_DAY_EVENT_INTEGRITY") from exc

    async def _find_series(
        self,
        identity: SeriesIdentity,
        context: ResolvedMarketDataQueryContext,
        *,
        for_update: bool = False,
    ) -> MdDataSeries | None:
        statement = _series_lookup_statement(
            semantic_key_sha256=identity.semantic_key_sha256,
            for_update=for_update,
        )
        rows = list((await self._db.execute(statement)).scalars().all())
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

    async def ensure_source_authorization_before_provider_io(
        self,
        context: ResolvedMarketDataQueryContext,
        source_authorization: MarketDataSourceAuthorization,
        *,
        provider_id: str,
        checked_at: datetime | None = None,
    ) -> None:
        """Revalidate one exact source grant before an external request starts.

        ``persist_provider_result`` repeats this validation after the provider
        responds, which closes the race between outbound I/O and durable
        receipt creation.  Scheduled collectors also need this preflight so a
        revoked, expired, or stale grant cannot trigger a paid/broad source
        request merely because its provider remains active.
        """
        _assert_writable_context(context)
        normalized_provider_id = _require_text(
            provider_id,
            field_name="provider_id",
            maximum=255,
        )
        local_checked_at = _require_aware_utc(
            checked_at or self._clock(),
            field_name="source authorization check timestamp",
        )
        await self._require_active_provider(normalized_provider_id)
        await self._validate_source_authorization_for_provider(
            context,
            provider_id=normalized_provider_id,
            source_authorization=source_authorization,
            local_received_at=local_checked_at,
            unverified_compatibility_reason=None,
        )

    async def _validate_source_authorization(
        self,
        context: ResolvedMarketDataQueryContext,
        result: ProviderFetchResult,
        source_authorization: MarketDataSourceAuthorization | None,
        *,
        local_received_at: datetime,
        unverified_compatibility_reason: str | None,
    ) -> _ValidatedSourceAuthorization:
        """Validate a frozen source grant against the live registry before persistence.

        A normal v2 write must supply the grant.  The only bypass is a bounded,
        explicit compatibility reason, which produces a permanently
        unverified receipt that v2 local reads reject.  Once a grant is
        supplied this method accepts neither an arbitrary mapping nor a
        caller-computed descriptor alone: it verifies the typed evidence, its
        canonical digest, request context, and the current registry row before
        the source snapshot can be staged.
        """
        return await self._validate_source_authorization_for_provider(
            context,
            provider_id=result.provider_id,
            source_authorization=source_authorization,
            local_received_at=local_received_at,
            unverified_compatibility_reason=unverified_compatibility_reason,
        )

    async def _validate_source_authorization_for_provider(
        self,
        context: ResolvedMarketDataQueryContext,
        *,
        provider_id: str,
        source_authorization: MarketDataSourceAuthorization | None,
        local_received_at: datetime,
        unverified_compatibility_reason: str | None,
    ) -> _ValidatedSourceAuthorization:
        """Validate one source grant using its explicit provider identity."""
        if source_authorization is None:
            reason = _normalize_unverified_compatibility_reason(unverified_compatibility_reason)
            return _ValidatedSourceAuthorization(
                state=SOURCE_AUTHORIZATION_STATE_UNVERIFIED_COMPATIBILITY,
                descriptor_sha256=None,
                provenance=MappingProxyType(
                    {
                        "version": _UNVERIFIED_COMPATIBILITY_PROVENANCE_VERSION,
                        "reason": reason,
                        "decision": "UNVERIFIED",
                    }
                ),
            )
        if unverified_compatibility_reason is not None:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_MODE_CONFLICT")
        provenance = _normalized_source_authorization_provenance(
            context,
            source_authorization,
            provider_id=provider_id,
        )
        # Re-read rather than use ``Session.get``: a long-lived request
        # session may already have an identity-mapped registry row from an
        # earlier control-plane lookup.  The query service owns any short
        # write authorization lock; this is the independent post-query
        # freshness/integrity check without taking a second lock.
        registry = await self._db.scalar(
            select(AssetDataSourceRegistry)
            .where(AssetDataSourceRegistry.source_id == provenance["source_registry_id"])
            .execution_options(populate_existing=True)
        )
        if registry is None:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_UNREGISTERED")
        _assert_source_authorization_matches_registry(
            provenance,
            registry,
            local_received_at=local_received_at,
        )
        return _ValidatedSourceAuthorization(
            state=SOURCE_AUTHORIZATION_STATE_VERIFIED,
            descriptor_sha256=str(provenance["descriptor_hash"]),
            provenance=MappingProxyType(provenance),
        )

    async def _get_or_create_shared_source_payload(
        self,
        validated: _ValidatedSharedSourcePayload | None,
    ) -> MdSourcePayload | None:
        """Persist one validated raw response once within the fact transaction.

        The payload cannot be published or queried independently.  It becomes
        reachable only through the source snapshots created in the same outer
        transaction.  A matching content address is revalidated before reuse
        so an unexpected manual/database corruption cannot be hidden by its
        natural-key lookup.
        """
        if validated is None:
            return None

        existing = await self._load_shared_source_payload(validated.content_sha256)
        if existing is not None:
            _assert_shared_source_payload_matches(existing, validated)
            return existing

        payload = MdSourcePayload(
            content_sha256=validated.content_sha256,
            payload_format=validated.payload_format,
            payload_bytes=validated.payload_bytes,
            canonical_payload_bytes=validated.canonical_payload_bytes,
        )
        try:
            # The nested savepoint lets a concurrent identical content write
            # resolve to the committed payload without rolling back the
            # enclosing source-snapshot transaction.  An operational lock is
            # deliberately surfaced as a normal write conflict for a retry.
            async with self._db.begin_nested():
                self._db.add(payload)
                await self._db.flush()
        except IntegrityError:
            existing = await self._load_shared_source_payload(validated.content_sha256)
            if existing is None:
                raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_WRITE_CONFLICT") from None
            _assert_shared_source_payload_matches(existing, validated)
            return existing
        return payload

    async def _load_shared_source_payload(self, content_sha256: str) -> MdSourcePayload | None:
        """Re-read a shared blob instead of trusting a long-lived identity map."""
        return await self._db.scalar(
            select(MdSourcePayload)
            .where(MdSourcePayload.content_sha256 == content_sha256)
            .execution_options(populate_existing=True)
        )

    def _make_source_snapshot(
        self,
        context: ResolvedMarketDataQueryContext,
        provider: DgProvider,
        result: ProviderFetchResult,
        validated: _ValidatedProviderFetch,
        *,
        source_authorization: _ValidatedSourceAuthorization,
        local_received_at: datetime,
        fetch_lease: MarketDataFetchLeaseHandle | None,
        shared_source_payload: MdSourcePayload | None,
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
        payload_manifest: dict[str, object] = {
            "format": "inline-json",
            "raw_payload": dict(validated.raw_payload),
            "observation_count": len(validated.observations),
        }
        if shared_source_payload is not None:
            shared = validated.shared_source_payload
            if shared is None:
                raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_INTEGRITY_CONFLICT")
            payload_manifest["format"] = "content-addressed-source-batch-v1"
            payload_manifest["receipt_payload"] = dict(shared.receipt_payload)
            payload_manifest.pop("raw_payload")
            payload_manifest["shared_source_payload"] = {
                "content_sha256": shared_source_payload.content_sha256,
                "payload_format": shared_source_payload.payload_format,
                "payload_bytes": shared_source_payload.payload_bytes,
                "payload_role": shared.payload_role,
            }
        provenance = {
            "provider_id": provider.provider_id,
            "source_revision": source_revision,
            "provider_retrieved_at": result.retrieved_at.isoformat(),
            "local_received_at": local_received_at.isoformat(),
            "warnings": list(result.warnings),
            "normalization_version": NORMALIZATION_VERSION,
        }
        if source_authorization.state == SOURCE_AUTHORIZATION_STATE_VERIFIED:
            # The mapping originates from the registry-checked normalizer above,
            # rather than from a caller-controlled free-form provenance field.
            provenance["source_authorization"] = dict(source_authorization.provenance)
        elif source_authorization.state == SOURCE_AUTHORIZATION_STATE_UNVERIFIED_COMPATIBILITY:
            provenance["unverified_compatibility"] = dict(source_authorization.provenance)
        else:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
        return MdSourceSnapshot(
            provider_id=provider.id,
            platform=platform,
            source_id=provider_id,
            adapter_id=adapter_id,
            endpoint_version=source_revision,
            request_fingerprint_sha256=context.query.query_fingerprint,
            provider_request_id=validated.provider_request_id,
            provider_request_fingerprint_sha256=(validated.provider_request_fingerprint_sha256),
            query_fingerprint_sha256=validated.query_fingerprint_sha256,
            source_authorization_state=source_authorization.state,
            source_authorization_descriptor_sha256=source_authorization.descriptor_sha256,
            fetch_lease_key_sha256=(
                fetch_lease.lease_key_sha256 if fetch_lease is not None else None
            ),
            fetch_lease_fence_token=(fetch_lease.fence_token if fetch_lease is not None else None),
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
        record_coordinates: Sequence[tuple[datetime, str]],
    ) -> dict[tuple[datetime, str], int]:
        """Allocate revision ordinals independently for each business record.

        A B2 receipt may carry multiple valid facts at an identical event
        timestamp.  The timestamp still scopes the database lookup, while the
        server-derived semantic-key digest controls which fact receives the
        next revision ordinal.
        """
        if not record_coordinates:
            return {}
        requested = frozenset(record_coordinates)
        if len(requested) != len(record_coordinates):
            raise MarketDataStoreError("DUPLICATE_PROVIDER_RECORD")
        requested_coordinates = tuple(sorted(requested))
        existing_maximums: dict[tuple[datetime, str], int] = {}
        for coordinate_chunk in _coordinate_chunks(
            requested_coordinates,
            _REVISION_COORDINATE_QUERY_CHUNK_SIZE,
        ):
            # Use a locking/current read after the series lock. Under MySQL's
            # default REPEATABLE READ, the earlier ordinary series lookup may
            # have established an older consistent snapshot; a later plain
            # aggregate could therefore miss a revision committed by the prior
            # holder while this writer waited for the series lock. MySQL does
            # not support a portable aggregate locking read, so read the rows
            # under FOR UPDATE and calculate the bounded maxima in-process.
            rows = (
                await self._db.execute(
                    _revision_number_current_read_statement(
                        series_id=series_id,
                        record_coordinates=coordinate_chunk,
                    )
                )
            ).all()
            if len(rows) > _MAX_CURRENT_REVISION_ROWS_PER_CHUNK:
                raise MarketDataStoreError("CURRENT_REVISION_READ_LIMIT_EXCEEDED")
            for event_time, semantic_record_key_sha256, revision_number in rows:
                stored_event_at = _stored_utc(event_time, field_name="revision event_time")
                stored_key_sha256 = _require_sha256_digest(
                    semantic_record_key_sha256,
                    code="LOCAL_OBSERVATION_INTEGRITY",
                )
                coordinate = (stored_event_at, stored_key_sha256)
                if coordinate in requested:
                    current_maximum = existing_maximums.get(coordinate, 0)
                    existing_maximums[coordinate] = max(current_maximum, int(revision_number))
        return {
            coordinate: existing_maximums.get(coordinate, 0) + 1
            for coordinate in record_coordinates
        }

    async def _lock_series_for_revision(
        self,
        series: MdDataSeries,
        context: ResolvedMarketDataQueryContext,
    ) -> MdDataSeries:
        """Serialize per-series revision-number allocation on engines with row locks.

        PostgreSQL and MySQL honour ``FOR UPDATE`` here, so concurrent source
        receipts cannot both allocate the same next revision number for an
        event/semantic-record coordinate. SQLite serializes writes at database
        level; the explicit lock remains a harmless no-op there while keeping
        the service contract uniform across the supported engines.
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
            revision_key_sha256=_observation_revision_identity_sha256(
                contract_version=_OBSERVATION_REVISION_CONTRACT_V3,
                series_semantic_key_sha256=series.semantic_key_sha256,
                source_snapshot_id=source_snapshot.id,
                event_at=observation.event_at,
                available_at=observation.available_at,
                fields_sha256=observation.fields_sha256,
                quality=observation.quality,
                revision_number=revision_number,
                source_available_at=observation.source_available_at,
                semantic_record_key_sha256=observation.semantic_record_key.sha256,
            ),
            normalization_version=NORMALIZATION_VERSION,
            semantic_record_key=observation.semantic_record_key.canonical_json,
            semantic_record_key_sha256=observation.semantic_record_key.sha256,
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
        if (
            not witness.is_trading_day
            or witness.event_type != "session"
            or witness.event_start is None
        ):
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
        or query.family_id != coverage.family_id
        or query.family_contract_version != coverage.family_contract_version
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
    provider_request_evidence = _validated_provider_request_evidence(context, result)
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
    shared_source_payload = _validate_shared_source_payload(
        raw_payload,
        result.shared_source_payload_segment,
    )
    observations: list[_ValidatedProviderObservation] = []
    seen_records: set[tuple[datetime, str]] = set()
    required_fields = frozenset(context.query.required_fields)
    normalized_fields_bytes = 0
    normalized_record_identity_bytes = 0
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
        semantic_record_key = _provider_observation_semantic_record_key(
            context,
            observation,
        )
        normalized_record_identity_bytes += len(semantic_record_key.canonical_json.encode("utf-8"))
        if normalized_record_identity_bytes > _MAX_NORMALIZED_RECORD_IDENTITIES_BYTES:
            raise MarketDataStoreError("PROVIDER_RECORD_IDENTITIES_TOO_LARGE")
        record_coordinate = (event_at, semantic_record_key.sha256)
        if record_coordinate in seen_records:
            # Retain the established single-record failure code so existing
            # callers do not need a semantic-key migration of their own.
            if semantic_record_key.is_singleton:
                raise MarketDataStoreError("DUPLICATE_PROVIDER_EVENT")
            raise MarketDataStoreError("DUPLICATE_PROVIDER_RECORD")
        if available_at > result.retrieved_at:
            raise MarketDataStoreError("PROVIDER_AVAILABILITY_AFTER_RETRIEVAL")
        seen_records.add(record_coordinate)
        fields = _json_safe_mapping(
            normalize_provider_fields(observation.fields),
            field_name="provider observation fields",
        )
        canonical_fields = _canonical_json(fields, field_name="provider observation fields")
        normalized_fields_bytes += len(canonical_fields.encode("utf-8"))
        if normalized_fields_bytes > _MAX_NORMALIZED_FIELDS_BYTES:
            raise MarketDataStoreError("PROVIDER_NORMALIZED_FIELDS_TOO_LARGE")
        missing_required_fields = tuple(
            field_name
            for field_name in sorted(required_fields)
            if not is_usable_field_value(field_name, fields.get(field_name))
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
                semantic_record_key=semantic_record_key,
            )
        )
    return _ValidatedProviderFetch(
        raw_payload=MappingProxyType(raw_payload),
        payload_sha256=_sha256(canonical_raw_payload),
        observations=tuple(observations),
        provider_request_id=provider_request_evidence["provider_request_id"],
        provider_request_fingerprint_sha256=provider_request_evidence[
            "provider_request_fingerprint_sha256"
        ],
        query_fingerprint_sha256=provider_request_evidence["query_fingerprint_sha256"],
        shared_source_payload=shared_source_payload,
    )


def _provider_observation_semantic_record_key(
    context: ResolvedMarketDataQueryContext,
    observation: ProviderMarketObservation,
) -> SemanticRecordKey:
    """Derive the record identity after binding a provider row to its family.

    Provider DTOs may carry business dimensions but never a canonical key or
    digest.  This prevents an adapter from selecting a storage identity that
    disagrees with the server-owned family contract.  The four B2 families are
    intentionally still unconfigured; the lower-level check merely ensures a
    future approved writer cannot accidentally collapse their rows into the
    singleton fact shape.
    """
    family_id = context.query.family_id
    dimensions = observation.record_dimensions
    if family_id in _MULTI_RECORD_FAMILY_IDS:
        if dimensions is None:
            raise MarketDataStoreError("PROVIDER_RECORD_DIMENSIONS_REQUIRED")
    elif dimensions is not None:
        raise MarketDataStoreError("UNEXPECTED_PROVIDER_RECORD_DIMENSIONS")

    if dimensions is None:
        return single_record_semantic_key()

    family_contract_version = context.query.family_contract_version
    if family_id is None or family_contract_version is None:
        raise MarketDataStoreError("PROVIDER_RECORD_FAMILY_BINDING_REQUIRED")
    try:
        normalized_dimensions = normalize_b2_record_dimensions(
            family_id=family_id,
            family_contract_version=family_contract_version,
            dimensions=dimensions,
        )
        return normalize_semantic_record_key(
            family_id=family_id,
            family_contract_version=family_contract_version,
            dimensions=normalized_dimensions,
        )
    except (B2FamilyContractError, TypeError, ValueError) as exc:
        raise MarketDataStoreError("PROVIDER_RECORD_DIMENSIONS_INVALID") from exc


def _validate_shared_source_payload(
    raw_payload: Mapping[str, object],
    segment: SharedSourcePayloadSegment | None,
) -> _ValidatedSharedSourcePayload | None:
    """Extract and content-address one fixed raw segment before any write."""
    if segment is None:
        return None
    if not isinstance(segment, SharedSourcePayloadSegment):
        raise TypeError("shared_source_payload_segment must be SharedSourcePayloadSegment or None")
    if (
        segment.segment_key != "source_batch"
        or segment.payload_format != "canonical-json-utf8-v1"
        or segment.payload_role != "source_batch"
    ):
        raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_SEGMENT_INVALID")
    source_batch = raw_payload.get(segment.segment_key)
    if not isinstance(source_batch, Mapping):
        raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_SEGMENT_MISSING")
    payload_json = _json_safe_mapping(source_batch, field_name="shared source payload")
    canonical_payload_bytes = _canonical_json(
        payload_json,
        field_name="shared source payload",
    ).encode("utf-8")
    payload_bytes = len(canonical_payload_bytes)
    if payload_bytes > MAX_SOURCE_PAYLOAD_BYTES:
        raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_TOO_LARGE")
    receipt_payload = dict(raw_payload)
    del receipt_payload[segment.segment_key]
    return _ValidatedSharedSourcePayload(
        content_sha256=hashlib.sha256(canonical_payload_bytes).hexdigest(),
        payload_format=segment.payload_format,
        payload_role=segment.payload_role,
        payload_bytes=payload_bytes,
        canonical_payload_bytes=canonical_payload_bytes,
        receipt_payload=MappingProxyType(receipt_payload),
    )


def _assert_shared_source_payload_matches(
    stored: MdSourcePayload,
    expected: _ValidatedSharedSourcePayload,
) -> None:
    """Fail closed if a natural-key payload does not exactly match its address."""
    try:
        stored_payload = bytes(stored.canonical_payload_bytes)
    except (TypeError, ValueError) as exc:
        raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_INTEGRITY_CONFLICT") from exc
    if (
        stored.content_sha256 != expected.content_sha256
        or stored.payload_format != expected.payload_format
        or stored.payload_bytes != expected.payload_bytes
        or len(stored_payload) != stored.payload_bytes
        or hashlib.sha256(stored_payload).hexdigest() != stored.content_sha256
        or stored_payload != expected.canonical_payload_bytes
    ):
        raise MarketDataStoreError("SHARED_SOURCE_PAYLOAD_INTEGRITY_CONFLICT")


def _validated_provider_request_evidence(
    context: ResolvedMarketDataQueryContext,
    result: ProviderFetchResult,
) -> Mapping[str, str]:
    """Bind a persisted source receipt to the exact one-time provider DTO.

    ``MarketDataProviderRequest`` already validates its own construction.  The
    store recomputes the DTO digest nevertheless, because this is the last
    boundary before immutable evidence is written and it must not silently
    equate the public query identity with a provider-call identity.
    """
    request = result.request
    request_id = _require_provider_request_id(request.request_id)
    query_fingerprint = _require_sha256_digest(
        context.query.query_fingerprint,
        code="QUERY_FINGERPRINT_INVALID",
    )
    dto_payload = _json_safe_mapping(request.dto_payload, field_name="provider request DTO")
    if dto_payload.get("request_id") != request_id:
        raise MarketDataStoreError("PROVIDER_REQUEST_EVIDENCE_INVALID")
    if dto_payload.get("query_fingerprint") != query_fingerprint:
        raise MarketDataStoreError("PROVIDER_REQUEST_EVIDENCE_INVALID")
    computed_fingerprint = _sha256(_canonical_json(dto_payload, field_name="provider request DTO"))
    declared_fingerprint = _require_sha256_digest(
        request.provider_request_fingerprint_sha256,
        code="PROVIDER_REQUEST_EVIDENCE_INVALID",
    )
    if declared_fingerprint != computed_fingerprint:
        raise MarketDataStoreError("PROVIDER_REQUEST_EVIDENCE_INVALID")
    return MappingProxyType(
        {
            "provider_request_id": request_id,
            "provider_request_fingerprint_sha256": declared_fingerprint,
            "query_fingerprint_sha256": query_fingerprint,
        }
    )


def _normalized_source_authorization_provenance(
    context: ResolvedMarketDataQueryContext,
    source_authorization: MarketDataSourceAuthorization,
    *,
    provider_id: str,
) -> dict[str, object]:
    """Return a canonical authorization receipt mapping for store validation.

    The persistence API intentionally does not accept a free-form mapping.  A
    real ``MarketDataSourceAuthorization`` must identify the actual provider,
    match the resolved query dimensions, state an ALLOW decision, and carry a
    digest recomputed from every persisted authorization field.  The digest is
    an integrity binding, not a cryptographic signature: the store separately
    compares the frozen fields with the current registry.  Public v2 callers
    obtain this typed DTO from the access authorizer before reaching this
    internal persistence boundary.
    """
    if type(source_authorization) is not MarketDataSourceAuthorization:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")

    source_registry_id = _require_text(
        source_authorization.source_registry_id,
        field_name="source_registry_id",
        maximum=255,
    )
    normalized_provider_id = _require_text(provider_id, field_name="provider_id", maximum=255)
    if source_registry_id != normalized_provider_id:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_PROVIDER_MISMATCH")

    asset_type = _require_authorization_lower(
        source_authorization.asset_type,
        field_name="source authorization asset_type",
        maximum=32,
    )
    market = _require_authorization_upper(
        source_authorization.market,
        field_name="source authorization market",
        maximum=128,
    )
    purpose = _require_authorization_lower(
        source_authorization.purpose,
        field_name="source authorization purpose",
        maximum=32,
    )
    venue = context.identity.venue
    if (
        venue is None
        or asset_type != context.identity.asset_type
        or market != venue
        or purpose != context.query.purpose
    ):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_CONTEXT_MISMATCH")
    if purpose not in _SOURCE_AUTHORIZATION_ALLOWED_USES:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_CONTEXT_MISMATCH")

    authorization = {
        "source_registry_id": source_registry_id,
        "registry_updated_at": _require_utc_authorization_timestamp(
            source_authorization.registry_updated_at,
            field_name="source authorization registry_updated_at",
        ),
        "asset_type": asset_type,
        "market": market,
        "purpose": purpose,
        "license_status": _require_authorization_upper(
            source_authorization.license_status,
            field_name="source authorization license_status",
            maximum=64,
        ),
        "allowed_uses": list(
            _require_authorization_tokens(
                source_authorization.allowed_uses,
                field_name="source authorization allowed_uses",
            )
        ),
        "jurisdictions": list(
            _require_authorization_tokens(
                source_authorization.jurisdictions,
                field_name="source authorization jurisdictions",
            )
        ),
        "effective_from": _require_utc_authorization_timestamp(
            source_authorization.effective_from,
            field_name="source authorization effective_from",
        ),
        "effective_to": _require_optional_utc_authorization_timestamp(
            source_authorization.effective_to,
            field_name="source authorization effective_to",
        ),
        "retention_policy": _require_authorization_upper(
            source_authorization.retention_policy,
            field_name="source authorization retention_policy",
            maximum=64,
        ),
        "retention_expires_at": _require_optional_utc_authorization_timestamp(
            source_authorization.retention_expires_at,
            field_name="source authorization retention_expires_at",
        ),
        "redistribution_policy": _require_authorization_upper(
            source_authorization.redistribution_policy,
            field_name="source authorization redistribution_policy",
            maximum=64,
        ),
        "principal_scope": _require_text(
            source_authorization.principal_scope,
            field_name="source authorization principal_scope",
            maximum=256,
        ),
        "tenant_scope": _require_text(
            source_authorization.tenant_scope,
            field_name="source authorization tenant_scope",
            maximum=256,
        ),
        "entitlement_revision": _require_sha256_digest(
            source_authorization.entitlement_revision,
            code="SOURCE_AUTHORIZATION_INVALID",
        ),
        "decision": source_authorization.decision,
    }
    if authorization["decision"] != "ALLOW":
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_DENIED")
    descriptor_hash = _require_sha256_digest(
        source_authorization.descriptor_hash,
        code="SOURCE_AUTHORIZATION_INVALID",
    )
    descriptor_payload = {
        "version": _SOURCE_AUTHORIZATION_VERSION,
        **authorization,
    }
    computed_descriptor_hash = _sha256(
        _canonical_json(
            descriptor_payload,
            field_name="source authorization descriptor",
        )
    )
    if descriptor_hash != computed_descriptor_hash:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_DESCRIPTOR_MISMATCH")
    authorization["descriptor_hash"] = descriptor_hash
    return authorization


def _assert_source_authorization_matches_registry(
    authorization: Mapping[str, object],
    registry: AssetDataSourceRegistry,
    *,
    local_received_at: datetime,
) -> None:
    """Refuse persistence if the supplied authorization is stale or unlicensed.

    Authorization is first evaluated at the query boundary before a local read
    or provider call.  This independent check closes the race between that
    evaluation and immutable receipt persistence by comparing every frozen
    registry field against a freshly loaded current row.  It is not a
    cryptographic trust boundary against code already running in this process.
    """
    if not registry.enabled:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    expected = _registry_authorization_fields(registry)
    for field_name, expected_value in expected.items():
        if authorization.get(field_name) != expected_value:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_STALE")

    asset_type = str(authorization["asset_type"])
    market = str(authorization["market"])
    purpose = str(authorization["purpose"])
    if asset_type.upper() not in _registry_authorization_tokens(
        registry.asset_types,
        field_name="registry asset_types",
    ):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    if authorization["license_status"] not in _SOURCE_AUTHORIZATION_APPROVED_LICENSES:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    allowed_uses = frozenset(str(value) for value in authorization["allowed_uses"])
    if not (_SOURCE_AUTHORIZATION_ALLOWED_USES[purpose] & allowed_uses):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    jurisdictions = tuple(str(value) for value in authorization["jurisdictions"])
    if not _source_authorization_jurisdiction_allows(jurisdictions, market):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    if authorization["retention_policy"] in _SOURCE_AUTHORIZATION_PROHIBITED_RETENTION_POLICIES:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    if (
        authorization["redistribution_policy"]
        not in _SOURCE_AUTHORIZATION_READABLE_REDISTRIBUTION_POLICIES
    ):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")

    at = _require_aware_utc(local_received_at, field_name="local receipt timestamp")
    effective_from = _parse_authorization_timestamp(
        str(authorization["effective_from"]),
        field_name="source authorization effective_from",
    )
    effective_to = _parse_optional_authorization_timestamp(
        authorization["effective_to"],
        field_name="source authorization effective_to",
    )
    retention_expires_at = _parse_optional_authorization_timestamp(
        authorization["retention_expires_at"],
        field_name="source authorization retention_expires_at",
    )
    if effective_from > at or (effective_to is not None and effective_to < at):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")
    if retention_expires_at is not None and retention_expires_at < at:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_DENIED")


def _source_authorization_receipt_purpose_allows_read(
    *,
    receipt_purpose: str,
    query_purpose: str,
) -> bool:
    """Return whether a frozen collection purpose may satisfy this local read.

    Current principal and source authorization are evaluated separately before
    this verifier runs.  This compatibility rule therefore only controls how
    a sealed receipt is reused, and contains the sole audited exception from
    exact purpose matching: ``research_cache_fill`` may serve ``research``.
    """
    return receipt_purpose in _SOURCE_AUTHORIZATION_RECEIPT_PURPOSES_BY_QUERY_PURPOSE.get(
        query_purpose,
        frozenset(),
    )


def _verified_source_authorization_registry_id(
    snapshot: MdSourceSnapshot,
    *,
    context: ResolvedMarketDataQueryContext,
) -> str:
    """Validate frozen authorization evidence before a v2 local read uses it.

    The relational state filters legacy and compatibility rows in SQL.  This
    verifier then binds a verified state to its canonical provenance, immutable
    source identifier, and the query's asset/market/purpose dimensions.  It is
    an integrity check for persisted evidence, not a cryptographic signature
    against trusted code already running inside this process.
    """
    if snapshot.source_authorization_state != SOURCE_AUTHORIZATION_STATE_VERIFIED:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_UNVERIFIED")
    try:
        descriptor_sha256 = _require_sha256_digest(
            snapshot.source_authorization_descriptor_sha256,
            code="SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY",
        )
        snapshot_source_id = _require_text(
            snapshot.source_id,
            field_name="source snapshot source_id",
            maximum=255,
        )
        provenance = _json_safe_mapping(
            snapshot.provenance_json,
            field_name="source snapshot provenance",
        )
        authorization = _json_safe_mapping(
            provenance.get("source_authorization"),
            field_name="source authorization provenance",
        )
        if set(authorization) != _SOURCE_AUTHORIZATION_PROVENANCE_FIELDS:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
        persisted_descriptor = authorization.pop("descriptor_hash")
        if persisted_descriptor != descriptor_sha256:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
        canonical_descriptor = _sha256(
            _canonical_json(
                {"version": _SOURCE_AUTHORIZATION_VERSION, **authorization},
                field_name="source authorization provenance",
            )
        )
        if canonical_descriptor != descriptor_sha256:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")

        source_registry_id = _require_text(
            authorization["source_registry_id"],
            field_name="source authorization source_registry_id",
            maximum=255,
        )
        if source_registry_id != snapshot_source_id:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
        asset_type = _require_authorization_lower(
            authorization["asset_type"],
            field_name="source authorization asset_type",
            maximum=32,
        )
        market = _require_authorization_upper(
            authorization["market"],
            field_name="source authorization market",
            maximum=128,
        )
        purpose = _require_authorization_lower(
            authorization["purpose"],
            field_name="source authorization purpose",
            maximum=32,
        )
        venue = context.identity.venue
        if (
            venue is None
            or asset_type != context.identity.asset_type
            or market != venue
            or not _source_authorization_receipt_purpose_allows_read(
                receipt_purpose=purpose,
                query_purpose=context.query.purpose,
            )
            or purpose not in _SOURCE_AUTHORIZATION_ALLOWED_USES
        ):
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")

        _require_utc_authorization_timestamp(
            authorization["registry_updated_at"],
            field_name="source authorization registry_updated_at",
        )
        license_status = _require_authorization_upper(
            authorization["license_status"],
            field_name="source authorization license_status",
            maximum=64,
        )
        allowed_uses = _require_persisted_authorization_tokens(
            authorization["allowed_uses"],
            field_name="source authorization allowed_uses",
        )
        jurisdictions = _require_persisted_authorization_tokens(
            authorization["jurisdictions"],
            field_name="source authorization jurisdictions",
        )
        effective_from = _parse_authorization_timestamp(
            _require_utc_authorization_timestamp(
                authorization["effective_from"],
                field_name="source authorization effective_from",
            ),
            field_name="source authorization effective_from",
        )
        effective_to_value = _require_optional_utc_authorization_timestamp(
            authorization["effective_to"],
            field_name="source authorization effective_to",
        )
        effective_to = _parse_optional_authorization_timestamp(
            effective_to_value,
            field_name="source authorization effective_to",
        )
        retention_policy = _require_authorization_upper(
            authorization["retention_policy"],
            field_name="source authorization retention_policy",
            maximum=64,
        )
        retention_expires_at_value = _require_optional_utc_authorization_timestamp(
            authorization["retention_expires_at"],
            field_name="source authorization retention_expires_at",
        )
        retention_expires_at = _parse_optional_authorization_timestamp(
            retention_expires_at_value,
            field_name="source authorization retention_expires_at",
        )
        redistribution_policy = _require_authorization_upper(
            authorization["redistribution_policy"],
            field_name="source authorization redistribution_policy",
            maximum=64,
        )
        _require_text(
            authorization["principal_scope"],
            field_name="source authorization principal_scope",
            maximum=256,
        )
        _require_text(
            authorization["tenant_scope"],
            field_name="source authorization tenant_scope",
            maximum=256,
        )
        _require_sha256_digest(
            authorization["entitlement_revision"],
            code="SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY",
        )
        if authorization["decision"] != "ALLOW":
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
        if (
            license_status not in _SOURCE_AUTHORIZATION_APPROVED_LICENSES
            or not (_SOURCE_AUTHORIZATION_ALLOWED_USES[purpose] & frozenset(allowed_uses))
            or not _source_authorization_jurisdiction_allows(jurisdictions, market)
            or retention_policy in _SOURCE_AUTHORIZATION_PROHIBITED_RETENTION_POLICIES
            or redistribution_policy not in _SOURCE_AUTHORIZATION_READABLE_REDISTRIBUTION_POLICIES
        ):
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
        receipt_at = _stored_utc(snapshot.retrieved_at, field_name="source snapshot retrieved_at")
        if effective_from > receipt_at or (effective_to is not None and effective_to < receipt_at):
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
        if retention_expires_at is not None and retention_expires_at < receipt_at:
            raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
    except (KeyError, TypeError, ValueError, MarketDataStoreError) as exc:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY") from exc
    return source_registry_id


def _registry_authorization_fields(registry: AssetDataSourceRegistry) -> dict[str, object]:
    """Normalize exactly the registry dimensions frozen into a receipt."""
    return {
        "source_registry_id": _require_text(
            registry.source_id,
            field_name="registry source_id",
            maximum=255,
        ),
        "registry_updated_at": _stored_utc(
            registry.updated_at,
            field_name="registry updated_at",
        ).isoformat(),
        "license_status": _require_authorization_upper(
            _normalized_registry_authorization_token(
                registry.license_status,
                field_name="registry license_status",
                maximum=64,
            ),
            field_name="registry license_status",
            maximum=64,
        ),
        "allowed_uses": list(
            _registry_authorization_tokens(
                registry.allowed_uses,
                field_name="registry allowed_uses",
            )
        ),
        "jurisdictions": list(
            _registry_authorization_tokens(
                registry.jurisdictions,
                field_name="registry jurisdictions",
            )
        ),
        "effective_from": _stored_utc(
            registry.effective_from,
            field_name="registry effective_from",
        ).isoformat(),
        "effective_to": (
            _stored_utc(registry.effective_to, field_name="registry effective_to").isoformat()
            if registry.effective_to is not None
            else None
        ),
        "retention_policy": _require_authorization_upper(
            _normalized_registry_authorization_token(
                registry.retention_policy,
                field_name="registry retention_policy",
                maximum=64,
            ),
            field_name="registry retention_policy",
            maximum=64,
        ),
        "retention_expires_at": (
            _stored_utc(
                registry.retention_expires_at,
                field_name="registry retention_expires_at",
            ).isoformat()
            if registry.retention_expires_at is not None
            else None
        ),
        "redistribution_policy": _require_authorization_upper(
            _normalized_registry_authorization_token(
                registry.redistribution_policy,
                field_name="registry redistribution_policy",
                maximum=64,
            ),
            field_name="registry redistribution_policy",
            maximum=64,
        ),
    }


def _require_authorization_tokens(value: object, *, field_name: str) -> tuple[str, ...]:
    """Require the immutable tuple shape emitted by the authorization boundary."""
    if not isinstance(value, tuple):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
    normalized = tuple(
        _require_authorization_upper(item, field_name=field_name, maximum=128) for item in value
    )
    if not normalized or normalized != tuple(sorted(set(normalized))):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
    return normalized


def _require_persisted_authorization_tokens(value: object, *, field_name: str) -> tuple[str, ...]:
    """Require the canonical JSON list stored from an authorization receipt."""
    if not isinstance(value, list):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
    normalized = tuple(
        _require_authorization_upper(item, field_name=field_name, maximum=128) for item in value
    )
    if not normalized or normalized != tuple(sorted(set(normalized))):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_RECEIPT_INTEGRITY")
    return normalized


def _registry_authorization_tokens(value: object, *, field_name: str) -> tuple[str, ...]:
    """Normalize a registry JSON list without accepting a free-form scalar."""
    if not isinstance(value, (list, tuple)):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_INVALID")
    normalized = tuple(
        sorted(
            {
                _normalized_registry_authorization_token(
                    item,
                    field_name=field_name,
                    maximum=128,
                )
                for item in value
            }
        )
    )
    if not normalized:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REGISTRY_INVALID")
    return normalized


def _normalized_registry_authorization_token(
    value: object,
    *,
    field_name: str,
    maximum: int,
) -> str:
    """Normalize registry text just as the authorization boundary does."""
    return _require_text(value, field_name=field_name, maximum=maximum).upper()


def _require_authorization_lower(value: object, *, field_name: str, maximum: int) -> str:
    """Require a canonical lowercase authorization token."""
    normalized = _require_text(value, field_name=field_name, maximum=maximum)
    if normalized != normalized.lower():
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
    return normalized


def _require_authorization_upper(value: object, *, field_name: str, maximum: int) -> str:
    """Require a canonical uppercase authorization token."""
    normalized = _require_text(value, field_name=field_name, maximum=maximum)
    if normalized != normalized.upper():
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
    return normalized


def _require_utc_authorization_timestamp(value: object, *, field_name: str) -> str:
    """Require the canonical UTC ISO-8601 form emitted by the authorizer."""
    parsed = _parse_authorization_timestamp(value, field_name=field_name)
    canonical = parsed.isoformat()
    if value != canonical:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
    return canonical


def _require_optional_utc_authorization_timestamp(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_utc_authorization_timestamp(value, field_name=field_name)


def _parse_authorization_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_INVALID") from exc
    return _require_aware_utc(parsed, field_name=field_name)


def _parse_optional_authorization_timestamp(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _parse_authorization_timestamp(value, field_name=field_name)


def _source_authorization_jurisdiction_allows(jurisdictions: Sequence[str], market: str) -> bool:
    """Apply the registry's global, venue, and country-prefix market rules."""
    if "GLOBAL" in jurisdictions:
        return True
    market_prefix = market.split("-", maxsplit=1)[0]
    return market in jurisdictions or market_prefix in jurisdictions


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
        and request.family_id == context.query.family_id
        and request.family_contract_version == context.query.family_contract_version
    )


def _revision_source_available_at(
    row: MdObservationRevision,
    *,
    available_at: datetime,
) -> datetime:
    """Recover one upstream availability claim without weakening local PIT evidence."""
    try:
        provenance = _json_safe_mapping(
            row.provenance_json,
            field_name="persisted observation provenance",
        )
        raw_source_available_at = provenance.get("provider_available_at")
        if not isinstance(raw_source_available_at, str):
            raise ValueError("provider_available_at must be an ISO-8601 string")
        source_available_at = _parse_timestamp(
            raw_source_available_at,
            field_name="provider_available_at",
        )
    except (MarketDataStoreError, TypeError, ValueError) as exc:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY") from exc
    if source_available_at > available_at:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    return source_available_at


def _observation_revision_identity_sha256(
    *,
    contract_version: str,
    series_semantic_key_sha256: str,
    source_snapshot_id: str,
    event_at: datetime,
    available_at: datetime,
    fields_sha256: str,
    quality: ObservationQuality,
    revision_number: int,
    source_available_at: datetime | None,
    semantic_record_key_sha256: str | None = None,
) -> str:
    """Build the immutable identity for one normalized observation revision."""
    revision_payload: dict[str, object] = {
        "revision_contract_version": contract_version,
        "series_semantic_key_sha256": series_semantic_key_sha256,
        "source_snapshot_id": source_snapshot_id,
        "event_at": event_at.isoformat(),
        "available_at": available_at.isoformat(),
        "fields_sha256": fields_sha256,
        "quality_status": quality.value,
        "revision_number": revision_number,
    }
    if contract_version in {
        _OBSERVATION_REVISION_CONTRACT_V2,
        _OBSERVATION_REVISION_CONTRACT_V3,
    }:
        if source_available_at is None:
            raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
        revision_payload["provider_available_at"] = source_available_at.isoformat()
    elif contract_version != _OBSERVATION_REVISION_CONTRACT_V1:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    if contract_version == _OBSERVATION_REVISION_CONTRACT_V3:
        revision_payload["semantic_record_key_sha256"] = _require_sha256_digest(
            semantic_record_key_sha256,
            code="LOCAL_OBSERVATION_INTEGRITY",
        )
    elif semantic_record_key_sha256 is not None:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    return _sha256(_canonical_json(revision_payload, field_name="revision identity"))


def _persisted_semantic_record_key(row: MdObservationRevision) -> SemanticRecordKey:
    """Recover and revalidate one immutable server-owned record identity."""
    raw_canonical_json = row.semantic_record_key
    raw_sha256 = row.semantic_record_key_sha256
    try:
        if not isinstance(raw_canonical_json, str):
            raise TypeError("semantic_record_key must be a string")
        payload = json.loads(raw_canonical_json)
        if not isinstance(payload, Mapping):
            raise ValueError("semantic_record_key must decode to an object")
        if raw_canonical_json == SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON:
            return SemanticRecordKey(
                canonical_json=raw_canonical_json,
                sha256=raw_sha256,
                dimensions={},
                is_singleton=True,
            )
        return SemanticRecordKey(
            canonical_json=raw_canonical_json,
            sha256=raw_sha256,
            dimensions=payload.get("dimensions"),
            is_singleton=False,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY") from exc


def _verified_revision_source_available_at(
    row: MdObservationRevision,
    *,
    context: ResolvedMarketDataQueryContext,
    event_at: datetime,
    available_at: datetime,
    fields_sha256: str,
    quality: ObservationQuality,
    revision_number: int,
    semantic_record_key: SemanticRecordKey,
) -> datetime | None:
    """Return a sealed source timestamp after validating the immutable identity.

    V1/V2 facts predate record-key sealing and remain valid only for the
    singleton identity supplied by the migration.  Every new V3 fact binds its
    semantic key digest, including new single-record writes.
    """
    series_semantic_key_sha256 = MarketDataStore.series_identity(context).semantic_key_sha256
    if semantic_record_key.is_singleton:
        v1_identity = _observation_revision_identity_sha256(
            contract_version=_OBSERVATION_REVISION_CONTRACT_V1,
            series_semantic_key_sha256=series_semantic_key_sha256,
            source_snapshot_id=row.source_snapshot_id,
            event_at=event_at,
            available_at=available_at,
            fields_sha256=fields_sha256,
            quality=quality,
            revision_number=revision_number,
            source_available_at=None,
        )
        if row.revision_key_sha256 == v1_identity:
            # The v1 contract did not bind provider availability.  Even a
            # syntactically valid timestamp in its free-form provenance is not
            # a verified source fact and must stay unavailable to strict
            # consumers.
            return None

        source_available_at = _revision_source_available_at(row, available_at=available_at)
        v2_identity = _observation_revision_identity_sha256(
            contract_version=_OBSERVATION_REVISION_CONTRACT_V2,
            series_semantic_key_sha256=series_semantic_key_sha256,
            source_snapshot_id=row.source_snapshot_id,
            event_at=event_at,
            available_at=available_at,
            fields_sha256=fields_sha256,
            quality=quality,
            revision_number=revision_number,
            source_available_at=source_available_at,
        )
        if row.revision_key_sha256 == v2_identity:
            return source_available_at
    else:
        source_available_at = _revision_source_available_at(row, available_at=available_at)

    v3_identity = _observation_revision_identity_sha256(
        contract_version=_OBSERVATION_REVISION_CONTRACT_V3,
        series_semantic_key_sha256=series_semantic_key_sha256,
        source_snapshot_id=row.source_snapshot_id,
        event_at=event_at,
        available_at=available_at,
        fields_sha256=fields_sha256,
        quality=quality,
        revision_number=revision_number,
        source_available_at=source_available_at,
        semantic_record_key_sha256=semantic_record_key.sha256,
    )
    if row.revision_key_sha256 != v3_identity:
        raise MarketDataStoreError("LOCAL_OBSERVATION_INTEGRITY")
    return source_available_at


def _decode_local_revision(
    row: MdObservationRevision,
    *,
    context: ResolvedMarketDataQueryContext,
    visibility_anchor: MarketDataVisibilityAnchor,
    published_at: datetime,
    visibility_sequence: int,
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
    if not _is_visibility_sequence(visibility_sequence) or not visibility_anchor.permits(
        visible_at=committed_at,
        visibility_sequence=visibility_sequence,
    ):
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
    semantic_record_key = _persisted_semantic_record_key(row)
    source_available_at = _verified_revision_source_available_at(
        row,
        context=context,
        event_at=event_at,
        available_at=available_at,
        fields_sha256=row.fields_sha256,
        quality=quality,
        revision_number=row.revision_number,
        semantic_record_key=semantic_record_key,
    )
    return LocalObservationRevision(
        revision_id=row.id,
        source_snapshot_id=row.source_snapshot_id,
        event_at=event_at,
        available_at=available_at,
        committed_at=committed_at,
        visible_at=committed_at,
        visibility_sequence=visibility_sequence,
        revision_number=row.revision_number,
        quality=quality,
        semantic_record_key=semantic_record_key.canonical_json,
        semantic_record_key_sha256=semantic_record_key.sha256,
        fields=MappingProxyType(fields),
        source_available_at=source_available_at,
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


def _verified_calendar_source_registry_id(snapshot: MdCalendarSnapshot) -> str:
    """Validate immutable calendar governance before it can prove coverage.

    Calendar imports freeze a registry-backed descriptor into the immutable
    definition.  The reader recomputes its digest and binds it to the relational
    source columns before treating an importer-written snapshot as evidence.
    This verifies persisted structure and integrity; it is not a signature over
    arbitrary in-process input.  The current v2 access grant performs the
    separate present-tense source entitlement check through
    ``allowed_source_registry_ids``.
    """
    if snapshot.source_governance_state != CALENDAR_SOURCE_GOVERNANCE_STATE_VERIFIED:
        raise MarketDataStoreError("CALENDAR_SOURCE_UNVERIFIED")
    source_registry_id = _require_text(
        snapshot.source_registry_id,
        field_name="calendar source_registry_id",
        maximum=128,
    )
    descriptor_sha256 = _require_sha256_digest(
        snapshot.source_governance_descriptor_sha256,
        code="CALENDAR_SOURCE_GOVERNANCE_INTEGRITY",
    )
    definition = _json_safe_mapping(snapshot.definition_json, field_name="calendar definition")
    manifest_hash = _require_sha256_digest(
        definition.get("manifest_hash"),
        code="CALENDAR_SOURCE_GOVERNANCE_INTEGRITY",
    )
    snapshot_hash = _require_sha256_digest(
        snapshot.snapshot_sha256,
        code="CALENDAR_SOURCE_GOVERNANCE_INTEGRITY",
    )
    if manifest_hash != snapshot_hash:
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    governance = _json_safe_mapping(
        definition.get("source_governance"),
        field_name="calendar source governance",
    )
    actual_descriptor = governance.pop("descriptor_hash", None)
    if actual_descriptor != descriptor_sha256:
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    if _sha256(_canonical_json(governance, field_name="calendar source governance")) != (
        descriptor_sha256
    ):
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    if set(governance) != {
        "version",
        "source_registry_id",
        "registry_updated_at",
        "license_status",
        "asset_types",
        "jurisdictions",
        "allowed_uses",
        "effective_from",
        "effective_to",
        "retention_policy",
        "retention_expires_at",
        "redistribution_policy",
        "approval_reference",
        "evidence_uri",
        "evidence_content_hash",
        "calendar_manifest_hash",
        "decision",
    }:
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    if (
        governance["version"] != _CALENDAR_SOURCE_GOVERNANCE_VERSION
        or governance["source_registry_id"] != source_registry_id
        or governance["calendar_manifest_hash"] != manifest_hash
        or governance["decision"] != "ALLOW"
    ):
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    _require_utc_authorization_timestamp(
        governance["registry_updated_at"],
        field_name="calendar source registry_updated_at",
    )
    _require_authorization_upper(
        governance["license_status"],
        field_name="calendar source license_status",
        maximum=64,
    )
    _require_calendar_governance_tokens(
        governance["asset_types"],
        field_name="calendar source asset_types",
    )
    _require_calendar_governance_tokens(
        governance["jurisdictions"],
        field_name="calendar source jurisdictions",
    )
    _require_calendar_governance_tokens(
        governance["allowed_uses"],
        field_name="calendar source allowed_uses",
    )
    _require_utc_authorization_timestamp(
        governance["effective_from"],
        field_name="calendar source effective_from",
    )
    _require_optional_utc_authorization_timestamp(
        governance["effective_to"],
        field_name="calendar source effective_to",
    )
    _require_authorization_upper(
        governance["retention_policy"],
        field_name="calendar source retention_policy",
        maximum=64,
    )
    _require_optional_utc_authorization_timestamp(
        governance["retention_expires_at"],
        field_name="calendar source retention_expires_at",
    )
    _require_authorization_upper(
        governance["redistribution_policy"],
        field_name="calendar source redistribution_policy",
        maximum=64,
    )
    _require_text(
        governance["approval_reference"],
        field_name="calendar approval_reference",
        maximum=255,
    )
    _require_text(
        governance["evidence_uri"],
        field_name="calendar evidence_uri",
        maximum=2048,
    )
    _require_sha256_digest(
        governance["evidence_content_hash"],
        code="CALENDAR_SOURCE_GOVERNANCE_INTEGRITY",
    )
    return source_registry_id


def _require_calendar_governance_tokens(value: object, *, field_name: str) -> tuple[str, ...]:
    """Require a canonical list frozen by the registry-backed importer."""
    if not isinstance(value, list):
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    normalized = tuple(
        _require_authorization_upper(item, field_name=field_name, maximum=128) for item in value
    )
    if not normalized or normalized != tuple(sorted(set(normalized))):
        raise MarketDataStoreError("CALENDAR_SOURCE_GOVERNANCE_INTEGRITY")
    return normalized


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
    candidates: Sequence[tuple[MdCalendarSnapshot, TimeWindow, datetime, int]],
    requested: TimeWindow,
) -> list[tuple[MdCalendarSnapshot, TimeWindow, datetime, int]] | None:
    """Select contiguous immutable blocks that prove one full calendar window.

    Import serialization rejects overlaps. This reader repeats that invariant
    defensively and concatenates adjacent rolling manifests without inventing
    weekday or holiday behavior. A gap remains an unknown calendar.
    """
    selected: list[tuple[MdCalendarSnapshot, TimeWindow, datetime, int]] = []
    cursor = requested.start_at
    ordered = sorted(candidates, key=lambda item: (item[1].start_at, item[1].end_at, item[0].id))
    for candidate in ordered:
        _snapshot, coverage, _published_at, _visibility_sequence = candidate
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
    segments: Sequence[tuple[MdCalendarSnapshot, TimeWindow, datetime, int]],
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


def _unknown_calendar_trading_day_events(
    *,
    calendar: CalendarSnapshot,
    visibility_anchor: MarketDataVisibilityAnchor,
    data_kind: str,
    frequency: str,
    reason: str,
) -> CalendarTradingDayEvents:
    """Return a typed absence without leaking a partial date-to-key map."""
    return CalendarTradingDayEvents(
        calendar_code=calendar.calendar_id,
        calendar_version=calendar.calendar_version,
        data_kind=data_kind,
        frequency=frequency,
        calendar_snapshot_id=None,
        timezone_name=calendar.timezone_name,
        coverage_window=None,
        visibility_anchor=visibility_anchor,
        status=CalendarStatus.UNKNOWN,
        reason=_require_text(reason, field_name="calendar trading-day reason", maximum=128),
        events=(),
    )


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


def _publication_is_visible_at_anchor(anchor: MarketDataVisibilityAnchor):
    """Build the portable complete-boundary predicate for one PIT anchor.

    The timestamp is a ceiling and the globally monotonic sequence is a
    separate ceiling.  Both are necessary: a client may ask for a future
    historical cutoff, and a subsequent receipt can retain an earlier
    timestamp while still receiving a later global sequence.
    """
    return and_(
        MdPublication.published_at <= anchor.visible_at,
        MdPublication.visibility_sequence <= anchor.max_visibility_sequence,
    )


def _is_visibility_sequence(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _normalize_allowed_source_registry_ids(
    value: frozenset[str] | None,
) -> frozenset[str] | None:
    """Validate the exact current-source allow-list used for a local read."""
    if value is None:
        return None
    if not isinstance(value, frozenset):
        raise TypeError("allowed_source_registry_ids must be a frozenset when supplied")
    return frozenset(
        _require_text(source_id, field_name="allowed source_registry_id", maximum=255)
        for source_id in value
    )


def _normalize_unverified_compatibility_reason(value: object) -> str:
    """Require a deliberately named, narrowly scoped no-grant write path."""
    if value is None:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REQUIRED")
    normalized = _require_text(
        value,
        field_name="unverified compatibility reason",
        maximum=64,
    )
    if normalized not in _UNVERIFIED_COMPATIBILITY_REASONS:
        raise MarketDataStoreError("SOURCE_AUTHORIZATION_REQUIRED")
    return normalized


def _require_provider_request_id(value: object) -> str:
    """Validate the CSPRNG request ID shape before it becomes receipt evidence."""
    normalized = _require_text(value, field_name="provider request_id", maximum=128)
    if len(normalized) < 32 or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in normalized
    ):
        raise MarketDataStoreError("PROVIDER_REQUEST_EVIDENCE_INVALID")
    return normalized


def _require_sha256_digest(value: object, *, code: str) -> str:
    """Return one canonical lowercase SHA-256 digest or a stable failure code."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MarketDataStoreError(code)
    return value


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


def _revision_is_usable_for_fields(
    revision: LocalObservationRevision,
    required_fields: Sequence[str],
) -> bool:
    """Return whether a persisted revision can satisfy this field projection."""
    return revision.quality is ObservationQuality.PASS and all(
        is_usable_field_value(field_name, revision.fields.get(field_name))
        for field_name in required_fields
    )


def _coordinate_chunks(
    values: Sequence[tuple[datetime, str]],
    size: int,
) -> tuple[tuple[tuple[datetime, str], ...], ...]:
    """Split exact event/key coordinate pairs below SQLite's bind-value budget."""
    return tuple(tuple(values[index : index + size]) for index in range(0, len(values), size))


def _series_lookup_statement(
    *,
    semantic_key_sha256: str,
    for_update: bool,
) -> Select[tuple[MdDataSeries]]:
    """Build an exact series lookup, using a current read when recovering a race."""
    statement = select(MdDataSeries).where(MdDataSeries.semantic_key_sha256 == semantic_key_sha256)
    return statement.with_for_update() if for_update else statement


def _revision_number_current_read_statement(
    *,
    series_id: str,
    record_coordinates: Sequence[tuple[datetime, str]],
) -> Select[tuple[datetime, str, int]]:
    """Build the post-series-lock current read used for ordinal allocation.

    The series row is locked before this query, serializing writers for one
    semantic series. ``FOR UPDATE`` additionally makes MySQL/InnoDB evaluate
    this read against the latest committed state rather than an earlier
    REPEATABLE READ snapshot established by a harmless pre-lock lookup. The
    predicate contains each requested event/key coordinate, never every
    historical record for a matching event. A bounded response prevents one
    pathological correction history from turning ordinal allocation into an
    unbounded materialization; callers fail before writing a new receipt.
    """
    return (
        select(
            MdObservationRevision.event_time,
            MdObservationRevision.semantic_record_key_sha256,
            MdObservationRevision.revision_number,
        )
        .where(
            MdObservationRevision.series_id == series_id,
            tuple_(
                MdObservationRevision.event_time,
                MdObservationRevision.semantic_record_key_sha256,
            ).in_(record_coordinates),
        )
        .order_by(
            MdObservationRevision.event_time,
            MdObservationRevision.semantic_record_key_sha256,
            MdObservationRevision.revision_number.desc(),
        )
        .limit(_MAX_CURRENT_REVISION_ROWS_PER_CHUNK + 1)
        .with_for_update()
    )


def _revision_sort_key(revision: LocalObservationRevision) -> tuple[int, int, str]:
    """Order selected revisions by sealed receipt, ordinal, then immutable ID."""
    return (
        revision.visibility_sequence,
        revision.revision_number,
        revision.revision_id,
    )


def _record_revision_output_sort_key(
    revision: LocalObservationRevision,
) -> tuple[datetime, str, int, str]:
    """Keep B2/PIT output stable across equal-timestamp business records."""
    return (
        revision.event_at,
        revision.semantic_record_key,
        revision.revision_number,
        revision.revision_id,
    )
