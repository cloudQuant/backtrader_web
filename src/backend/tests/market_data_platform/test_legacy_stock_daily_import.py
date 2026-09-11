"""RED contracts for an auditable ``STOCK_ZH_A_HIST`` daily-bar importer.

The legacy warehouse is evidence input only. A successful migration must carry
an immutable, content-addressed source subset through the canonical writer and
prove the resulting facts through a separate ``local_only`` reread.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.services.market_data.coverage import EventKey, TimeWindow
from app.services.market_data.legacy_stock_daily_import import (
    LEGACY_STOCK_DAILY_COLUMN_MAP,
    LEGACY_STOCK_DAILY_PROVIDER_ID,
    LEGACY_STOCK_DAILY_ROUTE_ID,
    LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
    LEGACY_STOCK_DAILY_TABLE,
    FrozenLegacyStockDailyCalendar,
    FrozenLegacyStockDailyIdentity,
    LegacyStockDailyBar,
    LegacyStockDailyBarRevisionBinding,
    LegacyStockDailyCanonicalWrite,
    LegacyStockDailyCanonicalWritePermit,
    LegacyStockDailyImportAttestation,
    LegacyStockDailyImportBatch,
    LegacyStockDailyImporter,
    LegacyStockDailyImportError,
    LegacyStockDailyImportScope,
    LegacyStockDailyLocalReread,
    LegacyStockDailyPublicationReceipt,
    LegacyStockDailyReadScopeReceipt,
    LegacyStockDailySourceBar,
    LegacyStockDailySourceBatchReceipt,
)
from app.services.market_data.publication import MarketDataVisibilityAnchor

UTC = timezone.utc
_SQLITE_DATE_TYPE = "LEGACY_STOCK_DAILY_DATE"
_MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
_SOURCE_COLUMNS = (
    "symbol",
    "data_date",
    "开盘",
    "最高",
    "最低",
    "收盘",
    "成交量",
    "涨跌幅",
)

sqlite3.register_converter(
    _SQLITE_DATE_TYPE,
    lambda value: date.fromisoformat(value.decode("ascii")),
)


def _at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, tzinfo=UTC)


def _canonical_json_bytes(value: object) -> bytes:
    """Build the stable JSON bytes expected at the content-address boundary."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _plain_json(value: object) -> object:
    """Turn frozen test evidence into ordinary JSON containers for comparison."""
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _approved_attestation(**overrides: object) -> LegacyStockDailyImportAttestation:
    values: dict[str, object] = {
        "source_id": LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
        "source_revision": "stock_zh_a_hist:legacy-warehouse-v1",
        "adjustment": "qfq",
        "source_timezone": "Asia/Shanghai",
        "retrieved_at": _at(10, 8),
        "schema_version": "stock-zh-a-hist-v1",
    }
    values.update(overrides)
    return LegacyStockDailyImportAttestation(**values)


def _identity(
    *,
    provider_symbol: str = "000001",
    canonical_id: str = "instrument:stock:CN-SZSE:000001",
    market: str = "CN-SZSE",
    identity_revision: str = "identity-revision-cn-szse-000001-v1",
    instrument_metadata_version: str = "instrument-metadata-v1",
) -> FrozenLegacyStockDailyIdentity:
    return FrozenLegacyStockDailyIdentity(
        provider_symbol=provider_symbol,
        canonical_id=canonical_id,
        market=market,
        identity_revision=identity_revision,
        instrument_metadata_version=instrument_metadata_version,
    )


def _read_scope_receipt(**overrides: object) -> LegacyStockDailyReadScopeReceipt:
    values: dict[str, object] = {
        "source_registry_id": LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
        "provider_id": LEGACY_STOCK_DAILY_PROVIDER_ID,
        "route_id": LEGACY_STOCK_DAILY_ROUTE_ID,
        "authorization_receipt_id": "legacy-stock-daily-read-scope-v1",
        "source_schema_sha256": "a" * 64,
    }
    values.update(overrides)
    return LegacyStockDailyReadScopeReceipt(**values)


def _write_permit(**overrides: object) -> LegacyStockDailyCanonicalWritePermit:
    values: dict[str, object] = {
        "canonical_id": "instrument:stock:CN-SZSE:000001",
        "source_registry_id": LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
        "provider_id": LEGACY_STOCK_DAILY_PROVIDER_ID,
        "route_id": LEGACY_STOCK_DAILY_ROUTE_ID,
        "read_authorization_receipt_id": "legacy-stock-daily-read-scope-v1",
        "source_batch_sha256": "a" * 64,
        "import_scope_sha256": "b" * 64,
        "source_receipt_id": "legacy-stock-daily-source-receipt-v1",
        "write_authorization_descriptor_sha256": "b" * 64,
        "resolved_context_sha256": "c" * 64,
        "fetch_lease_key_sha256": "d" * 64,
        "fetch_lease_fence_token": 7,
    }
    values.update(overrides)
    return LegacyStockDailyCanonicalWritePermit(**values)


def _write_permits_for_batch(
    batch: LegacyStockDailyImportBatch,
    source_batch_receipt: LegacyStockDailySourceBatchReceipt,
    *,
    read_authorization_receipt_id: str | None = None,
) -> dict[str, LegacyStockDailyCanonicalWritePermit]:
    """Issue one test-only current write permit for every resolved target."""
    return {
        canonical_id: _write_permit(
            canonical_id=canonical_id,
            source_batch_sha256=source_batch_receipt.source_batch_sha256,
            import_scope_sha256=batch.import_scope.import_scope_sha256,
            source_receipt_id=source_batch_receipt.source_receipt_id,
            resolved_context_sha256=hashlib.sha256(
                f"legacy-stock-daily-context:{canonical_id}".encode()
            ).hexdigest(),
            fetch_lease_key_sha256=hashlib.sha256(
                f"legacy-stock-daily-lease:{canonical_id}".encode()
            ).hexdigest(),
            read_authorization_receipt_id=(
                read_authorization_receipt_id or source_batch_receipt.authorization_receipt_id
            ),
        )
        for canonical_id in sorted({bar.canonical_id for bar in batch.bars})
    }


def _sealed_test_write_permits(
    *canonical_ids: str,
) -> dict[str, LegacyStockDailyCanonicalWritePermit]:
    """Issue isolated target permits for canonical-write DTO invariant tests."""
    return {
        canonical_id: _write_permit(
            canonical_id=canonical_id,
            resolved_context_sha256=hashlib.sha256(
                f"legacy-stock-daily-context:{canonical_id}".encode()
            ).hexdigest(),
            fetch_lease_key_sha256=hashlib.sha256(
                f"legacy-stock-daily-lease:{canonical_id}".encode()
            ).hexdigest(),
        )
        for canonical_id in canonical_ids
    }


def _event_keys() -> tuple[EventKey, EventKey]:
    return EventKey(_at(7, 7)), EventKey(_at(8, 7))


def _calendar(**overrides: object) -> FrozenLegacyStockDailyCalendar:
    """Freeze a published/PIT calendar snapshot rather than derive a time from a date."""
    first_key, second_key = _event_keys()
    values: dict[str, object] = {
        "calendar_snapshot_id": "calendar-snapshot-cn-szse-2026-09-v1",
        "calendar_code": "CN-SZSE",
        "calendar_version": "2026.09",
        "timezone_name": "Asia/Shanghai",
        "data_kind": "bars",
        "frequency": "1d",
        "coverage_window": TimeWindow(start_at=_at(6, 16), end_at=_at(9, 16)),
        "visibility_anchor": MarketDataVisibilityAnchor(
            visible_at=_at(10, 8),
            max_visibility_sequence=42,
        ),
        "event_key_by_trading_date": {
            date(2026, 9, 7): first_key,
            date(2026, 9, 8): second_key,
        },
    }
    values.update(overrides)
    return FrozenLegacyStockDailyCalendar(**values)


