"""Unit contracts for explicit route capability and policy purpose controls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.data.queries import _default_source_policy_registry
from app.services.market_data import openbb_runtime
from app.services.market_data.openbb_runtime import (
    OPENBB_RUNTIME_PERMIT_MATRIX,
    OpenBBRuntimeRoutePermit,
    approved_openbb_runtime_route_permits,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)


class _Provider:
    async def fetch(self, _request):
        raise AssertionError("route selection tests must not invoke an adapter")


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
    assert registry.resolve("market-default-v1").routes_for(
        SimpleNamespace(
            identity=context.identity,
            query=SimpleNamespace(
                family_id="fund.liquidity",
                data_kind="reference_series",
                frequency="1d",
                adjustment="source_reported",
                price_basis="nav",
                currency="CNY",
                unit="fund_share",
            ),
        )
    ) == ()


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
