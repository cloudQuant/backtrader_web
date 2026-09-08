"""Rename unreleased long market-data check constraints portably.

Revision ID: 20260909_market_data_constraint_name_portability
Revises: 20260909_market_data_exact_identity_collation
Create Date: 2026-09-09

Early SQLite-only Iteration 197 candidates could record three check-constraint
names that exceed PostgreSQL's 63-byte identifier limit.  The preceding
historical revisions now use short names for fresh databases, but an already
stamped candidate skips those revisions.  This reconciliation revision checks
the expression before replacing legacy names where the dialect can do so
without rebuilding referenced SQLite tables.  SQLite keeps an equivalent
legacy name: names have no semantic effect there, while table recreation would
break populated foreign-key graphs.  It never treats a name collision or a
differing expression as compatible.
"""

# alembic-meta: estimated_rows=0; lock_kind=short

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

import sqlalchemy as sa

from alembic import context, op

revision = "20260909_market_data_constraint_name_portability"
down_revision = "20260909_market_data_exact_identity_collation"
branch_labels = None
depends_on = None

_SHA256_LENGTH = 64
_RENAMES: Mapping[str, Mapping[str, tuple[str, str]]] = {
    "md_source_snapshots": {
        "ck_md_source_snapshot_provider_request_fingerprint_sha256_length": (
            "ck_md_srcsnap_provider_req_fp_sha256_len",
            "provider_request_fingerprint_sha256 IS NULL OR "
            f"length(provider_request_fingerprint_sha256) = {_SHA256_LENGTH}",
        ),
        "ck_md_source_snapshot_source_authorization_descriptor_sha256_length": (
            "ck_md_srcsnap_src_auth_desc_sha256_len",
            "source_authorization_descriptor_sha256 IS NULL OR "
            f"length(source_authorization_descriptor_sha256) = {_SHA256_LENGTH}",
        ),
    },
    "md_calendar_snapshots": {
        "ck_md_calendar_snapshot_source_governance_descriptor_sha256_length": (
            "ck_md_calsnap_src_gov_desc_sha256_len",
            "source_governance_descriptor_sha256 IS NULL OR "
            f"length(source_governance_descriptor_sha256) = {_SHA256_LENGTH}",
        ),
    },
}
_POSTGRES_IDENTIFIER_LIMIT = 63
_LEGACY_NAME_ALIASES: Mapping[str, tuple[str, ...]] = {
    legacy_name: tuple(
        dict.fromkeys((legacy_name, legacy_name[:_POSTGRES_IDENTIFIER_LIMIT]))
    )
    for table_renames in _RENAMES.values()
    for legacy_name in table_renames
}
_MYSQL_MAINTENANCE_FENCE_ENV = "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE"
_MYSQL_MIGRATION_LOCK_NAME = "ai_for_investor.market_data.constraint_name_portability"
_LOCK_TIMEOUT_SECONDS = 5


def _normalized_expression(expression: object) -> str:
    """Compare the SQLAlchemy PostgreSQL reflection of a portable SHA check.

    PostgreSQL reflects ``length(column)`` as ``length(column::text)`` for a
    varchar column.  The cast does not change the check's semantics, whereas
    every other token remains part of the strict drift comparison.
    """
    return "".join(str(expression).split()).lower().replace("::text", "")


def _observed_checks(bind: sa.Connection, table_name: str) -> dict[str, str]:
    return {
        str(check["name"]): _normalized_expression(check.get("sqltext", ""))
        for check in sa.inspect(bind).get_check_constraints(table_name)
        if check.get("name")
    }


def _legacy_constraint_names(legacy_name: str) -> tuple[str, ...]:
    """Return the full and PostgreSQL-truncated identifiers for one old check."""
    return _LEGACY_NAME_ALIASES.get(legacy_name, (legacy_name,))


def _present_legacy_constraint_names(
    observed: Mapping[str, str],
    *,
    legacy_name: str,
) -> tuple[str, ...]:
    return tuple(name for name in _legacy_constraint_names(legacy_name) if name in observed)


