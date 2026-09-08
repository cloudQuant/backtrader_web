"""Add post-freeze forward-observation evidence tables.

Revision ID: 20260904_ai_research_forward_observation
Revises: 20260904_ai_research_protocol_v2

This is an expand-only continuation of the protocol-v2 schema.  It records a
policy window separately from the future data that later arrives; it does not
retroactively label any historical dataset as forward evidence.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260904_ai_research_forward_observation"
down_revision = "20260904_ai_research_protocol_v2"
branch_labels = None
depends_on = None


def _id() -> sa.Column:
    return sa.Column("id", sa.String(length=36), nullable=False)


def _timestamp(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Create append-only forward observation policy and receipt tables."""

    op.create_table(
        "ai_research_forward_observation_epochs",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        _timestamp("candidate_frozen_at"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'OPEN'")),
        _timestamp("started_at"),
        _timestamp("ready_at", nullable=True),
        _timestamp("closed_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('OPEN', 'READY', 'CLOSED', 'BLOCKED')",
            name="ck_ai_research_forward_epoch_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "policy_version",
            name="uq_ai_research_forward_epoch_candidate_policy",
        ),
    )
    op.create_index(
        "ix_ai_research_forward_epoch_owner_status",
        "ai_research_forward_observation_epochs",
        ["user_id", "status", "started_at"],
    )

    op.create_table(
        "ai_research_forward_observation_snapshots",
        _id(),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "observation_epoch_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_forward_observation_epochs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        _timestamp("event_time"),
        _timestamp("ingested_at"),
        _timestamp("as_of_at"),
        _timestamp("candidate_frozen_at"),
        sa.Column("quality_status", sa.String(length=16), nullable=False, server_default=sa.text("'UNKNOWN'")),
        sa.Column("quality_evidence", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "quality_status IN ('PASS', 'FAIL', 'UNKNOWN')",
            name="ck_ai_research_forward_snapshot_quality",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "observation_epoch_id",
            "idempotency_key",
            name="uq_ai_research_forward_snapshot_idempotency",
        ),
        sa.UniqueConstraint(
            "observation_epoch_id",
            "dataset_snapshot_id",
            name="uq_ai_research_forward_snapshot_dataset",
        ),
    )
    op.create_index(
        "ix_ai_research_forward_snapshot_epoch_event",
        "ai_research_forward_observation_snapshots",
        ["observation_epoch_id", "event_time"],
    )


def downgrade() -> None:
    """Drop only the new forward-evidence tables; v2 and legacy records remain."""

    op.drop_table("ai_research_forward_observation_snapshots")
    op.drop_table("ai_research_forward_observation_epochs")
