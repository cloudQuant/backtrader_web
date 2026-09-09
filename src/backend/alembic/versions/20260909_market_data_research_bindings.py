"""Persist sealed local-first market-data artifacts for research backtests.

Revision ID: 20260909_market_data_research_bindings
Revises: 20260909_ai_research_market_data_merge
Create Date: 2026-09-09

The table records the server-owned identity, point-in-time evidence, and
controlled artifact digest for a research/backtest input.  The CSV itself is
stored below a configured controlled filesystem root, never in a caller path.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql

from alembic import op

revision = "20260909_market_data_research_bindings"
down_revision = "20260909_ai_research_market_data_merge"
branch_labels = None
depends_on = None

_TABLE = "md_research_data_bindings"
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")


def _exact_identifier_type(length: int) -> sa.types.TypeEngine[object]:
    """Keep canonical IDs bytewise across SQLite, MySQL, and PostgreSQL."""
    return (
        sa.String(length, collation="BINARY")
        .with_variant(mysql.VARCHAR(length, collation="utf8mb4_bin"), "mysql")
        .with_variant(postgresql.VARCHAR(length, collation="C"), "postgresql")
    )


def upgrade() -> None:
    """Create durable records for signed research-data artifact bindings."""
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", name="fk_md_rdb_user", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("binding_hash", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("binding_schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("artifact_relative_path", sa.String(length=512), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("artifact_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("canonical_id", _exact_identifier_type(512), nullable=False),
        sa.Column("instrument_metadata_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_code", sa.String(length=255), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("family_contract_version", sa.String(length=64), nullable=False),
        sa.Column("data_kind", sa.String(length=64), nullable=False),
        sa.Column("frequency", sa.String(length=32), nullable=False),
        sa.Column("source_policy_id", sa.String(length=128), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("knowledge_cutoff", _PIT_DATETIME, nullable=False),
        sa.Column("identity_knowledge_cutoff", _PIT_DATETIME, nullable=False),
        sa.Column("visibility_at", _PIT_DATETIME, nullable=False),
        sa.Column("visibility_sequence", sa.BigInteger(), nullable=False),
        sa.Column("identity_visibility_at", _PIT_DATETIME, nullable=False),
        sa.Column("identity_visibility_sequence", sa.BigInteger(), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.CheckConstraint(
            f"length(binding_hash) = {_SHA256_LENGTH}",
            name="ck_md_rdb_binding_hash_len",
        ),
        sa.CheckConstraint(
            f"length(manifest_sha256) = {_SHA256_LENGTH}",
            name="ck_md_rdb_manifest_hash_len",
        ),
        sa.CheckConstraint(
            f"length(artifact_sha256) = {_SHA256_LENGTH}",
            name="ck_md_rdb_artifact_hash_len",
        ),
        sa.CheckConstraint("artifact_size_bytes > 0", name="ck_md_rdb_artifact_size_pos"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REVOKED', 'INVALID')",
            name="ck_md_rdb_status",
        ),
        sa.CheckConstraint(
            "visibility_sequence >= 0 AND identity_visibility_sequence >= 0",
            name="ck_md_rdb_visibility_seq",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("binding_hash", name="uq_md_rdb_binding_hash"),
    )
    op.create_index("ix_md_rdb_owner_intent", _TABLE, ["user_id", "intent_id", "created_at"])
    op.create_index("ix_md_rdb_status_created", _TABLE, ["status", "created_at"])


def downgrade() -> None:
    """Remove only the research-binding receipt table and its indexes."""
    op.drop_index("ix_md_rdb_status_created", table_name=_TABLE)
    op.drop_index("ix_md_rdb_owner_intent", table_name=_TABLE)
    op.drop_table(_TABLE)
