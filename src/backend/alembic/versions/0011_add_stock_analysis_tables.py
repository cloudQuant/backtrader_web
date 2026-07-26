"""Add native stock analysis tables.

Revision ID: 0011_add_stock_analysis_tables
Revises: 0010_add_prompt_rollout_fields
Create Date: 2026-06-15
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_add_stock_analysis_tables"
down_revision = "0010_add_prompt_rollout_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_analysis_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=True),
        sa.Column("assistant_message_id", sa.String(36), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="ai_assistant"),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("symbol_name", sa.String(255), nullable=True),
        sa.Column("market_type", sa.String(32), nullable=False, server_default="A股"),
        sa.Column("analysis_date", sa.String(32), nullable=False),
        sa.Column("research_depth", sa.String(32), nullable=False, server_default="标准"),
        sa.Column("selected_modules", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("request_text", sa.Text(), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("step_events_json", sa.JSON(), nullable=True),
        sa.Column("data_quality_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_stock_analysis_tasks_user_id", "stock_analysis_tasks", ["user_id"])
    op.create_index(
        "ix_stock_analysis_tasks_conversation_id", "stock_analysis_tasks", ["conversation_id"]
    )
    op.create_index(
        "ix_stock_analysis_tasks_assistant_message_id",
        "stock_analysis_tasks",
        ["assistant_message_id"],
    )
    op.create_index("ix_stock_analysis_tasks_symbol", "stock_analysis_tasks", ["symbol"])
    op.create_index("ix_stock_analysis_tasks_status", "stock_analysis_tasks", ["status"])
    op.create_index("ix_stock_analysis_tasks_report_id", "stock_analysis_tasks", ["report_id"])

    op.create_table(
        "stock_analysis_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("stock_analysis_tasks.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("market_type", sa.String(32), nullable=False, server_default="A股"),
        sa.Column("analysis_date", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommendation_label", sa.String(20), nullable=False, server_default="持有"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="中等"),
        sa.Column("technical_score", sa.Float(), nullable=True),
        sa.Column("fundamental_score", sa.Float(), nullable=True),
        sa.Column("news_score", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("data_quality_json", sa.JSON(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("markdown_content", sa.Text(), nullable=True),
        sa.Column("html_content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_stock_analysis_reports_task_id", "stock_analysis_reports", ["task_id"])
    op.create_index("ix_stock_analysis_reports_user_id", "stock_analysis_reports", ["user_id"])
    op.create_index("ix_stock_analysis_reports_symbol", "stock_analysis_reports", ["symbol"])

    op.create_table(
        "stock_analysis_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(36),
            sa.ForeignKey("stock_analysis_reports.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_stock_analysis_exports_report_id", "stock_analysis_exports", ["report_id"])
    op.create_index("ix_stock_analysis_exports_user_id", "stock_analysis_exports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_analysis_exports_user_id", table_name="stock_analysis_exports")
    op.drop_index("ix_stock_analysis_exports_report_id", table_name="stock_analysis_exports")
    op.drop_table("stock_analysis_exports")
    op.drop_index("ix_stock_analysis_reports_symbol", table_name="stock_analysis_reports")
    op.drop_index("ix_stock_analysis_reports_user_id", table_name="stock_analysis_reports")
    op.drop_index("ix_stock_analysis_reports_task_id", table_name="stock_analysis_reports")
    op.drop_table("stock_analysis_reports")
    op.drop_index("ix_stock_analysis_tasks_report_id", table_name="stock_analysis_tasks")
    op.drop_index("ix_stock_analysis_tasks_status", table_name="stock_analysis_tasks")
    op.drop_index("ix_stock_analysis_tasks_symbol", table_name="stock_analysis_tasks")
    op.drop_index(
        "ix_stock_analysis_tasks_assistant_message_id",
        table_name="stock_analysis_tasks",
    )
    op.drop_index("ix_stock_analysis_tasks_conversation_id", table_name="stock_analysis_tasks")
    op.drop_index("ix_stock_analysis_tasks_user_id", table_name="stock_analysis_tasks")
    op.drop_table("stock_analysis_tasks")
