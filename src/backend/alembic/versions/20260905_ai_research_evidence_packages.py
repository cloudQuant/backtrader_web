"""Add immutable server-owned protocol-v2 evidence packages.

Revision ID: 20260905_ai_research_evidence_packages
Revises: 20260904_ai_research_profile_quarantine

The manifest is intentionally stored as a redacted JSON document.  Approval
records reference its content hash, while the additional binding hash excludes
the later human-decision audit snapshot so an approval does not invalidate
itself merely by being recorded.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_evidence_packages"
down_revision = "20260904_ai_research_profile_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the append-only evidence authority used by protocol-v2 approvals."""

    op.create_table(
        "ai_research_evidence_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("promotion_policy_version", sa.String(length=128), nullable=False),
        sa.Column("gate_input_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_binding_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'WITHDRAWN')",
            name="ck_ai_research_evidence_package_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "promotion_policy_version",
            "gate_input_evidence_hash",
            "manifest_hash",
            name="uq_ai_research_evidence_package_manifest",
        ),
    )
    op.create_index(
        "ix_ai_research_evidence_package_owner_run",
        "ai_research_evidence_packages",
        ["user_id", "run_id", "created_at"],
    )


def downgrade() -> None:
    """Drop only generated evidence metadata; source records remain intact."""

    op.drop_table("ai_research_evidence_packages")
