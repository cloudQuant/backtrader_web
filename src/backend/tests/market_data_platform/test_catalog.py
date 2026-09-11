"""Contracts for the Iteration 197 logical data catalog."""

from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, insert, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.database import Base, async_session_maker

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ITERATION_196_HEAD = "20260908_ai_research_approval_authority"
INTEGRATED_HEAD = "20260911_market_data_b2_completeness_evidence"
RESEARCH_BINDING_RECEIPT_TABLES = {
    "md_research_data_bindings",
    "md_research_data_binding_scopes",
    "md_research_data_binding_consumers",
    "md_research_data_binding_revocations",
}


def test_alembic_has_a_single_head_before_catalog_is_integrated() -> None:
    """A merge with Iteration 196 must rebase or add an explicit merge revision."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


@pytest.mark.asyncio
async def test_catalog_resolution_uses_registered_binding_not_legacy_endpoint_target() -> None:
    """A legacy endpoint table cannot override a dataset's registered primary binding."""
    from app.models.data_governance import (
        DgDataset,
        DgDatasetStorage,
        DgEndpoint,
        DgProvider,
        DgStorageTarget,
    )
    from app.services.market_data.catalog import DataCatalogResolver

    async with async_session_maker() as session:
        provider = DgProvider(provider_id="akshare", name="AkShare", category="china_market")
        dataset = DgDataset(
            dataset_code="market.stock_daily",
            display_name="A 股日线",
            domain="market",
            canonical_schema={"symbol": "string", "event_time": "date"},
            primary_key=["symbol", "event_time"],
        )
        storage = DgStorageTarget(
            storage_id="mysql_akshare_data",
            engine="mysql",
            url_env="AKSHARE_DATA_DATABASE_URL",
            database_name="akshare_data",
            role="legacy",
        )
        session.add_all([provider, dataset, storage])
        await session.flush()
        session.add(
            DgEndpoint(
                provider_id=provider.id,
                dataset_id=dataset.id,
                endpoint_name="stock_zh_a_hist",
                display_name="A 股历史行情",
                category="china_market",
                incremental_sync_key="event_time",
                target_database="obsolete_database",
                target_table="WRONG_LEGACY_TABLE",
            )
        )
        session.add(
            DgDatasetStorage(
                dataset_id=dataset.id,
                storage_target_id=storage.id,
                physical_table="STOCK_ZH_A_HIST",
                write_mode="legacy_read_only",
                is_primary=True,
            )
        )
        await session.flush()

        resolution = await DataCatalogResolver(session).resolve_primary("market.stock_daily")

        assert resolution.dataset_id == dataset.id
        assert resolution.dataset_code == "market.stock_daily"
        assert resolution.storage_id == "mysql_akshare_data"
        assert resolution.physical_table == "STOCK_ZH_A_HIST"
        assert resolution.write_mode == "legacy_read_only"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dataset_active", "storage_active", "is_primary"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ],
)
async def test_catalog_resolution_rejects_ineligible_or_missing_primary_binding(
    dataset_active: bool,
    storage_active: bool,
    is_primary: bool,
) -> None:
    """Local-first callers never receive an inactive or non-primary storage binding."""
    from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget
    from app.services.market_data.catalog import DataCatalogResolver, DatasetStorageNotFoundError

    async with async_session_maker() as session:
        dataset = DgDataset(
            dataset_code="market.stock_daily",
            display_name="A 股日线",
            domain="market",
            canonical_schema={"symbol": "string", "event_time": "date"},
            primary_key=["symbol", "event_time"],
            is_active=dataset_active,
        )
        storage = DgStorageTarget(
            storage_id="canonical_market_data",
            engine="postgresql",
            url_env="MARKET_DATA_DATABASE_URL",
            database_name="market_data",
            role="canonical",
            is_active=storage_active,
        )
        session.add_all([dataset, storage])
        await session.flush()
        session.add(
            DgDatasetStorage(
                dataset_id=dataset.id,
                storage_target_id=storage.id,
                physical_table="md_bars",
                write_mode="canonical_read_write",
                is_primary=is_primary,
            )
        )
        await session.flush()

        with pytest.raises(DatasetStorageNotFoundError):
            await DataCatalogResolver(session).resolve_primary("market.stock_daily")


