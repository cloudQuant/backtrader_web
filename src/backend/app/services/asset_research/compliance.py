"""Fail-closed jurisdiction policy for public multi-asset research conclusions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.config import get_settings

_MAINLAND_CHINA_JURISDICTIONS = frozenset({"CN", "CHINA", "MAINLAND_CHINA"})
_DIRECTIONAL_ASSET_TYPES = frozenset({"fx", "crypto"})


def _normalize_jurisdiction(value: object) -> str:
    """Normalize a configured jurisdiction without accepting a client value."""
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


@dataclass(frozen=True, slots=True)
class AssetResearchCompliancePolicy:
    """Resolve the server-owned jurisdiction gate for sensitive asset classes.

    The policy intentionally has no request parameter: a browser cannot claim
    another region to obtain a public FX or crypto direction. Mainland China is
    always research-only. Elsewhere, both an explicit operational switch and
    the frozen source jurisdiction declaration are required.
    """

    operator_jurisdiction: str
    directional_fx_crypto_enabled: bool

    @classmethod
    def from_runtime_settings(cls) -> AssetResearchCompliancePolicy:
        """Build the immutable process-level policy from typed server settings."""
        settings = get_settings()
        return cls(
            operator_jurisdiction=settings.ASSET_RESEARCH_OPERATOR_JURISDICTION,
            directional_fx_crypto_enabled=settings.ASSET_RESEARCH_DIRECTIONAL_FX_CRYPTO_ENABLED,
        )

    def is_region_restricted(
        self, *, asset_type: str, source_manifest: Mapping[str, object]
    ) -> bool:
        """Return whether the public conclusion must be region restricted."""
        if asset_type not in _DIRECTIONAL_ASSET_TYPES:
            return False
        operator_jurisdiction = _normalize_jurisdiction(self.operator_jurisdiction)
        if operator_jurisdiction in _MAINLAND_CHINA_JURISDICTIONS:
            return True
        if not self.directional_fx_crypto_enabled:
            return True
        allowed = self._source_jurisdictions(source_manifest)
        return not allowed or (
            operator_jurisdiction not in allowed and "GLOBAL" not in allowed
        )

    def frozen_context(self, *, source_manifest: Mapping[str, object]) -> dict[str, object]:
        """Return the policy facts that must participate in prediction identity."""
        return {
            "operator_jurisdiction": _normalize_jurisdiction(self.operator_jurisdiction),
            "directional_fx_crypto_enabled": self.directional_fx_crypto_enabled,
            "source_jurisdictions": sorted(self._source_jurisdictions(source_manifest)),
        }

    @staticmethod
    def _source_jurisdictions(source_manifest: Mapping[str, object]) -> set[str]:
        raw_jurisdictions = source_manifest.get("jurisdictions")
        if isinstance(raw_jurisdictions, str):
            allowed = {_normalize_jurisdiction(raw_jurisdictions)}
        elif isinstance(raw_jurisdictions, (list, tuple, set, frozenset)):
            allowed = {_normalize_jurisdiction(value) for value in raw_jurisdictions}
        else:
            allowed = set()
        allowed.discard("")
        return allowed
