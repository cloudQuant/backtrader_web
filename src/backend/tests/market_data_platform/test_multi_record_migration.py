"""Migration contracts for B2 semantic market-data record identities."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_HEAD_REVISION = "20260911_market_data_deferred_publications"
SEMANTIC_RECORD_KEYS_REVISION = "20260911_market_data_semantic_record_keys"
B2_COMPLETENESS_EVIDENCE_REVISION = "20260911_market_data_b2_completeness_evidence"
SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON = (
    '{"record_identity_contract_version":"market-data-semantic-record-key-v1","scope":"singleton"}'
)
SINGLE_RECORD_SEMANTIC_KEY_SHA256 = (
    "98220d1065fb50740a858df25f884573e8c6aea554b05a3268ed4d1fd621d08e"
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _load_semantic_record_key_migration() -> ModuleType:
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "20260911_market_data_semantic_record_keys.py"
    )
    spec = importlib.util.spec_from_file_location(
        "iteration197_semantic_record_key_migration",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _insert_legacy_observation(connection) -> tuple[datetime, str, str]:
    """Insert one pre-B2 fact with an opaque source record marker."""
    observed_at = datetime(2026, 9, 11, 8, 30, 15, 123456, tzinfo=timezone.utc)
    revision_hash = _sha("legacy-revision-key")
    opaque_source_record_key = "upstream=akshare|opaque:key/?#not-semantic"
    connection.execute(
        text(
            "INSERT INTO dg_providers "
            "(id, provider_id, name, category, auth_type, rate_limit, is_active, created_at) "
            "VALUES ('provider-1', 'akshare', 'AkShare', 'market', 'none', 60, 1, :observed_at)"
        ),
        {"observed_at": observed_at},
    )
    connection.execute(
        text(
            "INSERT INTO dg_datasets "
            "(id, dataset_code, display_name, domain, canonical_schema, primary_key, is_active, "
            "created_at) "
            "VALUES ('dataset-1', 'market.stock_daily', 'Stock daily', 'market', :schema, "
            ":primary_key, 1, :observed_at)"
        ),
        {
            "schema": json.dumps({}),
            "primary_key": json.dumps([]),
            "observed_at": observed_at,
        },
    )
    connection.execute(
        text(
            "INSERT INTO md_data_series "
            "(id, dataset_id, canonical_id, data_kind, frequency, semantic_key_sha256, "
            "semantic_identity_json, created_at) "
            "VALUES ('series-1', 'dataset-1', 'instrument:stock:cn:600000', 'bars', '1d', "
            ":series_hash, :semantic_identity, :observed_at)"
        ),
        {
            "series_hash": _sha("series-1"),
            "semantic_identity": json.dumps({}),
            "observed_at": observed_at,
        },
    )
    connection.execute(
        text(
            "INSERT INTO md_source_snapshots "
            "(id, provider_id, platform, source_id, adapter_id, endpoint_version, "
            "request_fingerprint_sha256, payload_sha256, request_json, payload_manifest_json, "
            "provenance_json, retrieved_at, created_at) "
            "VALUES ('source-1', 'provider-1', 'akshare', 'stock_zh_a_hist', 'akshare.stock.v1', "
            "'v1', :request_hash, :payload_hash, :request_json, :manifest_json, :provenance_json, "
            ":observed_at, :observed_at)"
        ),
        {
            "request_hash": _sha("request-1"),
            "payload_hash": _sha("payload-1"),
            "request_json": json.dumps({}),
            "manifest_json": json.dumps({}),
            "provenance_json": json.dumps({}),
            "observed_at": observed_at,
        },
    )
    connection.execute(
        text(
            "INSERT INTO md_observation_revisions "
            "(id, series_id, event_time, event_end, available_at, source_snapshot_id, "
            "quality_status, quality_policy_version, quality_details_json, fields_json, "
            "fields_sha256, revision_number, revision_key_sha256, normalization_version, "
            "source_record_key, provenance_json, committed_at, created_at) "
            "VALUES ('legacy-observation', 'series-1', :observed_at, NULL, :observed_at, 'source-1', "
            "'accepted', 'quality-v1', :quality_details, :fields_json, :fields_hash, 1, "
            ":revision_hash, 'normalization-v1', :source_record_key, :provenance_json, "
            ":observed_at, :observed_at)"
        ),
        {
            "observed_at": observed_at,
            "quality_details": json.dumps({}),
            "fields_json": json.dumps({"close": "10.5"}),
            "fields_hash": _sha("legacy-fields"),
            "revision_hash": revision_hash,
            "source_record_key": opaque_source_record_key,
            "provenance_json": json.dumps({"raw_row": 1}),
        },
    )
    return observed_at, revision_hash, opaque_source_record_key


def _observation_insert_sql() -> str:
    return (
        "INSERT INTO md_observation_revisions "
        "(id, series_id, event_time, available_at, source_snapshot_id, quality_status, "
        "quality_policy_version, quality_details_json, fields_json, fields_sha256, revision_number, "
        "revision_key_sha256, normalization_version, source_record_key, semantic_record_key, "
        "semantic_record_key_sha256, provenance_json, committed_at, created_at) "
        "VALUES (:id, 'series-1', :observed_at, :observed_at, 'source-1', 'accepted', "
        "'quality-v1', :quality_details, :fields_json, :fields_hash, 1, :revision_hash, "
        "'normalization-v1', :source_record_key, :semantic_record_key, "
        ":semantic_record_key_sha256, :provenance_json, :observed_at, :observed_at)"
    )


def _new_observation_values(*, observation_id: str, observed_at: datetime) -> dict[str, object]:
    from app.services.market_data.multi_record import normalize_semantic_record_key

    semantic_record_key = normalize_semantic_record_key(
        family_id="test.derivative",
        family_contract_version="test-v1",
        dimensions={"contract": "IF2609"},
    )
    return {
        "id": observation_id,
        "observed_at": observed_at,
        "quality_details": json.dumps({}),
        "fields_json": json.dumps({"open_interest": "123"}),
        "fields_hash": _sha(f"fields-{observation_id}"),
        "revision_hash": _sha(f"revision-{observation_id}"),
        "source_record_key": "upstream:opaque-contract-row",
        "semantic_record_key": semantic_record_key.canonical_json,
        "semantic_record_key_sha256": semantic_record_key.sha256,
        "provenance_json": json.dumps({"raw_row": 2}),
    }


def test_semantic_record_key_migration_backfills_legacy_rows_and_replaces_event_uniqueness(
    tmp_path: Path,
) -> None:
    """B2 rows gain a server-owned singleton identity without rewriting provenance."""
    database_path = tmp_path / "semantic-record-keys.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        with engine.begin() as connection:
            observed_at, legacy_revision_hash, opaque_source_record_key = (
                _insert_legacy_observation(connection)
            )

        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)

        with engine.begin() as connection:
            legacy_row = (
                connection.execute(
                    text(
                        "SELECT semantic_record_key, semantic_record_key_sha256, revision_key_sha256, "
                        "source_record_key FROM md_observation_revisions WHERE id = 'legacy-observation'"
                    )
                )
                .mappings()
                .one()
            )
            assert legacy_row == {
                "semantic_record_key": SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
                "semantic_record_key_sha256": SINGLE_RECORD_SEMANTIC_KEY_SHA256,
                "revision_key_sha256": legacy_revision_hash,
                "source_record_key": opaque_source_record_key,
            }

            values = _new_observation_values(
                observation_id="multi-record-observation",
                observed_at=observed_at,
            )
            connection.execute(text(_observation_insert_sql()), values)

        inspector = inspect(engine)
        unique_constraints = {
            constraint["name"]: tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("md_observation_revisions")
            if constraint.get("name")
        }
        assert "uq_md_observation_revision_series_event_number" not in unique_constraints
        assert unique_constraints["uq_md_observation_revision_series_event_record_number"] == (
            "series_id",
            "event_time",
            "semantic_record_key_sha256",
            "revision_number",
        )
        assert (
            "series_id",
            "event_time",
            "semantic_record_key_sha256",
            "available_at",
        ) == next(
            tuple(index.get("column_names") or ())
            for index in inspector.get_indexes("md_observation_revisions")
            if index.get("name") == "ix_md_observation_revision_series_event_record_available"
        )
        checks = {
            check["name"] for check in inspector.get_check_constraints("md_observation_revisions")
        }
        assert {
            "ck_md_observation_revision_semantic_record_key_nonempty",
            "ck_md_observation_revision_semantic_record_key_sha256_length",
        } <= checks

        duplicate_values = _new_observation_values(
            observation_id="duplicate-multi-record-observation",
            observed_at=observed_at,
        )
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text(_observation_insert_sql()), duplicate_values)

        invalid_hash_values = _new_observation_values(
            observation_id="bad-semantic-hash",
            observed_at=observed_at,
        )
        invalid_hash_values["semantic_record_key_sha256"] = "not-a-sha256"
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text(_observation_insert_sql()), invalid_hash_values)

        empty_key_values = _new_observation_values(
            observation_id="empty-semantic-key",
            observed_at=observed_at,
        )
        empty_key_values["semantic_record_key"] = ""
        empty_key_values["semantic_record_key_sha256"] = _sha("")
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text(_observation_insert_sql()), empty_key_values)

        null_key_values = _new_observation_values(
            observation_id="null-semantic-key",
            observed_at=observed_at,
        )
        null_key_values["semantic_record_key"] = None
        null_key_values["semantic_record_key_sha256"] = _sha("null-semantic-key")
        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text(_observation_insert_sql()), null_key_values)

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_SEMANTIC_RECORD_KEY_DOWNGRADE_BLOCKED",
        ):
            command.downgrade(config, PREVIOUS_HEAD_REVISION)
    finally:
        engine.dispose()


def test_semantic_record_key_migration_handles_a_populated_sqlite_child_with_foreign_keys(
    tmp_path: Path,
) -> None:
    """SQLite batch reconstruction retains outgoing fact foreign keys when enforcement is on."""
    database_path = tmp_path / "semantic-record-keys-foreign-keys.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    connection = None
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        connection = engine.connect()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        connection.commit()
        with connection.begin():
            observed_at, legacy_revision_hash, opaque_source_record_key = (
                _insert_legacy_observation(connection)
            )
        config.attributes["connection"] = connection
        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)
        if connection.in_transaction():
            connection.commit()

        migrated = (
            connection.execute(
                text(
                    "SELECT semantic_record_key_sha256, revision_key_sha256, source_record_key "
                    "FROM md_observation_revisions WHERE id = 'legacy-observation'"
                )
            )
            .mappings()
            .one()
        )
        assert migrated == {
            "semantic_record_key_sha256": SINGLE_RECORD_SEMANTIC_KEY_SHA256,
            "revision_key_sha256": legacy_revision_hash,
            "source_record_key": opaque_source_record_key,
        }
        assert observed_at == datetime(2026, 9, 11, 8, 30, 15, 123456, tzinfo=timezone.utc)
    finally:
        config.attributes.pop("connection", None)
        if connection is not None:
            connection.close()
        engine.dispose()


def test_empty_semantic_record_key_migration_can_return_to_its_predecessor(
    tmp_path: Path,
) -> None:
    """An empty local test database can reverse only the physical B2 shape."""
    database_path = tmp_path / "empty-semantic-record-keys.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)
        command.downgrade(config, PREVIOUS_HEAD_REVISION)

        columns = {
            column["name"] for column in inspect(engine).get_columns("md_observation_revisions")
        }
        assert "semantic_record_key" not in columns
        assert "semantic_record_key_sha256" not in columns
        unique_constraints = {
            constraint["name"]: tuple(constraint.get("column_names") or ())
            for constraint in inspect(engine).get_unique_constraints("md_observation_revisions")
            if constraint.get("name")
        }
        assert unique_constraints["uq_md_observation_revision_series_event_number"] == (
            "series_id",
            "event_time",
            "revision_number",
        )
    finally:
        engine.dispose()


def test_semantic_record_key_migration_accepts_a_complete_orm_startup_schema(
    tmp_path: Path,
) -> None:
    """A SQLite create_all fixture can stamp predecessor then reconcile to B2 safely."""
    import app.models.market_data_platform  # noqa: F401
    from app.db.database import Base

    database_path = tmp_path / "semantic-record-keys-startup-schema.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        Base.metadata.create_all(engine)
        command.stamp(config, PREVIOUS_HEAD_REVISION)
        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)

        columns = {
            column["name"] for column in inspect(engine).get_columns("md_observation_revisions")
        }
        assert {"semantic_record_key", "semantic_record_key_sha256"} <= columns
    finally:
        engine.dispose()


def test_semantic_record_key_migration_resumes_after_the_first_identity_column_ddl(
    tmp_path: Path,
) -> None:
    """A retry accepts the MySQL-relevant one-column state left by implicit DDL."""
    database_path = tmp_path / "semantic-record-keys-partial-column.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        with engine.begin() as connection:
            # The migration adds this column before its hash counterpart.  MySQL
            # commits each ALTER TABLE independently, so a retry must recognize
            # this exact verified partial shape instead of treating it as drift.
            connection.execute(
                text("ALTER TABLE md_observation_revisions ADD COLUMN semantic_record_key TEXT")
            )

        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)

        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("md_observation_revisions")
        }
        assert columns["semantic_record_key"]["nullable"] is False
        assert columns["semantic_record_key_sha256"]["nullable"] is False
        unique_constraints = {
            constraint["name"]: tuple(constraint.get("column_names") or ())
            for constraint in inspect(engine).get_unique_constraints("md_observation_revisions")
            if constraint.get("name")
        }
        assert unique_constraints["uq_md_observation_revision_series_event_record_number"] == (
            "series_id",
            "event_time",
            "semantic_record_key_sha256",
            "revision_number",
        )
    finally:
        engine.dispose()


def test_semantic_record_key_migration_resumes_after_the_old_unique_was_dropped(
    tmp_path: Path,
) -> None:
    """A verified writer-drain retry rebuilds an absent fact unique constraint."""
    database_path = tmp_path / "semantic-record-keys-missing-unique.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table(
                "md_observation_revisions", recreate="always"
            ) as batch:
                # This is the MySQL implicit-commit interruption point between
                # dropping legacy uniqueness and creating B2 fact uniqueness.
                batch.drop_constraint(
                    "uq_md_observation_revision_series_event_record_number",
                    type_="unique",
                )

        command.stamp(config, PREVIOUS_HEAD_REVISION)
        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)

        unique_constraints = {
            constraint["name"]: tuple(constraint.get("column_names") or ())
            for constraint in inspect(engine).get_unique_constraints("md_observation_revisions")
            if constraint.get("name")
        }
        assert unique_constraints["uq_md_observation_revision_series_event_record_number"] == (
            "series_id",
            "event_time",
            "semantic_record_key_sha256",
            "revision_number",
        )
    finally:
        engine.dispose()


def test_semantic_record_key_migration_refuses_both_legacy_and_b2_fact_uniques(
    tmp_path: Path,
) -> None:
    """A partially finalized B2 unique replacement cannot be treated as safe."""
    database_path = tmp_path / "semantic-record-keys-both-uniques.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table(
                "md_observation_revisions", recreate="always"
            ) as batch:
                batch.add_column(sa.Column("semantic_record_key", sa.Text(), nullable=False))
                batch.add_column(
                    sa.Column("semantic_record_key_sha256", sa.String(length=64), nullable=False)
                )
                batch.create_unique_constraint(
                    "uq_md_observation_revision_series_event_record_number",
                    [
                        "series_id",
                        "event_time",
                        "semantic_record_key_sha256",
                        "revision_number",
                    ],
                )
                batch.create_check_constraint(
                    "ck_md_observation_revision_semantic_record_key_nonempty",
                    "length(semantic_record_key) > 0",
                )
                batch.create_check_constraint(
                    "ck_md_observation_revision_semantic_record_key_sha256_length",
                    "length(semantic_record_key_sha256) = 64",
                )
                batch.create_index(
                    "ix_md_observation_revision_series_event_record_available",
                    [
                        "series_id",
                        "event_time",
                        "semantic_record_key_sha256",
                        "available_at",
                    ],
                )

        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_SEMANTIC_RECORD_KEY_SCHEMA_DRIFT: both legacy and B2",
        ):
            command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)
    finally:
        engine.dispose()


def test_semantic_record_key_migration_refuses_to_recover_a_missing_unique_with_duplicates(
    tmp_path: Path,
) -> None:
    """An interrupted MySQL unique replacement cannot silently admit duplicate facts."""
    database_path = tmp_path / "semantic-record-keys-duplicate-recovery.sqlite3"
    config = _config(f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, PREVIOUS_HEAD_REVISION)
        with engine.begin() as connection:
            observed_at, _legacy_revision_hash, _opaque_source_record_key = (
                _insert_legacy_observation(connection)
            )
        command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text(_observation_insert_sql()),
                _new_observation_values(
                    observation_id="unprotected-coordinate-first",
                    observed_at=observed_at,
                ),
            )

        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table(
                "md_observation_revisions", recreate="always"
            ) as batch:
                batch.drop_constraint(
                    "uq_md_observation_revision_series_event_record_number",
                    type_="unique",
                )
        with engine.begin() as connection:
            connection.execute(
                text(_observation_insert_sql()),
                _new_observation_values(
                    observation_id="unprotected-coordinate-duplicate",
                    observed_at=observed_at,
                ),
            )

        command.stamp(config, PREVIOUS_HEAD_REVISION)
        with pytest.raises(
            RuntimeError,
            match="MARKET_DATA_SEMANTIC_RECORD_KEY_SCHEMA_DRIFT: duplicate fact coordinate",
        ):
            command.upgrade(config, SEMANTIC_RECORD_KEYS_REVISION)
    finally:
        engine.dispose()


def test_semantic_record_key_check_normalizer_accepts_postgresql_text_casts() -> None:
    """PostgreSQL reflection must not turn this migration's own SHA check into drift."""
    migration = _load_semantic_record_key_migration()
    expected = migration._CHECKS["ck_md_observation_revision_semantic_record_key_sha256_length"]

    assert migration._normalized_expression(
        "length(semantic_record_key_sha256::text) = 64"
    ) == migration._normalized_expression(expected)
    assert migration._normalized_expression(
        "length(semantic_record_key_sha256::character varying) = 64"
    ) == migration._normalized_expression(expected)
    assert migration._normalized_expression(
        "((length((semantic_record_key_sha256)::text) = 64))"
    ) == migration._normalized_expression(expected)
    assert migration._normalized_expression(
        "((length(`semantic_record_key_sha256`) = 64))"
    ) == migration._normalized_expression(expected)
    assert migration._normalized_expression(
        "length(semantic_record_key_sha256::text) = 63"
    ) != migration._normalized_expression(expected)


