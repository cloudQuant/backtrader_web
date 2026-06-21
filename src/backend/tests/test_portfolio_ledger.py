import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.portfolio_ledger import PortfolioLedgerModel, PortfolioLedgerSnapshotModel
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_portfolio_ledger_create_import_holdings_and_snapshots(client: AsyncClient):
    _, headers = await register_and_login(client, username="ledger_user")

    created = await client.post(
        "/api/v1/portfolio-ledger",
        headers=headers,
        json={
            "name": "核心组合",
            "base_currency": "CNY",
            "source_type": "manual",
            "benchmark_symbol": "000300.SH",
            "tags": ["swing", "futures"],
            "notes": "iteration171",
        },
    )
    assert created.status_code == 201
    portfolio_id = created.json()["id"]

    imported = await client.post(
        f"/api/v1/portfolio-ledger/{portfolio_id}/import",
        headers=headers,
        json={
            "format": "json",
            "idempotency_key": "sha256-demo",
            "transactions": [
                {
                    "symbol": "RB2510",
                    "trade_type": "buy",
                    "quantity": 2,
                    "price": 3500,
                    "trade_date": "2026-05-26",
                    "tags": ["entry"],
                },
                {
                    "symbol": "RB2510",
                    "trade_type": "sell",
                    "quantity": 1,
                    "price": 3600,
                    "trade_date": "2026-05-27",
                    "notes": "trim",
                },
                {
                    "symbol": "RB2510",
                    "trade_type": "dividend",
                    "quantity": 0,
                    "price": 0,
                    "amount": 120,
                    "trade_date": "2026-05-28",
                },
                {
                    "symbol": "RB2510",
                    "trade_type": "fee",
                    "quantity": 0,
                    "price": 0,
                    "amount": 20,
                    "trade_date": "2026-05-29",
                },
            ],
        },
    )
    duplicated = await client.post(
        f"/api/v1/portfolio-ledger/{portfolio_id}/import",
        headers=headers,
        json={"format": "json", "idempotency_key": "sha256-demo", "transactions": []},
    )
    detail = await client.get(f"/api/v1/portfolio-ledger/{portfolio_id}", headers=headers)
    listed = await client.get("/api/v1/portfolio-ledger", headers=headers)
    holdings = await client.get(
        f"/api/v1/portfolio-ledger/{portfolio_id}/holdings",
        headers=headers,
    )
    transactions = await client.get(
        f"/api/v1/portfolio-ledger/{portfolio_id}/transactions",
        headers=headers,
    )
    backfilled = await client.post(
        f"/api/v1/portfolio-ledger/{portfolio_id}/snapshots/backfill",
        headers=headers,
    )
    snapshots = await client.get(
        f"/api/v1/portfolio-ledger/{portfolio_id}/snapshots",
        headers=headers,
    )
    exported = await client.get(f"/api/v1/portfolio-ledger/{portfolio_id}/export", headers=headers)

    assert imported.status_code == 200
    assert imported.json()["imported_count"] == 4
    assert duplicated.json()["duplicate"] is True
    assert detail.status_code == 200
    assert detail.json()["id"] == portfolio_id
    assert detail.json()["transaction_count"] == 4
    assert detail.json()["benchmark_symbol"] == "000300.SH"
    assert detail.json()["tags"] == ["swing", "futures"]
    assert detail.json()["notes"] == "iteration171"
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == portfolio_id
    assert listed.json()["items"][0]["transaction_count"] == 4
    assert holdings.status_code == 200
    assert holdings.json()["items"][0]["quantity"] == 1
    assert transactions.status_code == 200
    assert transactions.json()["total"] == 4
    assert transactions.json()["items"][0]["trade_type"] == "buy"
    assert transactions.json()["items"][0]["tags"] == ["entry"]
    assert backfilled.status_code == 200
    assert backfilled.json()["items"]
    assert backfilled.json()["items"][-1]["nav"] == 1000300.0
    assert snapshots.status_code == 200
    assert snapshots.json()["items"] == backfilled.json()["items"]
    assert exported.status_code == 200
    assert exported.json()["schema_version"] == "portfolio-ledger.v1"
    assert exported.json()["portfolio"]["id"] == portfolio_id
    assert exported.json()["transactions"][0]["symbol"] == "RB2510"

    async with async_session_maker() as session:
        portfolios = (await session.execute(select(PortfolioLedgerModel))).scalars().all()
        snapshot_rows = (
            (await session.execute(select(PortfolioLedgerSnapshotModel))).scalars().all()
        )

    assert len(portfolios) == 1
    assert len(snapshot_rows) == 4


@pytest.mark.asyncio
async def test_portfolio_legacy_route_still_exists(client: AsyncClient):
    _, headers = await register_and_login(client, username="legacy_portfolio_user")

    response = await client.get("/api/v1/portfolio/overview", headers=headers)

    assert response.status_code == 200
    assert "strategy_count" in response.json()
