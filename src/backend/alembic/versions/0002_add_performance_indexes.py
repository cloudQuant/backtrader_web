"""Add performance indexes for high-frequency queries.

Revision ID: 0002_add_performance_indexes
Revises: 0001_baseline
Create Date: 2026-03-26

"""

from alembic import op

revision = "0002_add_performance_indexes"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes for common query patterns."""
    # Get database connection
    bind = op.get_bind()
    _dialect = bind.dialect.name  # noqa: F841 - kept for future dialect-specific logic

    # SQLite and PostgreSQL/MySQL compatible index creation
    # Index for filtering tasks by status (common in dashboard queries)
    op.create_index(
        "idx_backtest_tasks_status",
        "backtest_tasks",
        ["status"],
        unique=False,
    )

    # Composite index for user task list queries (most common pattern)
    op.create_index(
        "idx_backtest_tasks_user_status",
        "backtest_tasks",
        ["user_id", "status"],
        unique=False,
    )

    # Index for optimization tasks status filtering
    try:
        op.create_index(
            "idx_optimization_tasks_status",
            "optimization_tasks",
            ["status"],
            unique=False,
        )
    except Exception:
        # Table may not exist in all deployments
        pass

    # Index for paper trading orders by status
    try:
        op.create_index(
            "idx_paper_trading_orders_account_status",
            "paper_trading_orders",
            ["account_id", "status"],
            unique=False,
        )
    except Exception:
        # Table may not exist in all deployments
        pass


def downgrade() -> None:
    """Remove performance indexes."""
    op.drop_index("idx_backtest_tasks_status", table_name="backtest_tasks")
    op.drop_index("idx_backtest_tasks_user_status", table_name="backtest_tasks")

    try:
        op.drop_index("idx_optimization_tasks_status", table_name="optimization_tasks")
    except Exception:
        pass

    try:
        op.drop_index("idx_paper_trading_orders_account_status", table_name="paper_trading_orders")
    except Exception:
        pass
