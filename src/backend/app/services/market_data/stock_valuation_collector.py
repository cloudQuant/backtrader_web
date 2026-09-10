"""Offline-only persistence for captured A-share valuation wide-table batches.

This module writes the private
``market.stock_valuation_captured_snapshot`` logical dataset only.  It has no
fetch method, HTTP client, CLI entry point, source-policy registration, public
family binding, request-time route, or UI enablement.  ``stock.valuation``
remains unconfigured.  A controlled scheduler or offline fixture may hand it
a typed batch that has already been captured; the collector then freezes
target identities and publishes one receipt per known canonical series through
:class:`MarketDataStore`.

The AkShare broad response has no trustworthy per-row source event time or
``as_of`` value.  Each persisted ``event_at`` is exactly the captured UTC
instant and is explicitly marked ``collector_observed``.  The microsecond
window only selects this instantaneous capture record; it does not claim a
daily source fact or a period of validity.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType

from app.services.market_data.access import MarketDataSourceAuthorization
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
    SharedSourcePayloadSegment,
)
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.snapshot_importer import (
    AkShareSnapshotImporter,
    AkShareSnapshotImportError,
    FrozenSnapshotIdentity,
    ImportedSnapshotObservation,
)
from app.services.market_data.store import (
    MAX_SOURCE_PAYLOAD_BYTES,
    MarketDataStore,
    MarketDataStoreError,
    PersistedProviderFetch,
)

UTC = timezone.utc
STOCK_VALUATION_COLLECTOR_VERSION = "stock-valuation-captured-batch-v1"
STOCK_VALUATION_PROVIDER_ID = "akshare"
STOCK_VALUATION_CAPTURE_ENDPOINT = "stock_zh_a_spot_em"
STOCK_VALUATION_DATASET_CODE = "market.stock_valuation_captured_snapshot"
STOCK_VALUATION_SOURCE_POLICY_ID = "market-stock-valuation-captured-batch-v1"
STOCK_VALUATION_REQUIRED_FIELDS = frozenset({"market_cap", "float_market_cap", "pe", "pb"})
STOCK_VALUATION_ADJUSTMENT = "unadjusted"
STOCK_VALUATION_PRICE_BASIS = "source_reported_valuation"
STOCK_VALUATION_CURRENCY = "CNY"
STOCK_VALUATION_UNIT = "mixed_source_reported"
STOCK_VALUATION_EVENT_AT_SEMANTICS = "collector_observed_capture_instant_not_source_event"
_SUPPORTED_MARKETS = frozenset({"CN-SSE", "CN-SZSE"})
_MAX_SOURCE_ROWS = 50_000
# Each per-target receipt retains the full safe source batch.  Keep the
# default-off candidate bounded before it can multiply one wide response into
# an unreviewable amount of immutable evidence.
_MAX_TARGETS_PER_BATCH = 16
# A complete captured source envelope may occupy at most 2 MiB.
_MAX_SOURCE_BATCH_BYTES = 2 * 1024 * 1024
# Each receipt must remain within the Store's 10 MiB immutable raw-payload boundary.
_MAX_SINGLE_RECEIPT_BYTES = MAX_SOURCE_PAYLOAD_BYTES
_MAX_NESTING_DEPTH = 32
_STOCK_CODE = re.compile(r"^[0-9]{6}$")
_NONFINITE_NUMERIC_SENTINEL = "__market_data_nonfinite_numeric__"
_SHARED_SOURCE_PAYLOAD_FORMAT = "canonical-json-utf8-v1"
_SHARED_SOURCE_PAYLOAD_ROLE = "source_batch"


class StockValuationCollectorError(ValueError):
    """Stable rejection emitted before an unsafe captured batch is published."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class StockValuationCollectorPartialPublishError(StockValuationCollectorError):
    """Expose the durable sequential prefix after a later target write fails."""

    def __init__(self, persisted_fetches: Sequence[PersistedProviderFetch]) -> None:
        super().__init__("STOCK_VALUATION_BATCH_PARTIALLY_PUBLISHED")
        self.persisted_fetches = tuple(persisted_fetches)


class StockValuationCollectorPartialPublishCancelledError(asyncio.CancelledError):
    """Preserve cancellation while retaining the receipts already made durable."""

    code = "STOCK_VALUATION_BATCH_PARTIALLY_PUBLISHED_CANCELLED"

    def __init__(self, persisted_fetches: Sequence[PersistedProviderFetch]) -> None:
        super().__init__(self.code)
        self.persisted_fetches = tuple(persisted_fetches)


@dataclass(frozen=True, slots=True)
class StockValuationQuarantinedRow:
    """One unmapped source row retained only as receipt-local quarantine evidence."""

    row_index: int
    provider_symbol: str
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.row_index, int) or self.row_index < 0:
            raise ValueError("quarantined row_index must be a non-negative integer")
        try:
            object.__setattr__(self, "provider_symbol", _require_stock_code(self.provider_symbol))
        except StockValuationCollectorError as exc:
            raise ValueError("quarantined provider_symbol is invalid") from exc
        if (
            not isinstance(self.reason_code, str)
            or not re.fullmatch(r"STOCK_VALUATION_[A-Z0-9_]{3,128}", self.reason_code)
        ):
            raise ValueError("quarantined reason_code is invalid")


