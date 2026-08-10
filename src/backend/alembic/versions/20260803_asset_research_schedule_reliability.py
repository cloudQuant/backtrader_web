"""Add durable lease and retry state for asset-research shadow schedules.

Revision ID: 20260803_asset_research_schedule_reliability
Revises: 20260802_asset_research_foundation

The schedule row is the coordination record for an approved single-asset
shadow run.  A retry stores the failed run's frozen configuration rather than
re-reading a later edited schedule, while each retry receives a separate run
audit record.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260803_asset_research_schedule_reliability"
down_revision = "20260802_asset_research_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("asset_signal_runs") as batch:
        batch.add_column(sa.Column("retry_of_run_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "attempt_number",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch.create_foreign_key(
            "fk_asset_signal_runs_retry_of_run",
            "asset_signal_runs",
            ["retry_of_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("asset_signal_schedules") as batch:
        batch.add_column(sa.Column("lease_token", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_error_code", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("retry_of_run_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("retry_not_before_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("retry_scheduled_fire_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("retry_cutoff_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("retry_schedule_version", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("retry_cutoff_policy_version", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("retry_schedule_config_json", sa.JSON(none_as_null=True), nullable=True)
        )
        batch.add_column(
            sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )
        batch.create_foreign_key(
            "fk_asset_schedule_retry_of_run",
            "asset_signal_runs",
            ["retry_of_run_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_asset_schedule_lease_pair",
            "(lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_asset_schedule_retry_context",
            "(retry_of_run_id IS NULL AND retry_not_before_at IS NULL "
            "AND retry_scheduled_fire_at IS NULL AND retry_cutoff_at IS NULL "
            "AND retry_schedule_version IS NULL AND retry_cutoff_policy_version IS NULL "
            "AND retry_schedule_config_json IS NULL AND retry_attempt = 0) OR "
            "(retry_of_run_id IS NOT NULL AND retry_not_before_at IS NOT NULL "
            "AND retry_scheduled_fire_at IS NOT NULL AND retry_cutoff_at IS NOT NULL "
            "AND retry_schedule_version IS NOT NULL AND retry_cutoff_policy_version IS NOT NULL "
            "AND retry_schedule_config_json IS NOT NULL AND retry_attempt > 0)",
        )
        batch.create_index("ix_asset_schedule_retry_due", ["retry_not_before_at"])


def downgrade() -> None:
    with op.batch_alter_table("asset_signal_schedules") as batch:
        batch.drop_index("ix_asset_schedule_retry_due")
        batch.drop_constraint("ck_asset_schedule_retry_context", type_="check")
        batch.drop_constraint("ck_asset_schedule_lease_pair", type_="check")
        batch.drop_constraint("fk_asset_schedule_retry_of_run", type_="foreignkey")
        batch.drop_column("retry_attempt")
        batch.drop_column("retry_schedule_config_json")
        batch.drop_column("retry_cutoff_policy_version")
        batch.drop_column("retry_schedule_version")
        batch.drop_column("retry_cutoff_at")
        batch.drop_column("retry_scheduled_fire_at")
        batch.drop_column("retry_not_before_at")
        batch.drop_column("retry_of_run_id")
        batch.drop_column("last_error_code")
        batch.drop_column("last_attempt_at")
        batch.drop_column("lease_expires_at")
        batch.drop_column("lease_token")

    with op.batch_alter_table("asset_signal_runs") as batch:
        batch.drop_constraint("fk_asset_signal_runs_retry_of_run", type_="foreignkey")
        batch.drop_column("attempt_number")
        batch.drop_column("retry_of_run_id")
