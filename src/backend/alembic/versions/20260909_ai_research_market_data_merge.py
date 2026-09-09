"""Merge Iteration 196 research and Iteration 197 market-data heads.

Revision ID: 20260909_ai_research_market_data_merge
Revises: 20260908_ai_research_approval_authority,
20260909_market_data_constraint_name_portability
Create Date: 2026-09-09

This revision intentionally contains no DDL.  It joins the independently
validated Iteration 196 research chain and Iteration 197 market-data chain so
new environments have one Alembic head.
"""

from __future__ import annotations

from collections.abc import Sequence

revision = "20260909_ai_research_market_data_merge"
down_revision: str | Sequence[str] | None = (
    "20260908_ai_research_approval_authority",
    "20260909_market_data_constraint_name_portability",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the revision graph without changing database objects."""


def downgrade() -> None:
    """Split the revision graph without changing database objects."""
