"""Regression tests for the CTP certification strategy workspaces.

These tests intentionally exercise the command-line entry points.  A dry run
must stay entirely offline: it is safe to run on a development machine without
CTP credentials or an active trading session.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_hongyuan_config_loads_credentials_from_reference_workspace_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The relocated workspace may reuse an explicitly configured source .env.

    The test fixture contains only disposable values.  It verifies discovery
    order without reading the developer's real credential files.
    """
    workspace = WORKSPACES["hongyuan"]
    reference_root = tmp_path / "backtrader"
    credential_file = (
        reference_root
        / "examples/007_ctp/live_certification/hongyuan_penetration/.env"
    )
    credential_file.parent.mkdir(parents=True)
    credential_file.write_text(
        "HONGYUAN_USER_ID=test-investor\nHONGYUAN_PASSWORD=test-password\n",
        encoding="utf-8",
    )

    saved_common_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "common" or name.startswith("common.")
    }
    for name in saved_common_modules:
        sys.modules.pop(name)
    sys.path.insert(0, str(workspace))
    monkeypatch.delenv("HONGYUAN_USER_ID", raising=False)
    monkeypatch.delenv("hongyuan_user_id", raising=False)
    monkeypatch.delenv("HONGYUAN_PASSWORD", raising=False)
    monkeypatch.delenv("hongyuan_password", raising=False)
    monkeypatch.setenv("BACKTRADER_REFERENCE_ROOT", str(reference_root))

    try:
        config = importlib.import_module("common.config")

        assert config.get_credentials() == ("test-investor", "test-password")
        assert os.getenv("HONGYUAN_USER_ID") is None
        assert os.getenv("HONGYUAN_PASSWORD") is None
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_runner_retries_an_empty_native_startup_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pre-start native crash may be retried once without duplicating an order."""
    workspace = WORKSPACES["hongyuan"]
    module_path = workspace / "run_case.py"
    saved_common_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "common" or name.startswith("common.")
    }
    for name in saved_common_modules:
        sys.modules.pop(name)
    sys.path.insert(0, str(workspace))

    try:
        spec = importlib.util.spec_from_file_location("hongyuan_case_runner", module_path)
        assert spec is not None
        assert spec.loader is not None
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)

        call_count = 0

        def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
            nonlocal call_count
            call_count += 1
            report_dir = tmp_path / "T01"
            if call_count == 1:
                report_dir.mkdir(parents=True, exist_ok=True)
                (report_dir / "stdout.log").touch()
                return SimpleNamespace(returncode=-11, stdout="", stderr="")
            (report_dir / "result.json").write_text(
                json.dumps({"case_id": "T01", "status": "BLOCKED"}),
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=2, stdout="", stderr="")

        monkeypatch.setattr(runner.subprocess, "run", fake_run)
        monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

        result = runner.run_case("T01", tmp_path)

        assert result["status"] == "BLOCKED"
        assert call_count == 2
        retry = json.loads((tmp_path / "T01" / "startup_retry.json").read_text())
        assert retry == {"first_exit_code": -11, "retry_delay_seconds": 2}
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


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


def test_hongyuan_create_cerebro_injects_store_seed_bars_into_live_feed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seed bars registered on the Store must reach the live feed at startup."""
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
        captured: dict[str, dict[str, object]] = {}

        class FakeBroker:
            """No-network broker constructor spy."""

            def __init__(self, *, store: object, **kwargs: object) -> None:
                captured["broker"] = {"store": store, **kwargs}

        class FakeFeed:
            """No-network feed constructor spy."""

            def __init__(self, **kwargs: object) -> None:
                captured["feed"] = kwargs

        class FakeCerebro:
            """Minimal Cerebro stand-in used only for constructor wiring."""

            def setbroker(self, _broker: object) -> None:
                pass

            def adddata(self, _data: object) -> None:
                pass

        monkeypatch.setattr(runtime, "BtApiBroker", FakeBroker)
        monkeypatch.setattr(runtime, "BtApiFeed", FakeFeed)
        monkeypatch.setattr(runtime.bt, "Cerebro", FakeCerebro)

        seed_bars = [{"datetime": "2026-09-04T00:00:00", "close": 3000.0}]
        store = type("Store", (), {"_historical_bars": {"rb-test": seed_bars}})()
        runtime.create_cerebro(store, symbol="rb-test")

        assert captured["feed"]["historical_bars"] == seed_bars
        assert captured["feed"]["backfill_start"] is False
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_wait_for_live_market_price_uses_the_ctp_quote_cache() -> None:
    """Remote order probes must seed from a live, valid CTP price rather than 3000."""
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
            def __init__(self) -> None:
                self._api = SimpleNamespace(_last_tick_price={"rb2610": 3501.0})
                self.subscribed: list[str] = []

            def subscribe(self, symbol: str) -> None:
                self.subscribed.append(symbol)

        store = FakeStore()

        assert runtime.wait_for_live_market_price(store, "SHFE.rb2610", timeout_seconds=0.1) == 3501.0
        assert store.subscribed == ["SHFE.rb2610"]
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_remote_validation_only_disables_local_cash_precheck_when_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ordinary runtime keeps local cash checks; certified remote runs do not."""
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
        broker_kwargs: list[dict[str, object]] = []

        class FakeBroker:
            """No-network broker constructor spy."""

            def __init__(self, *, store: object, **kwargs: object) -> None:
                broker_kwargs.append({"store": store, **kwargs})

        monkeypatch.setattr(runtime, "BtApiBroker", FakeBroker)
        monkeypatch.delenv(runtime.REMOTE_VALIDATION_ENV, raising=False)
        runtime.create_broker(object())
        monkeypatch.setenv(runtime.REMOTE_VALIDATION_ENV, "1")
        runtime.create_broker(object())

        assert "cash_check_enabled" not in broker_kwargs[0]
        assert broker_kwargs[1]["cash_check_enabled"] is False
        assert broker_kwargs[1]["cancel_wait_remote"] is True
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_remote_negative_close_probe_bypasses_only_position_precheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E02 may reach CTP only for a bounded explicit close-position probe."""
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
        monkeypatch.setenv(runtime.REMOTE_VALIDATION_ENV, "1")

        class FakeBroker:
            def _ensure_required_net_offset(self, _order: object):
                return "close_size_exceeds_position", "no closeable position"

        close_order = SimpleNamespace(info={"offset": "close_today"})
        opening_order = SimpleNamespace(info={"offset": "open"})
        broker = FakeBroker()

        runtime._enable_remote_negative_close_probe(broker)

        assert broker._ensure_required_net_offset(close_order) is None
        assert broker._ensure_required_net_offset(opening_order) == (
            "close_size_exceeds_position",
            "no closeable position",
        )
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_remote_order_preflight_blocks_zero_available_funds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit live certification must not queue normal orders with zero funds."""
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

        class ZeroAvailableFundsStore:
            """No-network account response with no spendable certification funds."""

            def get_balance(self) -> dict[str, float]:
                return {"cash": 0.0}

        class PositiveAvailableFundsStore:
            """No-network account response that permits the order flow."""

            def get_balance(self) -> dict[str, float]:
                return {"Available": 1.0}

        monkeypatch.setenv(runtime.REMOTE_VALIDATION_ENV, "1")
        blocked = runtime.build_order_preflight_block(
            ZeroAvailableFundsStore(), "T01"
        )

        assert isinstance(blocked, runtime.CertificationBlocked)
        assert not isinstance(blocked, Exception)
        assert blocked.details == {
            "preflight": "available_funds",
            "available_funds": "zero",
            "counter_order_submitted": False,
        }
        assert runtime.build_order_preflight_block(ZeroAvailableFundsStore(), "C01") is None
        assert runtime.build_order_preflight_block(PositiveAvailableFundsStore(), "T01") is None

        class UnrelatedPositionStore:
            """A position in another contract must not authorize a close test."""

            def get_positions(self) -> list[dict[str, object]]:
                return [{"instrument": "other", "volume": 1}]

        close_blocked = runtime.build_order_preflight_block(
            UnrelatedPositionStore(), "T02", symbol="rb-test"
        )
        assert isinstance(close_blocked, runtime.CertificationBlocked)
        assert close_blocked.details == {
            "preflight": "target_position",
            "target_position": "absent",
            "counter_order_submitted": False,
        }

        monkeypatch.delenv(runtime.REMOTE_VALIDATION_ENV, raising=False)
        assert runtime.build_order_preflight_block(ZeroAvailableFundsStore(), "T01") is None
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_run_with_timeout_drains_pending_broker_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A final broker drain preserves async CTP callbacks after the last bar."""
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

        class FakeTimer:
            """Timer stand-in that never calls its callback."""

            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.daemon = False

            def start(self) -> None:
                pass

            def cancel(self) -> None:
                pass

        class FakeBroker:
            """Records the explicit terminal update drain."""

            def __init__(self) -> None:
                self.drain_count = 0

            def next(self) -> None:
                self.drain_count += 1

        class FakeCerebro:
            """Minimal completed cerebro run."""

            def __init__(self) -> None:
                self.broker = FakeBroker()

            def run(self) -> list[object]:
                return []

            def runstop(self) -> None:
                pass

        monkeypatch.setattr(runtime.threading, "Timer", FakeTimer)
        cerebro = FakeCerebro()

        assert runtime.run_with_timeout(cerebro, timeout_seconds=1) == []
        assert cerebro.broker.drain_count == 1
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


