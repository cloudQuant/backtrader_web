"""The research adapter must reject provider fallbacks that point at another asset."""

import json
from datetime import datetime, timezone

import pytest

from app.schemas.asset_research import (
    FuturesIdentityDetails,
    InstrumentIdentity,
    StockIdentityDetails,
)
from app.services.asset_research.data import (
    DEFAULT_ASSET_RESEARCH_SOURCE_ID,
    AssetResearchDataError,
    StrictMarketDataAdapter,
)
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


class _FallbackingMarketService:
    async def lookup(self, **_: object) -> dict[str, object]:
        return {
            "asset_type": "futures",
            "symbol": "RB2609",
            "market": "CFFEX",
            "snapshot": {"price": 3210},
            "history": {"rows": [{"date": "2026-08-01", "close": 3210}]},
        }


class _PITMarketService:
    def __init__(self, *, include_availability: bool) -> None:
        self._include_availability = include_availability

    async def lookup(self, **_: object) -> dict[str, object]:
        observations: dict[str, object] = {}
        if self._include_availability:
            observations["snapshot.price"] = {
                "source_id": "pit-fixture",
                "observed_at": "2026-08-01T08:00:00+00:00",
                "published_at": "2026-08-01T08:01:00+00:00",
                "available_at": "2026-08-01T08:02:00+00:00",
                "license_tag": "APPROVED",
            }
        return {
            "asset_type": "futures",
            "symbol": "IF2609",
            "market": "CFFEX",
            "provider": "pit-fixture",
            "snapshot": {"price": 3210},
            "history": {"rows": []},
            "observations": observations,
        }


class _StockLookupMustNotRun:
    async def lookup(self, **_: object) -> dict[str, object]:
        raise AssertionError("stock identity must be rejected before market lookup")


class _WarehouseLookup:
    """Record the adapter's refresh choice without making a network request."""

    def __init__(self, *, source_id: str = DEFAULT_ASSET_RESEARCH_SOURCE_ID) -> None:
        self.source_id = source_id
        self.refresh_online: bool | None = None

    async def lookup(self, **kwargs: object) -> dict[str, object]:
        self.refresh_online = bool(kwargs["refresh_online"])
        return {
            "asset_type": "futures",
            "symbol": "IF2609",
            "market": "CFFEX",
            "source_id": self.source_id,
            "snapshot": {"price": 3210},
            "history": {"rows": []},
            "observations": {
                "snapshot.price": {
                    "available_at": "2026-08-01T08:00:00+00:00",
                }
            },
        }


class _DomainFactsWarehouseLookup:
    """Return one approved-source payload with non-stock domain facts."""

    async def lookup(self, **_: object) -> dict[str, object]:
        return {
            "asset_type": "futures",
            "symbol": "IF2609",
            "market": "CFFEX",
            "source_id": DEFAULT_ASSET_RESEARCH_SOURCE_ID,
            "snapshot": {"price": 3210},
            "futures": {
                "contract_calendar": "CFFEX",
                "term_structure_complete": False,
            },
            "history": {"rows": []},
            "observations": {
                "snapshot.price": {"available_at": "2026-08-01T08:00:00+00:00"},
                "futures.contract_calendar": {"available_at": "2026-08-01T08:00:00+00:00"},
                "futures.term_structure_complete": {"available_at": "2026-08-01T08:00:00+00:00"},
            },
        }


class _SecretBearingWarehouseLookup:
    """Simulate a malformed provider response which accidentally carries credentials."""

    async def lookup(self, **_: object) -> dict[str, object]:
        return {
            "asset_type": "futures",
            "symbol": "IF2609",
            "market": "CFFEX",
            "source_id": DEFAULT_ASSET_RESEARCH_SOURCE_ID,
            "snapshot": {"price": 3210, "api_key": "snapshot-secret"},
            "indicators": {"momentum": 0.2, "authorization": "Bearer indicator-secret"},
            "futures": {
                "contract_calendar": "CFFEX",
                "client_secret": "domain-secret",
            },
            "history": {
                "rows": [
                    {
                        "date": "2026-08-01",
                        "close": 3210,
                        "password": "history-secret",
                    }
                ]
            },
            "warnings": ["upstream api_key=warning-secret"],
            "observations": {
                "snapshot.price": {"available_at": "2026-08-01T08:00:00+00:00"},
                "snapshot.api_key": {"available_at": "2026-08-01T08:00:00+00:00"},
                "indicators.momentum": {"available_at": "2026-08-01T08:00:00+00:00"},
                "indicators.authorization": {"available_at": "2026-08-01T08:00:00+00:00"},
                "futures.contract_calendar": {"available_at": "2026-08-01T08:00:00+00:00"},
                "futures.client_secret": {"available_at": "2026-08-01T08:00:00+00:00"},
            },
        }


def _futures_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="test-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


