"""HTTP boundary contracts for the disabled-by-default v2 market-data endpoint."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.data.queries import (
    execute_market_data_query_with_singleflight,
    get_market_data_query_service,
)
from app.main import app
from app.schemas.market_data_platform import MarketDataQueryRequest
from app.services.market_data.query_service import MarketDataQueryServiceError

UTC = timezone.utc


def _payload() -> dict[str, object]:
    return {
        "identity": {"canonical_id": "instrument:stock:CN-SSE:600000"},
        "dataset_code": "market.stock_daily",
        "data_kind": "bars",
        "frequency": "1d",
        "start": "2026-09-08T09:00:00+00:00",
        "end": "2026-09-08T12:00:00+00:00",
        "required_fields": ["close"],
        "source_policy_id": "market-default-v1",
    }


def _execution(*, fetches: tuple[object, ...] = ()) -> object:
    at = datetime(2026, 9, 8, 12, tzinfo=UTC)
    query = SimpleNamespace(
        query_fingerprint="a" * 64,
        canonical_id="instrument:stock:CN-SSE:600000",
        dataset_code="market.stock_daily",
        instrument_metadata_version="stock-v1",
        data_kind="bars",
        frequency="1d",
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
    )


class _Service:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.requests: list[object] = []

    async def execute(self, request: object) -> object:
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _BlockingService(_Service):
    """A fake leader that exposes whether a follower starts a duplicate fetch."""

    def __init__(self, outcome: object) -> None:
        super().__init__(outcome)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, request: object) -> object:
        self.requests.append(request)
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


@pytest.mark.asyncio
async def test_v2_query_endpoint_is_disabled_by_default(client, auth_headers, monkeypatch) -> None:
    """An installed route remains unavailable until the rollout feature flag is set."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=False),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)

    assert response.status_code == 503
    assert response.json()["details"] == {"code": "MARKET_DATA_QUERY_V2_DISABLED"}
    assert service.requests == []


@pytest.mark.asyncio
async def test_v2_query_endpoint_returns_only_fixed_local_first_shape(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The HTTP adapter serializes local evidence without exposing provider exception text."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["query_id"] == "a" * 64
    assert body["canonical_id"] == "instrument:stock:CN-SSE:600000"
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


@pytest.mark.asyncio
async def test_v2_query_endpoint_maps_stable_service_code_without_traceback(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """A bad cursor becomes an actionable 422 code, not an adapter or SQL error."""
    import app.api.data.queries as queries

    service = _Service(MarketDataQueryServiceError("CURSOR_INVALID"))
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    try:
        response = await client.post("/api/v1/data/queries", json=_payload(), headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)

    assert response.status_code == 422
    assert response.json()["details"] == {"code": "CURSOR_INVALID"}


@pytest.mark.asyncio
async def test_v2_query_contract_rejects_invalid_public_input_before_service_execution(
    client,
    auth_headers,
    monkeypatch,
) -> None:
    """The endpoint retains the strict public DTO rather than accepting symbol-only input."""
    import app.api.data.queries as queries

    service = _Service(_execution())
    monkeypatch.setattr(
        queries,
        "get_settings",
        lambda: SimpleNamespace(MARKET_DATA_QUERY_V2_ENABLED=True),
    )
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    invalid = _payload()
    invalid["identity"] = {"symbol": "600000"}
    try:
        response = await client.post("/api/v1/data/queries", json=invalid, headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_market_data_query_service, None)

    assert response.status_code == 422
    assert service.requests == []


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
