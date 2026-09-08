"""Deterministic scope evidence for the Iteration 197 market-data cutover.

The data-family registry says what the server currently declares.  The market
page and the compatibility API separately say which asset and period inputs a
user can select.  This module joins those three sources into one deliberately
*provisional* manifest.  It is not a provider-capability inventory and it does
not enable the strategy page.

The manifest has a hard dependency on a frozen Iteration 196 baseline.  A
missing or non-frozen baseline fails before an artifact is produced.  This is
intentional: an otherwise plausible list of 21 families must not be mistaken
for a valid 196/197 integration boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, get_args

from app.schemas.market_data_platform import (
    MarketDataAssetType,
    MarketDataFrequency,
    MarketDataQueryBundleRequest,
)
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    FAMILY_CONTRACT_VERSION,
)
from app.services.market_data.legacy_contract import _FREQUENCY_BY_LEGACY_PERIOD

SCOPE_MANIFEST_SCHEMA_VERSION = "market-data-scope-manifest-v1"
ITER196_BASELINE_SCHEMA_VERSION = "iter196-market-data-baseline-v1"
SCOPE_MANIFEST_STATUS = "provisional"
_CURRENT_FAMILY_COUNT = 21
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_REF_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SOURCE_FILES = (
    ("scope_manifest_generator", "src/backend/app/services/market_data/scope_manifest.py"),
    ("backend_contract_registry", "src/backend/app/services/market_data/dataset_contracts.py"),
    ("backend_query_schema", "src/backend/app/schemas/market_data_platform.py"),
    ("backend_legacy_contract", "src/backend/app/services/market_data/legacy_contract.py"),
    ("frontend_market_page", "src/frontend/src/views/data/useDataPage.ts"),
)
_BASELINE_KEYS = frozenset(
    {
        "schema_version",
        "iteration",
        "status",
        "baseline_ref",
        "baseline_sha256",
        "artifact_ref",
        "frozen_at",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "scope_id",
        "scope_status",
        "family_contract_version",
        "iter196_baseline",
        "source_refs",
        "input_surfaces",
        "strategy_page_production_status",
        "rows",
        "manifest_sha256",
    }
)
_REQUIRED_FRONTEND_V2_MARKERS = (
    "function readyRealtimeBarsFamilyFromQueryBundle(",
    "`${assetType}.realtime`",
    "family.status !== 'ready'",
    "family.data_kind !== 'bars'",
    "family.frequency_semantics !== 'calendar_grid'",
)


class ScopeManifestError(ValueError):
    """Stable, non-secret failure at the scope-manifest boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Iter196Baseline:
    """The immutable integration input that Iteration 197 is allowed to bind."""

    baseline_ref: str
    baseline_sha256: str
    artifact_ref: str
    frozen_at: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> Iter196Baseline:
        """Validate a small explicit baseline envelope without guessing a ref."""
        if value is None:
            raise ScopeManifestError("ITER196_BASELINE_REQUIRED")
        if not isinstance(value, Mapping) or set(value) != _BASELINE_KEYS:
            raise ScopeManifestError("ITER196_BASELINE_INVALID")
        if value.get("schema_version") != ITER196_BASELINE_SCHEMA_VERSION:
            raise ScopeManifestError("ITER196_BASELINE_INVALID")
        if type(value.get("iteration")) is not int or value["iteration"] != 196:
            raise ScopeManifestError("ITER196_BASELINE_INVALID")
        if value.get("status") != "frozen":
            raise ScopeManifestError("ITER196_BASELINE_NOT_FROZEN")

        baseline_ref = _required_text(value.get("baseline_ref"))
        baseline_sha256 = _required_text(value.get("baseline_sha256"))
        artifact_ref = _required_text(value.get("artifact_ref"))
        frozen_at = _normalize_utc_timestamp(value.get("frozen_at"))
        if not _GIT_REF_RE.fullmatch(baseline_ref) or not _SHA256_RE.fullmatch(baseline_sha256):
            raise ScopeManifestError("ITER196_BASELINE_INVALID")
        return cls(
            baseline_ref=baseline_ref,
            baseline_sha256=baseline_sha256,
            artifact_ref=artifact_ref,
            frozen_at=frozen_at,
        )

    def as_dict(self) -> dict[str, Any]:
        """Render the exact baseline provenance carried into the manifest."""
        return {
            "schema_version": ITER196_BASELINE_SCHEMA_VERSION,
            "iteration": 196,
            "status": "frozen",
            "baseline_ref": self.baseline_ref,
            "baseline_sha256": self.baseline_sha256,
            "artifact_ref": self.artifact_ref,
            "frozen_at": self.frozen_at,
        }


