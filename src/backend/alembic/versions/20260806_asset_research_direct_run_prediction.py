"""Use a row-local run-to-prediction invariant that is safe on MySQL 9.4.

Revision ID: 20260806_asset_research_direct_run_prediction
Revises: 20260805_asset_research_outcome_reliability

The original association table required cross-table triggers to prove that a
successful run had exactly one prediction.  MySQL can enforce the same
cardinality without a trigger by storing the optional prediction and its audit
role directly on the run row: a CHECK requires both for ``SUCCEEDED`` and
requires both to be NULL for every other state.  The nullable foreign key
keeps the immutable prediction alive, while several successful runs may still
reuse one prediction.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260806_asset_research_direct_run_prediction"
down_revision = "20260805_asset_research_outcome_reliability"
branch_labels = None
depends_on = None

_LEGACY_LINK_TABLE = "asset_signal_run_predictions"
_RUN_TABLE = "asset_signal_runs"
_PREDICTION_TABLE = "asset_signal_predictions"
_TERMINAL_CONSTRAINT = "ck_asset_run_prediction_terminal"
_PREDICTION_FOREIGN_KEY = "fk_asset_signal_runs_prediction"
_PREDICTION_INDEX = "ix_asset_run_prediction_created"


def _table_exists(bind: Any, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _assert_legacy_links_are_terminal(bind: Any) -> None:
    """Refuse lossy conversion if an old database already violates its contract."""
    if not _table_exists(bind, _LEGACY_LINK_TABLE):
        return
    invalid_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM asset_signal_runs AS run_record
            LEFT JOIN asset_signal_run_predictions AS link_record
              ON link_record.run_id = run_record.id
            WHERE (run_record.status = 'SUCCEEDED' AND link_record.run_id IS NULL)
               OR (run_record.status <> 'SUCCEEDED' AND link_record.run_id IS NOT NULL)
            """
        )
    ).scalar_one()
    if int(invalid_count) != 0:
        raise RuntimeError(
            "ASSET_RUN_PREDICTION_LEGACY_INTEGRITY_ERROR: "
            "cannot convert runs whose terminal state and legacy prediction link disagree"
        )


def _backfill_direct_links(bind: Any) -> None:
    """Copy only pre-validated immutable audit facts before removing the old table."""
    if not _table_exists(bind, _LEGACY_LINK_TABLE):
        return
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE asset_signal_runs AS run_record
            SET prediction_id = link_record.prediction_id,
                prediction_link_role = link_record.link_role
            FROM asset_signal_run_predictions AS link_record
            WHERE link_record.run_id = run_record.id
            """
        )
        return
    if dialect == "mysql":
        op.execute(
            """
            UPDATE asset_signal_runs AS run_record
            INNER JOIN asset_signal_run_predictions AS link_record
              ON link_record.run_id = run_record.id
            SET run_record.prediction_id = link_record.prediction_id,
                run_record.prediction_link_role = link_record.link_role
            """
        )
        return
    if dialect == "sqlite":
        op.execute(
            """
            UPDATE asset_signal_runs
            SET prediction_id = (
                    SELECT link_record.prediction_id
                    FROM asset_signal_run_predictions AS link_record
                    WHERE link_record.run_id = asset_signal_runs.id
                ),
                prediction_link_role = (
                    SELECT link_record.link_role
                    FROM asset_signal_run_predictions AS link_record
                    WHERE link_record.run_id = asset_signal_runs.id
                )
            WHERE EXISTS (
                SELECT 1
                FROM asset_signal_run_predictions AS link_record
                WHERE link_record.run_id = asset_signal_runs.id
            )
            """
        )
        return
    raise RuntimeError(f"asset-research direct run relation does not support dialect: {dialect}")


def _drop_legacy_triggers(bind: Any) -> None:
    """Remove triggers only from databases upgraded through the old local chain."""
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_asset_run_terminal_cardinality ON asset_signal_runs")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_asset_succeeded_run_keeps_prediction "
            "ON asset_signal_run_predictions"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_asset_run_prediction_requires_running "
            "ON asset_signal_run_predictions"
        )
        return
    if dialect in {"mysql", "sqlite"}:
        op.execute("DROP TRIGGER IF EXISTS trg_asset_run_terminal_cardinality")
        op.execute("DROP TRIGGER IF EXISTS trg_asset_succeeded_run_keeps_prediction")
        op.execute("DROP TRIGGER IF EXISTS trg_asset_run_prediction_requires_running")
        return
    raise RuntimeError(f"asset-research direct run relation does not support dialect: {dialect}")


def upgrade() -> None:
    bind = op.get_bind()
    _assert_legacy_links_are_terminal(bind)

    with op.batch_alter_table(_RUN_TABLE) as batch:
        batch.add_column(sa.Column("prediction_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("prediction_link_role", sa.String(length=16), nullable=True))

    _backfill_direct_links(bind)

    with op.batch_alter_table(_RUN_TABLE) as batch:
        batch.create_foreign_key(
            _PREDICTION_FOREIGN_KEY,
            _PREDICTION_TABLE,
            ["prediction_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            _TERMINAL_CONSTRAINT,
            "(status = 'SUCCEEDED' AND prediction_id IS NOT NULL "
            "AND prediction_link_role IN ('CREATED', 'REUSED')) OR "
            "(status IN ('PENDING', 'RUNNING', 'FAILED', 'CANCELLED') "
            "AND prediction_id IS NULL AND prediction_link_role IS NULL)",
        )
        batch.create_index(_PREDICTION_INDEX, ["prediction_id", "created_at"])

    _drop_legacy_triggers(bind)
    if _table_exists(bind, _LEGACY_LINK_TABLE):
        op.drop_table(_LEGACY_LINK_TABLE)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _LEGACY_LINK_TABLE):
        op.create_table(
            _LEGACY_LINK_TABLE,
            sa.Column("run_id", sa.String(length=36), nullable=False),
            sa.Column("prediction_id", sa.String(length=36), nullable=False),
            sa.Column("link_role", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "retention_class", sa.String(length=32), nullable=False, server_default="research-v1"
            ),
            sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("tombstoned_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["run_id"], ["asset_signal_runs.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["prediction_id"], ["asset_signal_predictions.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("run_id"),
            sa.CheckConstraint(
                "link_role IN ('CREATED', 'REUSED')", name="ck_asset_run_prediction_role"
            ),
        )
        op.create_index(
            "ix_asset_run_prediction_prediction_created",
            _LEGACY_LINK_TABLE,
            ["prediction_id", "created_at"],
        )

    op.execute(
        """
        INSERT INTO asset_signal_run_predictions (
            run_id, prediction_id, link_role, created_at,
            retention_class, retention_expires_at, legal_hold, tombstoned_at
        )
        SELECT id, prediction_id, prediction_link_role, created_at,
               retention_class, retention_expires_at, legal_hold, tombstoned_at
        FROM asset_signal_runs
        WHERE prediction_id IS NOT NULL
        """
    )

    with op.batch_alter_table(_RUN_TABLE) as batch:
        batch.drop_constraint(_PREDICTION_FOREIGN_KEY, type_="foreignkey")
        batch.drop_index(_PREDICTION_INDEX)
        batch.drop_constraint(_TERMINAL_CONSTRAINT, type_="check")
        batch.drop_column("prediction_link_role")
        batch.drop_column("prediction_id")
