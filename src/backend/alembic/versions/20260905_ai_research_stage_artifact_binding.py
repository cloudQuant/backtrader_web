"""Bind verifiable local stage outputs to one durable stage attempt.

Revision ID: 20260905_ai_research_stage_artifact_binding
Revises: 20260905_ai_research_epoch_family_unique

Generic artifact descriptors remain read-compatible, but they cannot serve as
new successful stage outputs.  A stage-output binding records the user, run,
task, and attempt together, while the companion content table retains the
bytes whose SHA-256 digest is stored in the existing artifact record.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_stage_artifact_binding"
down_revision = "20260905_ai_research_epoch_family_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add verifiable local payloads and one immutable output binding per attempt."""

    op.create_table(
        "ai_research_artifact_contents",
        sa.Column(
            "artifact_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("artifact_id"),
    )
    op.create_table(
        "ai_research_stage_artifact_bindings",
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
            "artifact_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stage_attempt_id",
            name="uq_ai_research_stage_output_binding_attempt",
        ),
    )
    op.create_index(
        "ix_ai_research_stage_output_binding_owner_run",
        "ai_research_stage_artifact_bindings",
        ["user_id", "run_id", "created_at"],
    )


def downgrade() -> None:
    """Remove only the supplemental local-output proof records."""

    op.drop_index(
        "ix_ai_research_stage_output_binding_owner_run",
        table_name="ai_research_stage_artifact_bindings",
    )
    op.drop_table("ai_research_stage_artifact_bindings")
    op.drop_table("ai_research_artifact_contents")