@dataclass(frozen=True, slots=True)
class FrontendMarketInputSurface:
    """Narrowly parsed market-page inputs, retained with source provenance."""

    source_path: str
    source_sha256: str
    asset_types: tuple[str, ...]
    legacy_periods: tuple[str, ...]
    family_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Render only the frontend inputs that the bounded parser actually proved."""
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "asset_types": list(self.asset_types),
            "legacy_periods": list(self.legacy_periods),
            "family_ids": list(self.family_ids),
        }


@dataclass(frozen=True, slots=True)
class ApiInputSurface:
    """Typed public API inputs used to constrain, rather than expand, the registry."""

    asset_types: tuple[str, ...]
    frequencies: tuple[str, ...]
    legacy_period_to_frequency: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        """Render the exact typed and legacy compatibility input axes."""
        return {
            "asset_types": list(self.asset_types),
            "frequencies": list(self.frequencies),
            "legacy_period_to_frequency": [
                {"period": period, "frequency": frequency}
                for period, frequency in self.legacy_period_to_frequency
            ],
        }


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON in the one form used for every scope evidence hash."""
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScopeManifestError("SCOPE_MANIFEST_CANONICALIZATION_FAILED") from exc


def canonical_sha256(value: object) -> str:
    """Return a stable SHA-256 for JSON-compatible scope content."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_iter196_baseline(path: Path) -> Iter196Baseline:
    """Load a reviewed baseline envelope; nonexistent inputs never become defaults."""
    if not path.is_file():
        raise ScopeManifestError("ITER196_BASELINE_REQUIRED")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScopeManifestError("ITER196_BASELINE_INVALID") from exc
    return Iter196Baseline.from_mapping(payload)


def load_scope_manifest(path: Path) -> dict[str, Any]:
    """Load JSON as an object so callers cannot validate an array or scalar artifact."""
    if not path.is_file():
        raise ScopeManifestError("SCOPE_MANIFEST_REQUIRED")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScopeManifestError("SCOPE_MANIFEST_INVALID") from exc
    if not isinstance(payload, dict):
        raise ScopeManifestError("SCOPE_MANIFEST_INVALID")
    return payload


def inspect_frontend_market_input_surface(project_root: Path) -> FrontendMarketInputSurface:
    """Extract only stable current-page literals; syntax drift fails instead of guessing."""
    relative_path = "src/frontend/src/views/data/useDataPage.ts"
    source = _read_project_source(project_root, relative_path)
    asset_block = _const_block(
        source, "const assetTabs: AssetTab[] = [", "const assetDisplayConfigs:"
    )
    period_block = _const_block(source, "const basePeriods = [", "const periods = computed(")
    family_block = _const_block(
        source,
        "const assetDataFamilySpecs: Record<MarketAssetType, DataFamilySpec[]> = {",
        "const assetTableSearchKeywords:",
    )

    asset_types = _literal_values_from_block(asset_block, "key")
    legacy_periods = _literal_values_from_block(period_block, "value")
    family_ids = _literal_values_from_block(family_block, "familyId")
    if not asset_types or not legacy_periods or not family_ids:
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_SURFACE_UNREADABLE")
    if len(asset_types) != len(set(asset_types)) or len(legacy_periods) != len(set(legacy_periods)):
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_SURFACE_UNREADABLE")
    if len(family_ids) != len(set(family_ids)):
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_FAMILY_DRIFT")
    if any(marker not in source for marker in _REQUIRED_FRONTEND_V2_MARKERS):
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_V2_RULE_UNREADABLE")

    return FrontendMarketInputSurface(
        source_path=relative_path,
        source_sha256=_sha256_file(project_root, relative_path),
        asset_types=tuple(asset_types),
        legacy_periods=tuple(legacy_periods),
        family_ids=tuple(family_ids),
    )


def inspect_api_input_surface() -> ApiInputSurface:
    """Read API literals and the actual legacy period mapping from Python code."""
    asset_types = tuple(_literal_string_values(MarketDataAssetType))
    frequencies = tuple(_literal_string_values(MarketDataFrequency))
    raw_legacy_mapping = dict(_FREQUENCY_BY_LEGACY_PERIOD)
    if (
        not asset_types
        or not frequencies
        or not raw_legacy_mapping
        or any(
            not isinstance(period, str) or not isinstance(frequency, str)
            for period, frequency in raw_legacy_mapping.items()
        )
        or any(frequency not in frequencies for frequency in raw_legacy_mapping.values())
    ):
        raise ScopeManifestError("SCOPE_MANIFEST_API_SURFACE_UNREADABLE")
    return ApiInputSurface(
        asset_types=asset_types,
        frequencies=frequencies,
        legacy_period_to_frequency=tuple(sorted(raw_legacy_mapping.items())),
    )


def build_scope_manifest(
    *,
    project_root: Path,
    iter196_baseline: Iter196Baseline | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build one deterministic provisional manifest after proving its frozen baseline."""
    baseline = _validated_baseline(iter196_baseline)
    root = project_root.resolve()
    frontend = inspect_frontend_market_input_surface(root)
    api = inspect_api_input_surface()
    registry_families = _registry_families(api.asset_types)
    registry_family_ids = {family["family_id"] for family in registry_families}
    registry_asset_types = {family["asset_type"] for family in registry_families}

    if set(frontend.asset_types) != set(api.asset_types) or registry_asset_types != set(
        api.asset_types
    ):
        raise ScopeManifestError("SCOPE_MANIFEST_ASSET_SURFACE_DRIFT")
    if set(frontend.family_ids) != registry_family_ids:
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_FAMILY_DRIFT")
    if any(
        period not in dict(api.legacy_period_to_frequency) for period in frontend.legacy_periods
    ):
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_PERIOD_DRIFT")

    source_refs = [
        {
            "role": role,
            "path": relative_path,
            "sha256": _sha256_file(root, relative_path),
        }
        for role, relative_path in _SOURCE_FILES
    ]
    legacy_period_mapping = dict(api.legacy_period_to_frequency)
    rows = [
        _manifest_row(
            family=family,
            frontend=frontend,
            api=api,
            legacy_period_mapping=legacy_period_mapping,
        )
        for family in registry_families
    ]
    manifest_without_hash: dict[str, Any] = {
        "schema_version": SCOPE_MANIFEST_SCHEMA_VERSION,
        "scope_id": "iteration-197-market-data",
        "scope_status": SCOPE_MANIFEST_STATUS,
        "family_contract_version": FAMILY_CONTRACT_VERSION,
        "iter196_baseline": baseline.as_dict(),
        "source_refs": source_refs,
        "input_surfaces": {
            "frontend": frontend.as_dict(),
            "api": api.as_dict(),
        },
        # A baseline is only an input to future integration.  It never turns a
        # scope artifact into an authorization to change a live strategy path.
        "strategy_page_production_status": "not_enabled_by_scope_manifest",
        "rows": rows,
    }
    return {**manifest_without_hash, "manifest_sha256": canonical_sha256(manifest_without_hash)}


