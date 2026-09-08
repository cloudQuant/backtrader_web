"""Unit contracts for explicit route capability and policy purpose controls."""

from __future__ import annotations

from types import SimpleNamespace

from app.api.data.queries import _default_source_policy_registry
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


def test_default_policy_only_grants_research_cache_fill_after_server_opt_in() -> None:
    """A browser cannot enable the research-authorized write purpose by itself."""
    _default_source_policy_registry.cache_clear()
    disabled = _default_source_policy_registry("yfinance", ())
    enabled = _default_source_policy_registry("yfinance", (), True)

    assert not disabled.resolve("market-default-v1").allows_purpose("research_cache_fill")
    assert enabled.resolve("market-default-v1").allows_purpose("research_cache_fill")


def test_default_openbb_policy_is_limited_to_verified_date_aligned_frequencies() -> None:
    """An OpenBB fallback cannot receive intraday windows before their end semantics are reviewed."""
    _default_source_policy_registry.cache_clear()
    registry = _default_source_policy_registry("yfinance", ("US-NASDAQ",))
    context = SimpleNamespace(
        identity=SimpleNamespace(asset_type="stock", venue="US-NASDAQ"),
        query=SimpleNamespace(
            data_kind="bars",
            frequency="5min",
            adjustment=None,
            price_basis=None,
            currency=None,
            unit=None,
        ),
    )

    assert registry.resolve("market-default-v1").routes_for(context) == ()
