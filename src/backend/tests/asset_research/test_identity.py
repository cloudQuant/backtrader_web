"""Strict identity resolution tests; ambiguous input must never become a sample asset."""

from datetime import datetime, time, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.asset_research import (
    BondIdentityDetails,
    CryptoProductIdentityDetails,
    FundIdentityDetails,
    FuturesIdentityDetails,
    FxIdentityDetails,
    InstrumentIdentity,
    InstrumentResolveRequest,
)
from app.services.asset_research.identity import InstrumentResolutionError, InstrumentResolver


class _FakeMarketInstruments:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self._items = items

    async def list_instruments(self, **_: object) -> dict[str, object]:
        return {"items": self._items}


def _identity_kwargs(*, asset_type: str, identity_level: str, venue: str | None = "FIXTURE") -> dict[str, object]:
    """Return the shared, non-domain identity fields used by schema tests."""
    return {
        "asset_type": asset_type,
        "identity_level": identity_level,
        "canonical_id": f"{asset_type}:fixture:instrument",
        "display_symbol": f"{asset_type.upper()}-FIXTURE",
        "name": f"{asset_type} fixture",
        "venue": venue,
        "currency": "USD",
        "timezone": "UTC",
        "identifier_type": "FIXTURE",
        "identifier_value": f"{asset_type}-fixture",
        "product_type": asset_type.upper(),
        "metadata_version": "fixture-v1",
    }


def test_identity_rejects_details_from_another_asset_type() -> None:
    """A versioned catalog row may not pair an asset type with foreign details."""
    with pytest.raises(ValidationError, match="details do not match asset type"):
        InstrumentIdentity(
            **_identity_kwargs(asset_type="bond", identity_level="PRODUCT"),
            details=FundIdentityDetails(
                fund_identity_kind="LISTING",
                fund_id="fund",
                share_class_id="share-class",
            ),
        )


@pytest.mark.parametrize(
    ("kwargs", "details", "message"),
    [
        (
            _identity_kwargs(asset_type="bond", identity_level="PRODUCT", venue=None),
            BondIdentityDetails(bond_identity_kind="ISSUE", issuer_id="issuer"),
            "bond ISSUE requires ASSET",
        ),
        (
            _identity_kwargs(asset_type="bond", identity_level="PRODUCT", venue=None),
            BondIdentityDetails(bond_identity_kind="LISTING", issuer_id="issuer"),
            "bond LISTING requires venue",
        ),
        (
            _identity_kwargs(asset_type="fund", identity_level="PRODUCT", venue=None),
            FundIdentityDetails(
                fund_identity_kind="LISTING",
                fund_id="fund",
                share_class_id="share-class",
            ),
            "fund LISTING requires venue",
        ),
        (
            _identity_kwargs(asset_type="fund", identity_level="PRODUCT", venue=None),
            FundIdentityDetails(
                fund_identity_kind="SHARE_CLASS",
                fund_id="fund",
                share_class_id="share-class",
            ),
            "fund SHARE_CLASS requires dealing channel, cutoffs and nav calendar",
        ),
        (
            _identity_kwargs(asset_type="futures", identity_level="CONTRACT"),
            FuturesIdentityDetails(
                product_code="IF",
                contract_month="2609",
                trading_calendar_id="CFFEX",
            ),
            "futures CONTRACT requires expiry_at and contract_multiplier",
        ),
        (
            _identity_kwargs(asset_type="fx", identity_level="ASSET", venue="OTC"),
            FxIdentityDetails(
                base_currency="EUR",
                quote_currency="USD",
                settlement_type="SPOT",
                calendar_id="FX",
                price_convention="EUR_PER_USD",
            ),
            "fx ASSET must not bind venue",
        ),
        (
            _identity_kwargs(asset_type="fx", identity_level="CONTRACT", venue="OTC"),
            FxIdentityDetails(
                base_currency="EUR",
                quote_currency="USD",
                settlement_type="FORWARD",
                settlement_currency="USD",
                calendar_id="FX",
                price_convention="EUR_PER_USD",
            ),
            "fx CONTRACT requires value_date or expiry_at",
        ),
        (
            _identity_kwargs(asset_type="crypto", identity_level="CONTRACT"),
            CryptoProductIdentityDetails(
                base_asset_id="BTC",
                quote_asset_id="USDT",
                market_type="SPOT",
                linear_or_inverse="NOT_APPLICABLE",
            ),
            "crypto SPOT/PERPETUAL requires PRODUCT identity level",
        ),
        (
            _identity_kwargs(asset_type="crypto", identity_level="PRODUCT"),
            CryptoProductIdentityDetails(
                base_asset_id="BTC",
                quote_asset_id="USDT",
                market_type="DELIVERY_FUTURE",
                linear_or_inverse="LINEAR",
                expiry_at=datetime(2026, 12, 18, tzinfo=timezone.utc),
            ),
            "crypto DELIVERY_FUTURE requires CONTRACT identity level",
        ),
    ],
)
def test_identity_rejects_invalid_asset_specific_identity_contract(
    kwargs: dict[str, object], details: object, message: str
) -> None:
    """Asset-specific level and contract fields are authoritative, not advisory."""
    with pytest.raises(ValidationError, match=message):
        InstrumentIdentity(**kwargs, details=details)


