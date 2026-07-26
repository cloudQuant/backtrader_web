import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.config import get_settings
from app.db.database import async_session_maker, create_default_admin
from app.models.akshare_mgmt import DataInterface, InterfaceCategory
from app.models.data_governance import (
    DgEndpoint,
    DgIngestJob,
    DgProvider,
    DgQualityRule,
)
from tests.conftest import register_and_login


def test_data_governance_datetime_defaults_match_naive_schema() -> None:
    """PostgreSQL migrations use TIMESTAMP WITHOUT TIME ZONE for these fields."""
    timestamp_columns = [
        DgProvider.created_at,
        DgEndpoint.created_at,
        DgIngestJob.created_at,
        DgIngestJob.updated_at,
        DgQualityRule.created_at,
    ]

    for column in timestamp_columns:
        default = column.property.columns[0].default
        assert default is not None
        value = default.arg(None)
        assert value.tzinfo is None


@pytest.mark.asyncio
async def test_dg_bootstrap_keeps_akshare_interfaces_compatible(client: AsyncClient):
    _, headers = await register_and_login(client, username="dg_admin")
    settings = get_settings()
    async with async_session_maker() as session:
        category = InterfaceCategory(name="stock", description="stock")
        session.add(category)
        await session.flush()
        session.add(
            DataInterface(
                name="stock_zh_a_hist",
                display_name="A股历史行情",
                category_id=category.id,
                module_path="akshare",
                function_name="stock_zh_a_hist",
                parameters={"symbol": {"type": "string"}},
            )
        )
        await session.commit()

    response = await client.post("/api/v1/data-governance/bootstrap", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["akshare_migrated_endpoints"] >= 1

    async with async_session_maker() as session:
        providers = (await session.execute(select(DgProvider))).scalars().all()
        endpoints = (await session.execute(select(DgEndpoint))).scalars().all()
        view_rows = (
            await session.execute(text("SELECT name FROM ak_data_interfaces_compat"))
        ).all()

    assert {provider.provider_id for provider in providers} >= {
        "akshare",
        "yahoo",
        "fred",
        "coingecko",
        "cboe",
        "cftc",
    }
    assert any(endpoint.incremental_sync_key for endpoint in endpoints)
    assert any(row[0] == "stock_zh_a_hist" for row in view_rows)

    await create_default_admin()
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    legacy = await client.get("/api/v1/data/interfaces", headers=admin_headers)
    assert legacy.status_code == 200
    assert legacy.json()["total"] >= 1


@pytest.mark.asyncio
async def test_data_connector_preview_and_async_job(client: AsyncClient):
    _, headers = await register_and_login(client, username="dg_preview")
    await client.post("/api/v1/data-governance/bootstrap", headers=headers)

    providers = await client.get("/api/v1/data-governance/providers", headers=headers)
    endpoints = await client.get("/api/v1/data-governance/endpoints", headers=headers)
    endpoint_id = endpoints.json()["items"][0]["id"]

    preview = await client.post(
        f"/api/v1/data-governance/endpoints/{endpoint_id}/preview",
        headers=headers,
        json={"params": {"symbol": "RB2510"}},
    )
    job = await client.post(
        f"/api/v1/data-governance/endpoints/{endpoint_id}/jobs",
        headers=headers,
        json={"params": {"symbol": "RB2510"}},
    )
    job_detail = await client.get(
        f"/api/v1/data-governance/jobs/{job.json()['id']}",
        headers=headers,
    )
    jobs = await client.get(
        "/api/v1/data-governance/jobs",
        headers=headers,
        params={"endpoint_id": endpoint_id},
    )

    assert providers.status_code == 200
    assert providers.json()["total"] >= 6
    assert preview.status_code == 200
    assert preview.json()["columns"]
    assert preview.json()["status"] == "ok"
    assert job.status_code == 201
    assert job.json()["status"] == "completed"
    assert job_detail.status_code == 200
    assert job_detail.json()["id"] == job.json()["id"]
    assert jobs.status_code == 200
    assert jobs.json()["items"]
