"""Bind option prediction contexts to their owner and exact instrument.

Revision ID: 20260810_asset_research_option_context_binding
Revises: 20260809_asset_research_maturity_reason_contract

The former single-column snapshot foreign key only proved that a context
snapshot existed.  A direct database write could still attach another user's
or another contract's LONG snapshot to an option prediction, or reuse a
snapshot outside its availability window.  This revision adds compact
composite binding and timing keys, which use the already-frozen instrument ID
rather than adding a trigger that would need privileged binary-log access on
MySQL 9.4.0.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision = "20260810_asset_research_option_context_binding"
down_revision = "20260809_asset_research_maturity_reason_contract"
branch_labels = None
depends_on = None

_CONTEXT_TABLE = "asset_position_context_snapshots"
_PREDICTION_TABLE = "asset_signal_predictions"
_PARENT_UNIQUE = "uq_asset_position_context_prediction_binding"
_CHILD_FOREIGN_KEY = "fk_asset_prediction_position_context_binding"
_WINDOW_PARENT_UNIQUE = "uq_asset_position_context_prediction_window"
_WINDOW_CHILD_FOREIGN_KEY = "fk_asset_prediction_position_context_window"
_OPTION_LONG_WINDOW_CHECK = "ck_asset_option_long_context_window"
_BINDING_COLUMNS = [
    "id",
    "owner_scope",
    "user_id",
    "instrument_id",
    "position_context",
]
_CHILD_BINDING_COLUMNS = ["position_context_snapshot_id", *_BINDING_COLUMNS[1:]]
_WINDOW_COLUMNS = ["id", "as_of_at", "available_at", "expires_at"]
_CHILD_WINDOW_COLUMNS = [
    "position_context_snapshot_id",
    "position_context_snapshot_as_of_at",
    "position_context_snapshot_available_at",
    "position_context_snapshot_expires_at",
]


def _assert_existing_prediction_bindings(bind: Any) -> None:
    """Refuse migration rather than silently rewriting historical research facts."""
    statement = sa.text(
        """
        SELECT COUNT(*)
        FROM asset_signal_predictions AS prediction
        WHERE prediction.position_context_snapshot_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM asset_position_context_snapshots AS context_snapshot
              WHERE context_snapshot.id = prediction.position_context_snapshot_id
                AND context_snapshot.owner_scope = prediction.owner_scope
                AND (
                    context_snapshot.user_id = prediction.user_id
                    OR (
                        context_snapshot.user_id IS NULL
                        AND prediction.user_id IS NULL
                    )
                )
                AND context_snapshot.instrument_id = prediction.instrument_id
                AND context_snapshot.position_context = prediction.position_context
          )
        """
    )
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: ASSET_POSITION_CONTEXT_BINDING_BACKFILL_REQUIRED; "
            "the following count must be 0 before this DDL is executed."
        )
        op.execute(statement)
        return
    invalid_count = bind.execute(statement).scalar_one()
    if int(invalid_count) != 0:
        raise RuntimeError(
            "ASSET_POSITION_CONTEXT_BINDING_BACKFILL_REQUIRED: cannot add the "
            "composite binding while existing predictions point at a context "
            "owned by another principal, instrument, or position state"
        )


def _copy_context_windows(bind: Any) -> None:
    """Copy immutable context timing into predictions before enabling the FK."""
    dialect = bind.dialect.name
    if dialect == "mysql":
        op.execute(
            """
            UPDATE asset_signal_predictions AS prediction
            INNER JOIN asset_position_context_snapshots AS context_snapshot
              ON context_snapshot.id = prediction.position_context_snapshot_id
            SET prediction.position_context_snapshot_as_of_at = context_snapshot.as_of_at,
                prediction.position_context_snapshot_available_at = context_snapshot.available_at,
                prediction.position_context_snapshot_expires_at = context_snapshot.expires_at
            WHERE prediction.position_context_snapshot_id IS NOT NULL
            """
        )
        return
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE asset_signal_predictions AS prediction
            SET position_context_snapshot_as_of_at = context_snapshot.as_of_at,
                position_context_snapshot_available_at = context_snapshot.available_at,
                position_context_snapshot_expires_at = context_snapshot.expires_at
            FROM asset_position_context_snapshots AS context_snapshot
            WHERE context_snapshot.id = prediction.position_context_snapshot_id
            """
        )
        return
    if dialect == "sqlite":
        op.execute(
            """
            UPDATE asset_signal_predictions
            SET position_context_snapshot_as_of_at = (
                    SELECT context_snapshot.as_of_at
                    FROM asset_position_context_snapshots AS context_snapshot
                    WHERE context_snapshot.id = asset_signal_predictions.position_context_snapshot_id
                ),
                position_context_snapshot_available_at = (
                    SELECT context_snapshot.available_at
                    FROM asset_position_context_snapshots AS context_snapshot
                    WHERE context_snapshot.id = asset_signal_predictions.position_context_snapshot_id
                ),
                position_context_snapshot_expires_at = (
                    SELECT context_snapshot.expires_at
                    FROM asset_position_context_snapshots AS context_snapshot
                    WHERE context_snapshot.id = asset_signal_predictions.position_context_snapshot_id
                )
            WHERE position_context_snapshot_id IS NOT NULL
            """
        )
        return
    raise RuntimeError(f"asset-research context window migration does not support dialect: {dialect}")


