"""Contracts for the strict legacy-page-to-v2 market-data bridge."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.base import (
    get_legacy_market_data_query_contract_resolver,
    get_market_instrument_service,
)
from app.db.database import async_session_maker
from app.main import app
from app.models.asset_research import AssetInstrument
from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget
from app.models.market_data_platform import MdInstrumentLookupKey
from app.services.market_data.identity_projection import MarketDataIdentityProjectionWriter
from app.services.market_data.legacy_contract import (
    LegacyMarketDataQueryContractResolver,
    _semantics_for,
)

UTC = timezone.utc


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """Provide one request-like session over the shared isolated test database."""
    async with async_session_maker() as session:
        yield session


def _identity(*, canonical_id: str, symbol: str, venue: str) -> dict[str, object]:
    return {
        "asset_type": "stock",
        "identity_level": "ASSET",
        "canonical_id": canonical_id,
        "display_symbol": symbol,
        "name": "测试股票",
        "venue": venue,
        "currency": "CNY",
        "timezone": "Asia/Shanghai",
        "identifier_type": "EXCHANGE_SYMBOL",
        "identifier_value": symbol,
        "product_type": "EQUITY",
        "metadata_version": "market-v1",
        "details": {"kind": "STOCK", "exchange_symbol": f"{symbol}.SH"},
    }


async def _add_catalog(session: AsyncSession) -> None:
    dataset = DgDataset(
        id="dataset-market-bars",
        dataset_code="market.bars",
        display_name="统一市场 K 线",
        domain="market",
        canonical_schema={"asset_types": ["stock", "futures", "bond", "fund", "option", "fx", "crypto"]},
        primary_key=["canonical_id", "event_at"],
        is_active=True,
    )
    target = DgStorageTarget(
        id="target-canonical-market",
        storage_id="canonical-market-data",
        engine="sqlite",
        url_env="DATABASE_URL",
        database_name="backtrader",
        role="primary",
        is_active=True,
    )
    session.add_all(
        [
            dataset,
            target,
            DgDatasetStorage(
                id="binding-market-bars",
                dataset_id=dataset.id,
                storage_target_id=target.id,
                physical_table="md_observation_revisions",
                write_mode="canonical_append_only",
                is_primary=True,
            ),
        ]
    )
    await session.flush()


async def _add_identity(
    session: AsyncSession,
    *,
    canonical_id: str,
    symbol: str,
    market: str,
) -> None:
    now = datetime(2026, 9, 8, tzinfo=UTC)
    instrument = AssetInstrument(
        id=f"instrument-{canonical_id.rsplit(':', 1)[-1]}-{market}",
        canonical_id=canonical_id,
        asset_type="stock",
        identity_level="ASSET",
        venue=market,
        currency="CNY",
        product_type="EQUITY",
        identity_json=_identity(canonical_id=canonical_id, symbol=symbol, venue=market),
        metadata_version="market-v1",
        lifecycle_status="ACTIVE",
        valid_from=now,
        created_at=now,
    )
    session.add(instrument)
    await session.flush()
    session.add(
        MdInstrumentLookupKey(
            asset_type="stock",
            market=market,
            symbol=symbol,
            instrument_id=instrument.id,
            canonical_id=canonical_id,
            metadata_version="market-v1",
            is_active=True,
            valid_from=now,
        )
    )
    await session.flush()
    projections = MarketDataIdentityProjectionWriter(session)
    await projections.project(instrument)
    await session.commit()
    await projections.publish_staged()


@pytest.mark.asyncio
async def test_legacy_bridge_publishes_only_a_catalog_backed_exact_canonical_contract(
    db_session: AsyncSession,
) -> None:
    await _add_catalog(db_session)
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SSE:600000",
        symbol="600000",
        market="CN-SSE",
    )

    contract = await LegacyMarketDataQueryContractResolver(db_session).resolve(
        asset_type="stock",
        symbol="600000",
        period="weekly",
    )

    assert contract == {
        "version": "market-data-v2",
        "request": {
            "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1w",
            "required_fields": ["close"],
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "mode": "local_first",
        },
    }


@pytest.mark.asyncio
async def test_legacy_bridge_fails_closed_when_the_same_symbol_has_two_active_venues(
    db_session: AsyncSession,
) -> None:
    await _add_catalog(db_session)
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SSE:600000",
        symbol="600000",
        market="CN-SSE",
    )
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SZSE:600000",
        symbol="600000",
        market="CN-SZSE",
    )

    contract = await LegacyMarketDataQueryContractResolver(db_session).resolve(
        asset_type="stock",
        symbol="600000",
        period="daily",
    )

    assert contract is None


@pytest.mark.asyncio
async def test_legacy_bridge_never_publishes_a_contract_without_a_catalog_binding(
    db_session: AsyncSession,
) -> None:
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SSE:600000",
        symbol="600000",
        market="CN-SSE",
    )

    contract = await LegacyMarketDataQueryContractResolver(db_session).resolve(
        asset_type="stock",
        symbol="600000",
        period="daily",
    )

    assert contract is None


@pytest.mark.asyncio
async def test_legacy_bridge_only_publishes_periods_with_a_reviewed_default_route(
    db_session: AsyncSession,
) -> None:
    """An unsupported cadence must retain the old page API instead of stalling in v2."""
    resolver = LegacyMarketDataQueryContractResolver(
        db_session,
        openbb_allowed_markets=frozenset({"US-NYSE"}),
    )

    assert resolver._has_reviewed_route(
        asset_type="stock",
        venue="CN-SSE",
        frequency="1w",
        semantics=_semantics_for("stock", "CN-SSE"),
    )
    assert not resolver._has_reviewed_route(
        asset_type="futures",
        venue="CFFEX",
        frequency="1w",
        semantics=_semantics_for("futures", "CFFEX"),
    )
    assert resolver._has_reviewed_route(
        asset_type="fx",
        venue="CN-OTC",
        frequency="1d",
        semantics=_semantics_for("fx", "CN-OTC"),
    )
    assert resolver._has_reviewed_route(
        asset_type="crypto",
        venue="US-NYSE",
        frequency="1d",
        semantics=_semantics_for("crypto", "US-NYSE"),
    )
    assert not resolver._has_reviewed_route(
        asset_type="option",
        venue="CN-SSE",
        frequency="1d",
        semantics=_semantics_for("option", "CN-SSE"),
    )


class _ContractResolver:
    """Small HTTP-boundary double that proves the contract probe is provider-free."""

    def __init__(self, contract: dict[str, object] | None) -> None:
        self.contract = contract
        self.calls: list[dict[str, str]] = []

    async def resolve(self, *, asset_type: str, symbol: str, period: str) -> dict[str, object] | None:
        self.calls.append(
            {
                "asset_type": asset_type,
                "symbol": symbol,
                "period": period,
            }
        )
        return self.contract


class _SuccessfulLegacyLookupService:
    """Minimal legacy payload source for testing the optional bridge boundary."""

    async def lookup(self, **_kwargs: object) -> dict[str, object]:
        return {"symbol": "600000", "provider": "legacy-test"}


class _FailingContractResolver:
    """Simulate an unavailable v2 metadata database after a legacy success."""

    async def resolve(self, **_kwargs: object) -> None:
        raise SQLAlchemyError("metadata database unavailable")


@pytest.mark.asyncio
async def test_contract_probe_returns_catalog_contract_without_legacy_lookup(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The first page probe only asks the strict resolver and never invokes a provider."""
    import app.api.data.base as data_base

    expected = {
        "version": "market-data-v2",
        "request": {
            "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "required_fields": ["close"],
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "mode": "local_first",
        },
    }
    resolver = _ContractResolver(expected)
    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = lambda: resolver
    try:
        response = await client.get(
            "/api/v1/data/market-instruments/query-contract",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 200
    assert response.json() == expected
    assert resolver.calls == [{"asset_type": "stock", "symbol": "600000", "period": "daily"}]


@pytest.mark.asyncio
async def test_contract_probe_fails_closed_when_v2_is_disabled_or_unavailable(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A rollout gate or absent authoritative identity cannot silently create a contract."""
    import app.api.data.base as data_base

    resolver = _ContractResolver(None)
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = lambda: resolver
    try:
        monkeypatch.setattr(
            data_base,
            "get_settings",
            lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=False),
        )
        disabled = await client.get(
            "/api/v1/data/market-instruments/query-contract",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
        monkeypatch.setattr(
            data_base,
            "get_settings",
            lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
        )
        unavailable = await client.get(
            "/api/v1/data/market-instruments/query-contract",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert disabled.status_code == 503
    assert disabled.json()["details"] == {"code": "MARKET_DATA_QUERY_V2_DISABLED"}
    assert resolver.calls == [{"asset_type": "stock", "symbol": "600000", "period": "daily"}]
    assert unavailable.status_code == 404
    assert unavailable.json()["details"] == {"code": "MARKET_DATA_QUERY_CONTRACT_UNAVAILABLE"}


@pytest.mark.asyncio
async def test_legacy_lookup_survives_an_optional_v2_contract_database_failure(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A v2 compatibility probe cannot invalidate already returned legacy market data."""
    import app.api.data.base as data_base

    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = _FailingContractResolver
    try:
        response = await client.get(
            "/api/v1/data/market-instruments/lookup",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_market_instrument_service, None)
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 200
    assert response.json() == {"symbol": "600000", "provider": "legacy-test"}


@pytest.mark.asyncio
async def test_contract_probe_maps_metadata_database_failure_to_typed_unavailable(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A probe failure remains an explicit progressive-rollout compatibility state."""
    import app.api.data.base as data_base

    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = _FailingContractResolver
    try:
        response = await client.get(
            "/api/v1/data/market-instruments/query-contract",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 503
    assert response.json()["details"] == {"code": "MARKET_DATA_QUERY_CONTRACT_UNAVAILABLE"}
