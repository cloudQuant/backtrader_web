from __future__ import annotations

import math
from copy import deepcopy
from hashlib import sha256

import pytest

from app.services.research.canonical import canonical_json
from app.services.research.discovery_execution_contract import (
    DiscoveryExecutionCommand,
    DiscoveryExecutionResult,
)


def test_command_canonicalizes_hashes_and_detaches_snapshots() -> None:
    source = _command_payload()

    command = DiscoveryExecutionCommand.from_mapping(source)

    assert isinstance(command.payload, bytes)
    assert command.request_hash == sha256(command.payload).hexdigest()
    assert command.snapshot["stage"] == "VALIDATE_DISCOVERY"
    assert command.snapshot["params"] == {"lookback": 20, "symbols": ["RB0"]}

    first_snapshot = command.snapshot
    first_snapshot["params"]["lookback"] = 999
    source["params"]["symbols"].append("SA0")

    assert command.snapshot["params"] == {"lookback": 20, "symbols": ["RB0"]}


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        (lambda payload: payload.update({"unexpected": True}), "extra field"),
        (lambda payload: payload.update({"stage": "SEALED_EVALUATE"}), "wrong stage"),
        (lambda payload: payload["quota"].update({"fencing_token": True}), "bool quota"),
        (
            lambda payload: payload["dataset"].update({"partition_kind": "SEALED"}),
            "sealed partition",
        ),
        (lambda payload: payload["policy"].update({"input_read_only": 1}), "non-bool read-only"),
        (lambda payload: payload["policy"].update({"network_mode": "egress"}), "network"),
        (lambda payload: payload["policy"].update({"output_path": "/tmp/output"}), "output path"),
        (lambda payload: payload["params"].update({"api_key": "sk-test-secret"}), "secret"),
        (
            lambda payload: payload["execution_policy"].update(
                {"dataset_uri": "s3://private/data"}
            ),
            "uri",
        ),
        (lambda payload: payload.update({"candidate_hash": "A" * 64}), "uppercase hash"),
        (lambda payload: payload["code"].update({"size_bytes": 0}), "zero code bytes"),
    ],
)
def test_command_rejects_non_discovery_or_untrusted_content(mutation, label: str) -> None:
    payload = _command_payload()
    mutation(payload)

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_COMMAND_INVALID"):
        DiscoveryExecutionCommand.from_mapping(payload)


def test_command_rejects_nonfinite_deep_and_oversized_json_objects() -> None:
    nonfinite = _command_payload()
    nonfinite["params"] = {"score": math.nan}
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_COMMAND_INVALID"):
        DiscoveryExecutionCommand.from_mapping(nonfinite)

    too_deep = _command_payload()
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(17):
        child: dict[str, object] = {}
        cursor["next"] = child
        cursor = child
    too_deep["execution_policy"] = nested
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_COMMAND_INVALID"):
        DiscoveryExecutionCommand.from_mapping(too_deep)

    too_large = _command_payload()
    too_large["params"] = {"comment": "x" * 1_048_576}
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_COMMAND_INVALID"):
        DiscoveryExecutionCommand.from_mapping(too_large)


def test_command_accepts_positive_integer_identity_and_input_sizes_without_narrowing_them() -> None:
    payload = _command_payload()
    large_positive = 2_147_483_648
    payload["quota"]["fencing_token"] = large_positive
    payload["code"]["size_bytes"] = large_positive
    payload["dependencies"]["size_bytes"] = large_positive
    payload["dataset"]["object_size_bytes"] = large_positive

    command = DiscoveryExecutionCommand.from_mapping(payload)

    assert command.snapshot["quota"]["fencing_token"] == large_positive
    assert command.snapshot["dataset"]["object_size_bytes"] == large_positive


