import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from tests.conftest import register_and_login


class FakeScannerMarketClient:
    def __init__(self) -> None:
        self.context_calls = 0

    def fetch_pool_constituents(self, pool_id: str) -> list[dict]:
        assert pool_id == "hs300"
        return [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "asset_type": "equity",
                "exchange": "SZSE",
                "source": "akshare_fake",
            },
            {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "asset_type": "equity",
                "exchange": "SSE",
                "source": "akshare_fake",
            },
        ]

    def build_symbol_contexts(
        self,
        instruments: list[dict],
        *,
        lookback_days: int,
        timeframe: str,
    ) -> list[dict]:
        self.context_calls += 1
        rows = []
        for index, instrument in enumerate(instruments):
            rows.append(
                {
                    **instrument,
                    "price": 10.5 + index,
                    "volume": 1000000 + index * 10000,
                    "change_pct": 0.018 - index * 0.003,
                    "indicator": 0.72 - index * 0.04,
                    "factor": 0.67 - index * 0.03,
                    "news_sentiment": 0.55,
                    "portfolio_exposure": 0.0,
                    "provider": "akshare_fake",
                    "updated_at": "2026-06-19T04:00:00+00:00",
                    "lookback_days": lookback_days,
                    "timeframe": timeframe,
                }
            )
        return rows


