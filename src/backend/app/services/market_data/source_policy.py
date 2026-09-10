"""Server-owned, bounded provider policy for the local-first query path.

The public request carries a source-policy identifier so that the desired
provenance is part of a series identity.  It never carries a provider function,
an OpenBB extension, or an endpoint name.  This module resolves that identifier
to a reviewed sequence of adapters in process memory and verifies that every
selected route explicitly permits the resolved market and semantic axes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.services.market_data.providers import MarketDataProvider
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext


class MarketDataSourcePolicyError(ValueError):
    """Stable error raised when no approved policy can satisfy a query."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _nonempty_text(value: str, *, field_name: str, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must be a non-empty string up to {maximum} characters")
    return normalized


def _nonempty_text_set(
    value: frozenset[str],
    *,
    field_name: str,
    maximum: int = 128,
) -> frozenset[str]:
    if not isinstance(value, frozenset) or not value:
        raise ValueError(f"{field_name} must be a non-empty frozenset")
    return frozenset(_nonempty_text(item, field_name=field_name, maximum=maximum) for item in value)


def _semantic_capability_set(
    value: frozenset[str | None],
    *,
    field_name: str,
    maximum: int = 256,
) -> frozenset[str | None]:
    """Validate an explicit semantic capability set, retaining ``None`` precisely.

    ``None`` means that the route can serve an undeclared axis.  It never means
    wildcard support: every route must enumerate the values it can represent so
    a newly added public semantic value cannot silently reach a provider.
    """
    if not isinstance(value, frozenset) or not value:
        raise ValueError(f"{field_name} must be a non-empty frozenset")
    normalized: set[str | None] = set()
    for item in value:
        if item is None:
            normalized.add(None)
        else:
            normalized.add(_nonempty_text(item, field_name=field_name, maximum=maximum))
    return frozenset(normalized)


