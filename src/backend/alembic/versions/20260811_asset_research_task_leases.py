"""Add durable leases to interactive multi-asset research tasks.

Revision ID: 20260811_asset_research_task_leases
Revises: 20260810_asset_research_option_context_binding

Interactive tasks used to move directly from ``QUEUED`` to ``RUNNING`` in an
in-process background coroutine.  A process interruption could therefore
leave an otherwise retryable task permanently ``RUNNING``.  These nullable
operational fields make the worker claim explicit and recoverable without
changing the immutable prediction or run contracts.

The expansion is DDL-only: existing tasks receive a server-side attempt
default of zero and no synthetic lease or historical lifecycle mutation.
"""

# alembic-meta: estimated_rows=0; lock_kind=long

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260811_asset_research_task_leases"
down_revision = "20260810_asset_research_option_context_binding"
branch_labels = None
depends_on = None

_TASK_TABLE = "asset_analysis_tasks"
_LEASE_PAIR_CHECK = "ck_asset_task_lease_pair"
_ATTEMPT_COUNT_CHECK = "ck_asset_task_attempt_count"
_CLAIM_INDEX = "ix_asset_task_runner_claim"


def upgrade() -> None:
    """Expand task operational state without inventing a historic lease."""
    with op.batch_alter_table(_TASK_TABLE) as batch:
        batch.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.create_check_constraint(
            _LEASE_PAIR_CHECK,
            "(lease_token IS NULL AND lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL "
            "AND lease_heartbeat_at IS NOT NULL)",
        )
        batch.create_check_constraint(_ATTEMPT_COUNT_CHECK, "attempt_count >= 0")
        batch.create_index(
            _CLAIM_INDEX,
            ["status", "lease_expires_at", "created_at"],
        )


def downgrade() -> None:
    """Remove only operational lease columns; predictions and runs remain untouched."""
    with op.batch_alter_table(_TASK_TABLE) as batch:
        batch.drop_index(_CLAIM_INDEX)
        batch.drop_constraint(_ATTEMPT_COUNT_CHECK, type_="check")
        batch.drop_constraint(_LEASE_PAIR_CHECK, type_="check")
        batch.drop_column("attempt_count")
        batch.drop_column("lease_heartbeat_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_token")
