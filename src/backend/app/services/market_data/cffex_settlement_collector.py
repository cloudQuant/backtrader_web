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
import importlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Protocol

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
CFFEX_SETTLEMENT_PROVIDER_ENDPOINT = "cffex-settlement-scheduled-batch-v1"
CFFEX_SETTLEMENT_REQUIRED_FIELDS = frozenset({"settle", "previous_settle", "open_interest"})
CFFEX_SETTLEMENT_DATASET_CODE = "market.settlement"
CFFEX_SETTLEMENT_FAMILY_ID = "futures.settlement"
CFFEX_SETTLEMENT_MARKET = "CFFEX"
_MAX_SOURCE_ROWS = 50_000
_MAX_SOURCE_PAYLOAD_BYTES = 10 * 1024 * 1024
_MAX_NESTING_DEPTH = 32
_CFFEX_SYMBOL = re.compile(r"^[A-Z]{1,4}[0-9]{4}$")


class CffexSettlementCollectorError(ValueError):
    """Stable rejection emitted before an unsafe batch can become canonical data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CffexSettlementSourceBatch:
    """One source-owned, market-wide response for a single CFFEX trading date.

    ``raw_payload`` is an immutable evidence envelope.  It must carry the
    explicit source request and all returned rows under ``response_rows``;
    callers never supply a separate normalized row list that could diverge from
    the durable source receipt.
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
    """A source seam that performs exactly one all-market request per date."""

    async def fetch_batch(self, *, trading_date: date) -> CffexSettlementSourceBatch:
        """Return the raw CFFEX settlement response for one explicit trading date."""


