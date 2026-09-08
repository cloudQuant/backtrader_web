"""Bind one server-owned GENERATE materialization to durable provenance.

Revision ID: 20260905_ai_research_generation_materialization
Revises: 20260905_ai_research_task_events

The table records only immutable identifiers and hashes.  Generated code,
dependency content, and the server-built manifest remain content-addressed
artifacts; no provider prompt or raw model output is copied here.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_generation_materialization"
down_revision = "20260905_ai_research_task_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the immutable attempt-candidate-invocation materialization receipt."""

    op.create_table(
        "ai_research_generation_materializations",
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
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "model_invocation_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_model_invocations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "manifest_artifact_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_output_hash", sa.String(length=64), nullable=False),
        sa.Column("materialization_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stage_attempt_id",
            name="uq_ai_research_generation_materialization_attempt",
        ),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_ai_research_generation_materialization_candidate",
        ),
        sa.UniqueConstraint(
            "model_invocation_id",
            name="uq_ai_research_generation_materialization_invocation",
        ),
        sa.UniqueConstraint(
            "manifest_artifact_id",
            name="uq_ai_research_generation_materialization_manifest",
        ),
    )
    op.create_index(
        "ix_ai_research_generation_materialization_owner_run",
        "ai_research_generation_materializations",
        ["user_id", "run_id", "created_at"],
    )


def downgrade() -> None:
    """Remove only the supplemental generation materialization receipt."""

    op.drop_index(
        "ix_ai_research_generation_materialization_owner_run",
        table_name="ai_research_generation_materializations",
    )
    op.drop_table("ai_research_generation_materializations")
