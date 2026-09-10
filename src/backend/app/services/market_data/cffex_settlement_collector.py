"""Fail-closed scheduled collection for CFFEX daily futures settlement facts.

``futures.settlement`` is intentionally still an unconfigured public family.
This module is therefore an internal, opt-in collector candidate rather than a
request-time provider route.  A source returns one raw all-CFFEX snapshot for
one explicit trading date; the collector freezes the target identity map before
that I/O, validates every known contract row, and writes each immutable receipt
through :class:`MarketDataStore`.

The underlying normalized store is single-series oriented.  Each target gets
its own source receipt, but every receipt carries the complete immutable batch
envelope and the same batch digest, source retrieval instant, and fenced feed
lease.  That preserves the fact that one source call supplied the collection
without pretending it was an exact per-contract network request.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urlsplit

from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseError,
)
from app.services.market_data.field_quality import (
    FieldQualityValueError,
    normalize_numeric_field_value,
)
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.store import (
    MarketDataStore,
    PersistedProviderFetch,
)

UTC = timezone.utc
CFFEX_SETTLEMENT_COLLECTOR_VERSION = "cffex-settlement-collector-v1"
CFFEX_SETTLEMENT_PROVIDER_ENDPOINT = "futures_hist_daily_cffex"
CFFEX_SETTLEMENT_REQUIRED_FIELDS = frozenset({"settle", "previous_settle", "open_interest"})
CFFEX_SETTLEMENT_DATASET_CODE = "market.settlement"
CFFEX_SETTLEMENT_FAMILY_ID = "futures.settlement"
CFFEX_SETTLEMENT_FAMILY_CONTRACT_VERSION = "market-data-family-v1"
CFFEX_SETTLEMENT_MARKET = "CFFEX"
CFFEX_SETTLEMENT_SOURCE_POLICY_ID = "market-cffex-settlement-batch-v1"
CFFEX_SETTLEMENT_ADJUSTMENT = "unadjusted"
CFFEX_SETTLEMENT_PRICE_BASIS = "settle"
CFFEX_SETTLEMENT_CURRENCY = "CNY"
CFFEX_SETTLEMENT_UNIT = "contract"
CFFEX_SETTLEMENT_TRANSPORT_EVIDENCE_VERSION = "cffex-settlement-transport-evidence-v1"
CFFEX_SETTLEMENT_TRANSPORT_CERTIFICATE_POLICY = "pinned-peer-certificate-sha256-v1"
CFFEX_SETTLEMENT_DEFAULT_SOURCE_DESCRIPTOR_ID = "cffex-settlement-default-v1"
_MAX_SOURCE_ROWS = 50_000
_MAX_SOURCE_PAYLOAD_BYTES = 10 * 1024 * 1024
_MAX_NESTING_DEPTH = 32
_CFFEX_SYMBOL = re.compile(r"^[A-Z]{1,4}[0-9]{4}$")


class CffexSettlementCollectorError(ValueError):
    """Stable rejection emitted before an unsafe batch can become canonical data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CffexSettlementCollectorPartialPublishError(CffexSettlementCollectorError):
    """Report a sequential-store failure after an earlier target was published.

    ``MarketDataStore.persist_provider_result`` owns one immutable receipt and
    one publication transition per canonical series. The collector validates
    the complete source batch before starting those writes, but it must not
    present those independent publications as an atomic multi-series commit.
    This error exposes the durable prefix so an operator can reconcile or
    retry the exact date without guessing which contracts became visible.
    """

    def __init__(self, persisted_fetches: Sequence[PersistedProviderFetch]) -> None:
        super().__init__("CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED")
        self.persisted_fetches = tuple(persisted_fetches)


class CffexSettlementCollectorFetchLeaseReleaseError(CffexSettlementCollectorError):
    """Expose durable receipts when the post-publication feed lease cannot release.

    A release failure does not undo the individually published canonical
    receipts.  The caller therefore needs the same exact receipt prefix it
    would receive from a later Store failure before it decides whether to
    reconcile, retry, or wait for the lease to expire.
    """

    def __init__(self, persisted_fetches: Sequence[PersistedProviderFetch]) -> None:
        super().__init__("CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED")
        self.persisted_fetches = tuple(persisted_fetches)


class CffexSettlementCollectorPartialPublishCancelledError(asyncio.CancelledError):
    """Preserve task cancellation while exposing its already durable prefix.

    The collector cannot roll back a prior canonical series publication when a
    scheduler cancels a later target.  Raising a ``CancelledError`` subclass
    keeps cancellation handling intact while giving the scheduler the exact
    receipts it must reconcile before it retries the frozen date.
    """

    code = "CFFEX_SETTLEMENT_BATCH_PARTIALLY_PUBLISHED_CANCELLED"

    def __init__(self, persisted_fetches: Sequence[PersistedProviderFetch]) -> None:
        super().__init__(self.code)
        self.persisted_fetches = tuple(persisted_fetches)


@dataclass(frozen=True, slots=True)
class CffexSettlementSourceBatch:
    """One source-owned, market-wide response for a single CFFEX trading date.

    ``raw_payload`` is an immutable evidence envelope.  It must carry the
    explicit CFFEX collector request, the exact CFFEX-specific source route,
    versioned HTTPS/certificate transport evidence, and all returned rows
    under ``response_rows``; callers never supply a separate normalized row
    list that could diverge from the durable source receipt.
    """

    provider_id: str
    source_revision: str
    retrieved_at: datetime
    raw_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _require_text(self.provider_id, field_name="provider_id", maximum=255),
        )
        object.__setattr__(
            self,
            "source_revision",
            _require_text(self.source_revision, field_name="source_revision", maximum=128),
        )
        object.__setattr__(
            self,
            "retrieved_at",
            _as_utc(self.retrieved_at, field_name="source retrieved_at"),
        )
        if not isinstance(self.raw_payload, Mapping):
            raise TypeError("raw_payload must be a mapping")
        object.__setattr__(self, "raw_payload", MappingProxyType(dict(self.raw_payload)))


