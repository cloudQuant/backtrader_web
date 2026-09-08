"""Regression coverage for the F1 market-page data-product control plane."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.data.deps import get_market_data_access_authorizer
from app.main import app
from app.schemas.market_data_platform import (
    MarketDataFamilyContractResponse,
    MarketDataQueryBundleRequest,
    MarketDataQueryRequest,
)
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    DatasetContractRegistryError,
)

_ASSET_TYPES = ("stock", "futures", "bond", "fund", "option", "fx", "crypto")
_FAMILY_IDS = {
    "stock.realtime",
    "stock.valuation",
    "stock.liquidity",
    "futures.realtime",
    "futures.settlement",
    "futures.inventory",
    "bond.realtime",
    "bond.orderbook",
    "bond.fixed_income",
    "fund.realtime",
    "fund.liquidity",
    "fund.nav",
    "option.realtime",
    "option.derivative",
    "option.risk_surface",
    "fx.realtime",
    "fx.macro_fx",
    "fx.range",
    "crypto.realtime",
    "crypto.cme_position",
    "crypto.range",
}


class _PermittedMarketDataAccess:
    """Keep static-contract tests focused after v2 control-plane RBAC is enforced."""

    async def principal_for_user(self, _user: object) -> object:
        return object()

    @staticmethod
    def require_read_data(*, principal: object) -> None:
        assert principal is not None


@pytest.fixture
def permitted_market_data_access() -> None:
    """Supply the approved data-read gate required by v2 control-plane routes."""
    app.dependency_overrides[get_market_data_access_authorizer] = _PermittedMarketDataAccess
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)


def _query_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
        "dataset_code": "market.bars",
        "data_kind": "bars",
        "frequency": "1d",
        "start": "2026-09-08T09:00:00+00:00",
        "end": "2026-09-08T12:00:00+00:00",
        "required_fields": ["close"],
        "source_policy_id": "market-default-v1",
    }
    payload.update(changes)
    return payload


def test_registry_declares_all_twenty_one_current_market_page_families() -> None:
    """Each of seven current tabs receives exactly three stable family contracts."""
    entries = [
        family
        for asset_type in _ASSET_TYPES
        for family in DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
            MarketDataQueryBundleRequest(asset_type=asset_type)
        ).families
    ]

    assert len(entries) == 21
    assert {entry.family_id for entry in entries} == _FAMILY_IDS
    assert {entry.asset_type for entry in entries} == set(_ASSET_TYPES)
    assert all(
        sum(entry.asset_type == asset_type for entry in entries) == 3 for asset_type in _ASSET_TYPES
    )


def test_ready_entries_are_only_reviewed_bars_compatibility_contracts() -> None:
    """No quote, report, reference, chain, or surface may look executable in F1."""
    entries = [
        family
        for asset_type in _ASSET_TYPES
        for family in DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
            MarketDataQueryBundleRequest(asset_type=asset_type)
        ).families
    ]
    ready = [entry for entry in entries if entry.status == "ready"]
    not_ready = [entry for entry in entries if entry.status != "ready"]

    assert {entry.family_id for entry in ready} == {
        "stock.realtime",
        "futures.realtime",
        "bond.realtime",
        "fund.realtime",
        "option.realtime",
        "fx.realtime",
    }
    assert all(entry.dataset_code == "market.bars" for entry in ready)
    assert all(entry.data_kind == "bars" for entry in ready)
    assert all(entry.frequency_semantics == "calendar_grid" for entry in ready)
    assert all(entry.coverage_model == "calendar_grid" for entry in ready)
    assert all(entry.required_fields == ("close",) for entry in ready)
    assert all(entry.source_policy_id == "market-default-v1" for entry in ready)
    assert all(entry.family_contract_version == "market-data-family-v1" for entry in entries)
    assert all(entry.reason_code is None for entry in ready)
    assert all(entry.source_policy_id is None for entry in not_ready)
    assert all(entry.reason_code is not None for entry in not_ready)


def test_registry_preserves_non_bar_record_shapes_and_coverage_models() -> None:
    """Family declarations retain their own cadence and completeness proof model."""
    option_bundle = DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
        MarketDataQueryBundleRequest(asset_type="option")
    )
    futures_bundle = DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
        MarketDataQueryBundleRequest(asset_type="futures")
    )
    by_id = {
        entry.family_id: entry for entry in (*option_bundle.families, *futures_bundle.families)
    }

    derivative = by_id["option.derivative"]
    risk_surface = by_id["option.risk_surface"]
    inventory = by_id["futures.inventory"]

    assert (derivative.dataset_code, derivative.data_kind, derivative.frequencies) == (
        "market.option_chain",
        "option_chain",
        ("snapshot",),
    )
    assert derivative.coverage_model == "slice_completeness"
    assert {"expiry", "strike", "right"} <= set(derivative.dimension_fields)
    assert (risk_surface.data_kind, risk_surface.coverage_model) == (
        "option_risk_surface",
        "slice_completeness",
    )
    assert (inventory.data_kind, inventory.frequency_semantics, inventory.coverage_model) == (
        "inventory_report",
        "reporting_period",
        "report_completeness",
    )


def test_registry_returns_explicit_not_applicable_for_a_known_cross_asset_family() -> None:
    """A filtered family cannot acquire another asset's source policy by accident."""
    bundle = DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
        MarketDataQueryBundleRequest(asset_type="stock", family_id="futures.inventory")
    )

    assert bundle.requested_asset_type == "stock"
    assert len(bundle.families) == 1
    family = bundle.families[0]
    assert family.family_id == "futures.inventory"
    assert family.status == "not_applicable"
    assert family.reason_code == "DATA_FAMILY_NOT_APPLICABLE"
    assert family.source_policy_id is None


