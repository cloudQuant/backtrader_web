"""Contracts for the strict legacy-page-to-v2 market-data bridge."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.base import (
    get_legacy_market_data_query_contract_resolver,
    get_market_instrument_service,
)
from app.api.data.deps import get_market_data_access_authorizer
from app.db.database import async_session_maker
from app.main import app
from app.models.asset_research import AssetInstrument
from app.models.data_governance import DgDataset, DgDatasetStorage, DgStorageTarget
from app.models.market_data_platform import MdInstrumentLookupKey
from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity
from app.services.market_data.access import MarketDataAuthorizationError
from app.services.market_data.dataset_contracts import DatasetContractRegistryError
from app.services.market_data.identity_projection import MarketDataIdentityProjectionWriter
from app.services.market_data.legacy_contract import (
    LegacyMarketDataQueryContractResolver,
    _semantics_for,
)

UTC = timezone.utc


class _PermittedMarketDataAccess:
    """Provide the explicit data-read gate for query-contract bridge tests."""

    async def principal_for_user(self, _user: object) -> object:
        return object()

    @staticmethod
    def require_read_data(*, principal: object) -> None:
        assert principal is not None


class _DeniedMarketDataAccess:
    """Model an authenticated legacy caller without the v2 data entitlement."""

    async def principal_for_user(self, _user: object) -> object:
        return object()

    @staticmethod
    def require_read_data(*, principal: object) -> None:
        assert principal is not None
        raise MarketDataAuthorizationError("MARKET_DATA_READ_ENTITLEMENT_DENIED")


class _UnavailableMarketDataAccess:
    """Model a metadata authorization-store outage on the optional bridge."""

    async def principal_for_user(self, _user: object) -> object:
        raise SQLAlchemyError("authorization database unavailable")


@pytest.fixture
def permitted_market_data_access() -> None:
    """Keep contract semantics tests independent of RBAC provisioning fixtures."""
    app.dependency_overrides[get_market_data_access_authorizer] = _PermittedMarketDataAccess
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)


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
        canonical_schema={
            "asset_types": ["stock", "futures", "bond", "fund", "option", "fx", "crypto"]
        },
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
async def test_legacy_bridge_derives_a_ready_realtime_family_for_an_unbound_stock_request(
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
            "family_id": "stock.realtime",
            "family_contract_version": "market-data-family-v1",
        },
    }


@pytest.mark.asyncio
async def test_legacy_bridge_binds_a_selected_ready_family_to_the_exact_contract(
    db_session: AsyncSession,
) -> None:
    """A bundle-selected family returns its immutable product binding, not a nearby route."""
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
        period="daily",
        family_id="stock.realtime",
    )

    assert contract is not None
    assert contract["request"] == {
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
        "family_id": "stock.realtime",
        "family_contract_version": "market-data-family-v1",
    }


@pytest.mark.asyncio
async def test_legacy_bridge_rejects_an_unconfigured_or_cross_asset_selected_family(
    db_session: AsyncSession,
) -> None:
    """A UI card that has no executable product cannot reach the legacy bridge."""
    resolver = LegacyMarketDataQueryContractResolver(db_session)

    for family_id in ("", "stock.valuation", "futures.realtime", "stock.unknown"):
        with pytest.raises(DatasetContractRegistryError):
            await resolver.resolve(
                asset_type="stock",
                symbol="600000",
                period="daily",
                family_id=family_id,
            )


@pytest.mark.asyncio
async def test_legacy_bridge_does_not_issue_an_openbb_crypto_contract_without_a_ready_family(
    db_session: AsyncSession,
) -> None:
    """An allow-listed OpenBB venue cannot bypass the missing crypto product contract."""
    resolver = LegacyMarketDataQueryContractResolver(
        db_session,
        openbb_allowed_markets=frozenset({"US-NYSE"}),
    )

    # This route predicate is deliberately true: the refusal must come from
    # the server-owned product registry, before it can become a generic bars
    # contract or depend on a catalog/identity record.
    assert resolver._has_reviewed_route(
        asset_type="crypto",
        venue="US-NYSE",
        frequency="1d",
        semantics=_semantics_for("crypto", "US-NYSE"),
    )
    with pytest.raises(DatasetContractRegistryError) as exc_info:
        await resolver.resolve(
            asset_type="crypto",
            symbol="BTC-USD",
            period="daily",
        )

    assert exc_info.value.code == "DATA_FAMILY_UNCONFIGURED"


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
async def test_legacy_lookup_rechecks_raw_symbols_after_a_case_insensitive_database_match() -> None:
    """A MySQL ``*_ci`` match cannot turn ``RB0`` into a contract for ``rb0``."""

    class _Rows:
        @staticmethod
        def all() -> list[tuple[str, str, str]]:
            # Simulate a pre-migration case-insensitive SQL predicate returning
            # a differently cased projected key.
            return [("instrument:stock:CN-SSE:RB0", "stock", "RB0")]

    class _CaseInsensitiveLookupSession:
        @staticmethod
        async def execute(_statement: object) -> _Rows:
            return _Rows()

    resolver = LegacyMarketDataQueryContractResolver(_CaseInsensitiveLookupSession())  # type: ignore[arg-type]

    assert (
        await resolver._unique_active_canonical_id(asset_type="stock", symbol="rb0")
    ) is None
    assert (
        await resolver._unique_active_canonical_id(asset_type="stock", symbol="RB0")
    ) == "instrument:stock:CN-SSE:RB0"


@pytest.mark.asyncio
async def test_legacy_bridge_rechecks_the_frozen_symbol_after_case_insensitive_lookup(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frozen canonical projection is a second fail-closed exact-symbol proof."""
    canonical_id = "instrument:stock:CN-SSE:RB0"
    await _add_catalog(db_session)
    await _add_identity(
        db_session,
        canonical_id=canonical_id,
        symbol="RB0",
        market="CN-SSE",
    )
    resolver = LegacyMarketDataQueryContractResolver(db_session)

    async def _case_insensitive_lookup(**_kwargs: str) -> str:
        return canonical_id

    monkeypatch.setattr(resolver, "_unique_active_canonical_id", _case_insensitive_lookup)

    assert (
        await resolver.resolve(asset_type="stock", symbol="rb0", period="daily")
    ) is None