def test_result_binds_every_fence_and_detaches_snapshot() -> None:
    command = DiscoveryExecutionCommand.from_mapping(_command_payload())

    result = DiscoveryExecutionResult.from_mapping(_result_payload(command), command=command)

    assert isinstance(result.payload, bytes)
    assert result.snapshot["command_hash"] == command.request_hash
    snapshot = result.snapshot
    snapshot["returns"].append(0.99)
    assert result.snapshot["returns"] == [0.0125, -0.004]


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        (lambda payload: payload.update({"command_hash": "f" * 64}), "command mismatch"),
        (lambda payload: payload.update({"runner_identity": "other-runner"}), "runner mismatch"),
        (lambda payload: payload.update({"image_digest": f"sha256:{'f' * 64}"}), "image mismatch"),
        (lambda payload: payload.update({"exit_code": 1}), "successful nonzero exit"),
        (
            lambda payload: payload.update({"observed_market_performance": False}),
            "success unobserved",
        ),
        (lambda payload: payload.update({"returns": [0.01]}), "one observed return"),
        (lambda payload: payload.update({"error_code": "PROVIDER_FAILED"}), "success error"),
        (lambda payload: payload.update({"elapsed_milliseconds": 60_001}), "elapsed overflow"),
        (lambda payload: payload.update({"returns": [True, 0.01]}), "boolean return"),
        (lambda payload: payload.update({"error_code": "provider-failed"}), "unstable error"),
        (lambda payload: payload.update({"extra": "not allowed"}), "extra result"),
    ],
)
def test_result_rejects_invalid_fences_or_market_observation(mutation, label: str) -> None:
    command = DiscoveryExecutionCommand.from_mapping(_command_payload())
    payload = _result_payload(command)
    mutation(payload)

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_INVALID"):
        DiscoveryExecutionResult.from_mapping(payload, command=command)


def test_non_success_requires_error_and_preserves_real_observation_rules() -> None:
    command = DiscoveryExecutionCommand.from_mapping(_command_payload())

    observed_failure = _result_payload(command)
    observed_failure.update(
        {
            "status": "FAILED",
            "exit_code": 2,
            "observed_market_performance": True,
            "returns": [0.01, -0.02],
            "error_code": "EXECUTION_FAILED",
        }
    )
    assert (
        DiscoveryExecutionResult.from_mapping(observed_failure, command=command).snapshot["status"]
        == "FAILED"
    )

    unobserved_failure = deepcopy(observed_failure)
    unobserved_failure.update({"observed_market_performance": False, "returns": []})
    assert (
        DiscoveryExecutionResult.from_mapping(unobserved_failure, command=command).snapshot[
            "observed_market_performance"
        ]
        is False
    )

    invalid_unobserved = deepcopy(observed_failure)
    invalid_unobserved.update({"observed_market_performance": False, "returns": [0.01, 0.02]})
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_INVALID"):
        DiscoveryExecutionResult.from_mapping(invalid_unobserved, command=command)

    missing_error = deepcopy(unobserved_failure)
    missing_error["error_code"] = None
    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_INVALID"):
        DiscoveryExecutionResult.from_mapping(missing_error, command=command)


def test_result_respects_the_command_output_cap() -> None:
    command_payload = _command_payload()
    command_payload["policy"]["output_limit_bytes"] = 128
    command = DiscoveryExecutionCommand.from_mapping(command_payload)

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_INVALID"):
        DiscoveryExecutionResult.from_mapping(_result_payload(command), command=command)


def test_result_constructor_cannot_bypass_the_command_output_cap() -> None:
    command_payload = _command_payload()
    command_payload["policy"]["output_limit_bytes"] = 128
    command = DiscoveryExecutionCommand.from_mapping(command_payload)
    response_bytes = canonical_json(_result_payload(command)).encode("utf-8")

    with pytest.raises(ValueError, match="DISCOVERY_EXECUTION_RESULT_INVALID"):
        DiscoveryExecutionResult(payload=response_bytes, _command=command)


def test_result_preserves_finite_leveraged_losses_without_imposing_a_cash_only_domain() -> None:
    command = DiscoveryExecutionCommand.from_mapping(_command_payload())
    payload = _result_payload(command)
    payload["returns"] = [-1.5, 100_001.0]

    result = DiscoveryExecutionResult.from_mapping(payload, command=command)

    assert result.snapshot["returns"] == [-1.5, 100_001.0]


def test_failed_partial_execution_preserves_a_single_observed_market_return() -> None:
    command = DiscoveryExecutionCommand.from_mapping(_command_payload())
    payload = _result_payload(command)
    payload.update(status="FAILED", exit_code=2, error_code="RUNNER_FAILED", returns=[0.01])

    result = DiscoveryExecutionResult.from_mapping(payload, command=command)

    assert result.snapshot["observed_market_performance"] is True
    assert result.snapshot["returns"] == [0.01]


def _command_payload() -> dict[str, object]:
    return {
        "schema_version": "discovery-execution-command-v1",
        "operation_id": "discovery-op-1",
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
        "runner_identity": "discovery-runner-v1",
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
            "wall_timeout_seconds": 60,
            "output_limit_bytes": 1_000_000,
        },
    }


def _result_payload(command: DiscoveryExecutionCommand) -> dict[str, object]:
    snapshot = command.snapshot
    return {
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
