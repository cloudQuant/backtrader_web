"""Bounded, non-retrying chat-completions transport for trusted GENERATE workers.

Configuration is deployment-owned. This adapter never reads environment files,
chooses another route, silently substitutes a model, or invents missing usage.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from app.services.research.llm_gateway import ProviderRequest, ProviderResponse
from app.services.research.provider_contract import PreparedProviderRequest
from app.services.research.redaction import redact_sensitive_payload


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProviderConfig:
    """An explicit HTTPS endpoint and model pin, never an end-user override."""

    provider_id: str
    endpoint_url: str
    model_id: str
    api_key: SecretStr = field(repr=False)
    timeout_seconds: float = 60
    max_output_tokens: int = 1024
    max_response_bytes: int = 2_097_152
    max_request_bytes: int = 524_288

    def __post_init__(self) -> None:
        try:
            _identity(self.provider_id, 128)
            _identity(self.model_id, 256)
            endpoint = urlsplit(self.endpoint_url)
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username is not None
                or endpoint.password is not None
                or endpoint.query
                or endpoint.fragment
                or not endpoint.path.endswith("/chat/completions")
                or any(ord(char) <= 32 or ord(char) >= 127 for char in self.endpoint_url)
                or redact_sensitive_payload(self.endpoint_url) != self.endpoint_url
                or any(part in {".", ".."} for part in endpoint.path.split("/"))
            ):
                raise ValueError
            httpx.URL(self.endpoint_url)  # Validate port and URI syntax before any call.
            if not isinstance(self.api_key, SecretStr):
                raise ValueError
            secret = self.api_key.get_secret_value()
            if not secret or any(ord(char) <= 32 or ord(char) >= 127 for char in secret):
                raise ValueError
            if (
                type(self.timeout_seconds) not in {int, float}
                or not math.isfinite(self.timeout_seconds)
                or not 0 < self.timeout_seconds <= 300
            ):
                raise ValueError
            for value, ceiling in (
                (self.max_output_tokens, 131_072),
                (self.max_response_bytes, 16_777_216),
                (self.max_request_bytes, 1_048_576),
            ):
                if type(value) is not int or not 0 < value <= ceiling:
                    raise ValueError
        except Exception:
            raise ValueError("LLM_PROVIDER_CONFIG_INVALID") from None


class OpenAICompatibleResearchProvider:
    """Perform one bounded request and retain the response's actual model/id."""

    def __init__(
        self,
        *,
        config: OpenAICompatibleProviderConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(config, OpenAICompatibleProviderConfig):
            raise ValueError("LLM_PROVIDER_CONFIG_INVALID")
        self._config = config
        self._transport = transport

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """No redirects, retries, implicit proxies, streaming completions or tools."""

        return await self.generate_prepared(self.prepare(request))

    def prepare(self, request: ProviderRequest) -> PreparedProviderRequest:
        """Serialize one validated request without opening a network connection."""

        payload = self._payload(request)
        maximum = self._validated_payload_maximum(payload)
        return PreparedProviderRequest(
            payload=payload,
            provider_id=self._config.provider_id,
            model_id=self._config.model_id,
            endpoint_hash=_endpoint_hash(self._config.endpoint_url),
            max_output_tokens=maximum,
        )

    async def generate_prepared(self, prepared: PreparedProviderRequest) -> ProviderResponse:
        """Dispatch only a prepared body that still matches this exact route."""

        payload = self._validated_prepared_payload(prepared)
        try:
            # HTTPX phase timeouts do not provide a whole-operation deadline.
            async with asyncio.timeout(self._config.timeout_seconds):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=self._config.timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        self._config.endpoint_url,
                        content=payload,
                        headers={
                            "authorization": f"Bearer {self._config.api_key.get_secret_value()}",
                            "content-type": "application/json",
                            "accept": "application/json",
                            "accept-encoding": "identity",
                        },
                    ) as response:
                        if response.status_code != 200:
                            raise ValueError("LLM_PROVIDER_HTTP_FAILED")
                        if (
                            response.headers.get("content-encoding", "identity").lower()
                            != "identity"
                        ):
                            raise ValueError("LLM_PROVIDER_RESPONSE_INVALID")
                        if (
                            response.headers.get("content-type", "").split(";")[0].strip().lower()
                            != "application/json"
                        ):
                            raise ValueError("LLM_PROVIDER_RESPONSE_INVALID")
                        declared = response.headers.get("content-length")
                        if declared is not None:
                            if not declared.isdecimal():
                                raise ValueError("LLM_PROVIDER_RESPONSE_INVALID")
                            if int(declared) > self._config.max_response_bytes:
                                raise ValueError("LLM_PROVIDER_RESPONSE_TOO_LARGE")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if len(body) + len(chunk) > self._config.max_response_bytes:
                                raise ValueError("LLM_PROVIDER_RESPONSE_TOO_LARGE")
                            body.extend(chunk)
                        return _parse_response(bytes(body))
        except (TimeoutError, httpx.TimeoutException):
            raise ValueError("LLM_PROVIDER_TIMEOUT") from None
        except httpx.HTTPError:
            raise ValueError("LLM_PROVIDER_TRANSPORT_FAILED") from None

    def _validated_prepared_payload(self, prepared: object) -> bytes:
        try:
            if not isinstance(prepared, PreparedProviderRequest):
                raise ValueError
            if (
                prepared.provider_id != self._config.provider_id
                or prepared.model_id != self._config.model_id
                or prepared.endpoint_hash != _endpoint_hash(self._config.endpoint_url)
            ):
                raise ValueError
            maximum = self._validated_payload_maximum(prepared.payload)
            if prepared.max_output_tokens != maximum:
                raise ValueError
            return prepared.payload
        except Exception:
            raise ValueError("LLM_PROVIDER_REQUEST_INVALID") from None

    def _validated_payload_maximum(self, payload: bytes) -> int:
        try:
            if type(payload) is not bytes or not 0 < len(payload) <= self._config.max_request_bytes:
                raise ValueError
            body = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
            if not isinstance(body, dict):
                raise ValueError
            allowed = {
                "model",
                "stream",
                "n",
                "max_tokens",
                "temperature",
                "top_p",
                "seed",
                "messages",
            }
            required = {"model", "stream", "n", "max_tokens", "messages"}
            if set(body) - allowed or not required.issubset(body):
                raise ValueError
            if (
                body["model"] != self._config.model_id
                or body["stream"] is not False
                or type(body["n"]) is not int
                or body["n"] != 1
            ):
                raise ValueError
            maximum = body["max_tokens"]
            if type(maximum) is not int or not 0 < maximum <= self._config.max_output_tokens:
                raise ValueError
            for key, ceiling in (("temperature", 2), ("top_p", 1)):
                if key in body and (
                    type(body[key]) not in {int, float}
                    or not math.isfinite(body[key])
                    or not 0 <= body[key] <= ceiling
                ):
                    raise ValueError
            if "seed" in body and (
                type(body["seed"]) is not int or not -(2**31) <= body["seed"] < 2**31
            ):
                raise ValueError
            messages = body["messages"]
            if type(messages) is not list or len(messages) != 2:
                raise ValueError
            for message, role in zip(messages, ("system", "user"), strict=True):
                if (
                    type(message) is not dict
                    or set(message) != {"role", "content"}
                    or message["role"] != role
                    or type(message["content"]) is not str
                ):
                    raise ValueError
            return maximum
        except Exception:
            raise ValueError("LLM_PROVIDER_REQUEST_INVALID") from None

    def _payload(self, request: ProviderRequest) -> bytes:
        try:
            if request.resolved_model != self._config.model_id:
                raise ValueError
            sampling = dict(request.sampling_params)
            if set(sampling) - {"temperature", "top_p", "seed", "max_tokens"}:
                raise ValueError
            maximum = sampling.pop("max_tokens", self._config.max_output_tokens)
            if type(maximum) is not int or not 0 < maximum <= self._config.max_output_tokens:
                raise ValueError
            for key, ceiling in (("temperature", 2), ("top_p", 1)):
                if key in sampling and (
                    type(sampling[key]) not in {int, float}
                    or not math.isfinite(sampling[key])
                    or not 0 <= sampling[key] <= ceiling
                ):
                    raise ValueError
            if "seed" in sampling and (
                type(sampling["seed"]) is not int or not -(2**31) <= sampling["seed"] < 2**31
            ):
                raise ValueError
            payload = {
                "model": self._config.model_id,
                "stream": False,
                "n": 1,
                "max_tokens": maximum,
                **sampling,
                "messages": [
                    {"role": "system", "content": _json(request.system_input)},
                    {"role": "user", "content": _json(request.typed_input)},
                ],
            }
            encoded = _json(payload).encode("utf-8")
            if len(encoded) > self._config.max_request_bytes:
                raise ValueError
            return encoded
        except Exception:
            raise ValueError("LLM_PROVIDER_REQUEST_INVALID") from None


def _parse_response(raw: bytes) -> ProviderResponse:
    try:
        body = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        if not isinstance(body, dict):
            raise ValueError
        request_id, model = body.get("id"), body.get("model")
        _identity(request_id, 256)
        _identity(model, 256)
        choices = body.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError
        choice = choices[0]
        message = choice["message"]
        if (
            choice.get("finish_reason") != "stop"
            or not isinstance(message, dict)
            or message.get("tool_calls")
            or message.get("function_call")
            or message.get("refusal")
        ):
            raise ValueError
        output = message.get("content")
        if not isinstance(output, str) or not output.strip():
            raise ValueError
        usage = body.get("usage")
        # Leave malformed non-null usage for gateway's audited shape validator.
        return ProviderResponse(
            output=output,
            provider_request_id=request_id,
            token_usage={} if usage is None else usage,
            cost={},
            observed_model=model,
        )
    except Exception:
        raise ValueError("LLM_PROVIDER_RESPONSE_INVALID") from None


def _identity(value: object, maximum: int) -> None:
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
        or "\x00" in value
        or redact_sensitive_payload(value) != value
    ):
        raise ValueError


def _endpoint_hash(endpoint_url: str) -> str:
    return sha256(endpoint_url.encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError
