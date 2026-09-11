"""Reviewed, fixed-projection MySQL reader for legacy A-share daily rows.

``STOCK_ZH_A_HIST`` is a mixed-provenance historical warehouse.  This module
only establishes a narrow source-read boundary for a later, explicitly
authorized import command.  It does not read environment configuration,
register a provider route, write canonical data, or satisfy the existing
fixture-only :class:`LegacyStockDailyReader` protocol.

The caller must inject a MySQL source engine and a reviewed physical-projection
digest.  Every production-shaped read opens one read-only repeatable-read
snapshot, verifies a fixed InnoDB base-table manifest before and after the data
projection, and rolls the snapshot back.  Data values are always bound query
parameters; the only interpolated identifier is a validated schema name.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Protocol

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError

# v2 adds the base-table/storage-engine contract to the attested digest.
_SCHEMA_FORMAT = "legacy-stock-daily-mysql-projection-schema-v2"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MYSQL_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_STOCK_SYMBOL = re.compile(r"^[0-9]{6}$")
_MAX_SYMBOLS_PER_READ = 100
_MAX_WINDOW_DAYS = 31
_MAX_ROWS_PER_READ = 5_000

# This is intentionally duplicated rather than imported from the fixture-only
# importer.  A production source reader must not gain its authority, SQLite
# session coupling, or ``UNVERIFIED_COMPATIBILITY`` behavior through that
# harness.  A future production gate will bind both independently reviewed
# contracts before it can adapt rows into an import batch.
LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE = "STOCK_ZH_A_HIST"
LEGACY_STOCK_DAILY_MYSQL_SOURCE_COLUMNS = (
    "symbol",
    "data_date",
    "开盘",
    "最高",
    "最低",
    "收盘",
    "成交量",
    "涨跌幅",
)
_SOURCE_COLUMNS = LEGACY_STOCK_DAILY_MYSQL_SOURCE_COLUMNS

_SET_REPEATABLE_READ_SQL = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
_START_READ_ONLY_SNAPSHOT_SQL = "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY"
_TABLE_QUERY = text(
    """
    SELECT
        TABLE_TYPE AS table_type,
        ENGINE AS storage_engine
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = :source_schema
      AND TABLE_NAME = :table_name
    """
)
_SCHEMA_QUERY = text(
    """
    SELECT
        COLUMN_NAME AS column_name,
        ORDINAL_POSITION AS ordinal_position,
        COLUMN_TYPE AS column_type,
        IS_NULLABLE AS is_nullable,
        COLUMN_KEY AS column_key,
        COLUMN_DEFAULT AS column_default,
        EXTRA AS extra,
        COLLATION_NAME AS collation_name,
        CHARACTER_SET_NAME AS character_set_name
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = :source_schema
      AND TABLE_NAME = :table_name
      AND COLUMN_NAME IN :source_columns
    ORDER BY ORDINAL_POSITION ASC
    """
).bindparams(bindparam("source_columns", expanding=True))


class LegacyStockDailyMySQLSourceRepositoryError(ValueError):
    """Fail-closed source-read rejection before a canonical import can begin."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


class _AsyncSourceConnection(Protocol):
    """The narrow async connection surface used by this source reader."""

    async def execute(self, statement: Any, parameters: Mapping[str, object] | None = None) -> Any:
        """Execute one parameterized SQLAlchemy statement."""

    async def exec_driver_sql(self, statement: str) -> Any:
        """Execute one fixed transaction-control statement."""

    async def rollback(self) -> None:
        """Discard every read-only transaction before releasing the connection."""


class _AsyncSourceEngine(Protocol):
    """An injected engine; no module-level engine or URL factory is permitted."""

    dialect: Any

    def connect(self) -> AbstractAsyncContextManager[_AsyncSourceConnection]:
        """Open a caller-owned source connection."""


