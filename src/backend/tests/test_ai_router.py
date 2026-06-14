import json
from typing import Any

import pytest


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_default_provider_specs_include_core_providers() -> None:
    from app.services.ai_router.providers import get_default_provider_specs

    providers = get_default_provider_specs()

    assert {provider.name for provider in providers} >= {
        "openai",
        "anthropic",
        "ollama",
        "volcengine_ark",
        "siliconflow",
        "together",
        "groq",
    }
    assert next(provider for provider in providers if provider.name == "ollama").base_url == (
        "http://localhost:11434"
    )
    assert next(provider for provider in providers if provider.name == "volcengine_ark").base_url == (
        "https://ark.cn-beijing.volces.com/api/coding/v3"
    )
    volcengine_ark = next(provider for provider in providers if provider.name == "volcengine_ark")
    assert "doubao-seed-2.0-code" in volcengine_ark.models
    assert "doubao-seed-2.0-pro" in volcengine_ark.models
    assert "doubao-seed-2.0-lite" in volcengine_ark.models
    assert "doubao-seed-code" in volcengine_ark.models
    assert "minimax-m2.7" in volcengine_ark.models
    assert "minimax-m3" in volcengine_ark.models
    assert "glm-5.1" in volcengine_ark.models
    assert "deepseek-v4-flash" in volcengine_ark.models
    assert "deepseek-v4-pro" in volcengine_ark.models
    assert "kimi-k2.6" in volcengine_ark.models
    assert len(volcengine_ark.models) == 10
    assert "doubao-seed-1-8-251228" not in volcengine_ark.models
    assert "doubao-seed-2-0-pro-260215" not in volcengine_ark.models
    assert "doubao-seed-1-6-250615" not in volcengine_ark.models
    assert "doubao-seed-1-6-thinking-250615" not in volcengine_ark.models
    assert "doubao-seed-1-6-flash-250615" not in volcengine_ark.models
    siliconflow = next(provider for provider in providers if provider.name == "siliconflow")
    assert siliconflow.provider_type == "openai_compatible"
    assert siliconflow.base_url == "https://api.siliconflow.cn/v1"
    assert "deepseek-ai/DeepSeek-V4-Pro" in siliconflow.models
    assert "zai-org/GLM-5.1" in siliconflow.models


def test_provider_api_key_can_be_loaded_from_env_file(tmp_path, monkeypatch) -> None:
    from app.services.ai_router.providers import (
        AIProviderSpec,
        _read_env_file_values,
        get_provider_api_key,
        is_provider_configured,
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SILICONFLOW_TEST_API_KEY", raising=False)
    (tmp_path / ".env").write_text("SILICONFLOW_TEST_API_KEY=sk-local-test\n", encoding="utf-8")
    _read_env_file_values.cache_clear()

    spec = AIProviderSpec(
        name="siliconflow",
        display_name="硅基流动",
        provider_type="openai_compatible",
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_TEST_API_KEY",
        models=("deepseek-ai/DeepSeek-V4-Flash",),
    )

    try:
        assert get_provider_api_key(spec) == "sk-local-test"
        assert is_provider_configured(spec) is True
    finally:
        _read_env_file_values.cache_clear()


def test_ollama_health_check_reads_local_tags() -> None:
    from app.services.ai_router.ollama_adapter import check_ollama_health

    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeHTTPResponse(
            {"models": [{"name": "qwen2.5-coder:7b"}, {"name": "llama3.1:8b"}]}
        )

    health = check_ollama_health(base_url="http://localhost:11434", timeout=3, urlopen=fake_urlopen)

    assert captured["url"] == "http://localhost:11434/api/tags"
    assert captured["timeout"] == 3
    assert health.available is True
    assert health.models == ["qwen2.5-coder:7b", "llama3.1:8b"]
    assert health.error is None


def test_ollama_health_check_reports_unavailable_on_transport_error() -> None:
    from app.services.ai_router.ollama_adapter import check_ollama_health

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        raise OSError("connection refused")

    health = check_ollama_health(base_url="http://localhost:11434", timeout=1, urlopen=fake_urlopen)

    assert health.available is False
    assert health.models == []
    assert "connection refused" in str(health.error)


@pytest.mark.asyncio
async def test_chat_completion_uses_litellm_completion_when_available() -> None:
    from app.services.ai_router.router import AIChatRouter

    captured: dict[str, Any] = {}

    async def fake_litellm_completion(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            "model": "openai/gpt-4o-mini",
        }

    router = AIChatRouter(litellm_completion=fake_litellm_completion)

    response = await router.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="openai/gpt-4o-mini",
        temperature=0.1,
    )

    assert captured["model"] == "openai/gpt-4o-mini"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["temperature"] == 0.1
    assert response.content == "hello"
    assert response.prompt_tokens == 3
    assert response.completion_tokens == 4
    assert response.total_tokens == 7
    assert response.model == "openai/gpt-4o-mini"
    assert response.provider == "litellm"


@pytest.mark.asyncio
async def test_chat_completion_falls_back_to_openai_compatible_endpoint() -> None:
    from app.services.ai_router.router import AIChatRouter

    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeHTTPResponse(
            {
                "choices": [{"message": {"content": "fallback answer"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 5, "total_tokens": 7},
                "model": "gpt-4o-mini",
            }
        )

    router = AIChatRouter(litellm_completion=None, urlopen=fake_urlopen)

    response = await router.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
        provider="openai_compatible",
        base_url="http://provider.local/v1",
        api_key="sk-test",
        timeout=12,
        temperature=0.2,
    )

    assert captured["url"] == "http://provider.local/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["body"] == {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.2,
    }
    assert captured["timeout"] == 12
    assert response.content == "fallback answer"
    assert response.total_tokens == 7
    assert response.provider == "openai_compatible"
