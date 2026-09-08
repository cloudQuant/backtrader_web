"""Bounded HTTP boundary for a separately deployed discovery sandbox runner.

The endpoint, credential, and runner identity are deployment-owned.  This
adapter never discovers DNS, follows a route supplied by a command, executes
code locally, or exposes a remote response/error through its public errors.
"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.research.discovery_execution_contract import (
    DiscoveryExecutionCommand,
    DiscoveryExecutionResult,
)
from app.services.research.redaction import redact_sensitive_payload

_CONFIG_INVALID = "DISCOVERY_HTTP_EXECUTOR_CONFIG_INVALID"
_COMMAND_INVALID = "DISCOVERY_HTTP_EXECUTOR_COMMAND_INVALID"
_TIMEOUT_POLICY_INVALID = "DISCOVERY_HTTP_EXECUTOR_TIMEOUT_POLICY_INVALID"
_TIMEOUT = "DISCOVERY_HTTP_EXECUTOR_TIMEOUT"
_TRANSPORT_FAILED = "DISCOVERY_HTTP_EXECUTOR_TRANSPORT_FAILED"
_HTTP_FAILED = "DISCOVERY_HTTP_EXECUTOR_HTTP_FAILED"
_RESPONSE_INVALID = "DISCOVERY_HTTP_EXECUTOR_RESPONSE_INVALID"
_RESPONSE_TOO_LARGE = "DISCOVERY_HTTP_EXECUTOR_RESPONSE_TOO_LARGE"

_PATH = "/v1/discovery-executions"
_MAX_COMMAND_BYTES = 1_048_576
_MAX_RESPONSE_BYTES = 10_000_000
_MAX_TIMEOUT_SECONDS = 3_660
_MAX_IDENTIFIER_BYTES = 512


class _ExecutorFailure(Exception):
    """Internal sentinel that carries only a stable public error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class HttpDiscoverySandboxExecutor:
    """POST one immutable discovery command to one pinned HTTPS runner route."""

    def __init__(
        self,
        endpoint: str,
        bearer_token: str,
        runner_identity: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Accept only an explicit, deployment-owned HTTP runner configuration."""

        try:
            self._endpoint = _validated_endpoint(endpoint)
            self._bearer_token = _validated_bearer_token(bearer_token)
            self._runner_identity = _validated_runner_identity(runner_identity)
            self._timeout_seconds = _validated_timeout(timeout_seconds)
            if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
                raise ValueError
            self._transport = transport
        except Exception:
            raise ValueError(_CONFIG_INVALID) from None

    def __repr__(self) -> str:
        """Never include the endpoint or bearer token in diagnostic representations."""

        return "HttpDiscoverySandboxExecutor(<redacted>)"

    async def run(self, command: DiscoveryExecutionCommand) -> DiscoveryExecutionResult:
        """Dispatch one revalidated command without retries, redirects, or proxies."""

        verified, snapshot = self._revalidated_command(command)
        if snapshot["runner_identity"] != self._runner_identity:
            raise ValueError(_COMMAND_INVALID)
        wall_timeout = snapshot["policy"]["wall_timeout_seconds"]
        if not wall_timeout + 5 <= self._timeout_seconds <= wall_timeout + 60:
            raise ValueError(_TIMEOUT_POLICY_INVALID)
        response_limit = min(snapshot["policy"]["output_limit_bytes"], _MAX_RESPONSE_BYTES)

        try:
            # HTTPX phase timeouts do not impose a deadline on the combined
            # connection + request + response stream.  The outer deadline does.
            async with asyncio.timeout(self._timeout_seconds):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(
                        self._timeout_seconds,
                        connect=self._timeout_seconds,
                        read=self._timeout_seconds,
                        write=self._timeout_seconds,
                        pool=self._timeout_seconds,
                    ),
                    follow_redirects=False,
                    trust_env=False,
                    verify=True,
                ) as client:
                    async with client.stream(
                        "POST",
                        self._endpoint,
                        content=verified.payload,
                        headers={
                            "authorization": f"Bearer {self._bearer_token}",
                            "content-type": "application/json",
                            "accept": "application/json",
                            "accept-encoding": "identity",
                            "idempotency-key": snapshot["operation_id"],
                            "x-command-hash": verified.request_hash,
                        },
                    ) as response:
                        _require_response_headers(response, limit=response_limit)
                        body = await _read_response(response, limit=response_limit)
                        return _parse_result(body, command=verified)
        except _ExecutorFailure as exc:
            raise ValueError(exc.code) from None
        except (TimeoutError, httpx.TimeoutException):
            raise ValueError(_TIMEOUT) from None
        except httpx.HTTPError:
            raise ValueError(_TRANSPORT_FAILED) from None
        except Exception:
            raise ValueError(_TRANSPORT_FAILED) from None

    def _revalidated_command(
        self, command: object
    ) -> tuple[DiscoveryExecutionCommand, dict[str, Any]]:
        """Reconstruct the frozen contract immediately before the network boundary."""

        try:
            if type(command) is not DiscoveryExecutionCommand:
                raise ValueError
            if type(command.payload) is not bytes or len(command.payload) > _MAX_COMMAND_BYTES:
                raise ValueError
            verified = DiscoveryExecutionCommand(
                payload=command.payload,
                request_hash=command.request_hash,
            )
            return verified, verified.snapshot
        except Exception:
            raise ValueError(_COMMAND_INVALID) from None


def _validated_endpoint(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or redact_sensitive_payload(value) != value
    ):
        raise ValueError
    endpoint = urlsplit(value)
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
        or endpoint.path != _PATH
    ):
        raise ValueError
    try:
        port = endpoint.port
    except ValueError:
        raise ValueError from None
    if port is not None and not 1 <= port <= 65_535:
        raise ValueError
    httpx.URL(value)
    return value


def _validated_bearer_token(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
    ):
        raise ValueError
    return value


def _validated_runner_identity(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or "\x00" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES
        or redact_sensitive_payload(value) != value
        or "/" in value
        or "\\" in value
        or "://" in value
    ):
        raise ValueError
    return value


def _validated_timeout(value: object) -> float:
    if (
        type(value) not in {int, float}
        or not math.isfinite(value)
        or not 0 < value <= _MAX_TIMEOUT_SECONDS
    ):
        raise ValueError
    return float(value)


def _require_response_headers(response: httpx.Response, *, limit: int) -> None:
    if response.status_code != 200:
        raise _ExecutorFailure(_HTTP_FAILED)
    content_types = response.headers.get_list("content-type")
    if (
        len(content_types) != 1
        or content_types[0].split(";", 1)[0].strip().lower() != "application/json"
    ):
        raise _ExecutorFailure(_RESPONSE_INVALID)
    encodings = response.headers.get_list("content-encoding")
    if len(encodings) > 1 or (encodings and encodings[0].strip().lower() != "identity"):
        raise _ExecutorFailure(_RESPONSE_INVALID)
    lengths = response.headers.get_list("content-length")
    if len(lengths) > 1:
        raise _ExecutorFailure(_RESPONSE_INVALID)
    if lengths:
        length = lengths[0]
        if (
            not length
            or len(length) > len(str(_MAX_RESPONSE_BYTES))
            or not length.isascii()
            or not length.isdecimal()
        ):
            raise _ExecutorFailure(_RESPONSE_INVALID)
        if int(length) > limit:
            raise _ExecutorFailure(_RESPONSE_TOO_LARGE)


async def _read_response(response: httpx.Response, *, limit: int) -> bytes:
    body = bytearray()
    # Header validation already rejects every non-identity content encoding;
    # therefore ``aiter_bytes`` cannot transparently decompress an accepted
    # response, while remaining compatible with HTTPX MockTransport bodies.
    async for chunk in response.aiter_bytes(chunk_size=65_536):
        if len(body) + len(chunk) > limit:
            raise _ExecutorFailure(_RESPONSE_TOO_LARGE)
        body.extend(chunk)
    return bytes(body)


def _parse_result(raw: bytes, *, command: DiscoveryExecutionCommand) -> DiscoveryExecutionResult:
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_json_constant,
        )
        if type(decoded) is not dict:
            raise ValueError
        return DiscoveryExecutionResult.from_mapping(decoded, command=command)
    except Exception:
        raise _ExecutorFailure(_RESPONSE_INVALID) from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> Any:
    raise ValueError
