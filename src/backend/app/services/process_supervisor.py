"""
Process supervisor for live trading strategy subprocesses.

Extracted from LiveTradingManager (123-B) to isolate OS process
management from instance CRUD and gateway lifecycle concerns.
"""

import os
import signal
import sys
import time
from pathlib import Path


def is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Args:
        pid: The process ID to check.

    Returns:
        True if the process is alive, False otherwise.
    """
    if sys.platform == "win32":
        import ctypes

        _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def kill_pid(pid: int, *, force_after_seconds: float = 0.0) -> None:
    """Kill a process by PID.

    Args:
        pid: The process ID to kill.
        force_after_seconds: Seconds to wait after SIGTERM before SIGKILL.
    """
    import logging

    logger = logging.getLogger(__name__)

    if sys.platform == "win32":
        import subprocess as _sp

        try:
            _sp.call(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=_sp.DEVNULL,
                stderr=_sp.DEVNULL,
                creationflags=_sp.CREATE_NO_WINDOW,
            )
        except Exception as e:
            # Process may have already terminated; safe to ignore
            logger.debug("taskkill failed (process may be gone): %s", e)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError) as e:
            # Process may have already terminated; safe to ignore
            logger.debug("SIGTERM failed (process may be gone): %s", e)
            return

        if force_after_seconds <= 0:
            return

        deadline = time.monotonic() + force_after_seconds
        while time.monotonic() < deadline:
            if not is_pid_alive(pid):
                return
            time.sleep(min(0.05, max(deadline - time.monotonic(), 0.0)))

        if not is_pid_alive(pid):
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError) as e:
            logger.debug("SIGKILL failed (process may be gone): %s", e)


def _strategy_run_py_arg(arg: str) -> str | None:
    """Return the run.py path from a process argv item when it is strategy-owned."""
    token = arg.strip().strip("'\"")
    norm = token.replace("\\", "/")
    if not norm.endswith("/run.py"):
        return None
    if "/strategies/" not in norm and "/workspace_units/" not in norm:
        return None
    if not (norm.startswith("/") or (len(norm) >= 3 and norm[1:3] == ":/")):
        return None
    return token


def _scan_running_strategy_pids_procfs(proc_dir: Path | None = None) -> dict[str, int] | None:
    """Scan Linux procfs argv entries for strategy run.py processes.

    Returns None when procfs is unavailable, allowing callers to fall back to ps.
    """
    proc_dir = proc_dir or Path("/proc")
    if not proc_dir.exists():
        return None

    result: dict[str, int] = {}
    try:
        pid_dirs = list(proc_dir.iterdir())
    except OSError:
        return None

    for pid_dir in pid_dirs:
        if not pid_dir.name.isdigit():
            continue
        try:
            raw_cmdline = (pid_dir / "cmdline").read_bytes()
        except OSError:
            continue
        if b"run.py" not in raw_cmdline or (
            b"strategies" not in raw_cmdline and b"workspace_units" not in raw_cmdline
        ):
            continue
        for part in raw_cmdline.split(b"\0"):
            if not part:
                continue
            path = _strategy_run_py_arg(part.decode(errors="ignore"))
            if path is not None:
                result[path] = int(pid_dir.name)
                break

    return result


def _scan_running_strategy_pids_wmic() -> dict[str, int]:
    """Scan Windows process command lines for strategy run.py processes."""
    import subprocess as _sp

    result: dict[str, int] = {}
    out = _sp.check_output(
        [
            "wmic",
            "process",
            "where",
            "CommandLine like '%run.py%'",
            "get",
            "ProcessId,CommandLine",
            "/FORMAT:CSV",
        ],
        text=True,
        timeout=10,
        stderr=_sp.DEVNULL,
        creationflags=_sp.CREATE_NO_WINDOW,
    )
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("node,"):
            continue
        # CSV format: Node,CommandLine,ProcessId
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[-1].strip())
        except ValueError:
            continue
        cmdline = ",".join(parts[1:-1])
        for token in cmdline.split():
            path = _strategy_run_py_arg(token)
            if path is not None:
                result[path] = pid
                break
    return result


def _scan_running_strategy_pids_ps() -> dict[str, int]:
    """Fallback scan using ps output when procfs is unavailable."""
    import subprocess as _sp

    result: dict[str, int] = {}
    out = _sp.check_output(["ps", "-eo", "pid,args"], text=True, timeout=5, stderr=_sp.DEVNULL)
    for line in out.splitlines():
        line = line.strip()
        if "run.py" not in line or ("strategies" not in line and "workspace_units" not in line):
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        args = parts[1]
        for token in args.split():
            path = _strategy_run_py_arg(token)
            if path is not None:
                result[path] = pid
                break
    return result


def scan_running_strategy_pids() -> dict[str, int]:
    """Scan OS processes for running strategy run.py files.

    Returns:
        A dict mapping the absolute run.py path to its PID.
    """
    try:
        if sys.platform == "win32":
            return _scan_running_strategy_pids_wmic()

        procfs_result = _scan_running_strategy_pids_procfs()
        if procfs_result is not None:
            return procfs_result
        return _scan_running_strategy_pids_ps()
    except Exception as e:
        # Process scan is best-effort; log and return empty result
        import logging

        logging.getLogger(__name__).debug("Process scan failed: %s", e)
    return {}