@dataclass(frozen=True, slots=True)
class StockValuationCapturedBatch:
    """One previously captured full-market response, with no acquisition capability.

    ``raw_payload`` must later prove both the capture envelope and all source
    rows under ``capture`` and ``response_rows``.  It is intentionally not a
    callable source seam: construction cannot invoke AkShare, OpenBB, HTTP,
    or a command-line process.
    """

    provider_id: str
    source_revision: str
    captured_at: datetime
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
            "captured_at",
            _as_utc(self.captured_at, field_name="captured_at"),
        )
        if not isinstance(self.raw_payload, Mapping):
            raise TypeError("raw_payload must be a mapping")
        frozen_raw_payload = _freeze_raw_payload(self.raw_payload)
        if not isinstance(frozen_raw_payload, Mapping):  # Defensive: root was validated above.
            raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
        object.__setattr__(self, "raw_payload", frozen_raw_payload)


@dataclass(frozen=True, slots=True)
class StockValuationCollectionTarget:
    """One exact internal valuation series authorized before persistence."""

    context: ResolvedMarketDataQueryContext
    source_authorization: MarketDataSourceAuthorization
    frozen_identity: FrozenSnapshotIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.context, ResolvedMarketDataQueryContext):
            raise TypeError("context must be a ResolvedMarketDataQueryContext")
        if not isinstance(self.source_authorization, MarketDataSourceAuthorization):
            raise TypeError("source_authorization must be a MarketDataSourceAuthorization")
        if not isinstance(self.frozen_identity, FrozenSnapshotIdentity):
            raise TypeError("frozen_identity must be a FrozenSnapshotIdentity")


@dataclass(frozen=True, slots=True)
class StockValuationCollectionReport:
    """A successful publication report for one fully validated captured batch."""

    captured_at: datetime
    local_received_at: datetime
    provider_id: str
    source_revision: str
    source_batch_sha256: str
    source_batch_bytes: int
    source_row_count: int
    published_target_count: int
    quarantined_provider_symbols: tuple[str, ...]
    quarantined_rows: tuple[StockValuationQuarantinedRow, ...]
    persisted_fetches: tuple[PersistedProviderFetch, ...]


@dataclass(frozen=True, slots=True)
class _PreparedCollection:
    """The frozen target map and exact capture window derived before any writes."""

    window_start: datetime
    window_end: datetime
    targets_by_symbol: Mapping[str, StockValuationCollectionTarget]


@dataclass(frozen=True, slots=True)
class _NormalizedBatch:
    """The complete source claim after importer validation and quarantine fencing."""

    batch: StockValuationCapturedBatch
    safe_raw_payload: Mapping[str, object]
    source_batch_sha256: str
    source_batch_bytes: int
    source_row_count: int
    imported_by_target_symbol: Mapping[str, ImportedSnapshotObservation]
    quarantined_provider_symbols: tuple[str, ...]
    quarantined_rows: tuple[StockValuationQuarantinedRow, ...]