class AkShareCffexSettlementSource:
    """Explicit opt-in AkShare source for ``get_futures_daily`` CFFEX batches.

    The SDK is imported only when a caller explicitly invokes
    :meth:`fetch_batch`.  This class has no database dependency and no retry or
    fallback behaviour: a missing/failed source remains a typed failure for the
    operator rather than silently using another venue, date, or legacy table.
    """

    provider_id = "akshare"
    source_revision = "akshare.get_futures_daily:v1"

    async def fetch_batch(self, *, trading_date: date) -> CffexSettlementSourceBatch:
        target_date = _require_trading_date(trading_date)
        date_token = target_date.strftime("%Y%m%d")
        try:
            source_callable = await asyncio.to_thread(_resolve_akshare_callable)
            response = await asyncio.to_thread(
                source_callable,
                start_date=date_token,
                end_date=date_token,
                market=CFFEX_SETTLEMENT_MARKET,
            )
            rows = await asyncio.to_thread(_coerce_response_rows, response)
        except CffexSettlementCollectorError:
            raise
        except Exception as exc:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_UNAVAILABLE") from exc

        return CffexSettlementSourceBatch(
            provider_id=self.provider_id,
            source_revision=self.source_revision,
            retrieved_at=datetime.now(UTC),
            raw_payload={
                "collector_request": {
                    "market": CFFEX_SETTLEMENT_MARKET,
                    "trading_date": target_date.isoformat(),
                },
                "source_route": {
                    "endpoint": "get_futures_daily",
                    "call_kwargs": {
                        "start_date": date_token,
                        "end_date": date_token,
                        "market": CFFEX_SETTLEMENT_MARKET,
                    },
                },
                "response_rows": rows,
            },
        )


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
    """Safe aggregate proof of one source call and its canonical publications."""

    trading_date: date
    provider_id: str
    source_revision: str
    source_retrieved_at: datetime
    local_received_at: datetime
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
        source: CffexSettlementSource,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(store, MarketDataStore):
            raise TypeError("store must be a MarketDataStore")
        if not callable(getattr(source, "fetch_batch", None)):
            raise TypeError("source must implement fetch_batch")
        self._store = store
        self._source = source
        self._clock = clock or _utc_now

    async def collect(
        self,
        *,
        trading_date: date,
        targets: Sequence[CffexSettlementCollectionTarget],
    ) -> CffexSettlementCollectionReport:
        """Fetch one all-market source batch and publish every validated target row.

        Validation of the full source response completes before any target is
        persisted.  Thus a duplicate known symbol, a missing required metric,
        or a date/market mismatch cannot leave a partial batch published.
        Unknown but structurally valid CFFEX contracts remain in the immutable
        raw envelope and the report's quarantine list; they never become a
        canonical observation.
        """
        plan = _prepare_collection(trading_date=trading_date, targets=targets)

        # Validate the registered provider before it sees an external request,
        # then end any read-only control-plane transaction.  The lease manager
        # owns its short CAS transaction and the store owns fact/publication
        # transactions; none spans source I/O.
        await self._store.ensure_provider_active(plan.source_registry_id)
        await self._store.close_transaction_before_provider_io()
        lease_manager = self._store.fetch_lease_manager()
        try:
            lease = await lease_manager.acquire(plan.feed_lease_key_sha256)
        except MarketDataFetchLeaseError as exc:
            raise CffexSettlementCollectorError(exc.code) from exc
        if lease is None:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_FETCH_LEASE_BUSY")

        primary_failure: BaseException | None = None
        try:
            try:
                batch = await self._source.fetch_batch(trading_date=plan.trading_date)
            except CffexSettlementCollectorError:
                raise
            except Exception as exc:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_FAILED") from exc
            if not isinstance(batch, CffexSettlementSourceBatch):
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_BATCH_INVALID")
            if batch.provider_id != plan.source_registry_id:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PROVIDER_MISMATCH")

            normalized = _normalize_batch(batch=batch, plan=plan)
            local_received_at = _as_utc(self._clock(), field_name="local receipt timestamp")
            if batch.retrieved_at > local_received_at:
                raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RETRIEVED_AT_FUTURE")

            persisted_fetches: list[PersistedProviderFetch] = []
            for symbol in sorted(plan.targets_by_symbol):
                target = plan.targets_by_symbol[symbol]
                normalized_row = normalized.rows_by_symbol[symbol]
                result = _provider_result_for_target(
                    batch=normalized,
                    plan=plan,
                    target=target,
                    row=normalized_row,
                )
                persisted_fetches.append(
                    await self._store.persist_provider_result(
                        target.context,
                        result,
                        received_at=local_received_at,
                        source_authorization=target.source_authorization,
                        fetch_lease=lease,
                    )
                )

            return CffexSettlementCollectionReport(
                trading_date=plan.trading_date,
                provider_id=batch.provider_id,
                source_revision=batch.source_revision,
                source_retrieved_at=batch.retrieved_at,
                local_received_at=local_received_at,
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
            release_error: CffexSettlementCollectorError | None = None
            try:
                released = await lease_manager.release(lease)
                if not released:
                    release_error = CffexSettlementCollectorError(
                        "CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED"
                    )
            except MarketDataFetchLeaseError as exc:
                release_error = CffexSettlementCollectorError(
                    "CFFEX_SETTLEMENT_FETCH_LEASE_RELEASE_FAILED"
                )
                release_error.__cause__ = exc
            if primary_failure is None and release_error is not None:
                raise release_error


def cffex_settlement_feed_lease_key(
    *,
    trading_date: date,
    provider_id: str,
    source_authorization_descriptor_hash: str,
    targets: Sequence[CffexSettlementCollectionTarget],
) -> str:
    """Return the feed-level lease identity for one frozen market-wide batch.

    A per-symbol query lease would permit one network request per contract.
    This key instead binds the explicit trade date, approved source decision,
    and complete frozen identity/query map, so independent workers contend for
    the same all-market request without sharing a stale authorization plan.
    """
    target_date = _require_trading_date(trading_date)
    normalized_provider_id = _require_text(provider_id, field_name="provider_id", maximum=255)
    descriptor_hash = _require_sha256(
        source_authorization_descriptor_hash,
        field_name="source_authorization_descriptor_hash",
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
        _assert_target_authorization(source_authorization)
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
    authorization_hash = next(iter(authorization_hashes))
    feed_key = cffex_settlement_feed_lease_key(
        trading_date=target_date,
        provider_id=source_registry_id,
        source_authorization_descriptor_hash=authorization_hash,
        targets=frozen_targets,
    )
    return _PreparedCollection(
        trading_date=target_date,
        targets_by_symbol=MappingProxyType(dict(by_symbol)),
        source_registry_id=source_registry_id,
        source_authorization_descriptor_hash=authorization_hash,
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
        or query.family_id not in {None, CFFEX_SETTLEMENT_FAMILY_ID}
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_CONTRACT_INVALID")
    _require_cffex_symbol(identity.identity.display_symbol)


def _assert_target_authorization(source_authorization: MarketDataSourceAuthorization) -> None:
    """Keep a scheduled batch tied to one exact verified source decision."""
    if not isinstance(source_authorization, MarketDataSourceAuthorization):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_INVALID")
    if (
        source_authorization.asset_type != "futures"
        or source_authorization.market != CFFEX_SETTLEMENT_MARKET
        or source_authorization.decision != "ALLOW"
    ):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_TARGET_AUTHORIZATION_INVALID")
    _require_text(
        source_authorization.source_registry_id,
        field_name="source_registry_id",
        maximum=255,
    )


def _normalize_batch(
    *, batch: CffexSettlementSourceBatch, plan: _PreparedCollection
) -> _NormalizedBatch:
    """Validate one raw envelope in full before opening a fact-publication path."""
    safe_payload = _json_safe(batch.raw_payload)
    if not isinstance(safe_payload, Mapping):  # Defensive; _json_safe preserves mappings.
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_PAYLOAD_INVALID")
    payload = MappingProxyType(dict(safe_payload))
    _assert_source_request(payload=payload, trading_date=plan.trading_date)
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


def _assert_source_request(*, payload: Mapping[str, object], trading_date: date) -> None:
    """Bind raw evidence to one exact CFFEX date before consuming any row."""
    request = payload.get("collector_request")
    if not isinstance(request, Mapping):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if set(request) != {"market", "trading_date"}:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if request.get("market") != CFFEX_SETTLEMENT_MARKET:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")
    if request.get("trading_date") != trading_date.isoformat():
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_REQUEST_INVALID")


def _assert_row_market_and_date(*, row: Mapping[str, object], trading_date: date) -> None:
    market = _one_text_field(
        row,
        aliases=("MARKET", "market", "市场"),
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
        # Preserve the frozen internal context exactly. The collector may be
        # invoked with an unbound internal request while the public family
        # remains deliberately unconfigured; a provider receipt must not
        # invent a public family binding the caller did not resolve.
        family_id=context.query.family_id,
        provider_endpoint=CFFEX_SETTLEMENT_PROVIDER_ENDPOINT,
    )
    raw_payload = {
        "collector": {
            "contract_version": CFFEX_SETTLEMENT_COLLECTOR_VERSION,
            "collection_mode": "scheduled_market_batch",
            "trading_date": plan.trading_date.isoformat(),
            "source_batch_sha256": batch.source_batch_sha256,
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


def _resolve_akshare_callable() -> Callable[..., Any]:
    try:
        akshare = importlib.import_module("akshare")
    except ImportError as exc:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_UNAVAILABLE") from exc
    source_callable = getattr(akshare, "get_futures_daily", None)
    if not callable(source_callable):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_UNAVAILABLE")
    return source_callable


def _coerce_response_rows(response: object) -> list[dict[str, object]]:
    """Convert a bounded DataFrame-like source response to exact record mappings."""
    if response is None:
        return []
    try:
        length = len(response)  # type: ignore[arg-type]
    except TypeError:
        length = None
    if length is not None and length > _MAX_SOURCE_ROWS:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_TOO_LARGE")
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict(orient="records")
        except (TypeError, ValueError) as exc:
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_INVALID") from exc
    else:
        rows = response
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_INVALID")
    if len(rows) > _MAX_SOURCE_ROWS:
        raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_TOO_LARGE")
    normalized: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise CffexSettlementCollectorError("CFFEX_SETTLEMENT_SOURCE_RESPONSE_INVALID")
        normalized.append(dict(row))
    return normalized


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "AkShareCffexSettlementSource",
    "CFFEX_SETTLEMENT_COLLECTOR_VERSION",
    "CFFEX_SETTLEMENT_REQUIRED_FIELDS",
    "CffexSettlementCollectionReport",
    "CffexSettlementCollectionTarget",
    "CffexSettlementCollector",
    "CffexSettlementCollectorError",
    "CffexSettlementSource",
    "CffexSettlementSourceBatch",
    "cffex_settlement_feed_lease_key",
]
