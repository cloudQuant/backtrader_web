from __future__ import annotations

import json
from hashlib import sha256
from importlib import import_module

import pytest

_RAW_NOT_PROVIDED = object()
_GATE_CODES = (
    "CANDIDATE_FROZEN",
    "SEALED_HOLDOUT",
    "EVIDENCE_BINDING",
    "DEFLATED_SHARPE",
    "MAX_DRAWDOWN",
    "ROBUSTNESS",
    "COST",
    "SLIPPAGE",
    "TURNOVER",
    "CAPACITY",
    "EXTREME_PATH",
    "EXECUTION_SEMANTICS",
    "SECURITY_SCAN",
)


def _contract_module():
    return import_module("app.services.research.holdout_execution_contract")


def _command_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "holdout-execution-command-v2",
        "operation_id": "holdout-operation-1",
        "command_id": "command-1",
        "evaluation_id": "evaluation-1",
        "authorization_id": "authorization-1",
        "experiment_epoch_id": "epoch-1",
        "request_hash": "1" * 64,
        "candidate_id": "candidate-1",
        "candidate_hash": "2" * 64,
        "dataset_snapshot_id": "sealed-snapshot-1",
        "sealed_dataset_hash": "3" * 64,
        "sealed_dataset_identity_hash": "4" * 64,
        "freeze_receipt_fingerprint": "7" * 64,
        "capability_evidence_hash": "8" * 64,
        "policy_version": "promotion-v1",
        "promotion_policy_hash": "9" * 64,
        "evaluator_identity": "independent-holdout-evaluator",
        "evaluator_image_digest": f"sha256:{'5' * 64}",
        "lease_generation": 1,
    }
    payload.update(changes)
    return payload


def _command():
    return _contract_module().HoldoutExecutionCommand.from_mapping(_command_payload())