class StockValuationCollector:
    """Persist an already captured batch; this class cannot fetch market data.

    Callers must provide an internal, unbound, display-only local context and
    a current source grant for every target.  A malformed known target row, an
    ambiguous symbol, or a missing target row fails before any canonical
    receipt is written.
    """

    def __init__(
        self,
        *,
        store: MarketDataStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(store, MarketDataStore):
            raise TypeError("store must be a MarketDataStore")
        self._store = store
        self._clock = clock or _utc_now

    async def publish_captured_batch(
        self,
        *,
        batch: StockValuationCapturedBatch,
        targets: Sequence[StockValuationCollectionTarget],
    ) -> StockValuationCollectionReport:
        """Publish one captured batch without source I/O or route registration.

        Target rows are normalized with ``AkShareSnapshotImporter(mode='schedule')``
        using the collector-observed time basis.  An unmapped row is separately
        validated and quarantined with a stable reason when its own structure
        or fields are bad; it can never turn one target's valid receipt into a
        fact for another canonical series.
        """
        if not isinstance(batch, StockValuationCapturedBatch):
            raise TypeError("batch must be a StockValuationCapturedBatch")
        plan = _prepare_collection(batch=batch, targets=targets)
        normalized = _normalize_batch(batch=batch, plan=plan)
        _assert_receipt_fanout_budget(normalized=normalized, plan=plan)
        local_received_at = _as_utc(self._clock(), field_name="local receipt timestamp")
        if batch.captured_at > local_received_at:
            raise StockValuationCollectorError("STOCK_VALUATION_CAPTURED_AT_FUTURE")

        # This is only a control-plane revalidation against local persistence;
        # the collector has no outbound provider I/O to perform.
        await _preflight_authorizations(
            store=self._store,
            plan=plan,
            provider_id=batch.provider_id,
            checked_at=local_received_at,
        )

        persisted_fetches: list[PersistedProviderFetch] = []
        try:
            for provider_symbol in sorted(plan.targets_by_symbol):
                target = plan.targets_by_symbol[provider_symbol]
                imported = normalized.imported_by_target_symbol[provider_symbol]
                result = _provider_result_for_target(
                    normalized=normalized,
                    plan=plan,
                    target=target,
                    imported=imported,
                )
                # The store publishes a target receipt independently.  Shield
                # the critical section so cancellation cannot erase knowledge
                # of a receipt that became durable just before the interrupt.
                persistence_task = asyncio.create_task(
                    self._store.persist_provider_result(
                        target.context,
                        result,
                        received_at=local_received_at,
                        source_authorization=target.source_authorization,
                    )
                )
                try:
                    persisted = await asyncio.shield(persistence_task)
                except asyncio.CancelledError as cancellation:
                    try:
                        persisted = await _await_persistence_after_cancellation(persistence_task)
                    except BaseException as persistence_error:
                        raise cancellation from persistence_error
                    persisted_fetches.append(persisted)
                    raise StockValuationCollectorPartialPublishCancelledError(
                        persisted_fetches
                    ) from cancellation
                persisted_fetches.append(persisted)
        except StockValuationCollectorPartialPublishCancelledError:
            raise
        except asyncio.CancelledError as cancellation:
            if persisted_fetches:
                raise StockValuationCollectorPartialPublishCancelledError(
                    persisted_fetches
                ) from cancellation
            raise
        except Exception as exc:
            if persisted_fetches:
                raise StockValuationCollectorPartialPublishError(persisted_fetches) from exc
            raise

        return StockValuationCollectionReport(
            captured_at=batch.captured_at,
            local_received_at=local_received_at,
            provider_id=batch.provider_id,
            source_revision=batch.source_revision,
            source_batch_sha256=normalized.source_batch_sha256,
            source_batch_bytes=normalized.source_batch_bytes,
            source_row_count=normalized.source_row_count,
            published_target_count=len(persisted_fetches),
            quarantined_provider_symbols=normalized.quarantined_provider_symbols,
            quarantined_rows=normalized.quarantined_rows,
            persisted_fetches=tuple(persisted_fetches),
        )


def _prepare_collection(
    *,
    batch: StockValuationCapturedBatch,
    targets: Sequence[StockValuationCollectionTarget],
) -> _PreparedCollection:
    """Freeze exact stock contexts before processing the captured source claim."""
    if batch.provider_id != STOCK_VALUATION_PROVIDER_ID:
        raise StockValuationCollectorError("STOCK_VALUATION_PROVIDER_UNSUPPORTED")
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes, bytearray)):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGETS_INVALID")
    frozen_targets = tuple(targets)
    if not frozen_targets:
        raise StockValuationCollectorError("STOCK_VALUATION_TARGETS_EMPTY")
    if len(frozen_targets) > _MAX_TARGETS_PER_BATCH:
        raise StockValuationCollectorError("STOCK_VALUATION_TARGETS_TOO_MANY")

    window_start, window_end = _capture_instant_window(batch.captured_at)
    by_symbol: dict[str, StockValuationCollectionTarget] = {}
    canonical_ids: set[str] = set()
    for target in frozen_targets:
        if not isinstance(target, StockValuationCollectionTarget):
            raise StockValuationCollectorError("STOCK_VALUATION_TARGET_INVALID")
        _assert_target_context(
            context=target.context,
            expected_start=window_start,
            expected_end=window_end,
        )
        _assert_target_identity(context=target.context, frozen_identity=target.frozen_identity)
        _assert_target_authorization(
            context=target.context,
            source_authorization=target.source_authorization,
            provider_id=batch.provider_id,
        )
        provider_symbol = _require_stock_code(target.frozen_identity.provider_symbol)
        canonical_id = _require_text(
            target.context.query.canonical_id,
            field_name="canonical_id",
            maximum=512,
        )
        if canonical_id.startswith("quarantine:stock:"):
            raise StockValuationCollectorError("STOCK_VALUATION_TARGET_IDENTITY_INVALID")
        if provider_symbol in by_symbol or canonical_id in canonical_ids:
            raise StockValuationCollectorError("STOCK_VALUATION_TARGET_MAPPING_AMBIGUOUS")
        by_symbol[provider_symbol] = target
        canonical_ids.add(canonical_id)

    return _PreparedCollection(
        window_start=window_start,
        window_end=window_end,
        targets_by_symbol=MappingProxyType(dict(by_symbol)),
    )


def _assert_target_context(
    *,
    context: ResolvedMarketDataQueryContext,
    expected_start: datetime,
    expected_end: datetime,
) -> None:
    """Require one unbound private snapshot contract rather than a public product."""
    if not isinstance(context, ResolvedMarketDataQueryContext):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_INVALID")
    query = context.query
    identity = context.identity
    coverage = context.coverage_identity
    if (
        identity.asset_type != "stock"
        or identity.venue not in _SUPPORTED_MARKETS
        or query.dataset_code != STOCK_VALUATION_DATASET_CODE
        or query.data_kind != "valuation_snapshot"
        or query.frequency != "snapshot"
        or frozenset(query.required_fields) != STOCK_VALUATION_REQUIRED_FIELDS
        or query.start != expected_start
        or query.end != expected_end
        or query.family_id is not None
        or query.family_contract_version is not None
        or query.adjustment != STOCK_VALUATION_ADJUSTMENT
        or query.price_basis != STOCK_VALUATION_PRICE_BASIS
        or query.currency != STOCK_VALUATION_CURRENCY
        or query.unit != STOCK_VALUATION_UNIT
        or query.source_policy_id != STOCK_VALUATION_SOURCE_POLICY_ID
        or query.mode != "local_only"
        or query.consistency != "display"
        or query.purpose != "display"
        or context.storage.dataset_code != STOCK_VALUATION_DATASET_CODE
        or context.storage.physical_table != "md_observation_revisions"
        or context.storage.write_mode not in {"canonical_append_only", "canonical_read_write"}
        or coverage.dataset_code != STOCK_VALUATION_DATASET_CODE
        or coverage.asset_type != "stock"
        or coverage.market != identity.venue
        or coverage.data_kind != "valuation_snapshot"
        or coverage.frequency != "snapshot"
        or coverage.source_policy_id != STOCK_VALUATION_SOURCE_POLICY_ID
        or coverage.adjustment != STOCK_VALUATION_ADJUSTMENT
        or coverage.price_basis != STOCK_VALUATION_PRICE_BASIS
        or coverage.currency != STOCK_VALUATION_CURRENCY
        or coverage.unit != STOCK_VALUATION_UNIT
    ):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_CONTRACT_INVALID")


