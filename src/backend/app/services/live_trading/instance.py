import logging
import os
import sys
import uuid
from collections.abc import Callable
from datetime import datetime
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


class InstanceAccessError(ValueError):
    """Raised when an instance is absent or outside the caller's scope.

    The same error is intentionally used for both cases so API callers cannot
    enumerate another user's instance IDs.
    """


def require_instance_access(
    instance_id: str,
    user_id: str | None,
    load_instances: _Cb,
) -> dict[str, Any]:
    """Return an instance only when it belongs to the supplied user scope.

    ``None`` is reserved for trusted in-process maintenance callers. Every
    request-facing path must pass a concrete user ID. Historical ownerless
    records are deliberately invisible to such callers.
    """
    inst = load_instances().get(instance_id)
    if not isinstance(inst, dict) or (user_id is not None and inst.get("user_id") != user_id):
        raise InstanceAccessError("Instance not found")
    return inst


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


def _running_runtime_preference(
    instance_id: str, inst: dict[str, Any]
) -> tuple[bool, str, str, str]:
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


def _touch_running_instance_daily(inst: dict[str, Any], now: str) -> bool:
    """Touch running instances when they have moved to a new calendar day."""
    if str(inst.get("status") or "").lower() != "running":
        return False
    if not now:
        return False
    return str(inst.get("updated_at") or "").strip()[:10] != str(now).strip()[:10]


