"""Durable, fail-closed market-data capability lifecycle evaluation.

Environment settings are only operator kill switches.  A setting can narrow a
capability that has durable evidence, but cannot grant one on its own.  The
ledger preserves the four lifecycle facts required by Iteration 197:
declaration, installed runtime, real verification, and deployment
authorization.  It also binds each record to a descriptor of the exact
server-owned route so an old attestation cannot silently authorize a changed
provider contract.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import MdCapabilityLedgerEntry
from app.schemas.market_data_platform import (
    MarketDataCapabilitiesResponse,
    MarketDataCapabilityStateResponse,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)

UTC = timezone.utc
_LEDGER_DESCRIPTOR_VERSION = "market-data-capability-ledger-v1"
_DEFAULT_POLICY_ID = "market-default-v1"
_RESEARCH_CACHE_FILL_PURPOSE = "research_cache_fill"

MARKET_DATA_QUERY_V2_CAPABILITY = "market-data.query-v2"
MARKET_DATA_ONLINE_FETCH_CAPABILITY = "market-data.online-fetch"
MARKET_DATA_RESEARCH_CACHE_FILL_CAPABILITY = "market-data.research-cache-fill"
MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_CAPABILITY = "market-data.research-backtest-bridge"


@dataclass(frozen=True, slots=True)
class _CapabilityDefinition:
    """One server-owned lifecycle record expected by the current deployment."""

    capability_id: str
    scope: Literal["rollout", "route"]
    descriptor_sha256: str
    route_id: str | None = None


@dataclass(frozen=True, slots=True)
class _LedgerLifecycle:
    """Durable lifecycle evidence before settings and dependency narrowing."""

    declared: bool
    installed: bool
    verified: bool
    authorized: bool
    effective: bool
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class MarketDataCapabilityEvaluation:
    """One request-scoped effective capability read and safe public response."""

    response: MarketDataCapabilitiesResponse
    effective_source_policies: MarketDataSourcePolicyRegistry
    effective_route_ids: frozenset[str]

    def route_is_effective(self, route_id: str) -> bool:
        """Return whether one current policy route passed every durable gate."""
        return route_id in self.effective_route_ids


class MarketDataCapabilityLedger:
    """Read current market-data capability evidence from the application DB.

    This class intentionally exposes no request-facing mutation method.  A
    deployment attestation is an operator-controlled append-only database
    record, not something a browser, environment variable, or provider name
    may mint at runtime.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(db, AsyncSession):
            raise TypeError("db must be an AsyncSession")
        self._db = db
        self._clock = clock or _utc_now

    async def evaluate(
        self,
        *,
        settings: object,
        source_policies: MarketDataSourcePolicyRegistry,
    ) -> MarketDataCapabilityEvaluation:
        """Intersect settings with durable evidence and the current source policy.

        The current project has one public source policy.  Resolving it by its
        exact stable ID prevents a future policy from becoming effective merely
        because it happens to have compatible route fields.
        """
        if not isinstance(source_policies, MarketDataSourcePolicyRegistry):
            raise TypeError("source_policies must be a MarketDataSourcePolicyRegistry")
        policy = source_policies.resolve(_DEFAULT_POLICY_ID)
        definitions = _definitions_for(policy)
        records, ledger_available = await self._records_for(
            tuple(definition.capability_id for definition in definitions)
        )
        now = _trusted_now(self._clock)

        lifecycles = {
            definition.capability_id: _lifecycle_for(
                definition=definition,
                records=records.get(definition.capability_id, ()),
                ledger_available=ledger_available,
                now=now,
            )
            for definition in definitions
        }
        definitions_by_id = {definition.capability_id: definition for definition in definitions}

        raw_query_enabled = _setting_enabled(settings, "MARKET_DATA_QUERY_V2_ENABLED")
        raw_online_enabled = raw_query_enabled and _setting_enabled(
            settings, "MARKET_DATA_ONLINE_FETCH_ENABLED"
        )
        raw_cache_fill_enabled = raw_online_enabled and _setting_enabled(
            settings, "MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED"
        )
        raw_bridge_enabled = raw_query_enabled and _setting_enabled(
            settings, "MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED"
        )

        states: list[MarketDataCapabilityStateResponse] = []
        query_state = _state_from_lifecycle(
            definition=definitions_by_id[MARKET_DATA_QUERY_V2_CAPABILITY],
            lifecycle=lifecycles[MARKET_DATA_QUERY_V2_CAPABILITY],
            settings_enabled=raw_query_enabled,
            settings_reason="CAPABILITY_SETTING_DISABLED",
        )
        states.append(query_state)

        route_states: list[MarketDataCapabilityStateResponse] = []
        for definition in definitions:
            if definition.scope != "route":
                continue
            route_states.append(
                _state_from_lifecycle(
                    definition=definition,
                    lifecycle=lifecycles[definition.capability_id],
                    settings_enabled=raw_online_enabled,
                    settings_reason=(
                        "CAPABILITY_DEPENDENCY_DISABLED"
                        if raw_query_enabled
                        else "CAPABILITY_SETTING_DISABLED"
                    ),
                    dependency_enabled=query_state.effective,
                )
            )

        effective_route_ids = frozenset(
            state.route_id
            for state in route_states
            if state.effective and state.route_id is not None
        )
        online_state = _state_from_lifecycle(
            definition=definitions_by_id[MARKET_DATA_ONLINE_FETCH_CAPABILITY],
            lifecycle=lifecycles[MARKET_DATA_ONLINE_FETCH_CAPABILITY],
            settings_enabled=raw_online_enabled,
            settings_reason=(
                "CAPABILITY_DEPENDENCY_DISABLED"
                if raw_query_enabled
                else "CAPABILITY_SETTING_DISABLED"
            ),
            dependency_enabled=query_state.effective,
            extra_dependency_enabled=bool(effective_route_ids),
            extra_dependency_reason="CAPABILITY_ROUTE_UNAVAILABLE",
        )
        states.append(online_state)

        cache_fill_state = _state_from_lifecycle(
            definition=definitions_by_id[MARKET_DATA_RESEARCH_CACHE_FILL_CAPABILITY],
            lifecycle=lifecycles[MARKET_DATA_RESEARCH_CACHE_FILL_CAPABILITY],
            settings_enabled=raw_cache_fill_enabled,
            settings_reason=(
                "CAPABILITY_DEPENDENCY_DISABLED"
                if raw_online_enabled
                else "CAPABILITY_SETTING_DISABLED"
            ),
            dependency_enabled=online_state.effective,
        )
        states.append(cache_fill_state)

        bridge_state = _state_from_lifecycle(
            definition=definitions_by_id[MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_CAPABILITY],
            lifecycle=lifecycles[MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_CAPABILITY],
            settings_enabled=raw_bridge_enabled,
            settings_reason=(
                "CAPABILITY_DEPENDENCY_DISABLED"
                if raw_query_enabled
                else "CAPABILITY_SETTING_DISABLED"
            ),
            dependency_enabled=query_state.effective,
        )
        states.append(bridge_state)
        states.extend(route_states)

        response = MarketDataCapabilitiesResponse(
            query_v2_enabled=query_state.effective,
            online_fetch_enabled=online_state.effective,
            research_cache_fill_enabled=cache_fill_state.effective,
            research_backtest_bridge_enabled=bridge_state.effective,
            capability_states=tuple(states),
        )
        return MarketDataCapabilityEvaluation(
            response=response,
            effective_source_policies=_policy_with_effective_purposes(
                policy=policy,
                cache_fill_enabled=cache_fill_state.effective,
            ),
            effective_route_ids=effective_route_ids,
        )

    async def _records_for(
        self,
        capability_ids: tuple[str, ...],
    ) -> tuple[Mapping[str, tuple[MdCapabilityLedgerEntry, ...]], bool]:
        """Load all relevant revisions, preserving ambiguity for fail-closed reads."""
        try:
            result = await self._db.execute(
                select(MdCapabilityLedgerEntry).where(
                    MdCapabilityLedgerEntry.capability_id.in_(capability_ids)
                )
            )
        except SQLAlchemyError:
            # A missing migration, inaccessible database, or transient read
            # failure must not fall back to settings-only enablement.  Roll
            # back the failed read transaction so the caller may still return
            # a typed disabled state or perform a local-only query.
            await self._db.rollback()
            return MappingProxyType({}), False
        grouped: dict[str, list[MdCapabilityLedgerEntry]] = {}
        for record in result.scalars():
            grouped.setdefault(record.capability_id, []).append(record)
        return MappingProxyType(
            {capability_id: tuple(entries) for capability_id, entries in grouped.items()}
        ), True


