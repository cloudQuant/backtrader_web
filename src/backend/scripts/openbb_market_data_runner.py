"""Isolated JSON-line runner for the approved OpenBB market-data subset.

Run this script only from a dedicated environment containing the approved
OpenBB extension set.  The web process invokes it through
``OPENBB_MARKET_DATA_RUNNER`` and never imports OpenBB itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from importlib import metadata
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

PROTOCOL_VERSION = "openbb-market-data-v1"
SELF_CHECK_VERSION = "openbb-market-data-self-check-v1"
_ALLOWED_ASSET_TYPES = {"stock", "fund", "futures", "fx", "crypto"}
_YFINANCE_INTERVAL_BY_FREQUENCY = {
    "1d": "1d",
}
_MAX_YFINANCE_DAILY_WINDOW_DAYS = 3650
_MAX_RAW_PAYLOAD_BYTES = 4 * 1024 * 1024
_REQUIRED_DISTRIBUTIONS = ("openbb", "openbb-core", "openbb-yfinance", "yfinance")
_PERMIT_MANIFEST_VERSION = "openbb-runtime-permit-manifest-v1"
_PERMIT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "market_data"
    / "openbb_runtime_permit_manifest.json"
)
_OUTBOUND_END_BOUND_UNATTESTED = "OPENBB_YFINANCE_OUTBOUND_END_BOUND_UNATTESTED"
_RUNTIME_ARTIFACT_UNATTESTED = "OPENBB_YFINANCE_RUNTIME_ARTIFACT_UNATTESTED"
_RUNTIME_ARTIFACT_MANIFEST_VERSION = "openbb-yfinance-runtime-artifact-manifest-v1"
_YFINANCE_DAILY_END_BOUND_CONTRACT = (
    "openbb-yfinance-daily-inclusive-to-yfinance-exclusive-v1"
)
_RUNTIME_ARTIFACT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "market_data"
    / "openbb_yfinance_runtime_artifact_manifest.json"
)


@dataclass(frozen=True, slots=True)
class _RunnerRuntimeRoutePermit:
    """One exact runner-side mirror of a reviewed OpenBB route permit.

    This deliberately duplicates the web application's static permit matrix
    because this script must remain executable from an isolated OpenBB runtime
    without importing application code. A future enablement must update both
    sides together and prove their parity before this tuple can become
    nonempty.
    """

    route_id: str
    family_id: str
    provider: str
    asset_type: str
    market: str
    data_kind: str
    frequency: str
    adjustment: str | None
    price_basis: str | None
    currency: str | None
    unit: str | None
    endpoint: str

    def matches_request(self, request: Mapping[str, Any]) -> bool:
        """Require every permit axis and endpoint in the echoed DTO to match."""
        return (
            request.get("route_id") == self.route_id
            and request.get("family_id") == self.family_id
            and request.get("provider") == self.provider
            and request.get("asset_type") == self.asset_type
            and request.get("market") == self.market
            and request.get("data_kind") == self.data_kind
            and request.get("frequency") == self.frequency
            and request.get("adjustment") == self.adjustment
            and request.get("price_basis") == self.price_basis
            and request.get("currency") == self.currency
            and request.get("unit") == self.unit
            and request.get("provider_endpoint") == self.endpoint
        )


@dataclass(frozen=True, slots=True)
class _RunnerRuntimeArtifactFile:
    """One package-owned source file needed by the reviewed runner route."""

    relative_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class _RunnerRuntimeArtifactDistribution:
    """One exact installed distribution and the source files it must own."""

    distribution: str
    version: str
    files: tuple[_RunnerRuntimeArtifactFile, ...]


@dataclass(frozen=True, slots=True)
class _RunnerRuntimeArtifactManifest:
    """Pure-data, pre-import OpenBB runtime candidate contract."""

    manifest_version: str
    artifact_set_version: str
    attestation_state: str
    outbound_end_bound_contract: str | None
    distributions: tuple[_RunnerRuntimeArtifactDistribution, ...]


@dataclass(frozen=True, slots=True)
class _RuntimeArtifactAttestation:
    """Bounded result of validating a static runtime artifact contract."""

    status: str
    code: str | None
    manifest_status: str
    manifest_version: str | None
    artifact_set_version: str | None
    attestation_state: str | None
    distribution_names: tuple[str, ...]
    verified_file_count: int


def _manifest_text(value: object) -> str:
    """Require one non-blank pure-data manifest string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid static permit manifest")
    return value.strip()


