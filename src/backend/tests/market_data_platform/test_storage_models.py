"""Normalized storage-model contracts for Iteration 197 market data."""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.database import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
CATALOG_REVISION = "20260908_market_data_catalog"
OBSERVATIONS_REVISION = "20260908_market_data_observations"
SHARED_DATASET_BINDINGS_REVISION = "20260908_market_data_shared_dataset_bindings"
VISIBILITY_ANCHOR_REVISION = "20260908_market_data_visibility_anchor"
SOURCE_RECEIPT_EVIDENCE_REVISION = "20260908_market_data_source_receipt_evidence"
SOURCE_GOVERNANCE_REVISION = "20260908_market_data_source_governance"
FETCH_LEASE_REVISION = "20260909_market_data_fetch_leases"
EXACT_IDENTITY_COLLATION_REVISION = "20260909_market_data_exact_identity_collation"
CONSTRAINT_NAME_PORTABILITY_REVISION = "20260909_market_data_constraint_name_portability"
AI_RESEARCH_APPROVAL_REVISION = "20260908_ai_research_approval_authority"
MERGE_REVISION = "20260909_ai_research_market_data_merge"
RESEARCH_BINDINGS_REVISION = "20260909_market_data_research_bindings"
RESEARCH_BINDING_CONSUMERS_REVISION = "20260909_market_data_research_binding_consumers"
SHARED_SOURCE_PAYLOADS_REVISION = "20260910_market_data_shared_source_payloads"
CAPABILITY_LEDGER_REVISION = "20260910_market_data_capability_ledger"
DEFERRED_PUBLICATIONS_REVISION = "20260911_market_data_deferred_publications"
INTEGRATED_HEAD_REVISION = DEFERRED_PUBLICATIONS_REVISION
OBSERVATION_STORAGE_TABLES = {
    "md_instrument_lookup_keys",
    "md_data_series",
    "md_source_snapshots",
    "md_observation_revisions",
    "md_calendar_snapshots",
    "md_calendar_events",
}
STORAGE_TABLES = OBSERVATION_STORAGE_TABLES | {
    "md_source_payloads",
    "md_source_snapshot_payload_refs",
}


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _load_observations_migration() -> ModuleType:
    """Load the revision module directly for offline schema-recovery probes."""
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "20260908_market_data_observations.py"
    spec = importlib.util.spec_from_file_location(
        "iteration197_observations_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_shared_dataset_bindings_migration() -> ModuleType:
    """Load the candidate catalog-binding revision for isolated fence probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260908_market_data_shared_dataset_bindings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_shared_dataset_bindings_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_visibility_anchor_migration() -> ModuleType:
    """Load the receipt-order migration for isolated offline-mode probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260908_market_data_visibility_anchor.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_visibility_anchor_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_source_receipt_evidence_migration() -> ModuleType:
    """Load the receipt-evidence revision for offline fence probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260908_market_data_source_receipt_evidence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_source_receipt_evidence_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_shared_source_payloads_migration() -> ModuleType:
    """Load the child-evidence migration for direct schema-drift probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260910_market_data_shared_source_payloads.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_shared_source_payloads_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_capability_ledger_migration() -> ModuleType:
    """Load the capability-ledger revision for direct downgrade safety probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260910_market_data_capability_ledger.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_capability_ledger_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_fetch_lease_migration() -> ModuleType:
    """Load the lease revision for direct MySQL rollback-safety probes."""
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "20260909_market_data_fetch_leases.py"
    spec = importlib.util.spec_from_file_location(
        "iteration197_fetch_lease_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_source_governance_migration() -> ModuleType:
    """Load the source-governance revision for isolated maintenance-fence probes."""
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260908_market_data_source_governance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_source_governance_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_constraint_name_portability_migration() -> ModuleType:
    """Load the stamped-candidate reconciliation revision for direct probes."""
    migration_path = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260909_market_data_constraint_name_portability.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_constraint_name_portability_migration", migration_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unreleased_legacy_check_names_are_accepted_only_with_matching_semantics() -> None:
    """SQLite candidates created before the PG-safe rename stay upgradeable."""
    receipt_migration = _load_source_receipt_evidence_migration()
    receipt_name = receipt_migration._PROVIDER_FINGERPRINT_CHECK
    receipt_legacy_name = receipt_migration._LEGACY_CHECK_NAMES[receipt_name][0]
    receipt_expression = receipt_migration._CHECKS[receipt_name]
    assert (
        receipt_migration._matching_check_name(
            {receipt_legacy_name: receipt_migration._normalized_expression(receipt_expression)},
            name=receipt_name,
            expression=receipt_expression,
        )
        == receipt_legacy_name
    )
    with pytest.raises(RuntimeError, match="SCHEMA_DRIFT"):
        receipt_migration._matching_check_name(
            {receipt_legacy_name: "different"},
            name=receipt_name,
            expression=receipt_expression,
        )

    governance_migration = _load_source_governance_migration()
    governance_table = governance_migration._CALENDAR_SNAPSHOTS
    governance_name = "ck_md_calsnap_src_gov_desc_sha256_len"
    governance_legacy_name = governance_migration._LEGACY_TABLE_CHECK_NAMES[governance_table][
        governance_name
    ][0]
    governance_expression = governance_migration._TABLE_CHECKS[governance_table][governance_name]
    assert (
        governance_migration._matching_check_name(
            {
                governance_legacy_name: governance_migration._normalized_expression(
                    governance_expression
                )
            },
            table_name=governance_table,
            name=governance_name,
            expression=governance_expression,
        )
        == governance_legacy_name
    )
    with pytest.raises(RuntimeError, match="SCHEMA_DRIFT"):
        governance_migration._matching_check_name(
            {governance_legacy_name: "different"},
            table_name=governance_table,
            name=governance_name,
            expression=governance_expression,
        )


def test_constraint_portability_migration_preserves_a_stamped_legacy_sqlite_candidate(
    tmp_path: Path,
) -> None:
    """A database that skipped edited history reaches head without rebuilding FKs."""
    database_path = tmp_path / "market-data-legacy-constraint-names.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    migration = _load_constraint_name_portability_migration()
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            config.attributes["connection"] = connection
            command.upgrade(config, EXACT_IDENTITY_COLLATION_REVISION)
            if connection.in_transaction():
                connection.commit()
            with connection.begin():
                operations = Operations(MigrationContext.configure(connection))
                for table_name, renames in migration._RENAMES.items():
                    with operations.batch_alter_table(table_name, recreate="always") as batch:
                        for legacy_name, (portable_name, expression) in renames.items():
                            batch.drop_constraint(portable_name, type_="check")
                            batch.create_check_constraint(legacy_name, expression)

            with connection.begin():
                receipt_at = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
                connection.execute(
                    text(
                        "INSERT INTO dg_providers "
                        "(id, provider_id, name, category, auth_type, rate_limit, is_active, created_at) "
                        "VALUES ('provider-legacy-names', 'akshare', 'AkShare', 'market', 'none', "
                        "60, 1, :receipt_at)"
                    ),
                    {"receipt_at": receipt_at},
                )
                connection.execute(
                    text(
                        "INSERT INTO md_source_snapshots "
                        "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                        "request_fingerprint_sha256, payload_sha256, request_json, payload_manifest_json, "
                        "provenance_json, retrieved_at, created_at) "
                        "VALUES ('snapshot-legacy-names', 'provider-legacy-names', 'akshare', 'akshare', "
                        "'akshare.market-data', 'v1', :request_fingerprint, :payload_sha256, '{}', '{}', "
                        "'{}', :receipt_at, :receipt_at)"
                    ),
                    {
                        "request_fingerprint": _sha("legacy-constraint-request"),
                        "payload_sha256": _sha("legacy-constraint-payload"),
                        "receipt_at": receipt_at,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO md_calendar_snapshots "
                        "(id, calendar_code, calendar_version, timezone_name, source_snapshot_id, "
                        "snapshot_sha256, definition_json, created_at) "
                        "VALUES ('calendar-legacy-names', 'CN-SSE', '2026.09', 'Asia/Shanghai', "
                        "'snapshot-legacy-names', :snapshot_sha256, '{}', :receipt_at)"
                    ),
                    {
                        "snapshot_sha256": _sha("legacy-constraint-calendar"),
                        "receipt_at": receipt_at,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO md_calendar_events "
                        "(id, calendar_snapshot_id, trading_date, event_type, session_code, "
                        "is_trading_day, event_payload_json, event_sha256, created_at) "
                        "VALUES ('calendar-event-legacy-names', 'calendar-legacy-names', '2026-09-09', "
                        "'holiday', 'closed', 0, '{}', :event_sha256, :receipt_at)"
                    ),
                    {
                        "event_sha256": _sha("legacy-constraint-calendar-event"),
                        "receipt_at": receipt_at,
                    },
                )

            command.upgrade(config, CONSTRAINT_NAME_PORTABILITY_REVISION)

            inspector = inspect(connection)
            for table_name, renames in migration._RENAMES.items():
                observed = {
                    str(constraint["name"]): migration._normalized_expression(
                        constraint.get("sqltext", "")
                    )
                    for constraint in inspector.get_check_constraints(table_name)
                    if constraint.get("name")
                }
                for legacy_name, (portable_name, expression) in renames.items():
                    assert observed[legacy_name] == migration._normalized_expression(expression)
                    assert portable_name not in observed
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == (CONSTRAINT_NAME_PORTABILITY_REVISION)
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM md_source_snapshots WHERE id = 'snapshot-legacy-names'"
                    )
                ).scalar_one()
                == 1
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM md_calendar_events "
                        "WHERE id = 'calendar-event-legacy-names'"
                    )
                ).scalar_one()
                == 1
            )
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        engine.dispose()


def test_constraint_portability_normalizes_only_the_postgresql_varchar_text_cast() -> None:
    """A reflected PostgreSQL SHA-length constraint is semantically equivalent."""
    migration = _load_constraint_name_portability_migration()
    expression = (
        "provider_request_fingerprint_sha256 IS NULL OR "
        "length(provider_request_fingerprint_sha256) = 64"
    )
    reflected = (
        "provider_request_fingerprint_sha256 IS NULL OR "
        "length(provider_request_fingerprint_sha256::text) = 64"
    )

    assert migration._normalized_expression(reflected) == migration._normalized_expression(
        expression
    )
    assert migration._normalized_expression(
        "provider_request_fingerprint_sha256 IS NULL OR "
        "length(provider_request_fingerprint_sha256::text) = 63"
    ) != migration._normalized_expression(expression)

    legacy_name, (portable_name, _) = next(iter(migration._RENAMES["md_source_snapshots"].items()))
    postgres_truncated_name = legacy_name[:63]
    assert postgres_truncated_name in migration._legacy_constraint_names(legacy_name)
    assert migration._validate_rename_state(
        {postgres_truncated_name: migration._normalized_expression(reflected)},
        legacy_name=legacy_name,
        portable_name=portable_name,
        expression=expression,
    )


def test_constraint_portability_rejects_a_stamped_candidate_missing_both_constraint_names() -> None:
    """A migration marker cannot conceal absence of a SHA integrity constraint."""
    migration = _load_constraint_name_portability_migration()
    legacy_name, (portable_name, expression) = next(
        iter(migration._RENAMES["md_source_snapshots"].items())
    )

    with pytest.raises(RuntimeError, match="SCHEMA_DRIFT"):
        migration._validate_rename_state(
            {},
            legacy_name=legacy_name,
            portable_name=portable_name,
            expression=expression,
        )


def test_constraint_portability_migration_refuses_mysql_without_a_maintenance_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Implicit-commit CHECK replacement cannot start while MySQL writers may run."""
    migration = _load_constraint_name_portability_migration()

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("unfenced MySQL migration must not issue DDL or a lock query")

    monkeypatch.delenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, raising=False)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with pytest.raises(
        RuntimeError,
        match="MARKET_DATA_CONSTRAINT_NAME_PORTABILITY_MAINTENANCE_FENCE_REQUIRED",
    ):
        with migration._ddl_maintenance_fence():
            pass


