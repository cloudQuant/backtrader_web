"""Fail-closed normalization for attested legacy ``STOCK_ZH_A_HIST`` rows.

The legacy warehouse is evidence input only.  It is never a request-time data
fallback.  A later canonical-store adapter must still perform present-tense
source authorization and persist a provider receipt; this module deliberately
stops at an auditable, immutable import batch and a local-only reread seam.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.market_data.coverage import EventKey, TimeWindow
from app.services.market_data.field_quality import (
    FieldQualityValueError,
    normalize_numeric_field_value,
)
from app.services.market_data.publication import MarketDataVisibilityAnchor

UTC = timezone.utc
LEGACY_STOCK_DAILY_TABLE = "STOCK_ZH_A_HIST"
LEGACY_STOCK_DAILY_SCHEMA_VERSION = "stock-zh-a-hist-v1"
LEGACY_STOCK_DAILY_COLUMN_MAP: Mapping[str, str] = MappingProxyType(
    {
        "provider_symbol": "symbol",
        "event_date": "data_date",
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "volume": "成交量",
        "change_pct": "涨跌幅",
    }
)

_REQUIRED_FIELD_NAMES = ("open", "high", "low", "close", "volume", "change_pct")
_SOURCE_COLUMNS = tuple(LEGACY_STOCK_DAILY_COLUMN_MAP.values())
_RAW_PAYLOAD_FORMAT = "legacy-stock-daily-source-batch-v2"
_SOURCE_SCHEMA_FORMAT = "legacy-stock-daily-source-schema-v1"
_IMPORT_SCOPE_FORMAT = "legacy-stock-daily-import-scope-v1"
_CANONICAL_CONTRACT_FORMAT = "legacy-stock-daily-canonical-contract-v1"
_RAW_ROW_ORDER = MappingProxyType(
    {
        "keys": ("event_at_utc", "canonical_id", "provider_symbol"),
        "version": 1,
    }
)
_MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_MARKETS = frozenset({"CN-SSE", "CN-SZSE"})
# ``STOCK_ZH_A_HIST`` has historically accepted AkShare/Eastmoney records,
# Tencent fallbacks, and trends-derived rows.  Its table name therefore cannot
# prove an AkShare route.  The protocol labels it as an explicit legacy
# warehouse source until a separately reviewed per-row provenance migration
# exists.  Keep these identifiers public because every concrete gate/reader
# must reject an attempt to relabel the mixed table as an AkShare receipt.
LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID = "legacy-stock-zh-a-hist-warehouse"
LEGACY_STOCK_DAILY_PROVIDER_ID = LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID
LEGACY_STOCK_DAILY_ROUTE_ID = "legacy-stock-zh-a-hist-offline-import-v1"
LEGACY_STOCK_DAILY_PROVENANCE_CLASS = "mixed_legacy_warehouse"

_REQUIRED_ATTESTATION = {
    "source_id": LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
    "adjustment": "qfq",
    "source_timezone": "Asia/Shanghai",
    "schema_version": LEGACY_STOCK_DAILY_SCHEMA_VERSION,
}
_REQUIRED_PROVIDER_ID = LEGACY_STOCK_DAILY_PROVIDER_ID
_REQUIRED_ROUTE_ID = LEGACY_STOCK_DAILY_ROUTE_ID


class LegacyStockDailyImportError(ValueError):
    """Stable rejection emitted before a legacy row becomes canonical evidence."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class LegacyStockDailyImportAttestation:
    """Declared source semantics for a batch pending independent evidence review.

    ``retrieved_at`` is retained as descriptive legacy metadata only.  It is
    never copied into canonical availability; the evidence gate's sealed
    extraction receipt supplies that conservative bound after row selection.
    """

    source_id: str
    source_revision: str
    adjustment: str
    source_timezone: str
    retrieved_at: datetime
    schema_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_id",
            "source_revision",
            "adjustment",
            "source_timezone",
            "schema_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        object.__setattr__(
            self,
            "retrieved_at",
            _as_utc(self.retrieved_at, field_name="retrieved_at"),
        )


