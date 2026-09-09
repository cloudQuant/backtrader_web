"""Focused contract tests for the explicit AkShare v2 provider adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import date, datetime, timezone
from typing import Any

import pytest

from app.services.market_data import akshare_provider
from app.services.market_data.akshare_provider import (
    AKSHARE_ROUTE_REGISTRY,
    AKSHARE_SNAPSHOT_ROW_SCHEMAS,
    AkShareMarketDataProvider,
    AkShareProviderError,
    get_akshare_snapshot_row_schema,
)
from app.services.market_data.providers import MarketDataProviderRequest

UTC = timezone.utc


def _request(
    *,
    asset_type: str = "stock",
    provider: str = "akshare",
    data_kind: str = "bars",
    frequency: str = "1d",
    provider_symbol: str = "000001",
    market: str = "CN-SZSE",
    required_fields: frozenset[str] = frozenset({"close", "open"}),
    adjustment: str | None = None,
    price_basis: str | None = None,
    currency: str | None = None,
    unit: str | None = None,
    source_policy_id: str | None = "akshare-v2",
    route_id: str | None = None,
    product_type: str | None = None,
    fund_identity_kind: str | None = None,
) -> MarketDataProviderRequest:
    return MarketDataProviderRequest(
        query_fingerprint="b" * 64,
        canonical_id=f"instrument:{asset_type}:{market}:{provider_symbol}",
        asset_type=asset_type,
        provider_symbol=provider_symbol,
        market=market,
        data_kind=data_kind,
        frequency=frequency,
        start_at=datetime(2026, 1, 2, tzinfo=UTC),
        end_at=datetime(2026, 1, 4, tzinfo=UTC),
        required_fields=required_fields,
        provider=provider,
        adjustment=adjustment,
        price_basis=price_basis,
        currency=currency,
        unit=unit,
        source_policy_id=source_policy_id,
        route_id=route_id,
        product_type=product_type,
        fund_identity_kind=fund_identity_kind,
    )


def test_akshare_registry_declares_each_current_asset_type_explicitly() -> None:
    """Every currently supported asset type has a deliberate route decision."""
    assert {route.asset_type for route in AKSHARE_ROUTE_REGISTRY} == {
        "stock",
        "futures",
        "bond",
        "fund",
        "option",
        "fx",
        "crypto",
    }
    assert {
        (route.asset_type, route.data_kind, route.endpoint)
        for route in AKSHARE_ROUTE_REGISTRY
    } >= {
        ("stock", "reference_series", "stock_zh_a_hist"),
        ("fund", "reference_series", "fund_etf_hist_em"),
    }
    executable_routes = [
        route
        for route in AKSHARE_ROUTE_REGISTRY
        if route.endpoint is not None or route.endpoint_resolver is not None
    ]
    assert all(route.route_ids for route in executable_routes)
    assert len({route_id for route in executable_routes for route_id in route.route_ids}) == sum(
        len(route.route_ids) for route in executable_routes
    )


def test_snapshot_row_schemas_stay_out_of_the_request_time_provider_registry() -> None:
    """Wide-table schemas exist only for the offline importer, never as a symbol fallback."""
    assert {schema.asset_type for schema in AKSHARE_SNAPSHOT_ROW_SCHEMAS} == {
        "stock",
        "fund",
        "fx",
        "crypto",
        "option",
    }
    assert {route.data_kind for route in AKSHARE_ROUTE_REGISTRY} == {
        "bars",
        "reference_series",
    }
    assert get_akshare_snapshot_row_schema("stock").collector_observed_allowed is True
    assert get_akshare_snapshot_row_schema("fund").collector_observed_allowed is False
    assert get_akshare_snapshot_row_schema("fund").field_aliases["IOPV"] == "iopv"
    assert get_akshare_snapshot_row_schema("fx").field_aliases["最新价"] == "price"
    assert get_akshare_snapshot_row_schema("crypto").source_market_columns == ("市场", "market")
    assert get_akshare_snapshot_row_schema("crypto").field_aliases["最近报价"] == "price"

    with pytest.raises(AkShareProviderError) as unsupported:
        get_akshare_snapshot_row_schema("bond")

    assert unsupported.value.code == "AKSHARE_SNAPSHOT_ASSET_UNSUPPORTED"


@pytest.mark.asyncio
async def test_akshare_provider_uses_exact_symbol_route_and_preserves_provenance() -> None:
    """A one-symbol route is invoked in a worker thread and returns normalized records."""
    calls: list[dict[str, Any]] = []

    def fake_stock_route(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "日期": date(2026, 1, 2),
                "股票代码": "000001",
                "开盘": 10.0,
                "收盘": 10.5,
            },
            {
                "日期": date(2026, 1, 3),
                "股票代码": "000001",
                "开盘": 10.5,
                "收盘": 10.25,
            },
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)
    request = _request()
    result = await provider.fetch(request)

    assert calls == [
        {
            "symbol": "000001",
            "period": "daily",
            "start_date": "20260102",
            "end_date": "20260103",
            "adjust": "",
        }
    ]
    assert result.provider_id == "akshare"
    assert result.request is request
    assert [item.event_at for item in result.observations] == [
        datetime(2026, 1, 2, tzinfo=UTC),
        datetime(2026, 1, 3, tzinfo=UTC),
    ]
    assert result.observations[0].fields == {"open": 10.0, "close": 10.5}
    assert result.raw_payload["request"]["canonical_id"] == "instrument:stock:CN-SZSE:000001"
    assert result.raw_payload["request"]["provider_symbol"] == "000001"
    assert result.raw_payload["route"]["endpoint"] == "stock_zh_a_hist"
    assert result.raw_payload["response_rows"][0]["股票代码"] == "000001"
    expected_payload_hash = hashlib.sha256(
        json.dumps(
            dict(result.raw_payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert result.raw_payload_hash == expected_payload_hash


@pytest.mark.asyncio
async def test_akshare_provider_uses_the_current_market_page_field_contract() -> None:
    """AkShare labels map to the existing `change_pct` and `settle` schema names."""

    def fake_stock_route(**_: Any) -> list[dict[str, Any]]:
        return [
            {
                "日期": "2026-01-02",
                "股票代码": "000001",
                "开盘": 10.0,
                "收盘": 10.5,
                "涨跌幅": 5.0,
                "结算价": 10.25,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)
    result = await provider.fetch(
        _request(required_fields=frozenset({"open", "close", "change_pct", "settle"}))
    )

    assert result.observations[0].fields["change_pct"] == 5.0
    assert result.observations[0].fields["settle"] == 10.25


@pytest.mark.asyncio
async def test_akshare_provider_fetches_exact_stock_liquidity_reference_series() -> None:
    """The B1 stock-liquidity route remains code/date-bound and response-proven."""
    calls: list[dict[str, Any]] = []

    def fake_stock_route(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "日期": "2026-01-01",
                "股票代码": "000001",
                "成交量": 10,
                "成交额": 100.0,
                "换手率": 1.25,
            },
            {
                "日期": "2026-01-02",
                "股票代码": "000001",
                "成交量": 20,
                "成交额": 200.0,
                "换手率": 2.5,
            },
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)
    result = await provider.fetch(
        _request(
            data_kind="reference_series",
            required_fields=frozenset({"volume", "turnover", "turnover_rate"}),
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="share",
            route_id="akshare-stock-liquidity-primary-v1",
        )
    )

    assert calls == [
        {
            "symbol": "000001",
            "period": "daily",
            "start_date": "20260102",
            "end_date": "20260103",
            "adjust": "",
        }
    ]
    assert [item.event_at for item in result.observations] == [datetime(2026, 1, 2, tzinfo=UTC)]
    assert result.observations[0].fields == {
        "volume": 20,
        "turnover": 200.0,
        "turnover_rate": 2.5,
    }
    assert result.raw_payload["route"]["endpoint"] == "stock_zh_a_hist"
    assert result.raw_payload["request"]["route_id"] == "akshare-stock-liquidity-primary-v1"


@pytest.mark.asyncio
async def test_akshare_provider_fetches_exact_etf_liquidity_reference_series() -> None:
    """The B1 ETF route cannot borrow a broad spot table as a symbol fallback."""
    calls: list[dict[str, Any]] = []

    def fake_fund_route(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "日期": "2026-01-02",
                "成交量": 30,
                "成交额": 300.0,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_fund_route)
    result = await provider.fetch(
        _request(
            asset_type="fund",
            provider_symbol="159915",
            market="CN-SZSE",
            data_kind="reference_series",
            required_fields=frozenset({"volume", "turnover"}),
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="share",
            route_id="akshare-fund-liquidity-primary-v1",
        )
    )

    assert calls == [
        {
            "symbol": "159915",
            "period": "daily",
            "start_date": "20260102",
            "end_date": "20260103",
            "adjust": "",
        }
    ]
    assert [item.event_at for item in result.observations] == [datetime(2026, 1, 2, tzinfo=UTC)]
    assert result.observations[0].fields == {"volume": 30, "turnover": 300.0}
    assert result.warnings == ("AKSHARE_IDENTITY_SOURCE_REQUEST_BOUND",)
    assert result.raw_payload["route"]["endpoint"] == "fund_etf_hist_em"
    assert result.raw_payload["request"]["route_id"] == "akshare-fund-liquidity-primary-v1"


@pytest.mark.asyncio
async def test_akshare_provider_fetches_exact_etf_nav_reference_series() -> None:
    """ETF NAV uses its own source route and preserves source-reported NAV semantics."""
    calls: list[dict[str, Any]] = []

    def fake_fund_nav_route(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "净值日期": "2026-01-02",
                "单位净值": 1.2345,
                "累计净值": 1.4567,
                "日增长率": 0.98,
                "申购状态": "开放申购",
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_fund_nav_route)
    result = await provider.fetch(
        _request(
            asset_type="fund",
            provider_symbol="159915",
            market="CN-SZSE",
            data_kind="reference_series",
            required_fields=frozenset({"nav", "cumulative_nav", "daily_growth_rate"}),
            adjustment="source_reported",
            price_basis="nav",
            currency="CNY",
            unit="fund_share",
            route_id="akshare-fund-nav-primary-v1",
            product_type="ETF",
            fund_identity_kind="LISTING",
        )
    )

    assert calls == [
        {
            "fund": "159915",
            "start_date": "20260102",
            "end_date": "20260103",
        }
    ]
    assert [item.event_at for item in result.observations] == [datetime(2026, 1, 2, tzinfo=UTC)]
    assert result.observations[0].fields == {
        "nav": 1.2345,
        "cumulative_nav": 1.4567,
        "daily_growth_rate": 0.98,
        "申购状态": "开放申购",
    }
    assert result.warnings == ("AKSHARE_IDENTITY_SOURCE_REQUEST_BOUND",)
    assert result.raw_payload["route"]["endpoint"] == "fund_etf_fund_info_em"
    assert result.raw_payload["request"]["route_id"] == "akshare-fund-nav-primary-v1"


@pytest.mark.asyncio
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
async def test_akshare_provider_rejects_nav_requests_without_an_etf_listing_identity(
    product_type: str | None,
    fund_identity_kind: str | None,
) -> None:
    """The dedicated ETF NAV endpoint must reject every nearby fund product before I/O."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("invalid identity must not resolve a source callable")
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(
            _request(
                asset_type="fund",
                provider_symbol="159915",
                market="CN-SZSE",
                data_kind="reference_series",
                required_fields=frozenset({"nav", "cumulative_nav", "daily_growth_rate"}),
                adjustment="source_reported",
                price_basis="nav",
                currency="CNY",
                unit="fund_share",
                route_id="akshare-fund-nav-primary-v1",
                product_type=product_type,
                fund_identity_kind=fund_identity_kind,
            )
        )

    assert rejected.value.code == "AKSHARE_PRODUCT_IDENTITY_UNSUPPORTED"


