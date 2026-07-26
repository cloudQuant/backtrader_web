import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.db.database import create_default_admin
from tests.conftest import register_and_login

settings = get_settings()


async def _get_admin_headers(client: AsyncClient) -> dict[str, str]:
    await create_default_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_prompt_templates_create_list_activate_and_test_render(client: AsyncClient):
    headers = await _get_admin_headers(client)
    first = await client.post(
        "/api/v1/admin/prompt-templates",
        headers=headers,
        json={
            "name": "knowledge_qa",
            "version": "v1",
            "content": "默认回答 {{question}}",
            "variables": ["question"],
        },
    )
    second = await client.post(
        "/api/v1/admin/prompt-templates",
        headers=headers,
        json={
            "name": "knowledge_qa",
            "version": "v2",
            "content": "新版回答 {{question}}，风险提示：{{risk_note}}",
            "variables": ["question", "risk_note"],
        },
    )

    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    activate_first = await client.patch(
        f"/api/v1/admin/prompt-templates/{first_id}/activate",
        headers=headers,
    )
    activate_second = await client.patch(
        f"/api/v1/admin/prompt-templates/{second_id}/activate",
        headers=headers,
    )
    listed = await client.get("/api/v1/admin/prompt-templates", headers=headers)
    rendered = await client.post(
        f"/api/v1/admin/prompt-templates/{second_id}/test",
        headers=headers,
        json={"variables": {"question": "什么是均线策略", "risk_note": "不要承诺收益"}},
    )

    assert activate_first.status_code == 200
    assert activate_first.json()["status"] == "active"
    assert activate_second.status_code == 200
    assert activate_second.json()["status"] == "active"
    assert listed.status_code == 200
    status_by_id = {item["id"]: item["status"] for item in listed.json()["items"]}
    assert status_by_id[first_id] == "archived"
    assert status_by_id[second_id] == "active"
    assert rendered.status_code == 200
    assert rendered.json()["rendered_prompt"] == "新版回答 什么是均线策略，风险提示：不要承诺收益"
    assert rendered.json()["missing_variables"] == []


@pytest.mark.asyncio
async def test_admin_prompt_template_rollout_percentage_can_be_saved(client: AsyncClient):
    headers = await _get_admin_headers(client)

    response = await client.post(
        "/api/v1/admin/prompt-templates",
        headers=headers,
        json={
            "name": "strategy_review",
            "version": "v-canary",
            "content": "灰度模板 {{question}}",
            "variables": ["question"],
            "rollout_percentage": 25,
        },
    )

    assert response.status_code == 201
    assert response.json()["rollout_percentage"] == 25


@pytest.mark.asyncio
async def test_non_admin_cannot_manage_prompt_templates(client: AsyncClient):
    _, headers = await register_and_login(client, username="prompt_registry_non_admin")

    response = await client.get("/api/v1/admin/prompt-templates", headers=headers)

    assert response.status_code == 403
