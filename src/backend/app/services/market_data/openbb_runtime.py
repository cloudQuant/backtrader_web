"""Fail-closed OpenBB runtime permit matrix.

The configured market list is an operator input, not a route grant.  A route
exists only when it appears in this module's reviewed permit matrix.  The
initial matrix is deliberately empty because the local yfinance adapter has
not yet proven that its actual outbound request preserves the parent request's
exclusive end bound.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

OPENBB_RUNTIME_PERMIT_MATRIX_VERSION = "openbb-runtime-permit-matrix-v1"
OPENBB_YFINANCE_OUTBOUND_END_BOUND_UNATTESTED = "OPENBB_YFINANCE_OUTBOUND_END_BOUND_UNATTESTED"
SUPPORTED_OPENBB_RUNNER_PROVIDERS = frozenset({"yfinance"})


@dataclass(frozen=True, slots=True)
class OpenBBRuntimeRoutePermit:
    """One fully reviewed OpenBB route.

    Future permits must identify every route-selection axis.  In particular,
    markets and asset types cannot be inferred from an environment list.
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


# This is intentionally explicit rather than a generated default.  Do not add
# an environment-driven fallback here: a provider's configuration does not
# prove its endpoint, licensing, semantic, or outbound-window contract.
OPENBB_RUNTIME_PERMIT_MATRIX: tuple[OpenBBRuntimeRoutePermit, ...] = ()


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
