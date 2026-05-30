from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.db.database import async_session_maker, create_default_admin
from app.models.ai_call_log import AICallLog
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


async def _insert_ai_log(**overrides) -> AICallLog:
    values = {
        "user_id": None,
        "request_id": None,
        "service_name": "ai_chat",
        "mode": "knowledge_qa",
        "model_name": "gpt-4o-mini",
        "provider": "openai_compatible",
        "prompt_template_id": None,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "estimated_cost_usd": 0.00001,
        "latency_ms": 100,
        "status": "success",
        "error_code": None,
        "error_message": None,
        "created_at": datetime.now(timezone.utc),
        "response_chars": 20,
        "prompt_hash": "a" * 64,
    }
    values.update(overrides)
    record = AICallLog(**values)
    async with async_session_maker() as session:
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return record


@pytest.mark.asyncio
async def test_admin_ai_usage_aggregates_calls_by_service_model_user_and_day(client: AsyncClient):
    _, user_headers = await register_and_login(client, username="ai_usage_user")
    user_id = await _current_user_id(client, user_headers)
    _, other_headers = await register_and_login(client, username="ai_usage_other_user")
    other_user_id = await _current_user_id(client, other_headers)
    now = datetime(2026, 5, 24, 8, 30, tzinfo=timezone.utc)
    await _insert_ai_log(
        user_id=user_id,
        service_name="ai_chat",
        model_name="gpt-4o-mini",
        total_tokens=100,
        estimated_cost_usd=0.001,
        latency_ms=120,
        created_at=now,
    )
    await _insert_ai_log(
        user_id=user_id,
        service_name="ai_chat",
        model_name="gpt-4o-mini",
        total_tokens=40,
        estimated_cost_usd=0.0004,
        latency_ms=80,
        status="failed",
        error_code="HTTPError",
        created_at=now + timedelta(minutes=1),
        prompt_hash="b" * 64,
    )
    await _insert_ai_log(
        user_id=other_user_id,
        service_name="strategy_explainer",
        mode="strategy_review",
        model_name="gpt-4o",
        total_tokens=200,
        estimated_cost_usd=0.006,
        latency_ms=350,
        created_at=now + timedelta(days=1),
        prompt_hash="c" * 64,
    )

    response = await client.get("/api/v1/admin/ai/usage", headers=await _get_admin_headers(client))

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_calls"] == 3
    assert data["summary"]["failed_calls"] == 1
    assert data["summary"]["total_tokens"] == 340
    assert data["summary"]["estimated_cost_usd"] == pytest.approx(0.0074)
    assert {item["service_name"]: item["total_calls"] for item in data["by_service"]} == {
        "ai_chat": 2,
        "strategy_explainer": 1,
    }
    assert {item["model_name"]: item["total_tokens"] for item in data["by_model"]} == {
        "gpt-4o-mini": 140,
        "gpt-4o": 200,
    }
    assert {item["user_id"]: item["total_calls"] for item in data["by_user"]}[user_id] == 2
    assert data["by_day"][0]["date"] == "2026-05-24"


@pytest.mark.asyncio
async def test_admin_ai_failure_and_slow_call_endpoints_report_diagnostics(client: AsyncClient):
    await _insert_ai_log(service_name="ai_chat", status="success", latency_ms=100)
    await _insert_ai_log(
        service_name="ai_chat",
        status="failed",
        error_code="HTTPError",
        error_message="upstream failed",
        latency_ms=900,
        prompt_hash="b" * 64,
    )
    await _insert_ai_log(
        service_name="strategy_explainer",
        mode="strategy_review",
        status="failed",
        error_code="TimeoutError",
        error_message="timeout",
        latency_ms=1500,
        prompt_hash="c" * 64,
    )
    headers = await _get_admin_headers(client)

    failures = await client.get("/api/v1/admin/ai/failures", headers=headers)
    slow_calls = await client.get("/api/v1/admin/ai/slow-calls", headers=headers)

    assert failures.status_code == 200
    failure_data = failures.json()
    assert failure_data["summary"]["failed_calls"] == 2
    assert failure_data["summary"]["failure_rate"] == pytest.approx(2 / 3)
    assert {item["error_code"]: item["failed_calls"] for item in failure_data["by_error_code"]} == {
        "HTTPError": 1,
        "TimeoutError": 1,
    }
    assert failure_data["by_service"][0]["failed_calls"] >= 1

    assert slow_calls.status_code == 200
    slow_data = slow_calls.json()
    assert slow_data["summary"]["p95_latency_ms"] >= 900
    assert slow_data["summary"]["p99_latency_ms"] >= 900
    assert slow_data["top_calls"][0]["latency_ms"] == 1500
    assert "prompt_hash" not in slow_data["top_calls"][0]
    assert "error_message" not in slow_data["top_calls"][0]


