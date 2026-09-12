"""Make source authorization and calendar governance visible to v2 readers.

Revision ID: 20260908_market_data_source_governance
Revises: 20260908_market_data_source_receipt_evidence
Create Date: 2026-09-08

The expanded source-request receipt revision kept historical fields nullable.
This follow-up adds nullable state columns that distinguish registry-validated
receipts from explicit compatibility writes, plus registry-backed provenance
anchors for calendar snapshots.  Legacy rows deliberately remain NULL and
cannot qualify as current-authorized v2 facts until re-imported or collected
through the governed path.
"""

# alembic-meta: estimated_rows=0; lock_kind=short

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_market_data_source_governance"
down_revision = "20260908_market_data_source_receipt_evidence"
branch_labels = None
depends_on = None

_SHA256_LENGTH = 64
_SOURCE_SNAPSHOTS = "md_source_snapshots"
_CALENDAR_SNAPSHOTS = "md_calendar_snapshots"
_TABLE_COLUMNS: Mapping[str, Mapping[str, sa.types.TypeEngine[object]]] = {
    _SOURCE_SNAPSHOTS: {
        "source_authorization_state": sa.String(length=32),
        "source_authorization_descriptor_sha256": sa.String(length=_SHA256_LENGTH),
    },
    _CALENDAR_SNAPSHOTS: {
        "source_registry_id": sa.String(length=128),
        "source_governance_state": sa.String(length=32),
        "source_governance_descriptor_sha256": sa.String(length=_SHA256_LENGTH),
    },
}
_TABLE_CHECKS: Mapping[str, Mapping[str, str]] = {
    _SOURCE_SNAPSHOTS: {
        "ck_md_source_snapshot_source_authorization_state": (
            "source_authorization_state IS NULL OR "
            "source_authorization_state IN ('VERIFIED', 'UNVERIFIED_COMPATIBILITY')"
        ),
        "ck_md_srcsnap_src_auth_desc_sha256_len": (
            "source_authorization_descriptor_sha256 IS NULL OR "
            f"length(source_authorization_descriptor_sha256) = {_SHA256_LENGTH}"
        ),
        "ck_md_source_snapshot_source_authorization_evidence_state": (
            "(source_authorization_state IS NULL AND "
            "source_authorization_descriptor_sha256 IS NULL) OR "
            "(source_authorization_state = 'VERIFIED' AND "
            "source_authorization_descriptor_sha256 IS NOT NULL) OR "
            "(source_authorization_state = 'UNVERIFIED_COMPATIBILITY' AND "
            "source_authorization_descriptor_sha256 IS NULL)"
        ),
    },
    _CALENDAR_SNAPSHOTS: {
        "ck_md_calendar_snapshot_source_registry_id_length": (
            "source_registry_id IS NULL OR "
            "(length(source_registry_id) >= 1 AND length(source_registry_id) <= 128)"
        ),
        "ck_md_calendar_snapshot_source_governance_state": (
            "source_governance_state IS NULL OR "
            "source_governance_state IN ('VERIFIED', 'UNVERIFIED_COMPATIBILITY')"
        ),
        "ck_md_calsnap_src_gov_desc_sha256_len": (
            "source_governance_descriptor_sha256 IS NULL OR "
            f"length(source_governance_descriptor_sha256) = {_SHA256_LENGTH}"
        ),
        "ck_md_calendar_snapshot_source_governance_evidence_state": (
            "(source_registry_id IS NULL AND source_governance_state IS NULL AND "
            "source_governance_descriptor_sha256 IS NULL) OR "
            "(source_registry_id IS NOT NULL AND source_governance_state = 'VERIFIED' AND "
            "source_governance_descriptor_sha256 IS NOT NULL) OR "
            "(source_registry_id IS NOT NULL AND "
            "source_governance_state = 'UNVERIFIED_COMPATIBILITY' AND "
            "source_governance_descriptor_sha256 IS NULL)"
        ),
    },
}
_LEGACY_TABLE_CHECK_NAMES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    _SOURCE_SNAPSHOTS: {
        "ck_md_srcsnap_src_auth_desc_sha256_len": (
            "ck_md_source_snapshot_source_authorization_descriptor_sha256_length",
        ),
    },
    _CALENDAR_SNAPSHOTS: {
        "ck_md_calsnap_src_gov_desc_sha256_len": (
            "ck_md_calendar_snapshot_source_governance_descriptor_sha256_length",
        ),
    },
}
_CALENDAR_SOURCE_INDEX = "ix_md_calendar_snapshot_source_registry"
_CALENDAR_SOURCE_INDEX_COLUMNS = (
    "source_registry_id",
    "calendar_code",
    "calendar_version",
)
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_SOURCE_GOVERNANCE_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.source_governance"
_LOCK_TIMEOUT_SECONDS = 5