def _result_payload(
    command,
    *,
    measurements: object = _RAW_NOT_PROVIDED,
    **changes: object,
) -> dict[str, object]:
    """Build a fake evaluator-side safe receipt; raw inputs never cross the wire."""

    snapshot = command.snapshot
    supplied = measurements is not _RAW_NOT_PROVIDED
    raw = measurements if isinstance(measurements, dict) else {}
    artifact_hash = (
        sha256(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if supplied
        else "6" * 64
    )
    artifact_receipt = {
        "schema_version": "sealed-holdout-artifact-receipt-v1",
        "receipt_id": f"external-receipt-{artifact_hash[:16]}",
        "artifact_hash": artifact_hash,
        "artifact_size_bytes": 4096,
    }
    try:
        from app.services.research.statistics import calculate_deflated_sharpe

        dsr_probability = calculate_deflated_sharpe(
            raw["returns"],
            trial_sharpes=raw["trial_sharpes"],
            bars_per_year=252,
        )
    except (KeyError, TypeError, ValueError):
        dsr_probability = 0.0
    safe_metrics = {
        "deflated_sharpe_probability": dsr_probability,
        "max_drawdown": raw.get("max_drawdown", 1.0),
        "robustness_score": raw.get("robustness_score", 0.0),
        "cost_bps": raw.get("cost_bps", 99.0),
        "slippage_bps": raw.get("slippage_bps", 99.0),
        "turnover": raw.get("turnover", 99.0),
        "capacity_notional": raw.get("capacity_notional", 0.0),
        "extreme_path_loss": raw.get("extreme_path_loss", 1.0),
        "execution_semantics_match": raw.get("execution_semantics_match", False),
        "security_critical_findings": raw.get("security_critical_findings", 1),
        "security_scan_hash": raw.get("security_scan_hash", "0" * 64),
    }
    gate_passes = {
        "CANDIDATE_FROZEN": True,
        "SEALED_HOLDOUT": True,
        "EVIDENCE_BINDING": True,
        "DEFLATED_SHARPE": dsr_probability >= 0.95,
        "MAX_DRAWDOWN": float(safe_metrics["max_drawdown"]) <= 0.2,
        "ROBUSTNESS": float(safe_metrics["robustness_score"]) >= 0.8,
        "COST": float(safe_metrics["cost_bps"]) <= 5.0,
        "SLIPPAGE": float(safe_metrics["slippage_bps"]) <= 2.0,
        "TURNOVER": float(safe_metrics["turnover"]) <= 4.0,
        "CAPACITY": float(safe_metrics["capacity_notional"]) >= 100_000.0,
        "EXTREME_PATH": float(safe_metrics["extreme_path_loss"]) <= 0.25,
        "EXECUTION_SEMANTICS": safe_metrics["execution_semantics_match"] is True,
        "SECURITY_SCAN": safe_metrics["security_critical_findings"] == 0,
    }
    gate_results = [
        {
            "code": code,
            "status": "PASS" if gate_passes[code] else "FAIL",
            "reason_code": f"HOLDOUT_{code}_{'PASSED' if gate_passes[code] else 'FAILED'}",
        }
        for code in _GATE_CODES
    ]
    terminal_receipt = {
        "schema_version": "holdout-terminal-receipt-v1",
        "policy_version": snapshot["policy_version"],
        "promotion_policy_hash": snapshot["promotion_policy_hash"],
        "input_evidence_hash": _contract_module().holdout_input_evidence_hash(
            command=command,
            artifact_receipt=artifact_receipt,
        ),
        "artifact_receipt": artifact_receipt,
        "gate_results": gate_results,
        "safe_metrics": safe_metrics,
    }
    payload: dict[str, object] = {
        "schema_version": "holdout-execution-result-v2",
        "operation_id": snapshot["operation_id"],
        "command_hash": command.command_hash,
        "evaluator_identity": snapshot["evaluator_identity"],
        "evaluator_image_digest": snapshot["evaluator_image_digest"],
        "status": "SUCCEEDED",
        "terminal_receipt": terminal_receipt,
        "error_code": None,
    }
    payload.update(changes)
    return payload


def test_command_is_canonical_and_contains_only_opaque_sealed_references() -> None:
    command = _command()

    assert command.snapshot == _command_payload()
    assert command.command_hash == __import__("hashlib").sha256(command.payload).hexdigest()
    serialized = command.payload.decode("utf-8").lower()
    assert all(fragment not in serialized for fragment in ("token", "uri", "url", "path"))


@pytest.mark.parametrize(
    "field,value",
    (
        ("dataset_uri", "s3://sealed/raw.parquet"),
        ("authorization_token", "secret"),
        ("sealed_rows", [{"close": 100.0}]),
        ("evaluator_permissions", ["object:get"]),
    ),
)
def test_command_rejects_locations_secrets_raw_data_and_permissions(
    field: str,
    value: object,
) -> None:
    module = _contract_module()

    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_COMMAND_INVALID$"):
        module.HoldoutExecutionCommand.from_mapping(_command_payload(**{field: value}))


def test_result_is_bound_to_the_exact_command_and_strict_safe_receipt_schema() -> None:
    module = _contract_module()
    command = _command()

    result = module.HoldoutExecutionResult.from_mapping(
        _result_payload(command),
        command=command,
    )

    assert result.snapshot == _result_payload(command)
    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_RESULT_INVALID$"):
        module.HoldoutExecutionResult.from_mapping(
            _result_payload(command, command_hash="0" * 64),
            command=command,
        )
    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_RESULT_INVALID$"):
        receipt = _result_payload(command)["terminal_receipt"]
        assert isinstance(receipt, dict)
        receipt["returns"] = [0.01]
        module.HoldoutExecutionResult.from_mapping(
            _result_payload(command, terminal_receipt=receipt),
            command=command,
        )


def test_result_contains_only_aggregate_metrics_and_never_raw_paths() -> None:
    module = _contract_module()
    command = _command()
    raw_canary = 0.12345678912345678

    result = module.HoldoutExecutionResult.from_mapping(
        _result_payload(
            command,
            measurements={
                "returns": [raw_canary],
                "trial_sharpes": [raw_canary],
                "discovery_dataset_snapshot_hash": "a" * 64,
                "cost_model_hash": "b" * 64,
                "environment_hash": "c" * 64,
                "capability_evidence_hash": "d" * 64,
                "max_drawdown": 0.18,
                "robustness_score": 0.9,
                "cost_bps": 1.0,
                "slippage_bps": 1.0,
                "turnover": 1.0,
                "capacity_notional": 1_000_000.0,
                "extreme_path_loss": 0.18,
                "execution_semantics_match": True,
                "security_critical_findings": 0,
            },
        ),
        command=command,
    )

    serialized = result.payload.decode("utf-8")
    assert "returns" not in serialized
    assert "trial_sharpes" not in serialized
    assert str(raw_canary) not in serialized
    assert result.snapshot["terminal_receipt"]["safe_metrics"]["extreme_path_loss"] == 0.18


def test_result_rejects_empty_safe_metrics_even_when_all_gates_claim_pass() -> None:
    module = _contract_module()
    command = _command()
    payload = _result_payload(command)
    terminal = payload["terminal_receipt"]
    assert isinstance(terminal, dict)
    terminal["safe_metrics"] = {}
    gates = terminal["gate_results"]
    assert isinstance(gates, list)
    for gate in gates:
        gate["status"] = "PASS"
        gate["reason_code"] = f"HOLDOUT_{gate['code']}_PASSED"

    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_RESULT_INVALID$"):
        module.HoldoutExecutionResult.from_mapping(payload, command=command)


@pytest.mark.parametrize("status", ("OBSERVED", "UNKNOWN", "NOT_EXECUTED"))
def test_inspection_contract_has_three_fail_closed_outcomes(status: str) -> None:
    module = _contract_module()
    command = _command()
    result = _result_payload(command) if status == "OBSERVED" else None
    error_code = "HOLDOUT_REMOTE_OUTCOME_UNKNOWN" if status == "UNKNOWN" else None

    inspection = module.HoldoutExecutionInspection.from_mapping(
        {
            "schema_version": "holdout-execution-inspection-v2",
            "operation_id": command.snapshot["operation_id"],
            "command_hash": command.command_hash,
            "evaluator_identity": command.snapshot["evaluator_identity"],
            "evaluator_image_digest": command.snapshot["evaluator_image_digest"],
            "status": status,
            "result": result,
            "error_code": error_code,
        },
        command=command,
    )

    assert inspection.status == status
    assert inspection.result is not None if status == "OBSERVED" else inspection.result is None


def test_contract_rejects_duplicate_json_keys_and_noncanonical_payload() -> None:
    module = _contract_module()
    command = _command()
    duplicate = (
        b'{"schema_version":"holdout-execution-command-v2",'
        b'"schema_version":"holdout-execution-command-v2"}'
    )

    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_COMMAND_INVALID$"):
        module.HoldoutExecutionCommand(payload=duplicate, command_hash="0" * 64)
    with pytest.raises(ValueError, match="^HOLDOUT_EXECUTION_RESULT_INVALID$"):
        module.HoldoutExecutionResult(
            payload=json.dumps(_result_payload(command), indent=2).encode(),
            _command=command,
        )
