"""Add server-authorized and immutable research approval authority.

Revision ID: 20260908_ai_research_approval_authority
Revises: 20260908_ai_research_holdout_executions

Legacy approval rows remain readable.  New v2 request and decision authority is
an all-or-none nullable binding, while new human grants live in a dedicated
run-scoped table.  Database guards make decisions append-only, constrain
request transitions, and permit exactly one complete grant revocation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql as mysql_types
from sqlalchemy.dialects import postgresql as postgresql_types

from alembic import context, op

revision = "20260908_ai_research_approval_authority"
down_revision = "20260908_ai_research_holdout_executions"
branch_labels = None
depends_on = None

_GRANT_TABLE = "ai_research_approval_grants"
_GRANT_AUDIT_TABLE = "ai_research_approval_grant_audits"
_PROFILE_TABLE = "ai_research_capability_profiles"
_REQUEST_TABLE = "ai_research_approval_requests"
_DECISION_TABLE = "ai_research_human_decisions"
_DENIAL_FENCE_TABLE = "ai_research_approval_denial_fences"
_USER_TABLE = "users"
_PRINCIPAL_KIND_COLUMN = "principal_kind"
_PRINCIPAL_KIND_CHECK = "ck_users_principal_kind"
_PRINCIPAL_KIND_CHECK_SQL = "principal_kind IN ('HUMAN', 'SERVICE', 'UNKNOWN')"
_PRINCIPAL_KIND_DEFAULT = "UNKNOWN"

_PROFILE_MATERIAL_COLUMNS = (
    "id",
    "profile_id",
    "version",
    "topology",
    "actor_mode",
    "db_engine",
    "service_identities",
    "queue_capabilities",
    "storage_boundaries",
    "network_capabilities",
    "sandbox_capabilities",
    "approval_capabilities",
    "evidence_hash",
    "verified_at",
    "expires_at",
    "created_at",
)

_GRANT_INDEX = "ix_ai_research_approval_grant_scope"
_GRANT_AUDIT_INDEX = "ix_ai_research_approval_grant_audit_scope"
_REQUEST_INDEX = "ix_ai_research_approval_request_run_candidate_status"
_DECISION_INDEX = "ix_ai_research_human_decision_run_candidate_decided"
_DECISION_REQUEST_UNIQUE = "uq_ai_research_human_decision_approval_request"
_REQUEST_CANDIDATE_FK = "fk_ai_research_approval_request_candidate"
_DECISION_CANDIDATE_FK = "fk_ai_research_human_decision_candidate"
_DENIAL_FENCE_INDEX = "ix_ai_research_approval_denial_fence_run_candidate"
_PROFILE_EXPIRY_INDEX = "ix_ai_research_capability_profile_expiry"

_INDEX_SPECS = {
    (_GRANT_TABLE, _GRANT_INDEX): (
        ("actor_id", "run_id", "workspace_id", "permission", "expires_at"),
        False,
    ),
    (_GRANT_AUDIT_TABLE, _GRANT_AUDIT_INDEX): (
        ("run_id", "subject_id", "event_type", "occurred_at"),
        False,
    ),
    (_REQUEST_TABLE, _REQUEST_INDEX): (
        ("run_id", "candidate_id", "status", "requested_at"),
        False,
    ),
    (_DECISION_TABLE, _DECISION_INDEX): (
        ("run_id", "candidate_id", "decided_at"),
        False,
    ),
    (_DENIAL_FENCE_TABLE, _DENIAL_FENCE_INDEX): (
        ("run_id", "candidate_id", "created_at"),
        False,
    ),
}

_GRANT_CHECKS = {
    "ck_ai_research_approval_grant_human_identity": (
        "subject_kind = 'HUMAN' AND issuer_kind = 'HUMAN'"
    ),
    "ck_ai_research_approval_grant_permission": "permission = 'research:approve'",
    "ck_ai_research_approval_grant_revocation_time": (
        "revoked_at IS NULL OR revoked_at >= issued_at"
    ),
    "ck_ai_research_approval_grant_revocation_group": (
        "(revoked_at IS NULL AND revoked_by IS NULL AND revocation_reason IS NULL) OR "
        "(revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND "
        "length(trim(revocation_reason)) > 0)"
    ),
    "ck_ai_research_approval_grant_expiry": "expires_at > issued_at",
}
_GRANT_AUDIT_CHECKS = {
    "ck_ai_research_approval_grant_audit_event": "event_type IN ('ISSUED', 'REVOKED')",
    "ck_ai_research_approval_grant_audit_reason": (
        "(event_type = 'ISSUED' AND reason_hash IS NULL) OR "
        "(event_type = 'REVOKED' AND reason_hash IS NOT NULL)"
    ),
    "ck_ai_research_approval_grant_audit_hash_lengths": (
        "length(policy_material_hash) = 64 AND length(command_material_hash) = 64 AND "
        "(reason_hash IS NULL OR length(reason_hash) = 64)"
    ),
}
_REQUEST_CHECKS = {
    "ck_ai_research_approval_request_mode": (
        "approval_mode IS NULL OR approval_mode IN ('single_actor', 'multi_actor')"
    ),
    "ck_ai_research_approval_request_v2_binding": (
        "(run_id IS NULL AND evidence_package_id IS NULL AND "
        "policy_material_hash IS NULL AND approval_mode IS NULL AND "
        "capability_profile_id IS NULL AND capability_profile_version IS NULL AND "
        "capability_evidence_hash IS NULL AND request_material_hash IS NULL) OR "
        "(run_id IS NOT NULL AND evidence_package_id IS NOT NULL AND "
        "policy_material_hash IS NOT NULL AND approval_mode IS NOT NULL AND "
        "capability_profile_id IS NOT NULL AND capability_profile_version IS NOT NULL AND "
        "capability_evidence_hash IS NOT NULL AND request_material_hash IS NOT NULL)"
    ),
    "ck_ai_research_approval_request_decided_state": (
        "(status = 'PENDING' AND decided_at IS NULL) OR "
        "(status != 'PENDING' AND decided_at IS NOT NULL)"
    ),
    "ck_ai_research_approval_request_time_order": (
        "eligible_at >= requested_at AND expires_at > requested_at"
    ),
}
_DECISION_CHECKS = {
    "ck_ai_research_human_decision_mode": ("approval_mode IN ('single_actor', 'multi_actor')"),
    "ck_ai_research_human_decision_actor_mode": (
        "(approval_mode = 'single_actor' AND single_actor = TRUE) OR "
        "(approval_mode = 'multi_actor' AND single_actor = FALSE)"
    ),
    "ck_ai_research_human_decision_v2_binding": (
        "(approval_request_id IS NULL AND run_id IS NULL AND evidence_package_id IS NULL "
        "AND grant_id IS NULL AND grant_hash IS NULL AND policy_material_hash IS NULL "
        "AND capability_profile_id IS NULL AND capability_profile_version IS NULL "
        "AND capability_evidence_hash IS NULL AND challenge_hash IS NULL "
        "AND risk_acknowledgement_hash IS NULL AND reason_hash IS NULL "
        "AND gate_input_evidence_hash IS NULL AND decision_material_hash IS NULL) OR "
        "(approval_request_id IS NOT NULL AND run_id IS NOT NULL "
        "AND evidence_package_id IS NOT NULL AND grant_id IS NOT NULL "
        "AND grant_hash IS NOT NULL AND policy_material_hash IS NOT NULL "
        "AND capability_profile_id IS NOT NULL AND capability_profile_version IS NOT NULL "
        "AND capability_evidence_hash IS NOT NULL AND challenge_hash IS NOT NULL "
        "AND risk_acknowledgement_hash IS NOT NULL AND reason_hash IS NOT NULL "
        "AND gate_input_evidence_hash IS NOT NULL AND decision_material_hash IS NOT NULL "
        "AND requested_at IS NOT NULL AND eligible_at IS NOT NULL "
        "AND expires_at IS NOT NULL AND comment IS NOT NULL "
        "AND length(trim(comment)) > 0)"
    ),
    "ck_ai_research_human_decision_time_order": (
        "approval_request_id IS NULL OR "
        "(eligible_at >= requested_at AND decided_at >= requested_at "
        "AND expires_at > decided_at)"
    ),
}
_DENIAL_FENCE_CHECKS = {
    "ck_ai_research_approval_denial_fence_decision": (
        "decision IN ('REJECTED', 'REQUESTED_CHANGES')"
    ),
    "ck_ai_research_approval_denial_fence_hash_lengths": (
        "length(fence_scope_hash) = 64 AND length(gate_input_evidence_hash) = 64 AND "
        "length(evidence_package_hash) = 64 AND "
        "length(approval_policy_material_hash) = 64 AND "
        "length(approval_binding_hash) = 64"
    ),
}

# Ordered so a MySQL-family DDL interruption is an observable prefix.  SQLite
# attaches table-wide checks to the final nullable column.
_REQUEST_COLUMNS = (
    ("run_id", 36, "ai_research_runs", "fk_ai_research_approval_request_run"),
    ("workspace_id", 36, None, None),
    (
        "evidence_package_id",
        36,
        "ai_research_evidence_packages",
        "fk_ai_research_approval_request_evidence_package",
    ),
    ("policy_material_hash", 64, None, None),
    ("approval_mode", 32, None, None),
    ("capability_profile_id", 128, None, None),
    ("capability_profile_version", 128, None, None),
    ("capability_evidence_hash", 64, None, None),
    ("request_material_hash", 64, None, None),
)
_DECISION_COLUMNS = (
    ("run_id", 36, "ai_research_runs", "fk_ai_research_human_decision_run"),
    ("workspace_id", 36, None, None),
    (
        "approval_request_id",
        36,
        _REQUEST_TABLE,
        "fk_ai_research_human_decision_approval_request",
    ),
    (
        "evidence_package_id",
        36,
        "ai_research_evidence_packages",
        "fk_ai_research_human_decision_evidence_package",
    ),
    ("policy_material_hash", 64, None, None),
    ("capability_profile_id", 128, None, None),
    ("capability_profile_version", 128, None, None),
    ("capability_evidence_hash", 64, None, None),
    ("grant_id", 36, _GRANT_TABLE, "fk_ai_research_human_decision_grant"),
    ("grant_hash", 64, None, None),
    ("challenge_hash", 64, None, None),
    ("risk_acknowledgement_hash", 64, None, None),
    ("reason_hash", 64, None, None),
    ("gate_input_evidence_hash", 64, None, None),
    ("decision_material_hash", 64, None, None),
)
_REQUEST_REQUIRED = tuple(
    name for name, _length, _target, _constraint in _REQUEST_COLUMNS if name != "workspace_id"
)
_DECISION_REQUIRED = tuple(
    name for name, _length, _target, _constraint in _DECISION_COLUMNS if name != "workspace_id"
)

_DECISION_UPDATE_TRIGGER = "trg_ai_research_human_decision_update_guard"
_DECISION_DELETE_TRIGGER = "trg_ai_research_human_decision_delete_guard"
_REQUEST_UPDATE_TRIGGER = "trg_ai_research_approval_request_update_guard"
_REQUEST_DELETE_TRIGGER = "trg_ai_research_approval_request_delete_guard"
_GRANT_UPDATE_TRIGGER = "trg_ai_research_approval_grant_update_guard"
_GRANT_DELETE_TRIGGER = "trg_ai_research_approval_grant_delete_guard"
_GRANT_AUDIT_UPDATE_TRIGGER = "trg_ai_research_approval_grant_audit_update_guard"
_GRANT_AUDIT_DELETE_TRIGGER = "trg_ai_research_approval_grant_audit_delete_guard"
_PROFILE_UPDATE_TRIGGER = "trg_ai_research_capability_profile_update_guard"
_PROFILE_DELETE_TRIGGER = "trg_ai_research_capability_profile_delete_guard"
_DENIAL_FENCE_UPDATE_TRIGGER = "trg_ai_research_approval_denial_fence_update_guard"
_DENIAL_FENCE_DELETE_TRIGGER = "trg_ai_research_approval_denial_fence_delete_guard"

_DECISION_UPDATE_FUNCTION = "guard_ai_research_human_decision_update"
_DECISION_DELETE_FUNCTION = "deny_ai_research_human_decision_delete"
_REQUEST_UPDATE_FUNCTION = "guard_ai_research_approval_request_update"
_REQUEST_DELETE_FUNCTION = "deny_ai_research_approval_request_delete"
_GRANT_UPDATE_FUNCTION = "guard_ai_research_approval_grant_update"
_GRANT_DELETE_FUNCTION = "deny_ai_research_approval_grant_delete"
_GRANT_AUDIT_UPDATE_FUNCTION = "deny_ai_research_approval_grant_audit_update"
_GRANT_AUDIT_DELETE_FUNCTION = "deny_ai_research_approval_grant_audit_delete"
_PROFILE_UPDATE_FUNCTION = "deny_ai_research_capability_profile_update"
_PROFILE_DELETE_FUNCTION = "deny_ai_research_capability_profile_delete"
_DENIAL_FENCE_UPDATE_FUNCTION = "deny_ai_research_approval_denial_fence_update"
_DENIAL_FENCE_DELETE_FUNCTION = "deny_ai_research_approval_denial_fence_delete"

_REQUEST_IMMUTABLE_COLUMNS = (
    "id",
    "candidate_id",
    *(name for name, _length, _target, _constraint in _REQUEST_COLUMNS),
    "requested_by",
    "policy_version",
    "gate_input_evidence_hash",
    "evidence_package_hash",
    "idempotency_key",
    "requested_at",
    "eligible_at",
    "expires_at",
)
_GRANT_IMMUTABLE_COLUMNS = (
    "id",
    "actor_id",
    "run_id",
    "workspace_id",
    "permission",
    "subject_kind",
    "issuer_id",
    "issuer_kind",
    "grant_hash",
    "issued_at",
    "expires_at",
    "created_at",
)


class _PostgresqlGuardDefinition:
    __slots__ = (
        "legacy_signature",
        "relation_schema",
        "current_schema",
        "relation_oid",
        "resolved_relation_oid",
        "function_schema",
        "enabled",
        "when_expression",
        "update_columns",
        "trigger_definition",
        "function_definition",
    )

    def __init__(
        self,
        *,
        legacy_signature: str,
        relation_schema: str,
        current_schema: str,
        relation_oid: Any,
        resolved_relation_oid: Any,
        function_schema: str,
        enabled: str,
        when_expression: Any,
        update_columns: Any,
        trigger_definition: str,
        function_definition: str,
    ) -> None:
        self.legacy_signature = legacy_signature
        self.relation_schema = relation_schema
        self.current_schema = current_schema
        self.relation_oid = relation_oid
        self.resolved_relation_oid = resolved_relation_oid
        self.function_schema = function_schema
        self.enabled = enabled
        self.when_expression = when_expression
        self.update_columns = update_columns
        self.trigger_definition = trigger_definition
        self.function_definition = function_definition


class _PostgresqlFunctionDefinition:
    __slots__ = (
        "function_schema",
        "current_schema",
        "function_oid",
        "resolved_function_oid",
        "function_definition",
        "referencing_trigger_count",
        "target_trigger_count",
    )

    def __init__(
        self,
        *,
        function_schema: str,
        current_schema: str,
        function_oid: Any,
        resolved_function_oid: Any,
        function_definition: str,
        referencing_trigger_count: Any,
        target_trigger_count: Any,
    ) -> None:
        self.function_schema = function_schema
        self.current_schema = current_schema
        self.function_oid = function_oid
        self.resolved_function_oid = resolved_function_oid
        self.function_definition = function_definition
        self.referencing_trigger_count = referencing_trigger_count
        self.target_trigger_count = target_trigger_count


def upgrade() -> None:
    """Install exact approval authority and immutable state transitions."""

    bind = op.get_bind()
    if context.is_offline_mode():
        _upgrade_offline(bind)
    else:
        _upgrade_online(bind)
    _create_guards(bind)
    if not context.is_offline_mode():
        _assert_upgrade_schema_exact(bind)


def downgrade() -> None:
    """Remove authority metadata only when no v2 approval evidence is retained."""

    bind = op.get_bind()
    _acquire_downgrade_write_fence(bind)
    if not context.is_offline_mode():
        _assert_upgrade_schema_exact(bind)
    _assert_downgrade_safe(bind)
    if not context.is_offline_mode():
        _assert_upgrade_schema_exact(bind)
    _drop_guards(bind)
    if context.is_offline_mode():
        _downgrade_offline(bind)
    else:
        _downgrade_online(bind)


def _upgrade_offline(bind: Any) -> None:
    _upgrade_principal_kind_offline(bind)
    _create_grant_table()
    _create_grant_audit_table()
    _add_columns_offline(bind, _REQUEST_TABLE, _REQUEST_COLUMNS, _REQUEST_CHECKS)
    _add_columns_offline(bind, _DECISION_TABLE, _DECISION_COLUMNS, _DECISION_CHECKS)
    _create_denial_fence_table()
    _emit_data_prechecks()
    _ensure_candidate_foreign_keys(bind)
    _create_indexes_and_unique(bind)


def _upgrade_online(bind: Any) -> None:
    _ensure_principal_kind(bind)
    _assert_capability_profile_contract(bind)
    _assert_legacy_request_state_clean(bind)
    grant_state = _grant_schema_state(bind)
    if grant_state == "absent":
        _create_grant_table()
    elif grant_state != "exact":
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    grant_audit_state = _grant_audit_schema_state(bind)
    if grant_audit_state == "absent":
        _create_grant_audit_table()
    elif grant_audit_state != "exact":
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")

    _upgrade_existing_table(
        bind,
        table_name=_REQUEST_TABLE,
        specs=_REQUEST_COLUMNS,
        checks=_REQUEST_CHECKS,
    )
    _upgrade_existing_table(
        bind,
        table_name=_DECISION_TABLE,
        specs=_DECISION_COLUMNS,
        checks=_DECISION_CHECKS,
    )
    denial_fence_state = _denial_fence_schema_state(bind)
    if denial_fence_state == "absent":
        _create_denial_fence_table()
    elif denial_fence_state != "exact":
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    _assert_data_clean(bind)
    _ensure_foreign_keys(bind, _REQUEST_TABLE, _REQUEST_COLUMNS)
    _ensure_checks(bind, _REQUEST_TABLE, _REQUEST_CHECKS)
    _ensure_foreign_keys(bind, _DECISION_TABLE, _DECISION_COLUMNS)
    _ensure_checks(bind, _DECISION_TABLE, _DECISION_CHECKS)
    _ensure_candidate_foreign_keys(bind)
    _create_indexes_and_unique(bind)


def _assert_capability_profile_contract(bind: Any) -> None:
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name
    if not inspector.has_table(_PROFILE_TABLE):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    columns = {str(item["name"]): item for item in inspector.get_columns(_PROFILE_TABLE)}
    if tuple(columns) != _PROFILE_MATERIAL_COLUMNS and set(columns) != set(
        _PROFILE_MATERIAL_COLUMNS
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    string_lengths = {
        "id": 36,
        "profile_id": 128,
        "version": 128,
        "topology": 128,
        "actor_mode": 32,
        "db_engine": 64,
        "evidence_hash": 64,
    }
    json_columns = {
        "service_identities",
        "queue_capabilities",
        "storage_boundaries",
        "network_capabilities",
        "sandbox_capabilities",
        "approval_capabilities",
    }
    datetime_columns = {"verified_at", "expires_at", "created_at"}
    for name, column in columns.items():
        if bool(column.get("nullable")) != (name == "db_engine"):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if not _plain_column_metadata_matches(column):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if name in string_lengths and not _string_type_matches(
            column,
            string_lengths[name],
            dialect_name=dialect_name,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if name in json_columns and not isinstance(column.get("type"), sa.JSON):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if name in datetime_columns and not _datetime_type_matches(
            column,
            dialect_name=dialect_name,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    if tuple(inspector.get_pk_constraint(_PROFILE_TABLE).get("constrained_columns") or ()) != (
        "id",
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    unique_name = "uq_ai_research_capability_profile_version"
    unique_names = {
        str(item["name"])
        for item in inspector.get_unique_constraints(_PROFILE_TABLE)
        if item.get("name")
    }
    if unique_names != {unique_name}:
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    _assert_unique_constraint_exact(
        bind,
        table_name=_PROFILE_TABLE,
        name=unique_name,
        columns=("profile_id", "version"),
    )
    _assert_index_exact(
        bind,
        table_name=_PROFILE_TABLE,
        name=_PROFILE_EXPIRY_INDEX,
        columns=("profile_id", "expires_at"),
        unique=False,
    )


def _assert_upgrade_schema_exact(bind: Any) -> None:
    """Freshly reflect every migration-owned object after all DDL completes."""

    _assert_principal_kind_exact(bind)
    _assert_capability_profile_contract(bind)
    if _grant_schema_state(bind) != "exact":
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    if _grant_audit_schema_state(bind) != "exact":
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    if _denial_fence_schema_state(bind) != "exact":
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    for table_name, specs, checks in (
        (_REQUEST_TABLE, _REQUEST_COLUMNS, _REQUEST_CHECKS),
        (_DECISION_TABLE, _DECISION_COLUMNS, _DECISION_CHECKS),
    ):
        columns = {str(item["name"]): item for item in sa.inspect(bind).get_columns(table_name)}
        for name, length, target, constraint_name in specs:
            if name not in columns or not _nullable_string_column_matches(
                columns[name],
                length,
                dialect_name=bind.dialect.name,
            ):
                raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
            if target is not None and constraint_name is not None:
                _assert_foreign_key_exact(
                    bind,
                    table_name=table_name,
                    column_name=name,
                    target_table=target,
                    constraint_name=constraint_name,
                )
        _assert_checks_exact(bind, table_name=table_name, checks=checks)
        _assert_foreign_key_exact(
            bind,
            table_name=table_name,
            column_name="candidate_id",
            target_table="ai_research_candidates",
            constraint_name=(
                _REQUEST_CANDIDATE_FK if table_name == _REQUEST_TABLE else _DECISION_CANDIDATE_FK
            ),
        )
    for (table_name, name), (columns, unique) in _INDEX_SPECS.items():
        _assert_index_exact(
            bind,
            table_name=table_name,
            name=name,
            columns=columns,
            unique=unique,
        )
    _assert_decision_request_unique_exact(bind)
    _assert_guards_exact(bind)


def _upgrade_principal_kind_offline(bind: Any) -> None:
    """Render the resumable principal classification contract for SQL review."""

    op.add_column(
        _USER_TABLE,
        sa.Column(
            _PRINCIPAL_KIND_COLUMN,
            sa.String(length=16),
            nullable=True,
            server_default=sa.text(f"'{_PRINCIPAL_KIND_DEFAULT}'"),
        ),
    )
    op.execute(
        sa.text(
            f"UPDATE {_USER_TABLE} SET {_PRINCIPAL_KIND_COLUMN} = "
            f"'{_PRINCIPAL_KIND_DEFAULT}' WHERE {_PRINCIPAL_KIND_COLUMN} IS NULL"
        )
    )
    op.execute(
        "-- MANUAL PRECHECK: APPROVAL_PRINCIPAL_KIND_DATA_CONFLICT; abort if "
        "users.principal_kind contains a value outside HUMAN, SERVICE, UNKNOWN."
    )
    op.execute(
        sa.text(
            f"SELECT 1 FROM {_USER_TABLE} WHERE {_PRINCIPAL_KIND_COLUMN} NOT IN "
            "('HUMAN', 'SERVICE', 'UNKNOWN') LIMIT 1"
        )
    )
    if bind.dialect.name == "sqlite":
        op.execute(
            "-- SQLITE BATCH REBUILD REQUIRED: preserve the complete users table, make "
            "principal_kind VARCHAR(16) DEFAULT 'UNKNOWN' NOT NULL, and add CONSTRAINT "
            f"{_PRINCIPAL_KIND_CHECK} CHECK ({_PRINCIPAL_KIND_CHECK_SQL})."
        )
        return
    op.create_check_constraint(
        _PRINCIPAL_KIND_CHECK,
        _USER_TABLE,
        _PRINCIPAL_KIND_CHECK_SQL,
    )
    op.alter_column(
        _USER_TABLE,
        _PRINCIPAL_KIND_COLUMN,
        existing_type=sa.String(length=16),
        existing_server_default=sa.text(f"'{_PRINCIPAL_KIND_DEFAULT}'"),
        nullable=False,
    )


def _ensure_principal_kind(bind: Any) -> None:
    """Classify legacy users as UNKNOWN and finish any exact DDL prefix safely."""

    inspector = sa.inspect(bind)
    if not inspector.has_table(_USER_TABLE):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    columns = {str(item["name"]): item for item in inspector.get_columns(_USER_TABLE)}
    column = columns.get(_PRINCIPAL_KIND_COLUMN)
    if column is None:
        op.add_column(
            _USER_TABLE,
            sa.Column(
                _PRINCIPAL_KIND_COLUMN,
                sa.String(length=16),
                nullable=True,
                server_default=sa.text(f"'{_PRINCIPAL_KIND_DEFAULT}'"),
            ),
        )
        inspector = sa.inspect(bind)
        columns = {str(item["name"]): item for item in inspector.get_columns(_USER_TABLE)}
        column = columns.get(_PRINCIPAL_KIND_COLUMN)
    if column is None or not _principal_kind_column_matches(
        column,
        dialect_name=bind.dialect.name,
        nullable=None,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")

    principal_checks = _principal_kind_checks(bind)
    existing_check = principal_checks.get(_PRINCIPAL_KIND_CHECK)
    if existing_check is not None and not _sql_matches(
        existing_check,
        _PRINCIPAL_KIND_CHECK_SQL,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    if any(name != _PRINCIPAL_KIND_CHECK for name in principal_checks):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    _assert_principal_kind_dependencies_absent(bind)
    _assert_principal_kind_values_clean(bind, allow_null=True)
    bind.execute(
        sa.text(
            f"UPDATE {_USER_TABLE} SET {_PRINCIPAL_KIND_COLUMN} = "
            f"'{_PRINCIPAL_KIND_DEFAULT}' WHERE {_PRINCIPAL_KIND_COLUMN} IS NULL"
        )
    )
    _assert_principal_kind_values_clean(bind, allow_null=False)

    needs_check = existing_check is None
    needs_not_null = bool(column.get("nullable"))
    if bind.dialect.name == "sqlite" and (needs_check or needs_not_null):
        with op.batch_alter_table(_USER_TABLE, recreate="always") as batch_op:
            if needs_check:
                batch_op.create_check_constraint(
                    _PRINCIPAL_KIND_CHECK,
                    _PRINCIPAL_KIND_CHECK_SQL,
                )
            if needs_not_null:
                batch_op.alter_column(
                    _PRINCIPAL_KIND_COLUMN,
                    existing_type=sa.String(length=16),
                    existing_server_default=sa.text(f"'{_PRINCIPAL_KIND_DEFAULT}'"),
                    nullable=False,
                )
    else:
        if needs_check:
            op.create_check_constraint(
                _PRINCIPAL_KIND_CHECK,
                _USER_TABLE,
                _PRINCIPAL_KIND_CHECK_SQL,
            )
        if needs_not_null:
            op.alter_column(
                _USER_TABLE,
                _PRINCIPAL_KIND_COLUMN,
                existing_type=sa.String(length=16),
                existing_nullable=True,
                existing_server_default=sa.text(f"'{_PRINCIPAL_KIND_DEFAULT}'"),
                nullable=False,
            )
    _assert_principal_kind_exact(bind)


def _assert_principal_kind_exact(bind: Any) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_USER_TABLE):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    columns = {str(item["name"]): item for item in inspector.get_columns(_USER_TABLE)}
    column = columns.get(_PRINCIPAL_KIND_COLUMN)
    if column is None or not _principal_kind_column_matches(
        column,
        dialect_name=bind.dialect.name,
        nullable=False,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    checks = _principal_kind_checks(bind)
    if set(checks) != {_PRINCIPAL_KIND_CHECK} or not _sql_matches(
        checks[_PRINCIPAL_KIND_CHECK],
        _PRINCIPAL_KIND_CHECK_SQL,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    _assert_principal_kind_dependencies_absent(bind)
    _assert_principal_kind_values_clean(bind, allow_null=False)


def _principal_kind_column_matches(
    column: dict[str, Any],
    *,
    dialect_name: str,
    nullable: bool | None,
) -> bool:
    if not _string_type_matches(column, 16, dialect_name=dialect_name):
        return False
    if nullable is not None and bool(column.get("nullable")) is not nullable:
        return False
    if not _principal_default_matches(column.get("default"), dialect_name=dialect_name):
        return False
    if column.get("computed") is not None or column.get("identity") is not None:
        return False
    return True


def _principal_default_matches(value: Any, *, dialect_name: str) -> bool:
    if value is None:
        return False
    normalized = re.sub(r"\s+", " ", str(value).strip().upper())
    while (
        len(normalized) >= 2
        and normalized.startswith("(")
        and normalized.endswith(")")
        and _text_has_single_outer_parenthesis_pair(normalized)
    ):
        normalized = normalized[1:-1].strip()
    quoted_variants = {
        "'UNKNOWN'",
        "'UNKNOWN'::CHARACTER VARYING",
        "'UNKNOWN'::VARCHAR",
        "'UNKNOWN'::VARCHAR(16)",
    }
    if normalized in quoted_variants:
        return True
    return dialect_name in {"mysql", "mariadb"} and normalized == "UNKNOWN"


def _text_has_single_outer_parenthesis_pair(value: str) -> bool:
    depth = 0
    quoted = False
    index = 0
    while index < len(value):
        character = value[index]
        if character == "'":
            if quoted and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif not quoted and character == "(":
            depth += 1
        elif not quoted and character == ")":
            depth -= 1
            if depth == 0 and index != len(value) - 1:
                return False
            if depth < 0:
                return False
        index += 1
    return not quoted and depth == 0


def _principal_kind_checks(bind: Any) -> dict[str, str]:
    checks: dict[str, str] = {}
    for item in sa.inspect(bind).get_check_constraints(_USER_TABLE):
        sql = str(item.get("sqltext") or "")
        name = str(item.get("name") or "")
        if name != _PRINCIPAL_KIND_CHECK and not _sql_mentions_identifier(
            sql,
            _PRINCIPAL_KIND_COLUMN,
        ):
            continue
        if not name or name in checks:
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        checks[name] = sql
    return checks


def _sql_mentions_identifier(sql: str, identifier: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(identifier)}(?![A-Za-z0-9_])",
            re.sub(r"[`\"\[\]]", "", sql),
            re.IGNORECASE,
        )
    )


def _assert_principal_kind_dependencies_absent(bind: Any) -> None:
    inspector = sa.inspect(bind)
    for collection in (
        (inspector.get_pk_constraint(_USER_TABLE),),
        inspector.get_indexes(_USER_TABLE),
        inspector.get_unique_constraints(_USER_TABLE),
        _observed_foreign_keys(bind, _USER_TABLE),
    ):
        if any(
            _PRINCIPAL_KIND_COLUMN
            in tuple(item.get("column_names") or item.get("constrained_columns") or ())
            for item in collection
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")


def _assert_principal_kind_values_clean(bind: Any, *, allow_null: bool) -> None:
    null_predicate = "" if allow_null else f"{_PRINCIPAL_KIND_COLUMN} IS NULL OR "
    statement = sa.text(
        f"SELECT 1 FROM {_USER_TABLE} WHERE {null_predicate}"
        f"{_PRINCIPAL_KIND_COLUMN} IS NOT NULL AND {_PRINCIPAL_KIND_COLUMN} NOT IN "
        "('HUMAN', 'SERVICE', 'UNKNOWN') LIMIT 1"
    )
    if bind.execute(statement).first():
        raise RuntimeError("APPROVAL_PRINCIPAL_KIND_DATA_CONFLICT")


def _assert_checks_exact(bind: Any, *, table_name: str, checks: dict[str, str]) -> None:
    observed = {
        str(item["name"]): str(item.get("sqltext") or "")
        for item in sa.inspect(bind).get_check_constraints(table_name)
        if item.get("name")
    }
    if any(
        name not in observed or not _sql_matches(observed[name], sql)
        for name, sql in checks.items()
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")


def _assert_foreign_key_exact(
    bind: Any,
    *,
    table_name: str,
    column_name: str,
    target_table: str,
    constraint_name: str,
) -> None:
    matches = [
        item
        for item in _observed_foreign_keys(bind, table_name)
        if tuple(item.get("constrained_columns") or ()) == (column_name,)
    ]
    if len(matches) != 1 or not _foreign_key_matches(
        matches[0], target_table, expected_name=constraint_name
    ):
        raise RuntimeError(
            f"APPROVAL_AUTHORITY_SCHEMA_CONFLICT:{table_name}.{column_name}:FOREIGN_KEY"
        )


def _assert_index_exact(
    bind: Any,
    *,
    table_name: str,
    name: str,
    columns: tuple[str, ...],
    unique: bool,
) -> None:
    matches = [
        item for item in sa.inspect(bind).get_indexes(table_name) if item.get("name") == name
    ]
    if len(matches) != 1 or not _index_matches(
        matches[0],
        columns=columns,
        unique=unique,
        dialect_name=bind.dialect.name,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    if bind.dialect.name in {"mysql", "mariadb"}:
        _assert_mysql_index_catalog_exact(
            bind,
            table_name=table_name,
            name=name,
            columns=columns,
            unique=unique,
        )


def _assert_unique_constraint_exact(
    bind: Any,
    *,
    table_name: str,
    name: str,
    columns: tuple[str, ...],
    sqlite_as_index: bool = False,
) -> None:
    """Require one exact UQ and its dialect-specific reflected backing index."""

    inspector = sa.inspect(bind)
    indexes = [item for item in inspector.get_indexes(table_name) if item.get("name") == name]
    uniques = [
        item for item in inspector.get_unique_constraints(table_name) if item.get("name") == name
    ]
    dialect_name = bind.dialect.name
    if dialect_name == "sqlite" and sqlite_as_index:
        if (
            uniques
            or len(indexes) != 1
            or not _index_matches(
                indexes[0],
                columns=columns,
                unique=True,
                dialect_name=dialect_name,
            )
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        return

    if len(uniques) != 1:
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    unique = uniques[0]
    unique_metadata = {
        key: value for key, value in unique.items() if key not in {"name", "column_names"}
    }
    if tuple(unique.get("column_names") or ()) != columns:
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")

    if dialect_name == "postgresql":
        if unique_metadata.get("duplicates_index") not in (None, ""):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if not _index_metadata_is_default(unique_metadata):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if len(indexes) != 1 or not _index_matches(
            indexes[0],
            columns=columns,
            unique=True,
            dialect_name=dialect_name,
            duplicates_constraint=name,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        return

    if dialect_name in {"mysql", "mariadb"}:
        if unique_metadata.pop("duplicates_index", None) != name or not _index_metadata_is_default(
            unique_metadata
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if len(indexes) != 1 or not _index_matches(
            indexes[0],
            columns=columns,
            unique=True,
            dialect_name=dialect_name,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        _assert_mysql_index_catalog_exact(
            bind,
            table_name=table_name,
            name=name,
            columns=columns,
            unique=True,
        )
        return

    if indexes or not _index_metadata_is_default(unique_metadata):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")


def _assert_decision_request_unique_exact(bind: Any) -> None:
    _assert_unique_constraint_exact(
        bind,
        table_name=_DECISION_TABLE,
        name=_DECISION_REQUEST_UNIQUE,
        columns=("approval_request_id",),
        sqlite_as_index=True,
    )


def _create_grant_table() -> None:
    op.create_table(
        _GRANT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column("issuer_id", sa.String(length=36), nullable=False),
        sa.Column("issuer_kind", sa.String(length=16), nullable=False),
        sa.Column("grant_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=36), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in _GRANT_CHECKS.items()),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_ai_research_approval_grant_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_research_runs.id"],
            name="fk_ai_research_approval_grant_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["issuer_id"],
            ["users.id"],
            name="fk_ai_research_approval_grant_issuer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name="fk_ai_research_approval_grant_revoker",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_hash", name="uq_ai_research_approval_grant_hash"),
    )


def _create_grant_audit_table() -> None:
    op.create_table(
        _GRANT_AUDIT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("grant_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("policy_material_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("command_material_hash", sa.String(length=64), nullable=False),
        sa.Column("reason_hash", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in _GRANT_AUDIT_CHECKS.items()),
        sa.ForeignKeyConstraint(
            ["grant_id"],
            [f"{_GRANT_TABLE}.id"],
            name="fk_ai_research_approval_grant_audit_grant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name="fk_ai_research_approval_grant_audit_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_research_runs.id"],
            name="fk_ai_research_approval_grant_audit_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["users.id"],
            name="fk_ai_research_approval_grant_audit_subject",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_id",
            "idempotency_key",
            name="uq_ai_research_approval_grant_audit_idempotency",
        ),
        sa.UniqueConstraint(
            "grant_id",
            "event_type",
            name="uq_ai_research_approval_grant_audit_event",
        ),
    )


def _create_denial_fence_table() -> None:
    op.create_table(
        _DENIAL_FENCE_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_package_id", sa.String(length=36), nullable=False),
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("promotion_policy_version", sa.String(length=128), nullable=False),
        sa.Column("approval_policy_version", sa.String(length=128), nullable=False),
        sa.Column("approval_policy_material_hash", sa.String(length=64), nullable=False),
        sa.Column("gate_input_evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_package_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("fence_scope_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in _DENIAL_FENCE_CHECKS.items()),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["ai_research_candidates.id"],
            name="fk_ai_research_approval_denial_fence_candidate",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ai_research_runs.id"],
            name="fk_ai_research_approval_denial_fence_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_package_id"],
            ["ai_research_evidence_packages.id"],
            name="fk_ai_research_approval_denial_fence_evidence_package",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"],
            ["ai_research_human_decisions.id"],
            name="fk_ai_research_approval_denial_fence_decision",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "fence_scope_hash",
            name="uq_ai_research_approval_denial_fence_scope",
        ),
        sa.UniqueConstraint(
            "decision_id",
            name="uq_ai_research_approval_denial_fence_decision",
        ),
    )


def _add_columns_offline(
    bind: Any,
    table_name: str,
    specs: tuple[tuple[str, int, str | None, str | None], ...],
    checks: dict[str, str],
) -> None:
    if bind.dialect.name == "sqlite":
        for position, spec in enumerate(specs):
            _add_sqlite_column(
                table_name,
                spec,
                checks=checks if position == len(specs) - 1 else {},
            )
        return
    for name, length, _target, _constraint in specs:
        op.add_column(table_name, sa.Column(name, sa.String(length=length), nullable=True))
    for name, _length, target, constraint_name in specs:
        if target is not None and constraint_name is not None:
            op.create_foreign_key(
                constraint_name,
                table_name,
                target,
                [name],
                ["id"],
                ondelete="RESTRICT",
            )
    for check_name, check_sql in checks.items():
        op.create_check_constraint(check_name, table_name, check_sql)


def _upgrade_existing_table(
    bind: Any,
    *,
    table_name: str,
    specs: tuple[tuple[str, int, str | None, str | None], ...],
    checks: dict[str, str],
) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    observed = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    ordered_names = tuple(spec[0] for spec in specs)
    present = tuple(name for name in ordered_names if name in observed)
    if set(present) != set(ordered_names[: len(present)]):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    spec_by_name = {spec[0]: spec for spec in specs}
    for name in present:
        if not _nullable_string_column_matches(
            observed[name],
            spec_by_name[name][1],
            dialect_name=bind.dialect.name,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")

    if present and len(present) != len(specs):
        predicate = " OR ".join(f"{name} IS NOT NULL" for name in present)
        if bind.execute(sa.text(f"SELECT 1 FROM {table_name} WHERE {predicate} LIMIT 1")).first():
            raise RuntimeError("APPROVAL_AUTHORITY_PARTIAL_BINDING")
        _require_existing_sqlite_foreign_keys(bind, table_name, present, spec_by_name)

    for position, spec in enumerate(specs[len(present) :], start=len(present)):
        if bind.dialect.name == "sqlite":
            _add_sqlite_column(
                table_name,
                spec,
                checks=checks if position == len(specs) - 1 else {},
            )
        else:
            op.add_column(
                table_name,
                sa.Column(spec[0], sa.String(length=spec[1]), nullable=True),
            )


def _assert_legacy_request_state_clean(bind: Any) -> None:
    """Validate pre-existing columns before SQLite attaches new table checks."""

    statements = (
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE NOT "
        "((status = 'PENDING' AND decided_at IS NULL) OR "
        "(status != 'PENDING' AND decided_at IS NOT NULL)) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE eligible_at < requested_at "
        "OR expires_at <= requested_at LIMIT 1",
    )
    for statement in statements:
        if bind.execute(sa.text(statement)).first():
            raise RuntimeError("APPROVAL_AUTHORITY_DATA_CONFLICT")


def _add_sqlite_column(
    table_name: str,
    spec: tuple[str, int, str | None, str | None],
    *,
    checks: dict[str, str],
) -> None:
    name, length, target, constraint_name = spec
    foreign_sql = ""
    if context.is_offline_mode() and target is not None and constraint_name is not None:
        foreign_sql = f" CONSTRAINT {constraint_name} REFERENCES {target}(id) ON DELETE RESTRICT"
    check_sql = "".join(
        f" CONSTRAINT {check_name} CHECK ({expression})"
        for check_name, expression in checks.items()
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {table_name} ADD COLUMN {name} VARCHAR({length}){foreign_sql}{check_sql}"
        )
    )


def _create_indexes_and_unique(bind: Any) -> None:
    _ensure_index(
        bind,
        table_name=_GRANT_TABLE,
        name=_GRANT_INDEX,
        columns=("actor_id", "run_id", "workspace_id", "permission", "expires_at"),
        unique=False,
    )
    _ensure_index(
        bind,
        table_name=_GRANT_AUDIT_TABLE,
        name=_GRANT_AUDIT_INDEX,
        columns=("run_id", "subject_id", "event_type", "occurred_at"),
        unique=False,
    )
    _ensure_index(
        bind,
        table_name=_REQUEST_TABLE,
        name=_REQUEST_INDEX,
        columns=("run_id", "candidate_id", "status", "requested_at"),
        unique=False,
    )
    _ensure_index(
        bind,
        table_name=_DECISION_TABLE,
        name=_DECISION_INDEX,
        columns=("run_id", "candidate_id", "decided_at"),
        unique=False,
    )
    _ensure_decision_request_unique(bind)
    _ensure_index(
        bind,
        table_name=_DENIAL_FENCE_TABLE,
        name=_DENIAL_FENCE_INDEX,
        columns=("run_id", "candidate_id", "created_at"),
        unique=False,
    )


def _ensure_index(
    bind: Any,
    *,
    table_name: str,
    name: str,
    columns: tuple[str, ...],
    unique: bool,
) -> None:
    if context.is_offline_mode():
        _create_index(bind, name=name, table_name=table_name, columns=columns, unique=unique)
        return
    observed = {
        str(index["name"]): index
        for index in sa.inspect(bind).get_indexes(table_name)
        if index.get("name")
    }
    existing = observed.get(name)
    if existing is None:
        _create_index(bind, name=name, table_name=table_name, columns=columns, unique=unique)
        return
    if not _index_matches(
        existing,
        columns=columns,
        unique=unique,
        dialect_name=bind.dialect.name,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    if bind.dialect.name in {"mysql", "mariadb"}:
        _assert_mysql_index_catalog_exact(
            bind,
            table_name=table_name,
            name=name,
            columns=columns,
            unique=unique,
        )


def _create_index(
    bind: Any,
    *,
    name: str,
    table_name: str,
    columns: tuple[str, ...],
    unique: bool,
) -> None:
    dialect_options: dict[str, Any] = {}
    if bind.dialect.name == "mysql":
        dialect_options["mysql_using"] = "btree"
    elif bind.dialect.name == "mariadb":
        dialect_options["mariadb_using"] = "btree"
    op.create_index(
        name,
        table_name,
        list(columns),
        unique=unique,
        **dialect_options,
    )


def _index_matches(
    index: dict[str, Any],
    *,
    columns: tuple[str, ...],
    unique: bool,
    dialect_name: str,
    duplicates_constraint: str | None = None,
) -> bool:
    if (
        tuple(index.get("column_names") or ()) != columns
        or bool(index.get("unique", False)) is not unique
    ):
        return False
    reflected_type = str(index.get("type") or "").upper()
    if dialect_name in {"mysql", "mariadb"}:
        expected_type = "UNIQUE" if unique else ""
        if reflected_type != expected_type:
            return False
    elif reflected_type:
        return False
    reflected_duplicate = index.get("duplicates_constraint")
    if duplicates_constraint is None:
        if reflected_duplicate not in (None, ""):
            return False
    elif reflected_duplicate != duplicates_constraint:
        return False
    semantic_metadata = {
        key: value
        for key, value in index.items()
        if key not in {"name", "column_names", "unique", "type", "duplicates_constraint"}
    }
    return _index_metadata_is_default(semantic_metadata)


def _assert_mysql_index_catalog_exact(
    bind: Any,
    *,
    table_name: str,
    name: str,
    columns: tuple[str, ...],
    unique: bool,
) -> None:
    """Verify MySQL-family physical index properties omitted by Inspector."""

    dialect_name = bind.dialect.name
    if dialect_name not in {"mysql", "mariadb"}:
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    version = getattr(bind.dialect, "server_version_info", None)
    if not isinstance(version, tuple) or not version:
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    capability_rows = bind.execute(
        sa.text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = 'information_schema' AND TABLE_NAME = 'STATISTICS' "
            "AND COLUMN_NAME IN ('IS_VISIBLE', 'IGNORED')"
        )
    )
    capabilities = {str(row[0]).upper() for row in capability_rows}
    visibility_expression = "NULL"
    ignored_expression = "NULL"
    if dialect_name == "mysql" and version >= (8, 0):
        if "IS_VISIBLE" not in capabilities:
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        visibility_expression = "IS_VISIBLE"
    elif dialect_name == "mariadb" and version >= (10, 6):
        if "IGNORED" not in capabilities:
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        ignored_expression = "IGNORED"

    rows = list(
        bind.execute(
            sa.text(
                "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, INDEX_TYPE, "
                f"{visibility_expression} AS IS_VISIBLE, "
                f"{ignored_expression} AS IGNORED "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
                "AND INDEX_NAME = :index_name ORDER BY SEQ_IN_INDEX"
            ),
            {"table_name": table_name, "index_name": name},
        )
    )
    if len(rows) != len(columns):
        raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
    expected_non_unique = 0 if unique else 1
    for position, (row, column_name) in enumerate(zip(rows, columns, strict=True), start=1):
        try:
            exact = (
                len(row) == 7
                and str(row[0]) == name
                and int(row[1]) == expected_non_unique
                and int(row[2]) == position
                and str(row[3]) == column_name
                and str(row[4]).upper() == "BTREE"
            )
        except (TypeError, ValueError):
            exact = False
        if not exact:
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if visibility_expression != "NULL" and str(row[5]).upper() != "YES":
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if ignored_expression != "NULL" and str(row[6]).upper() != "NO":
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")


def _index_metadata_is_default(value: Any, *, key: str = "") -> bool:
    normalized_key = key.lower()
    if "visible" in normalized_key or "visibility" in normalized_key:
        return value is True or value in (None, "")
    if value is None or value is False or value == "":
        return True
    if isinstance(value, dict):
        return all(
            _index_metadata_is_default(item, key=str(item_key)) for item_key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return all(_index_metadata_is_default(item, key=key) for item in value)
    return False


def _ensure_decision_request_unique(bind: Any) -> None:
    if context.is_offline_mode():
        if bind.dialect.name == "sqlite":
            _create_index(
                bind,
                name=_DECISION_REQUEST_UNIQUE,
                table_name=_DECISION_TABLE,
                columns=("approval_request_id",),
                unique=True,
            )
        else:
            op.create_unique_constraint(
                _DECISION_REQUEST_UNIQUE,
                _DECISION_TABLE,
                ["approval_request_id"],
            )
        return

    inspector = sa.inspect(bind)
    indexes = [
        index
        for index in inspector.get_indexes(_DECISION_TABLE)
        if index.get("name") == _DECISION_REQUEST_UNIQUE
    ]
    uniques = [
        item
        for item in inspector.get_unique_constraints(_DECISION_TABLE)
        if item.get("name") == _DECISION_REQUEST_UNIQUE
    ]
    if indexes or uniques:
        _assert_decision_request_unique_exact(bind)
        return
    if bind.dialect.name == "sqlite":
        _create_index(
            bind,
            name=_DECISION_REQUEST_UNIQUE,
            table_name=_DECISION_TABLE,
            columns=("approval_request_id",),
            unique=True,
        )
    else:
        op.create_unique_constraint(
            _DECISION_REQUEST_UNIQUE,
            _DECISION_TABLE,
            ["approval_request_id"],
        )


def _ensure_foreign_keys(
    bind: Any,
    table_name: str,
    specs: tuple[tuple[str, int, str | None, str | None], ...],
) -> None:
    observed = _observed_foreign_keys(bind, table_name)
    for name, _length, target, constraint_name in specs:
        if target is None or constraint_name is None:
            continue
        matches = [
            item for item in observed if tuple(item.get("constrained_columns") or ()) == (name,)
        ]
        if matches:
            if len(matches) != 1 or not _foreign_key_matches(
                matches[0],
                target,
                expected_name=constraint_name,
            ):
                raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
            continue
        if bind.dialect.name == "sqlite":
            continue
        op.create_foreign_key(
            constraint_name,
            table_name,
            target,
            [name],
            ["id"],
            ondelete="RESTRICT",
        )


def _require_existing_sqlite_foreign_keys(
    bind: Any,
    table_name: str,
    present: tuple[str, ...],
    specs: dict[str, tuple[str, int, str | None, str | None]],
) -> None:
    if bind.dialect.name != "sqlite":
        return
    observed = _observed_foreign_keys(bind, table_name)
    for name in present:
        target = specs[name][2]
        if target is None:
            continue
        matches = [
            item for item in observed if tuple(item.get("constrained_columns") or ()) == (name,)
        ]
        if matches and (
            len(matches) != 1
            or not _foreign_key_matches(
                matches[0],
                target,
                expected_name=specs[name][3],
            )
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")


def _observed_foreign_keys(bind: Any, table_name: str) -> list[dict[str, Any]]:
    inspector = sa.inspect(bind)
    if bind.dialect.name != "sqlite":
        return list(inspector.get_foreign_keys(table_name))

    table_sql_row = bind.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
        {"table_name": table_name},
    ).first()
    table_sql = str(table_sql_row[0] or "") if table_sql_row is not None else ""
    names_by_column: dict[str, str] = {}
    identifier = r'[`"\[]?([A-Za-z_][A-Za-z0-9_]*)[`"\]]?'
    table_constraint = re.compile(
        rf"CONSTRAINT\s+{identifier}\s+FOREIGN\s+KEY\s*\(\s*{identifier}\s*\)",
        re.IGNORECASE,
    )
    inline_constraint = re.compile(
        rf"(?:\(|,)\s*{identifier}\s+[^,]*?CONSTRAINT\s+{identifier}\s+REFERENCES\b",
        re.IGNORECASE,
    )
    for match in table_constraint.finditer(table_sql):
        names_by_column[match.group(2)] = match.group(1)
    for match in inline_constraint.finditer(table_sql):
        names_by_column[match.group(1)] = match.group(2)

    reflected = {
        tuple(item.get("constrained_columns") or ()): dict(item)
        for item in inspector.get_foreign_keys(table_name)
    }
    observed: list[dict[str, Any]] = []
    for row in bind.execute(sa.text(f"PRAGMA foreign_key_list({table_name})")):
        key = (str(row[3]),)
        item = reflected.get(key, {})
        observed.append(
            {
                **item,
                "name": item.get("name") or names_by_column.get(key[0]),
                "constrained_columns": [key[0]],
                "referred_table": str(row[2]),
                "referred_columns": [str(row[4])],
                "options": {"ondelete": str(row[6]).upper()},
            }
        )
    return observed


def _foreign_key_matches(
    observed: dict[str, Any],
    target: str,
    *,
    expected_name: str | None = None,
) -> bool:
    options = observed.get("options") or {}
    return bool(
        (expected_name is None or str(observed.get("name") or "") == expected_name)
        and str(observed.get("referred_table")) == target
        and tuple(observed.get("referred_columns") or ()) == ("id",)
        and str(options.get("ondelete") or "").upper() == "RESTRICT"
    )


def _strict_foreign_key_matches(observed: dict[str, Any], target: str) -> bool:
    return _foreign_key_matches(observed, target)


def _ensure_candidate_foreign_keys(bind: Any) -> None:
    for table_name, constraint_name, specs in (
        (_REQUEST_TABLE, _REQUEST_CANDIDATE_FK, _REQUEST_COLUMNS),
        (_DECISION_TABLE, _DECISION_CANDIDATE_FK, _DECISION_COLUMNS),
    ):
        if context.is_offline_mode():
            if bind.dialect.name == "sqlite":
                op.execute(
                    f"-- SQLITE BATCH REBUILD REQUIRED: {constraint_name} "
                    "candidate_id REFERENCES ai_research_candidates(id) ON DELETE RESTRICT"
                )
            else:
                op.create_foreign_key(
                    constraint_name,
                    table_name,
                    "ai_research_candidates",
                    ["candidate_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
            continue
        required = {
            "candidate_id": ("ai_research_candidates", constraint_name),
            **{
                name: (target, spec_constraint)
                for name, _length, target, spec_constraint in specs
                if target is not None and spec_constraint is not None
            },
        }
        foreign_keys = _observed_foreign_keys(bind, table_name)
        exact_existing: dict[str, str] = {}
        for column_name, (target, expected_name) in required.items():
            matches = [
                item
                for item in foreign_keys
                if tuple(item.get("constrained_columns") or ()) == (column_name,)
            ]
            if matches and (
                len(matches) != 1
                or not _foreign_key_matches(matches[0], target, expected_name=expected_name)
            ):
                raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
            if matches:
                exact_existing[column_name] = expected_name
        if len(exact_existing) == len(required):
            continue
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                for existing_name in exact_existing.values():
                    batch_op.drop_constraint(existing_name, type_="foreignkey")
                for column_name, (target, expected_name) in required.items():
                    batch_op.create_foreign_key(
                        expected_name,
                        target,
                        [column_name],
                        ["id"],
                        ondelete="RESTRICT",
                    )
        else:
            op.create_foreign_key(
                constraint_name,
                table_name,
                "ai_research_candidates",
                ["candidate_id"],
                ["id"],
                ondelete="RESTRICT",
            )


def _ensure_checks(bind: Any, table_name: str, checks: dict[str, str]) -> None:
    inspector = sa.inspect(bind)
    observed = {
        str(item["name"]): str(item.get("sqltext") or "")
        for item in inspector.get_check_constraints(table_name)
        if item.get("name")
    }
    for name, expected in checks.items():
        if name in observed:
            if not _sql_matches(observed[name], expected):
                raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        elif bind.dialect.name == "sqlite":
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        else:
            op.create_check_constraint(name, table_name, expected)


def _grant_schema_state(bind: Any) -> str:
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name
    if not inspector.has_table(_GRANT_TABLE):
        return "absent"
    expected_lengths = {
        "id": 36,
        "actor_id": 36,
        "run_id": 36,
        "workspace_id": 36,
        "permission": 64,
        "subject_kind": 16,
        "issuer_id": 36,
        "issuer_kind": 16,
        "grant_hash": 64,
        "revoked_by": 36,
    }
    nullable = {"workspace_id", "revoked_at", "revoked_by", "revocation_reason"}
    datetime_columns = {"issued_at", "expires_at", "revoked_at", "created_at"}
    columns = {str(item["name"]): item for item in inspector.get_columns(_GRANT_TABLE)}
    expected_names = {
        "id",
        "actor_id",
        "run_id",
        "workspace_id",
        "permission",
        "subject_kind",
        "issuer_id",
        "issuer_kind",
        "grant_hash",
        "issued_at",
        "expires_at",
        "revoked_at",
        "revoked_by",
        "revocation_reason",
        "created_at",
    }
    if set(columns) != expected_names:
        return "conflict"
    for name, column in columns.items():
        if bool(column.get("nullable")) != (name in nullable):
            return "conflict"
        if not _plain_column_metadata_matches(column):
            return "conflict"
        if name in expected_lengths and not _string_type_matches(
            column,
            expected_lengths[name],
            dialect_name=dialect_name,
        ):
            return "conflict"
        if name in datetime_columns and not _datetime_type_matches(
            column,
            dialect_name=dialect_name,
        ):
            return "conflict"
        if name == "revocation_reason" and not _text_type_matches(
            column,
            dialect_name=dialect_name,
        ):
            return "conflict"
    if tuple(inspector.get_pk_constraint(_GRANT_TABLE).get("constrained_columns") or ()) != ("id",):
        return "conflict"
    unique_names = {
        str(item["name"])
        for item in inspector.get_unique_constraints(_GRANT_TABLE)
        if item.get("name")
    }
    unique_name = "uq_ai_research_approval_grant_hash"
    if unique_names != {unique_name}:
        return "conflict"
    try:
        _assert_unique_constraint_exact(
            bind,
            table_name=_GRANT_TABLE,
            name=unique_name,
            columns=("grant_hash",),
        )
    except RuntimeError:
        return "conflict"
    checks = {
        str(item["name"]): str(item.get("sqltext") or "")
        for item in inspector.get_check_constraints(_GRANT_TABLE)
        if item.get("name")
    }
    if set(checks) != set(_GRANT_CHECKS):
        return "conflict"
    if any(not _sql_matches(checks[name], sql) for name, sql in _GRANT_CHECKS.items()):
        return "conflict"
    expected_foreign_keys = {
        "actor_id": ("users", "fk_ai_research_approval_grant_actor"),
        "run_id": ("ai_research_runs", "fk_ai_research_approval_grant_run"),
        "issuer_id": ("users", "fk_ai_research_approval_grant_issuer"),
        "revoked_by": ("users", "fk_ai_research_approval_grant_revoker"),
    }
    observed_foreign_keys = _observed_foreign_keys(bind, _GRANT_TABLE)
    if len(observed_foreign_keys) != len(expected_foreign_keys):
        return "conflict"
    for column_name, (target, constraint_name) in expected_foreign_keys.items():
        matches = [
            item
            for item in observed_foreign_keys
            if tuple(item.get("constrained_columns") or ()) == (column_name,)
        ]
        if len(matches) != 1 or not _foreign_key_matches(
            matches[0], target, expected_name=constraint_name
        ):
            return "conflict"
    return "exact"


def _grant_audit_schema_state(bind: Any) -> str:
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name
    if not inspector.has_table(_GRANT_AUDIT_TABLE):
        return "absent"
    expected_lengths = {
        "id": 36,
        "grant_id": 36,
        "event_type": 16,
        "actor_id": 36,
        "run_id": 36,
        "workspace_id": 36,
        "subject_id": 36,
        "permission": 64,
        "policy_version": 128,
        "policy_material_hash": 64,
        "idempotency_key": 128,
        "command_material_hash": 64,
        "reason_hash": 64,
    }
    expected_names = {*expected_lengths, "occurred_at"}
    columns = {str(item["name"]): item for item in inspector.get_columns(_GRANT_AUDIT_TABLE)}
    if set(columns) != expected_names:
        return "conflict"
    nullable = {"workspace_id", "reason_hash"}
    if any(bool(column.get("nullable")) != (name in nullable) for name, column in columns.items()):
        return "conflict"
    if any(not _plain_column_metadata_matches(column) for column in columns.values()):
        return "conflict"
    if any(
        not _string_type_matches(columns[name], length, dialect_name=dialect_name)
        for name, length in expected_lengths.items()
    ):
        return "conflict"
    if not _datetime_type_matches(columns["occurred_at"], dialect_name=dialect_name):
        return "conflict"
    if tuple(inspector.get_pk_constraint(_GRANT_AUDIT_TABLE).get("constrained_columns") or ()) != (
        "id",
    ):
        return "conflict"
    unique_specs = {
        "uq_ai_research_approval_grant_audit_idempotency": (
            "actor_id",
            "idempotency_key",
        ),
        "uq_ai_research_approval_grant_audit_event": ("grant_id", "event_type"),
    }
    unique_names = {
        str(item["name"])
        for item in inspector.get_unique_constraints(_GRANT_AUDIT_TABLE)
        if item.get("name")
    }
    if unique_names != set(unique_specs):
        return "conflict"
    try:
        for unique_name, unique_columns in unique_specs.items():
            _assert_unique_constraint_exact(
                bind,
                table_name=_GRANT_AUDIT_TABLE,
                name=unique_name,
                columns=unique_columns,
            )
    except RuntimeError:
        return "conflict"
    checks = {
        str(item["name"]): str(item.get("sqltext") or "")
        for item in inspector.get_check_constraints(_GRANT_AUDIT_TABLE)
        if item.get("name")
    }
    if set(checks) != set(_GRANT_AUDIT_CHECKS) or any(
        not _sql_matches(checks[name], sql) for name, sql in _GRANT_AUDIT_CHECKS.items()
    ):
        return "conflict"
    expected_foreign_keys = {
        "grant_id": (_GRANT_TABLE, "fk_ai_research_approval_grant_audit_grant"),
        "actor_id": ("users", "fk_ai_research_approval_grant_audit_actor"),
        "run_id": ("ai_research_runs", "fk_ai_research_approval_grant_audit_run"),
        "subject_id": ("users", "fk_ai_research_approval_grant_audit_subject"),
    }
    foreign_keys = _observed_foreign_keys(bind, _GRANT_AUDIT_TABLE)
    if len(foreign_keys) != len(expected_foreign_keys):
        return "conflict"
    for column_name, (target, constraint_name) in expected_foreign_keys.items():
        matches = [
            item
            for item in foreign_keys
            if tuple(item.get("constrained_columns") or ()) == (column_name,)
        ]
        if len(matches) != 1 or not _foreign_key_matches(
            matches[0], target, expected_name=constraint_name
        ):
            return "conflict"
    return "exact"


def _denial_fence_schema_state(bind: Any) -> str:
    inspector = sa.inspect(bind)
    dialect_name = bind.dialect.name
    if not inspector.has_table(_DENIAL_FENCE_TABLE):
        return "absent"
    expected_lengths = {
        "id": 36,
        "candidate_id": 36,
        "run_id": 36,
        "evidence_package_id": 36,
        "decision_id": 36,
        "decision": 32,
        "promotion_policy_version": 128,
        "approval_policy_version": 128,
        "approval_policy_material_hash": 64,
        "gate_input_evidence_hash": 64,
        "evidence_package_hash": 64,
        "approval_binding_hash": 64,
        "fence_scope_hash": 64,
    }
    expected_names = {*expected_lengths, "created_at"}
    columns = {str(item["name"]): item for item in inspector.get_columns(_DENIAL_FENCE_TABLE)}
    if set(columns) != expected_names:
        return "conflict"
    if any(bool(column.get("nullable")) for column in columns.values()):
        return "conflict"
    if any(not _plain_column_metadata_matches(column) for column in columns.values()):
        return "conflict"
    if any(
        not _string_type_matches(columns[name], length, dialect_name=dialect_name)
        for name, length in expected_lengths.items()
    ):
        return "conflict"
    if not _datetime_type_matches(columns["created_at"], dialect_name=dialect_name):
        return "conflict"
    if tuple(inspector.get_pk_constraint(_DENIAL_FENCE_TABLE).get("constrained_columns") or ()) != (
        "id",
    ):
        return "conflict"
    unique_specs = {
        "uq_ai_research_approval_denial_fence_scope": ("fence_scope_hash",),
        "uq_ai_research_approval_denial_fence_decision": ("decision_id",),
    }
    unique_names = {
        str(item["name"])
        for item in inspector.get_unique_constraints(_DENIAL_FENCE_TABLE)
        if item.get("name")
    }
    if unique_names != set(unique_specs):
        return "conflict"
    try:
        for unique_name, unique_columns in unique_specs.items():
            _assert_unique_constraint_exact(
                bind,
                table_name=_DENIAL_FENCE_TABLE,
                name=unique_name,
                columns=unique_columns,
            )
    except RuntimeError:
        return "conflict"
    checks = {
        str(item["name"]): str(item.get("sqltext") or "")
        for item in inspector.get_check_constraints(_DENIAL_FENCE_TABLE)
        if item.get("name")
    }
    if set(checks) != set(_DENIAL_FENCE_CHECKS) or any(
        not _sql_matches(checks[name], sql) for name, sql in _DENIAL_FENCE_CHECKS.items()
    ):
        return "conflict"
    expected_foreign_keys = {
        "candidate_id": (
            "ai_research_candidates",
            "fk_ai_research_approval_denial_fence_candidate",
        ),
        "run_id": (
            "ai_research_runs",
            "fk_ai_research_approval_denial_fence_run",
        ),
        "evidence_package_id": (
            "ai_research_evidence_packages",
            "fk_ai_research_approval_denial_fence_evidence_package",
        ),
        "decision_id": (
            "ai_research_human_decisions",
            "fk_ai_research_approval_denial_fence_decision",
        ),
    }
    foreign_keys = _observed_foreign_keys(bind, _DENIAL_FENCE_TABLE)
    if len(foreign_keys) != len(expected_foreign_keys):
        return "conflict"
    for column_name, (target, constraint_name) in expected_foreign_keys.items():
        matches = [
            item
            for item in foreign_keys
            if tuple(item.get("constrained_columns") or ()) == (column_name,)
        ]
        if len(matches) != 1 or not _foreign_key_matches(
            matches[0], target, expected_name=constraint_name
        ):
            return "conflict"
    return "exact"


def _nullable_string_column_matches(
    column: dict[str, Any],
    length: int,
    *,
    dialect_name: str,
) -> bool:
    return (
        bool(column.get("nullable"))
        and _string_type_matches(column, length, dialect_name=dialect_name)
        and _plain_column_metadata_matches(column)
    )


def _string_type_matches(
    column: dict[str, Any],
    length: int,
    *,
    dialect_name: str,
) -> bool:
    observed_type = column.get("type")
    if dialect_name in {"sqlite", "postgresql"}:
        expected_type = sa.VARCHAR
    elif dialect_name in {"mysql", "mariadb"}:
        expected_type = mysql_types.VARCHAR
    else:
        return False
    return (
        type(observed_type) is expected_type
        and getattr(observed_type, "length", None) == length
        and _string_options_are_plain(observed_type, dialect_name=dialect_name)
    )


def _datetime_type_matches(column: dict[str, Any], *, dialect_name: str) -> bool:
    observed_type = column.get("type")
    if dialect_name == "postgresql":
        return (
            type(observed_type) is postgresql_types.TIMESTAMP
            and getattr(observed_type, "timezone", None) is True
            and getattr(observed_type, "precision", None) is None
        )
    if dialect_name in {"mysql", "mariadb"}:
        return (
            type(observed_type) is mysql_types.DATETIME
            and getattr(observed_type, "timezone", None) is False
            and getattr(observed_type, "fsp", None) is None
        )
    if dialect_name == "sqlite":
        return (
            type(observed_type) is sa.DATETIME and getattr(observed_type, "timezone", None) is False
        )
    return False


def _text_type_matches(column: dict[str, Any], *, dialect_name: str) -> bool:
    observed_type = column.get("type")
    if dialect_name in {"sqlite", "postgresql"}:
        expected_type = sa.TEXT
    elif dialect_name in {"mysql", "mariadb"}:
        expected_type = mysql_types.TEXT
    else:
        return False
    return (
        type(observed_type) is expected_type
        and getattr(observed_type, "length", None) is None
        and _string_options_are_plain(observed_type, dialect_name=dialect_name)
    )


def _string_options_are_plain(observed_type: Any, *, dialect_name: str) -> bool:
    if getattr(observed_type, "collation", None) is not None:
        return False
    if dialect_name not in {"mysql", "mariadb"}:
        return True
    return (
        getattr(observed_type, "charset", None) is None
        and getattr(observed_type, "ascii", False) is False
        and getattr(observed_type, "unicode", False) is False
        and getattr(observed_type, "binary", False) is False
        and getattr(observed_type, "national", False) is False
    )


def _plain_column_metadata_matches(column: dict[str, Any]) -> bool:
    """Reject defaults and generated-column semantics not owned by this revision."""

    return (
        column.get("default") is None
        and column.get("computed") is None
        and column.get("identity") is None
    )


def _emit_data_prechecks() -> None:
    op.execute(
        "-- MANUAL PRECHECK: APPROVAL_AUTHORITY_PARTIAL_BINDING; abort if a query "
        "below returns a row."
    )
    for statement in _partial_binding_queries():
        op.execute(sa.text(statement))
    op.execute(
        "-- MANUAL PRECHECK: APPROVAL_AUTHORITY_DATA_CONFLICT; abort if a query "
        "below returns a row."
    )
    for statement in _integrity_queries():
        op.execute(sa.text(statement))
    op.execute(
        "-- MANUAL PRECHECK: APPROVAL_AUTHORITY_ORPHAN; abort if a query below returns a row."
    )
    for statement in _orphan_queries():
        op.execute(sa.text(statement))


def _assert_data_clean(bind: Any) -> None:
    for statement in _partial_binding_queries():
        if bind.execute(sa.text(statement)).first():
            raise RuntimeError("APPROVAL_AUTHORITY_PARTIAL_BINDING")
    for statement in _integrity_queries():
        if bind.execute(sa.text(statement)).first():
            raise RuntimeError("APPROVAL_AUTHORITY_DATA_CONFLICT")
    for statement in _orphan_queries():
        if bind.execute(sa.text(statement)).first():
            raise RuntimeError("APPROVAL_AUTHORITY_ORPHAN")


def _partial_binding_queries() -> tuple[str, ...]:
    request_all_null = " AND ".join(f"{name} IS NULL" for name in _REQUEST_REQUIRED)
    request_all_set = " AND ".join(f"{name} IS NOT NULL" for name in _REQUEST_REQUIRED)
    decision_all_null = " AND ".join(f"{name} IS NULL" for name in _DECISION_REQUIRED)
    decision_all_set = " AND ".join(f"{name} IS NOT NULL" for name in _DECISION_REQUIRED)
    return (
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE NOT (({request_all_null}) OR "
        f"({request_all_set})) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} WHERE NOT (({decision_all_null}) OR "
        f"({decision_all_set})) LIMIT 1",
    )


def _integrity_queries() -> tuple[str, ...]:
    return (
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE approval_mode IS NOT NULL AND "
        "approval_mode NOT IN ('single_actor', 'multi_actor') LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} WHERE approval_mode NOT IN "
        "('single_actor', 'multi_actor') OR "
        "(approval_mode = 'single_actor' AND NOT single_actor) OR "
        "(approval_mode = 'multi_actor' AND single_actor) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE NOT "
        "((status = 'PENDING' AND decided_at IS NULL) OR "
        "(status != 'PENDING' AND decided_at IS NOT NULL)) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE eligible_at < requested_at "
        "OR expires_at <= requested_at LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} WHERE decision_material_hash IS NOT NULL AND "
        "(comment IS NULL OR length(trim(comment)) = 0 OR requested_at IS NULL OR "
        "eligible_at IS NULL OR expires_at IS NULL OR eligible_at < requested_at OR "
        "decided_at < requested_at OR expires_at <= decided_at) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} WHERE approval_request_id IS NOT NULL "
        "GROUP BY approval_request_id HAVING count(*) > 1 LIMIT 1",
        f"SELECT 1 FROM {_GRANT_TABLE} WHERE expires_at <= issued_at OR "
        "(revoked_at IS NOT NULL AND revoked_at < issued_at) OR NOT "
        "((revoked_at IS NULL AND revoked_by IS NULL AND revocation_reason IS NULL) OR "
        "(revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND "
        "length(trim(revocation_reason)) > 0)) LIMIT 1",
        f"SELECT 1 FROM {_GRANT_TABLE} AS issued_grant "
        "JOIN users AS subject ON subject.id = issued_grant.actor_id "
        "JOIN users AS issuer ON issuer.id = issued_grant.issuer_id "
        "LEFT JOIN users AS revoker ON revoker.id = issued_grant.revoked_by "
        "WHERE subject.principal_kind != 'HUMAN' OR issuer.principal_kind != 'HUMAN' "
        "OR (issued_grant.revoked_by IS NOT NULL AND revoker.principal_kind != 'HUMAN') LIMIT 1",
        f"SELECT 1 FROM {_GRANT_AUDIT_TABLE} AS audit "
        "JOIN users AS audit_actor ON audit_actor.id = audit.actor_id "
        "JOIN users AS subject ON subject.id = audit.subject_id "
        "WHERE audit_actor.principal_kind != 'HUMAN' "
        "OR subject.principal_kind != 'HUMAN' LIMIT 1",
        f"SELECT 1 FROM {_GRANT_AUDIT_TABLE} AS audit JOIN {_GRANT_TABLE} AS issued_grant "
        "ON issued_grant.id = audit.grant_id WHERE audit.subject_id != issued_grant.actor_id "
        "OR audit.run_id != issued_grant.run_id OR NOT ((audit.workspace_id = issued_grant.workspace_id) "
        "OR (audit.workspace_id IS NULL AND issued_grant.workspace_id IS NULL)) "
        "OR audit.permission != issued_grant.permission "
        "OR audit.policy_version != 'approval-grant-authority-v1' "
        "OR (audit.event_type = 'ISSUED' AND (audit.actor_id != issued_grant.issuer_id "
        "OR audit.occurred_at != issued_grant.issued_at OR audit.reason_hash IS NOT NULL)) "
        "OR (audit.event_type = 'REVOKED' AND (issued_grant.revoked_at IS NULL "
        "OR issued_grant.revoked_by IS NULL OR audit.actor_id != issued_grant.revoked_by "
        "OR audit.occurred_at != issued_grant.revoked_at OR audit.reason_hash IS NULL)) LIMIT 1",
        f"SELECT 1 FROM {_GRANT_TABLE} AS issued_grant LEFT JOIN {_GRANT_AUDIT_TABLE} AS issued "
        "ON issued.grant_id = issued_grant.id AND issued.event_type = 'ISSUED' "
        f"LEFT JOIN {_GRANT_AUDIT_TABLE} AS revoked ON revoked.grant_id = issued_grant.id "
        "AND revoked.event_type = 'REVOKED' WHERE issued.id IS NULL "
        "OR (issued_grant.revoked_at IS NULL AND revoked.id IS NOT NULL) "
        "OR (issued_grant.revoked_at IS NOT NULL AND revoked.id IS NULL) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} AS request "
        "JOIN ai_research_candidates AS candidate ON candidate.id = request.candidate_id "
        "JOIN ai_research_runs AS run ON run.id = request.run_id "
        "JOIN ai_research_evidence_packages AS package "
        "ON package.id = request.evidence_package_id "
        f"JOIN {_PROFILE_TABLE} AS profile ON profile.profile_id = request.capability_profile_id "
        "AND profile.version = request.capability_profile_version "
        "WHERE request.run_id IS NOT NULL AND (candidate.run_id != request.run_id "
        "OR package.run_id != request.run_id "
        "OR package.candidate_id != request.candidate_id "
        "OR package.manifest_hash != request.evidence_package_hash "
        "OR package.gate_input_evidence_hash != request.gate_input_evidence_hash "
        "OR profile.actor_mode != request.approval_mode "
        "OR profile.evidence_hash != request.capability_evidence_hash "
        "OR NOT ((request.workspace_id = run.workspace_id) OR "
        "(request.workspace_id IS NULL AND run.workspace_id IS NULL)) "
        "OR length(request.policy_material_hash) != 64 "
        "OR length(request.capability_evidence_hash) != 64 "
        "OR length(request.request_material_hash) != 64) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS decision "
        f"JOIN {_REQUEST_TABLE} AS request ON request.id = decision.approval_request_id "
        f"JOIN {_GRANT_TABLE} AS issued_grant ON issued_grant.id = decision.grant_id "
        "JOIN ai_research_evidence_packages AS package "
        "ON package.id = decision.evidence_package_id "
        f"JOIN {_PROFILE_TABLE} AS profile ON profile.profile_id = decision.capability_profile_id "
        "AND profile.version = decision.capability_profile_version "
        "WHERE decision.approval_request_id IS NOT NULL AND ("
        "decision.candidate_id != request.candidate_id "
        "OR decision.run_id != request.run_id "
        "OR decision.evidence_package_id != request.evidence_package_id "
        "OR decision.policy_version != request.policy_version "
        "OR decision.policy_material_hash != request.policy_material_hash "
        "OR decision.approval_mode != request.approval_mode "
        "OR decision.capability_profile_id != request.capability_profile_id "
        "OR decision.capability_profile_version != request.capability_profile_version "
        "OR decision.capability_evidence_hash != request.capability_evidence_hash "
        "OR decision.gate_input_evidence_hash != request.gate_input_evidence_hash "
        "OR decision.evidence_package_hash != request.evidence_package_hash "
        "OR decision.requested_at != request.requested_at "
        "OR decision.eligible_at != request.eligible_at "
        "OR decision.expires_at != request.expires_at "
        "OR issued_grant.actor_id != decision.actor_id OR issued_grant.run_id != decision.run_id "
        "OR issued_grant.grant_hash != decision.grant_hash "
        "OR package.candidate_id != decision.candidate_id "
        "OR package.run_id != decision.run_id "
        "OR profile.actor_mode != decision.approval_mode "
        "OR profile.evidence_hash != decision.capability_evidence_hash "
        "OR NOT ((decision.workspace_id = request.workspace_id) OR "
        "(decision.workspace_id IS NULL AND request.workspace_id IS NULL)) "
        "OR NOT ((decision.workspace_id = issued_grant.workspace_id) OR "
        "(decision.workspace_id IS NULL AND issued_grant.workspace_id IS NULL))) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS decision "
        f"JOIN {_GRANT_TABLE} AS issued_grant ON issued_grant.id = decision.grant_id "
        "WHERE decision.approval_request_id IS NOT NULL AND ("
        "issued_grant.issued_at > decision.decided_at "
        "OR issued_grant.expires_at <= decision.decided_at "
        "OR (issued_grant.revoked_at IS NOT NULL AND issued_grant.revoked_at <= decision.decided_at)) "
        "LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS decision "
        "JOIN users AS decision_actor ON decision_actor.id = decision.actor_id "
        "WHERE decision.decision_material_hash IS NOT NULL "
        "AND decision_actor.principal_kind != 'HUMAN' LIMIT 1",
        f"SELECT 1 FROM {_DENIAL_FENCE_TABLE} AS fence "
        f"JOIN {_DECISION_TABLE} AS decision ON decision.id = fence.decision_id "
        "JOIN ai_research_evidence_packages AS package "
        "ON package.id = fence.evidence_package_id WHERE "
        "fence.candidate_id != decision.candidate_id OR fence.run_id != decision.run_id "
        "OR fence.evidence_package_id != decision.evidence_package_id "
        "OR fence.decision != decision.decision "
        "OR fence.approval_policy_version != decision.policy_version "
        "OR fence.approval_policy_material_hash != decision.policy_material_hash "
        "OR fence.gate_input_evidence_hash != decision.gate_input_evidence_hash "
        "OR fence.evidence_package_hash != decision.evidence_package_hash "
        "OR fence.approval_binding_hash != package.approval_binding_hash LIMIT 1",
    )


def _orphan_queries() -> tuple[str, ...]:
    return (
        f"SELECT 1 FROM {_REQUEST_TABLE} AS item WHERE NOT EXISTS "
        "(SELECT 1 FROM ai_research_candidates AS parent "
        "WHERE parent.id = item.candidate_id) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS item WHERE NOT EXISTS "
        "(SELECT 1 FROM ai_research_candidates AS parent "
        "WHERE parent.id = item.candidate_id) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} AS item WHERE item.run_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM ai_research_runs AS parent WHERE parent.id = item.run_id) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} AS item WHERE item.evidence_package_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM ai_research_evidence_packages AS parent "
        "WHERE parent.id = item.evidence_package_id) LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} AS request WHERE request.run_id IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM {_PROFILE_TABLE} AS profile "
        "WHERE profile.profile_id = request.capability_profile_id "
        "AND profile.version = request.capability_profile_version) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS item WHERE item.run_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM ai_research_runs AS parent WHERE parent.id = item.run_id) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS item WHERE item.approval_request_id IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM {_REQUEST_TABLE} AS parent "
        "WHERE parent.id = item.approval_request_id) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS item WHERE item.evidence_package_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM ai_research_evidence_packages AS parent "
        "WHERE parent.id = item.evidence_package_id) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS item WHERE item.grant_id IS NOT NULL AND NOT EXISTS "
        f"(SELECT 1 FROM {_GRANT_TABLE} AS parent WHERE parent.id = item.grant_id) LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} AS decision "
        "WHERE decision.approval_request_id IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM {_PROFILE_TABLE} AS profile "
        "WHERE profile.profile_id = decision.capability_profile_id "
        "AND profile.version = decision.capability_profile_version) LIMIT 1",
        f"SELECT 1 FROM {_GRANT_TABLE} AS item WHERE NOT EXISTS "
        "(SELECT 1 FROM users AS parent WHERE parent.id = item.actor_id) OR NOT EXISTS "
        "(SELECT 1 FROM users AS parent WHERE parent.id = item.issuer_id) OR NOT EXISTS "
        "(SELECT 1 FROM ai_research_runs AS parent WHERE parent.id = item.run_id) OR "
        "(item.revoked_by IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM users AS parent WHERE parent.id = item.revoked_by)) LIMIT 1",
        f"SELECT 1 FROM {_GRANT_AUDIT_TABLE} AS item WHERE NOT EXISTS "
        f"(SELECT 1 FROM {_GRANT_TABLE} AS parent WHERE parent.id = item.grant_id) "
        "OR NOT EXISTS (SELECT 1 FROM users AS parent WHERE parent.id = item.actor_id) "
        "OR NOT EXISTS (SELECT 1 FROM users AS parent WHERE parent.id = item.subject_id) "
        "OR NOT EXISTS (SELECT 1 FROM ai_research_runs AS parent "
        "WHERE parent.id = item.run_id) LIMIT 1",
        f"SELECT 1 FROM {_DENIAL_FENCE_TABLE} AS fence WHERE NOT EXISTS "
        "(SELECT 1 FROM ai_research_candidates AS parent "
        "WHERE parent.id = fence.candidate_id) OR NOT EXISTS "
        "(SELECT 1 FROM ai_research_runs AS parent WHERE parent.id = fence.run_id) "
        "OR NOT EXISTS (SELECT 1 FROM ai_research_evidence_packages AS parent "
        "WHERE parent.id = fence.evidence_package_id) OR NOT EXISTS "
        f"(SELECT 1 FROM {_DECISION_TABLE} AS parent "
        "WHERE parent.id = fence.decision_id) LIMIT 1",
    )


def _create_guards(bind: Any) -> None:
    _create_deny_guard(
        bind,
        table_name=_PROFILE_TABLE,
        trigger_name=_PROFILE_UPDATE_TRIGGER,
        function_name=_PROFILE_UPDATE_FUNCTION,
        operation="UPDATE",
        error="APPROVAL_CAPABILITY_PROFILE_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_PROFILE_TABLE,
        trigger_name=_PROFILE_DELETE_TRIGGER,
        function_name=_PROFILE_DELETE_FUNCTION,
        operation="DELETE",
        error="APPROVAL_CAPABILITY_PROFILE_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_GRANT_AUDIT_TABLE,
        trigger_name=_GRANT_AUDIT_UPDATE_TRIGGER,
        function_name=_GRANT_AUDIT_UPDATE_FUNCTION,
        operation="UPDATE",
        error="APPROVAL_GRANT_AUDIT_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_GRANT_AUDIT_TABLE,
        trigger_name=_GRANT_AUDIT_DELETE_TRIGGER,
        function_name=_GRANT_AUDIT_DELETE_FUNCTION,
        operation="DELETE",
        error="APPROVAL_GRANT_AUDIT_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_DENIAL_FENCE_TABLE,
        trigger_name=_DENIAL_FENCE_UPDATE_TRIGGER,
        function_name=_DENIAL_FENCE_UPDATE_FUNCTION,
        operation="UPDATE",
        error="APPROVAL_DENIAL_FENCE_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_DENIAL_FENCE_TABLE,
        trigger_name=_DENIAL_FENCE_DELETE_TRIGGER,
        function_name=_DENIAL_FENCE_DELETE_FUNCTION,
        operation="DELETE",
        error="APPROVAL_DENIAL_FENCE_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_DECISION_TABLE,
        trigger_name=_DECISION_UPDATE_TRIGGER,
        function_name=_DECISION_UPDATE_FUNCTION,
        operation="UPDATE",
        error="APPROVAL_AUTHORITY_IMMUTABLE",
    )
    _create_deny_guard(
        bind,
        table_name=_DECISION_TABLE,
        trigger_name=_DECISION_DELETE_TRIGGER,
        function_name=_DECISION_DELETE_FUNCTION,
        operation="DELETE",
        error="APPROVAL_AUTHORITY_IMMUTABLE",
    )
    _create_update_guard(
        bind,
        table_name=_REQUEST_TABLE,
        trigger_name=_REQUEST_UPDATE_TRIGGER,
        function_name=_REQUEST_UPDATE_FUNCTION,
        predicate=_request_transition_predicate(bind.dialect.name),
        error="APPROVAL_REQUEST_TRANSITION_INVALID",
    )
    _create_deny_guard(
        bind,
        table_name=_REQUEST_TABLE,
        trigger_name=_REQUEST_DELETE_TRIGGER,
        function_name=_REQUEST_DELETE_FUNCTION,
        operation="DELETE",
        error="APPROVAL_AUTHORITY_IMMUTABLE",
    )
    _create_update_guard(
        bind,
        table_name=_GRANT_TABLE,
        trigger_name=_GRANT_UPDATE_TRIGGER,
        function_name=_GRANT_UPDATE_FUNCTION,
        predicate=_grant_revocation_predicate(bind.dialect.name),
        error="APPROVAL_GRANT_MUTATION_INVALID",
    )
    _create_deny_guard(
        bind,
        table_name=_GRANT_TABLE,
        trigger_name=_GRANT_DELETE_TRIGGER,
        function_name=_GRANT_DELETE_FUNCTION,
        operation="DELETE",
        error="APPROVAL_AUTHORITY_IMMUTABLE",
    )


def _create_deny_guard(
    bind: Any,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    operation: str,
    error: str,
) -> None:
    dialect = bind.dialect.name
    expected = _expected_deny_guard(
        dialect,
        table_name=table_name,
        trigger_name=trigger_name,
        function_name=function_name,
        operation=operation,
        error=error,
    )
    trigger_exists, postgresql_function_exists = _prepare_guard_function(
        bind,
        table_name=table_name,
        trigger_name=trigger_name,
        function_name=function_name,
        expected=expected,
    )
    if trigger_exists:
        return
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {table_name} "
                f"BEGIN SELECT RAISE(ABORT, '{error}'); END"
            )
        )
    elif dialect == "postgresql":
        return_value = "OLD" if operation == "DELETE" else "NEW"
        if not postgresql_function_exists:
            op.execute(
                sa.text(
                    f"CREATE FUNCTION {function_name}() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN "
                    f"RAISE EXCEPTION '{error}'; RETURN {return_value}; END; $$"
                )
            )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {table_name} "
                f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
            )
        )
    elif dialect in {"mysql", "mariadb"}:
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {table_name} "
                f"FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{error}'"
            )
        )
    else:
        raise RuntimeError(f"APPROVAL_AUTHORITY_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _create_update_guard(
    bind: Any,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    predicate: str,
    error: str,
) -> None:
    dialect = bind.dialect.name
    expected = _expected_update_guard(
        dialect,
        table_name=table_name,
        trigger_name=trigger_name,
        function_name=function_name,
        predicate=predicate,
        error=error,
    )
    trigger_exists, postgresql_function_exists = _prepare_guard_function(
        bind,
        table_name=table_name,
        trigger_name=trigger_name,
        function_name=function_name,
        expected=expected,
    )
    if trigger_exists:
        return
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE UPDATE ON {table_name} "
                f"WHEN NOT ({predicate}) BEGIN SELECT RAISE(ABORT, '{error}'); END"
            )
        )
    elif dialect == "postgresql":
        if not postgresql_function_exists:
            op.execute(
                sa.text(
                    f"CREATE FUNCTION {function_name}() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN "
                    f"IF {predicate} THEN RETURN NEW; END IF; "
                    f"RAISE EXCEPTION '{error}'; RETURN NEW; END; $$"
                )
            )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE UPDATE ON {table_name} "
                f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
            )
        )
    elif dialect in {"mysql", "mariadb"}:
        statement = (
            f"CREATE TRIGGER {trigger_name} BEFORE UPDATE ON {table_name} FOR EACH ROW "
            f"BEGIN IF NOT ({predicate}) THEN SIGNAL SQLSTATE '45000' "
            f"SET MESSAGE_TEXT = '{error}'; END IF; END"
        )
        if context.is_offline_mode():
            output = op.get_context().impl
            output.static_output("DELIMITER $$")
            output.static_output(f"{statement}$$")
            output.static_output("DELIMITER ;")
        else:
            op.execute(sa.text(statement))
    else:
        raise RuntimeError(f"APPROVAL_AUTHORITY_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _request_transition_predicate(dialect: str) -> str:
    comparisons = _immutable_comparisons(dialect, _REQUEST_IMMUTABLE_COLUMNS)
    return (
        "OLD.status = 'PENDING' AND NEW.status IN ('DECIDED', 'EXPIRED', 'REVOKED') "
        "AND OLD.decided_at IS NULL AND NEW.decided_at IS NOT NULL AND " + " AND ".join(comparisons)
    )


def _grant_revocation_predicate(dialect: str) -> str:
    comparisons = _immutable_comparisons(dialect, _GRANT_IMMUTABLE_COLUMNS)
    return (
        "OLD.revoked_at IS NULL AND OLD.revoked_by IS NULL AND "
        "OLD.revocation_reason IS NULL AND NEW.revoked_at IS NOT NULL AND "
        "NEW.revoked_by IS NOT NULL AND length(trim(NEW.revocation_reason)) > 0 AND "
        + " AND ".join(comparisons)
    )


def _immutable_comparisons(dialect: str, columns: Iterable[str]) -> list[str]:
    if dialect == "postgresql":
        return [f"NEW.{name} IS NOT DISTINCT FROM OLD.{name}" for name in columns]
    if dialect in {"mysql", "mariadb"}:
        return [f"NEW.{name} <=> OLD.{name}" for name in columns]
    return [f"NEW.{name} IS OLD.{name}" for name in columns]


def _guard_exists_exact(
    bind: Any,
    table_name: str,
    trigger_name: str,
    expected: str,
    *,
    function_name: str | None = None,
) -> bool:
    if context.is_offline_mode():
        return False
    definition = _trigger_definitions(bind, table_name).get(trigger_name)
    if definition is None:
        return False
    if bind.dialect.name == "postgresql":
        matches = (
            function_name is not None
            and isinstance(definition, _PostgresqlGuardDefinition)
            and _postgresql_guard_matches(
                definition,
                table_name=table_name,
                trigger_name=trigger_name,
                function_name=function_name,
                expected=expected,
            )
        )
    else:
        matches = isinstance(definition, str) and (
            _normalize_guard_sql(definition) == _normalize_guard_sql(expected)
        )
    if not matches:
        raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
    if bind.dialect.name == "postgresql":
        assert function_name is not None
        function = _postgresql_function_definition(
            bind,
            table_name=table_name,
            trigger_name=trigger_name,
            function_name=function_name,
        )
        if function is None or not _postgresql_function_matches(
            function,
            function_name=function_name,
            expected=expected,
            expected_target_count=1,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
    return True


def _prepare_guard_function(
    bind: Any,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    expected: str,
) -> tuple[bool, bool]:
    trigger_exists = _guard_exists_exact(
        bind,
        table_name,
        trigger_name,
        expected,
        function_name=function_name,
    )
    if context.is_offline_mode() or bind.dialect.name != "postgresql":
        return trigger_exists, False
    if trigger_exists:
        return True, True
    function = _postgresql_function_definition(
        bind,
        table_name=table_name,
        trigger_name=trigger_name,
        function_name=function_name,
    )
    if function is None:
        if trigger_exists:
            raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
        return False, False
    expected_target_count = 1 if trigger_exists else 0
    if not _postgresql_function_matches(
        function,
        function_name=function_name,
        expected=expected,
        expected_target_count=expected_target_count,
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
    return trigger_exists, True


def _expected_deny_guard(
    dialect: str,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    operation: str,
    error: str,
) -> str:
    if dialect == "sqlite":
        return (
            f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {table_name} "
            f"BEGIN SELECT RAISE(ABORT, '{error}'); END"
        )
    if dialect == "postgresql":
        event_bits = {"DELETE": 11, "UPDATE": 19}
        return_value = "OLD" if operation == "DELETE" else "NEW"
        return (
            f"{event_bits[operation]} {function_name} BEGIN "
            f"RAISE EXCEPTION '{error}'; RETURN {return_value}; END;"
        )
    if dialect in {"mysql", "mariadb"}:
        return f"BEFORE {operation} SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{error}'"
    raise RuntimeError(f"APPROVAL_AUTHORITY_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _expected_update_guard(
    dialect: str,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    predicate: str,
    error: str,
) -> str:
    if dialect == "sqlite":
        return (
            f"CREATE TRIGGER {trigger_name} BEFORE UPDATE ON {table_name} "
            f"WHEN NOT ({predicate}) BEGIN SELECT RAISE(ABORT, '{error}'); END"
        )
    if dialect == "postgresql":
        return (
            f"19 {function_name} BEGIN IF {predicate} THEN RETURN NEW; END IF; "
            f"RAISE EXCEPTION '{error}'; RETURN NEW; END;"
        )
    if dialect in {"mysql", "mariadb"}:
        return (
            f"BEFORE UPDATE BEGIN IF NOT ({predicate}) THEN SIGNAL SQLSTATE '45000' "
            f"SET MESSAGE_TEXT = '{error}'; END IF; END"
        )
    raise RuntimeError(f"APPROVAL_AUTHORITY_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _trigger_definitions(
    bind: Any,
    table_name: str,
) -> dict[str, str | _PostgresqlGuardDefinition]:
    dialect = bind.dialect.name
    if dialect == "sqlite":
        rows = bind.execute(
            sa.text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'trigger' AND tbl_name = :table_name"
            ),
            {"table_name": table_name},
        )
    elif dialect == "postgresql":
        rows = bind.execute(
            sa.text(
                "SELECT trigger.tgname, trigger.tgtype::text || ' ' || procedure.proname || "
                "' ' || procedure.prosrc, relation_namespace.nspname, current_schema(), "
                "relation.oid, "
                "to_regclass(format('%I.%I', current_schema(), :table_name))::oid, "
                "procedure_namespace.nspname, trigger.tgenabled, trigger.tgqual, "
                "trigger.tgattr::text, pg_get_triggerdef(trigger.oid, true), "
                "pg_get_functiondef(procedure.oid) FROM pg_trigger AS trigger "
                "JOIN pg_class AS relation ON relation.oid = trigger.tgrelid "
                "JOIN pg_namespace AS relation_namespace "
                "ON relation_namespace.oid = relation.relnamespace "
                "JOIN pg_proc AS procedure ON procedure.oid = trigger.tgfoid "
                "JOIN pg_namespace AS procedure_namespace "
                "ON procedure_namespace.oid = procedure.pronamespace "
                "WHERE relation_namespace.nspname = current_schema() "
                "AND relation.relname = :table_name "
                "AND relation.oid = "
                "to_regclass(format('%I.%I', current_schema(), :table_name))::oid "
                "AND NOT trigger.tgisinternal"
            ),
            {"table_name": table_name},
        )
    elif dialect in {"mysql", "mariadb"}:
        rows = bind.execute(
            sa.text(
                "SELECT TRIGGER_NAME, CONCAT(ACTION_TIMING, ' ', EVENT_MANIPULATION, ' ', "
                "ACTION_STATEMENT) FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = :table_name"
            ),
            {"table_name": table_name},
        )
    else:
        raise RuntimeError(f"APPROVAL_AUTHORITY_GUARD_DIALECT_UNSUPPORTED:{dialect}")
    definitions: dict[str, str | _PostgresqlGuardDefinition] = {}
    for row in rows:
        trigger_name = str(row[0])
        if trigger_name in definitions:
            raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
        if dialect == "postgresql":
            if len(row) != 12:
                raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
            definitions[trigger_name] = _PostgresqlGuardDefinition(
                legacy_signature=str(row[1] or ""),
                relation_schema=str(row[2] or ""),
                current_schema=str(row[3] or ""),
                relation_oid=row[4],
                resolved_relation_oid=row[5],
                function_schema=str(row[6] or ""),
                enabled=str(row[7] or ""),
                when_expression=row[8],
                update_columns=row[9],
                trigger_definition=str(row[10] or ""),
                function_definition=str(row[11] or ""),
            )
        else:
            definitions[trigger_name] = str(row[1] or "")
    return definitions


def _postgresql_function_definition(
    bind: Any,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
) -> _PostgresqlFunctionDefinition | None:
    rows = list(
        bind.execute(
            sa.text(
                "SELECT procedure_namespace.nspname, current_schema(), procedure.oid, "
                "to_regprocedure(format('%I.%I()', current_schema(), :function_name))::oid, "
                "pg_get_functiondef(procedure.oid), "
                "(SELECT COUNT(*) FROM pg_trigger AS referencing_trigger "
                "WHERE referencing_trigger.tgfoid = procedure.oid), "
                "(SELECT COUNT(*) FROM pg_trigger AS target_trigger "
                "JOIN pg_class AS target_relation ON target_relation.oid = target_trigger.tgrelid "
                "JOIN pg_namespace AS target_namespace "
                "ON target_namespace.oid = target_relation.relnamespace "
                "WHERE target_trigger.tgfoid = procedure.oid "
                "AND NOT target_trigger.tgisinternal "
                "AND target_trigger.tgname = :trigger_name "
                "AND target_namespace.nspname = current_schema() "
                "AND target_relation.relname = :table_name "
                "AND target_relation.oid = "
                "to_regclass(format('%I.%I', current_schema(), :table_name))::oid) "
                "FROM pg_proc AS procedure "
                "JOIN pg_namespace AS procedure_namespace "
                "ON procedure_namespace.oid = procedure.pronamespace "
                "WHERE procedure_namespace.nspname = current_schema() "
                "AND procedure.proname = :function_name AND procedure.pronargs = 0 "
                "AND procedure.oid = "
                "to_regprocedure(format('%I.%I()', current_schema(), :function_name))::oid"
            ),
            {
                "function_name": function_name,
                "table_name": table_name,
                "trigger_name": trigger_name,
            },
        )
    )
    if not rows:
        return None
    if len(rows) != 1 or len(rows[0]) != 7:
        raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
    row = rows[0]
    return _PostgresqlFunctionDefinition(
        function_schema=str(row[0] or ""),
        current_schema=str(row[1] or ""),
        function_oid=row[2],
        resolved_function_oid=row[3],
        function_definition=str(row[4] or ""),
        referencing_trigger_count=row[5],
        target_trigger_count=row[6],
    )


def _postgresql_guard_matches(
    definition: _PostgresqlGuardDefinition,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    expected: str,
) -> bool:
    expected_parts = re.fullmatch(
        rf"\s*(7|11|19)\s+{re.escape(function_name)}\s+(.+)\s*",
        expected,
        re.DOTALL,
    )
    if expected_parts is None:
        return False
    event = {"7": "INSERT", "11": "DELETE", "19": "UPDATE"}[expected_parts.group(1)]
    if (
        definition.relation_schema != definition.current_schema
        or not definition.current_schema
        or definition.function_schema != definition.current_schema
        or not isinstance(definition.relation_oid, int)
        or isinstance(definition.relation_oid, bool)
        or not isinstance(definition.resolved_relation_oid, int)
        or isinstance(definition.resolved_relation_oid, bool)
        or definition.relation_oid != definition.resolved_relation_oid
        or definition.enabled != "O"
        or definition.when_expression is not None
        or definition.update_columns != ""
        or _normalize_guard_sql(definition.legacy_signature) != _normalize_guard_sql(expected)
    ):
        return False
    return _postgresql_trigger_ddl_matches(
        definition.trigger_definition,
        schema_name=definition.current_schema,
        table_name=table_name,
        trigger_name=trigger_name,
        event=event,
        function_name=function_name,
    ) and _postgresql_function_ddl_matches(
        definition.function_definition,
        schema_name=definition.current_schema,
        function_name=function_name,
        expected_body=expected_parts.group(2),
    )


def _postgresql_function_matches(
    definition: _PostgresqlFunctionDefinition,
    *,
    function_name: str,
    expected: str,
    expected_target_count: int,
) -> bool:
    expected_parts = re.fullmatch(
        rf"\s*(7|11|19)\s+{re.escape(function_name)}\s+(.+)\s*",
        expected,
        re.DOTALL,
    )
    counts = (definition.referencing_trigger_count, definition.target_trigger_count)
    if (
        expected_parts is None
        or definition.function_schema != definition.current_schema
        or not definition.current_schema
        or not isinstance(definition.function_oid, int)
        or isinstance(definition.function_oid, bool)
        or not isinstance(definition.resolved_function_oid, int)
        or isinstance(definition.resolved_function_oid, bool)
        or definition.function_oid != definition.resolved_function_oid
        or any(not isinstance(value, int) or isinstance(value, bool) for value in counts)
        or definition.referencing_trigger_count != expected_target_count
        or definition.target_trigger_count != expected_target_count
    ):
        return False
    return _postgresql_function_ddl_matches(
        definition.function_definition,
        schema_name=definition.current_schema,
        function_name=function_name,
        expected_body=expected_parts.group(2),
    )


def _postgresql_trigger_ddl_matches(
    definition: str,
    *,
    schema_name: str,
    table_name: str,
    trigger_name: str,
    event: str,
    function_name: str,
) -> bool:
    normalized = _normalize_guard_sql(definition).rstrip(";")
    expected = {
        _normalize_guard_sql(
            f"CREATE TRIGGER {trigger_name} BEFORE {event} ON {relation} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        ).rstrip(";")
        for relation in (table_name, f"{schema_name}.{table_name}")
        for function in (function_name, f"{schema_name}.{function_name}")
    }
    return normalized in expected


def _postgresql_function_ddl_matches(
    definition: str,
    *,
    schema_name: str,
    function_name: str,
    expected_body: str,
) -> bool:
    identifier = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
    match = re.fullmatch(
        rf"\s*CREATE\s+OR\s+REPLACE\s+FUNCTION\s+"
        rf"(?P<identity>{identifier}(?:\s*\.\s*{identifier})?)\s*"
        r"\(\s*\)\s+RETURNS\s+TRIGGER\s+LANGUAGE\s+PLPGSQL\s+AS\s+"
        r"(?P<tag>\$[A-Za-z0-9_]*\$)(?P<body>.*)(?P=tag)\s*;?\s*",
        definition,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return False
    identity = re.sub(r'["\s]', "", match.group("identity")).lower()
    return identity in {
        function_name.lower(),
        f"{schema_name}.{function_name}".lower(),
    } and _normalize_guard_sql(match.group("body")) == _normalize_guard_sql(expected_body)


def _normalize_guard_sql(value: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[`\"\[\]]", "", value.upper()))


def _guard_contracts(bind: Any) -> tuple[tuple[str, str, str, str], ...]:
    deny_guards = (
        (
            _PROFILE_TABLE,
            _PROFILE_UPDATE_TRIGGER,
            _PROFILE_UPDATE_FUNCTION,
            "UPDATE",
            "APPROVAL_CAPABILITY_PROFILE_IMMUTABLE",
        ),
        (
            _PROFILE_TABLE,
            _PROFILE_DELETE_TRIGGER,
            _PROFILE_DELETE_FUNCTION,
            "DELETE",
            "APPROVAL_CAPABILITY_PROFILE_IMMUTABLE",
        ),
        (
            _GRANT_AUDIT_TABLE,
            _GRANT_AUDIT_UPDATE_TRIGGER,
            _GRANT_AUDIT_UPDATE_FUNCTION,
            "UPDATE",
            "APPROVAL_GRANT_AUDIT_IMMUTABLE",
        ),
        (
            _GRANT_AUDIT_TABLE,
            _GRANT_AUDIT_DELETE_TRIGGER,
            _GRANT_AUDIT_DELETE_FUNCTION,
            "DELETE",
            "APPROVAL_GRANT_AUDIT_IMMUTABLE",
        ),
        (
            _DENIAL_FENCE_TABLE,
            _DENIAL_FENCE_UPDATE_TRIGGER,
            _DENIAL_FENCE_UPDATE_FUNCTION,
            "UPDATE",
            "APPROVAL_DENIAL_FENCE_IMMUTABLE",
        ),
        (
            _DENIAL_FENCE_TABLE,
            _DENIAL_FENCE_DELETE_TRIGGER,
            _DENIAL_FENCE_DELETE_FUNCTION,
            "DELETE",
            "APPROVAL_DENIAL_FENCE_IMMUTABLE",
        ),
        (
            _DECISION_TABLE,
            _DECISION_UPDATE_TRIGGER,
            _DECISION_UPDATE_FUNCTION,
            "UPDATE",
            "APPROVAL_AUTHORITY_IMMUTABLE",
        ),
        (
            _DECISION_TABLE,
            _DECISION_DELETE_TRIGGER,
            _DECISION_DELETE_FUNCTION,
            "DELETE",
            "APPROVAL_AUTHORITY_IMMUTABLE",
        ),
        (
            _REQUEST_TABLE,
            _REQUEST_DELETE_TRIGGER,
            _REQUEST_DELETE_FUNCTION,
            "DELETE",
            "APPROVAL_AUTHORITY_IMMUTABLE",
        ),
        (
            _GRANT_TABLE,
            _GRANT_DELETE_TRIGGER,
            _GRANT_DELETE_FUNCTION,
            "DELETE",
            "APPROVAL_AUTHORITY_IMMUTABLE",
        ),
    )
    contracts = [
        (
            table_name,
            trigger_name,
            function_name,
            _expected_deny_guard(
                bind.dialect.name,
                table_name=table_name,
                trigger_name=trigger_name,
                function_name=function_name,
                operation=operation,
                error=error,
            ),
        )
        for table_name, trigger_name, function_name, operation, error in deny_guards
    ]
    contracts.extend(
        (
            table_name,
            trigger_name,
            function_name,
            _expected_update_guard(
                bind.dialect.name,
                table_name=table_name,
                trigger_name=trigger_name,
                function_name=function_name,
                predicate=predicate,
                error=error,
            ),
        )
        for table_name, trigger_name, function_name, predicate, error in (
            (
                _REQUEST_TABLE,
                _REQUEST_UPDATE_TRIGGER,
                _REQUEST_UPDATE_FUNCTION,
                _request_transition_predicate(bind.dialect.name),
                "APPROVAL_REQUEST_TRANSITION_INVALID",
            ),
            (
                _GRANT_TABLE,
                _GRANT_UPDATE_TRIGGER,
                _GRANT_UPDATE_FUNCTION,
                _grant_revocation_predicate(bind.dialect.name),
                "APPROVAL_GRANT_MUTATION_INVALID",
            ),
        )
    )
    return tuple(contracts)


def _assert_guards_exact(bind: Any) -> None:
    for table_name, trigger_name, function_name, expected in _guard_contracts(bind):
        trigger_exists, function_exists = _prepare_guard_function(
            bind,
            table_name=table_name,
            trigger_name=trigger_name,
            function_name=function_name,
            expected=expected,
        )
        if not trigger_exists or (bind.dialect.name == "postgresql" and not function_exists):
            raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")


def _drop_guards(bind: Any) -> None:
    for table_name, trigger_name, function_name, expected in _guard_contracts(bind):
        _drop_guard(
            bind,
            table_name=table_name,
            trigger_name=trigger_name,
            function_name=function_name,
            expected=expected,
        )


def _drop_guard(
    bind: Any,
    *,
    table_name: str,
    trigger_name: str,
    function_name: str,
    expected: str,
) -> None:
    dialect = bind.dialect.name
    if context.is_offline_mode():
        if dialect == "postgresql":
            op.execute(sa.text(f"DROP TRIGGER {trigger_name} ON {table_name}"))
            op.execute(sa.text(f"DROP FUNCTION {function_name}()"))
        else:
            op.execute(sa.text(f"DROP TRIGGER {trigger_name}"))
        return
    trigger_exists = _guard_exists_exact(
        bind,
        table_name,
        trigger_name,
        expected,
        function_name=function_name,
    )
    if dialect == "postgresql":
        function = _postgresql_function_definition(
            bind,
            table_name=table_name,
            trigger_name=trigger_name,
            function_name=function_name,
        )
        if function is None:
            if trigger_exists:
                raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
            return
        if not _postgresql_function_matches(
            function,
            function_name=function_name,
            expected=expected,
            expected_target_count=1 if trigger_exists else 0,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_GUARD_CONFLICT")
        if trigger_exists:
            op.execute(sa.text(f"DROP TRIGGER {trigger_name} ON {table_name}"))
        op.execute(sa.text(f"DROP FUNCTION {function_name}()"))
        return
    if trigger_exists:
        op.execute(sa.text(f"DROP TRIGGER {trigger_name}"))


def _assert_downgrade_safe(bind: Any) -> None:
    statements = (
        f"SELECT 1 FROM {_DENIAL_FENCE_TABLE} LIMIT 1",
        f"SELECT 1 FROM {_GRANT_AUDIT_TABLE} LIMIT 1",
        f"SELECT 1 FROM {_GRANT_TABLE} LIMIT 1",
        f"SELECT 1 FROM {_REQUEST_TABLE} WHERE request_material_hash IS NOT NULL LIMIT 1",
        f"SELECT 1 FROM {_DECISION_TABLE} WHERE decision_material_hash IS NOT NULL LIMIT 1",
    )
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED; abort if a query "
            "below returns a row."
        )
        for statement in statements:
            op.execute(sa.text(statement))
        return
    inspector = sa.inspect(bind)
    if inspector.has_table(_DENIAL_FENCE_TABLE) and bind.execute(sa.text(statements[0])).first():
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED")
    if inspector.has_table(_GRANT_AUDIT_TABLE) and bind.execute(sa.text(statements[1])).first():
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED")
    if inspector.has_table(_GRANT_TABLE) and bind.execute(sa.text(statements[2])).first():
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED")
    request_columns = {item["name"] for item in inspector.get_columns(_REQUEST_TABLE)}
    if "request_material_hash" in request_columns and bind.execute(sa.text(statements[3])).first():
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED")
    decision_columns = {item["name"] for item in inspector.get_columns(_DECISION_TABLE)}
    if (
        "decision_material_hash" in decision_columns
        and bind.execute(sa.text(statements[4])).first()
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED")


def _acquire_downgrade_write_fence(bind: Any) -> None:
    """Prevent authority writes between downgrade validation and destructive DDL."""

    if context.is_offline_mode():
        op.execute(
            "-- EXCLUSIVE MAINTENANCE REQUIRED: hold a database write fence from "
            "APPROVAL_AUTHORITY_DOWNGRADE_BLOCKED prechecks through all DROP statements."
        )
        return
    dialect = bind.dialect.name
    fenced_tables = (
        _USER_TABLE,
        _PROFILE_TABLE,
        _GRANT_TABLE,
        _GRANT_AUDIT_TABLE,
        _REQUEST_TABLE,
        _DECISION_TABLE,
        _DENIAL_FENCE_TABLE,
    )
    if dialect == "sqlite":
        for table_name in fenced_tables:
            bind.execute(sa.text(f"UPDATE {table_name} SET id = id WHERE 0"))
        return
    if dialect == "postgresql":
        bind.execute(
            sa.text("LOCK TABLE " + ", ".join(fenced_tables) + " IN ACCESS EXCLUSIVE MODE")
        )
        return
    if dialect in {"mysql", "mariadb"}:
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_REQUIRES_EXCLUSIVE_MAINTENANCE")
    raise RuntimeError(f"APPROVAL_AUTHORITY_DOWNGRADE_DIALECT_UNSUPPORTED:{dialect}")


def _downgrade_offline(bind: Any) -> None:
    _drop_indexes_and_unique(bind)
    op.drop_table(_DENIAL_FENCE_TABLE)
    if bind.dialect.name != "sqlite":
        op.drop_constraint(_DECISION_CANDIDATE_FK, _DECISION_TABLE, type_="foreignkey")
        op.drop_constraint(_REQUEST_CANDIDATE_FK, _REQUEST_TABLE, type_="foreignkey")
        for check_name in reversed(tuple(_DECISION_CHECKS)):
            op.drop_constraint(check_name, _DECISION_TABLE, type_="check")
        for _name, _length, _target, constraint_name in reversed(_DECISION_COLUMNS):
            if constraint_name is not None:
                op.drop_constraint(constraint_name, _DECISION_TABLE, type_="foreignkey")
        for check_name in reversed(_REQUEST_CHECKS):
            op.drop_constraint(check_name, _REQUEST_TABLE, type_="check")
        for _name, _length, _target, constraint_name in reversed(_REQUEST_COLUMNS):
            if constraint_name is not None:
                op.drop_constraint(constraint_name, _REQUEST_TABLE, type_="foreignkey")
    for name, _length, _target, _constraint in reversed(_DECISION_COLUMNS):
        op.drop_column(_DECISION_TABLE, name)
    for name, _length, _target, _constraint in reversed(_REQUEST_COLUMNS):
        op.drop_column(_REQUEST_TABLE, name)
    op.drop_table(_GRANT_AUDIT_TABLE)
    op.drop_table(_GRANT_TABLE)
    _downgrade_principal_kind_offline(bind)


def _downgrade_online(bind: Any) -> None:
    _drop_indexes_and_unique(bind)
    op.drop_table(_DENIAL_FENCE_TABLE)
    if bind.dialect.name == "sqlite":
        _downgrade_sqlite_existing_table(
            _DECISION_TABLE,
            _DECISION_COLUMNS,
            _DECISION_CHECKS,
            _DECISION_CANDIDATE_FK,
        )
        _downgrade_sqlite_existing_table(
            _REQUEST_TABLE,
            _REQUEST_COLUMNS,
            _REQUEST_CHECKS,
            _REQUEST_CANDIDATE_FK,
        )
        op.drop_table(_GRANT_AUDIT_TABLE)
        op.drop_table(_GRANT_TABLE)
        _drop_principal_kind(bind)
        _assert_downgrade_complete(bind)
        return
    _drop_candidate_foreign_keys(bind)
    for check_name in reversed(_DECISION_CHECKS):
        op.drop_constraint(check_name, _DECISION_TABLE, type_="check")
    for check_name in reversed(_REQUEST_CHECKS):
        op.drop_constraint(check_name, _REQUEST_TABLE, type_="check")
    _drop_foreign_keys(bind, _DECISION_TABLE, _DECISION_COLUMNS)
    _drop_foreign_keys(bind, _REQUEST_TABLE, _REQUEST_COLUMNS)
    for name, _length, _target, _constraint in reversed(_DECISION_COLUMNS):
        op.drop_column(_DECISION_TABLE, name)
    for name, _length, _target, _constraint in reversed(_REQUEST_COLUMNS):
        op.drop_column(_REQUEST_TABLE, name)
    op.drop_table(_GRANT_AUDIT_TABLE)
    op.drop_table(_GRANT_TABLE)
    _drop_principal_kind(bind)
    _assert_downgrade_complete(bind)


def _downgrade_principal_kind_offline(bind: Any) -> None:
    if bind.dialect.name == "sqlite":
        op.execute(
            "-- SQLITE BATCH REBUILD REQUIRED: preserve the complete users table and drop "
            f"CONSTRAINT {_PRINCIPAL_KIND_CHECK} plus COLUMN {_PRINCIPAL_KIND_COLUMN}."
        )
        return
    op.drop_constraint(_PRINCIPAL_KIND_CHECK, _USER_TABLE, type_="check")
    op.drop_column(_USER_TABLE, _PRINCIPAL_KIND_COLUMN)


def _drop_principal_kind(bind: Any) -> None:
    """Drop only the freshly revalidated, dependency-free principal contract."""

    _assert_principal_kind_exact(bind)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_USER_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(_PRINCIPAL_KIND_CHECK, type_="check")
            batch_op.drop_column(_PRINCIPAL_KIND_COLUMN)
        return
    op.drop_constraint(_PRINCIPAL_KIND_CHECK, _USER_TABLE, type_="check")
    op.drop_column(_USER_TABLE, _PRINCIPAL_KIND_COLUMN)


def _downgrade_sqlite_existing_table(
    table_name: str,
    specs: tuple[tuple[str, int, str | None, str | None], ...],
    checks: dict[str, str],
    candidate_constraint: str,
) -> None:
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        batch_op.drop_constraint(candidate_constraint, type_="foreignkey")
        for check_name in reversed(tuple(checks)):
            batch_op.drop_constraint(check_name, type_="check")
        for _name, _length, _target, constraint_name in reversed(specs):
            if constraint_name is not None:
                batch_op.drop_constraint(constraint_name, type_="foreignkey")
        for name, _length, _target, _constraint in reversed(specs):
            batch_op.drop_column(name)


def _assert_downgrade_complete(bind: Any) -> None:
    inspector = sa.inspect(bind)
    if any(
        inspector.has_table(table_name)
        for table_name in (_GRANT_TABLE, _GRANT_AUDIT_TABLE, _DENIAL_FENCE_TABLE)
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_INCOMPLETE")
    for table_name, specs in (
        (_REQUEST_TABLE, _REQUEST_COLUMNS),
        (_DECISION_TABLE, _DECISION_COLUMNS),
    ):
        columns = {str(item["name"]) for item in inspector.get_columns(table_name)}
        if any(name in columns for name, _length, _target, _constraint in specs):
            raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_INCOMPLETE")
        if any(
            tuple(item.get("constrained_columns") or ()) == ("candidate_id",)
            for item in _observed_foreign_keys(bind, table_name)
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_INCOMPLETE")
    if any(
        trigger_name in _trigger_definitions(bind, table_name)
        for table_name, trigger_name, _function_name, _expected in _guard_contracts(bind)
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_INCOMPLETE")
    user_columns = {str(item["name"]) for item in inspector.get_columns(_USER_TABLE)}
    if _PRINCIPAL_KIND_COLUMN in user_columns:
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_INCOMPLETE")
    if any(
        _sql_mentions_identifier(str(item.get("sqltext") or ""), _PRINCIPAL_KIND_COLUMN)
        for item in inspector.get_check_constraints(_USER_TABLE)
    ):
        raise RuntimeError("APPROVAL_AUTHORITY_DOWNGRADE_INCOMPLETE")


def _drop_indexes_and_unique(bind: Any) -> None:
    for table_name, name in reversed(tuple(_INDEX_SPECS)):
        columns, unique = _INDEX_SPECS[(table_name, name)]
        if not context.is_offline_mode():
            _assert_index_exact(
                bind,
                table_name=table_name,
                name=name,
                columns=columns,
                unique=unique,
            )
        op.drop_index(name, table_name=table_name)
    if context.is_offline_mode():
        if bind.dialect.name == "sqlite":
            op.drop_index(_DECISION_REQUEST_UNIQUE, table_name=_DECISION_TABLE)
        else:
            op.drop_constraint(
                _DECISION_REQUEST_UNIQUE,
                _DECISION_TABLE,
                type_="unique",
            )
        return
    _assert_decision_request_unique_exact(bind)
    if bind.dialect.name == "sqlite":
        op.drop_index(_DECISION_REQUEST_UNIQUE, table_name=_DECISION_TABLE)
    else:
        op.drop_constraint(_DECISION_REQUEST_UNIQUE, _DECISION_TABLE, type_="unique")


def _drop_foreign_keys(
    bind: Any,
    table_name: str,
    specs: tuple[tuple[str, int, str | None, str | None], ...],
) -> None:
    observed = _observed_foreign_keys(bind, table_name)
    for name, _length, _target, expected_name in reversed(specs):
        if expected_name is None:
            continue
        matches = [
            item for item in observed if tuple(item.get("constrained_columns") or ()) == (name,)
        ]
        target = next(spec_target for spec_name, _l, spec_target, _c in specs if spec_name == name)
        if (
            len(matches) != 1
            or target is None
            or not _foreign_key_matches(
                matches[0],
                target,
                expected_name=expected_name,
            )
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        op.drop_constraint(expected_name, table_name, type_="foreignkey")


def _drop_candidate_foreign_keys(bind: Any) -> None:
    for table_name, expected_name in (
        (_DECISION_TABLE, _DECISION_CANDIDATE_FK),
        (_REQUEST_TABLE, _REQUEST_CANDIDATE_FK),
    ):
        matches = [
            item
            for item in _observed_foreign_keys(bind, table_name)
            if tuple(item.get("constrained_columns") or ()) == ("candidate_id",)
        ]
        if not matches:
            continue
        if len(matches) != 1 or not _foreign_key_matches(
            matches[0],
            "ai_research_candidates",
            expected_name=expected_name,
        ):
            raise RuntimeError("APPROVAL_AUTHORITY_SCHEMA_CONFLICT")
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name, recreate="always") as batch_op:
                batch_op.drop_constraint(expected_name, type_="foreignkey")
        else:
            op.drop_constraint(expected_name, table_name, type_="foreignkey")


def _sql_matches(observed: str, expected: str) -> bool:
    return _normalize_sql(observed) == _normalize_sql(expected)


def _normalize_sql(value: str) -> tuple[Any, ...]:
    """Normalize safe reflection trivia without changing SQL literal contents."""

    # MySQL 9 prefixes every reflected string literal with a charset
    # introducer (``_utf8mb4'ACTIVE'``).  The introducer is storage trivia,
    # not semantics; strip it before tokenizing so the literal comparison
    # stays exact for both dialects.
    source = re.sub(r"_[A-Za-z0-9]+'", "'", value.strip())
    tokens = _tokenize_sql(source)
    if tokens is None:
        return ("__INVALID_SQL__", source)
    tokens = _strip_known_postgresql_casts(tokens)
    tokens = _remove_scalar_parentheses(tokens)
    tokens = _rewrite_postgresql_any(tokens)
    try:
        expression, position = _parse_boolean_or(tokens, 0)
    except ValueError:
        return ("__INVALID_SQL__", source)
    if position != len(tokens):
        return ("__INVALID_SQL__", source)
    return expression


def _tokenize_sql(value: str) -> list[str] | None:
    """Tokenize CHECK SQL while distinguishing literals from quoted identifiers."""

    tokens: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character.isspace():
            index += 1
            continue
        if character == "'":
            end = index + 1
            while end < len(value):
                if value[end] != "'":
                    end += 1
                    continue
                if end + 1 < len(value) and value[end + 1] == "'":
                    end += 2
                    continue
                break
            if end >= len(value):
                return None
            tokens.append(f"LITERAL:{value[index : end + 1]}")
            index = end + 1
            continue
        if character in {'"', "`"}:
            delimiter = character
            end = index + 1
            identifier: list[str] = []
            while end < len(value):
                if value[end] != delimiter:
                    identifier.append(value[end])
                    end += 1
                    continue
                if end + 1 < len(value) and value[end + 1] == delimiter:
                    identifier.append(delimiter)
                    end += 2
                    continue
                break
            if end >= len(value) or not identifier:
                return None
            tokens.append(f"QIDENT:{''.join(identifier).upper()}")
            index = end + 1
            continue
        if character == "[":
            previous_word = _sql_word(tokens[-1]) if tokens else None
            if (index + 1 < len(value) and value[index + 1] == "]") or previous_word == "ARRAY":
                tokens.append("[")
                index += 1
                continue
            end = value.find("]", index + 1)
            if end < 0 or end == index + 1:
                return None
            tokens.append(f"QIDENT:{value[index + 1 : end].upper()}")
            index = end + 1
            continue
        if character in "(),].":
            tokens.append(character)
            index += 1
            continue
        if character == ";" and not value[index + 1 :].strip():
            index = len(value)
            continue
        operator = next(
            (
                candidate
                for candidate in ("::", ">=", "<=", "<>", "!=", "=", ">", "<")
                if value.startswith(candidate, index)
            ),
            None,
        )
        if operator is not None:
            tokens.append("<>" if operator == "!=" else operator)
            index += len(operator)
            continue
        word = re.match(r"[A-Za-z_][A-Za-z0-9_$]*", value[index:])
        if word is not None:
            tokens.append(f"IDENT:{word.group(0).upper()}")
            index += len(word.group(0))
            continue
        number = re.match(r"[0-9]+(?:\.[0-9]+)?", value[index:])
        if number is not None:
            tokens.append(f"NUMBER:{number.group(0)}")
            index += len(number.group(0))
            continue
        return None
    return tokens


def _sql_word(token: str) -> str | None:
    if token.startswith("IDENT:"):
        return token.removeprefix("IDENT:")
    return None


def _strip_known_postgresql_casts(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    position = 0
    while position < len(tokens):
        if tokens[position] != "::":
            normalized.append(tokens[position])
            position += 1
            continue
        end = _known_postgresql_cast_end(tokens, position + 1)
        if end is None:
            normalized.append(tokens[position])
            position += 1
        else:
            position = end
    return normalized


def _known_postgresql_cast_end(tokens: list[str], position: int) -> int | None:
    if position >= len(tokens):
        return None
    word = _sql_word(tokens[position])
    if word in {"TEXT", "VARCHAR"}:
        end = position + 1
    elif (
        word == "CHARACTER"
        and position + 1 < len(tokens)
        and _sql_word(tokens[position + 1]) == "VARYING"
    ):
        end = position + 2
    else:
        return None
    if end < len(tokens) and tokens[end] == "(":
        return None
    if end + 1 < len(tokens) and tokens[end : end + 2] == ["[", "]"]:
        end += 2
    return end


def _remove_scalar_parentheses(tokens: list[str]) -> list[str]:
    normalized = list(tokens)
    changed = True
    while changed:
        changed = False
        output: list[str] = []
        position = 0
        while position < len(normalized):
            if (
                position + 2 < len(normalized)
                and normalized[position] == "("
                and normalized[position + 2] == ")"
                and normalized[position + 1].startswith(
                    ("IDENT:", "QIDENT:", "LITERAL:", "NUMBER:")
                )
            ):
                output.append(normalized[position + 1])
                position += 3
                changed = True
                continue
            output.append(normalized[position])
            position += 1
        normalized = output
    return normalized


def _rewrite_postgresql_any(tokens: list[str]) -> list[str]:
    normalized = list(tokens)
    position = 0
    while position + 2 < len(normalized):
        if (
            normalized[position] != "="
            or _sql_word(normalized[position + 1]) != "ANY"
            or normalized[position + 2] != "("
        ):
            position += 1
            continue
        close = _matching_token_parenthesis(normalized, position + 2)
        if close is None:
            return normalized
        contents = normalized[position + 3 : close]
        while _tokens_have_single_outer_parenthesis_pair(contents):
            contents = contents[1:-1]
        if (
            len(contents) < 3
            or _sql_word(contents[0]) != "ARRAY"
            or contents[1] != "["
            or contents[-1] != "]"
        ):
            position = close + 1
            continue
        normalized[position : close + 1] = ["IDENT:IN", "(", *contents[2:-1], ")"]
        position += 1
    return normalized


def _matching_token_parenthesis(tokens: list[str], start: int) -> int | None:
    depth = 0
    for position in range(start, len(tokens)):
        if tokens[position] == "(":
            depth += 1
        elif tokens[position] == ")":
            depth -= 1
            if depth == 0:
                return position
            if depth < 0:
                return None
    return None


def _tokens_have_single_outer_parenthesis_pair(tokens: list[str]) -> bool:
    if len(tokens) < 2 or tokens[0] != "(" or tokens[-1] != ")":
        return False
    return _matching_token_parenthesis(tokens, 0) == len(tokens) - 1


def _parse_boolean_or(tokens: list[str], position: int) -> tuple[tuple[Any, ...], int]:
    left, position = _parse_boolean_and(tokens, position)
    terms = [left]
    while position < len(tokens) and _sql_word(tokens[position]) == "OR":
        right, position = _parse_boolean_and(tokens, position + 1)
        terms.append(right)
    return _combine_boolean("OR", terms), position


def _parse_boolean_and(tokens: list[str], position: int) -> tuple[tuple[Any, ...], int]:
    left, position = _parse_boolean_not(tokens, position)
    terms = [left]
    while position < len(tokens) and _sql_word(tokens[position]) == "AND":
        right, position = _parse_boolean_not(tokens, position + 1)
        terms.append(right)
    return _combine_boolean("AND", terms), position


def _parse_boolean_not(tokens: list[str], position: int) -> tuple[tuple[Any, ...], int]:
    if position < len(tokens) and _sql_word(tokens[position]) == "NOT":
        operand, next_position = _parse_boolean_not(tokens, position + 1)
        return ("NOT", operand), next_position
    return _parse_boolean_primary(tokens, position)


def _parse_boolean_primary(tokens: list[str], position: int) -> tuple[tuple[Any, ...], int]:
    if position >= len(tokens):
        raise ValueError("missing Boolean operand")
    if tokens[position] == "(":
        expression, next_position = _parse_boolean_or(tokens, position + 1)
        if next_position >= len(tokens) or tokens[next_position] != ")":
            raise ValueError("unbalanced Boolean grouping")
        return expression, next_position + 1
    atom: list[str] = []
    depth = 0
    while position < len(tokens):
        token = tokens[position]
        word = _sql_word(token)
        if depth == 0 and (token == ")" or word in {"AND", "OR"}):
            break
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth < 0:
                break
        atom.append(_canonical_sql_token(token))
        position += 1
    if not atom or depth != 0:
        raise ValueError("invalid Boolean atom")
    return ("ATOM", *atom), position


def _canonical_sql_token(token: str) -> str:
    if token.startswith(("IDENT:", "QIDENT:")):
        return f"ID:{token.split(':', 1)[1]}"
    return token


def _combine_boolean(operator: str, terms: list[tuple[Any, ...]]) -> tuple[Any, ...]:
    if len(terms) == 1:
        return terms[0]
    flattened: list[tuple[Any, ...]] = []
    for term in terms:
        if term and term[0] == operator:
            flattened.extend(term[1:])
        else:
            flattened.append(term)
    return (operator, *flattened)
