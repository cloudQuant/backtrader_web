"""Enforce globally unique workspace paper-runtime identifiers.

Revision ID: 20260718_runtime_identity_lifecycle
Revises: 20260718_paper_runtime_risk_schema
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260718_runtime_identity_lifecycle"
down_revision = "20260718_paper_runtime_risk_schema"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_strategy_units_trading_instance_id"


def _has_index(table: str, name: str) -> bool:
    """Return whether a named index exists on the current bind."""
    return name in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}


def _duplicate_runtime_ids() -> list[str]:
    """Find legacy non-null runtime identifiers that cannot be made unique safely."""
    rows = op.get_bind().execute(
        sa.text(
            """
            SELECT trading_instance_id
            FROM strategy_units
            WHERE trading_instance_id IS NOT NULL
              AND trading_instance_id <> ''
            GROUP BY trading_instance_id
            HAVING COUNT(*) > 1
            LIMIT 10
            """
        )
    )
    return [str(row[0]) for row in rows]


def upgrade() -> None:
    """Make the public paper-runtime selector globally unique.

    A duplicate cannot be remapped automatically without risking a live runner
    association. Stop with a precise forward-fix instruction instead of silently
    changing a legacy unit's identifier.
    """
    if _has_index("strategy_units", _INDEX_NAME):
        identity_ready = True
    else:
        duplicates = _duplicate_runtime_ids()
        if duplicates:
            sample = ", ".join(duplicates)
            raise RuntimeError(
                "Cannot enforce unique strategy_units.trading_instance_id; "
                f"duplicate non-null runtime IDs found: {sample}. "
                "Resolve the duplicate runner mappings before retrying this migration."
            )
        op.create_index(_INDEX_NAME, "strategy_units", ["trading_instance_id"], unique=True)
        identity_ready = True

    if identity_ready:
        columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("risk_rules")}
        if "version" not in columns:
            op.add_column(
                "risk_rules",
                sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            )


def downgrade() -> None:
    """Remove the identity guard only in isolated rollback environments."""
    if _has_index("strategy_units", _INDEX_NAME):
        op.drop_index(_INDEX_NAME, table_name="strategy_units")
