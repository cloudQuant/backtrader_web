"""Add append-only safe task-event summaries for protocol-v2 polling.

Revision ID: 20260905_ai_research_task_events
Revises: 20260905_ai_research_stage_artifact_binding

Task events intentionally contain only a display-safe transition summary.  Raw
request payloads, lease tokens, executor receipts, and provider inputs remain
outside this polling stream.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_task_events"
down_revision = "20260905_ai_research_stage_artifact_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a fenced per-task sequence and its append-only safe event table."""

    with op.batch_alter_table("ai_research_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("event_sequence", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.create_check_constraint(
            "ck_ai_research_task_event_sequence", "event_sequence >= 0"
        )
    op.create_table(
        "ai_research_task_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_tasks.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column(
            "stage_attempt_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_stage_attempts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence_no > 0", name="ck_ai_research_task_event_sequence_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence_no", name="uq_ai_research_task_event_sequence"),
    )
    op.create_index(
        "ix_ai_research_task_event_task_sequence",
        "ai_research_task_events",
        ["task_id", "sequence_no"],
    )
    op.create_index(
        "ix_ai_research_task_event_owner_created",
        "ai_research_task_events",
        ["user_id", "created_at", "id"],
    )


def downgrade() -> None:
    """Remove only the v2 task event stream and its sequence fence."""

    op.drop_index("ix_ai_research_task_event_owner_created", table_name="ai_research_task_events")
    op.drop_index("ix_ai_research_task_event_task_sequence", table_name="ai_research_task_events")
    op.drop_table("ai_research_task_events")
    with op.batch_alter_table("ai_research_tasks") as batch_op:
        batch_op.drop_constraint("ck_ai_research_task_event_sequence", type_="check")
        batch_op.drop_column("event_sequence")
