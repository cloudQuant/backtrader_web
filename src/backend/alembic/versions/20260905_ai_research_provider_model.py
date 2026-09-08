"""Preserve provider-reported model independently from the configured request pin.

Legacy NULL values mean unobserved, never backfilled from the configured alias.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_provider_model"
down_revision = "20260905_ai_research_dataset_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_research_model_invocations",
        sa.Column("provider_reported_model", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_research_model_invocations", "provider_reported_model")