@contextmanager
def _ddl_maintenance_fence() -> Iterator[None]:
    """Bound DDL and require a confirmed MySQL writer drain before CHECK replacement.

    MySQL implicitly commits every CHECK drop/add.  A named migration lock
    serializes migration runners, while the explicit environment confirmation
    records that application writers have been drained for the whole
    drop/create window.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT_SECONDS}s'"))
        yield
        return
    if bind.dialect.name != "mysql":
        yield
        return
    if os.getenv(_MYSQL_MAINTENANCE_FENCE_ENV) != "confirmed":
        raise RuntimeError(
            "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE_REQUIRED: "
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
            "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MIGRATION_LOCK_UNAVAILABLE: "
            "could not acquire the migration fence"
        )
    try:
        yield
    finally:
        bind.execute(
            sa.text("SELECT RELEASE_LOCK(:lock_name)"),
            {"lock_name": _MYSQL_MIGRATION_LOCK_NAME},
        )


def _validate_rename_state(
    observed: Mapping[str, str],
    *,
    legacy_name: str,
    portable_name: str,
    expression: str,
) -> bool:
    """Return whether a legacy constraint needs replacement after semantic checks."""
    expected = _normalized_expression(expression)
    present_legacy_names = _present_legacy_constraint_names(observed, legacy_name=legacy_name)
    portable_expression = observed.get(portable_name)
    if not present_legacy_names and portable_expression is None:
        raise RuntimeError(
            "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_SCHEMA_DRIFT: "
            f"{legacy_name} and {portable_name} missing"
        )
    for observed_legacy_name in present_legacy_names:
        legacy_expression = observed[observed_legacy_name]
        if legacy_expression != expected:
            raise RuntimeError(
                "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_SCHEMA_DRIFT: "
                f"{observed_legacy_name}={legacy_expression!r}"
            )
    if portable_expression is not None and portable_expression != expected:
        raise RuntimeError(
            "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_SCHEMA_DRIFT: "
            f"{portable_name}={portable_expression!r}"
        )
    return bool(present_legacy_names)


def _reconcile_sqlite_table(bind: sa.Connection, table_name: str) -> None:
    """Validate legacy SQLite constraints without rebuilding referenced tables.

    ``md_source_snapshots`` and ``md_calendar_snapshots`` have child foreign
    keys.  SQLite batch recreation would issue ``DROP TABLE`` and fail with
    ``PRAGMA foreign_keys=ON`` for a populated candidate.  A constraint name
    is only an identifier, so leave a verified legacy name in place and let
    fresh PostgreSQL/MySQL databases receive portable names from the revised
    historical migrations.
    """
    observed = _observed_checks(bind, table_name)
    for legacy_name, (portable_name, expression) in _RENAMES[table_name].items():
        _validate_rename_state(
            observed,
            legacy_name=legacy_name,
            portable_name=portable_name,
            expression=expression,
        )


def _reconcile_non_sqlite_table(bind: sa.Connection, table_name: str) -> None:
    observed = _observed_checks(bind, table_name)
    for legacy_name, (portable_name, expression) in _RENAMES[table_name].items():
        if not _validate_rename_state(
            observed,
            legacy_name=legacy_name,
            portable_name=portable_name,
            expression=expression,
        ):
            continue
        present_legacy_names = _present_legacy_constraint_names(
            observed,
            legacy_name=legacy_name,
        )
        if portable_name in observed:
            for observed_legacy_name in present_legacy_names:
                op.drop_constraint(observed_legacy_name, table_name, type_="check")
            continue
        if bind.dialect.name == "postgresql":
            primary_legacy_name, *redundant_legacy_names = present_legacy_names
            op.execute(
                sa.text(
                    f'ALTER TABLE "{table_name}" '
                    f'RENAME CONSTRAINT "{primary_legacy_name}" TO "{portable_name}"'
                )
            )
            for redundant_legacy_name in redundant_legacy_names:
                op.drop_constraint(redundant_legacy_name, table_name, type_="check")
            continue
        for observed_legacy_name in present_legacy_names:
            op.drop_constraint(observed_legacy_name, table_name, type_="check")
        op.create_check_constraint(portable_name, table_name, expression)


def upgrade() -> None:
    """Replace only semantic-equivalent legacy check names on stamped candidates."""
    if context.is_offline_mode():
        raise RuntimeError(
            "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_OFFLINE_UNSUPPORTED: "
            "offline SQL cannot inspect existing constraint semantics"
        )
    bind = op.get_bind()
    with _ddl_maintenance_fence():
        for table_name in _RENAMES:
            if not sa.inspect(bind).has_table(table_name):
                raise RuntimeError(
                    "MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_SCHEMA_UNREADY: "
                    f"{table_name} missing"
                )
            if bind.dialect.name == "sqlite":
                _reconcile_sqlite_table(bind, table_name)
            else:
                _reconcile_non_sqlite_table(bind, table_name)


def downgrade() -> None:
    """Keep portable names because downgrade must not recreate invalid DDL."""
    # The preceding revised migrations already create the portable names on a
    # fresh database.  Reverting only the Alembic marker is therefore safe and
    # avoids reintroducing a name PostgreSQL or MySQL may reject.
    return None
