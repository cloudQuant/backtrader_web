import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "smoke_ctp_gateway.py"
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
        "worker": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


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
