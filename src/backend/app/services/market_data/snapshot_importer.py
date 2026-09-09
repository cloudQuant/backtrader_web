"""Offline-only normalization boundary for audited AkShare full-market snapshots.

An AkShare broad spot response is not an exact request-time provider result.
This module intentionally has no ``fetch`` method, no HTTP dependency, and no
link to a source-policy route.  A scheduler or shadow collector may hand it a
previously captured row set plus frozen master-data identities; it returns
standard :class:`ProviderMarketObservation` values only after every row proves
one exact identity and one permitted time basis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from types import MappingProxyType
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.market_data.akshare_provider import (
    AkShareProviderError,
    AkShareSnapshotRowSchema,
    get_akshare_snapshot_row_schema,
)
from app.services.market_data.field_quality import (
    FieldQualityValueError,
    normalize_numeric_field_value,
)
from app.services.market_data.providers import ProviderMarketObservation

UTC = timezone.utc
_MAX_SNAPSHOT_ROWS = 50_000
SnapshotImportMode = Literal["schedule", "shadow"]
SnapshotTimeBasis = Literal["source_row", "collector_observed"]


class AkShareSnapshotImportError(ValueError):
    """Stable error emitted before a broad source row can become normalized data."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class FrozenSnapshotIdentity:
    """One immutable source-symbol-to-canonical-identity projection for a batch."""

    canonical_id: str
    asset_type: str
    provider_symbol: str
    market: str
    provider_market: str | None = None

    def __post_init__(self) -> None:
        """Reject partial identities before a source row has a chance to match one."""
        for field_name in ("canonical_id", "asset_type", "provider_symbol", "market"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"frozen snapshot identity {field_name} must not be blank")
            object.__setattr__(self, field_name, value.strip())
        if self.provider_market is not None:
            if not isinstance(self.provider_market, str) or not self.provider_market.strip():
                raise ValueError("frozen snapshot identity provider_market must not be blank")
            object.__setattr__(self, "provider_market", self.provider_market.strip())


