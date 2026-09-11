"""Fail-closed raw-Popen transport for isolated OpenBB runners.

This module deliberately contains no OpenBB import, route permit, or provider
activation. It owns only bounded JSONL transport, fixed protocol attestation,
and POSIX process-group cleanup.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal

OPENBB_RUNNER_PROTOCOL_VERSION = "openbb-market-data-v2"
OPENBB_RUNNER_PROTOCOL_SELF_CHECK_VERSION = "openbb-market-data-protocol-self-check-v1"
OPENBB_RUNNER_TRANSPORT_VERSION = "openbb-jsonl-parent-stdin-ack-v2"
_MAX_RUNNER_OUTPUT_BYTES = 10 * 1024 * 1024
_RUNNER_READ_CHUNK_BYTES = 64 * 1024


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


@dataclass(frozen=True, slots=True)
class _OpenBBRunnerReceipt:
    """One newline-framed runner receipt retained before session shutdown."""

    data: bytes
    trailing: bytes
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


def _has_safe_openbb_process_group() -> bool:
    """Return whether this host can safely own a runner process group.

    The adapter intentionally has no request-process fallback.  It must be
    able to kill the entire runner session *before* it reaps the direct child;
    otherwise a finished leader PID could be reused before a stale process
    group ID is signalled.
    """
    return (
        os.name == "posix"
        and callable(getattr(os, "setsid", None))
        and callable(getattr(os, "killpg", None))
        and callable(getattr(os, "set_blocking", None))
        and callable(getattr(os, "waitpid", None))
        and hasattr(os, "WNOHANG")
        and hasattr(signal, "SIGKILL")
    )


def _has_safe_openbb_runner_event_loop() -> bool:
    """Return whether the current loop can drain raw-Popen pipes safely."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    return callable(getattr(loop, "add_reader", None)) and callable(
        getattr(loop, "add_writer", None)
    )


async def _read_openbb_runner_stream_bounded(
    stream: Any,
    *,
    maximum_bytes: int,
    initial_data: bytes = b"",
    initial_exceeded_limit: bool = False,
    stop_when_limit_exceeded: bool = False,
    close_stream: bool = True,
) -> _BoundedRunnerStream:
    """Drain one raw runner pipe while retaining a bounded response prefix."""
    loop = asyncio.get_running_loop()
    try:
        file_descriptor = stream.fileno()
        os.set_blocking(file_descriptor, False)
    except (AttributeError, OSError, ValueError) as exc:
        raise OpenBBProviderError("OPENBB_RUNNER_PROCESS_GROUP_UNSUPPORTED") from exc

    retained: list[bytes] = []
    if len(initial_data) <= maximum_bytes:
        retained.append(initial_data)
        remaining = maximum_bytes - len(initial_data)
        exceeded_limit = initial_exceeded_limit
    else:
        retained.append(initial_data[:maximum_bytes])
        remaining = 0
        exceeded_limit = True
    completed: asyncio.Future[_BoundedRunnerStream] = loop.create_future()

    def read_available() -> None:
        nonlocal remaining, exceeded_limit
        while True:
            try:
                chunk = os.read(file_descriptor, _RUNNER_READ_CHUNK_BYTES)
            except BlockingIOError:
                return
            except InterruptedError:
                continue
            except OSError as exc:
                if not completed.done():
                    completed.set_exception(exc)
                return
            if not chunk:
                if not completed.done():
                    completed.set_result(
                        _BoundedRunnerStream(
                            data=b"".join(retained),
                            exceeded_limit=exceeded_limit,
                        )
                    )
                return
            if remaining <= 0:
                exceeded_limit = True
                if stop_when_limit_exceeded and not completed.done():
                    completed.set_result(
                        _BoundedRunnerStream(
                            data=b"".join(retained),
                            exceeded_limit=True,
                        )
                    )
                    return
            elif len(chunk) <= remaining:
                retained.append(chunk)
                remaining -= len(chunk)
            else:
                retained.append(chunk[:remaining])
                remaining = 0
                exceeded_limit = True
                if stop_when_limit_exceeded and not completed.done():
                    completed.set_result(
                        _BoundedRunnerStream(
                            data=b"".join(retained),
                            exceeded_limit=True,
                        )
                    )
                    return

    loop.add_reader(file_descriptor, read_available)
    try:
        return await completed
    finally:
        loop.remove_reader(file_descriptor)
        if close_stream:
            with suppress(OSError):
                stream.close()


