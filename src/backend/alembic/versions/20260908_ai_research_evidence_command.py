"""Bind evidence packages to one terminal holdout command graph.

Revision ID: 20260908_ai_research_evidence_command
Revises: 20260907_ai_research_holdout_finalize

The four graph columns stay nullable so historical v1 manifests remain readable.
New v2 writers must populate the complete group; the database rejects partial
bindings.  Schema operations are resumable because MySQL-family DDL can commit
before Alembic records the revision marker.
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "20260908_ai_research_evidence_command"
down_revision = "20260907_ai_research_holdout_finalize"
branch_labels = None
depends_on = None

_TABLE = "ai_research_evidence_packages"
_MUTATION_ERROR = "EVIDENCE_PACKAGE_IMMUTABLE"
_INSERT_TRIGGER = "trg_ai_research_evidence_package_migration_insert_freeze"
_FREEZE_TRIGGER = "trg_ai_research_evidence_package_migration_freeze"
_DELETE_TRIGGER = "trg_ai_research_evidence_package_delete_guard"
_UPDATE_TRIGGER = "trg_ai_research_evidence_package_update_guard"
_INSERT_FUNCTION = "freeze_ai_research_evidence_package_insert"
_FREEZE_FUNCTION = "freeze_ai_research_evidence_package_update"
_DELETE_FUNCTION = "deny_ai_research_evidence_package_delete"
_UPDATE_FUNCTION = "guard_ai_research_evidence_package_update"
_GRAPH_CHECK = "ck_ai_research_evidence_package_command_graph"
_GRAPH_CHECK_SQL = (
    "(command_id IS NULL AND evaluation_id IS NULL AND artifact_binding_id IS NULL AND "
    "terminal_access_audit_id IS NULL) OR (command_id IS NOT NULL AND "
    "evaluation_id IS NOT NULL AND artifact_binding_id IS NOT NULL AND "
    "terminal_access_audit_id IS NOT NULL)"
)
_COLUMNS = {
    "command_id": (
        "ai_research_holdout_evaluation_commands",
        "fk_ai_research_evidence_package_command",
    ),
    "evaluation_id": (
        "ai_research_evaluations",
        "fk_ai_research_evidence_package_evaluation",
    ),
    "artifact_binding_id": (
        "ai_research_holdout_artifact_bindings",
        "fk_ai_research_evidence_package_artifact_binding",
    ),
    "terminal_access_audit_id": (
        "ai_research_holdout_access_audits",
        "fk_ai_research_evidence_package_terminal_audit",
    ),
}
_INDEXES = {
    "ix_ai_research_evidence_package_command_created": (
        ("command_id", "created_at"),
        False,
    ),
    "ix_ai_research_evidence_package_evaluation": (("evaluation_id",), False),
    "ix_ai_research_evidence_package_artifact_binding": (
        ("artifact_binding_id",),
        False,
    ),
    "ix_ai_research_evidence_package_terminal_audit": (
        ("terminal_access_audit_id",),
        False,
    ),
    "uq_ai_research_evidence_package_command": (("command_id",), True),
}
_IMMUTABLE_COLUMNS = (
    "id",
    "user_id",
    "run_id",
    "candidate_id",
    "command_id",
    "evaluation_id",
    "artifact_binding_id",
    "terminal_access_audit_id",
    "promotion_policy_version",
    "gate_input_evidence_hash",
    "manifest",
    "manifest_hash",
    "approval_binding_hash",
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
    """Add a nullable legacy-compatible, all-or-none command authority graph."""

    bind = op.get_bind()
    _create_insert_guard(bind)
    _create_freeze_guard(bind)
    _create_delete_guard(bind)
    if context.is_offline_mode():
        _upgrade_offline(bind)
    else:
        _upgrade_online(bind)
    _create_update_guard(bind)
    _drop_freeze_guard(bind)
    _drop_insert_guard(bind)


def downgrade() -> None:
    """Remove graph metadata only when no evidence package depends on it."""

    bind = op.get_bind()
    _create_insert_guard(bind)
    _create_freeze_guard(bind)
    try:
        _assert_downgrade_safe(bind)
    except Exception:
        _drop_freeze_guard(bind)
        _drop_insert_guard(bind)
        raise
    _drop_guard(bind, _UPDATE_TRIGGER, _UPDATE_FUNCTION)
    if context.is_offline_mode():
        _downgrade_offline(bind)
    else:
        _downgrade_online(bind)
    _drop_guard(bind, _DELETE_TRIGGER, _DELETE_FUNCTION)
    _drop_freeze_guard(bind)
    _drop_insert_guard(bind)


def _upgrade_offline(bind: Any) -> None:
    if bind.dialect.name == "sqlite":
        for column_name in _COLUMNS:
            _add_sqlite_column(column_name)
    else:
        for column_name in _COLUMNS:
            op.add_column(_TABLE, sa.Column(column_name, sa.String(length=36), nullable=True))
    _assert_upgrade_data_clean(bind)
    if bind.dialect.name != "sqlite":
        for column_name, (target_table, constraint_name) in _COLUMNS.items():
            op.create_foreign_key(
                constraint_name,
                _TABLE,
                target_table,
                [column_name],
                ["id"],
                ondelete="RESTRICT",
            )
        op.create_check_constraint(_GRAPH_CHECK, _TABLE, _GRAPH_CHECK_SQL)
    for index_name, (columns, unique) in _INDEXES.items():
        op.create_index(index_name, _TABLE, list(columns), unique=unique)


def _upgrade_online(bind: Any) -> None:
    inspector = sa.inspect(bind)
    observed_columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    present_graph_columns = tuple(name for name in _COLUMNS if name in observed_columns)
    for column_name in present_graph_columns:
        if not _column_contract_matches(observed_columns[column_name]):
            raise RuntimeError("EVIDENCE_COMMAND_GRAPH_COLUMN_CONFLICT")
    missing_graph_columns = tuple(name for name in _COLUMNS if name not in observed_columns)
    if present_graph_columns and missing_graph_columns:
        predicate = " OR ".join(f"{name} IS NOT NULL" for name in present_graph_columns)
        if bind.execute(sa.text(f"SELECT 1 FROM {_TABLE} WHERE {predicate} LIMIT 1")).first():
            raise RuntimeError("EVIDENCE_COMMAND_GRAPH_PARTIAL_DATA")

    for column_name in missing_graph_columns:
        if bind.dialect.name == "sqlite":
            _add_sqlite_column(column_name)
        else:
            op.add_column(_TABLE, sa.Column(column_name, sa.String(length=36), nullable=True))

    _assert_upgrade_data_clean(bind)
    observed_foreign_keys = _observed_foreign_keys(bind, inspector)
    for column_name, (target_table, constraint_name) in _COLUMNS.items():
        matching_column = [
            foreign_key
            for foreign_key in observed_foreign_keys
            if column_name in tuple(foreign_key.get("constrained_columns") or ())
        ]
        if matching_column:
            if len(matching_column) != 1 or not _foreign_key_matches(
                matching_column[0], column_name, target_table
            ):
                raise RuntimeError("EVIDENCE_COMMAND_GRAPH_FOREIGN_KEY_CONFLICT")
            continue
        if any(foreign_key.get("name") == constraint_name for foreign_key in observed_foreign_keys):
            raise RuntimeError("EVIDENCE_COMMAND_GRAPH_FOREIGN_KEY_CONFLICT")
        if column_name in observed_columns and bind.dialect.name == "sqlite":
            raise RuntimeError("EVIDENCE_COMMAND_GRAPH_FOREIGN_KEY_CONFLICT")
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                constraint_name,
                _TABLE,
                target_table,
                [column_name],
                ["id"],
                ondelete="RESTRICT",
            )

    observed_checks = {
        str(check.get("name")): str(check.get("sqltext") or "")
        for check in inspector.get_check_constraints(_TABLE)
        if check.get("name")
    }
    if _GRAPH_CHECK in observed_checks:
        if not _graph_check_matches(observed_checks[_GRAPH_CHECK]):
            raise RuntimeError("EVIDENCE_COMMAND_GRAPH_CHECK_CONFLICT")
    elif "terminal_access_audit_id" in observed_columns and bind.dialect.name == "sqlite":
        raise RuntimeError("EVIDENCE_COMMAND_GRAPH_CHECK_CONFLICT")
    elif bind.dialect.name != "sqlite":
        op.create_check_constraint(_GRAPH_CHECK, _TABLE, _GRAPH_CHECK_SQL)

    observed_indexes = {
        str(index["name"]): index for index in inspector.get_indexes(_TABLE) if index.get("name")
    }
    for index_name, (columns, unique) in _INDEXES.items():
        observed = observed_indexes.get(index_name)
        if observed is not None:
            if not _index_matches(
                observed,
                columns=columns,
                unique=unique,
                dialect_name=bind.dialect.name,
            ):
                raise RuntimeError("EVIDENCE_COMMAND_GRAPH_INDEX_CONFLICT")
            continue
        op.create_index(index_name, _TABLE, list(columns), unique=unique)


def _downgrade_offline(bind: Any) -> None:
    for index_name in reversed(tuple(_INDEXES)):
        op.drop_index(index_name, table_name=_TABLE)
    if bind.dialect.name != "sqlite":
        op.drop_constraint(_GRAPH_CHECK, _TABLE, type_="check")
        for _column_name, (_target_table, constraint_name) in reversed(tuple(_COLUMNS.items())):
            op.drop_constraint(constraint_name, _TABLE, type_="foreignkey")
    for column_name in reversed(tuple(_COLUMNS)):
        op.drop_column(_TABLE, column_name)


def _downgrade_online(bind: Any) -> None:
    inspector = sa.inspect(bind)
    observed_indexes = {
        str(index["name"]): index for index in inspector.get_indexes(_TABLE) if index.get("name")
    }
    for index_name in reversed(tuple(_INDEXES)):
        if index_name in observed_indexes:
            op.drop_index(index_name, table_name=_TABLE)

    if bind.dialect.name != "sqlite":
        observed_checks = {
            str(check.get("name"))
            for check in inspector.get_check_constraints(_TABLE)
            if check.get("name")
        }
        if _GRAPH_CHECK in observed_checks:
            op.drop_constraint(_GRAPH_CHECK, _TABLE, type_="check")

        observed_foreign_keys = inspector.get_foreign_keys(_TABLE)
        for column_name in reversed(tuple(_COLUMNS)):
            for foreign_key in observed_foreign_keys:
                if tuple(foreign_key.get("constrained_columns") or ()) != (column_name,):
                    continue
                constraint_name = foreign_key.get("name")
                if not constraint_name:
                    raise RuntimeError("EVIDENCE_COMMAND_GRAPH_FOREIGN_KEY_CONFLICT")
                op.drop_constraint(str(constraint_name), _TABLE, type_="foreignkey")

    observed_columns = {str(column["name"]) for column in inspector.get_columns(_TABLE)}
    for column_name in reversed(tuple(_COLUMNS)):
        if column_name in observed_columns:
            op.drop_column(_TABLE, column_name)


def _add_sqlite_column(column_name: str) -> None:
    target_table, constraint_name = _COLUMNS[column_name]
    check_sql = ""
    if column_name == "terminal_access_audit_id":
        check_sql = f" CONSTRAINT {_GRAPH_CHECK} CHECK ({_GRAPH_CHECK_SQL})"
    op.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD COLUMN {column_name} VARCHAR(36) "
            f"CONSTRAINT {constraint_name} REFERENCES {target_table}(id) "
            f"ON DELETE RESTRICT{check_sql}"
        )
    )


def _assert_upgrade_data_clean(bind: Any) -> None:
    checks = _upgrade_data_prechecks()
    if context.is_offline_mode():
        for error_code, statement in checks:
            op.execute(
                f"-- MANUAL PRECHECK: {error_code}; abort before applying the remaining "
                "upgrade if this query returns a row."
            )
            op.execute(sa.text(statement))
        return
    for error_code, statement in checks:
        if bind.execute(sa.text(statement)).first() is not None:
            raise RuntimeError(error_code)


def _upgrade_data_prechecks() -> tuple[tuple[str, str], ...]:
    all_null = " AND ".join(f"package.{name} IS NULL" for name in _COLUMNS)
    all_non_null = " AND ".join(f"package.{name} IS NOT NULL" for name in _COLUMNS)
    checks: list[tuple[str, str]] = [
        (
            "EVIDENCE_COMMAND_GRAPH_PARTIAL_DATA",
            f"SELECT 1 FROM {_TABLE} AS package "
            f"WHERE NOT (({all_null}) OR ({all_non_null})) LIMIT 1",
        ),
        (
            "EVIDENCE_COMMAND_GRAPH_DUPLICATE_COMMAND",
            f"SELECT package.command_id FROM {_TABLE} AS package "
            "WHERE package.command_id IS NOT NULL GROUP BY package.command_id "
            "HAVING COUNT(*) > 1 LIMIT 1",
        ),
    ]
    for column_name, (target_table, _constraint_name) in _COLUMNS.items():
        error_suffix = column_name.removesuffix("_id").upper()
        checks.append(
            (
                f"EVIDENCE_COMMAND_GRAPH_ORPHAN_{error_suffix}",
                f"SELECT 1 FROM {_TABLE} AS package LEFT JOIN {target_table} AS authority "
                f"ON authority.id = package.{column_name} "
                f"WHERE package.{column_name} IS NOT NULL AND authority.id IS NULL LIMIT 1",
            )
        )
    return tuple(checks)


def _column_contract_matches(column: dict[str, Any]) -> bool:
    column_type = column.get("type")
    return (
        column.get("nullable") is True
        and isinstance(column_type, sa.String)
        and getattr(column_type, "length", None) == 36
    )


def _index_matches(
    index: dict[str, Any],
    *,
    columns: tuple[str, ...],
    unique: bool,
    dialect_name: str,
) -> bool:
    if (
        tuple(index.get("column_names") or ()) != columns
        or bool(index.get("unique", False)) is not unique
    ):
        return False
    reflected_type = index.get("type")
    if reflected_type not in (None, ""):
        if not (
            dialect_name in {"mysql", "mariadb"}
            and unique
            and str(reflected_type).upper() == "UNIQUE"
        ):
            return False
    semantic_metadata = {
        key: value
        for key, value in index.items()
        if key not in {"name", "column_names", "unique", "type"}
    }
    return not _metadata_has_invisible_index(semantic_metadata) and _metadata_is_empty(
        semantic_metadata
    )


def _metadata_has_invisible_index(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        normalized_key = str(key).lower()
        if ("visible" in normalized_key or "visibility" in normalized_key) and item is False:
            return True
        if _metadata_has_invisible_index(item):
            return True
    return False


def _metadata_is_empty(value: Any) -> bool:
    if value is None or value is False or value == "":
        return True
    if isinstance(value, dict):
        return all(_metadata_is_empty(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return all(_metadata_is_empty(item) for item in value)
    return False


def _observed_foreign_keys(bind: Any, inspector: Any) -> list[dict[str, Any]]:
    if bind.dialect.name != "sqlite":
        return list(inspector.get_foreign_keys(_TABLE))

    grouped: dict[int, dict[str, Any]] = {}
    for row in bind.execute(sa.text(f"PRAGMA foreign_key_list({_TABLE})")):
        foreign_key = grouped.setdefault(
            int(row[0]),
            {
                "name": None,
                "constrained_columns": [],
                "referred_table": str(row[2]),
                "referred_columns": [],
                "options": {"ondelete": str(row[6]).upper()},
            },
        )
        foreign_key["constrained_columns"].append(str(row[3]))
        foreign_key["referred_columns"].append(str(row[4]))
    return list(grouped.values())


def _foreign_key_matches(
    foreign_key: dict[str, Any],
    column_name: str,
    target_table: str,
) -> bool:
    options = foreign_key.get("options") or {}
    return (
        tuple(foreign_key.get("constrained_columns") or ()) == (column_name,)
        and foreign_key.get("referred_table") == target_table
        and tuple(foreign_key.get("referred_columns") or ()) == ("id",)
        and str(options.get("ondelete") or "").upper() == "RESTRICT"
    )


def _graph_check_matches(sqltext: str) -> bool:
    tokens = _check_tokens(sqltext)
    if tokens is None:
        return False
    parsed = _CheckExpressionParser(tokens).parse()
    return parsed == frozenset({0, (1 << len(_COLUMNS)) - 1})


def _check_tokens(sqltext: str) -> tuple[str, ...] | None:
    source = re.sub(r"[`\"\[\]]", "", sqltext.upper())
    token_pattern = re.compile(r"\s*(AND\b|OR\b|IS\b|NOT\b|NULL\b|[A-Z_][A-Z0-9_]*|\(|\))")
    tokens: list[str] = []
    position = 0
    while position < len(source):
        match = token_pattern.match(source, position)
        if match is None:
            return None
        tokens.append(match.group(1))
        position = match.end()
    return tuple(tokens)


class _CheckExpressionParser:
    def __init__(self, tokens: tuple[str, ...]) -> None:
        self._tokens = tokens
        self._position = 0

    def parse(self) -> frozenset[int] | None:
        result = self._parse_or()
        if result is None or self._position != len(self._tokens):
            return None
        return result

    def _parse_or(self) -> frozenset[int] | None:
        result = self._parse_and()
        if result is None:
            return None
        while self._accept("OR"):
            right = self._parse_and()
            if right is None:
                return None
            result = result | right
        return result

    def _parse_and(self) -> frozenset[int] | None:
        result = self._parse_term()
        if result is None:
            return None
        while self._accept("AND"):
            right = self._parse_term()
            if right is None:
                return None
            result = result & right
        return result

    def _parse_term(self) -> frozenset[int] | None:
        if self._accept("("):
            result = self._parse_or()
            if result is None or not self._accept(")"):
                return None
            return result
        identifier = self._take()
        column_name = identifier.lower() if identifier is not None else ""
        if column_name not in _COLUMNS or not self._accept("IS"):
            return None
        is_not_null = self._accept("NOT")
        if not self._accept("NULL"):
            return None
        bit = 1 << tuple(_COLUMNS).index(column_name)
        return frozenset(
            mask for mask in range(1 << len(_COLUMNS)) if bool(mask & bit) is not is_not_null
        )

    def _accept(self, token: str) -> bool:
        if self._position >= len(self._tokens) or self._tokens[self._position] != token:
            return False
        self._position += 1
        return True

    def _take(self) -> str | None:
        if self._position >= len(self._tokens):
            return None
        token = self._tokens[self._position]
        self._position += 1
        return token


def _create_freeze_guard(bind: Any) -> None:
    _create_deny_guard(
        bind,
        trigger_name=_FREEZE_TRIGGER,
        function_name=_FREEZE_FUNCTION,
        operation="UPDATE",
    )


def _create_insert_guard(bind: Any) -> None:
    _create_deny_guard(
        bind,
        trigger_name=_INSERT_TRIGGER,
        function_name=_INSERT_FUNCTION,
        operation="INSERT",
    )


def _create_delete_guard(bind: Any) -> None:
    _create_deny_guard(
        bind,
        trigger_name=_DELETE_TRIGGER,
        function_name=_DELETE_FUNCTION,
        operation="DELETE",
    )


def _create_deny_guard(
    bind: Any,
    *,
    trigger_name: str,
    function_name: str,
    operation: str,
) -> None:
    dialect = bind.dialect.name
    expected_definition = _expected_deny_guard_definition(
        dialect,
        trigger_name=trigger_name,
        function_name=function_name,
        operation=operation,
    )
    postgresql_function_exists = False
    if dialect == "postgresql":
        trigger_exists, postgresql_function_exists = _prepare_postgresql_guard_function(
            bind,
            trigger_name=trigger_name,
            function_name=function_name,
            expected_definition=expected_definition,
        )
        if trigger_exists:
            return
    elif _existing_guard_matches(bind, trigger_name, expected_definition):
        return
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {_TABLE} "
                f"BEGIN SELECT RAISE(ABORT, '{_MUTATION_ERROR}'); END"
            )
        )
        return
    if dialect == "postgresql":
        return_value = "OLD" if operation == "DELETE" else "NEW"
        if not postgresql_function_exists:
            op.execute(
                sa.text(
                    f"CREATE FUNCTION {function_name}() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN "
                    f"RAISE EXCEPTION '{_MUTATION_ERROR}'; RETURN {return_value}; END; $$"
                )
            )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {_TABLE} "
                f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
            )
        )
        return
    if dialect in {"mysql", "mariadb"}:
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {_TABLE} "
                "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                f"SET MESSAGE_TEXT = '{_MUTATION_ERROR}'"
            )
        )
        return
    raise RuntimeError(f"EVIDENCE_PACKAGE_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _create_update_guard(bind: Any) -> None:
    dialect = bind.dialect.name
    predicate = _allowed_withdrawal_predicate(dialect)
    expected_definition = _expected_update_guard_definition(dialect, predicate=predicate)
    postgresql_function_exists = False
    if dialect == "postgresql":
        trigger_exists, postgresql_function_exists = _prepare_postgresql_guard_function(
            bind,
            trigger_name=_UPDATE_TRIGGER,
            function_name=_UPDATE_FUNCTION,
            expected_definition=expected_definition,
        )
        if trigger_exists:
            return
    elif _existing_guard_matches(bind, _UPDATE_TRIGGER, expected_definition):
        return
    if dialect == "sqlite":
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_UPDATE_TRIGGER} BEFORE UPDATE ON {_TABLE} "
                f"WHEN NOT ({predicate}) BEGIN "
                f"SELECT RAISE(ABORT, '{_MUTATION_ERROR}'); END"
            )
        )
        return
    if dialect == "postgresql":
        if not postgresql_function_exists:
            op.execute(
                sa.text(
                    f"CREATE FUNCTION {_UPDATE_FUNCTION}() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN "
                    f"IF {predicate} THEN RETURN NEW; END IF; "
                    f"RAISE EXCEPTION '{_MUTATION_ERROR}'; RETURN NEW; END; $$"
                )
            )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {_UPDATE_TRIGGER} BEFORE UPDATE ON {_TABLE} "
                f"FOR EACH ROW EXECUTE FUNCTION {_UPDATE_FUNCTION}()"
            )
        )
        return
    if dialect in {"mysql", "mariadb"}:
        statement = (
            f"CREATE TRIGGER {_UPDATE_TRIGGER} BEFORE UPDATE ON {_TABLE} FOR EACH ROW "
            f"BEGIN IF NOT ({predicate}) THEN SIGNAL SQLSTATE '45000' "
            f"SET MESSAGE_TEXT = '{_MUTATION_ERROR}'; END IF; END"
        )
        if context.is_offline_mode():
            output = op.get_context().impl
            output.static_output("DELIMITER $$")
            output.static_output(f"{statement}$$")
            output.static_output("DELIMITER ;")
        else:
            op.execute(sa.text(statement))
        return
    raise RuntimeError(f"EVIDENCE_PACKAGE_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _allowed_withdrawal_predicate(dialect: str) -> str:
    comparisons: list[str] = []
    for column_name in _IMMUTABLE_COLUMNS:
        if dialect == "postgresql" and column_name == "manifest":
            comparisons.append("NEW.manifest::text = OLD.manifest::text")
        elif dialect == "postgresql":
            comparisons.append(f"NEW.{column_name} IS NOT DISTINCT FROM OLD.{column_name}")
        elif dialect in {"mysql", "mariadb"}:
            comparisons.append(f"NEW.{column_name} <=> OLD.{column_name}")
        else:
            comparisons.append(f"NEW.{column_name} IS OLD.{column_name}")
    return "NEW.status = 'WITHDRAWN' AND OLD.status = 'ACTIVE' AND " + " AND ".join(comparisons)


def _existing_guard_matches(
    bind: Any,
    trigger_name: str,
    expected_definition: str,
) -> bool:
    if context.is_offline_mode():
        return False
    definition = _trigger_definitions(bind).get(trigger_name)
    if definition is None:
        return False
    if bind.dialect.name == "postgresql":
        matches = isinstance(definition, _PostgresqlGuardDefinition) and (
            _postgresql_guard_matches(
                definition,
                trigger_name=trigger_name,
                expected_definition=expected_definition,
            )
        )
    else:
        matches = isinstance(definition, str) and (
            _normalize_guard_definition(definition)
            == _normalize_guard_definition(expected_definition)
        )
    if not matches:
        raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
    return True


def _prepare_postgresql_guard_function(
    bind: Any,
    *,
    trigger_name: str,
    function_name: str,
    expected_definition: str,
) -> tuple[bool, bool]:
    trigger_exists = _existing_guard_matches(bind, trigger_name, expected_definition)
    if context.is_offline_mode():
        return trigger_exists, False
    function_definition = _postgresql_function_definition(
        bind,
        trigger_name=trigger_name,
        function_name=function_name,
    )
    if function_definition is None:
        if trigger_exists:
            raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
        return False, False
    expected_target_count = 1 if trigger_exists else 0
    if not _postgresql_function_matches(
        function_definition,
        function_name=function_name,
        expected_definition=expected_definition,
        expected_target_count=expected_target_count,
    ):
        raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
    return trigger_exists, True


def _postgresql_guard_matches(
    definition: _PostgresqlGuardDefinition,
    *,
    trigger_name: str,
    expected_definition: str,
) -> bool:
    expected = re.fullmatch(
        r"\s*(7|11|19)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)\s*", expected_definition, re.DOTALL
    )
    if expected is None:
        return False
    event = {"7": "INSERT", "11": "DELETE", "19": "UPDATE"}[expected.group(1)]
    function_name = expected.group(2)
    expected_body = expected.group(3)
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
        or _normalize_guard_definition(definition.legacy_signature)
        != _normalize_guard_definition(expected_definition)
    ):
        return False
    return _postgresql_trigger_ddl_matches(
        definition.trigger_definition,
        schema_name=definition.current_schema,
        trigger_name=trigger_name,
        event=event,
        function_name=function_name,
    ) and _postgresql_function_ddl_matches(
        definition.function_definition,
        schema_name=definition.current_schema,
        function_name=function_name,
        expected_body=expected_body,
    )


def _postgresql_function_matches(
    definition: _PostgresqlFunctionDefinition,
    *,
    function_name: str,
    expected_definition: str,
    expected_target_count: int,
) -> bool:
    expected = re.fullmatch(
        r"\s*(7|11|19)\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)\s*",
        expected_definition,
        re.DOTALL,
    )
    if expected is None or expected.group(2) != function_name:
        return False
    counts = (definition.referencing_trigger_count, definition.target_trigger_count)
    if (
        definition.function_schema != definition.current_schema
        or not definition.current_schema
        or not isinstance(definition.function_oid, int)
        or isinstance(definition.function_oid, bool)
        or not isinstance(definition.resolved_function_oid, int)
        or isinstance(definition.resolved_function_oid, bool)
        or definition.function_oid != definition.resolved_function_oid
        or any(not isinstance(value, int) or isinstance(value, bool) for value in counts)
        or any(value < 0 for value in counts)
        or definition.referencing_trigger_count != expected_target_count
        or definition.target_trigger_count != expected_target_count
    ):
        return False
    return _postgresql_function_ddl_matches(
        definition.function_definition,
        schema_name=definition.current_schema,
        function_name=function_name,
        expected_body=expected.group(3),
    )


def _postgresql_trigger_ddl_matches(
    definition: str,
    *,
    schema_name: str,
    trigger_name: str,
    event: str,
    function_name: str,
) -> bool:
    normalized = _normalize_guard_definition(definition).rstrip(";")
    expected_definitions = tuple(
        f"CREATE TRIGGER {trigger_name} BEFORE {event} ON {relation_name} "
        f"FOR EACH ROW EXECUTE FUNCTION {function_identity}()"
        for relation_name in (_TABLE, f"{schema_name}.{_TABLE}")
        for function_identity in (function_name, f"{schema_name}.{function_name}")
    )
    return normalized in {
        _normalize_guard_definition(expected).rstrip(";") for expected in expected_definitions
    }


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
    reflected_identity = re.sub(r'["\s]', "", match.group("identity")).lower()
    allowed_identities = {
        function_name.lower(),
        f"{schema_name}.{function_name}".lower(),
    }
    return reflected_identity in allowed_identities and _normalize_guard_definition(
        match.group("body")
    ) == _normalize_guard_definition(expected_body)


def _expected_deny_guard_definition(
    dialect: str,
    *,
    trigger_name: str,
    function_name: str,
    operation: str,
) -> str:
    if dialect == "sqlite":
        return (
            f"CREATE TRIGGER {trigger_name} BEFORE {operation} ON {_TABLE} "
            f"BEGIN SELECT RAISE(ABORT, '{_MUTATION_ERROR}'); END"
        )
    if dialect == "postgresql":
        event_bits = {"INSERT": 7, "DELETE": 11, "UPDATE": 19}
        return_value = "OLD" if operation == "DELETE" else "NEW"
        return (
            f"{event_bits[operation]} {function_name} BEGIN "
            f"RAISE EXCEPTION '{_MUTATION_ERROR}'; RETURN {return_value}; END;"
        )
    if dialect in {"mysql", "mariadb"}:
        return f"BEFORE {operation} SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '{_MUTATION_ERROR}'"
    raise RuntimeError(f"EVIDENCE_PACKAGE_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _expected_update_guard_definition(dialect: str, *, predicate: str) -> str:
    if dialect == "sqlite":
        return (
            f"CREATE TRIGGER {_UPDATE_TRIGGER} BEFORE UPDATE ON {_TABLE} "
            f"WHEN NOT ({predicate}) BEGIN "
            f"SELECT RAISE(ABORT, '{_MUTATION_ERROR}'); END"
        )
    if dialect == "postgresql":
        return (
            f"19 {_UPDATE_FUNCTION} BEGIN IF {predicate} THEN RETURN NEW; END IF; "
            f"RAISE EXCEPTION '{_MUTATION_ERROR}'; RETURN NEW; END;"
        )
    if dialect in {"mysql", "mariadb"}:
        return (
            f"BEFORE UPDATE BEGIN IF NOT ({predicate}) THEN SIGNAL SQLSTATE '45000' "
            f"SET MESSAGE_TEXT = '{_MUTATION_ERROR}'; END IF; END"
        )
    raise RuntimeError(f"EVIDENCE_PACKAGE_GUARD_DIALECT_UNSUPPORTED:{dialect}")


def _normalize_guard_definition(value: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[`\"\[\]]", "", value.upper()))


def _trigger_definitions(bind: Any) -> dict[str, str | _PostgresqlGuardDefinition]:
    dialect = bind.dialect.name
    if dialect == "sqlite":
        statement = sa.text(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = :table_name"
        )
        rows = bind.execute(statement, {"table_name": _TABLE})
    elif dialect == "postgresql":
        statement = sa.text(
            "SELECT trigger.tgname, trigger.tgtype::text || ' ' || procedure.proname || "
            "' ' || procedure.prosrc, relation_namespace.nspname, current_schema(), "
            "relation.oid, to_regclass(format('%I.%I', current_schema(), :table_name))::oid, "
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
        )
        rows = bind.execute(statement, {"table_name": _TABLE})
    elif dialect in {"mysql", "mariadb"}:
        statement = sa.text(
            "SELECT TRIGGER_NAME, CONCAT(ACTION_TIMING, ' ', EVENT_MANIPULATION, ' ', "
            "ACTION_STATEMENT) FROM information_schema.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = DATABASE() AND EVENT_OBJECT_TABLE = :table_name"
        )
        rows = bind.execute(statement, {"table_name": _TABLE})
    else:
        raise RuntimeError(f"EVIDENCE_PACKAGE_GUARD_DIALECT_UNSUPPORTED:{dialect}")
    definitions: dict[str, str | _PostgresqlGuardDefinition] = {}
    for row in rows:
        trigger_name = str(row[0])
        if trigger_name in definitions:
            raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
        if dialect == "postgresql":
            if len(row) != 12:
                raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
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
    trigger_name: str,
    function_name: str,
) -> _PostgresqlFunctionDefinition | None:
    statement = sa.text(
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
    )
    rows = list(
        bind.execute(
            statement,
            {
                "function_name": function_name,
                "table_name": _TABLE,
                "trigger_name": trigger_name,
            },
        )
    )
    if not rows:
        return None
    if len(rows) != 1 or len(rows[0]) != 7:
        raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
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


def _drop_freeze_guard(bind: Any) -> None:
    _drop_guard(bind, _FREEZE_TRIGGER, _FREEZE_FUNCTION)


def _drop_insert_guard(bind: Any) -> None:
    _drop_guard(bind, _INSERT_TRIGGER, _INSERT_FUNCTION)


def _drop_guard(bind: Any, trigger_name: str, function_name: str) -> None:
    dialect = bind.dialect.name
    if context.is_offline_mode():
        if dialect == "postgresql":
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name} ON {_TABLE}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {function_name}()"))
        else:
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
        return
    expected_definition = _expected_guard_definition_for_identity(
        dialect,
        trigger_name=trigger_name,
        function_name=function_name,
    )
    if dialect == "postgresql":
        definition = _trigger_definitions(bind).get(trigger_name)
        trigger_exists = definition is not None
        if trigger_exists and (
            not isinstance(definition, _PostgresqlGuardDefinition)
            or not _postgresql_guard_matches(
                definition,
                trigger_name=trigger_name,
                expected_definition=expected_definition,
            )
        ):
            raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
        function_definition = _postgresql_function_definition(
            bind,
            trigger_name=trigger_name,
            function_name=function_name,
        )
        if function_definition is None:
            if trigger_exists:
                raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
            return
        expected_target_count = 1 if trigger_exists else 0
        if not _postgresql_function_matches(
            function_definition,
            function_name=function_name,
            expected_definition=expected_definition,
            expected_target_count=expected_target_count,
        ):
            raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")
        if trigger_exists:
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name} ON {_TABLE}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {function_name}()"))
        return
    if _existing_guard_matches(bind, trigger_name, expected_definition):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))


def _expected_guard_definition_for_identity(
    dialect: str,
    *,
    trigger_name: str,
    function_name: str,
) -> str:
    deny_guards = {
        (_INSERT_TRIGGER, _INSERT_FUNCTION): "INSERT",
        (_FREEZE_TRIGGER, _FREEZE_FUNCTION): "UPDATE",
        (_DELETE_TRIGGER, _DELETE_FUNCTION): "DELETE",
    }
    operation = deny_guards.get((trigger_name, function_name))
    if operation is not None:
        return _expected_deny_guard_definition(
            dialect,
            trigger_name=trigger_name,
            function_name=function_name,
            operation=operation,
        )
    if (trigger_name, function_name) == (_UPDATE_TRIGGER, _UPDATE_FUNCTION):
        return _expected_update_guard_definition(
            dialect,
            predicate=_allowed_withdrawal_predicate(dialect),
        )
    raise RuntimeError("EVIDENCE_PACKAGE_GUARD_CONFLICT")


def _assert_downgrade_safe(bind: Any) -> None:
    if context.is_offline_mode():
        column_names = tuple(_COLUMNS)
    else:
        observed = {str(column["name"]) for column in sa.inspect(bind).get_columns(_TABLE)}
        column_names = tuple(name for name in _COLUMNS if name in observed)
    if not column_names:
        return
    predicate = " OR ".join(f"{name} IS NOT NULL" for name in column_names)
    statement = sa.text(f"SELECT 1 FROM {_TABLE} WHERE {predicate} LIMIT 1")
    if context.is_offline_mode():
        op.execute(
            "-- MANUAL PRECHECK: EVIDENCE_COMMAND_GRAPH_DOWNGRADE_BLOCKED; abort before "
            "applying this downgrade if the following query returns a row."
        )
        op.execute(statement)
        return
    if bind.execute(statement).scalar() is not None:
        raise RuntimeError("EVIDENCE_COMMAND_GRAPH_DOWNGRADE_BLOCKED")
