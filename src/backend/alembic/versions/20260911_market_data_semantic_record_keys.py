"""Add server-owned semantic record identities to normalized observations.

Revision ID: 20260911_market_data_semantic_record_keys
Revises: 20260911_market_data_deferred_publications
Create Date: 2026-09-11

A normalized observation used to be unique only by series, event timestamp,
and revision number.  That shape cannot retain independent option contracts,
inventory dimensions, or other B2 multi-record facts that share an event time.
This migration assigns every historical row one fixed server-owned singleton
semantic identity, then changes fact uniqueness to include a semantic-key hash.

``source_record_key`` remains opaque upstream trace metadata.  It is neither
used as the semantic identity nor changed during the migration.
"""

# alembic-meta: estimated_rows=bounded_backfill; lock_kind=writer_drain

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa

from alembic import context, op

revision = "20260911_market_data_semantic_record_keys"
down_revision = "20260911_market_data_deferred_publications"
branch_labels = None
depends_on = None

_TABLE = "md_observation_revisions"
_SHA256_LENGTH = 64
_OLD_UNIQUE = "uq_md_observation_revision_series_event_number"
_NEW_UNIQUE = "uq_md_observation_revision_series_event_record_number"
_PIT_INDEX = "ix_md_observation_revision_series_event_record_available"
_SEMANTIC_RECORD_KEY_COLUMN = "semantic_record_key"
_SEMANTIC_RECORD_KEY_SHA256_COLUMN = "semantic_record_key_sha256"
_SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON = (
    '{"record_identity_contract_version":"market-data-semantic-record-key-v1","scope":"singleton"}'
)
_SINGLE_RECORD_SEMANTIC_KEY_SHA256 = (
    "98220d1065fb50740a858df25f884573e8c6aea554b05a3268ed4d1fd621d08e"
)
_CHECKS = {
    "ck_md_observation_revision_semantic_record_key_nonempty": ("length(semantic_record_key) > 0"),
    "ck_md_observation_revision_semantic_record_key_sha256_length": (
        f"length(semantic_record_key_sha256) = {_SHA256_LENGTH}"
    ),
}
_SCHEMA_DRIFT = "MARKET_DATA_SEMANTIC_RECORD_KEY_SCHEMA_DRIFT"
_DOWNGRADE_BLOCKED = "MARKET_DATA_SEMANTIC_RECORD_KEY_DOWNGRADE_BLOCKED"
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_SEMANTIC_RECORD_KEY_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.semantic_record_key"
_LOCK_TIMEOUT_SECONDS = 5


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL and require a writer drain before fact identity changes."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_SECONDS}s'"))
        yield
        return
    if bind.dialect.name not in {"mysql", "mariadb"}:
        yield
        return
    if os.getenv(_MYSQL_MAINTENANCE_FENCE_ENV) != "confirmed":
        raise RuntimeError(
            "MARKET_DATA_SEMANTIC_RECORD_KEY_MAINTENANCE_FENCE_REQUIRED: "
            "stop market-data writers and set "
            f"{_MYSQL_MAINTENANCE_FENCE_ENV}=confirmed before MySQL DDL"
        )
    bind.execute(sa.text(f"SET SESSION lock_wait_timeout = {_LOCK_TIMEOUT_SECONDS}"))
    acquired = bind.execute(
        sa.text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
        {"lock_name": _MYSQL_MIGRATION_LOCK_NAME, "timeout_seconds": _LOCK_TIMEOUT_SECONDS},
    ).scalar_one()
    if acquired != 1:
        raise RuntimeError(
            "MARKET_DATA_SEMANTIC_RECORD_KEY_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"),
            {"lock_name": _MYSQL_MIGRATION_LOCK_NAME},
        )


def _is_offline() -> bool:
    return context.is_offline_mode()


def _normalized_expression(expression: object) -> str:
    """Normalize harmless reflection formatting before comparing named checks."""
    normalized = "".join(str(expression).split()).lower().replace('"', "").replace("`", "")
    # PostgreSQL reflects ``VARCHAR`` check operands with an explicit text
    # cast, for example ``length(semantic_record_key_sha256::text)=64``.
    # The cast does not change the portable check contract and must not make a
    # freshly created PostgreSQL schema look like an operator-modified table.
    normalized = re.sub(r"::(?:text|charactervarying|varchar)(?:\[\])?", "", normalized)
    normalized = re.sub(r"_(?:utf8mb4|utf8)(?=')", "", normalized)
    # PostgreSQL can retain parentheses around the operand after dropping its
    # reflected ``::text`` cast (``length((column)::text)``), while MySQL may
    # wrap an entire CHECK expression.  These forms do not alter either of
    # this migration's named integrity contracts.
    normalized = re.sub(r"\(\(([a-z_][a-z0-9_]*)\)\)", r"(\1)", normalized)
    while (
        normalized.startswith("(")
        and normalized.endswith(")")
        and _outer_parentheses_wrap(normalized)
    ):
        normalized = normalized[1:-1]
    return normalized


