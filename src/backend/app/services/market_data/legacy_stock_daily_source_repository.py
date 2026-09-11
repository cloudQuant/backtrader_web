"""Fixed-projection, SQLite-only reader for legacy A-share daily rows.

``STOCK_ZH_A_HIST`` is a mixed-provenance warehouse input.  This repository
does not infer an upstream provider, open an application database, or expose a
generic table reader.  An operator/test must explicitly provide an approved
physical-projection digest, and every read recomputes that digest before the
fixed SQL projection runs.

The first concrete adapter is deliberately limited to an explicitly injected
*in-memory* SQLite session used by an isolated test/development harness.
Project SQLite files, MySQL, and PostgreSQL all fail closed. Each needs its
own reviewed schema-lock/snapshot implementation; silently falling back to a
dialect-specific ``SELECT`` would weaken the source proof.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.legacy_stock_daily_import import (
    LEGACY_STOCK_DAILY_COLUMN_MAP,
    LEGACY_STOCK_DAILY_TABLE,
    LegacyStockDailyImportError,
)

_SCHEMA_FORMAT = "legacy-stock-daily-sqlite-projection-schema-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_COLUMNS = tuple(LEGACY_STOCK_DAILY_COLUMN_MAP.values())
_SQLITE_TABLE_INFO = 'PRAGMA table_info("STOCK_ZH_A_HIST")'
_FIXED_PROJECTION_SQL = (
    'SELECT "symbol", "data_date", "开盘", "最高", "最低", "收盘", "成交量", "涨跌幅" '
    'FROM "STOCK_ZH_A_HIST" ORDER BY "data_date" ASC, "symbol" ASC'
)


class LegacyStockDailySourceRepositoryError(LegacyStockDailyImportError):
    """Fail-closed source-repository rejection before a canonical write."""


@dataclass(frozen=True, slots=True)
class LegacyStockDailySourceColumn:
    """One physical SQLite projection column bound into the source digest."""

    ordinal: int
    name: str
    declared_type: str
    not_null: bool
    primary_key_position: int

    def __post_init__(self) -> None:
        if not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ValueError("source column ordinal must be a non-negative integer")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("source column name must be non-empty")
        if not isinstance(self.declared_type, str):
            raise TypeError("source declared type must be a string")
        if not isinstance(self.not_null, bool):
            raise TypeError("source not_null must be a bool")
        if not isinstance(self.primary_key_position, int) or self.primary_key_position < 0:
            raise ValueError("source primary_key_position must be a non-negative integer")

    def descriptor(self) -> dict[str, object]:
        """Return the canonical projection fragment used in evidence hashing."""
        return {
            "declared_type": self.declared_type,
            "name": self.name,
            "not_null": self.not_null,
            "ordinal": self.ordinal,
            "primary_key_position": self.primary_key_position,
        }


@dataclass(frozen=True, slots=True)
class LegacyStockDailySourceSchema:
    """The exact reviewed physical projection, excluding unrelated table columns."""

    table_name: str
    source_columns: tuple[str, ...]
    columns: tuple[LegacyStockDailySourceColumn, ...]
    schema_sha256: str

    def __post_init__(self) -> None:
        if self.table_name != LEGACY_STOCK_DAILY_TABLE:
            raise ValueError("legacy source schema table is unsupported")
        if self.source_columns != _SOURCE_COLUMNS:
            raise ValueError("legacy source schema projection is unsupported")
        if len(self.columns) != len(_SOURCE_COLUMNS):
            raise ValueError("legacy source schema column count is invalid")
        if tuple(column.name for column in self.columns) != _SOURCE_COLUMNS:
            raise ValueError("legacy source schema column order is invalid")
        if not isinstance(self.schema_sha256, str) or not _SHA256.fullmatch(self.schema_sha256):
            raise ValueError("legacy source schema digest is invalid")
        expected = _schema_digest(
            table_name=self.table_name,
            source_columns=self.source_columns,
            columns=self.columns,
        )
        if self.schema_sha256 != expected:
            raise ValueError("legacy source schema digest does not match the projection")


class LegacyStockDailySourceRepository:
    """Read one approved in-memory fixture table through a fixed eight-column query."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        approved_schema_sha256: str,
    ) -> None:
        if not isinstance(db, AsyncSession):
            raise TypeError("db must be an AsyncSession")
        if not isinstance(approved_schema_sha256, str) or not _SHA256.fullmatch(
            approved_schema_sha256
        ):
            raise ValueError("approved_schema_sha256 must be a lowercase SHA-256 digest")
        _require_isolated_sqlite(db)
        self._db = db
        self._approved_schema_sha256 = approved_schema_sha256

    async def inspect_projection_schema(self) -> LegacyStockDailySourceSchema:
        """Return the physical projection only if it matches the approved digest."""
        _require_isolated_sqlite(self._db)
        try:
            result = await self._db.execute(text(_SQLITE_TABLE_INFO))
            rows = tuple(result.mappings().all())
        except SQLAlchemyError as exc:
            raise LegacyStockDailySourceRepositoryError(
                "LEGACY_STOCK_DAILY_SOURCE_SCHEMA_UNAVAILABLE"
            ) from exc

        schema = _schema_from_rows(rows)
        if schema.schema_sha256 != self._approved_schema_sha256:
            raise LegacyStockDailySourceRepositoryError(
                "LEGACY_STOCK_DAILY_SOURCE_SCHEMA_APPROVAL_MISMATCH"
            )
        return schema

    async def read_rows(
        self,
        *,
        table_name: str,
        source_columns: tuple[str, ...],
        source_schema_sha256: str,
    ) -> Sequence[Mapping[str, object]]:
        """Recheck the schema then read the reviewed projection without ``SELECT *``."""
        if table_name != LEGACY_STOCK_DAILY_TABLE or source_columns != _SOURCE_COLUMNS:
            raise LegacyStockDailySourceRepositoryError(
                "LEGACY_STOCK_DAILY_SOURCE_QUERY_UNSUPPORTED"
            )
        if not isinstance(source_schema_sha256, str) or not _SHA256.fullmatch(source_schema_sha256):
            raise LegacyStockDailySourceRepositoryError("LEGACY_STOCK_DAILY_SOURCE_SCHEMA_INVALID")
        schema = await self.inspect_projection_schema()
        if schema.schema_sha256 != source_schema_sha256:
            raise LegacyStockDailySourceRepositoryError("LEGACY_STOCK_DAILY_SOURCE_SCHEMA_MISMATCH")
        try:
            result = await self._db.execute(text(_FIXED_PROJECTION_SQL))
            rows = tuple(
                MappingProxyType({column: row[column] for column in _SOURCE_COLUMNS})
                for row in result.mappings().all()
            )
        except (KeyError, SQLAlchemyError) as exc:
            raise LegacyStockDailySourceRepositoryError(
                "LEGACY_STOCK_DAILY_SOURCE_READ_FAILED"
            ) from exc
        return rows

    def _owns_isolated_session(self, db: AsyncSession) -> bool:
        """Return whether a private gate retained the exact injected harness session."""
        return db is self._db