def _calendar_at_anchor(
    calendar: FrozenLegacyStockDailyCalendar,
    *,
    visibility_anchor: MarketDataVisibilityAnchor,
) -> FrozenLegacyStockDailyCalendar:
    """Keep the exact date-to-event proof while moving to a postwrite PIT read."""
    return FrozenLegacyStockDailyCalendar(
        calendar_snapshot_id=calendar.calendar_snapshot_id,
        calendar_code=calendar.calendar_code,
        calendar_version=calendar.calendar_version,
        timezone_name=calendar.timezone_name,
        data_kind=calendar.data_kind,
        frequency=calendar.frequency,
        coverage_window=calendar.coverage_window,
        visibility_anchor=visibility_anchor,
        event_key_by_trading_date=dict(calendar.event_key_by_trading_date),
    )


def _rows(*, symbol: str = "000001") -> list[dict[str, object]]:
    """Source-shaped rows intentionally use a Python ``date`` from the DB driver."""
    return [
        {
            "symbol": symbol,
            "data_date": date(2026, 9, 7),
            "开盘": 10.0,
            "最高": 10.7,
            "最低": 9.8,
            "收盘": 10.5,
            "成交量": 123_400,
            "涨跌幅": 2.94,
        },
        {
            "symbol": symbol,
            "data_date": date(2026, 9, 8),
            "开盘": 10.5,
            "最高": 10.8,
            "最低": 10.1,
            "收盘": 10.2,
            "成交量": 98_700,
            "涨跌幅": -2.86,
        },
    ]


