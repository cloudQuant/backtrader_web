"""Create normalized append-only market-data evidence tables.

Revision ID: 20260908_market_data_observations
Revises: 20260908_market_data_catalog
Create Date: 2026-09-08

This revision only adds canonical Iteration 197 tables.  It neither migrates
nor rewrites legacy AkShare warehouse tables, CSV files, or existing trust
summary tables.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import context, op

revision = "20260908_market_data_observations"
down_revision = "20260908_market_data_catalog"
branch_labels = None
depends_on = None

_SHA256_LENGTH = 64
_PIT_DATETIME = sa.DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
_TABLE_COLUMNS = {
    "md_publications": {
        "id",
        "entity_type",
        "entity_id",
        "entity_sha256",
        "published_at",
        "created_at",
    },
    "md_instrument_identity_revisions": {
        "id",
        "instrument_id",
        "canonical_id",
        "asset_type",
        "market",
        "symbol",
        "metadata_version",
        "identity_json",
        "valid_from",
        "valid_to",
        "revision_number",
        "revision_sha256",
        "created_at",
    },
    "md_calendar_import_locks": {"calendar_code", "created_at"},
    "md_instrument_lookup_keys": {
        "id",
        "asset_type",
        "market",
        "symbol",
        "instrument_id",
        "canonical_id",
        "metadata_version",
        "is_active",
        "active_lookup_scope",
        "valid_from",
        "valid_to",
        "created_at",
    },
    "md_data_series": {
        "id",
        "dataset_id",
        "canonical_id",
        "data_kind",
        "frequency",
        "semantic_key_sha256",
        "semantic_identity_json",
        "created_at",
    },
    "md_source_snapshots": {
        "id",
        "provider_id",
        "platform",
        "source_id",
        "adapter_id",
        "endpoint_version",
        "request_fingerprint_sha256",
        "payload_sha256",
        "request_json",
        "payload_manifest_json",
        "payload_uri",
        "provenance_json",
        "source_observed_at",
        "source_published_at",
        "retrieved_at",
        "created_at",
    },
    "md_observation_revisions": {
        "id",
        "series_id",
        "event_time",
        "event_end",
        "available_at",
        "source_snapshot_id",
        "quality_status",
        "quality_policy_version",
        "quality_details_json",
        "fields_json",
        "fields_sha256",
        "revision_number",
        "revision_key_sha256",
        "normalization_version",
        "source_record_key",
        "provenance_json",
        "committed_at",
        "created_at",
    },
    "md_calendar_snapshots": {
        "id",
        "calendar_code",
        "calendar_version",
        "timezone_name",
        "source_snapshot_id",
        "snapshot_sha256",
        "definition_json",
        "effective_from",
        "effective_to",
        "created_at",
    },
    "md_calendar_events": {
        "id",
        "calendar_snapshot_id",
        "trading_date",
        "event_type",
        "session_code",
        "is_trading_day",
        "event_start",
        "event_end",
        "coverage_event_key",
        "event_payload_json",
        "event_sha256",
        "created_at",
    },
}
_TABLE_INDEXES = {
    "md_publications": {"ix_md_publication_entity_visible"},
    "md_instrument_identity_revisions": {
        "ix_md_instrument_identity_revision_canonical",
        "ix_md_instrument_identity_revision_exact",
    },
    "md_calendar_import_locks": set(),
    "md_instrument_lookup_keys": {
        "ix_md_instrument_lookup_active_exact",
        "ix_md_instrument_lookup_instrument_version",
    },
    "md_data_series": {"ix_md_data_series_dataset_canonical_kind"},
    "md_source_snapshots": {
        "ix_md_source_snapshot_provider_request",
        "ix_md_source_snapshot_payload_sha256",
    },
    "md_observation_revisions": {
        "ix_md_observation_revision_series_event",
        "ix_md_observation_revision_source",
        "ix_md_observation_revision_available",
    },
    "md_calendar_snapshots": {"ix_md_calendar_snapshot_code_version"},
    "md_calendar_events": {"ix_md_calendar_event_snapshot_trading_date"},
}
_TABLE_INDEX_SPECS = {
    "md_publications": {
        "ix_md_publication_entity_visible": (("entity_type", "entity_id", "published_at"), False),
    },
    "md_instrument_identity_revisions": {
        "ix_md_instrument_identity_revision_canonical": (("canonical_id", "valid_from"), False),
        "ix_md_instrument_identity_revision_exact": (
            ("asset_type", "market", "symbol", "valid_from"),
            False,
        ),
    },
    "md_calendar_import_locks": {},
    "md_instrument_lookup_keys": {
        "ix_md_instrument_lookup_active_exact": (
            ("asset_type", "market", "symbol", "is_active", "metadata_version"),
            False,
        ),
        "ix_md_instrument_lookup_instrument_version": (
            ("instrument_id", "metadata_version"),
            False,
        ),
    },
    "md_data_series": {
        "ix_md_data_series_dataset_canonical_kind": (
            ("dataset_id", "canonical_id", "data_kind"),
            False,
        ),
    },
    "md_source_snapshots": {
        "ix_md_source_snapshot_provider_request": (
            ("provider_id", "request_fingerprint_sha256"),
            False,
        ),
        "ix_md_source_snapshot_payload_sha256": (("payload_sha256",), False),
    },
    "md_observation_revisions": {
        "ix_md_observation_revision_series_event": (
            ("series_id", "event_time", "available_at"),
            False,
        ),
        "ix_md_observation_revision_source": (("source_snapshot_id",), False),
        "ix_md_observation_revision_available": (("available_at",), False),
    },
    "md_calendar_snapshots": {
        "ix_md_calendar_snapshot_code_version": (
            ("calendar_code", "calendar_version"),
            False,
        ),
    },
    "md_calendar_events": {
        "ix_md_calendar_event_snapshot_trading_date": (
            ("calendar_snapshot_id", "trading_date"),
            False,
        ),
    },
}
_TABLE_UNIQUES = {
    "md_publications": {"uq_md_publication_entity"},
    "md_instrument_identity_revisions": {
        "uq_md_instrument_identity_revision_number",
        "uq_md_instrument_identity_revision_sha256",
    },
    "md_calendar_import_locks": set(),
    "md_instrument_lookup_keys": {
        "uq_md_instrument_lookup_key_instrument",
        "uq_md_instrument_lookup_key_active",
    },
    "md_data_series": {"uq_md_data_series_semantic_key_sha256"},
    "md_source_snapshots": set(),
    "md_observation_revisions": {
        "uq_md_observation_revision_key_sha256",
        "uq_md_observation_revision_series_event_number",
    },
    "md_calendar_snapshots": {
        "uq_md_calendar_snapshot_code_version",
        "uq_md_calendar_snapshot_sha256",
    },
    "md_calendar_events": {
        "uq_md_calendar_event_sha256",
        "uq_md_calendar_event_snapshot_date_type_session",
        "uq_md_calendar_event_snapshot_coverage_key",
    },
}
_TABLE_UNIQUE_SPECS = {
    "md_publications": {
        "uq_md_publication_entity": ("entity_type", "entity_id"),
    },
    "md_instrument_identity_revisions": {
        "uq_md_instrument_identity_revision_number": ("instrument_id", "revision_number"),
        "uq_md_instrument_identity_revision_sha256": ("revision_sha256",),
    },
    "md_calendar_import_locks": {},
    "md_instrument_lookup_keys": {
        "uq_md_instrument_lookup_key_instrument": ("instrument_id",),
        "uq_md_instrument_lookup_key_active": (
            "asset_type",
            "market",
            "symbol",
            "active_lookup_scope",
        ),
    },
    "md_data_series": {
        "uq_md_data_series_semantic_key_sha256": ("semantic_key_sha256",),
    },
    "md_source_snapshots": {},
    "md_observation_revisions": {
        "uq_md_observation_revision_key_sha256": ("revision_key_sha256",),
        "uq_md_observation_revision_series_event_number": (
            "series_id",
            "event_time",
            "revision_number",
        ),
    },
    "md_calendar_snapshots": {
        "uq_md_calendar_snapshot_code_version": ("calendar_code", "calendar_version"),
        "uq_md_calendar_snapshot_sha256": ("snapshot_sha256",),
    },
    "md_calendar_events": {
        "uq_md_calendar_event_sha256": ("event_sha256",),
        "uq_md_calendar_event_snapshot_date_type_session": (
            "calendar_snapshot_id",
            "trading_date",
            "event_type",
            "session_code",
        ),
        "uq_md_calendar_event_snapshot_coverage_key": (
            "calendar_snapshot_id",
            "coverage_event_key",
        ),
    },
}
_TABLE_CHECKS = {
    "md_publications": {"ck_md_publication_entity_sha256_length"},
    "md_instrument_identity_revisions": {
        "ck_md_instrument_identity_revision_sha256_length",
        "ck_md_instrument_identity_revision_valid_window",
        "ck_md_instrument_identity_revision_number_positive",
    },
    "md_calendar_import_locks": set(),
    "md_instrument_lookup_keys": {
        "ck_md_instrument_lookup_key_active_scope",
        "ck_md_instrument_lookup_key_valid_window",
    },
    "md_data_series": {"ck_md_data_series_semantic_key_sha256_length"},
    "md_source_snapshots": {
        "ck_md_source_snapshot_request_fingerprint_sha256_length",
        "ck_md_source_snapshot_payload_sha256_length",
    },
    "md_observation_revisions": {
        "ck_md_observation_revision_fields_sha256_length",
        "ck_md_observation_revision_key_sha256_length",
        "ck_md_observation_revision_number_positive",
    },
    "md_calendar_snapshots": {
        "ck_md_calendar_snapshot_sha256_length",
        "ck_md_calendar_snapshot_effective_window",
    },
    "md_calendar_events": {
        "ck_md_calendar_event_sha256_length",
        "ck_md_calendar_event_time_window",
        "ck_md_calendar_event_coverage_key",
    },
}
_TABLE_FOREIGN_KEYS = {
    "md_publications": [],
    "md_instrument_identity_revisions": [
        (["instrument_id"], "asset_instruments", ["id"], "RESTRICT"),
    ],
    "md_calendar_import_locks": [],
    "md_instrument_lookup_keys": [(["instrument_id"], "asset_instruments", ["id"], "RESTRICT")],
    "md_data_series": [(["dataset_id"], "dg_datasets", ["id"], "RESTRICT")],
    "md_source_snapshots": [(["provider_id"], "dg_providers", ["id"], "RESTRICT")],
    "md_observation_revisions": [
        (["series_id"], "md_data_series", ["id"], "RESTRICT"),
        (["source_snapshot_id"], "md_source_snapshots", ["id"], "RESTRICT"),
    ],
    "md_calendar_snapshots": [
        (["source_snapshot_id"], "md_source_snapshots", ["id"], "RESTRICT")
    ],
    "md_calendar_events": [
        (["calendar_snapshot_id"], "md_calendar_snapshots", ["id"], "RESTRICT")
    ],
}
_TABLE_PRIMARY_KEYS = dict.fromkeys(_TABLE_COLUMNS, ("id",))
_TABLE_PRIMARY_KEYS["md_calendar_import_locks"] = ("calendar_code",)


def _is_offline() -> bool:
    return context.is_offline_mode()


def _table_exists(table_name: str) -> bool:
    return not _is_offline() and sa.inspect(op.get_bind()).has_table(table_name)


def _column_definitions(
    table_name: str,
    columns: tuple[Any, ...],
) -> dict[str, sa.Column[Any]]:
    """Extract the authoritative column contract from this migration's DDL call."""
    definitions = {
        str(column.name): column for column in columns if isinstance(column, sa.Column)
    }
    if not definitions or set(definitions) != _TABLE_COLUMNS[table_name]:
        raise RuntimeError(
            f"MARKET_DATA_OBSERVATIONS_MIGRATION_CONTRACT_INVALID: {table_name}"
        )
    return definitions


