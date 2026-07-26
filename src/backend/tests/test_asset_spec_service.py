"""Boundary tests for normalized asset specifications."""

from __future__ import annotations

import pytest

from app.services.asset_spec_service import AssetSpecService, infer_asset_type

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("RB0", "futures"),
        ("000001.SZ", "stock"),
        ("BTCUSDT", "crypto"),
        ("EURUSD", "fx"),
    ],
)
async def test_infer_asset_type_covers_supported_symbol_boundaries(symbol: str, expected: str):
    assert infer_asset_type(symbol) == expected


async def test_asset_spec_service_resolves_and_upserts_futures_contract_metadata():
    service = AssetSpecService()

    resolved = await service.get_or_create(symbol="RB0")
    updated = await service.upsert(resolved.model_copy(update={"commission_rate": 0.0002}))
    loaded = await service.get(symbol="RB0", asset_type="futures", exchange="SHFE")

    assert resolved.asset_type == "futures"
    assert resolved.contract_multiplier == 10.0
    assert resolved.margin_rate is not None and resolved.margin_rate > 0
    assert updated.commission_rate == 0.0002
    assert loaded is not None and loaded.id == resolved.id
