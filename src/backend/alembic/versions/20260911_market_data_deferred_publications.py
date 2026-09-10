"""Add durable deferred-publication holds for the legacy daily-import pilot.

Revision ID: 20260911_market_data_deferred_publications
Revises: 20260910_market_data_capability_ledger
Create Date: 2026-09-11

The hold is an additive child of an existing publication receipt and source
snapshot. It records whether the legacy stock-daily import has remained
deferred, been quarantined, or been promoted after independent verification.
It never reinterprets an existing receipt or changes its visibility state
during upgrade.
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

revision = "20260911_market_data_deferred_publications"
down_revision = "20260910_market_data_capability_ledger"
branch_labels = None
depends_on = None

_TABLE = "md_publication_release_holds"
_PUBLICATIONS_TABLE = "md_publications"
_SOURCE_SNAPSHOTS_TABLE = "md_source_snapshots"
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_INDEX = "ix_md_publication_release_hold_state_created"
_SCHEMA_DRIFT = "MARKET_DATA_PUBLICATION_RELEASE_HOLD_SCHEMA_DRIFT"
_DOWNGRADE_BLOCKED = "MARKET_DATA_PUBLICATION_RELEASE_HOLD_DOWNGRADE_BLOCKED"
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_PUBLICATION_RELEASE_HOLD_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.publication_release_hold"
_LOCK_TIMEOUT_SECONDS = 5

_COLUMN_SPECS: dict[str, tuple[sa.types.TypeEngine[Any], bool]] = {
    "id": (sa.String(length=36), False),
    "publication_id": (sa.String(length=36), False),
    "source_snapshot_id": (sa.String(length=36), False),
    "workflow_kind": (sa.String(length=64), False),
    "state": (sa.String(length=16), False),
    "intent_sha256": (sa.String(length=_SHA256_LENGTH), False),
    "quarantine_code": (sa.String(length=128), True),
    "quarantined_at": (_PIT_DATETIME, True),
    "promotion_evidence_sha256": (sa.String(length=_SHA256_LENGTH), True),
    "promoted_at": (_PIT_DATETIME, True),
    "created_at": (_PIT_DATETIME, False),
}
_CHECKS = {
    "ck_md_publication_release_hold_workflow_kind": ("workflow_kind = 'legacy_stock_daily_import'"),
    "ck_md_publication_release_hold_state": "state IN ('DEFERRED', 'QUARANTINED', 'PROMOTED')",
    "ck_md_publication_release_hold_intent_sha256_length": (
        f"length(intent_sha256) = {_SHA256_LENGTH}"
    ),
    "ck_md_publication_release_hold_promotion_evidence_sha256_length": (
        f"promotion_evidence_sha256 IS NULL OR length(promotion_evidence_sha256) = {_SHA256_LENGTH}"
    ),
    "ck_md_publication_release_hold_deferred_state_fields": (
        "state <> 'DEFERRED' OR "
        "(quarantine_code IS NULL AND quarantined_at IS NULL AND "
        "promotion_evidence_sha256 IS NULL AND promoted_at IS NULL)"
    ),
    "ck_md_publication_release_hold_quarantined_state_fields": (
        "state <> 'QUARANTINED' OR "
        "(quarantine_code IS NOT NULL AND length(quarantine_code) > 0 AND "
        "quarantined_at IS NOT NULL AND "
        "promotion_evidence_sha256 IS NULL AND promoted_at IS NULL)"
    ),
    "ck_md_publication_release_hold_promoted_state_fields": (
        "state <> 'PROMOTED' OR "
        "(quarantine_code IS NULL AND quarantined_at IS NULL AND "
        "promotion_evidence_sha256 IS NOT NULL AND promoted_at IS NOT NULL)"
    ),
}
_UNIQUE_CONSTRAINTS = {
    "uq_md_publication_release_hold_publication": ("publication_id",),
    "uq_md_publication_release_hold_source_snapshot": ("source_snapshot_id",),
}
_FOREIGN_KEYS = {
    "fk_md_publication_release_hold_publication": (
        ("publication_id",),
        _PUBLICATIONS_TABLE,
        ("id",),
        "RESTRICT",
    ),
    "fk_md_publication_release_hold_source_snapshot": (
        ("source_snapshot_id",),
        _SOURCE_SNAPSHOTS_TABLE,
        ("id",),
        "RESTRICT",
    ),
}


def _is_offline() -> bool:
    return context.is_offline_mode()


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL and require a confirmed writer drain on MySQL-family servers."""
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
            "MARKET_DATA_PUBLICATION_RELEASE_HOLD_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_PUBLICATION_RELEASE_HOLD_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _normalized_expression(expression: object) -> str:
    """Normalize only known server reflection differences for named checks."""
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
) -> tuple[type[object], int | None, bool | None, int | None]:
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
    return (
        type_._type_affinity,
        getattr(type_, "length", None),
        timezone_mode,
        precision,
    )