@dataclass(frozen=True, slots=True)
class LegacyStockDailyMySQLSourceColumn:
    """One reviewed physical source column in MySQL's information schema."""

    ordinal_position: int
    name: str
    column_type: str
    is_nullable: bool
    column_key: str
    column_default: str | None
    extra: str
    collation_name: str | None
    character_set_name: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.ordinal_position, int) or self.ordinal_position < 1:
            raise ValueError("ordinal_position must be a positive integer")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("source column name must be non-empty")
        for field_name in ("column_type", "column_key", "extra"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
        if not isinstance(self.is_nullable, bool):
            raise TypeError("is_nullable must be a bool")
        for field_name in ("column_default", "collation_name", "character_set_name"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")

    def descriptor(self) -> dict[str, object]:
        """Return the canonical fragment included in the reviewed schema digest."""
        return {
            "character_set_name": self.character_set_name,
            "collation_name": self.collation_name,
            "column_default": self.column_default,
            "column_key": self.column_key,
            "column_type": self.column_type,
            "extra": self.extra,
            "is_nullable": self.is_nullable,
            "name": self.name,
            "ordinal_position": self.ordinal_position,
        }


@dataclass(frozen=True, slots=True)
class LegacyStockDailyMySQLSourceSchema:
    """The exact approved eight-column source projection in one MySQL schema."""

    source_schema: str
    table_name: str
    table_type: str
    storage_engine: str
    source_columns: tuple[str, ...]
    columns: tuple[LegacyStockDailyMySQLSourceColumn, ...]
    schema_sha256: str

    def __post_init__(self) -> None:
        _require_source_schema(self.source_schema)
        if self.table_name != LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE:
            raise ValueError("legacy source schema table is unsupported")
        if self.table_type != "BASE TABLE" or self.storage_engine != "INNODB":
            raise ValueError("legacy source schema storage is unsupported")
        if self.source_columns != _SOURCE_COLUMNS:
            raise ValueError("legacy source schema projection is unsupported")
        if len(self.columns) != len(_SOURCE_COLUMNS):
            raise ValueError("legacy source schema column count is invalid")
        if tuple(column.name for column in self.columns) != _SOURCE_COLUMNS:
            raise ValueError("legacy source schema column order is invalid")
        _require_digest(self.schema_sha256, field_name="schema_sha256")
        expected = _schema_digest(
            source_schema=self.source_schema,
            table_name=self.table_name,
            table_type=self.table_type,
            storage_engine=self.storage_engine,
            source_columns=self.source_columns,
            columns=self.columns,
        )
        if self.schema_sha256 != expected:
            raise ValueError("legacy source schema digest does not match the projection")


@dataclass(frozen=True, slots=True)
class LegacyStockDailyMySQLReadBatch:
    """Rows and source manifest selected in one read-only MySQL snapshot."""

    source_schema: LegacyStockDailyMySQLSourceSchema
    symbols: tuple[str, ...]
    start_date: date
    end_date: date
    rows: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_schema, LegacyStockDailyMySQLSourceSchema):
            raise TypeError("source_schema must be a LegacyStockDailyMySQLSourceSchema")
        normalized_symbols = _normalize_symbols(self.symbols)
        _validate_date_window(start_date=self.start_date, end_date=self.end_date)
        rows = tuple(_fixed_projection_row(row) for row in self.rows)
        object.__setattr__(self, "symbols", normalized_symbols)
        object.__setattr__(self, "rows", rows)


class LegacyStockDailyMySQLSourceRepository:
    """Read a pre-approved legacy table only through an injected MySQL engine.

    The class intentionally has no factory, configuration lookup, route
    registration, scheduler hook, or canonical-store collaborator.  Creating
    it does not open a connection.  A separate audited control plane must
    provide the approved digest and call :meth:`read_projection` explicitly.
    """

    def __init__(
        self,
        source_engine: _AsyncSourceEngine,
        *,
        source_schema: str,
        approved_schema_sha256: str,
    ) -> None:
        _require_mysql_source_engine(source_engine)
        _require_source_schema(source_schema)
        _require_digest(approved_schema_sha256, field_name="approved_schema_sha256")
        self._source_engine = source_engine
        self._source_schema = source_schema
        self._approved_schema_sha256 = approved_schema_sha256

    @property
    def source_schema(self) -> str:
        """Return the fixed reviewed source schema name."""
        return self._source_schema

    @property
    def approved_schema_sha256(self) -> str:
        """Return the immutable physical-projection approval digest."""
        return self._approved_schema_sha256

    async def read_projection(
        self,
        *,
        symbols: Sequence[str],
        start_date: date,
        end_date: date,
        source_schema_sha256: str,
    ) -> LegacyStockDailyMySQLReadBatch:
        """Read fixed rows only after checking the scope's reviewed manifest.

        ``source_schema_sha256`` is supplied by a later authorization/read
        receipt.  It must exactly equal the constructor's reviewed value before
        any source connection is opened, then the physical table is checked
        both before and after reading rows within one snapshot.
        """
        normalized_symbols = _normalize_symbols(symbols)
        _validate_date_window(start_date=start_date, end_date=end_date)
        _require_digest(source_schema_sha256, field_name="source_schema_sha256")
        if source_schema_sha256 != self._approved_schema_sha256:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_APPROVAL_MISMATCH"
            )

        try:
            async with self._source_engine.connect() as connection:
                return await _read_projection_in_snapshot(
                    connection=connection,
                    source_schema=self._source_schema,
                    approved_schema_sha256=self._approved_schema_sha256,
                    symbols=normalized_symbols,
                    start_date=start_date,
                    end_date=end_date,
                )
        except LegacyStockDailyMySQLSourceRepositoryError:
            raise
        except SQLAlchemyError as exc:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_CONNECTION_UNAVAILABLE"
            ) from exc


