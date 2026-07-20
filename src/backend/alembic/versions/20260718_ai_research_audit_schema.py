"""Create durable AI research audit tables.

Revision ID: 20260718_ai_research_audit_schema
Revises: 20260705_b_data_backtest_trust
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260718_ai_research_audit_schema"
down_revision = "20260705_b_data_backtest_trust"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, name: str) -> bool:
    return name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns, unique=False)


def upgrade() -> None:
    """Create missing audit tables without failing legacy create_all databases."""
    if not _has_table("investment_mandates"):
        op.create_table(
            "investment_mandates",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("raw_prompt", sa.Text(), nullable=False),
            sa.Column("structured_goal", sa.JSON(), nullable=False),
            sa.Column("asset_scope", sa.JSON(), nullable=False),
            sa.Column("timeframe", sa.String(20), nullable=True),
            sa.Column("objective", sa.Text(), nullable=True),
            sa.Column("risk_constraints", sa.JSON(), nullable=False),
            sa.Column("trading_constraints", sa.JSON(), nullable=False),
            sa.Column("quality_gates", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("source", sa.String(30), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("research_pipeline_events"):
        op.create_table(
            "research_pipeline_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=True),
            sa.Column("mandate_id", sa.String(36), sa.ForeignKey("investment_mandates.id")),
            sa.Column("stage", sa.String(60), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("iteration", sa.Integer(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("input_payload", sa.JSON(), nullable=False),
            sa.Column("output_payload", sa.JSON(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("ai_strategy_research_versions"):
        op.create_table(
            "ai_strategy_research_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=True),
            sa.Column("mandate_id", sa.String(36), sa.ForeignKey("investment_mandates.id")),
            sa.Column("strategy_id", sa.String(36), nullable=True),
            sa.Column("unit_id", sa.String(36), nullable=True),
            sa.Column("backtest_task_id", sa.String(80), nullable=True),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("version_name", sa.String(120), nullable=False),
            sa.Column(
                "parent_version_id",
                sa.String(36),
                sa.ForeignKey("ai_strategy_research_versions.id"),
            ),
            sa.Column("strategy_name", sa.String(200), nullable=True),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("params", sa.JSON(), nullable=False),
            sa.Column("ai_rationale", sa.Text(), nullable=True),
            sa.Column("change_summary", sa.Text(), nullable=True),
            sa.Column("backtest_metrics", sa.JSON(), nullable=False),
            sa.Column("quality_gate_evaluations", sa.JSON(), nullable=False),
            sa.Column("quality_gate_status", sa.String(20), nullable=False),
            sa.Column("review", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "user_id", "run_id", "version_no", name="uq_ai_research_version_no"
            ),
        )
    if not _has_table("ai_strategy_research_version_comparisons"):
        op.create_table(
            "ai_strategy_research_version_comparisons",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column(
                "left_version_id",
                sa.String(36),
                sa.ForeignKey("ai_strategy_research_versions.id"),
                nullable=False,
            ),
            sa.Column(
                "right_version_id",
                sa.String(36),
                sa.ForeignKey("ai_strategy_research_versions.id"),
                nullable=False,
            ),
            sa.Column("metric_deltas", sa.JSON(), nullable=False),
            sa.Column("gate_deltas", sa.JSON(), nullable=False),
            sa.Column("code_diff", sa.Text(), nullable=False),
            sa.Column("verdict", sa.String(30), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    for table, name, columns in (
        ("investment_mandates", "ix_investment_mandates_user_id", ["user_id"]),
        ("investment_mandates", "ix_investment_mandates_status", ["status"]),
        ("research_pipeline_events", "ix_research_pipeline_events_user_id", ["user_id"]),
        ("research_pipeline_events", "ix_research_pipeline_events_run_id", ["run_id"]),
        ("research_pipeline_events", "ix_research_pipeline_events_workspace_id", ["workspace_id"]),
        ("research_pipeline_events", "ix_research_pipeline_events_created_at", ["created_at"]),
        ("ai_strategy_research_versions", "ix_ai_strategy_research_versions_run_id", ["run_id"]),
        (
            "ai_strategy_research_versions",
            "ix_ai_strategy_research_versions_created_at",
            ["created_at"],
        ),
        (
            "ai_strategy_research_version_comparisons",
            "ix_ai_strategy_research_version_comparisons_run_id",
            ["run_id"],
        ),
    ):
        _create_index_if_missing(name, table, columns)


def downgrade() -> None:
    """Remove tables only from isolated databases; production uses forward fixes."""
    for table in (
        "ai_strategy_research_version_comparisons",
        "ai_strategy_research_versions",
        "research_pipeline_events",
        "investment_mandates",
    ):
        if _has_table(table):
            op.drop_table(table)