def test_singleton_constants_stay_aligned_with_the_pure_identity_contract() -> None:
    """The migration and ORM cannot silently diverge from the server identity helper."""
    from app.models.market_data_platform import (
        SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON as model_canonical_json,
    )
    from app.models.market_data_platform import (
        SINGLE_RECORD_SEMANTIC_KEY_SHA256 as model_sha256,
    )
    from app.services.market_data.multi_record import (
        SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON as identity_canonical_json,
    )
    from app.services.market_data.multi_record import (
        SINGLE_RECORD_SEMANTIC_KEY_SHA256 as identity_sha256,
    )

    migration = _load_semantic_record_key_migration()
    assert {
        SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
        model_canonical_json,
        identity_canonical_json,
        migration._SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON,
    } == {SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON}
    assert {
        SINGLE_RECORD_SEMANTIC_KEY_SHA256,
        model_sha256,
        identity_sha256,
        migration._SINGLE_RECORD_SEMANTIC_KEY_SHA256,
    } == {SINGLE_RECORD_SEMANTIC_KEY_SHA256}
    assert _sha(SINGLE_RECORD_SEMANTIC_KEY_CANONICAL_JSON) == SINGLE_RECORD_SEMANTIC_KEY_SHA256


def test_semantic_record_key_revision_remains_the_b2_evidence_predecessor() -> None:
    """The physical B2 identity revision stays on the single integrated graph."""
    script = ScriptDirectory.from_config(_config("sqlite://"))

    revision = script.get_revision(SEMANTIC_RECORD_KEYS_REVISION)
    evidence_revision = script.get_revision(B2_COMPLETENESS_EVIDENCE_REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_HEAD_REVISION
    assert evidence_revision is not None
    assert evidence_revision.down_revision == SEMANTIC_RECORD_KEYS_REVISION
    assert script.get_heads() == [B2_COMPLETENESS_EVIDENCE_REVISION]
