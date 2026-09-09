"""Provider-neutral DTOs and the isolated OpenBB subprocess adapter.

OpenBB extensions are deliberately not imported by the FastAPI process.  The
adapter exchanges one bounded JSON request and response with an operator-owned
runner environment so extension dependencies, credentials and licenses remain
outside the web application's runtime dependency graph.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import shlex
import signal
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol

OPENBB_RUNNER_PROTOCOL_VERSION = "openbb-market-data-v1"
_MAX_RUNNER_OUTPUT_BYTES = 10 * 1024 * 1024
_MAX_OPENBB_RAW_PAYLOAD_BYTES = 4 * 1024 * 1024
_RUNNER_READ_CHUNK_BYTES = 64 * 1024
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
_RUNNER_HOME_ENVIRONMENT_KEY = "OPENBB_RUNNER_HOME"
_RUNNER_WORKDIR_ENVIRONMENT_KEY = "OPENBB_RUNNER_WORKDIR"


class OpenBBProviderError(RuntimeError):
    """Stable failure code emitted by the isolated OpenBB transport."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _BoundedRunnerStream:
    """A drained subprocess stream with a hard in-memory retention bound."""

    data: bytes
    exceeded_limit: bool


class _OpenBBRunnerGate:
    """One process-wide non-blocking admission gate for runner subprocesses."""

    def __init__(self) -> None:
        self._active = 0
        self._limit: int | None = None
        self._lock = asyncio.Lock()

    async def try_acquire(
        self,
        *,
        limit: int,
    ) -> Literal["acquired", "overloaded", "configuration_mismatch"]:
        """Reserve one slot, freezing the process-wide cap at first admission."""
        async with self._lock:
            if self._limit is None:
                self._limit = limit
            elif self._limit != limit:
                return "configuration_mismatch"
            if self._active >= self._limit:
                return "overloaded"
            self._active += 1
            return "acquired"

    async def release(self) -> None:
        """Release one previously admitted subprocess slot."""
        async with self._lock:
            if self._active < 1:
                raise RuntimeError("OpenBB runner gate release without acquisition")
            self._active -= 1


_PROCESS_OPENBB_RUNNER_GATE = _OpenBBRunnerGate()


async def _read_runner_stream_bounded(
    stream: asyncio.StreamReader,
    *,
    maximum_bytes: int,
) -> _BoundedRunnerStream:
    """Drain one runner pipe while retaining at most ``maximum_bytes``.

    Continuing to drain after the limit is crossed prevents a noisy child from
    blocking on its pipe before the timeout can terminate it. The parent
    retains only the bounded prefix, so untrusted runner output cannot grow web
    process memory before protocol validation rejects it.
    """
    retained: list[bytes] = []
    remaining = maximum_bytes
    exceeded_limit = False
    while chunk := await stream.read(_RUNNER_READ_CHUNK_BYTES):
        if remaining <= 0:
            exceeded_limit = True
            continue
        if len(chunk) <= remaining:
            retained.append(chunk)
            remaining -= len(chunk)
            continue
        retained.append(chunk[:remaining])
        remaining = 0
        exceeded_limit = True
    return _BoundedRunnerStream(data=b"".join(retained), exceeded_limit=exceeded_limit)