def test_identity_accepts_a_complete_futures_contract() -> None:
    """A complete exact contract remains a valid analysis identity."""
    identity = InstrumentIdentity(
        **_identity_kwargs(asset_type="futures", identity_level="CONTRACT", venue="CFFEX"),
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
            contract_multiplier=Decimal("300"),
            trading_calendar_id="CFFEX",
        ),
    )

    assert identity.identity_level == "CONTRACT"


def test_identity_accepts_an_unbound_fx_reference_pair() -> None:
    """An ASSET-level FX reference has no venue and remains non-executable."""
    identity = InstrumentIdentity(
        **_identity_kwargs(asset_type="fx", identity_level="ASSET", venue=None),
        details=FxIdentityDetails(
            base_currency="EUR",
            quote_currency="USD",
            settlement_type="SPOT",
            calendar_id="FX",
            price_convention="EUR_PER_USD",
        ),
    )

    assert identity.identity_level == "ASSET"


def test_identity_accepts_a_complete_open_end_fund_share_class() -> None:
    """Open-end fund identities freeze their channel, cutoffs and NAV calendar."""
    identity = InstrumentIdentity(
        **_identity_kwargs(asset_type="fund", identity_level="PRODUCT", venue=None),
        details=FundIdentityDetails(
            fund_identity_kind="SHARE_CLASS",
            fund_id="fund",
            share_class_id="a-class",
            dealing_frequency="DAILY",
            dealing_channel="DIRECT",
            subscription_cutoff=time(15, 0),
            redemption_cutoff=time(15, 0),
            nav_calendar_id="CN_FUND",
        ),
    )

    assert identity.details.fund_identity_kind == "SHARE_CLASS"


@pytest.mark.asyncio
async def test_resolver_creates_a_versioned_exact_futures_contract_identity() -> None:
    resolver = InstrumentResolver(
        _FakeMarketInstruments(
            [
                {
                    "asset_type": "futures",
                    "symbol": "IF2609",
                    "name": "沪深300股指期货2609",
                    "market": "CFFEX",
                    "source_table": "FUTURES_DAILY_MARKET",
                    "asset_research_identity": {
                        "asset_type": "futures",
                        "identity_level": "CONTRACT",
                        "canonical_id": "futures:CFFEX:IF2609:CNY",
                        "display_symbol": "IF2609",
                        "name": "沪深300股指期货2609",
                        "venue": "CFFEX",
                        "currency": "CNY",
                        "timezone": "Asia/Shanghai",
                        "identifier_type": "CONTRACT_CODE",
                        "identifier_value": "IF2609",
                        "product_type": "FUTURE",
                        "metadata_version": "licensed-futures-master:v1",
                        "details": {
                            "kind": "FUTURES",
                            "product_code": "IF",
                            "contract_month": "2609",
                            "underlying_id": "index:CSI300:CNY",
                            "expiry_at": "2026-09-18T07:15:00+00:00",
                            "contract_multiplier": "300",
                            "trading_calendar_id": "CFFEX",
                        },
                    },
                }
            ]
        )
    )

    identity = await resolver.resolve(
        InstrumentResolveRequest(asset_type="futures", query="if2609", venue="CFFEX")
    )

    assert identity.canonical_id == "futures:CFFEX:IF2609:CNY"
    assert identity.identity_level == "CONTRACT"
    assert identity.details.kind == "FUTURES"
    assert identity.metadata_version == "licensed-futures-master:v1"
    assert identity.details.contract_multiplier == Decimal("300")


