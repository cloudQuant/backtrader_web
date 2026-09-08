"""Opaque wire contracts for the separately deployed sealed evaluator.

Only server-owned identities and hashes cross this boundary.  Dataset locations,
bearer credentials, lease tokens, permissions, and sealed input rows are resolved
inside the evaluator deployment and are never accepted as command fields.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Protocol

from app.services.research.canonical import canonical_json

_COMMAND_SCHEMA = "holdout-execution-command-v2"
_RESULT_SCHEMA = "holdout-execution-result-v2"
_INSPECTION_SCHEMA = "holdout-execution-inspection-v2"
_TERMINAL_RECEIPT_SCHEMA = "holdout-terminal-receipt-v1"
_ARTIFACT_RECEIPT_SCHEMA = "sealed-holdout-artifact-receipt-v1"
_INPUT_EVIDENCE_SCHEMA = "holdout-terminal-input-evidence-v1"
_MAX_COMMAND_BYTES = 64 * 1024
_MAX_RESULT_BYTES = 64 * 1024
_MAX_IDENTIFIER_BYTES = 512
_MAX_COLLECTION_ITEMS = 100_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
_COMMAND_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "command_id",
        "evaluation_id",
        "authorization_id",
        "experiment_epoch_id",
        "request_hash",
        "candidate_id",
        "candidate_hash",
        "dataset_snapshot_id",
        "sealed_dataset_hash",
        "sealed_dataset_identity_hash",
        "freeze_receipt_fingerprint",
        "capability_evidence_hash",
        "policy_version",
        "promotion_policy_hash",
        "evaluator_identity",
        "evaluator_image_digest",
        "lease_generation",
    }
)
_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "command_hash",
        "evaluator_identity",
        "evaluator_image_digest",
        "status",
        "terminal_receipt",
        "error_code",
    }
)
_INSPECTION_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "command_hash",
        "evaluator_identity",
        "evaluator_image_digest",
        "status",
        "result",
        "error_code",
    }
)
_TERMINAL_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "policy_version",
        "promotion_policy_hash",
        "input_evidence_hash",
        "artifact_receipt",
        "gate_results",
        "safe_metrics",
    }
)
_ARTIFACT_RECEIPT_KEYS = frozenset(
    {"schema_version", "receipt_id", "artifact_hash", "artifact_size_bytes"}
)
_GATE_RESULT_KEYS = frozenset({"code", "status", "reason_code"})
REQUIRED_HOLDOUT_GATE_CODES = (
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
_SAFE_METRIC_KEYS = frozenset(
    {
        "deflated_sharpe_probability",
        "max_drawdown",
        "robustness_score",
        "cost_bps",
        "slippage_bps",
        "turnover",
        "capacity_notional",
        "extreme_path_loss",
        "execution_semantics_match",
        "security_critical_findings",
        "security_scan_hash",
    }
)
_FORBIDDEN_KEY_PARTS = frozenset(
    {
        "uri",
        "url",
        "path",
        "token",
        "secret",
        "credential",
        "permission",
        "returns",
        "samples",
        "rows",
        "measurements",
    }
)
_FORBIDDEN_LOCATION_PREFIXES = (
    "data:",
    "file:",
    "ftp:",
    "gs:",
    "http:",
    "https:",
    "s3:",
    "ssh:",
)


class _InvalidCommand(ValueError):
    pass


class _InvalidResult(ValueError):
    pass


class _InvalidInspection(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HoldoutExecutionCommand:
    """Canonical, location-free command bound to a leased holdout evaluation."""

    payload: bytes
    command_hash: str

    def __post_init__(self) -> None:
        try:
            snapshot = _decode(self.payload, maximum=_MAX_COMMAND_BYTES)
            _validate_command(snapshot)
            if _canonical_bytes(snapshot) != self.payload:
                raise _InvalidCommand
            if self.command_hash != sha256(self.payload).hexdigest():
                raise _InvalidCommand
        except Exception:
            raise ValueError("HOLDOUT_EXECUTION_COMMAND_INVALID") from None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> HoldoutExecutionCommand:
        try:
            _validate_command(payload)
            frozen = _canonical_bytes(payload)
            if len(frozen) > _MAX_COMMAND_BYTES:
                raise _InvalidCommand
            return cls(payload=frozen, command_hash=sha256(frozen).hexdigest())
        except Exception:
            raise ValueError("HOLDOUT_EXECUTION_COMMAND_INVALID") from None

    @property
    def snapshot(self) -> dict[str, Any]:
        return _decode(self.payload, maximum=_MAX_COMMAND_BYTES)


@dataclass(frozen=True, slots=True)
class HoldoutExecutionResult:
    """Canonical evaluator receipt bound to exactly one immutable command."""

    payload: bytes
    _command: HoldoutExecutionCommand = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            if type(self._command) is not HoldoutExecutionCommand:
                raise _InvalidResult
            snapshot = _decode(self.payload, maximum=_MAX_RESULT_BYTES)
            _validate_result(snapshot, self._command)
            if _canonical_bytes(snapshot) != self.payload:
                raise _InvalidResult
        except Exception:
            raise ValueError("HOLDOUT_EXECUTION_RESULT_INVALID") from None

    @classmethod
    def from_mapping(
        cls,
        payload: dict[str, Any],
        *,
        command: HoldoutExecutionCommand,
    ) -> HoldoutExecutionResult:
        try:
            _validate_result(payload, command)
            return cls(payload=_canonical_bytes(payload), _command=command)
        except Exception:
            raise ValueError("HOLDOUT_EXECUTION_RESULT_INVALID") from None

    @property
    def snapshot(self) -> dict[str, Any]:
        return _decode(self.payload, maximum=_MAX_RESULT_BYTES)


@dataclass(frozen=True, slots=True)
class HoldoutExecutionInspection:
    """One idempotency lookup: observed receipt, unknown, or proven absent."""

    status: str
    result: HoldoutExecutionResult | None
    error_code: str | None
    _operation_id: str = field(repr=False)
    _command_hash: str = field(repr=False)
    _evaluator_identity: str = field(repr=False)
    _evaluator_image_digest: str = field(repr=False)

    @classmethod
    def from_mapping(
        cls,
        payload: dict[str, Any],
        *,
        command: HoldoutExecutionCommand,
    ) -> HoldoutExecutionInspection:
        try:
            mapping = _exact_mapping(payload, _INSPECTION_KEYS)
            snapshot = command.snapshot
            if (
                mapping["schema_version"] != _INSPECTION_SCHEMA
                or mapping["operation_id"] != snapshot["operation_id"]
                or mapping["command_hash"] != command.command_hash
                or mapping["evaluator_identity"] != snapshot["evaluator_identity"]
                or mapping["evaluator_image_digest"] != snapshot["evaluator_image_digest"]
                or mapping["status"] not in {"OBSERVED", "UNKNOWN", "NOT_EXECUTED"}
            ):
                raise _InvalidInspection
            status = mapping["status"]
            result_payload = mapping["result"]
            error_code = mapping["error_code"]
            if status == "OBSERVED":
                if type(result_payload) is not dict or error_code is not None:
                    raise _InvalidInspection
                result = HoldoutExecutionResult.from_mapping(result_payload, command=command)
            elif status == "UNKNOWN":
                if result_payload is not None or not _valid_error_code(error_code):
                    raise _InvalidInspection
                result = None
            else:
                if result_payload is not None or error_code is not None:
                    raise _InvalidInspection
                result = None
            return cls(
                status=status,
                result=result,
                error_code=error_code,
                _operation_id=str(mapping["operation_id"]),
                _command_hash=str(mapping["command_hash"]),
                _evaluator_identity=str(mapping["evaluator_identity"]),
                _evaluator_image_digest=str(mapping["evaluator_image_digest"]),
            )
        except Exception:
            raise ValueError("HOLDOUT_EXECUTION_INSPECTION_INVALID") from None

    def proves_not_executed(self, command: HoldoutExecutionCommand) -> bool:
        """Return whether this exact inspection proves the operation absent."""

        if type(command) is not HoldoutExecutionCommand:
            return False
        snapshot = command.snapshot
        return bool(
            self.status == "NOT_EXECUTED"
            and self.result is None
            and self.error_code is None
            and self._operation_id == snapshot["operation_id"]
            and self._command_hash == command.command_hash
            and self._evaluator_identity == snapshot["evaluator_identity"]
            and self._evaluator_image_digest == snapshot["evaluator_image_digest"]
        )


class SealedHoldoutExecutor(Protocol):
    """Deployment-owned evaluator transport with an idempotency lookup."""

    async def execute(self, command: HoldoutExecutionCommand) -> HoldoutExecutionResult:
        """Dispatch the operation once using ``operation_id`` as idempotency key."""

    async def inspect(self, command: HoldoutExecutionCommand) -> HoldoutExecutionInspection:
        """Inspect the same operation without creating another side effect."""


def _validate_command(value: object) -> None:
    command = _exact_mapping(value, _COMMAND_KEYS)
    if command["schema_version"] != _COMMAND_SCHEMA:
        raise _InvalidCommand
    for key in (
        "operation_id",
        "command_id",
        "evaluation_id",
        "authorization_id",
        "experiment_epoch_id",
        "candidate_id",
        "dataset_snapshot_id",
        "policy_version",
        "evaluator_identity",
    ):
        _identifier(command[key])
    for key in (
        "request_hash",
        "candidate_hash",
        "sealed_dataset_hash",
        "sealed_dataset_identity_hash",
        "freeze_receipt_fingerprint",
        "capability_evidence_hash",
        "promotion_policy_hash",
    ):
        if type(command[key]) is not str or _SHA256.fullmatch(command[key]) is None:
            raise _InvalidCommand
    if (
        type(command["evaluator_image_digest"]) is not str
        or _IMAGE_DIGEST.fullmatch(command["evaluator_image_digest"]) is None
        or type(command["lease_generation"]) is not int
        or command["lease_generation"] < 1
    ):
        raise _InvalidCommand
    _reject_forbidden(command)


def _validate_result(value: object, command: HoldoutExecutionCommand) -> None:
    result = _exact_mapping(value, _RESULT_KEYS)
    snapshot = command.snapshot
    if (
        result["schema_version"] != _RESULT_SCHEMA
        or result["operation_id"] != snapshot["operation_id"]
        or result["command_hash"] != command.command_hash
        or result["evaluator_identity"] != snapshot["evaluator_identity"]
        or result["evaluator_image_digest"] != snapshot["evaluator_image_digest"]
        or result["status"] not in {"SUCCEEDED", "FAILED"}
    ):
        raise _InvalidResult
    terminal_receipt = result["terminal_receipt"]
    error_code = result["error_code"]
    if result["status"] == "SUCCEEDED":
        if error_code is not None or type(terminal_receipt) is not dict:
            raise _InvalidResult
        _validate_terminal_receipt(terminal_receipt, command=command)
    elif terminal_receipt is not None or not _valid_error_code(error_code):
        raise _InvalidResult


def holdout_input_evidence_hash(
    *,
    command: HoldoutExecutionCommand,
    artifact_receipt: dict[str, Any],
) -> str:
    """Hash the location-free terminal input without any reversible samples."""

    if type(command) is not HoldoutExecutionCommand:
        raise ValueError("HOLDOUT_EXECUTION_RESULT_INVALID")
    try:
        _validate_artifact_receipt(artifact_receipt)
    except Exception:
        raise ValueError("HOLDOUT_EXECUTION_RESULT_INVALID") from None
    return sha256(
        _canonical_bytes(
            {
                "schema_version": _INPUT_EVIDENCE_SCHEMA,
                "command_hash": command.command_hash,
                "artifact_receipt": artifact_receipt,
            }
        )
    ).hexdigest()


def _validate_terminal_receipt(
    value: object,
    *,
    command: HoldoutExecutionCommand,
) -> None:
    receipt = _exact_mapping(value, _TERMINAL_RECEIPT_KEYS)
    if (
        receipt["schema_version"] != _TERMINAL_RECEIPT_SCHEMA
        or receipt["policy_version"] != command.snapshot["policy_version"]
        or receipt["promotion_policy_hash"] != command.snapshot["promotion_policy_hash"]
    ):
        raise _InvalidResult
    artifact_receipt = _exact_mapping(receipt["artifact_receipt"], _ARTIFACT_RECEIPT_KEYS)
    _validate_artifact_receipt(artifact_receipt)
    if receipt["input_evidence_hash"] != holdout_input_evidence_hash(
        command=command,
        artifact_receipt=artifact_receipt,
    ):
        raise _InvalidResult

    gates = receipt["gate_results"]
    if type(gates) is not list or len(gates) != len(REQUIRED_HOLDOUT_GATE_CODES):
        raise _InvalidResult
    observed_codes: list[str] = []
    for gate_value in gates:
        gate = _exact_mapping(gate_value, _GATE_RESULT_KEYS)
        if (
            gate["code"] not in REQUIRED_HOLDOUT_GATE_CODES
            or gate["status"] not in {"PASS", "FAIL"}
            or not _valid_error_code(gate["reason_code"])
        ):
            raise _InvalidResult
        observed_codes.append(str(gate["code"]))
    if tuple(observed_codes) != REQUIRED_HOLDOUT_GATE_CODES:
        raise _InvalidResult
    _validate_safe_metrics(receipt["safe_metrics"])


def _validate_artifact_receipt(value: object) -> None:
    receipt = _exact_mapping(value, _ARTIFACT_RECEIPT_KEYS)
    if receipt["schema_version"] != _ARTIFACT_RECEIPT_SCHEMA:
        raise _InvalidResult
    _identifier(receipt["receipt_id"])
    if (
        type(receipt["artifact_hash"]) is not str
        or _SHA256.fullmatch(receipt["artifact_hash"]) is None
        or type(receipt["artifact_size_bytes"]) is not int
        or not 1 <= receipt["artifact_size_bytes"] <= 10_000_000_000
    ):
        raise _InvalidResult


def _validate_safe_metrics(value: object) -> None:
    if type(value) is not dict or set(value) != _SAFE_METRIC_KEYS:
        raise _InvalidResult
    for key, metric in value.items():
        if key == "execution_semantics_match":
            if type(metric) is not bool:
                raise _InvalidResult
        elif key == "security_critical_findings":
            if type(metric) is not int or metric < 0:
                raise _InvalidResult
        elif key == "security_scan_hash":
            if type(metric) is not str or _SHA256.fullmatch(metric) is None:
                raise _InvalidResult
        elif type(metric) not in {int, float} or isinstance(metric, bool):
            raise _InvalidResult
        elif not math.isfinite(float(metric)):
            raise _InvalidResult
        elif float(metric) < 0:
            raise _InvalidResult
        elif key in {"deflated_sharpe_probability", "robustness_score"} and float(metric) > 1:
            raise _InvalidResult


def _reject_forbidden(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            components = set(normalized.split("_"))
            if normalized == "sealed_rows" or components.intersection(_FORBIDDEN_KEY_PARTS):
                raise ValueError
            _reject_forbidden(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_forbidden(nested)
    elif isinstance(value, str) and value.lower().startswith(_FORBIDDEN_LOCATION_PREFIXES):
        raise ValueError


def _validate_json(value: object, *, depth: int) -> None:
    if depth > 16:
        raise ValueError
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError
        return
    if isinstance(value, list):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise ValueError
        for item in value:
            _validate_json(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _MAX_COLLECTION_ITEMS or any(type(key) is not str for key in value):
            raise ValueError
        for item in value.values():
            _validate_json(item, depth=depth + 1)
        return
    raise ValueError


def _identifier(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or "://" in value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError


def _valid_error_code(value: object) -> bool:
    return type(value) is str and _ERROR_CODE.fullmatch(value) is not None and len(value) <= 128


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError
    return value


def _decode(payload: object, *, maximum: int) -> dict[str, Any]:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise ValueError
    decoded = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    if type(decoded) is not dict:
        raise ValueError
    return decoded


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return canonical_json(payload).encode("utf-8")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError(value)
