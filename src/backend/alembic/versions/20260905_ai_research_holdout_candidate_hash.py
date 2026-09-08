"""Bind every sealed-holdout token to a frozen candidate content hash.

Revision ID: 20260905_ai_research_holdout_candidate_hash
Revises: 20260905_ai_research_data_prechecks

An authorization that records only a mutable candidate ID can no longer prove
which code/parameters/environment it evaluated.  This expand migration records
the frozen candidate digest and backfills existing v2 rows from their linked
candidate before making the field mandatory.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_holdout_candidate_hash"
down_revision = "20260905_ai_research_data_prechecks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Attach the immutable candidate hash to existing authorization receipts."""

    with op.batch_alter_table("ai_research_holdout_authorizations") as batch_op:
        batch_op.add_column(sa.Column("candidate_hash", sa.String(length=64), nullable=True))
    op.execute(
        """
        UPDATE ai_research_holdout_authorizations
        SET candidate_hash = (
            SELECT candidate_hash
            FROM ai_research_candidates
            WHERE ai_research_candidates.id = ai_research_holdout_authorizations.candidate_id
        )
        """
    )
    with op.batch_alter_table("ai_research_holdout_authorizations") as batch_op:
        batch_op.alter_column(
            "candidate_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )


def downgrade() -> None:
    """Remove only the new hash binding from v2 authorization receipts."""

    with op.batch_alter_table("ai_research_holdout_authorizations") as batch_op:
        batch_op.drop_column("candidate_hash")