@pytest.mark.asyncio
async def test_resolver_honors_requested_identity_level_without_reinterpreting_a_contract() -> None:
    item = {
        "asset_type": "futures",
        "symbol": "IF2609",
        "name": "沪深300股指期货2609",
        "market": "CFFEX",
        "asset_research_identity": {
            "asset_type": "futures",
            "identity_level": "CONTRACT",
            "canonical_id": "futures:CFFEX:IF2609:CNY",
            "display_symbol": "IF2609",
            "name": "沪深300股指期货2609",
            "venue": "CFFEX",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "CONTRACT_CODE",
            "identifier_value": "IF2609",
            "product_type": "FUTURE",
            "metadata_version": "licensed-futures-master:v1",
                    "details": {
                        "kind": "FUTURES",
                        "product_code": "IF",
                        "contract_month": "2609",
                        "expiry_at": "2026-09-18T07:15:00+00:00",
                        "contract_multiplier": "300",
                        "trading_calendar_id": "CFFEX",
                    },
        },
    }
    resolver = InstrumentResolver(_FakeMarketInstruments([item]))

    assert await resolver.search(
        asset_type="futures",
        query="IF2609",
        identity_level="PRODUCT",
        limit=20,
    ) == []
    with pytest.raises(InstrumentResolutionError, match="INSTRUMENT_UNSUPPORTED"):
        await resolver.resolve(
            InstrumentResolveRequest(
                asset_type="futures",
                query="IF2609",
                venue="CFFEX",
                identity_level="PRODUCT",
            )
        )


@pytest.mark.asyncio
async def test_resolver_honors_an_explicit_catalog_candidate_canonical_id() -> None:
    """A UI-selected catalog row must not be replaced by a same-code peer."""
    first = {
        "asset_type": "futures",
        "symbol": "IF2609",
        "name": "沪深300股指期货2609（主板）",
        "market": "CFFEX",
        "canonical_id": "futures:CFFEX:IF2609:main:CNY",
        "asset_research_identity": {
            "asset_type": "futures",
            "identity_level": "CONTRACT",
            "canonical_id": "futures:CFFEX:IF2609:main:CNY",
            "display_symbol": "IF2609",
            "name": "沪深300股指期货2609（主板）",
            "venue": "CFFEX",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "identifier_type": "CONTRACT_CODE",
            "identifier_value": "IF2609",
            "product_type": "FUTURE",
            "metadata_version": "licensed-futures-master:v1",
            "details": {
                "kind": "FUTURES",
                "product_code": "IF",
                "contract_month": "2609",
                "expiry_at": "2026-09-18T07:15:00+00:00",
                "contract_multiplier": "300",
                "trading_calendar_id": "CFFEX",
            },
        },
    }
    second = {
        **first,
        "name": "沪深300股指期货2609（测试）",
        "canonical_id": "futures:CFFEX:IF2609:test:CNY",
        "asset_research_identity": {
            **first["asset_research_identity"],
            "canonical_id": "futures:CFFEX:IF2609:test:CNY",
            "name": "沪深300股指期货2609（测试）",
        },
    }
    resolver = InstrumentResolver(_FakeMarketInstruments([first, second]))

    identity = await resolver.resolve(
        InstrumentResolveRequest(
            asset_type="futures",
            query="IF2609",
            venue="CFFEX",
            canonical_id="futures:CFFEX:IF2609:test:CNY",
            identity_level="CONTRACT",
        )
    )

    assert identity.canonical_id == "futures:CFFEX:IF2609:test:CNY"
    assert identity.name == "沪深300股指期货2609（测试）"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_type", "symbol", "market"),
    [
        ("bond", "113000", "XSHG"),
        ("fund", "510300", "XSHG"),
        ("futures", "IF2609", "CFFEX"),
        ("fx", "USD/CNH", "OTC"),
        ("crypto", "BTC/USDT", "BINANCE"),
    ],
)
async def test_resolver_rejects_candidates_without_versioned_asset_master_identity(
    asset_type: str, symbol: str, market: str
) -> None:
    """A display code alone must not cause the resolver to invent master data."""
    resolver = InstrumentResolver(
        _FakeMarketInstruments(
            [
                {
                    "asset_type": asset_type,
                    "symbol": symbol,
                    "name": symbol,
                    "market": market,
                }
            ]
        )
    )

    with pytest.raises(InstrumentResolutionError, match="INSTRUMENT_UNSUPPORTED"):
        await resolver.resolve(
            InstrumentResolveRequest(asset_type=asset_type, query=symbol, venue=market)
        )