def test_hongyuan_reconciliation_ignores_unrelated_position_snapshot_fluctuation(
    tmp_path: Path,
) -> None:
    """A no-order case only guards the selected test contract's position."""
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
        (tmp_path / "state_snapshots.json").write_text(
            json.dumps(
                [
                    {
                        "label": "before_action",
                        "balance": {"cash": 100.0, "value": 100.0},
                        "positions": [{"instrument": "other", "volume": 1}],
                        "tracked_symbol": "rb-test",
                        "tracked_positions": [],
                        "open_orders": [],
                    },
                    {
                        "label": "after_action_before_stop",
                        "balance": {"cash": 100.0, "value": 100.0},
                        "positions": [],
                        "tracked_symbol": "rb-test",
                        "tracked_positions": [],
                        "open_orders": [],
                    },
                ]
            ),
            encoding="utf-8",
        )
        result = SimpleNamespace(
            case_id="EM02",
            details={},
            observed_events=["strategy_trading_paused"],
            required_events=["strategy_trading_paused"],
            missing_required_events=[],
            required_events_present=True,
            scenario_id="EMERGENCY-02",
        )

        reconciliation = evidence.build_reconciliation(result, tmp_path)

        assert reconciliation["account_delta"]["positions_changed"] is True
        assert reconciliation["account_delta"]["tracked_positions_changed"] is False
        assert reconciliation["checks"]["account_position_unchanged"]["passed"] is True
        assert reconciliation["strict_reconciliation_pass"] is True
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_ctp_bridge_uses_session_order_ref_and_correlates_response_error() -> None:
    """A bare CTP response error must be tied to the matching CTP order request."""
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
        bridge = importlib.import_module("common.ctp_callback_bridge")

        class FakeTrader:
            """A session whose CTP counter already assigned an order reference."""

            def __init__(self) -> None:
                self._req_id = 7
                self._max_order_ref = 41
                self._error_event: dict[str, object] | None = None

            def next_order_ref(self) -> str:
                self._max_order_ref += 1
                return str(self._max_order_ref)

            def wait_error_event(self, timeout: float = 0) -> dict[str, object] | None:
                del timeout
                event, self._error_event = self._error_event, None
                return event

        class FakeApi:
            """Minimal CTP wrapper surface used by the certification bridge."""

            def __init__(self) -> None:
                self.trader_client = FakeTrader()
                self.received_payload: dict[str, object] | None = None

            def _next_request_id(self) -> int:
                self.trader_client._req_id += 1
                return self.trader_client._req_id

            def submit_order(self, payload: dict[str, object]) -> dict[str, object]:
                self.received_payload = dict(payload)
                request_id = self._next_request_id()
                self.trader_client._error_event = {
                    "event": "response_error",
                    "request_id": request_id,
                    "error_id": 101,
                    "error_msg": "counter rejection",
                    "field": {},
                }
                return {"order_ref": payload["order_ref"]}

        api = FakeApi()
        bridge.install_ctp_callback_bridge(SimpleNamespace(_api=api))

        response = api.submit_order({"bt_order_ref": 1, "symbol": "rb-test"})
        error_event = api.trader_client.wait_error_event()

        assert api.received_payload is not None
        assert api.received_payload["order_ref"] == "42"
        assert response == {"order_ref": "42"}
        assert error_event is not None
        assert error_event["field"] == {"OrderRef": "42", "bt_order_ref": 1}
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_ctp_bridge_leaves_unmatched_query_errors_unassociated() -> None:
    """A retryable account-query error must never be presented as an order rejection."""
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
        bridge = importlib.import_module("common.ctp_callback_bridge")

        class FakeTrader:
            def __init__(self) -> None:
                self._error_event = {
                    "event": "response_error",
                    "request_id": 999,
                    "error_id": 90,
                    "error_msg": "retry later",
                    "field": {},
                }

            def next_order_ref(self) -> str:
                return "42"

            def wait_error_event(self, timeout: float = 0) -> dict[str, object] | None:
                del timeout
                event, self._error_event = self._error_event, None
                return event

        class FakeApi:
            def __init__(self) -> None:
                self.trader_client = FakeTrader()

            def _next_request_id(self) -> int:
                return 8

            def submit_order(self, payload: dict[str, object]) -> dict[str, object]:
                del payload
                return {"order_ref": "42"}

        api = FakeApi()
        bridge.install_ctp_callback_bridge(SimpleNamespace(_api=api))

        error_event = api.trader_client.wait_error_event()

        assert error_event is not None
        assert error_event["field"] == {}
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_ctp_query_callback_emits_a_safe_normalized_order_row() -> None:
    """The CTP order-query callback must expose no account credentials."""
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
        bridge = importlib.import_module("common.ctp_callback_bridge")

        class Done:
            def __init__(self) -> None:
                self.called = False

            def set(self) -> None:
                self.called = True

        class FakeOrder:
            InstrumentID = "rb-test"
            ExchangeID = "SHFE"
            OrderRef = "42"
            OrderSysID = "sys-test"
            OrderStatus = "3"
            OrderSubmitStatus = "0"
            Direction = "0"
            CombOffsetFlag = "0"
            LimitPrice = 3000.0
            VolumeTotalOriginal = 1
            VolumeTraded = 0
            VolumeTotal = 1

        trader = SimpleNamespace(
            _hongyuan_ctp_order_query_rows=[],
            _hongyuan_ctp_order_query_error_id=0,
            _hongyuan_ctp_order_query_done=Done(),
        )
        spi = SimpleNamespace(_c=trader)

        bridge._on_rsp_qry_order(spi, FakeOrder(), SimpleNamespace(ErrorID=0), 8, True)

        assert trader._hongyuan_ctp_order_query_done.called is True
        assert trader._hongyuan_ctp_order_query_rows == [
            {
                "id": "sys-test",
                "external_order_id": "sys-test",
                "order_ref": "42",
                "symbol": "rb-test",
                "instrument": "rb-test",
                "exchange_id": "SHFE",
                "status": "accepted",
                "side": "buy",
                "offset": "open",
                "price": 3000.0,
                "size": 1,
                "filled": 0,
                "remaining": 1,
            }
        ]
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_ctp_query_callback_patches_the_active_spi_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bridge must patch the CTP package actually selected by BtApiStore."""
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
        bridge = importlib.import_module("common.ctp_callback_bridge")

        class ActiveSpi:
            pass

        ActiveSpi.__module__ = "active_ctp.ctp.client"
        active_module = SimpleNamespace(_TraderSpi=ActiveSpi)
        monkeypatch.setattr(
            bridge.importlib,
            "import_module",
            lambda name: active_module
            if name == "active_ctp.ctp.client"
            else (_ for _ in ()).throw(ImportError(name)),
        )

        assert bridge.enable_ctp_order_query_callback(SimpleNamespace(_spi=ActiveSpi()))
        assert ActiveSpi.OnRspQryOrder is bridge._on_rsp_qry_order
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_ctp_query_bridge_waits_for_a_counter_response() -> None:
    """Open-order reconciliation must not turn an unavailable query into an empty list."""
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
        bridge = importlib.import_module("common.ctp_callback_bridge")

        class Done:
            def __init__(self) -> None:
                self.called = False

            def clear(self) -> None:
                self.called = False

            def wait(self, _timeout: float) -> bool:
                return self.called

            def set(self) -> None:
                self.called = True

        class FakeQueryField:
            BrokerID = ""
            InvestorID = ""

        class FakeNativeApi:
            def __init__(self, trader: object) -> None:
                self.trader = trader
                self.request_id: int | None = None

            def ReqQryOrder(self, _field: object, request_id: int) -> int:
                self.request_id = request_id
                self.trader._hongyuan_ctp_order_query_rows = [
                    {"status": "accepted", "order_ref": "42"},
                    {"status": "canceled", "order_ref": "43"},
                ]
                self.trader._hongyuan_ctp_order_query_done.set()
                return 0

        trader = SimpleNamespace(
            is_ready=True,
            broker_id="broker",
            user_id="investor",
            _req_id=7,
            _hongyuan_ctp_order_query_done=Done(),
            _hongyuan_ctp_order_query_rows=[],
            _hongyuan_ctp_order_query_error_id=0,
        )
        trader.api = FakeNativeApi(trader)
        api = SimpleNamespace(trader_client=trader)

        rows = bridge.query_ctp_open_orders(
            api,
            timeout_seconds=0.1,
            field_factory=FakeQueryField,
        )

        assert rows == [{"status": "accepted", "order_ref": "42"}]
        assert trader.api.request_id == 8
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_registers_ctp_order_query_callback_before_connecting() -> None:
    """The native SPI must receive OnRspQryOrder before TraderClient starts."""
    source = (WORKSPACES["hongyuan"] / "common/runtime.py").read_text(encoding="utf-8")

    assert source.index("enable_ctp_order_query_callback()") < source.index("store.start()")


def test_hongyuan_started_store_installs_ctp_callback_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every live certification connection must activate the local CTP bridge."""
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
        bridge_calls: list[object] = []

        class FakeStore:
            def __init__(self, **_kwargs: object) -> None:
                self.started = False
                self.stopped = False

            def start(self) -> None:
                self.started = True

            def stop(self) -> None:
                self.stopped = True

        monkeypatch.setattr(runtime, "BtApiStore", FakeStore)
        monkeypatch.setattr(runtime.cfg, "get_env_key", lambda: "telecom")
        monkeypatch.setattr(
            runtime.cfg,
            "create_config",
            lambda _env_key: {
                "td_address": "tcp://test-td",
                "md_address": "tcp://test-md",
                "investor_id": "test-user",
            },
        )
        monkeypatch.setitem(runtime.cfg.HONGYUAN_ENVIRONMENTS, "telecom", {"name": "test"})
        monkeypatch.setattr(
            runtime,
            "install_ctp_callback_bridge",
            lambda store: bridge_calls.append(store),
        )

        with runtime.started_store("telecom") as (store, _config, _env_key):
            assert store.started is True

        assert bridge_calls == [store]
        assert store.stopped is True
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_local_submit_ack_is_not_treated_as_counter_acceptance() -> None:
    """A CTP client-side request id is not a counter-side order acceptance."""
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

        assert "order_status_accepted" not in evidence._event_aliases(
            {"event_type": "order_submit_accepted", "order_ref": "client-ref"}
        )
        assert "order_status_accepted" in evidence._event_aliases(
            {
                "event_type": "order_submit_accepted",
                "external_order_id": "counter-order-id",
            }
        )
    finally:
        sys.path.remove(str(workspace))
        for name in [
            name
            for name in sys.modules
            if name == "common" or name.startswith("common.")
        ]:
            sys.modules.pop(name)
        sys.modules.update(saved_common_modules)