def test_registry_rejects_unknown_family_without_nearby_fallback() -> None:
    """A typo cannot collapse to an adjacent data family or a legacy table name."""
    with pytest.raises(DatasetContractRegistryError) as unsupported:
        DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
            MarketDataQueryBundleRequest(asset_type="stock", family_id="stock.unknown")
        )

    assert unsupported.value.code == "DATA_FAMILY_UNSUPPORTED"


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_type": "stock", "provider": "akshare"},
        {"asset_type": "stock", "family_id": "stock.realtime/v2"},
        {"asset_type": "stock", "family_id": "stock.realTime"},
    ],
)
def test_bundle_request_dto_rejects_unrecognized_control_plane_axes(
    payload: dict[str, object],
) -> None:
    """The control plane itself never accepts a provider or an invalid family key."""
    with pytest.raises(ValidationError):
        MarketDataQueryBundleRequest.model_validate(payload)


def test_contract_dto_rejects_a_non_bar_product_claiming_ready_bars_compatibility() -> None:
    """The wire DTO enforces the same fail-closed boundary as the registry."""
    with pytest.raises(ValidationError):
        MarketDataFamilyContractResponse.model_validate(
            {
                "family_id": "option.derivative",
                "asset_type": "option",
                "status": "ready",
                "dataset_code": "market.bars",
                "data_kind": "option_chain",
                "frequency_semantics": "snapshot",
                "frequencies": ["snapshot"],
                "field_profile_id": "invalid-option-chain-v1",
                "required_fields": ["last"],
                "coverage_model": "slice_completeness",
                "source_policy_id": "market-default-v1",
            }
        )


@pytest.mark.parametrize(
    ("changes", "expected_message"),
    [
        ({"frequency": "snapshot"}, "bars queries cannot use the snapshot frequency"),
        (
            {"data_kind": "quote_snapshot", "frequency": "1d"},
            "snapshot data kinds require the explicit snapshot frequency",
        ),
        (
            {"data_kind": "position_report", "frequency": "snapshot"},
            "report and reference-series queries require a non-snapshot frequency",
        ),
        (
            {"data_kind": "inventory_report", "frequency": None},
            "report and reference-series queries require a non-snapshot frequency",
        ),
    ],
)
def test_query_dto_rejects_unsupported_data_kind_frequency_combinations(
    changes: dict[str, object],
    expected_message: str,
) -> None:
    """Explicit snapshot/report semantics cannot be smuggled through generic queries."""
    with pytest.raises(ValidationError, match=expected_message):
        MarketDataQueryRequest.model_validate(_query_payload(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"data_kind": "quote_snapshot", "frequency": "snapshot"},
        {"data_kind": "option_chain", "frequency": "snapshot"},
        {"data_kind": "option_risk_surface", "frequency": "snapshot"},
        {"data_kind": "reference_series", "frequency": "1d"},
        {"data_kind": "position_report", "frequency": "1w"},
        {"data_kind": "inventory_report", "frequency": "1d"},
    ],
)
def test_query_dto_accepts_only_explicit_intended_non_bar_cadences(
    changes: dict[str, object],
) -> None:
    """New record shapes remain representable without using a bars frequency surrogate."""
    request = MarketDataQueryRequest.model_validate(_query_payload(**changes))

    assert request.frequency == changes["frequency"]


def test_family_bound_query_requires_a_complete_exact_product_binding() -> None:
    """A bundle-selected product cannot be reinterpreted as a nearby bars contract."""
    bound = MarketDataQueryRequest.model_validate(
        _query_payload(
            family_id="stock.realtime",
            family_contract_version="market-data-family-v1",
        )
    )
    unbound = MarketDataQueryRequest.model_validate(_query_payload())

    assert bound.family_id == "stock.realtime"
    assert bound.family_contract_version == "market-data-family-v1"
    assert bound.query_fingerprint != unbound.query_fingerprint
    for changes in (
        {"family_id": "stock.realtime"},
        {"family_contract_version": "market-data-family-v1"},
        {"family_id": "stock realtime", "family_contract_version": "market-data-family-v1"},
    ):
        with pytest.raises(ValidationError):
            MarketDataQueryRequest.model_validate(_query_payload(**changes))


