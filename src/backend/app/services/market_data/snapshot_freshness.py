"""Server-owned freshness policies for locally persisted market snapshots.

Quote snapshots are not calendar-grid bars.  Their maximum age is a product
contract, not a hidden query-service constant or a client-controlled request
field.  This registry is intentionally static for the first Iteration 197
vertical: route approval still belongs to the source-policy registry, while
this module governs whether an already persisted exact snapshot is current
enough to satisfy a display read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext


class SnapshotFreshnessPolicyError(ValueError):
    """Stable failure when a snapshot product has no reviewed freshness SLA."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _text(value: str, *, field_name: str, maximum: int = 128) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must be a non-empty string up to {maximum} characters")
    return normalized


@dataclass(frozen=True, slots=True)
class SnapshotFreshnessPolicy:
    """One explicit SLA for an exact quote product and source-policy version.

    ``source_policy_id`` is already part of the query fingerprint, response,
    cursor binding, and persisted series identity.  Requiring it here makes a
    freshness SLA versioned by that same durable policy axis instead of letting
    a newer source route silently reuse a prior product's staleness budget.
    """

    policy_id: str
    dataset_code: str
    asset_types: frozenset[str]
    source_policy_ids: frozenset[str]
    max_age: timedelta
    data_kind: str = "quote_snapshot"

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text(self.policy_id, field_name="policy_id"))
        object.__setattr__(
            self, "dataset_code", _text(self.dataset_code, field_name="dataset_code", maximum=255)
        )
        object.__setattr__(self, "data_kind", _text(self.data_kind, field_name="data_kind"))
        if self.data_kind != "quote_snapshot":
            raise ValueError("snapshot freshness policies only support quote_snapshot")
        if not isinstance(self.asset_types, frozenset) or not self.asset_types:
            raise ValueError("asset_types must be a non-empty frozenset")
        normalized_asset_types = frozenset(
            _text(asset_type, field_name="asset_type") for asset_type in self.asset_types
        )
        if not isinstance(self.source_policy_ids, frozenset) or not self.source_policy_ids:
            raise ValueError("source_policy_ids must be a non-empty frozenset")
        normalized_source_policy_ids = frozenset(
            _text(source_policy_id, field_name="source_policy_id")
            for source_policy_id in self.source_policy_ids
        )
        if not isinstance(self.max_age, timedelta) or self.max_age <= timedelta(0):
            raise ValueError("max_age must be a positive timedelta")
        object.__setattr__(self, "asset_types", normalized_asset_types)
        object.__setattr__(self, "source_policy_ids", normalized_source_policy_ids)

    def matches(self, context: ResolvedMarketDataQueryContext) -> bool:
        """Return whether this policy exactly governs the resolved quote product."""
        return (
            context.query.dataset_code == self.dataset_code
            and context.query.data_kind == self.data_kind
            and context.identity.asset_type in self.asset_types
            and context.query.source_policy_id in self.source_policy_ids
        )


class SnapshotFreshnessPolicyRegistry:
    """Resolve exactly one product SLA without caller-supplied TTLs or wildcards."""

    def __init__(self, policies: tuple[SnapshotFreshnessPolicy, ...]) -> None:
        if not isinstance(policies, tuple) or not policies:
            raise ValueError("snapshot freshness registry requires a non-empty policy tuple")
        if any(not isinstance(policy, SnapshotFreshnessPolicy) for policy in policies):
            raise TypeError("snapshot freshness registry values must be SnapshotFreshnessPolicy")
        policy_ids = [policy.policy_id for policy in policies]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("snapshot freshness policy IDs must be unique")
        claimed_axes: set[tuple[str, str, str, str]] = set()
        for policy in policies:
            for asset_type in policy.asset_types:
                for source_policy_id in policy.source_policy_ids:
                    axis = (
                        policy.dataset_code,
                        policy.data_kind,
                        asset_type,
                        source_policy_id,
                    )
                    if axis in claimed_axes:
                        raise ValueError("snapshot freshness policies must not overlap")
                    claimed_axes.add(axis)
        self._policies = policies

    def resolve(self, context: ResolvedMarketDataQueryContext) -> SnapshotFreshnessPolicy:
        """Return the one reviewed SLA for a resolved quote query."""
        if not isinstance(context, ResolvedMarketDataQueryContext):
            raise TypeError("context must be a ResolvedMarketDataQueryContext")
        matches = tuple(policy for policy in self._policies if policy.matches(context))
        if len(matches) != 1:
            raise SnapshotFreshnessPolicyError("SNAPSHOT_FRESHNESS_POLICY_UNAVAILABLE")
        return matches[0]


DEFAULT_SNAPSHOT_FRESHNESS_POLICY_REGISTRY = SnapshotFreshnessPolicyRegistry(
    (
        SnapshotFreshnessPolicy(
            policy_id="market-quote-snapshot-display-v1",
            dataset_code="market.quote_snapshot",
            asset_types=frozenset({"stock", "futures", "bond", "fund", "option", "fx", "crypto"}),
            source_policy_ids=frozenset({"market-default-v1"}),
            max_age=timedelta(minutes=15),
        ),
    )
)


__all__ = [
    "DEFAULT_SNAPSHOT_FRESHNESS_POLICY_REGISTRY",
    "SnapshotFreshnessPolicy",
    "SnapshotFreshnessPolicyError",
    "SnapshotFreshnessPolicyRegistry",
]
