"""Regression gate for the Iteration 170 public API routes.

Iteration 197 routes legacy K-line reads through its governed local-first
bridge.  This gate keeps the old response shape while avoiding assumptions
about an HTTP handler's provider implementation.
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
from tests.conftest import register_and_login


class _LegacyContractResolver:
    async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
        return {"symbol": symbol, "period": period}


@pytest.mark.asyncio
async def test_iter170_keeps_legacy_data_portfolio_and_quote_routes(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All pre-existing routes remain callable with their public response shapes."""

    _, headers = await register_and_login(client, username="compat_user")
    access = SimpleNamespace(
        principal=SimpleNamespace(
            principal_scope="principal:iter170-compat",
            tenant_scope="default",
            entitlement_revision="iter170-compat-v1",
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

    async def fake_bridge(**kwargs: Any) -> dict[str, object]:
        request = kwargs["request"]
        return {
            "symbol": request.symbol,
            "count": 1,
            "kline": {
                "dates": ["2026-05-26"],
                "ohlc": [[1.0, 2.0, 1.0, 2.0]],
                "volumes": [100],
            },
            "records": [
                {
                    "date": "2026-05-26",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 1.0,
                    "close": 2.0,
                    "volume": 100,
                    "change": 1.0,
                }
            ],
        }

    monkeypatch.setattr(data_base, "execute_legacy_kline_local_first", fake_bridge)

    data = await client.get(
        "/api/v1/data/kline",
        headers=headers,
        params={"symbol": "000001.SZ", "start_date": "2026-05-26", "end_date": "2026-05-26"},
    )
    portfolio = await client.get("/api/v1/portfolio/overview", headers=headers)
    quote = await client.get("/api/v1/quote/sources", headers=headers)

    assert data.status_code == 200
    data_payload = data.json()
    assert {"symbol", "count", "kline", "records"}.issubset(data_payload)
    assert {"dates", "ohlc", "volumes"}.issubset(data_payload["kline"])
    assert portfolio.status_code == 200
    assert {"total_assets", "strategy_count"}.issubset(portfolio.json())
    assert quote.status_code == 200
    assert "sources" in quote.json()