class CffexSettlementSource(Protocol):
    """An authenticated source seam for one all-market request per date."""

    async def fetch_batch(self, *, trading_date: date) -> CffexSettlementSourceBatch:
        """Return the raw CFFEX settlement response for one explicit trading date."""


@dataclass(frozen=True, slots=True)
class CffexSettlementSourceDescriptor:
    """One reviewed source identity that binds transport evidence before I/O."""

    descriptor_id: str
    provider_id: str
    source_revision: str
    endpoint: str
    origin: str
    certificate_policy: str
    peer_certificate_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "descriptor_id",
            _require_text(self.descriptor_id, field_name="source descriptor ID", maximum=128),
        )
        object.__setattr__(
            self,
            "provider_id",
            _require_text(self.provider_id, field_name="source descriptor provider", maximum=255),
        )
        object.__setattr__(
            self,
            "source_revision",
            _require_text(
                self.source_revision,
                field_name="source descriptor revision",
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "endpoint",
            _require_text(self.endpoint, field_name="source descriptor endpoint", maximum=255),
        )
        object.__setattr__(self, "origin", _require_https_origin(self.origin))
        if self.certificate_policy != CFFEX_SETTLEMENT_TRANSPORT_CERTIFICATE_POLICY:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_INVALID")
        object.__setattr__(
            self,
            "peer_certificate_sha256",
            _require_lower_sha256(
                self.peer_certificate_sha256,
                code="CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_INVALID",
            ),
        )


@dataclass(frozen=True, slots=True)
class CffexSettlementSourceRegistration:
    """A static reviewed descriptor coupled to a construction-only source factory."""

    descriptor: CffexSettlementSourceDescriptor
    source_factory: Callable[[], CffexSettlementSource]

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, CffexSettlementSourceDescriptor):
            raise TypeError("descriptor must be a CffexSettlementSourceDescriptor")
        if not callable(self.source_factory):
            raise TypeError("source_factory must be callable")


# This candidate intentionally has no registered online source. A future
# accepted change must add one reviewed descriptor and its construction-only
# factory together; callers cannot supply a descriptor or source instance.
CFFEX_SETTLEMENT_REVIEWED_SOURCE_REGISTRY: Mapping[
    str, CffexSettlementSourceRegistration
] = MappingProxyType({})


class AkShareCffexSettlementSource:
    """Hard-disabled placeholder for AkShare's currently unauthenticated route.

    The installed AkShare CFFEX endpoint uses HTTP in the reviewed environment.
    A source receipt hash can prove the bytes retained by this service, but it
    cannot authenticate bytes acquired over that transport.  This candidate
    therefore refuses before importing AkShare or resolving its endpoint. A
    future HTTPS/certificate-reviewed adapter must implement
    :class:`CffexSettlementSource` in its own accepted change.
    """

    provider_id = "akshare"
    source_revision = "akshare.futures_hist_daily_cffex:v1"

    async def fetch_batch(self, *, trading_date: date) -> CffexSettlementSourceBatch:
        _require_trading_date(trading_date)
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_UNAPPROVED")


@dataclass(frozen=True, slots=True)
class CffexSettlementCollectionTarget:
    """One frozen canonical target authorized before the source call begins."""

    context: ResolvedMarketDataQueryContext
    source_authorization: MarketDataSourceAuthorization

    def __post_init__(self) -> None:
        if not isinstance(self.context, ResolvedMarketDataQueryContext):
            raise TypeError("context must be a ResolvedMarketDataQueryContext")
        if not isinstance(self.source_authorization, MarketDataSourceAuthorization):
            raise TypeError("source_authorization must be a MarketDataSourceAuthorization")


@dataclass(frozen=True, slots=True)
class CffexSettlementCollectionReport:
    """Safe aggregate proof that every target in one source batch published.

    This type is returned only after all target receipts have published. A
    later sequential write failure instead raises
    :class:`CffexSettlementCollectorPartialPublishError` with its published
    prefix, so callers cannot mistake an incomplete batch for a success.
    """

    trading_date: date
    provider_id: str
    source_revision: str
    source_retrieved_at: datetime
    local_received_at: datetime
    source_descriptor_id: str
    source_descriptor_sha256: str
    feed_lease_key_sha256: str
    source_batch_sha256: str
    source_row_count: int
    published_target_count: int
    quarantined_symbols: tuple[str, ...]
    persisted_fetches: tuple[PersistedProviderFetch, ...]


@dataclass(frozen=True, slots=True)
class _PreparedCollection:
    """Frozen collection plan that is safe to carry across source I/O."""

    trading_date: date
    targets_by_symbol: Mapping[str, CffexSettlementCollectionTarget]
    source_registry_id: str
    source_authorization_descriptor_hash: str
    source_descriptor: CffexSettlementSourceDescriptor
    source_descriptor_sha256: str
    feed_lease_key_sha256: str