@pytest.mark.asyncio
async def test_my_ai_usage_only_returns_current_user_records(client: AsyncClient):
    _, headers = await register_and_login(client, username="my_ai_usage_user")
    user_id = await _current_user_id(client, headers)
    _, other_headers = await register_and_login(client, username="other_ai_usage_user")
    other_user_id = await _current_user_id(client, other_headers)
    await _insert_ai_log(user_id=user_id, total_tokens=50, estimated_cost_usd=0.002)
    await _insert_ai_log(
        user_id=other_user_id, total_tokens=500, estimated_cost_usd=0.02, prompt_hash="b" * 64
    )

    response = await client.get("/api/v1/me/ai/usage", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_calls"] == 1
    assert data["summary"]["total_tokens"] == 50
    assert data["summary"]["estimated_cost_usd"] == pytest.approx(0.002)
    assert "by_user" not in data


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin_ai_observability(client: AsyncClient):
    _, headers = await register_and_login(client, username="not_ai_admin")

    response = await client.get("/api/v1/admin/ai/usage", headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_ai_provider_health_reports_configured_providers(
    client: AsyncClient, monkeypatch
):
    from app.services.ai_router.health import AIProviderHealthService, ProviderHealth

    async def fake_check_all(self):
        return [
            ProviderHealth(
                name="openai",
                display_name="OpenAI",
                provider_type="litellm",
                available=False,
                models=["gpt-4o-mini"],
                error="OPENAI_API_KEY not configured",
            ),
            ProviderHealth(
                name="ollama",
                display_name="Ollama",
                provider_type="litellm",
                base_url="http://localhost:11434",
                available=True,
                models=["qwen2.5-coder:7b"],
                error=None,
            ),
        ]

    monkeypatch.setattr(AIProviderHealthService, "check_all", fake_check_all)

    response = await client.get(
        "/api/v1/admin/ai/providers/health",
        headers=await _get_admin_headers(client),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {"total": 2, "available": 1, "unavailable": 1}
    assert {provider["name"]: provider["available"] for provider in data["providers"]} == {
        "openai": False,
        "ollama": True,
    }
    assert data["providers"][1]["base_url"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin_ai_provider_health(client: AsyncClient):
    _, headers = await register_and_login(client, username="not_ai_provider_admin")

    response = await client.get("/api/v1/admin/ai/providers/health", headers=headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_my_ai_available_models_returns_models_and_current_preferences(client: AsyncClient):
    _, headers = await register_and_login(client, username="ai_model_pref_user")

    response = await client.get("/api/v1/me/ai/available-models", headers=headers)

    assert response.status_code == 200
    data = response.json()
    provider_names = {provider["name"] for provider in data["providers"]}
    assert {"openai", "ollama"}.issubset(provider_names)
    assert any(model["model"] == "gpt-4o-mini" for model in data["models"])
    assert any(model["provider"] == "ollama" for model in data["models"])
    assert data["preferences"]["provider"] is None
    assert data["preferences"]["model"] is None


@pytest.mark.asyncio
async def test_my_ai_preferences_can_be_saved_and_returned(client: AsyncClient):
    _, headers = await register_and_login(client, username="ai_model_save_user")

    saved = await client.patch(
        "/api/v1/me/ai/preferences",
        headers=headers,
        json={"provider": "ollama", "model": "ollama/qwen2.5-coder:7b"},
    )
    loaded = await client.get("/api/v1/me/ai/available-models", headers=headers)

    assert saved.status_code == 200
    assert saved.json()["preferences"] == {
        "provider": "ollama",
        "model": "ollama/qwen2.5-coder:7b",
    }
    assert loaded.status_code == 200
    assert loaded.json()["preferences"] == {
        "provider": "ollama",
        "model": "ollama/qwen2.5-coder:7b",
    }


@pytest.mark.asyncio
async def test_my_ai_preferences_reject_unknown_model(client: AsyncClient):
    _, headers = await register_and_login(client, username="ai_model_invalid_user")

    response = await client.patch(
        "/api/v1/me/ai/preferences",
        headers=headers,
        json={"provider": "ollama", "model": "missing-model"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Selected AI model is not available"


@pytest.mark.asyncio
async def test_my_ai_preferences_test_checks_selected_provider(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from app.services.ai_router.health import AIProviderHealthService, ProviderHealth

    async def fake_check_all(self):
        return [
            ProviderHealth(
                name="ollama",
                display_name="Ollama",
                provider_type="litellm",
                available=True,
                base_url="http://localhost:11434",
                models=["ollama/qwen2.5-coder:7b"],
            )
        ]

    monkeypatch.setattr(AIProviderHealthService, "check_all", fake_check_all)
    _, headers = await register_and_login(client, username="ai_model_test_user")

    response = await client.post(
        "/api/v1/me/ai/preferences/test",
        headers=headers,
        json={"provider": "ollama", "model": "ollama/qwen2.5-coder:7b"},
    )

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["provider"] == "ollama"
    assert response.json()["model"] == "ollama/qwen2.5-coder:7b"


async def _current_user_id(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    return str(response.json()["id"])