@dataclass(frozen=True, slots=True)
class MarketDataProviderRoute:
    """One explicitly capable adapter route within a named source policy.

    ``request_provider`` is the provider name passed to an adapter.  For
    example, AkShare uses ``akshare`` while the isolated OpenBB runner may use
    ``yfinance``.  ``expected_result_provider_ids`` closes the other half of
    that boundary: a route cannot return a receipt from an unrelated source and
    have it persisted under this policy.  Market and semantic sets are required
    rather than optional so a provider cannot inherit unintended capability.
    """

    route_id: str
    request_provider: str
    expected_result_provider_ids: frozenset[str]
    asset_types: frozenset[str]
    data_kinds: frozenset[str]
    frequencies: frozenset[str]
    markets: frozenset[str]
    adjustments: frozenset[str | None]
    price_bases: frozenset[str | None]
    currencies: frozenset[str | None]
    units: frozenset[str | None]
    adapter: MarketDataProvider
    # Retained routes that predate the public family binding may leave this
    # unset. A permit-derived route must set one exact family so a similarly
    # shaped product cannot reach the provider by sharing asset/market axes.
    family_id: str | None = None
    # This is a server-owned adapter dispatch token. It is copied to the
    # signed provider DTO; callers never select it through a public request.
    provider_endpoint: str | None = None
    # Product and fund-identity constraints are optional only for retained
    # generic routes.  A route that declares them must match the frozen
    # master-data identity before it can authorize a provider call.
    product_types: frozenset[str] | None = None
    fund_identity_kinds: frozenset[str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", _nonempty_text(self.route_id, field_name="route_id"))
        object.__setattr__(
            self,
            "request_provider",
            _nonempty_text(self.request_provider, field_name="request_provider"),
        )
        object.__setattr__(
            self,
            "expected_result_provider_ids",
            _nonempty_text_set(
                self.expected_result_provider_ids,
                field_name="expected_result_provider_id",
                maximum=255,
            ),
        )
        object.__setattr__(
            self,
            "asset_types",
            _nonempty_text_set(self.asset_types, field_name="asset_type"),
        )
        object.__setattr__(
            self,
            "data_kinds",
            _nonempty_text_set(self.data_kinds, field_name="data_kind"),
        )
        object.__setattr__(
            self,
            "frequencies",
            _nonempty_text_set(self.frequencies, field_name="frequency"),
        )
        object.__setattr__(
            self,
            "markets",
            _nonempty_text_set(self.markets, field_name="market"),
        )
        object.__setattr__(
            self,
            "adjustments",
            _semantic_capability_set(self.adjustments, field_name="adjustment"),
        )
        object.__setattr__(
            self,
            "price_bases",
            _semantic_capability_set(self.price_bases, field_name="price_basis"),
        )
        object.__setattr__(
            self,
            "currencies",
            _semantic_capability_set(self.currencies, field_name="currency", maximum=32),
        )
        object.__setattr__(
            self,
            "units",
            _semantic_capability_set(self.units, field_name="unit"),
        )
        if self.family_id is not None:
            object.__setattr__(
                self,
                "family_id",
                _nonempty_text(self.family_id, field_name="family_id"),
            )
        if self.provider_endpoint is not None:
            object.__setattr__(
                self,
                "provider_endpoint",
                _nonempty_text(self.provider_endpoint, field_name="provider_endpoint", maximum=256),
            )
        if self.product_types is not None:
            object.__setattr__(
                self,
                "product_types",
                _nonempty_text_set(self.product_types, field_name="product_type"),
            )
        if self.fund_identity_kinds is not None:
            if "fund" not in self.asset_types:
                raise ValueError("fund_identity_kinds require a fund route")
            object.__setattr__(
                self,
                "fund_identity_kinds",
                _nonempty_text_set(
                    self.fund_identity_kinds,
                    field_name="fund_identity_kind",
                ),
            )
        if not hasattr(self.adapter, "fetch"):
            raise TypeError("adapter must implement fetch")

    def supports(self, context: ResolvedMarketDataQueryContext) -> bool:
        """Return whether the route explicitly authorizes this resolved query."""
        venue = context.identity.venue
        frozen_identity = getattr(context.identity, "identity", None)
        product_type = getattr(frozen_identity, "product_type", None)
        details = getattr(frozen_identity, "details", None)
        fund_identity_kind = getattr(details, "fund_identity_kind", None)
        return (
            venue is not None
            and context.identity.asset_type in self.asset_types
            and context.query.data_kind in self.data_kinds
            and (context.query.frequency or "snapshot") in self.frequencies
            and venue in self.markets
            and context.query.adjustment in self.adjustments
            and context.query.price_basis in self.price_bases
            and context.query.currency in self.currencies
            and context.query.unit in self.units
            and (
                self.family_id is None
                or getattr(context.query, "family_id", None) == self.family_id
            )
            and (self.product_types is None or product_type in self.product_types)
            and (self.fund_identity_kinds is None or fund_identity_kind in self.fund_identity_kinds)
        )


@dataclass(frozen=True, slots=True)
class MarketDataSourcePolicy:
    """A priority-ordered, server-maintained route sequence and purpose grant."""

    policy_id: str
    allowed_purposes: frozenset[str]
    routes: tuple[MarketDataProviderRoute, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "policy_id", _nonempty_text(self.policy_id, field_name="policy_id")
        )
        object.__setattr__(
            self,
            "allowed_purposes",
            _nonempty_text_set(self.allowed_purposes, field_name="allowed_purpose"),
        )
        routes = tuple(self.routes)
        if not routes:
            raise ValueError("source policy requires at least one provider route")
        if any(not isinstance(route, MarketDataProviderRoute) for route in routes):
            raise TypeError("source policy routes must be MarketDataProviderRoute values")
        route_ids = [route.route_id for route in routes]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("source policy route_id values must be unique")
        object.__setattr__(self, "routes", routes)

    def allows_purpose(self, purpose: str) -> bool:
        """Return whether this server-owned policy permits the public purpose."""
        return purpose in self.allowed_purposes

    def routes_for(
        self,
        context: ResolvedMarketDataQueryContext,
    ) -> tuple[MarketDataProviderRoute, ...]:
        """Return only explicitly capable routes in their policy priority order."""
        return tuple(route for route in self.routes if route.supports(context))


class MarketDataSourcePolicyRegistry:
    """Immutable lookup for approved policies; it never selects a default."""

    def __init__(
        self,
        policies: Iterable[MarketDataSourcePolicy],
        *,
        _allow_empty: bool = False,
    ) -> None:
        normalized = tuple(policies)
        if not isinstance(_allow_empty, bool):
            raise TypeError("_allow_empty must be a bool")
        if not normalized:
            if not _allow_empty:
                raise ValueError("source policy registry requires at least one policy")
            self._policies: dict[str, MarketDataSourcePolicy] = {}
            return
        if any(not isinstance(policy, MarketDataSourcePolicy) for policy in normalized):
            raise TypeError("policies must be MarketDataSourcePolicy values")
        policy_ids = [policy.policy_id for policy in normalized]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("source policy identifiers must be unique")
        self._policies = {policy.policy_id: policy for policy in normalized}

    @classmethod
    def empty(cls) -> MarketDataSourcePolicyRegistry:
        """Return a deliberate no-policy registry for a fail-closed narrowed view.

        Deployment capability gates can remove every route from an otherwise
        reviewed policy.  Constructing a normal registry with no policies is
        intentionally invalid, but the narrowed view must still be representable
        without retaining a disabled route as an accidental fallback.  Its
        inherited ``resolve`` method returns ``SOURCE_POLICY_UNAVAILABLE`` for
        every public policy ID.
        """
        return cls((), _allow_empty=True)

    def resolve(self, policy_id: str | None) -> MarketDataSourcePolicy:
        """Resolve one exact policy ID without a fallback or prefix match."""
        if policy_id is None:
            raise MarketDataSourcePolicyError("SOURCE_POLICY_REQUIRED")
        try:
            normalized = _nonempty_text(policy_id, field_name="source_policy_id")
        except (TypeError, ValueError) as exc:
            raise MarketDataSourcePolicyError("SOURCE_POLICY_REQUIRED") from exc
        policy = self._policies.get(normalized)
        if policy is None:
            raise MarketDataSourcePolicyError("SOURCE_POLICY_UNAVAILABLE")
        return policy
