"""Bind new discovery commands to an atomic search slot; retain legacy NULLs."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260906_ai_research_search_allocation"
down_revision = "20260905_ai_research_discovery_executions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_research_discovery_executions") as batch:
        batch.add_column(sa.Column("search_epoch_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("search_ordinal", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("search_budget_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("trial_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_discovery_search_epoch",
            "ai_research_experiment_epochs",
            ["search_epoch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_discovery_trial",
            "ai_research_trials",
            ["trial_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_ai_research_search_slot", ["search_epoch_id", "search_ordinal"]
        )
        batch.create_unique_constraint("uq_ai_research_discovery_trial", ["trial_id"])
        batch.create_check_constraint(
            "ck_ai_research_discovery_search_binding",
            "(search_epoch_id IS NULL AND search_ordinal IS NULL AND search_budget_hash IS NULL) "
            "OR (search_epoch_id IS NOT NULL AND search_ordinal IS NOT NULL "
            "AND search_ordinal > 0 AND search_budget_hash IS NOT NULL)",
        )


def downgrade() -> None:
    """Remove allocation metadata only; journal commands/results remain intact."""
    with op.batch_alter_table("ai_research_discovery_executions") as batch:
        batch.drop_constraint("ck_ai_research_discovery_search_binding", type_="check")
        batch.drop_constraint("uq_ai_research_discovery_trial", type_="unique")
        batch.drop_constraint("uq_ai_research_search_slot", type_="unique")
        batch.drop_constraint("fk_discovery_trial", type_="foreignkey")
        batch.drop_constraint("fk_discovery_search_epoch", type_="foreignkey")
        for column in ("trial_id", "search_budget_hash", "search_ordinal", "search_epoch_id"):
            batch.drop_column(column)
