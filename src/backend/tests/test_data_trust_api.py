"""Authenticated and failure-mapped tests for every data-trust endpoint."""

from __future__ import annotations

from typing import Any

import pytest

from app.api.data import trust as trust_api
from app.schemas.market_data_trust import (
    AssetSpecResponse,
    DataPrecheckResponse,
    MarketDataCoverageMatrixResponse,
    MarketDataCoverageResponse,
)
from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


def _spec() -> AssetSpecResponse:
    return AssetSpecResponse(
        id="spec-rb0",
        asset_type="futures",
        symbol="RB0",
        exchange="SHFE",
        contract_multiplier=10,
        margin_rate=0.1,
        min_order_size=1,
        commission_rate=0.0001,
    )


def _coverage() -> MarketDataCoverageMatrixResponse:
    return MarketDataCoverageMatrixResponse(
        total=1,
        items=[
            MarketDataCoverageResponse(
                id="coverage-rb0",
                asset_type="futures",
                symbol="RB0",
                timeframe="1h",
                row_count=120,
                quality_status="pass",
            )
        ],
        refreshed=True,
    )


class _AssetSpecs:
    async def get_or_create(self, **_: Any) -> AssetSpecResponse:
        return _spec()


class _Coverage:
    async def list_coverage(self, **_: Any) -> MarketDataCoverageMatrixResponse:
        return _coverage()

    async def refresh_local_csv_coverage(self, **_: Any) -> MarketDataCoverageMatrixResponse:
        return _coverage()

    async def refresh_warehouse_coverage(self, **_: Any) -> MarketDataCoverageMatrixResponse:
        return _coverage()


class _Precheck:
    async def precheck(self, *_: Any, **__: Any) -> DataPrecheckResponse:
        return DataPrecheckResponse(
            passed=True,
            status="pass",
            asset_type="futures",
            symbol="RB0",
            timeframe="1h",
            provider="local_csv",
            asset_spec=_spec(),
            coverage=_coverage().items[0],
        )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/data/trust/asset-specs/RB0",
        "/api/v1/data/trust/asset-specs/RB0/execution-model",
        "/api/v1/data/trust/coverage",
    ],
)
async def test_data_trust_endpoints_require_authentication(client, path: str):
    response = await client.get(path)

    assert response.status_code == 401


async def test_data_trust_endpoints_validate_and_return_canonical_responses(client, monkeypatch):
    _, headers = await register_and_login(client, username="data-trust-api")
    monkeypatch.setattr(trust_api, "get_asset_spec_service", lambda: _AssetSpecs())
    monkeypatch.setattr(trust_api, "get_market_data_coverage_service", lambda: _Coverage())
    monkeypatch.setattr(trust_api, "get_market_data_precheck_service", lambda: _Precheck())

    invalid = await client.get("/api/v1/data/trust/coverage?limit=0", headers=headers)
    spec = await client.get("/api/v1/data/trust/asset-specs/RB0", headers=headers)
    execution = await client.get(
        "/api/v1/data/trust/asset-specs/RB0/execution-model", headers=headers
    )
    coverage = await client.get("/api/v1/data/trust/coverage", headers=headers)
    refresh = await client.post("/api/v1/data/trust/coverage/refresh-local", headers=headers)
    warehouse_refresh = await client.post(
        "/api/v1/data/trust/coverage/refresh-warehouse", headers=headers
    )
    precheck = await client.post(
        "/api/v1/data/trust/precheck",
        headers=headers,
        json={"symbol": "RB0", "timeframe": "1h"},
    )

    assert invalid.status_code == 422
    assert spec.status_code == 200 and spec.json()["contract_multiplier"] == 10
    assert execution.status_code == 200 and execution.json()["margin_rate"] == 0.1
    assert coverage.status_code == 200 and coverage.json()["total"] == 1
    assert refresh.status_code == 200 and refresh.json()["refreshed"] is True
    assert warehouse_refresh.status_code == 200 and warehouse_refresh.json()["refreshed"] is True
    assert precheck.status_code == 200 and precheck.json()["passed"] is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/data/trust/asset-specs/RB0"),
        ("get", "/api/v1/data/trust/asset-specs/RB0/execution-model"),
        ("get", "/api/v1/data/trust/coverage"),
        ("post", "/api/v1/data/trust/coverage/refresh-local"),
        ("post", "/api/v1/data/trust/coverage/refresh-warehouse"),
        ("post", "/api/v1/data/trust/precheck"),
    ],
)
async def test_data_trust_services_map_unexpected_failures_to_503(
    client, monkeypatch, method: str, path: str
):
    _, headers = await register_and_login(
        client, username=f"data-trust-failure-{method}-{path[-4:]}"
    )

    class _Broken:
        def __getattr__(self, _: str):
            async def fail(**__: Any) -> None:
                raise RuntimeError("provider unavailable")

            return fail

    monkeypatch.setattr(trust_api, "get_asset_spec_service", lambda: _Broken())
    monkeypatch.setattr(trust_api, "get_market_data_coverage_service", lambda: _Broken())
    monkeypatch.setattr(trust_api, "get_market_data_precheck_service", lambda: _Broken())
    kwargs: dict[str, Any] = {"headers": headers}
    if path.endswith("/precheck"):
        kwargs["json"] = {"symbol": "RB0"}

    response = await getattr(client, method)(path, **kwargs)

    assert response.status_code == 503
    assert response.json()["message"] == "Market-data trust service is temporarily unavailable"
