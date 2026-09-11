"""Durable lifecycle gates for Iteration 197 market-data capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.api.data.queries import get_market_data_access_authorizer, get_market_data_query_service
from app.db.database import async_session_maker
from app.main import app
from app.models.market_data_platform import ImmutableMarketDataRecordError, MdCapabilityLedgerEntry
from app.services.market_data.access import (
    MarketDataAccessAuthorizer,
    MarketDataPrincipal,
)
from app.services.market_data.capability_ledger import (
    MARKET_DATA_ONLINE_FETCH_CAPABILITY,
    MARKET_DATA_QUERY_V2_CAPABILITY,
    MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_CAPABILITY,
    MARKET_DATA_RESEARCH_CACHE_FILL_CAPABILITY,
    MarketDataCapabilityEvaluation,
    MarketDataCapabilityLedger,
    rollout_capability_descriptor_sha256,
    route_capability_descriptor_sha256,
    route_capability_id,
)
from app.services.market_data.source_policy import (
    MarketDataLocalReadSource,
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
_ROLLOUT_IDS = (
    MARKET_DATA_QUERY_V2_CAPABILITY,
    MARKET_DATA_ONLINE_FETCH_CAPABILITY,
    MARKET_DATA_RESEARCH_CACHE_FILL_CAPABILITY,
    MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_CAPABILITY,
)


class _NoNetworkProvider:
    async def fetch(self, _request: object) -> object:
        raise AssertionError("capability ledger tests must not call providers")


class _ReadAuthorizer(MarketDataAccessAuthorizer):
    """Minimal current-read boundary for the HTTP capability checks."""

    def __init__(self) -> None:
        self.principal = MarketDataPrincipal(
            principal_id="ledger-user",
            principal_scope="principal-v1:ledger-user",
            tenant_scope="default",
            roles=("user",),
            permissions=("data:read",),
            entitlement_revision="e" * 64,
        )

    async def principal_for_user(self, _user: object) -> MarketDataPrincipal:
        return self.principal


class _QueryServiceDouble:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("missing capability evidence must reject before execution")


def _settings(**overrides: bool) -> SimpleNamespace:
    values: dict[str, object] = {
        "MARKET_DATA_QUERY_V2_ENABLED": True,
        "MARKET_DATA_ONLINE_FETCH_ENABLED": True,
        "MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED": True,
        "MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED": True,
        "MARKET_DATA_OPENBB_PROVIDER": "yfinance",
        "MARKET_DATA_OPENBB_ALLOWED_MARKETS": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _route() -> MarketDataProviderRoute:
    return MarketDataProviderRoute(
        route_id="ledger-stock-primary-v1",
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=_NoNetworkProvider(),
    )


def _secondary_route() -> MarketDataProviderRoute:
    return MarketDataProviderRoute(
        route_id="ledger-fund-primary-v1",
        request_provider="akshare",
        expected_result_provider_ids=frozenset({"akshare"}),
        asset_types=frozenset({"fund"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
        adapter=_NoNetworkProvider(),
    )


def _local_source() -> MarketDataLocalReadSource:
    return MarketDataLocalReadSource(
        local_source_id="ledger-stock-history-local-read-v1",
        source_registry_id="ledger-stock-history-warehouse",
        asset_types=frozenset({"stock"}),
        data_kinds=frozenset({"bars"}),
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE"}),
        adjustments=frozenset({"qfq"}),
        price_bases=frozenset({"close"}),
        currencies=frozenset({"CNY"}),
        units=frozenset({"share"}),
    )


def test_route_capability_descriptor_binds_the_private_kline_family_contract_pair() -> None:
    """An old route attestation cannot authorize the generic stock-bars product."""
    kline_route = replace(
        _route(),
        family_id="stock.kline_legacy",
        family_contract_version="market-data-kline-v1",
        provider_endpoint="stock_zh_a_hist",
    )
    baseline = route_capability_descriptor_sha256(kline_route)

    assert baseline != route_capability_descriptor_sha256(
        replace(
            kline_route,
            family_id="stock.realtime",
            family_contract_version="market-data-family-v1",
        )
    )
    assert baseline != route_capability_descriptor_sha256(
        replace(kline_route, provider_endpoint="equity.price.historical")
    )


def _policy(
    *,
    include_cache_fill: bool = True,
    include_secondary_route: bool = False,
    include_local_source: bool = False,
) -> MarketDataSourcePolicyRegistry:
    purposes = frozenset({"display", "research", "backtest"})
    if include_cache_fill:
        purposes = purposes | frozenset({"research_cache_fill"})
    routes = (_route(),)
    if include_secondary_route:
        routes = (*routes, _secondary_route())
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id="market-default-v1",
                allowed_purposes=purposes,
                routes=routes,
                local_sources=(_local_source(),) if include_local_source else (),
            ),
        )
    )


def _entry(
    *,
    capability_id: str,
    revision: int,
    descriptor_sha256: str,
    now: datetime = NOW,
    authorization_until: datetime | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
) -> MdCapabilityLedgerEntry:
    return MdCapabilityLedgerEntry(
        capability_id=capability_id,
        revision=revision,
        descriptor_sha256=descriptor_sha256,
        evidence_sha256="e" * 64,
        declared_capability=True,
        installed_capability=True,
        verified_capability=True,
        verified_at=now - timedelta(hours=1),
        verified_until=now + timedelta(hours=1),
        authorized_capability=True,
        authorized_at=now - timedelta(hours=1),
        authorized_until=authorization_until or now + timedelta(hours=1),
        effective_from=effective_from or now - timedelta(hours=1),
        effective_until=effective_until,
    )


async def _add_complete_evidence(
    *,
    policy: MarketDataSourcePolicyRegistry,
    now: datetime = NOW,
    descriptor_overrides: Mapping[str, str] | None = None,
    authorization_until_overrides: Mapping[str, datetime] | None = None,
) -> None:
    resolved = policy.resolve("market-default-v1")
    descriptor_overrides = descriptor_overrides or {}
    authorization_until_overrides = authorization_until_overrides or {}
    async with async_session_maker() as session:
        for revision, capability_id in enumerate(_ROLLOUT_IDS, start=1):
            session.add(
                _entry(
                    capability_id=capability_id,
                    revision=revision,
                    descriptor_sha256=descriptor_overrides.get(
                        capability_id,
                        rollout_capability_descriptor_sha256(capability_id),
                    ),
                    now=now,
                    authorization_until=authorization_until_overrides.get(capability_id),
                )
            )
        for revision, route in enumerate(resolved.routes, start=1):
            capability_id = route_capability_id(route.route_id)
            session.add(
                _entry(
                    capability_id=capability_id,
                    revision=revision,
                    descriptor_sha256=descriptor_overrides.get(
                        capability_id,
                        route_capability_descriptor_sha256(route),
                    ),
                    now=now,
                    authorization_until=authorization_until_overrides.get(capability_id),
                )
            )
        await session.commit()


async def _evaluate(
    *,
    policy: MarketDataSourcePolicyRegistry,
    settings: object | None = None,
    now: datetime = NOW,
):
    async with async_session_maker() as session:
        return await MarketDataCapabilityLedger(session, clock=lambda: now).evaluate(
            settings=settings or _settings(),
            source_policies=policy,
        )


def _states_by_id(evaluation: MarketDataCapabilityEvaluation) -> dict[str, object]:
    return {state.capability_id: state for state in evaluation.response.capability_states}


@pytest.mark.asyncio
async def test_enabled_settings_without_durable_entries_fail_closed() -> None:
    """Environment flags cannot mint a market-data capability by themselves."""
    policy = _policy()

    evaluation = await _evaluate(policy=policy)
    states = _states_by_id(evaluation)

    assert evaluation.response.query_v2_enabled is False
    assert evaluation.response.online_fetch_enabled is False
    assert evaluation.response.research_cache_fill_enabled is False
    assert evaluation.response.research_backtest_bridge_enabled is False
    assert states[MARKET_DATA_QUERY_V2_CAPABILITY].reason_code == "CAPABILITY_LEDGER_MISSING"
    assert states[MARKET_DATA_ONLINE_FETCH_CAPABILITY].reason_code == "CAPABILITY_LEDGER_MISSING"
    assert states[route_capability_id("ledger-stock-primary-v1")].reason_code == (
        "CAPABILITY_LEDGER_MISSING"
    )
    assert evaluation.effective_route_ids == frozenset()
    local_read_policy = evaluation.effective_source_policies.resolve("market-default-v1")
    assert tuple(route.route_id for route in local_read_policy.routes) == (
        "ledger-stock-primary-v1",
    )
    assert "research_cache_fill" not in local_read_policy.allowed_purposes


@pytest.mark.asyncio
async def test_complete_current_records_enable_only_the_matching_policy() -> None:
    """All durable lifecycle evidence plus settings enables the reviewed route set."""
    policy = _policy()
    await _add_complete_evidence(policy=policy)

    evaluation = await _evaluate(policy=policy)
    states = _states_by_id(evaluation)

    assert evaluation.response.query_v2_enabled is True
    assert evaluation.response.online_fetch_enabled is True
    assert evaluation.response.research_cache_fill_enabled is True
    assert evaluation.response.research_backtest_bridge_enabled is True
    assert evaluation.effective_route_ids == frozenset({"ledger-stock-primary-v1"})
    assert states[route_capability_id("ledger-stock-primary-v1")].effective is True
    assert all(state.reason_code is None for state in states.values())
    assert (
        "research_cache_fill"
        in evaluation.effective_source_policies.resolve("market-default-v1").allowed_purposes
    )


@pytest.mark.asyncio
async def test_descriptor_mismatch_cannot_be_overridden_by_env() -> None:
    """A self-consistent flag set still fails when durable route evidence is wrong."""
    policy = _policy()
    route = policy.resolve("market-default-v1").routes[0]
    await _add_complete_evidence(
        policy=policy,
        descriptor_overrides={route_capability_id(route.route_id): "d" * 64},
    )

    mismatched_evaluation = await _evaluate(policy=policy)
    mismatched_states = _states_by_id(mismatched_evaluation)
    assert mismatched_evaluation.response.query_v2_enabled is True
    assert mismatched_evaluation.response.online_fetch_enabled is False
    assert mismatched_states[route_capability_id(route.route_id)].reason_code == (
        "CAPABILITY_DESCRIPTOR_MISMATCH"
    )


@pytest.mark.asyncio
async def test_effective_online_routes_exclude_disabled_unrelated_routes_but_keep_local_policy() -> (
    None
):
    """A stale sibling cannot fetch while its prior local facts remain readable."""
    policy = _policy(include_secondary_route=True)
    secondary = policy.resolve("market-default-v1").routes[1]
    await _add_complete_evidence(
        policy=policy,
        descriptor_overrides={route_capability_id(secondary.route_id): "d" * 64},
    )

    evaluation = await _evaluate(policy=policy)
    states = _states_by_id(evaluation)
    local_read_policy = evaluation.effective_source_policies.resolve("market-default-v1")

    assert evaluation.response.online_fetch_enabled is True
    assert evaluation.effective_route_ids == frozenset({"ledger-stock-primary-v1"})
    assert tuple(route.route_id for route in local_read_policy.routes) == (
        "ledger-stock-primary-v1",
        "ledger-fund-primary-v1",
    )
    assert states[route_capability_id(secondary.route_id)].effective is False
    assert states[route_capability_id(secondary.route_id)].reason_code == (
        "CAPABILITY_DESCRIPTOR_MISMATCH"
    )


@pytest.mark.asyncio
async def test_effective_policy_preserves_local_read_sources_when_purposes_are_narrowed() -> None:
    """A rollout gate may narrow purposes but cannot erase approved local facts."""
    policy = _policy(include_local_source=True)

    evaluation = await _evaluate(policy=policy)
    effective_policy = evaluation.effective_source_policies.resolve("market-default-v1")

    assert effective_policy.local_sources == (_local_source(),)
    assert tuple(route.route_id for route in effective_policy.routes) == (
        "ledger-stock-primary-v1",
    )
    assert "research_cache_fill" not in effective_policy.allowed_purposes


@pytest.mark.asyncio
async def test_expired_authorization_fails_closed_even_when_every_flag_is_enabled() -> None:
    """Authorization expiry is evaluated from the database clock window, not env."""
    policy = _policy()
    await _add_complete_evidence(
        policy=policy,
        authorization_until_overrides={MARKET_DATA_QUERY_V2_CAPABILITY: NOW - timedelta(minutes=1)},
    )

    evaluation = await _evaluate(policy=policy)
    state = _states_by_id(evaluation)[MARKET_DATA_QUERY_V2_CAPABILITY]
    assert evaluation.response.query_v2_enabled is False
    assert state.reason_code == "CAPABILITY_AUTHORIZATION_EXPIRED"


@pytest.mark.asyncio
async def test_overlapping_current_revisions_fail_closed_without_selecting_a_newest_row() -> None:
    """The reader rejects two effective records instead of trusting ordering or revision."""
    policy = _policy()
    await _add_complete_evidence(policy=policy)
    async with async_session_maker() as session:
        session.add(
            _entry(
                capability_id=MARKET_DATA_QUERY_V2_CAPABILITY,
                revision=2,
                descriptor_sha256=rollout_capability_descriptor_sha256(
                    MARKET_DATA_QUERY_V2_CAPABILITY
                ),
                effective_from=NOW - timedelta(minutes=30),
            )
        )
        await session.commit()

    evaluation = await _evaluate(policy=policy)
    state = _states_by_id(evaluation)[MARKET_DATA_QUERY_V2_CAPABILITY]
    assert evaluation.response.query_v2_enabled is False
    assert state.reason_code == "CAPABILITY_LEDGER_AMBIGUOUS"


@pytest.mark.asyncio
async def test_capability_endpoint_and_query_gate_share_the_durable_evaluator(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """Neither the status endpoint nor a query-service double can bypass missing rows."""
    import app.api.data.queries as queries

    settings = _settings()
    authorizer = _ReadAuthorizer()
    service = _QueryServiceDouble()
    monkeypatch.setattr(queries, "get_settings", lambda: settings)
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    try:
        capabilities_response = await client.get(
            "/api/v1/data/market-data/capabilities",
            headers=auth_headers,
        )
        query_response = await client.post(
            "/api/v1/data/queries",
            json={
                "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
                "dataset_code": "market.stock_daily",
                "data_kind": "bars",
                "frequency": "1d",
                "family_id": "stock.realtime",
                "family_contract_version": "market-data-family-v1",
                "start": "2026-09-08T09:00:00+00:00",
                "end": "2026-09-08T12:00:00+00:00",
                "required_fields": ["close"],
                "source_policy_id": "market-default-v1",
            },
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)
        app.dependency_overrides.pop(get_market_data_query_service, None)

    assert capabilities_response.status_code == 200
    assert capabilities_response.json()["query_v2_enabled"] is False
    assert capabilities_response.json()["capability_states"]
    assert query_response.status_code == 503
    assert query_response.json()["details"] == {"code": "MARKET_DATA_QUERY_V2_DISABLED"}
    assert service.calls == 0


@pytest.mark.asyncio
async def test_ledger_entries_are_append_only() -> None:
    """A later deployment decision must append a revision instead of mutating evidence."""
    entry = _entry(
        capability_id=MARKET_DATA_QUERY_V2_CAPABILITY,
        revision=1,
        descriptor_sha256=rollout_capability_descriptor_sha256(MARKET_DATA_QUERY_V2_CAPABILITY),
    )
    async with async_session_maker() as session:
        session.add(entry)
        await session.commit()
        entry.declared_capability = False
        with pytest.raises(ImmutableMarketDataRecordError):
            await session.commit()
        await session.rollback()