def _assert_target_identity(
    *,
    context: ResolvedMarketDataQueryContext,
    frozen_identity: FrozenSnapshotIdentity,
) -> None:
    """Keep the offline row map tied to the exact resolved master-data identity."""
    resolved = context.identity
    if (
        frozen_identity.asset_type != "stock"
        or frozen_identity.provider_market is not None
        or frozen_identity.canonical_id != context.query.canonical_id
        or frozen_identity.canonical_id != resolved.canonical_id
        or frozen_identity.canonical_id != resolved.identity.canonical_id
        or frozen_identity.provider_symbol != resolved.identity.display_symbol
        or frozen_identity.market != resolved.venue
        or frozen_identity.market not in _SUPPORTED_MARKETS
    ):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_IDENTITY_MISMATCH")
    try:
        _require_stock_code(frozen_identity.provider_symbol)
    except StockValuationCollectorError:
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_IDENTITY_MISMATCH") from None


def _assert_target_authorization(
    *,
    context: ResolvedMarketDataQueryContext,
    source_authorization: MarketDataSourceAuthorization,
    provider_id: str,
) -> None:
    """Fence each target to its own current, market-specific source decision."""
    if not isinstance(source_authorization, MarketDataSourceAuthorization):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_AUTHORIZATION_INVALID")
    if (
        source_authorization.source_registry_id != provider_id
        or source_authorization.asset_type != "stock"
        or source_authorization.market != context.identity.venue
        or source_authorization.decision != "ALLOW"
    ):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_AUTHORIZATION_INVALID")
    if source_authorization.purpose != context.query.purpose:
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_AUTHORIZATION_CONTEXT_MISMATCH")
    _require_lower_sha256(
        source_authorization.descriptor_hash,
        code="STOCK_VALUATION_TARGET_AUTHORIZATION_INVALID",
    )


async def _preflight_authorizations(
    *,
    store: MarketDataStore,
    plan: _PreparedCollection,
    provider_id: str,
    checked_at: datetime,
) -> None:
    """Recheck all local source grants before the first irreversible write."""
    for target in plan.targets_by_symbol.values():
        try:
            await store.ensure_source_authorization_before_provider_io(
                target.context,
                target.source_authorization,
                provider_id=provider_id,
                checked_at=checked_at,
            )
        except asyncio.CancelledError:
            raise
        except (MarketDataStoreError, ValueError, TypeError) as exc:
            raise StockValuationCollectorError(
                "STOCK_VALUATION_SOURCE_AUTHORIZATION_REJECTED"
            ) from exc


