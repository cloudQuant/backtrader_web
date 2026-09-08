"""HTTP-boundary tests for the separately deployed discovery sandbox runner."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services.research.discovery_execution_contract import DiscoveryExecutionCommand
from app.services.research.http_discovery_sandbox import HttpDiscoverySandboxExecutor


def _command(
    *,
    runner_identity: str = "discovery-runner-v1",
    wall_timeout_seconds: int = 60,
    output_limit_bytes: int = 1_000_000,
) -> DiscoveryExecutionCommand:
    return DiscoveryExecutionCommand.from_mapping(
        {
            "schema_version": "discovery-execution-command-v1",
            "operation_id": "discovery-operation-1",
            "task_id": "task-1",
            "run_id": "run-1",
            "stage_attempt_id": "attempt-1",
            "candidate_id": "candidate-1",
            "stage": "VALIDATE_DISCOVERY",
            "candidate_hash": "a" * 64,
            "run_request_hash": "b" * 64,
            "lease_token_hash": "c" * 64,
            "environment_hash": "d" * 64,
            "cost_model_hash": "e" * 64,
            "runner_identity": runner_identity,
            "profile": {
                "id": "discovery-profile",
                "version": "v1",
                "evidence_hash": "f" * 64,
            },
            "quota": {"reservation_id": "reservation-1", "fencing_token": 1},
            "code": {"artifact_id": "code-1", "content_hash": "1" * 64, "size_bytes": 128},
            "dependencies": {
                "artifact_id": "dependencies-1",
                "content_hash": "2" * 64,
                "size_bytes": 64,
            },
            "dataset": {
                "snapshot_id": "snapshot-1",
                "snapshot_identity_hash": "3" * 64,
                "object_receipt_id": "receipt-1",
                "object_digest": "4" * 64,
                "object_size_bytes": 256,
                "partition_kind": "DISCOVERY",
            },
            "params": {"lookback": 20, "symbols": ["RB0"]},
            "execution_policy": {"engine": "backtrader", "seed": 7},
            "policy": {
                "version": "discovery-policy-v1",
                "image_digest": f"sha256:{'5' * 64}",
                "network_mode": "none",
                "input_read_only": True,
                "output_path": "/sandbox/output",
                "cpu_limit": 1,
                "memory_limit_mb": 256,
                "pid_limit": 64,
                "wall_timeout_seconds": wall_timeout_seconds,
                "output_limit_bytes": output_limit_bytes,
            },
        }
    )


def _result_payload(command: DiscoveryExecutionCommand, **changes: object) -> dict[str, object]:
    snapshot = command.snapshot
    result: dict[str, object] = {
        "schema_version": "discovery-execution-result-v1",
        "operation_id": snapshot["operation_id"],
        "command_hash": command.request_hash,
        "runner_identity": snapshot["runner_identity"],
        "image_digest": snapshot["policy"]["image_digest"],
        "status": "SUCCEEDED",
        "exit_code": 0,
        "elapsed_milliseconds": 500,
        "observed_market_performance": True,
        "returns": [0.0125, -0.004],
        "error_code": None,
    }
    result.update(changes)
    return result


def _result_bytes(command: DiscoveryExecutionCommand, **changes: object) -> bytes:
    return json.dumps(
        _result_payload(command, **changes),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _executor(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    endpoint: str = "https://runner.internal/v1/discovery-executions",
    bearer_token: str = "local-discovery-bearer",
    runner_identity: str = "discovery-runner-v1",
    timeout_seconds: int | float = 65,
) -> HttpDiscoverySandboxExecutor:
    return HttpDiscoverySandboxExecutor(
        endpoint=endpoint,
        bearer_token=bearer_token,
        runner_identity=runner_identity,
        timeout_seconds=timeout_seconds,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_executor_sends_exact_canonical_command_to_the_fixed_https_route() -> None:
    command = _command()
    calls: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "identity"},
            content=_result_bytes(command),
        )

    executor = _executor(transport=httpx.MockTransport(respond))

    result = await executor.run(command)

    assert result.snapshot == _result_payload(command)
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url) == "https://runner.internal/v1/discovery-executions"
    assert bytes(request.content) == command.payload
    assert request.headers["idempotency-key"] == command.snapshot["operation_id"]
    assert request.headers["x-command-hash"] == command.request_hash
    assert request.headers["authorization"] == "Bearer local-discovery-bearer"
    assert request.headers["accept-encoding"] == "identity"


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://runner.internal/v1/discovery-executions",
        "https://runner.internal/v1/discovery-executions/",
        "https://runner.internal/v1/discovery-executions?token=leak",
        "https://runner.internal/v1/discovery-executions#fragment",
        "https://user:password@runner.internal/v1/discovery-executions",
        "https://runner.internal:0/v1/discovery-executions",
        "https://runner.internal:99999/v1/discovery-executions",
        "https://runner.internal\n/v1/discovery-executions",
    ),
)
def test_executor_rejects_implicit_or_unsafe_routes_without_leaking_them(endpoint: str) -> None:
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_CONFIG_INVALID$") as error:
        _executor(endpoint=endpoint)

    assert endpoint not in str(error.value)


@pytest.mark.parametrize(
    "bearer_token,timeout_seconds",
    (
        ("local\r\nInjected: yes", 65),
        ("", 65),
        ("local-discovery-bearer", 0),
        ("local-discovery-bearer", 3661),
        ("local-discovery-bearer", True),
    ),
)
def test_executor_rejects_unsafe_tokens_and_constructor_timeouts(
    bearer_token: str, timeout_seconds: object
) -> None:
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_CONFIG_INVALID$") as error:
        _executor(bearer_token=bearer_token, timeout_seconds=timeout_seconds)

    if bearer_token:
        assert bearer_token not in repr(error.value)


def test_executor_rejects_control_bearing_runner_identity() -> None:
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_CONFIG_INVALID$"):
        _executor(runner_identity="discovery\ridentity")


@pytest.mark.asyncio
async def test_executor_revalidates_command_identity_and_timeout_before_network() -> None:
    calls: list[httpx.Request] = []
    transport = httpx.MockTransport(
        lambda request: calls.append(request) or httpx.Response(200, content=b"{}")
    )

    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_COMMAND_INVALID$"):
        await _executor(transport=transport).run(_command(runner_identity="other-runner"))
    assert calls == []

    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_TIMEOUT_POLICY_INVALID$"):
        await _executor(transport=transport, timeout_seconds=64).run(_command())
    assert calls == []

    tampered = _command()
    object.__setattr__(tampered, "request_hash", "0" * 64)
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_COMMAND_INVALID$"):
        await _executor(transport=transport).run(tampered)
    assert calls == []


@pytest.mark.asyncio
async def test_executor_enforces_a_total_timeout_and_cancels_the_transport() -> None:
    command = _command(wall_timeout_seconds=1)
    cancelled = asyncio.Event()

    async def wait_forever(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        raise AssertionError("unreachable")

    executor = _executor(transport=httpx.MockTransport(wait_forever), timeout_seconds=6)

    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_TIMEOUT$"):
        await asyncio.wait_for(executor.run(command), timeout=7)
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", (302, 401, 429, 500))
async def test_executor_never_redirects_retries_or_exposes_http_response_content(
    status: int,
) -> None:
    command = _command()
    calls: list[httpx.Request] = []
    token = "runner-bearer-secret"

    async def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            headers={"location": "https://attacker.example/secret"},
            content=b"remote-secret-response",
        )

    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_HTTP_FAILED$") as error:
        await _executor(transport=httpx.MockTransport(respond), bearer_token=token).run(command)

    assert len(calls) == 1
    assert token not in str(error.value)
    assert "attacker" not in str(error.value)
    assert "remote-secret-response" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers,body",
    (
        ({"content-type": "text/plain"}, b"not-json"),
        ({"content-type": "application/json", "content-encoding": "gzip"}, b"compressed"),
        ({"content-type": "application/json"}, b"\xff"),
    ),
)
async def test_executor_rejects_unsafe_response_headers_and_encoding(
    headers: dict[str, str], body: bytes
) -> None:
    command = _command()

    class RawResponseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield body

        async def aclose(self) -> None:
            return None

    def response() -> httpx.Response:
        if headers.get("content-encoding") == "gzip":
            # A streaming response avoids HTTPX eagerly attempting to decode
            # intentionally malformed gzip test bytes before the adapter can
            # reject its non-identity content-encoding header.
            return httpx.Response(200, headers=headers, stream=RawResponseStream())
        return httpx.Response(200, headers=headers, content=body)

    executor = _executor(transport=httpx.MockTransport(lambda request: response()))

    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_RESPONSE_INVALID$"):
        await executor.run(command)


@pytest.mark.asyncio
async def test_executor_rejects_duplicate_keys_nonfinite_json_and_wrong_result_binding() -> None:
    command = _command()
    valid = _result_bytes(command)
    duplicate = valid[:-1] + b',"operation_id":"other-operation"}'
    nonfinite = valid.replace(b"0.0125", b"NaN", 1)
    wrong_binding = _result_bytes(command, command_hash="f" * 64)

    for body in (duplicate, nonfinite, wrong_binding):
        executor = _executor(
            transport=httpx.MockTransport(
                lambda request, body=body: httpx.Response(
                    200, headers={"content-type": "application/json"}, content=body
                )
            )
        )
        with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_RESPONSE_INVALID$"):
            await executor.run(command)


@pytest.mark.asyncio
async def test_executor_checks_declared_and_streamed_response_limits_and_closes_streams() -> None:
    command = _command(output_limit_bytes=256)

    header_limited = _executor(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/json", "content-length": "257"},
                content=b"{}",
            )
        )
    )
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_RESPONSE_TOO_LARGE$"):
        await header_limited.run(command)

    class OversizedStream(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self):
            yield b"x" * 128
            yield b"y" * 129

        async def aclose(self) -> None:
            self.closed = True

    stream = OversizedStream()
    stream_limited = _executor(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, headers={"content-type": "application/json"}, stream=stream
            )
        )
    )
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_RESPONSE_TOO_LARGE$"):
        await stream_limited.run(command)
    assert stream.closed


@pytest.mark.asyncio
async def test_executor_rejects_a_non_httpx_transport_before_any_request() -> None:
    with pytest.raises(ValueError, match="^DISCOVERY_HTTP_EXECUTOR_CONFIG_INVALID$"):
        _executor(transport=object())  # type: ignore[arg-type]
