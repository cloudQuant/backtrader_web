import sqlalchemy as sa

from alembic import op

revision = "0010_add_prompt_rollout_fields"
down_revision = "0009_add_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prompt_templates",
        sa.Column("rollout_percentage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ai_call_logs",
        sa.Column("prompt_template_version", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_ai_call_logs_prompt_template_version",
        "ai_call_logs",
        ["prompt_template_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_call_logs_prompt_template_version", table_name="ai_call_logs")
    op.drop_column("ai_call_logs", "prompt_template_version")
    op.drop_column("prompt_templates", "rollout_percentage")
