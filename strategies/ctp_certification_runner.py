"""Safe command-line wrapper shared by the CTP certification workspaces.

The copied certification suites deliberately retain their individual case
implementations.  This module provides the user-facing safety boundary: list
and dry-run commands are offline, while any action that can reach a CTP front
needs an explicit ``--execute`` confirmation.
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


EXPECTED_CASE_COUNT = 33


@dataclass(frozen=True)
class CertificationWorkspace:
    """Static information needed to run one CTP certification workspace."""

    label: str
    suite_dir: Path
    project_root: Path
    environment_variable: str
    order_symbol_variable: str
    tick_symbol_variable: str

    @property
    def case_runner(self) -> Path:
        """Return the copied source-suite case runner."""
        return self.suite_dir / "run_case.py"


def _build_parser(workspace: CertificationWorkspace) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Run {workspace.label} CTP certification safely.",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="CASE_ID",
        help="Run one case; repeat this option to select multiple cases.",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Run every certification case in specification order.",
    )
    selection.add_argument(
        "--list",
        action="store_true",
        dest="list_cases",
        help="List the 33 available cases without connecting to CTP.",
    )
    selection.add_argument(
        "--dry-run",
        action="store_true",
        help="Offline dependency and suite-layout check; never connects to CTP.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required acknowledgement before a selected case can reach CTP.",
    )
    parser.add_argument(
        "--report-root",
        type=Path,
        help="Directory for runtime evidence; defaults to this workspace's reports/latest.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-case timeout in seconds (default: 180).",
    )
    parser.add_argument(
        "--environment",
        help="Override the workspace CTP environment without editing .env.",
    )
    parser.add_argument(
        "--order-symbol",
        help="Override the order-test contract without editing .env.",
    )
    parser.add_argument(
        "--tick-symbol",
        help="Override the market-data-test contract without editing .env.",
    )
    return parser


def _case_count(workspace: CertificationWorkspace) -> int:
    cases_dir = workspace.suite_dir / "cases"
    return len(
        [
            path
            for path in cases_dir.glob("*.py")
            if path.name != "__init__.py" and not path.name.startswith("_")
        ]
    )


def _probe_gateway_adapter() -> None:
    """Import the adapter classes without constructing a store or opening a socket."""
    for module_name, attribute in (
        ("backtrader.stores.btapistore", "BtApiStore"),
        ("backtrader.brokers.btapibroker", "BtApiBroker"),
        ("backtrader.feeds.btapifeed", "BtApiFeed"),
    ):
        module = importlib.import_module(module_name)
        getattr(module, attribute)


def _runtime_environment(
    workspace: CertificationWorkspace, args: argparse.Namespace
) -> dict[str, str]:
    environment = dict(os.environ)
    overrides = (
        (workspace.environment_variable, args.environment),
        (workspace.order_symbol_variable, args.order_symbol),
        (workspace.tick_symbol_variable, args.tick_symbol),
    )
    for key, value in overrides:
        if value:
            environment[key] = value
    return environment


def _run_list(workspace: CertificationWorkspace, environment: dict[str, str]) -> int:
    completed = subprocess.run(
        [sys.executable, str(workspace.case_runner), "--list"],
        cwd=workspace.project_root,
        env=environment,
        check=False,
    )
    return completed.returncode


def _dry_run(workspace: CertificationWorkspace) -> int:
    if not workspace.case_runner.is_file():
        print(f"Missing case runner: {workspace.case_runner}", file=sys.stderr)
        return 1

    count = _case_count(workspace)
    if count != EXPECTED_CASE_COUNT:
        print(
            f"Expected {EXPECTED_CASE_COUNT} certification cases, found {count}.",
            file=sys.stderr,
        )
        return 1

    try:
        _probe_gateway_adapter()
    except (AttributeError, ImportError, ModuleNotFoundError) as exc:
        print(f"BtApiStore adapter: unavailable ({exc})", file=sys.stderr)
        print(
            "Install the project CTP-enabled Backtrader build before using --execute.",
            file=sys.stderr,
        )
        return 1

    print(f"{workspace.label}: {count} certification cases are ready")
    print("BtApiStore adapter: ready")
    print("No CTP connection was opened")
    return 0


def main(workspace: CertificationWorkspace, argv: Sequence[str] | None = None) -> int:
    """Execute one workspace command and return its process-style exit code."""
    parser = _build_parser(workspace)
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.execute and (args.dry_run or args.list_cases):
        parser.error("--execute only applies to --case or --all")
    if args.dry_run:
        return _dry_run(workspace)

    environment = _runtime_environment(workspace, args)
    if args.list_cases:
        return _run_list(workspace, environment)

    if not args.case and not args.all:
        if not args.execute:
            return _dry_run(workspace)
        parser.error("Choose --dry-run, --list, --case CASE_ID, or --all")
    if not args.execute:
        parser.error(
            "CTP certification may submit or cancel orders; re-run with --execute to continue"
        )

    command = [sys.executable, str(workspace.case_runner)]
    if args.all:
        command.append("--all")
    else:
        command.extend(args.case)
    command.extend(["--timeout", str(args.timeout), "--execute"])
    if args.report_root is not None:
        command.extend(["--report-root", str(args.report_root)])

    print(f"Starting {workspace.label} certification with explicit confirmation.")
    completed = subprocess.run(
        command,
        cwd=workspace.project_root,
        env=environment,
        check=False,
    )
    return completed.returncode