def test_hongyuan_helper_collects_runtime_events_from_all_log_streams(tmp_path: Path) -> None:
    """Certification decisions must see monitor events as well as system events."""
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
        helpers = importlib.import_module("common.helpers")
        (tmp_path / "system.log").write_text(
            json.dumps({"event_type": "store_ready"}) + "\n", encoding="utf-8"
        )
        (tmp_path / "monitor.log").write_text(
            json.dumps({"event_type": "order_cancel_request"}) + "\n", encoding="utf-8"
        )

        assert helpers.collect_log_event_types(tmp_path) == {
            "store_ready",
            "order_cancel_request",
        }
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


def test_hongyuan_t03_waits_for_a_remote_cancel_terminal_status() -> None:
    """T03 must not stop merely because the local CTP client queued a request."""
    case_source = (WORKSPACES["hongyuan"] / "cases/T03_cancel_order.py").read_text(
        encoding="utf-8"
    )

    assert 'if status in ("Canceled", "Rejected", "Completed"):' in case_source
    assert 'if status in ("Submitted", "Accepted", "Completed", "Canceled", "Rejected"):' not in case_source


def test_hongyuan_e01_uses_a_bounded_insufficient_funds_probe() -> None:
    """The remote insufficient-funds test must never fan out a large order batch."""
    module_path = WORKSPACES["hongyuan"] / "cases/E01_insufficient_funds.py"
    spec = importlib.util.spec_from_file_location("ctp_hongyuan_e01", module_path)

    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.PROBE_ORDER_SIZE == 1
    assert module.PROBE_ORDER_COUNT == 1
    assert module.REMOTE_RESPONSE_TIMEOUT_SECONDS == 35


