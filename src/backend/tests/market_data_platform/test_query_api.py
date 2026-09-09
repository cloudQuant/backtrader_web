"""HTTP boundary contracts for the disabled-by-default v2 market-data endpoint."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.data.queries import (
    _default_source_policy_registry,
    execute_market_data_query_with_singleflight,
    get_market_data_access_authorizer,
    get_market_data_query_service,
)
from app.main import app
from app.schemas.market_data_platform import MarketDataQueryRequest
from app.services.market_data.access import (
    MarketDataAccessAuthorizer,
    MarketDataAuthorizationError,
    MarketDataPrincipal,
    MarketDataQueryAccess,
)
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import MarketDataQueryResolver
from app.services.market_data.query_service import (
    MarketDataQueryService,
    MarketDataQueryServiceError,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyRegistry,
)

UTC = timezone.utc


def _payload() -> dict[str, object]:
    return {
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
    }


def _execution(
    *,
    fetches: tuple[object, ...] = (),
    historical_status: str | None = None,
) -> object:
    at = datetime(2026, 9, 8, 12, tzinfo=UTC)
    query = SimpleNamespace(
        query_fingerprint="a" * 64,
        canonical_id="instrument:stock:CN-SSE:600000",
        dataset_code="market.stock_daily",
        instrument_metadata_version="stock-v1",
        data_kind="bars",
        frequency="1d",
        family_id="stock.realtime",
        family_contract_version="market-data-family-v1",
        source_policy_id="market-default-v1",
    )
    context = SimpleNamespace(query=query, identity=SimpleNamespace(asset_type="stock"))
    coverage = SimpleNamespace(
        status=SimpleNamespace(value="complete"),
        expected_event_keys=(),
        accepted_event_keys=(),
        missing_event_keys=(),
        coverage_ratio=1.0,
        gaps=(),
        rejection_counts={},
        calendar_reason=None,
    )
    observation = SimpleNamespace(
        revision_id="revision-1",
        source_snapshot_id="snapshot-1",
        event_at=at,
        available_at=at,
        committed_at=at,
        revision_number=1,
        quality=SimpleNamespace(value="pass"),
        fields={"close": "10.50"},
    )
    return SimpleNamespace(
        context=context,
        knowledge_cutoff=at,
        identity_knowledge_cutoff=at,
        coverage=coverage,
        observations=(observation,),
        next_cursor=None,
        fetches=fetches,
        warnings=(),
        refresh_status=None,
        historical_status=historical_status,
    )


class _Service:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.requests: list[object] = []
        self.cursor_bindings: list[object] = []
        self.accesses: list[object] = []

    async def execute(
        self,
        request: object,
        *,
        cursor_binding: object = None,
        access: object = None,
    ) -> object:
        self.requests.append(request)
        self.cursor_bindings.append(cursor_binding)
        self.accesses.append(access)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _BlockingService(_Service):
    """A fake leader that exposes whether a follower starts a duplicate fetch."""

    def __init__(self, outcome: object) -> None:
        super().__init__(outcome)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self,
        request: object,
        *,
        cursor_binding: object = None,
        access: object = None,
    ) -> object:
        self.requests.append(request)
        self.cursor_bindings.append(cursor_binding)
        self.accesses.append(access)
        self.started.set()
        await self.release.wait()
        return self.outcome


class _Db:
    """Minimal request-session stand-in used by the endpoint coordinator."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _AccessAuthorizer(MarketDataAccessAuthorizer):
    """Deterministic API-boundary authorization stand-in."""

    def __init__(
        self,
        principal: MarketDataPrincipal | Exception,
        *,
        revalidated_principal: MarketDataPrincipal | Exception | None = None,
    ) -> None:
        self.principal = principal
        self.revalidated_principal = revalidated_principal
        self.users: list[object] = []
        self.revalidated: list[MarketDataPrincipal] = []

    async def principal_for_user(self, user: object) -> MarketDataPrincipal:
        self.users.append(user)
        if isinstance(self.principal, Exception):
            raise self.principal
        return self.principal

    async def revalidate_principal(self, *, principal: MarketDataPrincipal) -> MarketDataPrincipal:
        self.revalidated.append(principal)
        current = self.revalidated_principal
        if current is None:
            current = self.principal
        if isinstance(current, Exception):
            raise current
        return current

    @staticmethod
    def require_read_data(*, principal: MarketDataPrincipal) -> None:
        if not principal.can_read_data:
            raise MarketDataAuthorizationError("MARKET_DATA_READ_ENTITLEMENT_DENIED")


