"""Small, dependency-free contracts shared by asset research plugins."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from app.schemas.asset_research import (
    EligibleAssetSnapshot,
    FeatureSet,
    OutcomeEvaluation,
    QualityAssessment,
    RawAssetSnapshot,
    ReportSection,
    ResearchDecision,
)

AssetResearchAssetType = Literal["bond", "fund", "futures", "option", "fx", "crypto"]


class AssetResearchPlugin(Protocol):
    """Full deterministic plugin contract used by the orchestration boundary."""

    asset_type: AssetResearchAssetType
    reason_codes: tuple[str, ...]

    def assess_quality(self, snapshot: RawAssetSnapshot) -> QualityAssessment: ...

    def promote_snapshot(
        self, snapshot: RawAssetSnapshot, quality: QualityAssessment
    ) -> EligibleAssetSnapshot | None: ...

    def compute_features(self, snapshot: EligibleAssetSnapshot) -> FeatureSet: ...

    def make_decision(
        self,
        features: FeatureSet | None,
        quality: QualityAssessment,
        *,
        position_context: str,
        horizon_code: str,
        snapshot: RawAssetSnapshot,
    ) -> ResearchDecision: ...

    def build_report_sections(
        self, snapshot: RawAssetSnapshot, published_decision: ResearchDecision
    ) -> list[ReportSection]: ...

    def score_outcome(
        self,
        *,
        decision: ResearchDecision,
        horizon_code: str,
        as_of: datetime,
        snapshot: RawAssetSnapshot,
    ) -> list[OutcomeEvaluation]: ...


class AssetResearchPluginRegistry:
    """Register one and only one plugin for every public asset type."""

    def __init__(self, plugins: tuple[AssetResearchPlugin, ...]) -> None:
        plugin_types = tuple(plugin.asset_type for plugin in plugins)
        if len(set(plugin_types)) != len(plugin_types):
            raise ValueError("asset_research_duplicate_plugin")
        self._plugins = plugins
        self._by_asset_type: dict[str, AssetResearchPlugin] = {
            plugin.asset_type: plugin for plugin in plugins
        }

    @property
    def asset_types(self) -> tuple[AssetResearchAssetType, ...]:
        """Return plugin types in their user-facing navigation order."""
        return tuple(plugin.asset_type for plugin in self._plugins)

    def plugins(self) -> tuple[AssetResearchPlugin, ...]:
        """Return all registered plugins in deterministic order."""
        return self._plugins

    def get(self, asset_type: str) -> AssetResearchPlugin:
        """Return the single plugin that owns a validated persisted asset type."""
        try:
            return self._by_asset_type[asset_type]
        except KeyError as exc:
            raise ValueError("asset_research_unsupported_asset_type") from exc