def validate_scope_manifest(*, manifest: Mapping[str, Any], project_root: Path) -> None:
    """Fail closed on altered rows, stale sources, or any non-frozen baseline."""
    if not isinstance(manifest, Mapping) or set(manifest) != _MANIFEST_KEYS:
        raise ScopeManifestError("SCOPE_MANIFEST_INVALID")
    if (
        manifest.get("schema_version") != SCOPE_MANIFEST_SCHEMA_VERSION
        or manifest.get("scope_id") != "iteration-197-market-data"
        or manifest.get("scope_status") != SCOPE_MANIFEST_STATUS
        or manifest.get("family_contract_version") != FAMILY_CONTRACT_VERSION
        or manifest.get("strategy_page_production_status") != "not_enabled_by_scope_manifest"
    ):
        raise ScopeManifestError("SCOPE_MANIFEST_INVALID")
    baseline = Iter196Baseline.from_mapping(_mapping_or_none(manifest.get("iter196_baseline")))
    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != _CURRENT_FAMILY_COUNT:
        raise ScopeManifestError("SCOPE_MANIFEST_INVALID")
    for row in rows:
        if not isinstance(row, Mapping):
            raise ScopeManifestError("SCOPE_MANIFEST_INVALID")
        received_hash = row.get("row_sha256")
        if not isinstance(received_hash, str) or not _SHA256_RE.fullmatch(received_hash):
            raise ScopeManifestError("SCOPE_MANIFEST_ROW_HASH_INVALID")
        canonical_row = {key: value for key, value in row.items() if key != "row_sha256"}
        if canonical_sha256(canonical_row) != received_hash:
            raise ScopeManifestError("SCOPE_MANIFEST_ROW_HASH_MISMATCH")

    received_manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(received_manifest_hash, str) or not _SHA256_RE.fullmatch(
        received_manifest_hash
    ):
        raise ScopeManifestError("SCOPE_MANIFEST_HASH_INVALID")
    canonical_manifest = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if canonical_sha256(canonical_manifest) != received_manifest_hash:
        raise ScopeManifestError("SCOPE_MANIFEST_HASH_MISMATCH")

    expected = build_scope_manifest(project_root=project_root, iter196_baseline=baseline)
    if canonical_json_bytes(dict(manifest)) != canonical_json_bytes(expected):
        raise ScopeManifestError("SCOPE_MANIFEST_CONTENT_DRIFT")