def _principal(*, can_read_data: bool = True) -> MarketDataPrincipal:
    permissions = ("data:read",) if can_read_data else ()
    return MarketDataPrincipal(
        principal_id="user-1",
        principal_scope="principal-v1:test-user",
        tenant_scope="default",
        roles=("user",) if can_read_data else (),
        permissions=permissions,
        entitlement_revision="e" * 64,
    )


@pytest.mark.asyncio
async def test_v2_query_endpoint_is_disabled_by_default(client, auth_headers, monkeypatch) -> None:
    """An installed route remains unavailable until the rollout feature flag is set."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=False),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 503
    assert response.json()["details"] == {"code": "MARKET_DATA_QUERY_V2_DISABLED"}
    assert service.requests == []


@pytest.mark.asyncio
async def test_v2_query_endpoint_rejects_research_cache_fill_until_server_opt_in(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The browser bridge cannot turn a current cache fill into an online write path."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    authorizer = _AccessAuthorizer(_principal())
    request = _payload()
    request["purpose"] = "research_cache_fill"
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=request, headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 503
    assert response.json()["details"] == {"code": "MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED"}
    assert service.requests == []


@pytest.mark.asyncio
async def test_v2_query_endpoint_allows_research_cache_fill_after_server_opt_in(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A server-approved cache fill reaches the normal audited query service."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    authorizer = _AccessAuthorizer(_principal())
    request = _payload()
    request["purpose"] = "research_cache_fill"
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(
            MARKET_DATA_QUERY_V2_ENABLED=True,
            MARKET_DATA_RESEARCH_CACHE_FILL_ENABLED=True,
        ),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=request, headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 200
    assert len(service.requests) == 1
    assert service.requests[0].purpose == "research_cache_fill"


@pytest.mark.asyncio
async def test_v2_query_endpoint_returns_only_fixed_local_first_shape(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The HTTP adapter serializes local evidence without exposing provider exception text."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 200
    body = response.json()
    assert body["query_id"] == "a" * 64
    assert body["canonical_id"] == "instrument:stock:CN-SSE:600000"
    assert body["family_id"] == "stock.realtime"
    assert body["family_contract_version"] == "market-data-family-v1"
    assert body["identity_knowledge_cutoff"] == "2026-09-08T12:00:00Z"
    assert body["coverage"]["status"] == "complete"
    assert body["refresh_status"] is None
    assert body["observations"] == [
        {
            "revision_id": "revision-1",
            "source_snapshot_id": "snapshot-1",
            "event_at": "2026-09-08T12:00:00Z",
            "available_at": "2026-09-08T12:00:00Z",
            "committed_at": "2026-09-08T12:00:00Z",
            "revision_number": 1,
            "quality": "pass",
            "fields": {"close": "10.50"},
        }
    ]
    assert len(service.requests) == 1
    assert service.cursor_bindings[0] is not None
    assert service.cursor_bindings[0].principal_scope == "principal-v1:test-user"
    assert service.cursor_bindings[0].entitlement_revision == "e" * 64
    assert service.accesses[0] is not None
    assert service.accesses[0].principal == _principal()


@pytest.mark.asyncio
async def test_v2_query_endpoint_exposes_strict_historical_status(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A strict local-only coverage gap remains a stable public status, not a refresh cue."""
    import app.api.data.queries as queries

    service = _Service(_execution(historical_status="HISTORICAL_COVERAGE_UNAVAILABLE"))
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 200
    assert response.json()["historical_status"] == "HISTORICAL_COVERAGE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_v2_query_endpoint_maps_stable_service_code_without_traceback(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A bad cursor becomes an actionable 422 code, not an adapter or SQL error."""
    import app.api.data.queries as queries

    service = _Service(MarketDataQueryServiceError("CURSOR_INVALID"))
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 422
    assert response.json()["details"] == {"code": "CURSOR_INVALID"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_changes",
    [
        {
            "identity": {"canonical_id": "instrument:option:CN-CFFEX:IO2609-C-3000"},
            "dataset_code": "market.option_chain",
            "data_kind": "option_chain",
            "frequency": "snapshot",
            "required_fields": ["last"],
        },
        {
            "identity": {"canonical_id": "instrument:crypto:US-BINANCE:BTCUSDT"},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "required_fields": ["close"],
        },
    ],
)
async def test_v2_query_endpoint_rejects_every_unbound_family_before_catalog_identity_or_provider(
    client,
    auth_headers,
    monkeypatch,
    request_changes: dict[str, object],
) -> None:
    """No raw public product can reach v2 orchestration without its family contract."""
    import app.api.data.queries as queries

    class _UnexpectedCatalog:
        def __init__(self) -> None:
            self.calls = 0

        async def resolve_primary(self, _dataset_code: str) -> object:
            self.calls += 1
            raise AssertionError("catalog must not be read for an unbound family query")

    class _UnexpectedIdentities:
        def __init__(self) -> None:
            self.calls = 0

        async def resolve(self, *_args: object, **_kwargs: object) -> object:
            self.calls += 1
            raise AssertionError("identity must not be read for an unbound family query")

    class _UnexpectedProvider:
        def __init__(self) -> None:
            self.requests: list[object] = []

        async def fetch(self, request: object) -> object:
            self.requests.append(request)
            raise AssertionError("provider must not be called for an unbound family query")

    class _UnexpectedProviderPolicy(MarketDataSourcePolicy):
        def routes_for(self, _context: object) -> tuple[MarketDataProviderRoute, ...]:
            raise AssertionError("provider routes must not be selected for an unbound family query")

    class _Store:
        def __init__(self) -> None:
            self.visibility_calls = 0

        async def resolve_visibility_anchor(
            self,
            *,
            knowledge_cutoff: datetime,
        ) -> MarketDataVisibilityAnchor:
            self.visibility_calls += 1
            return MarketDataVisibilityAnchor(
                visible_at=knowledge_cutoff,
                max_visibility_sequence=0,
            )

        async def read_observation_revisions(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("local observations must not be read after binding rejection")

        async def read_calendar_for_context(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("calendar must not be read after binding rejection")

        async def ensure_provider_active(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("provider activity must not be checked after binding rejection")

        async def persist_provider_result(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("provider output must not persist after binding rejection")

    catalog = _UnexpectedCatalog()
    identities = _UnexpectedIdentities()
    provider = _UnexpectedProvider()
    store = _Store()
    route = MarketDataProviderRoute(
        route_id="unexpected-option-chain-provider",
        request_provider="unexpected",
        expected_result_provider_ids=frozenset({"unexpected"}),
        asset_types=frozenset({"option"}),
        data_kinds=frozenset({"option_chain"}),
        frequencies=frozenset({"snapshot"}),
        markets=frozenset({"CN-CFFEX"}),
        adjustments=frozenset({None}),
        price_bases=frozenset({None}),
        currencies=frozenset({None}),
        units=frozenset({None}),
        adapter=provider,  # type: ignore[arg-type]
    )
    policy = _UnexpectedProviderPolicy(
        policy_id="market-default-v1",
        allowed_purposes=frozenset({"display"}),
        routes=(route,),
    )
    service = MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=catalog,  # type: ignore[arg-type]
            identities=identities,  # type: ignore[arg-type]
        ),
        store=store,  # type: ignore[arg-type]
        source_policies=MarketDataSourcePolicyRegistry((policy,)),
        clock=lambda: datetime(2026, 9, 8, 12, tzinfo=UTC),
    )
    authorizer = _AccessAuthorizer(_principal())
    request = _payload()
    request.update(request_changes)
    request.pop("family_id")
    request.pop("family_contract_version")
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=request, headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 422
    assert store.visibility_calls == 0
    assert catalog.calls == 0
    assert identities.calls == 0
    assert provider.requests == []


@pytest.mark.asyncio
async def test_v2_query_endpoint_maps_missing_service_access_to_forbidden(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The query-service online-access gate is never exposed as a 422 input error."""
    import app.api.data.queries as queries

    service = _Service(MarketDataQueryServiceError("MARKET_DATA_ACCESS_REQUIRED"))
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 403
    assert response.json()["details"] == {"code": "MARKET_DATA_ACCESS_REQUIRED"}


@pytest.mark.asyncio
async def test_v2_query_contract_rejects_invalid_public_input_before_service_execution(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The endpoint retains the strict public DTO rather than accepting symbol-only input."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    invalid = _payload()
    invalid["identity"] = {"symbol": "600000"}
    try:
        response = await client.post("/api/v1/data/queries", json=invalid, headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 422
    assert service.requests == []


@pytest.mark.asyncio
async def test_v2_query_endpoint_rejects_current_principal_without_data_read_entitlement(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A v2 request cannot reach the query service without a current role grant."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    authorizer = _AccessAuthorizer(_principal(can_read_data=False))
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 403
    assert response.json()["details"] == {"code": "MARKET_DATA_READ_ENTITLEMENT_DENIED"}
    assert service.requests == []


@pytest.mark.asyncio
async def test_v2_query_endpoint_maps_current_source_license_denial_to_forbidden(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A source authorization denial is not disguised as an invalid request."""
    import app.api.data.queries as queries

    service = _Service(MarketDataAuthorizationError("SOURCE_LICENSE_DENIED"))
    authorizer = _AccessAuthorizer(_principal())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[get_market_data_access_authorizer] = lambda: authorizer
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)
        app.dependency_overrides.pop(get_market_data_access_authorizer, None)

    assert response.status_code == 403
    assert response.json()["details"] == {"code": "SOURCE_LICENSE_DENIED"}


@pytest.mark.asyncio
async def test_equivalent_current_local_first_misses_share_one_fetch_and_commit() -> None:
    """A same-process follower re-reads the leader's receipt instead of fetching again."""
    import app.api.data.queries as queries

    request = MarketDataQueryRequest.model_validate(_payload())
    leader = _BlockingService(_execution(fetches=(SimpleNamespace(),)))
    follower = _Service(_execution())
    leader_db = _Db()
    follower_db = _Db()
    queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()
    try:
        leader_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=leader,
                db=leader_db,  # type: ignore[arg-type]
                request=request,
            )
        )
        await leader.started.wait()
        follower_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=follower,
                db=follower_db,  # type: ignore[arg-type]
                request=request,
            )
        )
        await asyncio.sleep(0)
        assert follower.requests == []

        leader.release.set()
        leader_result, follower_result = await asyncio.gather(leader_task, follower_task)
    finally:
        queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()

    assert leader_result.fetches
    assert follower_result.fetches == ()
    assert len(leader.requests) == 1
    assert len(follower.requests) == 1
    assert leader_db.commits == 1
    assert follower_db.commits == 0
    assert follower_db.rollbacks == 1