@dataclass(frozen=True, slots=True)
class LegacyStockDailyReadScopeReceipt:
    """Gate-owned authorization and physical schema proof returned before I/O.

    ``source_schema_sha256`` is the digest of the gate-verified physical table
    projection, not a hash inferred from this module's Python mapping.  The
    latter is separately included in the immutable import scope.
    """

    source_registry_id: str
    provider_id: str
    route_id: str
    authorization_receipt_id: str
    source_schema_sha256: str

    def __post_init__(self) -> None:
        for field_name in (
            "source_registry_id",
            "provider_id",
            "route_id",
            "authorization_receipt_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        _require_sha256(self.source_schema_sha256, field_name="source_schema_sha256")


@dataclass(frozen=True, slots=True)
class LegacyStockDailySourceBatchReceipt:
    """An immutable proof that one approved scope produced one selected batch.

    The evidence gate supplies this only after it has rechecked the exact
    legacy source scope and bound the raw source batch bytes to an upstream
    receipt.  A free-text ``source_revision`` is never a substitute for it.
    """

    source_batch_sha256: str
    source_registry_id: str
    provider_id: str
    route_id: str
    authorization_receipt_id: str
    source_receipt_id: str
    source_schema_sha256: str
    import_scope_sha256: str
    extracted_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "source_batch_sha256",
            "source_schema_sha256",
            "import_scope_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name=field_name)
        for field_name in (
            "source_registry_id",
            "provider_id",
            "route_id",
            "authorization_receipt_id",
            "source_receipt_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        object.__setattr__(
            self,
            "extracted_at",
            _as_utc(self.extracted_at, field_name="extracted_at"),
        )


@dataclass(frozen=True, slots=True)
class LegacyStockDailyCanonicalWritePermit:
    """Gate-owned current authorization and lease evidence for one canonical target.

    A concrete gate may create this only after it has reauthorized the exact
    route for the exact resolved context, canonical target, and principal
    immediately before the write.  The opaque descriptor hashes let this
    protocol bind that decision without accepting a caller-constructed
    authorization object.
    """

    canonical_id: str
    source_registry_id: str
    provider_id: str
    route_id: str
    read_authorization_receipt_id: str
    source_batch_sha256: str
    import_scope_sha256: str
    source_receipt_id: str
    write_authorization_descriptor_sha256: str
    resolved_context_sha256: str
    fetch_lease_key_sha256: str
    fetch_lease_fence_token: int

    def __post_init__(self) -> None:
        for field_name in (
            "canonical_id",
            "source_registry_id",
            "provider_id",
            "route_id",
            "read_authorization_receipt_id",
            "source_receipt_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        for field_name in (
            "write_authorization_descriptor_sha256",
            "resolved_context_sha256",
            "fetch_lease_key_sha256",
            "source_batch_sha256",
            "import_scope_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name=field_name)
        if (
            not isinstance(self.fetch_lease_fence_token, int)
            or isinstance(self.fetch_lease_fence_token, bool)
            or self.fetch_lease_fence_token < 1
        ):
            raise ValueError("fetch_lease_fence_token must be a positive integer")


@dataclass(frozen=True, slots=True)
class LegacyStockDailyBarRevisionBinding:
    """One canonical bar's immutable revision and source-snapshot evidence."""

    canonical_id: str
    event_at: datetime
    observation_revision_id: str
    source_snapshot_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "canonical_id",
            "observation_revision_id",
            "source_snapshot_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        object.__setattr__(self, "event_at", _as_utc(self.event_at, field_name="event_at"))


@dataclass(frozen=True, slots=True)
class LegacyStockDailyPublicationReceipt:
    """One post-commit publication receipt sealed for a written source snapshot."""

    publication_id: str
    source_snapshot_id: str
    visible_at: datetime
    visibility_sequence: int

    def __post_init__(self) -> None:
        for field_name in ("publication_id", "source_snapshot_id"):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        object.__setattr__(
            self,
            "visible_at",
            _as_utc(self.visible_at, field_name="visible_at"),
        )
        if (
            not isinstance(self.visibility_sequence, int)
            or isinstance(self.visibility_sequence, bool)
            or self.visibility_sequence < 1
        ):
            raise ValueError("visibility_sequence must be a positive integer")


@dataclass(frozen=True, slots=True)
class LegacyStockDailyCanonicalWrite:
    """The concrete canonical facts and sealed publication receipts from one write."""

    source_snapshot_ids: frozenset[str]
    observation_revision_ids: frozenset[str]
    observation_revision_source_snapshot_ids: Mapping[str, str]
    bar_revision_bindings: tuple[LegacyStockDailyBarRevisionBinding, ...]
    target_write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit]
    source_batch_sha256: str
    import_scope_sha256: str
    source_receipt_id: str
    local_observation_available_at: datetime
    published_at: datetime
    publication_receipts: tuple[LegacyStockDailyPublicationReceipt, ...]

    def __post_init__(self) -> None:
        for field_name in ("source_snapshot_ids", "observation_revision_ids"):
            values = _normalized_identifier_set(getattr(self, field_name), field_name=field_name)
            object.__setattr__(self, field_name, values)
        if not isinstance(self.observation_revision_source_snapshot_ids, Mapping):
            raise TypeError("observation_revision_source_snapshot_ids must be a mapping")
        revision_to_snapshot = {
            _require_text(
                revision_id, field_name="observation_revision_id", maximum=255
            ): _require_text(
                source_snapshot_id,
                field_name="source_snapshot_id",
                maximum=255,
            )
            for revision_id, source_snapshot_id in self.observation_revision_source_snapshot_ids.items()
        }
        if (
            frozenset(revision_to_snapshot) != self.observation_revision_ids
            or frozenset(revision_to_snapshot.values()) != self.source_snapshot_ids
        ):
            raise ValueError(
                "canonical write revision-to-source mapping does not match written facts"
            )
        bindings = tuple(self.bar_revision_bindings)
        if not bindings or any(
            not isinstance(item, LegacyStockDailyBarRevisionBinding) for item in bindings
        ):
            raise ValueError("bar_revision_bindings must be non-empty bar revision bindings")
        if (
            len({(item.canonical_id, item.event_at) for item in bindings}) != len(bindings)
            or len({item.observation_revision_id for item in bindings}) != len(bindings)
            or frozenset(item.observation_revision_id for item in bindings)
            != self.observation_revision_ids
            or any(
                revision_to_snapshot[item.observation_revision_id] != item.source_snapshot_id
                for item in bindings
            )
        ):
            raise ValueError("canonical write bar bindings do not match revision/source evidence")
        target_write_permits = _normalize_target_write_permits(
            self.target_write_permits,
            field_name="target_write_permits",
        )
        binding_targets = frozenset(item.canonical_id for item in bindings)
        if frozenset(target_write_permits) != binding_targets:
            raise ValueError("canonical write permits do not match bound bar targets")
        snapshot_targets: dict[str, str] = {}
        for binding in bindings:
            previous_target = snapshot_targets.setdefault(
                binding.source_snapshot_id,
                binding.canonical_id,
            )
            if previous_target != binding.canonical_id:
                raise ValueError("one source snapshot cannot prove multiple canonical targets")
        for field_name in (
            "source_batch_sha256",
            "import_scope_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name=field_name)
        object.__setattr__(
            self,
            "source_receipt_id",
            _require_text(self.source_receipt_id, field_name="source_receipt_id", maximum=255),
        )
        local_observation_available_at = _as_utc(
            self.local_observation_available_at,
            field_name="local_observation_available_at",
        )
        object.__setattr__(
            self,
            "published_at",
            _as_utc(self.published_at, field_name="published_at"),
        )
        if local_observation_available_at > self.published_at:
            raise ValueError("local_observation_available_at must not follow publication")
        receipts = tuple(self.publication_receipts)
        if not receipts or any(
            not isinstance(item, LegacyStockDailyPublicationReceipt) for item in receipts
        ):
            raise ValueError("publication_receipts must be non-empty publication receipts")
        if (
            len({item.publication_id for item in receipts}) != len(receipts)
            or len({item.source_snapshot_id for item in receipts}) != len(receipts)
            or len({item.visibility_sequence for item in receipts}) != len(receipts)
            or frozenset(item.source_snapshot_id for item in receipts) != self.source_snapshot_ids
            or any(item.visible_at < local_observation_available_at for item in receipts)
            or max(item.visible_at for item in receipts) != self.published_at
        ):
            raise ValueError("canonical write publication receipts do not match written snapshots")
        object.__setattr__(
            self,
            "observation_revision_source_snapshot_ids",
            MappingProxyType(revision_to_snapshot),
        )
        object.__setattr__(self, "bar_revision_bindings", bindings)
        object.__setattr__(self, "target_write_permits", target_write_permits)
        object.__setattr__(
            self,
            "local_observation_available_at",
            local_observation_available_at,
        )
        object.__setattr__(self, "publication_receipts", receipts)


@dataclass(frozen=True, slots=True)
class FrozenLegacyStockDailyIdentity:
    """An exact source-symbol to canonical identity mapping frozen before I/O."""

    provider_symbol: str
    canonical_id: str
    market: str
    identity_revision: str
    instrument_metadata_version: str

    def __post_init__(self) -> None:
        for field_name in (
            "provider_symbol",
            "canonical_id",
            "market",
            "identity_revision",
            "instrument_metadata_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )


@dataclass(frozen=True, slots=True)
class FrozenLegacyStockDailyCalendar:
    """One PIT-frozen, single-snapshot ``bars/1d`` source-date map."""

    calendar_snapshot_id: str
    calendar_code: str
    calendar_version: str
    timezone_name: str
    data_kind: str
    frequency: Literal["1d"]
    coverage_window: TimeWindow
    visibility_anchor: MarketDataVisibilityAnchor
    event_key_by_trading_date: Mapping[date, EventKey]

    def __post_init__(self) -> None:
        for field_name in (
            "calendar_snapshot_id",
            "calendar_code",
            "calendar_version",
            "timezone_name",
            "data_kind",
            "frequency",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        if not isinstance(self.coverage_window, TimeWindow):
            raise TypeError("coverage_window must be a TimeWindow")
        if not isinstance(self.visibility_anchor, MarketDataVisibilityAnchor):
            raise TypeError("visibility_anchor must be a MarketDataVisibilityAnchor")
        if not isinstance(self.event_key_by_trading_date, Mapping):
            raise TypeError("event_key_by_trading_date must be a mapping")
        normalized: dict[date, EventKey] = {}
        seen_keys: set[EventKey] = set()
        for trading_date, event_key in self.event_key_by_trading_date.items():
            if not isinstance(trading_date, date) or isinstance(trading_date, datetime):
                raise TypeError("calendar trading_date must be a date")
            if not isinstance(event_key, EventKey):
                raise TypeError("calendar event_key must be an EventKey")
            if not self.coverage_window.contains(event_key) or event_key in seen_keys:
                raise ValueError("calendar event map must be one-to-one inside its coverage")
            normalized[trading_date] = event_key
            seen_keys.add(event_key)
        if not normalized:
            raise ValueError("calendar event map must not be empty")
        object.__setattr__(self, "event_key_by_trading_date", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class LegacyStockDailyImportScope:
    """Immutable derivation context separately bound from selected raw rows.

    The raw-batch digest says which source cells were selected.  This scope
    digest says how those cells were interpreted: fixed source projection,
    attestation semantics, the PIT-frozen calendar, and the identity revisions
    used to derive canonical IDs and EventKeys.  A receipt must bind both.
    """

    attestation: LegacyStockDailyImportAttestation
    calendar: FrozenLegacyStockDailyCalendar
    frozen_identities: Mapping[str, FrozenLegacyStockDailyIdentity]
    read_scope_receipt: LegacyStockDailyReadScopeReceipt
    source_schema_sha256: str = field(init=False)
    import_scope_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        attestation = _validate_attestation(self.attestation)
        _validate_calendar(self.calendar)
        identities = _validate_frozen_identities(
            self.frozen_identities,
            calendar_code=self.calendar.calendar_code,
        )
        read_scope_receipt = _validate_read_scope_receipt(
            self.read_scope_receipt,
            attestation=attestation,
        )
        projection_sha256 = _sha256_json(_source_projection_descriptor())
        scope_payload = {
            "format": _IMPORT_SCOPE_FORMAT,
            "source_schema_sha256": read_scope_receipt.source_schema_sha256,
            "source_projection_sha256": projection_sha256,
            "source_projection": list(_SOURCE_COLUMNS),
            "column_map": dict(LEGACY_STOCK_DAILY_COLUMN_MAP),
            "raw_payload_format": _RAW_PAYLOAD_FORMAT,
            "row_order": _plain_json_value(_RAW_ROW_ORDER),
            "canonical_contract": {
                "format": _CANONICAL_CONTRACT_FORMAT,
                "data_kind": "bars",
                "frequency": "1d",
                "adjustment": "qfq",
                "required_fields": list(_REQUIRED_FIELD_NAMES),
            },
            "source_route": {
                "source_registry_id": read_scope_receipt.source_registry_id,
                "provider_id": read_scope_receipt.provider_id,
                "route_id": read_scope_receipt.route_id,
                "authorization_receipt_id": read_scope_receipt.authorization_receipt_id,
            },
            "attestation": {
                "source_id": attestation.source_id,
                "source_revision": attestation.source_revision,
                "adjustment": attestation.adjustment,
                "source_timezone": attestation.source_timezone,
                "schema_version": attestation.schema_version,
            },
            "calendar": _calendar_scope_descriptor(self.calendar),
            "identities": [
                {
                    "provider_symbol": identity.provider_symbol,
                    "canonical_id": identity.canonical_id,
                    "market": identity.market,
                    "identity_revision": identity.identity_revision,
                    "instrument_metadata_version": identity.instrument_metadata_version,
                }
                for identity in sorted(
                    identities.values(),
                    key=lambda item: (
                        item.provider_symbol,
                        item.canonical_id,
                        item.identity_revision,
                    ),
                )
            ],
        }
        object.__setattr__(self, "attestation", attestation)
        object.__setattr__(self, "frozen_identities", identities)
        object.__setattr__(self, "read_scope_receipt", read_scope_receipt)
        object.__setattr__(self, "source_schema_sha256", read_scope_receipt.source_schema_sha256)
        object.__setattr__(self, "import_scope_sha256", _sha256_json(scope_payload))


@dataclass(frozen=True, slots=True)
class LegacyStockDailySourceBar:
    """A normalized source fact before the canonical store creates local PIT time."""

    provider_symbol: str
    canonical_id: str
    market: str
    frequency: Literal["1d"]
    adjustment: Literal["qfq"]
    event_at: datetime
    source_available_at: datetime | None
    fields: Mapping[str, int | float | str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_symbol",
            _require_text(self.provider_symbol, field_name="provider_symbol", maximum=255),
        )
        object.__setattr__(
            self,
            "canonical_id",
            _require_text(self.canonical_id, field_name="canonical_id", maximum=255),
        )
        object.__setattr__(
            self, "market", _require_text(self.market, field_name="market", maximum=128)
        )
        if self.frequency != "1d" or self.adjustment != "qfq":
            raise ValueError("daily bar semantics do not match the reviewed contract")
        event_at = _as_utc(self.event_at, field_name="event_at")
        source_available_at = (
            None
            if self.source_available_at is None
            else _as_utc(self.source_available_at, field_name="source_available_at")
        )
        if source_available_at is not None and source_available_at < event_at:
            raise ValueError("source_available_at must not precede event_at")
        if not isinstance(self.fields, Mapping) or frozenset(self.fields) != frozenset(
            _REQUIRED_FIELD_NAMES
        ):
            raise ValueError("daily bar fields do not match the reviewed schema")
        normalized_fields = {
            name: _require_json_numeric(value, field_name=name)
            for name, value in self.fields.items()
        }
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "source_available_at", source_available_at)
        object.__setattr__(self, "fields", MappingProxyType(normalized_fields))


@dataclass(frozen=True, slots=True)
class LegacyStockDailyBar:
    """A canonical local fact with distinct upstream and local availability time."""

    provider_symbol: str
    canonical_id: str
    market: str
    frequency: Literal["1d"]
    adjustment: Literal["qfq"]
    event_at: datetime
    source_available_at: datetime
    available_at: datetime
    observation_revision_id: str
    source_snapshot_id: str
    fields: Mapping[str, int | float | str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_symbol",
            _require_text(self.provider_symbol, field_name="provider_symbol", maximum=255),
        )
        object.__setattr__(
            self,
            "canonical_id",
            _require_text(self.canonical_id, field_name="canonical_id", maximum=255),
        )
        object.__setattr__(
            self, "market", _require_text(self.market, field_name="market", maximum=128)
        )
        if self.frequency != "1d" or self.adjustment != "qfq":
            raise ValueError("daily bar semantics do not match the reviewed contract")
        event_at = _as_utc(self.event_at, field_name="event_at")
        source_available_at = _as_utc(self.source_available_at, field_name="source_available_at")
        available_at = _as_utc(self.available_at, field_name="available_at")
        if source_available_at < event_at or available_at < source_available_at:
            raise ValueError("canonical availability order is invalid")
        for field_name in ("observation_revision_id", "source_snapshot_id"):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name, maximum=255),
            )
        if not isinstance(self.fields, Mapping) or frozenset(self.fields) != frozenset(
            _REQUIRED_FIELD_NAMES
        ):
            raise ValueError("daily bar fields do not match the reviewed schema")
        normalized_fields = {
            name: _require_json_numeric(value, field_name=name)
            for name, value in self.fields.items()
        }
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "source_available_at", source_available_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "fields", MappingProxyType(normalized_fields))


@dataclass(frozen=True, slots=True)
class LegacyStockDailyImportBatch:
    """Immutable raw source subset and normalized projection for one import."""

    raw_payload: Mapping[str, object]
    bars: tuple[LegacyStockDailySourceBar, ...]
    calendar: FrozenLegacyStockDailyCalendar
    import_scope: LegacyStockDailyImportScope
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.calendar, FrozenLegacyStockDailyCalendar):
            raise TypeError("calendar must be a FrozenLegacyStockDailyCalendar")
        if not isinstance(self.import_scope, LegacyStockDailyImportScope):
            raise TypeError("import_scope must be a LegacyStockDailyImportScope")
        if self.import_scope.calendar != self.calendar:
            raise ValueError("import_scope calendar must match batch calendar")
        bars = tuple(self.bars)
        if not bars or any(not isinstance(bar, LegacyStockDailySourceBar) for bar in bars):
            raise ValueError("batch bars must be non-empty LegacyStockDailySourceBar values")
        if len({bar.source_available_at is None for bar in bars}) != 1:
            raise ValueError("batch bars must share one source-availability state")
        frozen_payload = _freeze_json_value(self.raw_payload)
        if not isinstance(frozen_payload, Mapping):
            raise TypeError("raw_payload must be a mapping")
        canonical_bytes = _canonical_json_bytes(frozen_payload)
        object.__setattr__(self, "raw_payload", frozen_payload)
        object.__setattr__(self, "bars", bars)
        object.__setattr__(self, "content_sha256", hashlib.sha256(canonical_bytes).hexdigest())


