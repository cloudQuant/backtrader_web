"""Add ai_trading_logs table.

Revision ID: 0005_add_ai_trading_logs
Revises: 0004_add_composite_listing_indexes
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_add_ai_trading_logs"
down_revision = "0004_add_composite_listing_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_trading_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("trade_id", sa.String(12), unique=True, nullable=False, index=True),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("assistant_mode", sa.String(30), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=True, index=True),
        sa.Column("exchange", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("order_type", sa.String(20), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profit", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=True),
        sa.Column("risk_approved", sa.Boolean(), nullable=False),
        sa.Column("risk_warnings", sa.JSON(), nullable=True),
        sa.Column("risk_blocked_reasons", sa.JSON(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        sa.Column("gateway_id", sa.String(100), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("reflection", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_trading_logs")
