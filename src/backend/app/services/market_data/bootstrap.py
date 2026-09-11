"""Idempotent, operator-triggered bootstrap for the Iteration 197 catalog.

The public local-first query path deliberately never creates catalog rows.  An
operator runs the accompanying CLI after the Alembic revisions are applied;
this module then registers the canonical normalized store, its reviewed bars
and quote-snapshot datasets, and only the providers whose route configuration
has been reviewed.

The canonical facts live in ``md_observation_revisions``.  Asset type,
identity, frequency, and policy remain dimensions of the semantic series key,
so logical datasets can share the same revision table without inventing
duplicate physical facts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from sqlalchemy import UniqueConstraint, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_governance import DgDataset, DgDatasetStorage, DgProvider, DgStorageTarget
from app.models.market_data_platform import (
    MdB2CompletenessManifestEntry,
    MdB2CompletenessReceipt,
    MdCalendarEvent,
    MdCalendarImportLock,
    MdCalendarSnapshot,
    MdDataSeries,
    MdInstrumentIdentityRevision,
    MdInstrumentLookupKey,
    MdObservationRevision,
    MdPublication,
    MdPublicationReleaseHold,
    MdSourceSnapshot,
    MdVisibilitySequenceAllocator,
)
from app.services.market_data.openbb_runtime import (
    SUPPORTED_OPENBB_RUNNER_PROVIDERS,
    approved_openbb_runtime_route_permits,
    openbb_runtime_registration_status,
)

CANONICAL_STORAGE_ID = "canonical_market_data"
CANONICAL_STORAGE_URL_ENV = "DATABASE_URL"
CANONICAL_STORAGE_ROLE = "canonical"
CANONICAL_PHYSICAL_TABLE = "md_observation_revisions"
CANONICAL_DATASET_CODE = "market.bars"
CANONICAL_QUOTE_SNAPSHOT_DATASET_CODE = "market.quote_snapshot"
CANONICAL_STOCK_VALUATION_CAPTURED_SNAPSHOT_DATASET_CODE = (
    "market.stock_valuation_captured_snapshot"
)
CANONICAL_VALUATION_DATASET_CODE = "market.valuation"
CANONICAL_LIQUIDITY_DATASET_CODE = "market.liquidity"
CANONICAL_SETTLEMENT_DATASET_CODE = "market.settlement"
CANONICAL_BOND_REFERENCE_DATASET_CODE = "market.bond_reference"
CANONICAL_FUND_NAV_DATASET_CODE = "market.fund_nav"
CANONICAL_FX_REFERENCE_DATASET_CODE = "market.fx_reference"
CANONICAL_REFERENCE_SERIES_DATASET_CODES = (
    CANONICAL_VALUATION_DATASET_CODE,
    CANONICAL_LIQUIDITY_DATASET_CODE,
    CANONICAL_SETTLEMENT_DATASET_CODE,
    CANONICAL_BOND_REFERENCE_DATASET_CODE,
    CANONICAL_FUND_NAV_DATASET_CODE,
    CANONICAL_FX_REFERENCE_DATASET_CODE,
)
CANONICAL_DATASET_CODES = (
    CANONICAL_DATASET_CODE,
    CANONICAL_QUOTE_SNAPSHOT_DATASET_CODE,
    CANONICAL_STOCK_VALUATION_CAPTURED_SNAPSHOT_DATASET_CODE,
    *CANONICAL_REFERENCE_SERIES_DATASET_CODES,
)
CANONICAL_WRITE_MODE = "canonical_append_only"
AKSHARE_PROVIDER_ID = "akshare"
SUPPORTED_ASSET_TYPES = (
    "stock",
    "futures",
    "bond",
    "fund",
    "option",
    "fx",
    "crypto",
)
_PROVIDER_TOKEN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SUPPORTED_ENGINES = frozenset({"sqlite", "mysql", "postgresql"})
_REQUIRED_TABLE_COLUMNS: Mapping[str, frozenset[str]] = {
    "dg_providers": frozenset(
        {
            "id",
            "provider_id",
            "name",
            "category",
            "auth_type",
            "rate_limit",
            "is_active",
        }
    ),
    "dg_datasets": frozenset(
        {
            "id",
            "dataset_code",
            "display_name",
            "domain",
            "canonical_schema",
            "primary_key",
            "is_active",
        }
    ),
    "dg_storage_targets": frozenset(
        {
            "id",
            "storage_id",
            "engine",
            "url_env",
            "database_name",
            "role",
            "is_active",
        }
    ),
    "dg_dataset_storages": frozenset(
        {
            "id",
            "dataset_id",
            "storage_target_id",
            "physical_table",
            "write_mode",
            "is_primary",
            "primary_dataset_id",
        }
    ),
    CANONICAL_PHYSICAL_TABLE: frozenset(
        {
            "id",
            "series_id",
            "event_time",
            "available_at",
            "source_snapshot_id",
            "revision_number",
        }
    ),
}
_REQUIRED_CATALOG_UNIQUES: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "dg_dataset_storages": {
        "uq_dg_dataset_storage_target_table": (
            "storage_target_id",
            "physical_table",
            "dataset_id",
        ),
        "uq_dg_dataset_storages_primary_dataset": ("primary_dataset_id",),
    }
}


@dataclass(frozen=True, slots=True)
class _ForeignKeyRequirement:
    """One portable referential-integrity contract reflected from a model table."""

    constrained_columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MarketTableRequirement:
    """The schema features needed by local-first query and persistence paths."""

    required_columns: frozenset[str]
    primary_key_columns: tuple[str, ...]
    unique_column_sets: frozenset[frozenset[str]]
    index_column_sequences: frozenset[tuple[str, ...]]
    foreign_keys: frozenset[_ForeignKeyRequirement]


def _market_table_requirement(table: Any) -> _MarketTableRequirement:
    """Build a dialect-neutral bootstrap contract from the mapped data model.

    The model and Alembic revision are tested for parity separately.  Keeping
    this contract model-derived makes schema readiness advance with a storage
    feature instead of leaving a manually maintained, partial list of
    ``md_*`` tables behind.
    """
    unique_column_sets = {
        frozenset(str(column.name) for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    unique_column_sets.update(
        frozenset((str(column.name),)) for column in table.columns if column.unique
    )
    foreign_keys = {
        _ForeignKeyRequirement(
            constrained_columns=tuple(str(element.parent.name) for element in constraint.elements),
            referred_table=str(constraint.elements[0].column.table.name),
            referred_columns=tuple(str(element.column.name) for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }
    return _MarketTableRequirement(
        required_columns=frozenset(str(column.name) for column in table.columns),
        primary_key_columns=tuple(str(column.name) for column in table.primary_key.columns),
        unique_column_sets=frozenset(unique_column_sets),
        index_column_sequences=frozenset(
            tuple(str(column.name) for column in index.columns) for index in table.indexes
        ),
        foreign_keys=frozenset(foreign_keys),
    )


_REQUIRED_MARKET_TABLES: Mapping[str, _MarketTableRequirement] = {
    model.__tablename__: _market_table_requirement(model.__table__)
    for model in (
        MdPublication,
        MdPublicationReleaseHold,
        MdVisibilitySequenceAllocator,
        MdInstrumentIdentityRevision,
        MdCalendarImportLock,
        MdInstrumentLookupKey,
        MdDataSeries,
        MdSourceSnapshot,
        MdB2CompletenessReceipt,
        MdB2CompletenessManifestEntry,
        MdObservationRevision,
        MdCalendarSnapshot,
        MdCalendarEvent,
    )
}


class MarketDataBootstrapError(RuntimeError):
    """Stable failure returned before an unsafe catalog mutation is committed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CanonicalStorageSpec:
    """A non-secret registration record for the application database."""

    engine: str
    database_name: str
    url_env: str = CANONICAL_STORAGE_URL_ENV
    storage_id: str = CANONICAL_STORAGE_ID
    role: str = CANONICAL_STORAGE_ROLE

    def __post_init__(self) -> None:
        if self.engine not in _SUPPORTED_ENGINES:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_ENGINE_UNSUPPORTED")
        if not self.database_name or len(self.database_name) > 100:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATABASE_NAME_INVALID")
        if self.url_env != CANONICAL_STORAGE_URL_ENV:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_STORAGE_ENV_INVALID")
        if self.storage_id != CANONICAL_STORAGE_ID or self.role != CANONICAL_STORAGE_ROLE:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_STORAGE_IDENTITY_INVALID")

    @classmethod
    def from_database_url(cls, database_url: str) -> CanonicalStorageSpec:
        """Build a secret-free storage registration from a SQLAlchemy URL."""
        try:
            parsed = make_url(database_url)
        except Exception as exc:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATABASE_URL_INVALID") from exc
        engine = parsed.drivername.split("+", maxsplit=1)[0].lower()
        if engine == "postgres":
            engine = "postgresql"
        if engine not in _SUPPORTED_ENGINES:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_ENGINE_UNSUPPORTED")
        database_name = _database_name(parsed.database, engine=engine)
        return cls(engine=engine, database_name=database_name)


