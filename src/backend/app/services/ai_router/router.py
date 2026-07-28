from __future__ import annotations

import asyncio
import inspect
import json
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

_LiteLLMCompletion = Callable[..., Awaitable[Any] | Any]
_URLOpen = Callable[..., Any]


@dataclass(frozen=True)
class ChatCompletionResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning: str | None = None


class AIChatRouter:
    def __init__(
        self,
        *,
        litellm_completion: _LiteLLMCompletion | None = None,
        urlopen: _URLOpen | None = None,
    ) -> None:
        self._litellm_completion = (
            litellm_completion if litellm_completion is not None else _load_litellm_completion()
        )
        self._urlopen = urlopen or urllib.request.urlopen

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatCompletionResponse:
        request_timeout = max(float(timeout), 0.001)
        if self._should_use_litellm(provider, model):
            request = self._call_litellm(
                messages=messages,
                model=model,
                temperature=temperature,
                api_base=base_url,
                api_key=api_key,
                timeout=request_timeout,
                max_tokens=max_tokens,
            )
        else:
            request = asyncio.to_thread(
                self._call_openai_compatible,
                messages=messages,
                model=model,
                base_url=base_url or "",
                api_key=api_key or "",
                timeout=request_timeout,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        return await asyncio.wait_for(request, timeout=request_timeout)

    def _should_use_litellm(self, provider: str | None, model: str) -> bool:
        if self._litellm_completion is None:
            return False
        if provider == "openai_compatible":
            return False
        return "/" in model or provider == "litellm"

    async def _call_litellm(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        api_base: str | None,
        api_key: str | None,
        timeout: float,
        max_tokens: int | None,
    ) -> ChatCompletionResponse:
        assert self._litellm_completion is not None
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = self._litellm_completion(**kwargs)
        if inspect.isawaitable(response):
            response = await response
        return _parse_chat_response(response, fallback_model=model, provider="litellm")

    def _call_openai_compatible(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        base_url: str,
        api_key: str,
        timeout: float,
        temperature: float,
        max_tokens: int | None,
    ) -> ChatCompletionResponse:
        endpoint = resolve_openai_compatible_endpoint(base_url)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with self._urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        return _parse_chat_response(body, fallback_model=model, provider="openai_compatible")


def resolve_openai_compatible_endpoint(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _load_litellm_completion() -> _LiteLLMCompletion | None:
    try:
        from litellm import acompletion
    except ImportError:
        return None
    return acompletion


def _parse_chat_response(
    response: Any,
    *,
    fallback_model: str,
    provider: str,
) -> ChatCompletionResponse:
    body = _to_mapping(response)
    content = _extract_content(body)
    usage = _to_mapping(body.get("usage") or {})
    return ChatCompletionResponse(
        content=content,
        model=str(body.get("model") or fallback_model),
        provider=provider,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        reasoning=_extract_reasoning(body),
    )


def _to_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _extract_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = _to_mapping(choices[0])
    message = _to_mapping(first_choice.get("message") or {})
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            item_map = _to_mapping(item)
            text = item_map.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_reasoning(body: dict[str, Any]) -> str | None:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = _to_mapping(choices[0])
    message = _to_mapping(first_choice.get("message") or {})
    reasoning = message.get("reasoning") or message.get("reasoning_content")
    return str(reasoning).strip() if reasoning else None


_default_router: AIChatRouter | None = None


def get_ai_chat_router() -> AIChatRouter:
    global _default_router
    if _default_router is None:
        _default_router = AIChatRouter()
    return _default_router
