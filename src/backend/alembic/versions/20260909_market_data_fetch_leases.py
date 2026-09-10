"""Add durable cross-worker market-data fetch lease fencing.

Revision ID: 20260909_market_data_fetch_leases
Revises: 20260908_market_data_source_governance
Create Date: 2026-09-09

The table holds only mutable coordination state.  It never replaces the
append-only source snapshot/publication evidence tables, and downgrade refuses
to erase an issued fencing generation.
"""

# alembic-meta: estimated_rows=0; lock_kind=short

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import context, op

revision = "20260909_market_data_fetch_leases"
down_revision = "20260908_market_data_source_governance"
branch_labels = None
depends_on = None

_TABLE = "md_fetch_leases"
_SOURCE_SNAPSHOTS = "md_source_snapshots"
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_LEASE_EXPIRY_INDEX = "ix_md_fetch_lease_expires_at"
_LEASE_COLUMN_SPECS: dict[str, tuple[sa.types.TypeEngine[Any], bool]] = {
    "lease_key_sha256": (sa.String(length=_SHA256_LENGTH), False),
    "owner_token": (sa.String(length=64), True),
    "fence_token": (sa.BigInteger(), False),
    "expires_at": (_PIT_DATETIME, True),
    "created_at": (_PIT_DATETIME, False),
    "updated_at": (_PIT_DATETIME, False),
    "released_at": (_PIT_DATETIME, True),
}
_LEASE_CHECK_EXPRESSIONS = {
    "ck_md_fetch_lease_key_sha256_length": f"length(lease_key_sha256) = {_SHA256_LENGTH}",
    "ck_md_fetch_lease_fence_token_positive": "fence_token >= 1",
    "ck_md_fetch_lease_owner_expiry_state": (
        "(owner_token IS NULL AND expires_at IS NULL) OR "
        "(owner_token IS NOT NULL AND expires_at IS NOT NULL)"
    ),
}
_SOURCE_BINDING_COLUMNS: dict[str, sa.types.TypeEngine[object]] = {
    "fetch_lease_key_sha256": sa.String(length=_SHA256_LENGTH),
    "fetch_lease_fence_token": sa.BigInteger(),
}
_SOURCE_BINDING_CHECK = "ck_md_source_snapshot_fetch_lease_generation_state"
_SOURCE_BINDING_CHECK_EXPRESSION = (
    "(fetch_lease_key_sha256 IS NULL AND fetch_lease_fence_token IS NULL) OR "
    "(fetch_lease_key_sha256 IS NOT NULL AND fetch_lease_fence_token IS NOT NULL AND "
    f"length(fetch_lease_key_sha256) = {_SHA256_LENGTH} AND fetch_lease_fence_token >= 1)"
)
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_FETCH_LEASE_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.fetch_leases"
_LOCK_TIMEOUT_SECONDS = 5