def _is_offline() -> bool:
    return context.is_offline_mode()


def _normalized_expression(expression: object) -> str:
    return "".join(str(expression).split()).lower()


def _require_table(bind: sa.Connection, table_name: str) -> None:
    if not sa.inspect(bind).has_table(table_name):
        raise RuntimeError(f"MARKET_DATA_SOURCE_GOVERNANCE_SCHEMA_UNREADY: {table_name} missing")


def _column_definitions(bind: sa.Connection, table_name: str) -> dict[str, dict[str, object]]:
    _require_table(bind, table_name)
    return {str(column["name"]): column for column in sa.inspect(bind).get_columns(table_name)}


def _assert_existing_column_compatible(
    *,
    table_name: str,
    column_name: str,
    definition: Mapping[str, object],
) -> None:
    expected_type = _TABLE_COLUMNS[table_name][column_name]
    actual_type = definition["type"]
    if (
        actual_type._type_affinity is not expected_type._type_affinity
        or getattr(actual_type, "length", None) != expected_type.length
        or not bool(definition.get("nullable"))
    ):
        raise RuntimeError(
            f"MARKET_DATA_SOURCE_GOVERNANCE_SCHEMA_DRIFT: {table_name}.{column_name}"
        )


def _ensure_columns(bind: sa.Connection, table_name: str) -> None:
    columns = _column_definitions(bind, table_name)
    for column_name, column_type in _TABLE_COLUMNS[table_name].items():
        existing = columns.get(column_name)
        if existing is None:
            op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))
            continue
        _assert_existing_column_compatible(
            table_name=table_name,
            column_name=column_name,
            definition=existing,
        )


def _observed_checks(bind: sa.Connection, table_name: str) -> dict[str, str]:
    return {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in sa.inspect(bind).get_check_constraints(table_name)
        if check.get("name")
    }


def _matching_check_name(
    observed: Mapping[str, str],
    *,
    table_name: str,
    name: str,
    expression: str,
) -> str | None:
    """Accept an equivalent legacy name from an unreleased SQLite candidate."""
    expected = _normalized_expression(expression)
    aliases = _LEGACY_TABLE_CHECK_NAMES.get(table_name, {}).get(name, ())
    for candidate_name in (name, *aliases):
        actual = observed.get(candidate_name)
        if actual is None:
            continue
        if actual != expected:
            raise RuntimeError(
                f"MARKET_DATA_SOURCE_GOVERNANCE_SCHEMA_DRIFT: {candidate_name}={actual!r}"
            )
        return candidate_name
    return None


def _ensure_checks(bind: sa.Connection, table_name: str) -> None:
    observed = _observed_checks(bind, table_name)
    missing: dict[str, str] = {}
    for name, expression in _TABLE_CHECKS[table_name].items():
        if (
            _matching_check_name(
                observed,
                table_name=table_name,
                name=name,
                expression=expression,
            )
            is None
        ):
            missing[name] = expression
    if not missing:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch:
            for name, expression in missing.items():
                batch.create_check_constraint(name, expression)
        return
    for name, expression in missing.items():
        op.create_check_constraint(name, table_name, expression)