@pytest.mark.asyncio
async def test_scanner_runs_safe_condition_dsl(client: AsyncClient):
    _, headers = await register_and_login(client, username="scanner_user")

    response = await client.post(
        "/api/v1/scanners/run",
        headers=headers,
        json={
            "universe": ["RB2510", "IF2510"],
            "condition": (
                "indicator > 0.6 and news_sentiment > 0.5 "
                "and lookback_days >= 20 and timeframe == '1d'"
            ),
            "lookback_days": 20,
            "timeframe": "1d",
        },
    )
    task = await client.get(
        f"/api/v1/scanners/tasks/{response.json()['task_id']}",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["task_id"]
    assert data["lookback_days"] == 20
    assert data["timeframe"] == "1d"
    assert all("symbol" in item for item in data["matches"])
    assert all("indicator" in item for item in data["matches"])
    assert task.status_code == 200
    assert task.json()["task_id"] == data["task_id"]
    assert task.json()["status"] == "completed"
    assert task.json()["matches"] == data["matches"]


@pytest.mark.asyncio
async def test_scanner_rejects_unsafe_expression(client: AsyncClient):
    _, headers = await register_and_login(client, username="scanner_unsafe")

    response = await client.post(
        "/api/v1/scanners/run",
        headers=headers,
        json={"universe": ["RB2510"], "condition": "__import__('os').system('x')"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_scanner_universe_pools_refresh_custom_and_run_real_factors(
    client: AsyncClient, tmp_path, monkeypatch
):
    from app.api import scanners as scanners_api
    from app.services.scanner_service import ScannerService
    from app.services.scanner_universe import ScannerUniverseService

    service = ScannerService(
        universe_service=ScannerUniverseService(
            storage_path=tmp_path / "scanner_universe_pools.json",
            market_client=FakeScannerMarketClient(),
        )
    )
    monkeypatch.setattr(scanners_api, "get_scanner_service", lambda: service)

    _, headers = await register_and_login(client, username="scanner_universe_user")

    pools = await client.get("/api/v1/scanners/universe-pools", headers=headers)
    assert pools.status_code == 200
    assert any(item["id"] == "hs300" for item in pools.json()["items"])

    refreshed = await client.post(
        "/api/v1/scanners/universe-pools/hs300/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["id"] == "hs300"
    assert refreshed_body["instrument_count"] == 2
    assert refreshed_body["instruments"][0]["symbol"] == "000001.SZ"
    assert refreshed_body["last_refresh_status"] == "ok"

    custom = await client.post(
        "/api/v1/scanners/universe-pools/custom",
        headers=headers,
        json={
            "name": "我的观察池",
            "description": "用户手动维护的标的池",
            "instruments": [
                {"symbol": "300750.SZ", "name": "宁德时代", "asset_type": "equity"},
                {"symbol": "110000.SH", "name": "测试转债", "asset_type": "convertible_bond"},
            ],
        },
    )
    assert custom.status_code == 200
    custom_body = custom.json()
    assert custom_body["is_custom"] is True
    assert custom_body["instrument_count"] == 2

    response = await client.post(
        "/api/v1/scanners/run",
        headers=headers,
        json={
            "universe_pool_id": custom_body["id"],
            "condition": "price > 0 and indicator >= 0.6",
            "lookback_days": 30,
            "timeframe": "1d",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["universe_pool_id"] == custom_body["id"]
    assert data["universe_count"] == 2
    assert data["matches"][0]["symbol"] == "300750.SZ"
    assert data["matches"][0]["name"] == "宁德时代"
    assert data["matches"][0]["provider"] == "akshare_fake"
    assert data["matches"][0]["updated_at"] == "2026-06-19T04:00:00+00:00"


@pytest.mark.asyncio
async def test_scanner_pool_metric_precompute_cache_is_used_by_run(
    client: AsyncClient, tmp_path, monkeypatch
):
    from app.api import scanners as scanners_api
    from app.services.scanner_service import ScannerService
    from app.services.scanner_universe import ScannerUniverseService

    fake_market_client = FakeScannerMarketClient()
    service = ScannerService(
        universe_service=ScannerUniverseService(
            storage_path=tmp_path / "scanner_universe_pools.json",
            market_client=fake_market_client,
        )
    )
    monkeypatch.setattr(scanners_api, "get_scanner_service", lambda: service)

    _, headers = await register_and_login(client, username="scanner_precompute_user")

    refreshed = await client.post(
        "/api/v1/scanners/universe-pools/hs300/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 200

    precomputed = await client.post(
        "/api/v1/scanners/universe-pools/hs300/precompute",
        headers=headers,
        json={"lookback_days": 20, "timeframe": "1d"},
    )
    assert precomputed.status_code == 200
    precomputed_body = precomputed.json()
    assert precomputed_body["pool_id"] == "hs300"
    assert precomputed_body["lookback_days"] == 20
    assert precomputed_body["timeframe"] == "1d"
    assert precomputed_body["total"] == 2
    assert precomputed_body["computed_at"]
    assert precomputed_body["cache_status"] == "updated"
    assert fake_market_client.context_calls == 1

    response = await client.post(
        "/api/v1/scanners/run",
        headers=headers,
        json={
            "universe_pool_id": "hs300",
            "condition": "price > 0 and indicator >= 0.6",
            "lookback_days": 20,
            "timeframe": "1d",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["factor_cache_status"] == "hit"
    assert data["universe_pool_id"] == "hs300"
    assert data["universe_count"] == 2
    assert data["matches"][0]["symbol"] == "000001.SZ"
    assert fake_market_client.context_calls == 1


@pytest.mark.asyncio
async def test_scanner_plan_daily_batch_persists_result_table(
    client: AsyncClient, tmp_path, monkeypatch
):
    from app.api import scanners as scanners_api
    from app.services.scanner_service import ScannerService
    from app.services.scanner_universe import ScannerUniverseService

    fake_market_client = FakeScannerMarketClient()
    service = ScannerService(
        universe_service=ScannerUniverseService(
            storage_path=tmp_path / "scanner_universe_pools.json",
            market_client=fake_market_client,
        )
    )
    monkeypatch.setattr(scanners_api, "get_scanner_service", lambda: service)

    _, headers = await register_and_login(client, username="scanner_plan_user")
    refreshed = await client.post(
        "/api/v1/scanners/universe-pools/hs300/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 200

    created = await client.post(
        "/api/v1/scanners/plans",
        headers=headers,
        json={
            "name": "沪深300动量日报",
            "universe_pool_id": "hs300",
            "indicator_rules": [
                {"metric": "indicator", "operator": ">=", "value": 0.6, "enabled": True},
                {"metric": "news_sentiment", "operator": ">=", "value": 0.5, "enabled": True},
            ],
            "condition": "indicator >= 0.6 and news_sentiment >= 0.5",
            "lookback_days": 20,
            "timeframe": "1d",
            "schedule_enabled": True,
            "schedule_frequency": "daily",
        },
    )
    assert created.status_code == 200
    plan = created.json()
    assert plan["id"]
    assert plan["name"] == "沪深300动量日报"
    assert plan["schedule_enabled"] is True

    daily = await client.post(
        "/api/v1/scanners/plans/daily-runs",
        headers=headers,
        json={"run_date": "2026-06-19"},
    )
    assert daily.status_code == 200
    daily_body = daily.json()
    assert daily_body["run_date"] == "2026-06-19"
    assert daily_body["total"] == 1
    run = daily_body["items"][0]
    assert run["plan_id"] == plan["id"]
    assert run["status"] == "completed"
    assert run["match_count"] == 2
    assert run["matches"][0]["symbol"] == "000001.SZ"
    assert run["metrics"]["factor_cache_status"] == "miss"
    assert fake_market_client.context_calls == 1

    history = await client.get(
        f"/api/v1/scanners/plans/{plan['id']}/runs",
        headers=headers,
    )
    assert history.status_code == 200
    history_body = history.json()
    assert history_body["total"] == 1
    assert history_body["items"][0]["run_date"] == "2026-06-19"
    assert history_body["items"][0]["matches"][1]["symbol"] == "600519.SH"

    duplicate = await client.post(
        "/api/v1/scanners/plans/daily-runs",
        headers=headers,
        json={"run_date": "2026-06-19"},
    )
    assert duplicate.status_code == 200
    duplicate_run = duplicate.json()["items"][0]
    assert duplicate_run["cache_status"] == "existing"
    assert fake_market_client.context_calls == 1


@pytest.mark.asyncio
async def test_scanner_plan_can_be_updated_deleted_and_manage_result_table(
    client: AsyncClient, tmp_path, monkeypatch
):
    from app.api import scanners as scanners_api
    from app.db import database as db_module
    from app.services.scanner_service import ScannerService
    from app.services.scanner_universe import ScannerUniverseService

    service = ScannerService(
        universe_service=ScannerUniverseService(
            storage_path=tmp_path / "scanner_universe_pools.json",
            market_client=FakeScannerMarketClient(),
        )
    )
    monkeypatch.setattr(scanners_api, "get_scanner_service", lambda: service)

    _, headers = await register_and_login(client, username="scanner_plan_crud_user")
    refreshed = await client.post(
        "/api/v1/scanners/universe-pools/hs300/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 200

    created = await client.post(
        "/api/v1/scanners/plans",
        headers=headers,
        json={
            "name": "沪深300动量日报",
            "universe_pool_id": "hs300",
            "indicator_rules": [
                {"metric": "indicator", "operator": ">=", "value": 0.6, "enabled": True},
            ],
            "condition": "indicator >= 0.6",
            "lookback_days": 20,
            "timeframe": "1d",
            "schedule_enabled": True,
            "schedule_frequency": "daily",
        },
    )
    assert created.status_code == 200
    plan = created.json()

    updated = await client.patch(
        f"/api/v1/scanners/plans/{plan['id']}",
        headers=headers,
        json={
            "name": "沪深300质量动量",
            "universe_pool_id": "hs300",
            "indicator_rules": [
                {"metric": "factor", "operator": ">=", "value": 0.65, "enabled": True},
                {"metric": "portfolio_exposure", "operator": "<=", "value": 0.2, "enabled": True},
            ],
            "condition": "factor >= 0.65 and portfolio_exposure <= 0.2",
            "lookback_days": 60,
            "timeframe": "4h",
            "schedule_enabled": False,
            "schedule_frequency": "daily",
            "status": "active",
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["id"] == plan["id"]
    assert updated_body["name"] == "沪深300质量动量"
    assert updated_body["lookback_days"] == 60
    assert updated_body["timeframe"] == "4h"
    assert updated_body["schedule_enabled"] is False

    created_table = await client.post(
        f"/api/v1/scanners/plans/{plan['id']}/result-table",
        headers=headers,
    )
    assert created_table.status_code == 200
    table_body = created_table.json()
    assert table_body["result_table_status"] == "ready"
    assert table_body["result_table_name"].startswith("scanner_plan_result_")

    async with db_module.engine.begin() as conn:
        table_exists = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).has_table(table_body["result_table_name"])
        )
    assert table_exists is True

    dropped_table = await client.delete(
        f"/api/v1/scanners/plans/{plan['id']}/result-table",
        headers=headers,
    )
    assert dropped_table.status_code == 200
    assert dropped_table.json()["result_table_status"] == "dropped"

    async with db_module.engine.begin() as conn:
        table_exists = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).has_table(table_body["result_table_name"])
        )
    assert table_exists is False

    deleted = await client.delete(
        f"/api/v1/scanners/plans/{plan['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    listed = await client.get("/api/v1/scanners/plans", headers=headers)
    assert listed.status_code == 200
    assert all(item["id"] != plan["id"] for item in listed.json()["items"])
