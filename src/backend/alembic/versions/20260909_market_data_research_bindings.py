"""Persist sealed local-first market-data artifacts for research backtests.

Revision ID: 20260909_market_data_research_bindings
Revises: 20260909_ai_research_market_data_merge
Create Date: 2026-09-09

The table records the server-owned identity, point-in-time evidence, and
controlled artifact digest for a research/backtest input.  The CSV itself is
stored below a configured controlled filesystem root, never in a caller path.
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql

from alembic import context, op

revision = "20260909_market_data_research_bindings"
down_revision = "20260909_ai_research_market_data_merge"
branch_labels = None
depends_on = None

_TABLE = "md_research_data_bindings"
_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_SCHEMA_DRIFT = "MARKET_DATA_RESEARCH_BINDING_SCHEMA_DRIFT"
_DOWNGRADE_BLOCKED = "MARKET_DATA_RESEARCH_BINDING_DOWNGRADE_BLOCKED"
_CHILD_RECEIPT_TABLES = (
    "md_research_data_binding_scopes",
    "md_research_data_binding_consumers",
    "md_research_data_binding_revocations",
)
_COLUMN_SPECS: dict[str, tuple[sa.types.TypeEngine[Any], bool]] = {
    "id": (sa.String(length=36), False),
    "user_id": (sa.String(length=36), False),
    "intent_id": (sa.String(length=128), False),
    "binding_hash": (sa.String(length=_SHA256_LENGTH), False),
    "binding_schema_version": (sa.String(length=64), False),
    "status": (sa.String(length=16), False),
    "artifact_relative_path": (sa.String(length=512), False),
    "artifact_sha256": (sa.String(length=_SHA256_LENGTH), False),
    "artifact_size_bytes": (sa.BigInteger(), False),
    "manifest_json": (sa.JSON(), False),
    "manifest_sha256": (sa.String(length=_SHA256_LENGTH), False),
    "canonical_id": (None, False),
    "instrument_metadata_version": (sa.String(length=128), False),
    "dataset_code": (sa.String(length=255), False),
    "family_id": (sa.String(length=128), False),
    "family_contract_version": (sa.String(length=64), False),
    "data_kind": (sa.String(length=64), False),
    "frequency": (sa.String(length=32), False),
    "source_policy_id": (sa.String(length=128), False),
    "query_fingerprint": (sa.String(length=_SHA256_LENGTH), False),
    "knowledge_cutoff": (_PIT_DATETIME, False),
    "identity_knowledge_cutoff": (_PIT_DATETIME, False),
    "visibility_at": (_PIT_DATETIME, False),
    "visibility_sequence": (sa.BigInteger(), False),
    "identity_visibility_at": (_PIT_DATETIME, False),
    "identity_visibility_sequence": (sa.BigInteger(), False),
    "created_at": (_PIT_DATETIME, False),
}
_CHECKS = {
    "ck_md_rdb_binding_hash_len": f"length(binding_hash) = {_SHA256_LENGTH}",
    "ck_md_rdb_manifest_hash_len": f"length(manifest_sha256) = {_SHA256_LENGTH}",
    "ck_md_rdb_artifact_hash_len": f"length(artifact_sha256) = {_SHA256_LENGTH}",
    "ck_md_rdb_artifact_size_pos": "artifact_size_bytes > 0",
    "ck_md_rdb_status": "status IN ('ACTIVE', 'REVOKED', 'INVALID')",
    "ck_md_rdb_visibility_seq": "visibility_sequence >= 0 AND identity_visibility_sequence >= 0",
}
_INDEXES = {
    "ix_md_rdb_owner_intent": (("user_id", "intent_id", "created_at"), False),
    "ix_md_rdb_status_created": (("status", "created_at"), False),
}
_UNIQUES = {"uq_md_rdb_binding_hash": ("binding_hash",)}
_FOREIGN_KEYS = {
    "fk_md_rdb_user": (("user_id",), "users", ("id",), "RESTRICT"),
}


def _exact_identifier_type(length: int) -> sa.types.TypeEngine[object]:
    """Keep canonical IDs bytewise across SQLite, MySQL, and PostgreSQL."""
    return (
        sa.String(length, collation="BINARY")
        .with_variant(mysql.VARCHAR(length, collation="utf8mb4_bin"), "mysql")
        .with_variant(postgresql.VARCHAR(length, collation="C"), "postgresql")
    )


_COLUMN_SPECS["canonical_id"] = (_exact_identifier_type(512), False)


def _is_offline() -> bool:
    return context.is_offline_mode()


def _normalized_expression(expression: object) -> str:
    """Normalize equivalent PostgreSQL/MySQL reflection for named checks.

    PostgreSQL deparses ``VARCHAR`` membership as ``= ANY (ARRAY[...])`` and
    adds harmless text casts.  MySQL can quote the same identifiers.  Keep the
    exact named predicate while removing only those dialect renderer details,
    so a startup schema made from this project's metadata is accepted without
    allowing a changed predicate to pass unnoticed.
    """
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
    """Compare only physical type attributes reflected by each dialect."""
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


def _table_columns_are_exact(bind: sa.Connection, table_name: str) -> dict[str, object]:
    inspector = sa.inspect(bind)
    columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    errors: dict[str, object] = {}
    if set(columns) != set(_COLUMN_SPECS):
        errors["columns"] = {
            "missing": sorted(set(_COLUMN_SPECS) - set(columns)),
            "unexpected": sorted(set(columns) - set(_COLUMN_SPECS)),
        }
    invalid_columns: dict[str, object] = {}
    for column_name, (expected_type, expected_nullable) in _COLUMN_SPECS.items():
        actual = columns.get(column_name)
        if actual is None:
            continue
        assert expected_type is not None
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
            invalid_columns[column_name] = {
                "actual": observed,
                "expected": expected,
                "nullable": bool(actual.get("nullable")),
                "expected_nullable": expected_nullable,
                "default": actual.get("default"),
            }
    if invalid_columns:
        errors["invalid_columns"] = invalid_columns
    return errors


def _assert_exact_canonical_id_collation(bind: sa.Connection) -> None:
    """Verify the identifier column did not silently inherit a human collation."""
    dialect = bind.dialect.name
    if dialect == "sqlite":
        ddl = bind.execute(
            sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": _TABLE},
        ).scalar_one_or_none()
        matcher = re.compile(
            r'(?is)(?:"canonical_id"|canonical_id)\s+VARCHAR\s*\(\s*512\s*\)'
            r'\s*(?:COLLATE\s+(?:"(?P<quoted>[^"]+)"|(?P<bare>\w+)))?'
        )
        match = matcher.search(ddl) if isinstance(ddl, str) else None
        collation = (match.group("quoted") or match.group("bare")) if match else None
        if match is None or (collation is not None and collation.upper() != "BINARY"):
            raise RuntimeError(f"{_SCHEMA_DRIFT}: canonical_id SQLite collation")
        return
    if dialect in {"mysql", "mariadb"}:
        collation = bind.execute(
            sa.text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name "
                "AND COLUMN_NAME = 'canonical_id'"
            ),
            {"table_name": _TABLE},
        ).scalar_one_or_none()
        if str(collation or "").lower() != "utf8mb4_bin":
            raise RuntimeError(f"{_SCHEMA_DRIFT}: canonical_id MySQL collation")
        return
    if dialect == "postgresql":
        collation = bind.execute(
            sa.text(
                "SELECT coll.collname FROM pg_attribute AS attr "
                "JOIN pg_class AS rel ON rel.oid = attr.attrelid "
                "JOIN pg_namespace AS ns ON ns.oid = rel.relnamespace "
                "JOIN pg_collation AS coll ON coll.oid = attr.attcollation "
                "WHERE ns.nspname = current_schema() AND rel.relname = :table_name "
                "AND attr.attname = 'canonical_id' AND attr.attnum > 0 AND NOT attr.attisdropped"
            ),
            {"table_name": _TABLE},
        ).scalar_one_or_none()
        if collation != "C":
            raise RuntimeError(f"{_SCHEMA_DRIFT}: canonical_id PostgreSQL collation")
        return
    raise RuntimeError(f"{_SCHEMA_DRIFT}: unsupported dialect {dialect}")


def _require_absent_or_exact_table(bind: sa.Connection) -> bool:
    """Accept a complete startup-created table, never a partial same-named table."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        present_children = [
            table_name for table_name in _CHILD_RECEIPT_TABLES if inspector.has_table(table_name)
        ]
        if present_children:
            raise RuntimeError(
                f"{_SCHEMA_DRIFT}: {_TABLE} missing while child receipts exist "
                f"({', '.join(present_children)})"
            )
        return False

    errors = _table_columns_are_exact(bind, _TABLE)
    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ()
    )
    if primary_key != ("id",):
        errors["primary_key"] = primary_key

    checks = {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in inspector.get_check_constraints(_TABLE)
        if check.get("name")
    }
    expected_checks = {name: _normalized_expression(value) for name, value in _CHECKS.items()}
    if checks != expected_checks:
        errors["checks"] = {"actual": checks, "expected": expected_checks}

    indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            False,
        )
        for index in inspector.get_indexes(_TABLE)
        if index.get("name") and not bool(index.get("unique", False))
    }
    if indexes != _INDEXES:
        errors["indexes"] = {"actual": indexes, "expected": _INDEXES}

    uniques = {
        str(item["name"]): tuple(str(column) for column in item.get("column_names") or ())
        for item in inspector.get_unique_constraints(_TABLE)
        if item.get("name")
    }
    if uniques != _UNIQUES:
        errors["uniques"] = {"actual": uniques, "expected": _UNIQUES}

    foreign_keys = {
        str(item["name"]): (
            tuple(str(column) for column in item.get("constrained_columns") or ()),
            str(item.get("referred_table") or ""),
            tuple(str(column) for column in item.get("referred_columns") or ()),
            str((item.get("options") or {}).get("ondelete") or "").upper(),
        )
        for item in inspector.get_foreign_keys(_TABLE)
        if item.get("name")
    }
    if foreign_keys != _FOREIGN_KEYS:
        errors["foreign_keys"] = {"actual": foreign_keys, "expected": _FOREIGN_KEYS}

    if errors:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: {errors}")
    _assert_exact_canonical_id_collation(bind)
    return True