async def _read_openbb_runner_receipt(
    stream: Any,
    *,
    maximum_bytes: int,
) -> _OpenBBRunnerReceipt:
    """Read one newline-framed receipt while keeping stdout open for cleanup."""
    loop = asyncio.get_running_loop()
    try:
        file_descriptor = stream.fileno()
        os.set_blocking(file_descriptor, False)
    except (AttributeError, OSError, ValueError) as exc:
        raise OpenBBProviderError("OPENBB_RUNNER_PROCESS_GROUP_UNSUPPORTED") from exc

    retained: list[bytes] = []
    retained_length = 0
    completed: asyncio.Future[_OpenBBRunnerReceipt] = loop.create_future()

    def finish(*, trailing: bytes = b"", exceeded_limit: bool = False) -> None:
        if not completed.done():
            completed.set_result(
                _OpenBBRunnerReceipt(
                    data=b"".join(retained),
                    trailing=trailing,
                    exceeded_limit=exceeded_limit,
                )
            )

    def read_available() -> None:
        nonlocal retained_length
        while True:
            try:
                chunk = os.read(file_descriptor, _RUNNER_READ_CHUNK_BYTES)
            except BlockingIOError:
                return
            except InterruptedError:
                continue
            except OSError as exc:
                if not completed.done():
                    completed.set_exception(exc)
                return
            if not chunk:
                finish()
                return
            newline_index = chunk.find(b"\n")
            receipt_chunk = chunk if newline_index < 0 else chunk[: newline_index + 1]
            remaining = maximum_bytes - retained_length
            if len(receipt_chunk) > remaining:
                if remaining > 0:
                    retained.append(receipt_chunk[:remaining])
                    retained_length += remaining
                finish(exceeded_limit=True)
                return
            retained.append(receipt_chunk)
            retained_length += len(receipt_chunk)
            if newline_index >= 0:
                finish(trailing=chunk[newline_index + 1 :])
                return

    loop.add_reader(file_descriptor, read_available)
    try:
        return await completed
    finally:
        loop.remove_reader(file_descriptor)


async def _write_openbb_runner_input(
    stream: Any,
    payload: bytes,
    *,
    close_after_write: bool = True,
) -> None:
    """Write one JSON envelope, optionally retaining stdin for a receipt ACK."""
    loop = asyncio.get_running_loop()
    try:
        file_descriptor = stream.fileno()
        os.set_blocking(file_descriptor, False)
    except (AttributeError, OSError, ValueError) as exc:
        raise OpenBBProviderError("OPENBB_RUNNER_PROCESS_GROUP_UNSUPPORTED") from exc

    if not payload:
        if close_after_write:
            with suppress(OSError):
                stream.close()
        return
    completed: asyncio.Future[None] = loop.create_future()
    position = 0

    def write_available() -> None:
        nonlocal position
        try:
            written = os.write(file_descriptor, payload[position:])
        except BlockingIOError:
            return
        except InterruptedError:
            return
        except (BrokenPipeError, ConnectionResetError):
            if not completed.done():
                completed.set_result(None)
            return
        except OSError as exc:
            if not completed.done():
                completed.set_exception(exc)
            return
        if written <= 0:
            if not completed.done():
                completed.set_exception(OSError("runner stdin accepted no bytes"))
            return
        position += written
        if position == len(payload) and not completed.done():
            completed.set_result(None)

    loop.add_writer(file_descriptor, write_available)
    try:
        await completed
    finally:
        loop.remove_writer(file_descriptor)
        if close_after_write:
            with suppress(OSError):
                stream.close()


def _kill_owned_openbb_runner_group(process_group_id: int) -> OpenBBProviderError | None:
    """Kill a runner session while its leader remains deliberately unreaped."""
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        # The unreaped leader retains the original PID/PGID identity.  If the
        # group is already gone, this numeric ID cannot have been reused yet.
        return None
    except PermissionError as exc:
        # A denied signal cannot prove that a descendant stopped.  The caller
        # waits at the group-confirmation boundary and then fails closed.
        return OpenBBProviderError("OPENBB_RUNNER_CLEANUP_FAILED", detail=str(exc)[:512])
    return None


