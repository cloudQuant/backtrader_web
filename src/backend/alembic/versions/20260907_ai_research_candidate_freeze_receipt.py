"""Persist one loss-intolerant identity receipt per frozen discovery candidate.

Revision ID: 20260907_ai_research_candidate_freeze_receipt
Revises: 20260906_ai_research_workflow_version
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260907_ai_research_candidate_freeze_receipt"
down_revision = "20260906_ai_research_workflow_version"
branch_labels = None
depends_on = None

_TABLE = "ai_research_candidate_freeze_receipts"
_UPDATE_TRIGGER = "trg_ai_research_freeze_receipt_no_update"
_DELETE_TRIGGER = "trg_ai_research_freeze_receipt_no_delete"
_POSTGRES_FUNCTION = "deny_ai_research_freeze_receipt_mutation"
_MUTATION_ERROR = "CANDIDATE_FREEZE_RECEIPT_IMMUTABLE"
_HOLDOUT_TABLE = "ai_research_holdout_authorizations"
_HOLDOUT_OLD_UNIQUE = "uq_ai_research_holdout_authorization_binding"
_HOLDOUT_EPOCH_UNIQUE = "uq_ai_research_holdout_authorization_epoch"


def upgrade() -> None:
    """Create the append-only strict candidate-freeze identity authority."""

    duplicate_epoch = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT experiment_epoch_id FROM {_HOLDOUT_TABLE} "
                "GROUP BY experiment_epoch_id HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .scalar()
    )
    if duplicate_epoch is not None:
        raise RuntimeError("HOLDOUT_AUTHORIZATION_EPOCH_DUPLICATES")
    _upgrade_holdout_epoch_unique()

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "experiment_epoch_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("candidate_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "workflow_version",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'discovery-v1'"),
        ),
        sa.Column("generation_materialization_hash", sa.String(length=64), nullable=False),
        sa.Column("ledger_hash", sa.String(length=64), nullable=False),
        sa.Column("attempt_count_total", sa.Integer(), nullable=False),
        sa.Column("market_trial_count", sa.Integer(), nullable=False),
        sa.Column("search_budget_hash", sa.String(length=64), nullable=False),
        sa.Column("dataset_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("dataset_snapshot_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("dependency_hash", sa.String(length=64), nullable=False),
        sa.Column("hypothesis_hash", sa.String(length=64), nullable=False),
        sa.Column("environment_hash", sa.String(length=64), nullable=False),
        sa.Column("cost_model_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "checker_version",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'candidate-freeze-v1'"),
        ),
        sa.Column("frozen_by", sa.String(length=128), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "workflow_version = 'discovery-v1'",
            name="ck_ai_research_candidate_freeze_receipt_workflow",
        ),
        sa.CheckConstraint(
            "checker_version = 'candidate-freeze-v1'",
            name="ck_ai_research_candidate_freeze_receipt_checker",
        ),
        sa.CheckConstraint(
            "attempt_count_total > 0 AND market_trial_count > 0",
            name="ck_ai_research_candidate_freeze_receipt_counts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            name="uq_ai_research_candidate_freeze_receipt_candidate",
        ),
    )
    op.create_index(
        "ix_ai_research_candidate_freeze_receipt_owner_run",
        _TABLE,
        ["user_id", "run_id", "frozen_at"],
    )
    op.create_index(
        "ix_ai_research_candidate_freeze_receipt_epoch",
        _TABLE,
        ["experiment_epoch_id", "frozen_at"],
    )
    with op.batch_alter_table("ai_research_forward_observation_epochs") as batch:
        batch.add_column(sa.Column("freeze_receipt_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column("freeze_receipt_fingerprint", sa.String(length=64), nullable=True)
        )
        batch.create_foreign_key(
            "fk_ai_research_forward_epoch_freeze_receipt",
            _TABLE,
            ["freeze_receipt_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_ai_research_forward_epoch_freeze_receipt_pair",
            "(freeze_receipt_id IS NULL AND freeze_receipt_fingerprint IS NULL) OR "
            "(freeze_receipt_id IS NOT NULL AND freeze_receipt_fingerprint IS NOT NULL)",
        )
    _create_immutability_guards()


def downgrade() -> None:
    """Refuse to discard any strict freeze receipt; drop only an empty table."""

    retained = op.get_bind().execute(sa.text(f"SELECT 1 FROM {_TABLE} LIMIT 1")).scalar()
    if retained is not None:
        raise RuntimeError("CANDIDATE_FREEZE_RECEIPT_DOWNGRADE_BLOCKED")
    with op.batch_alter_table("ai_research_forward_observation_epochs") as batch:
        batch.drop_constraint(
            "ck_ai_research_forward_epoch_freeze_receipt_pair",
            type_="check",
        )
        batch.drop_constraint(
            "fk_ai_research_forward_epoch_freeze_receipt",
            type_="foreignkey",
        )
        batch.drop_column("freeze_receipt_fingerprint")
        batch.drop_column("freeze_receipt_id")
    _drop_immutability_guards()
    # DROP TABLE owns removal of its indexes.  MySQL may select the explicit
    # epoch index to support this table's foreign key and rejects an early
    # DROP INDEX even though the table itself is about to be removed.
    op.drop_table(_TABLE)
    _downgrade_holdout_epoch_unique()


def _upgrade_holdout_epoch_unique() -> None:
    """Install the stronger guard without dropping the old MySQL guard first."""

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(_HOLDOUT_TABLE) as batch:
            batch.drop_constraint(_HOLDOUT_OLD_UNIQUE, type_="unique")
            batch.create_unique_constraint(_HOLDOUT_EPOCH_UNIQUE, ["experiment_epoch_id"])
        return
    op.create_unique_constraint(
        _HOLDOUT_EPOCH_UNIQUE,
        _HOLDOUT_TABLE,
        ["experiment_epoch_id"],
    )
    op.drop_constraint(_HOLDOUT_OLD_UNIQUE, _HOLDOUT_TABLE, type_="unique")


def _downgrade_holdout_epoch_unique() -> None:
    """Restore the old guard in a non-transactional-DDL-safe order."""

    old_columns = [
        "experiment_epoch_id",
        "candidate_id",
        "dataset_snapshot_id",
        "policy_version",
    ]
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(_HOLDOUT_TABLE) as batch:
            batch.drop_constraint(_HOLDOUT_EPOCH_UNIQUE, type_="unique")
            batch.create_unique_constraint(_HOLDOUT_OLD_UNIQUE, old_columns)
        return
    op.create_unique_constraint(_HOLDOUT_OLD_UNIQUE, _HOLDOUT_TABLE, old_columns)
    op.drop_constraint(_HOLDOUT_EPOCH_UNIQUE, _HOLDOUT_TABLE, type_="unique")


def _create_immutability_guards() -> None:
    """Install dialect-native UPDATE/DELETE denial at the database boundary."""

    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_UPDATE_TRIGGER} BEFORE UPDATE ON {_TABLE} "
                f"BEGIN SELECT RAISE(ABORT, '{_MUTATION_ERROR}'); END"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_DELETE_TRIGGER} BEFORE DELETE ON {_TABLE} "
                f"BEGIN SELECT RAISE(ABORT, '{_MUTATION_ERROR}'); END"
            )
        )
        return
    if dialect == "postgresql":
        op.execute(
            sa.text(
                f"CREATE FUNCTION {_POSTGRES_FUNCTION}() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN "
                f"RAISE EXCEPTION '{_MUTATION_ERROR}'; RETURN OLD; END; $$"
            )
        )
        for trigger in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
            operation = "UPDATE" if trigger == _UPDATE_TRIGGER else "DELETE"
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {_TABLE} "
                    f"FOR EACH ROW EXECUTE FUNCTION {_POSTGRES_FUNCTION}()"
                )
            )
        return
    if dialect in {"mysql", "mariadb"}:
        for trigger in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
            operation = "UPDATE" if trigger == _UPDATE_TRIGGER else "DELETE"
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {_TABLE} "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    f"SET MESSAGE_TEXT = '{_MUTATION_ERROR}'"
                )
            )
        return
    raise RuntimeError(f"CANDIDATE_FREEZE_RECEIPT_DIALECT_UNSUPPORTED:{dialect}")


def _drop_immutability_guards() -> None:
    """Remove guards only after downgrade proved that no receipts exist."""

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for trigger in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON {_TABLE}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_POSTGRES_FUNCTION}()"))
        return
    for trigger in (_UPDATE_TRIGGER, _DELETE_TRIGGER):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
