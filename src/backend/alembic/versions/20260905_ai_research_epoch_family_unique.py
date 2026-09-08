"""Make the server-derived experiment family a one-time disclosure budget.

Revision ID: 20260905_ai_research_epoch_family_unique
Revises: 20260905_ai_research_dataset_storage_reference

One user must not recreate the same canonical research family after it has
consumed (or is about to consume) its sealed-holdout budget.  The preflight
intentionally blocks upgrade if an older installation already has duplicate
families: silently picking one record would manufacture an unsafe history.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260905_ai_research_epoch_family_unique"
down_revision = "20260905_ai_research_dataset_storage_reference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reject ambiguous legacy families before adding a portable uniqueness guard."""

    duplicate = op.get_bind().execute(
        sa.text(
            "SELECT user_id, family_hash FROM ai_research_experiment_epochs "
            "GROUP BY user_id, family_hash HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError("EXPERIMENT_EPOCH_FAMILY_DEDUPLICATION_REQUIRED")
    with op.batch_alter_table("ai_research_experiment_epochs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_ai_research_epoch_owner_family",
            ["user_id", "family_hash"],
        )


def downgrade() -> None:
    """Remove only the database guard introduced by this migration."""

    with op.batch_alter_table("ai_research_experiment_epochs") as batch_op:
        batch_op.drop_constraint("uq_ai_research_epoch_owner_family", type_="unique")