def _manifest_optional_text(value: object) -> str | None:
    """Accept only a JSON null or a non-blank string semantic axis."""
    if value is None:
        return None
    return _manifest_text(value)


def _manifest_text_list(value: object) -> tuple[str, ...]:
    """Reject empty, duplicate, or non-string static permit list values."""
    if not isinstance(value, list):
        raise ValueError("invalid static permit manifest")
    parsed = tuple(_manifest_text(item) for item in value)
    if not parsed or len(set(parsed)) != len(parsed):
        raise ValueError("invalid static permit manifest")
    return parsed


def _manifest_route_permit(value: object) -> _RunnerRuntimeRoutePermit:
    """Convert one canonical pure-data permit without importing the web app."""
    if not isinstance(value, Mapping):
        raise ValueError("invalid static permit manifest")
    return _RunnerRuntimeRoutePermit(
        route_id=_manifest_text(value.get("route_id")),
        family_id=_manifest_text(value.get("family_id")),
        provider=_manifest_text(value.get("provider")),
        asset_type=_manifest_text(value.get("asset_type")),
        market=_manifest_text(value.get("market")),
        data_kind=_manifest_text(value.get("data_kind")),
        frequency=_manifest_text(value.get("frequency")),
        adjustment=_manifest_optional_text(value.get("adjustment")),
        price_basis=_manifest_optional_text(value.get("price_basis")),
        currency=_manifest_optional_text(value.get("currency")),
        unit=_manifest_optional_text(value.get("unit")),
        endpoint=_manifest_text(value.get("endpoint")),
    )


