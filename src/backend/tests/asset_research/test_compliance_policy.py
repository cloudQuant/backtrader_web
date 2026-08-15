"""Server-owned jurisdiction policy for public FX and crypto conclusions."""

from app.services.asset_research.compliance import AssetResearchCompliancePolicy


def test_mainland_china_never_publishes_fx_or_crypto_directional_advice() -> None:
    """A client request or a promoted record cannot bypass the China policy."""
    policy = AssetResearchCompliancePolicy(
        operator_jurisdiction="CN",
        directional_fx_crypto_enabled=True,
    )

    assert policy.is_region_restricted(asset_type="fx", source_manifest={"jurisdictions": ["CN"]})
    assert policy.is_region_restricted(
        asset_type="crypto", source_manifest={"jurisdictions": ["CN"]}
    )
    assert not policy.is_region_restricted(
        asset_type="bond", source_manifest={"jurisdictions": ["CN"]}
    )


def test_non_mainland_fx_crypto_need_explicit_switch_and_source_jurisdiction() -> None:
    """Unknown source scope remains closed even outside the mainland policy."""
    disabled = AssetResearchCompliancePolicy(
        operator_jurisdiction="US",
        directional_fx_crypto_enabled=False,
    )
    enabled = AssetResearchCompliancePolicy(
        operator_jurisdiction="US",
        directional_fx_crypto_enabled=True,
    )

    assert disabled.is_region_restricted(asset_type="fx", source_manifest={"jurisdictions": ["US"]})
    assert enabled.is_region_restricted(asset_type="crypto", source_manifest={})
    assert enabled.is_region_restricted(asset_type="fx", source_manifest={"jurisdictions": ["GB"]})
    assert not enabled.is_region_restricted(
        asset_type="crypto", source_manifest={"jurisdictions": ["US", "GB"]}
    )
    assert enabled.frozen_context(source_manifest={"jurisdictions": ["GB", "US"]}) == {
        "operator_jurisdiction": "US",
        "directional_fx_crypto_enabled": True,
        "source_jurisdictions": ["GB", "US"],
    }