def _assert_existing_option_long_windows(bind: Any) -> None:
    """Do not manufacture a historical close authorization during upgrade."""
    statement = sa.text(
        """
        SELECT COUNT(*)
        FROM asset_signal_predictions
        WHERE asset_type = 'option'
          AND position_context = 'LONG'
          AND (
              position_context_snapshot_id IS NULL
              OR position_context_snapshot_as_of_at IS NULL
              OR position_context_snapshot_available_at IS NULL
              OR position_context_snapshot_expires_at IS NULL
              OR position_context_snapshot_as_of_at > as_of_at
              OR position_context_snapshot_available_at > as_of_at
              OR as_of_at >= position_context_snapshot_expires_at
          )
        """
    )
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: ASSET_OPTION_LONG_CONTEXT_WINDOW_BACKFILL_REQUIRED; "
            "the following count must be 0 before this DDL is executed."
        )
        op.execute(statement)
        return
    invalid_count = bind.execute(statement).scalar_one()
    if int(invalid_count) != 0:
        raise RuntimeError(
            "ASSET_OPTION_LONG_CONTEXT_WINDOW_BACKFILL_REQUIRED: cannot enforce the "
            "option close window while existing predictions use an unavailable or "
            "expired position context"
        )


def upgrade() -> None:
    bind = op.get_bind()
    _assert_existing_prediction_bindings(bind)
    with op.batch_alter_table(_PREDICTION_TABLE) as batch:
        batch.add_column(
            sa.Column("position_context_snapshot_as_of_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "position_context_snapshot_available_at", sa.DateTime(timezone=True), nullable=True
            )
        )
        batch.add_column(
            sa.Column(
                "position_context_snapshot_expires_at", sa.DateTime(timezone=True), nullable=True
            )
        )
    _copy_context_windows(bind)
    _assert_existing_option_long_windows(bind)
    with op.batch_alter_table(_CONTEXT_TABLE) as batch:
        batch.create_unique_constraint(_PARENT_UNIQUE, _BINDING_COLUMNS)
        batch.create_unique_constraint(_WINDOW_PARENT_UNIQUE, _WINDOW_COLUMNS)
    with op.batch_alter_table(_PREDICTION_TABLE) as batch:
        batch.create_foreign_key(
            _CHILD_FOREIGN_KEY,
            _CONTEXT_TABLE,
            _CHILD_BINDING_COLUMNS,
            _BINDING_COLUMNS,
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            _WINDOW_CHILD_FOREIGN_KEY,
            _CONTEXT_TABLE,
            _CHILD_WINDOW_COLUMNS,
            _WINDOW_COLUMNS,
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            _OPTION_LONG_WINDOW_CHECK,
            "asset_type != 'option' OR position_context != 'LONG' OR "
            "(position_context_snapshot_as_of_at IS NOT NULL "
            "AND position_context_snapshot_available_at IS NOT NULL "
            "AND position_context_snapshot_expires_at IS NOT NULL "
            "AND position_context_snapshot_as_of_at <= as_of_at "
            "AND position_context_snapshot_available_at <= as_of_at "
            "AND as_of_at < position_context_snapshot_expires_at)",
        )


def downgrade() -> None:
    with op.batch_alter_table(_PREDICTION_TABLE) as batch:
        batch.drop_constraint(_OPTION_LONG_WINDOW_CHECK, type_="check")
        batch.drop_constraint(_WINDOW_CHILD_FOREIGN_KEY, type_="foreignkey")
        batch.drop_constraint(_CHILD_FOREIGN_KEY, type_="foreignkey")
        batch.drop_column("position_context_snapshot_expires_at")
        batch.drop_column("position_context_snapshot_available_at")
        batch.drop_column("position_context_snapshot_as_of_at")
    with op.batch_alter_table(_CONTEXT_TABLE) as batch:
        batch.drop_constraint(_WINDOW_PARENT_UNIQUE, type_="unique")
        batch.drop_constraint(_PARENT_UNIQUE, type_="unique")
