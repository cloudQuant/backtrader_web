"""Persist the pre-dispatch accounting snapshot without inventing legacy evidence."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_budget_context"
down_revision = "20260905_ai_research_provider_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_research_quota_reservations",
        sa.Column("reservation_context", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_research_quota_reservations", "reservation_context")
