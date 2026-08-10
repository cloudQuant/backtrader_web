"""Contract tests for the multi-asset research plugin registry."""

from app.services.asset_research.registry import DEFAULT_ASSET_RESEARCH_REGISTRY


def test_default_registry_exposes_each_supported_non_stock_asset() -> None:
    """Every Iteration 191 asset type has exactly one independently addressable plugin."""
    assert DEFAULT_ASSET_RESEARCH_REGISTRY.asset_types == (
        "bond",
        "fund",
        "futures",
        "option",
        "fx",
        "crypto",
    )
    assert tuple(plugin.asset_type for plugin in DEFAULT_ASSET_RESEARCH_REGISTRY.plugins()) == (
        "bond",
        "fund",
        "futures",
        "option",
        "fx",
        "crypto",
    )