def _outer_parentheses_wrap(expression: str) -> bool:
    """Return whether one outer parenthesis pair encloses all of ``expression``."""
    depth = 0
    for index, character in enumerate(expression):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index == len(expression) - 1
    return False


def _require_table(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table(_TABLE):
        raise RuntimeError(f"{_SCHEMA_DRIFT}: {_TABLE} missing")


def _column_definitions(bind: sa.Connection) -> dict[str, dict[str, object]]:
    _require_table(bind)
    return {str(column["name"]): column for column in sa.inspect(bind).get_columns(_TABLE)}


def _column_matches(
    column: dict[str, object],
    expected_type: sa.types.TypeEngine[Any],
    *,
    nullable: bool | None = None,
) -> bool:
    actual_type = column["type"]
    if actual_type._type_affinity is not expected_type._type_affinity:
        return False
    if getattr(actual_type, "length", None) != getattr(expected_type, "length", None):
        return False
    return nullable is None or bool(column.get("nullable")) == nullable


def _unique_constraints(bind: sa.Connection) -> dict[str, tuple[str, ...]]:
    return {
        str(constraint["name"]): tuple(
            str(column) for column in constraint.get("column_names") or ()
        )
        for constraint in sa.inspect(bind).get_unique_constraints(_TABLE)
        if constraint.get("name")
    }


def _indexes(bind: sa.Connection) -> dict[str, tuple[tuple[str, ...], bool]]:
    return {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique", False)),
        )
        for index in sa.inspect(bind).get_indexes(_TABLE)
        if index.get("name")
    }


def _checks(bind: sa.Connection) -> dict[str, str]:
    return {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in sa.inspect(bind).get_check_constraints(_TABLE)
        if check.get("name")
    }


def _ensure_identity_columns(bind: sa.Connection) -> None:
    """Add paired nullable columns and resume a verified partial MySQL DDL step."""
    columns = _column_definitions(bind)
    key = columns.get(_SEMANTIC_RECORD_KEY_COLUMN)
    key_hash = columns.get(_SEMANTIC_RECORD_KEY_SHA256_COLUMN)
    if key is None and key_hash is None:
        op.add_column(_TABLE, sa.Column(_SEMANTIC_RECORD_KEY_COLUMN, sa.Text(), nullable=True))
        op.add_column(
            _TABLE,
            sa.Column(
                _SEMANTIC_RECORD_KEY_SHA256_COLUMN, sa.String(length=_SHA256_LENGTH), nullable=True
            ),
        )
        return
    if key is None:
        if not _column_matches(key_hash, sa.String(length=_SHA256_LENGTH), nullable=True):
            raise RuntimeError(f"{_SCHEMA_DRIFT}: semantic record key hash column differs")
        op.add_column(_TABLE, sa.Column(_SEMANTIC_RECORD_KEY_COLUMN, sa.Text(), nullable=True))
        return
    if key_hash is None:
        if not _column_matches(key, sa.Text(), nullable=True):
            raise RuntimeError(f"{_SCHEMA_DRIFT}: semantic record key column differs")
        op.add_column(
            _TABLE,
            sa.Column(
                _SEMANTIC_RECORD_KEY_SHA256_COLUMN, sa.String(length=_SHA256_LENGTH), nullable=True
            ),
        )
        return
    if not _column_matches(key, sa.Text()) or not _column_matches(
        key_hash, sa.String(length=_SHA256_LENGTH)
    ):
        raise RuntimeError(f"{_SCHEMA_DRIFT}: semantic record identity column types differ")


def _backfill_single_record_identity(bind: sa.Connection) -> None:
    """Fill only rows with neither B2 key value; never reinterpret provenance."""
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    key = table.c[_SEMANTIC_RECORD_KEY_COLUMN]
    key_hash = table.c[_SEMANTIC_RECORD_KEY_SHA256_COLUMN]
    partial = bind.execute(
        sa.select(table.c.id)
        .where(
            sa.or_(
                sa.and_(key.is_(None), key_hash.is_not(None)),
                sa.and_(key.is_not(None), key_hash.is_(None)),
            )
        )
        .limit(1)
    ).scalar_one_or_none()
    if partial is not None:
        raise RuntimeError(
            f"{_SCHEMA_DRIFT}: row {partial!r} has a partial semantic record identity"
        )
    bind.execute(
        table.update()
        .where(sa.and_(key.is_(None), key_hash.is_(None)))
        .values(
            {
                _SEMANTIC_RECORD_KEY_COLUMN: _SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
                _SEMANTIC_RECORD_KEY_SHA256_COLUMN: _SINGLE_RECORD_SEMANTIC_KEY_SHA256,
            }
        )
    )
    invalid = bind.execute(
        sa.select(table.c.id)
        .where(
            sa.or_(
                key.is_(None),
                key_hash.is_(None),
                sa.func.length(key) <= 0,
                sa.func.length(key_hash) != _SHA256_LENGTH,
            )
        )
        .limit(1)
    ).scalar_one_or_none()
    if invalid is not None:
        raise RuntimeError(
            f"{_SCHEMA_DRIFT}: row {invalid!r} has an invalid semantic record identity"
        )