def _create_table() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", name="fk_md_rdb_user", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("binding_hash", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("binding_schema_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("artifact_relative_path", sa.String(length=512), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("artifact_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("canonical_id", _exact_identifier_type(512), nullable=False),
        sa.Column("instrument_metadata_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_code", sa.String(length=255), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("family_contract_version", sa.String(length=64), nullable=False),
        sa.Column("data_kind", sa.String(length=64), nullable=False),
        sa.Column("frequency", sa.String(length=32), nullable=False),
        sa.Column("source_policy_id", sa.String(length=128), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("knowledge_cutoff", _PIT_DATETIME, nullable=False),
        sa.Column("identity_knowledge_cutoff", _PIT_DATETIME, nullable=False),
        sa.Column("visibility_at", _PIT_DATETIME, nullable=False),
        sa.Column("visibility_sequence", sa.BigInteger(), nullable=False),
        sa.Column("identity_visibility_at", _PIT_DATETIME, nullable=False),
        sa.Column("identity_visibility_sequence", sa.BigInteger(), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        *(sa.CheckConstraint(expression, name=name) for name, expression in _CHECKS.items()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("binding_hash", name="uq_md_rdb_binding_hash"),
    )
    for index_name, (columns, _) in _INDEXES.items():
        op.create_index(index_name, _TABLE, list(columns))


def upgrade() -> None:
    """Create or validate durable records for signed research-data artifacts."""
    if _is_offline():
        _create_table()
        return
    if not _require_absent_or_exact_table(op.get_bind()):
        _create_table()


def _assert_downgrade_safe(bind: sa.Connection) -> bool:
    """Reject destructive rollback after any immutable binding receipt exists."""
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        present_children = [
            table_name for table_name in _CHILD_RECEIPT_TABLES if inspector.has_table(table_name)
        ]
        if present_children:
            raise RuntimeError(
                f"{_DOWNGRADE_BLOCKED}: {_TABLE} missing while child binding receipts exist "
                f"({', '.join(present_children)})"
            )
        return False
    _require_absent_or_exact_table(bind)
    present_children = [table for table in _CHILD_RECEIPT_TABLES if inspector.has_table(table)]
    if present_children:
        raise RuntimeError(
            f"{_DOWNGRADE_BLOCKED}: child binding receipts still exist ({', '.join(present_children)})"
        )
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    if bind.execute(sa.select(table.c.id).limit(1)).scalar_one_or_none() is not None:
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: immutable binding receipts exist ({_TABLE})")
    return True


def downgrade() -> None:
    """Remove only an empty binding receipt table after a verified online check."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove receipt tables empty")
    if not _assert_downgrade_safe(op.get_bind()):
        return
    for index_name in _INDEXES:
        op.drop_index(index_name, table_name=_TABLE)
    op.drop_table(_TABLE)