def test_constraint_portability_migration_uses_a_bounded_mysql_migration_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The writer-drain confirmation also serializes MySQL migration runners."""
    migration = _load_constraint_name_portability_migration()
    commands: list[str] = []

    class _ScalarResult:
        def scalar_one(self) -> int:
            return 1

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, statement: object, _params: object = None) -> _ScalarResult:
            commands.append(str(statement))
            return _ScalarResult()

    monkeypatch.setenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, "confirmed")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with migration._ddl_maintenance_fence():
        pass

    assert any("SET SESSION lock_wait_timeout" in command for command in commands)
    assert any("GET_LOCK" in command for command in commands)
    assert any("RELEASE_LOCK" in command for command in commands)


def _publication_table_columns(
    monkeypatch: pytest.MonkeyPatch, migration: ModuleType
) -> tuple[object, ...]:
    """Capture the migration's actual publication-table contract without a database."""
    captured: dict[str, tuple[object, ...]] = {}

    class _CapturingOperations:
        def __init__(self, operations: object) -> None:
            del operations

        def create_table(self, table_name: str, *columns: object, **kwargs: object) -> None:
            del kwargs
            captured[table_name] = columns

        def create_index(
            self,
            index_name: str,
            table_name: str,
            columns: list[str],
            **kwargs: object,
        ) -> None:
            del index_name, table_name, columns, kwargs

    monkeypatch.setattr(migration, "_SchemaAwareOperations", _CapturingOperations)
    migration.upgrade()
    return captured["md_publications"]


class _PreexistingPublicationInspector:
    """Offline inspector payload for a startup-created PostgreSQL publication table."""

    def __init__(
        self,
        migration: ModuleType,
        columns: tuple[object, ...],
        *,
        published_at_type: sa.types.TypeEngine[object],
        check_sql: str,
    ) -> None:
        expected_columns = migration._column_definitions("md_publications", columns)
        self._columns = [
            {
                "name": column_name,
                "type": published_at_type if column_name == "published_at" else column.type,
                "nullable": column.nullable,
                "default": None,
            }
            for column_name, column in expected_columns.items()
        ]
        self._indexes = [
            {
                "name": index_name,
                "column_names": list(specification[0]),
                "unique": specification[1],
            }
            for index_name, specification in migration._TABLE_INDEX_SPECS["md_publications"].items()
        ]
        self._uniques = [
            {"name": name, "column_names": list(columns)}
            for name, columns in migration._TABLE_UNIQUE_SPECS["md_publications"].items()
        ]
        self._checks = [
            {
                "name": "ck_md_publication_entity_sha256_length",
                "sqltext": check_sql,
            }
        ]

    def get_columns(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._columns

    def get_indexes(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._indexes

    def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._uniques

    def get_check_constraints(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return self._checks

    def get_foreign_keys(self, table_name: str) -> list[dict[str, object]]:
        assert table_name == "md_publications"
        return []

    def get_pk_constraint(self, table_name: str) -> dict[str, list[str]]:
        assert table_name == "md_publications"
        return {"constrained_columns": ["id"]}


def _preexisting_publication_contract(
    monkeypatch: pytest.MonkeyPatch,
    *,
    published_at_type: sa.types.TypeEngine[object],
    check_sql: str | None = None,
    dialect_name: str = "postgresql",
) -> tuple[bool, str]:
    """Run the schema-completeness check against a no-server inspector fixture."""
    migration = _load_observations_migration()
    columns = _publication_table_columns(monkeypatch, migration)
    expected_check_sql = next(
        str(constraint.sqltext)
        for constraint in columns
        if isinstance(constraint, sa.CheckConstraint)
        and constraint.name == "ck_md_publication_entity_sha256_length"
    )
    inspector = _PreexistingPublicationInspector(
        migration,
        columns,
        published_at_type=published_at_type,
        check_sql=expected_check_sql if check_sql is None else check_sql,
    )
    dialect = {
        "mysql": mysql.dialect(),
        "postgresql": postgresql.dialect(),
        "sqlite": sqlite.dialect(),
    }[dialect_name]
    bind = SimpleNamespace(dialect=dialect)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: bind))
    monkeypatch.setattr(migration.sa, "inspect", lambda bind: inspector)
    return migration._table_is_complete("md_publications", columns)


def test_observation_schema_recovery_rejects_postgresql_timestamp_without_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PostgreSQL timestamp without timezone cannot satisfy a PIT table contract."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=postgresql.TIMESTAMP(timezone=False),
    )

    assert not complete
    assert "invalid_columns" in detail
    assert "published_at" in detail


def test_observation_schema_recovery_accepts_sqlite_datetime_without_timezone_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQLite reflection may erase timezone metadata from a complete startup schema."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=sa.DateTime(),
        dialect_name="sqlite",
    )

    assert complete, detail


def test_observation_schema_recovery_rejects_mysql_datetime_without_microseconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-existing MySQL DATETIME(0) cannot preserve PIT publication order."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=mysql.DATETIME(fsp=0),
        dialect_name="mysql",
    )

    assert not complete
    assert "invalid_columns" in detail
    assert "published_at" in detail


def test_observation_migration_uses_mysql_microsecond_datetime_for_pit_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The migration keeps a B receipt later than A after MySQL persistence."""
    migration = _load_observations_migration()
    columns = _publication_table_columns(monkeypatch, migration)
    table = sa.Table("md_publications", sa.MetaData(), *columns)

    ddl = str(sa.schema.CreateTable(table).compile(dialect=mysql.dialect()))

    assert "published_at DATETIME(6)" in ddl
    assert "created_at DATETIME(6)" in ddl


def test_observation_schema_recovery_rejects_same_named_wrong_check_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reused CHECK name cannot hide an altered immutable-evidence rule."""
    complete, detail = _preexisting_publication_contract(
        monkeypatch,
        published_at_type=postgresql.TIMESTAMP(timezone=True),
        check_sql="length(entity_sha256) = 63",
    )

    assert not complete
    assert "invalid_checks" in detail
    assert "ck_md_publication_entity_sha256_length" in detail


def test_identity_key_models_render_bytewise_identifier_collations() -> None:
    """Fresh schemas cannot inherit a case-insensitive default for protocol identifiers."""
    from app.models.asset_research import AssetInstrument
    from app.models.market_data_platform import (
        MdInstrumentIdentityRevision,
        MdInstrumentLookupKey,
    )

    for dialect, expected_collation in (
        (mysql.dialect(), "COLLATE utf8mb4_bin"),
        (postgresql.dialect(), 'COLLATE "C"'),
        (sqlite.dialect(), 'COLLATE "BINARY"'),
    ):
        identity_ddl = str(
            sa.schema.CreateTable(MdInstrumentIdentityRevision.__table__).compile(dialect=dialect)
        )
        lookup_ddl = str(
            sa.schema.CreateTable(MdInstrumentLookupKey.__table__).compile(dialect=dialect)
        )
        authority_ddl = str(
            sa.schema.CreateTable(AssetInstrument.__table__).compile(dialect=dialect)
        )
        assert identity_ddl.count(expected_collation) >= 4
        assert lookup_ddl.count(expected_collation) >= 4
        assert authority_ddl.count(expected_collation) >= 1


