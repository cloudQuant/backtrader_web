"""Bind leased holdout evidence to immutable evaluation authority.

Revision ID: 20260907_ai_research_holdout_finalize
Revises: 20260907_ai_research_holdout_claim
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "20260907_ai_research_holdout_finalize"
down_revision = "20260907_ai_research_holdout_claim"
branch_labels = None
depends_on = None

_ACCESS_AUDIT_TABLE = "ai_research_holdout_access_audits"
_ACCESS_AUDIT_UPDATE_TRIGGER = "trg_ai_research_holdout_access_audit_no_update"
_ACCESS_AUDIT_DELETE_TRIGGER = "trg_ai_research_holdout_access_audit_no_delete"
_ACCESS_AUDIT_POSTGRES_FUNCTION = "deny_ai_research_holdout_access_audit_mutation"
_ACCESS_AUDIT_MUTATION_ERROR = "HOLDOUT_ACCESS_AUDIT_IMMUTABLE"

_BINDING_TABLE = "ai_research_holdout_artifact_bindings"
_BINDING_UPDATE_TRIGGER = "trg_ai_research_holdout_artifact_binding_no_update"
_BINDING_DELETE_TRIGGER = "trg_ai_research_holdout_artifact_binding_no_delete"
_BINDING_POSTGRES_FUNCTION = "deny_ai_research_holdout_artifact_binding_mutation"
_BINDING_MUTATION_ERROR = "HOLDOUT_ARTIFACT_BINDING_IMMUTABLE"

_GATE_TABLE = "ai_research_gate_decisions"
_GATE_UNIQUE = "uq_ai_research_gate_decision_evaluation_input_gate"
_GATE_UPDATE_TRIGGER = "trg_ai_research_gate_decision_no_update"
_GATE_DELETE_TRIGGER = "trg_ai_research_gate_decision_no_delete"
_GATE_POSTGRES_FUNCTION = "deny_ai_research_holdout_gate_decision_mutation"
_GATE_MUTATION_ERROR = "HOLDOUT_GATE_DECISION_IMMUTABLE"
_GATE_UNIQUE_COLUMNS = (
    "evaluation_id",
    "policy_version",
    "input_evidence_hash",
    "gate_code",
)

_ACCESS_ACTION_CHECK = "ck_ai_research_holdout_access_audit_action"
_ACCESS_OUTCOME_CHECK = "ck_ai_research_holdout_access_audit_outcome"
_BINDING_INDEXES = {
    "ix_ai_research_holdout_artifact_binding_owner_run": (
        "user_id",
        "run_id",
        "created_at",
    ),
    "ix_ai_research_holdout_artifact_binding_epoch_candidate": (
        "experiment_epoch_id",
        "candidate_id",
        "created_at",
    ),
}
_BINDING_COLUMNS = {
    "id",
    "user_id",
    "run_id",
    "command_id",
    "authorization_id",
    "evaluation_id",
    "experiment_epoch_id",
    "candidate_id",
    "dataset_snapshot_id",
    "artifact_id",
    "claim_access_audit_id",
    "request_hash",
    "lease_owner",
    "lease_generation",
    "lease_expires_at",
    "binding_schema_version",
    "authority_binding_hash",
    "created_at",
}
_BINDING_UNIQUES = {
    "uq_ai_research_holdout_artifact_binding_command",
    "uq_ai_research_holdout_artifact_binding_authorization",
    "uq_ai_research_holdout_artifact_binding_evaluation",
    "uq_ai_research_holdout_artifact_binding_artifact",
    "uq_ai_research_holdout_artifact_binding_claim_audit",
    "uq_ai_research_holdout_artifact_binding_authority_hash",
}

_NEW_ACTIONS = (
    "CHECKPOINT_RECORDED",
    "CHECKPOINT_REJECTED",
    "CHECKPOINT_UNKNOWN",
    "FINALIZE_COMPLETED",
    "FINALIZE_REJECTED",
    "FINALIZE_UNKNOWN",
    "RECONCILE_COMPLETED",
    "RECONCILE_REJECTED",
)

_LEGACY_ACTION_CHECK = (
    "action IN ('CLAIM_STARTED', 'CLAIM_REJECTED', 'CLAIM_UNKNOWN', "
    "'LEASE_EXPIRED_RECONCILING')"
)
_EXPANDED_ACTION_CHECK = (
    "action IN ('CLAIM_STARTED', 'CLAIM_REJECTED', 'CLAIM_UNKNOWN', "
    "'LEASE_EXPIRED_RECONCILING', 'CHECKPOINT_RECORDED', "
    "'CHECKPOINT_REJECTED', 'CHECKPOINT_UNKNOWN', 'FINALIZE_COMPLETED', "
    "'FINALIZE_REJECTED', 'FINALIZE_UNKNOWN', 'RECONCILE_COMPLETED', "
    "'RECONCILE_REJECTED')"
)
_LEGACY_OUTCOME_CHECK = (
    "(action IN ('CLAIM_STARTED', 'LEASE_EXPIRED_RECONCILING') AND "
    "result = 'ACCEPTED') OR (action = 'CLAIM_REJECTED' AND "
    "result = 'REJECTED') OR (action = 'CLAIM_UNKNOWN' AND result = 'UNKNOWN')"
)
_EXPANDED_OUTCOME_CHECK = (
    "(action IN ('CLAIM_STARTED', 'LEASE_EXPIRED_RECONCILING', "
    "'CHECKPOINT_RECORDED', 'FINALIZE_COMPLETED', 'RECONCILE_COMPLETED') AND "
    "result = 'ACCEPTED') OR (action IN ('CLAIM_REJECTED', "
    "'CHECKPOINT_REJECTED', 'FINALIZE_REJECTED', 'RECONCILE_REJECTED') AND "
    "result = 'REJECTED') OR (action IN ('CLAIM_UNKNOWN', "
    "'CHECKPOINT_UNKNOWN', 'FINALIZE_UNKNOWN') AND result = 'UNKNOWN')"
)


def upgrade() -> None:
    """Add immutable checkpoint authority and extend access-audit outcomes."""

    bind = op.get_bind()
    _assert_no_duplicate_gate_decisions(bind)
    mysql_family = bind.dialect.name in {"mysql", "mariadb"}

    # PostgreSQL/SQLite can roll the revision back transactionally.  MySQL-family
    # DDL auto-commits, so install the gate constraint last and make every prior
    # schema step resumable before it becomes the revision's completion marker.
    if not mysql_family:
        _create_gate_unique_constraint(bind)
        _create_gate_immutability_guards()

    _replace_access_audit_checks(bind, expanded=True)
    _create_binding_schema(bind)

    if mysql_family:
        _create_gate_unique_constraint(bind)
        _create_gate_immutability_guards()


def _create_binding_table() -> None:
    """Create the immutable one-to-one evidence binding table."""

    op.create_table(
        _BINDING_TABLE,
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
            "command_id",
            sa.String(length=36),
            sa.ForeignKey(
                "ai_research_holdout_evaluation_commands.id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "authorization_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_holdout_authorizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"),
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
        sa.Column(
            "dataset_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_dataset_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "artifact_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_artifacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "claim_access_audit_id",
            sa.String(length=36),
            sa.ForeignKey(_ACCESS_AUDIT_TABLE + ".id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=False),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "binding_schema_version",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'holdout-artifact-binding-v1'"),
        ),
        sa.Column("authority_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lease_generation > 0",
            name="ck_ai_research_holdout_artifact_binding_generation",
        ),
        sa.CheckConstraint(
            "binding_schema_version = 'holdout-artifact-binding-v1'",
            name="ck_ai_research_holdout_artifact_binding_schema",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "command_id",
            name="uq_ai_research_holdout_artifact_binding_command",
        ),
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_ai_research_holdout_artifact_binding_authorization",
        ),
        sa.UniqueConstraint(
            "evaluation_id",
            name="uq_ai_research_holdout_artifact_binding_evaluation",
        ),
        sa.UniqueConstraint(
            "artifact_id",
            name="uq_ai_research_holdout_artifact_binding_artifact",
        ),
        sa.UniqueConstraint(
            "claim_access_audit_id",
            name="uq_ai_research_holdout_artifact_binding_claim_audit",
        ),
        sa.UniqueConstraint(
            "authority_binding_hash",
            name="uq_ai_research_holdout_artifact_binding_authority_hash",
        ),
    )


def downgrade() -> None:
    """Refuse to erase bindings or access events introduced by this revision."""

    bind = op.get_bind()
    _assert_finalize_downgrade_empty(bind)

    _drop_binding_immutability_guards()
    op.drop_index(
        "ix_ai_research_holdout_artifact_binding_epoch_candidate",
        table_name=_BINDING_TABLE,
    )
    op.drop_index(
        "ix_ai_research_holdout_artifact_binding_owner_run",
        table_name=_BINDING_TABLE,
    )
    op.drop_table(_BINDING_TABLE)

    _replace_access_audit_checks(bind, expanded=False)

    _drop_gate_immutability_guards()
    with op.batch_alter_table(_GATE_TABLE) as batch:
        batch.drop_constraint(_GATE_UNIQUE, type_="unique")


def _assert_no_duplicate_gate_decisions(bind: Any) -> None:
    statement = sa.text(
        f"SELECT evaluation_id FROM {_GATE_TABLE} WHERE evaluation_id IS NOT NULL "
        "GROUP BY evaluation_id, policy_version, input_evidence_hash, gate_code "
        "HAVING COUNT(*) > 1 LIMIT 1"
    )
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: HOLDOUT_GATE_DECISION_DUPLICATES; abort before "
            "applying this revision if the following query returns any row."
        )
        op.execute(statement)
        return
    if bind.execute(statement).scalar() is not None:
        raise RuntimeError("HOLDOUT_GATE_DECISION_DUPLICATES")


def _assert_finalize_downgrade_empty(bind: Any) -> None:
    action_values = ", ".join(f"'{action}'" for action in _NEW_ACTIONS)
    statements = (
        sa.text(f"SELECT 1 FROM {_BINDING_TABLE} LIMIT 1"),
        sa.text(
            f"SELECT 1 FROM {_ACCESS_AUDIT_TABLE} "
            f"WHERE action IN ({action_values}) LIMIT 1"
        ),
        sa.text(f"SELECT 1 FROM {_GATE_TABLE} LIMIT 1"),
    )
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: HOLDOUT_FINALIZE_DOWNGRADE_BLOCKED; abort before "
            "applying this downgrade if any of the following queries returns a row."
        )
        for statement in statements:
            op.execute(statement)
        return
    if any(bind.execute(statement).scalar() is not None for statement in statements):
        raise RuntimeError("HOLDOUT_FINALIZE_DOWNGRADE_BLOCKED")


def _create_gate_unique_constraint(bind: Any) -> None:
    """Create the final gate uniqueness marker, resuming MySQL auto-committed DDL."""

    if _is_online_mysql_family(bind):
        observed = {
            str(item.get("name")): tuple(item.get("column_names") or ())
            for item in sa.inspect(bind).get_unique_constraints(_GATE_TABLE)
            if item.get("name")
        }
        if _GATE_UNIQUE in observed:
            if observed[_GATE_UNIQUE] != _GATE_UNIQUE_COLUMNS:
                raise RuntimeError("HOLDOUT_GATE_DECISION_UNIQUE_CONFLICT")
            return
    with op.batch_alter_table(_GATE_TABLE) as batch:
        batch.create_unique_constraint(_GATE_UNIQUE, list(_GATE_UNIQUE_COLUMNS))


def _replace_access_audit_checks(bind: Any, *, expanded: bool) -> None:
    """Replace action checks without dropping MySQL/PostgreSQL audit guards."""

    desired_action = _EXPANDED_ACTION_CHECK if expanded else _LEGACY_ACTION_CHECK
    desired_outcome = _EXPANDED_OUTCOME_CHECK if expanded else _LEGACY_OUTCOME_CHECK
    sqlite = bind.dialect.name == "sqlite"
    observed_names = {_ACCESS_ACTION_CHECK, _ACCESS_OUTCOME_CHECK}

    if _is_online_mysql_family(bind):
        observed = {
            str(item.get("name")): str(item.get("sqltext") or "")
            for item in sa.inspect(bind).get_check_constraints(_ACCESS_AUDIT_TABLE)
            if item.get("name")
        }
        marker = "CHECKPOINT_RECORDED"
        action_matches = marker in observed.get(_ACCESS_ACTION_CHECK, "")
        outcome_matches = marker in observed.get(_ACCESS_OUTCOME_CHECK, "")
        if not expanded:
            action_matches = bool(observed.get(_ACCESS_ACTION_CHECK)) and not action_matches
            outcome_matches = bool(observed.get(_ACCESS_OUTCOME_CHECK)) and not outcome_matches
        if action_matches and outcome_matches:
            return
        observed_names = set(observed)

    # SQLite batch-copy drops table triggers.  Other supported databases alter
    # CHECK constraints in place, so retaining the guards closes the mutation gap.
    if sqlite:
        _drop_access_audit_immutability_guards()
    with op.batch_alter_table(_ACCESS_AUDIT_TABLE) as batch:
        if _ACCESS_OUTCOME_CHECK in observed_names:
            batch.drop_constraint(_ACCESS_OUTCOME_CHECK, type_="check")
        if _ACCESS_ACTION_CHECK in observed_names:
            batch.drop_constraint(_ACCESS_ACTION_CHECK, type_="check")
        batch.create_check_constraint(_ACCESS_ACTION_CHECK, desired_action)
        batch.create_check_constraint(_ACCESS_OUTCOME_CHECK, desired_outcome)
    if sqlite:
        _create_access_audit_immutability_guards()


def _create_binding_schema(bind: Any) -> None:
    """Create or resume the MySQL-family binding table, indexes, and guards."""

    table_exists = False
    if _is_online_mysql_family(bind):
        inspector = sa.inspect(bind)
        table_exists = inspector.has_table(_BINDING_TABLE)
        if table_exists:
            observed_columns = {
                str(item["name"]) for item in inspector.get_columns(_BINDING_TABLE)
            }
            observed_uniques = {
                str(item["name"])
                for item in inspector.get_unique_constraints(_BINDING_TABLE)
                if item.get("name")
            }
            if observed_columns != _BINDING_COLUMNS or not _BINDING_UNIQUES <= observed_uniques:
                raise RuntimeError("HOLDOUT_ARTIFACT_BINDING_SCHEMA_CONFLICT")
    if not table_exists:
        _create_binding_table()

    observed_indexes: dict[str, tuple[str, ...]] = {}
    if _is_online_mysql_family(bind):
        observed_indexes = {
            str(item["name"]): tuple(item.get("column_names") or ())
            for item in sa.inspect(bind).get_indexes(_BINDING_TABLE)
            if item.get("name")
        }
    for index_name, columns in _BINDING_INDEXES.items():
        if index_name in observed_indexes:
            if observed_indexes[index_name] != columns:
                raise RuntimeError("HOLDOUT_ARTIFACT_BINDING_INDEX_CONFLICT")
            continue
        op.create_index(index_name, _BINDING_TABLE, list(columns))
    _create_binding_immutability_guards()


def _is_online_mysql_family(bind: Any) -> bool:
    return bind.dialect.name in {"mysql", "mariadb"} and not context.is_offline_mode()


def _create_access_audit_immutability_guards() -> None:
    _create_immutability_guards(
        table=_ACCESS_AUDIT_TABLE,
        update_trigger=_ACCESS_AUDIT_UPDATE_TRIGGER,
        delete_trigger=_ACCESS_AUDIT_DELETE_TRIGGER,
        postgres_function=_ACCESS_AUDIT_POSTGRES_FUNCTION,
        mutation_error=_ACCESS_AUDIT_MUTATION_ERROR,
        unsupported_error="HOLDOUT_ACCESS_AUDIT_DIALECT_UNSUPPORTED",
    )


def _drop_access_audit_immutability_guards() -> None:
    _drop_immutability_guards(
        table=_ACCESS_AUDIT_TABLE,
        update_trigger=_ACCESS_AUDIT_UPDATE_TRIGGER,
        delete_trigger=_ACCESS_AUDIT_DELETE_TRIGGER,
        postgres_function=_ACCESS_AUDIT_POSTGRES_FUNCTION,
    )


def _create_binding_immutability_guards() -> None:
    _create_immutability_guards(
        table=_BINDING_TABLE,
        update_trigger=_BINDING_UPDATE_TRIGGER,
        delete_trigger=_BINDING_DELETE_TRIGGER,
        postgres_function=_BINDING_POSTGRES_FUNCTION,
        mutation_error=_BINDING_MUTATION_ERROR,
        unsupported_error="HOLDOUT_ARTIFACT_BINDING_DIALECT_UNSUPPORTED",
    )


def _drop_binding_immutability_guards() -> None:
    _drop_immutability_guards(
        table=_BINDING_TABLE,
        update_trigger=_BINDING_UPDATE_TRIGGER,
        delete_trigger=_BINDING_DELETE_TRIGGER,
        postgres_function=_BINDING_POSTGRES_FUNCTION,
    )


def _create_gate_immutability_guards() -> None:
    _create_immutability_guards(
        table=_GATE_TABLE,
        update_trigger=_GATE_UPDATE_TRIGGER,
        delete_trigger=_GATE_DELETE_TRIGGER,
        postgres_function=_GATE_POSTGRES_FUNCTION,
        mutation_error=_GATE_MUTATION_ERROR,
        unsupported_error="HOLDOUT_GATE_DECISION_DIALECT_UNSUPPORTED",
    )


def _drop_gate_immutability_guards() -> None:
    _drop_immutability_guards(
        table=_GATE_TABLE,
        update_trigger=_GATE_UPDATE_TRIGGER,
        delete_trigger=_GATE_DELETE_TRIGGER,
        postgres_function=_GATE_POSTGRES_FUNCTION,
    )


def _create_immutability_guards(
    *,
    table: str,
    update_trigger: str,
    delete_trigger: str,
    postgres_function: str,
    mutation_error: str,
    unsupported_error: str,
) -> None:
    """Install native UPDATE/DELETE denial for each supported database."""

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {update_trigger} BEFORE UPDATE ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{mutation_error}'); END"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {delete_trigger} BEFORE DELETE ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{mutation_error}'); END"
            )
        )
        return
    if dialect == "postgresql":
        op.execute(
            sa.text(
                f"CREATE FUNCTION {postgres_function}() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN "
                f"RAISE EXCEPTION '{mutation_error}'; RETURN OLD; END; $$"
            )
        )
        for trigger, operation in (
            (update_trigger, "UPDATE"),
            (delete_trigger, "DELETE"),
        ):
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {postgres_function}()"
                )
            )
        return
    if dialect in {"mysql", "mariadb"}:
        existing = _mysql_trigger_names(bind, table) if not context.is_offline_mode() else set()
        for trigger, operation in (
            (update_trigger, "UPDATE"),
            (delete_trigger, "DELETE"),
        ):
            if trigger in existing:
                continue
            op.execute(
                sa.text(
                    f"CREATE TRIGGER {trigger} BEFORE {operation} ON {table} "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    f"SET MESSAGE_TEXT = '{mutation_error}'"
                )
            )
        return
    raise RuntimeError(f"{unsupported_error}:{dialect}")


def _mysql_trigger_names(bind: Any, table: str) -> set[str]:
    statement = sa.text(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
        "WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = :table_name"
    )
    return {
        str(row[0])
        for row in bind.execute(statement, {"table_name": table})
    }


def _drop_immutability_guards(
    *,
    table: str,
    update_trigger: str,
    delete_trigger: str,
    postgres_function: str,
) -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for trigger in (update_trigger, delete_trigger):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON {table}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {postgres_function}()"))
        return
    for trigger in (update_trigger, delete_trigger):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))