async def _terminate_runner_process(
    process: asyncio.subprocess.Process,
    *,
    process_group_id: int | None,
) -> None:
    """Stop a runner group without leaking its direct child or descendants."""
    if process_group_id is not None:
        try:
            # The leader may already have exited while a forked descendant
            # still holds stdout/stderr.  The known session leader PID is also
            # the process group ID, so kill it even after ``returncode`` is
            # set; ``getpgid(process.pid)`` would lose that group at exactly
            # the time the descendant needs cleanup.
            os.killpg(process_group_id, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    elif process.returncode is None:
        # Windows has no portable asyncio process-group equivalent here. The
        # direct child is still reaped; production isolation on that platform
        # must be supplied by the runner service/container.
        with suppress(ProcessLookupError):
            process.kill()
    with suppress(ProcessLookupError):
        await process.wait()


async def _communicate_runner_bounded(
    process: asyncio.subprocess.Process,
    request_bytes: bytes,
    *,
    timeout_seconds: float,
    process_group_id: int | None,
) -> tuple[_BoundedRunnerStream, _BoundedRunnerStream]:
    """Exchange runner JSON while bounding retained stdout and stderr bytes."""
    if process.stdin is None or process.stdout is None or process.stderr is None:
        await _terminate_runner_process(process, process_group_id=process_group_id)
        raise OpenBBProviderError("OPENBB_RUNNER_UNAVAILABLE")

    stdout_task = asyncio.create_task(
        _read_runner_stream_bounded(process.stdout, maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES)
    )
    stderr_task = asyncio.create_task(
        _read_runner_stream_bounded(process.stderr, maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES)
    )

    async def send_and_collect() -> tuple[int, _BoundedRunnerStream, _BoundedRunnerStream]:
        try:
            process.stdin.write(request_bytes)
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            # A runner may reject its input and exit immediately. Its bounded
            # stdout/stderr and exit code still determine the stable failure.
            pass
        finally:
            process.stdin.close()
        returncode, stdout, stderr = await asyncio.gather(process.wait(), stdout_task, stderr_task)
        return int(returncode), stdout, stderr

    try:
        returncode, stdout, stderr = await asyncio.wait_for(
            send_and_collect(), timeout=timeout_seconds
        )
    except TimeoutError as exc:
        await _terminate_runner_process(process, process_group_id=process_group_id)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise OpenBBProviderError("OPENBB_RUNNER_TIMEOUT") from exc
    except BaseException:
        await _terminate_runner_process(process, process_group_id=process_group_id)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise

    if stdout.exceeded_limit or stderr.exceeded_limit:
        raise OpenBBProviderError("OPENBB_RUNNER_OUTPUT_TOO_LARGE")
    if returncode != 0:
        detail = stderr.data.decode("utf-8", errors="replace")[:2048]
        raise OpenBBProviderError("OPENBB_RUNNER_FAILED", detail=detail)
    return stdout, stderr


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _require_text(value: str, *, field_name: str, maximum: int = 2048) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} is too long")
    return normalized


def _require_request_id(value: object) -> str:
    """Validate the opaque CSPRNG correlation token accepted from internal code."""
    if not isinstance(value, str):
        raise ValueError("request_id must be a string")
    normalized = value.strip()
    if (
        len(normalized) < 32
        or len(normalized) > 128
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            for character in normalized
        )
    ):
        raise ValueError("request_id must be an opaque base64url token")
    return normalized


