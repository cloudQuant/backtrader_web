"""Default registry for Iteration 191's independently governed asset plugins."""

from app.services.asset_research.plugins.base import ConfiguredAssetResearchPlugin
from app.services.asset_research.types import AssetResearchPluginRegistry

DEFAULT_ASSET_RESEARCH_REGISTRY = AssetResearchPluginRegistry(
    (
        ConfiguredAssetResearchPlugin(
            asset_type="bond",
            reason_codes=(
                "BOND.PRICE_IDENTITY_MISMATCH",
                "BOND.CURVE_MISSING",
                "BOND.PERPETUAL_MODEL_REQUIRED",
                "BOND.SPECIALIZED_MODEL_REQUIRED",
                "BOND.VALUATION_NOT_EXECUTABLE",
            ),
        ),
        ConfiguredAssetResearchPlugin(
            asset_type="fund",
            reason_codes=(
                "FUND.OFFICIAL_NAV_MISSING",
                "FUND.BENCHMARK_MISSING",
                "FUND.MANAGEMENT_EVIDENCE_LOW",
                "FUND.SPECIALIZED_MODEL_REQUIRED",
            ),
        ),
        ConfiguredAssetResearchPlugin(
            asset_type="futures",
            reason_codes=(
                "FUTURES.CONTINUOUS_PRICE_NOT_TRADABLE",
                "FUTURES.NEAR_EXPIRY",
                "FUTURES.TERM_STRUCTURE_INCOMPLETE",
            ),
        ),
        ConfiguredAssetResearchPlugin(
            asset_type="option",
            reason_codes=(
                "OPTION.NAKED_SHORT_BLOCKED",
                "OPTION.CHAIN_INCOMPLETE",
                "OPTION.SURFACE_COVERAGE_INSUFFICIENT",
            ),
        ),
        ConfiguredAssetResearchPlugin(
            asset_type="fx",
            reason_codes=("FX.PRICE_CONVENTION_UNKNOWN", "FX.REFERENCE_ONLY", "FX.MACRO_MISSING"),
        ),
        ConfiguredAssetResearchPlugin(
            asset_type="crypto",
            reason_codes=(
                "CRYPTO.REGION_RESTRICTED",
                "CRYPTO.VENUE_UNVERIFIED",
                "CRYPTO.ONCHAIN_UNSUPPORTED",
            ),
        ),
    )
)
