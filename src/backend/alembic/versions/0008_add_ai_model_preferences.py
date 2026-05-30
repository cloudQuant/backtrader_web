"""add ai model preferences

Revision ID: 0008_add_ai_model_preferences
Revises: 0007_add_ai_budget_fields
Create Date: 2026-05-26
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_add_ai_model_preferences"
down_revision = "0007_add_ai_budget_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_preferred_provider", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("ai_preferred_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ai_preferred_model")
    op.drop_column("users", "ai_preferred_provider")
