import os
import shutil
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "ensure_dual_stress_running.sh"
TRUE_BIN = shutil.which("true")
FALSE_BIN = shutil.which("false")

if TRUE_BIN is None or FALSE_BIN is None:  # pragma: no cover - required POSIX fixture
    raise RuntimeError("POSIX true/false commands are required for stress-script tests")


def _fake_dual_stress_process(*, targets: str, monitor: bool) -> subprocess.Popen:
    script_path = PROJECT_ROOT / "src/backend/scripts/run_dual_exchange_simulation.py"
    monitor_flag = " --monitor-only" if monitor else ""
    argv0 = (
        f"{script_path}{monitor_flag} --skip-seed --targets {targets} "
        "--hold-seconds 604800 --status-interval 30"
    )
    return subprocess.Popen(
        ["bash", "-c", f"exec -a '{argv0}' sleep 30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _fake_stuck_dual_stress_supervisor(*, targets: str) -> subprocess.Popen:
    script_path = PROJECT_ROOT / "src/backend/scripts/run_dual_exchange_simulation.py"
    argv0 = (
        f"{script_path} --skip-seed --targets {targets} --hold-seconds 604800 --status-interval 30"
    )
    return subprocess.Popen(
        [
            "bash",
            "-c",
            (f"exec -a '{argv0}' bash -c 'trap \"\" TERM; while true; do sleep 1; done'"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_restart_fails_when_existing_supervisor_does_not_exit(tmp_path: Path) -> None:
    targets = "unit-test-stuck-supervisor"
    stuck_process = _fake_stuck_dual_stress_supervisor(targets=targets)
    try:
        pid_file = tmp_path / "dual_stress.pid"
        log_file = tmp_path / "dual_stress.log"
        pid_file.write_text(str(stuck_process.pid), encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_PID_FILE": str(pid_file),
                "DUAL_STRESS_LOG_FILE": str(log_file),
                "PYTHON_BIN": TRUE_BIN,
                "STOP_TIMEOUT_SECONDS": "1",
                "TARGETS": targets,
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "restart"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 1
        assert (
            f"dual stress supervisor still running after 1s: pid={stuck_process.pid}"
            in result.stderr
        )
        assert "already running" not in result.stdout
        assert "started dual stress supervisor" not in result.stdout
    finally:
        stuck_process.kill()
        stuck_process.wait(timeout=5)


def test_status_discovers_running_monitor_without_pid_file(tmp_path: Path) -> None:
    targets = "unit-test-monitor"
    monitor_process = _fake_dual_stress_process(targets=targets, monitor=True)
    try:
        time.sleep(0.1)
        pid_file = tmp_path / "dual_stress.pid"
        monitor_pid_file = tmp_path / "dual_stress_monitor.pid"
        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_PID_FILE": str(pid_file),
                "DUAL_STRESS_MONITOR_PID_FILE": str(monitor_pid_file),
                "PYTHON_BIN": TRUE_BIN,
                "TARGETS": targets,
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "status"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "dual stress supervisor not running" in result.stdout
        assert f"dual stress monitor running: pid={monitor_process.pid}" in result.stdout
        assert monitor_pid_file.read_text(encoding="utf-8").strip() == str(monitor_process.pid)
    finally:
        monitor_process.kill()
        monitor_process.wait(timeout=5)


def test_status_reports_split_supervisor_pid_files(tmp_path: Path) -> None:
    supervisor_process = _fake_dual_stress_process(
        targets="unit-test-split-supervisor",
        monitor=False,
    )
    try:
        time.sleep(0.1)
        pid_file = tmp_path / "dual_stress.pid"
        split_pid_file = tmp_path / "ctp_remaining_rolling_supervisor.pid"
        split_pid_file.write_text(str(supervisor_process.pid), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_PID_FILE": str(pid_file),
                "DUAL_STRESS_SUPERVISOR_PID_FILES": str(split_pid_file),
                "PYTHON_BIN": TRUE_BIN,
                "TARGETS": "unit-test-no-primary-supervisor",
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "status"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "dual stress supervisor not running" in result.stdout
        assert (
            "split stress supervisor running: "
            f"pid={supervisor_process.pid} file={split_pid_file.name}"
        ) in result.stdout
    finally:
        supervisor_process.kill()
        supervisor_process.wait(timeout=5)


def test_status_removes_stale_split_supervisor_pid_file(tmp_path: Path) -> None:
    pid_file = tmp_path / "dual_stress.pid"
    split_pid_file = tmp_path / "ctp_remaining_rolling_supervisor.pid"
    split_pid_file.write_text("99999999", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "DUAL_STRESS_PID_FILE": str(pid_file),
            "DUAL_STRESS_SUPERVISOR_PID_FILES": str(split_pid_file),
            "PYTHON_BIN": TRUE_BIN,
            "TARGETS": "unit-test-stale-split-supervisor",
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT), "status"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert result.returncode == 0
    assert "split stress supervisors not running" in result.stdout
    assert not split_pid_file.exists()


def test_status_ignores_reused_pid_for_unrelated_split_supervisor_pid_file(
    tmp_path: Path,
) -> None:
    unrelated_process = subprocess.Popen(
        ["sleep", "30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        pid_file = tmp_path / "dual_stress.pid"
        split_pid_file = tmp_path / "ctp_remaining_rolling_supervisor.pid"
        split_pid_file.write_text(str(unrelated_process.pid), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_PID_FILE": str(pid_file),
                "DUAL_STRESS_SUPERVISOR_PID_FILES": str(split_pid_file),
                "PYTHON_BIN": TRUE_BIN,
                "TARGETS": "unit-test-reused-split-supervisor",
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "status"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert "split stress supervisors not running" in result.stdout
        assert f"pid={unrelated_process.pid}" not in result.stdout
        assert not split_pid_file.exists()
    finally:
        unrelated_process.kill()
        unrelated_process.wait(timeout=5)


def test_start_reuses_running_split_supervisor(tmp_path: Path) -> None:
    supervisor_process = _fake_dual_stress_process(
        targets="unit-test-split-start",
        monitor=False,
    )
    try:
        time.sleep(0.1)
        pid_file = tmp_path / "dual_stress.pid"
        log_file = tmp_path / "dual_stress.log"
        split_pid_file = tmp_path / "ctp_remaining_rolling_supervisor.pid"
        split_pid_file.write_text(str(supervisor_process.pid), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_PID_FILE": str(pid_file),
                "DUAL_STRESS_LOG_FILE": str(log_file),
                "DUAL_STRESS_SUPERVISOR_PID_FILES": str(split_pid_file),
                "PYTHON_BIN": FALSE_BIN,
                "TARGETS": "unit-test-no-primary-supervisor",
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "start"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert (
            "split stress supervisor already running: "
            f"pid={supervisor_process.pid}; not starting dual stress supervisor"
        ) in result.stdout
        assert "started dual stress supervisor" not in result.stdout
        assert not pid_file.exists()
    finally:
        supervisor_process.kill()
        supervisor_process.wait(timeout=5)


def test_start_reports_all_running_split_supervisors(tmp_path: Path) -> None:
    first_supervisor = _fake_dual_stress_process(
        targets="unit-test-split-start-first",
        monitor=False,
    )
    second_supervisor = _fake_dual_stress_process(
        targets="unit-test-split-start-second",
        monitor=False,
    )
    try:
        time.sleep(0.1)
        pid_file = tmp_path / "dual_stress.pid"
        log_file = tmp_path / "dual_stress.log"
        first_pid_file = tmp_path / "ctp_remaining_rolling_supervisor.pid"
        second_pid_file = tmp_path / "mt5_remaining_rolling_supervisor.pid"
        first_pid_file.write_text(str(first_supervisor.pid), encoding="utf-8")
        second_pid_file.write_text(str(second_supervisor.pid), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_PID_FILE": str(pid_file),
                "DUAL_STRESS_LOG_FILE": str(log_file),
                "DUAL_STRESS_SUPERVISOR_PID_FILES": (f"{first_pid_file} {second_pid_file}"),
                "PYTHON_BIN": FALSE_BIN,
                "TARGETS": "unit-test-no-primary-supervisor",
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "start"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert (
            "split stress supervisor already running: "
            f"pid={first_supervisor.pid}; not starting dual stress supervisor"
        ) in result.stdout
        assert (
            "split stress supervisor running: "
            f"pid={first_supervisor.pid} file={first_pid_file.name}"
        ) in result.stdout
        assert (
            "split stress supervisor running: "
            f"pid={second_supervisor.pid} file={second_pid_file.name}"
        ) in result.stdout
        assert "started dual stress supervisor" not in result.stdout
        assert not pid_file.exists()
    finally:
        first_supervisor.kill()
        first_supervisor.wait(timeout=5)
        second_supervisor.kill()
        second_supervisor.wait(timeout=5)


def test_monitor_reuses_discovered_running_monitor(tmp_path: Path) -> None:
    targets = "unit-test-monitor-reuse"
    monitor_process = _fake_dual_stress_process(targets=targets, monitor=True)
    try:
        time.sleep(0.1)
        monitor_pid_file = tmp_path / "dual_stress_monitor.pid"
        env = os.environ.copy()
        env.update(
            {
                "DUAL_STRESS_MONITOR_PID_FILE": str(monitor_pid_file),
                "PYTHON_BIN": FALSE_BIN,
                "TARGETS": targets,
            }
        )

        result = subprocess.run(
            ["bash", str(SCRIPT), "monitor"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )

        assert result.returncode == 0
        assert f"dual stress monitor already running: pid={monitor_process.pid}" in result.stdout
        assert monitor_pid_file.read_text(encoding="utf-8").strip() == str(monitor_process.pid)
    finally:
        monitor_process.kill()
        monitor_process.wait(timeout=5)
