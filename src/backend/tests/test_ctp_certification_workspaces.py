"""Regression tests for the CTP certification strategy workspaces.

These tests intentionally exercise the command-line entry points.  A dry run
must stay entirely offline: it is safe to run on a development machine without
CTP credentials or an active trading session.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from app.schemas.strategy import StrategyType
from app.services.strategy.runtime_support import infer_gateway_params
from app.services.strategy.templates import scan_strategies_folder

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKSPACES = {
    "simnow": REPOSITORY_ROOT / "strategies/simulate/ctp_simnow_certification",
    "hongyuan": REPOSITORY_ROOT / "strategies/live/ctp_hongyuan_penetration",
}
EXPECTED_CASE_IDS = {
    "C01",
    "T01",
    "T02",
    "T03",
    "M01",
    "M02",
    "M03",
    "M04",
    "M05",
    "O01",
    "O02",
    "O03",
    "TH01",
    "TH02",
    "TH03",
    "TH04",
    "TH05",
    "TH06",
    "V01",
    "V02",
    "V03",
    "E01",
    "E02",
    "E03",
    "EM01",
    "EM02",
    "EM03",
    "B01",
    "B02",
    "L01",
    "L02",
    "L03",
    "L04",
}


@pytest.mark.parametrize(("workspace_name", "workspace"), WORKSPACES.items())
def test_workspace_dry_run_is_offline_and_lists_all_cases(
    workspace_name: str, workspace: Path
) -> None:
    """Each workspace exposes all certification cases without a CTP connection."""
    completed = subprocess.run(
        [sys.executable, str(workspace / "run.py"), "--dry-run"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "33 certification cases" in completed.stdout
    assert "BtApiStore adapter: ready" in completed.stdout
    assert "No CTP connection was opened" in completed.stdout
    assert not (workspace / "reports").exists(), workspace_name


@pytest.mark.parametrize("workspace", WORKSPACES.values())
def test_workspace_default_start_is_an_offline_preflight(workspace: Path) -> None:
    """The app starts run.py without arguments, so that path must stay safe."""
    completed = subprocess.run(
        [sys.executable, str(workspace / "run.py")],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "No CTP connection was opened" in completed.stdout


@pytest.mark.parametrize("workspace", WORKSPACES.values())
def test_workspace_template_does_not_implicitly_start_a_gateway(workspace: Path) -> None:
    """Explicit CLI confirmation must precede gateway creation in the app too."""
    assert infer_gateway_params(workspace) is None


@pytest.mark.parametrize("workspace", WORKSPACES.values())
def test_workspace_requires_explicit_execute_for_live_case(workspace: Path) -> None:
    """A case selection alone must never be enough to submit a CTP order."""
    completed = subprocess.run(
        [sys.executable, str(workspace / "run.py"), "--case", "C01"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 2
    assert "--execute" in completed.stderr


@pytest.mark.parametrize("workspace", WORKSPACES.values())
def test_internal_case_runner_cannot_bypass_execution_confirmation(workspace: Path) -> None:
    """Calling the copied suite runner directly must retain the same safety gate."""
    completed = subprocess.run(
        [sys.executable, str(workspace / "run_case.py"), "C01"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 2
    assert "--execute" in completed.stderr


@pytest.mark.parametrize("workspace", WORKSPACES.values())
def test_workspace_contains_the_full_certification_case_set(workspace: Path) -> None:
    """Copy all 33 source cases, not merely a thin wrapper around a few examples."""
    case_files = sorted((workspace / "cases").glob("*.py"))
    case_ids = {path.stem.split("_", 1)[0] for path in case_files if path.name != "__init__.py"}

    assert len(case_files) == 34
    assert case_ids == EXPECTED_CASE_IDS
    assert (workspace / "common/runtime.py").is_file()
    assert (workspace / "common/certification.py").is_file()


@pytest.mark.parametrize("workspace", WORKSPACES.values())
def test_workspace_reports_are_gitignored(workspace: Path) -> None:
    """Runtime reports may contain account and order evidence, so keep them local."""
    report = workspace / "reports/latest/summary.json"
    completed = subprocess.run(
        ["git", "check-ignore", "--quiet", str(report.relative_to(REPOSITORY_ROOT))],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert completed.returncode == 0


def test_hongyuan_docx_report_uses_its_workspace_paths() -> None:
    """The relocated DOCX generator must not write back into the source repository."""
    workspace = WORKSPACES["hongyuan"]
    module_path = workspace / "fill_docx_report.py"
    spec = importlib.util.spec_from_file_location("ctp_hongyuan_docx_report", module_path)

    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.OUTPUT.parent == workspace
    assert module.RESULTS_ROOT == workspace / "reports/latest"


def test_workspaces_are_discoverable_strategy_templates() -> None:
    """The application can list both workspaces instead of treating them as loose scripts."""
    simulate_templates = scan_strategies_folder(StrategyType.simulate)
    live_templates = scan_strategies_folder(StrategyType.live)

    assert any(
        template.id == "simulate/ctp_simnow_certification"
        for template in simulate_templates
    )
    assert any(
        template.id == "live/ctp_hongyuan_penetration"
        for template in live_templates
    )