def test_storage_models_register_generic_cross_asset_fact_tables() -> None:
    """The normalized layer registers generic facts and exact lookup keys."""
    from app.models.asset_research import AssetInstrument
    from app.models.data_governance import DgDataset, DgProvider
    from app.models.market_data_platform import (
        MdCalendarEvent,
        MdCalendarSnapshot,
        MdDataSeries,
        MdFetchLease,
        MdInstrumentLookupKey,
        MdObservationRevision,
        MdSourcePayload,
        MdSourceSnapshot,
        MdSourceSnapshotPayloadRef,
    )

    assert STORAGE_TABLES <= set(Base.metadata.tables)
    assert "normalized_symbol" not in MdInstrumentLookupKey.__table__.c.keys()
    assert {
        "asset_type",
        "market",
        "symbol",
        "instrument_id",
        "canonical_id",
        "metadata_version",
        "is_active",
    } <= set(MdInstrumentLookupKey.__table__.c.keys())
    assert "symbol" not in MdDataSeries.__table__.c.keys()
    assert {
        "lease_key_sha256",
        "owner_token",
        "fence_token",
        "expires_at",
    } <= set(MdFetchLease.__table__.c.keys())
    assert {"dataset_id", "canonical_id", "data_kind", "semantic_key_sha256"} <= set(
        MdDataSeries.__table__.c.keys()
    )
    assert {"series_id", "event_time", "available_at", "source_snapshot_id", "fields_json"} <= set(
        MdObservationRevision.__table__.c.keys()
    )
    assert {
        "request_fingerprint_sha256",
        "provider_request_id",
        "provider_request_fingerprint_sha256",
        "query_fingerprint_sha256",
        "source_authorization_state",
        "source_authorization_descriptor_sha256",
        "fetch_lease_key_sha256",
        "fetch_lease_fence_token",
        "provenance_json",
    } <= set(MdSourceSnapshot.__table__.c.keys())
    assert {
        "content_sha256",
        "payload_format",
        "canonical_payload_bytes",
        "payload_bytes",
    } <= set(MdSourcePayload.__table__.c.keys())
    assert {"source_snapshot_id", "content_sha256", "payload_role"} <= set(
        MdSourceSnapshotPayloadRef.__table__.c.keys()
    )
    assert any(
        index.name == "ix_md_source_snapshot_payload_ref_content"
        and tuple(column.name for column in index.columns) == ("content_sha256",)
        for index in MdSourceSnapshotPayloadRef.__table__.indexes
    )
    assert any(
        index.name == "ix_md_source_snapshot_provider_request_id"
        and tuple(column.name for column in index.columns) == ("provider_id", "provider_request_id")
        and index.unique
        for index in MdSourceSnapshot.__table__.indexes
    )
    assert {
        "calendar_code",
        "calendar_version",
        "snapshot_sha256",
        "source_registry_id",
        "source_governance_state",
        "source_governance_descriptor_sha256",
    } <= set(MdCalendarSnapshot.__table__.c.keys())
    assert {"calendar_snapshot_id", "trading_date", "event_type", "event_sha256"} <= set(
        MdCalendarEvent.__table__.c.keys()
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        now = datetime(2026, 9, 8, tzinfo=timezone.utc)
        with Session(engine) as session:
            stock_dataset = DgDataset(
                id="dataset-stock",
                dataset_code="market.stock_daily",
                display_name="Stock daily bars",
                domain="market",
            )
            crypto_dataset = DgDataset(
                id="dataset-crypto",
                dataset_code="market.crypto_quote",
                display_name="Crypto quote snapshots",
                domain="market",
            )
            provider = DgProvider(
                id="provider-akshare",
                provider_id="akshare",
                name="AkShare",
                category="market",
            )
            stock_instrument = AssetInstrument(
                id="instrument-stock-v1",
                canonical_id="instrument:stock:cn:600000",
                asset_type="stock",
                identity_level="PRODUCT",
                identity_json={},
                metadata_version="instrument-v1",
            )
            stock_instrument_v2 = AssetInstrument(
                id="instrument-stock-v2",
                canonical_id="instrument:stock:cn:600000",
                asset_type="stock",
                identity_level="PRODUCT",
                identity_json={},
                metadata_version="instrument-v2",
            )
            crypto_instrument = AssetInstrument(
                id="instrument-crypto-v1",
                canonical_id="instrument:crypto:btc-usdt",
                asset_type="crypto",
                identity_level="PRODUCT",
                identity_json={},
                metadata_version="instrument-v1",
            )
            stock_lookup = MdInstrumentLookupKey(
                id="lookup-stock-v1",
                asset_type="stock",
                market="CN-SSE",
                symbol="600000",
                instrument_id=stock_instrument.id,
                canonical_id=stock_instrument.canonical_id,
                metadata_version=stock_instrument.metadata_version,
                is_active=True,
            )
            crypto_lookup = MdInstrumentLookupKey(
                id="lookup-crypto-v1",
                asset_type="crypto",
                market="BINANCE",
                symbol="BTC-USDT",
                instrument_id=crypto_instrument.id,
                canonical_id=crypto_instrument.canonical_id,
                metadata_version=crypto_instrument.metadata_version,
                is_active=True,
            )
            stock_series = MdDataSeries(
                id="series-stock",
                dataset_id=stock_dataset.id,
                canonical_id="instrument:stock:cn:600000",
                data_kind="bars",
                frequency="1d",
                semantic_key_sha256=_sha("stock-series"),
                semantic_identity_json={"price_basis": "close", "currency": "CNY"},
            )
            crypto_series = MdDataSeries(
                id="series-crypto",
                dataset_id=crypto_dataset.id,
                canonical_id="instrument:crypto:btc-usdt",
                data_kind="quote_snapshot",
                frequency=None,
                semantic_key_sha256=_sha("crypto-series"),
                semantic_identity_json={"price_basis": "mid", "currency": "USDT"},
            )
            source_snapshot = MdSourceSnapshot(
                id="source-snapshot-1",
                provider_id=provider.id,
                platform="akshare",
                source_id="stock_zh_a_hist",
                adapter_id="akshare.stock.v1",
                endpoint_version="v1",
                request_fingerprint_sha256=_sha("request-1"),
                payload_sha256=_sha("payload-1"),
                request_json={"symbol": "600000"},
                payload_manifest_json={"uri": "raw://payload-1"},
                provenance_json={"upstream": "eastmoney"},
                retrieved_at=now,
            )
            session.add_all(
                [
                    stock_dataset,
                    crypto_dataset,
                    provider,
                    stock_instrument,
                    stock_instrument_v2,
                    crypto_instrument,
                    stock_lookup,
                    crypto_lookup,
                    stock_series,
                    crypto_series,
                    source_snapshot,
                ]
            )
            session.commit()

        with Session(engine) as session:
            exact_lookup = session.scalar(
                select(MdInstrumentLookupKey).where(
                    MdInstrumentLookupKey.asset_type == "stock",
                    MdInstrumentLookupKey.market == "CN-SSE",
                    MdInstrumentLookupKey.symbol == "600000",
                    MdInstrumentLookupKey.is_active.is_(True),
                )
            )
            assert exact_lookup is not None
            assert exact_lookup.canonical_id == "instrument:stock:cn:600000"
            assert exact_lookup.active_lookup_scope == "ACTIVE"
            assert session.scalar(select(MdDataSeries).where(MdDataSeries.id == "series-stock"))
            assert session.scalar(select(MdDataSeries).where(MdDataSeries.id == "series-crypto"))
            legacy_snapshot = session.scalar(
                select(MdSourceSnapshot).where(MdSourceSnapshot.id == "source-snapshot-1")
            )
            assert legacy_snapshot is not None
            assert legacy_snapshot.provider_request_id is None
            assert legacy_snapshot.provider_request_fingerprint_sha256 is None
            assert legacy_snapshot.query_fingerprint_sha256 is None
            assert legacy_snapshot.source_authorization_state is None
            assert legacy_snapshot.source_authorization_descriptor_sha256 is None
            duplicate_key = MdDataSeries(
                id="series-duplicate",
                dataset_id="dataset-crypto",
                canonical_id="instrument:crypto:btc-usdt-alt",
                data_kind="quote_snapshot",
                semantic_key_sha256=_sha("stock-series"),
                semantic_identity_json={},
            )
            session.add(duplicate_key)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            duplicate_active_lookup = MdInstrumentLookupKey(
                id="lookup-stock-v2",
                asset_type="stock",
                market="CN-SSE",
                symbol="600000",
                instrument_id="instrument-stock-v2",
                canonical_id="instrument:stock:cn:600000",
                metadata_version="instrument-v2",
                is_active=True,
            )
            session.add(duplicate_active_lookup)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with Session(engine) as session:
            # Core SQL bypasses the ORM event that normally assigns ACTIVE.
            # The database check must still reject NULL because unique indexes
            # permit multiple NULLs on the supported database engines.
            with pytest.raises(IntegrityError):
                session.execute(
                    MdInstrumentLookupKey.__table__.insert().values(
                        id="lookup-active-null-scope",
                        asset_type="stock",
                        market="CN-SSE",
                        symbol="scope-null",
                        instrument_id="instrument-stock-v2",
                        canonical_id="instrument:stock:cn:600000",
                        metadata_version="instrument-null-scope",
                        is_active=True,
                        active_lookup_scope=None,
                        valid_from=now,
                        created_at=now,
                    )
                )
            session.rollback()

        with Session(engine) as session:
            zero_length_history = MdInstrumentLookupKey(
                id="lookup-stock-zero-length-history",
                asset_type="stock",
                market="CN-SSE",
                symbol="600000",
                instrument_id="instrument-stock-v2",
                canonical_id="instrument:stock:cn:600000",
                metadata_version="instrument-zero-length-history",
                is_active=False,
                valid_from=now,
                valid_to=now,
            )
            session.add(zero_length_history)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        assert "ix_md_instrument_lookup_active_exact" in {
            index["name"] for index in inspect(engine).get_indexes("md_instrument_lookup_keys")
        }
    finally:
        engine.dispose()


def test_observation_revisions_are_append_only_with_source_and_quality_provenance() -> None:
    """One logical event can retain revisions without overwriting prior source evidence."""
    from app.models.data_governance import DgDataset, DgProvider
    from app.models.market_data_platform import (
        ImmutableMarketDataRecordError,
        MdDataSeries,
        MdObservationRevision,
        MdSourceSnapshot,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        event_time = datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc)
        available_at = datetime(2026, 9, 8, 1, 31, tzinfo=timezone.utc)
        with Session(engine) as session:
            session.add_all(
                [
                    DgDataset(
                        id="dataset-bars",
                        dataset_code="market.stock_daily",
                        display_name="Stock daily bars",
                        domain="market",
                    ),
                    DgProvider(
                        id="provider-1",
                        provider_id="akshare",
                        name="AkShare",
                        category="market",
                    ),
                    MdDataSeries(
                        id="series-1",
                        dataset_id="dataset-bars",
                        canonical_id="instrument:stock:cn:600000",
                        data_kind="bars",
                        frequency="1d",
                        semantic_key_sha256=_sha("series-1"),
                        semantic_identity_json={},
                    ),
                    MdSourceSnapshot(
                        id="source-1",
                        provider_id="provider-1",
                        platform="akshare",
                        source_id="stock_zh_a_hist",
                        adapter_id="akshare.stock.v1",
                        endpoint_version="v1",
                        request_fingerprint_sha256=_sha("request-1"),
                        payload_sha256=_sha("payload-1"),
                        request_json={},
                        payload_manifest_json={},
                        provenance_json={},
                        retrieved_at=available_at,
                    ),
                    MdSourceSnapshot(
                        id="source-2",
                        provider_id="provider-1",
                        platform="akshare",
                        source_id="stock_zh_a_hist",
                        adapter_id="akshare.stock.v1",
                        endpoint_version="v2",
                        request_fingerprint_sha256=_sha("request-2"),
                        payload_sha256=_sha("payload-2"),
                        request_json={},
                        payload_manifest_json={},
                        provenance_json={},
                        retrieved_at=available_at,
                    ),
                ]
            )
            session.add(
                MdObservationRevision(
                    id="observation-1",
                    series_id="series-1",
                    event_time=event_time,
                    event_end=available_at,
                    available_at=available_at,
                    source_snapshot_id="source-1",
                    quality_status="accepted",
                    quality_policy_version="quality-v1",
                    quality_details_json={"gates": ["schema", "calendar"]},
                    fields_json={"open": "10.0", "close": "10.5"},
                    fields_sha256=_sha("fields-1"),
                    revision_number=1,
                    revision_key_sha256=_sha("revision-1"),
                    normalization_version="normalization-v1",
                    source_record_key="600000/2026-09-08",
                    provenance_json={"raw_row": 7},
                    committed_at=available_at,
                )
            )
            session.commit()

        with Session(engine) as session:
            revision = session.scalar(
                select(MdObservationRevision).where(MdObservationRevision.id == "observation-1")
            )
            assert revision is not None
            assert revision.source_snapshot_id == "source-1"
            assert revision.quality_policy_version == "quality-v1"
            assert revision.fields_json["close"] == "10.5"

            revision.quality_status = "rejected"
            with pytest.raises(ImmutableMarketDataRecordError):
                session.flush()
            session.rollback()

        with Session(engine) as session:
            session.add(
                MdObservationRevision(
                    id="observation-duplicate",
                    series_id="series-1",
                    event_time=event_time,
                    event_end=available_at,
                    available_at=available_at,
                    source_snapshot_id="source-2",
                    quality_status="accepted",
                    quality_policy_version="quality-v1",
                    quality_details_json={},
                    fields_json={"open": "10.0", "close": "10.6"},
                    fields_sha256=_sha("fields-2"),
                    revision_number=1,
                    revision_key_sha256=_sha("revision-2"),
                    normalization_version="normalization-v1",
                    source_record_key="600000/2026-09-08",
                    provenance_json={},
                    committed_at=available_at,
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_versioned_calendar_snapshots_keep_distinct_session_events() -> None:
    """Calendar facts are versioned independently of a particular asset class."""
    from app.models.market_data_platform import MdCalendarEvent, MdCalendarSnapshot

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            snapshot = MdCalendarSnapshot(
                id="calendar-1",
                calendar_code="CN-SSE",
                calendar_version="2026.09.08",
                timezone_name="Asia/Shanghai",
                snapshot_sha256=_sha("calendar-1"),
                definition_json={"weekend": ["SAT", "SUN"]},
                effective_from=date(2026, 1, 1),
                effective_to=date(2026, 12, 31),
            )
            event = MdCalendarEvent(
                id="calendar-event-1",
                calendar_snapshot_id=snapshot.id,
                trading_date=date(2026, 9, 8),
                event_type="session",
                session_code="day",
                is_trading_day=True,
                event_start=datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc),
                event_end=datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc),
                event_payload_json={
                    "coverage": {"data_kind": "bars", "frequency": "1d"},
                    "open": "09:30",
                    "close": "15:00",
                },
                event_sha256=_sha("calendar-event-1"),
            )
            session.add_all([snapshot, event])
            session.commit()

        with Session(engine) as session:
            session.add(
                MdCalendarEvent(
                    id="calendar-event-duplicate",
                    calendar_snapshot_id="calendar-1",
                    trading_date=date(2026, 9, 8),
                    event_type="session",
                    session_code="day",
                    is_trading_day=True,
                    event_start=datetime(2026, 9, 8, 1, 30, tzinfo=timezone.utc),
                    event_end=datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc),
                    event_payload_json={"coverage": {"data_kind": "bars", "frequency": "1d"}},
                    event_sha256=_sha("calendar-event-duplicate"),
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_observation_migration_upgrades_and_downgrades_sqlite_without_legacy_rewrite(
    tmp_path: Path,
) -> None:
    """The expand-only migration adds normalized tables and leaves legacy facts untouched."""
    database_path = tmp_path / "market-data-observations.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = _config(database_url)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, CATALOG_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE legacy_market_facts "
                    "(symbol VARCHAR(32) NOT NULL, close NUMERIC NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO legacy_market_facts (symbol, close) VALUES ('600000', 10.5)")
            )

        command.upgrade(config, OBSERVATIONS_REVISION)
        inspector = inspect(engine)
        assert OBSERVATION_STORAGE_TABLES <= set(inspector.get_table_names())
        assert {
            "uq_md_instrument_lookup_key_active",
            "uq_md_data_series_semantic_key_sha256",
            "uq_md_observation_revision_series_event_number",
        } <= {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("md_observation_revisions")
            if constraint["name"]
        } | {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("md_data_series")
            if constraint["name"]
        } | {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("md_instrument_lookup_keys")
            if constraint["name"]
        }
        assert engine.connect().execute(
            text("SELECT symbol, close FROM legacy_market_facts")
        ).one() == (
            "600000",
            10.5,
        )

        command.downgrade(config, CATALOG_REVISION)
        assert not (OBSERVATION_STORAGE_TABLES & set(inspect(engine).get_table_names()))
        assert engine.connect().execute(
            text("SELECT symbol, close FROM legacy_market_facts")
        ).one() == (
            "600000",
            10.5,
        )
    finally:
        engine.dispose()


