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
        "together",
        "groq",
    }
    assert next(provider for provider in providers if provider.name == "ollama").base_url == (
        "http://localhost:11434"
    )


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