def rollout_capability_descriptor_sha256(capability_id: str) -> str:
    """Return the fixed descriptor required by one global rollout capability."""
    normalized = _required_text(capability_id, field_name="capability_id", maximum=192)
    return _sha256(
        {
            "version": _LEDGER_DESCRIPTOR_VERSION,
            "scope": "rollout",
            "capability_id": normalized,
        }
    )


def route_capability_id(route_id: str) -> str:
    """Return the stable ledger key for one reviewed source-policy route."""
    normalized = _required_text(route_id, field_name="route_id", maximum=128)
    return f"market-data.route:{normalized}"


def route_capability_descriptor_sha256(route: MarketDataProviderRoute) -> str:
    """Hash every reviewed route axis except its process-local adapter object."""
    if not isinstance(route, MarketDataProviderRoute):
        raise TypeError("route must be a MarketDataProviderRoute")
    return _sha256(
        {
            "version": _LEDGER_DESCRIPTOR_VERSION,
            "scope": "route",
            "capability_id": route_capability_id(route.route_id),
            "route_id": route.route_id,
            "request_provider": route.request_provider,
            "expected_result_provider_ids": sorted(route.expected_result_provider_ids),
            "asset_types": sorted(route.asset_types),
            "data_kinds": sorted(route.data_kinds),
            "frequencies": sorted(route.frequencies),
            "markets": sorted(route.markets),
            "adjustments": _axis_payload(route.adjustments),
            "price_bases": _axis_payload(route.price_bases),
            "currencies": _axis_payload(route.currencies),
            "units": _axis_payload(route.units),
            "family_id": route.family_id,
            "family_contract_version": route.family_contract_version,
            "provider_endpoint": route.provider_endpoint,
            "product_types": sorted(route.product_types)
            if route.product_types is not None
            else None,
            "fund_identity_kinds": (
                sorted(route.fund_identity_kinds) if route.fund_identity_kinds is not None else None
            ),
        }
    )