def test_observation_migration_rejects_same_named_wrong_column_contract(tmp_path: Path) -> None:
    """Evidence recovery verifies typed columns before it accepts a pre-created table."""
    database_path = tmp_path / "wrong-observation-columns.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, CATALOG_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE md_instrument_lookup_keys (
                        id VARCHAR(36) PRIMARY KEY,
                        asset_type INTEGER NULL,
                        market VARCHAR(128) NOT NULL,
                        symbol VARCHAR(128) NOT NULL,
                        instrument_id VARCHAR(36) NOT NULL,
                        canonical_id VARCHAR(512) NOT NULL,
                        metadata_version VARCHAR(64) NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        active_lookup_scope VARCHAR(16),
                        valid_from DATETIME NOT NULL,
                        valid_to DATETIME,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_OBSERVATIONS_PARTIAL_SCHEMA_UNSAFE",
        ) as unsafe:
            command.upgrade(config, OBSERVATIONS_REVISION)
    finally:
        engine.dispose()

    assert "invalid_columns" in str(unsafe.value)
    assert "asset_type" in str(unsafe.value)


def test_observation_revision_is_linear_child_of_catalog_revision() -> None:
    """The revision remains on the catalog branch and keeps a single Alembic head."""
    script = ScriptDirectory.from_config(_config("sqlite://"))

    revision = script.get_revision(OBSERVATIONS_REVISION)
    assert revision is not None
    assert revision.down_revision == CATALOG_REVISION
    assert len(script.get_heads()) == 1


def test_deferred_publications_revision_extends_the_integrated_storage_graph() -> None:
    """The release-hold child table extends the single integrated evidence graph."""
    script = ScriptDirectory.from_config(_config("sqlite://"))

    shared_revision = script.get_revision(SHARED_DATASET_BINDINGS_REVISION)
    visibility_revision = script.get_revision(VISIBILITY_ANCHOR_REVISION)
    source_receipt_evidence_revision = script.get_revision(SOURCE_RECEIPT_EVIDENCE_REVISION)
    source_governance_revision = script.get_revision(SOURCE_GOVERNANCE_REVISION)
    fetch_lease_revision = script.get_revision(FETCH_LEASE_REVISION)
    exact_identity_collation_revision = script.get_revision(EXACT_IDENTITY_COLLATION_REVISION)
    constraint_name_portability_revision = script.get_revision(CONSTRAINT_NAME_PORTABILITY_REVISION)
    merge_revision = script.get_revision(MERGE_REVISION)
    research_bindings_revision = script.get_revision(RESEARCH_BINDINGS_REVISION)
    research_binding_consumers_revision = script.get_revision(RESEARCH_BINDING_CONSUMERS_REVISION)
    shared_source_payloads_revision = script.get_revision(SHARED_SOURCE_PAYLOADS_REVISION)
    capability_ledger_revision = script.get_revision(CAPABILITY_LEDGER_REVISION)
    deferred_publications_revision = script.get_revision(DEFERRED_PUBLICATIONS_REVISION)
    integrated_head_revision = script.get_revision(INTEGRATED_HEAD_REVISION)
    assert shared_revision is not None
    assert shared_revision.down_revision == OBSERVATIONS_REVISION
    assert visibility_revision is not None
    assert visibility_revision.down_revision == SHARED_DATASET_BINDINGS_REVISION
    assert source_receipt_evidence_revision is not None
    assert source_receipt_evidence_revision.down_revision == VISIBILITY_ANCHOR_REVISION
    assert source_governance_revision is not None
    assert source_governance_revision.down_revision == SOURCE_RECEIPT_EVIDENCE_REVISION
    assert fetch_lease_revision is not None
    assert fetch_lease_revision.down_revision == SOURCE_GOVERNANCE_REVISION
    assert exact_identity_collation_revision is not None
    assert exact_identity_collation_revision.down_revision == FETCH_LEASE_REVISION
    assert constraint_name_portability_revision is not None
    assert constraint_name_portability_revision.down_revision == EXACT_IDENTITY_COLLATION_REVISION
    assert merge_revision is not None
    assert merge_revision.down_revision == (
        AI_RESEARCH_APPROVAL_REVISION,
        CONSTRAINT_NAME_PORTABILITY_REVISION,
    )
    assert research_bindings_revision is not None
    assert research_bindings_revision.down_revision == MERGE_REVISION
    assert research_binding_consumers_revision is not None
    assert research_binding_consumers_revision.down_revision == RESEARCH_BINDINGS_REVISION
    assert shared_source_payloads_revision is not None
    assert shared_source_payloads_revision.down_revision == RESEARCH_BINDING_CONSUMERS_REVISION
    assert capability_ledger_revision is not None
    assert capability_ledger_revision.down_revision == SHARED_SOURCE_PAYLOADS_REVISION
    assert deferred_publications_revision is not None
    assert deferred_publications_revision.down_revision == CAPABILITY_LEDGER_REVISION
    assert integrated_head_revision is not None
    assert integrated_head_revision.down_revision == CAPABILITY_LEDGER_REVISION
    assert script.get_heads() == [INTEGRATED_HEAD_REVISION]


def test_shared_source_payload_migration_adds_child_evidence_without_parent_rewrite(
    tmp_path: Path,
) -> None:
    """A populated SQLite source parent upgrades with foreign keys enabled."""
    database_path = tmp_path / "market-data-shared-source-payloads.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    receipt_at = datetime(2026, 9, 10, 9, tzinfo=timezone.utc)
    try:
        command.upgrade(config, RESEARCH_BINDING_CONSUMERS_REVISION)
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.execute(
                text(
                    "INSERT INTO dg_providers "
                    "(id, provider_id, name, category, auth_type, rate_limit, is_active, created_at) "
                    "VALUES ('provider-shared-payload', 'akshare', 'AkShare', 'market', "
                    "'none', 60, 1, :now)"
                ),
                {"now": receipt_at},
            )
            connection.execute(
                text(
                    "INSERT INTO md_source_snapshots "
                    "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                    "request_fingerprint_sha256, payload_sha256, request_json, "
                    "payload_manifest_json, provenance_json, retrieved_at, created_at) "
                    "VALUES ('snapshot-shared-payload', 'provider-shared-payload', 'akshare', "
                    "'akshare', 'akshare.market-data', 'v1', :query_hash, :payload_hash, "
                    "'{}', '{}', '{}', :now, :now)"
                ),
                {
                    "query_hash": _sha("shared-payload-query"),
                    "payload_hash": _sha("shared-payload-receipt"),
                    "now": receipt_at,
                },
            )
        source_columns_before = {
            column["name"] for column in inspect(engine).get_columns("md_source_snapshots")
        }

        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            config.attributes["connection"] = connection
            command.upgrade(config, SHARED_SOURCE_PAYLOADS_REVISION)
        config.attributes.pop("connection", None)

        inspector = inspect(engine)
        assert source_columns_before == {
            column["name"] for column in inspector.get_columns("md_source_snapshots")
        }
        assert {"md_source_payloads", "md_source_snapshot_payload_refs"} <= set(
            inspector.get_table_names()
        )
        assert {
            "content_sha256",
            "payload_format",
            "canonical_payload_bytes",
            "payload_bytes",
            "created_at",
        } == {column["name"] for column in inspector.get_columns("md_source_payloads")}
        assert {
            "source_snapshot_id",
            "content_sha256",
            "payload_role",
            "created_at",
        } == {column["name"] for column in inspector.get_columns("md_source_snapshot_payload_refs")}
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM md_source_snapshots WHERE id = 'snapshot-shared-payload'"
                    )
                ).scalar_one()
                == 1
            )

        payload_hash = _sha("shared-payload-blob")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO md_source_payloads "
                    "(content_sha256, payload_format, canonical_payload_bytes, payload_bytes, created_at) "
                    "VALUES (:hash, 'canonical-json-utf8-v1', :payload, 2, :now)"
                ),
                {"hash": payload_hash, "payload": b"{}", "now": receipt_at},
            )
            connection.execute(
                text(
                    "INSERT INTO md_source_snapshot_payload_refs "
                    "(source_snapshot_id, content_sha256, payload_role, created_at) "
                    "VALUES ('snapshot-shared-payload', :hash, 'source_batch', :now)"
                ),
                {"hash": payload_hash, "now": receipt_at},
            )
        with pytest.raises(
            RuntimeError, match="MARKET_DATA_SHARED_SOURCE_PAYLOAD_DOWNGRADE_BLOCKED"
        ):
            command.downgrade(config, RESEARCH_BINDING_CONSUMERS_REVISION)
    finally:
        config.attributes.pop("connection", None)
        engine.dispose()


