"""Baseline migration covering all existing ORM tables.

Revision ID: 0001_baseline
Revises: None
Create Date: 2024-01-15 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- refresh_tokens ---
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("token_hash", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), default=False, index=True),
    )

    # --- user_roles ---
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(20), primary_key=True),
    )

    # --- strategies ---
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON()),
        sa.Column("category", sa.String(50), index=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- strategy_versions ---
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "strategy_id", sa.String(36), sa.ForeignKey("strategies.id"), nullable=False, index=True
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("version_name", sa.String(50), nullable=False),
        sa.Column("branch", sa.String(50)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tags", sa.JSON()),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON()),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "parent_version_id", sa.String(36), sa.ForeignKey("strategy_versions.id"), nullable=True
        ),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- version_comparisons ---
    op.create_table(
        "version_comparisons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "strategy_id", sa.String(36), sa.ForeignKey("strategies.id"), nullable=False, index=True
        ),
        sa.Column(
            "from_version_id", sa.String(36), sa.ForeignKey("strategy_versions.id"), nullable=False
        ),
        sa.Column(
            "to_version_id", sa.String(36), sa.ForeignKey("strategy_versions.id"), nullable=False
        ),
        sa.Column("code_diff", sa.Text(), nullable=True),
        sa.Column("params_diff", sa.JSON()),
        sa.Column("performance_diff", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    )

    # --- version_rollbacks ---
    op.create_table(
        "version_rollbacks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "strategy_id", sa.String(36), sa.ForeignKey("strategies.id"), nullable=False, index=True
        ),
        sa.Column(
            "from_version_id", sa.String(36), sa.ForeignKey("strategy_versions.id"), nullable=False
        ),
        sa.Column(
            "to_version_id", sa.String(36), sa.ForeignKey("strategy_versions.id"), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("snapshot_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    )

    # --- strategy_branches ---
    op.create_table(
        "strategy_branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "strategy_id", sa.String(36), sa.ForeignKey("strategies.id"), nullable=False, index=True
        ),
        sa.Column("branch_name", sa.String(50), nullable=False, index=True),
        sa.Column("parent_branch", sa.String(50), nullable=True),
        sa.Column("version_count", sa.Integer(), nullable=False),
        sa.Column(
            "last_version_id", sa.String(36), sa.ForeignKey("strategy_versions.id"), nullable=True
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    )

    # --- backtest_tasks ---
    op.create_table(
        "backtest_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(36), index=True),
        sa.Column(
            "strategy_version_id",
            sa.String(36),
            sa.ForeignKey("strategy_versions.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("symbol", sa.String(20), index=True),
        sa.Column("status", sa.String(20)),
        sa.Column("request_data", sa.JSON()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("log_dir", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- backtest_results ---
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id", sa.String(36), sa.ForeignKey("backtest_tasks.id"), unique=True, index=True
        ),
        sa.Column("total_return", sa.Float()),
        sa.Column("annual_return", sa.Float()),
        sa.Column("sharpe_ratio", sa.Float()),
        sa.Column("max_drawdown", sa.Float()),
        sa.Column("win_rate", sa.Float()),
        sa.Column("metrics_source", sa.String(20)),
        sa.Column("total_trades", sa.Integer()),
        sa.Column("profitable_trades", sa.Integer()),
        sa.Column("losing_trades", sa.Integer()),
        sa.Column("equity_curve", sa.JSON()),
        sa.Column("equity_dates", sa.JSON()),
        sa.Column("drawdown_curve", sa.JSON()),
        sa.Column("trades", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- optimization_tasks ---
    op.create_table(
        "optimization_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(20)),
        sa.Column("total", sa.Integer()),
        sa.Column("completed", sa.Integer()),
        sa.Column("failed", sa.Integer()),
        sa.Column("results", sa.JSON()),
        sa.Column("param_ranges", sa.JSON(), nullable=True),
        sa.Column("n_workers", sa.Integer()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- backtest_comparisons ---
    op.create_table(
        "backtest_comparisons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("backtest_task_ids", sa.JSON(), nullable=False),
        sa.Column("comparison_data", sa.JSON(), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- comparison_shares ---
    op.create_table(
        "comparison_shares",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "comparison_id",
            sa.String(36),
            sa.ForeignKey("backtest_comparisons.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "shared_with_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("can_edit", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- comparison_backtest_association ---
    op.create_table(
        "comparison_backtest_association",
        sa.Column(
            "comparison_id",
            sa.String(36),
            sa.ForeignKey("backtest_comparisons.id"),
            primary_key=True,
        ),
        sa.Column(
            "backtest_task_id", sa.String(36), sa.ForeignKey("backtest_tasks.id"), primary_key=True
        ),
    )

    # --- workspaces ---
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("workspace_type", sa.String(32), nullable=False, index=True),
        sa.Column("settings", sa.JSON()),
        sa.Column("trading_config", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- strategy_units ---
    op.create_table(
        "strategy_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("group_name", sa.String(200), nullable=True),
        sa.Column("strategy_id", sa.String(100), nullable=True),
        sa.Column("strategy_name", sa.String(200), nullable=True),
        sa.Column("symbol", sa.String(50), nullable=True),
        sa.Column("symbol_name", sa.String(200), nullable=True),
        sa.Column("timeframe", sa.String(10), nullable=True),
        sa.Column("timeframe_n", sa.Integer()),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer()),
        sa.Column("data_config", sa.JSON()),
        sa.Column("unit_settings", sa.JSON()),
        sa.Column("params", sa.JSON()),
        sa.Column("optimization_config", sa.JSON()),
        sa.Column("trading_mode", sa.String(20), nullable=False),
        sa.Column("gateway_config", sa.JSON()),
        sa.Column("lock_trading", sa.Boolean(), nullable=False),
        sa.Column("lock_running", sa.Boolean(), nullable=False),
        sa.Column("trading_instance_id", sa.String(36), nullable=True),
        sa.Column("trading_snapshot", sa.JSON()),
        sa.Column("run_status", sa.String(20)),
        sa.Column("run_count", sa.Integer()),
        sa.Column("last_run_time", sa.Float(), nullable=True),
        sa.Column("last_task_id", sa.String(36), nullable=True),
        sa.Column("last_optimization_task_id", sa.String(36), nullable=True),
        sa.Column("bar_count", sa.Integer(), nullable=True),
        sa.Column("metrics_snapshot", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- paper_trading_accounts ---
    op.create_table(
        "paper_trading_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("initial_cash", sa.Float(), nullable=False),
        sa.Column("current_cash", sa.Float(), nullable=False),
        sa.Column("total_equity", sa.Float(), nullable=False),
        sa.Column("profit_loss", sa.Float(), nullable=False),
        sa.Column("profit_loss_pct", sa.Float(), nullable=False),
        sa.Column("commission_rate", sa.Float(), nullable=False),
        sa.Column("slippage_rate", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- paper_trading_positions ---
    op.create_table(
        "paper_trading_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("market_value", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl_pct", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("entry_time", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- paper_trading_orders ---
    op.create_table(
        "paper_trading_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("limit_price", sa.Float(), nullable=True),
        sa.Column("filled_size", sa.Integer(), nullable=False),
        sa.Column("avg_fill_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("rejected_reason", sa.String(255), nullable=True),
        sa.Column("commission", sa.Float(), nullable=False),
        sa.Column("slippage", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("filled_at", sa.DateTime(), nullable=True),
    )

    # --- paper_trades ---
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_accounts.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_orders.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("commission", sa.Float(), nullable=False),
        sa.Column("slippage", sa.Float(), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("pnl_pct", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- knowledge_bases ---
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("settings", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- kb_documents ---
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("is_folder", sa.Boolean(), nullable=False),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("kb_documents.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("index_status", sa.String(20), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- document_chunks ---
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("kb_documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- chat_conversations ---
    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "knowledge_base_id",
            sa.String(36),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=True),
        sa.Column("settings", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- chat_messages ---
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.String(200), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- model_configs ---
    op.create_table(
        "model_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_name", sa.String(200), nullable=False, unique=True),
        sa.Column("category", sa.String(20), nullable=False, index=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("max_context", sa.Integer(), nullable=True),
        sa.Column("max_output", sa.Integer(), nullable=True),
        sa.Column("input_price", sa.Integer(), nullable=True),
        sa.Column("output_price", sa.Integer(), nullable=True),
        sa.Column("parameters", sa.JSON()),
        sa.Column("features", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- model_usage_logs ---
    op.create_table(
        "model_usage_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "model_id", sa.String(36), sa.ForeignKey("model_configs.id"), nullable=False, index=True
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- alerts ---
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_config", sa.JSON(), nullable=False),
        sa.Column("notification_enabled", sa.Boolean(), nullable=False),
        sa.Column("notification_channels", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("triggered_count", sa.Integer(), nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("alert_type", sa.String(20), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column(
            "rule_id", sa.String(36), sa.ForeignKey("alert_rules.id"), nullable=True, index=True
        ),
        sa.Column(
            "strategy_id", sa.String(36), sa.ForeignKey("strategies.id"), nullable=True, index=True
        ),
        sa.Column(
            "backtest_task_id",
            sa.String(36),
            sa.ForeignKey("backtest_tasks.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_accounts.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "position_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_positions.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("paper_trading_orders.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_value", sa.Float(), nullable=True),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("is_notification_sent", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    op.create_table(
        "alert_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "alert_id", sa.String(36), sa.ForeignKey("alerts.id"), nullable=False, index=True
        ),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- akshare data management ---
    op.create_table(
        "ak_data_scripts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("script_id", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("script_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("sub_category", sa.String(50), nullable=True, index=True),
        sa.Column(
            "frequency",
            sa.Enum(
                "hourly", "daily", "weekly", "monthly", "once", "manual", name="scriptfrequency"
            ),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("target_table", sa.String(100), nullable=True, index=True),
        sa.Column("module_path", sa.String(255), nullable=True),
        sa.Column("function_name", sa.String(100), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=True),
        sa.Column("estimated_duration", sa.Integer(), nullable=False),
        sa.Column("timeout", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, index=True),
        sa.Column(
            "created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True
        ),
        sa.Column(
            "updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ak_data_tables",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("table_comment", sa.String(200), nullable=True),
        sa.Column("category", sa.String(50), nullable=True, index=True),
        sa.Column("script_id", sa.String(100), nullable=True, index=True),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("last_update_time", sa.DateTime(), nullable=True, index=True),
        sa.Column("last_update_status", sa.String(20), nullable=True),
        sa.Column("data_start_date", sa.Date(), nullable=True),
        sa.Column("data_end_date", sa.Date(), nullable=True),
        sa.Column("symbol_raw", sa.String(100), nullable=True, index=True),
        sa.Column("symbol_normalized", sa.String(100), nullable=True, index=True),
        sa.Column("market", sa.String(50), nullable=True, index=True),
        sa.Column("asset_type", sa.String(50), nullable=True, index=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ak_interface_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )

    op.create_table(
        "ak_data_interfaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("ak_interface_categories.id"), nullable=False
        ),
        sa.Column("module_path", sa.String(255), nullable=True),
        sa.Column("function_name", sa.String(100), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("extra_config", sa.JSON(), nullable=False),
        sa.Column("return_type", sa.String(50), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ak_interface_parameters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "interface_id", sa.Integer(), sa.ForeignKey("ak_data_interfaces.id"), nullable=False
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "param_type",
            sa.Enum(
                "string",
                "integer",
                "float",
                "boolean",
                "date",
                "list",
                "option",
                name="parametertype",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )

    op.create_table(
        "ak_scheduled_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column(
            "script_id", sa.String(100), sa.ForeignKey("ak_data_scripts.script_id"), nullable=False
        ),
        sa.Column(
            "schedule_type",
            sa.Enum("once", "daily", "weekly", "monthly", "cron", "interval", name="scheduletype"),
            nullable=False,
        ),
        sa.Column("schedule_expression", sa.String(100), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("retry_on_failure", sa.Boolean(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("timeout", sa.Integer(), nullable=False),
        sa.Column("last_execution_at", sa.DateTime(), nullable=True),
        sa.Column("next_execution_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ak_task_executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("ak_scheduled_tasks.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("script_id", sa.String(100), nullable=False, index=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "timeout",
                "cancelled",
                name="taskstatus",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_trace", sa.Text(), nullable=True),
        sa.Column("rows_before", sa.Integer(), nullable=True),
        sa.Column("rows_after", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column(
            "triggered_by",
            sa.Enum("scheduler", "manual", "api", name="triggeredby"),
            nullable=False,
        ),
        sa.Column(
            "operator_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ak_task_executions")
    op.drop_table("ak_scheduled_tasks")
    op.drop_table("ak_interface_parameters")
    op.drop_table("ak_data_interfaces")
    op.drop_table("ak_interface_categories")
    op.drop_table("ak_data_tables")
    op.drop_table("ak_data_scripts")
    op.drop_table("alert_notifications")
    op.drop_table("alerts")
    op.drop_table("alert_rules")
    op.drop_table("model_usage_logs")
    op.drop_table("model_configs")
    op.drop_table("chat_messages")
    op.drop_table("chat_conversations")
    op.drop_table("document_chunks")
    op.drop_table("kb_documents")
    op.drop_table("knowledge_bases")
    op.drop_table("paper_trades")
    op.drop_table("paper_trading_orders")
    op.drop_table("paper_trading_positions")
    op.drop_table("paper_trading_accounts")
    op.drop_table("strategy_units")
    op.drop_table("workspaces")
    op.drop_table("comparison_backtest_association")
    op.drop_table("comparison_shares")
    op.drop_table("backtest_comparisons")
    op.drop_table("optimization_tasks")
    op.drop_table("backtest_results")
    op.drop_table("backtest_tasks")
    op.drop_table("strategy_branches")
    op.drop_table("version_rollbacks")
    op.drop_table("version_comparisons")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
    op.drop_table("user_roles")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
