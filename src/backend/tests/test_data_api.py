"""Compatibility tests for the governed legacy K-line HTTP facade.

The provider-specific normalization and cache-fill behavior live behind the
iteration 197 market-data bridge.  These tests intentionally exercise only the
legacy HTTP contract that existing clients consume.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient

import app.api.data.base as data_base
from app.api.data.deps import get_authorized_market_data_access
from app.api.data.queries import (
    get_market_data_capability_evaluation,
    get_market_data_query_service,
)
from app.main import app
from app.services.market_data.legacy_kline_projection import LegacyKlineBridgeError


class _LegacyContractResolver:
    async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
        return {"symbol": symbol, "period": period}


@pytest.fixture
def governed_kline_facade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install only the control-plane dependencies required by the facade.

    The bridge itself is replaced by each test.  No test route calls a provider
    directly or relies on network/dataframe behavior.
    """

    access = SimpleNamespace(
        principal=SimpleNamespace(
            principal_scope="principal:test-data-api",
            tenant_scope="default",
            entitlement_revision="test-data-api-v1",
        )
    )
    evaluation = SimpleNamespace(response=SimpleNamespace(query_v2_enabled=True))
    monkeypatch.setitem(app.dependency_overrides, get_authorized_market_data_access, lambda: access)
    monkeypatch.setitem(
        app.dependency_overrides,
        get_market_data_capability_evaluation,
        lambda: evaluation,
    )
    monkeypatch.setitem(app.dependency_overrides, get_market_data_query_service, lambda: object())
    monkeypatch.setitem(
        app.dependency_overrides,
        data_base.get_legacy_market_data_query_contract_resolver,
        lambda: _LegacyContractResolver(),
    )


@pytest.mark.asyncio
class TestKlineData:
    """Preserve the public legacy K-line route without provider coupling."""

    async def test_get_kline_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/data/kline",
            params={
                "symbol": "000001.SZ",
                "start_date": "2026-09-07",
                "end_date": "2026-09-07",
            },
        )

        assert response.status_code == 401

    async def test_get_kline_rejects_invalid_date_range_before_bridge_execution(
        self,
        client: AsyncClient,
        governed_kline_facade: None,
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
                "symbol": "000001.SZ",
                "start_date": "2026-09-08",
                "end_date": "2026-09-07",
                "period": "daily",
            },
        )

        assert response.status_code == 422
        assert bridge_calls == 0

    @pytest.mark.parametrize("period", ["daily", "weekly", "monthly"])
    async def test_get_kline_preserves_legacy_wire_shape(
        self,
        client: AsyncClient,
        governed_kline_facade: None,
        monkeypatch: pytest.MonkeyPatch,
        period: str,
    ) -> None:
        bridge_calls: list[dict[str, Any]] = []
        expected = {
            "symbol": "000001.SZ",
            "count": 1,
            "kline": {
                "dates": ["2026-09-07"],
                # Existing clients consume OHLC in [open, close, low, high] order.
                "ohlc": [[10.0, 10.3, 9.8, 10.5]],
                "volumes": [1_000_000],
            },
            "records": [
                {
                    "date": "2026-09-07",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.3,
                    "volume": 1_000_000,
                    "change": 2.5,
                }
            ],
        }

        async def fake_bridge(**kwargs: Any) -> dict[str, object]:
            bridge_calls.append(kwargs)
            return expected

        date_windows = {
            "daily": ("2026-09-07", "2026-09-07"),
            "weekly": ("2026-09-07", "2026-09-13"),
            "monthly": ("2026-09-01", "2026-09-30"),
        }
        start_date, end_date = date_windows[period]

        monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)
        response = await client.get(
            "/api/v1/data/kline",
            params={
                "symbol": "000001.SZ",
                "start_date": start_date,
                "end_date": end_date,
                "period": period,
            },
        )

        assert response.status_code == 200
        assert response.json() == expected
        assert len(bridge_calls) == 1
        assert bridge_calls[0]["request"].period == period

    async def test_get_kline_returns_a_bounded_bridge_failure(
        self,
        client: AsyncClient,
        governed_kline_facade: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def failing_bridge(**_kwargs: Any) -> dict[str, object]:
            raise LegacyKlineBridgeError("KLINE_COVERAGE_INCOMPLETE")

        monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", failing_bridge)
        response = await client.get(
            "/api/v1/data/kline",
            params={
                "symbol": "000001.SZ",
                "start_date": "2026-09-07",
                "end_date": "2026-09-07",
            },
        )

        assert response.status_code == 503
        assert response.json()["details"] == {"code": "KLINE_COVERAGE_INCOMPLETE"}


@pytest.mark.asyncio
class TestDataAPIRoutes:
    """Route registration is part of the legacy compatibility boundary."""

    async def test_kline_endpoint_remains_registered(self) -> None:
        from app.api.data import router

        routes = [route.path for route in router.routes]
        assert "/kline" in routes