@dataclass(frozen=True, slots=True)
class LegacyStockDailyLocalReread:
    """The independent canonical local-only evidence returned after a write."""

    bars: tuple[LegacyStockDailyBar, ...]
    calendar: FrozenLegacyStockDailyCalendar
    input_event_keys: tuple[EventKey, ...]
    accepted_event_keys: tuple[EventKey, ...]
    knowledge_cutoff: datetime
    visibility_anchor: MarketDataVisibilityAnchor
    mode: Literal["local_only"]
    source_snapshot_ids: frozenset[str]
    observation_revision_ids: frozenset[str]

    def __post_init__(self) -> None:
        bars = tuple(self.bars)
        input_event_keys = tuple(self.input_event_keys)
        accepted_event_keys = tuple(self.accepted_event_keys)
        if any(not isinstance(bar, LegacyStockDailyBar) for bar in bars):
            raise TypeError("bars must contain LegacyStockDailyBar values")
        if not isinstance(self.calendar, FrozenLegacyStockDailyCalendar):
            raise TypeError("calendar must be a FrozenLegacyStockDailyCalendar")
        if any(not isinstance(item, EventKey) for item in input_event_keys + accepted_event_keys):
            raise TypeError("event-key evidence must contain EventKey values")
        knowledge_cutoff = _as_utc(self.knowledge_cutoff, field_name="knowledge_cutoff")
        if not isinstance(self.visibility_anchor, MarketDataVisibilityAnchor):
            raise TypeError("visibility_anchor must be a MarketDataVisibilityAnchor")
        if self.mode != "local_only":
            raise ValueError("reread mode must be local_only")
        source_snapshot_ids = _normalized_identifier_set(
            self.source_snapshot_ids,
            field_name="source_snapshot_ids",
        )
        observation_revision_ids = _normalized_identifier_set(
            self.observation_revision_ids,
            field_name="observation_revision_ids",
        )
        object.__setattr__(self, "bars", bars)
        object.__setattr__(self, "input_event_keys", input_event_keys)
        object.__setattr__(self, "accepted_event_keys", accepted_event_keys)
        object.__setattr__(self, "knowledge_cutoff", knowledge_cutoff)
        object.__setattr__(self, "source_snapshot_ids", source_snapshot_ids)
        object.__setattr__(self, "observation_revision_ids", observation_revision_ids)