def _type_signature(
    type_: sa.types.TypeEngine[Any],
    *,
    preserve_timestamp_timezone: bool,
    preserve_timestamp_precision: bool,
) -> tuple[type[object], int | None, bool | None, int | None]:
    """Return portability-aware type affinity, length, timezone, and precision.

    SQLAlchemy maps both PostgreSQL ``TIMESTAMP`` and ``TIMESTAMP WITH TIME
    ZONE`` to the same ``DateTime`` type affinity.  Keep the ``timezone``
    flag only where reflection preserves it: PostgreSQL.  SQLite and MySQL do
    not retain this distinction, so treating their reflected ``DateTime``
    values as authoritative would reject a complete startup-created schema.
    """
    affinity = type_._type_affinity
    timezone_mode = (
        bool(getattr(type_, "timezone", False))
        if preserve_timestamp_timezone and isinstance(type_, sa.DateTime)
        else None
    )
    precision = (
        getattr(type_, "fsp", None)
        if preserve_timestamp_precision and isinstance(type_, sa.DateTime)
        else None
    )
    return affinity, getattr(type_, "length", None), timezone_mode, precision


def _normalize_check_expression(expression: object) -> str:
    """Normalize only presentation differences in a reflected CHECK expression.

    The comparison deliberately preserves operators, literals, and casts.  A
    pre-existing table is accepted only when its named constraint expresses
    the same rule as this migration, not merely when it reuses the same name.
    """
    normalized = "".join(str(expression).split())
    while (
        normalized.startswith("(")
        and normalized.endswith(")")
        and _outer_parentheses_wrap_expression(normalized)
    ):
        normalized = normalized[1:-1]
    return normalized


