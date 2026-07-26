"""Create workspace paper-runtime audit and equity storage.

Revision ID: 20260718_paper_runtime_risk_schema
Revises: 20260718_ai_research_audit_schema
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260718_paper_runtime_risk_schema"
down_revision = "20260718_ai_research_audit_schema"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _create_index_if_missing(
    name: str, table: str, columns: list[str], *, unique: bool = False
) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    """Create paper runtime tables and expand existing Alert scope safely."""
    if not _has_table("paper_review_reports"):
        op.create_table(
            "paper_review_reports",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
            ),
            sa.Column("unit_id", sa.String(36), sa.ForeignKey("strategy_units.id"), nullable=False),
            sa.Column("instance_id", sa.String(36), nullable=False),
            sa.Column(
                "paper_account_id", sa.String(36), sa.ForeignKey("paper_trading_accounts.id")
            ),
            sa.Column("source_record_id", sa.String(36), nullable=True, unique=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("observation_start_at", sa.DateTime(), nullable=True),
            sa.Column("observation_end_at", sa.DateTime(), nullable=True),
            sa.Column("report", sa.JSON(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("live_handoff_reviews"):
        op.create_table(
            "live_handoff_reviews",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
            ),
            sa.Column("unit_id", sa.String(36), sa.ForeignKey("strategy_units.id"), nullable=False),
            sa.Column("instance_id", sa.String(36), nullable=False),
            sa.Column(
                "paper_account_id", sa.String(36), sa.ForeignKey("paper_trading_accounts.id")
            ),
            sa.Column("source_record_id", sa.String(36), nullable=True, unique=True),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("checklist", sa.JSON(), nullable=False),
            sa.Column("decided_by", sa.String(120), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("risk_rules"):
        op.create_table(
            "risk_rules",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=True),
            sa.Column("unit_id", sa.String(36), sa.ForeignKey("strategy_units.id"), nullable=True),
            sa.Column("instance_id", sa.String(36), nullable=True),
            sa.Column(
                "paper_account_id", sa.String(36), sa.ForeignKey("paper_trading_accounts.id")
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("rule_type", sa.String(64), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if not _has_table("paper_equity_snapshots"):
        op.create_table(
            "paper_equity_snapshots",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(
                "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
            ),
            sa.Column("unit_id", sa.String(36), sa.ForeignKey("strategy_units.id"), nullable=False),
            sa.Column("instance_id", sa.String(36), nullable=False),
            sa.Column(
                "paper_account_id", sa.String(36), sa.ForeignKey("paper_trading_accounts.id")
            ),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("source", sa.String(32), nullable=False),
            sa.Column("total_equity", sa.Float(), nullable=False),
            sa.Column("cash", sa.Float(), nullable=False),
            sa.Column("position_value", sa.Float(), nullable=False),
            sa.Column("unrealized_pnl", sa.Float(), nullable=False),
            sa.Column("realized_pnl", sa.Float(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if _has_table("alerts"):
        columns = _columns("alerts")
        for name, column in (
            ("workspace_id", sa.Column("workspace_id", sa.String(36), nullable=True)),
            ("unit_id", sa.Column("unit_id", sa.String(36), nullable=True)),
            ("instance_id", sa.Column("instance_id", sa.String(36), nullable=True)),
            ("dedupe_key", sa.Column("dedupe_key", sa.String(200), nullable=True)),
        ):
            if name not in columns:
                op.add_column("alerts", column)

    for table, name, columns, unique in (
        (
            "paper_review_reports",
            "ix_paper_review_reports_runtime_created",
            ["instance_id", "created_at"],
            False,
        ),
        (
            "paper_review_reports",
            "ix_paper_review_reports_user_runtime",
            ["user_id", "instance_id"],
            False,
        ),
        (
            "live_handoff_reviews",
            "ix_live_handoff_reviews_runtime_created",
            ["instance_id", "created_at"],
            False,
        ),
        (
            "live_handoff_reviews",
            "ix_live_handoff_reviews_user_runtime",
            ["user_id", "instance_id"],
            False,
        ),
        (
            "risk_rules",
            "ix_risk_rules_user_scope",
            ["user_id", "workspace_id", "unit_id", "instance_id"],
            False,
        ),
        (
            "paper_equity_snapshots",
            "ix_paper_equity_snapshots_runtime_at",
            ["instance_id", "observed_at"],
            False,
        ),
        (
            "paper_equity_snapshots",
            "ix_paper_equity_snapshots_user_runtime_at",
            ["user_id", "instance_id", "observed_at"],
            False,
        ),
        (
            "paper_equity_snapshots",
            "uq_paper_equity_snapshots_idempotency",
            ["instance_id", "source", "observed_at"],
            True,
        ),
        (
            "alerts",
            "ix_alerts_user_instance_created",
            ["user_id", "instance_id", "created_at"],
            False,
        ),
        ("alerts", "ix_alerts_dedupe_key", ["dedupe_key"], False),
    ):
        _create_index_if_missing(name, table, columns, unique=unique)


def downgrade() -> None:
    """Drop only new tables in isolated environments; alert expansion is forward-only."""
    for table in (
        "paper_equity_snapshots",
        "risk_rules",
        "live_handoff_reviews",
        "paper_review_reports",
    ):
        if _has_table(table):
            op.drop_table(table)
