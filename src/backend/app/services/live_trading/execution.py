import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


async def start_instance(
    instance_id: str,
    load_instances,
    save_instances,
    is_pid_alive,
    resolve_strategy_dir,
    build_subprocess_env,
    release_gateway_for_instance,
    wait_process_callback,
    processes: dict[str, Any],
    stopping_instances: set[str],
) -> dict[str, Any]:
    instances = load_instances()
    if instance_id not in instances:
        raise ValueError("Instance does not exist")
    inst = instances[instance_id]

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

    env = build_subprocess_env(instance_id, inst, strategy_dir)
    sub_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        import subprocess as _sp

        sub_kwargs["creationflags"] = _sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(run_py),
            cwd=str(strategy_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            **sub_kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        release_gateway_for_instance(instance_id)
        raise
    stopping_instances.discard(instance_id)
    processes[instance_id] = proc

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inst["status"] = "running"
    inst["pid"] = proc.pid
    inst["error"] = None
    inst["started_at"] = now
    instances[instance_id] = inst
    save_instances(instances)
    asyncio.create_task(wait_process_callback(instance_id, proc))
    inst["id"] = instance_id
    return inst


async def stop_instance(
    instance_id: str,
    load_instances,
    save_instances,
    is_pid_alive,
    kill_pid,
    release_gateway_for_instance,
    processes: dict[str, Any],
    stopping_instances: set[str],
) -> dict[str, Any]:
    instances = load_instances()
    if instance_id not in instances:
        raise ValueError("Instance does not exist")
    inst = instances[instance_id]
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

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inst["status"] = "stopped"
    inst["pid"] = None
    inst["stopped_at"] = now
    instances[instance_id] = inst
    save_instances(instances)
    release_gateway_for_instance(instance_id)
    inst["id"] = instance_id
    return inst


async def start_all(
    user_id: str | None,
    load_instances,
    is_pid_alive,
    start_instance_callback,
) -> dict[str, Any]:
    instances = load_instances()
    success = 0
    failed = 0
    details = []
    for instance_id, inst in instances.items():
        if user_id and inst.get("user_id") and inst["user_id"] != user_id:
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
    load_instances,
    stop_instance_callback,
) -> dict[str, Any]:
    instances = load_instances()
    success = 0
    failed = 0
    details = []
    for instance_id, inst in instances.items():
        if user_id and inst.get("user_id") and inst["user_id"] != user_id:
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
    proc,
    load_instances,
    save_instances,
    resolve_strategy_dir,
    find_latest_log_dir,
    release_gateway_for_instance,
    processes: dict[str, Any],
    stopping_instances: set[str],
) -> None:
    try:
        await proc.wait()
    except Exception as e:
        # wait() may raise if process already terminated; safe to ignore
        # but log for debugging visibility
        import logging

        logging.getLogger(__name__).debug("proc.wait() raised (ignored): %s", e)
    finally:
        instances = load_instances()
        stale_callback = False
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
                if was_stopping:
                    inst["status"] = "stopped"
                    inst["error"] = None
                elif proc.returncode != 0:
                    stderr = ""
                    if proc.stderr:
                        try:
                            stderr_bytes = await proc.stderr.read()
                            for encoding in ("utf-8", "gbk", "cp936"):
                                try:
                                    stderr = stderr_bytes.decode(encoding)
                                    break
                                except (UnicodeDecodeError, LookupError):
                                    continue
                            else:
                                stderr = stderr_bytes.decode("utf-8", errors="replace")
                            stderr = stderr[-500:]
                        except Exception as e:
                            # stderr read failed; use empty string
                            import logging

                            logging.getLogger(__name__).warning("Failed to read stderr: %s", e)
                    inst["status"] = "error"
                    inst["error"] = stderr or f"Process exit code: {proc.returncode}"
                else:
                    inst["status"] = "stopped"
                    inst["error"] = None
                inst["pid"] = None
                inst["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            release_gateway_for_instance(instance_id)