@pytest.mark.parametrize(
    ("wrong_binary_type", "wrong_type_name"),
    [(mysql.BLOB(), "BLOB"), (mysql.LONGBLOB(), "LONGBLOB")],
)
def test_shared_source_payload_migration_rejects_mysql_binary_payload_schema_drift(
    monkeypatch: pytest.MonkeyPatch,
    wrong_binary_type: sa.types.TypeEngine[object],
    wrong_type_name: str,
) -> None:
    """MySQL BLOB widths cannot masquerade as the required MEDIUMBLOB."""
    migration = _load_shared_source_payloads_migration()
    dialect = mysql.dialect()

    class _Inspector:
        def has_table(self, table_name: str) -> bool:
            return table_name in migration._TABLE_SPECS

        def get_columns(self, table_name: str) -> list[dict[str, object]]:
            spec = migration._TABLE_SPECS[table_name]
            columns = spec["columns"]
            assert isinstance(columns, dict)
            rendered: list[dict[str, object]] = []
            for column_name, definition in columns.items():
                expected_type, nullable = definition
                assert isinstance(expected_type, sa.types.TypeEngine)
                actual_type = expected_type.dialect_impl(dialect)
                if table_name == migration._PAYLOADS and column_name == "canonical_payload_bytes":
                    actual_type = wrong_binary_type
                rendered.append(
                    {
                        "name": column_name,
                        "type": actual_type,
                        "nullable": nullable,
                        "default": None,
                    }
                )
            return rendered

        def get_pk_constraint(self, table_name: str) -> dict[str, object]:
            spec = migration._TABLE_SPECS[table_name]
            return {"constrained_columns": spec["primary_key"]}

        def get_check_constraints(self, table_name: str) -> list[dict[str, object]]:
            spec = migration._TABLE_SPECS[table_name]
            checks = spec["checks"]
            assert isinstance(checks, dict)
            return [{"name": name, "sqltext": expression} for name, expression in checks.items()]

        def get_indexes(self, table_name: str) -> list[dict[str, object]]:
            spec = migration._TABLE_SPECS[table_name]
            indexes = spec["indexes"]
            assert isinstance(indexes, dict)
            return [
                {"name": name, "column_names": columns, "unique": unique}
                for name, (columns, unique) in indexes.items()
            ]

        def get_foreign_keys(self, table_name: str) -> list[dict[str, object]]:
            spec = migration._TABLE_SPECS[table_name]
            foreign_keys = spec["foreign_keys"]
            assert isinstance(foreign_keys, dict)
            return [
                {
                    "name": name,
                    "constrained_columns": columns,
                    "referred_table": referred_table,
                    "referred_columns": referred_columns,
                    "options": {"ondelete": ondelete},
                }
                for name, (
                    columns,
                    referred_table,
                    referred_columns,
                    ondelete,
                ) in foreign_keys.items()
            ]

    bind = SimpleNamespace(dialect=dialect)
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: _Inspector())

    with pytest.raises(
        RuntimeError, match="MARKET_DATA_SHARED_SOURCE_PAYLOAD_SCHEMA_DRIFT"
    ) as drift:
        migration._require_absent_or_exact_tables(bind)

    assert "canonical_payload_bytes" in str(drift.value)
    assert "MEDIUMBLOB" in str(drift.value)
    assert wrong_type_name in str(drift.value)


def test_shared_source_payload_downgrade_locks_postgresql_evidence_before_empty_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL writers cannot insert evidence between proof and DROP."""
    migration = _load_shared_source_payloads_migration()
    calls: list[str] = []

    class _PostgresBind:
        dialect = postgresql.dialect()

        def execute(self, statement: object, *_args: object, **_kwargs: object) -> None:
            calls.append(str(statement))

    bind = _PostgresBind()

    def _assert_empty(observed_bind: object) -> None:
        assert observed_bind is bind
        calls.append("EMPTY_CHECK")

    monkeypatch.setattr(migration, "_is_offline", lambda: False)
    monkeypatch.setattr(migration, "_require_absent_or_exact_tables", lambda _bind: True)
    monkeypatch.setattr(migration, "_assert_downgrade_safe", _assert_empty)
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=lambda: bind,
            drop_index=lambda *_args, **_kwargs: calls.append("DROP_INDEX"),
            drop_table=lambda table_name: calls.append(f"DROP_TABLE:{table_name}"),
        ),
    )

    migration.downgrade()

    lock_statement = (
        "LOCK TABLE md_source_payloads, md_source_snapshot_payload_refs IN ACCESS EXCLUSIVE MODE"
    )
    assert "SET LOCAL lock_timeout = '5s'" in calls
    assert lock_statement in calls
    assert calls.index(lock_statement) < calls.index("EMPTY_CHECK")
    assert calls[-3:] == [
        "DROP_INDEX",
        "DROP_TABLE:md_source_snapshot_payload_refs",
        "DROP_TABLE:md_source_payloads",
    ]


def test_capability_ledger_downgrade_locks_postgresql_before_empty_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL attestation writers cannot race an empty-table proof."""
    migration = _load_capability_ledger_migration()
    calls: list[str] = []

    class _PostgresBind:
        dialect = postgresql.dialect()

        def execute(self, statement: object, *_args: object, **_kwargs: object) -> None:
            calls.append(str(statement))

    bind = _PostgresBind()

    def _assert_empty(observed_bind: object) -> None:
        assert observed_bind is bind
        calls.append("EMPTY_CHECK")

    monkeypatch.setattr(migration, "_is_offline", lambda: False)
    monkeypatch.setattr(migration, "_require_absent_or_exact_table", lambda _bind: True)
    monkeypatch.setattr(migration, "_assert_downgrade_safe", _assert_empty)
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=lambda: bind,
            drop_index=lambda *_args, **_kwargs: calls.append("DROP_INDEX"),
            drop_table=lambda table_name: calls.append(f"DROP_TABLE:{table_name}"),
        ),
    )

    migration.downgrade()

    lock_statement = "LOCK TABLE md_capability_ledger_entries IN ACCESS EXCLUSIVE MODE"
    assert "SET LOCAL lock_timeout = '5s'" in calls
    assert lock_statement in calls
    assert calls.index(lock_statement) < calls.index("EMPTY_CHECK")
    assert calls[-2:] == ["DROP_INDEX", "DROP_TABLE:md_capability_ledger_entries"]


def test_capability_ledger_downgrade_refuses_mysql_before_empty_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MySQL implicit DDL commits cannot safely erase an append-only ledger."""
    migration = _load_capability_ledger_migration()
    calls: list[str] = []

    class _MySqlBind:
        dialect = mysql.dialect()

    bind = _MySqlBind()
    monkeypatch.setattr(migration, "_is_offline", lambda: False)
    monkeypatch.setattr(
        migration,
        "_require_absent_or_exact_table",
        lambda _bind: calls.append("SCHEMA_CHECK") or True,
    )
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=lambda: bind,
            drop_index=lambda *_args, **_kwargs: calls.append("DROP_INDEX"),
            drop_table=lambda table_name: calls.append(f"DROP_TABLE:{table_name}"),
        ),
    )

    with pytest.raises(RuntimeError, match="MARKET_DATA_CAPABILITY_LEDGER_DOWNGRADE_BLOCKED"):
        migration.downgrade()

    assert calls == []


def test_fetch_lease_downgrade_refuses_mysql_before_empty_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MySQL cannot atomically prove issued lease evidence remains absent."""
    migration = _load_fetch_lease_migration()
    calls: list[str] = []

    class _MySqlBind:
        dialect = mysql.dialect()

    bind = _MySqlBind()
    monkeypatch.setattr(migration, "_is_offline", lambda: False)
    monkeypatch.setattr(
        migration,
        "_assert_source_binding_downgrade_safe",
        lambda _bind: calls.append("SOURCE_BINDING_CHECK"),
    )
    monkeypatch.setattr(
        migration,
        "_assert_downgrade_safe",
        lambda _bind: calls.append("LEASE_CHECK"),
    )
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=lambda: bind,
            drop_index=lambda *_args, **_kwargs: calls.append("DROP_INDEX"),
            drop_table=lambda table_name: calls.append(f"DROP_TABLE:{table_name}"),
        ),
    )

    with pytest.raises(RuntimeError, match="MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED"):
        migration.downgrade()

    assert calls == []


