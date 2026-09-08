"""Add the durable idempotency journal for sealed-holdout execution.

Revision ID: 20260908_ai_research_holdout_executions
Revises: 20260908_ai_research_evidence_command

The journal is written before any evaluator dispatch.  A retry accepts only an
exactly matching completed schema; partially applied or conflicting DDL fails
closed.  This matters for MySQL-family databases, whose DDL can commit before
Alembic advances the revision marker.
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_ai_research_holdout_executions"
down_revision = "20260908_ai_research_evidence_command"
branch_labels = None
depends_on = None

_TABLE = "ai_research_holdout_executions"
_ACCESS_TABLE = "ai_research_holdout_access_audits"
_ACCESS_ACTION_CHECK = "ck_ai_research_holdout_access_audit_action"
_ACCESS_OUTCOME_CHECK = "ck_ai_research_holdout_access_audit_outcome"
_ACCESS_UPDATE_TRIGGER = "trg_ai_research_holdout_access_audit_no_update"
_ACCESS_DELETE_TRIGGER = "trg_ai_research_holdout_access_audit_no_delete"
_ACCESS_MUTATION_ERROR = "HOLDOUT_ACCESS_AUDIT_IMMUTABLE"

_COLUMNS = {
    "id",
    "operation_id",
    "user_id",
    "command_id",
    "evaluation_id",
    "command_hash",
    "lease_owner",
    "lease_generation",
    "lease_expires_at",
    "state",
    "command_json",
    "result_hash",
    "result_json",
    "error_code",
    "prepared_at",
    "dispatched_at",
    "observed_at",
    "not_executed_at",
    "settled_at",
    "updated_at",
}
_NULLABLE = {
    "result_hash",
    "result_json",
    "error_code",
    "dispatched_at",
    "observed_at",
    "not_executed_at",
    "settled_at",
}
_UNIQUES = {
    "uq_ai_research_holdout_execution_operation": ("operation_id",),
    "uq_ai_research_holdout_execution_command": ("command_id",),
}
_INDEXES = {
    "ix_ai_research_holdout_execution_state_updated": ("state", "updated_at"),
    "ix_ai_research_holdout_execution_owner_command": ("user_id", "command_id"),
}
_FOREIGN_KEYS = {
    "user_id": "users",
    "command_id": "ai_research_holdout_evaluation_commands",
    "evaluation_id": "ai_research_evaluations",
}
_CHECK_SQL = {
    "ck_ai_research_holdout_execution_state": (
        "state IN ('PREPARED', 'IN_FLIGHT', 'OBSERVED', 'UNKNOWN', 'SETTLED')"
    ),
    "ck_ai_research_holdout_execution_generation": "lease_generation > 0",
    "ck_ai_research_holdout_execution_result_group": (
        "(result_hash IS NULL AND result_json IS NULL AND observed_at IS NULL) OR "
        "(result_hash IS NOT NULL AND result_json IS NOT NULL AND observed_at IS NOT NULL)"
    ),
    "ck_ai_research_holdout_execution_result_state": (
        "(state IN ('OBSERVED', 'SETTLED') AND result_hash IS NOT NULL) OR "
        "(state IN ('PREPARED', 'IN_FLIGHT', 'UNKNOWN') AND result_hash IS NULL)"
    ),
    "ck_ai_research_holdout_execution_error_state": (
        "(state = 'UNKNOWN' AND error_code IS NOT NULL) OR "
        "(state != 'UNKNOWN' AND error_code IS NULL)"
    ),
    "ck_ai_research_holdout_execution_settlement": (
        "(state = 'SETTLED' AND settled_at IS NOT NULL) OR "
        "(state != 'SETTLED' AND settled_at IS NULL)"
    ),
}

_LEGACY_ACTION_CHECK = (
    "action IN ('CLAIM_STARTED', 'CLAIM_REJECTED', 'CLAIM_UNKNOWN', "
    "'LEASE_EXPIRED_RECONCILING', 'CHECKPOINT_RECORDED', "
    "'CHECKPOINT_REJECTED', 'CHECKPOINT_UNKNOWN', 'FINALIZE_COMPLETED', "
    "'FINALIZE_REJECTED', 'FINALIZE_UNKNOWN', 'RECONCILE_COMPLETED', "
    "'RECONCILE_REJECTED')"
)
_EXPANDED_ACTION_CHECK = (
    "action IN ('CLAIM_STARTED', 'CLAIM_REJECTED', 'CLAIM_UNKNOWN', "
    "'LEASE_EXPIRED_RECONCILING', 'EXECUTION_OBSERVED_RECONCILING', "
    "'CHECKPOINT_RECORDED', 'CHECKPOINT_REJECTED', 'CHECKPOINT_UNKNOWN', "
    "'FINALIZE_COMPLETED', 'FINALIZE_REJECTED', 'FINALIZE_UNKNOWN', "
    "'RECONCILE_COMPLETED', 'RECONCILE_REJECTED')"
)
_LEGACY_OUTCOME_CHECK = (
    "(action IN ('CLAIM_STARTED', 'LEASE_EXPIRED_RECONCILING', "
    "'CHECKPOINT_RECORDED', 'FINALIZE_COMPLETED', 'RECONCILE_COMPLETED') AND "
    "result = 'ACCEPTED') OR (action IN ('CLAIM_REJECTED', "
    "'CHECKPOINT_REJECTED', 'FINALIZE_REJECTED', 'RECONCILE_REJECTED') AND "
    "result = 'REJECTED') OR (action IN ('CLAIM_UNKNOWN', "
    "'CHECKPOINT_UNKNOWN', 'FINALIZE_UNKNOWN') AND result = 'UNKNOWN')"
)
_EXPANDED_OUTCOME_CHECK = (
    "(action IN ('CLAIM_STARTED', 'LEASE_EXPIRED_RECONCILING', "
    "'EXECUTION_OBSERVED_RECONCILING', 'CHECKPOINT_RECORDED', "
    "'FINALIZE_COMPLETED', 'RECONCILE_COMPLETED') AND result = 'ACCEPTED') OR "
    "(action IN ('CLAIM_REJECTED', 'CHECKPOINT_REJECTED', "
    "'FINALIZE_REJECTED', 'RECONCILE_REJECTED') AND result = 'REJECTED') OR "
    "(action IN ('CLAIM_UNKNOWN', 'CHECKPOINT_UNKNOWN', "
    "'FINALIZE_UNKNOWN') AND result = 'UNKNOWN')"
)


def upgrade() -> None:
    """Install the journal and the exact recovery-audit transition."""

    bind = op.get_bind()
    if context.is_offline_mode():
        _offline_schema_precheck()
        _create_execution_table()
        _create_execution_indexes()
        _replace_access_checks(bind, expanded=True, observed="legacy")
        return

    schema_state = _execution_schema_state(bind)
    access_state = _access_check_state(bind)
    if schema_state == "conflict":
        raise RuntimeError("HOLDOUT_EXECUTION_SCHEMA_CONFLICT")
    if access_state == "conflict":
        raise RuntimeError("HOLDOUT_EXECUTION_ACCESS_SCHEMA_CONFLICT")
    if schema_state == "absent":
        _create_execution_table()
        _create_execution_indexes()
    if access_state == "legacy":
        _replace_access_checks(bind, expanded=True, observed=access_state)


def downgrade() -> None:
    """Remove the journal only when no execution or recovery audit is retained."""

    bind = op.get_bind()
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: HOLDOUT_EXECUTION_DOWNGRADE_BLOCKED; abort if "
            "either query below returns a row."
        )
        op.execute(sa.text(f"SELECT 1 FROM {_TABLE} LIMIT 1"))
        op.execute(
            sa.text(
                f"SELECT 1 FROM {_ACCESS_TABLE} "
                "WHERE action = 'EXECUTION_OBSERVED_RECONCILING' LIMIT 1"
            )
        )
        _drop_execution_schema()
        _replace_access_checks(bind, expanded=False, observed="expanded")
        return

    table_exists = sa.inspect(bind).has_table(_TABLE)
    if table_exists and bind.execute(sa.text(f"SELECT 1 FROM {_TABLE} LIMIT 1")).first():
        raise RuntimeError("HOLDOUT_EXECUTION_DOWNGRADE_BLOCKED")
    if bind.execute(
        sa.text(
            f"SELECT 1 FROM {_ACCESS_TABLE} WHERE action = 'EXECUTION_OBSERVED_RECONCILING' LIMIT 1"
        )
    ).first():
        raise RuntimeError("HOLDOUT_EXECUTION_DOWNGRADE_BLOCKED")

    access_state = _access_check_state(bind)
    if access_state == "conflict":
        raise RuntimeError("HOLDOUT_EXECUTION_ACCESS_SCHEMA_CONFLICT")
    if table_exists:
        schema_state = _execution_schema_state(bind)
        if schema_state != "exact":
            raise RuntimeError("HOLDOUT_EXECUTION_SCHEMA_CONFLICT")
        _drop_execution_schema()
    if access_state == "expanded":
        _replace_access_checks(bind, expanded=False, observed=access_state)


def _create_execution_table() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=128), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
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
            "evaluation_id",
            sa.String(length=36),
            sa.ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=False),
        sa.Column("lease_generation", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("command_json", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in _CHECK_SQL.items()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "operation_id",
            name="uq_ai_research_holdout_execution_operation",
        ),
        sa.UniqueConstraint(
            "command_id",
            name="uq_ai_research_holdout_execution_command",
        ),
    )


def _create_execution_indexes() -> None:
    for name, columns in _INDEXES.items():
        op.create_index(name, _TABLE, list(columns))


def _drop_execution_schema() -> None:
    for name in reversed(tuple(_INDEXES)):
        op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)


def _execution_schema_state(bind: Any) -> str:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        return "absent"

    columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    if set(columns) != _COLUMNS:
        return "conflict"
    if any(bool(column.get("nullable")) != (name in _NULLABLE) for name, column in columns.items()):
        return "conflict"
    primary_key = tuple(inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ())
    if primary_key != ("id",):
        return "conflict"

    uniques = {
        str(item.get("name")): tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(_TABLE)
        if item.get("name")
    }
    if uniques != _UNIQUES:
        return "conflict"
    indexes = {
        str(item.get("name")): tuple(item.get("column_names") or ())
        for item in inspector.get_indexes(_TABLE)
        if item.get("name") and not bool(item.get("unique"))
    }
    if indexes != _INDEXES:
        return "conflict"

    foreign_keys = {
        tuple(item.get("constrained_columns") or ()): item
        for item in inspector.get_foreign_keys(_TABLE)
    }
    if set(foreign_keys) != {(column,) for column in _FOREIGN_KEYS}:
        return "conflict"
    for column, target in _FOREIGN_KEYS.items():
        observed = foreign_keys[(column,)]
        if str(observed.get("referred_table")) != target:
            return "conflict"
        if tuple(observed.get("referred_columns") or ()) != ("id",):
            return "conflict"
        options = observed.get("options") or {}
        if str(options.get("ondelete", "")).upper() not in {"", "RESTRICT"}:
            return "conflict"

    checks = {
        str(item.get("name")): str(item.get("sqltext") or "")
        for item in inspector.get_check_constraints(_TABLE)
        if item.get("name")
    }
    if set(checks) != set(_CHECK_SQL):
        return "conflict"
    if any(not _sql_matches(checks[name], sql) for name, sql in _CHECK_SQL.items()):
        return "conflict"
    return "exact"


def _access_check_state(bind: Any) -> str:
    observed = {
        str(item.get("name")): str(item.get("sqltext") or "")
        for item in sa.inspect(bind).get_check_constraints(_ACCESS_TABLE)
        if item.get("name")
    }
    action = observed.get(_ACCESS_ACTION_CHECK)
    outcome = observed.get(_ACCESS_OUTCOME_CHECK)
    if action is None or outcome is None:
        return "conflict"
    if _sql_matches(action, _EXPANDED_ACTION_CHECK) and _sql_matches(
        outcome, _EXPANDED_OUTCOME_CHECK
    ):
        return "expanded"
    if _sql_matches(action, _LEGACY_ACTION_CHECK) and _sql_matches(outcome, _LEGACY_OUTCOME_CHECK):
        return "legacy"
    return "conflict"


def _replace_access_checks(bind: Any, *, expanded: bool, observed: str) -> None:
    expected = "legacy" if expanded else "expanded"
    if observed != expected:
        raise RuntimeError("HOLDOUT_EXECUTION_ACCESS_SCHEMA_CONFLICT")
    action_sql = _EXPANDED_ACTION_CHECK if expanded else _LEGACY_ACTION_CHECK
    outcome_sql = _EXPANDED_OUTCOME_CHECK if expanded else _LEGACY_OUTCOME_CHECK
    sqlite = bind.dialect.name == "sqlite"
    if sqlite:
        _drop_sqlite_access_guards()
    kwargs: dict[str, Any] = {}
    if sqlite and context.is_offline_mode():
        kwargs = {"copy_from": _offline_access_table(), "recreate": "always"}
    with op.batch_alter_table(_ACCESS_TABLE, **kwargs) as batch:
        batch.drop_constraint(_ACCESS_OUTCOME_CHECK, type_="check")
        batch.drop_constraint(_ACCESS_ACTION_CHECK, type_="check")
        batch.create_check_constraint(_ACCESS_ACTION_CHECK, action_sql)
        batch.create_check_constraint(_ACCESS_OUTCOME_CHECK, outcome_sql)
    if sqlite:
        _create_sqlite_access_guards()


def _offline_access_table() -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        _ACCESS_TABLE,
        metadata,
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
            sa.ForeignKey(
                "ai_research_holdout_evaluation_commands.id",
                ondelete="RESTRICT",
            ),
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
            sa.ForeignKey("ai_research_evaluations.id", ondelete="RESTRICT"),
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
            "result IN ('ACCEPTED', 'REJECTED', 'UNKNOWN')",
            name="ck_ai_research_holdout_access_audit_result",
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
        sa.CheckConstraint(_LEGACY_ACTION_CHECK, name=_ACCESS_ACTION_CHECK),
        sa.CheckConstraint(_LEGACY_OUTCOME_CHECK, name=_ACCESS_OUTCOME_CHECK),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action",
            "command_id",
            "lease_generation",
            name="uq_ai_research_holdout_access_audit_event",
        ),
    )
    sa.Index(
        "ix_ai_research_holdout_access_audit_actor_created",
        table.c.actor_identity,
        table.c.created_at,
    )
    sa.Index(
        "ix_ai_research_holdout_access_audit_requested_command",
        table.c.requested_command_id,
        table.c.created_at,
    )
    return table


def _drop_sqlite_access_guards() -> None:
    for trigger in (_ACCESS_UPDATE_TRIGGER, _ACCESS_DELETE_TRIGGER):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger}"))


def _create_sqlite_access_guards() -> None:
    op.execute(
        sa.text(
            f"CREATE TRIGGER {_ACCESS_UPDATE_TRIGGER} BEFORE UPDATE ON {_ACCESS_TABLE} "
            f"BEGIN SELECT RAISE(ABORT, '{_ACCESS_MUTATION_ERROR}'); END"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER {_ACCESS_DELETE_TRIGGER} BEFORE DELETE ON {_ACCESS_TABLE} "
            f"BEGIN SELECT RAISE(ABORT, '{_ACCESS_MUTATION_ERROR}'); END"
        )
    )


def _offline_schema_precheck() -> None:
    op.execute(
        "-- MANUAL PRECHECK: HOLDOUT_EXECUTION_SCHEMA_CONFLICT; abort unless "
        f"{_TABLE} is absent. For a retry, inspect and accept only the exact schema."
    )


def _sql_matches(observed: str, expected: str) -> bool:
    def normalize(value: str) -> str:
        value = value.lower().replace('"', "").replace("`", "")
        value = re.sub(r"\s+", "", value)
        while value.startswith("(") and value.endswith(")"):
            inner = value[1:-1]
            depth = 0
            balanced = True
            for character in inner:
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                    if depth < 0:
                        balanced = False
                        break
            if not balanced or depth != 0:
                break
            value = inner
        return value

    return normalize(observed) == normalize(expected)