def _ensure_calendar_source_index(bind: sa.Connection) -> None:
    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in sa.inspect(bind).get_indexes(_CALENDAR_SNAPSHOTS)
        if index.get("name")
    }
    expected = (_CALENDAR_SOURCE_INDEX_COLUMNS, False)
    actual = indexes.get(_CALENDAR_SOURCE_INDEX)
    if actual is None:
        op.create_index(
            _CALENDAR_SOURCE_INDEX,
            _CALENDAR_SNAPSHOTS,
            list(_CALENDAR_SOURCE_INDEX_COLUMNS),
            unique=False,
        )
        return
    if actual != expected:
        raise RuntimeError(
            f"MARKET_DATA_SOURCE_GOVERNANCE_SCHEMA_DRIFT: {_CALENDAR_SOURCE_INDEX}={actual!r}"
        )


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
            "MARKET_DATA_SOURCE_GOVERNANCE_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_SOURCE_GOVERNANCE_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    populated_tables: list[str] = []
    for table_name, columns in _TABLE_COLUMNS.items():
        observed = _column_definitions(bind, table_name)
        present = tuple(column for column in columns if column in observed)
        if not present:
            continue
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        populated = bind.execute(
            sa.select(table.c.id)
            .where(sa.or_(*(table.c[column].is_not(None) for column in present)))
            .limit(1)
        ).scalar()
        if populated is not None:
            populated_tables.append(table_name)
    if populated_tables:
        raise RuntimeError(
            "MARKET_DATA_SOURCE_GOVERNANCE_DOWNGRADE_BLOCKED: "
            "source-governance evidence is immutable"
        )


def _drop_table_columns_and_constraints(bind: sa.Connection, table_name: str) -> None:
    columns = _column_definitions(bind, table_name)
    present_columns = tuple(column for column in _TABLE_COLUMNS[table_name] if column in columns)
    if not present_columns:
        return
    observed_checks = _observed_checks(bind, table_name)
    indexes = {
        str(index["name"])
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch:
            if table_name == _CALENDAR_SNAPSHOTS and _CALENDAR_SOURCE_INDEX in indexes:
                batch.drop_index(_CALENDAR_SOURCE_INDEX)
            for name in _TABLE_CHECKS[table_name]:
                aliases = _LEGACY_TABLE_CHECK_NAMES.get(table_name, {}).get(name, ())
                for candidate_name in (name, *aliases):
                    if candidate_name in observed_checks:
                        batch.drop_constraint(candidate_name, type_="check")
            for column in present_columns:
                batch.drop_column(column)
        return
    if table_name == _CALENDAR_SNAPSHOTS and _CALENDAR_SOURCE_INDEX in indexes:
        op.drop_index(_CALENDAR_SOURCE_INDEX, table_name=table_name)
    for name in _TABLE_CHECKS[table_name]:
        aliases = _LEGACY_TABLE_CHECK_NAMES.get(table_name, {}).get(name, ())
        for candidate_name in (name, *aliases):
            if candidate_name in observed_checks:
                op.drop_constraint(candidate_name, table_name, type_="check")
    for column in present_columns:
        op.drop_column(table_name, column)


def upgrade() -> None:
    """Add compatibility-safe source trust state without a legacy backfill."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_SOURCE_GOVERNANCE_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot verify immutable source-receipt schemas"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        for table_name in _TABLE_COLUMNS:
            _ensure_columns(bind, table_name)
            _ensure_checks(bind, table_name)
        _ensure_calendar_source_index(bind)


def downgrade() -> None:
    """Never drop states that would erase active source-governance evidence."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_SOURCE_GOVERNANCE_DOWNGRADE_BLOCKED: "
            "offline SQL cannot prove governed evidence is absent"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _assert_downgrade_safe(bind)
        # Calendar constraints reference the new columns, so remove that
        # table first.  Source snapshots are otherwise independent.
        _drop_table_columns_and_constraints(bind, _CALENDAR_SNAPSHOTS)
        _drop_table_columns_and_constraints(bind, _SOURCE_SNAPSHOTS)
