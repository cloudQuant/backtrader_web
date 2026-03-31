"""
Process supervisor for live trading strategy subprocesses.

Extracted from LiveTradingManager (123-B) to isolate OS process
management from instance CRUD and gateway lifecycle concerns.
"""

import os
import signal
import sys


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
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
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


def kill_pid(pid: int) -> None:
    """Kill a process by PID.

    Args:
        pid: The process ID to kill.
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


def scan_running_strategy_pids() -> dict[str, int]:
    """Scan OS processes for running strategy run.py files.

    Returns:
        A dict mapping the absolute run.py path to its PID.
    """
    import subprocess as _sp

    result: dict[str, int] = {}
    try:
        if sys.platform == "win32":
            out = _sp.check_output(
                ["wmic", "process", "where",
                 "CommandLine like '%run.py%'",
                 "get", "ProcessId,CommandLine", "/FORMAT:CSV"],
                text=True, timeout=10, stderr=_sp.DEVNULL,
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
                    norm = token.replace("\\", "/")
                    if norm.endswith("run.py") and "strategies" in norm:
                        result[token] = pid
                        break
        else:
            out = _sp.check_output(
                ["ps", "-eo", "pid,args"], text=True, timeout=5, stderr=_sp.DEVNULL
            )
            for line in out.splitlines():
                line = line.strip()
                if "run.py" not in line or "strategies" not in line:
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
                    if token.endswith("run.py") and "strategies" in token:
                        result[token] = pid
                        break
    except Exception as e:
        # Process scan is best-effort; log and return empty result
        import logging
        logging.getLogger(__name__).debug("Process scan failed: %s", e)
    return result
