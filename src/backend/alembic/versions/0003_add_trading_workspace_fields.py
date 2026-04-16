"""Add trading workspace fields.

Revision ID: 0003_add_trading_workspace_fields
Revises: 0002_add_performance_indexes
Create Date: 2026-04-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_add_trading_workspace_fields"
down_revision = "0002_add_performance_indexes"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    workspace_columns = _column_names("workspaces")
    if "workspace_type" not in workspace_columns:
        op.add_column(
            "workspaces",
            sa.Column(
                "workspace_type", sa.String(length=32), nullable=False, server_default="research"
            ),
        )
    if "trading_config" not in workspace_columns:
        op.add_column(
            "workspaces",
            sa.Column("trading_config", sa.JSON(), nullable=True),
        )
    if "ix_workspaces_workspace_type" not in _index_names("workspaces"):
        op.create_index(
            "ix_workspaces_workspace_type",
            "workspaces",
            ["workspace_type"],
            unique=False,
        )

    unit_columns = _column_names("strategy_units")
    if "trading_mode" not in unit_columns:
        op.add_column(
            "strategy_units",
            sa.Column("trading_mode", sa.String(length=20), nullable=False, server_default="paper"),
        )
    if "gateway_config" not in unit_columns:
        op.add_column("strategy_units", sa.Column("gateway_config", sa.JSON(), nullable=True))
    if "lock_trading" not in unit_columns:
        op.add_column(
            "strategy_units",
            sa.Column("lock_trading", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "lock_running" not in unit_columns:
        op.add_column(
            "strategy_units",
            sa.Column("lock_running", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "trading_instance_id" not in unit_columns:
        op.add_column(
            "strategy_units",
            sa.Column("trading_instance_id", sa.String(length=36), nullable=True),
        )
    if "trading_snapshot" not in unit_columns:
        op.add_column("strategy_units", sa.Column("trading_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    unit_columns = _column_names("strategy_units")
    if "trading_snapshot" in unit_columns:
        op.drop_column("strategy_units", "trading_snapshot")
    if "trading_instance_id" in unit_columns:
        op.drop_column("strategy_units", "trading_instance_id")
    if "lock_running" in unit_columns:
        op.drop_column("strategy_units", "lock_running")
    if "lock_trading" in unit_columns:
        op.drop_column("strategy_units", "lock_trading")
    if "gateway_config" in unit_columns:
        op.drop_column("strategy_units", "gateway_config")
    if "trading_mode" in unit_columns:
        op.drop_column("strategy_units", "trading_mode")

    if "ix_workspaces_workspace_type" in _index_names("workspaces"):
        op.drop_index("ix_workspaces_workspace_type", table_name="workspaces")

    workspace_columns = _column_names("workspaces")
    if "trading_config" in workspace_columns:
        op.drop_column("workspaces", "trading_config")
    if "workspace_type" in workspace_columns:
        op.drop_column("workspaces", "workspace_type")
