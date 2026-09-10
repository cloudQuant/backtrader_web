"""Add content-addressed raw-source payloads without rewriting evidence parents.

Revision ID: 20260910_market_data_shared_source_payloads
Revises: 20260909_market_data_research_binding_consumers
Create Date: 2026-09-10

Wide provider responses can support several normalized target series.  This
revision stores each canonical UTF-8 raw segment once and links each immutable
source receipt through a new child table.  It intentionally does *not* alter
``md_source_snapshots``: populated SQLite installations can therefore upgrade
without rebuilding the parent table while it is referenced by observations and
calendar evidence.
"""

# alembic-meta: estimated_rows=0; lock_kind=short

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import context, op

revision = "20260910_market_data_shared_source_payloads"
down_revision = "20260909_market_data_research_binding_consumers"
branch_labels = None
depends_on = None

_PAYLOADS = "md_source_payloads"
_REFS = "md_source_snapshot_payload_refs"
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_CANONICAL_PAYLOAD_BYTES = sa.LargeBinary().with_variant(mysql.MEDIUMBLOB, "mysql")
_SCHEMA_DRIFT = "MARKET_DATA_SHARED_SOURCE_PAYLOAD_SCHEMA_DRIFT"
_DOWNGRADE_BLOCKED = "MARKET_DATA_SHARED_SOURCE_PAYLOAD_DOWNGRADE_BLOCKED"
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_SHARED_SOURCE_PAYLOAD_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.shared_source_payloads"
_LOCK_TIMEOUT_SECONDS = 5

