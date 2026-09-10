"""Integration contracts for resolving a public query into local-store semantics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetInstrument
from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget
from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, PublicMarketDataQueryRequest
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.dataset_contracts import (
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
)
from app.services.market_data.identity import MarketDataIdentityResolver
from app.services.market_data.identity_projection import MarketDataIdentityProjectionWriter
from app.services.market_data.query_resolution import (
    MarketDataQueryResolutionError,
    MarketDataQueryResolver,
)

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def _identity(*, version: str = "stock-v1") -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id="instrument:stock:CN-SSE:600000",
        display_symbol="600000",
        name="浦发银行",
        venue="CN-SSE",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="600000",
        product_type="EQUITY",
        metadata_version=version,
        details=StockIdentityDetails(exchange_symbol="600000.SH"),
    )


def _instrument(
    identity: InstrumentIdentity,
    *,
    valid_from: datetime = NOW - timedelta(days=30),
    valid_to: datetime | None = None,
) -> AssetInstrument:
    return AssetInstrument(
        canonical_id=identity.canonical_id,
        asset_type=identity.asset_type,
        identity_level=identity.identity_level,
        venue=identity.venue,
        currency=identity.currency,
        product_type=identity.product_type,
        identity_json=identity.model_dump(mode="json"),
        metadata_version=identity.metadata_version,
        lifecycle_status="ACTIVE",
        valid_from=valid_from,
        valid_to=valid_to,
    )


async def _add_published_instrument(
    session,
    identity: InstrumentIdentity,
    *,
    valid_from: datetime = NOW - timedelta(days=30),
    valid_to: datetime | None = None,
) -> AssetInstrument:
    """Persist one v2 identity fact and its post-commit visibility receipt."""
    instrument = _instrument(identity, valid_from=valid_from, valid_to=valid_to)
    session.add(instrument)
    await session.flush()
    projections = MarketDataIdentityProjectionWriter(session)
    await projections.project(instrument)
    await session.commit()
    await projections.publish_staged()
    return instrument


def _request(**changes: object) -> MarketDataQueryRequest:
    payload: dict[str, object] = {
        "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
        "dataset_code": "market.bars",
        "data_kind": "bars",
        "frequency": "1d",
        "start": "2026-09-08T09:30:00+08:00",
        "end": "2026-09-09T09:30:00+08:00",
        "required_fields": ["close"],
        "adjustment": "qfq",
        "price_basis": "close",
        "currency": "CNY",
        "unit": "share",
        "source_policy_id": "market-default-v1",
        "family_id": "stock.realtime",
        "family_contract_version": "market-data-family-v1",
        "mode": "local_first",
    }
    payload.update(changes)
    return MarketDataQueryRequest.model_validate(payload)


async def _add_catalog(session, *, dataset_code: str = "market.bars") -> None:
    dataset = DgDataset(
        dataset_code=dataset_code,
        display_name="A 股日线",
        domain="market",
        canonical_schema={"event_at": "timestamp", "close": "decimal"},
        primary_key=["canonical_id", "event_at"],
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
    session.add(
        DgDatasetStorage(
            dataset_id=dataset.id,
            storage_target_id=storage.id,
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
            is_primary=True,
        )
    )


@pytest.mark.asyncio
async def test_query_resolver_binds_catalog_identity_and_coverage_key() -> None:
    """A resolved query has one validated version and one registered local target."""
    identity = _identity()
    async with async_session_maker() as db:
        await _add_catalog(db)
        await _add_published_instrument(db, identity)

        result = await MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        ).resolve(_request())

    assert result.query.canonical_id == identity.canonical_id
    assert result.query.instrument_metadata_version == "stock-v1"
    assert result.storage.physical_table == "md_observation_revisions"
    assert result.coverage_identity.canonical_id == identity.canonical_id
    assert result.coverage_identity.asset_type == "stock"
    assert result.coverage_identity.market == "CN-SSE"
    assert result.coverage_identity.instrument_metadata_version == "stock-v1"


@pytest.mark.asyncio
async def test_private_kline_pair_is_preserved_through_resolution_and_coverage_identity() -> None:
    """The legacy bridge's private product pair cannot collapse into generic stock bars."""
    identity = _identity()
    async with async_session_maker() as db:
        await _add_catalog(db)
        await _add_published_instrument(db, identity)
        resolver = MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        )
        kline = await resolver.resolve(
            _request(
                family_id=KLINE_LEGACY_FAMILY_ID,
                family_contract_version=KLINE_LEGACY_CONTRACT_VERSION,
                required_fields=["open", "high", "low", "close", "volume", "change_pct"],
            )
        )
        realtime = await resolver.resolve(_request())

    assert kline.query.family_id == KLINE_LEGACY_FAMILY_ID
    assert kline.query.family_contract_version == KLINE_LEGACY_CONTRACT_VERSION
    assert kline.coverage_identity.family_id == KLINE_LEGACY_FAMILY_ID
    assert kline.coverage_identity.family_contract_version == KLINE_LEGACY_CONTRACT_VERSION
    assert kline.query.query_fingerprint != realtime.query.query_fingerprint
    assert (
        kline.coverage_identity.family_id,
        kline.coverage_identity.family_contract_version,
    ) != (
        realtime.coverage_identity.family_id,
        realtime.coverage_identity.family_contract_version,
    )


