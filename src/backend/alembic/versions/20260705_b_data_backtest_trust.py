"""Add Direction B data/backtest trust tables.

Revision ID: 20260705_b_data_backtest_trust
Revises: 0015_add_workspace_listing_indexes
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260705_b_data_backtest_trust"
down_revision = "0015_add_workspace_listing_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create trust tables and extend backtest metric storage."""
    op.create_table(
        "asset_specs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False, index=True),
        sa.Column("symbol", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("exchange", sa.String(64), nullable=False, index=True),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("contract_multiplier", sa.Float(), nullable=True),
        sa.Column("margin_rate", sa.Float(), nullable=True),
        sa.Column("tick_size", sa.Float(), nullable=True),
        sa.Column("lot_size", sa.Float(), nullable=True),
        sa.Column("min_order_size", sa.Float(), nullable=True),
        sa.Column("commission_rate", sa.Float(), nullable=True),
        sa.Column("commission_fixed", sa.Float(), nullable=True),
        sa.Column("slippage_model", sa.String(64), nullable=False),
        sa.Column("trading_calendar", sa.String(64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("asset_type", "symbol", "exchange", name="uq_asset_specs_lookup"),
    )
    op.create_table(
        "market_data_coverage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False, index=True),
        sa.Column("symbol", sa.String(64), nullable=False, index=True),
        sa.Column("timeframe", sa.String(16), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False, index=True),
        sa.Column("start_date", sa.String(32), nullable=True),
        sa.Column("end_date", sa.String(32), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("missing_ratio", sa.Float(), nullable=False),
        sa.Column("latest_bar_time", sa.String(64), nullable=True),
        sa.Column("quality_status", sa.String(20), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "asset_type",
            "symbol",
            "timeframe",
            "provider",
            name="uq_market_data_coverage_lookup",
        ),
    )
    op.create_table(
        "market_data_quality_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False, index=True),
        sa.Column("symbol", sa.String(64), nullable=False, index=True),
        sa.Column("timeframe", sa.String(16), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False, index=True),
        sa.Column("issue_type", sa.String(64), nullable=False, index=True),
        sa.Column("severity", sa.String(16), nullable=False, index=True),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("sample_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "robustness_test_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), nullable=True, index=True),
        sa.Column("strategy_version_id", sa.String(36), nullable=True, index=True),
        sa.Column("backtest_id", sa.String(36), nullable=False, index=True),
        sa.Column("method", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("gate_evaluations", sa.JSON(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.add_column("backtest_results", sa.Column("average_holding_bars", sa.Float(), nullable=True))
    op.add_column("backtest_results", sa.Column("max_consecutive_wins", sa.Integer(), nullable=True))
    op.add_column(
        "backtest_results",
        sa.Column("max_consecutive_losses", sa.Integer(), nullable=True),
    )
    op.add_column("backtest_results", sa.Column("profit_loss_ratio", sa.Float(), nullable=True))
    op.add_column("backtest_results", sa.Column("standard_metrics", sa.JSON(), nullable=True))
    op.add_column("backtest_results", sa.Column("result_summary", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop Direction B tables and columns."""
    op.drop_column("backtest_results", "result_summary")
    op.drop_column("backtest_results", "standard_metrics")
    op.drop_column("backtest_results", "profit_loss_ratio")
    op.drop_column("backtest_results", "max_consecutive_losses")
    op.drop_column("backtest_results", "max_consecutive_wins")
    op.drop_column("backtest_results", "average_holding_bars")
    op.drop_table("robustness_test_results")
    op.drop_table("market_data_quality_reports")
    op.drop_table("market_data_coverage")
    op.drop_table("asset_specs")