def _normalize_batch(
    *,
    batch: StockValuationCapturedBatch,
    plan: _PreparedCollection,
) -> _NormalizedBatch:
    """Normalize target rows strictly and retain unmapped row failures as quarantine."""
    safe_payload = _json_safe(batch.raw_payload)
    if not isinstance(safe_payload, Mapping):  # Defensive: _json_safe preserves mappings.
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
    payload = MappingProxyType(dict(safe_payload))
    _assert_no_sensitive_payload_keys(payload)
    # This bounds the complete persisted source envelope (including its
    # declared digest), independently from the larger Store receipt ceiling.
    canonical_payload = _canonical_json(
        payload,
        maximum_bytes=_MAX_SOURCE_BATCH_BYTES,
        overflow_code="STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE",
    )
    source_batch_sha256 = _assert_capture_envelope(payload=payload, batch=batch)

    rows_value = payload.get("response_rows")
    if not isinstance(rows_value, list):
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_RESPONSE_INVALID")
    if not rows_value:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_RESPONSE_EMPTY")
    if len(rows_value) > _MAX_SOURCE_ROWS:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE")

    rows_by_symbol: dict[str, list[tuple[int, Mapping[str, object]]]] = {}
    for row_index, raw_row in enumerate(rows_value):
        if not isinstance(raw_row, Mapping):
            raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_RESPONSE_INVALID")
        symbol = _source_row_symbol(raw_row)
        rows_by_symbol.setdefault(symbol, []).append((row_index, raw_row))

    target_rows: list[Mapping[str, object]] = []
    unknown_rows: list[tuple[int, str, Mapping[str, object]]] = []
    quarantined_rows: list[StockValuationQuarantinedRow] = []
    for symbol, source_rows in rows_by_symbol.items():
        if symbol in plan.targets_by_symbol:
            if len(source_rows) != 1:
                # A duplicate could revise a requested target.  Do not
                # downgrade that ambiguity to unknown-row quarantine.
                raise StockValuationCollectorError("STOCK_VALUATION_ROW_DUPLICATE")
            target_rows.append(source_rows[0][1])
            continue
        if len(source_rows) != 1:
            quarantined_rows.extend(
                StockValuationQuarantinedRow(
                    row_index=row_index,
                    provider_symbol=symbol,
                    reason_code="STOCK_VALUATION_UNKNOWN_ROW_DUPLICATE",
                )
                for row_index, _raw_row in source_rows
            )
            continue
        row_index, raw_row = source_rows[0]
        unknown_rows.append((row_index, symbol, raw_row))

    missing_symbols = set(plan.targets_by_symbol) - set(rows_by_symbol)
    if missing_symbols:
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_MISSING")
    try:
        imported = AkShareSnapshotImporter(mode="schedule").import_rows(
            asset_type="stock",
            rows=target_rows,
            frozen_identities=tuple(
                target.frozen_identity for target in plan.targets_by_symbol.values()
            ),
            required_fields=STOCK_VALUATION_REQUIRED_FIELDS,
            time_basis="collector_observed",
            collected_at=batch.captured_at,
        )
    except AkShareSnapshotImportError as exc:
        raise _snapshot_import_error(exc) from exc

    imported_by_target_symbol: dict[str, ImportedSnapshotObservation] = {}
    for item in imported.imported:
        provider_symbol = item.identity.provider_symbol
        target = plan.targets_by_symbol.get(provider_symbol)
        if target is None:
            continue
        if item.identity != target.frozen_identity:
            raise StockValuationCollectorError("STOCK_VALUATION_TARGET_IDENTITY_MISMATCH")
        if item.time_basis != "collector_observed" or item.source_event_time is not None:
            raise StockValuationCollectorError("STOCK_VALUATION_TIME_BASIS_INVALID")
        if provider_symbol in imported_by_target_symbol:
            raise StockValuationCollectorError("STOCK_VALUATION_ROW_DUPLICATE")
        imported_by_target_symbol[provider_symbol] = item

    if set(imported_by_target_symbol) != set(plan.targets_by_symbol):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_MISSING")
    for row_index, symbol, raw_row in unknown_rows:
        quarantined_rows.append(
            StockValuationQuarantinedRow(
                row_index=row_index,
                provider_symbol=symbol,
                reason_code=_unknown_row_quarantine_reason(
                    row=raw_row,
                    provider_symbol=symbol,
                    captured_at=batch.captured_at,
                ),
            )
        )
    quarantined_rows.sort(key=lambda item: (item.row_index, item.provider_symbol, item.reason_code))
    return _NormalizedBatch(
        batch=batch,
        safe_raw_payload=payload,
        source_batch_sha256=source_batch_sha256,
        source_batch_bytes=len(canonical_payload),
        source_row_count=len(rows_value),
        imported_by_target_symbol=MappingProxyType(dict(imported_by_target_symbol)),
        quarantined_provider_symbols=tuple(
            sorted({item.provider_symbol for item in quarantined_rows})
        ),
        quarantined_rows=tuple(quarantined_rows),
    )


def _unknown_row_quarantine_reason(
    *,
    row: Mapping[str, object],
    provider_symbol: str,
    captured_at: datetime,
) -> str:
    """Validate an unmapped row without letting it block a known target receipt."""
    try:
        AkShareSnapshotImporter(mode="schedule").import_rows(
            asset_type="stock",
            rows=(row,),
            frozen_identities=(
                FrozenSnapshotIdentity(
                    canonical_id=f"quarantine:stock:{provider_symbol}",
                    asset_type="stock",
                    provider_symbol=provider_symbol,
                    market="QUARANTINE",
                ),
            ),
            required_fields=STOCK_VALUATION_REQUIRED_FIELDS,
            time_basis="collector_observed",
            collected_at=captured_at,
        )
    except AkShareSnapshotImportError as exc:
        return _unknown_snapshot_import_reason(exc)
    return "STOCK_VALUATION_UNKNOWN_IDENTITY"


def _snapshot_import_error(error: AkShareSnapshotImportError) -> StockValuationCollectorError:
    """Translate importer details into receipt-safe collector error codes."""
    code_map = {
        "AKSHARE_SNAPSHOT_REQUIRED_FIELDS_MISSING": "STOCK_VALUATION_ROW_REQUIRED_FIELD_MISSING",
        "AKSHARE_SNAPSHOT_FIELD_VALUE_INVALID": "STOCK_VALUATION_ROW_FIELD_INVALID",
        "AKSHARE_SNAPSHOT_FIELDS_AMBIGUOUS": "STOCK_VALUATION_ROW_FIELD_AMBIGUOUS",
        "AKSHARE_SNAPSHOT_ROW_DUPLICATE": "STOCK_VALUATION_ROW_DUPLICATE",
        "AKSHARE_SNAPSHOT_TIMESTAMP_AMBIGUOUS": "STOCK_VALUATION_TIME_BASIS_INVALID",
        "AKSHARE_SNAPSHOT_TIME_BASIS_CONFLICT": "STOCK_VALUATION_TIME_BASIS_INVALID",
    }
    return StockValuationCollectorError(
        code_map.get(error.code, "STOCK_VALUATION_SNAPSHOT_NORMALIZATION_FAILED")
    )