async def _reap_owned_openbb_runner_process(process: subprocess.Popen[bytes]) -> int:
    """Reap the direct runner only after the owned session was terminated."""
    while True:
        try:
            process_id, status = os.waitpid(process.pid, os.WNOHANG)
        except InterruptedError:
            continue
        except ChildProcessError as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_REAP_FAILED") from exc
        if process_id == process.pid:
            process.returncode = os.waitstatus_to_exitcode(status)
            return int(process.returncode)
        await asyncio.sleep(0.005)


async def _confirm_openbb_runner_group_terminated(process_group_id: int) -> None:
    """Prove group disappearance without another destructive post-reap signal."""
    while True:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return
        except OSError:
            # A zero-signal denial leaves cleanup unproven.  Keep the request
            # in the shielded boundary rather than releasing its runner slot.
            # Other transient signal errors are equally not proof that the
            # process group vanished, so they retain ownership and retry.
            pass
        await asyncio.sleep(0.005)


async def _await_openbb_runner_cleanup(
    *tasks: asyncio.Future[Any],
    ignore_cancelled: bool = False,
) -> bool:
    """Wait for kill/reap/drain even if the caller cancels repeatedly."""
    pending = [task for task in tasks if task is not None]
    if not pending:
        return False
    cleanup = asyncio.gather(*pending, return_exceptions=True)
    cancellation_requested = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            cancellation_requested = True
            continue
    results = await cleanup
    errors = [
        result
        for result in results
        if isinstance(result, BaseException)
        and not (ignore_cancelled and isinstance(result, asyncio.CancelledError))
    ]
    if errors:
        error = errors[0]
        if isinstance(error, OpenBBProviderError):
            raise error
        raise OpenBBProviderError("OPENBB_RUNNER_CLEANUP_FAILED", detail=str(error)[:512])
    return cancellation_requested


async def _cleanup_owned_openbb_runner_group(
    process: subprocess.Popen[bytes],
    *,
    stdin: Any | None,
    parent_ack_fd: int | None = None,
    input_task: asyncio.Future[Any] | None,
    collector_task: asyncio.Future[Any] | None,
    completion_task: asyncio.Future[Any] | None,
    receipt_task: asyncio.Future[Any] | None,
    receipt: _OpenBBRunnerReceipt | None,
    stdout: Any | None,
    stderr: Any | None,
    stderr_task: asyncio.Future[_BoundedRunnerStream] | None,
    stderr_prefix: _BoundedRunnerStream | None,
) -> tuple[int, _BoundedRunnerStream, _BoundedRunnerStream]:
    """Kill, reap, drain, then confirm one raw-Popen OpenBB runner session."""
    signal_error = _kill_owned_openbb_runner_group(process.pid)
    if parent_ack_fd is not None:
        with suppress(OSError):
            os.close(parent_ack_fd)
    if stdin is not None:
        with suppress(OSError):
            stdin.close()
    # Do not release a runner admission after an I/O task failure without
    # proving that the killed session disappeared.  In particular, a pipe
    # drain exception must not skip the non-destructive zero-signal proof.
    # The `finally` also covers an unexpected waitpid failure after group kill.
    try:
        returncode = await _reap_owned_openbb_runner_process(process)

        if receipt_task is not None and not receipt_task.done():
            receipt_task.cancel()
        if completion_task is not None and not completion_task.done():
            completion_task.cancel()
        if receipt_task is not None:
            # The receipt reader may be cancelled after timeout/caller
            # cancellation.  Actual pipe failures still surface from the explicit
            # bounded drain tasks below.
            await asyncio.gather(receipt_task, return_exceptions=True)

        receipt_prefix = receipt.data if receipt is not None else b""
        stdout_task: asyncio.Future[_BoundedRunnerStream] | None = None
        if stdout is not None:
            stdout_task = asyncio.create_task(
                _read_openbb_runner_stream_bounded(
                    stdout,
                    maximum_bytes=max(0, _MAX_RUNNER_OUTPUT_BYTES - len(receipt_prefix)),
                    initial_data=receipt.trailing if receipt is not None else b"",
                    initial_exceeded_limit=receipt.exceeded_limit if receipt is not None else False,
                )
            )
        stderr_drain_task: asyncio.Future[_BoundedRunnerStream] | None = stderr_task
        if stderr_prefix is not None:
            stderr_drain_task = (
                asyncio.create_task(
                    _read_openbb_runner_stream_bounded(
                        stderr,
                        maximum_bytes=max(0, _MAX_RUNNER_OUTPUT_BYTES - len(stderr_prefix.data)),
                    )
                )
                if stderr is not None
                else None
            )
        await _await_openbb_runner_cleanup(
            *(
                task
                for task in (
                    input_task,
                    collector_task,
                    completion_task,
                    stderr_task,
                    stdout_task,
                    stderr_drain_task,
                )
                if task is not None
            ),
            ignore_cancelled=True,
        )
    finally:
        await _confirm_openbb_runner_group_terminated(process.pid)
    if signal_error is not None:
        raise signal_error
    stdout_drain = (
        stdout_task.result()
        if stdout_task is not None
        else _BoundedRunnerStream(data=b"", exceeded_limit=False)
    )
    stderr_drain = (
        stderr_drain_task.result()
        if stderr_drain_task is not None
        else _BoundedRunnerStream(data=b"", exceeded_limit=False)
    )
    final_stderr = (
        _BoundedRunnerStream(
            data=stderr_prefix.data + stderr_drain.data,
            exceeded_limit=stderr_prefix.exceeded_limit or stderr_drain.exceeded_limit,
        )
        if stderr_prefix is not None
        else stderr_drain
    )
    return (
        returncode,
        _BoundedRunnerStream(
            data=receipt_prefix + stdout_drain.data,
            exceeded_limit=stdout_drain.exceeded_limit,
        ),
        final_stderr,
    )