@dataclass(frozen=True, slots=True)
class LegacyStockDailyImportReport:
    """Evidence returned for a dry run or a completed canonical reread."""

    dry_run: bool
    action: Literal["would_import", "imported"]
    source_row_count: int
    normalized_bar_count: int
    calendar_snapshot_id: str
    source_batch_sha256: str
    import_scope_sha256: str
    source_receipt_id: str
    input_event_keys: tuple[EventKey, ...]
    accepted_event_keys: tuple[EventKey, ...]
    local_only_bars: tuple[LegacyStockDailyBar, ...]


class LegacyStockDailyReader(Protocol):
    """Read precisely the implementation-owned legacy source table."""

    async def read_rows(
        self,
        *,
        table_name: str,
        source_columns: tuple[str, ...],
        source_schema_sha256: str,
    ) -> Sequence[Mapping[str, object]]:
        """Return the exact reviewed projection for the fixed allowlisted table."""


class LegacyStockDailyCanonicalWriter(Protocol):
    """Publish an attested batch then prove it through a local-only reread."""

    async def write_daily_bars(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        source_batch_receipt: LegacyStockDailySourceBatchReceipt,
        write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit],
    ) -> LegacyStockDailyCanonicalWrite:
        """Persist only through an adapter that rechecks authorization and lease."""

    async def read_daily_bars_local_only(
        self,
        *,
        canonical_ids: frozenset[str],
        calendar: FrozenLegacyStockDailyCalendar,
        input_event_keys: tuple[EventKey, ...],
        canonical_write: LegacyStockDailyCanonicalWrite,
        knowledge_cutoff: datetime,
    ) -> LegacyStockDailyLocalReread:
        """Return independently selected canonical facts and coverage evidence."""


