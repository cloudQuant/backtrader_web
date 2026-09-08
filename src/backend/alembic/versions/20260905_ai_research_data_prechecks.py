"""Add server-owned expiry-bound data precheck evidence.

Revision ID: 20260905_ai_research_data_prechecks
Revises: 20260905_ai_research_evidence_packages

The precheck table is append-only evidence.  Runs retain the selected receipt
ID so an audit can reconstruct which current-data assertion gated submission.
The run reference is deliberately application-validated during this expand
migration to remain portable across SQLite, PostgreSQL and MySQL.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_data_prechecks"
down_revision = "20260905_ai_research_evidence_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create precheck evidence and attach its ID to new protocol-v2 runs."""

    op.create_table(
        "ai_research_data_prechecks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "hypothesis_version_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_hypothesis_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "experiment_epoch_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("profile_version", sa.String(length=128), nullable=False),
        sa.Column("promotion_policy_version", sa.String(length=128), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'BLOCKED')",
            name="ck_ai_research_data_precheck_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_research_data_precheck_owner_expiry",
        "ai_research_data_prechecks",
        ["user_id", "expires_at", "checked_at"],
    )
    op.create_index(
        "ix_ai_research_data_precheck_input",
        "ai_research_data_prechecks",
        ["user_id", "input_hash"],
    )
    with op.batch_alter_table("ai_research_runs") as batch_op:
        batch_op.add_column(sa.Column("data_precheck_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ai_research_runs_data_precheck_id", "ai_research_runs", ["data_precheck_id"])


def downgrade() -> None:
    """Remove only protocol-v2 precheck metadata, not legacy evidence."""

    op.drop_index("ix_ai_research_runs_data_precheck_id", table_name="ai_research_runs")
    with op.batch_alter_table("ai_research_runs") as batch_op:
        batch_op.drop_column("data_precheck_id")
    op.drop_index("ix_ai_research_data_precheck_input", table_name="ai_research_data_prechecks")
    op.drop_index("ix_ai_research_data_precheck_owner_expiry", table_name="ai_research_data_prechecks")
    op.drop_table("ai_research_data_prechecks")