@pytest.mark.asyncio
async def test_strict_adapter_rejects_a_provider_fallback_for_another_contract() -> None:
    identity = InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="test-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )

    with pytest.raises(AssetResearchDataError, match="INSTRUMENT_UNSUPPORTED"):
        await StrictMarketDataAdapter(_FallbackingMarketService()).collect(
            identity, cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc)
        )


@pytest.mark.asyncio
async def test_strict_adapter_rejects_stock_identity_before_market_lookup() -> None:
    """The non-stock research adapter must not silently become a stock fallback path."""
    identity = InstrumentIdentity(
        asset_type="stock",
        identity_level="PRODUCT",
        canonical_id="stock:CN:600519:CNY",
        display_symbol="600519",
        name="贵州茅台",
        venue="CN",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="LISTING_CODE",
        identifier_value="600519",
        product_type="STOCK",
        metadata_version="test-v1",
        details=StockIdentityDetails(exchange_symbol="600519.SH"),
    )

    with pytest.raises(AssetResearchDataError, match="INSTRUMENT_UNSUPPORTED"):
        await StrictMarketDataAdapter(_StockLookupMustNotRun()).collect(
            identity, cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc)
        )


@pytest.mark.asyncio
async def test_strict_adapter_requires_field_level_availability_for_pit_replay() -> None:
    """Retrieval time must never be substituted for a field's availability time."""
    identity = InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="test-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )
    cutoff_at = datetime(2026, 8, 1, 9, tzinfo=timezone.utc)

    verified = await StrictMarketDataAdapter(_PITMarketService(include_availability=True)).collect(
        identity,
        cutoff_at=cutoff_at,
    )
    unverified = await StrictMarketDataAdapter(
        _PITMarketService(include_availability=False)
    ).collect(identity, cutoff_at=cutoff_at)

    assert verified.source_manifest["point_in_time_status"] == "VERIFIED"
    assert verified.observations["snapshot.price"].available_at == datetime(
        2026, 8, 1, 8, 2, tzinfo=timezone.utc
    )
    assert unverified.source_manifest["point_in_time_status"] == "UNVERIFIED"
    assert unverified.observations["snapshot.price"].available_at is None
    quality = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures").assess_quality(unverified)
    assert quality.status == "REJECTED"
    assert "COMMON.PIT_UNVERIFIED" in quality.reason_codes


@pytest.mark.asyncio
async def test_default_research_adapter_never_triggers_an_online_refresh() -> None:
    """The generic warehouse bridge must not contact an unapproved upstream."""
    market_data = _WarehouseLookup()

    snapshot = await StrictMarketDataAdapter(
        market_data,
        declared_source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
    ).collect(_futures_identity(), cutoff_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc))

    assert market_data.refresh_online is False
    assert snapshot.source_manifest["source_id"] == DEFAULT_ASSET_RESEARCH_SOURCE_ID


@pytest.mark.asyncio
async def test_declared_source_adapter_rejects_a_response_from_a_different_source() -> None:
    """A provider label cannot switch after the capability was checked."""
    market_data = _WarehouseLookup(source_id="different-warehouse")

    with pytest.raises(AssetResearchDataError, match="SOURCE_UNAVAILABLE"):
        await StrictMarketDataAdapter(
            market_data,
            declared_source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
        ).collect(_futures_identity(), cutoff_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_strict_adapter_preserves_matching_asset_domain_facts_with_provenance() -> None:
    """Approved source-specific facts must reach the matching plugin unchanged."""
    snapshot = await StrictMarketDataAdapter(
        _DomainFactsWarehouseLookup(),
        declared_source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
    ).collect(_futures_identity(), cutoff_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc))

    assert snapshot.raw_fields["futures"] == {
        "contract_calendar": "CFFEX",
        "term_structure_complete": False,
    }
    assert snapshot.observations["futures.contract_calendar"].available_at == datetime(
        2026, 8, 1, 8, tzinfo=timezone.utc
    )
    assert snapshot.observations["futures.term_structure_complete"].value is False
    assert snapshot.source_manifest["point_in_time_status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_strict_adapter_redacts_provider_credentials_before_building_a_raw_snapshot() -> None:
    """Credentials must never become a persisted raw snapshot or provenance value."""
    snapshot = await StrictMarketDataAdapter(
        _SecretBearingWarehouseLookup(),
        declared_source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
    ).collect(_futures_identity(), cutoff_at=datetime(2026, 8, 1, 9, tzinfo=timezone.utc))

    serialized = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)

    for secret in (
        "snapshot-secret",
        "indicator-secret",
        "domain-secret",
        "history-secret",
        "warning-secret",
    ):
        assert secret not in serialized
    assert snapshot.raw_fields["snapshot"]["api_key"] == "[REDACTED]"
    assert snapshot.observations["indicators.authorization"].value == "[REDACTED]"
    assert snapshot.history_rows[0]["password"] == "[REDACTED]"
    assert snapshot.raw_fields["snapshot"]["price"] == 3210
    assert snapshot.raw_fields["futures"]["contract_calendar"] == "CFFEX"
