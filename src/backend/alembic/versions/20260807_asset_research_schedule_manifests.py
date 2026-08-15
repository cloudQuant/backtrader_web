"""Add immutable approval manifests for bounded system shadow schedules.

Revision ID: 20260807_asset_research_schedule_manifests
Revises: 20260806_asset_research_direct_run_prediction

System-owned ``PUBLIC_SHADOW`` and ``ADMIN_EVAL`` schedules must be expanded
from approved, versioned, static entries at configuration time.  This
migration deliberately refuses to infer approval evidence for any pre-existing
system schedule: such a row needs an explicit operator-reviewed conversion,
not a fabricated manifest backfill.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260807_asset_research_schedule_manifests"
down_revision = "20260806_asset_research_direct_run_prediction"
branch_labels = None
depends_on = None

_MANIFEST_TABLE = "asset_schedule_manifests"
_SCHEDULE_TABLE = "asset_signal_schedules"
_MANIFEST_FOREIGN_KEY = "fk_asset_schedule_manifest"
_MANIFEST_INDEX = "ix_asset_schedule_manifest_enabled"
_TARGET_UNIQUE = "uq_asset_schedule_system_target_key"
_SCHEDULE_CHECK = "ck_asset_schedule_manifest_owner"
_MANIFEST_SCOPE_CHECK = "ck_asset_schedule_manifest_scope"
_LEGACY_MANIFEST_SCOPE_CHECK = "ck_asset_schedule_manifest_owner"
_MANIFEST_REQUIRED_COLUMNS = {
    "id",
    "manifest_key",
    "manifest_version",
    "owner_scope",
    "approval_reference",
    "evidence_uri",
    "evidence_content_hash",
    "content_hash",
    "approved_by",
    "approved_at",
    "status",
    "idempotency_key",
    "idempotency_request_hash",
    "retired_by",
    "retired_at",
    "retirement_reason_codes_json",
    "created_at",
    "retention_class",
    "retention_expires_at",
    "legal_hold",
    "tombstoned_at",
}


def _retention_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "retention_class", sa.String(length=32), nullable=False, server_default="research-v1"
        ),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _assert_no_unapproved_system_schedules(bind: Any) -> None:
    count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM asset_signal_schedules
            WHERE owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL')
            """
        )
    ).scalar_one()
    if int(count) != 0:
        raise RuntimeError(
            "ASSET_SCHEDULE_MANIFEST_BACKFILL_REQUIRED: existing system schedules "
            "need explicit approved manifest evidence before this migration"
        )


def _table_columns(bind: Any, table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(bind).get_columns(table_name)}


