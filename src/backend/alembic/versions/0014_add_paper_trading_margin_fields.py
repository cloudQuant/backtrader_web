"""Add margin and contract metadata to paper trading positions.

Revision ID: 0014_add_paper_trading_margin_fields
Revises: 0013_float_paper_trading_sizes
Create Date: 2026-06-26
"""

import sqlalchemy as sa

from alembic import op

revision = "0014_add_paper_trading_margin_fields"
down_revision = "0013_float_paper_trading_sizes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("paper_trading_positions") as batch_op:
        batch_op.add_column(sa.Column("margin_value", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("multiplier", sa.Float(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("margin_rate", sa.Float(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("commission_rate", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(
            sa.Column("commission_amount", sa.Float(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("paper_trading_positions") as batch_op:
        batch_op.drop_column("commission_amount")
        batch_op.drop_column("commission_rate")
        batch_op.drop_column("margin_rate")
        batch_op.drop_column("multiplier")
        batch_op.drop_column("margin_value")
