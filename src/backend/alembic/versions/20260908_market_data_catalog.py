"""Create the Iteration 197 three-layer market-data catalog.

Revision ID: 20260908_market_data_catalog
Revises: 20260811_asset_research_task_leases
Create Date: 2026-09-08

The revision adds only catalog metadata and nullable foreign keys.  It does
not rewrite, move, or delete legacy market-data facts.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_market_data_catalog"
down_revision = "20260811_asset_research_task_leases"
branch_labels = None
depends_on = None

_ENDPOINT_DATASET_FK = "fk_dg_endpoints_dataset_id_dg_datasets"
_TABLE_STORAGE_FK = "fk_ak_data_tables_dataset_storage_id_dg_dataset_storages"
_PRIMARY_SLOT_CHECK = "ck_dg_dataset_storages_primary_slot"
_CATALOG_REQUIRED_COLUMNS = {
    "dg_datasets": {
        "id",
        "dataset_code",
        "display_name",
        "domain",
        "canonical_schema",
        "primary_key",
        "is_active",
        "created_at",
    },
    "dg_storage_targets": {
        "id",
        "storage_id",
        "engine",
        "url_env",
        "database_name",
        "role",
        "is_active",
        "created_at",
    },
    "dg_dataset_storages": {
        "id",
        "dataset_id",
        "storage_target_id",
        "physical_table",
        "write_mode",
        "is_primary",
        "primary_dataset_id",
        "created_at",
    },
}
_CATALOG_REQUIRED_INDEXES = {
    "dg_datasets": {
        "ix_dg_datasets_dataset_code": (("dataset_code",), True),
        "ix_dg_datasets_domain": (("domain",), False),
    },
    "dg_storage_targets": {
        "ix_dg_storage_targets_storage_id": (("storage_id",), True),
    },
    "dg_dataset_storages": {
        "ix_dg_dataset_storages_dataset_id": (("dataset_id",), False),
        "ix_dg_dataset_storages_storage_target_id": (("storage_target_id",), False),
    },
}
_CATALOG_REQUIRED_PRIMARY_KEYS = {
    "dg_datasets": ("id",),
    "dg_storage_targets": ("id",),
    "dg_dataset_storages": ("id",),
}
_CATALOG_REQUIRED_UNIQUES = {
    "dg_dataset_storages": {
        "uq_dg_dataset_storage_target_table": ("storage_target_id", "physical_table"),
        "uq_dg_dataset_storages_primary_dataset": ("primary_dataset_id",),
    },
}
_CATALOG_REQUIRED_CHECKS = {
    "dg_dataset_storages": {
        _PRIMARY_SLOT_CHECK: (
            "(is_primary=trueandprimary_dataset_idisnotnullandprimary_dataset_id=dataset_id)"
            "or(is_primary=falseandprimary_dataset_idisnull)"
        ),
    },
}


def _is_offline() -> bool:
    return context.is_offline_mode()


def _table_exists(table_name: str) -> bool:
    if _is_offline():
        return False
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(
        index.get("name") == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _foreign_key_exists(
    table_name: str,
    local_columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    if not _table_exists(table_name):
        return False
    return any(
        foreign_key.get("constrained_columns") == local_columns
        and foreign_key.get("referred_table") == referred_table
        and foreign_key.get("referred_columns") == referred_columns
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def _catalog_table_is_complete(table_name: str) -> tuple[bool, str]:
    """Recognize only a fully materialized catalog table after interrupted DDL."""
    inspector = sa.inspect(op.get_bind())
    missing_columns = _CATALOG_REQUIRED_COLUMNS[table_name] - {
        column["name"] for column in inspector.get_columns(table_name)
    }
    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique", False)),
        )
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }
    expected_indexes = _CATALOG_REQUIRED_INDEXES[table_name]
    missing_indexes = set(expected_indexes) - set(indexes)
    invalid_indexes = {
        index_name: {"actual": indexes[index_name], "expected": expected}
        for index_name, expected in expected_indexes.items()
        if index_name in indexes and indexes[index_name] != expected
    }
    primary_key = tuple(
        str(column) for column in inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    )
    unique_constraints = {
        str(constraint["name"]): tuple(
            str(column) for column in constraint.get("column_names") or ()
        )
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }
    expected_uniques = _CATALOG_REQUIRED_UNIQUES.get(table_name, {})
    missing_uniques = set(expected_uniques) - set(unique_constraints)
    invalid_uniques = {
        constraint_name: {
            "actual": unique_constraints[constraint_name],
            "expected": expected,
        }
        for constraint_name, expected in expected_uniques.items()
        if constraint_name in unique_constraints and unique_constraints[constraint_name] != expected
    }
    missing_checks: set[str] = set()
    invalid_checks: dict[str, dict[str, str]] = {}
    missing_foreign_keys: set[str] = set()
    if table_name == "dg_dataset_storages":
        checks = {
            str(constraint["name"]): "".join(str(constraint.get("sqltext", "")).lower().split())
            for constraint in inspector.get_check_constraints(table_name)
            if constraint.get("name")
        }
        for check_name, expected_sql in _CATALOG_REQUIRED_CHECKS[table_name].items():
            if check_name not in checks:
                missing_checks.add(check_name)
            elif checks[check_name] != expected_sql:
                invalid_checks[check_name] = {
                    "actual": checks[check_name],
                    "expected": expected_sql,
                }
        if not _foreign_key_exists(table_name, ["dataset_id"], "dg_datasets", ["id"]):
            missing_foreign_keys.add("dataset_id->dg_datasets.id")
        if not _foreign_key_exists(
            table_name,
            ["storage_target_id"],
            "dg_storage_targets",
            ["id"],
        ):
            missing_foreign_keys.add("storage_target_id->dg_storage_targets.id")

    missing_parts = [
        *(f"columns={sorted(missing_columns)}" for _ in [0] if missing_columns),
        *(
            f"primary_key={primary_key!r} expected={_CATALOG_REQUIRED_PRIMARY_KEYS[table_name]!r}"
            for _ in [0]
            if primary_key != _CATALOG_REQUIRED_PRIMARY_KEYS[table_name]
        ),
        *(f"indexes={sorted(missing_indexes)}" for _ in [0] if missing_indexes),
        *(f"invalid_indexes={invalid_indexes}" for _ in [0] if invalid_indexes),
        *(f"uniques={sorted(missing_uniques)}" for _ in [0] if missing_uniques),
        *(f"invalid_uniques={invalid_uniques}" for _ in [0] if invalid_uniques),
        *(f"checks={sorted(missing_checks)}" for _ in [0] if missing_checks),
        *(f"invalid_checks={invalid_checks}" for _ in [0] if invalid_checks),
        *(f"foreign_keys={sorted(missing_foreign_keys)}" for _ in [0] if missing_foreign_keys),
    ]
    return not missing_parts, "; ".join(missing_parts)


def _assert_catalog_table_complete(table_name: str) -> None:
    complete, detail = _catalog_table_is_complete(table_name)
    if not complete:
        raise RuntimeError(
            "MARKET_DATA_CATALOG_PARTIAL_SCHEMA_UNSAFE: "
            f"{table_name} is present but incomplete ({detail})"
        )


class _SchemaAwareOperations:
    """Avoid replaying DDL over historical ORM ``create_all`` databases."""

    def __init__(self, operations: Any) -> None:
        self._operations = operations

    def create_table(self, table_name: str, *columns: Any, **kwargs: Any) -> Any:
        if _table_exists(table_name):
            _assert_catalog_table_complete(table_name)
            return None
        return self._operations.create_table(table_name, *columns, **kwargs)

    def create_index(
        self, index_name: str, table_name: str, columns: list[str], **kwargs: Any
    ) -> Any:
        if _index_exists(table_name, index_name):
            return None
        return self._operations.create_index(index_name, table_name, columns, **kwargs)


def _upgrade_endpoint_dataset_reference() -> None:
    table_name = "dg_endpoints"
    if not _is_offline() and not _table_exists(table_name):
        return
    add_column = _is_offline() or not _column_exists(table_name, "dataset_id")
    create_index = _is_offline() or not _index_exists(table_name, "ix_dg_endpoints_dataset_id")
    create_foreign_key = _is_offline() or not _foreign_key_exists(
        table_name, ["dataset_id"], "dg_datasets", ["id"]
    )
    if not (add_column or create_index or create_foreign_key):
        return
    with op.batch_alter_table(table_name) as batch:
        if add_column:
            batch.add_column(sa.Column("dataset_id", sa.String(length=36), nullable=True))
        if create_index:
            batch.create_index("ix_dg_endpoints_dataset_id", ["dataset_id"], unique=False)
        if create_foreign_key:
            batch.create_foreign_key(
                _ENDPOINT_DATASET_FK,
                "dg_datasets",
                ["dataset_id"],
                ["id"],
            )


def _upgrade_data_table_storage_reference() -> None:
    table_name = "ak_data_tables"
    if not _is_offline() and not _table_exists(table_name):
        return
    add_column = _is_offline() or not _column_exists(table_name, "dataset_storage_id")
    create_index = _is_offline() or not _index_exists(
        table_name, "ix_ak_data_tables_dataset_storage_id"
    )
    create_foreign_key = _is_offline() or not _foreign_key_exists(
        table_name, ["dataset_storage_id"], "dg_dataset_storages", ["id"]
    )
    if not (add_column or create_index or create_foreign_key):
        return
    with op.batch_alter_table(table_name) as batch:
        if add_column:
            batch.add_column(sa.Column("dataset_storage_id", sa.String(length=36), nullable=True))
        if create_index:
            batch.create_index("ix_ak_data_tables_dataset_storage_id", ["dataset_storage_id"], unique=False)
        if create_foreign_key:
            batch.create_foreign_key(
                _TABLE_STORAGE_FK,
                "dg_dataset_storages",
                ["dataset_storage_id"],
                ["id"],
            )


def _assert_catalog_downgrade_is_safe() -> None:
    """Block a rollback that would delete populated catalog control-plane data."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_CATALOG_DOWNGRADE_BLOCKED: offline SQL cannot prove catalog tables empty"
        )

    bind = op.get_bind()
    populated_tables = []
    for table_name in _CATALOG_REQUIRED_COLUMNS:
        if not _table_exists(table_name):
            continue
        row_count = int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
        if row_count:
            populated_tables.append(f"{table_name}={row_count}")

    populated_references = []
    for table_name, column_name in (
        ("dg_endpoints", "dataset_id"),
        ("ak_data_tables", "dataset_storage_id"),
    ):
        if not _column_exists(table_name, column_name):
            continue
        reference_count = int(
            bind.execute(
                sa.text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NOT NULL")
            ).scalar_one()
        )
        if reference_count:
            populated_references.append(f"{table_name}.{column_name}={reference_count}")

    if populated_tables or populated_references:
        detail = ", ".join([*populated_tables, *populated_references])
        raise RuntimeError(
            "MARKET_DATA_CATALOG_DOWNGRADE_BLOCKED: export or migrate catalog control-plane "
            f"records before downgrade ({detail})"
        )


