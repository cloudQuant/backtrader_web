"""Add ai_call_logs table.

Revision ID: 0006_add_ai_call_logs
Revises: 0005_add_ai_trading_logs
Create Date: 2026-05-24
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_add_ai_call_logs"
down_revision = "0005_add_ai_trading_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_call_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("request_id", sa.String(64), nullable=True, index=True),
        sa.Column("service_name", sa.String(50), nullable=False, index=True),
        sa.Column("mode", sa.String(50), nullable=False, index=True),
        sa.Column("model_name", sa.String(100), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False, index=True),
        sa.Column("prompt_template_id", sa.String(100), nullable=True, index=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("error_code", sa.String(100), nullable=True, index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("response_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_hash", sa.String(64), nullable=False, index=True),
    )
    op.create_index("ix_ai_call_logs_created_at", "ai_call_logs", ["created_at"])
    op.create_index("ix_ai_call_logs_user_created_at", "ai_call_logs", ["user_id", "created_at"])
    op.create_index(
        "ix_ai_call_logs_service_created_at", "ai_call_logs", ["service_name", "created_at"]
    )
    op.create_index("ix_ai_call_logs_status_created_at", "ai_call_logs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_call_logs_status_created_at", table_name="ai_call_logs")
    op.drop_index("ix_ai_call_logs_service_created_at", table_name="ai_call_logs")
    op.drop_index("ix_ai_call_logs_user_created_at", table_name="ai_call_logs")
    op.drop_index("ix_ai_call_logs_created_at", table_name="ai_call_logs")
    op.drop_table("ai_call_logs")