@pytest.mark.asyncio
async def test_akshare_provider_requires_a_policy_route_id_when_product_axes_overlap() -> None:
    """Overlapping ETF reference products cannot select an endpoint by resemblance."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("ambiguous request must not fetch")
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(
            _request(
                asset_type="fund",
                provider_symbol="159915",
                market="CN-SZSE",
                data_kind="reference_series",
                required_fields=frozenset({"nav", "cumulative_nav", "daily_growth_rate"}),
                adjustment="source_reported",
                price_basis="nav",
                currency="CNY",
                unit="fund_share",
                route_id=None,
            )
        )

    assert rejected.value.code == "AKSHARE_ROUTE_UNSUPPORTED"


@pytest.mark.asyncio
async def test_akshare_provider_rejects_a_source_policy_route_id_for_another_product() -> None:
    """A broad reference-series data kind cannot bypass the exact route binding."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("mismatched route IDs must not fetch")
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(
            _request(
                data_kind="reference_series",
                required_fields=frozenset({"volume", "turnover", "turnover_rate"}),
                route_id="akshare-stock-primary-v1",
            )
        )

    assert rejected.value.code == "AKSHARE_ROUTE_UNSUPPORTED"


@pytest.mark.asyncio
async def test_akshare_provider_rejects_a_response_for_a_different_symbol() -> None:
    """A route response cannot be persisted when it identifies another instrument."""

    def fake_stock_route(**_: Any) -> list[dict[str, Any]]:
        return [
            {
                "日期": "2026-01-02",
                "股票代码": "000002",
                "开盘": 10.0,
                "收盘": 10.5,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)

    with pytest.raises(AkShareProviderError) as mismatch:
        await provider.fetch(_request())

    assert mismatch.value.code == "AKSHARE_IDENTITY_MISMATCH"


@pytest.mark.asyncio
async def test_akshare_provider_filters_an_inclusive_endpoint_to_the_half_open_window() -> None:
    """An inclusive date endpoint only yields `[start, end)` normalized observations."""

    def fake_stock_route(**_: Any) -> list[dict[str, Any]]:
        return [
            {
                "日期": "2026-01-01",
                "股票代码": "000001",
                "开盘": 9.0,
                "收盘": 10.0,
            },
            {
                "日期": "2026-01-02",
                "股票代码": "000001",
                "开盘": 10.0,
                "收盘": 10.5,
            },
            {
                "日期": "2026-01-04",
                "股票代码": "000001",
                "开盘": 10.5,
                "收盘": 11.0,
            },
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)
    result = await provider.fetch(_request())

    assert [item.event_at for item in result.observations] == [datetime(2026, 1, 2, tzinfo=UTC)]


@pytest.mark.asyncio
async def test_akshare_provider_filters_the_known_full_history_route_to_the_window() -> None:
    """A documented full-history endpoint only yields in-window normalized observations."""

    def fake_futures_route(**_: Any) -> list[dict[str, Any]]:
        return [
            {"date": "2026-01-01", "open": 9.0, "close": 10.0},
            {"date": "2026-01-02", "open": 10.0, "close": 10.5},
            {"date": "2026-01-04", "open": 10.5, "close": 11.0},
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_futures_route)
    result = await provider.fetch(
        _request(asset_type="futures", provider_symbol="IF2609", market="CFFEX")
    )

    assert [item.event_at for item in result.observations] == [datetime(2026, 1, 2, tzinfo=UTC)]
    assert result.observations[0].fields == {"open": 10.0, "close": 10.5}
    assert result.warnings == ("AKSHARE_IDENTITY_SOURCE_REQUEST_BOUND",)


@pytest.mark.asyncio
async def test_akshare_provider_selects_cffex_option_history_from_an_exact_contract() -> None:
    """A CFFEX option code chooses only its reviewed source function, never a chain alias."""
    resolved_endpoints: list[str] = []
    calls: list[dict[str, Any]] = []

    def callable_resolver(endpoint: str):
        resolved_endpoints.append(endpoint)

        def fake_option_route(**kwargs: Any) -> list[dict[str, Any]]:
            calls.append(kwargs)
            return [
                {"date": "2026-01-02", "open": 101.0, "close": 102.5},
                {"date": "2026-01-04", "open": 102.0, "close": 103.0},
            ]

        return fake_option_route

    provider = AkShareMarketDataProvider(callable_resolver=callable_resolver)
    result = await provider.fetch(
        _request(
            asset_type="option",
            provider_symbol="MO2609-P-5000",
            market="CFFEX",
            required_fields=frozenset({"close"}),
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="contract",
        )
    )

    assert resolved_endpoints == ["option_cffex_zz1000_daily_sina"]
    assert calls == [{"symbol": "MO2609-P-5000"}]
    assert [item.event_at for item in result.observations] == [datetime(2026, 1, 2, tzinfo=UTC)]
    assert result.observations[0].fields == {"open": 101.0, "close": 102.5}
    assert result.raw_payload["route"]["endpoint"] == "option_cffex_zz1000_daily_sina"


@pytest.mark.asyncio
async def test_akshare_provider_rejects_an_unapproved_market_before_calling_the_source() -> None:
    """A provider route cannot overwrite a US identity with China-market source data."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("unsupported markets must not invoke AkShare")
    )

    with pytest.raises(AkShareProviderError) as unsupported_market:
        await provider.fetch(_request(market="US"))

    assert unsupported_market.value.code == "AKSHARE_MARKET_UNSUPPORTED"


@pytest.mark.asyncio
async def test_akshare_provider_rejects_a_symbol_that_contradicts_its_market() -> None:
    """The China stock route validates the exchange implied by its source symbol."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("invalid exchange symbols must not invoke AkShare")
    )

    with pytest.raises(AkShareProviderError) as mismatch:
        await provider.fetch(_request(market="CN-SSE", provider_symbol="000001"))

    assert mismatch.value.code == "AKSHARE_SYMBOL_MARKET_MISMATCH"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_request",
    [
        _request(asset_type="futures", provider_symbol="RB0", market="CFFEX"),
        _request(asset_type="futures", provider_symbol="TA0", market="CFFEX"),
        _request(asset_type="fund", provider_symbol="159915", market="CN-SSE"),
    ],
)
async def test_akshare_provider_rejects_request_bound_routes_with_an_invalid_venue_symbol_pair(
    provider_request: MarketDataProviderRequest,
) -> None:
    """No-returned-symbol routes use explicit AkShare venue maps before a fetch."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("invalid venue mappings must not invoke AkShare")
    )

    with pytest.raises(AkShareProviderError) as mismatch:
        await provider.fetch(provider_request)

    assert mismatch.value.code == "AKSHARE_SYMBOL_MARKET_MISMATCH"


@pytest.mark.asyncio
async def test_akshare_provider_passes_the_explicit_adjustment_and_price_basis() -> None:
    """An adjusted series cannot be fetched with AkShare's unadjusted default."""
    calls: list[dict[str, Any]] = []

    def fake_stock_route(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "日期": "2026-01-02",
                "股票代码": "000001",
                "开盘": 10.0,
                "收盘": 10.5,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)
    await provider.fetch(
        _request(adjustment="qfq", price_basis="close", currency="CNY", unit="share")
    )

    assert calls[0]["adjust"] == "qfq"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"adjustment": "other"}, "AKSHARE_ADJUSTMENT_UNSUPPORTED"),
        ({"price_basis": "mid"}, "AKSHARE_PRICE_BASIS_UNSUPPORTED"),
        ({"currency": "USD"}, "AKSHARE_CURRENCY_UNSUPPORTED"),
        ({"unit": "lot"}, "AKSHARE_UNIT_UNSUPPORTED"),
    ],
)
async def test_akshare_provider_rejects_unmapped_query_semantics(
    changes: dict[str, str],
    expected_code: str,
) -> None:
    """Unsupported semantic dimensions fail before any source call can occur."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("unsupported semantics must not invoke AkShare")
    )

    with pytest.raises(AkShareProviderError) as unsupported:
        await provider.fetch(_request(**changes))

    assert unsupported.value.code == expected_code


@pytest.mark.asyncio
async def test_akshare_provider_requires_a_policy_for_request_bound_identity_routes() -> None:
    """Routes that omit a returned symbol require an explicit source-policy decision."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("missing source policy must not invoke AkShare")
    )

    with pytest.raises(AkShareProviderError) as missing_policy:
        await provider.fetch(
            _request(
                asset_type="futures",
                provider_symbol="IF2609",
                market="CFFEX",
                source_policy_id=None,
            )
        )

    assert missing_policy.value.code == "AKSHARE_SOURCE_POLICY_REQUIRED"


