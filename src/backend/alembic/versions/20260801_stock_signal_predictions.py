"""Add auditable single-stock signal predictions and batch runs.

Revision ID: 20260801_stock_signal_predictions
Revises: 21d572b67d8e
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260801_stock_signal_predictions"
down_revision = "21d572b67d8e"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


class _SchemaAwareOperations:
    """Do not replay DDL over legacy databases created with ``create_all``."""

    def __init__(self, operations: Any) -> None:
        self._operations = operations

    def __getattr__(self, name: str) -> Any:
        return getattr(self._operations, name)

    def create_table(self, table_name: str, *columns: Any, **kwargs: Any) -> Any:
        if _table_exists(table_name):
            return None
        return self._operations.create_table(table_name, *columns, **kwargs)

    def create_index(self, index_name: str, table_name: str, columns: list[str], **kwargs: Any) -> Any:
        if _index_exists(table_name, index_name):
            return None
        return self._operations.create_index(index_name, table_name, columns, **kwargs)

    def drop_index(self, index_name: str, table_name: str | None = None, **kwargs: Any) -> Any:
        if table_name is not None and not _index_exists(table_name, index_name):
            return None
        return self._operations.drop_index(index_name, table_name=table_name, **kwargs)


def upgrade() -> None:
    global op
    op = _SchemaAwareOperations(op)
    op.create_table(
        "stock_signal_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_key", sa.String(length=64), nullable=False),
        sa.Column("owner_scope", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("universe_code", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("scheduled_for_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("degraded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("universe_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("config_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("error_summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_key", name="uq_stock_signal_runs_run_key"),
    )
    op.create_index("ix_stock_signal_runs_owner_scope", "stock_signal_runs", ["owner_scope"])
    op.create_index("ix_stock_signal_runs_source", "stock_signal_runs", ["source"])
    op.create_index("ix_stock_signal_runs_universe_code", "stock_signal_runs", ["universe_code"])
    op.create_index("ix_stock_signal_runs_as_of_date", "stock_signal_runs", ["as_of_date"])
    op.create_index("ix_stock_signal_runs_status", "stock_signal_runs", ["status"])

    op.create_table(
        "stock_signal_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prediction_key", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("owner_scope", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("universe_code", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("symbol_name", sa.String(length=255), nullable=True),
        sa.Column("market_type", sa.String(length=32), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("as_of_at", sa.DateTime(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("next_trading_date", sa.Date(), nullable=True),
        sa.Column("signal_action", sa.String(length=16), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("buy_probability", sa.Float(), nullable=True),
        sa.Column("sell_probability", sa.Float(), nullable=True),
        sa.Column("watch_probability", sa.Float(), nullable=True),
        sa.Column("expected_excess_return", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("eligibility_status", sa.String(length=20), nullable=False),
        sa.Column("quality_reasons_json", sa.JSON(), nullable=False),
        sa.Column("data_freshness_json", sa.JSON(), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column("decision_policy_version", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome_status", sa.String(length=20), nullable=False),
        sa.Column("outcome_reason", sa.Text(), nullable=True),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("horizon_1d_return", sa.Float(), nullable=True),
        sa.Column("horizon_5d_return", sa.Float(), nullable=True),
        sa.Column("horizon_20d_return", sa.Float(), nullable=True),
        sa.Column("benchmark_1d_return", sa.Float(), nullable=True),
        sa.Column("benchmark_5d_return", sa.Float(), nullable=True),
        sa.Column("benchmark_20d_return", sa.Float(), nullable=True),
        sa.Column("excess_1d_return", sa.Float(), nullable=True),
        sa.Column("excess_5d_return", sa.Float(), nullable=True),
        sa.Column("excess_20d_return", sa.Float(), nullable=True),
        sa.Column("buy_is_correct_20d", sa.Boolean(), nullable=True),
        sa.Column("sell_is_correct_20d", sa.Boolean(), nullable=True),
        sa.Column("scored_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["stock_analysis_reports.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["stock_signal_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_key", name="uq_stock_signal_predictions_prediction_key"),
    )
    for index_name, columns in (
        ("ix_stock_signal_predictions_run_id", ["run_id"]),
        ("ix_stock_signal_predictions_report_id", ["report_id"]),
        ("ix_stock_signal_predictions_owner_scope", ["owner_scope"]),
        ("ix_stock_signal_predictions_source", ["source"]),
        ("ix_stock_signal_predictions_universe_code", ["universe_code"]),
        ("ix_stock_signal_predictions_symbol", ["symbol"]),
        ("ix_stock_signal_predictions_as_of_date", ["as_of_date"]),
        ("ix_stock_signal_predictions_next_trading_date", ["next_trading_date"]),
        ("ix_stock_signal_predictions_signal_action", ["signal_action"]),
        ("ix_stock_signal_predictions_eligibility_status", ["eligibility_status"]),
        ("ix_stock_signal_predictions_outcome_status", ["outcome_status"]),
        ("ix_stock_signal_prediction_symbol_date", ["symbol", "as_of_date"]),
        ("ix_stock_signal_prediction_scope_symbol_date", ["owner_scope", "symbol", "as_of_date"]),
        ("ix_stock_signal_prediction_universe_date", ["universe_code", "as_of_date"]),
        ("ix_stock_signal_prediction_outcome_next_date", ["outcome_status", "next_trading_date"]),
    ):
        op.create_index(index_name, "stock_signal_predictions", columns)


def downgrade() -> None:
    global op
    op = _SchemaAwareOperations(op)
    for index_name in (
        "ix_stock_signal_prediction_outcome_next_date",
        "ix_stock_signal_prediction_universe_date",
        "ix_stock_signal_prediction_scope_symbol_date",
        "ix_stock_signal_prediction_symbol_date",
        "ix_stock_signal_predictions_outcome_status",
        "ix_stock_signal_predictions_eligibility_status",
        "ix_stock_signal_predictions_signal_action",
        "ix_stock_signal_predictions_next_trading_date",
        "ix_stock_signal_predictions_as_of_date",
        "ix_stock_signal_predictions_symbol",
        "ix_stock_signal_predictions_universe_code",
        "ix_stock_signal_predictions_source",
        "ix_stock_signal_predictions_owner_scope",
        "ix_stock_signal_predictions_report_id",
        "ix_stock_signal_predictions_run_id",
    ):
        op.drop_index(index_name, table_name="stock_signal_predictions")
    if _table_exists("stock_signal_predictions"):
        op.drop_table("stock_signal_predictions")
    for index_name in (
        "ix_stock_signal_runs_status",
        "ix_stock_signal_runs_as_of_date",
        "ix_stock_signal_runs_universe_code",
        "ix_stock_signal_runs_source",
        "ix_stock_signal_runs_owner_scope",
    ):
        op.drop_index(index_name, table_name="stock_signal_runs")
    if _table_exists("stock_signal_runs"):
        op.drop_table("stock_signal_runs")