def _definitions_for(policy: MarketDataSourcePolicy) -> tuple[_CapabilityDefinition, ...]:
    """Return one ordered expected record for each global gate and policy route."""
    if not isinstance(policy, MarketDataSourcePolicy):
        raise TypeError("policy must be a MarketDataSourcePolicy")
    rollout_ids = (
        MARKET_DATA_QUERY_V2_CAPABILITY,
        MARKET_DATA_ONLINE_FETCH_CAPABILITY,
        MARKET_DATA_RESEARCH_CACHE_FILL_CAPABILITY,
        MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_CAPABILITY,
    )
    definitions: list[_CapabilityDefinition] = [
        _CapabilityDefinition(
            capability_id=capability_id,
            scope="rollout",
            descriptor_sha256=rollout_capability_descriptor_sha256(capability_id),
        )
        for capability_id in rollout_ids
    ]
    definitions.extend(
        _CapabilityDefinition(
            capability_id=route_capability_id(route.route_id),
            scope="route",
            route_id=route.route_id,
            descriptor_sha256=route_capability_descriptor_sha256(route),
        )
        for route in policy.routes
    )
    capability_ids = tuple(definition.capability_id for definition in definitions)
    if len(capability_ids) != len(set(capability_ids)):
        raise ValueError("source policy route IDs must map to unique capability IDs")
    return tuple(definitions)


def _lifecycle_for(
    *,
    definition: _CapabilityDefinition,
    records: Sequence[MdCapabilityLedgerEntry],
    ledger_available: bool,
    now: datetime,
) -> _LedgerLifecycle:
    """Evaluate one durable record without accepting overlapping revisions."""
    if not ledger_available:
        return _LedgerLifecycle(False, False, False, False, False, "CAPABILITY_LEDGER_UNAVAILABLE")

    current = tuple(record for record in records if _record_is_current(record, now=now))
    if len(current) > 1:
        return _LedgerLifecycle(False, False, False, False, False, "CAPABILITY_LEDGER_AMBIGUOUS")
    if not current:
        if any(
            _as_utc(record.effective_until) <= now for record in records if record.effective_until
        ):
            return _LedgerLifecycle(False, False, False, False, False, "CAPABILITY_LEDGER_EXPIRED")
        if records:
            return _LedgerLifecycle(
                False, False, False, False, False, "CAPABILITY_LEDGER_NOT_CURRENT"
            )
        return _LedgerLifecycle(False, False, False, False, False, "CAPABILITY_LEDGER_MISSING")

    record = current[0]
    declared = bool(record.declared_capability)
    installed = bool(record.installed_capability)
    verified = bool(record.verified_capability)
    authorized = bool(record.authorized_capability)
    if record.descriptor_sha256 != definition.descriptor_sha256:
        return _LedgerLifecycle(
            declared,
            installed,
            verified,
            authorized,
            False,
            "CAPABILITY_DESCRIPTOR_MISMATCH",
        )
    if not declared:
        return _LedgerLifecycle(
            declared, installed, verified, authorized, False, "CAPABILITY_UNDECLARED"
        )
    if not installed:
        return _LedgerLifecycle(
            declared, installed, verified, authorized, False, "CAPABILITY_NOT_INSTALLED"
        )
    if not verified:
        return _LedgerLifecycle(
            declared, installed, verified, authorized, False, "CAPABILITY_NOT_VERIFIED"
        )
    if not _attestation_is_current(record.verified_at, record.verified_until, now=now):
        return _LedgerLifecycle(
            declared,
            installed,
            verified,
            authorized,
            False,
            "CAPABILITY_VERIFICATION_EXPIRED",
        )
    if not authorized:
        return _LedgerLifecycle(
            declared, installed, verified, authorized, False, "CAPABILITY_NOT_AUTHORIZED"
        )
    if not _attestation_is_current(record.authorized_at, record.authorized_until, now=now):
        return _LedgerLifecycle(
            declared,
            installed,
            verified,
            authorized,
            False,
            "CAPABILITY_AUTHORIZATION_EXPIRED",
        )
    return _LedgerLifecycle(declared, installed, verified, authorized, True, None)