@pytest.mark.asyncio
async def test_singleflight_follower_revalidates_access_after_its_snapshot_rollback() -> None:
    """A follower rebuilds its access context before reading the leader's receipt."""
    import app.api.data.queries as queries

    request = MarketDataQueryRequest.model_validate(_payload())
    principal = _principal()
    authorizer = _AccessAuthorizer(principal)
    access = MarketDataQueryAccess(principal=principal, authorizer=authorizer)
    leader = _BlockingService(_execution(fetches=(SimpleNamespace(),)))
    follower = _Service(_execution())
    leader_db = _Db()
    follower_db = _Db()
    queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()
    try:
        leader_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=leader,  # type: ignore[arg-type]
                db=leader_db,  # type: ignore[arg-type]
                request=request,
                access=access,
            )
        )
        await leader.started.wait()
        follower_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=follower,  # type: ignore[arg-type]
                db=follower_db,  # type: ignore[arg-type]
                request=request,
                access=access,
            )
        )
        await asyncio.sleep(0)
        leader.release.set()
        await asyncio.gather(leader_task, follower_task)
    finally:
        queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()

    assert authorizer.revalidated == [principal]
    assert follower_db.rollbacks == 1
    assert len(follower.accesses) == 1
    assert follower.accesses[0].principal == principal


