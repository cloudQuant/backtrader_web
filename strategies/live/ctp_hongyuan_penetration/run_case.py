#!/usr/bin/env python
"""Run one or more Hongyuan penetration certification cases in isolated subprocesses.

Usage
-----
    # Run a single case
    python run_case.py C01

    # Run several cases
    python run_case.py C01 T01 T02 T03

    # Run ALL cases (sequential)
    python run_case.py --all

    # Specify custom report directory
    python run_case.py C01 --report-root ./my_reports
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from common.certification import (
    build_certification_coverage,
    enrich_result_payload,
    get_certification_scenario,
)

_SUITE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SUITE_DIR.parents[2]
_CASES_DIR = _SUITE_DIR / "cases"

# ---------------------------------------------------------------------------
# Case registry: maps case_id -> case file
# ---------------------------------------------------------------------------

CASE_REGISTRY: dict[str, Path] = {}


def _discover_cases():
    """Scan cases/ directory and build {case_id: path} registry."""
    for p in sorted(_CASES_DIR.glob("*.py")):
        if p.name.startswith("_") or p.name == "__init__.py":
            continue
        # Extract case_id from filename, e.g. C01_connect_and_login.py -> C01
        case_id = p.stem.split("_", 1)[0]
        CASE_REGISTRY[case_id] = p


_discover_cases()

# Ordered list following the spec sequence
CASE_ORDER = [
    "C01",
    "T01", "T02", "T03",
    "M01", "M02", "M03", "M04", "M05",
    "O01", "O02", "O03",
    "TH01", "TH02", "TH03", "TH04", "TH05", "TH06",
    "V01", "V02", "V03",
    "E01", "E02", "E03",
    "EM01", "EM02", "EM03",
    "B01", "B02",
    "L01", "L02", "L03", "L04",
]

# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 180
_NATIVE_STARTUP_CRASH_EXIT_CODE = -11
_NATIVE_STARTUP_RETRY_DELAY_SECONDS = 2


def _is_empty_native_startup_crash(
    completed: subprocess.CompletedProcess[str], report_dir: Path
) -> bool:
    """Return whether a SIGSEGV occurred before a case could reach CTP actions.

    ``started_store`` writes a durable before-action snapshot after successful
    connection and before any case can submit an order.  Retrying is safe only
    when that evidence is absent and the child left no non-empty log output.
    This deliberately avoids replaying a process that might have reached an
    order path.
    """
    if completed.returncode != _NATIVE_STARTUP_CRASH_EXIT_CODE:
        return False
    if (report_dir / "result.json").exists():
        return False
    try:
        artifacts = tuple(report_dir.iterdir())
    except OSError:
        return False
    return all(
        artifact.name == "stdout.log"
        and artifact.is_file()
        and artifact.stat().st_size == 0
        for artifact in artifacts
    )


def _run_child(
    cmd: list[str],
    *,
    timeout: int,
    child_environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Launch one isolated case child with the certification environment."""
    return subprocess.run(
        cmd,
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=child_environment,
        check=False,
    )