def _require_parent_tables(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    missing = [
        table_name
        for table_name in (_PUBLICATIONS_TABLE, _SOURCE_SNAPSHOTS_TABLE)
        if not inspector.has_table(table_name)
    ]
    if missing:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: required parent tables missing: {missing}")


def _require_absent_or_exact_table(bind: sa.Connection) -> bool:
    """Return whether a startup-created hold table matches the reviewed shape."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return False
    columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ()
    )
    unique_constraints = {
        str(constraint["name"]): tuple(
            str(column) for column in constraint.get("column_names") or ()
        )
        for constraint in inspector.get_unique_constraints(_TABLE)
        if constraint.get("name")
    }
    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique", False)),
        )
        for index in inspector.get_indexes(_TABLE)
        if index.get("name")
    }
    checks = {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in inspector.get_check_constraints(_TABLE)
        if check.get("name")
    }
    foreign_keys = {
        str(item["name"]): (
            tuple(str(column) for column in item.get("constrained_columns") or ()),
            str(item.get("referred_table") or ""),
            tuple(str(column) for column in item.get("referred_columns") or ()),
            str((item.get("options") or {}).get("ondelete") or "").upper(),
        )
        for item in inspector.get_foreign_keys(_TABLE)
        if item.get("name")
    }
    invalid_columns: dict[str, object] = {}
    for column_name, (expected_type, expected_nullable) in _COLUMN_SPECS.items():
        actual = columns.get(column_name)
        if actual is None:
            continue
        expected_signature = _type_signature(
            expected_type.dialect_impl(bind.dialect), dialect_name=bind.dialect.name
        )
        actual_signature = _type_signature(actual["type"], dialect_name=bind.dialect.name)
        if (
            actual_signature != expected_signature
            or bool(actual.get("nullable")) != expected_nullable
            or actual.get("default") is not None
        ):
            invalid_columns[column_name] = {
                "actual_type": actual_signature,
                "expected_type": expected_signature,
                "actual_nullable": bool(actual.get("nullable")),
                "expected_nullable": expected_nullable,
                "actual_default": actual.get("default"),
            }
    expected_checks = {
        name: _normalized_expression(expression) for name, expression in _CHECKS.items()
    }
    missing_checks = set(expected_checks) - set(checks)
    invalid_checks = {
        name: {"actual": checks[name], "expected": expression}
        for name, expression in expected_checks.items()
        if name in checks and checks[name] != expression
    }
    expected_index = (("state", "created_at"), False)
    if (
        set(columns) != set(_COLUMN_SPECS)
        or invalid_columns
        or primary_key != ("id",)
        or unique_constraints != _UNIQUE_CONSTRAINTS
        or indexes.get(_INDEX) != expected_index
        or missing_checks
        or invalid_checks
        or foreign_keys != _FOREIGN_KEYS
    ):
        raise RuntimeError(
            f"{_SCHEMA_DRIFT}: {{"
            f"'missing_columns': {sorted(set(_COLUMN_SPECS) - set(columns))}, "
            f"'unexpected_columns': {sorted(set(columns) - set(_COLUMN_SPECS))}, "
            f"'invalid_columns': {invalid_columns}, "
            f"'primary_key': {primary_key}, "
            f"'unique': {unique_constraints}, "
            f"'index': {indexes.get(_INDEX)}, "
            f"'missing_checks': {sorted(missing_checks)}, "
            f"'invalid_checks': {invalid_checks}, "
            f"'foreign_keys': {foreign_keys}"
            "}"
        )
    return True


def _create_table() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_kind", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("intent_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("quarantine_code", sa.String(length=128), nullable=True),
        sa.Column("quarantined_at", _PIT_DATETIME, nullable=True),
        sa.Column("promotion_evidence_sha256", sa.String(length=_SHA256_LENGTH), nullable=True),
        sa.Column("promoted_at", _PIT_DATETIME, nullable=True),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            [f"{_PUBLICATIONS_TABLE}.id"],
            name="fk_md_publication_release_hold_publication",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            [f"{_SOURCE_SNAPSHOTS_TABLE}.id"],
            name="fk_md_publication_release_hold_source_snapshot",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("publication_id", name="uq_md_publication_release_hold_publication"),
        sa.UniqueConstraint(
            "source_snapshot_id",
            name="uq_md_publication_release_hold_source_snapshot",
        ),
        *(sa.CheckConstraint(expression, name=name) for name, expression in _CHECKS.items()),
    )
    op.create_index(_INDEX, _TABLE, ["state", "created_at"])


def upgrade() -> None:
    """Create the empty child hold table without altering publication evidence."""
    if _is_offline():
        _create_table()
        return
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _require_parent_tables(bind)
        if not _require_absent_or_exact_table(bind):
            _create_table()


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    if bind.execute(sa.select(table.c.id).limit(1)).scalar() is not None:
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: publication release holds exist")


def _lock_for_downgrade(bind: sa.Connection) -> None:
    """Block PostgreSQL promotion writers before checking whether the table is empty."""
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"LOCK TABLE {_TABLE} IN ACCESS EXCLUSIVE MODE"))


def downgrade() -> None:
    """Drop only an empty hold table after an online safety check."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove table empty")
    bind = op.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        # MySQL DDL implicitly commits. The migration lock serializes migration
        # processes but ordinary hold writers do not take it, so an insert can
        # race the empty-table proof. Keep this evidence table irreversible
        # until a writer-participating maintenance fence exists.
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: MySQL cannot atomically prove the table empty")
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_table(bind):
            return
        _lock_for_downgrade(bind)
        _assert_downgrade_safe(bind)
        op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)
