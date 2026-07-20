import asyncio
import contextlib
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services.live_trading import instance as live_instance_service
from app.services.live_trading.metadata import (
    instance_timestamp,
    normalize_instance_metadata,
)

# Callback dependencies injected by ``LiveTradingManager``; typed loosely
# since the concrete signatures vary per callback.
_Cb = Callable[..., Any]
_SUBPROCESS_STDOUT_LOG = "subprocess.stdout.log"
_SUBPROCESS_STDERR_LOG = "subprocess.stderr.log"


def _optional_lock(lock: Any | None) -> contextlib.AbstractContextManager[Any]:
    return lock if lock is not None else contextlib.nullcontext()


def _decode_output_tail(data: bytes, limit: int = 500) -> str:
    for encoding in ("utf-8", "gbk", "cp936"):
        try:
            return data.decode(encoding)[-limit:]
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")[-limit:]


def _read_file_tail(path: Path, limit: int = 500, read_bytes: int = 8192) -> str:
    try:
        with path.open("rb") as handle:
            try:
                handle.seek(-read_bytes, os.SEEK_END)
            except OSError:
                handle.seek(0)
            data = handle.read()
    except OSError:
        return ""
    return _decode_output_tail(data, limit=limit)


def _close_subprocess_log_handles(proc: asyncio.subprocess.Process) -> None:
    proc_attrs = getattr(proc, "__dict__", {})
    for attr in ("_bt_stdout_handle", "_bt_stderr_handle"):
        handle = proc_attrs.get(attr)
        if handle is None:
            continue
        try:
            handle.close()
        except OSError:
            pass


def _merge_runtime_contract_metadata(
    target: dict[str, Any],
    source: dict[str, Any],
) -> None:
    source_params = source.get("params") if isinstance(source.get("params"), dict) else {}
    contract_metadata = source_params.get("contract_metadata")
    if not isinstance(contract_metadata, dict) or not contract_metadata:
        return

    target_params = (
        dict(target.get("params") or {}) if isinstance(target.get("params"), dict) else {}
    )
    target_metadata = (
        dict(target_params.get("contract_metadata") or {})
        if isinstance(target_params.get("contract_metadata"), dict)
        else {}
    )
    for key, value in contract_metadata.items():
        if isinstance(value, dict):
            target_metadata[str(key)] = dict(value)
    if not target_metadata:
        return
    target_params["contract_metadata"] = target_metadata
    target["params"] = target_params