def _final_schema_errors(bind: sa.Connection) -> dict[str, object]:
    columns = _column_definitions(bind)
    errors: dict[str, object] = {}
    key = columns.get(_SEMANTIC_RECORD_KEY_COLUMN)
    key_hash = columns.get(_SEMANTIC_RECORD_KEY_SHA256_COLUMN)
    if key is None or not _column_matches(key, sa.Text(), nullable=False):
        errors[_SEMANTIC_RECORD_KEY_COLUMN] = key
    if key_hash is None or not _column_matches(
        key_hash, sa.String(length=_SHA256_LENGTH), nullable=False
    ):
        errors[_SEMANTIC_RECORD_KEY_SHA256_COLUMN] = key_hash

    uniques = _unique_constraints(bind)
    if uniques.get(_NEW_UNIQUE) != (
        "series_id",
        "event_time",
        _SEMANTIC_RECORD_KEY_SHA256_COLUMN,
        "revision_number",
    ):
        errors[_NEW_UNIQUE] = uniques.get(_NEW_UNIQUE)
    if _OLD_UNIQUE in uniques:
        errors[_OLD_UNIQUE] = uniques[_OLD_UNIQUE]

    if _indexes(bind).get(_PIT_INDEX) != (
        ("series_id", "event_time", _SEMANTIC_RECORD_KEY_SHA256_COLUMN, "available_at"),
        False,
    ):
        errors[_PIT_INDEX] = _indexes(bind).get(_PIT_INDEX)

    checks = _checks(bind)
    for name, expression in _CHECKS.items():
        if checks.get(name) != _normalized_expression(expression):
            errors[name] = checks.get(name)
    return errors


def _assert_new_fact_coordinates_unique(bind: sa.Connection) -> None:
    """Prove an interrupted unique-constraint replacement has no duplicate rows."""
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    duplicate = bind.execute(
        sa.select(
            table.c.series_id,
            table.c.event_time,
            table.c[_SEMANTIC_RECORD_KEY_SHA256_COLUMN],
            table.c.revision_number,
        )
        .group_by(
            table.c.series_id,
            table.c.event_time,
            table.c[_SEMANTIC_RECORD_KEY_SHA256_COLUMN],
            table.c.revision_number,
        )
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            f"{_SCHEMA_DRIFT}: duplicate fact coordinate prevents unique-constraint recovery"
        )


def _create_or_upgrade_constraints(bind: sa.Connection) -> None:
    """Finalize non-null identity, unique facts, checks, and PIT sort support."""
    uniques = _unique_constraints(bind)
    if _NEW_UNIQUE in uniques and _OLD_UNIQUE in uniques:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: both legacy and B2 fact uniqueness constraints exist")
    if _NEW_UNIQUE not in uniques:
        # MySQL DDL commits implicitly.  If a process ends after the old
        # constraint is dropped but before the new one is created, a retry
        # under the same explicit writer drain can finish only after proving
        # that no unprotected duplicate coordinate was introduced.
        _assert_new_fact_coordinates_unique(bind)

    checks = _checks(bind)
    for name, expression in _CHECKS.items():
        observed = checks.get(name)
        if observed is not None and observed != _normalized_expression(expression):
            raise RuntimeError(f"{_SCHEMA_DRIFT}: {name} has a different expression")

    existing_indexes = _indexes(bind)
    observed_index = existing_indexes.get(_PIT_INDEX)
    expected_index = (
        ("series_id", "event_time", _SEMANTIC_RECORD_KEY_SHA256_COLUMN, "available_at"),
        False,
    )
    if observed_index is not None and observed_index != expected_index:
        raise RuntimeError(f"{_SCHEMA_DRIFT}: {_PIT_INDEX} has a different definition")

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(_TABLE, recreate="always") as batch:
            batch.alter_column(
                _SEMANTIC_RECORD_KEY_COLUMN,
                existing_type=sa.Text(),
                nullable=False,
            )
            batch.alter_column(
                _SEMANTIC_RECORD_KEY_SHA256_COLUMN,
                existing_type=sa.String(length=_SHA256_LENGTH),
                nullable=False,
            )
            if _OLD_UNIQUE in uniques:
                batch.drop_constraint(_OLD_UNIQUE, type_="unique")
            if _NEW_UNIQUE not in uniques:
                batch.create_unique_constraint(
                    _NEW_UNIQUE,
                    [
                        "series_id",
                        "event_time",
                        _SEMANTIC_RECORD_KEY_SHA256_COLUMN,
                        "revision_number",
                    ],
                )
            for name, expression in _CHECKS.items():
                if name not in checks:
                    batch.create_check_constraint(name, expression)
            if _PIT_INDEX not in existing_indexes:
                batch.create_index(
                    _PIT_INDEX,
                    [
                        "series_id",
                        "event_time",
                        _SEMANTIC_RECORD_KEY_SHA256_COLUMN,
                        "available_at",
                    ],
                    unique=False,
                )
        return

    op.alter_column(
        _TABLE,
        _SEMANTIC_RECORD_KEY_COLUMN,
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        _TABLE,
        _SEMANTIC_RECORD_KEY_SHA256_COLUMN,
        existing_type=sa.String(length=_SHA256_LENGTH),
        nullable=False,
    )
    if _OLD_UNIQUE in uniques:
        op.drop_constraint(_OLD_UNIQUE, _TABLE, type_="unique")
    if _NEW_UNIQUE not in uniques:
        op.create_unique_constraint(
            _NEW_UNIQUE,
            _TABLE,
            [
                "series_id",
                "event_time",
                _SEMANTIC_RECORD_KEY_SHA256_COLUMN,
                "revision_number",
            ],
        )
    for name, expression in _CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, _TABLE, expression)
    if _PIT_INDEX not in existing_indexes:
        op.create_index(
            _PIT_INDEX,
            _TABLE,
            ["series_id", "event_time", _SEMANTIC_RECORD_KEY_SHA256_COLUMN, "available_at"],
        )


