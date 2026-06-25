import argparse
import asyncio
import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "diagnostics" / "smoke_ctp_gateway.py"
)
SPEC = importlib.util.spec_from_file_location("smoke_ctp_gateway_script", SCRIPT_PATH)
smoke_ctp_gateway = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(smoke_ctp_gateway)


def make_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "strategy_id": "simulate/p_bb_rsi",
        "wait_seconds": 3.0,
        "settle_seconds": 0.5,
        "report_file": str(tmp_path / "ctp_gateway_smoke_report.json"),
        "worker_timeout_seconds": 45.0,
        "worker_grace_seconds": 0.5,
        "poll_interval_seconds": 0.1,
        "ctp_env": "manual",
        "worker": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class _IdleProc:
    returncode = None
    stdout = None
    stderr = None


def test_build_instances_defaults_to_manual_strategy_config_fronts():
    instance = smoke_ctp_gateway.build_instances("inst1", "simulate/p_bb_rsi")["inst1"]

    gateway = instance["params"]["gateway"]
    assert gateway["enabled"] is True
    assert gateway["ctp_env"] == "manual"


def test_build_instances_accepts_explicit_ctp_env():
    instance = smoke_ctp_gateway.build_instances(
        "inst1", "simulate/p_bb_rsi", ctp_env="auto"
    )["inst1"]

    assert instance["params"]["gateway"]["ctp_env"] == "auto"


