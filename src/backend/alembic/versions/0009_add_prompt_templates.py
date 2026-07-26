import sqlalchemy as sa

from alembic import op

revision = "0009_add_prompt_templates"
down_revision = "0008_add_ai_model_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_prompt_templates_name_version"),
    )
    op.create_index("ix_prompt_templates_name", "prompt_templates", ["name"])
    op.create_index("ix_prompt_templates_status", "prompt_templates", ["status"])
    op.create_index("ix_prompt_templates_created_by", "prompt_templates", ["created_by"])
    op.create_index("ix_prompt_templates_name_status", "prompt_templates", ["name", "status"])


def downgrade() -> None:
    op.drop_index("ix_prompt_templates_name_status", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_created_by", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_status", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_name", table_name="prompt_templates")
    op.drop_table("prompt_templates")
