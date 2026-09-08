"""Add owner-scoped v2 research configuration profile quarantine.

Revision ID: 20260904_ai_research_profile_quarantine
Revises: 20260904_ai_research_forward_observation

Legacy YAML remains read-compatible during the migration window. Imported
records enter this table without an owner and cannot become active until an
explicit authenticated claim; secrets are removed before persistence by the
application migration service.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260904_ai_research_profile_quarantine"
down_revision = "20260904_ai_research_forward_observation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create a secret-free, user-scoped v2 profile authority table."""

    op.create_table(
        "ai_research_config_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("legacy_source_id", sa.String(length=128), nullable=True),
        sa.Column("legacy_source_hash", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        # MySQL rejects defaults on TEXT columns. The table is new, so the
        # application-level empty-string default is sufficient and no
        # backfill/default is needed for existing rows.
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("credential_refs", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'QUARANTINED'"),
        ),
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
        sa.Column(
            "claimed_by",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUARANTINED', 'ACTIVE', 'RETIRED')",
            name="ck_ai_research_config_profile_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("legacy_source_hash", name="uq_ai_research_config_profile_legacy_hash"),
    )
    op.create_index(
        "ix_ai_research_config_profile_owner_status",
        "ai_research_config_profiles",
        ["owner_user_id", "workspace_id", "status", "updated_at"],
    )


def downgrade() -> None:
    """Drop only v2 profiles; the legacy YAML file is intentionally untouched."""

    op.drop_table("ai_research_config_profiles")