_TABLE_SPECS: dict[str, dict[str, object]] = {
    _PAYLOADS: {
        "columns": {
            "content_sha256": (sa.String(length=_SHA256_LENGTH), False),
            "payload_format": (sa.String(length=128), False),
            "canonical_payload_bytes": (_CANONICAL_PAYLOAD_BYTES, False),
            "payload_bytes": (sa.BigInteger(), False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("content_sha256",),
        "checks": {
            "ck_md_source_payload_content_sha256_length": (
                f"length(content_sha256) = {_SHA256_LENGTH}"
            ),
            "ck_md_source_payload_format_nonempty": "length(payload_format) > 0",
            "ck_md_source_payload_bytes_positive": "payload_bytes > 0",
        },
        "indexes": {},
        "foreign_keys": {},
    },
    _REFS: {
        "columns": {
            "source_snapshot_id": (sa.String(length=36), False),
            "content_sha256": (sa.String(length=_SHA256_LENGTH), False),
            "payload_role": (sa.String(length=128), False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("source_snapshot_id",),
        "checks": {
            "ck_md_source_snapshot_payload_ref_sha256_length": (
                f"length(content_sha256) = {_SHA256_LENGTH}"
            ),
            "ck_md_source_snapshot_payload_ref_role": "payload_role = 'source_batch'",
        },
        "indexes": {"ix_md_source_snapshot_payload_ref_content": (("content_sha256",), False)},
        "foreign_keys": {
            "fk_md_source_snapshot_payload_ref_snapshot": (
                ("source_snapshot_id",),
                "md_source_snapshots",
                ("id",),
                "RESTRICT",
            ),
            "fk_md_source_snapshot_payload_ref_payload": (
                ("content_sha256",),
                _PAYLOADS,
                ("content_sha256",),
                "RESTRICT",
            ),
        },
    },
}


def _is_offline() -> bool:
    return context.is_offline_mode()


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL and require a MySQL writer-drain confirmation."""
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
            "MARKET_DATA_SHARED_SOURCE_PAYLOAD_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_SHARED_SOURCE_PAYLOAD_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME})


def _normalized_expression(expression: object) -> str:
    """Normalize only known server rendering differences for named checks."""
    normalized = "".join(str(expression).split()).lower().replace('"', "").replace("`", "")
    normalized = re.sub(r"::(?:text|charactervarying|varchar)(?:\[\])?", "", normalized)
    normalized = re.sub(r"_(?:utf8mb4|utf8)(?=')", "", normalized)
    normalized = re.sub(
        r"([a-z_][a-z0-9_]*)=any\(array\[(.*?)\]\)",
        r"\1in(\2)",
        normalized,
    )
    while (
        normalized.startswith("(")
        and normalized.endswith(")")
        and _outer_parentheses_wrap(normalized)
    ):
        normalized = normalized[1:-1]
    return normalized


def _outer_parentheses_wrap(expression: str) -> bool:
    depth = 0
    for index, character in enumerate(expression):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index == len(expression) - 1
    return False


def _type_signature(
    type_: sa.types.TypeEngine[Any],
    *,
    dialect_name: str,
) -> tuple[type[object], int | None, bool | None, int | None, str | None]:
    timezone_mode = (
        bool(getattr(type_, "timezone", False))
        if dialect_name == "postgresql" and isinstance(type_, sa.DateTime)
        else None
    )
    precision = (
        getattr(type_, "fsp", None)
        if dialect_name in {"mysql", "mariadb"} and isinstance(type_, sa.DateTime)
        else None
    )
    mysql_binary_type = (
        str(getattr(type_, "__visit_name__", type(type_).__name__)).upper()
        if dialect_name in {"mysql", "mariadb"} and isinstance(type_, sa.types._Binary)
        else None
    )
    return (
        type_._type_affinity,
        getattr(type_, "length", None),
        timezone_mode,
        precision,
        mysql_binary_type,
    )


def _table_errors(
    bind: sa.Connection,
    table_name: str,
    spec: dict[str, object],
) -> dict[str, object]:
    inspector = sa.inspect(bind)
    columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    expected_columns = spec["columns"]
    assert isinstance(expected_columns, dict)
    errors: dict[str, object] = {}
    if set(columns) != set(expected_columns):
        errors["columns"] = {
            "missing": sorted(set(expected_columns) - set(columns)),
            "unexpected": sorted(set(columns) - set(expected_columns)),
        }
    invalid_columns: dict[str, object] = {}
    for column_name, definition in expected_columns.items():
        actual = columns.get(str(column_name))
        if actual is None:
            continue
        expected_type, expected_nullable = definition
        assert isinstance(expected_type, sa.types.TypeEngine)
        expected = _type_signature(
            expected_type.dialect_impl(bind.dialect),
            dialect_name=bind.dialect.name,
        )
        observed = _type_signature(actual["type"], dialect_name=bind.dialect.name)
        if (
            observed != expected
            or bool(actual.get("nullable")) != expected_nullable
            or actual.get("default") is not None
        ):
            invalid_columns[str(column_name)] = {
                "actual": observed,
                "expected": expected,
                "nullable": bool(actual.get("nullable")),
                "expected_nullable": expected_nullable,
                "default": actual.get("default"),
            }
    if invalid_columns:
        errors["invalid_columns"] = invalid_columns

    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    )
    expected_primary_key = spec["primary_key"]
    assert isinstance(expected_primary_key, tuple)
    if primary_key != expected_primary_key:
        errors["primary_key"] = {"actual": primary_key, "expected": expected_primary_key}

    checks = {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in inspector.get_check_constraints(table_name)
        if check.get("name")
    }
    expected_checks_raw = spec["checks"]
    assert isinstance(expected_checks_raw, dict)
    expected_checks = {
        str(name): _normalized_expression(expression)
        for name, expression in expected_checks_raw.items()
    }
    if checks != expected_checks:
        errors["checks"] = {"actual": checks, "expected": expected_checks}

    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            False,
        )
        for index in inspector.get_indexes(table_name)
        if index.get("name") and not bool(index.get("unique", False))
    }
    expected_indexes = spec["indexes"]
    assert isinstance(expected_indexes, dict)
    if indexes != expected_indexes:
        errors["indexes"] = {"actual": indexes, "expected": expected_indexes}

    foreign_keys = {
        str(item["name"]): (
            tuple(str(column) for column in item.get("constrained_columns") or ()),
            str(item.get("referred_table") or ""),
            tuple(str(column) for column in item.get("referred_columns") or ()),
            str((item.get("options") or {}).get("ondelete") or "").upper(),
        )
        for item in inspector.get_foreign_keys(table_name)
        if item.get("name")
    }
    expected_foreign_keys = spec["foreign_keys"]
    assert isinstance(expected_foreign_keys, dict)
    if foreign_keys != expected_foreign_keys:
        errors["foreign_keys"] = {"actual": foreign_keys, "expected": expected_foreign_keys}
    return errors


def _require_absent_or_exact_tables(bind: sa.Connection) -> bool:
    """Accept both complete startup-created tables, create neither otherwise."""
    inspector = sa.inspect(bind)
    presence = {table_name: inspector.has_table(table_name) for table_name in _TABLE_SPECS}
    if not any(presence.values()):
        return False
    if not all(presence.values()):
        raise RuntimeError(f"{_SCHEMA_DRIFT}: partial shared-source-payload schema {presence}")
    errors = {
        table_name: _table_errors(bind, table_name, spec)
        for table_name, spec in _TABLE_SPECS.items()
    }
    errors = {table_name: value for table_name, value in errors.items() if value}
    if errors:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: {errors}")
    return True


def _create_tables() -> None:
    op.create_table(
        _PAYLOADS,
        sa.Column("content_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("payload_format", sa.String(length=128), nullable=False),
        sa.Column("canonical_payload_bytes", _CANONICAL_PAYLOAD_BYTES, nullable=False),
        sa.Column("payload_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("content_sha256"),
        sa.CheckConstraint(
            f"length(content_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_payload_content_sha256_length",
        ),
        sa.CheckConstraint(
            "length(payload_format) > 0",
            name="ck_md_source_payload_format_nonempty",
        ),
        sa.CheckConstraint(
            "payload_bytes > 0",
            name="ck_md_source_payload_bytes_positive",
        ),
    )
    op.create_table(
        _REFS,
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("content_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("payload_role", sa.String(length=128), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("source_snapshot_id"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["md_source_snapshots.id"],
            name="fk_md_source_snapshot_payload_ref_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["content_sha256"],
            [f"{_PAYLOADS}.content_sha256"],
            name="fk_md_source_snapshot_payload_ref_payload",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"length(content_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_snapshot_payload_ref_sha256_length",
        ),
        sa.CheckConstraint(
            "payload_role = 'source_batch'",
            name="ck_md_source_snapshot_payload_ref_role",
        ),
    )
    op.create_index("ix_md_source_snapshot_payload_ref_content", _REFS, ["content_sha256"])


def upgrade() -> None:
    """Create two append-only child tables without a source-snapshot rewrite."""
    if _is_offline():
        _create_tables()
        return
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_tables(bind):
            _create_tables()


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    for table_name in (_REFS, _PAYLOADS):
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        first_column = next(iter(table.c), None)
        if first_column is not None and bind.execute(sa.select(first_column).limit(1)).scalar() is not None:
            raise RuntimeError(
                f"{_DOWNGRADE_BLOCKED}: immutable shared source evidence exists in {table_name}"
            )


def _lock_downgrade_evidence_tables(bind: sa.Connection) -> None:
    """Prevent PostgreSQL writers from racing the irreversible empty check."""
    if bind.dialect.name != "postgresql":
        return
    bind.execute(
        sa.text(
            f"LOCK TABLE {_PAYLOADS}, {_REFS} IN ACCESS EXCLUSIVE MODE"
        )
    )


def downgrade() -> None:
    """Drop only empty shared-evidence tables after an online safety check."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove tables empty")
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_tables(bind):
            return
        _lock_downgrade_evidence_tables(bind)
        _assert_downgrade_safe(bind)
        op.drop_index("ix_md_source_snapshot_payload_ref_content", table_name=_REFS)
        op.drop_table(_REFS)
        op.drop_table(_PAYLOADS)
