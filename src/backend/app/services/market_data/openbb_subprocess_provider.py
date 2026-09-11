"""OpenBB subprocess-provider configuration and receipt validation.

The provider remains disabled unless an operator supplies an isolated runner,
the exact protocol declaration, and separately approved runtime permits. This
module does not import OpenBB, activate permits, or perform network I/O itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import tempfile
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.market_data import openbb_runner
from app.services.market_data.provider_models import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
    _as_utc,
    _canonical_json,
    _require_text,
)

OPENBB_RUNNER_PROTOCOL_VERSION = openbb_runner.OPENBB_RUNNER_PROTOCOL_VERSION
OPENBB_RUNNER_PROTOCOL_SELF_CHECK_VERSION = openbb_runner.OPENBB_RUNNER_PROTOCOL_SELF_CHECK_VERSION
OPENBB_RUNNER_TRANSPORT_VERSION = openbb_runner.OPENBB_RUNNER_TRANSPORT_VERSION
OpenBBProviderError = openbb_runner.OpenBBProviderError
_OpenBBRunnerGate = openbb_runner._OpenBBRunnerGate
_OpenBBSubprocessRunner = openbb_runner._OpenBBSubprocessRunner
_PROCESS_OPENBB_RUNNER_GATE = openbb_runner._PROCESS_OPENBB_RUNNER_GATE

_MAX_OPENBB_RAW_PAYLOAD_BYTES = 4 * 1024 * 1024
DEFAULT_OPENBB_MAX_CONCURRENT_RUNS = 4
_OPENBB_RAW_PAYLOAD_FORMAT = "openbb-records-pre-normalization-v1"
_OPENBB_RAW_TIMESTAMP_FIELDS = ("event_at", "date", "datetime", "timestamp")
_RUNNER_BASE_ENVIRONMENT_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "PYTHONIOENCODING",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)
_RUNNER_OPENBB_CONTROL_ENVIRONMENT_KEYS = ("OPENBB_ALLOWED_PROVIDERS",)
_OPENBB_RUNNER_PROTOCOL_ENVIRONMENT_KEY = "OPENBB_MARKET_DATA_RUNNER_PROTOCOL"
_RUNNER_HOME_ENVIRONMENT_KEY = "OPENBB_RUNNER_HOME"
_RUNNER_WORKDIR_ENVIRONMENT_KEY = "OPENBB_RUNNER_WORKDIR"


def _require_openbb_max_concurrent_runs(value: int) -> int:
    """Validate the operator-owned runner concurrency cap."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_concurrent_runs must be a positive integer")
    return value


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether either resolved path can contain the other one."""
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _runner_path_overlaps_application_checkout(path: Path) -> bool:
    """Reject a runner path that is in, or can contain, the application checkout.

    A bare equality check lets a runner use a subdirectory of the web checkout,
    where OpenBB extensions could read application code, configuration, or a
    repository-local secret.  When this source is in a Git checkout, protect
    the checkout root in both directions.  Packaged deployments may lack Git
    metadata, so retain the conservative current-workdir descendant check.
    """
    try:
        source_path = Path(__file__).resolve(strict=True)
        # The fixed module layout gives a conservative package boundary even
        # for installed wheels, which deliberately have no ``.git`` marker.
        application_package_root = source_path.parents[2]
        if _paths_overlap(path, application_package_root):
            return True
        checkout_root = next(
            (parent for parent in source_path.parents if (parent / ".git").exists()),
            None,
        )
        if checkout_root is not None:
            return _paths_overlap(path, checkout_root)
        current_workdir = Path.cwd().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return True
    return _paths_overlap(path, current_workdir)


def _is_safe_openbb_runner_file(value: object, *, executable: bool) -> bool:
    """Accept one existing absolute runner binary or script file only."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    path = Path(value)
    if not path.is_absolute():
        return False
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    if not resolved.is_file():
        return False
    if _runner_path_overlaps_application_checkout(resolved):
        return False
    return not executable or os.access(resolved, os.X_OK)


def _is_safe_openbb_trusted_python(value: object) -> bool:
    """Accept one absolute Python interpreter selected by the runner operator.

    The web process cannot prove a binary's provenance from its pathname.
    Requiring an absolute executable with a Python interpreter basename keeps
    the remaining trust decision explicit in the operator-owned deployment
    configuration and rejects shells, wrappers, and arbitrary executables.
    """
    if not _is_safe_openbb_runner_file(value, executable=True):
        return False
    try:
        executable_name = Path(str(value)).resolve(strict=True).name
    except (OSError, RuntimeError, ValueError):
        return False
    return re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable_name) is not None


