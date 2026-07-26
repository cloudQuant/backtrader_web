import os

import pytest

from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_admin_can_save_ai_provider_config_without_exposing_secret(
    client, monkeypatch, tmp_path
):
    monkeypatch.setenv("AI_PROVIDER_CONFIG_PATH", str(tmp_path / "ai_provider_config.json"))

    _, admin_headers = await register_and_login(
        client,
        username="admin",
        password=os.environ.get("ADMIN_PASSWORD", "TestAdmin@12345"),
    )

    response = await client.put(
        "/api/v1/admin/ai/provider-configs/local_openai",
        headers=admin_headers,
        json={
            "display_name": "Local OpenAI",
            "provider_type": "openai_compatible",
            "base_url": "https://llm.example.com/v1",
            "api_key": "sk-local-secret",
            "models": ["local-model"],
            "enabled": True,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["provider"] == "local_openai"
    assert payload["api_key_configured"] is True
    assert "sk-local-secret" not in response.text

    models_response = await client.get("/api/v1/me/ai/available-models", headers=admin_headers)

    assert models_response.status_code == 200, models_response.text
    models_payload = models_response.json()
    assert {
        "provider": "local_openai",
        "model": "local-model",
        "display_name": "Local OpenAI / local-model",
    } in models_payload["models"]


@pytest.mark.asyncio
async def test_non_admin_cannot_update_ai_provider_config(client, monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER_CONFIG_PATH", str(tmp_path / "ai_provider_config.json"))
    _, headers = await register_and_login(client)

    response = await client.put(
        "/api/v1/admin/ai/provider-configs/local_openai",
        headers=headers,
        json={
            "display_name": "Local OpenAI",
            "provider_type": "openai_compatible",
            "base_url": "https://llm.example.com/v1",
            "api_key": "sk-local-secret",
            "models": ["local-model"],
            "enabled": True,
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_disabled_ai_provider_is_hidden_from_available_models(
    client,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("AI_PROVIDER_CONFIG_PATH", str(tmp_path / "ai_provider_config.json"))

    _, admin_headers = await register_and_login(
        client,
        username="admin",
        password=os.environ.get("ADMIN_PASSWORD", "TestAdmin@12345"),
    )

    response = await client.put(
        "/api/v1/admin/ai/provider-configs/local_openai",
        headers=admin_headers,
        json={
            "display_name": "Local OpenAI",
            "provider_type": "openai_compatible",
            "base_url": "https://llm.example.com/v1",
            "api_key": "sk-local-secret",
            "models": ["local-model"],
            "enabled": False,
        },
    )
    models_response = await client.get("/api/v1/me/ai/available-models", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert models_response.status_code == 200, models_response.text
    models_payload = models_response.json()
    assert "local_openai" not in {provider["name"] for provider in models_payload["providers"]}
    assert "local_openai" not in {model["provider"] for model in models_payload["models"]}


@pytest.mark.asyncio
async def test_deleted_default_ai_provider_is_hidden_from_admin_and_available_models(
    client,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("AI_PROVIDER_CONFIG_PATH", str(tmp_path / "ai_provider_config.json"))

    _, admin_headers = await register_and_login(
        client,
        username="admin",
        password=os.environ.get("ADMIN_PASSWORD", "TestAdmin@12345"),
    )

    response = await client.delete(
        "/api/v1/admin/ai/provider-configs/ollama",
        headers=admin_headers,
    )
    configs_response = await client.get("/api/v1/admin/ai/provider-configs", headers=admin_headers)
    models_response = await client.get("/api/v1/me/ai/available-models", headers=admin_headers)

    assert response.status_code == 204, response.text
    assert configs_response.status_code == 200, configs_response.text
    assert models_response.status_code == 200, models_response.text
    assert "ollama" not in {item["provider"] for item in configs_response.json()["items"]}
    assert "ollama" not in {provider["name"] for provider in models_response.json()["providers"]}
    assert "ollama" not in {model["provider"] for model in models_response.json()["models"]}
