"""Offline contracts for the operator-only Iteration 197 catalog bootstrap."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import func, inspect, select, text

from app.db.database import async_session_maker
from app.models.data_governance import (
    DgDataset,
    DgDatasetStorage,
    DgEndpoint,
    DgProvider,
    DgStorageTarget,
)
from app.services.market_data import bootstrap as bootstrap_module
from app.services.market_data.bootstrap import (
    AKSHARE_PROVIDER_ID,
    CANONICAL_DATASET_CODE,
    CANONICAL_DATASET_CODES,
    CANONICAL_PHYSICAL_TABLE,
    CANONICAL_QUOTE_SNAPSHOT_DATASET_CODE,
    CANONICAL_STOCK_VALUATION_CAPTURED_SNAPSHOT_DATASET_CODE,
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


class _LegacySharedBindingInspector:
    """Reflect the pre-F2 two-column table claim from a migrated catalog."""

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
        constraints = list(self._delegate.get_unique_constraints(table_name))
        if table_name != "dg_dataset_storages":
            return constraints
        return [
            {
                **constraint,
                "column_names": ["storage_target_id", "physical_table"],
            }
            if constraint.get("name") == "uq_dg_dataset_storage_target_table"
            else constraint
            for constraint in constraints
        ]


def _legacy_shared_binding_constraint_is_rejected(sync_connection: object) -> bool:
    """The operator gate must not try a shared binding before F2 DDL exists."""
    inspector = _LegacySharedBindingInspector(inspect(sync_connection))
    return bootstrap_module._catalog_table_unique_constraints_are_incomplete(
        inspector,
        "dg_dataset_storages",
        bootstrap_module._REQUIRED_CATALOG_UNIQUES["dg_dataset_storages"],
    )


@pytest.mark.asyncio
async def test_bootstrap_registers_b1_logical_datasets_without_routes() -> None:
    """A market allow-list cannot register OpenBB before a runtime permit exists."""
    async with async_session_maker() as session:
        result = await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()

        resolutions = {
            dataset_code: await DataCatalogResolver(session).resolve_primary(dataset_code)
            for dataset_code in CANONICAL_DATASET_CODES
        }
        await MarketDataStore(session).ensure_provider_active(AKSHARE_PROVIDER_ID)
        datasets = {
            dataset.dataset_code: dataset
            for dataset in (
                await session.execute(
                    select(DgDataset).where(DgDataset.dataset_code.in_(CANONICAL_DATASET_CODES))
                )
            )
            .scalars()
            .all()
        }
        bindings = list(
            (
                await session.execute(
                    select(DgDatasetStorage, DgDataset)
                    .join(DgDataset, DgDatasetStorage.dataset_id == DgDataset.id)
                    .where(DgDataset.dataset_code.in_(CANONICAL_DATASET_CODES))
                )
            ).all()
        )
        provider_ids = list(
            (await session.execute(select(DgProvider.provider_id).order_by(DgProvider.provider_id)))
            .scalars()
            .all()
        )
        endpoint_count = await session.scalar(select(func.count()).select_from(DgEndpoint))

    assert result.openbb_status == "not_configured_runtime_permits_unattested"
    assert result.dataset_code == CANONICAL_DATASET_CODE
    assert result.dataset_codes == CANONICAL_DATASET_CODES
    assert result.as_dict()["dataset_codes"] == list(CANONICAL_DATASET_CODES)
    assert result.registered_provider_ids == (AKSHARE_PROVIDER_ID,)
    assert {resolution.storage_id for resolution in resolutions.values()} == {CANONICAL_STORAGE_ID}
    assert {resolution.physical_table for resolution in resolutions.values()} == {
        CANONICAL_PHYSICAL_TABLE
    }
    assert {resolution.write_mode for resolution in resolutions.values()} == {CANONICAL_WRITE_MODE}
    assert len({resolution.dataset_id for resolution in resolutions.values()}) == len(
        CANONICAL_DATASET_CODES
    )
    assert set(datasets) == set(CANONICAL_DATASET_CODES)
    bars_dataset = datasets[CANONICAL_DATASET_CODE]
    quote_dataset = datasets[CANONICAL_QUOTE_SNAPSHOT_DATASET_CODE]
    captured_valuation_dataset = datasets[CANONICAL_STOCK_VALUATION_CAPTURED_SNAPSHOT_DATASET_CODE]
    assert bars_dataset.canonical_schema["supported_asset_types"] == list(SUPPORTED_ASSET_TYPES)
    assert bars_dataset.primary_key == [
        "semantic_key_sha256",
        "event_time",
        "available_at",
        "source_snapshot_id",
        "revision_number",
    ]
    assert quote_dataset.canonical_schema["schema_version"] == "market-quote-snapshot-v1"
    assert quote_dataset.canonical_schema["data_kind"] == "quote_snapshot"
    quote_fields = quote_dataset.canonical_schema["observation_fields"]
    assert quote_fields["price"] == "decimal|null"
    assert quote_fields["turnover"] == "decimal|null"
    assert "last" not in quote_fields
    assert "amount" not in quote_fields
    assert quote_dataset.primary_key == bars_dataset.primary_key
    captured_valuation_schema = captured_valuation_dataset.canonical_schema
    assert captured_valuation_schema["schema_version"] == (
        "market-stock-valuation-captured-snapshot-v1"
    )
    assert captured_valuation_schema["internal_only"] is True
    assert captured_valuation_schema["data_kind"] == "valuation_snapshot"
    assert captured_valuation_schema["frequency"] == "snapshot"
    assert captured_valuation_schema["frequency_semantics"] == "snapshot"
    assert captured_valuation_schema["time_basis"] == "collector_observed"
    assert captured_valuation_schema["supported_asset_types"] == ["stock"]
    assert {
        "market_cap",
        "float_market_cap",
        "pe",
        "pb",
    } <= set(captured_valuation_schema["observation_fields"])
    assert "as_of" not in captured_valuation_schema["observation_fields"]
    assert captured_valuation_schema["provenance_constraints"] == {
        "source_event_time": None,
        "source_as_of": None,
        "time_basis": "collector_observed",
    }
    assert captured_valuation_dataset.primary_key == bars_dataset.primary_key
    expected_reference_schemas = {
        "market.valuation": ("stock", {"market_cap", "float_market_cap", "pe", "pb", "as_of"}),
        "market.liquidity": ("stock", {"volume", "turnover", "turnover_rate"}),
        "market.settlement": ("futures", {"settle", "previous_settle", "open_interest"}),
        "market.bond_reference": (
            "bond",
            {"yield_to_maturity", "coupon", "maturity_date", "previous_close"},
        ),
        "market.fund_nav": ("fund", {"nav", "cumulative_nav", "daily_growth_rate"}),
        "market.fx_reference": (
            "fx",
            {"rate", "previous_close", "base_currency", "quote_currency"},
        ),
    }
    for dataset_code, (asset_type, required_fields) in expected_reference_schemas.items():
        dataset = datasets[dataset_code]
        schema = dataset.canonical_schema
        assert schema["data_kind"] == "reference_series"
        assert schema["supported_asset_types"] == [asset_type] or (
            dataset_code == "market.liquidity"
            and schema["supported_asset_types"] == ["stock", "fund"]
        )
        assert required_fields <= set(schema["observation_fields"])
        assert dataset.primary_key == bars_dataset.primary_key
    assert {(binding.physical_table, binding.is_primary) for binding, _ in bindings} == {
        (CANONICAL_PHYSICAL_TABLE, True)
    }
    assert {dataset.dataset_code for _, dataset in bindings} == set(CANONICAL_DATASET_CODES)
    assert len({binding.id for binding, _ in bindings}) == len(CANONICAL_DATASET_CODES)
    assert provider_ids == [AKSHARE_PROVIDER_ID]
    assert endpoint_count == 0


def test_bootstrap_schema_contract_covers_every_iteration197_market_table() -> None:
    """A future table cannot be omitted from the pre-bootstrap readiness gate."""
    assert set(bootstrap_module._REQUIRED_MARKET_TABLES) == {
        "md_publications",
        "md_publication_release_holds",
        "md_visibility_sequence_allocator",
        "md_instrument_identity_revisions",
        "md_calendar_import_locks",
        "md_instrument_lookup_keys",
        "md_data_series",
        "md_source_snapshots",
        "md_b2_completeness_receipts",
        "md_b2_completeness_manifest_entries",
        "md_observation_revisions",
        "md_calendar_snapshots",
        "md_calendar_events",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "drop_statement",
    ("DROP TABLE md_calendar_events", "DROP TABLE md_publication_release_holds"),
)
async def test_bootstrap_refuses_when_a_noncanonical_market_table_is_missing(
    drop_statement: str,
) -> None:
    """A partial md_* migration cannot register a catalog that later readers cannot use."""
    async with async_session_maker() as session:
        await session.execute(text(drop_statement))
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
async def test_bootstrap_refuses_the_pre_f2_shared_binding_constraint_shape() -> None:
    """The candidate DDL is a hard prerequisite, not an IntegrityError fallback."""
    async with async_session_maker() as session:
        connection = await session.connection()
        rejected = await connection.run_sync(_legacy_shared_binding_constraint_is_rejected)

    assert rejected


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

    assert len(first.created) == 2 + 2 * len(CANONICAL_DATASET_CODES)
    assert first.dataset_code == CANONICAL_DATASET_CODE
    assert first.dataset_codes == CANONICAL_DATASET_CODES
    assert second.created == ()
    assert second.dataset_codes == CANONICAL_DATASET_CODES
    assert set(second.verified) == {
        "storage:canonical_market_data",
        "dataset:market.bars",
        *(f"dataset:{dataset_code}" for dataset_code in CANONICAL_DATASET_CODES),
        *(f"binding:{dataset_code}" for dataset_code in CANONICAL_DATASET_CODES),
        "provider:akshare",
    }
    assert counts == {
        "storage": 1,
        "dataset": len(CANONICAL_DATASET_CODES),
        "binding": len(CANONICAL_DATASET_CODES),
        "provider": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("drifted_field", ["canonical_schema", "primary_key"])
async def test_bootstrap_rejects_quote_snapshot_dataset_contract_drift(
    drifted_field: str,
) -> None:
    """The quote dataset cannot be silently repurposed after its first registration."""
    async with async_session_maker() as session:
        await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()
        quote_dataset = await session.scalar(
            select(DgDataset).where(DgDataset.dataset_code == CANONICAL_QUOTE_SNAPSHOT_DATASET_CODE)
        )
        assert quote_dataset is not None
        if drifted_field == "canonical_schema":
            quote_dataset.canonical_schema = {
                **dict(quote_dataset.canonical_schema),
                "data_kind": "bars",
            }
        else:
            quote_dataset.primary_key = ["event_time"]
        await session.commit()

        with pytest.raises(MarketDataBootstrapError) as blocked:
            await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.rollback()

    assert blocked.value.code == "MARKET_DATA_BOOTSTRAP_DATASET_CONFLICT"


@pytest.mark.asyncio
async def test_bootstrap_rejects_an_unreviewed_dataset_claim_on_the_shared_facts_table() -> None:
    """Only reviewed B1 logical datasets may use this bootstrap's shared binding."""
    async with async_session_maker() as session:
        await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()
        storage = await session.scalar(
            select(DgStorageTarget).where(DgStorageTarget.storage_id == CANONICAL_STORAGE_ID)
        )
        assert storage is not None
        unreviewed = DgDataset(
            dataset_code="market.unreviewed",
            display_name="Unreviewed market product",
            domain="market",
            canonical_schema={},
            primary_key=[],
            is_active=True,
        )
        session.add(unreviewed)
        await session.flush()
        session.add(
            DgDatasetStorage(
                dataset_id=unreviewed.id,
                storage_target_id=storage.id,
                physical_table=CANONICAL_PHYSICAL_TABLE,
                write_mode=CANONICAL_WRITE_MODE,
                is_primary=True,
            )
        )
        await session.commit()

        with pytest.raises(MarketDataBootstrapError) as blocked:
            await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.rollback()

    assert blocked.value.code == "MARKET_DATA_BOOTSTRAP_PHYSICAL_BINDING_CONFLICT"


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
    """An intentional registered-provider kill switch remains operator-owned on later runs."""
    async with async_session_maker() as session:
        await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.commit()
        provider = await session.scalar(
            select(DgProvider).where(DgProvider.provider_id == AKSHARE_PROVIDER_ID)
        )
        assert provider is not None
        provider.is_active = False
        await session.commit()

        with pytest.raises(MarketDataBootstrapError) as blocked:
            await MarketDataPlatformBootstrapper(session).bootstrap(_spec())
        await session.rollback()
        restored = await session.scalar(
            select(DgProvider).where(DgProvider.provider_id == AKSHARE_PROVIDER_ID)
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


def test_settings_spec_keeps_a_mixed_case_openbb_provider_unregistered_without_a_permit() -> None:
    """A normalized provider plus a market list remains only configuration, not authority."""
    settings = SimpleNamespace(
        DATABASE_URL="sqlite+aiosqlite:////tmp/backtrader.db",
        MARKET_DATA_OPENBB_PROVIDER="YFinance",
        MARKET_DATA_OPENBB_ALLOWED_MARKETS="US-NYSE",
    )

    spec = MarketDataBootstrapSpec.from_settings(settings)

    assert spec.openbb_provider == "yfinance"
    assert spec.openbb_provider_id is None


def test_bootstrap_spec_rejects_an_openbb_provider_without_a_verified_runner_contract() -> None:
    """The catalog cannot register a provider merely because its name is syntactically valid."""
    with pytest.raises(MarketDataBootstrapError) as rejected:
        MarketDataBootstrapSpec(
            storage=CanonicalStorageSpec.from_database_url("sqlite+aiosqlite://"),
            openbb_provider="unreviewed_provider",
            openbb_allowed_markets=("US-NYSE",),
        )

    assert rejected.value.code == "MARKET_DATA_BOOTSTRAP_OPENBB_PROVIDER_UNSUPPORTED"