@pytest.mark.asyncio
async def test_singleflight_follower_rejects_changed_access_before_service_reread() -> None:
    """A coalesced read fails closed instead of replaying under a stale grant."""
    import app.api.data.queries as queries

    request = MarketDataQueryRequest.model_validate(_payload())
    principal = _principal()
    authorizer = _AccessAuthorizer(
        principal,
        revalidated_principal=MarketDataAuthorizationError(
            "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"
        ),
    )
    access = MarketDataQueryAccess(principal=principal, authorizer=authorizer)
    leader = _BlockingService(_execution(fetches=(SimpleNamespace(),)))
    follower = _Service(_execution())
    leader_db = _Db()
    follower_db = _Db()
    queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()
    try:
        leader_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=leader,  # type: ignore[arg-type]
                db=leader_db,  # type: ignore[arg-type]
                request=request,
                access=access,
            )
        )
        await leader.started.wait()
        follower_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=follower,  # type: ignore[arg-type]
                db=follower_db,  # type: ignore[arg-type]
                request=request,
                access=access,
            )
        )
        await asyncio.sleep(0)
        leader.release.set()
        await leader_task
        with pytest.raises(MarketDataAuthorizationError) as rejected:
            await follower_task
    finally:
        queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()

    assert rejected.value.code == "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH"
    assert authorizer.revalidated == [principal]
    assert follower_db.rollbacks == 1
    assert follower.requests == []


