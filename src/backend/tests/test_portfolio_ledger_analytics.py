from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.services.risk_analytics.benchmark import BenchmarkService
from tests.conftest import register_and_login


def _build_transactions() -> list[dict[str, object]]:
    start_date = date(2026, 1, 1)
    transactions: list[dict[str, object]] = []
    for index in range(32):
        symbol = "AAA" if index % 2 == 0 else "BBB"
        base_price = 100.0 if symbol == "AAA" else 80.0
        drift = index * (1.15 if symbol == "AAA" else 0.85)
        swing = ((index % 5) - 2) * 0.7
        transactions.append(
            {
                "symbol": symbol,
                "trade_type": "buy",
                "quantity": 1,
                "price": round(base_price + drift + swing, 2),
                "trade_date": (start_date + timedelta(days=index)).isoformat(),
            }
        )
    return transactions


async def _fake_benchmark_fetcher(
    symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, object]]:
    del symbol
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    records: list[dict[str, object]] = []
    close = 1000.0
    for offset in range((end - start).days + 1):
        current_date = start + timedelta(days=offset)
        close += 3.5 + ((offset % 4) - 1.5)
        records.append({"date": current_date.isoformat(), "close": round(close, 2)})
    return records


@pytest.mark.asyncio
async def test_portfolio_ledger_analytics_endpoints(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        BenchmarkService,
        "_default_fetcher",
        staticmethod(_fake_benchmark_fetcher),
    )
    _, headers = await register_and_login(client, username="ledger_analytics_user")

    created = await client.post(
        "/api/v1/portfolio-ledger",
        headers=headers,
        json={
            "name": "分析组合",
            "base_currency": "CNY",
            "source_type": "manual",
            "benchmark_symbol": "000300.SH",
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    imported = await client.post(
        f"/api/v1/portfolio-ledger/{portfolio_id}/import",
        headers=headers,
        json={
            "format": "json",
            "idempotency_key": "analytics-seed-1",
            "transactions": _build_transactions(),
        },
    )
    assert imported.status_code == 200
    assert imported.json()["imported_count"] == 32

    var_cvar = await client.get(
        f"/api/v1/portfolio-ledger/{portfolio_id}/analytics/var-cvar",
        headers=headers,
        params={"method": "historical"},
    )
    position_sizing = await client.get(
        f"/api/v1/portfolio-ledger/{portfolio_id}/analytics/position-sizing",
        headers=headers,
        params={"target_volatility": 0.12, "max_position": 0.8},
    )
    benchmark_metrics = await client.get(
        f"/api/v1/portfolio-ledger/{portfolio_id}/analytics/benchmark-metrics",
        headers=headers,
        params={"risk_free_rate": 0.02},
    )
    brinson = await client.post(
        f"/api/v1/portfolio-ledger/{portfolio_id}/analytics/brinson",
        headers=headers,
        json={
            "benchmark_weights": {"AAA": 0.55, "BBB": 0.45},
            "benchmark_returns": {"AAA": 0.08, "BBB": 0.03},
        },
    )
    fama_french = await client.post(
        f"/api/v1/portfolio-ledger/{portfolio_id}/analytics/fama-french",
        headers=headers,
        json={
            "smb_returns": [
                round(((index % 3) - 1) * 0.002 + index * 0.0001, 6) for index in range(31)
            ],
            "hml_returns": [
                round(((index % 4) - 1.5) * 0.0015 - index * 0.00005, 6) for index in range(31)
            ],
        },
    )
    missing = await client.get(
        "/api/v1/portfolio-ledger/missing/analytics/var-cvar",
        headers=headers,
    )

    assert var_cvar.status_code == 200
    assert var_cvar.json()["portfolio_id"] == portfolio_id
    assert var_cvar.json()["status"] == "ok"
    assert var_cvar.json()["observation_count"] == 31
    assert var_cvar.json()["var_95"] is not None

    assert position_sizing.status_code == 200
    assert position_sizing.json()["portfolio_id"] == portfolio_id
    assert position_sizing.json()["status"] == "ok"
    assert position_sizing.json()["recommended_position"] is not None
    assert position_sizing.json()["max_position"] == 0.8

    assert benchmark_metrics.status_code == 200
    assert benchmark_metrics.json()["portfolio_id"] == portfolio_id
    assert benchmark_metrics.json()["status"] == "ok"
    assert benchmark_metrics.json()["benchmark_id"] == "hs300"
    assert benchmark_metrics.json()["observation_count"] == 31

    assert brinson.status_code == 200
    assert brinson.json()["portfolio_id"] == portfolio_id
    assert brinson.json()["status"] == "ok"
    assert brinson.json()["asset_count"] == 2
    assert brinson.json()["total_excess_return"] is not None

    assert fama_french.status_code == 200
    assert fama_french.json()["portfolio_id"] == portfolio_id
    assert fama_french.json()["benchmark_id"] == "hs300"
    assert fama_french.json()["status"] == "ok"
    assert fama_french.json()["observation_count"] == 31
    assert fama_french.json()["market_beta"] is not None

    assert missing.status_code == 404