def test_fetch_lease_downgrade_locks_postgresql_before_empty_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL writers cannot add lease evidence after the checks begin."""
    migration = _load_fetch_lease_migration()
    calls: list[str] = []

    class _PostgresBind:
        dialect = postgresql.dialect()

        def execute(self, statement: object, *_args: object, **_kwargs: object) -> None:
            calls.append(str(statement))

    class _Inspector:
        def has_table(self, table_name: str) -> bool:
            return table_name in {migration._SOURCE_SNAPSHOTS, migration._TABLE}

    bind = _PostgresBind()
    monkeypatch.setattr(migration, "_is_offline", lambda: False)
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: _Inspector())
    monkeypatch.setattr(
        migration,
        "_assert_source_binding_downgrade_safe",
        lambda _bind: calls.append("SOURCE_BINDING_CHECK"),
    )
    monkeypatch.setattr(
        migration,
        "_assert_downgrade_safe",
        lambda _bind: calls.append("LEASE_CHECK"),
    )
    monkeypatch.setattr(
        migration,
        "_drop_source_binding_columns_and_constraint",
        lambda _bind: calls.append("DROP_SOURCE_BINDING_COLUMNS"),
    )
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(
            get_bind=lambda: bind,
            drop_index=lambda *_args, **_kwargs: calls.append("DROP_INDEX"),
            drop_table=lambda table_name: calls.append(f"DROP_TABLE:{table_name}"),
        ),
    )

    migration.downgrade()

    lock_statement = "LOCK TABLE md_source_snapshots, md_fetch_leases IN ACCESS EXCLUSIVE MODE"
    assert "SET LOCAL lock_timeout = '5s'" in calls
    assert lock_statement in calls
    assert calls.index(lock_statement) < calls.index("SOURCE_BINDING_CHECK")
    assert calls.index(lock_statement) < calls.index("LEASE_CHECK")
    assert calls[-3:] == [
        "DROP_SOURCE_BINDING_COLUMNS",
        "DROP_INDEX",
        "DROP_TABLE:md_fetch_leases",
    ]


def test_capability_ledger_migration_blocks_nonempty_sqlite_downgrade(
    tmp_path: Path,
) -> None:
    """A durable ledger entry remains intact when rollback is requested."""
    database_path = tmp_path / "market-data-capability-ledger.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    observed_at = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    expires_at = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
    try:
        command.upgrade(config, INTEGRATED_HEAD_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO md_capability_ledger_entries ("
                    "id, capability_id, revision, descriptor_sha256, evidence_sha256, "
                    "declared_capability, installed_capability, verified_capability, "
                    "verified_at, verified_until, authorized_capability, authorized_at, "
                    "authorized_until, effective_from, effective_until, created_at"
                    ") VALUES ("
                    ":id, :capability_id, :revision, :descriptor_sha256, :evidence_sha256, "
                    ":declared_capability, :installed_capability, :verified_capability, "
                    ":verified_at, :verified_until, :authorized_capability, :authorized_at, "
                    ":authorized_until, :effective_from, :effective_until, :created_at"
                    ")"
                ),
                {
                    "id": "capability-ledger-entry-1",
                    "capability_id": "market-data.query-v2",
                    "revision": 1,
                    "descriptor_sha256": _sha("descriptor"),
                    "evidence_sha256": _sha("evidence"),
                    "declared_capability": True,
                    "installed_capability": True,
                    "verified_capability": True,
                    "verified_at": observed_at,
                    "verified_until": expires_at,
                    "authorized_capability": True,
                    "authorized_at": observed_at,
                    "authorized_until": expires_at,
                    "effective_from": observed_at,
                    "effective_until": expires_at,
                    "created_at": observed_at,
                },
            )

        with pytest.raises(RuntimeError, match="MARKET_DATA_CAPABILITY_LEDGER_DOWNGRADE_BLOCKED"):
            command.downgrade(config, SHARED_SOURCE_PAYLOADS_REVISION)

        assert inspect(engine).has_table("md_capability_ledger_entries")
    finally:
        engine.dispose()


def test_exact_identity_collation_migration_accepts_sqlite_binary_defaults_and_blocks_evidence_rollback(
    tmp_path: Path,
) -> None:
    """SQLite defaults are binary; semantic rollback is deliberately refused."""
    database_path = tmp_path / "market-data-exact-identity.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, FETCH_LEASE_REVISION)
        command.upgrade(config, EXACT_IDENTITY_COLLATION_REVISION)
        with engine.connect() as connection:
            table_sql = {
                table_name: connection.execute(
                    text(
                        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :table_name"
                    ),
                    {"table_name": table_name},
                ).scalar_one()
                for table_name in ("md_instrument_identity_revisions", "md_instrument_lookup_keys")
            }
        assert all("COLLATE NOCASE" not in sql.upper() for sql in table_sql.values())
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO md_instrument_identity_revisions "
                    "(id, instrument_id, canonical_id, asset_type, market, symbol, metadata_version, "
                    "identity_json, valid_from, revision_number, revision_sha256, created_at) "
                    "VALUES ('identity-revision-1', 'instrument-1', 'instrument:stock:CN-SSE:RB0', "
                    "'stock', 'CN-SSE', 'RB0', 'v1', '{}', '2026-09-09 00:00:00', 1, :digest, "
                    "'2026-09-09 00:00:00')"
                ),
                {"digest": _sha("identity-revision-1")},
            )
        with pytest.raises(RuntimeError, match="MARKET_DATA_EXACT_IDENTITY_DOWNGRADE_BLOCKED"):
            command.downgrade(config, FETCH_LEASE_REVISION)
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM md_instrument_identity_revisions"))
        command.downgrade(config, FETCH_LEASE_REVISION)
    finally:
        engine.dispose()


def test_visibility_anchor_migration_backfills_global_receipt_order(tmp_path: Path) -> None:
    """Pre-existing sealed receipts gain a stable sequence and allocator seed."""
    database_path = tmp_path / "market-data-visibility-anchor.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, SHARED_DATASET_BINDINGS_REVISION)
        first_visible_at = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
        second_visible_at = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO md_publications "
                    "(id, entity_type, entity_id, entity_sha256, published_at, created_at) "
                    "VALUES (:id, 'source_snapshot', :entity_id, :digest, :published_at, :created_at)"
                ),
                [
                    {
                        "id": "receipt-later-id",
                        "entity_id": "entity-later-id",
                        "digest": _sha("receipt-later-id"),
                        "published_at": second_visible_at,
                        "created_at": second_visible_at,
                    },
                    {
                        "id": "receipt-earlier-id",
                        "entity_id": "entity-earlier-id",
                        "digest": _sha("receipt-earlier-id"),
                        "published_at": first_visible_at,
                        "created_at": first_visible_at,
                    },
                ],
            )

        command.upgrade(config, VISIBILITY_ANCHOR_REVISION)
        inspector = inspect(engine)
        assert "visibility_sequence" in {
            column["name"] for column in inspector.get_columns("md_publications")
        }
        assert "md_visibility_sequence_allocator" in inspector.get_table_names()
        assert {
            "uq_md_publication_visibility_sequence",
            "ix_md_publication_visible_anchor",
        } <= {index["name"] for index in inspector.get_indexes("md_publications")}
        assert "ck_md_publication_visibility_sequence_positive" in {
            constraint["name"] for constraint in inspector.get_check_constraints("md_publications")
        }
        assert "ck_md_publication_visibility_state" in {
            constraint["name"] for constraint in inspector.get_check_constraints("md_publications")
        }
        with engine.connect() as connection:
            receipts = connection.execute(
                text(
                    "SELECT id, visibility_sequence FROM md_publications "
                    "ORDER BY visibility_sequence"
                )
            ).all()
            allocator = connection.execute(
                text(
                    "SELECT singleton_id, next_visibility_sequence "
                    "FROM md_visibility_sequence_allocator"
                )
            ).one()
        assert receipts == [("receipt-earlier-id", 1), ("receipt-later-id", 2)]
        assert allocator == (1, 3)

        # A rollback would discard the only durable tie-breaker for these two
        # immutable receipts.  The migration must fail before it drops any
        # derived table, constraint, or column.
        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_VISIBILITY_ANCHOR_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, SHARED_DATASET_BINDINGS_REVISION)
        assert "md_visibility_sequence_allocator" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_source_receipt_evidence_migration_preserves_legacy_receipts_and_blocks_evidence_loss(
    tmp_path: Path,
) -> None:
    """The expansion leaves legacy rows NULL and never permits evidence-dropping rollback."""
    database_path = tmp_path / "market-data-source-receipt-evidence.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, VISIBILITY_ANCHOR_REVISION)
        receipt_at = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dg_providers "
                    "(id, provider_id, name, category, auth_type, rate_limit, is_active, created_at) "
                    "VALUES ('provider-legacy', 'akshare', 'AkShare', 'market', 'none', 60, 1, :now)"
                ),
                {"now": receipt_at},
            )
            connection.execute(
                text(
                    "INSERT INTO md_source_snapshots "
                    "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                    "request_fingerprint_sha256, payload_sha256, request_json, payload_manifest_json, "
                    "provenance_json, retrieved_at, created_at) "
                    "VALUES ('snapshot-legacy', 'provider-legacy', 'akshare', 'akshare', "
                    "'akshare.market-data', 'v1', :query_hash, :payload_hash, '{}', '{}', '{}', "
                    ":now, :now)"
                ),
                {
                    "query_hash": _sha("legacy-public-query"),
                    "payload_hash": _sha("legacy-payload"),
                    "now": receipt_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO md_source_snapshots "
                    "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                    "request_fingerprint_sha256, payload_sha256, request_json, payload_manifest_json, "
                    "provenance_json, retrieved_at, created_at) "
                    "VALUES ('snapshot-legacy-null', 'provider-legacy', 'akshare', 'akshare', "
                    "'akshare.market-data', 'v1', :query_hash, :payload_hash, '{}', '{}', '{}', "
                    ":now, :now)"
                ),
                {
                    "query_hash": _sha("legacy-public-query-second-null"),
                    "payload_hash": _sha("legacy-payload-second-null"),
                    "now": receipt_at,
                },
            )

        command.upgrade(config, SOURCE_RECEIPT_EVIDENCE_REVISION)
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("md_source_snapshots")}
        assert {
            "provider_request_id",
            "provider_request_fingerprint_sha256",
            "query_fingerprint_sha256",
        } <= columns
        request_id_index = next(
            index
            for index in inspector.get_indexes("md_source_snapshots")
            if index["name"] == "ix_md_source_snapshot_provider_request_id"
        )
        assert tuple(request_id_index["column_names"]) == (
            "provider_id",
            "provider_request_id",
        )
        assert bool(request_id_index["unique"])
        assert {
            "ck_md_source_snapshot_provider_request_id_length",
            "ck_md_srcsnap_provider_req_fp_sha256_len",
            "ck_md_source_snapshot_query_fingerprint_sha256_length",
            "ck_md_source_snapshot_provider_request_evidence_state",
        } <= {
            constraint["name"]
            for constraint in inspector.get_check_constraints("md_source_snapshots")
            if constraint["name"]
        }
        with engine.connect() as connection:
            legacy = connection.execute(
                text(
                    "SELECT request_fingerprint_sha256, provider_request_id, "
                    "provider_request_fingerprint_sha256, query_fingerprint_sha256 "
                    "FROM md_source_snapshots WHERE id = 'snapshot-legacy'"
                )
            ).one()
            legacy_null_count = connection.execute(
                text(
                    "SELECT count(*) FROM md_source_snapshots "
                    "WHERE provider_id = 'provider-legacy' AND provider_request_id IS NULL"
                )
            ).scalar_one()
        assert legacy == (_sha("legacy-public-query"), None, None, None)
        assert legacy_null_count == 2

        provider_request_id = "a" * 32
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE md_source_snapshots SET "
                    "provider_request_id = :request_id, "
                    "provider_request_fingerprint_sha256 = :request_hash, "
                    "query_fingerprint_sha256 = :query_hash "
                    "WHERE id = 'snapshot-legacy'"
                ),
                {
                    "request_id": provider_request_id,
                    "request_hash": _sha("provider-request"),
                    "query_hash": _sha("explicit-public-query"),
                },
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO md_source_snapshots "
                        "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                        "request_fingerprint_sha256, provider_request_id, "
                        "provider_request_fingerprint_sha256, query_fingerprint_sha256, "
                        "payload_sha256, request_json, payload_manifest_json, provenance_json, "
                        "retrieved_at, created_at) "
                        "VALUES ('snapshot-duplicate-provider-request', 'provider-legacy', "
                        "'akshare', 'akshare', 'akshare.market-data', 'v1', :request_fingerprint, "
                        ":provider_request_id, :provider_request_fingerprint, :query_fingerprint, "
                        ":payload_hash, '{}', '{}', '{}', :now, :now)"
                    ),
                    {
                        "request_fingerprint": _sha("duplicate-public-query"),
                        "provider_request_id": provider_request_id,
                        "provider_request_fingerprint": _sha("duplicate-provider-request"),
                        "query_fingerprint": _sha("duplicate-explicit-public-query"),
                        "payload_hash": _sha("duplicate-payload"),
                        "now": receipt_at,
                    },
                )
        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, VISIBILITY_ANCHOR_REVISION)
    finally:
        engine.dispose()


def test_source_receipt_evidence_migration_accepts_complete_startup_created_schema(
    tmp_path: Path,
) -> None:
    """A complete ORM startup schema is accepted instead of replaying incompatible DDL."""
    database_path = tmp_path / "market-data-source-receipt-startup.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        # Import registration is explicit so this remains a true create_all
        # compatibility probe regardless of test collection order.
        import app.models.market_data_platform  # noqa: F401

        Base.metadata.create_all(engine)
        command.stamp(config, VISIBILITY_ANCHOR_REVISION)
        command.upgrade(config, SOURCE_RECEIPT_EVIDENCE_REVISION)

        assert {
            "provider_request_id",
            "provider_request_fingerprint_sha256",
            "query_fingerprint_sha256",
        } <= {column["name"] for column in inspect(engine).get_columns("md_source_snapshots")}
    finally:
        engine.dispose()


def test_source_governance_migration_preserves_legacy_rows_and_blocks_evidence_loss(
    tmp_path: Path,
) -> None:
    """Legacy receipts stay NULL while governed source state can never be dropped."""
    database_path = tmp_path / "market-data-source-governance.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, SOURCE_RECEIPT_EVIDENCE_REVISION)
        receipt_at = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dg_providers "
                    "(id, provider_id, name, category, auth_type, rate_limit, is_active, created_at) "
                    "VALUES ('provider-governance', 'akshare', 'AkShare', 'market', 'none', 60, 1, :now)"
                ),
                {"now": receipt_at},
            )
            connection.execute(
                text(
                    "INSERT INTO md_source_snapshots "
                    "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                    "request_fingerprint_sha256, payload_sha256, request_json, payload_manifest_json, "
                    "provenance_json, retrieved_at, created_at) "
                    "VALUES ('snapshot-governance-legacy', 'provider-governance', 'akshare', 'akshare', "
                    "'akshare.market-data', 'v1', :query_hash, :payload_hash, '{}', '{}', '{}', "
                    ":now, :now)"
                ),
                {
                    "query_hash": _sha("governance-legacy-public-query"),
                    "payload_hash": _sha("governance-legacy-payload"),
                    "now": receipt_at,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO md_calendar_snapshots "
                    "(id, calendar_code, calendar_version, timezone_name, snapshot_sha256, "
                    "definition_json, effective_from, effective_to, created_at) "
                    "VALUES ('calendar-governance-legacy', 'CN-SSE', '2026.09', 'Asia/Shanghai', "
                    ":snapshot_hash, '{}', '2026-01-01', '2026-12-31', :now)"
                ),
                {"snapshot_hash": _sha("calendar-governance-legacy"), "now": receipt_at},
            )

        command.upgrade(config, SOURCE_GOVERNANCE_REVISION)
        inspector = inspect(engine)
        source_columns = {column["name"] for column in inspector.get_columns("md_source_snapshots")}
        calendar_columns = {
            column["name"] for column in inspector.get_columns("md_calendar_snapshots")
        }
        assert {
            "source_authorization_state",
            "source_authorization_descriptor_sha256",
        } <= source_columns
        assert {
            "source_registry_id",
            "source_governance_state",
            "source_governance_descriptor_sha256",
        } <= calendar_columns
        assert "ix_md_calendar_snapshot_source_registry" in {
            index["name"] for index in inspector.get_indexes("md_calendar_snapshots")
        }
        assert {
            "ck_md_source_snapshot_source_authorization_state",
            "ck_md_srcsnap_src_auth_desc_sha256_len",
            "ck_md_source_snapshot_source_authorization_evidence_state",
        } <= {
            constraint["name"]
            for constraint in inspector.get_check_constraints("md_source_snapshots")
            if constraint["name"]
        }
        assert {
            "ck_md_calendar_snapshot_source_registry_id_length",
            "ck_md_calendar_snapshot_source_governance_state",
            "ck_md_calsnap_src_gov_desc_sha256_len",
            "ck_md_calendar_snapshot_source_governance_evidence_state",
        } <= {
            constraint["name"]
            for constraint in inspector.get_check_constraints("md_calendar_snapshots")
            if constraint["name"]
        }
        with engine.connect() as connection:
            legacy_source = connection.execute(
                text(
                    "SELECT source_authorization_state, source_authorization_descriptor_sha256 "
                    "FROM md_source_snapshots WHERE id = 'snapshot-governance-legacy'"
                )
            ).one()
            legacy_calendar = connection.execute(
                text(
                    "SELECT source_registry_id, source_governance_state, "
                    "source_governance_descriptor_sha256 FROM md_calendar_snapshots "
                    "WHERE id = 'calendar-governance-legacy'"
                )
            ).one()
        assert legacy_source == (None, None)
        assert legacy_calendar == (None, None, None)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE md_source_snapshots SET "
                    "source_authorization_state = 'UNVERIFIED_COMPATIBILITY' "
                    "WHERE id = 'snapshot-governance-legacy'"
                )
            )
            connection.execute(
                text(
                    "UPDATE md_calendar_snapshots SET source_registry_id = 'akshare', "
                    "source_governance_state = 'VERIFIED', "
                    "source_governance_descriptor_sha256 = :descriptor_hash "
                    "WHERE id = 'calendar-governance-legacy'"
                ),
                {"descriptor_hash": _sha("calendar-governance-descriptor")},
            )
        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_SOURCE_GOVERNANCE_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, SOURCE_RECEIPT_EVIDENCE_REVISION)
    finally:
        engine.dispose()


def test_fetch_lease_migration_creates_fenced_schema_and_blocks_generation_loss(
    tmp_path: Path,
) -> None:
    """Issued fencing generations are never silently deleted by downgrade."""
    database_path = tmp_path / "market-data-fetch-leases.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    now = datetime(2026, 9, 9, 9, tzinfo=timezone.utc)
    try:
        command.upgrade(config, FETCH_LEASE_REVISION)

        inspector = inspect(engine)
        assert "md_fetch_leases" in inspector.get_table_names()
        assert {
            "lease_key_sha256",
            "owner_token",
            "fence_token",
            "expires_at",
            "created_at",
            "updated_at",
            "released_at",
        } == {column["name"] for column in inspector.get_columns("md_fetch_leases")}
        assert "ix_md_fetch_lease_expires_at" in {
            index["name"] for index in inspector.get_indexes("md_fetch_leases")
        }
        assert {
            "ck_md_fetch_lease_key_sha256_length",
            "ck_md_fetch_lease_fence_token_positive",
            "ck_md_fetch_lease_owner_expiry_state",
        } <= {
            constraint["name"]
            for constraint in inspector.get_check_constraints("md_fetch_leases")
            if constraint["name"]
        }

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dg_providers "
                    "(id, provider_id, name, category, auth_type, rate_limit, is_active, created_at) "
                    "VALUES ('provider-fetch-lease', 'akshare', 'AkShare', 'market', 'none', 60, 1, :now)"
                ),
                {"now": now},
            )
            connection.execute(
                text(
                    "INSERT INTO md_source_snapshots "
                    "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
                    "request_fingerprint_sha256, payload_sha256, request_json, payload_manifest_json, "
                    "provenance_json, retrieved_at, created_at) "
                    "VALUES ('snapshot-fetch-lease', 'provider-fetch-lease', 'akshare', 'akshare', "
                    "'akshare.market-data', 'v1', :query_hash, :payload_hash, '{}', '{}', '{}', "
                    ":now, :now)"
                ),
                {
                    "query_hash": _sha("fetch-lease-public-query"),
                    "payload_hash": _sha("fetch-lease-payload"),
                    "now": now,
                },
            )

        source_columns = {column["name"] for column in inspector.get_columns("md_source_snapshots")}
        assert {"fetch_lease_key_sha256", "fetch_lease_fence_token"} <= source_columns
        assert "ck_md_source_snapshot_fetch_lease_generation_state" in {
            constraint["name"]
            for constraint in inspector.get_check_constraints("md_source_snapshots")
            if constraint["name"]
        }

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE md_source_snapshots SET fetch_lease_fence_token = 7 "
                        "WHERE id = 'snapshot-fetch-lease'"
                    )
                )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE md_source_snapshots SET fetch_lease_key_sha256 = :key, "
                    "fetch_lease_fence_token = 7 WHERE id = 'snapshot-fetch-lease'"
                ),
                {"key": _sha("source-receipt-fetch-lease")},
            )

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, SOURCE_GOVERNANCE_REVISION)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO md_fetch_leases "
                    "(lease_key_sha256, owner_token, fence_token, expires_at, "
                    "created_at, updated_at, released_at) "
                    "VALUES (:key, 'owner-1', 7, :expires_at, :now, :now, NULL)"
                ),
                {"key": _sha("issued-fetch-lease"), "expires_at": now, "now": now},
            )

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_FETCH_LEASE_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, SOURCE_GOVERNANCE_REVISION)
    finally:
        engine.dispose()


def test_source_governance_migration_accepts_complete_startup_created_schema(
    tmp_path: Path,
) -> None:
    """The migration accepts the complete current ORM schema without replaying DDL."""
    database_path = tmp_path / "market-data-source-governance-startup.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        import app.models.market_data_platform  # noqa: F401

        Base.metadata.create_all(engine)
        command.stamp(config, SOURCE_RECEIPT_EVIDENCE_REVISION)
        command.upgrade(config, SOURCE_GOVERNANCE_REVISION)

        source_columns = {
            column["name"] for column in inspect(engine).get_columns("md_source_snapshots")
        }
        calendar_columns = {
            column["name"] for column in inspect(engine).get_columns("md_calendar_snapshots")
        }
        assert {
            "source_authorization_state",
            "source_authorization_descriptor_sha256",
        } <= source_columns
        assert {
            "source_registry_id",
            "source_governance_state",
            "source_governance_descriptor_sha256",
        } <= calendar_columns
    finally:
        engine.dispose()


def test_fetch_lease_migration_accepts_complete_startup_created_schema(
    tmp_path: Path,
) -> None:
    """Startup metadata cannot cause the durable-fencing migration to replay DDL."""
    database_path = tmp_path / "market-data-fetch-lease-startup.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        import app.models.market_data_platform  # noqa: F401

        Base.metadata.create_all(engine)
        command.stamp(config, SOURCE_GOVERNANCE_REVISION)
        command.upgrade(config, FETCH_LEASE_REVISION)

        inspector = inspect(engine)
        assert "md_fetch_leases" in inspector.get_table_names()
        assert "ix_md_fetch_lease_expires_at" in {
            index["name"] for index in inspector.get_indexes("md_fetch_leases")
        }
        assert {"fetch_lease_key_sha256", "fetch_lease_fence_token"} <= {
            column["name"] for column in inspector.get_columns("md_source_snapshots")
        }
        assert "ck_md_source_snapshot_fetch_lease_generation_state" in {
            constraint["name"]
            for constraint in inspector.get_check_constraints("md_source_snapshots")
            if constraint["name"]
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("owner_token_definition", "fence_check"),
    [
        ("VARCHAR(64) NOT NULL", "fence_token >= 1"),
        ("VARCHAR(64)", "fence_token >= 0"),
    ],
    ids=["non-nullable-owner", "weakened-fence-check"],
)
def test_fetch_lease_migration_rejects_weakened_same_name_startup_schema(
    tmp_path: Path,
    owner_token_definition: str,
    fence_check: str,
) -> None:
    """A same-named lease table cannot bypass fencing with weakened DDL."""
    database_path = tmp_path / "market-data-fetch-leases-schema-drift.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, SOURCE_GOVERNANCE_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    CREATE TABLE md_fetch_leases (
                        lease_key_sha256 VARCHAR(64) NOT NULL PRIMARY KEY,
                        owner_token {owner_token_definition},
                        fence_token BIGINT NOT NULL,
                        expires_at DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        released_at DATETIME,
                        CONSTRAINT ck_md_fetch_lease_key_sha256_length
                            CHECK (length(lease_key_sha256) = 64),
                        CONSTRAINT ck_md_fetch_lease_fence_token_positive
                            CHECK ({fence_check}),
                        CONSTRAINT ck_md_fetch_lease_owner_expiry_state
                            CHECK (
                                (owner_token IS NULL AND expires_at IS NULL) OR
                                (owner_token IS NOT NULL AND expires_at IS NOT NULL)
                            )
                    )
                    """
                )
            )
            connection.execute(
                text("CREATE INDEX ix_md_fetch_lease_expires_at ON md_fetch_leases (expires_at)")
            )

        with pytest.raises(RuntimeError, match="MARKET_DATA_FETCH_LEASE_SCHEMA_DRIFT"):
            command.upgrade(config, FETCH_LEASE_REVISION)
    finally:
        engine.dispose()