def _is_offline() -> bool:
    return context.is_offline_mode()


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL with an explicit MySQL writer-drain precondition."""
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
            "MARKET_DATA_FETCH_LEASE_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_FETCH_LEASE_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _require_absent_or_exact_table(bind: sa.Connection) -> bool:
    """Return whether a complete startup-created table already exists.

    ``Base.metadata.create_all`` can precede Alembic stamping in development.
    Accept only the full reviewed shape; a partial same-named table must not be
    mistaken for a successful coordination migration.
    """
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return False
    columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ()
    )
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
    preserve_timestamp_timezone = bind.dialect.name == "postgresql"
    preserve_timestamp_precision = bind.dialect.name == "mysql"
    invalid_columns: dict[str, dict[str, object]] = {}
    for column_name, (expected_type, expected_nullable) in _LEASE_COLUMN_SPECS.items():
        actual = columns.get(column_name)
        if actual is None:
            continue
        expected_signature = _type_signature(
            expected_type.dialect_impl(bind.dialect),
            preserve_timestamp_timezone=preserve_timestamp_timezone,
            preserve_timestamp_precision=preserve_timestamp_precision,
        )
        actual_signature = _type_signature(
            actual["type"],
            preserve_timestamp_timezone=preserve_timestamp_timezone,
            preserve_timestamp_precision=preserve_timestamp_precision,
        )
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
    normalized_expected_checks = {
        name: _normalized_expression(expression)
        for name, expression in _LEASE_CHECK_EXPRESSIONS.items()
    }
    missing_columns = set(_LEASE_COLUMN_SPECS) - set(columns)
    missing_checks = set(normalized_expected_checks) - set(checks)
    invalid_checks = {
        name: {"actual": checks[name], "expected": expression}
        for name, expression in normalized_expected_checks.items()
        if name in checks and checks[name] != expression
    }
    if (
        set(columns) != set(_LEASE_COLUMN_SPECS)
        or invalid_columns
        or primary_key != ("lease_key_sha256",)
        or indexes.get(_LEASE_EXPIRY_INDEX) != (("expires_at",), False)
        or missing_checks
        or invalid_checks
    ):
        details = {
            "missing_columns": sorted(missing_columns),
            "invalid_columns": invalid_columns,
            "primary_key": primary_key,
            "index": indexes.get(_LEASE_EXPIRY_INDEX),
            "missing_checks": sorted(missing_checks),
            "invalid_checks": invalid_checks,
        }
        raise RuntimeError(f"MARKET_DATA_FETCH_LEASE_SCHEMA_DRIFT: {details}")
    return True


def _normalized_expression(expression: object) -> str:
    normalized = "".join(str(expression).split()).lower()
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
    preserve_timestamp_timezone: bool,
    preserve_timestamp_precision: bool,
) -> tuple[type[object], int | None, bool | None, int | None]:
    """Return a dialect-aware type signature for startup-schema drift checks."""
    timezone_mode = (
        bool(getattr(type_, "timezone", False))
        if preserve_timestamp_timezone and isinstance(type_, sa.DateTime)
        else None
    )
    precision = (
        getattr(type_, "fsp", None)
        if preserve_timestamp_precision and isinstance(type_, sa.DateTime)
        else None
    )
    return type_._type_affinity, getattr(type_, "length", None), timezone_mode, precision


def _require_source_snapshots(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table(_SOURCE_SNAPSHOTS):
        raise RuntimeError("MARKET_DATA_FETCH_LEASE_SCHEMA_UNREADY: md_source_snapshots missing")


def _source_snapshot_columns(bind: sa.Connection) -> dict[str, dict[str, object]]:
    _require_source_snapshots(bind)
    return {
        str(column["name"]): column for column in sa.inspect(bind).get_columns(_SOURCE_SNAPSHOTS)
    }


def _ensure_source_binding_columns(bind: sa.Connection) -> None:
    columns = _source_snapshot_columns(bind)
    for column_name, expected_type in _SOURCE_BINDING_COLUMNS.items():
        existing = columns.get(column_name)
        if existing is None:
            op.add_column(
                _SOURCE_SNAPSHOTS,
                sa.Column(column_name, expected_type, nullable=True),
            )
            continue
        actual_type = existing["type"]
        if (
            actual_type._type_affinity is not expected_type._type_affinity
            or getattr(actual_type, "length", None) != getattr(expected_type, "length", None)
            or not bool(existing.get("nullable"))
        ):
            raise RuntimeError(
                f"MARKET_DATA_FETCH_LEASE_SCHEMA_DRIFT: {_SOURCE_SNAPSHOTS}.{column_name}"
            )


def _ensure_source_binding_check(bind: sa.Connection) -> None:
    observed = {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in sa.inspect(bind).get_check_constraints(_SOURCE_SNAPSHOTS)
        if check.get("name")
    }
    actual = observed.get(_SOURCE_BINDING_CHECK)
    expected = _normalized_expression(_SOURCE_BINDING_CHECK_EXPRESSION)
    if actual is not None:
        if actual != expected:
            raise RuntimeError(
                f"MARKET_DATA_FETCH_LEASE_SCHEMA_DRIFT: {_SOURCE_BINDING_CHECK}={actual!r}"
            )
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_SOURCE_SNAPSHOTS) as batch:
            batch.create_check_constraint(_SOURCE_BINDING_CHECK, _SOURCE_BINDING_CHECK_EXPRESSION)
        return
    op.create_check_constraint(
        _SOURCE_BINDING_CHECK,
        _SOURCE_SNAPSHOTS,
        _SOURCE_BINDING_CHECK_EXPRESSION,
    )


def _assert_source_binding_downgrade_safe(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table(_SOURCE_SNAPSHOTS):
        return
    columns = _source_snapshot_columns(bind)
    present = tuple(column for column in _SOURCE_BINDING_COLUMNS if column in columns)
    if not present:
        return
    table = sa.Table(_SOURCE_SNAPSHOTS, sa.MetaData(), autoload_with=bind)
    populated = bind.execute(
        sa.select(table.c.id)
        .where(sa.or_(*(table.c[column].is_not(None) for column in present)))
        .limit(1)
    ).scalar()
    if populated is not None:
        raise RuntimeError(
            "MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED: "
            "source-receipt lease generations are immutable"
        )


def _drop_source_binding_columns_and_constraint(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table(_SOURCE_SNAPSHOTS):
        return
    columns = _source_snapshot_columns(bind)
    present = tuple(column for column in _SOURCE_BINDING_COLUMNS if column in columns)
    if not present:
        return
    checks = {
        str(check["name"])
        for check in sa.inspect(bind).get_check_constraints(_SOURCE_SNAPSHOTS)
        if check.get("name")
    }
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_SOURCE_SNAPSHOTS) as batch:
            if _SOURCE_BINDING_CHECK in checks:
                batch.drop_constraint(_SOURCE_BINDING_CHECK, type_="check")
            for column in present:
                batch.drop_column(column)
        return
    if _SOURCE_BINDING_CHECK in checks:
        op.drop_constraint(_SOURCE_BINDING_CHECK, _SOURCE_SNAPSHOTS, type_="check")
    for column in present:
        op.drop_column(_SOURCE_SNAPSHOTS, column)


def _lock_for_downgrade(bind: sa.Connection) -> None:
    """Prevent PostgreSQL evidence writers from racing irreversible checks."""
    if bind.dialect.name != "postgresql":
        return
    tables = [_SOURCE_SNAPSHOTS]
    if sa.inspect(bind).has_table(_TABLE):
        tables.append(_TABLE)
    bind.execute(sa.text(f"LOCK TABLE {', '.join(tables)} IN ACCESS EXCLUSIVE MODE"))


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table(_TABLE):
        return
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    issued = bind.execute(sa.select(table.c.lease_key_sha256).limit(1)).scalar()
    if issued is not None:
        raise RuntimeError(
            "MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED: issued fence generations must not be erased"
        )


def upgrade() -> None:
    """Create portable owner/fence state for distributed provider work."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_FETCH_LEASE_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot verify durable fencing schema state"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        if not _require_absent_or_exact_table(bind):
            op.create_table(
                _TABLE,
                *(
                    sa.Column(column_name, type_, nullable=nullable)
                    for column_name, (type_, nullable) in _LEASE_COLUMN_SPECS.items()
                ),
                sa.CheckConstraint(
                    _LEASE_CHECK_EXPRESSIONS["ck_md_fetch_lease_key_sha256_length"],
                    name="ck_md_fetch_lease_key_sha256_length",
                ),
                sa.CheckConstraint(
                    _LEASE_CHECK_EXPRESSIONS["ck_md_fetch_lease_fence_token_positive"],
                    name="ck_md_fetch_lease_fence_token_positive",
                ),
                sa.CheckConstraint(
                    _LEASE_CHECK_EXPRESSIONS["ck_md_fetch_lease_owner_expiry_state"],
                    name="ck_md_fetch_lease_owner_expiry_state",
                ),
                sa.PrimaryKeyConstraint("lease_key_sha256"),
            )
            op.create_index(_LEASE_EXPIRY_INDEX, _TABLE, ["expires_at"], unique=False)
        _ensure_source_binding_columns(bind)
        _ensure_source_binding_check(bind)


def downgrade() -> None:
    """Drop only an unused coordination table; never reset live fence tokens."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED: "
            "offline SQL cannot prove issued fence generations are absent"
        )
    bind = op.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        # MySQL-family DDL implicitly commits.  The migration GET_LOCK is not
        # acquired by normal receipt writers, so it cannot make the empty
        # proof and subsequent DROP atomic.  Lease generations are evidence;
        # refuse rollback rather than risk erasing a concurrent generation.
        raise RuntimeError(
            "MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED: "
            "MySQL cannot atomically prove lease evidence is absent"
        )
    with _ddl_maintenance_fence():
        _lock_for_downgrade(bind)
        _assert_source_binding_downgrade_safe(bind)
        _assert_downgrade_safe(bind)
        _drop_source_binding_columns_and_constraint(bind)
        if sa.inspect(bind).has_table(_TABLE):
            op.drop_index(_LEASE_EXPIRY_INDEX, table_name=_TABLE)
            op.drop_table(_TABLE)