@pytest.mark.asyncio
async def test_akshare_provider_rejects_a_mismatched_forex_response_symbol() -> None:
    """The forex route independently verifies the code that AkShare returns."""

    def fake_forex_route(**_: Any) -> list[dict[str, Any]]:
        return [
            {
                "日期": "2026-01-02",
                "代码": "USDCNY",
                "今开": 7.0,
                "最新价": 7.1,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_forex_route)

    with pytest.raises(AkShareProviderError) as mismatch:
        await provider.fetch(_request(asset_type="fx", provider_symbol="USDCNH", market="OTC"))

    assert mismatch.value.code == "AKSHARE_IDENTITY_MISMATCH"


@pytest.mark.asyncio
async def test_akshare_provider_fetches_the_exact_fx_range_ohlc_shape() -> None:
    """The FX range family keeps its full reviewed OHLC contract end to end."""
    calls: list[dict[str, Any]] = []

    def fake_forex_route(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        return [
            {
                "日期": "2026-01-02",
                "代码": "USDCNH",
                "今开": 7.0,
                "最新价": 7.1,
                "最高": 7.2,
                "最低": 6.9,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_forex_route)
    result = await provider.fetch(
        _request(
            asset_type="fx",
            provider_symbol="USDCNH",
            market="OTC",
            required_fields=frozenset({"open", "high", "low", "close"}),
            adjustment="unadjusted",
            price_basis="close",
            route_id="akshare-fx-primary-v1",
        )
    )

    assert calls == [{"symbol": "USDCNH"}]
    assert result.observations[0].fields == {
        "open": 7.0,
        "close": 7.1,
        "high": 7.2,
        "low": 6.9,
    }
    assert result.raw_payload["route"]["endpoint"] == "forex_hist_em"


@pytest.mark.asyncio
async def test_akshare_provider_times_out_bounded_worker_calls() -> None:
    """A stalled synchronous AkShare endpoint cannot wait indefinitely in the request path."""

    def slow_stock_route(**_: Any) -> list[dict[str, Any]]:
        time.sleep(0.1)
        return []

    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: slow_stock_route,
        timeout_seconds=0.02,
        max_concurrency=1,
    )

    with pytest.raises(AkShareProviderError) as timeout:
        await provider.fetch(_request())

    assert timeout.value.code == "AKSHARE_TIMEOUT"
    # Let the non-cancellable worker complete so its completion callback can
    # release the bounded slot before this test event loop is torn down.
    await asyncio.sleep(0.12)


@pytest.mark.asyncio
async def test_akshare_provider_times_out_while_all_worker_slots_are_held() -> None:
    """A timed-out non-cancellable worker cannot make the next request wait forever."""

    def slow_stock_route(**_: Any) -> list[dict[str, Any]]:
        time.sleep(0.1)
        return []

    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: slow_stock_route,
        timeout_seconds=0.02,
        max_concurrency=1,
    )

    with pytest.raises(AkShareProviderError) as first_timeout:
        await provider.fetch(_request())
    with pytest.raises(AkShareProviderError) as capacity_timeout:
        await provider.fetch(_request())

    assert first_timeout.value.code == "AKSHARE_TIMEOUT"
    assert capacity_timeout.value.code == "AKSHARE_TIMEOUT"
    await asyncio.sleep(0.12)


@pytest.mark.asyncio
async def test_akshare_provider_rejects_oversized_dataframe_before_materializing_rows() -> None:
    """A dataframe-like source cannot allocate record dictionaries past the store row limit."""

    class OversizedDataframe:
        def __len__(self) -> int:
            return 50_001

        def to_dict(self, *, orient: str) -> list[dict[str, Any]]:
            pytest.fail(f"to_dict must not run for an oversized response: {orient}")

    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: lambda **_: OversizedDataframe()
    )

    with pytest.raises(AkShareProviderError) as oversized:
        await provider.fetch(_request())

    assert oversized.value.code == "AKSHARE_RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_akshare_provider_rejects_provenance_larger_than_the_store_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance is size-checked before a result can reach the normalized writer."""
    monkeypatch.setattr(akshare_provider, "_MAX_PROVENANCE_BYTES", 1)

    def fake_stock_route(**_: Any) -> list[dict[str, Any]]:
        return [
            {
                "日期": "2026-01-02",
                "股票代码": "000001",
                "开盘": 10.0,
                "收盘": 10.5,
            }
        ]

    provider = AkShareMarketDataProvider(callable_resolver=lambda _: fake_stock_route)

    with pytest.raises(AkShareProviderError) as oversized:
        await provider.fetch(_request())

    assert oversized.value.code == "AKSHARE_PROVENANCE_TOO_LARGE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_request", "expected_code"),
    [
        (
            _request(asset_type="option", provider_symbol="UNKNOWN2609", market="CFFEX"),
            "AKSHARE_SYMBOL_MARKET_MISMATCH",
        ),
        (_request(asset_type="crypto"), "AKSHARE_ROUTE_UNSUPPORTED"),
        (_request(provider="openbb"), "AKSHARE_PROVIDER_MISMATCH"),
    ],
)
async def test_akshare_provider_fails_closed_for_unapproved_routes_or_sources(
    provider_request: MarketDataProviderRequest,
    expected_code: str,
) -> None:
    """The adapter never guesses an endpoint or silently switches providers."""
    provider = AkShareMarketDataProvider(
        callable_resolver=lambda _: pytest.fail("a disallowed route must not be invoked")
    )

    with pytest.raises(AkShareProviderError) as rejected:
        await provider.fetch(provider_request)

    assert rejected.value.code == expected_code