def test_shared_dataset_binding_migration_refuses_mysql_without_a_maintenance_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Implicit-commit MySQL DDL cannot run until writers have been drained."""
    migration = _load_shared_dataset_bindings_migration()

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("unfenced MySQL migration must not issue DDL or a lock query")

    monkeypatch.delenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, raising=False)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with pytest.raises(RuntimeError, match="MARKET_DATA_SHARED_BINDING_MAINTENANCE_FENCE_REQUIRED"):
        with migration._ddl_maintenance_fence():
            pass


def test_shared_dataset_binding_migration_uses_a_bounded_mysql_migration_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit deployment fence also serializes MySQL migration runners."""
    migration = _load_shared_dataset_bindings_migration()
    commands: list[str] = []

    class _ScalarResult:
        def scalar_one(self) -> int:
            return 1

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, statement: object, _params: object = None) -> _ScalarResult:
            commands.append(str(statement))
            return _ScalarResult()

    monkeypatch.setenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, "confirmed")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with migration._ddl_maintenance_fence():
        pass

    assert any("SET SESSION lock_wait_timeout" in command for command in commands)
    assert any("GET_LOCK" in command for command in commands)
    assert any("RELEASE_LOCK" in command for command in commands)


def test_visibility_anchor_migration_refuses_mysql_without_a_maintenance_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The receipt-order backfill never starts MySQL DDL while writers may run."""
    migration = _load_visibility_anchor_migration()

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("unfenced MySQL migration must not issue a lock query")

    monkeypatch.delenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, raising=False)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with pytest.raises(
        RuntimeError,
        match="MARKET_DATA_VISIBILITY_ANCHOR_MAINTENANCE_FENCE_REQUIRED",
    ):
        with migration._ddl_maintenance_fence():
            pass


def test_visibility_anchor_migration_uses_a_bounded_mysql_migration_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit fence serializes concurrent visibility-anchor migrations."""
    migration = _load_visibility_anchor_migration()
    commands: list[str] = []

    class _ScalarResult:
        def scalar_one(self) -> int:
            return 1

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, statement: object, _params: object = None) -> _ScalarResult:
            commands.append(str(statement))
            return _ScalarResult()

    monkeypatch.setenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, "confirmed")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with migration._ddl_maintenance_fence():
        pass

    assert any("SET SESSION lock_wait_timeout" in command for command in commands)
    assert any("GET_LOCK" in command for command in commands)
    assert any("RELEASE_LOCK" in command for command in commands)