@dataclass(frozen=True, slots=True)
class _NormalizedTargetRow:
    """One exact target row ready for a standard provider receipt projection."""

    symbol: str
    fields: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _NormalizedBatch:
    """Validated source evidence and the rows that can safely become facts."""

    batch: CffexSettlementSourceBatch
    safe_raw_payload: Mapping[str, object]
    source_batch_sha256: str
    source_row_count: int
    rows_by_symbol: Mapping[str, _NormalizedTargetRow]
    quarantined_symbols: tuple[str, ...]


class CffexSettlementCollector:
    """Collect and publish one explicit CFFEX settlement date through existing guards.

    The collector deliberately accepts already-resolved, already-authorized
    targets.  Resolving identities and evaluating source entitlements must
    happen before this call, so the frozen plan cannot change while a broad
    provider response is in flight.  It does not register a public policy or
    turn the currently unconfigured ``futures.settlement`` family on.
    """

    def __init__(
        self,
        *,
        store: MarketDataStore,
        source_descriptor_id: str = CFFEX_SETTLEMENT_DEFAULT_SOURCE_DESCRIPTOR_ID,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(store, MarketDataStore):
            raise TypeError("store must be a MarketDataStore")
        self._store = store
        self._source_descriptor_id = _require_text(
            source_descriptor_id,
            field_name="source_descriptor_id",
            maximum=128,
        )
        self._clock = clock or _utc_now

    async def collect(
        self,
        *,
        trading_date: date,
        targets: Sequence[CffexSettlementCollectionTarget],
    ) -> CffexSettlementCollectionReport:
        """Fetch one all-market source batch and publish every validated target row.

        Validation of the full source response completes before any target is
        persisted. Thus a duplicate symbol, a missing required metric, or a
        date/market mismatch cannot leave a partial batch published. Unknown
        but structurally valid CFFEX contracts remain in the immutable raw
        envelope and the report's quarantine list; they never become a
        canonical observation.

        Existing store primitives publish each canonical-series receipt in
        sequence. A database failure after an earlier publication is therefore
        surfaced as :class:`CffexSettlementCollectorPartialPublishError`, not
        as a successful batch report. The exception exposes exactly the
        durable prefix for reconciliation; this candidate makes no atomic
        multi-contract publication claim.
        """
        registration = _reviewed_source_registration(self._source_descriptor_id)
        plan = _prepare_collection(
            trading_date=trading_date,
            targets=targets,
            source_descriptor=registration.descriptor,
        )

        # Revalidate every frozen grant before it sees an external request,
        # then end any read-only control-plane transaction. Persistence repeats
        # this check after source I/O, closing the authorization-change race.
        # The lease manager owns its short CAS transaction and the store owns
        # fact/publication transactions; none spans source I/O.
        authorization_checked_at = _as_utc(
            self._clock(),
            field_name="source authorization check timestamp",
        )
        for target in plan.targets_by_symbol.values():
            await self._store.ensure_source_authorization_before_provider_io(
                target.context,
                target.source_authorization,
                provider_id=plan.source_registry_id,
                checked_at=authorization_checked_at,
            )
        await self._store.close_transaction_before_provider_io()
        lease_manager = self._store.fetch_lease_manager()
        try:
            lease = await lease_manager.acquire(plan.feed_lease_key_sha256)
        except MarketDataFetchLeaseError as exc:
            raise CffexSettlementCollectorError(exc.code) from exc
        if lease is None:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_FETCH_LEASE_BUSY")

        persisted_fetches: list[PersistedProviderFetch] = []
        primary_failure: BaseException | None = None
        try:
            source = _build_reviewed_source(registration)
            try:
                batch = await source.fetch_batch(trading_date=plan.trading_date)
            except CffexSettlementCollectorError:
                raise
            except Exception as exc:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_FAILED") from exc
            if not isinstance(batch, CffexSettlementSourceBatch):
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_BATCH_INVALID")
            if batch.provider_id != plan.source_registry_id:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PROVIDER_MISMATCH")
            if batch.provider_id != plan.source_descriptor.provider_id:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH")
            if batch.source_revision != plan.source_descriptor.source_revision:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH")

            normalized = _normalize_batch(
                batch=batch,
                plan=plan,
                source_descriptor=plan.source_descriptor,
            )
            local_received_at = _as_utc(self._clock(), field_name="local receipt timestamp")
            if batch.retrieved_at > local_received_at:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RETRIEVED_AT_FUTURE")

            try:
                for symbol in sorted(plan.targets_by_symbol):
                    target = plan.targets_by_symbol[symbol]
                    normalized_row = normalized.rows_by_symbol[symbol]
                    result = _provider_result_for_target(
                        batch=normalized,
                        plan=plan,
                        target=target,
                        row=normalized_row,
                    )
                    # A cancellation must not land after the Store has made a
                    # receipt durable but before this collector learns its
                    # exact ID. Keep the Store operation in its own task and
                    # complete that critical section before re-raising an
                    # interrupt outcome with the durable prefix.
                    persistence_task = asyncio.create_task(
                        self._store.persist_provider_result(
                            target.context,
                            result,
                            received_at=local_received_at,
                            source_authorization=target.source_authorization,
                            fetch_lease=lease,
                        )
                    )
                    try:
                        persisted = await asyncio.shield(persistence_task)
                    except asyncio.CancelledError as cancellation:
                        try:
                            persisted = await _await_persistence_after_cancellation(
                                persistence_task
                            )
                        except BaseException as persistence_error:
                            # A failed Store task has no returned receipt to
                            # append. Preserve the original cancellation and
                            # let recovery inspect Store's published/hidden
                            # boundary rather than fabricating a prefix.
                            raise cancellation from persistence_error
                        persisted_fetches.append(persisted)
                        raise CffexSettlementCollectorPartialPublishCancelledError(
                            persisted_fetches
                        ) from cancellation
                    persisted_fetches.append(persisted)
            except Exception as exc:
                if persisted_fetches:
                    raise CffexSettlementCollectorPartialPublishError(persisted_fetches) from exc
                raise

            return CffexSettlementCollectionReport(
                trading_date=plan.trading_date,
                provider_id=batch.provider_id,
                source_revision=batch.source_revision,
                source_retrieved_at=batch.retrieved_at,
                local_received_at=local_received_at,
                source_descriptor_id=plan.source_descriptor.descriptor_id,
                source_descriptor_sha256=plan.source_descriptor_sha256,
                feed_lease_key_sha256=plan.feed_lease_key_sha256,
                source_batch_sha256=normalized.source_batch_sha256,
                source_row_count=normalized.source_row_count,
                published_target_count=len(persisted_fetches),
                quarantined_symbols=normalized.quarantined_symbols,
                persisted_fetches=tuple(persisted_fetches),
            )
        except BaseException as exc:
            primary_failure = exc
            raise
        finally:
            release_error: CffexSettlementCollectorFetchLeaseReleaseError | None = None
            try:
                release_task = asyncio.create_task(lease_manager.release(lease))
                try:
                    released = await asyncio.shield(release_task)
                except asyncio.CancelledError as cancellation:
                    try:
                        released = await _await_lease_release_after_cancellation(release_task)
                    except BaseException as release_failure:
                        if persisted_fetches:
                            raise CffexSettlementCollectorPartialPublishCancelledError(
                                persisted_fetches
                            ) from release_failure
                        raise cancellation from release_failure
                    if not released:
                        release_error = CffexSettlementCollectorFetchLeaseReleaseError(
                            persisted_fetches
                        )
                        if persisted_fetches:
                            raise CffexSettlementCollectorPartialPublishCancelledError(
                                persisted_fetches
                            ) from release_error
                        raise cancellation from release_error
                    if primary_failure is None and persisted_fetches:
                        raise CffexSettlementCollectorPartialPublishCancelledError(
                            persisted_fetches
                        ) from cancellation
                    if primary_failure is None:
                        raise
                if not released:
                    release_error = CffexSettlementCollectorFetchLeaseReleaseError(
                        persisted_fetches
                    )
            except Exception as exc:
                release_error = CffexSettlementCollectorFetchLeaseReleaseError(
                    persisted_fetches
                )
                release_error.__cause__ = exc
            if primary_failure is None and release_error is not None:
                raise release_error


def _reviewed_source_registration(source_descriptor_id: str) -> CffexSettlementSourceRegistration:
    """Resolve only a source identity compiled into the reviewed registry."""
    registration = CFFEX_SETTLEMENT_REVIEWED_SOURCE_REGISTRY.get(source_descriptor_id)
    if not isinstance(registration, CffexSettlementSourceRegistration):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_UNAPPROVED")
    if registration.descriptor.descriptor_id != source_descriptor_id:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_UNAPPROVED")
    return registration


def _build_reviewed_source(registration: CffexSettlementSourceRegistration) -> CffexSettlementSource:
    """Construct the static reviewed adapter only after the collection lease exists."""
    try:
        source = registration.source_factory()
    except Exception as exc:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_FACTORY_FAILED") from exc
    if not callable(getattr(source, "fetch_batch", None)):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_FACTORY_INVALID")
    return source


def cffex_settlement_feed_lease_key(
    *,
    trading_date: date,
    provider_id: str,
    source_authorization_descriptor_hash: str,
    source_descriptor_sha256: str,
    targets: Sequence[CffexSettlementCollectionTarget],
) -> str:
    """Return the feed-level lease identity for one frozen market-wide batch.

    A per-symbol query lease would permit one network request per contract.
    This key instead binds the explicit trade date, approved source decision,
    reviewed source descriptor, and complete frozen identity/query map, so
    independent workers contend for the same all-market request without
    sharing a stale authorization or source-transport plan.
    """
    target_date = _require_trading_date(trading_date)
    normalized_provider_id = _require_text(provider_id, field_name="provider_id", maximum=255)
    descriptor_hash = _require_sha256(
        source_authorization_descriptor_hash,
        field_name="source_authorization_descriptor_hash",
    )
    reviewed_source_descriptor_hash = _require_lower_sha256(
        source_descriptor_sha256,
        code="CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_INVALID",
    )
    target_payload: list[dict[str, str]] = []
    for target in targets:
        if not isinstance(target, CffexSettlementCollectionTarget):
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_INVALID")
        context = target.context
        target_payload.append(
            {
                "canonical_id": context.query.canonical_id,
                "provider_symbol": context.identity.identity.display_symbol,
                "query_fingerprint": context.query.query_fingerprint,
            }
        )
    if not target_payload:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGETS_EMPTY")
    payload = {
        "contract_version": CFFEX_SETTLEMENT_COLLECTOR_VERSION,
        "provider_id": normalized_provider_id,
        "trading_date": target_date.isoformat(),
        "source_authorization_descriptor_hash": descriptor_hash,
        "source_descriptor_sha256": reviewed_source_descriptor_hash,
        "targets": sorted(
            target_payload,
            key=lambda item: (
                item["canonical_id"],
                item["provider_symbol"],
                item["query_fingerprint"],
            ),
        ),
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _prepare_collection(
    *,
    trading_date: date,
    targets: Sequence[CffexSettlementCollectionTarget],
    source_descriptor: CffexSettlementSourceDescriptor,
) -> _PreparedCollection:
    target_date = _require_trading_date(trading_date)
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes, bytearray)):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGETS_INVALID")
    frozen_targets = tuple(targets)
    if not frozen_targets:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGETS_EMPTY")

    expected_start, expected_end = _daily_window(target_date)
    by_symbol: dict[str, CffexSettlementCollectionTarget] = {}
    canonical_ids: set[str] = set()
    source_ids: set[str] = set()
    authorization_hashes: set[str] = set()
    for target in frozen_targets:
        if not isinstance(target, CffexSettlementCollectionTarget):
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_INVALID")
        context = target.context
        _assert_target_context(
            context=context,
            expected_start=expected_start,
            expected_end=expected_end,
        )
        source_authorization = target.source_authorization
        _assert_target_authorization(
            context=context,
            source_authorization=source_authorization,
        )
        source_ids.add(source_authorization.source_registry_id)
        authorization_hashes.add(
            _require_sha256(
                source_authorization.descriptor_hash,
                field_name="source_authorization_descriptor_hash",
            )
        )
        symbol = _require_cffex_symbol(context.identity.identity.display_symbol)
        canonical_id = _require_text(
            context.query.canonical_id,
            field_name="canonical_id",
            maximum=512,
        )
        if symbol in by_symbol or canonical_id in canonical_ids:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_MAPPING_AMBIGUOUS")
        by_symbol[symbol] = target
        canonical_ids.add(canonical_id)

    if len(source_ids) != 1 or len(authorization_hashes) != 1:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_AMBIGUOUS")
    source_registry_id = next(iter(source_ids))
    if source_registry_id != source_descriptor.provider_id:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH")
    authorization_hash = next(iter(authorization_hashes))
    reviewed_source_descriptor_hash = _source_descriptor_sha256(source_descriptor)
    feed_key = cffex_settlement_feed_lease_key(
        trading_date=target_date,
        provider_id=source_registry_id,
        source_authorization_descriptor_hash=authorization_hash,
        source_descriptor_sha256=reviewed_source_descriptor_hash,
        targets=frozen_targets,
    )
    return _PreparedCollection(
        trading_date=target_date,
        targets_by_symbol=MappingProxyType(dict(by_symbol)),
        source_registry_id=source_registry_id,
        source_authorization_descriptor_hash=authorization_hash,
        source_descriptor=source_descriptor,
        source_descriptor_sha256=reviewed_source_descriptor_hash,
        feed_lease_key_sha256=feed_key,
    )


