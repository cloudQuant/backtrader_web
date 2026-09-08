"""Immutable, non-sealed wire contracts for discovery validation runners.

This module deliberately defines only the bytes exchanged with a separately
deployed discovery runner.  It neither starts a sandbox nor grants sealed-data
access.  The command carries opaque identities and content hashes exclusively;
callers must resolve every referenced input server-side before dispatch.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from app.services.research.canonical import canonical_json
from app.services.research.redaction import redact_sensitive_payload

_COMMAND_SCHEMA_VERSION = "discovery-execution-command-v1"
_RESULT_SCHEMA_VERSION = "discovery-execution-result-v1"
_MAX_COMMAND_BYTES = 1_048_576
_MAX_RESULT_BYTES = 10_000_000
_MAX_EMBEDDED_OBJECT_BYTES = 262_144
_MAX_IDENTIFIER_BYTES = 512
_MAX_ERROR_CODE_BYTES = 128
_MAX_JSON_DEPTH = 16
_MAX_JSON_COLLECTION_ITEMS = 100_000
_MAX_RETURNS = 100_000

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
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
_FORBIDDEN_NESTED_KEY_PARTS = frozenset({"path", "uri", "url", "location"})
_COMMAND_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "task_id",
        "run_id",
        "stage_attempt_id",
        "candidate_id",
        "stage",
        "candidate_hash",
        "run_request_hash",
        "lease_token_hash",
        "environment_hash",
        "cost_model_hash",
        "runner_identity",
        "profile",
        "quota",
        "code",
        "dependencies",
        "dataset",
        "params",
        "execution_policy",
        "policy",
    }
)
_RESULT_KEYS = frozenset(
    {
        "schema_version",
        "operation_id",
        "command_hash",
        "runner_identity",
        "image_digest",
        "status",
        "exit_code",
        "elapsed_milliseconds",
        "observed_market_performance",
        "returns",
        "error_code",
    }
)


class _InvalidCommand(ValueError):
    """Private validation sentinel so public failures remain stable."""


class _InvalidResult(ValueError):
    """Private validation sentinel so public failures remain stable."""


@dataclass(frozen=True, slots=True)
class DiscoveryExecutionCommand:
    """Canonical, immutable input to a non-sealed discovery runner."""

    payload: bytes
    request_hash: str

    def __post_init__(self) -> None:
        try:
            snapshot = _decode_canonical_object(
                self.payload,
                maximum=_MAX_COMMAND_BYTES,
                invalid_type=_InvalidCommand,
            )
            _validate_command(snapshot)
            if _canonical_bytes(snapshot, _InvalidCommand) != self.payload:
                raise _InvalidCommand
            if (
                type(self.request_hash) is not str
                or self.request_hash != sha256(self.payload).hexdigest()
            ):
                raise _InvalidCommand
        except Exception:
            raise ValueError("DISCOVERY_EXECUTION_COMMAND_INVALID") from None

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> DiscoveryExecutionCommand:
        """Validate and freeze a discovery-only command as canonical UTF-8 bytes."""

        try:
            _validate_command(payload)
            canonical_payload = _canonical_bytes(payload, _InvalidCommand)
            if len(canonical_payload) > _MAX_COMMAND_BYTES:
                raise _InvalidCommand
            return cls(
                payload=canonical_payload,
                request_hash=sha256(canonical_payload).hexdigest(),
            )
        except Exception:
            raise ValueError("DISCOVERY_EXECUTION_COMMAND_INVALID") from None

    @property
    def snapshot(self) -> dict[str, Any]:
        """Return a fresh detached representation of the immutable command."""

        return _snapshot(self.payload)


@dataclass(frozen=True, slots=True)
class DiscoveryExecutionResult:
    """Canonical runner result bound to exactly one discovery command."""

    payload: bytes
    _command: DiscoveryExecutionCommand = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            if type(self._command) is not DiscoveryExecutionCommand:
                raise _InvalidResult
            snapshot = _decode_canonical_object(
                self.payload,
                maximum=_MAX_RESULT_BYTES,
                invalid_type=_InvalidResult,
            )
            _validate_result(snapshot, self._command)
            if _canonical_bytes(snapshot, _InvalidResult) != self.payload:
                raise _InvalidResult
        except Exception:
            raise ValueError("DISCOVERY_EXECUTION_RESULT_INVALID") from None

    @classmethod
    def from_mapping(
        cls,
        payload: dict[str, Any],
        *,
        command: DiscoveryExecutionCommand,
    ) -> DiscoveryExecutionResult:
        """Validate a runner result against every command identity fence."""

        try:
            if type(command) is not DiscoveryExecutionCommand:
                raise _InvalidResult
            _validate_result(payload, command)
            canonical_payload = _canonical_bytes(payload, _InvalidResult)
            return cls(payload=canonical_payload, _command=command)
        except Exception:
            raise ValueError("DISCOVERY_EXECUTION_RESULT_INVALID") from None

    @property
    def snapshot(self) -> dict[str, Any]:
        """Return a fresh detached representation of the immutable result."""

        return _snapshot(self.payload)


def _validate_command(payload: object) -> None:
    command = _exact_mapping(payload, _COMMAND_KEYS, _InvalidCommand)
    if command["schema_version"] != _COMMAND_SCHEMA_VERSION:
        raise _InvalidCommand
    for field_name in (
        "operation_id",
        "task_id",
        "run_id",
        "stage_attempt_id",
        "candidate_id",
        "runner_identity",
    ):
        _opaque_identifier(command[field_name], _InvalidCommand)
    if command["stage"] != "VALIDATE_DISCOVERY":
        raise _InvalidCommand
    for field_name in (
        "candidate_hash",
        "run_request_hash",
        "lease_token_hash",
        "environment_hash",
        "cost_model_hash",
    ):
        _hash(command[field_name], _InvalidCommand)
    _validate_profile(command["profile"])
    _validate_quota(command["quota"])
    _validate_artifact(command["code"])
    _validate_artifact(command["dependencies"])
    _validate_dataset(command["dataset"])
    _embedded_json_object(command["params"])
    _embedded_json_object(command["execution_policy"])
    _validate_policy(command["policy"])


def _validate_profile(value: object) -> None:
    profile = _exact_mapping(value, frozenset({"id", "version", "evidence_hash"}), _InvalidCommand)
    _opaque_identifier(profile["id"], _InvalidCommand)
    _opaque_identifier(profile["version"], _InvalidCommand)
    _hash(profile["evidence_hash"], _InvalidCommand)


def _validate_quota(value: object) -> None:
    quota = _exact_mapping(value, frozenset({"reservation_id", "fencing_token"}), _InvalidCommand)
    _opaque_identifier(quota["reservation_id"], _InvalidCommand)
    _positive_int(quota["fencing_token"], _InvalidCommand)


def _validate_artifact(value: object) -> None:
    artifact = _exact_mapping(
        value,
        frozenset({"artifact_id", "content_hash", "size_bytes"}),
        _InvalidCommand,
    )
    _opaque_identifier(artifact["artifact_id"], _InvalidCommand)
    _hash(artifact["content_hash"], _InvalidCommand)
    _positive_int(artifact["size_bytes"], _InvalidCommand)


def _validate_dataset(value: object) -> None:
    dataset = _exact_mapping(
        value,
        frozenset(
            {
                "snapshot_id",
                "snapshot_identity_hash",
                "object_receipt_id",
                "object_digest",
                "object_size_bytes",
                "partition_kind",
            }
        ),
        _InvalidCommand,
    )
    _opaque_identifier(dataset["snapshot_id"], _InvalidCommand)
    _hash(dataset["snapshot_identity_hash"], _InvalidCommand)
    _opaque_identifier(dataset["object_receipt_id"], _InvalidCommand)
    _hash(dataset["object_digest"], _InvalidCommand)
    _positive_int(dataset["object_size_bytes"], _InvalidCommand)
    if dataset["partition_kind"] not in {"DISCOVERY", "ITERATION_VALIDATION"}:
        raise _InvalidCommand


def _validate_policy(value: object) -> None:
    policy = _exact_mapping(
        value,
        frozenset(
            {
                "version",
                "image_digest",
                "network_mode",
                "input_read_only",
                "output_path",
                "cpu_limit",
                "memory_limit_mb",
                "pid_limit",
                "wall_timeout_seconds",
                "output_limit_bytes",
            }
        ),
        _InvalidCommand,
    )
    _opaque_identifier(policy["version"], _InvalidCommand)
    if (
        type(policy["image_digest"]) is not str
        or _IMAGE_DIGEST.fullmatch(policy["image_digest"]) is None
    ):
        raise _InvalidCommand
    if policy["network_mode"] != "none" or policy["input_read_only"] is not True:
        raise _InvalidCommand
    if policy["output_path"] != "/sandbox/output":
        raise _InvalidCommand
    _bounded_int(policy["cpu_limit"], minimum=1, maximum=64, invalid_type=_InvalidCommand)
    _bounded_int(
        policy["memory_limit_mb"],
        minimum=16,
        maximum=1_048_576,
        invalid_type=_InvalidCommand,
    )
    _bounded_int(policy["pid_limit"], minimum=1, maximum=4_096, invalid_type=_InvalidCommand)
    _bounded_int(
        policy["wall_timeout_seconds"],
        minimum=1,
        maximum=3_600,
        invalid_type=_InvalidCommand,
    )
    _bounded_int(
        policy["output_limit_bytes"],
        minimum=1,
        maximum=_MAX_RESULT_BYTES,
        invalid_type=_InvalidCommand,
    )


def _validate_result(payload: object, command: DiscoveryExecutionCommand) -> None:
    result = _exact_mapping(payload, _RESULT_KEYS, _InvalidResult)
    command_snapshot = command.snapshot
    if result["schema_version"] != _RESULT_SCHEMA_VERSION:
        raise _InvalidResult
    if result["operation_id"] != command_snapshot["operation_id"]:
        raise _InvalidResult
    if result["command_hash"] != command.request_hash:
        raise _InvalidResult
    if result["runner_identity"] != command_snapshot["runner_identity"]:
        raise _InvalidResult
    if result["image_digest"] != command_snapshot["policy"]["image_digest"]:
        raise _InvalidResult
    if result["status"] not in {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"}:
        raise _InvalidResult

    exit_code = result["exit_code"]
    if exit_code is not None and type(exit_code) is not int:
        raise _InvalidResult
    elapsed = result["elapsed_milliseconds"]
    _bounded_int(
        elapsed,
        minimum=0,
        maximum=command_snapshot["policy"]["wall_timeout_seconds"] * 1_000,
        invalid_type=_InvalidResult,
    )
    observed = result["observed_market_performance"]
    if type(observed) is not bool:
        raise _InvalidResult
    returns = result["returns"]
    _validate_returns(returns)
    error_code = result["error_code"]
    _validate_error_code(error_code)

    if result["status"] == "SUCCEEDED":
        if exit_code != 0 or observed is not True or len(returns) < 2 or error_code is not None:
            raise _InvalidResult
    elif error_code is None:
        raise _InvalidResult
    if observed is False and returns:
        raise _InvalidResult
    if observed is True and not returns:
        raise _InvalidResult
    output_limit = command_snapshot["policy"]["output_limit_bytes"]
    if len(_canonical_bytes(result, _InvalidResult)) > min(output_limit, _MAX_RESULT_BYTES):
        raise _InvalidResult


def _validate_returns(value: object) -> None:
    if type(value) is not list or len(value) > _MAX_RETURNS:
        raise _InvalidResult
    for item in value:
        # Preserve measured losses/gains, including leveraged instruments. The
        # wire contract is not a cash-only economic domain or a quality gate.
        if type(item) not in {int, float} or not math.isfinite(item):
            raise _InvalidResult


def _validate_error_code(value: object) -> None:
    if value is None:
        return
    if (
        type(value) is not str
        or len(value.encode("utf-8")) > _MAX_ERROR_CODE_BYTES
        or _ERROR_CODE.fullmatch(value) is None
    ):
        raise _InvalidResult


def _embedded_json_object(value: object) -> None:
    if type(value) is not dict:
        raise _InvalidCommand
    if redact_sensitive_payload(value) != value:
        raise _InvalidCommand
    _validate_embedded_json(value, depth=1)
    if len(_canonical_bytes(value, _InvalidCommand)) > _MAX_EMBEDDED_OBJECT_BYTES:
        raise _InvalidCommand


def _validate_embedded_json(value: object, *, depth: int) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise _InvalidCommand
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise _InvalidCommand
        return
    if type(value) is str:
        _safe_embedded_string(value)
        return
    if type(value) is list:
        if len(value) > _MAX_JSON_COLLECTION_ITEMS:
            raise _InvalidCommand
        for item in value:
            _validate_embedded_json(item, depth=depth + 1)
        return
    if type(value) is dict:
        if len(value) > _MAX_JSON_COLLECTION_ITEMS:
            raise _InvalidCommand
        for key, item in value.items():
            if type(key) is not str or not key or _forbidden_nested_key(key):
                raise _InvalidCommand
            _safe_embedded_string(key)
            _validate_embedded_json(item, depth=depth + 1)
        return
    raise _InvalidCommand


def _safe_embedded_string(value: str) -> None:
    if (
        "\x00" in value
        or len(value.encode("utf-8")) > _MAX_EMBEDDED_OBJECT_BYTES
        or redact_sensitive_payload(value) != value
        or _looks_like_location(value)
    ):
        raise _InvalidCommand


def _forbidden_nested_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(part in normalized for part in _FORBIDDEN_NESTED_KEY_PARTS)


def _exact_mapping(
    value: object,
    expected_keys: frozenset[str],
    invalid_type: type[_InvalidCommand] | type[_InvalidResult],
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected_keys:
        raise invalid_type
    return value


def _opaque_identifier(
    value: object,
    invalid_type: type[_InvalidCommand] | type[_InvalidResult],
) -> None:
    if (
        type(value) is not str
        or not value
        or value.strip() != value
        or "\x00" in value
        or len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES
        or redact_sensitive_payload(value) != value
        or _looks_like_location(value)
    ):
        raise invalid_type


def _hash(value: object, invalid_type: type[_InvalidCommand] | type[_InvalidResult]) -> None:
    if type(value) is not str or _SHA256_HEX.fullmatch(value) is None:
        raise invalid_type


def _positive_int(
    value: object, invalid_type: type[_InvalidCommand] | type[_InvalidResult]
) -> None:
    if type(value) is not int or value < 1:
        raise invalid_type


def _bounded_int(
    value: object,
    *,
    minimum: int,
    maximum: int,
    invalid_type: type[_InvalidCommand] | type[_InvalidResult],
) -> None:
    if type(value) is not int or value < minimum or value > maximum:
        raise invalid_type


def _looks_like_location(value: str) -> bool:
    lowered = value.lower()
    return (
        "/" in value
        or "\\" in value
        or value.startswith((".", "~"))
        or "://" in value
        or lowered.startswith(_FORBIDDEN_LOCATION_PREFIXES)
    )


def _canonical_bytes(
    value: object,
    invalid_type: type[_InvalidCommand] | type[_InvalidResult],
) -> bytes:
    try:
        return canonical_json(value).encode("utf-8")
    except Exception as exc:
        raise invalid_type from exc


def _decode_canonical_object(
    payload: object,
    *,
    maximum: int,
    invalid_type: type[_InvalidCommand] | type[_InvalidResult],
) -> dict[str, Any]:
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise invalid_type
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise invalid_type from exc
    if type(decoded) is not dict:
        raise invalid_type
    return decoded


def _snapshot(payload: bytes) -> dict[str, Any]:
    """Decode immutable canonical bytes into a new nested object graph."""

    decoded = json.loads(payload.decode("utf-8"))
    if type(decoded) is not dict:  # Construction validates this invariant.
        raise RuntimeError("DISCOVERY_EXECUTION_CONTRACT_CORRUPTED")
    return decoded
