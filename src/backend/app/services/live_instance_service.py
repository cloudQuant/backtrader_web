import logging
import uuid
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)


def sync_status_on_boot(load_instances, save_instances, is_pid_alive) -> None:
    instances = load_instances()
    changed = False
    for inst in instances.values():
        if inst.get("status") == "running":
            pid = inst.get("pid")
            if not pid or not is_pid_alive(pid):
                inst["status"] = "stopped"
                inst["pid"] = None
                changed = True
    if changed:
        save_instances(instances)


def list_instances(
    user_id: str | None,
    load_instances,
    save_instances,
    scan_running_strategy_pids,
    is_pid_alive,
    resolve_strategy_dir,
    find_latest_log_dir,
) -> list[dict[str, Any]]:
    instances = load_instances()
    changed = False
    running_pids = scan_running_strategy_pids()
    for instance_id, inst in instances.items():
        inst["id"] = instance_id
        if inst.get("status") == "running":
            pid = inst.get("pid")
            if not pid or not is_pid_alive(pid):
                inst["status"] = "stopped"
                inst["pid"] = None
                changed = True
        if inst.get("status") != "running":
            try:
                strategy_dir = resolve_strategy_dir(inst["strategy_id"])
                run_py_path = str(strategy_dir / "run.py")
                if run_py_path in running_pids:
                    inst["status"] = "running"
                    inst["pid"] = running_pids[run_py_path]
                    changed = True
            except ValueError as e:
                _logger.debug(f"Failed to resolve strategy dir for {inst.get('strategy_id')}: {e}")
    if changed:
        save_instances(instances)

    result = []
    for inst in instances.values():
        if user_id and inst.get("user_id") and inst["user_id"] != user_id:
            continue
        try:
            strategy_dir = resolve_strategy_dir(inst["strategy_id"])
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
    load_instances,
    save_instances,
    resolve_strategy_dir,
    get_template_by_id,
    infer_gateway_params,
    find_latest_log_dir,
) -> dict[str, Any]:
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        "started_at": None,
        "stopped_at": None,
        "log_dir": find_latest_log_dir(strategy_dir),
    }

    instances = load_instances()
    instances[instance_id] = inst
    save_instances(instances)
    return inst


def remove_instance(
    instance_id: str,
    user_id: str | None,
    load_instances,
    save_instances,
    kill_pid,
    release_gateway_for_instance,
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
    load_instances,
    save_instances,
    is_pid_alive,
    resolve_strategy_dir,
    find_latest_log_dir,
) -> dict[str, Any] | None:
    instances = load_instances()
    inst = instances.get(instance_id)
    if not inst:
        return None
    if user_id and inst.get("user_id") and inst["user_id"] != user_id:
        return None
    inst["id"] = instance_id
    if inst.get("status") == "running":
        pid = inst.get("pid")
        if not pid or not is_pid_alive(pid):
            inst["status"] = "stopped"
            inst["pid"] = None
            instances[instance_id] = inst
            save_instances(instances)
    try:
        strategy_dir = resolve_strategy_dir(inst["strategy_id"])
        inst["log_dir"] = find_latest_log_dir(strategy_dir)
    except ValueError:
        inst["log_dir"] = None
    return inst
