"""Enforce bytewise comparison for market-data identity keys.

Revision ID: 20260909_market_data_exact_identity_collation
Revises: 20260909_market_data_fetch_leases
Create Date: 2026-09-09

Market identifiers are protocol values.  A database default such as a MySQL
``*_ci`` collation must not make ``RB0`` and ``rb0`` equal before the strict
identity resolver can reject the mismatched request.  The revision changes
only the lookup and immutable identity-projection identifier columns; it does
not rewrite an AkShare warehouse or any market-data fact.
"""

# alembic-meta: estimated_rows=0; lock_kind=short

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql

from alembic import context, op

revision = "20260909_market_data_exact_identity_collation"
down_revision = "20260909_market_data_fetch_leases"
branch_labels = None
depends_on = None

_IDENTITY_REVISIONS = "md_instrument_identity_revisions"
_LOOKUP_KEYS = "md_instrument_lookup_keys"
_ASSET_INSTRUMENTS = "asset_instruments"
_IDENTIFIER_COLUMNS: dict[str, tuple[tuple[str, int, bool], ...]] = {
    _ASSET_INSTRUMENTS: (("canonical_id", 512, False),),
    _IDENTITY_REVISIONS: (
        ("canonical_id", 512, False),
        ("asset_type", 16, False),
        ("market", 128, True),
        ("symbol", 128, False),
    ),
    _LOOKUP_KEYS: (
        ("canonical_id", 512, False),
        ("asset_type", 16, False),
        ("market", 128, False),
        ("symbol", 128, False),
    ),
}
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_EXACT_IDENTITY_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.exact_identity"
_LOCK_TIMEOUT_SECONDS = 5


def _is_offline() -> bool:
    return context.is_offline_mode()


def _exact_identifier_type(length: int) -> sa.types.TypeEngine[Any]:
    """Return one exact-comparison type for all supported database engines."""
    return (
        sa.String(length, collation="BINARY")
        .with_variant(mysql.VARCHAR(length, collation="utf8mb4_bin"), "mysql")
        .with_variant(postgresql.VARCHAR(length, collation="C"), "postgresql")
    )


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound online DDL and require a MySQL writer drain before table rebuilds."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_SECONDS}s'"))
        yield
        return
    if bind.dialect.name != "mysql":
        yield
        return
    if os.getenv(_MYSQL_MAINTENANCE_FENCE_ENV) != "confirmed":
        raise RuntimeError(
            "MARKET_DATA_EXACT_IDENTITY_MAINTENANCE_FENCE_REQUIRED: "
            "stop market-data writers and set "
            f"{_MYSQL_MAINTENANCE_FENCE_ENV}=confirmed before MySQL DDL"
        )
    bind.execute(sa.text(f"SET SESSION lock_wait_timeout = {_LOCK_TIMEOUT_SECONDS}"))
    acquired = bind.execute(
        sa.text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
        {"lock_name": _MYSQL_MIGRATION_LOCK_NAME, "timeout_seconds": _LOCK_TIMEOUT_SECONDS},
    ).scalar_one()
    if acquired != 1:
        raise RuntimeError(
            "MARKET_DATA_EXACT_IDENTITY_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _require_identifier_columns(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    for table_name, expected_columns in _IDENTIFIER_COLUMNS.items():
        if not inspector.has_table(table_name):
            raise RuntimeError(f"MARKET_DATA_EXACT_IDENTITY_SCHEMA_UNREADY: {table_name} missing")
        columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
        for column_name, length, nullable in expected_columns:
            actual = columns.get(column_name)
            if actual is None:
                raise RuntimeError(
                    f"MARKET_DATA_EXACT_IDENTITY_SCHEMA_UNREADY: {table_name}.{column_name} missing"
                )
            actual_type = actual["type"]
            if (
                not isinstance(actual_type, sa.String)
                or getattr(actual_type, "length", None) != length
                or bool(actual.get("nullable")) != nullable
            ):
                raise RuntimeError(
                    f"MARKET_DATA_EXACT_IDENTITY_SCHEMA_DRIFT: {table_name}.{column_name}"
                )


def _assert_sqlite_binary_collation(bind: sa.Connection) -> None:
    """Reject a non-default SQLite collation because SQLite cannot alter it in place."""
    for table_name, expected_columns in _IDENTIFIER_COLUMNS.items():
        ddl = bind.execute(
            sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).scalar_one_or_none()
        if not isinstance(ddl, str):
            raise RuntimeError(
                f"MARKET_DATA_EXACT_IDENTITY_SCHEMA_UNREADY: {table_name} definition missing"
            )
        for column_name, _, _ in expected_columns:
            # Absence of a SQLite COLLATE clause means BINARY, which is the
            # desired contract. A non-binary explicit collation is unsafe and
            # cannot be changed without a reviewed table reconstruction.
            matcher = re.compile(
                rf'(?is)(?:"{re.escape(column_name)}"|{re.escape(column_name)})'
                r"\s+VARCHAR\s*\(\s*\d+\s*\)\s*"
                r'(?:COLLATE\s+(?:"(?P<quoted>[^"]+)"|(?P<bare>\w+)))?'
            )
            match = matcher.search(ddl)
            if match is None:
                raise RuntimeError(
                    f"MARKET_DATA_EXACT_IDENTITY_SCHEMA_DRIFT: {table_name}.{column_name}"
                )
            collation = match.group("quoted") or match.group("bare")
            if collation is not None and collation.upper() != "BINARY":
                raise RuntimeError(
                    "MARKET_DATA_EXACT_IDENTITY_SCHEMA_DRIFT: "
                    f"{table_name}.{column_name} has a non-binary SQLite collation"
                )


def _alter_mysql_columns() -> None:
    for table_name, expected_columns in _IDENTIFIER_COLUMNS.items():
        for column_name, length, nullable in expected_columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.String(length),
                type_=_exact_identifier_type(length),
                existing_nullable=nullable,
            )


