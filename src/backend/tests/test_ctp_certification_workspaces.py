"""Regression tests for the CTP certification strategy workspaces.

These tests intentionally exercise the command-line entry points.  A dry run
must stay entirely offline: it is safe to run on a development machine without
CTP credentials or an active trading session.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
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


def _report_inventory(workspace: Path) -> dict[str, tuple[bool, int, int]]:
    """Return a stable inventory for reports that already exist locally."""
    reports_dir = workspace / "reports"
    if not reports_dir.exists():
        return {}

    inventory: dict[str, tuple[bool, int, int]] = {}
    for path in reports_dir.rglob("*"):
        stat = path.stat()
        inventory[str(path.relative_to(reports_dir))] = (
            path.is_dir(),
            stat.st_mtime_ns,
            stat.st_size,
        )
    return inventory


@pytest.mark.parametrize(("workspace_name", "workspace"), WORKSPACES.items())
def test_workspace_dry_run_is_offline_and_lists_all_cases(
    workspace_name: str, workspace: Path
) -> None:
    """Each workspace exposes all certification cases without a CTP connection."""
    reports_before = _report_inventory(workspace)
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
    assert _report_inventory(workspace) == reports_before, workspace_name


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
def test_workspace_propagates_a_case_failure_as_a_nonzero_exit_code(
    workspace: Path, tmp_path: Path
) -> None:
    """The wrapper must not report success when its selected case fails."""
    completed = subprocess.run(
        [
            sys.executable,
            str(workspace / "run.py"),
            "--case",
            "UNKNOWN",
            "--execute",
            "--report-root",
            str(tmp_path / workspace.name),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 1, completed.stdout + completed.stderr


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


def test_hongyuan_started_store_masks_investor_id_in_console_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Live-start diagnostics must never emit the complete investor identifier."""
    workspace = WORKSPACES["hongyuan"]
    saved_common_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "common" or name.startswith("common.")
    }
    for name in saved_common_modules:
        sys.modules.pop(name)
    sys.path.insert(0, str(workspace))

    try:
        runtime = importlib.import_module("common.runtime")

        class FakeStore:
            """No-network stand-in for the connection lifecycle."""

            is_connected = True

            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

        investor_id = "1234567890"
        monkeypatch.setattr(runtime, "BtApiStore", FakeStore)
        monkeypatch.setattr(
            runtime.cfg,
            "create_config",
            lambda _env_key: {
                "td_address": "tcp://test-td:1",
                "md_address": "tcp://test-md:2",
                "investor_id": investor_id,
            },
        )

        with runtime.started_store("telecom"):
            pass

        output = capsys.readouterr().out
        assert investor_id not in output
        assert "12***90" in output
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_runtime_records_auth_events_with_surrogate_safe_json(
    tmp_path: Path,
) -> None:
    """CTP callback text must not make the login evidence writer crash."""
    workspace = WORKSPACES["hongyuan"]
    saved_common_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "common" or name.startswith("common.")
    }
    for name in saved_common_modules:
        sys.modules.pop(name)
    sys.path.insert(0, str(workspace))

    try:
        runtime = importlib.import_module("common.runtime")
        log_path = tmp_path / "system.log"
        event_types = runtime.record_runtime_events(
            [
                (
                    "runtime_event",
                    (),
                    {
                        "event": {
                            "event_type": "store_auth_success",
                            "details": {
                                "system_name": chr(0xDC85),
                                "password": "not-for-logs",
                                "investor_id": "1234567890",
                                "InvestorID": "0987654321",
                                "AuthCode": "not-for-logs-auth-code",
                            },
                        }
                    },
                )
            ],
            log_path,
        )

        raw = log_path.read_bytes()
        assert event_types == {"store_auth_success"}
        assert b"not-for-logs" not in raw
        assert b"1234567890" not in raw
        assert b"0987654321" not in raw
        assert b"not-for-logs-auth-code" not in raw
        assert json.loads(raw.decode("utf-8"))["event_type"] == "store_auth_success"
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_snapshot_writer_escapes_ctp_surrogate_text(tmp_path: Path) -> None:
    """A legacy CTP text field must not make account evidence unwritable."""
    workspace = WORKSPACES["hongyuan"]
    saved_common_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "common" or name.startswith("common.")
    }
    for name in saved_common_modules:
        sys.modules.pop(name)
    sys.path.insert(0, str(workspace))

    try:
        evidence = importlib.import_module("common.evidence")

        class FakeStore:
            """No-network snapshot source with a legacy CTP text response."""

            is_connected = True

            def get_balance(self) -> dict[str, str]:
                return {"StatusMsg": chr(0xDC85)}

            def get_positions(self) -> list[dict[str, str]]:
                return []

            def get_open_orders(self) -> list[dict[str, str]]:
                return []

        snapshot = evidence.capture_store_snapshot(
            report_dir=tmp_path,
            case_id="C01",
            label="before_action",
            store=FakeStore(),
            env_key="telecom",
            config={"investor_id": "1234567890"},
        )

        raw = (tmp_path / "state_snapshots.json").read_bytes()
        assert snapshot["account_id_masked"] == "12***90"
        assert b"1234567890" not in raw
        assert json.loads(raw.decode("utf-8"))[0]["balance"]["StatusMsg"] == chr(0xDC85)
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_result_writer_escapes_ctp_surrogate_text(tmp_path: Path) -> None:
    """Audit and result evidence must survive legacy CTP text fields too."""
    workspace = WORKSPACES["hongyuan"]
    saved_common_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "common" or name.startswith("common.")
    }
    for name in saved_common_modules:
        sys.modules.pop(name)
    sys.path.insert(0, str(workspace))

    try:
        result_module = importlib.import_module("common.result")
        result = result_module.CaseResult(
            case_id="C01",
            case_name="connect",
            status="PASS",
            details={"system_name": chr(0xDC85)},
            audit_events=[{"details": {"system_name": chr(0xDC85)}}],
        )

        result_module.save_result(result, tmp_path)

        audit_text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
        result_text = (tmp_path / "result.json").read_text(encoding="utf-8")
        assert json.loads(audit_text)["details"]["system_name"] == chr(0xDC85)
        assert json.loads(result_text)["details"]["system_name"] == chr(0xDC85)
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_c01_validates_auth_without_starting_a_market_data_feed() -> None:
    """The login scenario must not depend on a tradable or current contract."""
    case_source = (WORKSPACES["hongyuan"] / "cases/C01_connect_and_login.py").read_text(
        encoding="utf-8"
    )

    assert "record_runtime_events" in case_source
    assert "create_cerebro(" not in case_source
    assert "run_with_timeout(" not in case_source


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
