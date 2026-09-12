"""HTTP wiring contracts for the governed legacy K-line facade."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

import app.api.data.base as data_base
from app.api.data.deps import get_authorized_market_data_access
from app.api.data.queries import (
    get_market_data_capability_evaluation,
    get_market_data_query_service,
)
from app.db.database import get_db
from app.main import app
from app.services.market_data.access import MarketDataAuthorizationError


class _Db:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _Service:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def execute(self, request: object, **_kwargs: object) -> object:
        self.requests.append(request)
        return SimpleNamespace(fetches=())


class _ContractResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
        self.calls.append((symbol, period))
        return {"version": "market-data-v2", "request": {}}


@pytest.fixture
def governed_kline_dependencies() -> tuple[_Db, _Service, _ContractResolver]:
    """Provide the route's authorized control plane without a real provider or database."""
    db = _Db()
    service = _Service()
    contracts = _ContractResolver()
    access = SimpleNamespace(
        principal=SimpleNamespace(
            principal_scope="user:api-test",
            tenant_scope="default",
            entitlement_revision="test-v1",
        )
    )
    evaluation = SimpleNamespace(response=SimpleNamespace(query_v2_enabled=True))
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_authorized_market_data_access] = lambda: access
    app.dependency_overrides[get_market_data_capability_evaluation] = lambda: evaluation
    app.dependency_overrides[get_market_data_query_service] = lambda: service
    app.dependency_overrides[data_base.get_legacy_market_data_query_contract_resolver] = lambda: (
        contracts
    )
    try:
        yield db, service, contracts
    finally:
        for dependency in (
            get_db,
            get_authorized_market_data_access,
            get_market_data_capability_evaluation,
            get_market_data_query_service,
            data_base.get_legacy_market_data_query_contract_resolver,
        ):
            app.dependency_overrides.pop(dependency, None)