def _load_static_runtime_permit_manifest() -> tuple[
    str | None,
    tuple[str, ...],
    tuple[str, ...],
    tuple[_RunnerRuntimeRoutePermit, ...],
    str | None,
]:
    """Load the web/runner shared JSON data without importing application code.

    A malformed or missing manifest never supplies a fallback route.  The
    runner remembers a stable failure state so a request remains fail-closed
    and the self-check can report why it is blocked.
    """
    try:
        raw = json.loads(_PERMIT_MANIFEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("manifest root must be an object")
        if _manifest_text(raw.get("manifest_version")) != _PERMIT_MANIFEST_VERSION:
            raise ValueError("manifest version is unsupported")
        permit_matrix_version = _manifest_text(raw.get("permit_matrix_version"))
        provider_names = _manifest_text_list(raw.get("supported_runner_providers"))
        dangerous_environment_keys = _manifest_text_list(
            raw.get("dangerous_extension_environment_keys")
        )
        raw_permits = raw.get("runtime_route_permits")
        if not isinstance(raw_permits, list):
            raise ValueError("route permits must be a list")
        permits = tuple(_manifest_route_permit(value) for value in raw_permits)
        if len({permit.route_id for permit in permits}) != len(permits) or any(
            permit.provider not in provider_names for permit in permits
        ):
            raise ValueError("route permits are invalid")
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None, (), (), (), "OPENBB_PERMIT_MANIFEST_INVALID"
    return permit_matrix_version, provider_names, dangerous_environment_keys, permits, None


(
    _PERMIT_MATRIX_VERSION,
    _EXACT_ALLOWED_PROVIDER_NAMES,
    _DANGEROUS_OPENBB_ENVIRONMENT_KEYS,
    _ACTIVE_RUNTIME_ROUTE_PERMITS,
    _PERMIT_MANIFEST_ERROR,
) = _load_static_runtime_permit_manifest()


def _artifact_manifest_text(value: object) -> str:
    """Return one exact non-blank static artifact-manifest text value."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("invalid static runtime artifact manifest")
    return value


def _artifact_manifest_relative_path(value: object) -> str:
    """Reject paths that could escape a distribution's owned file inventory."""
    relative_path = _artifact_manifest_text(value)
    if "\\" in relative_path or "\x00" in relative_path:
        raise ValueError("invalid static runtime artifact manifest")
    parts = relative_path.split("/")
    windows_path = PureWindowsPath(relative_path)
    if (
        PurePosixPath(relative_path).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or windows_path.root
        or not parts
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("invalid static runtime artifact manifest")
    return relative_path


def _artifact_manifest_sha256(value: object) -> str:
    """Accept only a lowercase SHA-256 digest from reviewed static data."""
    sha256 = _artifact_manifest_text(value)
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ValueError("invalid static runtime artifact manifest")
    return sha256


def _artifact_manifest_file(value: object) -> _RunnerRuntimeArtifactFile:
    """Parse one hash-pinned distribution file with no path fallback."""
    if not isinstance(value, Mapping) or set(value) != {"relative_path", "sha256"}:
        raise ValueError("invalid static runtime artifact manifest")
    return _RunnerRuntimeArtifactFile(
        relative_path=_artifact_manifest_relative_path(value.get("relative_path")),
        sha256=_artifact_manifest_sha256(value.get("sha256")),
    )


def _artifact_manifest_distribution(value: object) -> _RunnerRuntimeArtifactDistribution:
    """Parse one exact distribution version and its package-owned source files."""
    if not isinstance(value, Mapping) or set(value) != {"distribution", "version", "files"}:
        raise ValueError("invalid static runtime artifact manifest")
    distribution = _artifact_manifest_text(value.get("distribution"))
    if distribution not in _REQUIRED_DISTRIBUTIONS:
        raise ValueError("invalid static runtime artifact manifest")
    raw_files = value.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("invalid static runtime artifact manifest")
    files = tuple(_artifact_manifest_file(item) for item in raw_files)
    if len({item.relative_path for item in files}) != len(files):
        raise ValueError("invalid static runtime artifact manifest")
    return _RunnerRuntimeArtifactDistribution(
        distribution=distribution,
        version=_artifact_manifest_text(value.get("version")),
        files=files,
    )


def _load_static_runtime_artifact_manifest() -> tuple[
    _RunnerRuntimeArtifactManifest | None,
    str | None,
]:
    """Load the versioned pre-import artifact contract without importing OpenBB.

    ``disabled`` is an explicit safe default. ``candidate`` records an exact
    fork package set and its bounded daily end-date contract, but remains
    non-executable: a future isolated-image/import-closure design must add a
    new execution attestation state in code.  This parser deliberately does
    not accept a data-only transition to ``attested``.
    """
    try:
        raw = json.loads(_RUNTIME_ARTIFACT_MANIFEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping) or set(raw) != {
            "manifest_version",
            "artifact_set_version",
            "attestation_state",
            "outbound_end_bound_contract",
            "artifacts",
        }:
            raise ValueError("manifest root is invalid")
        manifest_version = _artifact_manifest_text(raw.get("manifest_version"))
        if manifest_version != _RUNTIME_ARTIFACT_MANIFEST_VERSION:
            raise ValueError("manifest version is unsupported")
        artifact_set_version = _artifact_manifest_text(raw.get("artifact_set_version"))
        attestation_state = _artifact_manifest_text(raw.get("attestation_state"))
        outbound_end_bound_contract = raw.get("outbound_end_bound_contract")
        raw_distributions = raw.get("artifacts")
        if not isinstance(raw_distributions, list):
            raise ValueError("artifact list is invalid")
        if attestation_state == "disabled":
            if raw_distributions or outbound_end_bound_contract is not None:
                raise ValueError("disabled manifests cannot name artifacts")
            distributions: tuple[_RunnerRuntimeArtifactDistribution, ...] = ()
            contract: str | None = None
        elif attestation_state == "candidate":
            if outbound_end_bound_contract != _YFINANCE_DAILY_END_BOUND_CONTRACT:
                raise ValueError("candidate end-bound contract is invalid")
            distributions = tuple(
                _artifact_manifest_distribution(item) for item in raw_distributions
            )
            if tuple(item.distribution for item in distributions) != _REQUIRED_DISTRIBUTIONS:
                raise ValueError("candidate distributions are incomplete or unordered")
            contract = _YFINANCE_DAILY_END_BOUND_CONTRACT
        else:
            raise ValueError("artifact attestation state is unsupported")
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None, "invalid"
    return (
        _RunnerRuntimeArtifactManifest(
            manifest_version=manifest_version,
            artifact_set_version=artifact_set_version,
            attestation_state=attestation_state,
            outbound_end_bound_contract=contract,
            distributions=distributions,
        ),
        None,
    )


(
    _RUNTIME_ARTIFACT_MANIFEST,
    _RUNTIME_ARTIFACT_MANIFEST_ERROR,
) = _load_static_runtime_artifact_manifest()


def _sha256_file(path: Path) -> str:
    """Hash one installed package file without importing its package."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_artifact_attestation() -> _RuntimeArtifactAttestation:
    """Verify exact installed artifacts before an OpenBB import can occur.

    The result deliberately contains no installation paths or expected hashes.
    All validation failures collapse to one public stable code so the runner
    cannot disclose package layout while still refusing an unreviewed runtime.
    """
    manifest = _RUNTIME_ARTIFACT_MANIFEST
    if manifest is None:
        return _RuntimeArtifactAttestation(
            status="unattested",
            code=_RUNTIME_ARTIFACT_UNATTESTED,
            manifest_status="invalid",
            manifest_version=None,
            artifact_set_version=None,
            attestation_state=None,
            distribution_names=(),
            verified_file_count=0,
        )
    distribution_names = tuple(item.distribution for item in manifest.distributions)
    expected_file_count = sum(len(item.files) for item in manifest.distributions)
    common = {
        "manifest_version": manifest.manifest_version,
        "artifact_set_version": manifest.artifact_set_version,
        "attestation_state": manifest.attestation_state,
        "distribution_names": distribution_names,
    }
    if manifest.attestation_state == "disabled":
        return _RuntimeArtifactAttestation(
            status="unattested",
            code=_RUNTIME_ARTIFACT_UNATTESTED,
            manifest_status="valid",
            verified_file_count=0,
            **common,
        )
    try:
        for artifact in manifest.distributions:
            distribution = metadata.distribution(artifact.distribution)
            if distribution.version != artifact.version:
                raise ValueError("distribution version differs")
            owned_relative_paths = {str(item) for item in distribution.files or ()}
            distribution_root = Path(distribution.locate_file(".")).resolve(strict=True)
            for file_artifact in artifact.files:
                if file_artifact.relative_path not in owned_relative_paths:
                    raise ValueError("distribution does not own artifact file")
                located_file = Path(distribution.locate_file(file_artifact.relative_path))
                if located_file.is_symlink() or not located_file.is_file():
                    raise ValueError("artifact file is not a regular owned file")
                resolved_file = located_file.resolve(strict=True)
                try:
                    resolved_file.relative_to(distribution_root)
                except ValueError as exc:
                    raise ValueError("artifact file escapes distribution root") from exc
                if _sha256_file(resolved_file) != file_artifact.sha256:
                    raise ValueError("artifact file differs")
    except Exception:
        return _RuntimeArtifactAttestation(
            status="unattested",
            code=_RUNTIME_ARTIFACT_UNATTESTED,
            manifest_status="valid",
            verified_file_count=0,
            **common,
        )
    return _RuntimeArtifactAttestation(
        status="candidate",
        code=_RUNTIME_ARTIFACT_UNATTESTED,
        manifest_status="valid",
        verified_file_count=expected_file_count,
        **common,
    )


def _emit(payload: Mapping[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
    sys.stdout.flush()
    return 0


def _json_default(value: object) -> str | float:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _json_safe(value: object) -> object:
    """Preserve a bounded OpenBB record representation before normalization."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
            normalized[key] = _json_safe(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        return _json_safe(item())
    raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")


def _canonical_json(value: object) -> str:
    """Serialize raw runner evidence once for its source receipt hash."""
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _raw_payload(rows: list[dict[str, Any]]) -> tuple[dict[str, object], str]:
    """Return the pre-normalization source-record evidence and its verified hash."""
    payload = {
        "format": "openbb-records-pre-normalization-v1",
        "records": _json_safe(rows),
    }
    encoded = _canonical_json(payload).encode("utf-8")
    if len(encoded) > _MAX_RAW_PAYLOAD_BYTES:
        raise ValueError("OPENBB_RAW_PAYLOAD_TOO_LARGE")
    return payload, hashlib.sha256(encoded).hexdigest()


def _error(request_id: object, code: str, detail: str) -> int:
    return _emit(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "error": {"code": code, "detail": detail[:2048]},
        }
    )


def _configured_provider_names() -> tuple[str, ...]:
    """Read the raw provider tokens so spelling and cardinality stay attestable."""
    return tuple(os.getenv("OPENBB_ALLOWED_PROVIDERS", "yfinance").split(","))


def _provider_allow_list_is_exact(provider_names: tuple[str, ...]) -> bool:
    """Accept only the one reviewed provider name, once, with exact spelling."""
    return provider_names == _EXACT_ALLOWED_PROVIDER_NAMES


def _distribution_versions() -> dict[str, str | None]:
    """Read installed package metadata only; this never imports an OpenBB extension."""
    versions: dict[str, str | None] = {}
    for distribution_name in _REQUIRED_DISTRIBUTIONS:
        try:
            versions[distribution_name] = metadata.version(distribution_name)
        except (metadata.PackageNotFoundError, OSError, ValueError):
            versions[distribution_name] = None
    return versions


def _self_check_payload() -> dict[str, object]:
    """Return a local, non-secret attestation for the blocked runtime boundary.

    It intentionally uses distribution metadata, static artifact data, and
    the static permit matrix rather than importing ``openbb`` or
    invoking provider coverage APIs.  That keeps a self-check non-network and
    prevents it from changing runtime state or loading a mutable extension
    merely to inspect it.
    """
    configured_provider_names = _configured_provider_names()
    distribution_versions = _distribution_versions()
    artifact_attestation = _runtime_artifact_attestation()
    dangerous_environment_keys = [
        key for key in _DANGEROUS_OPENBB_ENVIRONMENT_KEYS if os.getenv(key)
    ]
    outbound_end_bound_attested = _yfinance_outbound_end_bound_is_attested(
        artifact_attestation=artifact_attestation
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "self_check_version": SELF_CHECK_VERSION,
        "status": "blocked",
        "attestation": {
            "runtime": {
                "distribution_versions": distribution_versions,
                "missing_distributions": [
                    name for name, version in distribution_versions.items() if version is None
                ],
                "artifact_attestation": {
                    "status": artifact_attestation.status,
                    "code": artifact_attestation.code,
                    "manifest_status": artifact_attestation.manifest_status,
                    "manifest_version": artifact_attestation.manifest_version,
                    "artifact_set_version": artifact_attestation.artifact_set_version,
                    "attestation_state": artifact_attestation.attestation_state,
                    "distribution_names": list(artifact_attestation.distribution_names),
                    "verified_file_count": artifact_attestation.verified_file_count,
                    "paths_included": False,
                    "hashes_included": False,
                },
            },
            "coverage": {
                "permit_matrix_version": _PERMIT_MATRIX_VERSION,
                "coverage_source": "canonical-static-permit-manifest",
                "permit_manifest_status": (
                    "valid" if _PERMIT_MANIFEST_ERROR is None else "invalid"
                ),
                "active_route_ids": [
                    permit.route_id for permit in _ACTIVE_RUNTIME_ROUTE_PERMITS
                ],
            },
            "configuration": {
                "configured_provider_names": list(configured_provider_names),
                "provider_allow_list_status": (
                    "exact"
                    if _provider_allow_list_is_exact(configured_provider_names)
                    else "invalid"
                ),
                "dangerous_openbb_environment_keys": dangerous_environment_keys,
                "secret_values_included": False,
            },
            "outbound_end_bound": {
                "code": None if outbound_end_bound_attested else _OUTBOUND_END_BOUND_UNATTESTED,
                "status": "attested" if outbound_end_bound_attested else "unattested",
            },
        },
    }


def _yfinance_outbound_end_bound_is_attested(
    *,
    artifact_attestation: _RuntimeArtifactAttestation | None = None,
) -> bool:
    """Return whether the actual installed yfinance call has a proved end bound.

    A static candidate proves only the reviewed fork source and its intended
    inclusive-to-exclusive daily date transformation. It cannot authorize an
    OpenBB import: this runner has no accepted isolated-image/import-closure
    state yet. The check is intentionally tied to the caller's same artifact
    result so a future execution design cannot create a metadata TOCTOU gap.
    """
    if artifact_attestation is None:
        artifact_attestation = _runtime_artifact_attestation()
    manifest = _RUNTIME_ARTIFACT_MANIFEST
    return (
        artifact_attestation.status == "attested"
        and manifest is not None
        and manifest.attestation_state == "attested"
        and manifest.outbound_end_bound_contract == _YFINANCE_DAILY_END_BOUND_CONTRACT
    )


def _has_active_runtime_route_permit(request: Mapping[str, Any]) -> bool:
    """Require an exact runner-side permit even after an end-bound implementation exists.

    This duplicate, intentionally empty runtime guard prevents a future change
    to the outbound-bound attestation from implicitly enabling asset or market
    classes. A reviewed enablement must update this runner guard and the web
    policy matrix in the same change, with parity tests.
    """
    return any(permit.matches_request(request) for permit in _ACTIVE_RUNTIME_ROUTE_PERMITS)


def _as_utc_text(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("OpenBB row has no usable event timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _route(obb: Any, *, asset_type: str, endpoint: str) -> Callable[..., Any]:
    """Resolve only the exact server-permitted endpoint for one asset class."""
    if (asset_type, endpoint) == ("stock", "equity.price.historical"):
        return obb.equity.price.historical
    if (asset_type, endpoint) == ("fund", "etf.historical"):
        return obb.etf.historical
    if (asset_type, endpoint) == ("futures", "derivatives.futures.historical"):
        return obb.derivatives.futures.historical
    if (asset_type, endpoint) == ("fx", "currency.price.historical"):
        return obb.currency.price.historical
    if (asset_type, endpoint) == ("crypto", "crypto.price.historical"):
        return obb.crypto.price.historical
    raise ValueError("OPENBB_ENDPOINT_UNSUPPORTED")


def _records(result: Any) -> list[dict[str, Any]]:
    if hasattr(result, "to_df"):
        # OpenBB's OBBject.to_df() defaults to ``index="date"``.  Converting
        # that DataFrame with ``orient="records"`` drops its index and leaves
        # the child protocol without an event timestamp.  Requesting an
        # index-free frame retains the ``date`` column as a source field.
        dataframe = result.to_df(index=None)
        return [dict(item) for item in dataframe.to_dict(orient="records")]
    if hasattr(result, "results") and isinstance(result.results, list):
        return [dict(item) for item in result.results if isinstance(item, Mapping)]
    if isinstance(result, list):
        return [dict(item) for item in result if isinstance(item, Mapping)]
    raise ValueError("OpenBB response has no record representation")


def _normalize_records(
    rows: list[dict[str, Any]],
    *,
    start_at: datetime,
    end_at: datetime,
) -> list[dict[str, Any]]:
    """Normalize and enforce the parent's exact half-open response window."""
    normalized: list[dict[str, Any]] = []
    timestamp_fields = ("event_at", "date", "datetime", "timestamp")
    for row in rows:
        event_value = next(
            (row.get(key) for key in timestamp_fields if row.get(key) is not None), None
        )
        event_at = datetime.fromisoformat(_as_utc_text(event_value))
        if not start_at <= event_at < end_at:
            continue
        fields = {key: value for key, value in row.items() if key not in timestamp_fields}
        if fields:
            normalized.append({"event_at": event_at.isoformat(), "fields": fields})
    return normalized


def _request_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _yfinance_historical_window(request: Mapping[str, Any]) -> tuple[datetime, datetime]:
    """Validate the sole reviewed daily window before loading OpenBB.

    The day-aligned, half-open platform interval must be no longer than ten
    365-day years.  This is a route boundary rather than a response filter, so
    it remains enforced even while the artifact, outbound-bound, or permit
    gates are disabled.
    """
    frequency = request.get("frequency")
    if frequency != "1d":
        raise ValueError("OPENBB_FREQUENCY_UNSUPPORTED")
    start_at = _request_timestamp(request.get("start_at"), field_name="start_at")
    end_at = _request_timestamp(request.get("end_at"), field_name="end_at")
    if start_at >= end_at:
        raise ValueError("OPENBB_WINDOW_INVALID")
    if end_at - start_at > timedelta(days=_MAX_YFINANCE_DAILY_WINDOW_DAYS):
        raise ValueError("OPENBB_WINDOW_TOO_LARGE")
    if any(
        value != 0
        for value in (
            start_at.hour,
            start_at.minute,
            start_at.second,
            start_at.microsecond,
            end_at.hour,
            end_at.minute,
            end_at.second,
            end_at.microsecond,
        )
    ):
        raise ValueError("OPENBB_WINDOW_ALIGNMENT_UNSUPPORTED")
    return start_at, end_at


def _yfinance_historical_arguments(request: Mapping[str, Any]) -> dict[str, object]:
    """Translate one UTC day-aligned half-open window to yfinance arguments."""
    start_at, end_at = _yfinance_historical_window(request)
    provider_symbol = request.get("provider_symbol")
    if not isinstance(provider_symbol, str) or not provider_symbol.strip():
        raise ValueError("OPENBB_SYMBOL_INVALID")
    return {
        "symbol": provider_symbol,
        "start_date": start_at.date().isoformat(),
        "end_date": (end_at - timedelta(microseconds=1)).date().isoformat(),
        "interval": _YFINANCE_INTERVAL_BY_FREQUENCY["1d"],
        "provider": request["provider"],
    }


def _provider_error_code(exc: Exception) -> str:
    """Translate common provider failures into bounded operational outcomes.

    The parent FastAPI process receives only this stable code through the JSON
    protocol.  A temporary provider rate limit must remain distinguishable
    from a malformed response or unsupported route, so the query service can
    retain local data and try a later approved route.
    """
    detail = str(exc).casefold()
    if any(token in detail for token in ("rate limit", "too many requests", "http 429", "429")):
        return "OPENBB_RATE_LIMITED"
    if any(token in detail for token in ("unauthorized", "forbidden", "authentication", "api key")):
        return "OPENBB_AUTH_REQUIRED"
    if any(token in detail for token in ("no results", "empty data", "[empty]")):
        return "OPENBB_EMPTY_RESPONSE"
    return "OPENBB_ROUTE_FAILED"


def main() -> int:
    try:
        envelope = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        return _error(None, "OPENBB_RUNNER_INVALID_REQUEST", str(exc))
    if not isinstance(envelope, Mapping):
        return _error(None, "OPENBB_RUNNER_INVALID_REQUEST", "request envelope must be an object")
    request_id = envelope.get("request_id")
    if envelope.get("protocol_version") != PROTOCOL_VERSION or not isinstance(request_id, str):
        return _error(
            request_id, "OPENBB_RUNNER_INVALID_REQUEST", "protocol or request ID is invalid"
        )
    request = envelope.get("request")
    if not isinstance(request, Mapping):
        return _error(request_id, "OPENBB_RUNNER_INVALID_REQUEST", "request body must be an object")
    if request.get("request_id") != request_id:
        return _error(request_id, "OPENBB_RUNNER_INVALID_REQUEST", "request ID must match envelope")
    dangerous_environment_keys = [
        key for key in _DANGEROUS_OPENBB_ENVIRONMENT_KEYS if os.getenv(key)
    ]
    if dangerous_environment_keys:
        # This must happen before route checks and, especially, before the
        # OpenBB import.  A wrapper or runner service that asks OpenBB to load
        # mutable extensions or stream command output has a different trust
        # boundary from this reviewed JSON-line protocol.
        return _error(
            request_id,
            "OPENBB_RUNNER_DANGEROUS_ENVIRONMENT",
            "runner refuses mutable OpenBB extension environment",
        )
    if _PERMIT_MANIFEST_ERROR is not None:
        return _error(
            request_id,
            _PERMIT_MANIFEST_ERROR,
            "canonical static permit manifest is unavailable or invalid",
        )

    asset_type = request.get("asset_type")
    provider = request.get("provider")
    if asset_type not in _ALLOWED_ASSET_TYPES:
        return _error(request_id, "OPENBB_UNSUPPORTED", "asset type is not approved for the runner")
    allowed_providers = _configured_provider_names()
    if not _provider_allow_list_is_exact(allowed_providers):
        return _error(
            request_id,
            "OPENBB_RUNNER_PROVIDER_ALLOW_LIST_INVALID",
            "OPENBB_ALLOWED_PROVIDERS must be exactly yfinance",
        )
    if not isinstance(provider, str) or provider != _EXACT_ALLOWED_PROVIDER_NAMES[0]:
        return _error(request_id, "OPENBB_UNSUPPORTED", "provider is not approved for the runner")
    if request.get("data_kind") != "bars":
        return _error(request_id, "OPENBB_UNSUPPORTED", "only bars are approved for this runner")
    # The current runner does not perform corporate-action adjustment, price
    # basis conversion, currency conversion, or unit conversion.  Refuse every
    # declared semantic axis instead of returning a provider-default series
    # under a caller's stronger label.
    if any(
        request.get(field_name) is not None
        for field_name in ("adjustment", "price_basis", "currency", "unit")
    ):
        return _error(
            request_id,
            "OPENBB_SEMANTICS_UNSUPPORTED",
            "runner only supports undeclared provider-native price semantics",
        )
    try:
        _yfinance_historical_window(request)
    except ValueError as exc:
        code = str(exc)
        if code.startswith("OPENBB_"):
            return _error(request_id, code, "request cannot be represented by this provider")
        return _error(request_id, "OPENBB_RUNNER_INVALID_REQUEST", "invalid provider request")
    artifact_attestation = _runtime_artifact_attestation()
    if artifact_attestation.status != "attested":
        # A source checkout, package version, or package file that differs
        # from the static reviewed artifact set must fail before OpenBB can
        # import its extension graph.  The public response stays bounded and
        # never serializes local paths or expected hashes.
        return _error(
            request_id,
            _RUNTIME_ARTIFACT_UNATTESTED,
            "the OpenBB yfinance runtime artifact is not attested",
        )
    if not _yfinance_outbound_end_bound_is_attested(
        artifact_attestation=artifact_attestation
    ):
        # This must remain before the OpenBB import. The installed helper's
        # post-fetch filtering cannot prove that yfinance received the parent
        # request's exclusive end bound, so importing it for a live request is
        # itself disallowed until a separate reviewed change supplies proof.
        return _error(
            request_id,
            _OUTBOUND_END_BOUND_UNATTESTED,
            "the yfinance outbound end bound is not attested",
        )
    if not _has_active_runtime_route_permit(request):
        return _error(
            request_id,
            "OPENBB_ROUTE_UNATTESTED",
            "no exact active runner permit matches this request",
        )

    try:
        from openbb import obb  # type: ignore[import-not-found]
    except ImportError:
        return _error(request_id, "OPENBB_RUNNER_UNAVAILABLE", "OpenBB import is unavailable")

    try:
        if provider != "yfinance":
            return _error(
                request_id, "OPENBB_UNSUPPORTED", "provider window semantics are not approved"
            )
        call_arguments = _yfinance_historical_arguments(request)
        result = _route(
            obb,
            asset_type=str(asset_type),
            endpoint=str(request["provider_endpoint"]),
        )(**call_arguments)
        raw_payload, raw_payload_sha256 = _raw_payload(_records(result))
        source_rows = raw_payload["records"]
        if not isinstance(source_rows, list) or any(
            not isinstance(row, dict) for row in source_rows
        ):
            raise ValueError("OPENBB_RAW_PAYLOAD_INVALID")
        records = _normalize_records(
            source_rows,
            start_at=_request_timestamp(request.get("start_at"), field_name="start_at"),
            end_at=_request_timestamp(request.get("end_at"), field_name="end_at"),
        )
    except ValueError as exc:
        code = str(exc)
        if code.startswith("OPENBB_"):
            return _error(request_id, code, "request cannot be represented by this provider")
        return _error(request_id, "OPENBB_RUNNER_INVALID_REQUEST", "invalid provider request")
    except Exception as exc:  # Runner boundary: serialise provider exceptions, never trace to web.
        return _error(request_id, _provider_error_code(exc), "provider request failed")

    source_revision = f"openbb-raw-sha256:{raw_payload_sha256}"
    return _emit(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "request": dict(request),
            "provider_id": f"openbb:{provider}",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source_revision": source_revision,
            "records": records,
            "raw_payload": raw_payload,
            "raw_payload_sha256": raw_payload_sha256,
            "warnings": [],
        }
    )


def _run(argv: list[str]) -> int:
    """Choose the local self-check without allowing undocumented CLI modes."""
    if argv == ["--self-check"]:
        return _emit(_self_check_payload())
    if argv:
        return _error(None, "OPENBB_RUNNER_ARGUMENT_INVALID", "unsupported runner argument")
    return main()


if __name__ == "__main__":
    raise SystemExit(_run(sys.argv[1:]))