def upgrade() -> None:
    """Add logical dataset and storage metadata without changing legacy facts."""
    operations = _SchemaAwareOperations(op)
    operations.create_table(
        "dg_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_code", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("canonical_schema", sa.JSON(), nullable=False),
        sa.Column("primary_key", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    operations.create_index(
        "ix_dg_datasets_dataset_code", "dg_datasets", ["dataset_code"], unique=True
    )
    operations.create_index("ix_dg_datasets_domain", "dg_datasets", ["domain"], unique=False)

    operations.create_table(
        "dg_storage_targets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("storage_id", sa.String(length=100), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("url_env", sa.String(length=100), nullable=False),
        sa.Column("database_name", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    operations.create_index(
        "ix_dg_storage_targets_storage_id", "dg_storage_targets", ["storage_id"], unique=True
    )

    operations.create_table(
        "dg_dataset_storages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("storage_target_id", sa.String(length=36), nullable=False),
        sa.Column("physical_table", sa.String(length=128), nullable=False),
        sa.Column("write_mode", sa.String(length=32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("primary_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["dg_datasets.id"]),
        sa.ForeignKeyConstraint(["storage_target_id"], ["dg_storage_targets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_target_id",
            "physical_table",
            name="uq_dg_dataset_storage_target_table",
        ),
        sa.UniqueConstraint(
            "primary_dataset_id",
            name="uq_dg_dataset_storages_primary_dataset",
        ),
        sa.CheckConstraint(
            "(is_primary = true AND primary_dataset_id IS NOT NULL "
            "AND primary_dataset_id = dataset_id) "
            "OR (is_primary = false AND primary_dataset_id IS NULL)",
            name=_PRIMARY_SLOT_CHECK,
        ),
    )
    operations.create_index(
        "ix_dg_dataset_storages_dataset_id", "dg_dataset_storages", ["dataset_id"], unique=False
    )
    operations.create_index(
        "ix_dg_dataset_storages_storage_target_id",
        "dg_dataset_storages",
        ["storage_target_id"],
        unique=False,
    )

    _upgrade_endpoint_dataset_reference()
    _upgrade_data_table_storage_reference()


def downgrade() -> None:
    """Remove only the catalog metadata introduced by this revision."""
    _assert_catalog_downgrade_is_safe()
    with op.batch_alter_table("ak_data_tables") as batch:
        batch.drop_constraint(_TABLE_STORAGE_FK, type_="foreignkey")
        batch.drop_index("ix_ak_data_tables_dataset_storage_id")
        batch.drop_column("dataset_storage_id")

    with op.batch_alter_table("dg_endpoints") as batch:
        batch.drop_constraint(_ENDPOINT_DATASET_FK, type_="foreignkey")
        batch.drop_index("ix_dg_endpoints_dataset_id")
        batch.drop_column("dataset_id")

    op.drop_index("ix_dg_dataset_storages_storage_target_id", table_name="dg_dataset_storages")
    op.drop_index("ix_dg_dataset_storages_dataset_id", table_name="dg_dataset_storages")
    op.drop_table("dg_dataset_storages")
    op.drop_index("ix_dg_storage_targets_storage_id", table_name="dg_storage_targets")
    op.drop_table("dg_storage_targets")
    op.drop_index("ix_dg_datasets_domain", table_name="dg_datasets")
    op.drop_index("ix_dg_datasets_dataset_code", table_name="dg_datasets")
    op.drop_table("dg_datasets")