def _coerce_pid(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _infer_started_at_from_pid(pid: int) -> str | None:
    if pid <= 0:
        return None
    if sys.platform == "win32":
        return None

    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.is_file():
        return None

    try:
        stat_text = stat_path.read_text(encoding="utf-8")
        close_paren = stat_text.rfind(")")
        if close_paren < 0:
            return None
        parts = stat_text[close_paren + 2 :].split()
        if len(parts) < 20:
            return None
        start_ticks = int(parts[19])
    except (OSError, ValueError):
        return None

    try:
        with Path("/proc/stat").open(encoding="utf-8") as handle:
            boot_time: float | None = None
            for line in handle:
                if not line.startswith("btime"):
                    continue
                boot_time = float(line.split()[1])
                break
    except OSError:
        return None
    if boot_time is None:
        return None

    try:
        clock_ticks = os.sysconf("SC_CLK_TCK")
        epoch_seconds = boot_time + start_ticks / clock_ticks
        return datetime.fromtimestamp(epoch_seconds).strftime("%Y-%m-%d %H:%M:%S")
    except (AttributeError, OSError, ValueError):
        return None


def _started_day(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:10]


def _refresh_started_at_from_pid(inst: dict[str, Any], pid: int) -> bool:
    inferred_started = _infer_started_at_from_pid(pid)
    if not inferred_started:
        return False

    inferred_day = _started_day(inferred_started)
    if not inferred_day:
        return False

    current_day = _started_day(inst.get("started_at"))
    if not current_day:
        return False
    if not current_day or inferred_day > current_day:
        inst["started_at"] = inferred_started
        return True

    return False


def _running_pid_for_instance(
    inst: dict[str, Any],
    running_pids: dict[str, int],
    resolve_strategy_dir: _Cb,
) -> int | None:
    try:
        strategy_dir = _resolve_instance_strategy_dir(inst, resolve_strategy_dir)
    except ValueError:
        return None
    run_py_path = str(strategy_dir / "run.py")
    candidates = [run_py_path]
    resolved_path = _runtime_dir_key(run_py_path)
    if resolved_path:
        candidates.append(resolved_path)
    for candidate in candidates:
        pid = running_pids.get(candidate)
        if pid:
            return pid
    return None


def sync_status_on_boot(load_instances: _Cb, save_instances: _Cb, is_pid_alive: _Cb) -> None:
    instances = load_instances()
    changed = False
    now = instance_timestamp()
    for instance_id, inst in instances.items():
        if normalize_instance_metadata(inst, instance_id=instance_id, now=now):
            changed = True
        if inst.get("status") == "running":
            pid = _coerce_pid(inst.get("pid"))
            if not pid or not is_pid_alive(pid):
                inst["status"] = "stopped"
                inst["pid"] = None
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
            elif _refresh_started_at_from_pid(inst, pid):
                normalize_instance_metadata(inst, instance_id=instance_id, now=now)
                changed = True
            elif _touch_running_instance_daily(inst, now):
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
            mapped_pid = _running_pid_for_instance(inst, running_pids, resolve_strategy_dir)
            pid = _coerce_pid(inst.get("pid"))
            # A PID can be recycled by an unrelated application after the strategy
            # exits.  Treat the strategy-process scan as the source of truth rather
            # than trusting that an arbitrary live PID still belongs to this instance.
            if not mapped_pid or not is_pid_alive(mapped_pid):
                inst["status"] = "stopped"
                inst["pid"] = None
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
            elif pid != mapped_pid:
                inst["pid"] = mapped_pid
                inst["status"] = "running"
                inst["started_at"] = now
                inst["error"] = None
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
            elif _refresh_started_at_from_pid(inst, pid):
                normalize_instance_metadata(inst, instance_id=instance_id, now=now)
                changed = True
            elif _touch_running_instance_daily(inst, now):
                normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
                changed = True
        if inst.get("status") != "running":
            try:
                strategy_dir = _resolve_instance_strategy_dir(inst, resolve_strategy_dir)
                mapped_pid = _running_pid_for_instance(inst, running_pids, resolve_strategy_dir)
                if mapped_pid and is_pid_alive(mapped_pid):
                    inst["status"] = "running"
                    inst["pid"] = mapped_pid
                    inst["started_at"] = now
                    inst["error"] = None
                    normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
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
            and (user_id is None or inst.get("user_id") == user_id)
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
            for existing_instance_id, _inst in matching:
                if existing_instance_id == keep_id:
                    continue
                instances.pop(existing_instance_id, None)
                dirty = True
            keep_inst["id"] = keep_id
            if normalize_instance_metadata(keep_inst, instance_id=keep_id, now=now):
                instances[keep_id] = keep_inst
                dirty = True
            if dirty:
                save_instances(instances)
            return keep_inst
        for existing_instance_id, _inst in matching:
            instances.pop(existing_instance_id, None)

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
    if user_id is not None and inst.get("user_id") != user_id:
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
    if user_id is not None and inst.get("user_id") != user_id:
        return None
    inst["id"] = instance_id
    now = instance_timestamp()
    changed = normalize_instance_metadata(inst, instance_id=instance_id, now=now)
    running_pids = scan_running_strategy_pids()
    if inst.get("status") == "running":
        mapped_pid = None
        try:
            mapped_pid = _running_pid_for_instance(
                inst,
                running_pids,
                resolve_strategy_dir,
            )
        except ValueError:
            mapped_pid = None
        pid = _coerce_pid(inst.get("pid"))
        # A live PID alone is insufficient: it can already have been reused by
        # another process.  The scanned run.py path must match this instance.
        if not mapped_pid or not is_pid_alive(mapped_pid):
            inst["status"] = "stopped"
            inst["pid"] = None
            normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
            changed = True
        elif pid != mapped_pid:
            inst["status"] = "running"
            inst["pid"] = mapped_pid
            inst["started_at"] = now
            inst["error"] = None
            normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
            changed = True
        elif _refresh_started_at_from_pid(inst, pid):
            normalize_instance_metadata(inst, instance_id=instance_id, now=now)
            changed = True
        elif _touch_running_instance_daily(inst, now):
            normalize_instance_metadata(inst, instance_id=instance_id, now=now, touch=True)
            changed = True
    try:
        strategy_dir = _resolve_instance_strategy_dir(inst, resolve_strategy_dir)
        if inst.get("status") != "running":
            mapped_pid = _running_pid_for_instance(inst, running_pids, resolve_strategy_dir)
            if mapped_pid and is_pid_alive(mapped_pid):
                inst["status"] = "running"
                inst["pid"] = mapped_pid
                inst["started_at"] = now
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


def get_active_instances(
    instance_ids: list[str],
    user_id: str | None,
    load_instances: _Cb,
    scan_running_strategy_pids: _Cb,
    is_pid_alive: _Cb,
    resolve_strategy_dir: _Cb,
) -> list[dict[str, Any]]:
    """Return process-validated states for selected instances without log scans.

    Portfolio summaries only need to know whether the workspace units still
    have matching ``run.py`` processes. Reusing ``list_instances`` here would
    scan every persisted strategy directory for logs, even when the page only
    renders a subset of active workspace units. This read-only helper scans
    processes once and validates just the requested IDs.
    """
    requested_ids = [str(instance_id or "").strip() for instance_id in instance_ids]
    requested_ids = list(dict.fromkeys(instance_id for instance_id in requested_ids if instance_id))
    if not requested_ids:
        return []

    instances = load_instances()
    running_pids = scan_running_strategy_pids()
    now = instance_timestamp()
    result: list[dict[str, Any]] = []

    for instance_id in requested_ids:
        stored = instances.get(instance_id)
        if not isinstance(stored, dict):
            continue
        if user_id is not None and stored.get("user_id") != user_id:
            continue

        instance = dict(stored)
        instance["id"] = instance_id
        status = str(instance.get("status") or "stopped").strip().lower()
        mapped_pid = _running_pid_for_instance(instance, running_pids, resolve_strategy_dir)
        if mapped_pid and is_pid_alive(mapped_pid):
            instance["status"] = "running"
            instance["pid"] = mapped_pid
            if status != "running" or not instance.get("started_at"):
                instance["started_at"] = now
            result.append(instance)
            continue

        # The matching process is absent, so a persisted running record is
        # stale. Keep its stopped status in the return value so callers can
        # exclude it without mutating instance storage from a read request.
        instance["status"] = "stopped"
        instance["pid"] = None
        result.append(instance)

    return result
