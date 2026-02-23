"""
Live trading instance manager.

Manages strategy instances (CRUD/start/stop). Uses a JSON file for persistence and runs strategies
in subprocesses.
"""
import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id

logger = logging.getLogger(__name__)

# Persistence file
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"


def _load_instances() -> Dict[str, dict]:
    """Load instances from the JSON file.

    Returns:
        A dictionary of instances keyed by instance ID.
    """
    if _INSTANCES_FILE.is_file():
        try:
            return json.loads(_INSTANCES_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def _save_instances(data: Dict[str, dict]):
    """Save instances to the JSON file.

    Args:
        data: The instances dictionary to save.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _INSTANCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _find_latest_log_dir(strategy_dir: Path) -> Optional[str]:
    """Find the latest log directory for a strategy.

    Args:
        strategy_dir: The strategy directory path.

    Returns:
        The path to the latest log directory, or None if not found.
    """
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return None
    subdirs = sorted(logs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in subdirs:
        if d.is_dir():
            return str(d)
    return None


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Args:
        pid: The process ID to check.

    Returns:
        True if the process is alive, False otherwise.
    """
    try:
        import os
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class LiveTradingManager:
    """Live trading manager (singleton pattern usage).

    Attributes:
        _processes: Dictionary of running subprocesses by instance ID.
    """

    def __init__(self):
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        # Sync process status on startup
        self._sync_status_on_boot()

    def _sync_status_on_boot(self):
        """Check if previously running instances are still running on startup.

        Updates the status of instances that were marked as 'running'
        but whose processes are no longer alive.
        """
        instances = _load_instances()
        changed = False
        for iid, inst in instances.items():
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
                    changed = True
        if changed:
            _save_instances(instances)

    # ---- CRUD ----

    def list_instances(self, user_id: str = None) -> List[dict]:
        """List live trading instances, optionally filtered by user.

        Args:
            user_id: Optional user ID to filter instances.

        Returns:
            A list of instance dictionaries.
        """
        instances = _load_instances()
        result = []
        for iid, inst in instances.items():
            # Filter by user
            if user_id and inst.get("user_id") and inst["user_id"] != user_id:
                continue
            # Real-time status refresh
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
            inst["id"] = iid
            # Latest log directory
            strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
            inst["log_dir"] = _find_latest_log_dir(strategy_dir)
            result.append(inst)
        # Save refreshed status
        _save_instances({r["id"]: {k: v for k, v in r.items()} for r in result})
        return result

    def add_instance(self, strategy_id: str, params: Optional[Dict[str, Any]] = None, user_id: str = None) -> dict:
        """Add a new live trading instance.

        Args:
            strategy_id: The strategy ID.
            params: Optional strategy parameter overrides.
            user_id: Optional user ID who owns the instance.

        Returns:
            The created instance dictionary.

        Raises:
            ValueError: If the strategy doesn't exist or lacks run.py.
        """
        strategy_dir = STRATEGIES_DIR / strategy_id
        if not (strategy_dir / "run.py").is_file():
            raise ValueError(f"Strategy {strategy_id} does not exist or lacks run.py")

        tpl = get_template_by_id(strategy_id)
        name = tpl.name if tpl else strategy_id

        iid = str(uuid.uuid4())[:8]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst = {
            "id": iid,
            "strategy_id": strategy_id,
            "strategy_name": name,
            "user_id": user_id,
            "status": "stopped",
            "pid": None,
            "error": None,
            "params": params or {},
            "created_at": now,
            "started_at": None,
            "stopped_at": None,
            "log_dir": _find_latest_log_dir(strategy_dir),
        }

        instances = _load_instances()
        instances[iid] = inst
        _save_instances(instances)
        return inst

    def remove_instance(self, instance_id: str, user_id: str = None) -> bool:
        """Remove a live trading instance.

        Args:
            instance_id: The instance ID to remove.
            user_id: Optional user ID for permission check.

        Returns:
            True if the instance was removed, False otherwise.
        """
        instances = _load_instances()
        if instance_id not in instances:
            return False
        inst = instances[instance_id]
        if user_id and inst.get("user_id") and inst["user_id"] != user_id:
            return False
        # Stop first if running
        if inst.get("status") == "running" and inst.get("pid"):
            self._kill_pid(inst["pid"])
        del instances[instance_id]
        _save_instances(instances)
        self._processes.pop(instance_id, None)
        return True

    def get_instance(self, instance_id: str, user_id: str = None) -> Optional[dict]:
        """Get a live trading instance by ID.

        Args:
            instance_id: The instance ID.
            user_id: Optional user ID for permission check.

        Returns:
            The instance dictionary, or None if not found.
        """
        instances = _load_instances()
        inst = instances.get(instance_id)
        if inst:
            if user_id and inst.get("user_id") and inst["user_id"] != user_id:
                return None
            inst["id"] = instance_id
            strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
            inst["log_dir"] = _find_latest_log_dir(strategy_dir)
        return inst

    # ---- Start/Stop ----

    async def start_instance(self, instance_id: str) -> dict:
        """Start a live trading instance.

        Args:
            instance_id: The instance ID to start.

        Returns:
            The updated instance dictionary.

        Raises:
            ValueError: If the instance doesn't exist or is already running.
        """
        instances = _load_instances()
        if instance_id not in instances:
            raise ValueError("Instance does not exist")
        inst = instances[instance_id]

        if inst["status"] == "running" and inst.get("pid") and _is_pid_alive(inst["pid"]):
            raise ValueError("Strategy is already running")

        strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
        run_py = strategy_dir / "run.py"
        if not run_py.is_file():
            raise ValueError(f"run.py does not exist: {run_py}")

        # Start subprocess
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(run_py),
            cwd=str(strategy_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[instance_id] = proc

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst["status"] = "running"
        inst["pid"] = proc.pid
        inst["error"] = None
        inst["started_at"] = now
        instances[instance_id] = inst
        _save_instances(instances)

        # Wait for process to finish in background
        asyncio.create_task(self._wait_process(instance_id, proc))

        inst["id"] = instance_id
        return inst

    async def stop_instance(self, instance_id: str) -> dict:
        """Stop a live trading instance.

        Args:
            instance_id: The instance ID to stop.

        Returns:
            The updated instance dictionary.

        Raises:
            ValueError: If the instance doesn't exist.
        """
        instances = _load_instances()
        if instance_id not in instances:
            raise ValueError("Instance does not exist")
        inst = instances[instance_id]

        pid = inst.get("pid")
        if pid and _is_pid_alive(pid):
            self._kill_pid(pid)

        # Clean up asyncio process reference
        proc = self._processes.pop(instance_id, None)
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inst["status"] = "stopped"
        inst["pid"] = None
        inst["stopped_at"] = now
        instances[instance_id] = inst
        _save_instances(instances)
        inst["id"] = instance_id
        return inst

    async def start_all(self) -> dict:
        """Start all stopped instances.

        Returns:
            A dictionary with success/failed counts and details.
        """
        instances = _load_instances()
        success = 0
        failed = 0
        details = []
        for iid, inst in instances.items():
            if inst["status"] == "running" and inst.get("pid") and _is_pid_alive(inst["pid"]):
                continue
            try:
                await self.start_instance(iid)
                success += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": "started"})
            except Exception as e:
                failed += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": str(e)})
        return {"success": success, "failed": failed, "details": details}

    async def stop_all(self) -> dict:
        """Stop all running instances.

        Returns:
            A dictionary with success/failed counts and details.
        """
        instances = _load_instances()
        success = 0
        failed = 0
        details = []
        for iid, inst in instances.items():
            if inst["status"] != "running":
                continue
            try:
                await self.stop_instance(iid)
                success += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": "stopped"})
            except Exception as e:
                failed += 1
                details.append({"id": iid, "strategy_id": inst["strategy_id"], "result": str(e)})
        return {"success": success, "failed": failed, "details": details}

    # ---- Internal Methods ----

    async def _wait_process(self, instance_id: str, proc: asyncio.subprocess.Process):
        """Wait for process to finish in background and update status.

        Args:
            instance_id: The instance ID.
            proc: The subprocess to wait for.
        """
        try:
            await proc.wait()
        except Exception:
            pass
        finally:
            instances = _load_instances()
            if instance_id in instances:
                inst = instances[instance_id]
                if proc.returncode != 0:
                    stderr = ""
                    if proc.stderr:
                        try:
                            stderr_bytes = await proc.stderr.read()
                            stderr = stderr_bytes.decode("utf-8", errors="replace")[-500:]
                        except Exception:
                            pass
                    inst["status"] = "error"
                    inst["error"] = stderr or f"Process exit code: {proc.returncode}"
                else:
                    inst["status"] = "stopped"
                inst["pid"] = None
                inst["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Refresh log directory
                strategy_dir = STRATEGIES_DIR / inst["strategy_id"]
                inst["log_dir"] = _find_latest_log_dir(strategy_dir)
                instances[instance_id] = inst
                _save_instances(instances)
            self._processes.pop(instance_id, None)

    @staticmethod
    def _kill_pid(pid: int):
        """Kill a process by PID.

        Args:
            pid: The process ID to kill.
        """
        import os
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass


# Global singleton
_manager: Optional[LiveTradingManager] = None


def get_live_trading_manager() -> LiveTradingManager:
    """Get the global live trading manager singleton.

    Returns:
        The LiveTradingManager instance.
    """
    global _manager
    if _manager is None:
        _manager = LiveTradingManager()
    return _manager
