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


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    """Add missing fields without failing a legacy ``create_all`` database."""
    existing_columns = _column_names("paper_trading_positions")
    for column in (
        sa.Column("margin_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("multiplier", sa.Float(), nullable=False, server_default="1"),
        sa.Column("margin_rate", sa.Float(), nullable=False, server_default="1"),
        sa.Column("commission_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("commission_amount", sa.Float(), nullable=False, server_default="0"),
    ):
        if column.name not in existing_columns:
            op.add_column("paper_trading_positions", column)


def downgrade() -> None:
    with op.batch_alter_table("paper_trading_positions") as batch_op:
        batch_op.drop_column("commission_amount")
        batch_op.drop_column("commission_rate")
        batch_op.drop_column("margin_rate")
        batch_op.drop_column("multiplier")
        batch_op.drop_column("margin_value")