def write_scope_manifest(*, manifest: Mapping[str, Any], output_path: Path) -> None:
    """Write one complete JSON artifact atomically after the caller has validated it."""
    parent = output_path.parent
    if not parent.is_dir():
        raise ScopeManifestError("SCOPE_MANIFEST_OUTPUT_DIRECTORY_MISSING")
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temporary_path.write_text(encoded, encoding="utf-8")
        temporary_path.replace(output_path)
    except OSError as exc:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ScopeManifestError("SCOPE_MANIFEST_WRITE_FAILED") from exc


def _validated_baseline(
    baseline: Iter196Baseline | Mapping[str, Any] | None,
) -> Iter196Baseline:
    if isinstance(baseline, Iter196Baseline):
        # Re-run the public envelope validation so a hand-constructed instance
        # cannot bypass the same future-proof rules as file-based inputs.
        return Iter196Baseline.from_mapping(baseline.as_dict())
    return Iter196Baseline.from_mapping(baseline)


def _registry_families(api_asset_types: tuple[str, ...]) -> list[dict[str, Any]]:
    families = [
        family.model_dump(mode="json")
        for asset_type in sorted(api_asset_types)
        for family in DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(
            MarketDataQueryBundleRequest(asset_type=asset_type)
        ).families
    ]
    if len(families) != _CURRENT_FAMILY_COUNT:
        raise ScopeManifestError("SCOPE_MANIFEST_REGISTRY_CARDINALITY_INVALID")
    family_ids = [family["family_id"] for family in families]
    if len(family_ids) != len(set(family_ids)):
        raise ScopeManifestError("SCOPE_MANIFEST_REGISTRY_CARDINALITY_INVALID")
    if any(family["family_contract_version"] != FAMILY_CONTRACT_VERSION for family in families):
        raise ScopeManifestError("SCOPE_MANIFEST_REGISTRY_VERSION_DRIFT")
    return sorted(families, key=lambda family: str(family["family_id"]))