async def inspect_legacy_stock_daily_mysql_source_schema(
    source_engine: _AsyncSourceEngine,
    *,
    source_schema: str,
) -> LegacyStockDailyMySQLSourceSchema:
    """Return a candidate MySQL schema digest from an injected read-only snapshot.

    This helper is descriptive only.  Its return value is not authorization to
    import a source and is deliberately separate from the constructor that
    requires an already reviewed digest.
    """
    _require_mysql_source_engine(source_engine)
    _require_source_schema(source_schema)
    try:
        async with source_engine.connect() as connection:
            return await _inspect_schema_in_snapshot(
                connection=connection,
                source_schema=source_schema,
            )
    except LegacyStockDailyMySQLSourceRepositoryError:
        raise
    except SQLAlchemyError as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_CONNECTION_UNAVAILABLE"
        ) from exc


async def _read_projection_in_snapshot(
    *,
    connection: _AsyncSourceConnection,
    source_schema: str,
    approved_schema_sha256: str,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
) -> LegacyStockDailyMySQLReadBatch:
    """Verify the manifest, read fixed rows, and recheck it before rollback."""
    try:
        await _begin_read_only_snapshot(connection)
        schema_before = await _inspect_schema_on_connection(
            connection=connection,
            source_schema=source_schema,
        )
        if schema_before.schema_sha256 != approved_schema_sha256:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_APPROVAL_MISMATCH"
            )
        result = await connection.execute(
            _projection_query(source_schema),
            {
                "symbols": symbols,
                "start_date": start_date,
                "end_date": end_date,
                "row_limit": _MAX_ROWS_PER_READ + 1,
            },
        )
        source_rows = tuple(result.mappings().all())
        if len(source_rows) > _MAX_ROWS_PER_READ:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_ROW_LIMIT_EXCEEDED"
            )
        rows = tuple(_fixed_projection_row(row) for row in source_rows)
        schema_after = await _inspect_schema_on_connection(
            connection=connection,
            source_schema=source_schema,
        )
        if schema_after.schema_sha256 != approved_schema_sha256:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_CHANGED_DURING_READ"
            )
        return LegacyStockDailyMySQLReadBatch(
            source_schema=schema_after,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
        )
    except LegacyStockDailyMySQLSourceRepositoryError:
        raise
    except (KeyError, TypeError, SQLAlchemyError) as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_READ_FAILED"
        ) from exc
    finally:
        await _rollback_snapshot(connection)


async def _inspect_schema_in_snapshot(
    *,
    connection: _AsyncSourceConnection,
    source_schema: str,
) -> LegacyStockDailyMySQLSourceSchema:
    """Inspect one candidate schema from an otherwise disposable snapshot."""
    try:
        await _begin_read_only_snapshot(connection)
        return await _inspect_schema_on_connection(
            connection=connection,
            source_schema=source_schema,
        )
    finally:
        await _rollback_snapshot(connection)


async def _begin_read_only_snapshot(connection: _AsyncSourceConnection) -> None:
    """Start the required MySQL repeatable-read, read-only snapshot."""
    try:
        await connection.exec_driver_sql(_SET_REPEATABLE_READ_SQL)
        await connection.exec_driver_sql(_START_READ_ONLY_SNAPSHOT_SQL)
    except SQLAlchemyError as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SNAPSHOT_FAILED"
        ) from exc


async def _rollback_snapshot(connection: _AsyncSourceConnection) -> None:
    """Always discard the snapshot; a source reader must never commit work."""
    try:
        await connection.rollback()
    except SQLAlchemyError as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SNAPSHOT_CLEANUP_FAILED"
        ) from exc