def _is_safe_openbb_runner_command(command: tuple[str, ...]) -> bool:
    """Require only ``<absolute python> -I -S <absolute runner.py>``.

    ``-I`` prevents startup from honoring ``PYTHONPATH`` and other Python
    environment selectors; ``-S`` prevents ``site`` and ``sitecustomize``
    execution.  The runner also checks those flags itself before any possible
    OpenBB dynamic import, so an operator cannot restore ordinary interpreter
    startup through a future artifact or route permit change.  No shell,
    wrapper, arbitrary flag, module mode, or relative path is accepted.
    """
    return (
        len(command) == 4
        and _is_safe_openbb_trusted_python(command[0])
        and command[1] == "-I"
        and command[2] == "-S"
        and _is_safe_openbb_runner_file(command[3], executable=False)
    )


class OpenBBSubprocessProvider:
    """Execute an OpenBB-only runner through a bounded JSON protocol."""

    def __init__(
        self,
        *,
        command: tuple[str, ...] | None,
        timeout_seconds: float = 30.0,
        configuration_error: str | None = None,
        max_concurrent_runs: int = DEFAULT_OPENBB_MAX_CONCURRENT_RUNS,
    ) -> None:
        if command is not None and not command:
            raise ValueError("runner command cannot be empty")
        if command is not None and not _is_safe_openbb_runner_command(command):
            raise ValueError(
                "runner command must be '<absolute python> -I -S <absolute runner.py>'"
            )
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if configuration_error not in {
            None,
            "OPENBB_RUNNER_COMMAND_INVALID",
            "OPENBB_RUNNER_PROTOCOL_UNSUPPORTED",
        }:
            raise ValueError("configuration_error must be a supported stable code")
        if command is not None and configuration_error is not None:
            raise ValueError("configured runner command cannot also carry an error")
        self._command = command
        self._timeout_seconds = timeout_seconds
        self._configuration_error = configuration_error
        self._max_concurrent_runs = _require_openbb_max_concurrent_runs(max_concurrent_runs)

    @classmethod
    def from_environment(
        cls,
        *,
        max_concurrent_runs: int = DEFAULT_OPENBB_MAX_CONCURRENT_RUNS,
    ) -> OpenBBSubprocessProvider:
        """Build the adapter from the exact isolated Python runner command."""
        raw_command = os.getenv("OPENBB_MARKET_DATA_RUNNER", "").strip()
        if not raw_command:
            return cls(command=None, max_concurrent_runs=max_concurrent_runs)
        try:
            command = tuple(shlex.split(raw_command))
        except ValueError:
            # Dependency construction must remain safe even when an operator
            # typo leaves an unmatched quote in the environment variable.
            return cls(
                command=None,
                configuration_error="OPENBB_RUNNER_COMMAND_INVALID",
                max_concurrent_runs=max_concurrent_runs,
            )
        if not _is_safe_openbb_runner_command(command):
            return cls(
                command=None,
                configuration_error="OPENBB_RUNNER_COMMAND_INVALID",
                max_concurrent_runs=max_concurrent_runs,
            )
        if os.getenv(_OPENBB_RUNNER_PROTOCOL_ENVIRONMENT_KEY) != OPENBB_RUNNER_PROTOCOL_VERSION:
            return cls(
                command=None,
                configuration_error="OPENBB_RUNNER_PROTOCOL_UNSUPPORTED",
                max_concurrent_runs=max_concurrent_runs,
            )
        return cls(command=command, max_concurrent_runs=max_concurrent_runs)

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        """Return one verified response or a typed failure without shell invocation."""
        if self._command is None:
            raise OpenBBProviderError(self._configuration_error or "OPENBB_RUNNER_UNAVAILABLE")
        admission = await _PROCESS_OPENBB_RUNNER_GATE.try_acquire(limit=self._max_concurrent_runs)
        if admission == "configuration_mismatch":
            raise OpenBBProviderError("OPENBB_RUNNER_CONCURRENCY_CONFIG_MISMATCH")
        if admission == "overloaded":
            raise OpenBBProviderError("OPENBB_RUNNER_OVERLOADED")
        try:
            request_payload = {
                "protocol_version": OPENBB_RUNNER_PROTOCOL_VERSION,
                "request_id": request.request_id,
                "request": request.dto_payload,
            }
            encoded_request = _canonical_json(request_payload).encode("utf-8")
            runner = _OpenBBSubprocessRunner(
                command=self._command,
                environment=_openbb_runner_environment(),
                workdir=_openbb_runner_workdir(),
            )
            await runner.attest_protocol(timeout_seconds=self._timeout_seconds)
            stdout, _stderr = await runner.execute(
                encoded_request,
                timeout_seconds=self._timeout_seconds,
            )
            try:
                response = json.loads(stdout.data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE") from exc
            if not isinstance(response, Mapping):
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
            if response.get("protocol_version") != OPENBB_RUNNER_PROTOCOL_VERSION:
                raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_MISMATCH")
            if response.get("request_id") != request.request_id:
                raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_MISMATCH")
            if isinstance(response.get("error"), Mapping):
                error = response["error"]
                code = _require_text(
                    str(error.get("code") or "OPENBB_RUNNER_ERROR"), field_name="error code"
                )
                detail = str(error.get("detail") or "")[:2048] or None
                raise OpenBBProviderError(code, detail=detail)
            echoed_request = response.get("request")
            try:
                echoed_request_matches = isinstance(echoed_request, Mapping) and _canonical_json(
                    dict(echoed_request)
                ) == _canonical_json(request.dto_payload)
            except (TypeError, ValueError):
                echoed_request_matches = False
            if not echoed_request_matches:
                raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_MISMATCH")

            return self._parse_response(response, request)
        finally:
            await _PROCESS_OPENBB_RUNNER_GATE.release()

    @staticmethod
    def _parse_response(
        response: Mapping[str, Any], request: MarketDataProviderRequest
    ) -> ProviderFetchResult:
        try:
            provider_id = _require_text(str(response["provider_id"]), field_name="provider_id")
            source_revision = _require_text(
                str(response["source_revision"]), field_name="source_revision"
            )
            retrieved_at = _parse_timestamp(response["retrieved_at"], field_name="retrieved_at")
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE") from exc
        if not provider_id.startswith("openbb:"):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")

        records = response.get("records")
        if not isinstance(records, list):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        observations: list[ProviderMarketObservation] = []
        seen_events: set[datetime] = set()
        for record in records:
            if not isinstance(record, Mapping):
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
            try:
                event_at = _parse_timestamp(record["event_at"], field_name="event_at")
                fields = record["fields"]
            except (KeyError, TypeError, ValueError) as exc:
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE") from exc
            if not isinstance(fields, Mapping):
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
            if not request.start_at <= event_at < request.end_at or event_at in seen_events:
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
            seen_events.add(event_at)
            try:
                observations.append(
                    ProviderMarketObservation(
                        event_at=event_at,
                        available_at=retrieved_at,
                        fields=fields,
                    )
                )
            except (TypeError, ValueError) as exc:
                raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE") from exc

        raw_payload = response.get("raw_payload")
        if not isinstance(raw_payload, Mapping):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        raw_records = raw_payload.get("records")
        if (
            raw_payload.get("format") != _OPENBB_RAW_PAYLOAD_FORMAT
            or not isinstance(raw_records, list)
            or any(not isinstance(record, Mapping) for record in raw_records)
        ):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        try:
            raw_payload_sha256 = _require_text(
                str(response["raw_payload_sha256"]),
                field_name="raw_payload_sha256",
                maximum=64,
            ).lower()
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE") from exc
        if len(raw_payload_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in raw_payload_sha256
        ):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        try:
            raw_payload_bytes = _canonical_json(dict(raw_payload)).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE") from exc
        if len(raw_payload_bytes) > _MAX_OPENBB_RAW_PAYLOAD_BYTES:
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        actual_raw_payload_sha256 = hashlib.sha256(raw_payload_bytes).hexdigest()
        if actual_raw_payload_sha256 != raw_payload_sha256:
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        if not _normalized_records_bind_to_raw_payload(
            observations=tuple(observations),
            raw_records=raw_records,
            request=request,
        ):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        warnings_raw = response.get("warnings", [])
        if not isinstance(warnings_raw, list) or any(
            not isinstance(item, str) for item in warnings_raw
        ):
            raise OpenBBProviderError("OPENBB_RUNNER_INVALID_RESPONSE")
        return ProviderFetchResult(
            provider_id=provider_id,
            source_revision=source_revision,
            retrieved_at=retrieved_at,
            observations=tuple(observations),
            raw_payload=raw_payload,
            request=request,
            warnings=tuple(warnings_raw),
        )


def _parse_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} is not an ISO timestamp") from exc
    return _as_utc(parsed, field_name=field_name)