def _require_sha256(value: object, *, field_name: str) -> str:
    """Validate a canonical SHA-256 hex digest without accepting a prefix."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return normalized


def _require_openbb_max_concurrent_runs(value: int) -> int:
    """Validate the operator-owned runner concurrency cap."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_concurrent_runs must be a positive integer")
    return value


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class MarketDataProviderRequest:
    """The bounded, provider-neutral request sent to one market-data adapter.

    ``request_id`` is generated once for each authorized fetch attempt with
    the operating-system CSPRNG.  It intentionally differs from the public
    query fingerprint, which describes business semantics rather than a
    specific provider call.
    """

    query_fingerprint: str
    canonical_id: str
    asset_type: str
    provider_symbol: str
    market: str
    data_kind: str
    frequency: str
    start_at: datetime
    end_at: datetime
    required_fields: frozenset[str]
    provider: str
    adjustment: str | None = None
    price_basis: str | None = None
    currency: str | None = None
    unit: str | None = None
    source_policy_id: str | None = None
    route_id: str | None = None
    # The resolved query product and the server-owned endpoint remain in the
    # echoed DTO so an isolated runner cannot substitute a same-shaped route.
    family_id: str | None = None
    provider_endpoint: str | None = None
    # These frozen master-data facts let an adapter defend a product-specific
    # source route even when it is invoked outside the policy selector.
    product_type: str | None = None
    fund_identity_kind: str | None = None
    # This is the reviewed, server-owned source-policy descriptor.  It is
    # deliberately separate from the authenticated caller's dynamic access
    # grant below, so a receipt can prove both what route policy allowed and
    # which current principal/source decision authorized the attempt.
    policy_descriptor_hash: str | None = None
    access_grant_descriptor_hash: str | None = None
    request_id: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    def __post_init__(self) -> None:
        for field_name in (
            "query_fingerprint",
            "canonical_id",
            "asset_type",
            "provider_symbol",
            "market",
            "data_kind",
            "frequency",
            "provider",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "adjustment",
            "price_basis",
            "currency",
            "unit",
            "source_policy_id",
            "route_id",
            "family_id",
            "provider_endpoint",
            "product_type",
            "fund_identity_kind",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_text(value, field_name=field_name, maximum=256),
                )
        object.__setattr__(self, "request_id", _require_request_id(self.request_id))
        if self.policy_descriptor_hash is not None:
            object.__setattr__(
                self,
                "policy_descriptor_hash",
                _require_sha256(
                    self.policy_descriptor_hash,
                    field_name="policy_descriptor_hash",
                ),
            )
        if self.access_grant_descriptor_hash is not None:
            object.__setattr__(
                self,
                "access_grant_descriptor_hash",
                _require_sha256(
                    self.access_grant_descriptor_hash,
                    field_name="access_grant_descriptor_hash",
                ),
            )
        if len(self.query_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.query_fingerprint.lower()
        ):
            raise ValueError("query_fingerprint must be a SHA-256 hex digest")
        start_at = _as_utc(self.start_at, field_name="start_at")
        end_at = _as_utc(self.end_at, field_name="end_at")
        if start_at >= end_at:
            raise ValueError("provider request requires a half-open [start_at, end_at) interval")
        if not isinstance(self.required_fields, frozenset) or not self.required_fields:
            raise ValueError("required_fields must be a non-empty frozenset")
        for field_name in self.required_fields:
            _require_text(field_name, field_name="required field", maximum=256)
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

    @property
    def dto_payload(self) -> dict[str, Any]:
        """Return the exact outbound DTO that a provider receipt must echo."""
        return {
            "request_id": self.request_id,
            "query_fingerprint": self.query_fingerprint,
            "canonical_id": self.canonical_id,
            "asset_type": self.asset_type,
            "provider_symbol": self.provider_symbol,
            "market": self.market,
            "data_kind": self.data_kind,
            "frequency": self.frequency,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "required_fields": sorted(self.required_fields),
            "provider": self.provider,
            "adjustment": self.adjustment,
            "price_basis": self.price_basis,
            "currency": self.currency,
            "unit": self.unit,
            "source_policy_id": self.source_policy_id,
            "route_id": self.route_id,
            "family_id": self.family_id,
            "provider_endpoint": self.provider_endpoint,
            "product_type": self.product_type,
            "fund_identity_kind": self.fund_identity_kind,
            "policy_descriptor_hash": self.policy_descriptor_hash,
            "access_grant_descriptor_hash": self.access_grant_descriptor_hash,
        }

    @property
    def provider_request_fingerprint_sha256(self) -> str:
        """Hash the complete outbound DTO independently from query identity."""
        return hashlib.sha256(_canonical_json(self.dto_payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderMarketObservation:
    """One normalized observation returned by a provider adapter."""

    event_at: datetime
    available_at: datetime
    fields: Mapping[str, Any]

    def __post_init__(self) -> None:
        event_at = _as_utc(self.event_at, field_name="event_at")
        available_at = _as_utc(self.available_at, field_name="available_at")
        if not isinstance(self.fields, Mapping):
            raise TypeError("fields must be a mapping")
        normalized_fields: dict[str, Any] = {}
        for field_name, value in self.fields.items():
            normalized_field_name = _require_text(field_name, field_name="field", maximum=256)
            if normalized_field_name in normalized_fields:
                raise ValueError("provider observation contains duplicate normalized field names")
            normalized_fields[normalized_field_name] = value
        if not normalized_fields:
            raise ValueError("provider observation fields must not be empty")
        object.__setattr__(self, "event_at", event_at)
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "fields", MappingProxyType(normalized_fields))


@dataclass(frozen=True, slots=True)
class ProviderFetchResult:
    """Source-provenanced provider response ready for validation and persistence."""

    provider_id: str
    source_revision: str
    retrieved_at: datetime
    observations: tuple[ProviderMarketObservation, ...]
    raw_payload: Mapping[str, Any]
    request: MarketDataProviderRequest
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "provider_id", _require_text(self.provider_id, field_name="provider_id")
        )
        object.__setattr__(
            self,
            "source_revision",
            _require_text(self.source_revision, field_name="source_revision"),
        )
        object.__setattr__(
            self, "retrieved_at", _as_utc(self.retrieved_at, field_name="retrieved_at")
        )
        observations = tuple(self.observations)
        if any(not isinstance(item, ProviderMarketObservation) for item in observations):
            raise TypeError("observations must contain ProviderMarketObservation values")
        if not isinstance(self.raw_payload, Mapping):
            raise TypeError("raw_payload must be a mapping")
        if not isinstance(self.request, MarketDataProviderRequest):
            raise TypeError("request must be the original MarketDataProviderRequest")
        warnings = tuple(_require_text(item, field_name="warning") for item in self.warnings)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "raw_payload", MappingProxyType(dict(self.raw_payload)))
        object.__setattr__(self, "warnings", warnings)

    @property
    def raw_payload_hash(self) -> str:
        """Return a deterministic integrity hash for the persisted source payload."""
        # ``__post_init__`` freezes the top-level receipt mapping so callers
        # cannot replace its evidence envelope after provider validation.
        # ``json.dumps`` does not know how to serialize ``mappingproxy``
        # directly, however.  Hash a plain snapshot of that immutable mapping
        # so the public provenance helper remains usable for every validated
        # AkShare/OpenBB result and preserves the same canonical JSON bytes.
        return hashlib.sha256(_canonical_json(dict(self.raw_payload)).encode("utf-8")).hexdigest()


