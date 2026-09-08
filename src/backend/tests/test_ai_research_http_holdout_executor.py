from __future__ import annotations

import json
from importlib import import_module

import httpx
import pytest

from tests.test_ai_research_holdout_execution_contract import (
    _command,
    _result_payload,
)


def _module():
    return import_module("app.services.research.http_holdout_executor")


def _executor(*, transport=None, endpoint="https://holdout.internal/v1/holdout-executions"):
    return _module().HttpSealedHoldoutExecutor(
        endpoint=endpoint,
        bearer_token="deployment-only-secret",
        evaluator_identity="independent-holdout-evaluator",
        evaluator_image_digest=f"sha256:{'5' * 64}",
        timeout_seconds=30,
        max_response_bytes=10_000_000,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_execute_posts_once_with_idempotency_and_never_puts_secret_in_body() -> None:
    command = _command()
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "identity"},
            content=json.dumps(_result_payload(command), separators=(",", ":")).encode(),
        )

    result = await _executor(transport=httpx.MockTransport(respond)).execute(command)

    assert result.snapshot == _result_payload(command)
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.headers["idempotency-key"] == command.snapshot["operation_id"]
    assert request.headers["x-command-hash"] == command.command_hash
    assert request.headers["authorization"] == "Bearer deployment-only-secret"
    assert b"deployment-only-secret" not in bytes(request.content)


@pytest.mark.asyncio
@pytest.mark.parametrize("remote_status", ("OBSERVED", "UNKNOWN", "NOT_EXECUTED"))
async def test_inspect_uses_exact_operation_route_and_parses_all_outcomes(
    remote_status: str,
) -> None:
    command = _command()
    requests: list[httpx.Request] = []
    inspection = {
        "schema_version": "holdout-execution-inspection-v2",
        "operation_id": command.snapshot["operation_id"],
        "command_hash": command.command_hash,
        "evaluator_identity": command.snapshot["evaluator_identity"],
        "evaluator_image_digest": command.snapshot["evaluator_image_digest"],
        "status": remote_status,
        "result": _result_payload(command) if remote_status == "OBSERVED" else None,
        "error_code": ("HOLDOUT_REMOTE_OUTCOME_UNKNOWN" if remote_status == "UNKNOWN" else None),
    }

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "identity"},
            json=inspection,
        )

    observed = await _executor(transport=httpx.MockTransport(respond)).inspect(command)

    assert observed.status == remote_status
    assert str(requests[0].url).endswith("/v1/holdout-executions/holdout-operation-1")
    assert requests[0].method == "GET"


@pytest.mark.asyncio
async def test_timeout_and_remote_errors_are_stable_and_redacted_without_retry() -> None:
    command = _command()
    calls = 0

    async def fail(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, content=b"s3://sealed/path deployment-only-secret")

    with pytest.raises(ValueError, match="^HOLDOUT_HTTP_EXECUTOR_HTTP_FAILED$") as error:
        await _executor(transport=httpx.MockTransport(fail)).execute(command)

    assert calls == 1
    assert "sealed" not in str(error.value).lower()
    assert "secret" not in str(error.value).lower()


@pytest.mark.asyncio
async def test_execute_rejects_raw_sealed_values_on_http_response_wire() -> None:
    command = _command()
    raw_canary = 0.24681357924681357
    forged = _result_payload(command)
    terminal = forged["terminal_receipt"]
    assert isinstance(terminal, dict)
    terminal["returns"] = [raw_canary]

    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=forged)

    with pytest.raises(
        ValueError,
        match="^HOLDOUT_HTTP_EXECUTOR_RESPONSE_INVALID$",
    ) as error:
        await _executor(transport=httpx.MockTransport(respond)).execute(command)

    assert str(raw_canary) not in str(error.value)


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://holdout.internal/v1/holdout-executions",
        "https://holdout.internal/v1/holdout-executions/",
        "https://user:password@holdout.internal/v1/holdout-executions",
        "https://holdout.internal/v1/holdout-executions?token=secret",
    ),
)
def test_executor_accepts_only_pinned_https_collection_route(endpoint: str) -> None:
    with pytest.raises(ValueError, match="^HOLDOUT_HTTP_EXECUTOR_CONFIG_INVALID$"):
        _executor(endpoint=endpoint)
