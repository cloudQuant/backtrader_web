"""Add workspace listing indexes.

Revision ID: 0015_add_workspace_listing_indexes
Revises: 0014_add_paper_trading_margin_fields
Create Date: 2026-07-04
"""

from __future__ import annotations

from alembic import op

revision = "0015_add_workspace_listing_indexes"
down_revision = "0014_add_paper_trading_margin_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add composite indexes for workspace list endpoints."""
    op.create_index(
        "ix_workspaces_user_type_updated_id",
        "workspaces",
        ["user_id", "workspace_type", "updated_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_workspaces_user_updated_id",
        "workspaces",
        ["user_id", "updated_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop composite indexes for workspace list endpoints."""
    op.drop_index("ix_workspaces_user_updated_id", table_name="workspaces")
    op.drop_index("ix_workspaces_user_type_updated_id", table_name="workspaces")