def test_registry_rejects_any_drift_from_a_bound_ready_family() -> None:
    """Family execution must preserve the server-declared dataset and field profile."""
    binding = {
        "family_id": "stock.realtime",
        "family_contract_version": "market-data-family-v1",
        "asset_type": "stock",
        "dataset_code": "market.bars",
        "data_kind": "bars",
        "frequency": "1d",
        "required_fields": ("close",),
        "source_policy_id": "market-default-v1",
    }
    DEFAULT_DATASET_CONTRACT_REGISTRY.assert_query_binding(**binding)

    for changes in (
        {"dataset_code": "market.stock_daily"},
        {"data_kind": "reference_series"},
        {"frequency": "5min"},
        {"required_fields": ("close", "volume")},
        {"source_policy_id": "market-premium-v2"},
        {"asset_type": "futures"},
        {"family_contract_version": "market-data-family-v0"},
    ):
        with pytest.raises(DatasetContractRegistryError):
            DEFAULT_DATASET_CONTRACT_REGISTRY.assert_query_binding(**(binding | changes))


@pytest.mark.asyncio
async def test_query_bundle_endpoint_is_disabled_with_the_v2_rollout_flag(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """The static control plane shares the existing explicit v2 rollout gate."""
    import app.api.data.queries as queries

    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=False),
    )

    response = await client.get(
        "/api/v1/data/market-instruments/query-bundle",
        params={"asset_type": "stock"},
        headers=auth_headers,
    )

    assert response.status_code == 503
    assert response.json()["details"] == {"code": "MARKET_DATA_QUERY_V2_DISABLED"}


@pytest.mark.asyncio
async def test_query_bundle_endpoint_returns_static_contracts_without_a_query_service(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """The bundle endpoint has no provider/service dependency and exposes all three stock cards."""
    import app.api.data.queries as queries

    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )

    def unexpected_query_service(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("query bundle must not construct a data query service")

    monkeypatch.setattr(queries, "get_market_data_query_service", unexpected_query_service)
    response = await client.get(
        "/api/v1/data/market-instruments/query-bundle",
        params={"asset_type": "stock"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "market-data-family-bundle-v1"
    assert body["requested_asset_type"] == "stock"
    assert [(entry["family_id"], entry["status"]) for entry in body["families"]] == [
        ("stock.realtime", "ready"),
        ("stock.valuation", "unconfigured"),
        ("stock.liquidity", "unconfigured"),
    ]
    assert body["families"][0]["required_fields"] == ["close"]
    assert body["families"][1]["source_policy_id"] is None


@pytest.mark.asyncio
async def test_query_bundle_endpoint_fails_closed_for_unknown_or_extra_query_axes(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """No arbitrary provider, endpoint, or nearest family may be selected by a bundle request."""
    import app.api.data.queries as queries

    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    unknown = await client.get(
        "/api/v1/data/market-instruments/query-bundle",
        params={"asset_type": "stock", "family_id": "stock.unknown"},
        headers=auth_headers,
    )
    extra_axis = await client.get(
        "/api/v1/data/market-instruments/query-bundle",
        params={"asset_type": "stock", "provider": "akshare"},
        headers=auth_headers,
    )
    duplicate_axis = await client.get(
        "/api/v1/data/market-instruments/query-bundle?asset_type=stock&asset_type=fx",
        headers=auth_headers,
    )

    assert unknown.status_code == 422
    assert unknown.json()["details"] == {"code": "DATA_FAMILY_UNSUPPORTED"}
    assert extra_axis.status_code == 422
    assert extra_axis.json()["details"] == {"code": "DATA_FAMILY_REQUEST_INVALID"}
    assert duplicate_axis.status_code == 422
    assert duplicate_axis.json()["details"] == {"code": "DATA_FAMILY_REQUEST_INVALID"}


@pytest.mark.asyncio
async def test_query_bundle_endpoint_marks_cross_asset_filter_not_applicable(
    client,
    auth_headers,
    monkeypatch,
    permitted_market_data_access,
) -> None:
    """A known product from another asset type is explicit and still non-executable."""
    import app.api.data.queries as queries

    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    response = await client.get(
        "/api/v1/data/market-instruments/query-bundle",
        params={"asset_type": "stock", "family_id": "futures.inventory"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    family = response.json()["families"][0]
    assert family["status"] == "not_applicable"
    assert family["reason_code"] == "DATA_FAMILY_NOT_APPLICABLE"
    assert family["source_policy_id"] is None


@pytest.mark.asyncio
async def test_query_bundle_requires_data_read_before_returning_control_plane_metadata(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """An authenticated principal without a role cannot enumerate v2 contracts."""
    import app.api.data.queries as queries

    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    response = await client.get(
        "/api/v1/data/market-instruments/query-bundle",
        params={"asset_type": "stock"},
        headers=auth_headers,
    )

    assert response.status_code == 403
    assert response.json()["details"] == {"code": "MARKET_DATA_READ_ENTITLEMENT_DENIED"}


def test_query_bundle_route_is_registered_alongside_existing_bars_contract_routes() -> None:
    """F1 adds an independent control-plane path and leaves the bars bridge intact."""
    paths = {route.path for route in app.routes}

    assert "/api/v1/data/market-instruments/query-bundle" in paths
    assert "/api/v1/data/market-instruments/query-contract" in paths
    assert "/api/v1/data/queries" in paths