@dataclass(frozen=True, slots=True)
class MarketDataBootstrapSpec:
    """The reviewed catalog records an operator intends to materialize."""

    storage: CanonicalStorageSpec
    openbb_provider: str | None = None
    openbb_allowed_markets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        provider = _normalize_openbb_provider(self.openbb_provider)
        markets = _normalize_markets(self.openbb_allowed_markets)
        if markets and provider is None:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_OPENBB_PROVIDER_REQUIRED")
        if provider is not None and provider not in SUPPORTED_OPENBB_RUNNER_PROVIDERS:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_OPENBB_PROVIDER_UNSUPPORTED")
        object.__setattr__(self, "openbb_provider", provider)
        object.__setattr__(self, "openbb_allowed_markets", markets)

    @classmethod
    def from_settings(cls, settings: Any) -> MarketDataBootstrapSpec:
        """Translate the existing runtime settings without persisting secrets."""
        allowed_markets = tuple(
            item.strip()
            for item in str(settings.MARKET_DATA_OPENBB_ALLOWED_MARKETS).split(",")
            if item.strip()
        )
        return cls(
            storage=CanonicalStorageSpec.from_database_url(str(settings.DATABASE_URL)),
            openbb_provider=settings.MARKET_DATA_OPENBB_PROVIDER,
            openbb_allowed_markets=allowed_markets,
        )

    @property
    def openbb_provider_id(self) -> str | None:
        """Return a receipt provider only when an exact runtime permit exists."""
        if self.openbb_provider is None or not self.openbb_allowed_markets:
            return None
        if not approved_openbb_runtime_route_permits(
            self.openbb_provider, self.openbb_allowed_markets
        ):
            return None
        return f"openbb:{self.openbb_provider}"


