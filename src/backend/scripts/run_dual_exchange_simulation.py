#!/usr/bin/env python
"""Seed and run the CTP + MT5 simulated trading stress suite."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import signal
import sys
import time
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def _suppress_default_admin_warning_for_stress_script() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r"Insecure default admin password detected\..*",
        category=UserWarning,
    )


_suppress_default_admin_warning_for_stress_script()

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parents[1]
LOCAL_BACKTRADER_DIR = PROJECT_ROOT.parent / "backtrader"
LOCAL_BT_API_PY_DIR = PROJECT_ROOT.parent / "bt_api_py" / "bt_api_py"


def configure_local_source_paths(
    *,
    env: dict[str, str] | None = None,
    sys_path: list[str] | None = None,
    source_paths: list[Path] | None = None,
) -> None:
    target_env = os.environ if env is None else env
    target_sys_path = sys.path if sys_path is None else sys_path
    candidates = source_paths or [LOCAL_BACKTRADER_DIR, LOCAL_BT_API_PY_DIR]
    paths = [str(path) for path in candidates if path.is_dir()]
    if not paths:
        return

    seen: set[str] = set()
    existing = [item for item in target_env.get("PYTHONPATH", "").split(os.pathsep) if item]
    ordered = []
    for item in [*paths, *existing]:
        if item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    target_env["PYTHONPATH"] = os.pathsep.join(ordered)

    for item in reversed(paths):
        while item in target_sys_path:
            target_sys_path.remove(item)
        target_sys_path.insert(0, item)


configure_local_source_paths()
for path in (BACKEND_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.db.database import async_session_maker, ensure_database_ready  # noqa: E402
from app.models.workspace import StrategyUnit, Workspace  # noqa: E402
from app.services import workspace_unit_runtime  # noqa: E402
from app.services.workspace_service import WorkspaceService  # noqa: E402
from seed_simulated_workspaces import (  # noqa: E402
    STRESS_UNIT_PREFIXES,
    WORKSPACE_NAMES,
    build_workspace_specs,
    load_workspaces,
    seed_workspace,
)

TARGET_WORKSPACE_KEYS = ("futures", "mt5")
DEFAULT_STATUS_INTERVAL_SECONDS = 30
DEFAULT_HOLD_GRACE_SECONDS = 120
DEFAULT_STALE_HEARTBEAT_SECONDS = 180
DEFAULT_MAX_PROCESS_CPU_ALERT_PCT = 20.0
DEFAULT_TOTAL_MEMORY_ALERT_MB = 10240.0
DEFAULT_TOTAL_LOG_ALERT_MB = 1024.0
DEFAULT_TOTAL_TICK_LOG_ALERT_MB = 250.0
DEFAULT_ROLLING_BATCH_START_ATTEMPTS = 2
DEFAULT_ROLLING_BATCH_RETRY_WAIT_SECONDS = 30
TARGET_KEY_CHOICES = {"futures", "mt5"}
DATA_ACTIVITY_LOG_NAMES = ("bar.log", "value.log", "position.log")
_CTP_CFFEX_DAY_PREFIXES = {"IF", "IC", "IH", "IM", "T", "TF", "TS", "TL"}
_CTP_SYMBOL_RE = re.compile(r"^([A-Za-z]+)\d+$")


class ProcessResource:
    def __init__(
        self,
        pid: int,
        cpu_pct: float = 0.0,
        rss_mb: float = 0.0,
        pss_mb: float = 0.0,
        uss_mb: float = 0.0,
        started_at_epoch: float | None = None,
    ) -> None:
        self.pid = pid
        self.cpu_pct = cpu_pct
        self.rss_mb = rss_mb
        self.pss_mb = pss_mb
        self.uss_mb = uss_mb
        self.started_at_epoch = started_at_epoch


_PROCESS_CPU_SAMPLES: dict[int, tuple[float, float]] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed and start 50 CTP + 50 MT5 simulated trading units."
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Do not create/update strategy units before starting.",
    )
    parser.add_argument(
        "--no-stop-existing",
        action="store_true",
        help="Do not stop already-running target units before starting.",
    )
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=None,
        help="Keep this supervisor alive for N seconds after starting. Defaults to max session timeout.",
    )
    parser.add_argument(
        "--no-hold",
        action="store_true",
        help="Exit immediately after starting. Use only if another backend process owns the gateways.",
    )
    parser.add_argument(
        "--monitor-only",
        action="store_true",
        help="Only monitor existing target units; do not seed, stop, or start units.",
    )
    parser.add_argument(
        "--status-interval",
        type=int,
        default=DEFAULT_STATUS_INTERVAL_SECONDS,
        help="Seconds between status snapshots while holding.",
    )
    parser.add_argument(
        "--targets",
        default="futures,mt5",
        help="Comma-separated target workspace keys to run: futures,mt5.",
    )
    parser.add_argument(
        "--unit-ids",
        default="",
        help="Comma-separated strategy unit IDs to start/stop/monitor within the selected targets.",
    )
    parser.add_argument(
        "--no-monitor-after-hold",
        action="store_true",
        help=(
            "Stop status output after hold-seconds elapses. By default the supervisor "
            "keeps reporting while target units are still running."
        ),
    )
    parser.add_argument(
        "--rolling-restart",
        action="store_true",
        help="Restart selected target units in small batches and keep this supervisor attached.",
    )
    parser.add_argument(
        "--rolling-batch-size",
        type=int,
        default=1,
        help="Number of units to stop/start per rolling restart batch.",
    )
    parser.add_argument(
        "--rolling-batch-wait-seconds",
        type=int,
        default=45,
        help="Seconds to wait after each rolling restart batch before checking health.",
    )
    parser.add_argument(
        "--rolling-batch-start-attempts",
        type=int,
        default=DEFAULT_ROLLING_BATCH_START_ATTEMPTS,
        help="Number of run_units attempts for each rolling restart batch after one stop.",
    )
    parser.add_argument(
        "--rolling-batch-retry-wait-seconds",
        type=int,
        default=DEFAULT_ROLLING_BATCH_RETRY_WAIT_SECONDS,
        help="Seconds to wait before retrying failed rolling batch starts.",
    )
    parser.add_argument(
        "--skip-fresh-heartbeats",
        action="store_true",
        help="In rolling restart mode, skip units whose live heartbeat is already fresh.",
    )
    parser.add_argument(
        "--skip-fresh-data-logs",
        action="store_true",
        help=(
            "In rolling restart mode, skip units whose bar/value/position logs are "
            "fresh or in a known quiet trading window."
        ),
    )
    parser.add_argument(
        "--no-stop-owned-on-signal",
        action="store_true",
        help=(
            "Deprecated compatibility flag. Gateway-backed stress supervisors must stop "
            "owned units on SIGINT/SIGTERM to avoid leaving child strategies alive after "
            "their in-process gateway owner exits."
        ),
    )
    return parser.parse_args()


def parse_target_keys(value: str) -> tuple[str, ...]:
    keys = tuple(
        key.strip().lower()
        for key in str(value or "").split(",")
        if key.strip()
    )
    invalid = [key for key in keys if key not in TARGET_KEY_CHOICES]
    if invalid:
        raise ValueError(f"invalid target key(s): {', '.join(invalid)}")
    return keys or TARGET_WORKSPACE_KEYS


def parse_unit_ids(value: str) -> set[str]:
    return {
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    }


def target_specs_by_key() -> dict[str, list[dict[str, Any]]]:
    specs = build_workspace_specs()
    return {key: list(specs[key]) for key in TARGET_WORKSPACE_KEYS}


def target_names(specs: list[dict[str, Any]]) -> list[str]:
    return [str(spec["strategy_name"]) for spec in specs]


async def load_target_units(
    workspace: Workspace,
    specs: list[dict[str, Any]],
    unit_ids: set[str] | None = None,
) -> tuple[list[StrategyUnit], list[str]]:
    selected_unit_ids = {str(unit_id) for unit_id in (unit_ids or set()) if str(unit_id).strip()}
    if selected_unit_ids:
        async with async_session_maker() as session:
            result = await session.execute(
                select(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace.id,
                    StrategyUnit.id.in_(selected_unit_ids),
                )
            )
            units = list(result.scalars().all())

        found = {str(unit.id) for unit in units}
        missing = sorted(selected_unit_ids - found)
        return sorted(units, key=lambda unit: str(unit.strategy_name or "")), missing

    names = target_names(specs)
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit).where(
                StrategyUnit.workspace_id == workspace.id,
                StrategyUnit.strategy_name.in_(names),
            )
        )
        units = list(result.scalars().all())

    by_name = {str(unit.strategy_name): unit for unit in units}
    ordered = [by_name[name] for name in names if name in by_name]
    missing = [name for name in names if name not in by_name]
    return ordered, missing


async def seed_targets(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
) -> None:
    service = WorkspaceService()
    for key in TARGET_WORKSPACE_KEYS:
        workspace = workspaces[WORKSPACE_NAMES[key]]
        created, updated = await seed_workspace(service, workspace, specs_by_key[key])
        print_log(
            f"{WORKSPACE_NAMES[key]}: target={len(specs_by_key[key])}, "
            f"created={created}, updated={updated}"
        )


async def stop_targets(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    unit_ids: set[str] | None = None,
) -> dict[str, Counter[str]]:
    summaries: dict[str, Counter[str]] = {}
    for key in TARGET_WORKSPACE_KEYS:
        workspace = workspaces[WORKSPACE_NAMES[key]]
        units, _missing = await load_target_units(workspace, specs_by_key[key], unit_ids)
        if not units:
            summaries[key] = Counter({"missing": len(specs_by_key[key])})
            continue
        results = await WorkspaceService().stop_units(
            str(workspace.id),
            str(workspace.user_id),
            [str(unit.id) for unit in units],
        )
        counter = Counter("stopped" if item.get("cancelled") else "idle" for item in results)
        summaries[key] = counter
        print_log(
            f"{WORKSPACE_NAMES[key]}: stopped={counter.get('stopped', 0)}, "
            f"idle={counter.get('idle', 0)}"
        )
    return summaries


async def start_target_workspace(
    key: str,
    workspace: Workspace,
    specs: list[dict[str, Any]],
    unit_ids: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]], list[str], set[str]]:
    units, missing = await load_target_units(workspace, specs, unit_ids)
    if missing:
        return key, [{"status": "failed", "error": f"missing {len(missing)} target units"}], missing, set()
    results = await WorkspaceService().run_units(
        str(workspace.id),
        str(workspace.user_id),
        [str(unit.id) for unit in units],
        parallel=True,
    )
    owned_unit_ids = {
        str(item.get("unit_id"))
        for item in results
        if str(item.get("status") or "").lower() == "running"
        and not bool(item.get("already_running"))
        and str(item.get("unit_id") or "").strip()
    }
    return key, results, [], owned_unit_ids


async def start_targets(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    unit_ids: set[str] | None = None,
) -> tuple[dict[str, Counter[str]], dict[str, set[str]]]:
    tasks = []
    for key in TARGET_WORKSPACE_KEYS:
        tasks.append(
            start_target_workspace(
                key,
                workspaces[WORKSPACE_NAMES[key]],
                specs_by_key[key],
                unit_ids,
            )
        )

    summaries: dict[str, Counter[str]] = {}
    owned_unit_ids_by_key: dict[str, set[str]] = {}
    for key, results, missing, owned_unit_ids in await asyncio.gather(*tasks):
        counter = Counter(str(item.get("status") or "unknown") for item in results)
        if missing:
            counter["missing"] += len(missing)
        failed_examples = [
            str(item.get("error") or item.get("result") or "")
            for item in results
            if str(item.get("status") or "").lower() == "failed"
        ]
        summaries[key] = counter
        print_log(
            f"{WORKSPACE_NAMES[key]}: running={counter.get('running', 0)}, "
            f"failed={counter.get('failed', 0)}, missing={counter.get('missing', 0)}"
        )
        if failed_examples:
            print_log(f"{WORKSPACE_NAMES[key]} first error: {failed_examples[0][:500]}")
        owned_unit_ids_by_key[key] = owned_unit_ids
    return summaries, owned_unit_ids_by_key


def chunked_units(units: list[StrategyUnit], batch_size: int) -> list[list[StrategyUnit]]:
    size = max(int(batch_size or 1), 1)
    return [units[index : index + size] for index in range(0, len(units), size)]


def unit_heartbeat_state(
    unit: StrategyUnit,
    *,
    live_processes: dict[Path, list[int]],
    stale_heartbeat_seconds: int = DEFAULT_STALE_HEARTBEAT_SECONDS,
    now: float | None = None,
) -> str:
    run_path = unit_run_path(unit).resolve()
    pids = live_processes.get(run_path, [])
    if run_path not in live_processes:
        return "not_running"

    started_at_epochs: list[float] = []
    sample_time = time.monotonic()
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = None
    for pid in pids:
        resource = read_process_resource(
            pid,
            uptime_seconds=uptime_seconds,
            sample_time=sample_time,
        )
        if resource and resource.started_at_epoch is not None:
            started_at_epochs.append(resource.started_at_epoch)
    current_time = time.time() if now is None else now
    session_since = min(started_at_epochs) if started_at_epochs else current_time
    heartbeat_age = latest_log_age_seconds(
        unit_log_dir(unit),
        now=current_time,
        since_timestamp=session_since,
    )
    if heartbeat_age is None:
        return "missing"
    if heartbeat_age <= stale_heartbeat_seconds:
        return "fresh"
    return "stale"


def unit_data_log_state(
    unit: StrategyUnit,
    *,
    live_processes: dict[Path, list[int]],
    stale_heartbeat_seconds: int = DEFAULT_STALE_HEARTBEAT_SECONDS,
    now: float | None = None,
) -> str:
    run_path = unit_run_path(unit).resolve()
    pids = live_processes.get(run_path, [])
    if run_path not in live_processes:
        return "not_running"

    started_at_epochs: list[float] = []
    sample_time = time.monotonic()
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = None
    for pid in pids:
        resource = read_process_resource(
            pid,
            uptime_seconds=uptime_seconds,
            sample_time=sample_time,
        )
        if resource and resource.started_at_epoch is not None:
            started_at_epochs.append(resource.started_at_epoch)
    current_time = time.time() if now is None else now
    session_since = min(started_at_epochs) if started_at_epochs else current_time
    session_age = max(current_time - session_since, 0.0)
    if session_age < stale_heartbeat_seconds:
        return "warmup"

    data_log_age = latest_data_log_age_seconds(
        unit_log_dir(unit),
        now=current_time,
        since_timestamp=session_since,
    )
    if data_log_age is None:
        if is_ctp_data_quiet_time(unit_live_symbol(unit), current_time):
            return "quiet"
        return "missing"
    if data_log_age <= stale_heartbeat_seconds:
        return "fresh"
    if is_ctp_data_quiet_time(unit_live_symbol(unit), current_time):
        return "quiet"
    return "stale"


def filter_units_for_rolling_restart(
    units: list[StrategyUnit],
    *,
    skip_fresh_heartbeats: bool,
    skip_fresh_data_logs: bool = False,
    live_processes: dict[Path, list[int]] | None = None,
) -> list[StrategyUnit]:
    processes = running_unit_processes() if live_processes is None else live_processes
    selected = list(units)
    if skip_fresh_heartbeats:
        selected = [
            unit
            for unit in selected
            if unit_heartbeat_state(unit, live_processes=processes) != "fresh"
        ]
    if skip_fresh_data_logs:
        selected = [
            unit
            for unit in selected
            if unit_data_log_state(unit, live_processes=processes)
            not in {"fresh", "quiet", "warmup"}
        ]
    return selected



async def restart_target_batch(
    key: str,
    workspace: Workspace,
    units: list[StrategyUnit],
    *,
    start_attempts: int = 1,
    retry_wait_seconds: int = 0,
) -> tuple[Counter[str], set[str]]:
    unit_ids = [str(unit.id) for unit in units]
    stop_results = await WorkspaceService().stop_units(
        str(workspace.id),
        str(workspace.user_id),
        unit_ids,
    )
    stop_counter = Counter("stopped" if item.get("cancelled") else "idle" for item in stop_results)
    print_log(
        f"{WORKSPACE_NAMES[key]} rolling batch stop: "
        f"stopped={stop_counter.get('stopped', 0)}, idle={stop_counter.get('idle', 0)}"
    )
    attempts = max(int(start_attempts or 1), 1)
    retry_wait = max(int(retry_wait_seconds or 0), 0)
    pending_units = list(units)
    final_results: dict[str, dict[str, Any]] = {}
    owned_unit_ids: set[str] = set()
    for attempt in range(1, attempts + 1):
        pending_ids = [str(unit.id) for unit in pending_units]
        results = await WorkspaceService().run_units(
            str(workspace.id),
            str(workspace.user_id),
            pending_ids,
            parallel=True,
        )
        for item in results:
            unit_id = str(item.get("unit_id") or "").strip()
            if unit_id:
                final_results[unit_id] = item
        counter = Counter(str(item.get("status") or "unknown") for item in results)
        failed_examples = [
            str(item.get("error") or item.get("result") or "")
            for item in results
            if str(item.get("status") or "").lower() == "failed"
        ]
        attempt_label = (
            f" attempt {attempt}/{attempts}" if attempts > 1 else ""
        )
        print_log(
            f"{WORKSPACE_NAMES[key]} rolling batch start{attempt_label}: "
            f"running={counter.get('running', 0)}, failed={counter.get('failed', 0)}"
        )
        if failed_examples:
            print_log(
                f"{WORKSPACE_NAMES[key]} rolling batch first error: "
                f"{failed_examples[0][:500]}"
            )
        running_ids = {
            str(item.get("unit_id"))
            for item in results
            if str(item.get("status") or "").lower() == "running"
            and str(item.get("unit_id") or "").strip()
        }
        owned_unit_ids.update(
            str(item.get("unit_id"))
            for item in results
            if str(item.get("status") or "").lower() == "running"
            and not bool(item.get("already_running"))
            and str(item.get("unit_id") or "").strip()
        )
        pending_units = [unit for unit in pending_units if str(unit.id) not in running_ids]
        if not pending_units or attempt >= attempts:
            break
        print_log(
            f"{WORKSPACE_NAMES[key]} rolling batch retrying "
            f"{len(pending_units)} failed unit(s) after {retry_wait}s"
        )
        if retry_wait > 0:
            await asyncio.sleep(retry_wait)

    final_items = [
        final_results.get(str(unit.id), {"status": "unknown"})
        for unit in units
    ]
    return Counter(str(item.get("status") or "unknown") for item in final_items), owned_unit_ids


async def rolling_restart_targets(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    unit_ids: set[str] | None = None,
    *,
    batch_size: int = 1,
    batch_wait_seconds: int = 45,
    batch_start_attempts: int = DEFAULT_ROLLING_BATCH_START_ATTEMPTS,
    batch_retry_wait_seconds: int = DEFAULT_ROLLING_BATCH_RETRY_WAIT_SECONDS,
    skip_fresh_heartbeats: bool = False,
    skip_fresh_data_logs: bool = False,
) -> tuple[dict[str, Counter[str]], dict[str, set[str]]]:
    summaries: dict[str, Counter[str]] = {}
    owned_unit_ids_by_key: dict[str, set[str]] = {}
    live_processes = running_unit_processes()
    for key in TARGET_WORKSPACE_KEYS:
        workspace = workspaces[WORKSPACE_NAMES[key]]
        units, missing = await load_target_units(workspace, specs_by_key[key], unit_ids)
        selected_units = filter_units_for_rolling_restart(
            units,
            skip_fresh_heartbeats=skip_fresh_heartbeats,
            skip_fresh_data_logs=skip_fresh_data_logs,
            live_processes=live_processes,
        )
        key_counter: Counter[str] = Counter()
        if missing:
            key_counter["missing"] += len(missing)
        if not selected_units:
            summaries[key] = key_counter
            owned_unit_ids_by_key[key] = set()
            print_log(f"{WORKSPACE_NAMES[key]} rolling restart: no units selected")
            continue

        key_owned: set[str] = set()
        batches = chunked_units(selected_units, batch_size)
        for index, batch in enumerate(batches, start=1):
            names = ", ".join(str(unit.strategy_name or unit.id) for unit in batch)
            print_log(
                f"{WORKSPACE_NAMES[key]} rolling batch {index}/{len(batches)}: {names[:500]}"
            )
            batch_counter, batch_owned = await restart_target_batch(
                key,
                workspace,
                batch,
                start_attempts=batch_start_attempts,
                retry_wait_seconds=batch_retry_wait_seconds,
            )
            key_counter.update(batch_counter)
            key_owned.update(batch_owned)
            if batch_wait_seconds > 0:
                await asyncio.sleep(batch_wait_seconds)
            batch_ids = {str(unit.id) for unit in batch}
            batch_summary = await status_summary(
                {WORKSPACE_NAMES[key]: workspace},
                {key: specs_by_key[key]},
                batch_ids,
                target_keys=(key,),
            )
            print_status(
                f"rolling batch {index} check",
                batch_summary,
                target_keys=(key,),
            )
        summaries[key] = key_counter
        owned_unit_ids_by_key[key] = key_owned
    return summaries, owned_unit_ids_by_key


async def stop_owned_targets(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    unit_ids_by_key: dict[str, set[str]],
    *,
    owner_pid: int | None = None,
    live_processes: dict[Path, list[int]] | None = None,
) -> dict[str, Counter[str]]:
    summaries: dict[str, Counter[str]] = {}
    current_owner_pid = os.getpid() if owner_pid is None else owner_pid
    current_live_processes = running_unit_processes() if live_processes is None else live_processes
    for key in TARGET_WORKSPACE_KEYS:
        owned_unit_ids = {str(unit_id) for unit_id in unit_ids_by_key.get(key, set()) if str(unit_id)}
        if not owned_unit_ids:
            continue
        workspace = workspaces[WORKSPACE_NAMES[key]]
        units, _missing = await load_target_units(workspace, specs_by_key[key], owned_unit_ids)
        if not units:
            continue
        units = [
            unit
            for unit in units
            if unit_has_process_owned_by_pid(unit, current_live_processes, current_owner_pid)
        ]
        if not units:
            print_log(f"{WORKSPACE_NAMES[key]} owned stop skipped: no current owned processes")
            continue
        results = await WorkspaceService().stop_units(
            str(workspace.id),
            str(workspace.user_id),
            [str(unit.id) for unit in units],
        )
        counter = Counter("stopped" if item.get("cancelled") else "idle" for item in results)
        summaries[key] = counter
        print_log(
            f"{WORKSPACE_NAMES[key]} owned stop: stopped={counter.get('stopped', 0)}, "
            f"idle={counter.get('idle', 0)}"
        )
    return summaries


async def handle_stop_signal(
    stop_event: asyncio.Event,
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    owned_unit_ids_by_key: dict[str, set[str]],
    *,
    stop_owned_on_signal: bool = True,
) -> None:
    if not stop_event.is_set():
        return
    if not stop_owned_on_signal:
        print_log(
            "stop signal received; --no-stop-owned-on-signal is ignored for "
            "gateway-backed stress units; stopping owned target units"
        )
    else:
        print_log("stop signal received; stopping target units")
    await stop_owned_targets(workspaces, specs_by_key, owned_unit_ids_by_key)


async def status_summary(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    unit_ids: set[str] | None = None,
    target_keys: tuple[str, ...] | None = None,
) -> dict[str, Counter[str]]:
    summaries: dict[str, Counter[str]] = {}
    service = WorkspaceService()
    live_processes = running_unit_processes()
    for key in (target_keys or TARGET_WORKSPACE_KEYS):
        workspace = workspaces[WORKSPACE_NAMES[key]]
        units, missing = await load_target_units(workspace, specs_by_key[key], unit_ids)
        target_ids = {str(unit.id) for unit in units}
        statuses = await service.get_units_status(str(workspace.id), str(workspace.user_id))
        counter: Counter[str] = Counter()
        for item in statuses or []:
            if str(item.id) in target_ids:
                counter[str(item.run_status or "unknown")] += 1
        if missing:
            counter["missing"] += len(missing)
        counter.update(runtime_health_counter(units, live_processes=live_processes))
        summaries[key] = counter
    return summaries


def status_timestamp(now: datetime | None = None) -> str:
    current = now if now is not None else datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    return current.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def print_log(
    message: str,
    *,
    now: datetime | None = None,
    file: Any | None = None,
) -> None:
    if file is None:
        file = sys.stdout
    print(f"{status_timestamp(now)} {message}", file=file, flush=True)


def print_status(
    prefix: str,
    summaries: dict[str, Counter[str]],
    *,
    now: datetime | None = None,
    target_keys: tuple[str, ...] | None = None,
) -> None:
    parts = []
    for key in (target_keys or TARGET_WORKSPACE_KEYS):
        counter = summaries.get(key, Counter())
        alerts = resource_alerts(counter)
        parts.append(
            f"{WORKSPACE_NAMES[key]} running={counter.get('running', 0)} "
            f"failed={counter.get('failed', 0)} idle={counter.get('idle', 0)} "
            f"missing={counter.get('missing', 0)} "
            f"process={counter.get('process_alive', 0)} "
            f"heartbeat={counter.get('heartbeat_fresh', 0)} "
            f"stale={counter.get('heartbeat_stale', 0)} "
            f"no_log={counter.get('heartbeat_missing', 0)} "
            f"data_log={counter.get('data_log_fresh', 0)} "
            f"data_stale={counter.get('data_log_stale', 0)} "
            f"data_missing={counter.get('data_log_missing', 0)} "
            f"data_quiet={counter.get('data_log_quiet', 0)} "
            f"alerts={','.join(alerts) if alerts else '-'} "
            f"cpu={float(counter.get('cpu_pct_total', 0.0)):.1f}% "
            f"max_cpu={float(counter.get('cpu_pct_max', 0.0)):.1f}% "
            f"rss={float(counter.get('rss_mb_total', 0.0)):.1f}MB "
            f"pss={float(counter.get('pss_mb_total', 0.0)):.1f}MB "
            f"uss={float(counter.get('uss_mb_total', 0.0)):.1f}MB "
            f"log={float(counter.get('log_mb_total', 0.0)):.1f}MB "
            f"log_disk={float(counter.get('log_disk_mb_total', 0.0)):.1f}MB "
            f"tick={float(counter.get('tick_log_mb_total', 0.0)):.1f}MB "
            f"tick_max={float(counter.get('tick_log_mb_max', 0.0)):.1f}MB "
            f"tick_disk={float(counter.get('tick_log_disk_mb_total', 0.0)):.1f}MB "
            f"tick_disk_max={float(counter.get('tick_log_disk_mb_max', 0.0)):.1f}MB"
        )
    print(f"{status_timestamp(now)} {prefix}: " + " | ".join(parts), flush=True)


def resource_alerts(counter: Counter[str]) -> list[str]:
    alerts: list[str] = []
    if counter.get("running", 0) > counter.get("process_alive", 0):
        alerts.append("process_missing")
    if counter.get("process_alive", 0) > counter.get("running", 0):
        alerts.append("process_orphaned")
    if counter.get("failed", 0) > 0:
        alerts.append("unit_failed")
    if counter.get("idle", 0) > 0:
        alerts.append("unit_idle")
    if counter.get("missing", 0) > 0:
        alerts.append("unit_missing")
    if counter.get("heartbeat_stale", 0) > 0:
        alerts.append("heartbeat_stale")
    if counter.get("heartbeat_missing", 0) > 0:
        alerts.append("heartbeat_missing")
    if counter.get("data_log_stale", 0) > 0:
        alerts.append("data_log_stale")
    if counter.get("data_log_missing", 0) > 0:
        alerts.append("data_log_missing")
    if float(counter.get("cpu_pct_max", 0.0)) >= DEFAULT_MAX_PROCESS_CPU_ALERT_PCT:
        alerts.append("cpu_high")
    pss_total = float(counter.get("pss_mb_total", 0.0))
    rss_total = float(counter.get("rss_mb_total", 0.0))
    if pss_total > 0:
        if pss_total >= DEFAULT_TOTAL_MEMORY_ALERT_MB:
            alerts.append("pss_high")
    elif rss_total >= DEFAULT_TOTAL_MEMORY_ALERT_MB:
        alerts.append("rss_high")
    if float(counter.get("log_mb_total", 0.0)) >= DEFAULT_TOTAL_LOG_ALERT_MB:
        alerts.append("log_high")
    if float(counter.get("tick_log_mb_total", 0.0)) >= DEFAULT_TOTAL_TICK_LOG_ALERT_MB:
        alerts.append("tick_log_high")
    if float(counter.get("log_disk_mb_total", 0.0)) >= DEFAULT_TOTAL_LOG_ALERT_MB:
        alerts.append("log_disk_high")
    if float(counter.get("tick_log_disk_mb_total", 0.0)) >= DEFAULT_TOTAL_TICK_LOG_ALERT_MB:
        alerts.append("tick_log_disk_high")
    return alerts


def any_targets_running(summaries: dict[str, Counter[str]]) -> bool:
    return any(
        counter.get("running", 0) > 0 or counter.get("process_alive", 0) > 0
        for counter in summaries.values()
    )


def unit_run_path(unit: StrategyUnit) -> Path:
    return workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id)) / "run.py"


def unit_log_dir(unit: StrategyUnit) -> Path:
    return workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id)) / "logs"


def unit_live_symbol(unit: StrategyUnit) -> str:
    if not hasattr(unit, "workspace_id") or not hasattr(unit, "id"):
        return ""
    config_path = workspace_unit_runtime.unit_dir(str(unit.workspace_id), str(unit.id)) / "config.yaml"
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    in_live = False
    for line in lines:
        stripped = line.strip()
        if not line.startswith(" ") and stripped.endswith(":"):
            in_live = stripped == "live:"
            continue
        if in_live and stripped.startswith("symbol:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return ""


def ctp_product_prefix(symbol: str) -> str:
    match = _CTP_SYMBOL_RE.match(str(symbol or "").strip())
    return match.group(1).upper() if match else ""


def is_ctp_data_quiet_time(symbol: str, now: float | None = None) -> bool:
    prefix = ctp_product_prefix(symbol)
    if not prefix:
        return False
    current = datetime.fromtimestamp(time.time() if now is None else now).astimezone()
    minute_of_day = current.hour * 60 + current.minute
    if prefix in _CTP_CFFEX_DAY_PREFIXES:
        return (
            minute_of_day < 9 * 60 + 30
            or 11 * 60 + 30 <= minute_of_day < 13 * 60
            or minute_of_day >= 15 * 60
        )
    return (
        minute_of_day < 9 * 60
        or 10 * 60 + 15 <= minute_of_day < 10 * 60 + 30
        or 11 * 60 + 30 <= minute_of_day < 13 * 60 + 30
        or 15 * 60 <= minute_of_day < 21 * 60
    )


def process_parent_pid(pid: int) -> int | None:
    try:
        for line in (Path("/proc") / str(pid) / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("PPid:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def unit_has_process_owned_by_pid(
    unit: StrategyUnit,
    live_processes: dict[Path, list[int]],
    owner_pid: int,
) -> bool:
    run_path = unit_run_path(unit).resolve()
    return any(process_parent_pid(pid) == owner_pid for pid in live_processes.get(run_path, []))


def running_unit_processes() -> dict[Path, list[int]]:
    proc_dir = Path("/proc")
    if not proc_dir.exists():
        return {}

    processes: dict[Path, list[int]] = {}
    for pid_dir in proc_dir.iterdir():
        if not pid_dir.name.isdigit():
            continue
        try:
            raw_cmdline = (pid_dir / "cmdline").read_bytes()
        except OSError:
            continue
        if b"workspace_units" not in raw_cmdline or b"run.py" not in raw_cmdline:
            continue
        for part in raw_cmdline.split(b"\0"):
            try:
                text = part.decode()
            except UnicodeDecodeError:
                continue
            if text.endswith("/run.py") and "workspace_units" in text:
                processes.setdefault(Path(text).resolve(), []).append(int(pid_dir.name))
    return processes


def running_unit_run_paths() -> set[Path]:
    return set(running_unit_processes())


def read_process_memory_rollup(proc_dir: Path) -> tuple[float, float]:
    """Return PSS and USS in MB from Linux smaps_rollup when available."""
    try:
        text = (proc_dir / "smaps_rollup").read_text(encoding="utf-8")
    except OSError:
        return 0.0, 0.0

    values_kb: dict[str, float] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            values_kb[key] = float(parts[0])
        except ValueError:
            continue

    pss_mb = values_kb.get("Pss", 0.0) / 1024.0
    uss_mb = (
        values_kb.get("Private_Clean", 0.0)
        + values_kb.get("Private_Dirty", 0.0)
        + values_kb.get("Private_Hugetlb", 0.0)
    ) / 1024.0
    return max(pss_mb, 0.0), max(uss_mb, 0.0)


def process_cpu_pct(
    pid: int,
    total_cpu_seconds: float,
    elapsed_seconds: float,
    *,
    sample_time: float | None = None,
    cpu_samples: dict[int, tuple[float, float]] | None = None,
) -> float:
    samples = _PROCESS_CPU_SAMPLES if cpu_samples is None else cpu_samples
    current_sample_time = time.monotonic() if sample_time is None else sample_time
    previous = samples.get(pid)
    samples[pid] = (current_sample_time, total_cpu_seconds)
    if previous is not None:
        previous_sample_time, previous_cpu_seconds = previous
        delta_time = current_sample_time - previous_sample_time
        delta_cpu = total_cpu_seconds - previous_cpu_seconds
        if delta_time > 0 and delta_cpu >= 0:
            return max(delta_cpu / delta_time * 100.0, 0.0)
    return max(total_cpu_seconds / max(elapsed_seconds, 0.001) * 100.0, 0.0)


def prune_process_cpu_samples(active_pids: set[int]) -> None:
    for pid in list(_PROCESS_CPU_SAMPLES):
        if pid not in active_pids:
            _PROCESS_CPU_SAMPLES.pop(pid, None)


def read_process_resource(
    pid: int,
    uptime_seconds: float | None = None,
    *,
    sample_time: float | None = None,
) -> ProcessResource | None:
    proc_dir = Path("/proc") / str(pid)
    try:
        stat_text = (proc_dir / "stat").read_text(encoding="utf-8")
        statm_fields = (proc_dir / "statm").read_text(encoding="utf-8").split()
    except OSError:
        return None

    try:
        fields = stat_text.rsplit(") ", 1)[1].split()
        clock_ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        page_size = os.sysconf(os.sysconf_names["SC_PAGE_SIZE"])
        process_seconds = (float(fields[11]) + float(fields[12])) / float(clock_ticks)
        started_seconds = float(fields[19]) / float(clock_ticks)
        uptime = uptime_seconds if uptime_seconds is not None else float(
            Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
        )
        elapsed_seconds = max(uptime - started_seconds, 0.001)
        rss_mb = float(statm_fields[1]) * float(page_size) / 1024.0 / 1024.0
        pss_mb, uss_mb = read_process_memory_rollup(proc_dir)
        boot_time_epoch = time.time() - uptime
        started_at_epoch = boot_time_epoch + started_seconds
    except (IndexError, KeyError, OSError, TypeError, ValueError, ZeroDivisionError):
        return None

    return ProcessResource(
        pid=pid,
        cpu_pct=process_cpu_pct(
            pid,
            process_seconds,
            elapsed_seconds,
            sample_time=sample_time,
        ),
        rss_mb=max(rss_mb, 0.0),
        pss_mb=max(pss_mb, 0.0),
        uss_mb=max(uss_mb, 0.0),
        started_at_epoch=started_at_epoch,
    )


def log_bytes(
    log_dir: Path,
    pattern: str = "*.log",
    *,
    since_timestamp: float | None = None,
) -> int:
    try:
        paths = list(log_dir.glob(pattern))
    except OSError:
        return 0

    total = 0
    for path in paths:
        try:
            stat = path.stat()
            if since_timestamp is not None and stat.st_mtime < since_timestamp:
                continue
            if path.is_file():
                total += stat.st_size
        except OSError:
            continue
    return total


def latest_log_age_seconds(
    log_dir: Path,
    now: float | None = None,
    *,
    since_timestamp: float | None = None,
) -> float | None:
    try:
        files = []
        for path in log_dir.iterdir():
            if not path.is_file():
                continue
            stat = path.stat()
            if since_timestamp is not None and stat.st_mtime < since_timestamp:
                continue
            files.append((path, stat))
    except OSError:
        return None
    if not files:
        return None

    latest_mtime = max(stat.st_mtime for _path, stat in files)
    return max((time.time() if now is None else now) - latest_mtime, 0.0)


def latest_data_log_age_seconds(
    log_dir: Path,
    now: float | None = None,
    *,
    since_timestamp: float | None = None,
) -> float | None:
    try:
        stats = []
        for name in DATA_ACTIVITY_LOG_NAMES:
            path = log_dir / name
            if not path.is_file():
                continue
            stat = path.stat()
            if stat.st_size <= 0:
                continue
            if since_timestamp is not None and stat.st_mtime < since_timestamp:
                continue
            stats.append(stat)
    except OSError:
        return None
    if not stats:
        return None

    latest_mtime = max(stat.st_mtime for stat in stats)
    return max((time.time() if now is None else now) - latest_mtime, 0.0)


def runtime_health_counter(
    units: list[StrategyUnit],
    *,
    live_run_paths: set[Path] | None = None,
    live_processes: dict[Path, list[int]] | None = None,
    stale_heartbeat_seconds: int = DEFAULT_STALE_HEARTBEAT_SECONDS,
) -> Counter[str]:
    if live_processes is None:
        if live_run_paths is not None:
            live_processes = {path: [] for path in live_run_paths}
        else:
            live_processes = running_unit_processes()
    now = time.time()
    sample_time = time.monotonic()
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = None
    counter: Counter[str] = Counter()
    active_pids: set[int] = set()
    cpu_total = 0.0
    cpu_max = 0.0
    rss_total = 0.0
    rss_max = 0.0
    pss_total = 0.0
    pss_max = 0.0
    uss_total = 0.0
    uss_max = 0.0
    log_total_bytes = 0
    tick_total_bytes = 0
    tick_max_bytes = 0
    log_disk_total_bytes = 0
    tick_disk_total_bytes = 0
    tick_disk_max_bytes = 0
    for unit in units:
        run_path = unit_run_path(unit).resolve()
        pids = live_processes.get(run_path, [])
        process_alive = run_path in live_processes
        if process_alive:
            counter["process_alive"] += 1

        started_at_epochs: list[float] = []
        for pid in pids:
            active_pids.add(pid)
            resource = read_process_resource(
                pid,
                uptime_seconds=uptime_seconds,
                sample_time=sample_time,
            )
            if resource is None:
                continue
            cpu_total += resource.cpu_pct
            cpu_max = max(cpu_max, resource.cpu_pct)
            rss_total += resource.rss_mb
            rss_max = max(rss_max, resource.rss_mb)
            pss_total += resource.pss_mb
            pss_max = max(pss_max, resource.pss_mb)
            uss_total += resource.uss_mb
            uss_max = max(uss_max, resource.uss_mb)
            if resource.started_at_epoch is not None:
                started_at_epochs.append(resource.started_at_epoch)

        log_dir = unit_log_dir(unit)
        session_since = None
        if process_alive:
            session_since = min(started_at_epochs) if started_at_epochs else now
        unit_log_bytes = 0
        unit_tick_bytes = 0
        if process_alive:
            unit_log_bytes = log_bytes(log_dir, since_timestamp=session_since)
            unit_tick_bytes = log_bytes(log_dir, "tick.log", since_timestamp=session_since)
        unit_log_disk_bytes = log_bytes(log_dir)
        unit_tick_disk_bytes = log_bytes(log_dir, "tick.log")
        log_total_bytes += unit_log_bytes
        tick_total_bytes += unit_tick_bytes
        tick_max_bytes = max(tick_max_bytes, unit_tick_bytes)
        log_disk_total_bytes += unit_log_disk_bytes
        tick_disk_total_bytes += unit_tick_disk_bytes
        tick_disk_max_bytes = max(tick_disk_max_bytes, unit_tick_disk_bytes)

        if process_alive:
            heartbeat_age = latest_log_age_seconds(
                log_dir,
                now=now,
                since_timestamp=session_since,
            )
            if heartbeat_age is None:
                counter["heartbeat_missing"] += 1
            elif heartbeat_age <= stale_heartbeat_seconds:
                counter["heartbeat_fresh"] += 1
            else:
                counter["heartbeat_stale"] += 1

            session_age = max(now - session_since, 0.0)
            if session_age < stale_heartbeat_seconds:
                counter["data_log_warmup"] += 1
            else:
                data_log_age = latest_data_log_age_seconds(
                    log_dir,
                    now=now,
                    since_timestamp=session_since,
                )
                if data_log_age is None:
                    if is_ctp_data_quiet_time(unit_live_symbol(unit), now):
                        counter["data_log_quiet"] += 1
                    else:
                        counter["data_log_missing"] += 1
                elif data_log_age <= stale_heartbeat_seconds:
                    counter["data_log_fresh"] += 1
                else:
                    if is_ctp_data_quiet_time(unit_live_symbol(unit), now):
                        counter["data_log_quiet"] += 1
                    else:
                        counter["data_log_stale"] += 1
    counter["cpu_pct_total"] = round(cpu_total, 1)
    counter["cpu_pct_max"] = round(cpu_max, 1)
    counter["rss_mb_total"] = round(rss_total, 1)
    counter["rss_mb_max"] = round(rss_max, 1)
    counter["pss_mb_total"] = round(pss_total, 1)
    counter["pss_mb_max"] = round(pss_max, 1)
    counter["uss_mb_total"] = round(uss_total, 1)
    counter["uss_mb_max"] = round(uss_max, 1)
    counter["log_mb_total"] = round(log_total_bytes / 1024.0 / 1024.0, 1)
    counter["tick_log_mb_total"] = round(tick_total_bytes / 1024.0 / 1024.0, 1)
    counter["tick_log_mb_max"] = round(tick_max_bytes / 1024.0 / 1024.0, 1)
    counter["log_disk_mb_total"] = round(log_disk_total_bytes / 1024.0 / 1024.0, 1)
    counter["tick_log_disk_mb_total"] = round(tick_disk_total_bytes / 1024.0 / 1024.0, 1)
    counter["tick_log_disk_mb_max"] = round(tick_disk_max_bytes / 1024.0 / 1024.0, 1)
    prune_process_cpu_samples(active_pids)
    return counter


def default_hold_seconds(specs_by_key: dict[str, list[dict[str, Any]]]) -> int:
    max_timeout = 0
    for specs in specs_by_key.values():
        for spec in specs:
            unit_settings = spec.get("unit_settings") if isinstance(spec, dict) else None
            if not isinstance(unit_settings, dict):
                continue
            try:
                timeout = int(unit_settings.get("session_timeout") or 0)
            except (TypeError, ValueError):
                timeout = 0
            max_timeout = max(max_timeout, timeout)
    return max_timeout + DEFAULT_HOLD_GRACE_SECONDS if max_timeout > 0 else 0


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda _signum, _frame: stop_event.set())


def has_owned_started_units(unit_ids_by_key: dict[str, set[str]]) -> bool:
    return any(unit_ids for unit_ids in unit_ids_by_key.values())


async def hold_monitor(
    workspaces: dict[str, Workspace],
    specs_by_key: dict[str, list[dict[str, Any]]],
    *,
    hold_seconds: int,
    status_interval: int,
    stop_event: asyncio.Event,
    unit_ids: set[str] | None = None,
    monitor_after_hold: bool = True,
) -> None:
    if hold_seconds <= 0:
        return

    deadline = time.monotonic() + hold_seconds
    last_summaries: dict[str, Counter[str]] = {}
    while time.monotonic() < deadline and not stop_event.is_set():
        remaining = max(deadline - time.monotonic(), 0.0)
        sleep_for = min(max(status_interval, 5), remaining)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_for)
        except asyncio.TimeoutError:
            pass
        last_summaries = await status_summary(workspaces, specs_by_key, unit_ids)
        print_status("status", last_summaries)
        if not any_targets_running(last_summaries):
            return

    if stop_event.is_set():
        return

    if not last_summaries:
        last_summaries = await status_summary(workspaces, specs_by_key, unit_ids)
        print_status("hold elapsed", last_summaries)

    if not monitor_after_hold or not any_targets_running(last_summaries):
        return

    print_log("hold elapsed; target units still running, continuing status monitor")
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(status_interval, 5))
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            return
        summaries = await status_summary(workspaces, specs_by_key, unit_ids)
        print_status("status", summaries)
        if not any_targets_running(summaries):
            return


async def main() -> int:
    global TARGET_WORKSPACE_KEYS

    args = parse_args()
    try:
        TARGET_WORKSPACE_KEYS = parse_target_keys(args.targets)
    except ValueError as exc:
        print_log(str(exc), file=sys.stderr)
        return 2
    target_unit_ids = parse_unit_ids(args.unit_ids)

    await ensure_database_ready()

    specs_by_key = target_specs_by_key()
    for key, prefix in STRESS_UNIT_PREFIXES.items():
        if key in TARGET_WORKSPACE_KEYS:
            print_log(f"{WORKSPACE_NAMES[key]} target prefix: {prefix}")

    workspaces = await load_workspaces()

    if args.monitor_only:
        monitor_summaries = await status_summary(workspaces, specs_by_key, target_unit_ids)
        print_status("monitor", monitor_summaries)
        if args.no_hold:
            return 0

        hold_seconds = (
            int(args.hold_seconds)
            if args.hold_seconds is not None
            else default_hold_seconds(specs_by_key)
        )
        if hold_seconds <= 0:
            hold_seconds = DEFAULT_STATUS_INTERVAL_SECONDS

        stop_event = asyncio.Event()
        install_signal_handlers(stop_event)
        print_log(f"monitor holding for {hold_seconds}s")
        await hold_monitor(
            workspaces,
            specs_by_key,
            hold_seconds=hold_seconds,
            status_interval=int(args.status_interval),
            stop_event=stop_event,
            unit_ids=target_unit_ids,
            monitor_after_hold=not args.no_monitor_after_hold,
        )
        return 0

    if not args.skip_seed:
        await seed_targets(workspaces, specs_by_key)
        workspaces = await load_workspaces()

    if args.rolling_restart:
        _start_summaries, owned_unit_ids_by_key = await rolling_restart_targets(
            workspaces,
            specs_by_key,
            target_unit_ids,
            batch_size=int(args.rolling_batch_size),
            batch_wait_seconds=int(args.rolling_batch_wait_seconds),
            batch_start_attempts=int(args.rolling_batch_start_attempts),
            batch_retry_wait_seconds=int(args.rolling_batch_retry_wait_seconds),
            skip_fresh_heartbeats=bool(args.skip_fresh_heartbeats),
            skip_fresh_data_logs=bool(args.skip_fresh_data_logs),
        )
        status_summaries = await status_summary(workspaces, specs_by_key, target_unit_ids)
        print_status("rolling restarted", status_summaries)
    else:
        if not args.no_stop_existing:
            await stop_targets(workspaces, specs_by_key, target_unit_ids)

        _start_summaries, owned_unit_ids_by_key = await start_targets(
            workspaces, specs_by_key, target_unit_ids
        )
        status_summaries = await status_summary(workspaces, specs_by_key, target_unit_ids)
        print_status("started", status_summaries)

    if args.rolling_restart and not has_owned_started_units(owned_unit_ids_by_key):
        return 0
    if args.rolling_restart and args.no_hold:
        print_log("--rolling-restart requires hold mode; ignoring --no-hold")
        args.no_hold = False

    if args.no_hold and not has_owned_started_units(owned_unit_ids_by_key):
        return 0
    if args.no_hold:
        print_log(
            "--no-hold requested but this process started target units; "
            "continuing to hold so subprocess watchers stay attached"
        )

    hold_seconds = (
        int(args.hold_seconds)
        if args.hold_seconds is not None
        else default_hold_seconds(specs_by_key)
    )
    if hold_seconds <= 0:
        return 0

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)
    print_log(f"supervisor holding for {hold_seconds}s")
    try:
        await hold_monitor(
            workspaces,
            specs_by_key,
            hold_seconds=hold_seconds,
            status_interval=int(args.status_interval),
            stop_event=stop_event,
            unit_ids=target_unit_ids,
            monitor_after_hold=not args.no_monitor_after_hold,
        )
    finally:
        await handle_stop_signal(
            stop_event,
            workspaces,
            specs_by_key,
            owned_unit_ids_by_key,
            stop_owned_on_signal=not args.no_stop_owned_on_signal,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
