"""Add composite indexes for common listing queries.

Targets:
  - ``backtest_tasks`` list-by-user-with-recency:
    ``WHERE user_id = ? ORDER BY created_at DESC``
    (see :class:`app.services.backtest_manager.BacktestExecutionManager.list_tasks`).
  - ``backtest_tasks`` version-diff lookup:
    ``WHERE strategy_version_id = ? AND status = 'completed' ORDER BY created_at DESC``
    (see :class:`app.services.version_diff_service`).

The single-column indexes added in 0002 do not help with the trailing
``ORDER BY created_at DESC``; SQLite/PostgreSQL/MySQL all benefit from a
composite index whose leading columns match the equality predicate and whose
trailing column matches the sort order.

Revision ID: 0004_add_composite_listing_indexes
Revises: 0003_add_trading_workspace_fields
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op

revision = "0004_add_composite_listing_indexes"
down_revision = "0003_add_trading_workspace_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add composite listing indexes."""
    # Dashboard: tasks for a user, newest first.
    op.create_index(
        "idx_backtest_tasks_user_created_at",
        "backtest_tasks",
        ["user_id", "created_at"],
        unique=False,
    )

    # Version-diff lookup: most recent completed task for a strategy version.
    op.create_index(
        "idx_backtest_tasks_version_status_created_at",
        "backtest_tasks",
        ["strategy_version_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop composite listing indexes."""
    op.drop_index(
        "idx_backtest_tasks_version_status_created_at", table_name="backtest_tasks"
    )
    op.drop_index("idx_backtest_tasks_user_created_at", table_name="backtest_tasks")
