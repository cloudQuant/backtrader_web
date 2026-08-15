"""Asset-specific public report outlines must not collapse to a generic memo."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.schemas.asset_research import (
    FuturesIdentityDetails,
    FuturesResearchDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
    ResearchDecision,
)
from app.services.asset_research.reports import asset_report_outline, build_asset_report_sections


@pytest.mark.parametrize(
    ("asset_type", "expected_count", "expected_title"),
    [
        ("bond", 14, "债券身份、市场和关键条款"),
        ("fund", 15, "基金身份、份额类别、类型和交易机制"),
        ("futures", 13, "观点、动作、置信度和资格"),
        ("option", 13, "精确合约身份和标的"),
        ("fx", 11, "产品身份、报价方向和结算"),
        ("crypto", 12, "资产、链、合约地址、场所和产品"),
    ],
)
def test_each_asset_has_the_required_public_report_chapters(
    asset_type: str, expected_count: int, expected_title: str
) -> None:
    """The frontend and exports need a stable, domain-specific chapter contract."""
    outline = asset_report_outline(asset_type)  # type: ignore[arg-type]

    assert len(outline) == expected_count
    assert outline[0][1] == expected_title
    assert len({section_id for section_id, _ in outline}) == expected_count
    # Some requirement documents embed the public recommendation in a more
    # specific first chapter (for example futures uses "观点、动作、置信度和资格").
    # The stable section ID, rather than a translated title, is the contract
    # that proves the published decision is represented.
    assert "public_decision" in {section_id for section_id, _ in outline}


def test_public_report_scalar_values_have_content_addressed_evidence_ids() -> None:
    """Every rendered public scalar must bind to its frozen snapshot, not just a chapter."""
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
        metadata_version="fixture-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )
    snapshot = RawAssetSnapshot(
        identity=identity,
        cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        raw_schema_version="fixture-v1",
        source_manifest={"source_id": "fixture-source", "license_status": "APPROVED"},
        content_hash="a" * 64,
    )
    decision = ResearchDecision(
        asset_type="futures",
        market_view="NEUTRAL",
        normalized_direction="NEUTRAL",
        position_context="FLAT",
        horizon_code="standard",
        quality_status="ELIGIBLE",
        asset_details=FuturesResearchDetails(
            contract_code="IF2609",
            days_to_expiry=48,
            basis=Decimal("12.5"),
            annualized_carry=Decimal("0.031"),
            margin_ratio=Decimal("0.12"),
        ),
    )

    sections = build_asset_report_sections(snapshot=snapshot, published_decision=decision)
    market_state = next(section for section in sections if section.section_id == "market_state")
    source_version = next(section for section in sections if section.section_id == "source_version")

    assert "annualized_carry=0.031（证据 ID：detail:" in market_state.markdown
    assert "margin_ratio=0.12（证据 ID：detail:" in market_state.markdown
    assert any(evidence_id.startswith("detail:") for evidence_id in market_state.evidence_ids)
    assert all(
        len(evidence_id.split(":", maxsplit=1)[1]) == 64
        for evidence_id in market_state.evidence_ids
    )
    assert any(
        evidence_id.startswith("source_snapshot:") for evidence_id in source_version.evidence_ids
    )