class LegacyStockDailyEvidenceGate(Protocol):
    """Prove a legacy source scope before its table can be read.

    A production implementation must bind this decision to current source
    authorization and a sealed source receipt manifest.  This module has no
    concrete production gate, so an unreviewed legacy table cannot become a
    canonical source merely by attaching an attestation string.
    """

    async def authorize_legacy_read(
        self,
        *,
        table_name: str,
        attestation: LegacyStockDailyImportAttestation,
        calendar: FrozenLegacyStockDailyCalendar,
        frozen_identities: Mapping[str, FrozenLegacyStockDailyIdentity],
    ) -> LegacyStockDailyReadScopeReceipt:
        """Authorize the exact pre-read context and return its physical schema proof."""

    async def certify_source_batch(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        import_scope: LegacyStockDailyImportScope,
    ) -> LegacyStockDailySourceBatchReceipt:
        """Return a receipt that cryptographically binds the selected source batch."""

    async def authorize_canonical_writes(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        import_scope: LegacyStockDailyImportScope,
        source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        """Reauthorize every exact target/context and acquire each current write fence."""


class LegacyStockDailyImporter:
    """Normalize one constrained legacy batch without table, calendar, or ID inference."""

    def __init__(
        self,
        *,
        reader: LegacyStockDailyReader,
        writer: LegacyStockDailyCanonicalWriter,
        evidence_gate: LegacyStockDailyEvidenceGate,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(getattr(reader, "read_rows", None)):
            raise TypeError("reader must implement read_rows")
        if not callable(getattr(writer, "write_daily_bars", None)) or not callable(
            getattr(writer, "read_daily_bars_local_only", None)
        ):
            raise TypeError("writer must implement canonical write and local-only reread")
        if (
            not callable(getattr(evidence_gate, "authorize_legacy_read", None))
            or not callable(getattr(evidence_gate, "certify_source_batch", None))
            or not callable(getattr(evidence_gate, "authorize_canonical_writes", None))
        ):
            raise TypeError(
                "evidence_gate must implement precheck, source-batch certification, and write authorizations"
            )
        self._reader = reader
        self._writer = writer
        self._evidence_gate = evidence_gate
        self._clock = clock or (lambda: datetime.now(UTC))

    async def import_table(
        self,
        *,
        table_name: str,
        attestation: LegacyStockDailyImportAttestation | None,
        calendar: FrozenLegacyStockDailyCalendar,
        frozen_identities: Mapping[str, FrozenLegacyStockDailyIdentity],
        dry_run: bool,
    ) -> LegacyStockDailyImportReport:
        """Read, normalize, write, and prove exactly one audited legacy table."""
        _require_exact_table(table_name)
        approved_attestation = _validate_attestation(attestation)
        _validate_calendar(calendar)
        identities = _validate_frozen_identities(
            frozen_identities, calendar_code=calendar.calendar_code
        )
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a bool")
        try:
            read_scope_receipt = await self._evidence_gate.authorize_legacy_read(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                attestation=approved_attestation,
                calendar=calendar,
                frozen_identities=identities,
            )
            import_scope = LegacyStockDailyImportScope(
                attestation=approved_attestation,
                calendar=calendar,
                frozen_identities=identities,
                read_scope_receipt=read_scope_receipt,
            )
        except LegacyStockDailyImportError:
            raise
        except Exception as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_PRECHECK_FAILED") from exc
        try:
            rows = await self._reader.read_rows(
                table_name=LEGACY_STOCK_DAILY_TABLE,
                source_columns=_SOURCE_COLUMNS,
                source_schema_sha256=import_scope.source_schema_sha256,
            )
        except LegacyStockDailyImportError:
            raise
        except Exception as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LEGACY_READ_FAILED") from exc
        bars, raw_rows = _normalize_rows(
            rows=rows,
            calendar=calendar,
            identities=identities,
        )
        batch = LegacyStockDailyImportBatch(
            raw_payload={
                "format": _RAW_PAYLOAD_FORMAT,
                "row_order": _RAW_ROW_ORDER,
                "rows": raw_rows,
                "source_columns": _SOURCE_COLUMNS,
                "table_name": LEGACY_STOCK_DAILY_TABLE,
            },
            bars=bars,
            calendar=calendar,
            import_scope=import_scope,
        )
        try:
            source_batch_receipt = await self._evidence_gate.certify_source_batch(
                batch=batch,
                attestation=approved_attestation,
                import_scope=import_scope,
            )
            _validate_source_batch_receipt(
                source_batch_receipt,
                batch=batch,
                attestation=approved_attestation,
                import_scope=import_scope,
            )
            batch = _bind_source_receipt_availability(
                batch,
                source_available_at=source_batch_receipt.extracted_at,
            )
        except LegacyStockDailyImportError:
            raise
        except Exception as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED") from exc
        input_event_keys = tuple(sorted({EventKey(bar.event_at) for bar in batch.bars}))
        if dry_run:
            return LegacyStockDailyImportReport(
                dry_run=True,
                action="would_import",
                source_row_count=len(rows),
                normalized_bar_count=len(batch.bars),
                calendar_snapshot_id=calendar.calendar_snapshot_id,
                source_batch_sha256=batch.content_sha256,
                import_scope_sha256=import_scope.import_scope_sha256,
                source_receipt_id=source_batch_receipt.source_receipt_id,
                input_event_keys=input_event_keys,
                accepted_event_keys=(),
                local_only_bars=(),
            )
        try:
            write_permits = await self._evidence_gate.authorize_canonical_writes(
                batch=batch,
                attestation=approved_attestation,
                import_scope=import_scope,
                source_batch_receipt=source_batch_receipt,
            )
            _validate_canonical_write_permits(
                write_permits,
                batch=batch,
                import_scope=import_scope,
                source_batch_receipt=source_batch_receipt,
            )
        except LegacyStockDailyImportError:
            raise
        except Exception as exc:
            raise LegacyStockDailyImportError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
            ) from exc
        try:
            canonical_write = await self._writer.write_daily_bars(
                batch=batch,
                attestation=approved_attestation,
                source_batch_receipt=source_batch_receipt,
                write_permits=write_permits,
            )
        except LegacyStockDailyImportError:
            raise
        except Exception as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_CANONICAL_WRITE_FAILED") from exc
        if not isinstance(canonical_write, LegacyStockDailyCanonicalWrite):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID")
        _validate_canonical_write(
            canonical_write,
            batch=batch,
            source_batch_receipt=source_batch_receipt,
            import_scope=import_scope,
            write_permits=write_permits,
        )
        try:
            postwrite_cutoff = max(
                _as_utc(self._clock(), field_name="postwrite_clock"),
                canonical_write.published_at,
            )
        except (TypeError, ValueError) as exc:
            raise LegacyStockDailyImportError(
                "LEGACY_STOCK_DAILY_LOCAL_REREAD_PIT_INVALID"
            ) from exc
        try:
            reread = await self._writer.read_daily_bars_local_only(
                canonical_ids=frozenset(bar.canonical_id for bar in batch.bars),
                calendar=calendar,
                input_event_keys=input_event_keys,
                canonical_write=canonical_write,
                knowledge_cutoff=postwrite_cutoff,
            )
        except LegacyStockDailyImportError:
            raise
        except Exception as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_FAILED") from exc
        _validate_local_reread(
            batch=batch,
            input_event_keys=input_event_keys,
            canonical_write=canonical_write,
            source_batch_receipt=source_batch_receipt,
            knowledge_cutoff=postwrite_cutoff,
            reread=reread,
        )
        return LegacyStockDailyImportReport(
            dry_run=False,
            action="imported",
            source_row_count=len(rows),
            normalized_bar_count=len(batch.bars),
            calendar_snapshot_id=calendar.calendar_snapshot_id,
            source_batch_sha256=batch.content_sha256,
            import_scope_sha256=import_scope.import_scope_sha256,
            source_receipt_id=source_batch_receipt.source_receipt_id,
            input_event_keys=input_event_keys,
            accepted_event_keys=reread.accepted_event_keys,
            local_only_bars=reread.bars,
        )


def _require_exact_table(value: object) -> None:
    if value != LEGACY_STOCK_DAILY_TABLE:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_TABLE_UNSUPPORTED")


def _validate_attestation(
    value: LegacyStockDailyImportAttestation | None,
) -> LegacyStockDailyImportAttestation:
    if value is None:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_ATTESTATION_REQUIRED")
    if not isinstance(value, LegacyStockDailyImportAttestation):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_ATTESTATION_INVALID")
    try:
        source_timezone = ZoneInfo(value.source_timezone)
    except ZoneInfoNotFoundError as exc:
        raise LegacyStockDailyImportError(
            "LEGACY_STOCK_DAILY_ATTESTATION_SEMANTICS_INVALID"
        ) from exc
    if (
        value.source_id != _REQUIRED_ATTESTATION["source_id"]
        or value.adjustment != _REQUIRED_ATTESTATION["adjustment"]
        or value.source_timezone != _REQUIRED_ATTESTATION["source_timezone"]
        or source_timezone.key != _REQUIRED_ATTESTATION["source_timezone"]
        or value.schema_version != _REQUIRED_ATTESTATION["schema_version"]
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_ATTESTATION_SEMANTICS_INVALID")
    return value


def _validate_source_batch_receipt(
    value: object,
    *,
    batch: LegacyStockDailyImportBatch,
    attestation: LegacyStockDailyImportAttestation,
    import_scope: LegacyStockDailyImportScope,
) -> LegacyStockDailySourceBatchReceipt:
    """Reject any receipt that does not bind raw bytes and their derivation scope."""
    if not isinstance(value, LegacyStockDailySourceBatchReceipt):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED")
    read_scope_receipt = import_scope.read_scope_receipt
    if (
        value.source_batch_sha256 != batch.content_sha256
        or batch.import_scope != import_scope
        or import_scope.attestation != attestation
        or value.source_registry_id != read_scope_receipt.source_registry_id
        or value.provider_id != read_scope_receipt.provider_id
        or value.route_id != read_scope_receipt.route_id
        or value.authorization_receipt_id != read_scope_receipt.authorization_receipt_id
        or value.source_schema_sha256 != import_scope.source_schema_sha256
        or value.import_scope_sha256 != import_scope.import_scope_sha256
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED")
    return value


def _normalize_target_write_permits(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
    """Freeze one non-forgeable permit per canonical target identity."""
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{field_name} must be a non-empty mapping")
    normalized: dict[str, LegacyStockDailyCanonicalWritePermit] = {}
    for canonical_id, permit in value.items():
        target = _require_text(canonical_id, field_name="canonical_id", maximum=255)
        if (
            not isinstance(permit, LegacyStockDailyCanonicalWritePermit)
            or permit.canonical_id != target
        ):
            raise ValueError(f"{field_name} contains an invalid target permit")
        if target in normalized:
            raise ValueError(f"{field_name} contains duplicate canonical targets")
        normalized[target] = permit
    if len({permit.resolved_context_sha256 for permit in normalized.values()}) != len(normalized):
        raise ValueError(f"{field_name} reuses a resolved context across canonical targets")
    if len({permit.fetch_lease_key_sha256 for permit in normalized.values()}) != len(normalized):
        raise ValueError(f"{field_name} reuses a fetch lease across canonical targets")
    return MappingProxyType(normalized)


def _validate_canonical_write_permits(
    value: object,
    *,
    batch: LegacyStockDailyImportBatch,
    import_scope: LegacyStockDailyImportScope,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
    """Require one fresh write permit for every sealed canonical target."""
    try:
        permits = _normalize_target_write_permits(
            value,
            field_name="target_write_permits",
        )
    except (TypeError, ValueError) as exc:
        raise LegacyStockDailyImportError(
            "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
        ) from exc
    expected_targets = frozenset(bar.canonical_id for bar in batch.bars)
    if frozenset(permits) != expected_targets:
        raise LegacyStockDailyImportError(
            "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
        )
    read_scope_receipt = import_scope.read_scope_receipt
    for permit in permits.values():
        if (
            permit.source_registry_id != source_batch_receipt.source_registry_id
            or permit.provider_id != source_batch_receipt.provider_id
            or permit.route_id != source_batch_receipt.route_id
            or permit.read_authorization_receipt_id != read_scope_receipt.authorization_receipt_id
            or permit.read_authorization_receipt_id != source_batch_receipt.authorization_receipt_id
            or permit.source_batch_sha256 != source_batch_receipt.source_batch_sha256
            or permit.import_scope_sha256 != import_scope.import_scope_sha256
            or permit.source_receipt_id != source_batch_receipt.source_receipt_id
        ):
            raise LegacyStockDailyImportError(
                "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
            )
    return permits


def _validate_canonical_write(
    value: LegacyStockDailyCanonicalWrite,
    *,
    batch: LegacyStockDailyImportBatch,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    import_scope: LegacyStockDailyImportScope,
    write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit],
) -> None:
    """Bind the write result to sealed source evidence and each target permit."""
    expected_bar_keys = {(bar.canonical_id, bar.event_at) for bar in batch.bars}
    bound_bar_keys = {
        (binding.canonical_id, binding.event_at) for binding in value.bar_revision_bindings
    }
    if (
        value.source_batch_sha256 != source_batch_receipt.source_batch_sha256
        or value.import_scope_sha256 != import_scope.import_scope_sha256
        or value.source_receipt_id != source_batch_receipt.source_receipt_id
        or value.target_write_permits != write_permits
        or bound_bar_keys != expected_bar_keys
        or value.local_observation_available_at < source_batch_receipt.extracted_at
        or any(bar.source_available_at != source_batch_receipt.extracted_at for bar in batch.bars)
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_CANONICAL_WRITE_INVALID")


def _validate_read_scope_receipt(
    value: object,
    *,
    attestation: LegacyStockDailyImportAttestation,
) -> LegacyStockDailyReadScopeReceipt:
    """Require the gate's pre-read proof to match the fixed source route."""
    if not isinstance(value, LegacyStockDailyReadScopeReceipt):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_PRECHECK_UNVERIFIED")
    if (
        value.source_registry_id != attestation.source_id
        or value.provider_id != _REQUIRED_PROVIDER_ID
        or value.route_id != _REQUIRED_ROUTE_ID
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_PRECHECK_UNVERIFIED")
    return value


def _validate_calendar(value: object) -> None:
    if not isinstance(value, FrozenLegacyStockDailyCalendar):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_CALENDAR_INVALID")
    try:
        timezone = ZoneInfo(value.timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_CALENDAR_SEMANTICS_INVALID") from exc
    if (
        value.calendar_code not in _ALLOWED_MARKETS
        or value.data_kind != "bars"
        or value.frequency != "1d"
        or value.timezone_name != "Asia/Shanghai"
        or timezone.key != "Asia/Shanghai"
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_CALENDAR_SEMANTICS_INVALID")


def _validate_frozen_identities(
    values: Mapping[str, FrozenLegacyStockDailyIdentity],
    *,
    calendar_code: str,
) -> Mapping[str, FrozenLegacyStockDailyIdentity]:
    if not isinstance(values, Mapping) or not values:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_IDENTITY_MAPPING_INVALID")
    normalized: dict[str, FrozenLegacyStockDailyIdentity] = {}
    for provider_symbol, identity in values.items():
        if not isinstance(provider_symbol, str) or not provider_symbol.strip():
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_IDENTITY_MAPPING_INVALID")
        if not isinstance(identity, FrozenLegacyStockDailyIdentity):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_IDENTITY_MAPPING_INVALID")
        normalized_symbol = provider_symbol.strip()
        if (
            normalized_symbol != identity.provider_symbol
            or identity.market not in _ALLOWED_MARKETS
            or identity.market != calendar_code
            or normalized_symbol in normalized
        ):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_IDENTITY_MAPPING_INVALID")
        normalized[normalized_symbol] = identity
    return MappingProxyType(normalized)


def _normalize_rows(
    *,
    rows: object,
    calendar: FrozenLegacyStockDailyCalendar,
    identities: Mapping[str, FrozenLegacyStockDailyIdentity],
) -> tuple[tuple[LegacyStockDailySourceBar, ...], tuple[Mapping[str, object], ...]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_READER_RESULT_INVALID")
    if not rows:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SOURCE_EMPTY")
    normalized_pairs: list[tuple[LegacyStockDailySourceBar, Mapping[str, object]]] = []
    seen: set[tuple[str, EventKey]] = set()
    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_ROW_INVALID")
        _require_source_columns(raw_row)
        provider_symbol = _required_symbol(
            raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["provider_symbol"]]
        )
        identity = identities.get(provider_symbol)
        if identity is None:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_IDENTITY_UNMATCHED")
        trading_date = _parse_trading_date(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["event_date"]])
        event_key = calendar.event_key_by_trading_date.get(trading_date)
        if event_key is None:
            raise LegacyStockDailyImportError(
                "LEGACY_STOCK_DAILY_CALENDAR_EVENT_UNMAPPED",
                detail=trading_date.isoformat(),
            )
        dedupe_key = (identity.canonical_id, event_key)
        if dedupe_key in seen:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_ROW_DUPLICATE")
        seen.add(dedupe_key)
        fields = _normalize_fields(raw_row)
        open_value = _as_decimal(fields["open"])
        high_value = _as_decimal(fields["high"])
        low_value = _as_decimal(fields["low"])
        close_value = _as_decimal(fields["close"])
        if low_value > min(open_value, close_value) or high_value < max(open_value, close_value):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_OHLC_INVALID")
        bar = LegacyStockDailySourceBar(
            provider_symbol=provider_symbol,
            canonical_id=identity.canonical_id,
            market=identity.market,
            frequency="1d",
            adjustment="qfq",
            event_at=event_key.event_at,
            source_available_at=None,
            fields=fields,
        )
        raw_row_payload = MappingProxyType(
            {
                "symbol": _raw_source_scalar(
                    raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["provider_symbol"]]
                ),
                "data_date": trading_date.isoformat(),
                "开盘": _raw_source_scalar(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["open"]]),
                "最高": _raw_source_scalar(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["high"]]),
                "最低": _raw_source_scalar(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["low"]]),
                "收盘": _raw_source_scalar(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["close"]]),
                "成交量": _raw_source_scalar(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["volume"]]),
                "涨跌幅": _raw_source_scalar(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["change_pct"]]),
            }
        )
        normalized_pairs.append((bar, raw_row_payload))
    normalized_pairs.sort(
        key=lambda item: (item[0].event_at, item[0].canonical_id, item[0].provider_symbol)
    )
    return (
        tuple(item[0] for item in normalized_pairs),
        tuple(item[1] for item in normalized_pairs),
    )


