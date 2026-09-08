"""Allow reviewed logical datasets to share normalized market facts.

Revision ID: 20260908_market_data_shared_dataset_bindings
Revises: 20260908_market_data_observations
Create Date: 2026-09-08

This candidate revision changes only the catalog uniqueness invariant.  It does
not move, rewrite, or fetch market facts.  It must be jointly integrated with
the Iteration 196 migration head before any deployment; this file has not been
applied to an application database by this iteration task.
"""

# alembic-meta: estimated_rows=0; lock_kind=long

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_market_data_shared_dataset_bindings"
down_revision = "20260908_market_data_observations"
branch_labels = None
depends_on = None

_TABLE = "dg_dataset_storages"
_BINDING_UNIQUE = "uq_dg_dataset_storage_target_table"
_LEGACY_BINDING_COLUMNS = ("storage_target_id", "physical_table")
_DATASET_AWARE_BINDING_COLUMNS = (
    "storage_target_id",
    "physical_table",
    "dataset_id",
)
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_SHARED_BINDING_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.shared_dataset_bindings"
_LOCK_TIMEOUT_SECONDS = 5


def _is_offline() -> bool:
    return context.is_offline_mode()


def _table_exists() -> bool:
    if _is_offline():
        return False
    return sa.inspect(op.get_bind()).has_table(_TABLE)


def _named_unique_columns() -> dict[str, frozenset[tuple[str, ...]]]:
    """Return named uniqueness contracts across constraint/index reflection."""
    inspector = sa.inspect(op.get_bind())
    result: dict[str, set[tuple[str, ...]]] = {}
    for constraint in inspector.get_unique_constraints(_TABLE) or ():
        name = constraint.get("name")
        columns = constraint.get("column_names")
        if name and columns:
            result.setdefault(str(name), set()).add(tuple(str(column) for column in columns))
    for index in inspector.get_indexes(_TABLE) or ():
        name = index.get("name")
        columns = index.get("column_names")
        if name and bool(index.get("unique")) and columns:
            result.setdefault(str(name), set()).add(tuple(str(column) for column in columns))
    return {name: frozenset(columns) for name, columns in result.items()}


def _binding_unique_state() -> str:
    """Classify the exact named constraint required by this revision."""
    if not _table_exists():
        raise RuntimeError("MARKET_DATA_SHARED_BINDING_SCHEMA_UNREADY: dg_dataset_storages missing")
    definitions = _named_unique_columns().get(_BINDING_UNIQUE, frozenset())
    if definitions == frozenset({_LEGACY_BINDING_COLUMNS}):
        return "legacy"
    if definitions == frozenset({_DATASET_AWARE_BINDING_COLUMNS}):
        return "dataset_aware"
    if not definitions:
        raise RuntimeError(
            "MARKET_DATA_SHARED_BINDING_SCHEMA_UNREADY: uq_dg_dataset_storage_target_table missing"
        )
    raise RuntimeError(
        "MARKET_DATA_SHARED_BINDING_SCHEMA_DRIFT: "
        f"uq_dg_dataset_storage_target_table={sorted(definitions)!r}"
    )


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound table-rebuild DDL with dialect-aware operational preconditions.

    PostgreSQL can roll back the replacement in one transaction, but still
    receives a short lock timeout. MySQL DDL commits implicitly: an advisory
    lock serializes migration runners, while the explicit environment fence is
    an executable release gate that the deploy runner may set only after the
    API, collectors, and bootstrap writers have been stopped.  The migration
    cannot prove that external drain itself, so it fails closed without that
    operator-provided fence instead of performing a partially atomic change.
    """
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_SECONDS}s'"))
        yield
        return
    if dialect_name != "mysql":
        yield
        return

    if os.getenv(_MYSQL_MAINTENANCE_FENCE_ENV) != "confirmed":
        raise RuntimeError(
            "MARKET_DATA_SHARED_BINDING_MAINTENANCE_FENCE_REQUIRED: "
            "stop market-data writers and set "
            f"{_MYSQL_MAINTENANCE_FENCE_ENV}=confirmed before MySQL DDL"
        )
    bind.execute(sa.text(f"SET SESSION lock_wait_timeout = {_LOCK_TIMEOUT_SECONDS}"))
    acquired = bind.execute(
        sa.text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
        {
            "lock_name": _MYSQL_MIGRATION_LOCK_NAME,
            "timeout_seconds": _LOCK_TIMEOUT_SECONDS,
        },
    ).scalar_one()
    if acquired != 1:
        raise RuntimeError(
            "MARKET_DATA_SHARED_BINDING_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the MySQL migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_MIGRATION_LOCK_NAME}
        )


def _replace_binding_unique(*, new_columns: tuple[str, ...]) -> None:
    """Use batch DDL after the required dialect-specific maintenance fence."""
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_BINDING_UNIQUE, type_="unique")
        batch.create_unique_constraint(_BINDING_UNIQUE, list(new_columns))


def _assert_downgrade_has_no_shared_bindings() -> None:
    """Reject a rollback before it would make two datasets mutually exclusive."""
    shared_group_count = int(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT COUNT(*) FROM ("
                " SELECT 1"
                " FROM dg_dataset_storages"
                " GROUP BY storage_target_id, physical_table"
                " HAVING COUNT(DISTINCT dataset_id) > 1"
                ") AS market_data_shared_binding_groups"
            )
        )
        .scalar_one()
    )
    if shared_group_count:
        raise RuntimeError(
            "MARKET_DATA_SHARED_BINDING_DOWNGRADE_BLOCKED: "
            "shared physical-table bindings must be removed or migrated before rollback"
        )


def upgrade() -> None:
    """Make logical dataset ownership part of a physical-table binding key."""
    if _is_offline():
        # SQLite (and Alembic batch mode generally) must reflect the current
        # table definition before it can rebuild a table.  Rendering a script
        # in ``--sql`` mode supplies a mock connection instead, so emitting
        # partial DDL here would falsely claim that a portable offline upgrade
        # exists.  Keep this candidate migration explicitly online-only until
        # a reviewed, dialect-specific offline DDL plan is provided.
        raise RuntimeError(
            "MARKET_DATA_SHARED_BINDING_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot safely rebuild dg_dataset_storages"
        )

    with _ddl_maintenance_fence():
        state = _binding_unique_state()
        if state == "dataset_aware":
            return
        _replace_binding_unique(
            new_columns=_DATASET_AWARE_BINDING_COLUMNS,
        )
        if _binding_unique_state() != "dataset_aware":
            raise RuntimeError("MARKET_DATA_SHARED_BINDING_SCHEMA_UNREADY: upgrade not reflected")


def downgrade() -> None:
    """Restore the legacy invariant only when no shared binding exists."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_SHARED_BINDING_DOWNGRADE_BLOCKED: "
            "offline SQL cannot prove shared bindings are absent"
        )

    with _ddl_maintenance_fence():
        state = _binding_unique_state()
        if state == "legacy":
            return
        _assert_downgrade_has_no_shared_bindings()
        _replace_binding_unique(
            new_columns=_LEGACY_BINDING_COLUMNS,
        )
        if _binding_unique_state() != "legacy":
            raise RuntimeError("MARKET_DATA_SHARED_BINDING_SCHEMA_UNREADY: downgrade not reflected")