class MarketDataProvider(Protocol):
    """A narrow adapter boundary for AkShare, OpenBB, or approved future sources."""

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        """Fetch an exact bounded request without writing storage directly."""


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


def _is_safe_openbb_runner_command(command: tuple[str, ...]) -> bool:
    """Require a small, shell-free, absolute runner command grammar.

    The operator may run one dedicated executable, or one absolute executable
    with one absolute script argument.  Permitting arbitrary interpreter
    switches, module names, relative paths, or wrappers would make the
    configured command an unreviewed program-selection mechanism.
    """
    if not command or not _is_safe_openbb_runner_file(command[0], executable=True):
        return False
    return len(command) == 1 or (
        len(command) == 2 and _is_safe_openbb_runner_file(command[1], executable=False)
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
            raise ValueError("runner command must be an explicit absolute executable or script")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if (
            configuration_error is not None
            and configuration_error != "OPENBB_RUNNER_COMMAND_INVALID"
        ):
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
        """Build the adapter from an operator-defined executable command only."""
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
            subprocess_options: dict[str, bool] = {}
            if os.name == "posix":
                # Required by ``_terminate_runner_process`` to make each runner
                # its own killable process group without touching the web worker.
                subprocess_options["start_new_session"] = True
            try:
                process = await asyncio.create_subprocess_exec(
                    *self._command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_openbb_runner_environment(),
                    cwd=_openbb_runner_workdir(),
                    **subprocess_options,
                )
            except OSError as exc:
                raise OpenBBProviderError("OPENBB_RUNNER_UNAVAILABLE", detail=str(exc)) from exc

            encoded_request = _canonical_json(request_payload).encode("utf-8")
            stdout, _stderr = await _communicate_runner_bounded(
                process,
                encoded_request,
                timeout_seconds=self._timeout_seconds,
                process_group_id=process.pid if os.name == "posix" else None,
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
