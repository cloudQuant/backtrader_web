import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.services.live_trading.metadata import (
    instance_timestamp,
    normalize_instance_metadata,
)

_logger = logging.getLogger(__name__)

# Callback dependencies injected by ``LiveTradingManager`` (file-IO, PID checks,
# directory resolution, etc.). Typed loosely since signatures vary per callback.
_Cb = Callable[..., Any]


def _resolve_instance_strategy_dir(
    inst: dict[str, Any],
    resolve_strategy_dir: _Cb,
) -> Path:
    runtime_dir = str(inst.get("runtime_dir") or "").strip()
    if runtime_dir:
        candidate = Path(runtime_dir).expanduser()
        if candidate.is_dir():
            return candidate
    return resolve_strategy_dir(inst["strategy_id"])


def _runtime_dir_key(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return str(Path(text).expanduser().resolve())
    except OSError:
        return str(Path(text).expanduser())


def _running_runtime_preference(instance_id: str, inst: dict[str, Any]) -> tuple[bool, str, str, str]:
    return (
        inst.get("error") in (None, ""),
        str(inst.get("started_at") or ""),
        str(inst.get("created_at") or ""),
        instance_id,
    )


def _dedupe_running_runtime_dirs(instances: dict[str, dict[str, Any]]) -> bool:
    by_runtime: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for instance_id, inst in instances.items():
        if str(inst.get("status") or "").lower() != "running":
            continue
        key = _runtime_dir_key(inst.get("runtime_dir"))
        if not key:
            continue
        by_runtime.setdefault(key, []).append((instance_id, inst))

    changed = False
    for entries in by_runtime.values():
        if len(entries) <= 1:
            continue
        keep_id, _keep_inst = max(entries, key=lambda item: _running_runtime_preference(*item))
        for instance_id, _inst in entries:
            if instance_id == keep_id:
                continue
            instances.pop(instance_id, None)
            changed = True
    return changed


def sync_status_on_boot(load_instances: _Cb, save_instances: _Cb, is_pid_alive: _Cb) -> None:
    instances = load_instances()
    changed = False
    now = instance_timestamp()
    for instance_id, inst in instances.items():
        if normalize_instance_metadata(inst, instance_id=instance_id, now=now):
            changed = True
        if inst.get("status") == "running":
            pid = inst.get("pid")
            if not pid or not is_pid_alive(pid):
                inst["status"] = "stopped"
                inst["pid"] = None
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
    if changed:
        save_instances(instances)


def list_instances(
    user_id: str | None,
    load_instances: _Cb,
    save_instances: _Cb,
    scan_running_strategy_pids: _Cb,
    is_pid_alive: _Cb,
    resolve_strategy_dir: _Cb,
    find_latest_log_dir: _Cb,
) -> list[dict[str, Any]]:
    instances = load_instances()
    changed = False
    now = instance_timestamp()
    running_pids = scan_running_strategy_pids()
    for instance_id, inst in instances.items():
        inst["id"] = instance_id
        if normalize_instance_metadata(inst, instance_id=instance_id, now=now):
            changed = True
        if inst.get("status") == "running":
            pid = inst.get("pid")
            if not pid or not is_pid_alive(pid):
                inst["status"] = "stopped"
                inst["pid"] = None
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
        if inst.get("status") != "running":
            try:
                strategy_dir = _resolve_instance_strategy_dir(inst, resolve_strategy_dir)
                run_py_path = str(strategy_dir / "run.py")
                if run_py_path in running_pids:
                    inst["status"] = "running"
                    inst["pid"] = running_pids[run_py_path]
                    inst["error"] = None
                    normalize_instance_metadata(
                        inst, instance_id=instance_id, now=now, touch=True
                    )
                    changed = True
            except ValueError as e:
                _logger.debug(f"Failed to resolve strategy dir for {inst.get('strategy_id')}: {e}")
    if _dedupe_running_runtime_dirs(instances):
        changed = True
    if changed:
        save_instances(instances)

    result = []
    for inst in instances.values():
        if user_id and inst.get("user_id") and inst["user_id"] != user_id:
            continue
        try:
            strategy_dir = _resolve_instance_strategy_dir(inst, resolve_strategy_dir)
        except ValueError:
            inst["log_dir"] = None
        else:
            inst["log_dir"] = find_latest_log_dir(strategy_dir)
        result.append(inst)
    return result


def add_instance(
    strategy_id: str,
    params: dict[str, Any] | None,
    user_id: str | None,
    load_instances: _Cb,
    save_instances: _Cb,
    resolve_strategy_dir: _Cb,
    get_template_by_id: _Cb,
    infer_gateway_params: _Cb,
    find_latest_log_dir: _Cb,
    runtime_dir: str | None = None,
) -> dict[str, Any]:
    runtime_dir_text = str(runtime_dir or "").strip()
    if runtime_dir_text:
        strategy_dir = Path(runtime_dir_text).expanduser()
    else:
        try:
            strategy_dir = resolve_strategy_dir(strategy_id)
        except ValueError:
            raise ValueError(f"Invalid strategy_id: {strategy_id}") from None
    if not (strategy_dir / "run.py").is_file():
        raise ValueError(f"Strategy {strategy_id} does not exist or lacks run.py")

    template = get_template_by_id(strategy_id)
    name = template.name if template else strategy_id

    merged_params = dict(params) if params else {}
    if "gateway" not in merged_params:
        try:
            inferred = infer_gateway_params(strategy_dir)
        except (KeyError, TypeError, ValueError, OSError):
            inferred = None
        if inferred:
            merged_params["gateway"] = inferred

    instance_id = str(uuid.uuid4())[:8]
    now = instance_timestamp()
    inst = {
        "id": instance_id,
        "strategy_id": strategy_id,
        "strategy_name": name,
        "user_id": user_id,
        "status": "stopped",
        "pid": None,
        "error": None,
        "params": merged_params,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "stopped_at": None,
        "log_dir": find_latest_log_dir(strategy_dir),
    }
    if runtime_dir_text:
        inst["runtime_dir"] = runtime_dir_text
    normalize_instance_metadata(inst, instance_id=instance_id, now=now)

    instances = load_instances()
    runtime_key = _runtime_dir_key(runtime_dir_text)
    if runtime_key:
        matching = [
            (instance_id, inst)
            for instance_id, inst in instances.items()
            if _runtime_dir_key(inst.get("runtime_dir")) == runtime_key
            and (not user_id or not inst.get("user_id") or inst.get("user_id") == user_id)
        ]
        running = [
            (instance_id, inst)
            for instance_id, inst in matching
            if str(inst.get("status") or "").lower() == "running" and inst.get("pid")
        ]
        if running:
            keep_id, keep_inst = max(
                running,
                key=lambda item: _running_runtime_preference(*item),
            )
            dirty = False
            for instance_id, _inst in matching:
                if instance_id == keep_id:
                    continue
                instances.pop(instance_id, None)
                dirty = True
            keep_inst["id"] = keep_id
            if normalize_instance_metadata(keep_inst, instance_id=keep_id, now=now):
                instances[keep_id] = keep_inst
                dirty = True
            if dirty:
                save_instances(instances)
            return keep_inst
        for instance_id, _inst in matching:
            instances.pop(instance_id, None)

    instances[instance_id] = inst
    save_instances(instances)
    return inst


def remove_instance(
    instance_id: str,
    user_id: str | None,
    load_instances: _Cb,
    save_instances: _Cb,
    kill_pid: _Cb,
    release_gateway_for_instance: _Cb,
    processes: dict[str, Any],
) -> bool:
    instances = load_instances()
    if instance_id not in instances:
        return False
    inst = instances[instance_id]
    if user_id and inst.get("user_id") and inst["user_id"] != user_id:
        return False
    if inst.get("status") == "running" and inst.get("pid"):
        kill_pid(inst["pid"])
    del instances[instance_id]
    save_instances(instances)
    processes.pop(instance_id, None)
    release_gateway_for_instance(instance_id)
    return True


def get_instance(
    instance_id: str,
    user_id: str | None,
    load_instances: _Cb,
    save_instances: _Cb,
    is_pid_alive: _Cb,
    scan_running_strategy_pids: _Cb,
    resolve_strategy_dir: _Cb,
    find_latest_log_dir: _Cb,
) -> dict[str, Any] | None:
    instances = load_instances()
    inst = instances.get(instance_id)
    if not inst:
        return None
    if user_id and inst.get("user_id") and inst["user_id"] != user_id:
        return None
    inst["id"] = instance_id
    now = instance_timestamp()
    changed = normalize_instance_metadata(inst, instance_id=instance_id, now=now)
    if inst.get("status") == "running":
        pid = inst.get("pid")
        if not pid or not is_pid_alive(pid):
            inst["status"] = "stopped"
            inst["pid"] = None
            normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
            changed = True
    try:
        strategy_dir = _resolve_instance_strategy_dir(inst, resolve_strategy_dir)
        if inst.get("status") != "running":
            running_pids = scan_running_strategy_pids()
            run_py_path = str(strategy_dir / "run.py")
            pid = running_pids.get(run_py_path)
            if pid and is_pid_alive(pid):
                inst["status"] = "running"
                inst["pid"] = pid
                inst["error"] = None
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
        inst["log_dir"] = find_latest_log_dir(strategy_dir)
    except ValueError:
        inst["log_dir"] = None
    if changed:
        instances[instance_id] = inst
        save_instances(instances)
    return inst