def _alter_postgresql_columns() -> None:
    for table_name, expected_columns in _IDENTIFIER_COLUMNS.items():
        for column_name, length, _ in expected_columns:
            op.execute(
                sa.text(
                    f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" '
                    f'TYPE VARCHAR({length}) COLLATE "C" '
                    f'USING "{column_name}"::VARCHAR({length})'
                )
            )


def upgrade() -> None:
    """Make canonical and triple lookup predicates bytewise on server databases."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_EXACT_IDENTITY_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot verify the current identifier-column contract"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _require_identifier_columns(bind)
        if bind.dialect.name == "mysql":
            _alter_mysql_columns()
        elif bind.dialect.name == "postgresql":
            _alter_postgresql_columns()
        elif bind.dialect.name == "sqlite":
            _assert_sqlite_binary_collation(bind)
        else:
            raise RuntimeError(
                f"MARKET_DATA_EXACT_IDENTITY_DIALECT_UNSUPPORTED: {bind.dialect.name}"
            )


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    """Permit a test/dev rollback only before any exact identity has been recorded."""
    populated_tables: list[str] = []
    inspector = sa.inspect(bind)
    for table_name in _IDENTIFIER_COLUMNS:
        if not inspector.has_table(table_name):
            continue
        populated = bind.execute(sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")).scalar()
        if populated is not None:
            populated_tables.append(table_name)
    if populated_tables:
        raise RuntimeError(
            "MARKET_DATA_EXACT_IDENTITY_DOWNGRADE_BLOCKED: "
            "cannot remove exact-identifier migration state after identity evidence exists "
            f"({', '.join(populated_tables)})"
        )


def downgrade() -> None:
    """Allow only an empty-chain rollback without weakening recorded identities.

    The previous model columns are ordinary strings, so restoring them would
    reintroduce a database-default collation.  Empty test/development chains
    can move their Alembic marker back while retaining the stricter physical
    shape; any database that has recorded an identity must instead restore a
    reviewed pre-migration snapshot.
    """
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_EXACT_IDENTITY_DOWNGRADE_BLOCKED: "
            "offline SQL cannot prove identity tables are empty"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _assert_downgrade_safe(bind)
