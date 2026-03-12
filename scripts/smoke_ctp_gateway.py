#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.live_trading_manager import LiveTradingManager
from app.services.strategy_service import get_strategy_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-id", default="simulate/p_bb_rsi")
    parser.add_argument("--wait-seconds", type=float, default=5.0)
    parser.add_argument("--settle-seconds", type=float, default=0.5)
    parser.add_argument("--report-file", default="/tmp/ctp_gateway_smoke_report.json")
    parser.add_argument("--worker-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--worker-grace-seconds", type=float, default=5.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.5)
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


def build_instances(instance_id: str, strategy_id: str) -> dict[str, dict[str, Any]]:
    return {
        instance_id: {
            "strategy_id": strategy_id,
            "status": "stopped",
            "pid": None,
            "error": None,
            "params": {"gateway": {"enabled": True}},
        }
    }


async def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    strategy_dir = get_strategy_dir(args.strategy_id)
    instance_id = f"smoke-{uuid.uuid4().hex[:8]}"
    instances = build_instances(instance_id, args.strategy_id)
    report_path = Path(args.report_file)
    report: dict[str, Any] = {
        "strategy_id": args.strategy_id,
        "strategy_dir": str(strategy_dir),
        "instance_id": instance_id,
        "started": False,
        "stopped": False,
        "exception": None,
        "gateway_keys_after_start": [],
        "gateway_keys_after_stop": [],
        "process_present": None,
        "process_returncode_before_stop": None,
        "final_instance_status": None,
        "final_instance_error": None,
        "logs_before": snapshot_logs(strategy_dir),
        "logs_after": None,
        "log_changes": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "started_status": None,
        "stopped_status": None,
        "pid": None,
        "wait_seconds": args.wait_seconds,
        "report_file": str(report_path),
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
                except Exception as exc:
                    report["exception"] = {"type": type(exc).__name__, "message": str(exc)}
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
                    report["final_instance_status"] = instances.get(instance_id, {}).get("status")
                    report["final_instance_error"] = instances.get(instance_id, {}).get("error")

    report["logs_after"] = snapshot_logs(strategy_dir)
    report["log_changes"] = diff_logs(report["logs_before"], report["logs_after"])
    report["completed_at"] = datetime.now().isoformat(timespec="seconds")
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
    timed_out = False
    with open(stdout_path, "w", encoding="utf-8") as stdout_file:
        with open(stderr_path, "w", encoding="utf-8") as stderr_file:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=stdout_file,
                stderr=stderr_file,
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