def _unknown_snapshot_import_reason(error: AkShareSnapshotImportError) -> str:
    """Map one unmapped row's importer result to receipt-safe quarantine metadata."""
    code_map = {
        "AKSHARE_SNAPSHOT_REQUIRED_FIELDS_MISSING": (
            "STOCK_VALUATION_UNKNOWN_ROW_REQUIRED_FIELD_MISSING"
        ),
        "AKSHARE_SNAPSHOT_FIELD_VALUE_INVALID": "STOCK_VALUATION_UNKNOWN_ROW_FIELD_INVALID",
        "AKSHARE_SNAPSHOT_FIELDS_AMBIGUOUS": "STOCK_VALUATION_UNKNOWN_ROW_FIELD_AMBIGUOUS",
        "AKSHARE_SNAPSHOT_TIMESTAMP_AMBIGUOUS": "STOCK_VALUATION_UNKNOWN_ROW_TIME_BASIS_INVALID",
        "AKSHARE_SNAPSHOT_TIME_BASIS_CONFLICT": "STOCK_VALUATION_UNKNOWN_ROW_TIME_BASIS_INVALID",
        "AKSHARE_SNAPSHOT_FIELDS_EMPTY": "STOCK_VALUATION_UNKNOWN_ROW_REQUIRED_FIELD_MISSING",
    }
    return code_map.get(error.code, "STOCK_VALUATION_UNKNOWN_ROW_NORMALIZATION_FAILED")


def _assert_receipt_fanout_budget(
    *,
    normalized: _NormalizedBatch,
    plan: _PreparedCollection,
) -> None:
    """Preflight compact target-specific receipt evidence before persistence.

    ``MarketDataStore`` deliberately seals one immutable source snapshot for
    every series publication.  The complete bounded source envelope has
    already been verified independently and is content-addressed once; this
    check protects only each per-target receipt from bypassing the Store's raw
    payload ceiling.
    """
    for provider_symbol in sorted(plan.targets_by_symbol):
        target = plan.targets_by_symbol[provider_symbol]
        _canonical_json(
            _receipt_raw_payload(normalized=normalized, plan=plan, target=target),
            maximum_bytes=_MAX_SINGLE_RECEIPT_BYTES,
            overflow_code="STOCK_VALUATION_RECEIPT_EVIDENCE_TOO_LARGE",
        )


def _assert_capture_envelope(
    *,
    payload: Mapping[str, object],
    batch: StockValuationCapturedBatch,
) -> str:
    """Bind fixed AkShare capture evidence and its self-excluding batch digest."""
    if set(payload) != {"capture", "response_rows"}:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_REQUEST_INVALID")
    capture = payload.get("capture")
    if not isinstance(capture, Mapping):
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_REQUEST_INVALID")
    expected_capture_keys = {
        "asset_type",
        "batch_sha256",
        "captured_at",
        "collector_version",
        "endpoint",
        "provider_id",
        "request_shape",
        "source_revision",
        "time_basis",
    }
    if set(capture) != expected_capture_keys:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_REQUEST_INVALID")
    if (
        capture.get("asset_type") != "stock"
        or capture.get("time_basis") != "collector_observed"
        or capture.get("captured_at") != batch.captured_at.isoformat()
        or capture.get("collector_version") != STOCK_VALUATION_COLLECTOR_VERSION
        or capture.get("provider_id") != batch.provider_id
        or capture.get("provider_id") != STOCK_VALUATION_PROVIDER_ID
        or capture.get("endpoint") != STOCK_VALUATION_CAPTURE_ENDPOINT
        or capture.get("request_shape") != {"args": [], "kwargs": {}}
        or capture.get("source_revision") != batch.source_revision
    ):
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_REQUEST_INVALID")
    declared_hash = _require_lower_sha256(
        capture.get("batch_sha256"),
        code="STOCK_VALUATION_SOURCE_BATCH_HASH_INVALID",
    )
    unsigned_capture = {key: value for key, value in capture.items() if key != "batch_sha256"}
    expected_hash = hashlib.sha256(
        _canonical_json(
            {
                "capture": unsigned_capture,
                "response_rows": payload["response_rows"],
            },
            maximum_bytes=_MAX_SOURCE_BATCH_BYTES,
            overflow_code="STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE",
        )
    ).hexdigest()
    if declared_hash != expected_hash:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_BATCH_HASH_INVALID")
    return declared_hash


def _source_row_symbol(row: Mapping[str, object]) -> str:
    """Return one exact six-digit source code without coercing numeric values."""
    aliases = ("代码", "股票代码", "symbol", "code")
    values = [row[alias] for alias in aliases if alias in row]
    if not values:
        raise StockValuationCollectorError("STOCK_VALUATION_ROW_SYMBOL_MISSING")
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise StockValuationCollectorError("STOCK_VALUATION_ROW_SYMBOL_INVALID")
        normalized.add(value.strip())
    if len(normalized) != 1:
        raise StockValuationCollectorError("STOCK_VALUATION_ROW_SYMBOL_AMBIGUOUS")
    try:
        return _require_stock_code(next(iter(normalized)))
    except StockValuationCollectorError:
        raise StockValuationCollectorError("STOCK_VALUATION_ROW_SYMBOL_INVALID") from None