def _bind_source_receipt_availability(
    batch: LegacyStockDailyImportBatch,
    *,
    source_available_at: datetime,
) -> LegacyStockDailyImportBatch:
    """Reissue the source projection with the gate-owned source-availability time.

    The raw source payload and its content address do not change.  Only the
    upstream availability lower bound changes after an independent evidence
    gate has certified when this selected source batch was actually extracted.
    The canonical store will assign a distinct trusted local ``available_at``
    when it receives the result.
    """
    receipt_source_available_at = _as_utc(
        source_available_at,
        field_name="source receipt extracted_at",
    )
    rebound = LegacyStockDailyImportBatch(
        raw_payload=batch.raw_payload,
        bars=tuple(
            LegacyStockDailySourceBar(
                provider_symbol=bar.provider_symbol,
                canonical_id=bar.canonical_id,
                market=bar.market,
                frequency=bar.frequency,
                adjustment=bar.adjustment,
                event_at=bar.event_at,
                source_available_at=receipt_source_available_at,
                fields=bar.fields,
            )
            for bar in batch.bars
        ),
        calendar=batch.calendar,
        import_scope=batch.import_scope,
    )
    if rebound.content_sha256 != batch.content_sha256:
        raise AssertionError("rebinding source receipt availability changed raw source evidence")
    return rebound


