"""Fail-closed OpenBB runtime permits from one static, reviewed manifest.

The configured market list is an operator input, not a route grant.  A route
exists only when it appears in the package-local JSON manifest that is also
read directly by the isolated runner.  The initial manifest is deliberately
empty because the local yfinance adapter has not yet proven that its actual
outbound request preserves the parent request's exclusive end bound.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_MANIFEST_VERSION = "openbb-runtime-permit-manifest-v1"
_MANIFEST_PATH = Path(__file__).with_name("openbb_runtime_permit_manifest.json")


@dataclass(frozen=True, slots=True)
class OpenBBRuntimeRoutePermit:
    """One fully reviewed OpenBB route.

    Future permits must identify every route-selection axis.  In particular,
    markets and asset types cannot be inferred from an environment list.
    """

    route_id: str
    family_id: str
    family_contract_version: str
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


@dataclass(frozen=True, slots=True)
class _OpenBBRuntimePermitManifest:
    """Validated representation of the pure-data runner permit manifest."""

    version: str
    permit_matrix_version: str
    supported_runner_providers: tuple[str, ...]
    dangerous_extension_environment_keys: tuple[str, ...]
    runtime_route_permits: tuple[OpenBBRuntimeRoutePermit, ...]


def _manifest_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:{field_name}")
    return value.strip()


def _manifest_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _manifest_text(value, field_name=field_name)


def _manifest_text_list(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError(f"OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:{field_name}")
    parsed = tuple(_manifest_text(item, field_name=field_name) for item in value)
    if not parsed or len(set(parsed)) != len(parsed):
        raise RuntimeError(f"OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:{field_name}")
    return parsed


def _manifest_permit(value: object) -> OpenBBRuntimeRoutePermit:
    if not isinstance(value, Mapping):
        raise RuntimeError("OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:runtime_route_permits")
    return OpenBBRuntimeRoutePermit(
        route_id=_manifest_text(value.get("route_id"), field_name="route_id"),
        family_id=_manifest_text(value.get("family_id"), field_name="family_id"),
        family_contract_version=_manifest_text(
            value.get("family_contract_version"), field_name="family_contract_version"
        ),
        provider=_manifest_text(value.get("provider"), field_name="provider"),
        asset_type=_manifest_text(value.get("asset_type"), field_name="asset_type"),
        market=_manifest_text(value.get("market"), field_name="market"),
        data_kind=_manifest_text(value.get("data_kind"), field_name="data_kind"),
        frequency=_manifest_text(value.get("frequency"), field_name="frequency"),
        adjustment=_manifest_optional_text(value.get("adjustment"), field_name="adjustment"),
        price_basis=_manifest_optional_text(value.get("price_basis"), field_name="price_basis"),
        currency=_manifest_optional_text(value.get("currency"), field_name="currency"),
        unit=_manifest_optional_text(value.get("unit"), field_name="unit"),
        endpoint=_manifest_text(value.get("endpoint"), field_name="endpoint"),
    )


def _load_openbb_runtime_permit_manifest() -> _OpenBBRuntimePermitManifest:
    """Read one package-local data file and reject ambiguous permit shape."""
    try:
        loaded: Any = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID") from exc
    if not isinstance(loaded, Mapping):
        raise RuntimeError("OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID")
    version = _manifest_text(loaded.get("manifest_version"), field_name="manifest_version")
    if version != _MANIFEST_VERSION:
        raise RuntimeError("OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:manifest_version")
    providers = _manifest_text_list(
        loaded.get("supported_runner_providers"),
        field_name="supported_runner_providers",
    )
    dangerous_keys = _manifest_text_list(
        loaded.get("dangerous_extension_environment_keys"),
        field_name="dangerous_extension_environment_keys",
    )
    permit_values = loaded.get("runtime_route_permits")
    if not isinstance(permit_values, list):
        raise RuntimeError("OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:runtime_route_permits")
    permits = tuple(_manifest_permit(value) for value in permit_values)
    if len({permit.route_id for permit in permits}) != len(permits) or any(
        permit.provider not in providers for permit in permits
    ):
        raise RuntimeError("OPENBB_RUNTIME_PERMIT_MANIFEST_INVALID:runtime_route_permits")
    return _OpenBBRuntimePermitManifest(
        version=version,
        permit_matrix_version=_manifest_text(
            loaded.get("permit_matrix_version"), field_name="permit_matrix_version"
        ),
        supported_runner_providers=providers,
        dangerous_extension_environment_keys=dangerous_keys,
        runtime_route_permits=permits,
    )


_RUNTIME_PERMIT_MANIFEST = _load_openbb_runtime_permit_manifest()
OPENBB_RUNTIME_PERMIT_MANIFEST_VERSION = _RUNTIME_PERMIT_MANIFEST.version
OPENBB_RUNTIME_PERMIT_MATRIX_VERSION = _RUNTIME_PERMIT_MANIFEST.permit_matrix_version
SUPPORTED_OPENBB_RUNNER_PROVIDERS = frozenset(_RUNTIME_PERMIT_MANIFEST.supported_runner_providers)
DANGEROUS_OPENBB_EXTENSION_ENVIRONMENT_KEYS = frozenset(
    _RUNTIME_PERMIT_MANIFEST.dangerous_extension_environment_keys
)


# This is intentionally read from pure data rather than constructed from an
# environment default. Do not add an environment-driven fallback here: a
# provider's configuration does not prove its endpoint, licensing, semantic,
# or outbound-window contract.
OPENBB_RUNTIME_PERMIT_MATRIX: tuple[OpenBBRuntimeRoutePermit, ...] = (
    _RUNTIME_PERMIT_MANIFEST.runtime_route_permits
)


def approved_openbb_runtime_route_permits(
    provider: str,
    allowed_markets: tuple[str, ...],
) -> tuple[OpenBBRuntimeRoutePermit, ...]:
    """Return only explicit permits that intersect the operator market list.

    With the initial empty matrix this always returns no routes.  Keeping the
    filtering here makes a later, reviewed addition bounded by both the exact
    permit and the operator's narrower deployment allow-list.
    """
    permitted_markets = frozenset(allowed_markets)
    return tuple(
        permit
        for permit in OPENBB_RUNTIME_PERMIT_MATRIX
        if permit.provider == provider and permit.market in permitted_markets
    )


def openbb_runtime_registration_status(
    *,
    provider: str | None,
    allowed_markets: tuple[str, ...],
) -> Literal[
    "not_configured_no_allowed_markets",
    "not_configured_runtime_permits_unattested",
]:
    """Give bootstrap a safe, operator-readable reason for no provider row."""
    if provider is None or not allowed_markets:
        return "not_configured_no_allowed_markets"
    return "not_configured_runtime_permits_unattested"