def _state_from_lifecycle(
    *,
    definition: _CapabilityDefinition,
    lifecycle: _LedgerLifecycle,
    settings_enabled: bool,
    settings_reason: str,
    dependency_enabled: bool = True,
    extra_dependency_enabled: bool = True,
    extra_dependency_reason: str = "CAPABILITY_DEPENDENCY_DISABLED",
) -> MarketDataCapabilityStateResponse:
    """Render a safe public state after applying settings and dependency gates."""
    if not lifecycle.effective:
        effective = False
        reason_code = lifecycle.reason_code
    elif not settings_enabled:
        effective = False
        reason_code = settings_reason
    elif not dependency_enabled:
        effective = False
        reason_code = "CAPABILITY_DEPENDENCY_DISABLED"
    elif not extra_dependency_enabled:
        effective = False
        reason_code = extra_dependency_reason
    else:
        effective = True
        reason_code = None
    return MarketDataCapabilityStateResponse(
        capability_id=definition.capability_id,
        scope=definition.scope,
        route_id=definition.route_id,
        declared=lifecycle.declared,
        installed=lifecycle.installed,
        verified=lifecycle.verified,
        authorized=lifecycle.authorized,
        effective=effective,
        reason_code=reason_code,
    )


def _policy_with_effective_purposes(
    *,
    policy: MarketDataSourcePolicy,
    cache_fill_enabled: bool,
) -> MarketDataSourcePolicyRegistry:
    """Retain local-read policy while narrowing only purpose escalation.

    A deployment lifecycle record approves an *online collection route*, not
    deletion of facts previously persisted under the reviewed source policy.
    Keeping every reviewed route here allows authenticated ``local_only`` and
    local-first cache rereads to retain their source authorization filter.
    ``MarketDataCapabilityEvaluation.effective_route_ids`` is passed separately
    to the query service and is the sole provider-I/O route selector.
    """
    if not isinstance(policy, MarketDataSourcePolicy):
        raise TypeError("policy must be a MarketDataSourcePolicy")
    if not isinstance(cache_fill_enabled, bool):
        raise TypeError("cache_fill_enabled must be a bool")
    purposes = policy.allowed_purposes
    if not cache_fill_enabled:
        purposes = purposes - frozenset({_RESEARCH_CACHE_FILL_PURPOSE})
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id=policy.policy_id,
                allowed_purposes=purposes,
                routes=policy.routes,
            ),
        )
    )


def _record_is_current(record: MdCapabilityLedgerEntry, *, now: datetime) -> bool:
    """Return whether a revision's activation window contains ``now``."""
    return _as_utc(record.effective_from) <= now and (
        record.effective_until is None or _as_utc(record.effective_until) > now
    )


def _attestation_is_current(
    recorded_at: datetime | None,
    expires_at: datetime | None,
    *,
    now: datetime,
) -> bool:
    """Require a non-future, finite attestation window for current enablement."""
    if recorded_at is None or expires_at is None:
        return False
    return _as_utc(recorded_at) <= now < _as_utc(expires_at)


def _setting_enabled(settings: object, name: str) -> bool:
    """Treat absent, malformed, or false rollout settings as disabled."""
    return bool(getattr(settings, name, False))


def _axis_payload(values: frozenset[str | None]) -> list[str | None]:
    """Canonicalize semantic axes that intentionally allow an explicit null."""
    return sorted(values, key=lambda item: (item is not None, item or ""))


def _sha256(payload: Mapping[str, object]) -> str:
    """Hash one canonical descriptor without retaining sensitive evidence."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must be a non-empty string up to {maximum} characters")
    return normalized


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite test values and production UTC timestamps."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _trusted_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("capability ledger clock must return an aware datetime")
    return value.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)
