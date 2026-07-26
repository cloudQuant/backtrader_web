"""Add scanner plan and batch result tables.

Revision ID: 0012_add_scanner_plan_tables
Revises: 0011_add_stock_analysis_tables
Create Date: 2026-06-19
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_add_scanner_plan_tables"
down_revision = "0011_add_stock_analysis_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scanner_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("universe_pool_id", sa.String(120), nullable=False),
        sa.Column("indicator_rules", sa.JSON(), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("timeframe", sa.String(20), nullable=False, server_default="1d"),
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schedule_frequency", sa.String(20), nullable=False, server_default="daily"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("result_table_name", sa.String(120), nullable=True),
        sa.Column("result_table_status", sa.String(20), nullable=False, server_default="missing"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_scanner_plans_owner_name"),
    )
    op.create_index("ix_scanner_plans_owner_id", "scanner_plans", ["owner_id"])
    op.create_index("ix_scanner_plans_universe_pool_id", "scanner_plans", ["universe_pool_id"])
    op.create_index("ix_scanner_plans_status", "scanner_plans", ["status"])
    op.create_index("ix_scanner_plans_result_table_name", "scanner_plans", ["result_table_name"])

    op.create_table(
        "scanner_plan_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "plan_id",
            sa.String(36),
            sa.ForeignKey("scanner_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_date", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("universe_pool_id", sa.String(120), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("timeframe", sa.String(20), nullable=False, server_default="1d"),
        sa.Column("universe_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("match_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("source_task_id", sa.String(36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("plan_id", "run_date", name="uq_scanner_plan_runs_plan_date"),
    )
    op.create_index("ix_scanner_plan_runs_owner_id", "scanner_plan_runs", ["owner_id"])
    op.create_index("ix_scanner_plan_runs_plan_id", "scanner_plan_runs", ["plan_id"])
    op.create_index("ix_scanner_plan_runs_run_date", "scanner_plan_runs", ["run_date"])
    op.create_index("ix_scanner_plan_runs_status", "scanner_plan_runs", ["status"])
    op.create_index(
        "ix_scanner_plan_runs_universe_pool_id",
        "scanner_plan_runs",
        ["universe_pool_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scanner_plan_runs_universe_pool_id", table_name="scanner_plan_runs")
    op.drop_index("ix_scanner_plan_runs_status", table_name="scanner_plan_runs")
    op.drop_index("ix_scanner_plan_runs_run_date", table_name="scanner_plan_runs")
    op.drop_index("ix_scanner_plan_runs_plan_id", table_name="scanner_plan_runs")
    op.drop_index("ix_scanner_plan_runs_owner_id", table_name="scanner_plan_runs")
    op.drop_table("scanner_plan_runs")
    op.drop_index("ix_scanner_plans_result_table_name", table_name="scanner_plans")
    op.drop_index("ix_scanner_plans_status", table_name="scanner_plans")
    op.drop_index("ix_scanner_plans_universe_pool_id", table_name="scanner_plans")
    op.drop_index("ix_scanner_plans_owner_id", table_name="scanner_plans")
    op.drop_table("scanner_plans")