def _manifest_row(
    *,
    family: Mapping[str, Any],
    frontend: FrontendMarketInputSurface,
    api: ApiInputSurface,
    legacy_period_mapping: Mapping[str, str],
) -> dict[str, Any]:
    frequencies = tuple(str(value) for value in family["frequencies"])
    if any(frequency not in api.frequencies for frequency in frequencies):
        raise ScopeManifestError("SCOPE_MANIFEST_API_FREQUENCY_DRIFT")
    asset_type = str(family["asset_type"])
    family_id = str(family["family_id"])
    declared_compatibility_periods = [
        period for period in frontend.legacy_periods if legacy_period_mapping[period] in frequencies
    ]
    is_v2_compatibility_family = (
        family_id == f"{asset_type}.realtime"
        and family["status"] == "ready"
        and family["data_kind"] == "bars"
        and family["frequency_semantics"] == "calendar_grid"
    )
    row_without_hash: dict[str, Any] = {
        "family_id": family_id,
        "asset_type": asset_type,
        "family_contract_version": family["family_contract_version"],
        "contract_status": family["status"],
        "dataset_code": family["dataset_code"],
        "data_kind": family["data_kind"],
        "frequency_semantics": family["frequency_semantics"],
        "frequencies": list(frequencies),
        "field_profile": {
            "field_profile_id": family["field_profile_id"],
            "required_fields": list(family["required_fields"]),
            "optional_fields": list(family["optional_fields"]),
            "dimension_fields": list(family["dimension_fields"]),
        },
        "coverage_model": family["coverage_model"],
        "source_policy_id": family["source_policy_id"],
        "reason_code": family["reason_code"],
        "frontend": {
            "market_page_asset_supported": asset_type in frontend.asset_types,
            "market_page_family_declared": family_id in frontend.family_ids,
            "legacy_page_period_inputs": list(frontend.legacy_periods),
            "declared_compatibility_periods": declared_compatibility_periods,
            "v2_query_periods": (
                declared_compatibility_periods if is_v2_compatibility_family else []
            ),
        },
        "api": {
            "asset_type_accepted": asset_type in api.asset_types,
            "declared_api_frequency_inputs": list(frequencies),
            "legacy_period_aliases": sorted(
                period
                for period, frequency in api.legacy_period_to_frequency
                if frequency in frequencies
            ),
        },
        "strategy_page_production_status": "not_enabled_by_scope_manifest",
    }
    return {**row_without_hash, "row_sha256": canonical_sha256(row_without_hash)}


def _read_project_source(project_root: Path, relative_path: str) -> str:
    path = _project_file(project_root, relative_path)
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ScopeManifestError("SCOPE_MANIFEST_SOURCE_PROVENANCE_UNAVAILABLE") from exc


def _sha256_file(project_root: Path, relative_path: str) -> str:
    path = _project_file(project_root, relative_path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ScopeManifestError("SCOPE_MANIFEST_SOURCE_PROVENANCE_UNAVAILABLE") from exc


def _project_file(project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise ScopeManifestError("SCOPE_MANIFEST_SOURCE_PROVENANCE_UNAVAILABLE")
    return path


def _const_block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.find(start_marker)
    if start < 0:
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_SURFACE_UNREADABLE")
    end = source.find(end_marker, start + len(start_marker))
    if end < 0:
        raise ScopeManifestError("SCOPE_MANIFEST_FRONTEND_SURFACE_UNREADABLE")
    return source[start:end]


def _literal_values_from_block(block: str, property_name: str) -> tuple[str, ...]:
    expression = re.compile(r"\b" + re.escape(property_name) + r"\s*:\s*(['\"])([A-Za-z0-9_.-]+)\1")
    return tuple(match.group(2) for match in expression.finditer(block))


def _literal_string_values(annotation: object) -> tuple[str, ...]:
    values = get_args(annotation)
    if not values or any(not isinstance(value, str) for value in values):
        raise ScopeManifestError("SCOPE_MANIFEST_API_SURFACE_UNREADABLE")
    if len(values) != len(set(values)):
        raise ScopeManifestError("SCOPE_MANIFEST_API_SURFACE_UNREADABLE")
    return tuple(values)


def _required_text(value: object) -> str:
    if not isinstance(value, str):
        raise ScopeManifestError("ITER196_BASELINE_INVALID")
    normalized = value.strip()
    if not normalized:
        raise ScopeManifestError("ITER196_BASELINE_INVALID")
    return normalized


def _normalize_utc_timestamp(value: object) -> str:
    raw = _required_text(value)
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ScopeManifestError("ITER196_BASELINE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ScopeManifestError("ITER196_BASELINE_INVALID")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping_or_none(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


__all__ = [
    "ITER196_BASELINE_SCHEMA_VERSION",
    "SCOPE_MANIFEST_SCHEMA_VERSION",
    "ApiInputSurface",
    "FrontendMarketInputSurface",
    "Iter196Baseline",
    "ScopeManifestError",
    "build_scope_manifest",
    "canonical_json_bytes",
    "canonical_sha256",
    "inspect_api_input_surface",
    "inspect_frontend_market_input_surface",
    "load_iter196_baseline",
    "load_scope_manifest",
    "validate_scope_manifest",
    "write_scope_manifest",
]