def test_hongyuan_e01_reports_a_safe_block_when_a_passive_probe_is_accepted() -> None:
    """A safely canceled passive order is not evidence of an insufficient-funds error."""
    source = (WORKSPACES["hongyuan"] / "cases/E01_insufficient_funds.py").read_text(
        encoding="utf-8"
    )

    assert "柜台接受并允许撤销受控一手被动委托" in source
    assert "timer.blocked_result(" in source


def test_hongyuan_e02_uses_the_scoped_remote_close_rejection_path() -> None:
    """E02 must test the counter response, not stop at the local position guard."""
    source = (WORKSPACES["hongyuan"] / "cases/E02_insufficient_position.py").read_text(
        encoding="utf-8"
    )

    assert "remote_negative_close_probe=True" in source
    assert "validation_enabled=False" in source
    assert "record_runtime_events(" in source
    assert "wait_for_live_market_price" in source
    assert 'Path(log_dir).glob("*.log")' in source


def test_hongyuan_error_cases_require_their_specific_counter_error_semantics() -> None:
    """An expired contract must not make E01/E02 look like a valid negative test."""
    modules: dict[str, object] = {}
    for case_id, filename in {
        "E01": "E01_insufficient_funds.py",
        "E02": "E02_insufficient_position.py",
    }.items():
        module_path = WORKSPACES["hongyuan"] / "cases" / filename
        spec = importlib.util.spec_from_file_location(f"ctp_hongyuan_{case_id}_semantics", module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[case_id] = module

    expired_contract_error = {"ErrorID": "16", "ErrorMsg": "CTP:找不到合约"}
    transient_counter_error = {
        "event_type": "order_reject_remote",
        "ErrorMsg": "已撤单报单被拒绝SHFE:结算组数据没有同步",
    }
    assert modules["E01"]._matches_insufficient_funds_error(expired_contract_error) is False
    assert modules["E02"]._matches_insufficient_position_error(expired_contract_error) is False
    assert modules["E01"]._matches_insufficient_funds_error({"ErrorMsg": "可用资金不足"})
    assert modules["E02"]._matches_insufficient_position_error({"ErrorMsg": "可平持仓不足"})
    assert modules["E01"]._normalize_remote_counter_error(transient_counter_error) is not None
    assert modules["E01"]._matches_funds_precondition_error(transient_counter_error)

    for filename in ("E01_insufficient_funds.py", "E02_insufficient_position.py"):
        source = (WORKSPACES["hongyuan"] / "cases" / filename).read_text(encoding="utf-8")
        assert "wait_for_live_market_price" in source


def test_hongyuan_default_contract_is_a_live_certification_contract() -> None:
    """Keep the workspace default off the expired rb2605 contract."""
    source = (WORKSPACES["hongyuan"] / "common/config.py").read_text(encoding="utf-8")

    assert 'DEFAULT_ORDER_SYMBOL = "rb2610"' in source
    assert 'DEFAULT_TICK_SYMBOL = "rb2610"' in source


def test_hongyuan_docx_conclusion_uses_the_configurable_certification_contract() -> None:
    """Formal reports must not reintroduce the retired fixed contract name."""
    source = (WORKSPACES["hongyuan"] / "fill_docx_report.py").read_text(encoding="utf-8")

    assert "def certification_order_symbol" in source
    assert '"rb2605"' not in source


def test_hongyuan_e01_records_post_run_ctp_callbacks_before_evaluating_result() -> None:
    """Async callbacks arriving after the final broker drain must remain evidence."""
    source = (WORKSPACES["hongyuan"] / "cases/E01_insufficient_funds.py").read_text(
        encoding="utf-8"
    )

    assert "record_runtime_events" in source
    assert "store.get_notifications()" in source
    assert "helpers.collect_log_event_types(log_dir)" in source
    assert "for path in sorted(Path(log_dir).glob(\"*.log\"))" in source
    assert "stop_on_exit=False" not in source


@pytest.mark.parametrize("case_id", ["V01", "V02", "E02", "EM01", "L04"])
def test_hongyuan_local_rejection_cases_seed_a_deterministic_live_feed(
    case_id: str,
) -> None:
    """Local-rejection cases must not depend on an external CTP bar arrival."""
    case_file = next((WORKSPACES["hongyuan"] / "cases").glob(f"{case_id}_*.py"))
    source = case_file.read_text(encoding="utf-8")

    assert "seed_bar = {" in source
    assert "store.set_history(symbol, [seed_bar])" in source


def test_hongyuan_e02_marks_local_position_rejection_as_blocked_not_remote_failure() -> None:
    """A local safety rejection cannot be presented as a failed CTP callback."""
    source = next(
        (WORKSPACES["hongyuan"] / "cases").glob("E02_*.py")
    ).read_text(encoding="utf-8")

    assert "runtime_event_types = record_runtime_events(" in source
    assert "helpers.collect_log_event_types(log_dir)" in source
    assert "if local_rejection and not remote_errors:" in source
    assert "本地持仓校验已拒绝订单" in source


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
