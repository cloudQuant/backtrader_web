"""Add a durable per-prediction lease for outcome evaluation workers.

Revision ID: 20260805_asset_research_outcome_reliability
Revises: 20260804_asset_research_run_integrity

Outcome rows are append-only score facts, while the prediction row is the
natural unit of collection: one legal observed snapshot can score several
heads.  These operational fields are explicitly excluded from immutable
decision content and let multiple worker processes safely claim a prediction
once at a time.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260805_asset_research_outcome_reliability"
down_revision = "20260804_asset_research_run_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("asset_signal_predictions") as batch:
        batch.add_column(sa.Column("outcome_lease_token", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("outcome_lease_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("outcome_last_attempt_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("outcome_last_error_code", sa.String(length=128), nullable=True))
        batch.create_check_constraint(
            "ck_asset_prediction_outcome_lease_pair",
            "(outcome_lease_token IS NULL AND outcome_lease_expires_at IS NULL) OR "
            "(outcome_lease_token IS NOT NULL AND outcome_lease_expires_at IS NOT NULL)",
        )
        batch.create_index(
            "ix_asset_prediction_outcome_lease",
            ["outcome_lease_expires_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("asset_signal_predictions") as batch:
        batch.drop_index("ix_asset_prediction_outcome_lease")
        batch.drop_constraint("ck_asset_prediction_outcome_lease_pair", type_="check")
        batch.drop_column("outcome_last_error_code")
        batch.drop_column("outcome_last_attempt_at")
        batch.drop_column("outcome_lease_expires_at")
        batch.drop_column("outcome_lease_token")