@pytest.mark.asyncio
async def test_query_resolver_rechecks_every_axis_of_a_bundle_selected_family() -> None:
    """An executable card stays bound through catalog and identity resolution."""
    identity = _identity()
    async with async_session_maker() as db:
        await _add_catalog(db, dataset_code="market.bars")
        await _add_published_instrument(db, identity)
        resolver = MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        )
        bound = _request(
            dataset_code="market.bars",
            required_fields=["close"],
            family_id="stock.realtime",
            family_contract_version="market-data-family-v1",
        )
        result = await resolver.resolve(bound)

        with pytest.raises(MarketDataQueryResolutionError) as mismatched:
            await resolver.resolve(
                _request(
                    dataset_code="market.bars",
                    required_fields=["close", "volume"],
                    family_id="stock.realtime",
                    family_contract_version="market-data-family-v1",
                )
            )

    assert result.query.family_id == "stock.realtime"
    assert result.query.family_contract_version == "market-data-family-v1"
    assert mismatched.value.code == "DATA_FAMILY_QUERY_CONTRACT_MISMATCH"


@pytest.mark.asyncio
async def test_query_resolver_requires_explicit_exact_fx_range_semantic_axes() -> None:
    """FX's explicit ``None`` axes cannot be replaced by omitted/defaulted values."""

    class _Catalog:
        async def resolve_primary(self, dataset_code: str) -> object:
            return SimpleNamespace(dataset_code=dataset_code)

    class _FxIdentities:
        async def resolve(self, *_args: object, **_kwargs: object) -> object:
            return SimpleNamespace(
                asset_type="fx",
                canonical_id="instrument:fx:CN-OTC:USDCNH",
                metadata_version="fx-v1",
                valid_to=None,
                venue="CN-OTC",
            )

    payload: dict[str, object] = {
        "identity": {"canonical_id": "instrument:fx:CN-OTC:USDCNH"},
        "dataset_code": "market.bars",
        "data_kind": "bars",
        "frequency": "1d",
        "start": "2026-09-08T09:30:00+08:00",
        "end": "2026-09-09T09:30:00+08:00",
        "required_fields": ["open", "high", "low", "close"],
        "adjustment": "unadjusted",
        "price_basis": "close",
        "currency": None,
        "unit": None,
        "source_policy_id": "market-default-v1",
        "family_id": "fx.range",
        "family_contract_version": "market-data-family-v1",
        "mode": "local_first",
    }
    resolver = MarketDataQueryResolver(
        catalog=_Catalog(),  # type: ignore[arg-type]
        identities=_FxIdentities(),  # type: ignore[arg-type]
    )

    accepted = PublicMarketDataQueryRequest.model_validate_json(json.dumps(payload))
    result = await resolver.resolve(accepted)

    assert {"adjustment", "price_basis", "currency", "unit"} <= accepted.model_fields_set
    assert result.query.family_id == "fx.range"
    assert result.query.currency is None
    assert result.query.unit is None

    for axis_name in ("adjustment", "price_basis", "currency", "unit"):
        omitted = dict(payload)
        omitted.pop(axis_name)
        request = PublicMarketDataQueryRequest.model_validate_json(json.dumps(omitted))
        with pytest.raises(MarketDataQueryResolutionError) as rejected:
            await resolver.resolve(request)
        assert rejected.value.code == "DATA_FAMILY_QUERY_CONTRACT_MISMATCH"

    for axis_name, value in (
        ("adjustment", "qfq"),
        ("price_basis", "settle"),
        ("currency", "USD"),
        ("unit", "contract"),
    ):
        request = PublicMarketDataQueryRequest.model_validate_json(
            json.dumps(payload | {axis_name: value})
        )
        with pytest.raises(MarketDataQueryResolutionError) as rejected:
            await resolver.resolve(request)
        assert rejected.value.code == "DATA_FAMILY_QUERY_CONTRACT_MISMATCH"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {
            "dataset_code": "market.option_chain",
            "data_kind": "option_chain",
            "frequency": "snapshot",
            "required_fields": ["last"],
        },
        {
            "dataset_code": "market.position_report",
            "data_kind": "position_report",
            "frequency": "1w",
            "required_fields": ["net_position"],
        },
        {
            "identity": {"canonical_id": "instrument:crypto:US-BINANCE:BTCUSDT"},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "required_fields": ["close"],
        },
    ],
)
async def test_query_resolver_rejects_every_unbound_public_product_before_catalog_or_identity(
    changes: dict[str, object],
) -> None:
    """Raw public requests cannot bypass a family contract, including generic bars."""

    class _UnexpectedCatalog:
        async def resolve_primary(self, _dataset_code: str) -> object:
            raise AssertionError("catalog must not be read for an unbound non-bars query")

    class _UnexpectedIdentities:
        async def resolve(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("identity must not be read for an unbound non-bars query")

    resolver = MarketDataQueryResolver(
        catalog=_UnexpectedCatalog(),  # type: ignore[arg-type]
        identities=_UnexpectedIdentities(),  # type: ignore[arg-type]
    )
    with pytest.raises(MarketDataQueryResolutionError) as rejected:
        await resolver.resolve(
            _request(
                **changes,
                family_id=None,
                family_contract_version=None,
            )
        )

    assert rejected.value.code == "DATA_FAMILY_BINDING_REQUIRED"


@pytest.mark.asyncio
async def test_query_resolver_rejects_a_bound_unconfigured_multi_record_family() -> None:
    """A family key is not sufficient until its record-key and coverage model are ready."""

    class _UnexpectedCatalog:
        async def resolve_primary(self, _dataset_code: str) -> object:
            raise AssertionError("catalog must not be read for an unconfigured family")

    class _UnexpectedIdentities:
        async def resolve(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("identity must not be read for an unconfigured family")

    resolver = MarketDataQueryResolver(
        catalog=_UnexpectedCatalog(),  # type: ignore[arg-type]
        identities=_UnexpectedIdentities(),  # type: ignore[arg-type]
    )
    request = _request(
        identity={"canonical_id": "instrument:option:CN-CFFEX:IO2609-C-3000"},
        dataset_code="market.option_chain",
        data_kind="option_chain",
        frequency="snapshot",
        required_fields=["last"],
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
    )

    with pytest.raises(MarketDataQueryResolutionError) as rejected:
        await resolver.resolve(request)

    assert rejected.value.code == "DATA_FAMILY_UNCONFIGURED"


@pytest.mark.asyncio
async def test_query_resolver_fails_closed_without_a_declared_dataset_or_primary_storage() -> None:
    """The v1 path never guesses a storage table from an asset type or provider."""
    async with async_session_maker() as db:
        resolver = MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        )
        with pytest.raises(MarketDataQueryResolutionError) as missing_dataset:
            await resolver.resolve(_request(dataset_code=None))
        with pytest.raises(MarketDataQueryResolutionError) as missing_policy:
            await resolver.resolve(_request(source_policy_id=None))

        db.add(_instrument(_identity()))
        await db.commit()
        with pytest.raises(MarketDataQueryResolutionError) as missing_storage:
            await resolver.resolve(_request())

    assert missing_dataset.value.code == "DATASET_REQUIRED"
    assert missing_policy.value.code == "SOURCE_POLICY_REQUIRED"
    assert missing_storage.value.code == "DATASET_UNAVAILABLE"


@pytest.mark.asyncio
async def test_query_resolver_rejects_an_identity_version_that_changes_inside_the_window() -> None:
    """One response cannot silently span two master-data identity versions."""
    identity = _identity()
    request = _request(
        start="2026-09-08T09:30:00+08:00",
        end="2026-09-10T09:30:00+08:00",
    )
    version_end = datetime(2026, 9, 9, 0, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        await _add_catalog(db)
        await _add_published_instrument(db, identity, valid_to=version_end)
        resolver = MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        )

        with pytest.raises(MarketDataQueryResolutionError) as crossing:
            await resolver.resolve(request)

    assert crossing.value.code == "IDENTITY_VERSION_WINDOW_CROSSES"