@pytest.mark.asyncio
async def test_catalog_resolution_rejects_ambiguous_primary_rows_from_corrupt_storage() -> None:
    """The resolver remains fail-closed if corruption bypassed catalog constraints."""
    from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget
    from app.services.market_data.catalog import DataCatalogResolver, DatasetStorageNotFoundError

    dataset = DgDataset(dataset_code="market.stock_daily", display_name="A 股日线", domain="market")
    storage = DgStorageTarget(
        storage_id="canonical_market_data",
        engine="postgresql",
        url_env="MARKET_DATA_DATABASE_URL",
        database_name="market_data",
        role="canonical",
    )
    binding = DgDatasetStorage(
        dataset_id="dataset-1",
        storage_target_id="storage-1",
        physical_table="md_bars",
        is_primary=True,
    )

    class _CorruptResult:
        def all(self):
            return [(binding, dataset, storage), (binding, dataset, storage)]

    class _CorruptSession:
        async def execute(self, _statement):
            return _CorruptResult()

    with pytest.raises(DatasetStorageNotFoundError):
        await DataCatalogResolver(_CorruptSession()).resolve_primary("market.stock_daily")


@pytest.mark.asyncio
async def test_catalog_rejects_two_primary_bindings_for_one_dataset() -> None:
    """A dataset may have many storage bindings but only one primary binding."""
    from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget

    async with async_session_maker() as session:
        dataset = DgDataset(
            dataset_code="market.stock_daily",
            display_name="A 股日线",
            domain="market",
            canonical_schema={"symbol": "string", "event_time": "date"},
            primary_key=["symbol", "event_time"],
        )
        canonical_store = DgStorageTarget(
            storage_id="canonical_market_data",
            engine="postgresql",
            url_env="MARKET_DATA_DATABASE_URL",
            database_name="market_data",
            role="canonical",
        )
        legacy_store = DgStorageTarget(
            storage_id="mysql_akshare_data",
            engine="mysql",
            url_env="AKSHARE_DATA_DATABASE_URL",
            database_name="akshare_data",
            role="legacy",
        )
        session.add_all([dataset, canonical_store, legacy_store])
        await session.flush()

        session.add_all(
            [
                DgDatasetStorage(
                    dataset_id=dataset.id,
                    storage_target_id=canonical_store.id,
                    physical_table="md_bars",
                    write_mode="canonical_read_write",
                    is_primary=True,
                ),
                DgDatasetStorage(
                    dataset_id=dataset.id,
                    storage_target_id=legacy_store.id,
                    physical_table="STOCK_ZH_A_HIST",
                    write_mode="legacy_read_only",
                    is_primary=True,
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_catalog_rejects_inconsistent_primary_slot_from_core_sql() -> None:
    """The database constraint protects the catalog even outside the ORM event path."""
    from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget

    async with async_session_maker() as session:
        dataset = DgDataset(
            dataset_code="market.stock_daily",
            display_name="A 股日线",
            domain="market",
            canonical_schema={"symbol": "string", "event_time": "date"},
            primary_key=["symbol", "event_time"],
        )
        storage = DgStorageTarget(
            storage_id="canonical_market_data",
            engine="postgresql",
            url_env="MARKET_DATA_DATABASE_URL",
            database_name="market_data",
            role="canonical",
        )
        session.add_all([dataset, storage])
        await session.flush()

        with pytest.raises(IntegrityError):
            await session.execute(
                insert(DgDatasetStorage).values(
                    id=str(uuid4()),
                    dataset_id=dataset.id,
                    storage_target_id=storage.id,
                    physical_table="md_bars",
                    write_mode="canonical_read_write",
                    is_primary=True,
                    primary_dataset_id=None,
                )
            )


def test_catalog_migration_creates_metadata_without_legacy_market_table_rewrite(
    tmp_path: Path,
) -> None:
    """The catalog schema extends metadata and leaves legacy market facts untouched."""
    database_path = tmp_path / "catalog.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"dg_datasets", "dg_storage_targets", "dg_dataset_storages"} <= tables
        assert "dataset_id" in {column["name"] for column in inspector.get_columns("dg_endpoints")}
        assert "dataset_storage_id" in {
            column["name"] for column in inspector.get_columns("ak_data_tables")
        }
    finally:
        engine.dispose()


def test_catalog_migration_accepts_current_startup_created_schema_at_iteration_196_baseline(
    tmp_path: Path,
) -> None:
    """The integrated upgrade accepts an ORM-created schema baselined at Iteration 196.

    A deployment that created its Iteration 196 ORM schema before introducing
    Alembic must explicitly baseline that reviewed 196 state.  The unified
    head then has to run only the Iteration 197 chain; it must not replay the
    already-materialized 196 branch into existing tables.
    """
    database_path = tmp_path / "startup-created.sqlite3"
    sync_database_url = f"sqlite:///{database_path}"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(sync_database_url)
    try:
        Base.metadata.create_all(engine)
        command.stamp(config, ITERATION_196_HEAD)

        command.upgrade(config, "head")

        inspector = inspect(engine)
        assert "dg_dataset_storages" in inspector.get_table_names()
        assert RESEARCH_BINDING_RECEIPT_TABLES <= set(inspector.get_table_names())
        observation_columns = {
            column["name"] for column in inspector.get_columns("md_observation_revisions")
        }
        assert {"semantic_record_key", "semantic_record_key_sha256"} <= observation_columns
        observation_uniques = {
            constraint["name"]: tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("md_observation_revisions")
        }
        assert observation_uniques["uq_md_observation_revision_series_event_record_number"] == (
            "series_id",
            "event_time",
            "semantic_record_key_sha256",
            "revision_number",
        )
        observation_indexes = {
            index["name"]: tuple(index.get("column_names") or ())
            for index in inspector.get_indexes("md_observation_revisions")
        }
        assert observation_indexes["ix_md_observation_revision_series_event_record_available"] == (
            "series_id",
            "event_time",
            "semantic_record_key_sha256",
            "available_at",
        )
        assert ScriptDirectory.from_config(config).get_heads() == [INTEGRATED_HEAD]

        command.downgrade(config, ITERATION_196_HEAD)
        command.upgrade(config, "head")

        tables_after_round_trip = set(inspect(engine).get_table_names())
        assert "dg_dataset_storages" in tables_after_round_trip
        assert RESEARCH_BINDING_RECEIPT_TABLES <= tables_after_round_trip
    finally:
        engine.dispose()


def test_catalog_migration_rejects_partial_catalog_schema(tmp_path: Path) -> None:
    """A partial non-transactional DDL attempt cannot be stamped as complete."""
    database_path = tmp_path / "partial-catalog.sqlite3"
    sync_database_url = f"sqlite:///{database_path}"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(sync_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE dg_datasets (id VARCHAR(36) PRIMARY KEY)"))
        command.stamp(config, "20260811_asset_research_task_leases")

        with pytest.raises(RuntimeError, match="MARKET_DATA_CATALOG_PARTIAL_SCHEMA_UNSAFE"):
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_catalog_migration_rejects_same_named_wrong_column_contract(tmp_path: Path) -> None:
    """Recovery refuses a table whose names match but type/nullability do not."""
    database_path = tmp_path / "wrong-catalog-columns.sqlite3"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{database_path}")
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE dg_datasets (
                        id VARCHAR(36) PRIMARY KEY,
                        dataset_code VARCHAR(160) NOT NULL,
                        display_name VARCHAR(255) NOT NULL,
                        domain INTEGER NULL,
                        canonical_schema JSON NOT NULL,
                        primary_key JSON NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
        command.stamp(config, "20260811_asset_research_task_leases")

        with pytest.raises(
            RuntimeError, match="MARKET_DATA_CATALOG_PARTIAL_SCHEMA_UNSAFE"
        ) as unsafe:
            command.upgrade(config, "head")
    finally:
        engine.dispose()

    assert "invalid_columns" in str(unsafe.value)
    assert "domain" in str(unsafe.value)


def test_catalog_migration_rejects_same_named_but_wrong_catalog_index(tmp_path: Path) -> None:
    """Schema recovery must verify an existing index's columns and uniqueness."""
    database_path = tmp_path / "wrong-catalog-index.sqlite3"
    sync_database_url = f"sqlite:///{database_path}"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(sync_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE dg_datasets (
                        id VARCHAR(36) PRIMARY KEY,
                        dataset_code VARCHAR(160) NOT NULL,
                        display_name VARCHAR(255) NOT NULL,
                        domain VARCHAR(80) NOT NULL,
                        canonical_schema JSON NOT NULL,
                        primary_key JSON NOT NULL,
                        is_active BOOLEAN NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text("CREATE UNIQUE INDEX ix_dg_datasets_dataset_code ON dg_datasets (domain)")
            )
            connection.execute(text("CREATE INDEX ix_dg_datasets_domain ON dg_datasets (domain)"))
        command.stamp(config, "20260811_asset_research_task_leases")

        with pytest.raises(RuntimeError, match="MARKET_DATA_CATALOG_PARTIAL_SCHEMA_UNSAFE"):
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_catalog_migration_preserves_legacy_metadata_and_fact_rows(tmp_path: Path) -> None:
    """SQLite batch migration preserves old catalog rows and unrelated market facts."""
    database_path = tmp_path / "legacy-facts.sqlite3"
    sync_database_url = f"sqlite:///{database_path}"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(sync_database_url)
    try:
        command.upgrade(config, "20260811_asset_research_task_leases")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO dg_providers
                    (id, provider_id, name, category, auth_type, rate_limit, is_active, created_at)
                    VALUES
                    (:id, :provider_id, :name, :category, :auth_type, :rate_limit, :is_active,
                     :created_at)
                    """
                ),
                {
                    "id": "provider-1",
                    "provider_id": "akshare",
                    "name": "AkShare",
                    "category": "china_market",
                    "auth_type": "none",
                    "rate_limit": 60,
                    "is_active": True,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO dg_endpoints
                    (id, provider_id, endpoint_name, display_name, category, params_schema,
                     auth_type, rate_limit, cache_ttl_sec, target_database, target_table,
                     normalization_profile, quality_profile, incremental_sync_key, is_active,
                     created_at)
                    VALUES
                    (:id, :provider_id, :endpoint_name, :display_name, :category, :params_schema,
                     :auth_type, :rate_limit, :cache_ttl_sec, :target_database, :target_table,
                     :normalization_profile, :quality_profile, :incremental_sync_key, :is_active,
                     :created_at)
                    """
                ),
                {
                    "id": "endpoint-1",
                    "provider_id": "provider-1",
                    "endpoint_name": "stock_zh_a_hist",
                    "display_name": "A 股历史行情",
                    "category": "china_market",
                    "params_schema": "{}",
                    "auth_type": "none",
                    "rate_limit": 60,
                    "cache_ttl_sec": 300,
                    "target_database": "akshare_data",
                    "target_table": "STOCK_ZH_A_HIST",
                    "normalization_profile": "{}",
                    "quality_profile": "{}",
                    "incremental_sync_key": "event_time",
                    "is_active": True,
                    "created_at": "2026-09-08 00:00:00",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ak_data_tables
                    (id, table_name, row_count, metadata, created_at, updated_at)
                    VALUES (:id, :table_name, :row_count, :metadata, :created_at, :updated_at)
                    """
                ),
                {
                    "id": 1,
                    "table_name": "STOCK_ZH_A_HIST",
                    "row_count": 1,
                    "metadata": "{}",
                    "created_at": "2026-09-08 00:00:00",
                    "updated_at": "2026-09-08 00:00:00",
                },
            )
            connection.execute(
                text("CREATE TABLE legacy_market_facts (symbol VARCHAR(16), close NUMERIC)")
            )
            connection.execute(
                text("INSERT INTO legacy_market_facts (symbol, close) VALUES ('000001', 10.5)")
            )

        command.upgrade(config, "head")

        with engine.connect() as connection:
            endpoint = connection.execute(
                text(
                    "SELECT target_database, target_table, dataset_id "
                    "FROM dg_endpoints WHERE id = 'endpoint-1'"
                )
            ).one()
            table = connection.execute(
                text(
                    "SELECT table_name, row_count, dataset_storage_id "
                    "FROM ak_data_tables WHERE id = 1"
                )
            ).one()
            fact = connection.execute(text("SELECT symbol, close FROM legacy_market_facts")).one()

        assert endpoint == ("akshare_data", "STOCK_ZH_A_HIST", None)
        assert table == ("STOCK_ZH_A_HIST", 1, None)
        assert fact == ("000001", 10.5)
    finally:
        engine.dispose()


def test_catalog_migration_blocks_downgrade_when_catalog_has_data(tmp_path: Path) -> None:
    """Rollback cannot silently delete persisted catalog control-plane records."""
    database_path = tmp_path / "downgrade-blocked.sqlite3"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO dg_datasets
                    (id, dataset_code, display_name, domain, canonical_schema, primary_key,
                     is_active, created_at)
                    VALUES
                    ('dataset-1', 'market.stock_daily', 'A 股日线', 'market', '{}', '[]', 1,
                     '2026-09-08 00:00:00')
                    """
                )
            )

        with pytest.raises(RuntimeError, match="MARKET_DATA_CATALOG_DOWNGRADE_BLOCKED"):
            command.downgrade(config, "20260811_asset_research_task_leases")

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM dg_datasets")) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql+aiomysql://market_data:secret@localhost/market_data",
        "postgresql+asyncpg://market_data:secret@localhost/market_data",
    ],
)
def test_catalog_migration_renders_offline_for_supported_server_dialects(database_url: str) -> None:
    """Offline SQL rendering must not try to inspect Alembic's mock connection."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    output = StringIO()
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.output_buffer = output

    command.upgrade(
        config,
        "20260811_asset_research_task_leases:20260908_market_data_catalog",
        sql=True,
    )

    assert "CREATE TABLE dg_datasets" in output.getvalue()