def test_parent_main_returns_success_when_worker_writes_valid_report(tmp_path, monkeypatch, capsys):
    args = make_args(tmp_path)
    report_path = Path(args.report_file)
    valid_report = {
        "started": True,
        "stopped": True,
        "exception": None,
        "gateway_keys_after_start": ["ctp-future-089763"],
        "gateway_keys_after_stop": [],
        "process_present": True,
        "process_returncode_before_stop": None,
        "final_instance_error": None,
    }

    class FakeProc:
        def __init__(self):
            self.returncode = 0

        def poll(self):
            report_path.write_text(json.dumps(valid_report), encoding="utf-8")
            return self.returncode

    def fake_popen(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(smoke_ctp_gateway.subprocess, "Popen", fake_popen)

    exit_code = smoke_ctp_gateway._parent_main(args)
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["worker_returncode"] == 0
    assert output["worker_timed_out"] is False
    assert output["started"] is True
    assert output["stopped"] is True


def test_parent_main_keeps_valid_report_when_worker_exits_nonzero(tmp_path, monkeypatch, capsys):
    args = make_args(tmp_path)
    report_path = Path(args.report_file)
    valid_report = {
        "started": True,
        "stopped": True,
        "exception": None,
        "gateway_keys_after_start": ["ctp-future-089763"],
        "gateway_keys_after_stop": [],
        "process_present": True,
        "process_returncode_before_stop": None,
        "final_instance_error": None,
    }

    class FakeProc:
        def __init__(self):
            self.returncode = -11

        def poll(self):
            report_path.write_text(json.dumps(valid_report), encoding="utf-8")
            return self.returncode

    def fake_popen(*args, **kwargs):
        return FakeProc()

    monkeypatch.setattr(smoke_ctp_gateway.subprocess, "Popen", fake_popen)

    exit_code = smoke_ctp_gateway._parent_main(args)
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["worker_returncode"] == -11
    assert output["worker_timed_out"] is False
    assert output["started"] is True
    assert output["stopped"] is True
    assert output["final_instance_error"] is None


def test_parent_main_returns_timeout_payload_when_worker_hangs(tmp_path, monkeypatch, capsys):
    args = make_args(
        tmp_path,
        worker_timeout_seconds=1.0,
        worker_grace_seconds=0.1,
        poll_interval_seconds=0.1,
    )
    monotonic_values = iter([0.0, 2.0])

    def fake_monotonic():
        try:
            return next(monotonic_values)
        except StopIteration:
            return 2.0

    class HangingProc:
        def __init__(self, stdout_handle, stderr_handle):
            self.returncode = None
            self.stdout_handle = stdout_handle
            self.stderr_handle = stderr_handle
            self.wait_calls = 0
            self.stdout_handle.write("worker stdout timeout\n")
            self.stdout_handle.flush()
            self.stderr_handle.write("worker stderr timeout\n")
            self.stderr_handle.flush()

        def poll(self):
            return None

        def terminate(self):
            self.returncode = -15

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout)
            return self.returncode

        def kill(self):
            self.returncode = -9

    def fake_popen(*args, **kwargs):
        return HangingProc(kwargs["stdout"], kwargs["stderr"])

    monkeypatch.setattr(smoke_ctp_gateway.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(smoke_ctp_gateway.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(smoke_ctp_gateway.time, "sleep", lambda _: None)

    exit_code = smoke_ctp_gateway._parent_main(args)
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["exception"]["type"] == "WorkerTimeoutError"
    assert output["worker_timed_out"] is True
    assert output["worker_returncode"] == -9
    assert "worker stdout timeout" in output["worker_stdout_tail"]
    assert "worker stderr timeout" in output["worker_stderr_tail"]


def test_parent_main_disables_manual_gateway_restore_for_worker(tmp_path, monkeypatch, capsys):
    args = make_args(tmp_path)
    report_path = Path(args.report_file)
    captured_env = {}
    valid_report = {
        "started": True,
        "stopped": True,
        "exception": None,
        "gateway_keys_after_start": ["ctp-future-089763"],
        "gateway_keys_after_stop": [],
        "process_present": True,
        "process_returncode_before_stop": None,
        "final_instance_error": None,
    }

    class FakeProc:
        def __init__(self):
            self.returncode = 0

        def poll(self):
            report_path.write_text(json.dumps(valid_report), encoding="utf-8")
            return self.returncode

    def fake_popen(*args, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        return FakeProc()

    monkeypatch.setattr(smoke_ctp_gateway.subprocess, "Popen", fake_popen)

    exit_code = smoke_ctp_gateway._parent_main(args)
    json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured_env["LIVE_TRADING_RESTORE_MANUAL_GATEWAYS"] == "false"


def test_collect_ctp_native_diagnostics_reports_extension_state():
    diagnostics = smoke_ctp_gateway.collect_ctp_native_diagnostics()

    assert isinstance(diagnostics["native_loaded"], bool)
    if "diagnostic_error" not in diagnostics:
        assert isinstance(diagnostics["expected_extensions"], list)
        assert isinstance(diagnostics["available_extensions"], list)
        assert diagnostics["python_version"]


def test_collect_external_ctp_runtime_diagnostics_uses_child_processes():
    diagnostics = smoke_ctp_gateway.collect_external_ctp_runtime_diagnostics()

    assert {"ctp", "openctp_ctp"} <= set(diagnostics)
    for item in diagnostics.values():
        assert "ok" in item
        assert "timed_out" in item
        assert "returncode" in item


def test_run_smoke_marks_missing_strategy_runtime_as_blocked(tmp_path, monkeypatch):
    args = make_args(tmp_path, place_test_order=False)

    class FakeManager:
        def __init__(self):
            self._gateways = {}
            self._processes = {}

        async def start_instance(self, instance_id):
            raise ValueError("run.py does not exist: /tmp/missing/run.py")

        def get_gateway_health(self):
            return []

    monkeypatch.setattr(smoke_ctp_gateway, "LiveTradingManager", FakeManager)

    report = asyncio.run(smoke_ctp_gateway.run_smoke(args))

    assert report["e2e_status"] == "BLOCKED"
    assert report["blocked_reason"] == "runtime_prerequisite_missing"
    assert report["exception"]["type"] == "ValueError"
    assert "run.py does not exist" in report["exception"]["message"]
    assert smoke_ctp_gateway._validate_report(report) == 1


def test_run_smoke_marks_gateway_runtime_import_error_as_blocked(tmp_path, monkeypatch):
    args = make_args(tmp_path, place_test_order=False)

    class FakeManager:
        def __init__(self):
            self._gateways = {}
            self._processes = {}

        async def start_instance(self, instance_id):
            raise ImportError(
                "bt_api_base 网关模块无法加载。 ModuleNotFoundError: "
                "No module named 'bt_api_base.gateway.config'"
            )

        def get_gateway_health(self):
            return []

    monkeypatch.setattr(smoke_ctp_gateway, "LiveTradingManager", FakeManager)

    report = asyncio.run(smoke_ctp_gateway.run_smoke(args))

    assert report["e2e_status"] == "BLOCKED"
    assert report["blocked_reason"] == "runtime_prerequisite_missing"
    assert report["exception"]["type"] == "ImportError"
    assert smoke_ctp_gateway._validate_report(report) == 1


def test_run_smoke_uses_generated_runtime_dir(tmp_path, monkeypatch):
    args = make_args(tmp_path, place_test_order=False)
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    (template_dir / "config.yaml").write_text(
        "ctp:\n  fronts:\n    telecom:\n      td_address: tcp://td\n      md_address: tcp://md\n",
        encoding="utf-8",
    )
    captured_instances = {}

    class FakeManager:
        def __init__(self):
            self._gateways = {
                "ctp-future-1": {
                    "config": {},
                    "runtime": object(),
                    "instances": set(),
                }
            }
            self._processes = {}

        async def start_instance(self, instance_id):
            from app.services import live_trading_manager

            captured_instances.update(live_trading_manager._load_instances())
            self._processes[instance_id] = _IdleProc()
            return {"status": "running", "pid": 123}

        async def stop_instance(self, instance_id):
            self._processes.pop(instance_id, None)
            self._gateways.clear()
            return {"status": "stopped"}

        def get_gateway_health(self):
            return [
                {
                    "gateway_key": "ctp-future-1",
                    "selected_ctp_env": "set2_7x24",
                    "td_front": "tcp://td",
                    "md_front": "tcp://md",
                    "selection_reason": "forced_set2",
                    "auth_state": "unknown",
                    "login_state": "unknown",
                    "tick_count": 0,
                    "order_count": 0,
                    "is_healthy": True,
                }
            ]

    monkeypatch.setattr(smoke_ctp_gateway, "get_strategy_dir", lambda _: template_dir)
    monkeypatch.setattr(smoke_ctp_gateway, "LiveTradingManager", FakeManager)
    monkeypatch.setattr(smoke_ctp_gateway, "PROJECT_ROOT", tmp_path)

    report = asyncio.run(smoke_ctp_gateway.run_smoke(args))
    instance = next(iter(captured_instances.values()))
    runtime_dir = Path(instance["runtime_dir"])

    assert runtime_dir == Path(report["runtime_dir"])
    assert (runtime_dir / "run.py").is_file()
    assert (runtime_dir / "config.yaml").is_file()
    assert report["e2e_status"] == "PASS"


def test_collect_gateway_prerequisites_uses_runtime_front_selection(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / ".env").write_text(
        "\n".join(
            [
                "CTP_USER_ID=089763",
                "CTP_BROKER_ID=9999",
                "CTP_PASSWORD=secret",
                "CTP_APP_ID=simnow_client_test",
                "CTP_AUTH_CODE=0000000000000000",
                "CTP_SET1_TD_FRONT_1=tcp://set1-td",
                "CTP_SET1_MD_FRONT_1=tcp://set1-md",
                "CTP_SET2_TD_FRONT=tcp://set2-td",
                "CTP_SET2_MD_FRONT=tcp://set2-md",
            ]
        ),
        encoding="utf-8",
    )
    instance = smoke_ctp_gateway.build_instances(
        "inst1", "simulate/p_bb_rsi", runtime_dir=runtime_dir, ctp_env="auto"
    )["inst1"]

    def fake_build_runtime_kwargs(*args, **kwargs):
        return {
            "account_id": "089763",
            "investor_id": "089763",
            "broker_id": "9999",
            "td_front": "tcp://set2-td",
            "md_front": "tcp://set2-md",
            "selected_ctp_env": "set2_7x24",
            "selection_reason": "auto_regular_session_set1_unreachable",
            "requested_ctp_env": "auto",
            "set1_group": "1",
        }

    monkeypatch.setattr(
        smoke_ctp_gateway.gateway_launch_builder,
        "build_ctp_gateway_runtime_kwargs",
        fake_build_runtime_kwargs,
    )

    result = smoke_ctp_gateway.collect_gateway_prerequisites(instance, runtime_dir)

    assert result["missing_required_fields"] == []
    assert result["selected_ctp_env"] == "set2_7x24"
    assert result["td_front"] == "tcp://set2-td"
    assert result["selection_reason"] == "auto_regular_session_set1_unreachable"


def test_collect_gateway_prerequisites_defaults_to_strategy_simnow_fronts(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "config.yaml").write_text(
        "\n".join(
            [
                "ctp:",
                "  app_id: simnow_client_test",
                "  auth_code: '0000000000000000'",
                "  fronts:",
                "    telecom:",
                "      td_address: tcp://simnow-td",
                "      md_address: tcp://simnow-md",
                "live:",
                "  network: telecom",
            ]
        ),
        encoding="utf-8",
    )
    (runtime_dir / ".env").write_text(
        "\n".join(
            [
                "CTP_USER_ID=089763",
                "CTP_BROKER_ID=9999",
                "CTP_PASSWORD=secret",
            ]
        ),
        encoding="utf-8",
    )
    instance = smoke_ctp_gateway.build_instances(
        "inst1", "simulate/p_bb_rsi", runtime_dir=runtime_dir
    )["inst1"]

    result = smoke_ctp_gateway.collect_gateway_prerequisites(instance, runtime_dir)

    assert result["missing_required_fields"] == []
    assert result["selected_ctp_env"] == "custom_front"
    assert result["requested_ctp_env"] == "manual"
    assert result["td_front"] == "tcp://simnow-td"
    assert result["md_front"] == "tcp://simnow-md"


def test_run_smoke_marks_missing_ctp_credentials_as_blocked(tmp_path, monkeypatch):
    args = make_args(tmp_path, place_test_order=False)
    template_dir = tmp_path / "template"
    template_dir.mkdir()

    class FakeManager:
        def __init__(self):
            self._gateways = {}
            self._processes = {}

        async def start_instance(self, instance_id):
            self._processes[instance_id] = _IdleProc()
            return {"status": "running", "pid": 456}

        async def stop_instance(self, instance_id):
            self._processes.pop(instance_id, None)
            return {"status": "stopped"}

        def get_gateway_health(self):
            return []

    monkeypatch.setattr(smoke_ctp_gateway, "get_strategy_dir", lambda _: template_dir)
    monkeypatch.setattr(smoke_ctp_gateway, "LiveTradingManager", FakeManager)
    monkeypatch.setattr(smoke_ctp_gateway, "PROJECT_ROOT", tmp_path)

    report = asyncio.run(smoke_ctp_gateway.run_smoke(args))

    assert report["e2e_status"] == "BLOCKED"
    assert report["blocked_reason"] == "credentials_unavailable"
    assert report["gateway_prerequisites"]["requested_ctp_env"] == "manual"
    assert set(report["gateway_prerequisites"]["missing_required_fields"]) >= {
        "investor_id",
        "broker_id",
        "password",
    }
    assert smoke_ctp_gateway._validate_report(report) == 1