async def start_instance(
    instance_id: str,
    load_instances: _Cb,
    save_instances: _Cb,
    is_pid_alive: _Cb,
    resolve_strategy_dir: _Cb,
    build_subprocess_env: _Cb,
    release_gateway_for_instance: _Cb,
    wait_process_callback: _Cb,
    processes: dict[str, Any],
    stopping_instances: set[str],
    instance_lock: Any | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    instances = load_instances()
    if instance_id not in instances:
        raise live_instance_service.InstanceAccessError("Instance not found")
    inst = instances[instance_id]
    if user_id is not None and inst.get("user_id") != user_id:
        raise live_instance_service.InstanceAccessError("Instance not found")

    if inst["status"] == "running" and inst.get("pid") and is_pid_alive(inst["pid"]):
        raise ValueError("Strategy is already running")

    try:
        runtime_dir = str(inst.get("runtime_dir") or "").strip()
        strategy_dir = (
            Path(runtime_dir).expanduser()
            if runtime_dir
            else resolve_strategy_dir(inst["strategy_id"])
        )
    except ValueError as exc:
        raise ValueError(f"Invalid strategy_id: {inst['strategy_id']}") from exc
    run_py = strategy_dir / "run.py"
    if not run_py.is_file():
        raise ValueError(f"run.py does not exist: {run_py}")

    try:
        # Gateway preparation may wait for an external broker to authenticate.
        # Keep that synchronous adapter work off the ASGI event loop so a bad
        # broker credential cannot stall health checks, status polling, or the
        # portfolio/risk APIs while this instance is being started.
        env = await asyncio.to_thread(build_subprocess_env, instance_id, inst, strategy_dir)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        release_gateway_for_instance(instance_id)
        now = instance_timestamp()
        async with _optional_lock(instance_lock):
            latest = load_instances()
            inst = latest.get(instance_id, inst)
            inst["status"] = "error"
            inst["pid"] = None
            inst["error"] = str(exc)
            inst["stopped_at"] = now
            normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
            latest[instance_id] = inst
            save_instances(latest)
        raise ValueError(str(exc)) from exc

    sub_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        import subprocess as _sp

        sub_kwargs["creationflags"] = _sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW
    stdout_handle = None
    stderr_handle = None
    try:
        logs_dir = strategy_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / _SUBPROCESS_STDOUT_LOG
        stderr_path = logs_dir / _SUBPROCESS_STDERR_LOG
        stdout_handle = stdout_path.open("ab", buffering=0)
        stderr_handle = stderr_path.open("ab", buffering=0)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(run_py),
            cwd=str(strategy_dir),
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=env,
            **sub_kwargs,
        )
        proc._bt_stdout_handle = stdout_handle
        proc._bt_stderr_handle = stderr_handle
        proc._bt_stderr_path = str(stderr_path)
    except (OSError, subprocess.SubprocessError):
        for handle in (stdout_handle, stderr_handle):
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
        release_gateway_for_instance(instance_id)
        raise
    stopping_instances.discard(instance_id)
    processes[instance_id] = proc

    refreshed_inst = inst
    now = instance_timestamp()
    async with _optional_lock(instance_lock):
        latest = load_instances()
        latest_inst = latest.get(instance_id)
        if isinstance(latest_inst, dict):
            _merge_runtime_contract_metadata(latest_inst, refreshed_inst)
            inst = latest_inst
        else:
            inst = refreshed_inst
        inst["status"] = "running"
        inst["pid"] = proc.pid
        inst["error"] = None
        inst["started_at"] = now
        inst["stopped_at"] = None
        normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
        latest[instance_id] = inst
        save_instances(latest)
    asyncio.create_task(wait_process_callback(instance_id, proc))
    inst["id"] = instance_id
    return inst