def _constraint_names(bind: Any, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    names = {
        str(item["name"])
        for item in inspector.get_check_constraints(table_name)
        if item.get("name")
    }
    names.update(
        str(item["name"]) for item in inspector.get_foreign_keys(table_name) if item.get("name")
    )
    names.update(
        str(item["name"])
        for item in inspector.get_unique_constraints(table_name)
        if item.get("name")
    )
    return names


def _index_names(bind: Any, table_name: str) -> set[str]:
    return {
        str(item["name"]) for item in sa.inspect(bind).get_indexes(table_name) if item.get("name")
    }


def _create_manifest_table() -> None:
    op.create_table(
        _MANIFEST_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manifest_key", sa.String(length=128), nullable=False),
        sa.Column("manifest_version", sa.String(length=64), nullable=False),
        sa.Column("owner_scope", sa.String(length=32), nullable=False),
        sa.Column("approval_reference", sa.String(length=512), nullable=False),
        sa.Column("evidence_uri", sa.String(length=2048), nullable=True),
        sa.Column("evidence_content_hash", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_request_hash", sa.String(length=64), nullable=True),
        sa.Column("retired_by", sa.String(length=128), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retirement_reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_retention_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "manifest_key", "manifest_version", name="uq_asset_schedule_manifest_version"
        ),
        sa.UniqueConstraint(
            "approved_by",
            "idempotency_key",
            name="uq_asset_schedule_manifest_actor_idempotency",
        ),
        sa.CheckConstraint(
            "owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL')",
            name=_MANIFEST_SCOPE_CHECK,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RETIRED')",
            name="ck_asset_schedule_manifest_status",
        ),
        sa.CheckConstraint(
            "(evidence_uri IS NULL AND evidence_content_hash IS NULL) OR "
            "(evidence_uri IS NOT NULL AND evidence_content_hash IS NOT NULL)",
            name="ck_asset_schedule_manifest_evidence",
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND retired_by IS NULL AND retired_at IS NULL) OR "
            "(status = 'RETIRED' AND retired_by IS NOT NULL AND retired_at IS NOT NULL)",
            name="ck_asset_schedule_manifest_retirement",
        ),
    )


def _ensure_manifest_table(bind: Any) -> None:
    """Resume safely if a non-transactional MySQL DDL step previously stopped."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_MANIFEST_TABLE):
        _create_manifest_table()
        return
    if not _MANIFEST_REQUIRED_COLUMNS <= _table_columns(bind, _MANIFEST_TABLE):
        raise RuntimeError(
            "ASSET_SCHEDULE_MANIFEST_PARTIAL_SCHEMA_UNSAFE: manifest table is not compatible"
        )
    checks = _constraint_names(bind, _MANIFEST_TABLE)
    if _LEGACY_MANIFEST_SCOPE_CHECK in checks:
        op.drop_constraint(
            _LEGACY_MANIFEST_SCOPE_CHECK,
            _MANIFEST_TABLE,
            type_="check",
        )
        op.create_check_constraint(
            _MANIFEST_SCOPE_CHECK,
            _MANIFEST_TABLE,
            "owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL')",
        )
    elif _MANIFEST_SCOPE_CHECK not in checks:
        raise RuntimeError(
            "ASSET_SCHEDULE_MANIFEST_PARTIAL_SCHEMA_UNSAFE: manifest scope constraint is missing"
        )


def _assert_manifest_table_empty(bind: Any) -> None:
    if not sa.inspect(bind).has_table(_MANIFEST_TABLE):
        return
    count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {_MANIFEST_TABLE}")).scalar_one()
    if int(count) != 0:
        raise RuntimeError(
            "ASSET_SCHEDULE_MANIFEST_DOWNGRADE_BLOCKED: export or retire audited manifest "
            "records before removing their schema"
        )


def upgrade() -> None:
    bind = op.get_bind()
    _assert_no_unapproved_system_schedules(bind)
    _ensure_manifest_table(bind)
    manifest_indexes = _index_names(bind, _MANIFEST_TABLE)
    if "ix_asset_schedule_manifest_scope_status" not in manifest_indexes:
        op.create_index(
            "ix_asset_schedule_manifest_scope_status",
            _MANIFEST_TABLE,
            ["owner_scope", "status", "approved_at"],
        )
    if "ix_asset_schedule_manifests_content_hash" not in manifest_indexes:
        op.create_index(
            "ix_asset_schedule_manifests_content_hash",
            _MANIFEST_TABLE,
            ["content_hash"],
        )

    schedule_columns = _table_columns(bind, _SCHEDULE_TABLE)
    schedule_constraints = _constraint_names(bind, _SCHEDULE_TABLE)
    schedule_indexes = _index_names(bind, _SCHEDULE_TABLE)
    with op.batch_alter_table(_SCHEDULE_TABLE) as batch:
        if "approved_manifest_id" not in schedule_columns:
            batch.add_column(sa.Column("approved_manifest_id", sa.String(length=36), nullable=True))
        if "manifest_entry_key" not in schedule_columns:
            batch.add_column(sa.Column("manifest_entry_key", sa.String(length=128), nullable=True))
        if "manifest_content_hash" not in schedule_columns:
            batch.add_column(
                sa.Column("manifest_content_hash", sa.String(length=64), nullable=True)
            )
        if "system_target_key" not in schedule_columns:
            batch.add_column(sa.Column("system_target_key", sa.String(length=64), nullable=True))
        if _MANIFEST_FOREIGN_KEY not in schedule_constraints:
            batch.create_foreign_key(
                _MANIFEST_FOREIGN_KEY,
                _MANIFEST_TABLE,
                ["approved_manifest_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if _TARGET_UNIQUE not in schedule_constraints and _TARGET_UNIQUE not in schedule_indexes:
            batch.create_unique_constraint(_TARGET_UNIQUE, ["system_target_key"])
        if _SCHEDULE_CHECK not in schedule_constraints:
            batch.create_check_constraint(
                _SCHEDULE_CHECK,
                "(owner_scope = 'USER' AND approved_manifest_id IS NULL "
                "AND manifest_entry_key IS NULL AND manifest_content_hash IS NULL "
                "AND system_target_key IS NULL) OR "
                "(owner_scope IN ('PUBLIC_SHADOW', 'ADMIN_EVAL') "
                "AND approved_manifest_id IS NOT NULL AND manifest_entry_key IS NOT NULL "
                "AND manifest_content_hash IS NOT NULL AND "
                # TRUE/FALSE literals are portable across SQLite / MySQL /
                # PostgreSQL; `enabled = 1` breaks on PostgreSQL booleans.
                "((enabled = TRUE AND system_target_key IS NOT NULL) "
                "OR (enabled = FALSE AND system_target_key IS NULL)))",
            )
        if _MANIFEST_INDEX not in schedule_indexes:
            batch.create_index(_MANIFEST_INDEX, ["approved_manifest_id", "enabled"])


def downgrade() -> None:
    bind = op.get_bind()
    _assert_manifest_table_empty(bind)

    with op.batch_alter_table(_SCHEDULE_TABLE) as batch:
        # InnoDB requires a supporting child index for the manifest foreign
        # key.  Drop the FK first; otherwise MySQL 9.4 correctly rejects
        # removal of this composite index during a full downgrade.
        batch.drop_constraint(_MANIFEST_FOREIGN_KEY, type_="foreignkey")
        batch.drop_index(_MANIFEST_INDEX)
        batch.drop_constraint(_SCHEDULE_CHECK, type_="check")
        batch.drop_constraint(_TARGET_UNIQUE, type_="unique")
        batch.drop_column("system_target_key")
        batch.drop_column("manifest_content_hash")
        batch.drop_column("manifest_entry_key")
        batch.drop_column("approved_manifest_id")

    op.drop_index("ix_asset_schedule_manifests_content_hash", table_name=_MANIFEST_TABLE)
    op.drop_index("ix_asset_schedule_manifest_scope_status", table_name=_MANIFEST_TABLE)
    op.drop_table(_MANIFEST_TABLE)
