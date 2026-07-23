"""Add workspace listing indexes.

Revision ID: 0015_add_workspace_listing_indexes
Revises: 0014_add_paper_trading_margin_fields
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_add_workspace_listing_indexes"
down_revision = "0014_add_paper_trading_margin_fields"
branch_labels = None
depends_on = None


def _has_index(table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    """Add composite indexes for workspace list endpoints."""
    if not _has_index("workspaces", "ix_workspaces_user_type_updated_id"):
        op.create_index(
            "ix_workspaces_user_type_updated_id",
            "workspaces",
            ["user_id", "workspace_type", "updated_at", "id"],
            unique=False,
        )
    if not _has_index("workspaces", "ix_workspaces_user_updated_id"):
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
