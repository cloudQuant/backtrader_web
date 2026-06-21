#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"
WORKSPACE_ROOT = PROJECT_ROOT.parent
BT_API_PY_DIR = WORKSPACE_ROOT / "bt_api_py"
BT_API_BASE_SRC_DIR = BT_API_PY_DIR / "bt_api" / "bt_api_base" / "src"
BT_API_CTP_SRC_DIR = BT_API_PY_DIR / "bt_api" / "bt_api_ctp" / "src"


def _prepend_python_paths(paths: list[Path]) -> None:
    valid_paths = [str(path) for path in paths if path.is_dir()]
    for path in reversed(valid_paths):
        if path not in sys.path:
            sys.path.insert(0, path)
    existing = [part for part in os.environ.get("PYTHONPATH", "").split(os.pathsep) if part]
    merged = valid_paths + [part for part in existing if part not in valid_paths]
    if merged:
        os.environ["PYTHONPATH"] = os.pathsep.join(merged)


_prepend_python_paths([BACKEND_DIR, BT_API_PY_DIR, BT_API_BASE_SRC_DIR, BT_API_CTP_SRC_DIR])

from app.services.live_trading_manager import LiveTradingManager
from app.services.gateway import launch_builder as gateway_launch_builder
from app.services.strategy import runtime_support as strategy_runtime_support
from app.services.strategy_service import get_strategy_dir

