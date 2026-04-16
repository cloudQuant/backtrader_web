"""
Integration tests for akshare data management APIs.
"""

import sys
from types import ModuleType

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.database import async_session_maker, create_default_admin
from app.models.akshare_mgmt import DataTable, TaskExecution, TaskStatus, TriggeredBy

settings = get_settings()


async def get_admin_headers(client: AsyncClient) -> dict[str, str]:
    await create_default_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def dummy_akshare_module() -> ModuleType:
    module = ModuleType("akshare")
    large_default_values = [f"symbol_{index:03d}" for index in range(80)]

    def stock_zh_a_hist(**_: object) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "日期": "2024-01-02",
                    "开盘": 10.0,
                    "收盘": 10.5,
                    "最高": 10.8,
                    "最低": 9.9,
                    "成交量": 1000,
                },
                {
                    "日期": "2024-01-03",
                    "开盘": 10.5,
                    "收盘": 10.2,
                    "最高": 10.7,
                    "最低": 10.1,
                    "成交量": 900,
                },
            ]
        )

    def stock_zh_a_spot() -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "000001", "name": "PingAn"}])

    def stock_big_default(vars_list=large_default_values) -> pd.DataFrame:
        return pd.DataFrame([{"symbol": "000001"}])

    module.stock_zh_a_hist = stock_zh_a_hist
    module.stock_zh_a_spot = stock_zh_a_spot
    module.stock_big_default = stock_big_default
    return module


@pytest.fixture
async def warehouse_engine(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    import app.db.akshare_data_database as akshare_db_module
    import app.services.akshare_data_service as akshare_data_service_module

    monkeypatch.setattr(akshare_db_module, "akshare_data_engine", engine)
    monkeypatch.setattr(akshare_data_service_module, "akshare_data_engine", engine)

    yield engine
    await engine.dispose()


class TestAkshareManagementApi:
    async def test_scan_scripts_and_create_task(
        self,
        client: AsyncClient,
        monkeypatch,
        dummy_akshare_module: ModuleType,
    ):
        admin_headers = await get_admin_headers(client)
        monkeypatch.setitem(sys.modules, "akshare", dummy_akshare_module)
        monkeypatch.delitem(
            sys.modules,
            "app.data_fetch.scripts.stocks.daily.stock_zh_a_hist",
            raising=False,
        )

        scan_resp = await client.post("/api/v1/data/scripts/scan", headers=admin_headers)
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert scan_data["registered"] + scan_data["updated"] >= 1

        list_resp = await client.get("/api/v1/data/scripts", headers=admin_headers)
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert any(item["script_id"] == "stock_zh_a_hist" for item in list_data["items"])

        task_resp = await client.post(
            "/api/v1/data/tasks",
            headers=admin_headers,
            json={
                "name": "日线采集任务",
                "script_id": "stock_zh_a_hist",
                "schedule_type": "cron",
                "schedule_expression": "0 8 * * 1-5",
                "parameters": {"symbol": "000001"},
                "is_active": True,
                "retry_on_failure": True,
                "max_retries": 3,
                "timeout": 0,
            },
        )
        assert task_resp.status_code == 201
        task_data = task_resp.json()
        assert task_data["script_id"] == "stock_zh_a_hist"

        tasks_resp = await client.get("/api/v1/data/tasks", headers=admin_headers)
        assert tasks_resp.status_code == 200
        assert tasks_resp.json()["total"] == 1

    async def test_bootstrap_interfaces_and_list(
        self,
        client: AsyncClient,
        monkeypatch,
        dummy_akshare_module: ModuleType,
    ):
        admin_headers = await get_admin_headers(client)
        monkeypatch.setitem(sys.modules, "akshare", dummy_akshare_module)

        bootstrap_resp = await client.post(
            "/api/v1/data/interfaces/bootstrap",
            headers=admin_headers,
            params={"refresh": "true"},
        )
        assert bootstrap_resp.status_code == 200
        bootstrap_data = bootstrap_resp.json()
        assert bootstrap_data["created"] + bootstrap_data["updated"] >= 1

        categories_resp = await client.get(
            "/api/v1/data/interfaces/categories", headers=admin_headers
        )
        assert categories_resp.status_code == 200
        assert len(categories_resp.json()) >= 1

        interfaces_resp = await client.get("/api/v1/data/interfaces", headers=admin_headers)
        assert interfaces_resp.status_code == 200
        items = interfaces_resp.json()["items"]
        assert any(item["name"] == "stock_zh_a_hist" for item in items)
        big_default_interface = next(item for item in items if item["name"] == "stock_big_default")
        assert len(big_default_interface["params"][0]["default_value"]) > 255

    async def test_interfaces_endpoints_require_admin(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        categories_resp = await client.get(
            "/api/v1/data/interfaces/categories", headers=auth_headers
        )
        assert categories_resp.status_code == 403

        interfaces_resp = await client.get("/api/v1/data/interfaces", headers=auth_headers)
        assert interfaces_resp.status_code == 403

        detail_resp = await client.get("/api/v1/data/interfaces/1", headers=auth_headers)
        assert detail_resp.status_code == 403

    async def test_tables_list_schema_and_rows(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        warehouse_engine,
    ):
        async with warehouse_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    CREATE TABLE stock_daily_000001 (
                        date TEXT,
                        close REAL
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    INSERT INTO stock_daily_000001 (date, close)
                    VALUES ('2024-01-02', 10.5), ('2024-01-03', 10.2)
                    """
                )
            )

        async with async_session_maker() as session:
            table = DataTable(
                id=1,
                table_name="stock_daily_000001",
                table_comment="A股日线",
                category="stocks",
                script_id="stock_zh_a_hist",
                row_count=2,
                last_update_status="success",
                metadata_json={"columns": ["date", "close"]},
            )
            session.add(table)
            session.add(
                TaskExecution(
                    execution_id="ak_exec_test001",
                    script_id="stock_zh_a_hist",
                    status=TaskStatus.COMPLETED,
                    triggered_by=TriggeredBy.MANUAL,
                    result={"ok": True},
                )
            )
            await session.commit()

        list_resp = await client.get("/api/v1/data/tables", headers=auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1

        detail_resp = await client.get("/api/v1/data/tables/1", headers=auth_headers)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["table_name"] == "stock_daily_000001"

        schema_resp = await client.get("/api/v1/data/tables/1/schema", headers=auth_headers)
        assert schema_resp.status_code == 200
        schema_data = schema_resp.json()
        assert schema_data["table_name"] == "stock_daily_000001"
        assert {column["name"] for column in schema_data["columns"]} == {"date", "close"}

        rows_resp = await client.get("/api/v1/data/tables/1/data", headers=auth_headers)
        assert rows_resp.status_code == 200
        rows_data = rows_resp.json()
        assert rows_data["total"] == 2
        assert rows_data["rows"][0]["date"] == "2024-01-02"

        execution_resp = await client.get("/api/v1/data/executions", headers=auth_headers)
        assert execution_resp.status_code == 200
        assert execution_resp.json()["total"] == 1