class _SqliteLegacyReader:
    """Read an isolated typed SQLite legacy table; never an application database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.calls: list[str] = []
        self.returned_rows: tuple[Mapping[str, object], ...] = ()

    async def read_rows(
        self,
        *,
        table_name: str,
        source_columns: tuple[str, ...],
        source_schema_sha256: str,
    ) -> tuple[Mapping[str, object], ...]:
        self.calls.append(table_name)
        assert source_columns == _SOURCE_COLUMNS
        assert source_schema_sha256 == "a" * 64
        projection = ", ".join(f'"{column}"' for column in source_columns)
        with sqlite3.connect(
            self.database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
        ) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f'SELECT {projection} FROM "{table_name}" ORDER BY data_date ASC, symbol ASC'
            ).fetchall()
        self.returned_rows = tuple(dict(row) for row in rows)
        return self.returned_rows


class _RowsLegacyReader:
    """Direct edge-case reader, used only for source-driver values and failures."""

    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.rows = tuple(dict(row) for row in rows)
        self.calls: list[str] = []

    async def read_rows(
        self,
        *,
        table_name: str,
        source_columns: tuple[str, ...],
        source_schema_sha256: str,
    ) -> tuple[Mapping[str, object], ...]:
        self.calls.append(table_name)
        assert source_columns == _SOURCE_COLUMNS
        assert source_schema_sha256 == "a" * 64
        return tuple(dict(row) for row in self.rows)


class _FailingLegacyReader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def read_rows(
        self,
        *,
        table_name: str,
        source_columns: tuple[str, ...],
        source_schema_sha256: str,
    ) -> tuple[Mapping[str, object], ...]:
        self.calls.append(table_name)
        assert source_columns == _SOURCE_COLUMNS
        assert source_schema_sha256 == "a" * 64
        raise RuntimeError("legacy driver disconnected")


class _RejectingLegacyEvidenceGate:
    """A real unverified legacy table must stop before a database row is read."""

    async def authorize_legacy_read(self, **_kwargs: object) -> object:
        raise RuntimeError("legacy table has no source receipts")

    async def certify_source_batch(self, **_kwargs: object) -> object:
        raise AssertionError("preflight rejection must prevent batch certification")

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("preflight rejection must prevent write authorization")


class _UnsealedLegacyEvidenceGate:
    """A preflight alone cannot certify the source rows returned by a table."""

    async def authorize_legacy_read(self, **_kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        return _read_scope_receipt()

    async def certify_source_batch(self, **_kwargs: object) -> object:
        raise RuntimeError("no immutable source-batch receipt")

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("unsealed source must prevent write authorization")


class _MismatchedLegacyEvidenceGate:
    """A receipt for a different byte sequence cannot certify this read result."""

    async def authorize_legacy_read(self, **_kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        return _read_scope_receipt()

    async def certify_source_batch(self, **_kwargs: object) -> LegacyStockDailySourceBatchReceipt:
        return LegacyStockDailySourceBatchReceipt(
            source_batch_sha256="b" * 64,
            source_registry_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID,
            route_id=LEGACY_STOCK_DAILY_ROUTE_ID,
            authorization_receipt_id="legacy-stock-daily-read-scope-v1",
            source_receipt_id="wrong-batch-receipt",
            source_schema_sha256="a" * 64,
            import_scope_sha256="c" * 64,
            extracted_at=_at(10, 8),
        )

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("mismatched source batch must prevent write authorization")


class _SchemaMismatchedLegacyEvidenceGate:
    """A raw receipt cannot claim a schema other than the pre-read manifest."""

    async def authorize_legacy_read(self, **_kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        return _read_scope_receipt()

    async def certify_source_batch(self, **kwargs: object) -> LegacyStockDailySourceBatchReceipt:
        batch = kwargs["batch"]
        import_scope = kwargs["import_scope"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        return LegacyStockDailySourceBatchReceipt(
            source_batch_sha256=batch.content_sha256,
            source_registry_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID,
            route_id=LEGACY_STOCK_DAILY_ROUTE_ID,
            authorization_receipt_id="legacy-stock-daily-read-scope-v1",
            source_receipt_id="wrong-schema-receipt",
            source_schema_sha256="b" * 64,
            import_scope_sha256=import_scope.import_scope_sha256,
            extracted_at=_at(10, 8),
        )

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("mismatched schema must prevent write authorization")


class _ReplayedScopeEvidenceGate:
    """Return a receipt sealed for a different derivation scope but the same rows."""

    def __init__(self, *, stale_import_scope_sha256: str) -> None:
        self.stale_import_scope_sha256 = stale_import_scope_sha256
        self.batch: LegacyStockDailyImportBatch | None = None

    async def authorize_legacy_read(self, **_kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        return _read_scope_receipt()

    async def certify_source_batch(self, **kwargs: object) -> LegacyStockDailySourceBatchReceipt:
        batch = kwargs["batch"]
        import_scope = kwargs["import_scope"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        self.batch = batch
        return LegacyStockDailySourceBatchReceipt(
            source_batch_sha256=batch.content_sha256,
            source_registry_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID,
            route_id=LEGACY_STOCK_DAILY_ROUTE_ID,
            authorization_receipt_id="legacy-stock-daily-read-scope-v1",
            source_receipt_id="replayed-scope-receipt",
            source_schema_sha256=import_scope.source_schema_sha256,
            import_scope_sha256=self.stale_import_scope_sha256,
            extracted_at=_at(10, 8),
        )

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("replayed scope must prevent write authorization")


class _InvalidReadScopeEvidenceGate:
    """A pre-read receipt for an unapproved route must stop before reader I/O."""

    async def authorize_legacy_read(self, **_kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        return _read_scope_receipt(provider_id="unexpected-provider")

    async def certify_source_batch(self, **_kwargs: object) -> object:
        raise AssertionError("invalid pre-read scope must stop before batch certification")

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("invalid pre-read scope must prevent write authorization")


class _AllowingLegacyEvidenceGate:
    """A test-only stand-in for the future sealed-source authorization gate."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def authorize_legacy_read(self, **kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        self.calls.append(kwargs)
        return _read_scope_receipt()

    async def certify_source_batch(self, **kwargs: object) -> LegacyStockDailySourceBatchReceipt:
        self.calls.append(kwargs)
        batch = kwargs["batch"]
        import_scope = kwargs["import_scope"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert batch.import_scope == import_scope
        return LegacyStockDailySourceBatchReceipt(
            source_batch_sha256=batch.content_sha256,
            source_registry_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID,
            route_id=LEGACY_STOCK_DAILY_ROUTE_ID,
            authorization_receipt_id=import_scope.read_scope_receipt.authorization_receipt_id,
            source_receipt_id="legacy-stock-daily-source-receipt-v1",
            source_schema_sha256=import_scope.source_schema_sha256,
            import_scope_sha256=import_scope.import_scope_sha256,
            extracted_at=_at(10, 8),
        )

    async def authorize_canonical_writes(
        self,
        **kwargs: object,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        self.calls.append(kwargs)
        batch = kwargs["batch"]
        source_batch_receipt = kwargs["source_batch_receipt"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt)
        return _write_permits_for_batch(
            batch,
            source_batch_receipt,
        )


class _SourceBatchAuthorizationReplayEvidenceGate:
    """A source receipt cannot reuse a different pre-read authorization decision."""

    async def authorize_legacy_read(self, **_kwargs: object) -> LegacyStockDailyReadScopeReceipt:
        return _read_scope_receipt(authorization_receipt_id="current-read-authorization")

    async def certify_source_batch(self, **kwargs: object) -> LegacyStockDailySourceBatchReceipt:
        batch = kwargs["batch"]
        import_scope = kwargs["import_scope"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert isinstance(import_scope, LegacyStockDailyImportScope)
        return LegacyStockDailySourceBatchReceipt(
            source_batch_sha256=batch.content_sha256,
            source_registry_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID,
            route_id=LEGACY_STOCK_DAILY_ROUTE_ID,
            authorization_receipt_id="stale-read-authorization",
            source_receipt_id="stale-authorization-source-receipt",
            source_schema_sha256=import_scope.source_schema_sha256,
            import_scope_sha256=import_scope.import_scope_sha256,
            extracted_at=_at(10, 8),
        )

    async def authorize_canonical_writes(self, **_kwargs: object) -> object:
        raise AssertionError("a replayed read authorization must prevent a write permit")


class _MismatchedCanonicalWritePermitEvidenceGate(_AllowingLegacyEvidenceGate):
    """A stale read authorization cannot be exchanged for a new write permit."""

    async def authorize_canonical_writes(
        self,
        **kwargs: object,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        self.calls.append(kwargs)
        batch = kwargs["batch"]
        source_batch_receipt = kwargs["source_batch_receipt"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt)
        return _write_permits_for_batch(
            batch,
            source_batch_receipt,
            read_authorization_receipt_id="stale-read-authorization",
        )


class _MismatchedCanonicalWriteSourceBindingEvidenceGate(_AllowingLegacyEvidenceGate):
    """A current target permit still cannot be replayed across sealed source evidence."""

    def __init__(self, *, permit_field: str, replacement: object) -> None:
        super().__init__()
        self.permit_field = permit_field
        self.replacement = replacement

    async def authorize_canonical_writes(
        self,
        **kwargs: object,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        self.calls.append(kwargs)
        batch = kwargs["batch"]
        source_batch_receipt = kwargs["source_batch_receipt"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt)
        permits = _write_permits_for_batch(batch, source_batch_receipt)
        return {
            canonical_id: replace(permit, **{self.permit_field: self.replacement})
            for canonical_id, permit in permits.items()
        }


class _MissingTargetWritePermitEvidenceGate(_AllowingLegacyEvidenceGate):
    """A multi-target raw batch may not write under only one target's lease."""

    async def authorize_canonical_writes(
        self,
        **kwargs: object,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        self.calls.append(kwargs)
        batch = kwargs["batch"]
        source_batch_receipt = kwargs["source_batch_receipt"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt)
        permits = _write_permits_for_batch(batch, source_batch_receipt)
        canonical_id = min(permits)
        return {canonical_id: permits[canonical_id]}


class _ReusedTargetWriteEvidenceGate(_AllowingLegacyEvidenceGate):
    """A target-named permit cannot reuse another target's context or lease."""

    def __init__(self, *, permit_field: str) -> None:
        super().__init__()
        self.permit_field = permit_field

    async def authorize_canonical_writes(
        self,
        **kwargs: object,
    ) -> Mapping[str, LegacyStockDailyCanonicalWritePermit]:
        self.calls.append(kwargs)
        batch = kwargs["batch"]
        source_batch_receipt = kwargs["source_batch_receipt"]
        assert isinstance(batch, LegacyStockDailyImportBatch)
        assert isinstance(source_batch_receipt, LegacyStockDailySourceBatchReceipt)
        permits = _write_permits_for_batch(batch, source_batch_receipt)
        first_target, second_target = sorted(permits)
        return {
            **permits,
            second_target: replace(
                permits[second_target],
                **{self.permit_field: getattr(permits[first_target], self.permit_field)},
            ),
        }


def _project_canonical_bar(
    bar: LegacyStockDailySourceBar,
    *,
    binding: LegacyStockDailyBarRevisionBinding,
    available_at: datetime,
) -> LegacyStockDailyBar:
    """Return a distinct fake canonical fact, never the in-memory input object."""
    assert bar.source_available_at is not None
    assert (binding.canonical_id, binding.event_at) == (bar.canonical_id, bar.event_at)
    return LegacyStockDailyBar(
        provider_symbol=bar.provider_symbol,
        canonical_id=bar.canonical_id,
        market=bar.market,
        frequency=bar.frequency,
        adjustment=bar.adjustment,
        event_at=bar.event_at,
        source_available_at=bar.source_available_at,
        available_at=available_at,
        observation_revision_id=binding.observation_revision_id,
        source_snapshot_id=binding.source_snapshot_id,
        fields=dict(bar.fields),
    )


class _CanonicalDailyBarWriter:
    """Capture batch writes and reconstruct a separate local-only proof result."""

    def __init__(
        self,
        *,
        write_error: BaseException | None = None,
        reread_error: BaseException | None = None,
        returned_calendar: FrozenLegacyStockDailyCalendar | None = None,
        returned_visibility_anchor: MarketDataVisibilityAnchor | None = None,
        returned_input_event_keys: tuple[EventKey, ...] | None = None,
        returned_accepted_event_keys: tuple[EventKey, ...] | None = None,
        returned_source_snapshot_ids: frozenset[str] | None = None,
        returned_observation_revision_ids: frozenset[str] | None = None,
        canonical_write: LegacyStockDailyCanonicalWrite | None = None,
        returned_local_observation_available_at: datetime | None = None,
        returned_bar_revision_ids: tuple[str, ...] | None = None,
    ) -> None:
        self.write_error = write_error
        self.reread_error = reread_error
        self.returned_calendar = returned_calendar
        self.returned_visibility_anchor = returned_visibility_anchor
        self.returned_input_event_keys = returned_input_event_keys
        self.returned_accepted_event_keys = returned_accepted_event_keys
        self.returned_source_snapshot_ids = returned_source_snapshot_ids
        self.returned_observation_revision_ids = returned_observation_revision_ids
        self.canonical_write = canonical_write
        self.returned_local_observation_available_at = returned_local_observation_available_at
        self.returned_bar_revision_ids = returned_bar_revision_ids
        self.write_calls: list[
            tuple[LegacyStockDailyImportBatch, LegacyStockDailyImportAttestation]
        ] = []
        self.source_batch_receipts: list[LegacyStockDailySourceBatchReceipt] = []
        self.write_permits: list[Mapping[str, LegacyStockDailyCanonicalWritePermit]] = []
        self.local_only_calls: list[dict[str, object]] = []
        self._canonical_projection: tuple[LegacyStockDailyBar, ...] = ()
        self.last_reread: LegacyStockDailyLocalReread | None = None

    async def write_daily_bars(
        self,
        *,
        batch: LegacyStockDailyImportBatch,
        attestation: LegacyStockDailyImportAttestation,
        source_batch_receipt: LegacyStockDailySourceBatchReceipt,
        write_permits: Mapping[str, LegacyStockDailyCanonicalWritePermit],
    ) -> LegacyStockDailyCanonicalWrite:
        self.write_calls.append((batch, attestation))
        self.source_batch_receipts.append(source_batch_receipt)
        self.write_permits.append(dict(write_permits))
        if self.write_error is not None:
            raise self.write_error
        source_snapshot_by_target = {
            canonical_id: f"source-snapshot-legacy-stock-daily-{index}"
            for index, canonical_id in enumerate(sorted(write_permits), start=1)
        }
        bindings = tuple(
            LegacyStockDailyBarRevisionBinding(
                canonical_id=bar.canonical_id,
                event_at=bar.event_at,
                observation_revision_id=f"observation-revision-{index}",
                source_snapshot_id=source_snapshot_by_target[bar.canonical_id],
            )
            for index, bar in enumerate(batch.bars, start=1)
        )
        observation_revision_ids = frozenset(
            binding.observation_revision_id for binding in bindings
        )
        canonical_write = self.canonical_write or LegacyStockDailyCanonicalWrite(
            source_snapshot_ids=frozenset(source_snapshot_by_target.values()),
            observation_revision_ids=observation_revision_ids,
            observation_revision_source_snapshot_ids={
                binding.observation_revision_id: binding.source_snapshot_id for binding in bindings
            },
            bar_revision_bindings=bindings,
            target_write_permits=dict(write_permits),
            source_batch_sha256=source_batch_receipt.source_batch_sha256,
            import_scope_sha256=source_batch_receipt.import_scope_sha256,
            source_receipt_id=source_batch_receipt.source_receipt_id,
            local_observation_available_at=_at(10, 9),
            published_at=_at(10, 9),
            publication_receipts=tuple(
                LegacyStockDailyPublicationReceipt(
                    publication_id=f"publication-legacy-stock-daily-{index}",
                    source_snapshot_id=source_snapshot_id,
                    visible_at=_at(10, 9),
                    visibility_sequence=42 + index,
                )
                for index, source_snapshot_id in enumerate(
                    sorted(source_snapshot_by_target.values()),
                    start=1,
                )
            ),
        )
        binding_by_bar_key = {
            (binding.canonical_id, binding.event_at): binding
            for binding in canonical_write.bar_revision_bindings
        }
        projection_bindings = (
            tuple(
                replace(binding, observation_revision_id=revision_id)
                for binding, revision_id in zip(
                    (binding_by_bar_key[(bar.canonical_id, bar.event_at)] for bar in batch.bars),
                    self.returned_bar_revision_ids,
                    strict=True,
                )
            )
            if self.returned_bar_revision_ids is not None
            else tuple(binding_by_bar_key[(bar.canonical_id, bar.event_at)] for bar in batch.bars)
        )
        self._canonical_projection = tuple(
            _project_canonical_bar(
                bar,
                binding=binding,
                available_at=self.returned_local_observation_available_at
                or canonical_write.local_observation_available_at,
            )
            for bar, binding in zip(batch.bars, projection_bindings, strict=True)
        )
        return canonical_write

    async def read_daily_bars_local_only(
        self,
        *,
        canonical_ids: frozenset[str],
        calendar: FrozenLegacyStockDailyCalendar,
        input_event_keys: tuple[EventKey, ...],
        canonical_write: LegacyStockDailyCanonicalWrite,
        knowledge_cutoff: datetime,
    ) -> LegacyStockDailyLocalReread:
        self.local_only_calls.append(
            {
                "canonical_ids": canonical_ids,
                "calendar": calendar,
                "input_event_keys": input_event_keys,
                "canonical_write": canonical_write,
                "knowledge_cutoff": knowledge_cutoff,
            }
        )
        if self.reread_error is not None:
            raise self.reread_error
        visibility_anchor = self.returned_visibility_anchor or MarketDataVisibilityAnchor(
            visible_at=knowledge_cutoff,
            max_visibility_sequence=(
                calendar.visibility_anchor.max_visibility_sequence
                + len(canonical_write.publication_receipts)
            ),
        )
        reread_calendar = self.returned_calendar or _calendar_at_anchor(
            calendar,
            visibility_anchor=visibility_anchor,
        )
        self.last_reread = LegacyStockDailyLocalReread(
            bars=self._canonical_projection,
            calendar=reread_calendar,
            input_event_keys=self.returned_input_event_keys or input_event_keys,
            accepted_event_keys=self.returned_accepted_event_keys or input_event_keys,
            knowledge_cutoff=knowledge_cutoff,
            visibility_anchor=visibility_anchor,
            mode="local_only",
            source_snapshot_ids=self.returned_source_snapshot_ids
            or canonical_write.source_snapshot_ids,
            observation_revision_ids=self.returned_observation_revision_ids
            or canonical_write.observation_revision_ids,
        )
        return self.last_reread


def _sqlite_reader(
    tmp_path: Path,
    *,
    rows: Sequence[Mapping[str, object]],
    columns: Sequence[str] = _SOURCE_COLUMNS,
) -> _SqliteLegacyReader:
    """Materialize a bounded observed source schema with a typed date column."""
    database_path = tmp_path / "legacy-stock-daily.sqlite3"
    supported_columns = {
        "symbol": "TEXT",
        "data_date": _SQLITE_DATE_TYPE,
        "开盘": "REAL",
        "最高": "REAL",
        "最低": "REAL",
        "收盘": "REAL",
        "成交量": "INTEGER",
        "涨跌幅": "REAL",
        "legacy_ingest_note": "TEXT",
    }
    assert set(columns) <= set(supported_columns)
    quoted_columns = ", ".join(f'"{column}" {supported_columns[column]}' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_columns = ", ".join(f'"{column}"' for column in columns)
    with sqlite3.connect(database_path, detect_types=sqlite3.PARSE_DECLTYPES) as connection:
        connection.execute(f'CREATE TABLE "{LEGACY_STOCK_DAILY_TABLE}" ({quoted_columns})')
        connection.executemany(
            f'INSERT INTO "{LEGACY_STOCK_DAILY_TABLE}" ({insert_columns}) VALUES ({placeholders})',
            [
                tuple(
                    value.isoformat()
                    if isinstance(value := row.get(column), date)
                    and not isinstance(value, datetime)
                    else value
                    for column in columns
                )
                for row in rows
            ],
        )
        connection.commit()
    return _SqliteLegacyReader(database_path)


def _importer(
    tmp_path: Path,
    *,
    rows: Sequence[Mapping[str, object]] | None = None,
    columns: Sequence[str] = _SOURCE_COLUMNS,
    reader: object | None = None,
    writer: _CanonicalDailyBarWriter | None = None,
    evidence_gate: object | None = None,
    clock=lambda: _at(10, 10),
) -> tuple[LegacyStockDailyImporter, object, _CanonicalDailyBarWriter]:
    resolved_reader = reader or _sqlite_reader(
        tmp_path,
        rows=_rows() if rows is None else rows,
        columns=columns,
    )
    resolved_writer = writer or _CanonicalDailyBarWriter()
    resolved_gate = evidence_gate or _AllowingLegacyEvidenceGate()
    return (
        LegacyStockDailyImporter(
            reader=resolved_reader,
            writer=resolved_writer,
            evidence_gate=resolved_gate,
            clock=clock,
        ),
        resolved_reader,
        resolved_writer,
    )


def _expected_raw_payload() -> dict[str, object]:
    return {
        "format": "legacy-stock-daily-source-batch-v2",
        "row_order": {
            "keys": ["event_at_utc", "canonical_id", "provider_symbol"],
            "version": 1,
        },
        "rows": [
            {
                "symbol": "000001",
                "data_date": "2026-09-07",
                "开盘": 10.0,
                "最高": 10.7,
                "最低": 9.8,
                "收盘": 10.5,
                "成交量": 123_400,
                "涨跌幅": 2.94,
            },
            {
                "symbol": "000001",
                "data_date": "2026-09-08",
                "开盘": 10.5,
                "最高": 10.8,
                "最低": 10.1,
                "收盘": 10.2,
                "成交量": 98_700,
                "涨跌幅": -2.86,
            },
        ],
        "source_columns": list(_SOURCE_COLUMNS),
        "table_name": LEGACY_STOCK_DAILY_TABLE,
    }


def test_legacy_stock_daily_import_contract_uses_one_allowlisted_table_and_static_mapping() -> None:
    assert LEGACY_STOCK_DAILY_TABLE == "STOCK_ZH_A_HIST"
    assert dict(LEGACY_STOCK_DAILY_COLUMN_MAP) == {
        "provider_symbol": "symbol",
        "event_date": "data_date",
        "open": "开盘",
        "high": "最高",
        "low": "最低",
        "close": "收盘",
        "volume": "成交量",
        "change_pct": "涨跌幅",
    }


def test_canonical_write_rejects_one_revision_for_multiple_bars() -> None:
    """Each canonical bar must retain its own immutable observation revision."""
    canonical_id = "instrument:stock:CN-SZSE:000001"
    first_event, second_event = _event_keys()
    with pytest.raises(ValueError, match="bar bindings"):
        LegacyStockDailyCanonicalWrite(
            source_snapshot_ids=frozenset({"source-snapshot-1"}),
            observation_revision_ids=frozenset({"observation-revision-1"}),
            observation_revision_source_snapshot_ids={
                "observation-revision-1": "source-snapshot-1",
            },
            bar_revision_bindings=(
                LegacyStockDailyBarRevisionBinding(
                    canonical_id=canonical_id,
                    event_at=first_event.event_at,
                    observation_revision_id="observation-revision-1",
                    source_snapshot_id="source-snapshot-1",
                ),
                LegacyStockDailyBarRevisionBinding(
                    canonical_id=canonical_id,
                    event_at=second_event.event_at,
                    observation_revision_id="observation-revision-1",
                    source_snapshot_id="source-snapshot-1",
                ),
            ),
            target_write_permits=_sealed_test_write_permits(canonical_id),
            source_batch_sha256="a" * 64,
            import_scope_sha256="b" * 64,
            source_receipt_id="legacy-stock-daily-source-receipt-v1",
            local_observation_available_at=_at(10, 9),
            published_at=_at(10, 9),
            publication_receipts=(
                LegacyStockDailyPublicationReceipt(
                    publication_id="publication-1",
                    source_snapshot_id="source-snapshot-1",
                    visible_at=_at(10, 9),
                    visibility_sequence=43,
                ),
            ),
        )


def test_canonical_write_rejects_publication_before_local_receipt() -> None:
    """Every written target must be published no earlier than its local receipt."""
    first_canonical_id = "instrument:stock:CN-SZSE:000001"
    second_canonical_id = "instrument:stock:CN-SSE:600000"
    first_event, second_event = _event_keys()
    with pytest.raises(ValueError, match="publication receipts"):
        LegacyStockDailyCanonicalWrite(
            source_snapshot_ids=frozenset({"source-snapshot-1", "source-snapshot-2"}),
            observation_revision_ids=frozenset(
                {"observation-revision-1", "observation-revision-2"}
            ),
            observation_revision_source_snapshot_ids={
                "observation-revision-1": "source-snapshot-1",
                "observation-revision-2": "source-snapshot-2",
            },
            bar_revision_bindings=(
                LegacyStockDailyBarRevisionBinding(
                    canonical_id=first_canonical_id,
                    event_at=first_event.event_at,
                    observation_revision_id="observation-revision-1",
                    source_snapshot_id="source-snapshot-1",
                ),
                LegacyStockDailyBarRevisionBinding(
                    canonical_id=second_canonical_id,
                    event_at=second_event.event_at,
                    observation_revision_id="observation-revision-2",
                    source_snapshot_id="source-snapshot-2",
                ),
            ),
            target_write_permits=_sealed_test_write_permits(
                first_canonical_id,
                second_canonical_id,
            ),
            source_batch_sha256="a" * 64,
            import_scope_sha256="b" * 64,
            source_receipt_id="legacy-stock-daily-source-receipt-v1",
            local_observation_available_at=_at(10, 9),
            published_at=_at(10, 9),
            publication_receipts=(
                LegacyStockDailyPublicationReceipt(
                    publication_id="publication-1",
                    source_snapshot_id="source-snapshot-1",
                    visible_at=_at(10, 8),
                    visibility_sequence=43,
                ),
                LegacyStockDailyPublicationReceipt(
                    publication_id="publication-2",
                    source_snapshot_id="source-snapshot-2",
                    visible_at=_at(10, 9),
                    visibility_sequence=44,
                ),
            ),
        )


def test_import_scope_hash_binds_the_read_authorization_receipt_identity() -> None:
    """The same table rows cannot migrate under a different pre-read authorization."""
    arguments = {
        "attestation": _approved_attestation(),
        "calendar": _calendar(),
        "frozen_identities": {"000001": _identity()},
    }
    first = LegacyStockDailyImportScope(
        **arguments,
        read_scope_receipt=_read_scope_receipt(authorization_receipt_id="read-authorization-a"),
    )
    second = LegacyStockDailyImportScope(
        **arguments,
        read_scope_receipt=_read_scope_receipt(authorization_receipt_id="read-authorization-b"),
    )

    assert first.import_scope_sha256 != second.import_scope_sha256


@pytest.mark.asyncio
async def test_unknown_table_or_invalid_attestation_cannot_open_any_io(tmp_path: Path) -> None:
    """Mutable migration inputs fail before legacy or canonical I/O begins."""
    importer, reader, writer = _importer(tmp_path)
    with pytest.raises(LegacyStockDailyImportError) as unknown_table:
        await importer.import_table(
            table_name="STOCK_ZH_A_HIST_2026",
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    with pytest.raises(LegacyStockDailyImportError) as invalid_attestation:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(adjustment="unadjusted"),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    assert unknown_table.value.code == "LEGACY_STOCK_DAILY_TABLE_UNSUPPORTED"
    assert invalid_attestation.value.code == "LEGACY_STOCK_DAILY_ATTESTATION_SEMANTICS_INVALID"
    assert isinstance(reader, _SqliteLegacyReader)
    assert reader.calls == []
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_unverified_legacy_source_cannot_open_table_or_canonical_writer(
    tmp_path: Path,
) -> None:
    """An attestation string cannot upgrade a mixed warehouse into AkShare facts."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_RejectingLegacyEvidenceGate(),
    )
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_PRECHECK_FAILED"
    assert reader.calls == []
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_unsealed_source_batch_cannot_reach_the_canonical_writer(tmp_path: Path) -> None:
    """A checked table scope still needs a receipt bound to the selected rows."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_UnsealedLegacyEvidenceGate(),
    )
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_source_receipt_for_different_raw_bytes_cannot_reach_canonical_writer(
    tmp_path: Path,
) -> None:
    """The evidence gate must bind the exact normalized raw payload hash."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_MismatchedLegacyEvidenceGate(),
    )
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_invalid_pre_read_route_or_schema_proof_cannot_open_legacy_io(tmp_path: Path) -> None:
    """The reader only opens after the gate returns an approved physical scope."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_InvalidReadScopeEvidenceGate(),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_PRECHECK_UNVERIFIED"
    assert reader.calls == []
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_source_receipt_for_a_different_physical_schema_cannot_reach_writer(
    tmp_path: Path,
) -> None:
    """The batch receipt must repeat the physical schema manifest authorized before read."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_SchemaMismatchedLegacyEvidenceGate(),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_source_batch_cannot_replay_a_different_read_authorization_receipt(
    tmp_path: Path,
) -> None:
    """The post-read source receipt must repeat the scope's authorization identity."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_SourceBatchAuthorizationReplayEvidenceGate(),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_stale_write_authorization_permit_cannot_reach_canonical_writer(
    tmp_path: Path,
) -> None:
    """Read authorization is not a substitute for a current pre-write decision."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_MismatchedCanonicalWritePermitEvidenceGate(),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_variant",
    [
        "attestation_revision",
        "calendar_anchor",
        "calendar_event_map",
        "identity_revision",
        "identity_metadata_version",
    ],
)
async def test_same_raw_rows_cannot_replay_a_receipt_from_a_different_import_scope(
    tmp_path: Path,
    scope_variant: str,
) -> None:
    """Raw bytes alone cannot authorize a different PIT interpretation of those bytes."""
    baseline_writer = _CanonicalDailyBarWriter()
    baseline_importer, _reader, _writer = _importer(tmp_path, writer=baseline_writer)
    await baseline_importer.import_table(
        table_name=LEGACY_STOCK_DAILY_TABLE,
        attestation=_approved_attestation(),
        calendar=_calendar(),
        frozen_identities={"000001": _identity()},
        dry_run=False,
    )
    baseline_batch = baseline_writer.write_calls[0][0]

    attestation = _approved_attestation()
    calendar = _calendar()
    identity = _identity()
    if scope_variant == "attestation_revision":
        attestation = _approved_attestation(source_revision="stock_zh_a_hist:legacy-warehouse-v2")
    elif scope_variant == "calendar_anchor":
        calendar = _calendar(
            visibility_anchor=MarketDataVisibilityAnchor(
                visible_at=_at(10, 8),
                max_visibility_sequence=41,
            )
        )
    elif scope_variant == "calendar_event_map":
        calendar = _calendar(
            event_key_by_trading_date={
                date(2026, 9, 7): EventKey(_at(7, 8)),
                date(2026, 9, 8): EventKey(_at(8, 8)),
            }
        )
    elif scope_variant == "identity_revision":
        identity = _identity(identity_revision="identity-revision-cn-szse-000001-v2")
    elif scope_variant == "identity_metadata_version":
        identity = _identity(instrument_metadata_version="instrument-metadata-v2")
    else:
        raise AssertionError(f"unhandled scope variant: {scope_variant}")

    replay_gate = _ReplayedScopeEvidenceGate(
        stale_import_scope_sha256=baseline_batch.import_scope.import_scope_sha256,
    )
    writer = _CanonicalDailyBarWriter()
    importer, _reader, _writer = _importer(
        tmp_path,
        reader=_RowsLegacyReader(_rows()),
        writer=writer,
        evidence_gate=replay_gate,
    )
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=attestation,
            calendar=calendar,
            frozen_identities={"000001": identity},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_BATCH_UNVERIFIED"
    assert replay_gate.batch is not None
    assert replay_gate.batch.content_sha256 == baseline_batch.content_sha256
    assert replay_gate.batch.import_scope.import_scope_sha256 != (
        baseline_batch.import_scope.import_scope_sha256
    )
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_non_bars_or_non_daily_calendar_cannot_open_legacy_io(tmp_path: Path) -> None:
    """A date map from another calendar grid cannot certify stock daily rows."""
    importer, reader, writer = _importer(tmp_path)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(data_kind="reference_series"),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    assert rejected.value.code == "LEGACY_STOCK_DAILY_CALENDAR_SEMANTICS_INVALID"
    assert isinstance(reader, _SqliteLegacyReader)
    assert reader.calls == []
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_value",
    [
        datetime(2026, 9, 7, 0, 0, tzinfo=UTC),
        "2026-09-07T00:00:00",
        "2026/09/07",
    ],
)
async def test_only_python_date_or_strict_iso_date_text_can_name_a_legacy_trading_day(
    tmp_path: Path,
    invalid_value: object,
) -> None:
    """A datetime never becomes a daily EventKey label by truncation."""
    rows = _rows()
    rows[0]["data_date"] = invalid_value
    direct_reader = _RowsLegacyReader(rows)
    importer, _reader, writer = _importer(tmp_path, reader=direct_reader)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    assert rejected.value.code == "LEGACY_STOCK_DAILY_EVENT_DATE_INVALID"
    assert direct_reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("permit_field", "replacement"),
    [
        ("source_batch_sha256", "f" * 64),
        ("import_scope_sha256", "e" * 64),
        ("source_receipt_id", "replayed-source-receipt"),
    ],
)
async def test_write_permit_cannot_replay_another_sealed_source_scope(
    tmp_path: Path,
    permit_field: str,
    replacement: object,
) -> None:
    """Current route authorization cannot be detached from raw batch/scope/receipt evidence."""
    reader = _RowsLegacyReader(_rows())
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_MismatchedCanonicalWriteSourceBindingEvidenceGate(
            permit_field=permit_field,
            replacement=replacement,
        ),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_multi_target_batch_requires_one_current_write_permit_per_target(
    tmp_path: Path,
) -> None:
    """A single target's context and lease cannot authorize another target's rows."""
    rows = (*_rows(symbol="000001"), *_rows(symbol="000002"))
    reader = _RowsLegacyReader(rows)
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_MissingTargetWritePermitEvidenceGate(),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={
                "000001": _identity(),
                "000002": _identity(
                    provider_symbol="000002",
                    canonical_id="instrument:stock:CN-SZSE:000002",
                    identity_revision="identity-revision-cn-szse-000002-v1",
                ),
            },
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("permit_field", ("resolved_context_sha256", "fetch_lease_key_sha256"))
async def test_multi_target_permit_cannot_reuse_a_sibling_context_or_lease(
    tmp_path: Path,
    permit_field: str,
) -> None:
    """A target label alone cannot turn another target's context/lease into its own."""
    rows = (*_rows(symbol="000001"), *_rows(symbol="000002"))
    reader = _RowsLegacyReader(rows)
    writer = _CanonicalDailyBarWriter()
    importer = LegacyStockDailyImporter(
        reader=reader,
        writer=writer,
        evidence_gate=_ReusedTargetWriteEvidenceGate(permit_field=permit_field),
    )

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={
                "000001": _identity(),
                "000002": _identity(
                    provider_symbol="000002",
                    canonical_id="instrument:stock:CN-SZSE:000002",
                    identity_revision="identity-revision-cn-szse-000002-v1",
                ),
            },
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_CANONICAL_WRITE_AUTHORIZATION_UNVERIFIED"
    assert reader.calls == [LEGACY_STOCK_DAILY_TABLE]
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_typed_legacy_dates_write_an_immutable_content_addressed_batch_then_independently_reread(
    tmp_path: Path,
) -> None:
    """Writer input includes only reviewed source evidence, bars, and calendar proof."""
    rows = _rows()
    rows[0]["legacy_ingest_note"] = "must not enter source receipt"
    calendar = _calendar()
    attestation = _approved_attestation()
    importer, reader, writer = _importer(
        tmp_path,
        rows=rows,
        columns=(*_SOURCE_COLUMNS, "legacy_ingest_note"),
    )
    report = await importer.import_table(
        table_name=LEGACY_STOCK_DAILY_TABLE,
        attestation=attestation,
        calendar=calendar,
        frozen_identities={"000001": _identity()},
        dry_run=False,
    )
    assert isinstance(reader, _SqliteLegacyReader)
    assert isinstance(reader.returned_rows[0]["data_date"], date)
    assert not isinstance(reader.returned_rows[0]["data_date"], datetime)
    assert len(writer.write_calls) == 1
    batch, written_attestation = writer.write_calls[0]
    assert written_attestation == attestation
    assert batch.calendar == calendar
    assert batch.import_scope.attestation == attestation
    assert batch.import_scope.source_schema_sha256 == "a" * 64
    assert [bar.event_at for bar in batch.bars] == [key.event_at for key in _event_keys()]
    assert [bar.source_available_at for bar in batch.bars] == [_at(10, 8), _at(10, 8)]
    assert _plain_json(batch.raw_payload) == _expected_raw_payload()
    assert (
        batch.content_sha256
        == hashlib.sha256(_canonical_json_bytes(_expected_raw_payload())).hexdigest()
    )
    assert (
        json.loads(_canonical_json_bytes(_plain_json(batch.raw_payload))) == _expected_raw_payload()
    )
    raw_rows = batch.raw_payload["rows"]
    assert isinstance(raw_rows, tuple)
    assert all(isinstance(row, Mapping) for row in raw_rows)
    assert all(set(row) == set(_SOURCE_COLUMNS) for row in raw_rows)
    with pytest.raises(TypeError):
        batch.raw_payload["forged"] = "must fail"  # type: ignore[index]
    with pytest.raises(TypeError):
        raw_rows[0]["收盘"] = 0.0  # type: ignore[index]
    assert writer.source_batch_receipts == [
        LegacyStockDailySourceBatchReceipt(
            source_batch_sha256=batch.content_sha256,
            source_registry_id=LEGACY_STOCK_DAILY_SOURCE_REGISTRY_ID,
            provider_id=LEGACY_STOCK_DAILY_PROVIDER_ID,
            route_id=LEGACY_STOCK_DAILY_ROUTE_ID,
            authorization_receipt_id="legacy-stock-daily-read-scope-v1",
            source_receipt_id="legacy-stock-daily-source-receipt-v1",
            source_schema_sha256="a" * 64,
            import_scope_sha256=batch.import_scope.import_scope_sha256,
            extracted_at=_at(10, 8),
        )
    ]
    assert len(writer.local_only_calls) == 1
    local_only_call = writer.local_only_calls[0]
    assert local_only_call["canonical_ids"] == frozenset({"instrument:stock:CN-SZSE:000001"})
    assert local_only_call["calendar"] == calendar
    assert local_only_call["input_event_keys"] == _event_keys()
    assert local_only_call["knowledge_cutoff"] == _at(10, 10)
    assert isinstance(local_only_call["canonical_write"], LegacyStockDailyCanonicalWrite)
    assert writer.last_reread is not None
    assert report.local_only_bars == writer.last_reread.bars
    assert report.local_only_bars is not batch.bars
    assert [bar.source_available_at for bar in report.local_only_bars] == [_at(10, 8), _at(10, 8)]
    assert [bar.available_at for bar in report.local_only_bars] == [_at(10, 9), _at(10, 9)]
    assert report.calendar_snapshot_id == calendar.calendar_snapshot_id
    assert report.source_batch_sha256 == batch.content_sha256
    assert report.import_scope_sha256 == batch.import_scope.import_scope_sha256
    assert report.input_event_keys == _event_keys()
    assert report.accepted_event_keys == _event_keys()


@pytest.mark.asyncio
@pytest.mark.parametrize("retrieved_at", [_at(10, 7), _at(10, 11)])
async def test_caller_declared_retrieval_time_cannot_become_source_or_local_availability_time(
    tmp_path: Path,
    retrieved_at: datetime,
) -> None:
    """A caller timestamp cannot overwrite source extraction or trusted local receipt time."""
    writer = _CanonicalDailyBarWriter()
    importer, _reader, _writer = _importer(tmp_path, writer=writer)
    report = await importer.import_table(
        table_name=LEGACY_STOCK_DAILY_TABLE,
        attestation=_approved_attestation(retrieved_at=retrieved_at),
        calendar=_calendar(),
        frozen_identities={"000001": _identity()},
        dry_run=False,
    )

    batch = writer.write_calls[0][0]
    assert [bar.source_available_at for bar in batch.bars] == [_at(10, 8), _at(10, 8)]
    assert [bar.source_available_at for bar in batch.bars] != [retrieved_at, retrieved_at]
    assert [bar.available_at for bar in report.local_only_bars] == [_at(10, 9), _at(10, 9)]
    assert [bar.available_at for bar in report.local_only_bars] != [retrieved_at, retrieved_at]


@pytest.mark.asyncio
async def test_local_reread_rejects_source_extraction_as_the_store_owned_availability_time(
    tmp_path: Path,
) -> None:
    """A concrete Store adapter must report its trusted local receipt time, not source time."""
    writer = _CanonicalDailyBarWriter(
        returned_local_observation_available_at=_at(10, 8),
    )
    importer, _reader, _writer = _importer(tmp_path, writer=writer)

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_LOCAL_REREAD_AVAILABILITY_MISMATCH"
    assert len(writer.write_calls) == 1
    assert len(writer.local_only_calls) == 1


@pytest.mark.asyncio
async def test_local_reread_rejects_swapped_per_bar_revision_evidence(tmp_path: Path) -> None:
    """Aggregate revision IDs cannot certify bars whose individual evidence was swapped."""
    writer = _CanonicalDailyBarWriter(
        returned_bar_revision_ids=("observation-revision-2", "observation-revision-1"),
    )
    importer, _reader, _writer = _importer(tmp_path, writer=writer)

    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
    assert len(writer.write_calls) == 1
    assert len(writer.local_only_calls) == 1


@pytest.mark.asyncio
async def test_same_legacy_row_set_has_one_deterministic_source_batch_order_and_hash(
    tmp_path: Path,
) -> None:
    """A reader's incidental row order cannot change the signed source batch."""
    forward_writer = _CanonicalDailyBarWriter()
    reverse_writer = _CanonicalDailyBarWriter()
    forward_importer, _forward_reader, _ = _importer(
        tmp_path,
        reader=_RowsLegacyReader(_rows()),
        writer=forward_writer,
    )
    reverse_importer, _reverse_reader, _ = _importer(
        tmp_path,
        reader=_RowsLegacyReader(tuple(reversed(_rows()))),
        writer=reverse_writer,
    )
    arguments = {
        "table_name": LEGACY_STOCK_DAILY_TABLE,
        "attestation": _approved_attestation(),
        "calendar": _calendar(),
        "frozen_identities": {"000001": _identity()},
        "dry_run": False,
    }

    forward_report = await forward_importer.import_table(**arguments)
    reverse_report = await reverse_importer.import_table(**arguments)

    forward_batch = forward_writer.write_calls[0][0]
    reverse_batch = reverse_writer.write_calls[0][0]
    assert forward_batch.bars == reverse_batch.bars
    assert forward_batch.raw_payload == reverse_batch.raw_payload
    assert forward_report.source_batch_sha256 == reverse_report.source_batch_sha256


@pytest.mark.asyncio
async def test_import_scope_is_stable_for_identity_mapping_order_and_descriptive_retrieval_time(
    tmp_path: Path,
) -> None:
    """Only derivation semantics, never mapping insertion order or caller metadata, affect scope."""
    rows = (*_rows(symbol="000001"), *_rows(symbol="000002"))
    first_identity = _identity()
    second_identity = _identity(
        provider_symbol="000002",
        canonical_id="instrument:stock:CN-SZSE:000002",
        identity_revision="identity-revision-cn-szse-000002-v1",
    )
    forward_writer = _CanonicalDailyBarWriter()
    reverse_writer = _CanonicalDailyBarWriter()
    forward_importer, _forward_reader, _ = _importer(
        tmp_path,
        reader=_RowsLegacyReader(rows),
        writer=forward_writer,
    )
    reverse_importer, _reverse_reader, _ = _importer(
        tmp_path,
        reader=_RowsLegacyReader(tuple(reversed(rows))),
        writer=reverse_writer,
    )

    await forward_importer.import_table(
        table_name=LEGACY_STOCK_DAILY_TABLE,
        attestation=_approved_attestation(retrieved_at=_at(10, 7)),
        calendar=_calendar(),
        frozen_identities={"000001": first_identity, "000002": second_identity},
        dry_run=False,
    )
    await reverse_importer.import_table(
        table_name=LEGACY_STOCK_DAILY_TABLE,
        attestation=_approved_attestation(retrieved_at=_at(10, 11)),
        calendar=_calendar(),
        frozen_identities={"000002": second_identity, "000001": first_identity},
        dry_run=False,
    )

    forward_batch = forward_writer.write_calls[0][0]
    reverse_batch = reverse_writer.write_calls[0][0]
    assert forward_batch.content_sha256 == reverse_batch.content_sha256
    assert forward_batch.import_scope.import_scope_sha256 == (
        reverse_batch.import_scope.import_scope_sha256
    )
    assert [bar.source_available_at for bar in forward_batch.bars] == [_at(10, 8)] * 4
    assert [bar.source_available_at for bar in reverse_batch.bars] == [_at(10, 8)] * 4
    expected_targets = {
        "instrument:stock:CN-SZSE:000001",
        "instrument:stock:CN-SZSE:000002",
    }
    assert set(forward_writer.write_permits[0]) == expected_targets
    assert set(reverse_writer.write_permits[0]) == expected_targets
    assert forward_writer.local_only_calls
    forward_write = forward_writer.local_only_calls[0]["canonical_write"]
    assert isinstance(forward_write, LegacyStockDailyCanonicalWrite)
    assert set(forward_write.target_write_permits) == expected_targets
    assert len(forward_write.source_snapshot_ids) == len(expected_targets)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returned_input", "returned_accepted", "expected_code"),
    [
        (_event_keys()[:1], None, "LEGACY_STOCK_DAILY_LOCAL_REREAD_EVENT_KEYS_MISMATCH"),
        (None, _event_keys()[:1], "LEGACY_STOCK_DAILY_LOCAL_REREAD_EVENT_KEYS_MISMATCH"),
        (
            None,
            (*_event_keys(), EventKey(_at(6, 17))),
            "LEGACY_STOCK_DAILY_LOCAL_REREAD_EVENT_KEYS_MISMATCH",
        ),
        (
            None,
            (*_event_keys(), EventKey(_at(9, 16))),
            "LEGACY_STOCK_DAILY_LOCAL_REREAD_EVENT_OUT_OF_WINDOW",
        ),
    ],
)
async def test_local_reread_requires_exact_input_and_accepted_event_key_evidence(
    tmp_path: Path,
    returned_input: tuple[EventKey, ...] | None,
    returned_accepted: tuple[EventKey, ...] | None,
    expected_code: str,
) -> None:
    """Partial, broadened, or out-of-window local evidence cannot certify an import."""
    writer = _CanonicalDailyBarWriter(
        returned_input_event_keys=returned_input,
        returned_accepted_event_keys=returned_accepted,
    )
    importer, _reader, _writer = _importer(tmp_path, writer=writer)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    assert rejected.value.code == expected_code
    assert len(writer.write_calls) == 1
    assert len(writer.local_only_calls) == 1


@pytest.mark.asyncio
async def test_local_reread_must_use_a_fresh_postwrite_visibility_anchor(tmp_path: Path) -> None:
    """A write cannot be certified by rereading through its prewrite PIT anchor."""
    calendar = _calendar()
    writer = _CanonicalDailyBarWriter(
        returned_calendar=calendar,
        returned_visibility_anchor=calendar.visibility_anchor,
    )
    importer, _reader, _writer = _importer(tmp_path, writer=writer)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=calendar,
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_LOCAL_REREAD_PIT_INVALID"
    assert len(writer.write_calls) == 1
    assert len(writer.local_only_calls) == 1


@pytest.mark.asyncio
async def test_newer_anchor_still_must_include_this_writes_publication_receipt(
    tmp_path: Path,
) -> None:
    """An intervening publication sequence does not prove this batch is visible."""
    import_scope = LegacyStockDailyImportScope(
        attestation=_approved_attestation(),
        calendar=_calendar(),
        frozen_identities={"000001": _identity()},
        read_scope_receipt=_read_scope_receipt(),
    )
    source_batch_sha256 = hashlib.sha256(_canonical_json_bytes(_expected_raw_payload())).hexdigest()
    canonical_write = LegacyStockDailyCanonicalWrite(
        source_snapshot_ids=frozenset({"source-snapshot-legacy-stock-daily-v1"}),
        observation_revision_ids=frozenset({"observation-revision-1", "observation-revision-2"}),
        observation_revision_source_snapshot_ids={
            "observation-revision-1": "source-snapshot-legacy-stock-daily-v1",
            "observation-revision-2": "source-snapshot-legacy-stock-daily-v1",
        },
        bar_revision_bindings=(
            LegacyStockDailyBarRevisionBinding(
                canonical_id="instrument:stock:CN-SZSE:000001",
                event_at=_event_keys()[0].event_at,
                observation_revision_id="observation-revision-1",
                source_snapshot_id="source-snapshot-legacy-stock-daily-v1",
            ),
            LegacyStockDailyBarRevisionBinding(
                canonical_id="instrument:stock:CN-SZSE:000001",
                event_at=_event_keys()[1].event_at,
                observation_revision_id="observation-revision-2",
                source_snapshot_id="source-snapshot-legacy-stock-daily-v1",
            ),
        ),
        target_write_permits={
            "instrument:stock:CN-SZSE:000001": _write_permit(
                source_batch_sha256=source_batch_sha256,
                import_scope_sha256=import_scope.import_scope_sha256,
                source_receipt_id="legacy-stock-daily-source-receipt-v1",
                resolved_context_sha256=hashlib.sha256(
                    b"legacy-stock-daily-context:instrument:stock:CN-SZSE:000001"
                ).hexdigest(),
                fetch_lease_key_sha256=hashlib.sha256(
                    b"legacy-stock-daily-lease:instrument:stock:CN-SZSE:000001"
                ).hexdigest(),
            )
        },
        source_batch_sha256=source_batch_sha256,
        import_scope_sha256=import_scope.import_scope_sha256,
        source_receipt_id="legacy-stock-daily-source-receipt-v1",
        local_observation_available_at=_at(10, 9),
        published_at=_at(10, 9),
        publication_receipts=(
            LegacyStockDailyPublicationReceipt(
                publication_id="publication-this-write",
                source_snapshot_id="source-snapshot-legacy-stock-daily-v1",
                visible_at=_at(10, 9),
                visibility_sequence=100,
            ),
        ),
    )
    writer = _CanonicalDailyBarWriter(
        canonical_write=canonical_write,
        returned_visibility_anchor=MarketDataVisibilityAnchor(
            visible_at=_at(10, 10),
            max_visibility_sequence=43,
        ),
    )
    importer, _reader, _writer = _importer(tmp_path, writer=writer)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_LOCAL_REREAD_PIT_INVALID"
    assert len(writer.write_calls) == 1
    assert len(writer.local_only_calls) == 1


@pytest.mark.asyncio
async def test_local_reread_must_prove_its_facts_are_from_this_canonical_write(
    tmp_path: Path,
) -> None:
    """A local reread of some other source snapshot cannot certify this import."""
    writer = _CanonicalDailyBarWriter(
        returned_source_snapshot_ids=frozenset({"unrelated-source-snapshot"}),
    )
    importer, _reader, _writer = _importer(tmp_path, writer=writer)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )

    assert rejected.value.code == "LEGACY_STOCK_DAILY_LOCAL_REREAD_WRITE_MISMATCH"
    assert len(writer.write_calls) == 1
    assert len(writer.local_only_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "expected_code"),
    [
        ("reader", "LEGACY_STOCK_DAILY_LEGACY_READ_FAILED"),
        ("writer", "LEGACY_STOCK_DAILY_CANONICAL_WRITE_FAILED"),
        ("reread", "LEGACY_STOCK_DAILY_LOCAL_REREAD_FAILED"),
    ],
)
async def test_reader_writer_and_reread_failures_are_closed_and_stable(
    tmp_path: Path,
    stage: str,
    expected_code: str,
) -> None:
    """Infrastructure faults never become an inferred partial import report."""
    writer = _CanonicalDailyBarWriter(
        write_error=RuntimeError("canonical write unavailable") if stage == "writer" else None,
        reread_error=RuntimeError("local read unavailable") if stage == "reread" else None,
    )
    reader: object = _FailingLegacyReader() if stage == "reader" else _RowsLegacyReader(_rows())
    importer, _reader, _writer = _importer(tmp_path, reader=reader, writer=writer)
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    assert rejected.value.code == expected_code
    assert (len(writer.write_calls), len(writer.local_only_calls)) == {
        "reader": (0, 0),
        "writer": (1, 0),
        "reread": (1, 1),
    }[stage]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda row: row.__setitem__("开盘", float("nan")),
            "LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID",
        ),
        (
            lambda row: row.__setitem__("最高", float("inf")),
            "LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID",
        ),
        (lambda row: row.__setitem__("收盘", True), "LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID"),
        (lambda row: row.__setitem__("成交量", 12.5), "LEGACY_STOCK_DAILY_FIELD_VALUE_INVALID"),
        (
            lambda row: row.__setitem__("成交量", _MAX_SAFE_JSON_INTEGER + 1),
            "LEGACY_STOCK_DAILY_VOLUME_OUT_OF_RANGE",
        ),
        (lambda row: row.__setitem__("最低", 11.0), "LEGACY_STOCK_DAILY_OHLC_INVALID"),
    ],
)
async def test_empty_or_invalid_legacy_rows_fail_closed_before_any_canonical_write(
    tmp_path: Path,
    mutate,
    expected_code: str,
) -> None:
    """Unsafe source cells cannot enter a JSON receipt or canonical bar fact."""
    rows = _rows()
    mutate(rows[0])
    importer, _reader, writer = _importer(tmp_path, reader=_RowsLegacyReader(rows))
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=False,
        )
    assert rejected.value.code == expected_code
    assert writer.write_calls == []
    assert writer.local_only_calls == []


@pytest.mark.asyncio
async def test_empty_legacy_result_is_never_a_successful_dry_run_or_import(tmp_path: Path) -> None:
    """No source rows means no evidence a dry-run can certify."""
    importer, _reader, writer = _importer(tmp_path, reader=_RowsLegacyReader(()))
    with pytest.raises(LegacyStockDailyImportError) as rejected:
        await importer.import_table(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            attestation=_approved_attestation(),
            calendar=_calendar(),
            frozen_identities={"000001": _identity()},
            dry_run=True,
        )
    assert rejected.value.code == "LEGACY_STOCK_DAILY_SOURCE_EMPTY"
    assert writer.write_calls == []
    assert writer.local_only_calls == []
