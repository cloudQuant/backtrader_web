"""Unit contracts for explicit route capability and policy purpose controls."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.api.data.queries import _default_source_policy_registry
from app.schemas.market_data_platform import MarketDataQueryBundleRequest
from app.services.market_data import openbb_runtime
from app.services.market_data.akshare_provider import AKSHARE_ROUTE_REGISTRY
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    FAMILY_CONTRACT_VERSION,
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
)
from app.services.market_data.openbb_runtime import (
    OPENBB_RUNTIME_PERMIT_MATRIX,
    OpenBBRuntimeRoutePermit,
    approved_openbb_runtime_route_permits,
)
from app.services.market_data.source_policy import (
    MarketDataLocalReadSource,
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)


class _Provider:
    async def fetch(self, _request):
        raise AssertionError("route selection tests must not invoke an adapter")


def _ready_public_default_family_pairs() -> set[tuple[str, str]]:
    """Read the executable public pairs from the issued registry bundles."""
    pairs: set[tuple[str, str]] = set()
    for asset_type in ("stock", "futures", "bond", "fund", "option", "fx", "crypto"):
        bundle = DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
            MarketDataQueryBundleRequest(asset_type=asset_type)
        )
        for family in bundle.families:
            if family.status == "ready" and family.source_policy_id == "market-default-v1":
                pairs.add((family.family_id, family.family_contract_version))
    return pairs


def _context(**query_changes):
    query = {
        "data_kind": "bars",
        "frequency": "1d",
        "adjustment": "qfq",
        "price_basis": "close",
        "currency": "CNY",
        "unit": "share",
    }
    query.update(query_changes)
    return SimpleNamespace(
        identity=SimpleNamespace(asset_type="stock", venue="CN-SSE"),
        query=SimpleNamespace(**query),
    )


def _route() -> MarketDataProviderRoute:
    return MarketDataProviderRoute(
        route_id="akshare-stock-v1",
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=_Provider(),
    )


def _local_source(**changes: object) -> MarketDataLocalReadSource:
    values: dict[str, object] = {
        "local_source_id": "legacy-stock-zh-a-hist-local-read-v1",
        "source_registry_id": "legacy-stock-zh-a-hist-warehouse",
        "asset_types": frozenset({"stock"}),
        "data_kinds": frozenset({"bars"}),
        "frequencies": frozenset({"1d"}),
        "markets": frozenset({"CN-SSE"}),
        "adjustments": frozenset({"qfq"}),
        "price_bases": frozenset({"close"}),
        "currencies": frozenset({"CNY"}),
        "units": frozenset({"share"}),
    }
    values.update(changes)
    return MarketDataLocalReadSource(**values)  # type: ignore[arg-type]


def test_local_read_source_is_not_a_provider_route() -> None:
    """A local source may authorize stored facts but carries no I/O dispatch fields."""
    local_source = _local_source()

    assert not isinstance(local_source, MarketDataProviderRoute)
    assert all(
        not hasattr(local_source, field_name)
        for field_name in ("adapter", "request_provider", "route_id")
    )
    with pytest.raises(TypeError, match="routes must be MarketDataProviderRoute"):
        MarketDataSourcePolicy(
            policy_id="wrong-route-type-v1",
            allowed_purposes=frozenset({"display"}),
            routes=(local_source,),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="local_sources must be MarketDataLocalReadSource"):
        MarketDataSourcePolicy(
            policy_id="wrong-local-source-type-v1",
            allowed_purposes=frozenset({"display"}),
            routes=(),
            local_sources=(_route(),),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("query_changes", "identity_changes"),
    (
        ({"data_kind": "snapshot"}, {}),
        ({"frequency": "1w"}, {}),
        ({"adjustment": "hfq"}, {}),
        ({"price_basis": "settlement"}, {}),
        ({"currency": "USD"}, {}),
        ({"unit": "contract"}, {}),
        ({}, {"asset_type": "fund"}),
        ({}, {"venue": "CN-SZSE"}),
    ),
)
def test_local_read_source_matches_every_declared_axis_exactly(
    query_changes: dict[str, str],
    identity_changes: dict[str, str],
) -> None:
    """A nearby local series cannot broaden into a source-policy authorization."""
    local_source = _local_source()
    context = _context(**query_changes)
    for field_name, value in identity_changes.items():
        setattr(context.identity, field_name, value)

    assert local_source.supports(_context())
    assert not local_source.supports(context)


def test_policy_keeps_local_read_sources_out_of_provider_route_selection() -> None:
    """A local-only policy remains readable without becoming an online route list."""
    local_source = _local_source()
    policy = MarketDataSourcePolicy(
        policy_id="local-only-stock-history-v1",
        allowed_purposes=frozenset({"display"}),
        routes=(),
        local_sources=(local_source,),
    )

    assert policy.routes_for(_context()) == ()
    assert policy.local_sources_for(_context()) == (local_source,)


def test_policy_defaults_local_read_sources_to_empty_and_requires_a_capability() -> None:
    """Retained route policies stay compatible while a completely empty policy is rejected."""
    routed_policy = MarketDataSourcePolicy(
        policy_id="route-only-v1",
        allowed_purposes=frozenset({"display"}),
        routes=(_route(),),
    )

    assert routed_policy.local_sources == ()
    with pytest.raises(ValueError, match="at least one provider route or local read source"):
        MarketDataSourcePolicy(
            policy_id="empty-v1",
            allowed_purposes=frozenset({"display"}),
            routes=(),
        )


def test_policy_copy_preserves_local_read_sources() -> None:
    """A policy rebuilt by dataclass replacement retains its reviewed local sources."""
    local_source = _local_source()
    policy = MarketDataSourcePolicy(
        policy_id="local-copy-v1",
        allowed_purposes=frozenset({"display"}),
        routes=(),
        local_sources=(local_source,),
    )

    rebuilt = replace(policy, allowed_purposes=frozenset({"display", "research"}))

    assert rebuilt.routes == ()
    assert rebuilt.local_sources == (local_source,)
    assert rebuilt.local_sources[0].local_source_id == "legacy-stock-zh-a-hist-local-read-v1"
    assert rebuilt.local_sources_for(_context()) == (local_source,)


def test_policy_requires_unique_local_source_ids_without_conflating_registry_scope() -> None:
    """One registry may have multiple scopes, but every policy selection key is unique."""
    primary = _local_source(local_source_id="legacy-stock-qfq-v1")
    other_scope = _local_source(
        local_source_id="legacy-stock-hfq-v1",
        adjustments=frozenset({"hfq"}),
    )

    policy = MarketDataSourcePolicy(
        policy_id="separate-local-scopes-v1",
        allowed_purposes=frozenset({"display"}),
        routes=(),
        local_sources=(primary, other_scope),
    )

    assert [source.local_source_id for source in policy.local_sources_for(_context())] == [
        "legacy-stock-qfq-v1"
    ]
    with pytest.raises(ValueError, match="local_source_id values must be unique"):
        MarketDataSourcePolicy(
            policy_id="duplicate-local-source-id-v1",
            allowed_purposes=frozenset({"display"}),
            routes=(),
            local_sources=(primary, primary),
        )


@pytest.mark.parametrize(
    ("family_id", "family_contract_version"),
    (
        ("stock.realtime", None),
        (None, FAMILY_CONTRACT_VERSION),
    ),
)
def test_route_rejects_a_partial_family_contract_pair(
    family_id: str | None,
    family_contract_version: str | None,
) -> None:
    """A route cannot pin a family while treating its version as a wildcard."""
    with pytest.raises(ValueError, match="family_id and family_contract_version"):
        replace(
            _route(),
            family_id=family_id,
            family_contract_version=family_contract_version,
        )


def test_route_requires_every_declared_market_and_semantic_axis() -> None:
    """A route cannot broaden from an adjusted CNY share series to a nearby semantic series."""
    route = _route()

    assert route.supports(_context())
    assert not route.supports(_context(adjustment="hfq"))
    assert not route.supports(_context(currency="USD"))
    assert not route.supports(_context(unit="contract"))
    assert not route.supports(_context(frequency="1w"))


def test_policy_purpose_is_server_owned_and_registry_has_no_default() -> None:
    """Caller-supplied policy IDs and purposes must resolve to an explicit server grant."""
    policy = MarketDataSourcePolicy(
        policy_id="market-public-v1",
        allowed_purposes=frozenset({"display", "research"}),
        routes=(_route(),),
    )
    registry = MarketDataSourcePolicyRegistry((policy,))

    assert registry.resolve("market-public-v1").allows_purpose("research")
    assert not registry.resolve("market-public-v1").allows_purpose("export")


def test_default_policy_routes_an_exact_cffex_option_contract_to_akshare() -> None:
    """The options adapter is reachable only through the reviewed CFFEX semantic route."""
    registry = _default_source_policy_registry("yfinance", ())
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="option", venue="CFFEX"),
        query=SimpleNamespace(
            family_id="option.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
            data_kind="bars",
            frequency="1d",
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="contract",
        ),
    )

    routes = registry.resolve("market-default-v1").routes_for(context)

    assert [route.route_id for route in routes] == ["akshare-cffex-option-primary-v1"]


def test_default_policy_routes_private_kline_to_its_exact_akshare_route() -> None:
    """The full legacy K-line product cannot fall through stock realtime bars."""
    registry = _default_source_policy_registry("yfinance", ())
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="stock", venue="CN-SSE"),
        query=SimpleNamespace(
            family_id="stock.kline_legacy",
            family_contract_version="market-data-kline-v1",
            data_kind="bars",
            frequency="1w",
            adjustment="qfq",
            price_basis="close",
            currency="CNY",
            unit="share",
        ),
    )

    routes = registry.resolve("market-default-v1").routes_for(context)

    assert [route.route_id for route in routes] == ["akshare-stock-kline-legacy-v1"]
    assert routes[0].family_id == "stock.kline_legacy"
    assert routes[0].family_contract_version == "market-data-kline-v1"


def test_default_policy_binds_every_akshare_route_to_its_registry_family_pair() -> None:
    """Every ready public family maps to one exact policy and adapter route pair."""
    policy = _default_source_policy_registry("yfinance", ()).resolve("market-default-v1")
    policy_pairs_by_route_id = {
        route.route_id: (route.family_id, route.family_contract_version)
        for route in policy.routes
        if route.request_provider == "akshare"
    }
    adapter_pairs_by_route_id = {
        route_id: (route.family_id, route.family_contract_version)
        for route in AKSHARE_ROUTE_REGISTRY
        for route_id in route.route_ids
    }
    expected_public_pairs = _ready_public_default_family_pairs()
    expected_all_pairs = expected_public_pairs | {
        (KLINE_LEGACY_FAMILY_ID, KLINE_LEGACY_CONTRACT_VERSION)
    }

    assert policy_pairs_by_route_id == adapter_pairs_by_route_id
    assert all(
        family_id is not None and family_contract_version is not None
        for family_id, family_contract_version in policy_pairs_by_route_id.values()
    )
    assert set(policy_pairs_by_route_id.values()) == expected_all_pairs
    assert {
        pair for pair in policy_pairs_by_route_id.values() if pair[0] != KLINE_LEGACY_FAMILY_ID
    } == (expected_public_pairs)


@pytest.mark.parametrize(
    ("family_id", "route_id"),
    (
        ("fx.realtime", "akshare-fx-primary-v1"),
        ("fx.range", "akshare-fx-range-primary-v1"),
    ),
)
def test_default_policy_keeps_fx_realtime_and_range_on_distinct_exact_routes(
    family_id: str,
    route_id: str,
) -> None:
    """Equal FX transport axes cannot make one public family select the other."""
    policy = _default_source_policy_registry("yfinance", ()).resolve("market-default-v1")
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="fx", venue="CN-OTC"),
        query=SimpleNamespace(
            family_id=family_id,
            family_contract_version=FAMILY_CONTRACT_VERSION,
            data_kind="bars",
            frequency="1d",
            adjustment="unadjusted",
            price_basis="close",
            currency=None,
            unit=None,
        ),
    )

    routes = policy.routes_for(context)

    assert [route.route_id for route in routes] == [route_id]
    assert routes[0].family_id == family_id
    assert routes[0].family_contract_version == FAMILY_CONTRACT_VERSION


def test_default_policy_rejects_fx_range_when_its_strict_semantics_drift() -> None:
    """The range route cannot behave as an unbound FX bars fallback."""
    policy = _default_source_policy_registry("yfinance", ()).resolve("market-default-v1")
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="fx", venue="CN-OTC"),
        query=SimpleNamespace(
            family_id="fx.range",
            family_contract_version=FAMILY_CONTRACT_VERSION,
            data_kind="bars",
            frequency="1d",
            adjustment=None,
            price_basis="close",
            currency=None,
            unit=None,
        ),
    )

    assert policy.routes_for(context) == ()


def test_default_policy_routes_only_the_exact_etf_nav_product_contract() -> None:
    """ETF NAV cannot share an ETF-bar or liquidity route merely by asset type."""
    registry = _default_source_policy_registry("yfinance", ())
    context = SimpleNamespace(
        identity=SimpleNamespace(
            asset_type="fund",
            venue="CN-SZSE",
            identity=SimpleNamespace(
                product_type="ETF",
                details=SimpleNamespace(fund_identity_kind="LISTING"),
            ),
        ),
        query=SimpleNamespace(
            family_id="fund.nav",
            family_contract_version=FAMILY_CONTRACT_VERSION,
            data_kind="reference_series",
            frequency="1d",
            adjustment="source_reported",
            price_basis="nav",
            currency="CNY",
            unit="fund_share",
        ),
    )

    routes = registry.resolve("market-default-v1").routes_for(context)

    assert [route.route_id for route in routes] == ["akshare-fund-nav-primary-v1"]
    assert (
        registry.resolve("market-default-v1").routes_for(
            SimpleNamespace(
                identity=context.identity,
                query=SimpleNamespace(
                    family_id="fund.liquidity",
                    family_contract_version=FAMILY_CONTRACT_VERSION,
                    data_kind="reference_series",
                    frequency="1d",
                    adjustment="source_reported",
                    price_basis="nav",
                    currency="CNY",
                    unit="fund_share",
                ),
            )
        )
        == ()
    )


@pytest.mark.parametrize(
    ("product_type", "fund_identity_kind"),
    (
        ("LOF", "LISTING"),
        ("REIT", "LISTING"),
        ("ETF", "SHARE_CLASS"),
        (None, "LISTING"),
        ("ETF", None),
    ),
)
def test_default_policy_rejects_non_etf_or_non_listing_fund_nav_identities(
    product_type: str | None,
    fund_identity_kind: str | None,
) -> None:
    """ETF NAV policy selection depends on frozen product and listing facts."""
    registry = _default_source_policy_registry("yfinance", ())
    context = SimpleNamespace(
        identity=SimpleNamespace(
            asset_type="fund",
            venue="CN-SZSE",
            identity=SimpleNamespace(
                product_type=product_type,
                details=SimpleNamespace(fund_identity_kind=fund_identity_kind),
            ),
        ),
        query=SimpleNamespace(
            family_id="fund.nav",
            family_contract_version=FAMILY_CONTRACT_VERSION,
            data_kind="reference_series",
            frequency="1d",
            adjustment="source_reported",
            price_basis="nav",
            currency="CNY",
            unit="fund_share",
        ),
    )

    assert registry.resolve("market-default-v1").routes_for(context) == ()


def test_default_policy_only_grants_research_cache_fill_after_server_opt_in() -> None:
    """A browser cannot enable the research-authorized write purpose by itself."""
    _default_source_policy_registry.cache_clear()
    disabled = _default_source_policy_registry("yfinance", ())
    enabled = _default_source_policy_registry("yfinance", (), True)

    assert not disabled.resolve("market-default-v1").allows_purpose("research_cache_fill")
    assert enabled.resolve("market-default-v1").allows_purpose("research_cache_fill")


@pytest.mark.parametrize(
    ("asset_type", "market"),
    (
        ("stock", "US-NYSE"),
        ("fund", "US-NASDAQ"),
        ("futures", "US-CME"),
        ("fx", "US-OTC"),
        ("crypto", "GLOBAL"),
    ),
)
def test_default_openbb_policy_has_no_active_routes_while_outbound_end_is_unattested(
    asset_type: str,
    market: str,
) -> None:
    """A nonempty environment list cannot turn a blocked candidate into a broad fallback."""
    _default_source_policy_registry.cache_clear()
    registry = _default_source_policy_registry(
        "yfinance", ("US-NYSE", "US-NASDAQ", "US-CME", "US-OTC", "GLOBAL")
    )
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type=asset_type, venue=market),
        query=SimpleNamespace(
            data_kind="bars",
            frequency="1d",
            adjustment=None,
            price_basis=None,
            currency=None,
            unit=None,
        ),
    )

    assert registry.resolve("market-default-v1").routes_for(context) == ()


def test_openbb_runtime_permit_matrix_is_explicitly_empty() -> None:
    """No environment token may infer a provider, asset, market, or endpoint permit."""
    assert OPENBB_RUNTIME_PERMIT_MATRIX == ()
    assert (
        approved_openbb_runtime_route_permits(
            "yfinance", ("US-NYSE", "US-NASDAQ", "US-CME", "US-OTC", "GLOBAL")
        )
        == ()
    )


def test_default_policy_projects_every_axis_of_a_synthetic_explicit_openbb_permit(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """A future permit cannot lose product, market, or semantic scope in policy composition."""
    permit = OpenBBRuntimeRoutePermit(
        route_id="openbb-yfinance-stock-us-nyse-1d-v1",
        family_id="stock.realtime",
        family_contract_version="market-data-family-v1",
        provider="yfinance",
        asset_type="stock",
        market="US-NYSE",
        data_kind="bars",
        frequency="1d",
        adjustment=None,
        price_basis=None,
        currency=None,
        unit=None,
        endpoint="equity.price.historical",
    )
    monkeypatch.setattr(openbb_runtime, "OPENBB_RUNTIME_PERMIT_MATRIX", (permit,))
    _default_source_policy_registry.cache_clear()
    request.addfinalizer(_default_source_policy_registry.cache_clear)
    registry = _default_source_policy_registry("yfinance", ("US-NYSE",))
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="stock", venue="US-NYSE"),
        query=SimpleNamespace(
            family_id=permit.family_id,
            family_contract_version=permit.family_contract_version,
            data_kind="bars",
            frequency="1d",
            adjustment=None,
            price_basis=None,
            currency=None,
            unit=None,
        ),
    )

    routes = registry.resolve("market-default-v1").routes_for(context)

    assert [route.route_id for route in routes] == [permit.route_id]
    assert routes[0].request_provider == permit.provider
    assert routes[0].expected_result_provider_ids == frozenset({"openbb:yfinance"})
    assert routes[0].asset_types == frozenset({permit.asset_type})
    assert routes[0].markets == frozenset({permit.market})
    assert routes[0].data_kinds == frozenset({permit.data_kind})
    assert routes[0].frequencies == frozenset({permit.frequency})
    assert routes[0].family_id == permit.family_id
    assert routes[0].family_contract_version == permit.family_contract_version
    assert routes[0].provider_endpoint == permit.endpoint

    other_family_context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="stock", venue="US-NYSE"),
        query=SimpleNamespace(
            family_id="stock.valuation",
            data_kind="bars",
            frequency="1d",
            adjustment=None,
            price_basis=None,
            currency=None,
            unit=None,
        ),
    )
    assert registry.resolve("market-default-v1").routes_for(other_family_context) == ()