def _normalized_records_bind_to_raw_payload(
    *,
    observations: tuple[ProviderMarketObservation, ...],
    raw_records: list[Mapping[str, Any]],
    request: MarketDataProviderRequest,
) -> bool:
    """Recompute the runner's normalized record projection from hashed source rows.

    The subprocess protocol keeps raw source records and normalized records
    separate for provenance. A verified raw-payload hash alone is insufficient
    if a compromised runner can substitute the normalized values, so accept a
    response only when the ordered, in-window event and field projection is
    exactly reproducible from that receipt.
    """
    try:
        projected = _project_openbb_raw_records(raw_records, request=request)
        if len(projected) != len(observations):
            return False
        return all(
            expected.event_at == actual.event_at
            and _canonical_json(dict(expected.fields)) == _canonical_json(dict(actual.fields))
            for expected, actual in zip(projected, observations, strict=True)
        )
    except (TypeError, ValueError):
        return False


def _project_openbb_raw_records(
    raw_records: list[Mapping[str, Any]],
    *,
    request: MarketDataProviderRequest,
) -> tuple[ProviderMarketObservation, ...]:
    """Apply the reviewed runner record projection without importing OpenBB."""
    projected: list[ProviderMarketObservation] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise TypeError("raw record must be a mapping")
        event_at = _openbb_raw_record_event_at(raw_record)
        if not request.start_at <= event_at < request.end_at:
            continue
        fields = {
            field_name: value
            for field_name, value in raw_record.items()
            if field_name not in _OPENBB_RAW_TIMESTAMP_FIELDS
        }
        if not fields:
            continue
        projected.append(
            ProviderMarketObservation(
                event_at=event_at,
                # Availability belongs to the signed runner envelope rather
                # than an individual raw row. It is irrelevant to this
                # event/field projection but required by the shared DTO.
                available_at=request.start_at,
                fields=fields,
            )
        )
    return tuple(projected)