class _OpenBBSubprocessRunner:
    """Run one JSON request in a raw-Popen POSIX session that this process owns."""

    def __init__(
        self,
        *,
        command: tuple[str, ...],
        environment: Mapping[str, str],
        workdir: str,
    ) -> None:
        self._command = command
        self._environment = dict(environment)
        self._workdir = workdir

    async def attest_protocol(self, *, timeout_seconds: float) -> None:
        """Prove the fixed JSONL/parent-ACK transport before a request spawn.

        The operator declaration is a deployment constraint, not evidence that
        the configured script understands the upgraded transport.  This
        one-shot preflight derives its sole extra CLI flag in this module,
        closes stdin so an old EOF-reading runner cannot masquerade as v2, and
        uses a parent-created ACK fd to keep the verified leader alive through
        group cleanup.
        """
        if not _has_safe_openbb_process_group() or not _has_safe_openbb_runner_event_loop():
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED")

        try:
            protocol_ack_read_fd, protocol_ack_write_fd = os.pipe()
        except OSError as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED") from exc
        preflight_environment = dict(self._environment)
        preflight_environment["OPENBB_PROTOCOL_SELF_CHECK_ACK_FD"] = str(protocol_ack_read_fd)
        try:
            process = subprocess.Popen(
                (*self._command, "--protocol-self-check"),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=preflight_environment,
                cwd=self._workdir,
                start_new_session=True,
                close_fds=True,
                pass_fds=(protocol_ack_read_fd,),
            )
        except OSError as exc:
            with suppress(OSError):
                os.close(protocol_ack_read_fd)
            with suppress(OSError):
                os.close(protocol_ack_write_fd)
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED") from exc
        finally:
            with suppress(OSError):
                os.close(protocol_ack_read_fd)

        if process.stdout is None or process.stderr is None:
            cleanup_task = asyncio.create_task(
                _cleanup_owned_openbb_runner_group(
                    process,
                    stdin=None,
                    parent_ack_fd=protocol_ack_write_fd,
                    input_task=None,
                    collector_task=None,
                    completion_task=None,
                    receipt_task=None,
                    receipt=None,
                    stdout=process.stdout,
                    stderr=process.stderr,
                    stderr_task=None,
                    stderr_prefix=None,
                )
            )
            try:
                await _await_openbb_runner_cleanup(cleanup_task)
            except Exception as exc:
                raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED") from exc
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED")

        receipt_task = asyncio.create_task(
            _read_openbb_runner_receipt(
                process.stdout,
                maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES,
            )
        )
        stderr_task = asyncio.create_task(
            _read_openbb_runner_stream_bounded(
                process.stderr,
                maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES,
                stop_when_limit_exceeded=True,
                close_stream=False,
            )
        )

        async def collect_receipt() -> _OpenBBRunnerReceipt:
            return await receipt_task

        collector_task = asyncio.create_task(collect_receipt())

        async def collect_receipt_or_stderr_limit() -> tuple[
            _OpenBBRunnerReceipt | None,
            _BoundedRunnerStream | None,
        ]:
            done, _pending = await asyncio.wait(
                (collector_task, stderr_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if collector_task in done:
                return await collector_task, None
            stderr_prefix = await stderr_task
            if stderr_prefix.exceeded_limit:
                return None, stderr_prefix
            return await collector_task

        completion_task = asyncio.create_task(collect_receipt_or_stderr_limit())
        initial_cancellation = False
        cleanup_cancellation = False
        receipt: _OpenBBRunnerReceipt | None = None
        stderr_prefix: _BoundedRunnerStream | None = None
        preflight_error: Exception | None = None
        cleanup_error: Exception | None = None
        cleanup_result: tuple[int, _BoundedRunnerStream, _BoundedRunnerStream] | None = None
        try:
            receipt, stderr_prefix = await asyncio.wait_for(
                asyncio.shield(completion_task), timeout=timeout_seconds
            )
        except asyncio.CancelledError:
            initial_cancellation = True
            raise
        except Exception as exc:
            preflight_error = exc
        finally:
            cleanup_task = asyncio.create_task(
                _cleanup_owned_openbb_runner_group(
                    process,
                    stdin=None,
                    parent_ack_fd=protocol_ack_write_fd,
                    input_task=None,
                    collector_task=collector_task,
                    completion_task=completion_task,
                    receipt_task=receipt_task,
                    receipt=receipt,
                    stdout=process.stdout,
                    stderr=process.stderr,
                    stderr_task=stderr_task,
                    stderr_prefix=stderr_prefix,
                )
            )
            try:
                cleanup_cancellation = await _await_openbb_runner_cleanup(cleanup_task)
                cleanup_result = cleanup_task.result()
            except Exception as exc:
                cleanup_error = exc
        if cleanup_cancellation and not initial_cancellation:
            raise asyncio.CancelledError
        if preflight_error is not None:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED") from preflight_error
        if cleanup_error is not None:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED") from cleanup_error
        if cleanup_result is None:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED")
        _returncode, stdout, stderr = cleanup_result
        if stdout.exceeded_limit or stderr.exceeded_limit or receipt is None:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED")
        try:
            response = json.loads(stdout.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED") from exc
        if not isinstance(response, Mapping) or set(response) != {
            "protocol_version",
            "protocol_self_check_version",
            "status",
            "transport_version",
        }:
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED")
        if (
            response.get("protocol_version") != OPENBB_RUNNER_PROTOCOL_VERSION
            or response.get("protocol_self_check_version")
            != OPENBB_RUNNER_PROTOCOL_SELF_CHECK_VERSION
            or response.get("transport_version") != OPENBB_RUNNER_TRANSPORT_VERSION
            or response.get("status") != "ready"
        ):
            raise OpenBBProviderError("OPENBB_RUNNER_PROTOCOL_UNATTESTED")

    async def execute(
        self,
        request_bytes: bytes,
        *,
        timeout_seconds: float,
    ) -> tuple[_BoundedRunnerStream, _BoundedRunnerStream]:
        """Exchange one bounded JSON response and reap its whole runner group."""
        if not _has_safe_openbb_process_group() or not _has_safe_openbb_runner_event_loop():
            raise OpenBBProviderError("OPENBB_RUNNER_PROCESS_GROUP_UNSUPPORTED")
        try:
            # Do not use asyncio's child watcher here.  It can reap a finished
            # direct child before the parent signals the original group,
            # turning a later numeric PGID kill into an unrelated process kill.
            process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment,
                cwd=self._workdir,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_UNAVAILABLE", detail=str(exc)[:512]) from exc

        if process.stdin is None or process.stdout is None or process.stderr is None:
            cleanup_task = asyncio.create_task(
                _cleanup_owned_openbb_runner_group(
                    process,
                    stdin=process.stdin,
                    input_task=None,
                    collector_task=None,
                    completion_task=None,
                    receipt_task=None,
                    receipt=None,
                    stdout=process.stdout,
                    stderr=process.stderr,
                    stderr_task=None,
                    stderr_prefix=None,
                )
            )
            await _await_openbb_runner_cleanup(cleanup_task)
            raise OpenBBProviderError("OPENBB_RUNNER_UNAVAILABLE")

        input_task = asyncio.create_task(
            _write_openbb_runner_input(
                process.stdin,
                request_bytes + b"\n",
                close_after_write=False,
            )
        )
        receipt_task = asyncio.create_task(
            _read_openbb_runner_receipt(
                process.stdout,
                maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES,
            )
        )
        stderr_task = asyncio.create_task(
            _read_openbb_runner_stream_bounded(
                process.stderr,
                maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES,
                stop_when_limit_exceeded=True,
                close_stream=False,
            )
        )

        async def send_and_collect() -> _OpenBBRunnerReceipt:
            await input_task
            return await receipt_task

        collector_task = asyncio.create_task(send_and_collect())

        async def collect_receipt_or_stderr_limit() -> tuple[
            _OpenBBRunnerReceipt | None,
            _BoundedRunnerStream | None,
        ]:
            done, _pending = await asyncio.wait(
                (collector_task, stderr_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if collector_task in done:
                return await collector_task, None
            stderr_prefix = await stderr_task
            if stderr_prefix.exceeded_limit:
                return None, stderr_prefix
            return await collector_task

        completion_task = asyncio.create_task(collect_receipt_or_stderr_limit())
        initial_cancellation = False
        cleanup_cancellation = False
        receipt: _OpenBBRunnerReceipt | None = None
        stderr_prefix: _BoundedRunnerStream | None = None
        cleanup_result: tuple[int, _BoundedRunnerStream, _BoundedRunnerStream] | None = None
        try:
            receipt, stderr_prefix = await asyncio.wait_for(
                asyncio.shield(completion_task), timeout=timeout_seconds
            )
        except TimeoutError as exc:
            raise OpenBBProviderError("OPENBB_RUNNER_TIMEOUT") from exc
        except asyncio.CancelledError:
            initial_cancellation = True
            raise
        finally:
            # This shielded cleanup boundary owns the PID from Popen through
            # group kill, waitpid, bounded pipe drain, and zero-signal proof.
            cleanup_task = asyncio.create_task(
                _cleanup_owned_openbb_runner_group(
                    process,
                    stdin=process.stdin,
                    input_task=input_task,
                    collector_task=collector_task,
                    stderr_task=stderr_task,
                    completion_task=completion_task,
                    receipt_task=receipt_task,
                    receipt=receipt,
                    stdout=process.stdout,
                    stderr=process.stderr,
                    stderr_prefix=stderr_prefix,
                )
            )
            cleanup_cancellation = await _await_openbb_runner_cleanup(cleanup_task)
            cleanup_result = cleanup_task.result()
        if cleanup_cancellation and not initial_cancellation:
            raise asyncio.CancelledError
        if cleanup_result is None:
            raise OpenBBProviderError("OPENBB_RUNNER_REAP_FAILED")
        returncode, stdout, stderr = cleanup_result
        if stdout.exceeded_limit or stderr.exceeded_limit:
            raise OpenBBProviderError("OPENBB_RUNNER_OUTPUT_TOO_LARGE")
        # A valid line-framed receipt is followed by parent-owned session
        # termination, so SIGKILL commonly supplies the direct-child status.
        # Without a receipt, retain the ordinary non-zero runner failure.
        if returncode != 0 and receipt is None:
            detail = stderr.data.decode("utf-8", errors="replace")[:2048] or None
            raise OpenBBProviderError("OPENBB_RUNNER_FAILED", detail=detail)
        return stdout, stderr
