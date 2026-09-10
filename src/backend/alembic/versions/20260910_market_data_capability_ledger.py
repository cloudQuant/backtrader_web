"""Add durable, append-only market-data capability attestations.

Revision ID: 20260910_market_data_capability_ledger
Revises: 20260910_market_data_shared_source_payloads
Create Date: 2026-09-10

Rollout environment variables remain kill switches only.  This table stores
the durable declaration, installed-runtime, verification, authorization, and
expiry evidence that must exist before any v2 capability can be effective.
The migration creates a new isolated table and does not reinterpret earlier
provider receipts or grant a capability during upgrade.
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

revision = "20260910_market_data_capability_ledger"
down_revision = "20260910_market_data_shared_source_payloads"
branch_labels = None
depends_on = None

_TABLE = "md_capability_ledger_entries"
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_INDEX = "ix_md_capability_ledger_current"
_DOWNGRADE_BLOCKED = "MARKET_DATA_CAPABILITY_LEDGER_DOWNGRADE_BLOCKED"
_SCHEMA_DRIFT = "MARKET_DATA_CAPABILITY_LEDGER_SCHEMA_DRIFT"
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_CAPABILITY_LEDGER_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.capability_ledger"
_LOCK_TIMEOUT_SECONDS = 5

_COLUMN_SPECS: dict[str, tuple[sa.types.TypeEngine[Any], bool]] = {
    "id": (sa.String(length=36), False),
    "capability_id": (sa.String(length=192), False),
    "revision": (sa.Integer(), False),
    "descriptor_sha256": (sa.String(length=_SHA256_LENGTH), False),
    "evidence_sha256": (sa.String(length=_SHA256_LENGTH), False),
    "declared_capability": (sa.Boolean(), False),
    "installed_capability": (sa.Boolean(), False),
    "verified_capability": (sa.Boolean(), False),
    "verified_at": (_PIT_DATETIME, True),
    "verified_until": (_PIT_DATETIME, True),
    "authorized_capability": (sa.Boolean(), False),
    "authorized_at": (_PIT_DATETIME, True),
    "authorized_until": (_PIT_DATETIME, True),
    "effective_from": (_PIT_DATETIME, False),
    "effective_until": (_PIT_DATETIME, True),
    "created_at": (_PIT_DATETIME, False),
}
_CHECKS = {
    "ck_md_capability_ledger_capability_nonempty": "length(capability_id) > 0",
    "ck_md_capability_ledger_revision_positive": "revision >= 1",
    "ck_md_capability_ledger_descriptor_sha256_length": (
        f"length(descriptor_sha256) = {_SHA256_LENGTH}"
    ),
    "ck_md_capability_ledger_evidence_sha256_length": f"length(evidence_sha256) = {_SHA256_LENGTH}",
    "ck_md_capability_ledger_effective_window": (
        "effective_until IS NULL OR effective_until > effective_from"
    ),
    "ck_md_capability_ledger_install_requires_declaration": (
        "installed_capability = false OR declared_capability = true"
    ),
    "ck_md_capability_ledger_verification_state": (
        "(verified_capability = false AND verified_at IS NULL AND verified_until IS NULL) "
        "OR (verified_capability = true AND installed_capability = true "
        "AND verified_at IS NOT NULL AND verified_until IS NOT NULL "
        "AND verified_until > verified_at)"
    ),
    "ck_md_capability_ledger_authorization_state": (
        "(authorized_capability = false AND authorized_at IS NULL "
        "AND authorized_until IS NULL) OR "
        "(authorized_capability = true AND verified_capability = true "
        "AND authorized_at IS NOT NULL AND authorized_until IS NOT NULL "
        "AND authorized_until > authorized_at)"
    ),
}


def _is_offline() -> bool:
    return context.is_offline_mode()


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Keep capability-schema DDL bounded and explicit on MySQL."""
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
            "MARKET_DATA_CAPABILITY_LEDGER_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_CAPABILITY_LEDGER_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _normalized_expression(expression: object) -> str:
    """Normalize only known dialect rendering differences for named checks."""
    normalized = "".join(str(expression).split()).lower().replace('"', "").replace("`", "")
    normalized = re.sub(r"::(?:text|charactervarying|varchar)(?:\[\])?", "", normalized)
    normalized = re.sub(r"_(?:utf8mb4|utf8)(?=')", "", normalized)
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


def _require_absent_or_exact_table(bind: sa.Connection) -> bool:
    """Return whether a startup-created ledger table matches the reviewed shape."""
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
    if (
        set(columns) != set(_COLUMN_SPECS)
        or invalid_columns
        or primary_key != ("id",)
        or unique_constraints.get("uq_md_capability_ledger_revision")
        != ("capability_id", "revision")
        or indexes.get(_INDEX) != (("capability_id", "effective_from", "effective_until"), False)
        or missing_checks
        or invalid_checks
    ):
        raise RuntimeError(
            f"{_SCHEMA_DRIFT}: {{"
            f"'missing_columns': {sorted(set(_COLUMN_SPECS) - set(columns))}, "
            f"'invalid_columns': {invalid_columns}, "
            f"'primary_key': {primary_key}, "
            f"'unique': {unique_constraints.get('uq_md_capability_ledger_revision')}, "
            f"'index': {indexes.get(_INDEX)}, "
            f"'missing_checks': {sorted(missing_checks)}, "
            f"'invalid_checks': {invalid_checks}"
            "}"
        )
    return True


def _create_table() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=192), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("descriptor_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("declared_capability", sa.Boolean(), nullable=False),
        sa.Column("installed_capability", sa.Boolean(), nullable=False),
        sa.Column("verified_capability", sa.Boolean(), nullable=False),
        sa.Column("verified_at", _PIT_DATETIME, nullable=True),
        sa.Column("verified_until", _PIT_DATETIME, nullable=True),
        sa.Column("authorized_capability", sa.Boolean(), nullable=False),
        sa.Column("authorized_at", _PIT_DATETIME, nullable=True),
        sa.Column("authorized_until", _PIT_DATETIME, nullable=True),
        sa.Column("effective_from", _PIT_DATETIME, nullable=False),
        sa.Column("effective_until", _PIT_DATETIME, nullable=True),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability_id", "revision", name="uq_md_capability_ledger_revision"),
        *(sa.CheckConstraint(expression, name=name) for name, expression in _CHECKS.items()),
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["capability_id", "effective_from", "effective_until"],
    )


def upgrade() -> None:
    """Create an empty durable capability ledger without granting any route."""
    if _is_offline():
        _create_table()
        return
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_table(bind):
            _create_table()


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    if bind.execute(sa.select(table.c.id).limit(1)).scalar() is not None:
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: capability attestations exist")


def _lock_for_downgrade(bind: sa.Connection) -> None:
    """Block PostgreSQL writers while the irreversible empty check runs."""
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"LOCK TABLE {_TABLE} IN ACCESS EXCLUSIVE MODE"))


def downgrade() -> None:
    """Drop only an empty attestation table after an online safety check."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove table empty")
    bind = op.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        # MySQL DDL implicitly commits.  GET_LOCK only serializes migration
        # processes; normal application writers do not take it, so an insert
        # could race the empty-table proof and be erased by DROP.  Keep an
        # append-only attestation table irreversible on MySQL until a future
        # writer-participating fence can prove this transition safe.
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: MySQL cannot atomically prove the ledger empty")
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_table(bind):
            return
        _lock_for_downgrade(bind)
        _assert_downgrade_safe(bind)
        op.drop_index(_INDEX, table_name=_TABLE)
        op.drop_table(_TABLE)