def _assert_target_context(
    *,
    context: ResolvedMarketDataQueryContext,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    """Reject a nearby bars/snapshot/context from entering the settlement collector."""
    if not isinstance(context, ResolvedMarketDataQueryContext):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_INVALID")
    query = context.query
    identity = context.identity
    if (
        identity.asset_type != "futures"
        or identity.venue != CFFEX_SETTLEMENT_MARKET
        or query.dataset_code != CFFEX_SETTLEMENT_DATASET_CODE
        or query.data_kind != "reference_series"
        or query.frequency != "1d"
        or frozenset(query.required_fields) != CFFEX_SETTLEMENT_REQUIRED_FIELDS
        or query.start != expected_start
        or query.end != expected_end
        or query.family_id != CFFEX_SETTLEMENT_FAMILY_ID
        or query.family_contract_version != CFFEX_SETTLEMENT_FAMILY_CONTRACT_VERSION
        or query.adjustment != CFFEX_SETTLEMENT_ADJUSTMENT
        or query.price_basis != CFFEX_SETTLEMENT_PRICE_BASIS
        or query.currency != CFFEX_SETTLEMENT_CURRENCY
        or query.unit != CFFEX_SETTLEMENT_UNIT
        or query.source_policy_id != CFFEX_SETTLEMENT_SOURCE_POLICY_ID
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_CONTRACT_INVALID")
    _require_cffex_symbol(identity.identity.display_symbol)


def _assert_target_authorization(
    *,
    context: ResolvedMarketDataQueryContext,
    source_authorization: MarketDataSourceAuthorization,
) -> None:
    """Keep a scheduled batch tied to one exact verified source decision."""
    if not isinstance(source_authorization, MarketDataSourceAuthorization):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_INVALID")
    if (
        source_authorization.asset_type != "futures"
        or source_authorization.market != CFFEX_SETTLEMENT_MARKET
        or source_authorization.decision != "ALLOW"
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_INVALID")
    if source_authorization.purpose != context.query.purpose:
        raise CffexSettlementCollectorError(
            "CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_CONTEXT_MISMATCH"
        )
    _require_text(
        source_authorization.source_registry_id,
        field_name="source_registry_id",
        maximum=255,
    )


def _normalize_batch(
    *,
    batch: CffexSettlementSourceBatch,
    plan: _PreparedCollection,
    source_descriptor: CffexSettlementSourceDescriptor,
) -> _NormalizedBatch:
    """Validate one raw envelope in full before opening a fact-publication path."""
    safe_payload = _json_safe(batch.raw_payload)
    if not isinstance(safe_payload, Mapping):  # Defensive; _json_safe preserves mappings.
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
    payload = MappingProxyType(dict(safe_payload))
    _assert_no_sensitive_payload_keys(payload)
    _assert_source_request(
        payload=payload,
        trading_date=plan.trading_date,
        source_descriptor=source_descriptor,
    )
    rows_value = payload.get("response_rows")
    if not isinstance(rows_value, list):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_INVALID")
    if not rows_value:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_EMPTY")
    if len(rows_value) > _MAX_SOURCE_ROWS:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_TOO_LARGE")

    rows_by_symbol: dict[str, _NormalizedTargetRow] = {}
    seen_symbols: set[str] = set()
    quarantined_symbols: set[str] = set()
    for raw_row in rows_value:
        if not isinstance(raw_row, Mapping):
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_INVALID")
        row = MappingProxyType(dict(raw_row))
        _assert_row_market_and_date(row=row, trading_date=plan.trading_date)
        symbol = _source_row_symbol(row)
        if symbol in seen_symbols:
            # A broad source response is one atomic factual claim.  A
            # duplicate, including one for an as-yet-unmapped contract, makes
            # that claim ambiguous and cannot be attached to any known row.
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_DUPLICATE")
        seen_symbols.add(symbol)
        # The source claims one all-market CFFEX settlement snapshot, so every
        # row must satisfy the reviewed metric contract before a known target
        # can publish. An unmapped symbol may be quarantined, but it cannot
        # smuggle an incomplete or malformed row into a batch receipt.
        normalized_fields = _normalized_settlement_fields(row)
        target = plan.targets_by_symbol.get(symbol)
        if target is None:
            # The complete raw envelope remains attached to every known target
            # receipt, while this source-only symbol cannot escape into a
            # canonical series without a frozen identity mapping.
            quarantined_symbols.add(symbol)
            continue
        rows_by_symbol[symbol] = _NormalizedTargetRow(
            symbol=symbol,
            fields=normalized_fields,
        )

    missing_symbols = set(plan.targets_by_symbol) - set(rows_by_symbol)
    if missing_symbols:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_MISSING")
    source_batch_sha256 = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return _NormalizedBatch(
        batch=batch,
        safe_raw_payload=payload,
        source_batch_sha256=source_batch_sha256,
        source_row_count=len(rows_value),
        rows_by_symbol=MappingProxyType(dict(rows_by_symbol)),
        quarantined_symbols=tuple(sorted(quarantined_symbols)),
    )


def _assert_source_request(
    *,
    payload: Mapping[str, object],
    trading_date: date,
    source_descriptor: CffexSettlementSourceDescriptor,
) -> None:
    """Bind raw evidence to one exact CFFEX route and date before any row."""
    if "transport_evidence" not in payload:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if set(payload) != {
        "collector_request",
        "source_route",
        "transport_evidence",
        "response_rows",
    }:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    request = payload.get("collector_request")
    if not isinstance(request, Mapping):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if set(request) != {"market", "trading_date"}:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if request.get("market") != CFFEX_SETTLEMENT_MARKET:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if request.get("trading_date") != trading_date.isoformat():
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    source_route = payload.get("source_route")
    if not isinstance(source_route, Mapping):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if set(source_route) != {"endpoint", "origin", "call_kwargs"}:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if source_route.get("endpoint") != source_descriptor.endpoint:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    source_origin = _require_https_origin(source_route.get("origin"))
    if source_origin != source_descriptor.origin:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_DESCRIPTOR_MISMATCH")
    expected_date_token = trading_date.strftime("%Y%m%d")
    if source_route.get("call_kwargs") != {"date": expected_date_token}:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    _assert_transport_evidence(
        payload.get("transport_evidence"),
        source_origin=source_origin,
        source_descriptor=source_descriptor,
    )


def _assert_transport_evidence(
    value: object,
    *,
    source_origin: str,
    source_descriptor: CffexSettlementSourceDescriptor,
) -> None:
    """Require minimal, redacted TLS evidence bound to the exact route origin."""
    if not isinstance(value, Mapping):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if set(value) != {
        "contract_version",
        "scheme",
        "origin",
        "tls_verified",
        "certificate_policy",
        "peer_certificate_sha256",
    }:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if value.get("contract_version") != CFFEX_SETTLEMENT_TRANSPORT_EVIDENCE_VERSION:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if value.get("scheme") != "https":
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if value.get("tls_verified") is not True:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if _require_https_origin(value.get("origin")) != source_origin:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if value.get("certificate_policy") != source_descriptor.certificate_policy:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    if _require_lower_sha256(
        value.get("peer_certificate_sha256"),
        code="CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID",
    ) != source_descriptor.peer_certificate_sha256:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")


def _require_https_origin(value: object) -> str:
    """Return one canonical HTTPS origin that carries no credentials or path."""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 255:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise CffexSettlementCollectorError(
            "CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID"
        ) from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port == 0
        or value != f"https://{parsed.netloc}"
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_TRANSPORT_EVIDENCE_INVALID")
    return value


def _assert_no_sensitive_payload_keys(value: object) -> None:
    """Reject credential-shaped keys anywhere in a durable raw source envelope."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or _is_sensitive_source_key(key):
                raise CffexSettlementCollectorError(
                    "CFFEX_SETTLEMENT_SOURCE_SENSITIVE_PAYLOAD_REJECTED"
                )
            _assert_no_sensitive_payload_keys(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _assert_no_sensitive_payload_keys(item)


def _is_sensitive_source_key(key: str) -> bool:
    """Recognize common credential-bearing mapping keys without retaining values."""
    compact = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(
        marker in compact
        for marker in (
            "authorization",
            "token",
            "secret",
            "password",
            "credential",
            "cookie",
            "apikey",
            "privatekey",
            "bearer",
            "headers",
            "accesskey",
        )
    )


def _source_descriptor_sha256(descriptor: CffexSettlementSourceDescriptor) -> str:
    """Return the exact reviewed source transport identity carried by lease and receipt."""
    payload = {
        "descriptor_id": descriptor.descriptor_id,
        "provider_id": descriptor.provider_id,
        "source_revision": descriptor.source_revision,
        "endpoint": descriptor.endpoint,
        "origin": descriptor.origin,
        "certificate_policy": descriptor.certificate_policy,
        "peer_certificate_sha256": descriptor.peer_certificate_sha256,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _require_lower_sha256(value: object, *, code: str) -> str:
    """Require a non-secret canonical digest without reflecting an invalid value."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CffexSettlementCollectorError(code)
    return value


def _assert_row_market_and_date(*, row: Mapping[str, object], trading_date: date) -> None:
    # ``futures_hist_daily_cffex`` is itself CFFEX-scoped and its real rows
    # expose ``symbol,date,settle,pre_settle,open_interest`` without a market
    # column. The immutable route/request above is therefore the authority
    # when this field is absent. If a source does supply a market value, it
    # must agree exactly rather than silently widening the batch venue.
    market_aliases = ("MARKET", "market", "市场")
    if any(alias in row for alias in market_aliases):
        market = _one_text_field(
            row,
            aliases=market_aliases,
            missing_code="CFFEX_SETTLEMENT_ROW_MARKET_MISSING",
            invalid_code="CFFEX_SETTLEMENT_ROW_MARKET_INVALID",
            ambiguous_code="CFFEX_SETTLEMENT_ROW_MARKET_AMBIGUOUS",
        )
        if market != CFFEX_SETTLEMENT_MARKET:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_MARKET_INVALID")
    row_date = _one_trade_date_field(row)
    if row_date != trading_date:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_DATE_MISMATCH")


def _source_row_symbol(row: Mapping[str, object]) -> str:
    raw_symbol = _one_text_field(
        row,
        aliases=("SYMBOL", "symbol", "代码"),
        missing_code="CFFEX_SETTLEMENT_ROW_SYMBOL_MISSING",
        invalid_code="CFFEX_SETTLEMENT_ROW_SYMBOL_INVALID",
        ambiguous_code="CFFEX_SETTLEMENT_ROW_SYMBOL_AMBIGUOUS",
    )
    try:
        return _require_cffex_symbol(raw_symbol)
    except CffexSettlementCollectorError:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_SYMBOL_INVALID") from None


def _normalized_settlement_fields(row: Mapping[str, object]) -> Mapping[str, object]:
    """Map only the reviewed CFFEX legacy aliases and require all three facts."""
    aliases = {
        "settle": ("SETTLE_PRICE", "settle", "结算价"),
        "previous_settle": ("PREV_SETTLE", "pre_settle", "previous_settle", "前结算价"),
        "open_interest": ("OPEN_INTEREST", "open_interest", "持仓量"),
    }
    fields: dict[str, object] = {}
    for field_name, source_names in aliases.items():
        values = [row[name] for name in source_names if name in row]
        if not values:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_REQUIRED_FIELD_MISSING")
        normalized_values: list[object] = []
        for value in values:
            try:
                normalized = normalize_numeric_field_value(value, field_name=field_name)
            except FieldQualityValueError as exc:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_FIELD_INVALID") from exc
            if normalized is None:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_REQUIRED_FIELD_MISSING")
            normalized_values.append(normalized)
        if not _all_numeric_values_equal(normalized_values):
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_FIELD_AMBIGUOUS")
        fields[field_name] = normalized_values[0]
    return MappingProxyType(fields)


def _all_numeric_values_equal(values: Sequence[object]) -> bool:
    """Compare reviewed numeric aliases without an accidental float/string distinction."""
    if not values:
        return False
    try:
        canonical = Decimal(str(values[0]))
        if not canonical.is_finite():
            return False
        return all(
            Decimal(str(value)).is_finite() and Decimal(str(value)) == canonical
            for value in values[1:]
        )
    except Exception:
        return False


def _provider_result_for_target(
    *,
    batch: _NormalizedBatch,
    plan: _PreparedCollection,
    target: CffexSettlementCollectionTarget,
    row: _NormalizedTargetRow,
) -> ProviderFetchResult:
    context = target.context
    request = MarketDataProviderRequest(
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
        provider=batch.batch.provider_id,
        adjustment=context.query.adjustment,
        price_basis=context.query.price_basis,
        currency=context.query.currency,
        unit=context.query.unit,
        source_policy_id=context.query.source_policy_id,
        # Preserve the frozen family binding exactly; a provider receipt must
        # not invent a family revision the collector did not resolve.
        family_id=context.query.family_id,
        family_contract_version=context.query.family_contract_version,
        provider_endpoint=plan.source_descriptor.endpoint,
    )
    raw_payload = {
        "collector": {
            "contract_version": CFFEX_SETTLEMENT_COLLECTOR_VERSION,
            "collection_mode": "scheduled_market_batch",
            "trading_date": plan.trading_date.isoformat(),
            "source_batch_sha256": batch.source_batch_sha256,
            "source_descriptor_id": plan.source_descriptor.descriptor_id,
            "source_descriptor_sha256": plan.source_descriptor_sha256,
            "feed_lease_key_sha256": plan.feed_lease_key_sha256,
            "frozen_provider_symbol": row.symbol,
            "frozen_canonical_id": context.query.canonical_id,
            "quarantined_symbols": list(batch.quarantined_symbols),
        },
        "source_batch": dict(batch.safe_raw_payload),
    }
    event_at, _ = _daily_window(plan.trading_date)
    return ProviderFetchResult(
        provider_id=batch.batch.provider_id,
        source_revision=batch.batch.source_revision,
        retrieved_at=batch.batch.retrieved_at,
        observations=(
            ProviderMarketObservation(
                event_at=event_at,
                # The source receipt time is retained as upstream availability;
                # MarketDataStore will record the later local receipt/publication
                # instant for point-in-time visibility. Never substitute the
                # trading date here.
                available_at=batch.batch.retrieved_at,
                fields=row.fields,
            ),
        ),
        raw_payload=raw_payload,
        request=request,
        warnings=("CFFEX_SETTLEMENT_SCHEDULED_BATCH",),
    )


def _one_text_field(
    row: Mapping[str, object],
    *,
    aliases: Sequence[str],
    missing_code: str,
    invalid_code: str,
    ambiguous_code: str,
) -> str:
    present = [row[alias] for alias in aliases if alias in row]
    if not present:
        raise CffexSettlementCollectorError(missing_code)
    normalized_values: set[str] = set()
    for value in present:
        if not isinstance(value, str) or not value or value != value.strip():
            raise CffexSettlementCollectorError(invalid_code)
        normalized_values.add(value)
    if len(normalized_values) != 1:
        raise CffexSettlementCollectorError(ambiguous_code)
    return next(iter(normalized_values))


def _one_trade_date_field(row: Mapping[str, object]) -> date:
    present = [row[alias] for alias in ("TRADE_DATE", "trade_date", "date", "日期") if alias in row]
    if not present:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_DATE_MISSING")
    parsed_values: set[date] = set()
    for value in present:
        try:
            parsed_values.add(_parse_source_trade_date(value))
        except (TypeError, ValueError) as exc:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_DATE_INVALID") from exc
    if len(parsed_values) != 1:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_ROW_DATE_AMBIGUOUS")
    return next(iter(parsed_values))


def _parse_source_trade_date(value: object) -> date:
    """Parse only a date-like source value; never infer a local provider instant."""
    if isinstance(value, datetime):
        raise ValueError("datetime is not a source trade date")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("source trade date is invalid")
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d 00:00:00", "%Y-%m-%dT00:00:00"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError("source trade date is invalid")


def _daily_window(trading_date: date) -> tuple[datetime, datetime]:
    target_date = _require_trading_date(trading_date)
    start = datetime.combine(target_date, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _require_trading_date(value: object) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TRADING_DATE_INVALID")
    return value


def _require_cffex_symbol(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not _CFFEX_SYMBOL.fullmatch(value)
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SYMBOL_INVALID")
    return value


def _as_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TIMESTAMP_INVALID")
    return value.astimezone(UTC)


def _require_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_BATCH_INVALID")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_BATCH_INVALID")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_INVALID")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_INVALID")
    return normalized


def _canonical_json(value: object) -> bytes:
    try:
        encoded = json.dumps(
            _json_safe(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID") from exc
    if len(encoded) > _MAX_SOURCE_PAYLOAD_BYTES:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_TOO_LARGE")
    return encoded


def _json_safe(value: object, *, depth: int = 0) -> object:
    """Canonicalize bounded raw evidence without inventing string fallbacks."""
    if depth > _MAX_NESTING_DEPTH:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(UTC).isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in normalized:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
            normalized[key] = _json_safe(item, depth=depth + 1)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item, depth=depth + 1) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar = item_method()
        except (TypeError, ValueError) as exc:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID") from exc
        if scalar is value:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
        return _json_safe(scalar, depth=depth + 1)
    raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _await_persistence_after_cancellation(
    persistence_task: asyncio.Task[PersistedProviderFetch],
) -> PersistedProviderFetch:
    """Finish one shielded Store critical section despite repeated cancels.

    The caller re-raises cancellation immediately after this task returns, but
    cannot let an interrupt split Store publication from the collector's
    in-memory durable-prefix record. A second cancellation therefore waits for
    the same task instead of creating an unobserved commit/return gap.
    """
    while True:
        try:
            return await asyncio.shield(persistence_task)
        except asyncio.CancelledError:
            if persistence_task.done():
                return persistence_task.result()


async def _await_lease_release_after_cancellation(release_task: asyncio.Task[bool]) -> bool:
    """Finish one release task before reporting a cancellation after durable publication."""
    while True:
        try:
            return await asyncio.shield(release_task)
        except asyncio.CancelledError:
            if release_task.done():
                return release_task.result()


__all__ = [
    "AkShareCffexSettlementSource",
    "CFFEX_SETTLEMENT_ADJUSTMENT",
    "CFFEX_SETTLEMENT_COLLECTOR_VERSION",
    "CFFEX_SETTLEMENT_CURRENCY",
    "CFFEX_SETTLEMENT_PRICE_BASIS",
    "CFFEX_SETTLEMENT_REQUIRED_FIELDS",
    "CFFEX_SETTLEMENT_SOURCE_POLICY_ID",
    "CFFEX_SETTLEMENT_UNIT",
    "CffexSettlementCollectionReport",
    "CffexSettlementCollectionTarget",
    "CffexSettlementCollector",
    "CffexSettlementCollectorError",
    "CffexSettlementCollectorFetchLeaseReleaseError",
    "CffexSettlementCollectorPartialPublishCancelledError",
    "CffexSettlementCollectorPartialPublishError",
    "CffexSettlementSource",
    "CffexSettlementSourceBatch",
    "cffex_settlement_feed_lease_key",
]