def _provider_result_for_target(
    *,
    normalized: _NormalizedBatch,
    plan: _PreparedCollection,
    target: StockValuationCollectionTarget,
    imported: ImportedSnapshotObservation,
) -> ProviderFetchResult:
    """Project one importer result with a shared immutable source payload."""
    context = target.context
    fields = {
        field_name: imported.observation.fields[field_name]
        for field_name in sorted(STOCK_VALUATION_REQUIRED_FIELDS)
    }
    request = MarketDataProviderRequest(
        query_fingerprint=context.query.query_fingerprint,
        canonical_id=context.query.canonical_id,
        asset_type=context.identity.asset_type,
        provider_symbol=target.frozen_identity.provider_symbol,
        market=context.identity.venue or "",
        data_kind=context.query.data_kind,
        frequency=context.query.frequency or "snapshot",
        start_at=context.query.start,
        end_at=context.query.end,
        required_fields=frozenset(context.query.required_fields),
        provider=normalized.batch.provider_id,
        adjustment=context.query.adjustment,
        price_basis=context.query.price_basis,
        currency=context.query.currency,
        unit=context.query.unit,
        source_policy_id=context.query.source_policy_id,
        family_id=context.query.family_id,
        # This is evidence for an already received batch, not an endpoint
        # route that this collector may invoke.
        provider_endpoint=STOCK_VALUATION_CAPTURE_ENDPOINT,
    )
    raw_payload = _receipt_raw_payload(normalized=normalized, plan=plan, target=target)
    return ProviderFetchResult(
        provider_id=normalized.batch.provider_id,
        source_revision=normalized.batch.source_revision,
        retrieved_at=normalized.batch.captured_at,
        observations=(
            ProviderMarketObservation(
                # This is the exact collector-observed capture instant.  The
                # receipt keeps the source event time explicitly null.
                event_at=normalized.batch.captured_at,
                available_at=normalized.batch.captured_at,
                fields=fields,
            ),
        ),
        raw_payload=raw_payload,
        request=request,
        warnings=(
            "STOCK_VALUATION_OFFLINE_CAPTURED_BATCH",
            "STOCK_VALUATION_COLLECTOR_OBSERVED",
            "STOCK_VALUATION_CAPTURE_INSTANT_NOT_SOURCE_EVENT",
        ),
        shared_source_payload_segment=SharedSourcePayloadSegment(
            segment_key="source_batch",
            payload_format=_SHARED_SOURCE_PAYLOAD_FORMAT,
            payload_role=_SHARED_SOURCE_PAYLOAD_ROLE,
        ),
    )


def _receipt_raw_payload(
    *,
    normalized: _NormalizedBatch,
    plan: _PreparedCollection,
    target: StockValuationCollectionTarget,
) -> Mapping[str, object]:
    """Return a compact target receipt that points to the shared source payload."""
    return {
        "collector": {
            "contract_version": STOCK_VALUATION_COLLECTOR_VERSION,
            "collection_mode": "offline_captured_scheduled_batch",
            "source_batch_sha256": normalized.source_batch_sha256,
            "source_revision": normalized.batch.source_revision,
            "capture_endpoint": STOCK_VALUATION_CAPTURE_ENDPOINT,
            "captured_at": normalized.batch.captured_at.isoformat(),
            "time_basis": "collector_observed",
            "source_event_time": None,
            "event_at": normalized.batch.captured_at.isoformat(),
            "event_window": {
                "start_at": plan.window_start.isoformat(),
                "end_at": plan.window_end.isoformat(),
            },
            "event_at_semantics": STOCK_VALUATION_EVENT_AT_SEMANTICS,
            "source_as_of": None,
            "frozen_identity": {
                "canonical_id": target.frozen_identity.canonical_id,
                "asset_type": target.frozen_identity.asset_type,
                "provider_symbol": target.frozen_identity.provider_symbol,
                "market": target.frozen_identity.market,
                "provider_market": target.frozen_identity.provider_market,
            },
            "quarantined_provider_symbols": list(normalized.quarantined_provider_symbols),
            "quarantined_rows": [
                {
                    "row_index": item.row_index,
                    "provider_symbol": item.provider_symbol,
                    "reason_code": item.reason_code,
                }
                for item in normalized.quarantined_rows
            ],
        },
        "source_batch": dict(normalized.safe_raw_payload),
    }


def _capture_instant_window(captured_at: datetime) -> tuple[datetime, datetime]:
    """Return the narrow storage selection window for one capture instant."""
    start = _as_utc(captured_at, field_name="captured_at")
    return start, start + timedelta(microseconds=1)


