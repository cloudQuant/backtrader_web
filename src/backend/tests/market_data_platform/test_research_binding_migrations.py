"""Migration-level safety contracts for Iteration 197 research binding receipts."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MERGE_REVISION = "20260909_ai_research_market_data_merge"
BINDING_REVISION = "20260909_market_data_research_bindings"
CONSUMERS_REVISION = "20260909_market_data_research_binding_consumers"
RECEIPT_TABLES = (
    "md_research_data_bindings",
    "md_research_data_binding_scopes",
    "md_research_data_binding_consumers",
    "md_research_data_binding_revocations",
)


def _migration_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    return config


def _load_migration(filename: str, module_name: str) -> ModuleType:
    """Load a revision directly to preserve reflection-normalization regression cases."""
    path = BACKEND_ROOT / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("filename", "module_name", "postgresql", "mysql", "expected"),
    [
        (
            "20260909_market_data_research_bindings.py",
            "research_binding_receipt_migration",
            "status::text=any(array['active'::charactervarying,'revoked'::charactervarying,"
            "'invalid'::charactervarying]::text[])",
            "((`status` in (_utf8mb4'ACTIVE',_utf8mb4'REVOKED',_utf8mb4'INVALID')))",
            "status IN ('ACTIVE', 'REVOKED', 'INVALID')",
        ),
        (
            "20260909_market_data_research_binding_consumers.py",
            "research_binding_consumer_migration",
            "status::text=any(array['revoked'::charactervarying,'invalid'::charactervarying]"
            "::text[])",
            "((`status` in (_utf8mb4'REVOKED',_utf8mb4'INVALID')))",
            "status IN ('REVOKED', 'INVALID')",
        ),
    ],
)
def test_receipt_migrations_accept_only_equivalent_postgresql_and_mysql_check_rendering(
    filename: str,
    module_name: str,
    postgresql: str,
    mysql: str,
    expected: str,
) -> None:
    """Metadata-created constraints survive only known server reflection rewrites."""
    migration = _load_migration(filename, module_name)
    normalized_expected = migration._normalized_expression(expected)

    assert migration._normalized_expression(postgresql) == normalized_expected
    assert migration._normalized_expression(mysql) == normalized_expected
    assert (
        migration._normalized_expression("status IN ('ACTIVE', 'INVALID')") != normalized_expected
    )


def _insert_orphan_receipt(database_path: Path, table_name: str) -> None:
    """Seed exactly one table while intentionally bypassing FK checks for rollback tests."""
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            table = sa.Table(table_name, sa.MetaData(), autoload_with=connection)
            binding_id = str(uuid4())
            issued_at = datetime(2026, 9, 9, tzinfo=timezone.utc)
            if table_name == "md_research_data_bindings":
                values = {
                    "id": binding_id,
                    "user_id": str(uuid4()),
                    "intent_id": "intent-1",
                    "binding_hash": "a" * 64,
                    "binding_schema_version": "v1",
                    "status": "ACTIVE",
                    "artifact_relative_path": "bindings/a/data.csv",
                    "artifact_sha256": "b" * 64,
                    "artifact_size_bytes": 1,
                    "manifest_json": {},
                    "manifest_sha256": "c" * 64,
                    "canonical_id": "stock:CN-SSE:600000",
                    "instrument_metadata_version": "v1",
                    "dataset_code": "market.stock_daily",
                    "family_id": "stock.daily",
                    "family_contract_version": "v1",
                    "data_kind": "bars",
                    "frequency": "1d",
                    "source_policy_id": "policy-1",
                    "query_fingerprint": "d" * 64,
                    "knowledge_cutoff": issued_at,
                    "identity_knowledge_cutoff": issued_at,
                    "visibility_at": issued_at,
                    "visibility_sequence": 0,
                    "identity_visibility_at": issued_at,
                    "identity_visibility_sequence": 0,
                    "created_at": issued_at,
                }
            elif table_name == "md_research_data_binding_scopes":
                values = {
                    "binding_id": binding_id,
                    "user_id": str(uuid4()),
                    "intent_id": "intent-1",
                    "workspace_id": str(uuid4()),
                    "created_at": issued_at,
                }
            elif table_name == "md_research_data_binding_consumers":
                values = {
                    "id": str(uuid4()),
                    "binding_id": binding_id,
                    "user_id": str(uuid4()),
                    "intent_id": "intent-1",
                    "workspace_id": str(uuid4()),
                    "unit_id": str(uuid4()),
                    "created_at": issued_at,
                }
            elif table_name == "md_research_data_binding_revocations":
                values = {
                    "id": str(uuid4()),
                    "binding_id": binding_id,
                    "actor_user_id": str(uuid4()),
                    "status": "REVOKED",
                    "reason_code": "test",
                    "revoked_at": issued_at,
                    "created_at": issued_at,
                }
            else:
                raise AssertionError(f"unexpected receipt table: {table_name}")
            connection.execute(table.insert().values(**values))
            connection.commit()
    finally:
        engine.dispose()


def test_binding_migration_rejects_partial_same_named_schema(tmp_path: Path) -> None:
    """A partial binding table cannot be mistaken for a completed migration."""
    database_path = tmp_path / "partial-binding.sqlite3"
    config = _migration_config(database_path)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, MERGE_REVISION)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE md_research_data_bindings (id VARCHAR(36))"))

        with pytest.raises(RuntimeError, match="MARKET_DATA_RESEARCH_BINDING_SCHEMA_DRIFT"):
            command.upgrade(config, BINDING_REVISION)

        tables = set(inspect(engine).get_table_names())
        assert "md_research_data_bindings" in tables
        assert "md_research_data_binding_scopes" not in tables
    finally:
        engine.dispose()


def test_binding_migration_rejects_child_only_drift_in_upgrade_and_downgrade(
    tmp_path: Path,
) -> None:
    """A missing parent receipt never permits a child-only schema to advance either way."""
    database_path = tmp_path / "child-only-drift.sqlite3"
    config = _migration_config(database_path)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, MERGE_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE md_research_data_binding_scopes (binding_id VARCHAR(36))")
            )

        with pytest.raises(RuntimeError, match="MARKET_DATA_RESEARCH_BINDING_SCHEMA_DRIFT"):
            command.upgrade(config, BINDING_REVISION)

        command.stamp(config, BINDING_REVISION)
        with pytest.raises(RuntimeError, match="MARKET_DATA_RESEARCH_BINDING_DOWNGRADE_BLOCKED"):
            command.downgrade(config, MERGE_REVISION)

        assert "md_research_data_binding_scopes" in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_consumer_migration_rejects_partial_child_receipt_schema(tmp_path: Path) -> None:
    """A partial child receipt set is unsafe even if its parent binding table is valid."""
    database_path = tmp_path / "partial-children.sqlite3"
    config = _migration_config(database_path)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, BINDING_REVISION)
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE md_research_data_binding_scopes (binding_id VARCHAR(36))")
            )

        with pytest.raises(RuntimeError, match="MARKET_DATA_RESEARCH_BINDING_SCHEMA_DRIFT"):
            command.upgrade(config, CONSUMERS_REVISION)

        tables = set(inspect(engine).get_table_names())
        assert "md_research_data_binding_scopes" in tables
        assert "md_research_data_binding_consumers" not in tables
        assert "md_research_data_binding_revocations" not in tables
    finally:
        engine.dispose()


def test_binding_downgrade_blocks_populated_binding_receipt(tmp_path: Path) -> None:
    """The first receipt migration cannot erase an issued binding by itself."""
    database_path = tmp_path / "populated-binding.sqlite3"
    config = _migration_config(database_path)
    command.upgrade(config, BINDING_REVISION)
    _insert_orphan_receipt(database_path, "md_research_data_bindings")

    with pytest.raises(RuntimeError, match="MARKET_DATA_RESEARCH_BINDING_DOWNGRADE_BLOCKED"):
        command.downgrade(config, MERGE_REVISION)

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM md_research_data_bindings")) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize("populated_table", RECEIPT_TABLES)
def test_consumer_downgrade_blocks_any_populated_immutable_receipt(
    tmp_path: Path,
    populated_table: str,
) -> None:
    """No downgrade may erase a parent or child immutable receipt after issuance."""
    database_path = tmp_path / f"populated-{populated_table}.sqlite3"
    config = _migration_config(database_path)
    command.upgrade(config, CONSUMERS_REVISION)
    _insert_orphan_receipt(database_path, populated_table)

    with pytest.raises(RuntimeError, match="MARKET_DATA_RESEARCH_BINDING_DOWNGRADE_BLOCKED"):
        command.downgrade(config, BINDING_REVISION)

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text(f"SELECT COUNT(*) FROM {populated_table}")) == 1
    finally:
        engine.dispose()


def test_empty_receipt_tables_downgrade_and_reupgrade_cleanly(tmp_path: Path) -> None:
    """An empty deployment can return to the merge revision and later move forward again."""
    database_path = tmp_path / "empty-round-trip.sqlite3"
    config = _migration_config(database_path)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, CONSUMERS_REVISION)
        assert set(RECEIPT_TABLES) <= set(inspect(engine).get_table_names())

        command.downgrade(config, MERGE_REVISION)
        assert not set(RECEIPT_TABLES) & set(inspect(engine).get_table_names())

        command.upgrade(config, CONSUMERS_REVISION)
        assert set(RECEIPT_TABLES) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///research_bindings.db",
        "postgresql+asyncpg://market_data:secret@localhost/market_data",
        "mysql+aiomysql://market_data:secret@localhost/market_data",
    ],
)
def test_binding_migrations_render_offline_for_supported_dialects(database_url: str) -> None:
    """Offline rendering must not inspect a mock connection for supported database dialects."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    output = StringIO()
    config.output_buffer = output

    command.upgrade(config, f"{MERGE_REVISION}:{CONSUMERS_REVISION}", sql=True)

    rendered = output.getvalue()
    for table_name in RECEIPT_TABLES:
        assert f"CREATE TABLE {table_name}" in rendered
