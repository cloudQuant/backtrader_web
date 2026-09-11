"""Persist immutable selector completeness evidence for B2 local facts.

Revision ID: 20260911_market_data_b2_completeness_evidence
Revises: 20260911_market_data_semantic_record_keys
Create Date: 2026-09-11

The semantic-record-key migration makes same-event multi-record facts durable,
but it does not prove that a particular option slice or report was complete.
This revision adds an append-only receipt and its explicit expected-key members.
The tables are internal evidence only: they do not enable any B2 public family,
provider route, scheduler, or HTTP endpoint.
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

revision = "20260911_market_data_b2_completeness_evidence"
down_revision = "20260911_market_data_semantic_record_keys"
branch_labels = None
depends_on = None

_RECEIPTS = "md_b2_completeness_receipts"
_ENTRIES = "md_b2_completeness_manifest_entries"
_PARENT_TABLES = ("md_data_series", "md_source_snapshots")
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_SCHEMA_DRIFT = "MARKET_DATA_B2_COMPLETENESS_EVIDENCE_SCHEMA_DRIFT"
_DOWNGRADE_BLOCKED = "MARKET_DATA_B2_COMPLETENESS_EVIDENCE_DOWNGRADE_BLOCKED"
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_B2_COMPLETENESS_EVIDENCE_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.b2_completeness_evidence"
_LOCK_TIMEOUT_SECONDS = 5

_TABLE_SPECS: dict[str, dict[str, object]] = {
    _RECEIPTS: {
        "columns": {
            "id": (sa.String(length=36), False),
            "series_id": (sa.String(length=36), False),
            "source_snapshot_id": (sa.String(length=36), False),
            "family_id": (sa.String(length=128), False),
            "family_contract_version": (sa.String(length=128), False),
            "selector_kind": (sa.String(length=16), False),
            "event_at": (_PIT_DATETIME, False),
            "selector_dimensions_json": (sa.JSON(), False),
            "selector_digest": (sa.String(length=_SHA256_LENGTH), False),
            "manifest_sha256": (sa.String(length=_SHA256_LENGTH), False),
            "expected_record_count": (sa.Integer(), False),
            "zero_record_evidence_sha256": (sa.String(length=_SHA256_LENGTH), True),
            "receipt_sha256": (sa.String(length=_SHA256_LENGTH), False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("id",),
        "checks": {
            "ck_md_b2_completeness_receipt_family_nonempty": "length(family_id) > 0",
            "ck_md_b2_completeness_receipt_contract_nonempty": (
                "length(family_contract_version) > 0"
            ),
            "ck_md_b2_completeness_receipt_selector_kind": "selector_kind IN ('slice', 'report')",
            "ck_md_b2_completeness_receipt_selector_digest_length": (
                f"length(selector_digest) = {_SHA256_LENGTH}"
            ),
            "ck_md_b2_completeness_receipt_manifest_sha256_length": (
                f"length(manifest_sha256) = {_SHA256_LENGTH}"
            ),
            "ck_md_b2_completeness_receipt_sha256_length": (
                f"length(receipt_sha256) = {_SHA256_LENGTH}"
            ),
            "ck_md_b2_completeness_receipt_zero_evidence_length": (
                "zero_record_evidence_sha256 IS NULL OR "
                f"length(zero_record_evidence_sha256) = {_SHA256_LENGTH}"
            ),
            "ck_md_b2_completeness_receipt_expected_count_range": (
                "expected_record_count >= 0 AND expected_record_count <= 50000"
            ),
            "ck_md_b2_completeness_receipt_zero_evidence_state": (
                "(expected_record_count = 0 AND zero_record_evidence_sha256 IS NOT NULL) OR "
                "(expected_record_count > 0 AND zero_record_evidence_sha256 IS NULL)"
            ),
        },
        "indexes": {
            "ix_md_b2_completeness_receipt_source": (("source_snapshot_id", "event_at"), False)
        },
        "unique_constraints": {
            "uq_md_b2_completeness_receipt_series_event_selector": (
                "series_id",
                "event_at",
                "selector_digest",
            ),
            "uq_md_b2_completeness_receipt_sha256": ("receipt_sha256",),
        },
        "foreign_keys": {
            "fk_md_b2_completeness_receipt_series": (
                ("series_id",),
                "md_data_series",
                ("id",),
                "RESTRICT",
            ),
            "fk_md_b2_completeness_receipt_source_snapshot": (
                ("source_snapshot_id",),
                "md_source_snapshots",
                ("id",),
                "RESTRICT",
            ),
        },
    },
    _ENTRIES: {
        "columns": {
            "receipt_id": (sa.String(length=36), False),
            "semantic_record_key_sha256": (sa.String(length=_SHA256_LENGTH), False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("receipt_id", "semantic_record_key_sha256"),
        "checks": {
            "ck_md_b2_completeness_entry_key_sha256_length": (
                f"length(semantic_record_key_sha256) = {_SHA256_LENGTH}"
            ),
        },
        "indexes": {},
        "unique_constraints": {},
        "foreign_keys": {
            "fk_md_b2_completeness_entry_receipt": (
                ("receipt_id",),
                _RECEIPTS,
                ("id",),
                "RESTRICT",
            ),
        },
    },
}


def _is_offline() -> bool:
    return context.is_offline_mode()


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL and require an explicit writer drain on MySQL-family engines."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_SECONDS}s'"))
        yield
        return
    if bind.dialect.name not in {"mysql", "mariadb"}:
        yield
        return
    if os.getenv(_MYSQL_MAINTENANCE_FENCE_ENV) != "confirmed":
        raise RuntimeError(
            "MARKET_DATA_B2_COMPLETENESS_EVIDENCE_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_B2_COMPLETENESS_EVIDENCE_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _normalized_expression(expression: object) -> str:
    """Normalize only known PostgreSQL/MySQL reflection spelling differences."""
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


def _unique_constraints(
    inspector: sa.Inspector,
    table_name: str,
) -> dict[str, tuple[str, ...]]:
    """Normalize dialects which reflect a named unique as an index instead."""
    constraints = {
        str(item["name"]): tuple(str(column) for column in item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table_name)
        if item.get("name")
    }
    for index in inspector.get_indexes(table_name):
        if not index.get("name") or not bool(index.get("unique", False)):
            continue
        name = str(index["name"])
        columns = tuple(str(column) for column in index.get("column_names") or ())
        existing = constraints.setdefault(name, columns)
        if existing != columns:
            raise RuntimeError(
                f"{_SCHEMA_DRIFT}: unique reflection disagreement {table_name}.{name}"
            )
    return constraints


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

    uniques = _unique_constraints(inspector, table_name)
    expected_uniques = spec["unique_constraints"]
    assert isinstance(expected_uniques, dict)
    if uniques != expected_uniques:
        errors["unique_constraints"] = {"actual": uniques, "expected": expected_uniques}

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


def _require_parent_tables(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    missing = [table_name for table_name in _PARENT_TABLES if not inspector.has_table(table_name)]
    if missing:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: required parent tables missing {missing}")


def _require_absent_or_exact_tables(bind: sa.Connection) -> bool:
    """Accept neither table or both exact tables; partial/current drift is rejected."""
    _require_parent_tables(bind)
    inspector = sa.inspect(bind)
    presence = {table_name: inspector.has_table(table_name) for table_name in _TABLE_SPECS}
    if not any(presence.values()):
        return False
    if not all(presence.values()):
        raise RuntimeError(f"{_SCHEMA_DRIFT}: partial B2 completeness schema {presence}")
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
        _RECEIPTS,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("family_contract_version", sa.String(length=128), nullable=False),
        sa.Column("selector_kind", sa.String(length=16), nullable=False),
        sa.Column("event_at", _PIT_DATETIME, nullable=False),
        sa.Column("selector_dimensions_json", sa.JSON(), nullable=False),
        sa.Column("selector_digest", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("expected_record_count", sa.Integer(), nullable=False),
        sa.Column("zero_record_evidence_sha256", sa.String(length=_SHA256_LENGTH), nullable=True),
        sa.Column("receipt_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["md_data_series.id"],
            name="fk_md_b2_completeness_receipt_series",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["md_source_snapshots.id"],
            name="fk_md_b2_completeness_receipt_source_snapshot",
            ondelete="RESTRICT",
        ),
        *(
            sa.CheckConstraint(expression, name=name)
            for name, expression in _TABLE_SPECS[_RECEIPTS]["checks"].items()
        ),
        sa.UniqueConstraint(
            "series_id",
            "event_at",
            "selector_digest",
            name="uq_md_b2_completeness_receipt_series_event_selector",
        ),
        sa.UniqueConstraint("receipt_sha256", name="uq_md_b2_completeness_receipt_sha256"),
    )
    op.create_index(
        "ix_md_b2_completeness_receipt_source",
        _RECEIPTS,
        ["source_snapshot_id", "event_at"],
    )
    op.create_table(
        _ENTRIES,
        sa.Column("receipt_id", sa.String(length=36), nullable=False),
        sa.Column("semantic_record_key_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("receipt_id", "semantic_record_key_sha256"),
        sa.ForeignKeyConstraint(
            ["receipt_id"],
            [f"{_RECEIPTS}.id"],
            name="fk_md_b2_completeness_entry_receipt",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"length(semantic_record_key_sha256) = {_SHA256_LENGTH}",
            name="ck_md_b2_completeness_entry_key_sha256_length",
        ),
    )


def upgrade() -> None:
    """Create only exact durable B2 completeness evidence tables."""
    if _is_offline():
        _create_tables()
        return
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_tables(bind):
            _create_tables()


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    for table_name in (_ENTRIES, _RECEIPTS):
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        first_column = next(iter(table.c), None)
        if (
            first_column is not None
            and bind.execute(sa.select(first_column).limit(1)).scalar() is not None
        ):
            raise RuntimeError(
                f"{_DOWNGRADE_BLOCKED}: immutable B2 completeness evidence exists in {table_name}"
            )


def _lock_downgrade_evidence_tables(bind: sa.Connection) -> None:
    """Prevent PostgreSQL writers from racing the irreversible empty check."""
    if bind.dialect.name != "postgresql":
        return
    bind.execute(sa.text(f"LOCK TABLE {_ENTRIES}, {_RECEIPTS} IN ACCESS EXCLUSIVE MODE"))


def downgrade() -> None:
    """Drop only empty B2 receipt tables after an online schema proof."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove tables empty")
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_tables(bind):
            return
        _lock_downgrade_evidence_tables(bind)
        _assert_downgrade_safe(bind)
        op.drop_table(_ENTRIES)
        op.drop_index("ix_md_b2_completeness_receipt_source", table_name=_RECEIPTS)
        op.drop_table(_RECEIPTS)
