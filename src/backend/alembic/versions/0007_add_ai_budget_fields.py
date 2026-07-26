"""Add AI budget fields to users.

Revision ID: 0007_add_ai_budget_fields
Revises: 0006_add_ai_call_logs
Create Date: 2026-05-24
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_add_ai_budget_fields"
down_revision = "0006_add_ai_call_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_budget_daily_usd", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("ai_budget_mode", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ai_budget_mode")
    op.drop_column("users", "ai_budget_daily_usd")
