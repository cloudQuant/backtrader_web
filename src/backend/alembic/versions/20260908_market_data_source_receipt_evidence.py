"""Expand source receipts with separated provider-call and query evidence.

Revision ID: 20260908_market_data_source_receipt_evidence
Revises: 20260908_market_data_visibility_anchor
Create Date: 2026-09-08

The existing ``request_fingerprint_sha256`` column remains the public query
fingerprint.  This revision adds nullable compatibility columns for the
per-attempt provider request ID, the full outbound provider DTO digest, and an
explicit query digest.  It deliberately does not backfill legacy immutable
receipts: a NULL triplet identifies records collected before this evidence
contract existed.
"""

# alembic-meta: estimated_rows=0; lock_kind=short

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_market_data_source_receipt_evidence"
down_revision = "20260908_market_data_visibility_anchor"
branch_labels = None
depends_on = None

_TABLE = "md_source_snapshots"
_SHA256_LENGTH = 64
_EVIDENCE_COLUMNS = {
    "provider_request_id": sa.String(length=128),
    "provider_request_fingerprint_sha256": sa.String(length=_SHA256_LENGTH),
    "query_fingerprint_sha256": sa.String(length=_SHA256_LENGTH),
}
_REQUEST_ID_CHECK = "ck_md_source_snapshot_provider_request_id_length"
_PROVIDER_FINGERPRINT_CHECK = "ck_md_source_snapshot_provider_request_fingerprint_sha256_length"
_QUERY_FINGERPRINT_CHECK = "ck_md_source_snapshot_query_fingerprint_sha256_length"
_EVIDENCE_STATE_CHECK = "ck_md_source_snapshot_provider_request_evidence_state"
_CHECKS = {
    _REQUEST_ID_CHECK: (
        "provider_request_id IS NULL OR "
        "(length(provider_request_id) >= 32 AND length(provider_request_id) <= 128)"
    ),
    _PROVIDER_FINGERPRINT_CHECK: (
        "provider_request_fingerprint_sha256 IS NULL OR "
        f"length(provider_request_fingerprint_sha256) = {_SHA256_LENGTH}"
    ),
    _QUERY_FINGERPRINT_CHECK: (
        f"query_fingerprint_sha256 IS NULL OR length(query_fingerprint_sha256) = {_SHA256_LENGTH}"
    ),
    _EVIDENCE_STATE_CHECK: (
        "(provider_request_id IS NULL AND "
        "provider_request_fingerprint_sha256 IS NULL AND "
        "query_fingerprint_sha256 IS NULL) OR "
        "(provider_request_id IS NOT NULL AND "
        "provider_request_fingerprint_sha256 IS NOT NULL AND "
        "query_fingerprint_sha256 IS NOT NULL)"
    ),
}
_REQUEST_ID_INDEX = "ix_md_source_snapshot_provider_request_id"
_REQUEST_ID_INDEX_COLUMNS = ("provider_id", "provider_request_id")
_REQUEST_ID_INDEX_UNIQUE = True
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.source_receipt_evidence"
_LOCK_TIMEOUT_SECONDS = 5


def _is_offline() -> bool:
    return context.is_offline_mode()


def _normalized_expression(expression: object) -> str:
    return "".join(str(expression).split()).lower()


def _require_table(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table(_TABLE):
        raise RuntimeError(
            "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_SCHEMA_UNREADY: md_source_snapshots missing"
        )


def _column_definitions(bind: sa.Connection) -> dict[str, dict[str, object]]:
    _require_table(bind)
    return {str(column["name"]): column for column in sa.inspect(bind).get_columns(_TABLE)}


def _assert_existing_column_compatible(
    column_name: str,
    definition: dict[str, object],
) -> None:
    column_type = definition["type"]
    expected_type = _EVIDENCE_COLUMNS[column_name]
    if (
        column_type._type_affinity is not expected_type._type_affinity
        or getattr(column_type, "length", None) != expected_type.length
        or not bool(definition.get("nullable"))
    ):
        raise RuntimeError(
            f"MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_SCHEMA_DRIFT: md_source_snapshots.{column_name}"
        )


def _ensure_columns(bind: sa.Connection) -> None:
    columns = _column_definitions(bind)
    for column_name, column_type in _EVIDENCE_COLUMNS.items():
        existing = columns.get(column_name)
        if existing is None:
            op.add_column(_TABLE, sa.Column(column_name, column_type, nullable=True))
            continue
        _assert_existing_column_compatible(column_name, existing)


def _observed_checks(bind: sa.Connection) -> dict[str, str]:
    return {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in sa.inspect(bind).get_check_constraints(_TABLE)
        if check.get("name")
    }


def _ensure_checks(bind: sa.Connection) -> None:
    observed = _observed_checks(bind)
    missing: dict[str, str] = {}
    for name, expression in _CHECKS.items():
        actual = observed.get(name)
        expected = _normalized_expression(expression)
        if actual is None:
            missing[name] = expression
        elif actual != expected:
            raise RuntimeError(
                f"MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_SCHEMA_DRIFT: {name}={actual!r}"
            )
    if not missing:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE) as batch:
            for name, expression in missing.items():
                batch.create_check_constraint(name, expression)
        return
    for name, expression in missing.items():
        op.create_check_constraint(name, _TABLE, expression)