def _freeze_raw_payload(
    value: object,
    *,
    depth: int = 0,
    active_container_ids: set[int] | None = None,
) -> object:
    """Detach and recursively freeze source containers before later verification.

    The constructor receives user-owned nested dictionaries and lists.  A
    top-level mapping proxy alone would leave those references mutable before
    ``publish_captured_batch`` verifies the envelope digest.  Preserve scalar
    values for the later JSON-safety boundary while replacing every mapping and
    sequence with an independent immutable snapshot.
    """
    if depth > _MAX_NESTING_DEPTH:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
    if active_container_ids is None:
        active_container_ids = set()
    if isinstance(value, Mapping):
        container_id = id(value)
        if container_id in active_container_ids:
            raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
        active_container_ids.add(container_id)
        try:
            return MappingProxyType(
                {
                    key: _freeze_raw_payload(
                        item,
                        depth=depth + 1,
                        active_container_ids=active_container_ids,
                    )
                    for key, item in value.items()
                }
            )
        finally:
            active_container_ids.remove(container_id)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        container_id = id(value)
        if container_id in active_container_ids:
            raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
        active_container_ids.add(container_id)
        try:
            return tuple(
                _freeze_raw_payload(
                    item,
                    depth=depth + 1,
                    active_container_ids=active_container_ids,
                )
                for item in value
            )
        finally:
            active_container_ids.remove(container_id)
    return value


def _require_stock_code(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or not _STOCK_CODE.fullmatch(value):
        raise StockValuationCollectorError("STOCK_VALUATION_TARGET_IDENTITY_INVALID")
    return value


def _require_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise StockValuationCollectorError("STOCK_VALUATION_INPUT_INVALID")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise StockValuationCollectorError("STOCK_VALUATION_INPUT_INVALID")
    return normalized


def _require_lower_sha256(value: object, *, code: str) -> str:
    """Return one exact lower-case SHA-256 digest without exposing the source value."""
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[0-9a-f]{64}", value)
    ):
        raise StockValuationCollectorError(code)
    return value


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StockValuationCollectorError("STOCK_VALUATION_INPUT_INVALID")
    return value.astimezone(UTC)


def _assert_no_sensitive_payload_keys(value: object) -> None:
    """Reject credential-shaped keys before raw evidence reaches the store."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or _is_sensitive_source_key(key):
                raise StockValuationCollectorError(
                    "STOCK_VALUATION_SOURCE_SENSITIVE_PAYLOAD_REJECTED"
                )
            _assert_no_sensitive_payload_keys(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _assert_no_sensitive_payload_keys(item)


def _is_sensitive_source_key(key: str) -> bool:
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


def _canonical_json(
    value: object,
    *,
    maximum_bytes: int = _MAX_SOURCE_BATCH_BYTES,
    overflow_code: str = "STOCK_VALUATION_SOURCE_RESPONSE_TOO_LARGE",
) -> bytes:
    """Encode safe raw evidence with a caller-selected pre-persistence bound."""
    if not isinstance(maximum_bytes, int) or isinstance(maximum_bytes, bool) or maximum_bytes < 1:
        raise ValueError("maximum_bytes must be a positive integer")
    if not isinstance(overflow_code, str) or not overflow_code:
        raise ValueError("overflow_code must be a non-empty string")
    try:
        encoded = json.dumps(
            _json_safe(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID") from exc
    if len(encoded) > maximum_bytes:
        raise StockValuationCollectorError(overflow_code)
    return encoded


def _json_safe(value: object, *, depth: int = 0) -> object:
    """Canonicalize bounded raw evidence without retaining unsafe object values."""
    if depth > _MAX_NESTING_DEPTH:
        raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _NONFINITE_NUMERIC_SENTINEL
    if isinstance(value, Decimal):
        return format(value, "f") if value.is_finite() else _NONFINITE_NUMERIC_SENTINEL
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
                raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
            normalized[key] = _json_safe(item, depth=depth + 1)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item, depth=depth + 1) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar = item_method()
        except Exception as exc:
            raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID") from exc
        if scalar is value:
            raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")
        return _json_safe(scalar, depth=depth + 1)
    raise StockValuationCollectorError("STOCK_VALUATION_SOURCE_PAYLOAD_INVALID")


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _await_persistence_after_cancellation(
    persistence_task: asyncio.Task[PersistedProviderFetch],
) -> PersistedProviderFetch:
    """Finish one shielded write before exposing cancellation and its durable prefix."""
    while True:
        try:
            return await asyncio.shield(persistence_task)
        except asyncio.CancelledError:
            if persistence_task.done():
                return persistence_task.result()


__all__ = [
    "STOCK_VALUATION_ADJUSTMENT",
    "STOCK_VALUATION_CAPTURE_ENDPOINT",
    "STOCK_VALUATION_COLLECTOR_VERSION",
    "STOCK_VALUATION_CURRENCY",
    "STOCK_VALUATION_DATASET_CODE",
    "STOCK_VALUATION_EVENT_AT_SEMANTICS",
    "STOCK_VALUATION_PRICE_BASIS",
    "STOCK_VALUATION_PROVIDER_ID",
    "STOCK_VALUATION_REQUIRED_FIELDS",
    "STOCK_VALUATION_SOURCE_POLICY_ID",
    "STOCK_VALUATION_UNIT",
    "StockValuationCapturedBatch",
    "StockValuationCollectionReport",
    "StockValuationCollectionTarget",
    "StockValuationCollector",
    "StockValuationCollectorError",
    "StockValuationCollectorPartialPublishCancelledError",
    "StockValuationCollectorPartialPublishError",
    "StockValuationQuarantinedRow",
]
