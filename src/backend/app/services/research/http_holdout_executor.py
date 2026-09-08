"""Pinned HTTP client for the separately deployed sealed evaluator service."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.services.research.holdout_execution_contract import (
    HoldoutExecutionCommand,
    HoldoutExecutionInspection,
    HoldoutExecutionResult,
)

_CONFIG_INVALID = "HOLDOUT_HTTP_EXECUTOR_CONFIG_INVALID"
_COMMAND_INVALID = "HOLDOUT_HTTP_EXECUTOR_COMMAND_INVALID"
_TIMEOUT = "HOLDOUT_HTTP_EXECUTOR_TIMEOUT"
_TRANSPORT_FAILED = "HOLDOUT_HTTP_EXECUTOR_TRANSPORT_FAILED"
_HTTP_FAILED = "HOLDOUT_HTTP_EXECUTOR_HTTP_FAILED"
_RESPONSE_INVALID = "HOLDOUT_HTTP_EXECUTOR_RESPONSE_INVALID"
_RESPONSE_TOO_LARGE = "HOLDOUT_HTTP_EXECUTOR_RESPONSE_TOO_LARGE"
_PATH = "/v1/holdout-executions"


class _HttpFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HttpSealedHoldoutExecutor:
    """Execute and inspect one stable operation without redirects or retries."""

    def __init__(
        self,
        *,
        endpoint: str,
        bearer_token: str,
        evaluator_identity: str,
        evaluator_image_digest: str,
        timeout_seconds: float,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        try:
            self._endpoint = _endpoint(endpoint)
            self._bearer_token = _secret(bearer_token)
            self._evaluator_identity = _identity(evaluator_identity)
            self._evaluator_image_digest = _image_digest(evaluator_image_digest)
            self._timeout_seconds = _timeout(timeout_seconds)
            if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 10_000_000:
                raise ValueError
            self._max_response_bytes = max_response_bytes
            if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
                raise ValueError
            self._transport = transport
        except Exception:
            raise ValueError(_CONFIG_INVALID) from None

    def __repr__(self) -> str:
        return "HttpSealedHoldoutExecutor(<redacted>)"

    async def execute(self, command: HoldoutExecutionCommand) -> HoldoutExecutionResult:
        verified = self._command(command)
        body = await self._request("POST", self._endpoint, command=verified)
        try:
            return HoldoutExecutionResult.from_mapping(_json_object(body), command=verified)
        except Exception:
            raise ValueError(_RESPONSE_INVALID) from None

    async def inspect(self, command: HoldoutExecutionCommand) -> HoldoutExecutionInspection:
        verified = self._command(command)
        operation_id = quote(str(verified.snapshot["operation_id"]), safe="")
        body = await self._request(
            "GET",
            f"{self._endpoint}/{operation_id}",
            command=verified,
        )
        try:
            return HoldoutExecutionInspection.from_mapping(_json_object(body), command=verified)
        except Exception:
            raise ValueError(_RESPONSE_INVALID) from None

    def _command(self, command: object) -> HoldoutExecutionCommand:
        try:
            if type(command) is not HoldoutExecutionCommand:
                raise ValueError
            verified = HoldoutExecutionCommand(
                payload=command.payload,
                command_hash=command.command_hash,
            )
            snapshot = verified.snapshot
            if (
                snapshot["evaluator_identity"] != self._evaluator_identity
                or snapshot["evaluator_image_digest"] != self._evaluator_image_digest
            ):
                raise ValueError
            return verified
        except Exception:
            raise ValueError(_COMMAND_INVALID) from None

    async def _request(
        self,
        method: str,
        url: str,
        *,
        command: HoldoutExecutionCommand,
    ) -> bytes:
        snapshot = command.snapshot
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(self._timeout_seconds),
                    follow_redirects=False,
                    trust_env=False,
                    verify=True,
                ) as client:
                    async with client.stream(
                        method,
                        url,
                        content=command.payload if method == "POST" else None,
                        headers={
                            "authorization": f"Bearer {self._bearer_token}",
                            "accept": "application/json",
                            "accept-encoding": "identity",
                            "content-type": "application/json",
                            "idempotency-key": str(snapshot["operation_id"]),
                            "x-command-hash": command.command_hash,
                        },
                    ) as response:
                        _headers(response, limit=self._max_response_bytes)
                        return await _body(response, limit=self._max_response_bytes)
        except _HttpFailure as exc:
            raise ValueError(exc.code) from None
        except (TimeoutError, httpx.TimeoutException):
            raise ValueError(_TIMEOUT) from None
        except httpx.HTTPError:
            raise ValueError(_TRANSPORT_FAILED) from None
        except ValueError:
            raise
        except Exception:
            raise ValueError(_TRANSPORT_FAILED) from None


def _endpoint(value: object) -> str:
    if type(value) is not str or not value or any(ord(char) <= 32 for char in value):
        raise ValueError
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != _PATH
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError
    _ = parsed.port
    httpx.URL(value)
    return value


def _secret(value: object) -> str:
    if type(value) is not str or not value or any(not 32 < ord(char) < 127 for char in value):
        raise ValueError
    return value


def _identity(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value.encode()) > 512
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or "://" in value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError
    return value


def _image_digest(value: object) -> str:
    if (
        type(value) is not str
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise ValueError
    return value


def _timeout(value: object) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= 3600:
        raise ValueError
    return float(value)


def _headers(response: httpx.Response, *, limit: int) -> None:
    if response.status_code != 200:
        raise _HttpFailure(_HTTP_FAILED)
    content_types = response.headers.get_list("content-type")
    if (
        len(content_types) != 1
        or content_types[0].split(";", 1)[0].strip().lower() != "application/json"
    ):
        raise _HttpFailure(_RESPONSE_INVALID)
    encodings = response.headers.get_list("content-encoding")
    if len(encodings) > 1 or (encodings and encodings[0].lower() != "identity"):
        raise _HttpFailure(_RESPONSE_INVALID)
    lengths = response.headers.get_list("content-length")
    if len(lengths) > 1:
        raise _HttpFailure(_RESPONSE_INVALID)
    if lengths and (not lengths[0].isdigit() or int(lengths[0]) > limit):
        raise _HttpFailure(_RESPONSE_TOO_LARGE)


async def _body(response: httpx.Response, *, limit: int) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=65_536):
        if len(body) + len(chunk) > limit:
            raise _HttpFailure(_RESPONSE_TOO_LARGE)
        body.extend(chunk)
    return bytes(body)


def _json_object(raw: bytes) -> dict[str, Any]:
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    if type(value) is not dict:
        raise ValueError
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError(value)