def _require_source_columns(raw_row: Mapping[object, object]) -> None:
    for semantic, column in LEGACY_STOCK_DAILY_COLUMN_MAP.items():
        if column not in raw_row:
            raise LegacyStockDailyImportError(
                "LEGACY_STOCK_DAILY_REQUIRED_SEMANTIC_MISSING",
                detail=semantic,
            )


def _required_symbol(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_SYMBOL_INVALID")
    return value.strip()


def _parse_trading_date(value: object) -> date:
    if isinstance(value, datetime):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_EVENT_DATE_INVALID")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_EVENT_DATE_INVALID")
    normalized = value.strip()
    if not _ISO_DATE.fullmatch(normalized):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_EVENT_DATE_INVALID")
    try:
        return date.fromisoformat(normalized)
    except ValueError as exc:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_EVENT_DATE_INVALID") from exc


def _normalize_fields(raw_row: Mapping[object, object]) -> Mapping[str, int | float | str]:
    fields = {
        "open": _nonnegative_numeric(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["open"]], "open"),
        "high": _nonnegative_numeric(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["high"]], "high"),
        "low": _nonnegative_numeric(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["low"]], "low"),
        "close": _nonnegative_numeric(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["close"]], "close"),
        "volume": _volume(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["volume"]]),
        "change_pct": _numeric(raw_row[LEGACY_STOCK_DAILY_COLUMN_MAP["change_pct"]], "change_pct"),
    }
    return MappingProxyType(fields)


def _nonnegative_numeric(value: object, field_name: str) -> int | float | str:
    normalized = _numeric(value, field_name)
    if _as_decimal(normalized) < 0:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
    return normalized


def _numeric(value: object, field_name: str) -> int | float | str:
    try:
        normalized = normalize_numeric_field_value(value, field_name=field_name)
    except FieldQualityValueError as exc:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID") from exc
    if normalized is None or isinstance(normalized, bool):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
    if isinstance(normalized, int):
        if abs(normalized) > _MAX_SAFE_JSON_INTEGER:
            return str(normalized)
        return normalized
    if isinstance(normalized, float):
        if not math.isfinite(normalized):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
        return normalized
    if isinstance(normalized, str):
        try:
            decimal_value = Decimal(normalized)
        except (InvalidOperation, ValueError) as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID") from exc
        if not decimal_value.is_finite():
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
        return normalized
    raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")


def _volume(value: object) -> int:
    normalized = _numeric(value, "volume")
    decimal_value = _as_decimal(normalized)
    if (
        decimal_value < 0
        or decimal_value != decimal_value.to_integral_value()
        or decimal_value > _MAX_SAFE_JSON_INTEGER
    ):
        code = (
            "LEGACY_STOCK_DAILY_VOLUME_OUT_OF_RANGE"
            if decimal_value > _MAX_SAFE_JSON_INTEGER
            else "LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID"
        )
        raise LegacyStockDailyImportError(code)
    return int(decimal_value)


def _as_decimal(value: int | float | str) -> Decimal:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID") from exc
    if not decimal_value.is_finite():
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
    return decimal_value


def _raw_source_scalar(value: object) -> object:
    """Retain one selected source cell in a JSON-safe representation only."""
    if isinstance(value, datetime):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_EVENT_DATE_INVALID")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool) or value is None:
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_JSON_INTEGER:
            return str(value)
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
        return str(value)
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            scalar_value = item_method()
        except (TypeError, ValueError) as exc:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID") from exc
        if scalar_value is value:
            raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")
        return _raw_source_scalar(scalar_value)
    raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID")


def _validate_local_reread(
    *,
    batch: LegacyStockDailyImportBatch,
    input_event_keys: tuple[EventKey, ...],
    canonical_write: LegacyStockDailyCanonicalWrite,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    knowledge_cutoff: datetime,
    reread: object,
) -> None:
    if not isinstance(reread, LegacyStockDailyLocalReread):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_INVALID")
    if not _same_calendar_snapshot_and_event_map(batch.calendar, reread.calendar):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_CALENDAR_MISMATCH")
    if (
        reread.mode != "local_only"
        or reread.knowledge_cutoff != knowledge_cutoff
        or reread.visibility_anchor.visible_at != knowledge_cutoff
        or reread.calendar.visibility_anchor != reread.visibility_anchor
        or reread.visibility_anchor.max_visibility_sequence
        <= batch.calendar.visibility_anchor.max_visibility_sequence
        or canonical_write.published_at > knowledge_cutoff
        or any(
            not reread.visibility_anchor.permits(
                visible_at=receipt.visible_at,
                visibility_sequence=receipt.visibility_sequence,
            )
            for receipt in canonical_write.publication_receipts
        )
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_PIT_INVALID")
    if (
        reread.source_snapshot_ids != canonical_write.source_snapshot_ids
        or reread.observation_revision_ids != canonical_write.observation_revision_ids
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH")
    evidence = reread.input_event_keys + reread.accepted_event_keys
    if any(not batch.calendar.coverage_window.contains(key) for key in evidence):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_EVENT_OUT_OF_WINDOW")
    if (
        reread.input_event_keys != input_event_keys
        or reread.accepted_event_keys != input_event_keys
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_EVENT_KEYS_MISMATCH")
    if len(reread.bars) != len(batch.bars) or any(
        not _same_source_bar_and_canonical_bar(source_bar, canonical_bar)
        for source_bar, canonical_bar in zip(batch.bars, reread.bars, strict=True)
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_MISMATCH")
    binding_by_bar_key = {
        (binding.canonical_id, binding.event_at): binding
        for binding in canonical_write.bar_revision_bindings
    }
    if any(
        (binding := binding_by_bar_key.get((bar.canonical_id, bar.event_at))) is None
        or bar.observation_revision_id != binding.observation_revision_id
        or bar.source_snapshot_id != binding.source_snapshot_id
        for bar in reread.bars
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH")
    if any(
        bar.source_available_at != source_batch_receipt.extracted_at
        or bar.available_at != canonical_write.local_observation_available_at
        for bar in reread.bars
    ):
        raise LegacyStockDailyImportError("LEGACY_STOCK_DAILY_LOCAL_REREAD_AVAILABILITY_MISMATCH")


def _same_source_bar_and_canonical_bar(
    source_bar: LegacyStockDailySourceBar,
    canonical_bar: LegacyStockDailyBar,
) -> bool:
    """Compare durable bar semantics while excluding Store-owned local receipt time."""
    return (
        source_bar.provider_symbol == canonical_bar.provider_symbol
        and source_bar.canonical_id == canonical_bar.canonical_id
        and source_bar.market == canonical_bar.market
        and source_bar.frequency == canonical_bar.frequency
        and source_bar.adjustment == canonical_bar.adjustment
        and source_bar.event_at == canonical_bar.event_at
        and source_bar.source_available_at == canonical_bar.source_available_at
        and source_bar.fields == canonical_bar.fields
    )


def _same_calendar_snapshot_and_event_map(
    left: FrozenLegacyStockDailyCalendar,
    right: FrozenLegacyStockDailyCalendar,
) -> bool:
    """Compare immutable calendar semantics while allowing a later PIT anchor."""
    return (
        left.calendar_snapshot_id == right.calendar_snapshot_id
        and left.calendar_code == right.calendar_code
        and left.calendar_version == right.calendar_version
        and left.timezone_name == right.timezone_name
        and left.data_kind == right.data_kind
        and left.frequency == right.frequency
        and left.coverage_window == right.coverage_window
        and dict(left.event_key_by_trading_date) == dict(right.event_key_by_trading_date)
    )


def _require_json_numeric(value: object, *, field_name: str) -> int | float | str:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a JSON-safe numeric value")
    if isinstance(value, int):
        return value if abs(value) <= _MAX_SAFE_JSON_INTEGER else str(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise TypeError(f"{field_name} must be a JSON-safe numeric value") from exc
        if parsed.is_finite():
            return value
    raise TypeError(f"{field_name} must be a JSON-safe numeric value")


def _freeze_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError("JSON mapping keys must be non-empty strings")
            copied[key] = _freeze_json_value(item)
        return MappingProxyType(copied)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json_value(item) for item in value)
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value if abs(value) <= _MAX_SAFE_JSON_INTEGER else str(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise TypeError("JSON floats must be finite")
    raise TypeError("raw payload contains a non-JSON-safe value")


def _plain_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json_value(item) for item in value]
    return value


def _source_projection_descriptor() -> Mapping[str, object]:
    """Describe the module-owned logical projection independently of DB types."""
    return {
        "format": _SOURCE_SCHEMA_FORMAT,
        "table_name": LEGACY_STOCK_DAILY_TABLE,
        "source_columns": list(_SOURCE_COLUMNS),
        "semantic_column_map": dict(LEGACY_STOCK_DAILY_COLUMN_MAP),
    }


def _calendar_scope_descriptor(
    calendar: FrozenLegacyStockDailyCalendar,
) -> Mapping[str, object]:
    """Serialize every pre-read calendar fact that affects date interpretation."""
    return {
        "calendar_snapshot_id": calendar.calendar_snapshot_id,
        "calendar_code": calendar.calendar_code,
        "calendar_version": calendar.calendar_version,
        "timezone_name": calendar.timezone_name,
        "data_kind": calendar.data_kind,
        "frequency": calendar.frequency,
        "coverage_window": {
            "start_at": _utc_iso(calendar.coverage_window.start_at),
            "end_at": _utc_iso(calendar.coverage_window.end_at),
        },
        "visibility_anchor": {
            "visible_at": _utc_iso(calendar.visibility_anchor.visible_at),
            "max_visibility_sequence": calendar.visibility_anchor.max_visibility_sequence,
        },
        "event_key_by_trading_date": [
            {
                "trading_date": trading_date.isoformat(),
                "event_at": _utc_iso(event_key.event_at),
            }
            for trading_date, event_key in sorted(calendar.event_key_by_trading_date.items())
        ],
    }


def _utc_iso(value: datetime) -> str:
    return _as_utc(value, field_name="scope datetime").isoformat()


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            _plain_json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError("raw payload is not canonical JSON") from exc


def _require_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{field_name} must be non-blank text")
    return value.strip()


def _normalized_identifier_set(value: object, *, field_name: str) -> frozenset[str]:
    if not isinstance(value, (frozenset, set, tuple, list)):
        raise TypeError(f"{field_name} must be an identifier collection")
    normalized = frozenset(
        _require_text(item, field_name=field_name, maximum=255) for item in value
    )
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _as_utc(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(UTC)