async def _inspect_schema_on_connection(
    *,
    connection: _AsyncSourceConnection,
    source_schema: str,
) -> LegacyStockDailyMySQLSourceSchema:
    """Build the fixed projection manifest using bound information-schema filters."""
    try:
        table_result = await connection.execute(
            _TABLE_QUERY,
            {
                "source_schema": source_schema,
                "table_name": LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
            },
        )
        table_rows = tuple(table_result.mappings().all())
    except SQLAlchemyError as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_UNAVAILABLE"
        ) from exc
    table_type, storage_engine = _table_metadata_from_rows(table_rows)
    try:
        column_result = await connection.execute(
            _SCHEMA_QUERY,
            {
                "source_schema": source_schema,
                "table_name": LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
                "source_columns": _SOURCE_COLUMNS,
            },
        )
        column_rows = tuple(column_result.mappings().all())
    except SQLAlchemyError as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_UNAVAILABLE"
        ) from exc
    return _schema_from_rows(
        source_schema=source_schema,
        table_type=table_type,
        storage_engine=storage_engine,
        rows=column_rows,
    )


def _projection_query(source_schema: str):
    """Return the only data query allowed by this reader.

    ``source_schema`` has already passed the strict MySQL identifier validator;
    table and column names are implementation constants.  Values remain bound
    parameters, including the expandable symbol list.
    """
    quoted_schema = _quote_mysql_identifier(source_schema)
    return text(
        "\n".join(
            (
                "SELECT",
                "    `symbol` AS `symbol`,",
                "    `data_date` AS `data_date`,",
                "    `开盘` AS `开盘`,",
                "    `最高` AS `最高`,",
                "    `最低` AS `最低`,",
                "    `收盘` AS `收盘`,",
                "    `成交量` AS `成交量`,",
                "    `涨跌幅` AS `涨跌幅`",
                f"FROM {quoted_schema}.`{LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE}`",
                "WHERE `symbol` IN :symbols",
                "  AND `data_date` >= :start_date",
                "  AND `data_date` <= :end_date",
                "ORDER BY `data_date` ASC, `symbol` ASC",
                "LIMIT :row_limit",
            )
        )
    ).bindparams(bindparam("symbols", expanding=True))


def _schema_from_rows(
    *,
    source_schema: str,
    table_type: str,
    storage_engine: str,
    rows: Sequence[Mapping[str, object]],
) -> LegacyStockDailyMySQLSourceSchema:
    """Validate exactly one physical definition for each fixed source column."""
    by_name: dict[str, LegacyStockDailyMySQLSourceColumn] = {}
    for row in rows:
        try:
            column = LegacyStockDailyMySQLSourceColumn(
                ordinal_position=_required_positive_int(
                    row.get("ordinal_position"), field_name="ordinal_position"
                ),
                name=_required_column_name(row.get("column_name")),
                column_type=_normalized_required_text(
                    row.get("column_type"), field_name="column_type"
                ),
                is_nullable=_mysql_nullable(row.get("is_nullable")),
                column_key=_optional_metadata_text(row.get("column_key"), field_name="column_key")
                or "",
                column_default=_optional_metadata_text(
                    row.get("column_default"), field_name="column_default"
                ),
                extra=_optional_metadata_text(row.get("extra"), field_name="extra") or "",
                collation_name=_optional_metadata_text(
                    row.get("collation_name"), field_name="collation_name"
                ),
                character_set_name=_optional_metadata_text(
                    row.get("character_set_name"), field_name="character_set_name"
                ),
            )
        except (TypeError, ValueError) as exc:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
            ) from exc
        if column.name not in _SOURCE_COLUMNS or column.name in by_name:
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
            )
        by_name[column.name] = column
    if set(by_name) != set(_SOURCE_COLUMNS):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
        )
    columns = tuple(by_name[name] for name in _SOURCE_COLUMNS)
    return LegacyStockDailyMySQLSourceSchema(
        source_schema=source_schema,
        table_name=LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
        table_type=table_type,
        storage_engine=storage_engine,
        source_columns=_SOURCE_COLUMNS,
        columns=columns,
        schema_sha256=_schema_digest(
            source_schema=source_schema,
            table_name=LEGACY_STOCK_DAILY_MYSQL_SOURCE_TABLE,
            table_type=table_type,
            storage_engine=storage_engine,
            source_columns=_SOURCE_COLUMNS,
            columns=columns,
        ),
    )