@dataclass(frozen=True, slots=True)
class MarketDataBootstrapResult:
    """A serializable account of records created or verified by one run."""

    storage_id: str
    dataset_code: str
    registered_provider_ids: tuple[str, ...]
    created: tuple[str, ...]
    verified: tuple[str, ...]
    openbb_status: str
    # ``dataset_code`` remains the legacy bars entrypoint for operator callers.
    # The ordered tuple exposes every catalog product this bootstrap guarantees.
    dataset_codes: tuple[str, ...] = CANONICAL_DATASET_CODES
    supported_asset_types: tuple[str, ...] = SUPPORTED_ASSET_TYPES

    def as_dict(self) -> dict[str, object]:
        """Return operator-safe output with no database URL or credentials."""
        return {
            "storage_id": self.storage_id,
            "dataset_code": self.dataset_code,
            "dataset_codes": list(self.dataset_codes),
            "registered_provider_ids": list(self.registered_provider_ids),
            "created": list(self.created),
            "verified": list(self.verified),
            "openbb_status": self.openbb_status,
            "supported_asset_types": list(self.supported_asset_types),
        }


class MarketDataPlatformBootstrapper:
    """Create the fixed 197 control-plane prerequisites in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bootstrap(self, spec: MarketDataBootstrapSpec) -> MarketDataBootstrapResult:
        """Register missing approved catalog records and fail closed on drift.

        The caller owns commit or rollback.  That makes ``--dry-run`` and a
        deployment transaction observable without a public request ever being
        able to seed or reactivate a provider.
        """
        if not isinstance(spec, MarketDataBootstrapSpec):
            raise TypeError("spec must be a MarketDataBootstrapSpec")
        await self._assert_schema_ready(expected_engine=spec.storage.engine)

        created: list[str] = []
        verified: list[str] = []
        storage = await self._ensure_storage(spec.storage, created=created, verified=verified)
        datasets: list[DgDataset] = []
        for dataset_code, display_name, canonical_schema, primary_key in _canonical_dataset_specs():
            datasets.append(
                await self._ensure_dataset(
                    dataset_code=dataset_code,
                    display_name=display_name,
                    canonical_schema=canonical_schema,
                    primary_key=primary_key,
                    created=created,
                    verified=verified,
                )
            )
        for dataset in datasets:
            await self._ensure_primary_binding(
                dataset=dataset,
                storage=storage,
                created=created,
                verified=verified,
            )

        provider_ids = [
            await self._ensure_provider(
                provider_id=AKSHARE_PROVIDER_ID,
                name="AkShare",
                category="market_data",
                created=created,
                verified=verified,
            )
        ]
        if spec.openbb_provider_id is not None:
            provider_ids.append(
                await self._ensure_provider(
                    provider_id=spec.openbb_provider_id,
                    name=f"OpenBB {spec.openbb_provider}",
                    category="market_data",
                    created=created,
                    verified=verified,
                )
            )
            openbb_status = "registered"
        else:
            openbb_status = openbb_runtime_registration_status(
                provider=spec.openbb_provider,
                allowed_markets=spec.openbb_allowed_markets,
            )

        await self._session.flush()
        return MarketDataBootstrapResult(
            storage_id=storage.storage_id,
            dataset_code=CANONICAL_DATASET_CODE,
            registered_provider_ids=tuple(provider_ids),
            created=tuple(created),
            verified=tuple(verified),
            openbb_status=openbb_status,
            dataset_codes=tuple(dataset.dataset_code for dataset in datasets),
        )

    async def _assert_schema_ready(self, *, expected_engine: str) -> None:
        connection = await self._session.connection()
        actual_engine = str(connection.dialect.name).lower()
        if actual_engine == "postgres":
            actual_engine = "postgresql"
        if actual_engine != expected_engine:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_ENGINE_MISMATCH")
        try:
            missing_parts = await connection.run_sync(_missing_schema_parts)
        except Exception as exc:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_SCHEMA_UNREADY") from exc
        if missing_parts:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_SCHEMA_UNREADY")

    async def _ensure_storage(
        self,
        spec: CanonicalStorageSpec,
        *,
        created: list[str],
        verified: list[str],
    ) -> DgStorageTarget:
        rows = await _rows_for_unique(
            self._session,
            select(DgStorageTarget).where(DgStorageTarget.storage_id == spec.storage_id),
        )
        if len(rows) > 1:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_STORAGE_INTEGRITY")
        if not rows:
            record = DgStorageTarget(
                storage_id=spec.storage_id,
                engine=spec.engine,
                url_env=spec.url_env,
                database_name=spec.database_name,
                role=spec.role,
                is_active=True,
            )
            self._session.add(record)
            await self._session.flush()
            created.append(f"storage:{spec.storage_id}")
            return record

        record = rows[0]
        if (
            record.engine != spec.engine
            or record.url_env != spec.url_env
            or record.database_name != spec.database_name
            or record.role != spec.role
        ):
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_STORAGE_CONFLICT")
        if not record.is_active:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_STORAGE_INACTIVE")
        verified.append(f"storage:{spec.storage_id}")
        return record

    async def _ensure_dataset(
        self,
        *,
        dataset_code: str,
        display_name: str,
        canonical_schema: Mapping[str, object],
        primary_key: Sequence[str],
        created: list[str],
        verified: list[str],
    ) -> DgDataset:
        rows = await _rows_for_unique(
            self._session,
            select(DgDataset).where(DgDataset.dataset_code == dataset_code),
        )
        if len(rows) > 1:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATASET_INTEGRITY")
        if not rows:
            record = DgDataset(
                dataset_code=dataset_code,
                display_name=display_name,
                domain="market",
                canonical_schema=dict(canonical_schema),
                primary_key=list(primary_key),
                is_active=True,
            )
            self._session.add(record)
            await self._session.flush()
            created.append(f"dataset:{dataset_code}")
            return record

        record = rows[0]
        if (
            record.display_name != display_name
            or record.domain != "market"
            or not _same_json(record.canonical_schema, canonical_schema)
            or not _same_json(record.primary_key, primary_key)
        ):
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATASET_CONFLICT")
        if not record.is_active:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATASET_INACTIVE")
        verified.append(f"dataset:{dataset_code}")
        return record

    async def _ensure_primary_binding(
        self,
        *,
        dataset: DgDataset,
        storage: DgStorageTarget,
        created: list[str],
        verified: list[str],
    ) -> DgDatasetStorage:
        rows = await _rows_for_unique(
            self._session,
            select(DgDatasetStorage).where(DgDatasetStorage.dataset_id == dataset.id),
        )
        primary_rows = [row for row in rows if row.is_primary]
        if len(primary_rows) > 1:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PRIMARY_BINDING_INTEGRITY")
        shared_bindings = await self._shared_physical_bindings(storage=storage)
        if any(
            shared_dataset.dataset_code not in CANONICAL_DATASET_CODES
            for _, shared_dataset in shared_bindings
        ):
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PHYSICAL_BINDING_CONFLICT")
        if primary_rows:
            record = primary_rows[0]
            if (
                record.storage_target_id != storage.id
                or record.physical_table != CANONICAL_PHYSICAL_TABLE
                or record.write_mode != CANONICAL_WRITE_MODE
                or record.primary_dataset_id != dataset.id
            ):
                raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PRIMARY_BINDING_CONFLICT")
            verified.append(f"binding:{dataset.dataset_code}")
            return record

        if any(binding.dataset_id == dataset.id for binding, _ in shared_bindings):
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PRIMARY_BINDING_CONFLICT")
        record = DgDatasetStorage(
            dataset_id=dataset.id,
            storage_target_id=storage.id,
            physical_table=CANONICAL_PHYSICAL_TABLE,
            write_mode=CANONICAL_WRITE_MODE,
            is_primary=True,
        )
        self._session.add(record)
        await self._session.flush()
        created.append(f"binding:{dataset.dataset_code}")
        return record

    async def _shared_physical_bindings(
        self,
        *,
        storage: DgStorageTarget,
    ) -> list[tuple[DgDatasetStorage, DgDataset]]:
        """Return all catalog claims on the shared normalized fact table.

        The migration permits exactly the reviewed canonical datasets to share
        the table.  Any third product must add an explicit storage contract
        rather than silently piggybacking on this bootstrap's write binding.
        """
        rows = await self._session.execute(
            select(DgDatasetStorage, DgDataset)
            .join(DgDataset, DgDatasetStorage.dataset_id == DgDataset.id)
            .where(
                DgDatasetStorage.storage_target_id == storage.id,
                DgDatasetStorage.physical_table == CANONICAL_PHYSICAL_TABLE,
            )
        )
        return list(rows.all())

    async def _ensure_provider(
        self,
        *,
        provider_id: str,
        name: str,
        category: str,
        created: list[str],
        verified: list[str],
    ) -> str:
        rows = await _rows_for_unique(
            self._session,
            select(DgProvider).where(DgProvider.provider_id == provider_id),
        )
        if len(rows) > 1:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PROVIDER_INTEGRITY")
        if not rows:
            self._session.add(
                DgProvider(
                    provider_id=provider_id,
                    name=name,
                    category=category,
                    auth_type="none",
                    rate_limit=60,
                    is_active=True,
                )
            )
            await self._session.flush()
            created.append(f"provider:{provider_id}")
            return provider_id

        record = rows[0]
        if (
            record.name != name
            or record.category != category
            or record.auth_type != "none"
            or record.api_key_env is not None
        ):
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PROVIDER_CONFLICT")
        if not record.is_active:
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_PROVIDER_INACTIVE")
        verified.append(f"provider:{provider_id}")
        return provider_id


def _database_name(value: str | None, *, engine: str) -> str:
    """Return an identifier suitable for the catalog, never the full connection URL."""
    if not value:
        if engine == "sqlite":
            return ":memory:"
        raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATABASE_NAME_INVALID")
    if engine == "sqlite":
        value = PurePath(value).name or value
    if len(value) > 100:
        raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_DATABASE_NAME_INVALID")
    return value


def _normalize_openbb_provider(value: str | None) -> str | None:
    """Validate a provider name before it can become a persisted provider ID."""
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if not _PROVIDER_TOKEN_PATTERN.fullmatch(normalized):
        raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_OPENBB_PROVIDER_INVALID")
    return normalized


def _normalize_markets(values: Iterable[str]) -> tuple[str, ...]:
    """Retain reviewed venue names exactly while rejecting malformed tokens."""
    if isinstance(values, (str, bytes)):
        raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_OPENBB_MARKETS_INVALID")
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or len(item) > 128 or any(character.isspace() for character in item):
            raise MarketDataBootstrapError("MARKET_DATA_BOOTSTRAP_OPENBB_MARKETS_INVALID")
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def _canonical_dataset_specs() -> tuple[tuple[str, str, dict[str, object], list[str]], ...]:
    """Return the fixed, operator-owned contracts for normalized facts.

    Registering a dataset only makes its catalog/storage contract resolvable.
    It intentionally creates no endpoint, source policy, provider route, or
    request-time quote-fetch capability.
    """
    return (
        (
            CANONICAL_DATASET_CODE,
            "Unified market bars",
            _canonical_bars_schema(),
            _canonical_bars_primary_key(),
        ),
        (
            CANONICAL_QUOTE_SNAPSHOT_DATASET_CODE,
            "Unified market quote snapshots",
            _canonical_quote_snapshot_schema(),
            _canonical_quote_snapshot_primary_key(),
        ),
        (
            CANONICAL_STOCK_VALUATION_CAPTURED_SNAPSHOT_DATASET_CODE,
            "Internal captured stock valuation snapshots",
            _canonical_stock_valuation_captured_snapshot_schema(),
            _canonical_observation_revision_primary_key(),
        ),
        (
            CANONICAL_VALUATION_DATASET_CODE,
            "Stock valuation reference series",
            _canonical_valuation_schema(),
            _canonical_reference_series_primary_key(),
        ),
        (
            CANONICAL_LIQUIDITY_DATASET_CODE,
            "Market liquidity reference series",
            _canonical_liquidity_schema(),
            _canonical_reference_series_primary_key(),
        ),
        (
            CANONICAL_SETTLEMENT_DATASET_CODE,
            "Futures settlement reference series",
            _canonical_settlement_schema(),
            _canonical_reference_series_primary_key(),
        ),
        (
            CANONICAL_BOND_REFERENCE_DATASET_CODE,
            "Bond fixed-income reference series",
            _canonical_bond_reference_schema(),
            _canonical_reference_series_primary_key(),
        ),
        (
            CANONICAL_FUND_NAV_DATASET_CODE,
            "Fund NAV reference series",
            _canonical_fund_nav_schema(),
            _canonical_reference_series_primary_key(),
        ),
        (
            CANONICAL_FX_REFERENCE_DATASET_CODE,
            "FX reference series",
            _canonical_fx_reference_schema(),
            _canonical_reference_series_primary_key(),
        ),
    )


def _canonical_bars_schema() -> dict[str, object]:
    """Describe the shared bars contract without collapsing asset semantics."""
    return {
        "schema_version": "market-bars-v1",
        "data_kind": "bars",
        "supported_asset_types": list(SUPPORTED_ASSET_TYPES),
        "identity_fields": [
            "canonical_id",
            "asset_type",
            "market",
            "instrument_metadata_version",
        ],
        "series_dimensions": [
            "frequency",
            "adjustment",
            "price_basis",
            "currency",
            "unit",
            "source_policy_id",
        ],
        "observation_fields": {
            "event_time": "timestamp",
            "event_end": "timestamp|null",
            "available_at": "timestamp",
            "open": "decimal|null",
            "high": "decimal|null",
            "low": "decimal|null",
            "close": "decimal|null",
            "volume": "decimal|null",
            "amount": "decimal|null",
            "settle": "decimal|null",
            "open_interest": "decimal|null",
        },
        "provenance_fields": [
            "source_snapshot_id",
            "revision_number",
            "quality_status",
            "normalization_version",
        ],
    }


def _canonical_bars_primary_key() -> list[str]:
    """Return the immutable revision identity exposed by the normalized fact store."""
    return _canonical_observation_revision_primary_key()


def _canonical_quote_snapshot_schema() -> dict[str, object]:
    """Describe point-in-time quote facts stored beside, but apart from, bars."""
    return {
        "schema_version": "market-quote-snapshot-v1",
        "data_kind": "quote_snapshot",
        "supported_asset_types": list(SUPPORTED_ASSET_TYPES),
        "identity_fields": [
            "canonical_id",
            "asset_type",
            "market",
            "instrument_metadata_version",
        ],
        "series_dimensions": [
            "frequency",
            "price_basis",
            "currency",
            "unit",
            "source_policy_id",
        ],
        "observation_fields": {
            "event_time": "timestamp",
            "event_end": "timestamp|null",
            "available_at": "timestamp",
            "price": "decimal|null",
            "bid": "decimal|null",
            "ask": "decimal|null",
            "bid_size": "decimal|null",
            "ask_size": "decimal|null",
            "volume": "decimal|null",
            "turnover": "decimal|null",
            "settle": "decimal|null",
            "open_interest": "decimal|null",
        },
        "provenance_fields": [
            "source_snapshot_id",
            "revision_number",
            "quality_status",
            "normalization_version",
        ],
    }


def _canonical_quote_snapshot_primary_key() -> list[str]:
    """Return quote revision identity without claiming bars share its semantics."""
    return _canonical_observation_revision_primary_key()


def _canonical_stock_valuation_captured_snapshot_schema() -> dict[str, object]:
    """Describe the private collector-observed valuation snapshot candidate.

    This is an internal logical dataset over the shared immutable revision
    table.  It has no public family, route, freshness policy, or declared
    coverage semantics.  The capture instant is an observation timestamp, not
    a source-row event time or a daily valuation ``as_of`` claim.
    """
    return {
        "schema_version": "market-stock-valuation-captured-snapshot-v1",
        "internal_only": True,
        "data_kind": "valuation_snapshot",
        "frequency": "snapshot",
        "frequency_semantics": "snapshot",
        "time_basis": "collector_observed",
        "supported_asset_types": ["stock"],
        "identity_fields": [
            "canonical_id",
            "asset_type",
            "market",
            "instrument_metadata_version",
        ],
        "series_dimensions": [
            "frequency",
            "adjustment",
            "price_basis",
            "currency",
            "unit",
            "source_policy_id",
        ],
        "observation_fields": {
            "event_time": "timestamp",
            "event_end": "timestamp|null",
            "available_at": "timestamp",
            "market_cap": "decimal|null",
            "float_market_cap": "decimal|null",
            "pe": "decimal|null",
            "pb": "decimal|null",
        },
        "provenance_constraints": {
            "source_event_time": None,
            "source_as_of": None,
            "time_basis": "collector_observed",
        },
        "provenance_fields": [
            "source_snapshot_id",
            "revision_number",
            "quality_status",
            "normalization_version",
        ],
    }


def _canonical_valuation_schema() -> dict[str, object]:
    """Describe daily stock valuation facts without authorizing their collection."""
    return _canonical_reference_series_schema(
        schema_version="market-valuation-v1",
        supported_asset_types=("stock",),
        observation_fields={
            "market_cap": "decimal|null",
            "float_market_cap": "decimal|null",
            "pe": "decimal|null",
            "pb": "decimal|null",
            "as_of": "date|null",
        },
    )


def _canonical_liquidity_schema() -> dict[str, object]:
    """Describe stock/fund liquidity facts while retaining their asset identity axis."""
    return _canonical_reference_series_schema(
        schema_version="market-liquidity-v1",
        supported_asset_types=("stock", "fund"),
        observation_fields={
            "volume": "decimal|null",
            "turnover": "decimal|null",
            "turnover_rate": "decimal|null",
        },
    )


def _canonical_settlement_schema() -> dict[str, object]:
    """Describe final futures settlement facts, not intraday quote approximations."""
    return _canonical_reference_series_schema(
        schema_version="market-settlement-v1",
        supported_asset_types=("futures",),
        observation_fields={
            "settle": "decimal|null",
            "previous_settle": "decimal|null",
            "open_interest": "decimal|null",
        },
    )


def _canonical_bond_reference_schema() -> dict[str, object]:
    """Describe bond fixed-income observations separate from the quote product."""
    return _canonical_reference_series_schema(
        schema_version="market-bond-reference-v1",
        supported_asset_types=("bond",),
        observation_fields={
            "yield_to_maturity": "decimal|null",
            "coupon": "decimal|null",
            "maturity_date": "date|null",
            "previous_close": "decimal|null",
        },
    )


def _canonical_fund_nav_schema() -> dict[str, object]:
    """Describe fund NAV history rather than inferring NAV from an ETF price bar."""
    return _canonical_reference_series_schema(
        schema_version="market-fund-nav-v1",
        supported_asset_types=("fund",),
        observation_fields={
            "nav": "decimal|null",
            "cumulative_nav": "decimal|null",
            "daily_growth_rate": "decimal|null",
        },
    )


def _canonical_fx_reference_schema() -> dict[str, object]:
    """Describe directed FX reference rates with the quoted currencies retained."""
    return _canonical_reference_series_schema(
        schema_version="market-fx-reference-v1",
        supported_asset_types=("fx",),
        observation_fields={
            "rate": "decimal|null",
            "previous_close": "decimal|null",
            "base_currency": "string|null",
            "quote_currency": "string|null",
        },
    )


def _canonical_reference_series_schema(
    *,
    schema_version: str,
    supported_asset_types: tuple[str, ...],
    observation_fields: Mapping[str, str],
) -> dict[str, object]:
    """Return an inert logical reference-series contract over the revision fact table."""
    return {
        "schema_version": schema_version,
        "data_kind": "reference_series",
        "supported_asset_types": list(supported_asset_types),
        "identity_fields": [
            "canonical_id",
            "asset_type",
            "market",
            "instrument_metadata_version",
        ],
        "series_dimensions": [
            "frequency",
            "adjustment",
            "price_basis",
            "currency",
            "unit",
            "source_policy_id",
        ],
        "observation_fields": {
            "event_time": "timestamp",
            "event_end": "timestamp|null",
            "available_at": "timestamp",
            **dict(observation_fields),
        },
        "provenance_fields": [
            "source_snapshot_id",
            "revision_number",
            "quality_status",
            "normalization_version",
        ],
    }


def _canonical_reference_series_primary_key() -> list[str]:
    """Reference facts share the immutable revision identity, not bars semantics."""
    return _canonical_observation_revision_primary_key()


def _canonical_observation_revision_primary_key() -> list[str]:
    """Return the immutable identity exposed by ``md_observation_revisions``."""
    return [
        "semantic_key_sha256",
        "event_time",
        "available_at",
        "source_snapshot_id",
        "revision_number",
    ]


def _same_json(left: object, right: object) -> bool:
    """Compare JSON-like values without relying on dictionary insertion order."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False
        return all(_same_json(left[key], right[key]) for key in left)
    if (
        isinstance(left, Sequence)
        and not isinstance(left, (str, bytes))
        and isinstance(right, Sequence)
        and not isinstance(right, (str, bytes))
    ):
        return len(left) == len(right) and all(
            _same_json(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


async def _rows_for_unique(session: AsyncSession, statement: Any) -> list[Any]:
    """Load all rows so corrupted duplicate control-plane records fail closed."""
    return list((await session.execute(statement)).scalars().all())


def _missing_schema_parts(connection: Any) -> tuple[str, ...]:
    """Inspect the complete Iteration 197 persistence shape before catalog DML.

    The check intentionally uses reflected column and constraint semantics
    rather than an Alembic revision label.  That keeps startup-created schemas
    supportable while rejecting a partial migration before catalog rows can
    point readers at tables that cannot safely answer or persist a request.
    """
    inspector = inspect(connection)
    missing: list[str] = []
    for table_name, required_columns in _REQUIRED_TABLE_COLUMNS.items():
        if not inspector.has_table(table_name):
            missing.append(table_name)
            continue
        actual = {str(column["name"]) for column in inspector.get_columns(table_name)}
        if not required_columns.issubset(actual):
            missing.append(table_name)
    for table_name, required_uniques in _REQUIRED_CATALOG_UNIQUES.items():
        if not inspector.has_table(table_name):
            continue
        if _catalog_table_unique_constraints_are_incomplete(
            inspector,
            table_name,
            required_uniques,
        ):
            missing.append(table_name)
    for table_name, requirement in _REQUIRED_MARKET_TABLES.items():
        if not inspector.has_table(table_name):
            missing.append(table_name)
            continue
        if _market_table_is_incomplete(inspector, table_name, requirement):
            missing.append(table_name)
    return tuple(missing)


def _catalog_table_unique_constraints_are_incomplete(
    inspector: Any,
    table_name: str,
    required_uniques: Mapping[str, tuple[str, ...]],
) -> bool:
    """Require the catalog's named shared-table and primary-slot invariants.

    Some drivers expose a unique constraint as a unique index.  The named
    contract is accepted in either reflection form, but a two-column legacy
    claim is intentionally not treated as equivalent to the three-column
    dataset-aware binding introduced for quote snapshots.
    """
    reflected: dict[str, tuple[str, ...]] = {}
    for constraint in inspector.get_unique_constraints(table_name) or ():
        name = constraint.get("name")
        columns = constraint.get("column_names")
        if name and columns:
            reflected[str(name)] = tuple(str(column) for column in columns)
    for index in inspector.get_indexes(table_name) or ():
        name = index.get("name")
        columns = index.get("column_names")
        if name and bool(index.get("unique")) and columns:
            sequence = tuple(str(column) for column in columns)
            existing = reflected.get(str(name))
            if existing is not None and existing != sequence:
                return True
            reflected[str(name)] = sequence
    return any(reflected.get(name) != expected for name, expected in required_uniques.items())


def _market_table_is_incomplete(
    inspector: Any,
    table_name: str,
    requirement: _MarketTableRequirement,
) -> bool:
    """Return whether a reflected market table lacks a core storage invariant."""
    actual_columns = {str(column["name"]) for column in inspector.get_columns(table_name)}
    if not requirement.required_columns.issubset(actual_columns):
        return True

    primary_key = inspector.get_pk_constraint(table_name) or {}
    if tuple(str(column) for column in primary_key.get("constrained_columns") or ()) != (
        requirement.primary_key_columns
    ):
        return True

    reflected_unique_sets = {
        frozenset(str(column) for column in constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table_name) or ()
        if constraint.get("column_names")
    }
    reflected_indexes = tuple(inspector.get_indexes(table_name) or ())
    reflected_unique_sets.update(
        frozenset(str(column) for column in index.get("column_names") or ())
        for index in reflected_indexes
        if bool(index.get("unique")) and index.get("column_names")
    )
    if not requirement.unique_column_sets.issubset(reflected_unique_sets):
        return True

    reflected_index_sequences = {
        tuple(str(column) for column in index.get("column_names") or ())
        for index in reflected_indexes
        if index.get("column_names")
    }
    if not requirement.index_column_sequences.issubset(reflected_index_sequences):
        return True

    reflected_foreign_keys = {
        _ForeignKeyRequirement(
            constrained_columns=tuple(
                str(column) for column in foreign_key.get("constrained_columns") or ()
            ),
            referred_table=str(foreign_key.get("referred_table") or ""),
            referred_columns=tuple(
                str(column) for column in foreign_key.get("referred_columns") or ()
            ),
        )
        for foreign_key in inspector.get_foreign_keys(table_name) or ()
        if foreign_key.get("constrained_columns")
    }
    return not requirement.foreign_keys.issubset(reflected_foreign_keys)
