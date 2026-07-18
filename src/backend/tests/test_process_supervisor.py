"""Tests for process supervisor."""

import os
import signal
import sys
from unittest.mock import patch

import pytest

from app.services.process_supervisor import (
    _scan_running_strategy_pids_procfs,
    is_pid_alive,
    kill_pid,
    scan_running_strategy_pids,
)


class TestIsPidAlive:
    def test_current_process_is_alive(self):
        assert is_pid_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        # PID 99999999 almost certainly doesn't exist
        assert is_pid_alive(99999999) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    def test_pid_zero_raises(self):
        # os.kill(0, 0) sends signal to process group — may succeed
        # but this tests the boundary behavior
        result = is_pid_alive(0)
        assert isinstance(result, bool)


class TestKillPid:
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    def test_kill_nonexistent_pid(self):
        """Killing a non-existent PID should not raise."""
        kill_pid(99999999)  # Should log debug and not raise

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    @patch("os.kill")
    def test_sends_sigterm(self, mock_kill):
        kill_pid(12345)
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    @patch("time.sleep", return_value=None)
    @patch("time.monotonic", side_effect=[0.0, 0.2, 0.2])
    @patch("app.services.process_supervisor.is_pid_alive", side_effect=[True, True])
    @patch("os.kill")
    def test_escalates_to_sigkill_when_process_survives_sigterm(
        self,
        mock_kill,
        _mock_alive,
        _mock_monotonic,
        _mock_sleep,
    ):
        kill_pid(12345, force_after_seconds=0.1)

        assert mock_kill.call_args_list[0].args == (12345, signal.SIGTERM)
        assert mock_kill.call_args_list[-1].args == (12345, signal.SIGKILL)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only")
    @patch("os.kill", side_effect=ProcessLookupError)
    def test_handles_process_already_gone(self, mock_kill):
        """Should not raise when process is already terminated."""
        kill_pid(12345)  # No exception


class TestScanRunningStrategyPids:
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    def test_procfs_uses_argv_items_and_ignores_shell_text(self, tmp_path):
        proc_dir = tmp_path / "proc"
        proc_dir.mkdir()
        good_pid = proc_dir / "1234"
        good_pid.mkdir()
        good_path = "/home/user/app/workspace_units/ws-1/unit-1/run.py"
        (good_pid / "cmdline").write_bytes(b"python\0" + good_path.encode() + b"\0--flag\0")

        shell_pid = proc_dir / "2222"
        shell_pid.mkdir()
        (shell_pid / "cmdline").write_bytes(
            b"bash\0-lc\0python - <<'PY'\n"
            b"print('/home/user/app/workspace_units/ws-2/unit-2/run.py')\nPY\0"
        )

        other_pid = proc_dir / "3333"
        other_pid.mkdir()
        (other_pid / "cmdline").write_bytes(b"python\0/home/user/other_project/run.py\0")

        assert _scan_running_strategy_pids_procfs(proc_dir) == {good_path: 1234}

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    @patch("app.services.process_supervisor._scan_running_strategy_pids_procfs", return_value=None)
    @patch("subprocess.check_output")
    def test_finds_strategy_processes(self, mock_output, _mock_procfs):
        mock_output.return_value = (
            "  PID ARGS\n"
            " 1234 python /home/user/strategies/ma_cross/run.py\n"
            " 5678 python /opt/app/server.py\n"
            " 9012 python /home/user/strategies/rsi_strategy/run.py\n"
        )
        result = scan_running_strategy_pids()
        assert len(result) == 2
        assert "/home/user/strategies/ma_cross/run.py" in result
        assert result["/home/user/strategies/ma_cross/run.py"] == 1234

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    @patch("app.services.process_supervisor._scan_running_strategy_pids_procfs", return_value=None)
    @patch("subprocess.check_output")
    def test_finds_workspace_unit_processes(self, mock_output, _mock_procfs):
        mock_output.return_value = (
            "  PID ARGS\n"
            " 2222 python /home/user/app/workspace_units/ws-1/unit-1/run.py\n"
            " 3333 python /home/user/other_project/run.py\n"
        )

        result = scan_running_strategy_pids()

        assert result == {"/home/user/app/workspace_units/ws-1/unit-1/run.py": 2222}

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    @patch("app.services.process_supervisor._scan_running_strategy_pids_procfs", return_value=None)
    @patch("subprocess.check_output")
    def test_empty_output(self, mock_output, _mock_procfs):
        mock_output.return_value = "  PID ARGS\n"
        result = scan_running_strategy_pids()
        assert result == {}

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    @patch("app.services.process_supervisor._scan_running_strategy_pids_procfs", return_value=None)
    @patch("subprocess.check_output", side_effect=Exception("ps failed"))
    def test_handles_scan_failure(self, mock_output, _mock_procfs):
        """Should return empty dict on failure, not raise."""
        result = scan_running_strategy_pids()
        assert result == {}

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    @patch("app.services.process_supervisor._scan_running_strategy_pids_procfs", return_value=None)
    @patch("subprocess.check_output")
    def test_ignores_non_strategy_run_py(self, mock_output, _mock_procfs):
        mock_output.return_value = "  PID ARGS\n 1234 python /home/user/other_project/run.py\n"
        result = scan_running_strategy_pids()
        assert result == {}

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix ps command")
    @patch("app.services.process_supervisor._scan_running_strategy_pids_procfs", return_value=None)
    @patch("subprocess.check_output")
    def test_handles_malformed_lines(self, mock_output, _mock_procfs):
        mock_output.return_value = (
            "  PID ARGS\n bad_pid python /home/user/strategies/test/run.py\n\n 1234\n"
        )
        result = scan_running_strategy_pids()
        assert result == {}