async def stop_instance(
    instance_id: str,
    load_instances: _Cb,
    save_instances: _Cb,
    is_pid_alive: _Cb,
    kill_pid: _Cb,
    release_gateway_for_instance: _Cb,
    processes: dict[str, Any],
    stopping_instances: set[str],
    instance_lock: Any | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    instances = load_instances()
    if instance_id not in instances:
        raise live_instance_service.InstanceAccessError("Instance not found")
    inst = instances[instance_id]
    if user_id is not None and inst.get("user_id") != user_id:
        raise live_instance_service.InstanceAccessError("Instance not found")
    stopping_instances.add(instance_id)

    pid = inst.get("pid")
    if pid and is_pid_alive(pid):
        kill_pid(pid)

    proc = processes.pop(instance_id, None)
    if proc and proc.returncode is None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except (ProcessLookupError, asyncio.TimeoutError, OSError, RuntimeError):
            proc.kill()

    now = instance_timestamp()
    async with _optional_lock(instance_lock):
        latest = load_instances()
        inst = latest.get(instance_id, inst)
        inst["status"] = "stopped"
        inst["pid"] = None
        inst["stopped_at"] = now
        normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
        latest[instance_id] = inst
        save_instances(latest)
    release_gateway_for_instance(instance_id)
    inst["id"] = instance_id
    return inst


async def start_all(
    user_id: str | None,
    load_instances: _Cb,
    is_pid_alive: _Cb,
    start_instance_callback: _Cb,
) -> dict[str, Any]:
    instances = load_instances()
    success = 0
    failed = 0
    details = []
    for instance_id, inst in instances.items():
        if user_id is not None and inst.get("user_id") != user_id:
            continue
        if inst["status"] == "running" and inst.get("pid") and is_pid_alive(inst["pid"]):
            continue
        try:
            await start_instance_callback(instance_id)
            success += 1
            details.append(
                {"id": instance_id, "strategy_id": inst["strategy_id"], "result": "started"}
            )
        except Exception as exc:
            failed += 1
            details.append(
                {"id": instance_id, "strategy_id": inst["strategy_id"], "result": str(exc)}
            )
    return {"success": success, "failed": failed, "details": details}


async def stop_all(
    user_id: str | None,
    load_instances: _Cb,
    stop_instance_callback: _Cb,
) -> dict[str, Any]:
    instances = load_instances()
    success = 0
    failed = 0
    details = []
    for instance_id, inst in instances.items():
        if user_id is not None and inst.get("user_id") != user_id:
            continue
        if inst["status"] != "running":
            continue
        try:
            await stop_instance_callback(instance_id)
            success += 1
            details.append(
                {"id": instance_id, "strategy_id": inst["strategy_id"], "result": "stopped"}
            )
        except Exception as exc:
            failed += 1
            details.append(
                {"id": instance_id, "strategy_id": inst["strategy_id"], "result": str(exc)}
            )
    return {"success": success, "failed": failed, "details": details}


async def wait_process(
    instance_id: str,
    proc: asyncio.subprocess.Process,
    load_instances: _Cb,
    save_instances: _Cb,
    resolve_strategy_dir: _Cb,
    find_latest_log_dir: _Cb,
    release_gateway_for_instance: _Cb,
    processes: dict[str, Any],
    stopping_instances: set[str],
    instance_lock: Any | None = None,
) -> None:
    try:
        await proc.wait()
    except asyncio.CancelledError:
        # Supervisors can intentionally exit after starting a detached strategy
        # (for example run_dual_exchange_simulation.py --no-hold). In that case
        # asyncio cancels this background watcher while the child process is
        # still running and proc.returncode is still None. The instance must
        # remain running for the next monitor/backend process to observe it.
        pass
    except Exception as e:
        # wait() may raise if process already terminated; safe to ignore
        # but log for debugging visibility
        import logging

        logging.getLogger(__name__).debug("proc.wait() raised (ignored): %s", e)
    finally:
        _close_subprocess_log_handles(proc)
        stale_callback = False
        async with _optional_lock(instance_lock):
            instances = load_instances()
            current_proc = processes.get(instance_id)
            if current_proc is not None and current_proc is not proc:
                stale_callback = True
            if instance_id in instances:
                inst = instances[instance_id]
                current_pid = inst.get("pid")
                if current_pid not in (None, proc.pid):
                    stale_callback = True
                if not stale_callback:
                    was_stopping = instance_id in stopping_instances
                    if proc.returncode is None and not was_stopping:
                        stale_callback = True
                    else:
                        if was_stopping:
                            inst["status"] = "stopped"
                            inst["error"] = None
                        elif proc.returncode != 0:
                            stderr = ""
                            if proc.stderr:
                                try:
                                    stderr_bytes = await proc.stderr.read()
                                    stderr = _decode_output_tail(stderr_bytes, limit=500)
                                except Exception as e:
                                    # stderr read failed; use empty string
                                    import logging

                                    logging.getLogger(__name__).warning(
                                        "Failed to read stderr: %s", e
                                    )
                            if not stderr:
                                proc_attrs = getattr(proc, "__dict__", {})
                                stderr_path = str(proc_attrs.get("_bt_stderr_path") or "").strip()
                                if stderr_path:
                                    stderr = _read_file_tail(Path(stderr_path), limit=500)
                            inst["status"] = "error"
                            inst["error"] = stderr or f"Process exit code: {proc.returncode}"
                        else:
                            inst["status"] = "stopped"
                            inst["error"] = None
                        inst["pid"] = None
                        now = instance_timestamp()
                        inst["stopped_at"] = now
                        normalize_instance_metadata(
                            inst, instance_id=instance_id, now=now, touch=True
                        )
                        try:
                            runtime_dir = str(inst.get("runtime_dir") or "").strip()
                            strategy_dir = (
                                Path(runtime_dir).expanduser()
                                if runtime_dir
                                else resolve_strategy_dir(inst["strategy_id"])
                            )
                            inst["log_dir"] = find_latest_log_dir(strategy_dir)
                        except ValueError:
                            inst["log_dir"] = None
                        instances[instance_id] = inst
                        save_instances(instances)
            if not stale_callback:
                processes.pop(instance_id, None)
                stopping_instances.discard(instance_id)
        if not stale_callback:
            release_gateway_for_instance(instance_id)
