"""Transport-contract tests; never sends a request to an external provider."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from hashlib import sha256

import httpx
import pytest
from pydantic import SecretStr

from app.services.research.llm_gateway import ProviderRequest


def _config(**changes):
    from app.services.research.openai_compatible_provider import OpenAICompatibleProviderConfig

    return OpenAICompatibleProviderConfig(
        **{
            "provider_id": "operator-route-v1",
            "endpoint_url": "https://provider.example/v1/chat/completions",
            "model_id": "pinned-model-v1",
            "api_key": SecretStr("local-test-credential"),
            **changes,
        }
    )


def _request():
    return ProviderRequest(
        resolved_model="pinned-model-v1",
        prompt_template_version="prompt-v1",
        system_input={"prompt_content": "Return the reviewed JSON schema"},
        typed_input={"hypothesis": {"question": "momentum"}},
        sampling_params={"temperature": 0.1, "max_tokens": 16},
    )


def _body(**changes):
    return {
        "id": "request-123",
        "model": "pinned-model-v1",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"content": "draft"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        **changes,
    }


@pytest.mark.asyncio
async def test_adapter_preserves_response_identity_and_sends_only_fixed_request_fields():
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json=_body())

    config = _config()
    provider = OpenAICompatibleResearchProvider(
        config=config, transport=httpx.MockTransport(respond)
    )
    result = await provider.generate(_request())
    assert result.provider_request_id == "request-123"
    assert result.observed_model == "pinned-model-v1"
    assert result.token_usage == _body()["usage"]
    assert result.output == "draft"
    assert result.cost == {}  # Unknown, not a fabricated zero-cost bill.
    assert result.fallback_chain == ()
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload["model"] == "pinned-model-v1"
    assert payload["max_tokens"] == 16
    assert payload["stream"] is False and payload["n"] == 1
    assert [item["role"] for item in payload["messages"]] == ["system", "user"]
    assert calls[0].headers["authorization"] == "Bearer local-test-credential"
    assert "local-test-credential" not in repr(config)


@pytest.mark.asyncio
async def test_prepared_request_is_network_free_immutable_and_sends_the_exact_prepared_bytes():
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json=_body())

    provider = OpenAICompatibleResearchProvider(
        config=_config(), transport=httpx.MockTransport(respond)
    )

    prepared = provider.prepare(_request())

    assert calls == []
    assert prepared.provider_id == "operator-route-v1"
    assert prepared.model_id == "pinned-model-v1"
    assert prepared.max_output_tokens == 16
    assert (
        prepared.endpoint_hash
        == sha256(b"https://provider.example/v1/chat/completions").hexdigest()
    )
    assert prepared.body_hash == sha256(prepared.payload).hexdigest()
    with pytest.raises((AttributeError, TypeError)):
        prepared.payload = b"replacement"

    result = await provider.generate_prepared(prepared)

    assert result.output == "draft"
    assert len(calls) == 1
    assert bytes(calls[0].content) == prepared.payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prepared_change,payload_change",
    [
        ({"provider_id": "other-route"}, None),
        ({"model_id": "other-model"}, None),
        ({"endpoint_hash": "0" * 64}, None),
        ({"max_output_tokens": 15}, None),
        ({}, {"model": "other-model"}),
        ({}, {"max_tokens": 15}),
        ({}, {"tools": []}),
        ({}, {"response_format": {"type": "json_object"}}),
    ],
)
async def test_prepared_dispatch_rejects_metadata_or_body_tampering_before_network(
    prepared_change, payload_change
):
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider
    from app.services.research.provider_contract import PreparedProviderRequest

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json=_body())

    provider = OpenAICompatibleResearchProvider(
        config=_config(), transport=httpx.MockTransport(respond)
    )
    prepared = provider.prepare(_request())
    if payload_change is not None:
        payload = json.loads(prepared.payload)
        payload.update(payload_change)
        prepared = PreparedProviderRequest(
            payload=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            provider_id=prepared.provider_id,
            model_id=prepared.model_id,
            endpoint_hash=prepared.endpoint_hash,
            max_output_tokens=prepared.max_output_tokens,
        )
    prepared = replace(prepared, **prepared_change)

    with pytest.raises(ValueError, match="^LLM_PROVIDER_REQUEST_INVALID$"):
        await provider.generate_prepared(prepared)
    assert calls == []


def test_prepared_provider_request_rejects_mutable_or_invalid_contract_fields():
    from app.services.research.provider_contract import PreparedProviderRequest

    valid = {
        "payload": b"{}",
        "provider_id": "provider-v1",
        "model_id": "model-v1",
        "endpoint_hash": "a" * 64,
        "max_output_tokens": 1,
    }
    assert PreparedProviderRequest(**valid).body_hash == sha256(b"{}").hexdigest()

    for change in (
        {"payload": bytearray(b"{}")},
        {"payload": b""},
        {"provider_id": ""},
        {"model_id": "\x00"},
        {"endpoint_hash": "not-a-hash"},
        {"max_output_tokens": True},
        {"max_output_tokens": 0},
    ):
        with pytest.raises(ValueError, match="^LLM_PREPARED_REQUEST_INVALID$"):
            PreparedProviderRequest(**{**valid, **change})


@pytest.mark.parametrize(
    "url",
    [
        "http://provider.example/v1/chat/completions",
        "https://user:password@provider.example/v1/chat/completions",
        "https://provider.example/v1/chat/completions?key=secret",
        "https://provider.example/v1/chat/completions#fragment",
        "https://provider.example/v1/other",
    ],
)
def test_adapter_rejects_unsafe_or_implicit_endpoints(url):
    with pytest.raises(ValueError, match="^LLM_PROVIDER_CONFIG_INVALID$"):
        _config(endpoint_url=url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("resolved_model", "another-model"),
        ("sampling_params", {"base_url": "https://attacker.example"}),
        ("sampling_params", {"max_tokens": 2048}),
    ],
)
async def test_adapter_rejects_model_or_transport_overrides_before_network(field, value):
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(200, json=_body())

    provider = OpenAICompatibleResearchProvider(
        config=_config(), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ValueError, match="^LLM_PROVIDER_REQUEST_INVALID$"):
        await provider.generate(replace(_request(), **{field: value}))
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_adapter_never_redirects_retries_or_exposes_http_error_body(status):
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "https://attacker.example"}, text="secret"
        )

    provider = OpenAICompatibleResearchProvider(
        config=_config(), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ValueError, match="^LLM_PROVIDER_HTTP_FAILED$"):
        await provider.generate(_request())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_adapter_preserves_missing_usage_as_unknown_instead_of_zero():
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    provider = OpenAICompatibleResearchProvider(
        config=_config(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=_body(usage=None))),
    )
    response = await provider.generate(_request())
    assert response.token_usage == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"id": None},
        {"model": None},
        {"choices": []},
        {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]},
        {
            "choices": [
                {"finish_reason": "stop", "message": {"content": "draft", "tool_calls": [{}]}}
            ]
        },
    ],
)
async def test_adapter_refuses_incomplete_identity_or_nonfinal_output(changes):
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    provider = OpenAICompatibleResearchProvider(
        config=_config(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=_body(**changes))),
    )
    with pytest.raises(ValueError, match="^LLM_PROVIDER_RESPONSE_INVALID$"):
        await provider.generate(_request())


@pytest.mark.asyncio
async def test_adapter_has_total_timeout_even_when_transport_keeps_waiting():
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    cancelled = asyncio.Event()

    async def respond(request):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    provider = OpenAICompatibleResearchProvider(
        config=_config(timeout_seconds=0.05), transport=httpx.MockTransport(respond)
    )
    with pytest.raises(ValueError, match="^LLM_PROVIDER_TIMEOUT$"):
        await asyncio.wait_for(provider.generate(_request()), 1)
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_adapter_limits_response_bytes_and_closes_stream_on_rejection():
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider

    class ResponseStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"x" * 64
            yield b"y" * 64

        async def aclose(self):
            self.closed = True

    stream = ResponseStream()
    provider = OpenAICompatibleResearchProvider(
        config=_config(max_response_bytes=100),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "application/json"}, stream=stream
            )
        ),
    )
    with pytest.raises(ValueError, match="^LLM_PROVIDER_RESPONSE_TOO_LARGE$"):
        await provider.generate(_request())
    assert stream.closed