async def inspect_legacy_stock_daily_source_schema(
    db: AsyncSession,
) -> LegacyStockDailySourceSchema:
    """Inspect an injected SQLite fixture to obtain a candidate approval digest.

    This helper does not authorize a table.  It exists so an explicit test or
    offline review step can capture a physical projection hash before creating
    :class:`LegacyStockDailySourceRepository` with that hash.
    """
    if not isinstance(db, AsyncSession):
        raise TypeError("db must be an AsyncSession")
    _require_isolated_sqlite(db)
    try:
        result = await db.execute(text(_SQLITE_TABLE_INFO))
        rows = tuple(result.mappings().all())
    except SQLAlchemyError as exc:
        raise LegacyStockDailySourceRepositoryError(
            "LEGACY_STOCK_DAILY_SOURCE_SCHEMA_UNAVAILABLE"
        ) from exc
    return _schema_from_rows(rows)


def _schema_from_rows(rows: Sequence[Mapping[str, object]]) -> LegacyStockDailySourceSchema:
    """Build the fixed schema descriptor from SQLite ``PRAGMA table_info`` rows."""
    by_name: dict[str, LegacyStockDailySourceColumn] = {}
    for row in rows:
        try:
            column = LegacyStockDailySourceColumn(
                ordinal=_required_int(row.get("cid"), field_name="cid"),
                name=_required_column_name(row.get("name")),
                declared_type=_normalized_declared_type(row.get("type")),
                not_null=_sqlite_boolean(row.get("notnull"), field_name="notnull"),
                primary_key_position=_required_int(row.get("pk"), field_name="pk"),
            )
        except (TypeError, ValueError) as exc:
            raise LegacyStockDailySourceRepositoryError(
                "LEGACY_STOCK_DAILY_SOURCE_SCHEMA_INVALID"
            ) from exc
        if column.name in by_name:
            raise LegacyStockDailySourceRepositoryError("LEGACY_STOCK_DAILY_SOURCE_SCHEMA_INVALID")
        by_name[column.name] = column
    if any(column not in by_name for column in _SOURCE_COLUMNS):
        raise LegacyStockDailySourceRepositoryError("LEGACY_STOCK_DAILY_SOURCE_SCHEMA_INVALID")
    columns = tuple(by_name[column] for column in _SOURCE_COLUMNS)
    return LegacyStockDailySourceSchema(
        table_name=LEGACY_STOCK_DAILY_TABLE,
        source_columns=_SOURCE_COLUMNS,
        columns=columns,
        schema_sha256=_schema_digest(
            table_name=LEGACY_STOCK_DAILY_TABLE,
            source_columns=_SOURCE_COLUMNS,
            columns=columns,
        ),
    )


def _schema_digest(
    *,
    table_name: str,
    source_columns: tuple[str, ...],
    columns: tuple[LegacyStockDailySourceColumn, ...],
) -> str:
    payload = {
        "columns": [column.descriptor() for column in columns],
        "format": _SCHEMA_FORMAT,
        "source_columns": list(source_columns),
        "table_name": table_name,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _require_isolated_sqlite(db: AsyncSession) -> None:
    """Accept only an in-memory SQLite bind explicitly supplied by a harness."""
    bind = db.get_bind()
    if bind.dialect.name != "sqlite":
        raise LegacyStockDailySourceRepositoryError("LEGACY_STOCK_DAILY_SOURCE_ENGINE_UNSUPPORTED")
    # A file-backed SQLite URL can be the application's actual warehouse.
    # This test/development-only adapter must never open it, even when the
    # caller happens to know the exact legacy table name and schema digest.
    if bind.url.database not in {None, ":memory:"}:
        raise LegacyStockDailySourceRepositoryError(
            "LEGACY_STOCK_DAILY_SOURCE_CONNECTION_NOT_ISOLATED"
        )


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _required_column_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("SQLite schema column name is invalid")
    return value


def _normalized_declared_type(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("SQLite schema declared type is invalid")
    return " ".join(value.upper().split())


def _sqlite_boolean(value: object, *, field_name: str) -> bool:
    if value in (0, False):
        return False
    if value in (1, True):
        return True
    raise ValueError(f"{field_name} must be a SQLite boolean")