def _openbb_raw_record_event_at(record: Mapping[str, Any]) -> datetime:
    """Match the isolated runner's explicit raw timestamp precedence rules."""
    value = next(
        (
            record.get(field_name)
            for field_name in _OPENBB_RAW_TIMESTAMP_FIELDS
            if record.get(field_name) is not None
        ),
        None,
    )
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("raw record event timestamp is invalid") from exc
    else:
        raise TypeError("raw record has no usable event timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedicated_runner_directory(
    source: Mapping[str, str],
    *,
    environment_key: str,
    error_code: str,
) -> str:
    """Resolve one required isolated runner directory without any fallback.

    A missing value used to inherit the web process working directory or the
    operating system temporary root.  Both make OpenBB extensions able to
    discover application state or mutate shared files.  An operator must now
    name an existing absolute directory for the runner service explicitly.
    """
    configured = source.get(environment_key, "").strip()
    if not configured or "\x00" in configured:
        raise OpenBBProviderError(error_code)
    candidate = Path(configured)
    if not candidate.is_absolute():
        raise OpenBBProviderError(error_code)
    try:
        resolved = candidate.resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise OpenBBProviderError(error_code) from exc
    if (
        not resolved.is_dir()
        or resolved == temporary_root
        or _runner_path_overlaps_application_checkout(resolved)
    ):
        raise OpenBBProviderError(error_code)
    inherited_home = source.get("HOME", "").strip()
    if inherited_home:
        try:
            inherited_home_directory = Path(inherited_home).resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            # A malformed inherited HOME must not relax the dedicated-path
            # requirement; it simply cannot be compared to a real directory.
            inherited_home_directory = None
        if inherited_home_directory is not None and resolved == inherited_home_directory:
            raise OpenBBProviderError(error_code)
    return str(resolved)


def _openbb_runner_environment(parent: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the minimal subprocess environment for a separately managed runner.

    The web process must not donate its database URL, session/JWT secrets,
    proxy credentials, Python import path, or home-directory configuration to
    a local OpenBB runner. Provider credentials belong to the runner's own
    service account or command wrapper. Only portable execution settings and
    the non-secret provider allow-list may cross this boundary.
    """
    source = os.environ if parent is None else parent
    environment = {
        key: value for key in _RUNNER_BASE_ENVIRONMENT_KEYS if (value := source.get(key))
    }
    for key in _RUNNER_OPENBB_CONTROL_ENVIRONMENT_KEYS:
        value = source.get(key)
        if value:
            environment[key] = value
    environment["HOME"] = _dedicated_runner_directory(
        source,
        environment_key=_RUNNER_HOME_ENVIRONMENT_KEY,
        error_code="OPENBB_RUNNER_HOME_INVALID",
    )
    return environment


def _openbb_runner_workdir(parent: Mapping[str, str] | None = None) -> str:
    """Return a dedicated runner directory, never the web process working tree."""
    source = os.environ if parent is None else parent
    return _dedicated_runner_directory(
        source,
        environment_key=_RUNNER_WORKDIR_ENVIRONMENT_KEY,
        error_code="OPENBB_RUNNER_WORKDIR_INVALID",
    )
