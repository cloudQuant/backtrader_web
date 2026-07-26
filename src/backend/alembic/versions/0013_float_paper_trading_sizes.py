"""Allow fractional paper trading order, position, and trade sizes.

Revision ID: 0013_float_paper_trading_sizes
Revises: 0012_add_scanner_plan_tables
Create Date: 2026-06-26
"""

import sqlalchemy as sa

from alembic import op

revision = "0013_float_paper_trading_sizes"
down_revision = "0012_add_scanner_plan_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("paper_trading_positions") as batch_op:
        batch_op.alter_column(
            "size",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )
    with op.batch_alter_table("paper_trading_orders") as batch_op:
        batch_op.alter_column(
            "size",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "filled_size",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )
    with op.batch_alter_table("paper_trades") as batch_op:
        batch_op.alter_column(
            "size",
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("paper_trades") as batch_op:
        batch_op.alter_column(
            "size",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
    with op.batch_alter_table("paper_trading_orders") as batch_op:
        batch_op.alter_column(
            "filled_size",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "size",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
    with op.batch_alter_table("paper_trading_positions") as batch_op:
        batch_op.alter_column(
            "size",
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