@pytest.mark.asyncio
async def test_resolver_uses_authoritative_crypto_product_identity_without_reparsing_quote_asset() -> None:
    resolver = InstrumentResolver(
        _FakeMarketInstruments(
            [
                {
                    "asset_type": "crypto",
                    "symbol": "BTC/USDT",
                    "name": "BTC/USDT spot",
                    "market": "BINANCE",
                    "asset_research_identity": {
                        "asset_type": "crypto",
                        "identity_level": "PRODUCT",
                        "canonical_id": "crypto:binance:BTC-USDT:spot",
                        "display_symbol": "BTC/USDT",
                        "name": "BTC/USDT spot",
                        "venue": "BINANCE",
                        "currency": "USDT",
                        "timezone": "UTC",
                        "identifier_type": "VENUE_PAIR",
                        "identifier_value": "BTC/USDT",
                        "product_type": "SPOT",
                        "metadata_version": "licensed-crypto-master:v1",
                        "details": {
                            "kind": "CRYPTO_PRODUCT",
                            "base_asset_id": "BTC",
                            "quote_asset_id": "USDT",
                            "settlement_asset_id": "USDT",
                            "market_type": "SPOT",
                            "linear_or_inverse": "NOT_APPLICABLE",
                        },
                    },
                }
            ]
        )
    )

    identity = await resolver.resolve(
        InstrumentResolveRequest(asset_type="crypto", query="BTC/USDT", venue="BINANCE")
    )

    assert identity.details.base_asset_id == "BTC"
    assert identity.details.quote_asset_id == "USDT"
    assert identity.metadata_version == "licensed-crypto-master:v1"


@pytest.mark.asyncio
async def test_resolver_rejects_an_ambiguous_prefix_instead_of_selecting_a_recent_sample() -> None:
    resolver = InstrumentResolver(
        _FakeMarketInstruments(
            [
                {"asset_type": "futures", "symbol": "IF2606", "name": "IF2606", "market": "CFFEX"},
                {"asset_type": "futures", "symbol": "IF2609", "name": "IF2609", "market": "CFFEX"},
            ]
        )
    )

    with pytest.raises(InstrumentResolutionError, match="INSTRUMENT_AMBIGUOUS"):
        await resolver.resolve(InstrumentResolveRequest(asset_type="futures", query="IF"))


@pytest.mark.asyncio
async def test_resolver_rejects_an_under_specified_option_instead_of_inventing_contract_terms() -> None:
    """A quote symbol is not enough to identify an option contract safely."""
    resolver = InstrumentResolver(
        _FakeMarketInstruments(
            [
                {
                    "asset_type": "option",
                    "symbol": "510050C2609M03000",
                    "name": "50ETF 2026年9月3000认购",
                    "market": "XSHG",
                    "expiry_at": "2026-09-23T07:00:00+00:00",
                    "strike": "3.000",
                    "option_right": "CALL",
                }
            ]
        )
    )

    with pytest.raises(InstrumentResolutionError, match="INSTRUMENT_UNSUPPORTED"):
        await resolver.resolve(
            InstrumentResolveRequest(
                asset_type="option",
                query="510050C2609M03000",
                venue="XSHG",
            )
        )


