"""Offline contracts for the operator-only Iteration 197 catalog bootstrap."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func, inspect, select, text

from app.db.database import async_session_maker
from app.models.data_governance import DgDataset, DgDatasetStorage, DgProvider, DgStorageTarget
from app.services.market_data import bootstrap as bootstrap_module
from app.services.market_data.bootstrap import (
    AKSHARE_PROVIDER_ID,
    CANONICAL_DATASET_CODE,
    CANONICAL_PHYSICAL_TABLE,
    CANONICAL_STORAGE_ID,
    CANONICAL_WRITE_MODE,
    SUPPORTED_ASSET_TYPES,
    CanonicalStorageSpec,
    MarketDataBootstrapError,
    MarketDataBootstrapSpec,
    MarketDataPlatformBootstrapper,
)
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.store import MarketDataStore


def _spec(*, openbb_markets: tuple[str, ...] = ("US-NYSE",)) -> MarketDataBootstrapSpec:
    return MarketDataBootstrapSpec(
        storage=CanonicalStorageSpec.from_database_url("sqlite+aiosqlite://"),
        openbb_provider="yfinance",
        openbb_allowed_markets=openbb_markets,
    )


class _UniqueIndexesOnlyInspector:
    """Present a dialect that reflects uniqueness as unique indexes instead of constraints."""

    def __init__(self, delegate: object, table_name: str) -> None:
        self._delegate = delegate
        self._table_name = table_name

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
        if table_name == self._table_name:
            return []
        return self._delegate.get_unique_constraints(table_name)

    def get_indexes(self, table_name: str) -> list[dict[str, object]]:
        indexes = list(self._delegate.get_indexes(table_name))
        if table_name != self._table_name:
            return indexes
        requirement = bootstrap_module._REQUIRED_MARKET_TABLES[table_name]
        for ordinal, unique_columns in enumerate(requirement.unique_column_sets):
            indexes.append(
                {
                    "name": f"equivalent_unique_{ordinal}",
                    "column_names": sorted(unique_columns),
                    "unique": True,
                }
            )
        return indexes


def _market_table_accepts_unique_indexes(sync_connection: object) -> bool:
    """Exercise portable reflected-uniqueness semantics against the SQLite fixture."""
    table_name = "md_observation_revisions"
    inspector = _UniqueIndexesOnlyInspector(inspect(sync_connection), table_name)
    requirement = bootstrap_module._REQUIRED_MARKET_TABLES[table_name]
    return not bootstrap_module._market_table_is_incomplete(inspector, table_name, requirement)


@pytest.mark.asyncio
async def test_bootstrap_registers_unified_canonical_bars_and_approved_providers() -> None:
    """A migrated empty catalog becomes query-ready without any network access."""
    async with async_session_maker() as session:
        result = await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()

        resolution = await DataCatalogResolver(session).resolve_primary(CANONICAL_DATASET_CODE)
        await MarketDataStore(session).ensure_provider_active(AKSHARE_PROVIDER_ID)
        await MarketDataStore(session).ensure_provider_active("openbb:yfinance")
        dataset = await session.scalar(
            select(DgDataset).where(DgDataset.dataset_code == CANONICAL_DATASET_CODE)
        )
        provider_ids = list(
            (await session.execute(select(DgProvider.provider_id).order_by(DgProvider.provider_id)))
            .scalars()
            .all()
        )

    assert result.openbb_status == "registered"
    assert result.registered_provider_ids == (AKSHARE_PROVIDER_ID, "openbb:yfinance")
    assert resolution.storage_id == CANONICAL_STORAGE_ID
    assert resolution.physical_table == CANONICAL_PHYSICAL_TABLE
    assert resolution.write_mode == CANONICAL_WRITE_MODE
    assert dataset is not None
    assert dataset.canonical_schema["supported_asset_types"] == list(SUPPORTED_ASSET_TYPES)
    assert dataset.primary_key == [
        "semantic_key_sha256",
        "event_time",
        "available_at",
        "source_snapshot_id",
        "revision_number",
    ]
    assert provider_ids == [AKSHARE_PROVIDER_ID, "openbb:yfinance"]


def test_bootstrap_schema_contract_covers_every_iteration197_market_table() -> None:
    """A future table cannot be omitted from the pre-bootstrap readiness gate."""
    assert set(bootstrap_module._REQUIRED_MARKET_TABLES) == {
        "md_publications",
        "md_instrument_identity_revisions",
        "md_calendar_import_locks",
        "md_instrument_lookup_keys",
        "md_data_series",
        "md_source_snapshots",
        "md_observation_revisions",
        "md_calendar_snapshots",
        "md_calendar_events",
    }


@pytest.mark.asyncio
async def test_bootstrap_refuses_when_a_noncanonical_market_table_is_missing() -> None:
    """A partial md_* migration cannot register a catalog that later readers cannot use."""
    async with async_session_maker() as session:
        await session.execute(text("DROP TABLE md_calendar_events"))
        await session.commit()

        with pytest.raises(MarketDataBootstrapError) as blocked:
            await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.rollback()
        provider_count = await session.scalar(select(func.count()).select_from(DgProvider))
        dataset_count = await session.scalar(select(func.count()).select_from(DgDataset))

    assert blocked.value.code == "MARKET_DATA_BOOTSTRAP_SCHEMA_UNREADY"
    assert provider_count == 0
    assert dataset_count == 0


@pytest.mark.asyncio
async def test_bootstrap_refuses_when_a_core_market_lookup_index_is_missing() -> None:
    """A manually incomplete migration cannot lose its point-in-time lookup index."""
    async with async_session_maker() as session:
        await session.execute(text("DROP INDEX ix_md_observation_revision_available"))
        await session.commit()

        with pytest.raises(MarketDataBootstrapError) as blocked:
            await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.rollback()
        provider_count = await session.scalar(select(func.count()).select_from(DgProvider))

    assert blocked.value.code == "MARKET_DATA_BOOTSTRAP_SCHEMA_UNREADY"
    assert provider_count == 0


@pytest.mark.asyncio
async def test_bootstrap_accepts_unique_index_reflection_as_equivalent_uniqueness() -> None:
    """MySQL-style unique-index reflection satisfies the same persistence invariant."""
    async with async_session_maker() as session:
        connection = await session.connection()
        accepts_equivalent = await connection.run_sync(_market_table_accepts_unique_indexes)

    assert accepts_equivalent


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_does_not_duplicate_control_plane_rows() -> None:
    """A second operator run verifies the exact contract instead of rewriting it."""
    async with async_session_maker() as session:
        first = await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()
        second = await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()
        counts = {
            "storage": await session.scalar(select(func.count()).select_from(DgStorageTarget)),
            "dataset": await session.scalar(select(func.count()).select_from(DgDataset)),
            "binding": await session.scalar(select(func.count()).select_from(DgDatasetStorage)),
            "provider": await session.scalar(select(func.count()).select_from(DgProvider)),
        }

    assert len(first.created) == 5
    assert second.created == ()
    assert set(second.verified) == {
        "storage:canonical_market_data",
        "dataset:market.bars",
        "binding:market.bars",
        "provider:akshare",
        "provider:openbb:yfinance",
    }
    assert counts == {"storage": 1, "dataset": 1, "binding": 1, "provider": 2}


@pytest.mark.asyncio
async def test_bootstrap_does_not_register_openbb_without_an_explicit_market_allow_list() -> None:
    """A default provider name alone cannot silently approve OpenBB traffic."""
    async with async_session_maker() as session:
        result = await MarketDataPlatformBootstrapper(session).bootstrap(_spec(openbb_markets=()))
        await session.commit()
        provider_ids = list((await session.execute(select(DgProvider.provider_id))).scalars().all())

    assert result.openbb_status == "not_configured_no_allowed_markets"
    assert result.registered_provider_ids == (AKSHARE_PROVIDER_ID,)
    assert provider_ids == [AKSHARE_PROVIDER_ID]


@pytest.mark.asyncio
async def test_bootstrap_refuses_to_reactivate_a_disabled_provider() -> None:
    """An intentional provider kill switch remains operator-owned on later runs."""
    async with async_session_maker() as session:
        await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()
        provider = await session.scalar(
            select(DgProvider).where(DgProvider.provider_id == "openbb:yfinance")
        )
        assert provider is not None
        provider.is_active = False
        await session.commit()

        with pytest.raises(MarketDataBootstrapError) as blocked:
            await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.rollback()
        restored = await session.scalar(
            select(DgProvider).where(DgProvider.provider_id == "openbb:yfinance")
        )

    assert blocked.value.code == "MARKET_DATA_BOOTSTRAP_PROVIDER_INACTIVE"
    assert restored is not None
    assert restored.is_active is False


@pytest.mark.asyncio
async def test_bootstrap_refuses_a_storage_spec_for_a_different_connected_engine() -> None:
    """A hand-built spec cannot label a SQLite session as a MySQL target."""
    spec = MarketDataBootstrapSpec(
        storage=CanonicalStorageSpec.from_database_url(
            "mysql+aiomysql://catalog_user:secret@db.example/market_data"
        )
    )

    async with async_session_maker() as session:
        with pytest.raises(MarketDataBootstrapError) as mismatch:
            await MarketDataPlatformBootstrapper(session).bootstrap(spec)

    assert mismatch.value.code == "MARKET_DATA_BOOTSTRAP_ENGINE_MISMATCH"


@pytest.mark.parametrize(
    ("database_url", "engine", "database_name"),
    [
        ("sqlite+aiosqlite:////var/lib/app/backtrader.db", "sqlite", "backtrader.db"),
        ("mysql+aiomysql://catalog_user:secret@db.example/akshare_data", "mysql", "akshare_data"),
        (
            "postgresql+asyncpg://catalog_user:secret@db.example:5432/market_data",
            "postgresql",
            "market_data",
        ),
    ],
)
def test_storage_spec_is_cross_dialect_and_never_retains_connection_credentials(
    database_url: str,
    engine: str,
    database_name: str,
) -> None:
    """Catalog registration stores an env name and database identifier, never a URL secret."""
    spec = CanonicalStorageSpec.from_database_url(database_url)

    assert spec.engine == engine
    assert spec.database_name == database_name
    assert spec.url_env == "DATABASE_URL"
    assert "secret" not in repr(spec)


def test_settings_spec_requires_an_explicit_openbb_market_approval() -> None:
    """Runtime defaults do not become a provider authorization by themselves."""
    settings = SimpleNamespace(
        DATABASE_URL="sqlite+aiosqlite:////tmp/backtrader.db",
        MARKET_DATA_OPENBB_PROVIDER="yfinance",
        MARKET_DATA_OPENBB_ALLOWED_MARKETS="",
    )

    spec = MarketDataBootstrapSpec.from_settings(settings)

    assert spec.openbb_provider == "yfinance"
    assert spec.openbb_provider_id is None


def test_settings_spec_normalizes_a_mixed_case_openbb_provider_before_registration() -> None:
    """Bootstrap IDs must equal query-policy receipt IDs for the same settings."""
    settings = SimpleNamespace(
        DATABASE_URL="sqlite+aiosqlite:////tmp/backtrader.db",
        MARKET_DATA_OPENBB_PROVIDER="YFinance",
        MARKET_DATA_OPENBB_ALLOWED_MARKETS="US-NYSE",
    )

    spec = MarketDataBootstrapSpec.from_settings(settings)

    assert spec.openbb_provider == "yfinance"
    assert spec.openbb_provider_id == "openbb:yfinance"


def test_bootstrap_spec_rejects_an_openbb_provider_without_a_verified_runner_contract() -> None:
    """The catalog cannot register a provider merely because its name is syntactically valid."""
    with pytest.raises(MarketDataBootstrapError) as rejected:
        MarketDataBootstrapSpec(
            storage=CanonicalStorageSpec.from_database_url("sqlite+aiosqlite://"),
            openbb_provider="unreviewed_provider",
            openbb_allowed_markets=("US-NYSE",),
        )

    assert rejected.value.code == "MARKET_DATA_BOOTSTRAP_OPENBB_PROVIDER_UNSUPPORTED"