def _ensure_request_id_index(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in inspector.get_indexes(_TABLE)
        if index.get("name")
    }
    uniques = {
        str(constraint["name"]): tuple(
            str(column) for column in constraint.get("column_names") or ()
        )
        for constraint in inspector.get_unique_constraints(_TABLE)
        if constraint.get("name")
    }
    expected = (_REQUEST_ID_INDEX_COLUMNS, _REQUEST_ID_INDEX_UNIQUE)
    actual = indexes.get(_REQUEST_ID_INDEX)
    if actual is not None:
        if actual != expected:
            raise RuntimeError(
                f"MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_SCHEMA_DRIFT: {_REQUEST_ID_INDEX}={actual!r}"
            )
        return
    unique_constraint = uniques.get(_REQUEST_ID_INDEX)
    if unique_constraint is not None:
        if unique_constraint != _REQUEST_ID_INDEX_COLUMNS:
            raise RuntimeError(
                "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_SCHEMA_DRIFT: "
                f"{_REQUEST_ID_INDEX}={unique_constraint!r}"
            )
        return
    op.create_index(
        _REQUEST_ID_INDEX,
        _TABLE,
        list(_REQUEST_ID_INDEX_COLUMNS),
        unique=_REQUEST_ID_INDEX_UNIQUE,
    )


def _request_id_index_or_constraint_names(bind: sa.Connection) -> tuple[set[str], set[str]]:
    """Return reflected index and unique-constraint names for portable teardown.

    PostgreSQL/MySQL expose a named unique index through ``get_indexes``;
    other backends may reflect the same database rule as a unique constraint.
    The upgrade accepts either authoritative representation, and downgrade
    must remove the one that actually exists before dropping its column.
    """
    inspector = sa.inspect(bind)
    indexes = {
        str(index["name"])
        for index in inspector.get_indexes(_TABLE)
        if index.get("name")
    }
    uniques = {
        str(constraint["name"])
        for constraint in inspector.get_unique_constraints(_TABLE)
        if constraint.get("name")
    }
    return indexes, uniques


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL with an explicit MySQL writer-drain precondition."""
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
            "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    columns = _column_definitions(bind)
    present = tuple(column for column in _EVIDENCE_COLUMNS if column in columns)
    if not present:
        return
    snapshots = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    populated = bind.execute(
        sa.select(snapshots.c.id)
        .where(sa.or_(*(snapshots.c[column].is_not(None) for column in present)))
        .limit(1)
    ).scalar()
    if populated is not None:
        raise RuntimeError(
            "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_DOWNGRADE_BLOCKED: "
            "provider-call evidence is immutable"
        )


def _drop_columns_and_constraints(bind: sa.Connection) -> None:
    columns = _column_definitions(bind)
    present_columns = tuple(column for column in _EVIDENCE_COLUMNS if column in columns)
    observed_checks = _observed_checks(bind)
    indexes, unique_constraints = _request_id_index_or_constraint_names(bind)
    if not present_columns:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE) as batch:
            if _REQUEST_ID_INDEX in indexes:
                batch.drop_index(_REQUEST_ID_INDEX)
            elif _REQUEST_ID_INDEX in unique_constraints:
                batch.drop_constraint(_REQUEST_ID_INDEX, type_="unique")
            for name in _CHECKS:
                if name in observed_checks:
                    batch.drop_constraint(name, type_="check")
            for column in present_columns:
                batch.drop_column(column)
        return
    if _REQUEST_ID_INDEX in indexes:
        op.drop_index(_REQUEST_ID_INDEX, table_name=_TABLE)
    elif _REQUEST_ID_INDEX in unique_constraints:
        op.drop_constraint(_REQUEST_ID_INDEX, _TABLE, type_="unique")
    for name in _CHECKS:
        if name in observed_checks:
            op.drop_constraint(name, _TABLE, type_="check")
    for column in present_columns:
        op.drop_column(_TABLE, column)


def upgrade() -> None:
    """Add nullable, independently named evidence fields without a backfill."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot verify the existing immutable receipt schema"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _ensure_columns(bind)
        _ensure_checks(bind)
        _ensure_request_id_index(bind)


def downgrade() -> None:
    """Drop only empty compatibility columns; never erase immutable evidence."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_DOWNGRADE_BLOCKED: "
            "offline SQL cannot prove provider-call evidence is absent"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _assert_downgrade_safe(bind)
        _drop_columns_and_constraints(bind)