@pytest.mark.asyncio
async def test_resolver_freezes_all_required_exact_option_contract_terms() -> None:
    resolver = InstrumentResolver(
        _FakeMarketInstruments(
            [
                {
                    "asset_type": "option",
                    "symbol": "510050C2609M03000",
                    "name": "50ETF 2026年9月3000认购",
                    "market": "XSHG",
                    "source_table": "LICENSED_OPTION_MASTER",
                    "option_contract_id": "510050C2609M03000",
                    "underlying_instrument_id": "fund:XSHG:510050:CNY",
                    "underlying_contract_id": "fund:XSHG:510050:CNY",
                    "expiry_at": "2026-09-23T07:00:00+00:00",
                    "last_trade_at": "2026-09-23T07:00:00+00:00",
                    "strike": "3.000",
                    "option_right": "CALL",
                    "exercise_style": "EUROPEAN",
                    "settlement_type": "PHYSICAL",
                    "deliverable": "10000 units of 510050",
                    "contract_multiplier": "10000",
                    "quote_unit": "CNY_PER_UNIT",
                    "tick_size": "0.0001",
                    "trading_calendar_id": "XSHG",
                    "automatic_exercise_rule": "EXERCISE_IF_ITM",
                    "position_limit_rule": "XSHG_ETF_OPTION_V1",
                    "margin_rule_version": "XSHG_ETF_OPTION_MARGIN_V1",
                    "asset_research_identity": {
                        "asset_type": "option",
                        "identity_level": "CONTRACT",
                        "canonical_id": "option:XSHG:510050C2609M03000:CALL:2026-09-23:3.000:CNY",
                        "display_symbol": "510050C2609M03000",
                        "name": "50ETF 2026年9月3000认购",
                        "venue": "XSHG",
                        "currency": "CNY",
                        "timezone": "Asia/Shanghai",
                        "identifier_type": "OPTION_CONTRACT_CODE",
                        "identifier_value": "510050C2609M03000",
                        "product_type": "OPTION",
                        "metadata_version": "licensed-option-master:v1",
                        "details": {
                            "kind": "OPTION",
                            "option_contract_id": "510050C2609M03000",
                            "exchange": "XSHG",
                            "underlying_instrument_id": "fund:XSHG:510050:CNY",
                            "underlying_contract_id": "fund:XSHG:510050:CNY",
                            "expiry_at": "2026-09-23T07:00:00+00:00",
                            "last_trade_at": "2026-09-23T07:00:00+00:00",
                            "strike": "3.000",
                            "option_right": "CALL",
                            "exercise_style": "EUROPEAN",
                            "settlement_type": "PHYSICAL",
                            "deliverable": "10000 units of 510050",
                            "contract_multiplier": "10000",
                            "quote_unit": "CNY_PER_UNIT",
                            "tick_size": "0.0001",
                            "trading_calendar_id": "XSHG",
                            "automatic_exercise_rule": "EXERCISE_IF_ITM",
                            "position_limit_rule": "XSHG_ETF_OPTION_V1",
                            "margin_rule_version": "XSHG_ETF_OPTION_MARGIN_V1",
                        },
                    },
                }
            ]
        )
    )

    identity = await resolver.resolve(
        InstrumentResolveRequest(
            asset_type="option",
            query="510050C2609M03000",
            venue="XSHG",
        )
    )

    assert identity.identity_level == "CONTRACT"
    assert identity.details.option_contract_id == "510050C2609M03000"
    assert identity.details.exchange == "XSHG"
    assert identity.details.underlying_instrument_id == "fund:XSHG:510050:CNY"
    assert identity.details.underlying_contract_id == "fund:XSHG:510050:CNY"
    assert identity.details.last_trade_at.isoformat() == "2026-09-23T07:00:00+00:00"
    assert identity.details.deliverable == "10000 units of 510050"
    assert identity.details.tick_size == Decimal("0.0001")