def _outer_parentheses_wrap_expression(expression: str) -> bool:
    """Return whether one outer parenthesis pair encloses the whole expression."""
    depth = 0
    for index, character in enumerate(expression):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index == len(expression) - 1
    return False


def _check_definitions(table_name: str, columns: tuple[Any, ...]) -> dict[str, str]:
    """Extract the authoritative named CHECK expressions from this DDL call."""
    constraints = tuple(
        constraint for constraint in columns if isinstance(constraint, sa.CheckConstraint)
    )
    definitions = {
        str(constraint.name): _normalize_check_expression(constraint.sqltext)
        for constraint in constraints
    }
    if (
        set(definitions) != _TABLE_CHECKS[table_name]
        or len(definitions) != len(constraints)
        or any(constraint.name is None for constraint in constraints)
    ):
        raise RuntimeError(
            f"MARKET_DATA_OBSERVATIONS_MIGRATION_CONTRACT_INVALID: {table_name} checks"
        )
    return definitions


def _table_is_complete(table_name: str, columns: tuple[Any, ...]) -> tuple[bool, str]:
    """Recognize only complete startup-created evidence tables as already upgraded."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    preserve_timestamp_timezone = getattr(bind.dialect, "name", None) == "postgresql"
    preserve_timestamp_precision = getattr(bind.dialect, "name", None) == "mysql"
    expected_columns = _column_definitions(table_name, columns)
    observed_columns = {
        str(column["name"]): column for column in inspector.get_columns(table_name)
    }
    observed_indexes = {
        str(index["name"]): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique", False)),
        )
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }
    observed_uniques = {
        str(constraint["name"]): tuple(
            str(column) for column in constraint.get("column_names") or ()
        )
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }
    observed_checks = {
        str(constraint["name"]): _normalize_check_expression(constraint.get("sqltext", ""))
        for constraint in inspector.get_check_constraints(table_name)
        if constraint.get("name")
    }
    observed_foreign_keys = {
        (
            tuple(str(column) for column in foreign_key.get("constrained_columns") or ()),
            str(foreign_key.get("referred_table")),
            tuple(str(column) for column in foreign_key.get("referred_columns") or ()),
            str((foreign_key.get("options") or {}).get("ondelete") or "").upper(),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }
    expected_foreign_keys = {
        (tuple(local_columns), referred_table, tuple(referred_columns), ondelete)
        for local_columns, referred_table, referred_columns, ondelete in _TABLE_FOREIGN_KEYS[
            table_name
        ]
    }
    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
    )

    missing_columns = _TABLE_COLUMNS[table_name] - set(observed_columns)
    invalid_columns: dict[str, dict[str, object]] = {}
    for column_name, expected in expected_columns.items():
        actual = observed_columns.get(column_name)
        if actual is None:
            continue
        actual_type = actual["type"]
        expected_type_signature = _type_signature(
            expected.type.dialect_impl(bind.dialect),
            preserve_timestamp_timezone=preserve_timestamp_timezone,
            preserve_timestamp_precision=preserve_timestamp_precision,
        )
        actual_type_signature = _type_signature(
            actual_type,
            preserve_timestamp_timezone=preserve_timestamp_timezone,
            preserve_timestamp_precision=preserve_timestamp_precision,
        )
        expected_default = (
            None if expected.server_default is None else str(expected.server_default.arg)
        )
        actual_default = actual.get("default")
        if (
            actual_type_signature != expected_type_signature
            or bool(actual.get("nullable")) != bool(expected.nullable)
            or actual_default != expected_default
        ):
            invalid_columns[column_name] = {
                "actual_type": actual_type_signature,
                "expected_type": expected_type_signature,
                "actual_nullable": bool(actual.get("nullable")),
                "expected_nullable": bool(expected.nullable),
                "actual_default": actual_default,
                "expected_default": expected_default,
            }
    expected_indexes = _TABLE_INDEX_SPECS[table_name]
    missing_indexes = set(expected_indexes) - set(observed_indexes)
    invalid_indexes = {
        index_name: {
            "actual": observed_indexes[index_name],
            "expected": expected,
        }
        for index_name, expected in expected_indexes.items()
        if index_name in observed_indexes and observed_indexes[index_name] != expected
    }
    expected_uniques = _TABLE_UNIQUE_SPECS[table_name]
    missing_uniques = set(expected_uniques) - set(observed_uniques)
    invalid_uniques = {
        constraint_name: {
            "actual": observed_uniques[constraint_name],
            "expected": expected,
        }
        for constraint_name, expected in expected_uniques.items()
        if constraint_name in observed_uniques and observed_uniques[constraint_name] != expected
    }
    expected_checks = _check_definitions(table_name, columns)
    missing_checks = set(expected_checks) - set(observed_checks)
    invalid_checks = {
        check_name: {
            "actual": observed_checks[check_name],
            "expected": expected_expression,
        }
        for check_name, expected_expression in expected_checks.items()
        if check_name in observed_checks and observed_checks[check_name] != expected_expression
    }
    missing_foreign_keys = expected_foreign_keys - observed_foreign_keys
    missing_parts = [
        *(f"columns={sorted(missing_columns)}" for _ in [0] if missing_columns),
        *(f"invalid_columns={invalid_columns}" for _ in [0] if invalid_columns),
        *(f"indexes={sorted(missing_indexes)}" for _ in [0] if missing_indexes),
        *(f"invalid_indexes={invalid_indexes}" for _ in [0] if invalid_indexes),
        *(f"uniques={sorted(missing_uniques)}" for _ in [0] if missing_uniques),
        *(f"invalid_uniques={invalid_uniques}" for _ in [0] if invalid_uniques),
        *(f"checks={sorted(missing_checks)}" for _ in [0] if missing_checks),
        *(f"invalid_checks={invalid_checks}" for _ in [0] if invalid_checks),
        *(f"foreign_keys={sorted(missing_foreign_keys)}" for _ in [0] if missing_foreign_keys),
        *(
            f"primary_key={primary_key!r} expected={_TABLE_PRIMARY_KEYS[table_name]!r}"
            for _ in [0]
            if primary_key != _TABLE_PRIMARY_KEYS[table_name]
        ),
    ]
    return not missing_parts, "; ".join(missing_parts)


def _assert_table_complete(table_name: str, columns: tuple[Any, ...]) -> None:
    complete, detail = _table_is_complete(table_name, columns)
    if not complete:
        raise RuntimeError(
            "MARKET_DATA_OBSERVATIONS_PARTIAL_SCHEMA_UNSAFE: "
            f"{table_name} is present but incomplete ({detail})"
        )


class _SchemaAwareOperations:
    """Avoid replaying table DDL over a complete ORM ``create_all`` database."""

    def __init__(self, operations: Any) -> None:
        self._operations = operations

    def create_table(self, table_name: str, *columns: Any, **kwargs: Any) -> Any:
        if _table_exists(table_name):
            _assert_table_complete(table_name, columns)
            return None
        return self._operations.create_table(table_name, *columns, **kwargs)

    def create_index(
        self,
        index_name: str,
        table_name: str,
        columns: list[str],
        **kwargs: Any,
    ) -> Any:
        if _table_exists(table_name):
            existing_indexes = {
                str(index["name"])
                for index in sa.inspect(op.get_bind()).get_indexes(table_name)
                if index.get("name")
            }
            if index_name in existing_indexes:
                return None
        return self._operations.create_index(index_name, table_name, columns, **kwargs)


def _assert_downgrade_safe() -> None:
    """Do not silently drop immutable evidence that has already been committed."""
    if _is_offline():
        raise RuntimeError(
            "MARKET_DATA_OBSERVATIONS_DOWNGRADE_BLOCKED: offline SQL cannot prove tables empty"
        )

    bind = op.get_bind()
    populated_tables = []
    for table_name in _TABLE_COLUMNS:
        if not _table_exists(table_name):
            continue
        row_count = int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())
        if row_count:
            populated_tables.append(f"{table_name}={row_count}")
    if populated_tables:
        raise RuntimeError(
            "MARKET_DATA_OBSERVATIONS_DOWNGRADE_BLOCKED: export immutable evidence before "
            f"downgrade ({', '.join(populated_tables)})"
        )


def upgrade() -> None:
    """Create generic, append-only normalized market-data evidence tables."""
    operations = _SchemaAwareOperations(op)
    operations.create_table(
        "md_publications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("entity_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("published_at", _PIT_DATETIME, nullable=True),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_md_publication_entity"),
        sa.CheckConstraint(
            f"length(entity_sha256) = {_SHA256_LENGTH}",
            name="ck_md_publication_entity_sha256_length",
        ),
    )
    operations.create_index(
        "ix_md_publication_entity_visible",
        "md_publications",
        ["entity_type", "entity_id", "published_at"],
        unique=False,
    )

    operations.create_table(
        "md_instrument_identity_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("market", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("metadata_version", sa.String(length=64), nullable=False),
        sa.Column("identity_json", sa.JSON(), nullable=False),
        sa.Column("valid_from", _PIT_DATETIME, nullable=False),
        sa.Column("valid_to", _PIT_DATETIME, nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["asset_instruments.id"],
            name="fk_md_identity_revision_instrument",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "revision_number",
            name="uq_md_instrument_identity_revision_number",
        ),
        sa.UniqueConstraint(
            "revision_sha256",
            name="uq_md_instrument_identity_revision_sha256",
        ),
        sa.CheckConstraint(
            f"length(revision_sha256) = {_SHA256_LENGTH}",
            name="ck_md_instrument_identity_revision_sha256_length",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_md_instrument_identity_revision_valid_window",
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_md_instrument_identity_revision_number_positive",
        ),
    )
    operations.create_index(
        "ix_md_instrument_identity_revision_canonical",
        "md_instrument_identity_revisions",
        ["canonical_id", "valid_from"],
        unique=False,
    )
    operations.create_index(
        "ix_md_instrument_identity_revision_exact",
        "md_instrument_identity_revisions",
        ["asset_type", "market", "symbol", "valid_from"],
        unique=False,
    )

    operations.create_table(
        "md_calendar_import_locks",
        sa.Column("calendar_code", sa.String(length=128), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.PrimaryKeyConstraint("calendar_code"),
    )

    operations.create_table(
        "md_instrument_lookup_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("market", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("metadata_version", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("active_lookup_scope", sa.String(length=16), nullable=True),
        sa.Column("valid_from", _PIT_DATETIME, nullable=False),
        sa.Column("valid_to", _PIT_DATETIME, nullable=True),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["asset_instruments.id"],
            name="fk_md_instrument_lookup_key_instrument_id_asset_instruments",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            name="uq_md_instrument_lookup_key_instrument",
        ),
        sa.UniqueConstraint(
            "asset_type",
            "market",
            "symbol",
            "active_lookup_scope",
            name="uq_md_instrument_lookup_key_active",
        ),
        sa.CheckConstraint(
            "(is_active = true AND active_lookup_scope IS NOT NULL AND active_lookup_scope = 'ACTIVE') "
            "OR (is_active = false AND active_lookup_scope IS NULL)",
            name="ck_md_instrument_lookup_key_active_scope",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_md_instrument_lookup_key_valid_window",
        ),
    )
    operations.create_index(
        "ix_md_instrument_lookup_active_exact",
        "md_instrument_lookup_keys",
        ["asset_type", "market", "symbol", "is_active", "metadata_version"],
        unique=False,
    )
    operations.create_index(
        "ix_md_instrument_lookup_instrument_version",
        "md_instrument_lookup_keys",
        ["instrument_id", "metadata_version"],
        unique=False,
    )

    operations.create_table(
        "md_data_series",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_id", sa.String(length=512), nullable=False),
        sa.Column("data_kind", sa.String(length=64), nullable=False),
        sa.Column("frequency", sa.String(length=16), nullable=True),
        sa.Column("semantic_key_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("semantic_identity_json", sa.JSON(), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["dg_datasets.id"],
            name="fk_md_data_series_dataset_id_dg_datasets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("semantic_key_sha256", name="uq_md_data_series_semantic_key_sha256"),
        sa.CheckConstraint(
            f"length(semantic_key_sha256) = {_SHA256_LENGTH}",
            name="ck_md_data_series_semantic_key_sha256_length",
        ),
    )
    operations.create_index(
        "ix_md_data_series_dataset_canonical_kind",
        "md_data_series",
        ["dataset_id", "canonical_id", "data_kind"],
        unique=False,
    )

    operations.create_table(
        "md_source_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("adapter_id", sa.String(length=128), nullable=False),
        sa.Column("endpoint_version", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("payload_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("payload_manifest_json", sa.JSON(), nullable=False),
        sa.Column("payload_uri", sa.Text(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("source_observed_at", _PIT_DATETIME, nullable=True),
        sa.Column("source_published_at", _PIT_DATETIME, nullable=True),
        sa.Column("retrieved_at", _PIT_DATETIME, nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["dg_providers.id"],
            name="fk_md_source_snapshot_provider_id_dg_providers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"length(request_fingerprint_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_snapshot_request_fingerprint_sha256_length",
        ),
        sa.CheckConstraint(
            f"length(payload_sha256) = {_SHA256_LENGTH}",
            name="ck_md_source_snapshot_payload_sha256_length",
        ),
    )
    operations.create_index(
        "ix_md_source_snapshot_provider_request",
        "md_source_snapshots",
        ["provider_id", "request_fingerprint_sha256"],
        unique=False,
    )
    operations.create_index(
        "ix_md_source_snapshot_payload_sha256",
        "md_source_snapshots",
        ["payload_sha256"],
        unique=False,
    )

    operations.create_table(
        "md_observation_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("series_id", sa.String(length=36), nullable=False),
        sa.Column("event_time", _PIT_DATETIME, nullable=False),
        sa.Column("event_end", _PIT_DATETIME, nullable=True),
        sa.Column("available_at", _PIT_DATETIME, nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("quality_policy_version", sa.String(length=128), nullable=False),
        sa.Column("quality_details_json", sa.JSON(), nullable=False),
        sa.Column("fields_json", sa.JSON(), nullable=False),
        sa.Column("fields_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_key_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("normalization_version", sa.String(length=128), nullable=False),
        sa.Column("source_record_key", sa.String(length=512), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("committed_at", _PIT_DATETIME, nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["md_data_series.id"],
            name="fk_md_observation_revision_series_id_md_data_series",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["md_source_snapshots.id"],
            name="fk_md_observation_revision_source_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_key_sha256",
            name="uq_md_observation_revision_key_sha256",
        ),
        sa.UniqueConstraint(
            "series_id",
            "event_time",
            "revision_number",
            name="uq_md_observation_revision_series_event_number",
        ),
        sa.CheckConstraint(
            f"length(fields_sha256) = {_SHA256_LENGTH}",
            name="ck_md_observation_revision_fields_sha256_length",
        ),
        sa.CheckConstraint(
            f"length(revision_key_sha256) = {_SHA256_LENGTH}",
            name="ck_md_observation_revision_key_sha256_length",
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_md_observation_revision_number_positive",
        ),
    )
    operations.create_index(
        "ix_md_observation_revision_series_event",
        "md_observation_revisions",
        ["series_id", "event_time", "available_at"],
        unique=False,
    )
    operations.create_index(
        "ix_md_observation_revision_source",
        "md_observation_revisions",
        ["source_snapshot_id"],
        unique=False,
    )
    operations.create_index(
        "ix_md_observation_revision_available",
        "md_observation_revisions",
        ["available_at"],
        unique=False,
    )

    operations.create_table(
        "md_calendar_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("calendar_code", sa.String(length=128), nullable=False),
        sa.Column("calendar_version", sa.String(length=128), nullable=False),
        sa.Column("timezone_name", sa.String(length=128), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["md_source_snapshots.id"],
            name="fk_md_calendar_snapshot_source_snapshot_id_md_source_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "calendar_code",
            "calendar_version",
            name="uq_md_calendar_snapshot_code_version",
        ),
        sa.UniqueConstraint("snapshot_sha256", name="uq_md_calendar_snapshot_sha256"),
        sa.CheckConstraint(
            f"length(snapshot_sha256) = {_SHA256_LENGTH}",
            name="ck_md_calendar_snapshot_sha256_length",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_md_calendar_snapshot_effective_window",
        ),
    )
    operations.create_index(
        "ix_md_calendar_snapshot_code_version",
        "md_calendar_snapshots",
        ["calendar_code", "calendar_version"],
        unique=False,
    )

    operations.create_table(
        "md_calendar_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("calendar_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("session_code", sa.String(length=128), nullable=False),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("event_start", _PIT_DATETIME, nullable=True),
        sa.Column("event_end", _PIT_DATETIME, nullable=True),
        sa.Column("coverage_event_key", sa.String(length=128), nullable=True),
        sa.Column("event_payload_json", sa.JSON(), nullable=False),
        sa.Column("event_sha256", sa.String(length=_SHA256_LENGTH), nullable=False),
        sa.Column("created_at", _PIT_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(
            ["calendar_snapshot_id"],
            ["md_calendar_snapshots.id"],
            name="fk_md_calendar_event_snapshot_id_md_calendar_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_sha256", name="uq_md_calendar_event_sha256"),
        sa.UniqueConstraint(
            "calendar_snapshot_id",
            "trading_date",
            "event_type",
            "session_code",
            name="uq_md_calendar_event_snapshot_date_type_session",
        ),
        sa.UniqueConstraint(
            "calendar_snapshot_id",
            "coverage_event_key",
            name="uq_md_calendar_event_snapshot_coverage_key",
        ),
        sa.CheckConstraint(
            f"length(event_sha256) = {_SHA256_LENGTH}",
            name="ck_md_calendar_event_sha256_length",
        ),
        sa.CheckConstraint(
            "event_end IS NULL OR event_start IS NULL OR event_end >= event_start",
            name="ck_md_calendar_event_time_window",
        ),
        sa.CheckConstraint(
            "coverage_event_key IS NULL OR "
            "(is_trading_day = true AND event_type = 'session' AND event_start IS NOT NULL)",
            name="ck_md_calendar_event_coverage_key",
        ),
    )
    operations.create_index(
        "ix_md_calendar_event_snapshot_trading_date",
        "md_calendar_events",
        ["calendar_snapshot_id", "trading_date"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only empty normalized evidence tables created by this revision."""
    _assert_downgrade_safe()
    op.drop_index("ix_md_calendar_event_snapshot_trading_date", table_name="md_calendar_events")
    op.drop_table("md_calendar_events")
    op.drop_index("ix_md_calendar_snapshot_code_version", table_name="md_calendar_snapshots")
    op.drop_table("md_calendar_snapshots")
    op.drop_index("ix_md_observation_revision_available", table_name="md_observation_revisions")
    op.drop_index("ix_md_observation_revision_source", table_name="md_observation_revisions")
    op.drop_index("ix_md_observation_revision_series_event", table_name="md_observation_revisions")
    op.drop_table("md_observation_revisions")
    op.drop_index("ix_md_source_snapshot_payload_sha256", table_name="md_source_snapshots")
    op.drop_index("ix_md_source_snapshot_provider_request", table_name="md_source_snapshots")
    op.drop_table("md_source_snapshots")
    op.drop_index("ix_md_data_series_dataset_canonical_kind", table_name="md_data_series")
    op.drop_table("md_data_series")
    op.drop_index(
        "ix_md_instrument_lookup_instrument_version",
        table_name="md_instrument_lookup_keys",
    )
    op.drop_index(
        "ix_md_instrument_lookup_active_exact",
        table_name="md_instrument_lookup_keys",
    )
    op.drop_table("md_instrument_lookup_keys")
    op.drop_table("md_calendar_import_locks")
    op.drop_index(
        "ix_md_instrument_identity_revision_exact",
        table_name="md_instrument_identity_revisions",
    )
    op.drop_index(
        "ix_md_instrument_identity_revision_canonical",
        table_name="md_instrument_identity_revisions",
    )
    op.drop_table("md_instrument_identity_revisions")
    op.drop_index("ix_md_publication_entity_visible", table_name="md_publications")
    op.drop_table("md_publications")