def test_source_receipt_evidence_migration_refuses_mysql_without_a_maintenance_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Implicit-commit receipt-schema DDL waits for an explicit writer drain."""
    migration = _load_source_receipt_evidence_migration()

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("unfenced MySQL migration must not issue a lock query")

    monkeypatch.delenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, raising=False)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with pytest.raises(
        RuntimeError,
        match="MARKET_DATA_SOURCE_RECEIPT_EVIDENCE_MAINTENANCE_FENCE_REQUIRED",
    ):
        with migration._ddl_maintenance_fence():
            pass


def test_source_receipt_evidence_migration_uses_a_bounded_mysql_migration_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The receipt-evidence migration serializes MySQL runners under the fence."""
    migration = _load_source_receipt_evidence_migration()
    commands: list[str] = []

    class _ScalarResult:
        def scalar_one(self) -> int:
            return 1

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, statement: object, _params: object = None) -> _ScalarResult:
            commands.append(str(statement))
            return _ScalarResult()

    monkeypatch.setenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, "confirmed")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with migration._ddl_maintenance_fence():
        pass

    assert any("SET SESSION lock_wait_timeout" in command for command in commands)
    assert any("GET_LOCK" in command for command in commands)
    assert any("RELEASE_LOCK" in command for command in commands)


def test_source_governance_migration_refuses_mysql_without_a_maintenance_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Governance DDL cannot start on MySQL until market-data writers are drained."""
    migration = _load_source_governance_migration()

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("unfenced MySQL migration must not issue a lock query")

    monkeypatch.delenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, raising=False)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with pytest.raises(
        RuntimeError,
        match="MARKET_DATA_SOURCE_GOVERNANCE_MAINTENANCE_FENCE_REQUIRED",
    ):
        with migration._ddl_maintenance_fence():
            pass


def test_source_governance_migration_uses_a_bounded_mysql_migration_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The writer-drain fence serializes concurrent governance migrations."""
    migration = _load_source_governance_migration()
    commands: list[str] = []

    class _ScalarResult:
        def scalar_one(self) -> int:
            return 1

    class _MySqlBind:
        dialect = SimpleNamespace(name="mysql")

        def execute(self, statement: object, _params: object = None) -> _ScalarResult:
            commands.append(str(statement))
            return _ScalarResult()

    monkeypatch.setenv(migration._MYSQL_MAINTENANCE_FENCE_ENV, "confirmed")
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: _MySqlBind()))

    with migration._ddl_maintenance_fence():
        pass

    assert any("SET SESSION lock_wait_timeout" in command for command in commands)
    assert any("GET_LOCK" in command for command in commands)
    assert any("RELEASE_LOCK" in command for command in commands)


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+aiomysql://market_data:fixture@localhost/market_data",
        "postgresql+asyncpg://market_data:fixture@localhost/market_data",
    ],
)
def test_observation_migration_renders_for_supported_server_dialects(database_url: str) -> None:
    """The migration uses portable DDL and never emits a legacy fact-table rewrite."""
    output = StringIO()
    config = _config(database_url)
    config.output_buffer = output

    command.upgrade(
        config,
        f"{CATALOG_REVISION}:{OBSERVATIONS_REVISION}",
        sql=True,
    )

    rendered = output.getvalue()
    assert "CREATE TABLE md_instrument_lookup_keys" in rendered
    assert "CREATE TABLE md_observation_revisions" in rendered
    assert "legacy_market_facts" not in rendered


@pytest.mark.parametrize(
    ("database_url", "payload_type"),
    [
        ("mysql+aiomysql://market_data:fixture@localhost/market_data", "MEDIUMBLOB"),
        ("postgresql+asyncpg://market_data:fixture@localhost/market_data", "BYTEA"),
    ],
)
def test_shared_source_payload_migration_renders_portable_child_evidence(
    database_url: str,
    payload_type: str,
) -> None:
    """Offline review renders BLOB/BYTEA child tables without parent-table DDL."""
    output = StringIO()
    config = _config(database_url)
    config.output_buffer = output

    command.upgrade(
        config,
        f"{RESEARCH_BINDING_CONSUMERS_REVISION}:{SHARED_SOURCE_PAYLOADS_REVISION}",
        sql=True,
    )

    rendered = output.getvalue()
    assert "CREATE TABLE md_source_payloads" in rendered
    assert "CREATE TABLE md_source_snapshot_payload_refs" in rendered
    assert payload_type in rendered
    assert "ALTER TABLE md_source_snapshots" not in rendered


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+aiomysql://market_data:fixture@localhost/market_data",
        "postgresql+asyncpg://market_data:fixture@localhost/market_data",
    ],
)
def test_shared_dataset_binding_migration_refuses_offline_sql_rendering(
    database_url: str,
) -> None:
    """Batch table reconstruction is never misrepresented as offline-safe DDL."""
    config = _config(database_url)
    config.output_buffer = StringIO()

    with pytest.raises(RuntimeError, match="MARKET_DATA_SHARED_BINDING_OFFLINE_UNSUPPORTED"):
        command.upgrade(
            config,
            f"{OBSERVATIONS_REVISION}:{SHARED_DATASET_BINDINGS_REVISION}",
            sql=True,
        )