_SMOKE_RUNTIME_SCRIPT = """\
from __future__ import annotations

import signal
import time

running = True


def _stop(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)

print("ctp gateway smoke runtime ready", flush=True)
while running:
    time.sleep(0.2)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-id", default="simulate/p_bb_rsi")
    parser.add_argument("--wait-seconds", type=float, default=5.0)
    parser.add_argument("--settle-seconds", type=float, default=0.5)
    parser.add_argument("--report-file", default="/tmp/ctp_gateway_smoke_report.json")
    parser.add_argument("--worker-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--worker-grace-seconds", type=float, default=5.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
    parser.add_argument(
        "--place-test-order",
        action="store_true",
        help="Reserved for controlled SimNow order/cancel smoke. Default is connection-only.",
    )
    parser.add_argument("--worker", action="store_true")
    return parser.parse_args()


def snapshot_logs(strategy_dir: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return result
    for path in sorted(logs_dir.glob("*.log")):
        stat = path.stat()
        result[path.name] = {
            "mtime": stat.st_mtime,
            "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(
                sep=" ", timespec="seconds"
            ),
            "size": stat.st_size,
        }
    return result


def diff_logs(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    names = sorted(set(before) | set(after))
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        prev = before.get(name)
        curr = after.get(name)
        result[name] = {
            "changed": prev != curr,
            "before": prev,
            "after": curr,
        }
    return result


def _prepare_smoke_runtime(report_path: Path) -> Path:
    runtime_dir = report_path.with_suffix(report_path.suffix + ".runtime")
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "logs").mkdir(exist_ok=True)
    (runtime_dir / "run.py").write_text(_SMOKE_RUNTIME_SCRIPT, encoding="utf-8")
    return runtime_dir


def build_instances(
    instance_id: str, strategy_id: str, runtime_dir: Path | None = None
) -> dict[str, dict[str, Any]]:
    instance: dict[str, Any] = {
        "strategy_id": strategy_id,
        "status": "stopped",
        "pid": None,
        "error": None,
        "params": {
            "gateway": {
                "enabled": True,
                "provider": "ctp_gateway",
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
                "ctp_env": "auto",
            }
        },
    }
    if runtime_dir is not None:
        instance["runtime_dir"] = str(runtime_dir)
    return {instance_id: instance}


def _ctp_runtime_inputs(
    gateway_params: dict[str, Any], config_data: dict[str, Any], env_data: dict[str, str]
) -> dict[str, Any]:
    ctp = dict(config_data.get("ctp", {}) or {})
    live = dict(config_data.get("live", {}) or {})
    fronts = dict(ctp.get("fronts", {}) or {})
    network = str(live.get("network") or "simnow")
    front = dict(fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {})
    selection = gateway_launch_builder.resolve_ctp_front_selection(
        gateway_params=gateway_params,
        env_data=env_data,
        front=front,
    )
    investor_id = (
        gateway_params.get("investor_id")
        or gateway_params.get("user_id")
        or env_data.get("CTP_INVESTOR_ID")
        or env_data.get("CTP_USER_ID")
        or ctp.get("investor_id", "")
        or ctp.get("user_id", "")
    )
    broker_id = (
        gateway_params.get("broker_id") or env_data.get("CTP_BROKER_ID") or ctp.get("broker_id", "")
    )
    password = (
        gateway_params.get("password") or env_data.get("CTP_PASSWORD") or ctp.get("password", "")
    )
    app_id = (
        gateway_params.get("app_id")
        or env_data.get("CTP_APP_ID")
        or ctp.get("app_id", "simnow_client_test")
    )
    auth_code = (
        gateway_params.get("auth_code")
        or env_data.get("CTP_AUTH_CODE")
        or ctp.get("auth_code", "0000000000000000")
    )
    account_id = gateway_params.get("account_id") or investor_id
    required = {
        "account_id": account_id,
        "investor_id": investor_id,
        "broker_id": broker_id,
        "password": password,
        "td_front": selection.get("td_front", ""),
        "md_front": selection.get("md_front", ""),
    }
    missing = [key for key, value in required.items() if not str(value or "").strip()]
    if not missing:
        try:
            runtime_kwargs = gateway_launch_builder.build_ctp_gateway_runtime_kwargs(
                config_data=config_data,
                env_data=env_data,
                gateway_params=gateway_params,
                default_transport="tcp",
            )
        except Exception:
            runtime_kwargs = {}
        if runtime_kwargs:
            account_id = runtime_kwargs.get("account_id", account_id)
            investor_id = runtime_kwargs.get("investor_id", investor_id)
            broker_id = runtime_kwargs.get("broker_id", broker_id)
            selection.update(
                {
                    "td_front": runtime_kwargs.get("td_front")
                    or runtime_kwargs.get("td_address")
                    or selection.get("td_front", ""),
                    "md_front": runtime_kwargs.get("md_front")
                    or runtime_kwargs.get("md_address")
                    or selection.get("md_front", ""),
                    "selected_ctp_env": runtime_kwargs.get("selected_ctp_env")
                    or selection.get("selected_ctp_env", ""),
                    "selection_reason": runtime_kwargs.get("selection_reason")
                    or selection.get("selection_reason", ""),
                    "requested_ctp_env": runtime_kwargs.get("requested_ctp_env")
                    or selection.get("requested_ctp_env", ""),
                    "set1_group": runtime_kwargs.get("set1_group")
                    or selection.get("set1_group", ""),
                }
            )
    return {
        "account_id": str(account_id or ""),
        "investor_id": str(investor_id or ""),
        "broker_id": str(broker_id or ""),
        "has_password": bool(str(password or "").strip()),
        "has_app_id": bool(str(app_id or "").strip()),
        "has_auth_code": bool(str(auth_code or "").strip()),
        "td_front": str(selection.get("td_front") or ""),
        "md_front": str(selection.get("md_front") or ""),
        "selected_ctp_env": str(selection.get("selected_ctp_env") or ""),
        "selection_reason": str(selection.get("selection_reason") or ""),
        "selected_at": str(selection.get("selected_at") or ""),
        "requested_ctp_env": str(selection.get("requested_ctp_env") or ""),
        "set1_group": str(selection.get("set1_group") or ""),
        "missing_required_fields": missing,
    }


def collect_gateway_prerequisites(instance: dict[str, Any], runtime_dir: Path) -> dict[str, Any]:
    gateway_params = gateway_launch_builder.get_gateway_params(instance, "tcp")
    result: dict[str, Any] = {
        "enabled": bool(gateway_params.get("enabled")),
        "exchange_type": str(gateway_params.get("exchange_type") or ""),
        "provider": str(gateway_params.get("provider") or ""),
        "missing_required_fields": [],
    }
    if not result["enabled"] or result["exchange_type"] != "CTP":
        return result
    try:
        config_data = strategy_runtime_support.load_strategy_config(runtime_dir)
        env_data = strategy_runtime_support.load_strategy_env(runtime_dir, PROJECT_ROOT)
        result.update(_ctp_runtime_inputs(gateway_params, config_data, env_data))
    except Exception as exc:
        result["prerequisite_error"] = {"type": type(exc).__name__, "message": str(exc)}
    return result


def summarize_gateway_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "selected_ctp_env": "",
            "auth_state": "unknown",
            "login_state": "unknown",
            "tick_count": 0,
            "order_count": 0,
            "is_healthy": False,
        }
    row = rows[0]
    return {
        "gateway_key": row.get("gateway_key", ""),
        "selected_ctp_env": row.get("selected_ctp_env", ""),
        "td_front": row.get("td_front", ""),
        "md_front": row.get("md_front", ""),
        "selection_reason": row.get("selection_reason", ""),
        "auth_state": row.get("auth_state", "unknown"),
        "login_state": row.get("login_state", "unknown"),
        "front_id": row.get("front_id", ""),
        "session_id": row.get("session_id", ""),
        "trading_day": row.get("trading_day", ""),
        "market_connection": row.get("market_connection", "unknown"),
        "trade_connection": row.get("trade_connection", "unknown"),
        "tick_count": row.get("tick_count", 0),
        "order_count": row.get("order_count", 0),
        "is_healthy": bool(row.get("is_healthy")),
    }


def _blocked_reason_for_exception(exc: Exception) -> str:
    message = str(exc).lower()
    exc_name = type(exc).__name__.lower()
    if "run.py does not exist" in message:
        return "runtime_prerequisite_missing"
    if (
        "bt_api_base 网关模块无法加载" in message
        or "no module named 'bt_api_base.gateway.config'" in message
        or "bt_api_base.gateway.runtime" in message
    ):
        return "runtime_prerequisite_missing"
    if any(token in message for token in ("credential", "password", "auth_code", "app_id")):
        return "credentials_unavailable"
    if any(token in message for token in ("ctp sdk", "cthost", "thost", "importerror")):
        return "ctp_sdk_unavailable"
    if any(
        token in message
        for token in ("not ready", "timeout", "timed out", "network", "connect", "front")
    ) or "timeout" in exc_name:
        return "external_environment_unavailable"
    return ""


def _blocked_reason_for_report(report: dict[str, Any]) -> str:
    prerequisites = report.get("gateway_prerequisites")
    if not isinstance(prerequisites, dict):
        return ""
    gateway_was_requested = prerequisites.get("enabled") is True
    gateway_was_not_acquired = report.get("gateway_keys_after_start") == []
    missing_required = prerequisites.get("missing_required_fields")
    if gateway_was_requested and gateway_was_not_acquired and missing_required:
        return "credentials_unavailable"
    return ""


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    instance_id = f"smoke-{uuid.uuid4().hex[:8]}"
    report_path = Path(args.report_file)
    strategy_dir = get_strategy_dir(args.strategy_id)
    runtime_dir = _prepare_smoke_runtime(report_path)
    instances = build_instances(instance_id, args.strategy_id, runtime_dir=runtime_dir)
    gateway_prerequisites = collect_gateway_prerequisites(instances[instance_id], runtime_dir)
    report: dict[str, Any] = {
        "strategy_id": args.strategy_id,
        "strategy_dir": str(strategy_dir),
        "runtime_dir": str(runtime_dir),
        "instance_id": instance_id,
        "started": False,
        "stopped": False,
        "exception": None,
        "gateway_keys_after_start": [],
        "gateway_keys_after_stop": [],
        "gateway_health_after_start": [],
        "gateway_health_summary_after_start": {},
        "gateway_health_after_stop": [],
        "process_present": None,
        "process_returncode_before_stop": None,
        "final_instance_status": None,
        "final_instance_error": None,
        "logs_before": snapshot_logs(runtime_dir),
        "logs_after": None,
        "log_changes": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "started_status": None,
        "stopped_status": None,
        "pid": None,
        "gateway_prerequisites": gateway_prerequisites,
        "wait_seconds": args.wait_seconds,
        "report_file": str(report_path),
        "place_test_order": bool(args.place_test_order),
        "test_order_result": {"status": "skipped", "reason": "place_test_order_not_requested"},
        "e2e_status": "PENDING",
        "blocked_reason": None,
        "completed_at": None,
    }

    def _load_instances() -> dict[str, dict[str, Any]]:
        return instances

    def _save_instances(data: dict[str, dict[str, Any]]) -> None:
        snapshot = copy.deepcopy(data)
        instances.clear()
        instances.update(snapshot)

    with patch("app.services.live_trading_manager._load_instances", side_effect=_load_instances):
        with patch("app.services.live_trading_manager._save_instances", side_effect=_save_instances):
            with patch("app.services.live_trading_manager._find_latest_log_dir", return_value=None):
                manager = LiveTradingManager()
                try:
                    started = await manager.start_instance(instance_id)
                    report["started"] = True
                    report["started_status"] = started.get("status")
                    report["pid"] = started.get("pid")
                    report["gateway_keys_after_start"] = list(manager._gateways.keys())
                    health_after_start = manager.get_gateway_health()
                    report["gateway_health_after_start"] = health_after_start
                    report["gateway_health_summary_after_start"] = summarize_gateway_health(
                        health_after_start
                    )
                    if args.place_test_order:
                        report["test_order_result"] = {
                            "status": "blocked",
                            "reason": "controlled order/cancel smoke is not implemented in this script yet",
                        }
                except Exception as exc:
                    report["exception"] = {"type": type(exc).__name__, "message": str(exc)}
                    blocked_reason = _blocked_reason_for_exception(exc)
                    if blocked_reason:
                        report["e2e_status"] = "BLOCKED"
                        report["blocked_reason"] = blocked_reason
                    else:
                        report["e2e_status"] = "FAIL"
                else:
                    await asyncio.sleep(args.wait_seconds)
                    proc = manager._processes.get(instance_id)
                    report["process_present"] = proc is not None
                    if proc is not None:
                        report["process_returncode_before_stop"] = proc.returncode
                        if proc.returncode is not None:
                            try:
                                if proc.stdout is not None:
                                    report["stdout_tail"] = (
                                        await proc.stdout.read()
                                    ).decode("utf-8", errors="replace")[-2000:]
                            except Exception as exc:
                                report["stdout_tail"] = f"<stdout read failed: {exc}>"
                            try:
                                if proc.stderr is not None:
                                    report["stderr_tail"] = (
                                        await proc.stderr.read()
                                    ).decode("utf-8", errors="replace")[-2000:]
                            except Exception as exc:
                                report["stderr_tail"] = f"<stderr read failed: {exc}>"
                    if instance_id in manager._processes:
                        stopped = await manager.stop_instance(instance_id)
                        report["stopped"] = True
                        report["stopped_status"] = stopped.get("status")
                        await asyncio.sleep(args.settle_seconds)
                    report["gateway_keys_after_stop"] = list(manager._gateways.keys())
                    report["gateway_health_after_stop"] = manager.get_gateway_health()
                    report["final_instance_status"] = instances.get(instance_id, {}).get("status")
                    report["final_instance_error"] = instances.get(instance_id, {}).get("error")

    report["logs_after"] = snapshot_logs(runtime_dir)
    report["log_changes"] = diff_logs(report["logs_before"], report["logs_after"])
    report["completed_at"] = datetime.now().isoformat(timespec="seconds")
    if report.get("e2e_status") == "PENDING":
        blocked_reason = _blocked_reason_for_report(report)
        if blocked_reason:
            report["e2e_status"] = "BLOCKED"
            report["blocked_reason"] = blocked_reason
        else:
            report["e2e_status"] = "PASS" if _validate_report(report) == 0 else "FAIL"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def print_summary(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _tail_text_file(path: Path, max_chars: int = 2000) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text("utf-8", errors="replace")[-max_chars:]
    except Exception as exc:
        return f"<read failed: {exc}>"


def _validate_report(report: dict[str, Any]) -> int:
    if report.get("exception"):
        return 1
    if not report.get("started"):
        return 1
    if report.get("gateway_keys_after_start") == []:
        return 1
    if report.get("process_present") is False and report.get("process_returncode_before_stop") not in (0, None):
        return 1
    if report.get("gateway_keys_after_stop"):
        return 1
    if report.get("final_instance_error"):
        return 1
    if report.get("stopped") is False and report.get("process_returncode_before_stop") is None:
        return 1
    return 0


def _worker_main(args: argparse.Namespace) -> int:
    os.environ.setdefault("LIVE_TRADING_RESTORE_MANUAL_GATEWAYS", "false")
    try:
        report = asyncio.run(run_smoke(args))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "started": False,
                    "stopped": False,
                    "exception": {"type": type(exc).__name__, "message": str(exc)},
                    "report_file": args.report_file,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print_summary(report)
    return _validate_report(report)


def _parent_main(args: argparse.Namespace) -> int:
    report_path = Path(args.report_file)
    stdout_path = report_path.with_suffix(report_path.suffix + ".worker.stdout.log")
    stderr_path = report_path.with_suffix(report_path.suffix + ".worker.stderr.log")
    if report_path.exists():
        report_path.unlink()
    if stdout_path.exists():
        stdout_path.unlink()
    if stderr_path.exists():
        stderr_path.unlink()
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--strategy-id",
        args.strategy_id,
        "--wait-seconds",
        str(args.wait_seconds),
        "--settle-seconds",
        str(args.settle_seconds),
        "--report-file",
        str(report_path),
    ]
    if getattr(args, "place_test_order", False):
        cmd.append("--place-test-order")
    worker_env = dict(os.environ)
    worker_env["LIVE_TRADING_RESTORE_MANUAL_GATEWAYS"] = "false"
    timed_out = False
    with open(stdout_path, "w", encoding="utf-8") as stdout_file:
        with open(stderr_path, "w", encoding="utf-8") as stderr_file:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=stdout_file,
                stderr=stderr_file,
                env=worker_env,
                text=True,
            )
            deadline = time.monotonic() + max(args.worker_timeout_seconds, 1.0)
            while True:
                returncode = proc.poll()
                if returncode is not None:
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    proc.terminate()
                    try:
                        proc.wait(timeout=max(args.worker_grace_seconds, 0.1))
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    break
                time.sleep(max(args.poll_interval_seconds, 0.1))
            result_returncode = proc.returncode
    if not report_path.is_file():
        message = f"worker exited with code {result_returncode}"
        if timed_out:
            message = (
                f"worker timed out after {args.worker_timeout_seconds:.1f}s "
                f"and exited with code {result_returncode}"
            )
        payload = {
            "started": False,
            "stopped": False,
            "exception": {
                "type": "WorkerProcessError" if not timed_out else "WorkerTimeoutError",
                "message": message,
            },
            "worker_returncode": result_returncode,
            "worker_timed_out": timed_out,
            "worker_stdout_tail": _tail_text_file(stdout_path),
            "worker_stderr_tail": _tail_text_file(stderr_path),
            "report_file": str(report_path),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    report = json.loads(report_path.read_text("utf-8"))
    report["worker_returncode"] = result_returncode
    report["worker_timed_out"] = timed_out
    report["worker_stdout_tail"] = _tail_text_file(stdout_path)
    report["worker_stderr_tail"] = _tail_text_file(stderr_path)
    print_summary(report)
    return _validate_report(report)


def main() -> int:
    args = parse_args()
    if args.worker:
        return _worker_main(args)
    return _parent_main(args)


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
