"""Scope sealed research-data bindings to trusted strategy units.

Revision ID: 20260909_market_data_research_binding_consumers
Revises: 20260909_market_data_research_bindings
Create Date: 2026-09-09

The binding receipt is minted before an AI-research workspace creates its
strategy units.  These append-only control/evidence rows establish the first
trusted workspace scope and every permitted unit consumer afterwards.  Generic
workspace API requests cannot write either table.
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import context, op

revision = "20260909_market_data_research_binding_consumers"
down_revision = "20260909_market_data_research_bindings"
branch_labels = None
depends_on = None

_BINDINGS = "md_research_data_bindings"
_SCOPES = "md_research_data_binding_scopes"
_CONSUMERS = "md_research_data_binding_consumers"
_REVOCATIONS = "md_research_data_binding_revocations"
_RECEIPT_TABLES = (_BINDINGS, _SCOPES, _CONSUMERS, _REVOCATIONS)
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_SCHEMA_DRIFT = "MARKET_DATA_RESEARCH_BINDING_SCHEMA_DRIFT"
_DOWNGRADE_BLOCKED = "MARKET_DATA_RESEARCH_BINDING_DOWNGRADE_BLOCKED"
_TABLE_SPECS: dict[str, dict[str, object]] = {
    _SCOPES: {
        "columns": {
            "binding_id": (sa.String(length=36), False),
            "user_id": (sa.String(length=36), False),
            "intent_id": (sa.String(length=128), False),
            "workspace_id": (sa.String(length=36), False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("binding_id",),
        "checks": {"ck_md_rdb_scope_intent_nonempty": "length(intent_id) > 0"},
        "indexes": {"ix_md_rdb_scope_workspace": (("workspace_id", "created_at"), False)},
        "uniques": {},
        "foreign_keys": {
            "fk_md_rdb_scope_binding": (("binding_id",), _BINDINGS, ("id",), "RESTRICT"),
        },
    },
    _CONSUMERS: {
        "columns": {
            "id": (sa.String(length=36), False),
            "binding_id": (sa.String(length=36), False),
            "user_id": (sa.String(length=36), False),
            "intent_id": (sa.String(length=128), False),
            "workspace_id": (sa.String(length=36), False),
            "unit_id": (sa.String(length=36), False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("id",),
        "checks": {"ck_md_rdb_consumer_intent_nonempty": "length(intent_id) > 0"},
        "indexes": {
            "ix_md_rdb_consumer_lookup": (("binding_id", "workspace_id", "intent_id"), False),
        },
        "uniques": {
            "uq_md_rdb_consumer_binding_unit": ("binding_id", "unit_id"),
            "uq_md_rdb_consumer_unit": ("unit_id",),
        },
        "foreign_keys": {
            "fk_md_rdb_consumer_binding": (("binding_id",), _BINDINGS, ("id",), "RESTRICT"),
        },
    },
    _REVOCATIONS: {
        "columns": {
            "id": (sa.String(length=36), False),
            "binding_id": (sa.String(length=36), False),
            "actor_user_id": (sa.String(length=36), True),
            "status": (sa.String(length=16), False),
            "reason_code": (sa.String(length=128), False),
            "revoked_at": (_PIT_DATETIME, False),
            "created_at": (_PIT_DATETIME, False),
        },
        "primary_key": ("id",),
        "checks": {
            "ck_md_rdb_revocation_status": "status IN ('REVOKED', 'INVALID')",
            "ck_md_rdb_revocation_reason_nonempty": "length(reason_code) > 0",
        },
        "indexes": {"ix_md_rdb_revocation_created": (("created_at",), False)},
        "uniques": {"uq_md_rdb_revocation_binding": ("binding_id",)},
        "foreign_keys": {
            "fk_md_rdb_revocation_binding": (("binding_id",), _BINDINGS, ("id",), "RESTRICT"),
        },
    },
}


def _is_offline() -> bool:
    return context.is_offline_mode()


def _normalized_expression(expression: object) -> str:
    """Normalize only dialect renderer differences for named exact checks."""
    normalized = "".join(str(expression).split()).lower().replace('"', "").replace("`", "")
    normalized = re.sub(r"::(?:text|charactervarying|varchar)(?:\[\])?", "", normalized)
    normalized = re.sub(r"_(?:utf8mb4|utf8)(?=')", "", normalized)
    normalized = re.sub(
        r"([a-z_][a-z0-9_]*)=any\(array\[(.*?)\]\)",
        r"\1in(\2)",
        normalized,
    )
    while (
        normalized.startswith("(")
        and normalized.endswith(")")
        and _outer_parentheses_wrap(normalized)
    ):
        normalized = normalized[1:-1]
    return normalized


def _outer_parentheses_wrap(expression: str) -> bool:
    """Return whether one outer pair encloses the complete expression."""
    depth = 0
    for index, character in enumerate(expression):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index == len(expression) - 1
    return False


def _type_signature(
    type_: sa.types.TypeEngine[Any],
    *,
    dialect_name: str,
) -> tuple[type[object], int | None, bool | None, int | None]:
    timezone_mode = (
        bool(getattr(type_, "timezone", False))
        if dialect_name == "postgresql" and isinstance(type_, sa.DateTime)
        else None
    )
    precision = (
        getattr(type_, "fsp", None)
        if dialect_name in {"mysql", "mariadb"} and isinstance(type_, sa.DateTime)
        else None
    )
    return type_._type_affinity, getattr(type_, "length", None), timezone_mode, precision


def _table_errors(
    bind: sa.Connection, table_name: str, spec: dict[str, object]
) -> dict[str, object]:
    inspector = sa.inspect(bind)
    columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    expected_columns = spec["columns"]
    assert isinstance(expected_columns, dict)
    errors: dict[str, object] = {}
    if set(columns) != set(expected_columns):
        errors["columns"] = {
            "missing": sorted(set(expected_columns) - set(columns)),
            "unexpected": sorted(set(columns) - set(expected_columns)),
        }
    invalid_columns: dict[str, object] = {}
    for column_name, definition in expected_columns.items():
        actual = columns.get(column_name)
        if actual is None:
            continue
        expected_type, expected_nullable = definition
        assert isinstance(expected_type, sa.types.TypeEngine)
        expected = _type_signature(
            expected_type.dialect_impl(bind.dialect),
            dialect_name=bind.dialect.name,
        )
        observed = _type_signature(actual["type"], dialect_name=bind.dialect.name)
        if (
            observed != expected
            or bool(actual.get("nullable")) != expected_nullable
            or actual.get("default") is not None
        ):
            invalid_columns[str(column_name)] = {
                "actual": observed,
                "expected": expected,
                "nullable": bool(actual.get("nullable")),
                "expected_nullable": expected_nullable,
                "default": actual.get("default"),
            }
    if invalid_columns:
        errors["invalid_columns"] = invalid_columns

    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    )
    expected_primary_key = spec["primary_key"]
    assert isinstance(expected_primary_key, tuple)
    if primary_key != expected_primary_key:
        errors["primary_key"] = {"actual": primary_key, "expected": expected_primary_key}

    checks = {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in inspector.get_check_constraints(table_name)
        if check.get("name")
    }
    expected_checks_raw = spec["checks"]
    assert isinstance(expected_checks_raw, dict)
    expected_checks = {
        str(name): _normalized_expression(expression)
        for name, expression in expected_checks_raw.items()
    }
    if checks != expected_checks:
        errors["checks"] = {"actual": checks, "expected": expected_checks}

    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            False,
        )
        for index in inspector.get_indexes(table_name)
        if index.get("name") and not bool(index.get("unique", False))
    }
    expected_indexes = spec["indexes"]
    assert isinstance(expected_indexes, dict)
    if indexes != expected_indexes:
        errors["indexes"] = {"actual": indexes, "expected": expected_indexes}

    uniques = {
        str(item["name"]): tuple(str(column) for column in item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table_name)
        if item.get("name")
    }
    expected_uniques = spec["uniques"]
    assert isinstance(expected_uniques, dict)
    if uniques != expected_uniques:
        errors["uniques"] = {"actual": uniques, "expected": expected_uniques}

    foreign_keys = {
        str(item["name"]): (
            tuple(str(column) for column in item.get("constrained_columns") or ()),
            str(item.get("referred_table") or ""),
            tuple(str(column) for column in item.get("referred_columns") or ()),
            str((item.get("options") or {}).get("ondelete") or "").upper(),
        )
        for item in inspector.get_foreign_keys(table_name)
        if item.get("name")
    }
    expected_foreign_keys = spec["foreign_keys"]
    assert isinstance(expected_foreign_keys, dict)
    if foreign_keys != expected_foreign_keys:
        errors["foreign_keys"] = {"actual": foreign_keys, "expected": expected_foreign_keys}
    return errors


def _require_absent_or_exact_tables(bind: sa.Connection) -> bool:
    """Accept all three complete startup-created child tables or create none of them."""
    inspector = sa.inspect(bind)
    presence = {table_name: inspector.has_table(table_name) for table_name in _TABLE_SPECS}
    if not inspector.has_table(_BINDINGS):
        raise RuntimeError(f"{_SCHEMA_DRIFT}: {_BINDINGS} missing for child receipt tables")
    if not any(presence.values()):
        return False
    if not all(presence.values()):
        raise RuntimeError(f"{_SCHEMA_DRIFT}: partial child receipt tables {presence}")
    errors = {
        table_name: table_errors
        for table_name, spec in _TABLE_SPECS.items()
        if (table_errors := _table_errors(bind, table_name, spec))
    }
    if errors:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: {errors}")
    return True


def _create_tables() -> None:
    op.create_table(
        _SCOPES,
        sa.Column(
            "binding_id",
            sa.String(length=36),
            sa.ForeignKey(_BINDINGS + ".id", name="fk_md_rdb_scope_binding", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.CheckConstraint("length(intent_id) > 0", name="ck_md_rdb_scope_intent_nonempty"),
    )
    op.create_index("ix_md_rdb_scope_workspace", _SCOPES, ["workspace_id", "created_at"])

    op.create_table(
        _CONSUMERS,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "binding_id",
            sa.String(length=36),
            sa.ForeignKey(
                _BINDINGS + ".id", name="fk_md_rdb_consumer_binding", ondelete="RESTRICT"
            ),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.UniqueConstraint("binding_id", "unit_id", name="uq_md_rdb_consumer_binding_unit"),
        sa.UniqueConstraint("unit_id", name="uq_md_rdb_consumer_unit"),
        sa.CheckConstraint("length(intent_id) > 0", name="ck_md_rdb_consumer_intent_nonempty"),
    )
    op.create_index(
        "ix_md_rdb_consumer_lookup",
        _CONSUMERS,
        ["binding_id", "workspace_id", "intent_id"],
    )

    op.create_table(
        _REVOCATIONS,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "binding_id",
            sa.String(length=36),
            sa.ForeignKey(
                _BINDINGS + ".id",
                name="fk_md_rdb_revocation_binding",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("revoked_at", _PIT_DATETIME, nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.UniqueConstraint("binding_id", name="uq_md_rdb_revocation_binding"),
        sa.CheckConstraint(
            "status IN ('REVOKED', 'INVALID')",
            name="ck_md_rdb_revocation_status",
        ),
        sa.CheckConstraint("length(reason_code) > 0", name="ck_md_rdb_revocation_reason_nonempty"),
    )
    op.create_index("ix_md_rdb_revocation_created", _REVOCATIONS, ["created_at"])


def upgrade() -> None:
    """Create or validate immutable binding scope, consumer, and revocation receipts."""
    if _is_offline():
        _create_tables()
        return
    if not _require_absent_or_exact_tables(op.get_bind()):
        _create_tables()


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    """Refuse to erase any binding chain evidence while stepping back one revision."""
    inspector = sa.inspect(bind)
    populated_tables: list[str] = []
    for table_name in _RECEIPT_TABLES:
        if not inspector.has_table(table_name):
            continue
        table = sa.Table(table_name, sa.MetaData(), autoload_with=bind)
        first_column = next(iter(table.c), None)
        if first_column is None:
            continue
        if bind.execute(sa.select(first_column).limit(1)).scalar_one_or_none() is not None:
            populated_tables.append(table_name)
    if populated_tables:
        raise RuntimeError(
            f"{_DOWNGRADE_BLOCKED}: immutable binding receipts exist ({', '.join(populated_tables)})"
        )


def downgrade() -> None:
    """Drop only an empty child receipt schema after a verified online check."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove receipt tables empty")
    if not _require_absent_or_exact_tables(op.get_bind()):
        return
    _assert_downgrade_safe(op.get_bind())
    op.drop_index("ix_md_rdb_revocation_created", table_name=_REVOCATIONS)
    op.drop_table(_REVOCATIONS)
    op.drop_index("ix_md_rdb_consumer_lookup", table_name=_CONSUMERS)
    op.drop_table(_CONSUMERS)
    op.drop_index("ix_md_rdb_scope_workspace", table_name=_SCOPES)
    op.drop_table(_SCOPES)