def upgrade() -> None:
    """Backfill singleton record identities and unlock B2 multi-record facts."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_SEMANTIC_RECORD_KEY_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot validate or backfill immutable fact identities"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        _ensure_identity_columns(bind)
        _backfill_single_record_identity(bind)
        _create_or_upgrade_constraints(bind)
        errors = _final_schema_errors(bind)
        if errors:
            raise RuntimeError(f"{_SCHEMA_DRIFT}: final schema mismatch {errors}")


def _lock_for_downgrade(bind: sa.Connection) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"LOCK TABLE {_TABLE} IN ACCESS EXCLUSIVE MODE"))


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    table = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
    if bind.execute(sa.select(table.c.id).limit(1)).scalar_one_or_none() is not None:
        raise RuntimeError(
            f"{_DOWNGRADE_BLOCKED}: immutable semantic record identities have been recorded"
        )


def downgrade() -> None:
    """Remove identity columns only from an empty test/development fact table."""
    if _is_offline():
        raise RuntimeError(f"{_DOWNGRADE_BLOCKED}: offline SQL cannot prove the table empty")
    bind = op.get_bind()
    if bind.dialect.name in {"mysql", "mariadb"}:
        raise RuntimeError(
            f"{_DOWNGRADE_BLOCKED}: MySQL cannot atomically prove the fact table empty"
        )
    with _ddl_maintenance_fence():
        _require_table(bind)
        _lock_for_downgrade(bind)
        _assert_downgrade_safe(bind)
        uniques = _unique_constraints(bind)
        checks = _checks(bind)
        indexes = _indexes(bind)
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(_TABLE, recreate="always") as batch:
                if _PIT_INDEX in indexes:
                    batch.drop_index(_PIT_INDEX)
                if _NEW_UNIQUE in uniques:
                    batch.drop_constraint(_NEW_UNIQUE, type_="unique")
                for name in _CHECKS:
                    if name in checks:
                        batch.drop_constraint(name, type_="check")
                batch.drop_column(_SEMANTIC_RECORD_KEY_SHA256_COLUMN)
                batch.drop_column(_SEMANTIC_RECORD_KEY_COLUMN)
                batch.create_unique_constraint(
                    _OLD_UNIQUE,
                    ["series_id", "event_time", "revision_number"],
                )
            return
        if _PIT_INDEX in indexes:
            op.drop_index(_PIT_INDEX, table_name=_TABLE)
        if _NEW_UNIQUE in uniques:
            op.drop_constraint(_NEW_UNIQUE, _TABLE, type_="unique")
        for name in _CHECKS:
            if name in checks:
                op.drop_constraint(name, _TABLE, type_="check")
        op.drop_column(_TABLE, _SEMANTIC_RECORD_KEY_SHA256_COLUMN)
        op.drop_column(_TABLE, _SEMANTIC_RECORD_KEY_COLUMN)
        op.create_unique_constraint(
            _OLD_UNIQUE,
            _TABLE,
            ["series_id", "event_time", "revision_number"],
        )
