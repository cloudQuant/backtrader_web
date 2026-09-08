"""Persist durable discovery-runner command and receipt evidence.

Revision ID: 20260905_ai_research_discovery_executions
Revises: 20260905_ai_research_budget_context

This additive receipt table intentionally does not create trials, complete
stages, or mutate quota settlement state.  It retains observed or ambiguous
external execution evidence for later fenced consumers.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_discovery_executions"
down_revision = "20260905_ai_research_budget_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add one immutable command/receipt record per discovery execution."""

    op.create_table(
        "ai_research_discovery_executions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
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
            "task_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "stage_attempt_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "quota_reservation_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_quota_reservations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("command_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PREPARED', 'OBSERVED', 'UNKNOWN')",
            name="ck_ai_research_discovery_execution_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stage_attempt_id",
            name="uq_ai_research_discovery_execution_attempt",
        ),
        sa.UniqueConstraint(
            "quota_reservation_id",
            name="uq_ai_research_discovery_execution_reservation",
        ),
    )
    op.create_index(
        "ix_ai_research_discovery_execution_owner_run",
        "ai_research_discovery_executions",
        ["user_id", "run_id", "created_at"],
    )


def downgrade() -> None:
    """Remove only the additive discovery execution journal."""

    op.drop_index(
        "ix_ai_research_discovery_execution_owner_run",
        table_name="ai_research_discovery_executions",
    )
    op.drop_table("ai_research_discovery_executions")