@pytest.mark.asyncio
async def test_refresh_queries_do_not_reuse_local_first_singleflight_followers() -> None:
    """Refresh has its own fetch semantics, so each request executes directly."""
    import app.api.data.queries as queries

    request = MarketDataQueryRequest.model_validate({**_payload(), "mode": "refresh"})
    first = _BlockingService(_execution(fetches=(SimpleNamespace(),)))
    second = _BlockingService(_execution(fetches=(SimpleNamespace(),)))
    first_db = _Db()
    second_db = _Db()
    queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()
    try:
        first_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=first,
                db=first_db,  # type: ignore[arg-type]
                request=request,
            )
        )
        await first.started.wait()
        second_task = asyncio.create_task(
            execute_market_data_query_with_singleflight(
                service=second,
                db=second_db,  # type: ignore[arg-type]
                request=request,
            )
        )
        await asyncio.sleep(0)
        assert len(second.requests) == 1

        first.release.set()
        second.release.set()
        await asyncio.gather(first_task, second_task)
    finally:
        queries._INFLIGHT_LOCAL_FIRST_QUERIES.clear()

    assert len(first.requests) == 1
    assert first_db.commits == 0
    assert second_db.commits == 0
    assert first_db.rollbacks == 0
    assert second_db.rollbacks == 0


def test_legacy_data_routes_remain_registered_alongside_v2_query_route() -> None:
    """Iteration 197 adds a new route and does not replace page-critical legacy paths."""
    paths = {route.path for route in app.routes}

    assert "/api/v1/data/queries" in paths
    assert "/api/v1/data/kline" in paths
    assert "/api/v1/data/market-instruments/lookup" in paths
    assert "/api/v1/data/market-instruments/options" in paths


@pytest.mark.parametrize(
    ("asset_type", "venue", "expected_route_id"),
    [
        ("stock", "CN-SSE", "akshare-stock-liquidity-primary-v1"),
        ("fund", "CN-SZSE", "akshare-fund-liquidity-primary-v1"),
    ],
)
def test_default_policy_selects_only_exact_unadjusted_liquidity_routes(
    asset_type: str,
    venue: str,
    expected_route_id: str,
) -> None:
    """B1 liquidity cannot reuse adjusted realtime-bars or another asset's provider route."""
    _default_source_policy_registry.cache_clear()
    try:
        policy = _default_source_policy_registry("yfinance", ()).resolve("market-default-v1")
        context = SimpleNamespace(
            identity=SimpleNamespace(asset_type=asset_type, venue=venue),
            query=SimpleNamespace(
                data_kind="reference_series",
                frequency="1d",
                adjustment="unadjusted",
                price_basis="close",
                currency="CNY",
                unit="share",
            ),
        )

        routes = policy.routes_for(context)

        assert [route.route_id for route in routes] == [expected_route_id]
        assert policy.routes_for(
            SimpleNamespace(
                identity=context.identity,
                query=SimpleNamespace(
                    data_kind="reference_series",
                    frequency="1d",
                    adjustment="qfq",
                    price_basis="close",
                    currency="CNY",
                    unit="share",
                ),
            )
        ) == ()
        other_routes = policy.routes_for(
            SimpleNamespace(
                identity=SimpleNamespace(
                    asset_type="fund" if asset_type == "stock" else "stock",
                    venue=venue,
                ),
                query=context.query,
            )
        )
        assert [route.route_id for route in other_routes] == [
            (
                "akshare-fund-liquidity-primary-v1"
                if asset_type == "stock"
                else "akshare-stock-liquidity-primary-v1"
            )
        ]
    finally:
        _default_source_policy_registry.cache_clear()
