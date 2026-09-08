"""Create durable server-owned sealed-holdout evaluation requests.

Revision ID: 20260907_ai_research_holdout_request
Revises: 20260907_ai_research_candidate_freeze_receipt
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260907_ai_research_holdout_request"
down_revision = "20260907_ai_research_candidate_freeze_receipt"
branch_labels = None
depends_on = None

_TABLE = "ai_research_holdout_evaluation_commands"
_AUDIT_TABLE = "ai_research_holdout_request_audits"
_AUDIT_UPDATE_TRIGGER = "trg_ai_research_holdout_request_audit_no_update"
_AUDIT_DELETE_TRIGGER = "trg_ai_research_holdout_request_audit_no_delete"
_AUDIT_POSTGRES_FUNCTION = "deny_ai_research_holdout_request_audit_mutation"
_AUDIT_MUTATION_ERROR = "HOLDOUT_REQUEST_AUDIT_IMMUTABLE"


def upgrade() -> None:
    """Add one token-free durable command per selected experiment epoch."""

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
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
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
            "expected_candidate_state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'FROZEN'"),
        ),
        sa.Column(
            "freeze_receipt_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_candidate_freeze_receipts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("freeze_receipt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "dataset_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dataset_policy_version", sa.String(length=128), nullable=False),
        sa.Column("sealed_dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("sealed_dataset_identity_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("evaluator_identity", sa.String(length=128), nullable=False),
        sa.Column("evaluator_version", sa.String(length=128), nullable=False),
        sa.Column("capability_profile_id", sa.String(length=128), nullable=False),
        sa.Column("capability_profile_version", sa.String(length=128), nullable=False),
        sa.Column("capability_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "authorization_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "evaluation_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        sa.Column(
            "stage",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'REQUEST_HOLDOUT'"),
        ),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', "
            "'TIMED_OUT', 'RECONCILING')",
            name="ck_ai_research_holdout_command_status",
        ),
        sa.CheckConstraint(
            "stage = 'REQUEST_HOLDOUT'",
            name="ck_ai_research_holdout_command_stage",
        ),
        sa.CheckConstraint(
            "expected_candidate_state = 'FROZEN'",
            name="ck_ai_research_holdout_command_candidate_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_ai_research_holdout_command_idempotency",
        ),
        sa.UniqueConstraint(
            "experiment_epoch_id",
            name="uq_ai_research_holdout_command_epoch",
        ),
        sa.UniqueConstraint(
            "freeze_receipt_id",
            name="uq_ai_research_holdout_command_freeze_receipt",
        ),
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_ai_research_holdout_command_authorization",
        ),
        sa.UniqueConstraint(
            "evaluation_id",
            name="uq_ai_research_holdout_command_evaluation",
        ),
    )
    op.create_index(
        "ix_ai_research_holdout_command_owner_status",
        _TABLE,
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_ai_research_holdout_evaluation_commands_trace_id",
        _TABLE,
        ["trace_id"],
    )
    op.create_table(
        _AUDIT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("expected_candidate_hash", sa.String(length=64), nullable=False),
        sa.Column("resolved_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=256), nullable=False),
        sa.Column(
            "command_id",
            sa.String(length=36),
            sa.ForeignKey(_TABLE + ".id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "purpose = 'HOLDOUT_EVALUATION_REQUEST'",
            name="ck_ai_research_holdout_request_audit_purpose",
        ),
        sa.CheckConstraint(
            "result IN ('ACCEPTED', 'REJECTED', 'UNKNOWN')",
            name="ck_ai_research_holdout_request_audit_result",
        ),
        sa.CheckConstraint(
            "(result = 'ACCEPTED' AND command_id IS NOT NULL AND "
            "resolved_snapshot_id IS NOT NULL) OR "
            "(result IN ('REJECTED', 'UNKNOWN') AND command_id IS NULL AND "
            "resolved_snapshot_id IS NULL)",
            name="ck_ai_research_holdout_request_audit_authority",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "command_id",
            name="uq_ai_research_holdout_request_audit_command",
        ),
    )
    op.create_index(
        "ix_ai_research_holdout_request_audit_actor_created",
        _AUDIT_TABLE,
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_research_holdout_request_audit_candidate_created",
        _AUDIT_TABLE,
        ["candidate_id", "created_at"],
    )
    _create_audit_immutability_guards()


def downgrade() -> None:
    """Refuse to discard queued work; remove only an empty command table."""

    retained_command = op.get_bind().execute(sa.text(f"SELECT 1 FROM {_TABLE} LIMIT 1")).scalar()
    retained_audit = (
        op.get_bind().execute(sa.text(f"SELECT 1 FROM {_AUDIT_TABLE} LIMIT 1")).scalar()
    )
    if retained_command is not None or retained_audit is not None:
        raise RuntimeError("HOLDOUT_REQUEST_DOWNGRADE_BLOCKED")
    _drop_audit_immutability_guards()
    op.drop_index(
        "ix_ai_research_holdout_request_audit_candidate_created",
        table_name=_AUDIT_TABLE,
    )
    op.drop_index(
        "ix_ai_research_holdout_request_audit_actor_created",
        table_name=_AUDIT_TABLE,
    )
    op.drop_table(_AUDIT_TABLE)
    op.drop_index("ix_ai_research_holdout_evaluation_commands_trace_id", table_name=_TABLE)
    op.drop_index("ix_ai_research_holdout_command_owner_status", table_name=_TABLE)
    op.drop_table(_TABLE)


def _create_audit_immutability_guards() -> None:
    """Install database-native UPDATE/DELETE denial for audit evidence."""

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
        for trigger in (_AUDIT_UPDATE_TRIGGER, _AUDIT_DELETE_TRIGGER):
            operation = "UPDATE" if trigger == _AUDIT_UPDATE_TRIGGER else "DELETE"
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {_AUDIT_TABLE} "
                    f"FOR EACH ROW EXECUTE FUNCTION {_AUDIT_POSTGRES_FUNCTION}()"
                )
            )
        return
    if dialect in {"mysql", "mariadb"}:
        for trigger in (_AUDIT_UPDATE_TRIGGER, _AUDIT_DELETE_TRIGGER):
            operation = "UPDATE" if trigger == _AUDIT_UPDATE_TRIGGER else "DELETE"
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {_AUDIT_TABLE} "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    f"SET MESSAGE_TEXT = '{_AUDIT_MUTATION_ERROR}'"
                )
            )
        return
    raise RuntimeError(f"HOLDOUT_REQUEST_AUDIT_DIALECT_UNSUPPORTED:{dialect}")


def _drop_audit_immutability_guards() -> None:
    """Remove mutation guards only after proving that no audit evidence remains."""

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for trigger in (_AUDIT_UPDATE_TRIGGER, _AUDIT_DELETE_TRIGGER):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON {_AUDIT_TABLE}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_AUDIT_POSTGRES_FUNCTION}()"))
        return
    for trigger in (_AUDIT_UPDATE_TRIGGER, _AUDIT_DELETE_TRIGGER):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
