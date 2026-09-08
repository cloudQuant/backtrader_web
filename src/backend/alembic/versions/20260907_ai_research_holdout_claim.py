"""Add fenced internal claims for durable sealed-holdout commands.

Revision ID: 20260907_ai_research_holdout_claim
Revises: 20260907_ai_research_holdout_request
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260907_ai_research_holdout_claim"
down_revision = "20260907_ai_research_holdout_request"
branch_labels = None
depends_on = None

_COMMAND_TABLE = "ai_research_holdout_evaluation_commands"
_EVALUATION_TABLE = "ai_research_evaluations"
_AUDIT_TABLE = "ai_research_holdout_access_audits"
_AUDIT_UPDATE_TRIGGER = "trg_ai_research_holdout_access_audit_no_update"
_AUDIT_DELETE_TRIGGER = "trg_ai_research_holdout_access_audit_no_delete"
_AUDIT_POSTGRES_FUNCTION = "deny_ai_research_holdout_access_audit_mutation"
_AUDIT_MUTATION_ERROR = "HOLDOUT_ACCESS_AUDIT_IMMUTABLE"


def upgrade() -> None:
    """Add claim fencing without backfilling authority onto queued commands."""

    with op.batch_alter_table(_COMMAND_TABLE) as batch:
        batch.drop_constraint("ck_ai_research_holdout_command_stage", type_="check")
        batch.add_column(sa.Column("lease_owner", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("lease_token_hash", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "lease_generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_stage",
            "stage IN ('REQUEST_HOLDOUT', 'HOLDOUT_PENDING')",
        )
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_binding_pair",
            "(authorization_id IS NULL AND evaluation_id IS NULL) OR "
            "(authorization_id IS NOT NULL AND evaluation_id IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_lease_group",
            "(lease_owner IS NULL AND lease_token_hash IS NULL AND "
            "lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token_hash IS NOT NULL AND "
            "lease_expires_at IS NOT NULL AND lease_heartbeat_at IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_state_bindings",
            "(status = 'QUEUED' AND stage = 'REQUEST_HOLDOUT' AND "
            "authorization_id IS NULL AND evaluation_id IS NULL AND lease_owner IS NULL AND "
            "lease_token_hash IS NULL AND lease_generation = 0 AND lease_expires_at IS NULL "
            "AND lease_heartbeat_at IS NULL AND attempt_count = 0 AND started_at IS NULL) OR "
            "(status = 'RUNNING' AND stage = 'HOLDOUT_PENDING' AND "
            "authorization_id IS NOT NULL AND evaluation_id IS NOT NULL AND "
            "lease_owner IS NOT NULL AND lease_token_hash IS NOT NULL AND "
            "lease_generation >= 1 AND lease_expires_at IS NOT NULL AND "
            "lease_heartbeat_at IS NOT NULL AND attempt_count = lease_generation AND "
            "started_at IS NOT NULL) OR "
            "(status = 'RECONCILING' AND stage = 'REQUEST_HOLDOUT' AND "
            "authorization_id IS NULL AND evaluation_id IS NULL AND lease_owner IS NULL AND "
            "lease_token_hash IS NULL AND lease_generation = 0 AND lease_expires_at IS NULL "
            "AND lease_heartbeat_at IS NULL AND attempt_count = 0 AND started_at IS NULL "
            "AND error_code IS NOT NULL) OR "
            "(status IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'RECONCILING') "
            "AND stage = 'HOLDOUT_PENDING' AND authorization_id IS NOT NULL AND "
            "evaluation_id IS NOT NULL AND lease_owner IS NULL AND lease_token_hash IS NULL "
            "AND lease_generation >= 1 AND lease_expires_at IS NULL AND "
            "lease_heartbeat_at IS NULL AND attempt_count = lease_generation AND "
            "started_at IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_attempt_count",
            "attempt_count >= 0",
        )
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_lease_generation",
            "lease_generation >= 0",
        )
    op.create_index(
        "ix_ai_research_holdout_command_claim",
        _COMMAND_TABLE,
        ["status", "stage", "lease_expires_at", "created_at"],
    )

    with op.batch_alter_table(_EVALUATION_TABLE) as batch:
        batch.create_unique_constraint(
            "uq_ai_research_evaluation_authorization",
            ["authorization_id"],
        )

    op.create_table(
        _AUDIT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_identity", sa.String(length=128), nullable=False),
        sa.Column("evaluator_version", sa.String(length=128), nullable=False),
        sa.Column("requested_command_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column(
            "command_id",
            sa.String(length=36),
            sa.ForeignKey(f"{_COMMAND_TABLE}.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "authorization_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "evaluation_id",
            sa.String(length=36),
            sa.ForeignKey(f"{_EVALUATION_TABLE}.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "experiment_epoch_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_experiment_epochs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_candidates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("lease_generation", sa.Integer(), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('CLAIM_STARTED', 'CLAIM_REJECTED', 'CLAIM_UNKNOWN', "
            "'LEASE_EXPIRED_RECONCILING')",
            name="ck_ai_research_holdout_access_audit_action",
        ),
        sa.CheckConstraint(
            "result IN ('ACCEPTED', 'REJECTED', 'UNKNOWN')",
            name="ck_ai_research_holdout_access_audit_result",
        ),
        sa.CheckConstraint(
            "(action IN ('CLAIM_STARTED', 'LEASE_EXPIRED_RECONCILING') AND "
            "result = 'ACCEPTED') OR (action = 'CLAIM_REJECTED' AND result = 'REJECTED') OR "
            "(action = 'CLAIM_UNKNOWN' AND result = 'UNKNOWN')",
            name="ck_ai_research_holdout_access_audit_outcome",
        ),
        sa.CheckConstraint(
            "(result = 'ACCEPTED' AND command_id IS NOT NULL AND "
            "authorization_id IS NOT NULL AND evaluation_id IS NOT NULL AND "
            "experiment_epoch_id IS NOT NULL AND candidate_id IS NOT NULL AND "
            "dataset_snapshot_id IS NOT NULL AND lease_generation IS NOT NULL) OR "
            "(result IN ('REJECTED', 'UNKNOWN') AND command_id IS NULL AND "
            "authorization_id IS NULL AND evaluation_id IS NULL AND "
            "experiment_epoch_id IS NULL AND candidate_id IS NULL AND "
            "dataset_snapshot_id IS NULL AND lease_generation IS NULL)",
            name="ck_ai_research_holdout_access_audit_authority",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action",
            "command_id",
            "lease_generation",
            name="uq_ai_research_holdout_access_audit_event",
        ),
    )
    op.create_index(
        "ix_ai_research_holdout_access_audit_actor_created",
        _AUDIT_TABLE,
        ["actor_identity", "created_at"],
    )
    op.create_index(
        "ix_ai_research_holdout_access_audit_requested_command",
        _AUDIT_TABLE,
        ["requested_command_id", "created_at"],
    )
    _create_audit_immutability_guards()


def downgrade() -> None:
    """Refuse to erase access history or an authority-bearing command."""

    retained_audit = (
        op.get_bind().execute(sa.text(f"SELECT 1 FROM {_AUDIT_TABLE} LIMIT 1")).scalar()
    )
    retained_claim = op.get_bind().execute(
        sa.text(
            f"SELECT 1 FROM {_COMMAND_TABLE} WHERE status <> 'QUEUED' "
            "OR authorization_id IS NOT NULL OR evaluation_id IS NOT NULL "
            "OR lease_owner IS NOT NULL OR lease_token_hash IS NOT NULL "
            "OR lease_generation <> 0 OR lease_expires_at IS NOT NULL "
            "OR lease_heartbeat_at IS NOT NULL OR attempt_count <> 0 OR started_at IS NOT NULL "
            "LIMIT 1"
        )
    ).scalar()
    if retained_audit is not None or retained_claim is not None:
        raise RuntimeError("HOLDOUT_CLAIM_DOWNGRADE_BLOCKED")

    _drop_audit_immutability_guards()
    op.drop_index(
        "ix_ai_research_holdout_access_audit_requested_command",
        table_name=_AUDIT_TABLE,
    )
    op.drop_index(
        "ix_ai_research_holdout_access_audit_actor_created",
        table_name=_AUDIT_TABLE,
    )
    op.drop_table(_AUDIT_TABLE)
    with op.batch_alter_table(_EVALUATION_TABLE) as batch:
        batch.drop_constraint("uq_ai_research_evaluation_authorization", type_="unique")
    op.drop_index("ix_ai_research_holdout_command_claim", table_name=_COMMAND_TABLE)
    with op.batch_alter_table(_COMMAND_TABLE) as batch:
        for constraint in (
            "ck_ai_research_holdout_command_binding_pair",
            "ck_ai_research_holdout_command_lease_group",
            "ck_ai_research_holdout_command_state_bindings",
            "ck_ai_research_holdout_command_attempt_count",
            "ck_ai_research_holdout_command_lease_generation",
            "ck_ai_research_holdout_command_stage",
        ):
            batch.drop_constraint(constraint, type_="check")
        for column in (
            "started_at",
            "attempt_count",
            "lease_heartbeat_at",
            "lease_expires_at",
            "lease_generation",
            "lease_token_hash",
            "lease_owner",
        ):
            batch.drop_column(column)
        batch.create_check_constraint(
            "ck_ai_research_holdout_command_stage",
            "stage = 'REQUEST_HOLDOUT'",
        )


def _create_audit_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_AUDIT_UPDATE_TRIGGER} BEFORE UPDATE ON {_AUDIT_TABLE} "
                f"BEGIN SELECT RAISE(ABORT, '{_AUDIT_MUTATION_ERROR}'); END"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_AUDIT_DELETE_TRIGGER} BEFORE DELETE ON {_AUDIT_TABLE} "
                f"BEGIN SELECT RAISE(ABORT, '{_AUDIT_MUTATION_ERROR}'); END"
            )
        )
        return
    if dialect == "postgresql":
        op.execute(
            sa.text(
                f"CREATE FUNCTION {_AUDIT_POSTGRES_FUNCTION}() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN "
                f"RAISE EXCEPTION '{_AUDIT_MUTATION_ERROR}'; RETURN OLD; END; $$"
            )
        )
        for trigger, operation in (
            (_AUDIT_UPDATE_TRIGGER, "UPDATE"),
            (_AUDIT_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {_AUDIT_TABLE} "
                    f"FOR EACH ROW EXECUTE FUNCTION {_AUDIT_POSTGRES_FUNCTION}()"
                )
            )
        return
    if dialect in {"mysql", "mariadb"}:
        for trigger, operation in (
            (_AUDIT_UPDATE_TRIGGER, "UPDATE"),
            (_AUDIT_DELETE_TRIGGER, "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {_AUDIT_TABLE} "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    f"SET MESSAGE_TEXT = '{_AUDIT_MUTATION_ERROR}'"
                )
            )
        return
    raise RuntimeError(f"HOLDOUT_ACCESS_AUDIT_DIALECT_UNSUPPORTED:{dialect}")


def _drop_audit_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for trigger in (_AUDIT_UPDATE_TRIGGER, _AUDIT_DELETE_TRIGGER):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON {_AUDIT_TABLE}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_AUDIT_POSTGRES_FUNCTION}()"))
        return
    for trigger in (_AUDIT_UPDATE_TRIGGER, _AUDIT_DELETE_TRIGGER):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