@pytest.mark.asyncio
async def test_legacy_bridge_resolves_case_distinct_exact_symbols_independently(
    db_session: AsyncSession,
) -> None:
    """A bytewise identity contract permits separately registered case-distinct symbols."""
    await _add_catalog(db_session)
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SSE:RB0",
        symbol="RB0",
        market="CN-SSE",
    )
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SSE:rb0",
        symbol="rb0",
        market="CN-SSE",
    )
    resolver = LegacyMarketDataQueryContractResolver(db_session)

    upper = await resolver.resolve(asset_type="stock", symbol="RB0", period="daily")
    lower = await resolver.resolve(asset_type="stock", symbol="rb0", period="daily")

    assert upper is not None
    assert lower is not None
    assert upper["request"]["identity"] == {"canonical_id": "instrument:stock:CN-SSE:RB0"}
    assert lower["request"]["identity"] == {"canonical_id": "instrument:stock:CN-SSE:rb0"}


@pytest.mark.asyncio
async def test_legacy_bridge_rejects_a_corrupt_cross_asset_lookup_projection(
    db_session: AsyncSession,
) -> None:
    """A stock lookup must not mint a stock family contract for a futures identity."""
    await _add_catalog(db_session)
    await _add_identity(
        db_session,
        canonical_id="instrument:stock:CN-SSE:600000",
        symbol="600000",
        market="CN-SSE",
    )

    now = datetime(2026, 9, 8, tzinfo=UTC)
    future_identity = InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="instrument:futures:CFFEX:IF2609",
        display_symbol="IF2609",
        name="沪深300股指期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="market-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )
    future = AssetInstrument(
        id="instrument-futures-if2609",
        canonical_id=future_identity.canonical_id,
        asset_type=future_identity.asset_type,
        identity_level=future_identity.identity_level,
        venue=future_identity.venue,
        currency=future_identity.currency,
        product_type=future_identity.product_type,
        identity_json=future_identity.model_dump(mode="json"),
        metadata_version=future_identity.metadata_version,
        lifecycle_status="ACTIVE",
        valid_from=now,
        created_at=now,
    )
    db_session.add(future)
    await db_session.flush()
    projections = MarketDataIdentityProjectionWriter(db_session)
    await projections.project(future)
    await db_session.commit()
    await projections.publish_staged()

    stock_lookup = await db_session.scalar(
        select(MdInstrumentLookupKey).where(
            MdInstrumentLookupKey.asset_type == "stock",
            MdInstrumentLookupKey.market == "CN-SSE",
            MdInstrumentLookupKey.symbol == "600000",
            MdInstrumentLookupKey.is_active.is_(True),
        )
    )
    assert stock_lookup is not None
    stock_lookup.is_active = False
    db_session.add(
        MdInstrumentLookupKey(
            asset_type="stock",
            market="CN-SSE",
            symbol="600000",
            instrument_id=future.id,
            canonical_id=future.canonical_id,
            metadata_version=future.metadata_version,
            is_active=True,
            valid_from=now,
        )
    )
    await db_session.commit()

    contract = await LegacyMarketDataQueryContractResolver(db_session).resolve(
        asset_type="stock",
        symbol="600000",
        period="daily",
        family_id="stock.realtime",
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

    async def resolve(
        self,
        *,
        asset_type: str,
        symbol: str,
        period: str,
        family_id: str | None = None,
    ) -> dict[str, object] | None:
        call = {"asset_type": asset_type, "symbol": symbol, "period": period}
        if family_id is not None:
            call["family_id"] = family_id
        self.calls.append(call)
        return self.contract


class _SuccessfulLegacyLookupService:
    """Minimal legacy payload source for testing the optional bridge boundary."""

    async def lookup(self, **_kwargs: object) -> dict[str, object]:
        return {"symbol": "600000", "provider": "legacy-test"}


class _FailingContractResolver:
    """Simulate an unavailable v2 metadata database after a legacy success."""

    async def resolve(self, **_kwargs: object) -> None:
        raise SQLAlchemyError("metadata database unavailable")


class _UnconfiguredFamilyContractResolver:
    """Model an auto-derived family whose product contract remains unavailable."""

    async def resolve(self, **_kwargs: object) -> None:
        raise DatasetContractRegistryError("DATA_FAMILY_UNCONFIGURED")


@pytest.mark.asyncio
async def test_contract_probe_returns_catalog_contract_without_legacy_lookup(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
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
            "family_id": "stock.realtime",
            "family_contract_version": "market-data-family-v1",
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
async def test_contract_probe_forwards_the_explicit_bundle_family_to_the_server_resolver(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """The frontend-selected product reaches the exact-contract issuer unchanged."""
    import app.api.data.base as data_base

    expected = {
        "version": "market-data-v2",
        "request": {
            "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "required_fields": ["close"],
            "source_policy_id": "market-default-v1",
            "mode": "local_first",
            "family_id": "stock.realtime",
            "family_contract_version": "market-data-family-v1",
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
            params={
                "asset_type": "stock",
                "symbol": "600000",
                "period": "daily",
                "family_id": "stock.realtime",
            },
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 200
    assert response.json() == expected
    assert resolver.calls == [
        {
            "asset_type": "stock",
            "symbol": "600000",
            "period": "daily",
            "family_id": "stock.realtime",
        }
    ]


@pytest.mark.asyncio
async def test_contract_probe_fails_closed_when_v2_is_disabled_or_unavailable(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
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
    permitted_market_data_access,
) -> None:
    """A v2 compatibility probe cannot invalidate already returned legacy market data."""
    import app.api.data.base as data_base

    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = (
        _FailingContractResolver
    )
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
async def test_legacy_lookup_includes_v2_contract_only_after_data_read_is_granted(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """The optional legacy bridge remains functional for an entitled caller."""
    import app.api.data.base as data_base

    expected = {
        "version": "market-data-v2",
        "request": {
            "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "required_fields": ["close"],
            "source_policy_id": "market-default-v1",
            "mode": "local_first",
            "family_id": "stock.realtime",
            "family_contract_version": "market-data-family-v1",
        },
    }
    resolver = _ContractResolver(expected)
    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = lambda: resolver
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
    assert response.json() == {
        "symbol": "600000",
        "provider": "legacy-test",
        "query_contract": expected,
        "query_contract_symbol": "600000",
        "query_contract_canonical_id": "instrument:stock:CN-SSE:600000",
    }
    assert resolver.calls == [{"asset_type": "stock", "symbol": "600000", "period": "daily"}]


@pytest.mark.asyncio
async def test_legacy_lookup_omits_a_malformed_optional_v2_contract(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """A mixed metadata response cannot turn a successful legacy lookup into a 500."""
    import app.api.data.base as data_base

    resolver = _ContractResolver({"version": "market-data-v2", "request": {"identity": {}}})
    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = lambda: resolver
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
    assert resolver.calls == [{"asset_type": "stock", "symbol": "600000", "period": "daily"}]


@pytest.mark.asyncio
async def test_legacy_lookup_omits_an_unconfigured_auto_derived_family_contract(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """An optional v2 refusal cannot turn a completed legacy lookup into a client error."""
    import app.api.data.base as data_base

    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = (
        _UnconfiguredFamilyContractResolver
    )
    try:
        response = await client.get(
            "/api/v1/data/market-instruments/lookup",
            params={"asset_type": "crypto", "symbol": "BTC-USD", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_market_instrument_service, None)
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 200
    assert response.json() == {"symbol": "600000", "provider": "legacy-test"}


@pytest.mark.asyncio
async def test_legacy_lookup_omits_v2_contract_for_a_caller_without_data_read(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """Legacy compatibility data remains available, but cannot disclose v2 metadata."""
    import app.api.data.base as data_base

    resolver = _ContractResolver({"unexpected": True})
    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_market_data_access_authorizer] = _DeniedMarketDataAccess
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = lambda: resolver
    try:
        response = await client.get(
            "/api/v1/data/market-instruments/lookup",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_market_instrument_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 200
    assert response.json() == {"symbol": "600000", "provider": "legacy-test"}
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_legacy_lookup_survives_an_optional_v2_authorization_database_failure(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """An unavailable optional entitlement lookup cannot turn legacy data into a 500."""
    import app.api.data.base as data_base

    resolver = _ContractResolver({"unexpected": True})
    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_instrument_service] = _SuccessfulLegacyLookupService
    app.dependency_overrides[get_market_data_access_authorizer] = _UnavailableMarketDataAccess
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = lambda: resolver
    try:
        response = await client.get(
            "/api/v1/data/market-instruments/lookup",
            params={"asset_type": "stock", "symbol": "600000", "period": "daily"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_market_instrument_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)
        app.dependency_overrides.pop(get_legacy_market_data_query_contract_resolver, None)

    assert response.status_code == 200
    assert response.json() == {"symbol": "600000", "provider": "legacy-test"}
    assert resolver.calls == []


@pytest.mark.asyncio
async def test_contract_probe_maps_metadata_database_failure_to_typed_unavailable(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """A probe failure remains an explicit progressive-rollout compatibility state."""
    import app.api.data.base as data_base

    monkeypatch.setattr(
        data_base,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_legacy_market_data_query_contract_resolver] = (
        _FailingContractResolver
    )
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


@pytest.mark.asyncio
async def test_contract_probe_requires_data_read_before_catalog_or_identity_resolution(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The bridge cannot expose catalog/master-data metadata to an unentitled user."""
    import app.api.data.base as data_base

    resolver = _ContractResolver({"unexpected": True})
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

    assert response.status_code == 403
    assert response.json()["details"] == {"code": "MARKET_DATA_READ_ENTITLEMENT_DENIED"}
    assert resolver.calls == []