@pytest.mark.asyncio
async def test_kline_facade_uses_the_governed_bridge_and_preserves_its_wire_shape(
    client: AsyncClient,
    governed_kline_dependencies: tuple[_Db, _Service, _ContractResolver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, service, contracts = governed_kline_dependencies
    bridge_calls: list[dict[str, Any]] = []

    async def fake_bridge(**kwargs: Any) -> dict[str, object]:
        bridge_calls.append(kwargs)
        contract = await kwargs["contract_resolver"].resolve_kline_legacy(
            symbol=kwargs["request"].symbol,
            period=kwargs["request"].period,
        )
        assert contract["version"] == "market-data-v2"
        first = await kwargs["execute_local_first"](
            SimpleNamespace(
                mode="local_first",
                knowledge_cutoff=None,
                query_fingerprint="legacy-kline-api-test",
            )
        )
        final = await kwargs["execute_local_only"](SimpleNamespace(mode="local_only"))
        assert first.fetches == ()
        assert final.fetches == ()
        return {
            "symbol": "600000",
            "count": 1,
            "kline": {"dates": ["2026-09-07"], "ohlc": [[10.0, 10.0, 9.0, 11.0]], "volumes": [1]},
            "records": [
                {
                    "date": "2026-09-07",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.0,
                    "volume": 1,
                    "change": 0.0,
                }
            ],
        }

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
    response = await client.get(
        "/api/v1/data/kline",
        params={
            "symbol": "600000",
            "start_date": "2026-09-07",
            "end_date": "2026-09-07",
            "period": "daily",
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert len(bridge_calls) == 1
    assert contracts.calls == [("600000", "daily")]
    assert len(service.requests) == 2


@pytest.mark.asyncio
async def test_kline_facade_rejects_invalid_date_input_without_invoking_the_bridge(
    client: AsyncClient,
    governed_kline_dependencies: tuple[_Db, _Service, _ContractResolver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge_calls = 0

    async def fake_bridge(**_kwargs: Any) -> dict[str, object]:
        nonlocal bridge_calls
        bridge_calls += 1
        return {}

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
    response = await client.get(
        "/api/v1/data/kline",
        params={
            "symbol": "600000",
            "start_date": "2026-09-08",
            "end_date": "2026-09-07",
            "period": "daily",
        },
    )

    assert response.status_code == 422
    assert bridge_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start_date", "end_date", "period"),
    [
        ("0001-01-01", "0001-01-01", "daily"),
        ("9999-12-31", "9999-12-31", "daily"),
        ("0001-01-01", "0001-01-07", "weekly"),
        ("0001-01-01", "0001-01-31", "monthly"),
        ("9999-12-01", "9999-12-31", "monthly"),
    ],
)
async def test_kline_facade_rejects_iso_calendar_endpoints_that_cannot_form_a_utc_window(
    client: AsyncClient,
    governed_kline_dependencies: tuple[_Db, _Service, _ContractResolver],
    monkeypatch: pytest.MonkeyPatch,
    start_date: str,
    end_date: str,
    period: str,
) -> None:
    """Calendar overflow/underflow remains a 422 selector failure, not a 500."""
    bridge_calls = 0

    async def fake_bridge(**_kwargs: Any) -> dict[str, object]:
        nonlocal bridge_calls
        bridge_calls += 1
        return {}

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
    response = await client.get(
        "/api/v1/data/kline",
        params={
            "symbol": "600000",
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
        },
    )

    assert response.status_code == 422
    assert response.json()["details"] == {"code": "KLINE_REQUEST_INVALID"}
    assert bridge_calls == 0


@pytest.mark.asyncio
async def test_kline_facade_authorizes_before_parsing_an_invalid_selector(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unentitled caller cannot use validation as a pre-auth route probe."""

    async def denied_access() -> object:
        raise HTTPException(
            status_code=403,
            detail={"code": "MARKET_DATA_READ_ENTITLEMENT_DENIED"},
        )

    def unexpected_parser(**_kwargs: object) -> object:
        raise AssertionError("the selector parser must not run before data:read")

    app.dependency_overrides[get_authorized_market_data_access] = denied_access
    monkeypatch.setattr(data_base, "parse_legacy_kline_request", unexpected_parser)
    try:
        response = await client.get(
            "/api/v1/data/kline",
            params={
                "symbol": "600000",
                "start_date": "2026-09-08",
                "end_date": "2026-09-07",
                "period": "daily",
            },
        )
    finally:
        app.dependency_overrides.pop(get_authorized_market_data_access, None)

    assert response.status_code == 403
    assert response.json()["details"] == {"code": "MARKET_DATA_READ_ENTITLEMENT_DENIED"}


@pytest.mark.asyncio
async def test_kline_facade_rejects_cursor_or_duplicate_selector_before_bridge_execution(
    client: AsyncClient,
    governed_kline_dependencies: tuple[_Db, _Service, _ContractResolver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge_calls = 0

    async def fake_bridge(**_kwargs: Any) -> dict[str, object]:
        nonlocal bridge_calls
        bridge_calls += 1
        return {}

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
    for params in (
        [
            ("symbol", "600000"),
            ("start_date", "2026-09-07"),
            ("end_date", "2026-09-07"),
            ("cursor", "client-cursor"),
        ],
        [
            ("symbol", "600000"),
            ("symbol", "600001"),
            ("start_date", "2026-09-07"),
            ("end_date", "2026-09-07"),
        ],
    ):
        response = await client.get("/api/v1/data/kline", params=params)

        assert response.status_code == 422
    assert bridge_calls == 0


@pytest.mark.asyncio
async def test_kline_facade_stops_before_contract_or_query_work_when_v2_is_disabled(
    client: AsyncClient,
    governed_kline_dependencies: tuple[_Db, _Service, _ContractResolver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db, service, contracts = governed_kline_dependencies
    app.dependency_overrides[get_market_data_capability_evaluation] = lambda: SimpleNamespace(
        response=SimpleNamespace(query_v2_enabled=False)
    )
    bridge_calls = 0

    async def fake_bridge(**_kwargs: Any) -> dict[str, object]:
        nonlocal bridge_calls
        bridge_calls += 1
        return {}

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
    response = await client.get(
        "/api/v1/data/kline",
        params={"symbol": "600000", "start_date": "2026-09-07", "end_date": "2026-09-07"},
    )

    assert response.status_code == 503
    assert response.json()["details"] == {"code": "MARKET_DATA_QUERY_V2_DISABLED"}
    assert bridge_calls == 0
    assert contracts.calls == []
    assert service.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expected_status"),
    [
        ("MARKET_DATA_READ_ENTITLEMENT_DENIED", 403),
        ("SOURCE_ROUTE_AUTHORIZATION_DENIED", 503),
    ],
)
async def test_kline_facade_keeps_source_route_failures_out_of_data_read_denials(
    client: AsyncClient,
    governed_kline_dependencies: tuple[_Db, _Service, _ContractResolver],
    monkeypatch: pytest.MonkeyPatch,
    error_code: str,
    expected_status: int,
) -> None:
    async def failing_bridge(**_kwargs: Any) -> dict[str, object]:
        raise MarketDataAuthorizationError(error_code)

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", failing_bridge)
    response = await client.get(
        "/api/v1/data/kline",
        params={"symbol": "600000", "start_date": "2026-09-07", "end_date": "2026-09-07"},
    )

    assert response.status_code == expected_status
    assert response.json()["details"] == {"code": error_code}


def test_kline_handler_has_no_direct_akshare_or_market_instrument_fallback() -> None:
    source = inspect.getsource(data_base.get_kline_data)

    assert "akshare" not in source.casefold()
    assert "MarketInstrumentService" not in source