@dataclass(frozen=True, slots=True)
class ImportedSnapshotObservation:
    """A standard observation paired with explicit identity and time provenance.

    ``observation.event_at`` and ``observation.available_at`` equal the source
    row timestamp for ``source_row`` records.  For the opt-in
    ``collector_observed`` basis they equal caller-supplied ``collected_at``;
    that value is not represented as an upstream provider event time.
    """

    identity: FrozenSnapshotIdentity
    observation: ProviderMarketObservation
    source_event_time: datetime | None
    time_basis: SnapshotTimeBasis

    def __post_init__(self) -> None:
        """Make source-time provenance impossible to omit or relabel."""
        if not isinstance(self.identity, FrozenSnapshotIdentity):
            raise TypeError("snapshot identity must be FrozenSnapshotIdentity")
        if not isinstance(self.observation, ProviderMarketObservation):
            raise TypeError("snapshot observation must be ProviderMarketObservation")
        if self.time_basis not in {"source_row", "collector_observed"}:
            raise ValueError("snapshot time_basis is invalid")
        if self.time_basis == "source_row":
            source_event_time = _require_aware_utc(
                self.source_event_time,
                field_name="source_event_time",
            )
            if (
                self.observation.event_at != source_event_time
                or self.observation.available_at != source_event_time
            ):
                raise ValueError("source-row observations must retain their source timestamp")
            object.__setattr__(self, "source_event_time", source_event_time)
        elif self.source_event_time is not None:
            raise ValueError("collector-observed records must not claim a provider event timestamp")
        elif self.observation.event_at != self.observation.available_at:
            raise ValueError("collector-observed records must retain one caller-supplied timestamp")

    def provenance_payload(self) -> Mapping[str, object]:
        """Return payload metadata a scheduler must preserve with its source receipt."""
        return MappingProxyType(
            {
                "canonical_id": self.identity.canonical_id,
                "asset_type": self.identity.asset_type,
                "provider_symbol": self.identity.provider_symbol,
                "market": self.identity.market,
                "provider_market": self.identity.provider_market,
                "source_event_time": (
                    self.source_event_time.isoformat()
                    if self.source_event_time is not None
                    else None
                ),
                "time_basis": self.time_basis,
                "collector_observed_at": (
                    self.observation.event_at.isoformat()
                    if self.time_basis == "collector_observed"
                    else None
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class SnapshotImportResult:
    """Normalized rows and deterministic per-row provenance for one offline batch."""

    asset_type: str
    mode: SnapshotImportMode
    imported: tuple[ImportedSnapshotObservation, ...]

    def __post_init__(self) -> None:
        """Prevent a batch from silently yielding two rows for one identity."""
        if self.mode not in {"schedule", "shadow"}:
            raise ValueError("snapshot import mode is invalid")
        if not isinstance(self.asset_type, str) or not self.asset_type.strip():
            raise ValueError("snapshot import asset_type must not be blank")
        imported = tuple(self.imported)
        if any(not isinstance(item, ImportedSnapshotObservation) for item in imported):
            raise TypeError("snapshot imports must contain ImportedSnapshotObservation values")
        canonical_ids = [item.identity.canonical_id for item in imported]
        if len(canonical_ids) != len(set(canonical_ids)):
            raise ValueError("snapshot import result cannot contain duplicate canonical identities")
        asset_type = self.asset_type.strip()
        if any(item.identity.asset_type != asset_type for item in imported):
            raise ValueError("snapshot import result identities must match its asset_type")
        object.__setattr__(self, "asset_type", asset_type)
        object.__setattr__(self, "imported", imported)

    @property
    def observations(self) -> tuple[ProviderMarketObservation, ...]:
        """Expose the standard provider-neutral objects consumed by the existing store."""
        return tuple(item.observation for item in self.imported)

    @property
    def provenance_rows(self) -> tuple[Mapping[str, object], ...]:
        """Expose immutable metadata required beside the raw captured row set."""
        return tuple(item.provenance_payload() for item in self.imported)


class AkShareSnapshotImporter:
    """Pure schedule/shadow row normalizer; it can never be used as a request adapter."""

    def __init__(self, *, mode: SnapshotImportMode) -> None:
        if mode not in {"schedule", "shadow"}:
            raise ValueError("snapshot importer mode must be schedule or shadow")
        self._mode = mode

    def import_rows(
        self,
        *,
        asset_type: str,
        rows: Sequence[Mapping[str, Any]],
        frozen_identities: Sequence[FrozenSnapshotIdentity],
        required_fields: frozenset[str],
        time_basis: SnapshotTimeBasis = "source_row",
        collected_at: datetime | None = None,
    ) -> SnapshotImportResult:
        """Normalize a previously collected wide response without any fetch or fallback.

        ``collector_observed`` is intentionally opt-in and valid only for
        schemas that explicitly allow it.  It requires a caller-provided,
        timezone-aware ``collected_at`` and is represented in provenance as
        ``source_event_time: null`` / ``time_basis: collector_observed``.
        The importer never reads a clock to manufacture source timing.
        """
        schema = _snapshot_schema(asset_type)
        validated_rows = _validated_rows(rows)
        identities_by_source_key = _frozen_identity_map(
            schema=schema,
            frozen_identities=frozen_identities,
        )
        normalized_required_fields = _required_fields(required_fields, schema=schema)
        if time_basis not in {"source_row", "collector_observed"}:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIME_BASIS_INVALID")
        if time_basis == "collector_observed":
            if not schema.collector_observed_allowed:
                raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_COLLECTOR_TIME_UNSUPPORTED")
            audited_collected_at = _require_aware_utc(collected_at, field_name="collected_at")
        else:
            if collected_at is not None:
                raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_COLLECTED_AT_UNEXPECTED")
            audited_collected_at = None

        imported: list[ImportedSnapshotObservation] = []
        seen_canonical_ids: set[str] = set()
        for row in validated_rows:
            provider_symbol = _resolve_row_identity(row, schema)
            provider_market = _resolve_row_source_market(row, schema)
            identity = identities_by_source_key.get((provider_market, provider_symbol))
            if identity is None:
                raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_UNMATCHED")
            if identity.canonical_id in seen_canonical_ids:
                raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_ROW_DUPLICATE")

            source_event_time = _source_event_time(row, schema)
            if time_basis == "source_row":
                if source_event_time is None:
                    raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_MISSING")
                event_at = source_event_time
            else:
                if source_event_time is not None:
                    raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIME_BASIS_CONFLICT")
                if audited_collected_at is None:  # Defensive; validated above.
                    raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_COLLECTED_AT_REQUIRED")
                event_at = audited_collected_at

            fields = _normalize_snapshot_fields(
                row,
                schema=schema,
                required_fields=normalized_required_fields,
            )
            observation = ProviderMarketObservation(
                event_at=event_at,
                available_at=event_at,
                fields=fields,
            )
            imported.append(
                ImportedSnapshotObservation(
                    identity=identity,
                    observation=observation,
                    source_event_time=source_event_time if time_basis == "source_row" else None,
                    time_basis=time_basis,
                )
            )
            seen_canonical_ids.add(identity.canonical_id)

        return SnapshotImportResult(
            asset_type=schema.asset_type,
            mode=self._mode,
            imported=tuple(imported),
        )


def _snapshot_schema(asset_type: str) -> AkShareSnapshotRowSchema:
    """Translate the provider schema error into the importer's stable boundary code."""
    try:
        return get_akshare_snapshot_row_schema(asset_type)
    except AkShareProviderError as exc:
        raise AkShareSnapshotImportError(exc.code) from exc


def _validated_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    """Bound the captured batch before any per-row parsing begins."""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_ROWS_INVALID")
    if len(rows) > _MAX_SNAPSHOT_ROWS:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_ROWS_TOO_LARGE")
    normalized_rows: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_ROWS_INVALID")
        normalized_rows.append(MappingProxyType(dict(row)))
    return tuple(normalized_rows)


def _frozen_identity_map(
    *,
    schema: AkShareSnapshotRowSchema,
    frozen_identities: Sequence[FrozenSnapshotIdentity],
) -> Mapping[tuple[str | None, str], FrozenSnapshotIdentity]:
    """Build a one-to-one exact source map; aliases and duplicate keys are unsafe."""
    if not isinstance(frozen_identities, Sequence) or isinstance(
        frozen_identities, (str, bytes, bytearray)
    ):
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_MAPPING_INVALID")
    identities = tuple(frozen_identities)
    if not identities:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_MAPPING_EMPTY")
    by_source_key: dict[tuple[str | None, str], FrozenSnapshotIdentity] = {}
    canonical_ids: set[str] = set()
    for identity in identities:
        if not isinstance(identity, FrozenSnapshotIdentity):
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_MAPPING_INVALID")
        if identity.asset_type != schema.asset_type:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_ASSET_TYPE_MISMATCH")
        if schema.source_market_columns:
            if identity.provider_market is None:
                raise AkShareSnapshotImportError(
                    "AKSHARE_SNAPSHOT_IDENTITY_PROVIDER_MARKET_MISSING"
                )
        elif identity.provider_market is not None:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_PROVIDER_MARKET_UNEXPECTED")
        source_key = (identity.provider_market, identity.provider_symbol)
        if source_key in by_source_key or identity.canonical_id in canonical_ids:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_AMBIGUOUS")
        by_source_key[source_key] = identity
        canonical_ids.add(identity.canonical_id)
    return MappingProxyType(by_source_key)


def _required_fields(
    required_fields: frozenset[str],
    *,
    schema: AkShareSnapshotRowSchema,
) -> frozenset[str]:
    """Keep required-field semantics as explicit as the provider request boundary."""
    if not isinstance(required_fields, frozenset) or not required_fields:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_REQUIRED_FIELDS_INVALID")
    normalized: set[str] = set()
    for field_name in required_fields:
        if not isinstance(field_name, str) or not field_name.strip():
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_REQUIRED_FIELDS_INVALID")
        normalized.add(field_name.strip())
    if len(normalized) != len(required_fields):
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_REQUIRED_FIELDS_INVALID")
    if not normalized.issubset(frozenset(schema.field_aliases.values())):
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_REQUIRED_FIELDS_UNSUPPORTED")
    return frozenset(normalized)


def _resolve_row_identity(row: Mapping[str, Any], schema: AkShareSnapshotRowSchema) -> str:
    """Require one exact returned source symbol, allowing redundant equal columns only."""
    values = _present_values(row, schema.identity_columns)
    if not values:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_MISSING")
    normalized_values: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_MISSING")
        normalized_values.add(value.strip())
    if len(normalized_values) != 1:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_IDENTITY_AMBIGUOUS")
    return next(iter(normalized_values))


def _resolve_row_source_market(
    row: Mapping[str, Any], schema: AkShareSnapshotRowSchema
) -> str | None:
    """Require an explicit raw source market for schemas whose symbol is not global."""
    if not schema.source_market_columns:
        return None
    values = _present_values(row, schema.source_market_columns)
    if not values:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_PROVIDER_MARKET_MISSING")
    normalized_values: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_PROVIDER_MARKET_MISSING")
        normalized_values.add(value.strip())
    if len(normalized_values) != 1:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_PROVIDER_MARKET_AMBIGUOUS")
    return next(iter(normalized_values))


def _source_event_time(
    row: Mapping[str, Any],
    schema: AkShareSnapshotRowSchema,
) -> datetime | None:
    """Parse a row-owned timestamp, never synthesizing one from the process clock."""
    values = _present_values(row, schema.timestamp_columns)
    if not values:
        return None
    parsed = tuple(_parse_source_timestamp(value, schema=schema) for value in values)
    if len(set(parsed)) != 1:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_AMBIGUOUS")
    return parsed[0]


def _present_values(row: Mapping[str, Any], columns: Sequence[str]) -> tuple[Any, ...]:
    """Return only source values explicitly present under an approved schema column."""
    return tuple(row[column] for column in columns if column in row)


def _parse_source_timestamp(value: Any, *, schema: AkShareSnapshotRowSchema) -> datetime:
    """Parse an explicit source time under the schema's declared source timezone."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        # A date-only bar stamp cannot prove when a broad snapshot was available.
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_INVALID")
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_MISSING")
        if "T" not in normalized and " " not in normalized:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_INVALID")
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_INVALID") from exc
    else:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMESTAMP_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(schema.source_timezone))
        except ZoneInfoNotFoundError as exc:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_TIMEZONE_INVALID") from exc
    return parsed.astimezone(UTC)


def _normalize_snapshot_fields(
    row: Mapping[str, Any],
    *,
    schema: AkShareSnapshotRowSchema,
    required_fields: frozenset[str],
) -> Mapping[str, Any]:
    """Map explicit source columns without turning identity/time columns into data fields."""
    excluded_columns = {
        *schema.identity_columns,
        *schema.source_market_columns,
        *schema.timestamp_columns,
    }
    fields: dict[str, Any] = {}
    for raw_name, raw_value in row.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_ROWS_INVALID")
        source_name = raw_name.strip()
        if source_name in excluded_columns:
            continue
        field_name = schema.field_aliases.get(source_name)
        if field_name is None:
            continue
        if field_name in fields:
            raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_FIELDS_AMBIGUOUS")
        fields[field_name] = _normalize_numeric_snapshot_value(
            raw_value,
            field_name=field_name,
        )
    missing = sorted(
        field_name
        for field_name in required_fields
        if field_name not in fields or fields[field_name] is None
    )
    if missing:
        raise AkShareSnapshotImportError(
            "AKSHARE_SNAPSHOT_REQUIRED_FIELDS_MISSING",
            detail=",".join(missing),
        )
    if not fields:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_FIELDS_EMPTY")
    return MappingProxyType(fields)


def _require_aware_utc(value: datetime | None, *, field_name: str) -> datetime:
    """Validate explicit audit time without providing any local-clock fallback."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AkShareSnapshotImportError("AKSHARE_SNAPSHOT_COLLECTED_AT_REQUIRED")
    return value.astimezone(UTC)


def _normalize_numeric_snapshot_value(
    value: Any,
    *,
    field_name: str,
) -> int | float | str | None:
    """Apply the shared typed policy while retaining the importer's stable error."""
    try:
        return normalize_numeric_field_value(value, field_name=field_name)
    except FieldQualityValueError as exc:
        raise AkShareSnapshotImportError(
            "AKSHARE_SNAPSHOT_FIELD_VALUE_INVALID",
            detail=field_name,
        ) from exc


__all__ = [
    "AkShareSnapshotImportError",
    "AkShareSnapshotImporter",
    "FrozenSnapshotIdentity",
    "ImportedSnapshotObservation",
    "SnapshotImportResult",
]
