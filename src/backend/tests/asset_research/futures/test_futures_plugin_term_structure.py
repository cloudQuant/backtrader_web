"""Futures plugin contracts for contract-level basis computation."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity, RawAssetSnapshot
from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def _snapshot() -> RawAssetSnapshot:
    return RawAssetSnapshot(
        identity=InstrumentIdentity(
            asset_type="futures",
            identity_level="CONTRACT",
            canonical_id="futures:fixture:oil:202604",
            display_symbol="OIL2404",
            name="Fixture oil future",
            venue="FIXTURE",
            currency="USD",
            timezone="UTC",
            identifier_type="CONTRACT_CODE",
            identifier_value="OIL2404",
            product_type="FUTURE",
            metadata_version="fixture-v1",
            details=FuturesIdentityDetails(
                product_code="OIL",
                contract_month="202604",
                expiry_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                contract_multiplier=Decimal("1000"),
                trading_calendar_id="FIXTURE",
            ),
        ),
        cutoff_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        raw_fields={
            "snapshot": {"price": 102.0, "bid": 101.9, "ask": 102.1},
            "futures": {
                "contract_calendar": "FIXTURE",
                "contract_terms": "fixture-terms",
                "term_structure": {
                    "as_of": "2026-01-01",
                    "expiry_date": "2026-04-01",
                    "spot_price": 100.0,
                    "futures_price": 102.0,
                    "quote_unit": "USD_PER_BARREL",
                    "spot_quality": "WTI_CUSHING",
                    "futures_quality": "WTI_CUSHING",
                    "spot_location": "CUSHING",
                    "futures_location": "CUSHING",
                    "tax_basis": "EX_TAX",
                },
            },
        },
        history_rows=[
            {"date": "2025-12-31", "close": 101.0},
            {"date": "2026-01-01", "close": 102.0},
        ],
        source_manifest={
            "license_status": "APPROVED",
            "capabilities": ["price", "contract_calendar"],
        },
        license_tags=["APPROVED"],
        content_hash="d" * 64,
    )


def test_futures_plugin_derives_contract_basis_and_carry_from_a_frozen_comparable_curve() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures")
    raw_snapshot = _snapshot()
    eligible = plugin.promote_snapshot(raw_snapshot, plugin.assess_quality(raw_snapshot))

    assert eligible is not None
    features = plugin.compute_features(eligible)

    assert float(Decimal(str(features.values["basis"]))) == pytest.approx(2.0)
    assert float(Decimal(str(features.values["annualized_carry"]))) == pytest.approx(
        0.02 * 365 / 90
    )
    assert features.values["days_to_expiry"] == 90.0
    assert features.values["futures_term_structure_reason_code"] is None


def test_futures_report_details_expose_the_frozen_term_structure_result() -> None:
    plugin = DEFAULT_ASSET_RESEARCH_REGISTRY.get("futures")
    raw_snapshot = _snapshot()
    quality = plugin.assess_quality(raw_snapshot)
    eligible = plugin.promote_snapshot(raw_snapshot, quality)

    assert eligible is not None
    decision = plugin.make_decision(
        plugin.compute_features(eligible),
        quality,
        position_context="FLAT",
        horizon_code="20D",
        snapshot=raw_snapshot,
    )
    details = decision.asset_details

    assert float(details.basis or 0) == pytest.approx(2.0)
    assert float(details.annualized_carry or 0) == pytest.approx(0.02 * 365 / 90)
    assert details.term_structure_reason_code is None