def _table_metadata_from_rows(rows: Sequence[Mapping[str, object]]) -> tuple[str, str]:
    """Require the one InnoDB base table for which snapshot semantics apply."""
    if len(rows) != 1 or not isinstance(rows[0], Mapping):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
        )
    try:
        table_type = _normalized_table_property(rows[0].get("table_type"), field_name="table_type")
        storage_engine = _normalized_table_property(
            rows[0].get("storage_engine"), field_name="storage_engine"
        )
    except (TypeError, ValueError) as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
        ) from exc
    if table_type != "BASE TABLE" or storage_engine != "INNODB":
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_STORAGE_UNSUPPORTED"
        )
    return table_type, storage_engine


def _fixed_projection_row(row: Mapping[str, object]) -> Mapping[str, object]:
    """Retain only the reviewed projection and fail closed on a malformed row."""
    if not isinstance(row, Mapping):
        raise TypeError("legacy source result row must be a mapping")
    try:
        return MappingProxyType({column: row[column] for column in _SOURCE_COLUMNS})
    except KeyError as exc:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_ROW_INVALID"
        ) from exc


def _schema_digest(
    *,
    source_schema: str,
    table_name: str,
    table_type: str,
    storage_engine: str,
    source_columns: tuple[str, ...],
    columns: tuple[LegacyStockDailyMySQLSourceColumn, ...],
) -> str:
    payload = {
        "columns": [column.descriptor() for column in columns],
        "format": _SCHEMA_FORMAT,
        "source_columns": list(source_columns),
        "source_schema": source_schema,
        "storage_engine": storage_engine,
        "table_name": table_name,
        "table_type": table_type,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _normalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Accept a bounded, deterministic list of A-share source symbols."""
    if isinstance(symbols, str) or not isinstance(symbols, Sequence):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID"
        )
    normalized: list[str] = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not _STOCK_SYMBOL.fullmatch(symbol):
            raise LegacyStockDailyMySQLSourceRepositoryError(
                "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID"
            )
        normalized.append(symbol)
    unique_symbols = tuple(sorted(set(normalized)))
    if not unique_symbols or len(unique_symbols) > _MAX_SYMBOLS_PER_READ:
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID"
        )
    return unique_symbols


def _validate_date_window(*, start_date: date, end_date: date) -> None:
    """Reject invalid or timestamp-like source windows before opening MySQL."""
    if (
        isinstance(start_date, datetime)
        or isinstance(end_date, datetime)
        or not isinstance(start_date, date)
        or not isinstance(end_date, date)
        or start_date > end_date
        or (end_date - start_date).days + 1 > _MAX_WINDOW_DAYS
    ):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_QUERY_INPUT_INVALID"
        )


def _require_mysql_source_engine(source_engine: object) -> None:
    """Require an injected MySQL-capable engine before it can open a connection."""
    dialect = getattr(source_engine, "dialect", None)
    if getattr(dialect, "name", None) != "mysql" or not callable(
        getattr(source_engine, "connect", None)
    ):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_ENGINE_UNSUPPORTED"
        )


def _require_source_schema(source_schema: object) -> None:
    if not isinstance(source_schema, str) or not _MYSQL_IDENTIFIER.fullmatch(source_schema):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            "LEGACY_STOCK_DAILY_MYSQL_SOURCE_SCHEMA_INVALID"
        )


def _require_digest(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LegacyStockDailyMySQLSourceRepositoryError(
            f"LEGACY_STOCK_DAILY_MYSQL_SOURCE_{field_name.upper()}_INVALID"
        )


def _quote_mysql_identifier(identifier: str) -> str:
    """Quote a schema identifier already restricted to MySQL identifier syntax."""
    _require_source_schema(identifier)
    return f"`{identifier}`"


def _required_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _required_column_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("column_name must be non-empty text")
    return value


def _normalized_required_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _optional_metadata_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text or None")
    return value


def _normalized_table_property(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return " ".join(value.upper().split())


def _mysql_nullable(value: object) -> bool:
    if not isinstance(value, str):
        raise TypeError("is_nullable must be text")
    normalized = value.strip().upper()
    if normalized == "YES":
        return True
    if normalized == "NO":
        return False
    raise ValueError("is_nullable must be YES or NO")