def run_case(case_id: str, report_root: Path, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run a single case in an isolated subprocess, return result dict."""
    case_file = CASE_REGISTRY.get(case_id)
    if case_file is None:
        print(f"[ERROR] Unknown case: {case_id}")
        print(f"  Available: {', '.join(sorted(CASE_REGISTRY))}")
        return {"case_id": case_id, "status": "FAIL", "failure_reason": "Unknown case_id"}

    report_dir = report_root / case_id
    report_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-u", str(case_file),
        "--report-dir", str(report_dir),
    ]
    child_environment = os.environ.copy()
    child_environment["HONGYUAN_CERTIFICATION_REMOTE_VALIDATION"] = "1"

    print(f"\n{'='*60}")
    print(f"  Running {case_id}: {case_file.stem}")
    print(f"  Report -> {report_dir}")
    print(f"{'='*60}")

    try:
        completed = _run_child(
            cmd,
            timeout=timeout,
            child_environment=child_environment,
        )
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT] {case_id} exceeded {timeout}s")
        return enrich_result_payload({
            "case_id": case_id,
            "status": "BLOCKED",
            "failure_reason": f"Timeout {timeout}s",
        })

    if _is_empty_native_startup_crash(completed, report_dir):
        retry_path = report_dir / "startup_retry.json"
        with retry_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "first_exit_code": completed.returncode,
                    "retry_delay_seconds": _NATIVE_STARTUP_RETRY_DELAY_SECONDS,
                },
                handle,
                ensure_ascii=True,
                indent=2,
            )
        print(
            "  [RETRY] Native CTP child stopped before durable startup evidence; "
            "retrying once after cooldown"
        )
        time.sleep(_NATIVE_STARTUP_RETRY_DELAY_SECONDS)
        try:
            completed = _run_child(
                cmd,
                timeout=timeout,
                child_environment=child_environment,
            )
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {case_id} retry exceeded {timeout}s")
            return enrich_result_payload({
                "case_id": case_id,
                "status": "BLOCKED",
                "failure_reason": f"Retry timeout {timeout}s",
            })

    # Relay output
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    # Read result.json if available
    result_path = report_dir / "result.json"
    if result_path.exists():
        with open(result_path, "r", encoding="utf-8") as fh:
            return enrich_result_payload(json.load(fh))

    # Fallback
    status = {0: "PASS", 1: "FAIL", 2: "BLOCKED"}.get(completed.returncode, "FAIL")
    return enrich_result_payload({
        "case_id": case_id,
        "status": status,
        "failure_reason": f"exit_code={completed.returncode}",
    })


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary(results: list[dict], report_root: Path) -> int:
    """Print and save a summary table."""
    results = [enrich_result_payload(result) for result in results]
    print(f"\n{'='*60}")
    print("  CERTIFICATION SUMMARY")
    print(f"{'='*60}\n")

    pass_count = sum(1 for r in results if r.get("status") == "PASS")
    fail_count = sum(1 for r in results if r.get("status") == "FAIL")
    blocked_count = sum(1 for r in results if r.get("status") == "BLOCKED")

    for r in results:
        status = r.get("status", "?")
        case_id = r.get("case_id", "?")
        scenario_id = r.get("scenario_id", "")
        reason = r.get("failure_reason", "")
        icon = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "◉"}.get(status, "?")
        line = f"  {icon} [{status:7s}] {case_id}"
        if scenario_id:
            line += f" -> {scenario_id}"
        if reason:
            line += f"  -- {reason[:80]}"
        print(line)

    print(f"\n  Total: {len(results)}  PASS: {pass_count}  FAIL: {fail_count}  BLOCKED: {blocked_count}")
    certification = build_certification_coverage(
        case_order=CASE_ORDER,
        case_registry=CASE_REGISTRY,
        results=results,
    )
    print(
        "  Scenarios: "
        f"{certification['covered_scenarios']}/{certification['total_scenarios']} covered"
    )

    # Save summary JSON
    summary_path = report_root / "summary.json"
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total": len(results),
        "pass": pass_count,
        "fail": fail_count,
        "blocked": blocked_count,
        "certification": certification,
        "results": results,
    }
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=True, indent=2)
    print(f"\n  Summary saved -> {summary_path}")

    if fail_count:
        return 1
    if blocked_count:
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    """Main entry point for running Hongyuan certification cases."""
    parser = argparse.ArgumentParser(
        description="Run Hongyuan penetration certification cases",
    )
    parser.add_argument(
        "cases", nargs="*",
        help="Case IDs to run (e.g. C01 T01). Omit for --all.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run all 33 cases in spec order",
    )
    parser.add_argument(
        "--report-root", default="",
        help="Root directory for reports (default: reports/latest)",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help=f"Per-case timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_cases",
        help="List all available cases and exit",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required acknowledgement before a case can connect to CTP.",
    )
    args = parser.parse_args()

    if args.list_cases:
        print("Available cases:")
        for cid in CASE_ORDER:
            path = CASE_REGISTRY.get(cid)
            scenario = get_certification_scenario(cid)
            tag = " (not found)" if path is None else ""
            print(
                f"  {cid} -> {scenario.scenario_id}: "
                f"{path.stem if path else '?'}{tag}"
            )
        return

    case_ids = CASE_ORDER if args.all else args.cases
    if not case_ids:
        parser.print_help()
        return
    if not args.execute:
        parser.error(
            "CTP certification may submit or cancel orders; use run.py --case CASE_ID --execute"
        )

    report_root = (
        Path(args.report_root) if args.report_root
        else _SUITE_DIR / "reports" / "latest"
    )
    report_root.mkdir(parents=True, exist_ok=True)

    results = []
    for cid in case_ids:
        result = run_case(cid, report_root, timeout=args.timeout)
        results.append(result)

    return print_summary(results, report_root)


if __name__ == "__main__":
    raise SystemExit(main())
