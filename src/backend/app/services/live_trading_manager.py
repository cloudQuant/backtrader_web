"""
Live trading instance manager.

Manages strategy instances (CRUD/start/stop). Uses a JSON file for persistence and runs strategies
in subprocesses.
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id

try:
    from loguru import logger  # type: ignore[import-untyped]
except ImportError:
    logger = logging.getLogger(__name__)

_WORKSPACE_DIR = Path(__file__).resolve().parents[5]
_BACKTRADER_WEB_DIR = Path(__file__).resolve().parents[4]
_BT_API_PY_DIR = _WORKSPACE_DIR / "bt_api_py"
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"
_MANUAL_GATEWAY_DIR = _DATA_DIR / "manual_gateways"

_DEFAULT_TRANSPORT = "tcp" if sys.platform == "win32" else "ipc"


def _load_instances() -> dict[str, dict]:
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


def _save_instances(data: dict[str, dict]) -> None:
    """Save instances to the JSON file.

    Args:
        data: The instances dictionary to save.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _INSTANCES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _find_latest_log_dir(strategy_dir: Path) -> str | None:
    """Find the latest log directory for a strategy.

    Supports logs/<subdir>/ or flat logs/ (no subdirs) for simulate strategies.

    Args:
        strategy_dir: The strategy directory path.

    Returns:
        The path to the latest log directory, or None if not found.
    """
    logs_dir = strategy_dir / "logs"
    if not logs_dir.is_dir():
        return None
    subdirs = sorted(
        [d for d in logs_dir.iterdir() if d.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if subdirs:
        return str(subdirs[0])
    # Fallback: flat logs/ (no subdirs), e.g. simulate strategies
    expected = {
        "value.log",
        "data.log",
        "trade.log",
        "bar.log",
        "indicator.log",
        "position.log",
        "order.log",
        "system.log",
        "tick.log",
    }
    if any((logs_dir / f).is_file() for f in expected):
        return str(logs_dir)
    return None


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Args:
        pid: The process ID to check.

    Returns:
        True if the process is alive, False otherwise.
    """
    if sys.platform == "win32":
        # Use Win32 API to avoid os.kill(pid, 0) which can trigger
        # KeyboardInterrupt on Windows.
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


def _scan_running_strategy_pids() -> dict[str, int]:
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
    except Exception:
        pass
    return result


class LiveTradingManager:
    """Live trading manager (singleton pattern usage).

    Attributes:
        _processes: Dictionary of running subprocesses by instance ID.
    """

    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._gateways: dict[str, dict[str, Any]] = {}
        self._gateway_lock = threading.RLock()
        self._instance_gateways: dict[str, str] = {}
        self._stopping_instances: set[str] = set()
        # Sync process status on startup
        self._sync_status_on_boot()

    def _sync_status_on_boot(self) -> None:
        """Check if previously running instances are still running on startup.

        Updates the status of instances that were marked as 'running'
        but whose processes are no longer alive.
        """
        instances = _load_instances()
        changed = False
        for _iid, inst in instances.items():
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
                    changed = True
        if changed:
            _save_instances(instances)

    # ---- CRUD ----

    def list_instances(self, user_id: str = None) -> list[dict]:
        """List live trading instances, optionally filtered by user.

        Also detects externally-started strategy processes by scanning OS
        processes and matching run.py paths to registered instances.

        Args:
            user_id: Optional user ID to filter instances.

        Returns:
            A list of instance dictionaries.
        """
        instances = _load_instances()
        changed = False

        # Build a map of strategy_id -> resolved run.py path for external detection
        running_pids = _scan_running_strategy_pids()

        # Refresh status for ALL instances (before user filter)
        for iid, inst in instances.items():
            inst["id"] = iid
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
                    changed = True
            # Detect externally-started processes for stopped instances
            if inst.get("status") != "running":
                try:
                    strategy_dir = self._resolve_strategy_dir(inst["strategy_id"])
                    run_py_path = str(strategy_dir / "run.py")
                    if run_py_path in running_pids:
                        inst["status"] = "running"
                        inst["pid"] = running_pids[run_py_path]
                        changed = True
                except ValueError:
                    pass
        if changed:
            _save_instances(instances)

        result = []
        for _iid, inst in instances.items():
            if user_id and inst.get("user_id") and inst["user_id"] != user_id:
                continue
            try:
                strategy_dir = self._resolve_strategy_dir(inst["strategy_id"])
            except ValueError:
                inst["log_dir"] = None
            else:
                inst["log_dir"] = _find_latest_log_dir(strategy_dir)
            result.append(inst)
        return result

    def get_gateway_health(self) -> list[dict[str, Any]]:
        """Return health snapshots for all active gateways.

        Includes both shared GatewayRuntime instances and synthetic entries
        for running strategy instances that use direct CTP connections.

        Returns:
            A list of dicts, one per gateway, each containing the gateway key
            and its health snapshot from GatewayRuntime.health.
        """
        results: list[dict[str, Any]] = []
        gateway_instance_ids: set[str] = set()

        # 1. Real shared gateway runtimes
        with self._gateway_lock:
            gateway_items = list(self._gateways.items())
        for key, state in gateway_items:
            if state.get("process_mode") == "subprocess":
                proc = state.get("process")
                pid = None
                if proc is not None:
                    pid = getattr(proc, "pid", None)
                if not pid:
                    pid_file = state.get("pid_file")
                    if pid_file:
                        try:
                            pid = int(Path(pid_file).read_text(encoding="utf-8").strip())
                        except Exception:
                            pid = None
                running = bool(pid and _is_pid_alive(int(pid)))
                ready = False
                if running:
                    ready = self._ping_subprocess_gateway_ready(state)
                recent_errors: list[dict[str, Any]] = []
                has_fatal_error = False
                if running and not ready:
                    recent_errors = self._read_subprocess_recent_errors(state)
                    has_fatal_error = bool(recent_errors)
                elif not running:
                    recent_errors = [{"source": "process", "message": "Gateway process not running"}]
                results.append({
                    "gateway_key": key,
                    "state": "running" if ready else ("error" if has_fatal_error or not running else "starting"),
                    "is_healthy": ready,
                    "exchange": state.get("exchange_type", ""),
                    "asset_type": state.get("asset_type", ""),
                    "account_id": state.get("account_id", ""),
                    "market_connection": "connected" if ready else ("error" if has_fatal_error or not running else "connecting"),
                    "trade_connection": "connected" if ready else ("error" if has_fatal_error or not running else "connecting"),
                    "uptime_sec": 0,
                    "strategy_count": 0,
                    "symbol_count": 0,
                    "tick_count": 0,
                    "order_count": 0,
                    "heartbeat_age_sec": None,
                    "ref_count": state.get("ref_count", 0),
                    "instances": sorted(state.get("instances", set())),
                    "recent_errors": [] if ready else recent_errors,
                })
                gateway_instance_ids.update(state.get("instances", set()))
                continue
            runtime = state.get("runtime")
            if runtime is None:
                continue
            health = getattr(runtime, "health", None)
            try:
                snap: dict[str, Any] = health.snapshot() if health is not None else {}
            except Exception as exc:
                logger.exception("Failed to build gateway health snapshot for %s", key)
                snap = {
                    "state": "error",
                    "is_healthy": False,
                    "market_connection": "error",
                    "trade_connection": "error",
                    "uptime_sec": 0,
                    "strategy_count": 0,
                    "symbol_count": 0,
                    "tick_count": 0,
                    "order_count": 0,
                    "heartbeat_age_sec": None,
                    "recent_errors": [{"source": "health", "message": str(exc)}],
                }
            snap["gateway_key"] = key
            snap["ref_count"] = state.get("ref_count", 0)
            snap["instances"] = sorted(state.get("instances", set()))
            results.append(snap)
            gateway_instance_ids.update(state.get("instances", set()))

        # 2. Synthetic entries for running instances using direct CTP (no gateway)
        instances = _load_instances()
        for iid, inst in instances.items():
            if iid in gateway_instance_ids:
                continue
            if inst.get("status") != "running":
                continue
            pid = inst.get("pid")
            if not pid or not _is_pid_alive(pid):
                continue
            # Determine exchange/asset type from strategy config
            strategy_id = inst.get("strategy_id", "")
            exchange = "CTP"
            asset_type = "FUTURE"
            account_id = ""
            try:
                strategy_dir = self._resolve_strategy_dir(strategy_id)
                config_data = self._load_strategy_config(strategy_dir)
                env_data = self._load_strategy_env(strategy_dir)
                ctp = config_data.get("ctp", {}) or {}
                account_id = (
                    env_data.get("CTP_INVESTOR_ID")
                    or env_data.get("CTP_USER_ID")
                    or ctp.get("investor_id", "")
                )
            except Exception:
                pass
            name = inst.get("strategy_name") or strategy_id
            results.append({
                "gateway_key": f"direct:{strategy_id}",
                "state": "running",
                "is_healthy": True,
                "exchange": exchange,
                "asset_type": asset_type,
                "account_id": account_id,
                "market_connection": "connected",
                "trade_connection": "connected",
                "uptime_sec": 0,
                "strategy_count": 1,
                "symbol_count": 0,
                "tick_count": 0,
                "order_count": 0,
                "heartbeat_age_sec": None,
                "ref_count": 1,
                "instances": [iid],
                "recent_errors": [],
                "strategy_name": name,
            })
        return results

    def connect_gateway(
        self, exchange_type: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        """Manually connect a gateway with provided credentials.

        Args:
            exchange_type: Exchange type (CTP, IB_WEB, BINANCE, OKX).
            credentials: Exchange-specific credential dict.

        Returns:
            A dict with gateway_key, status, and message.
        """
        exchange_type = self._normalize_gateway_exchange_type(exchange_type)
        account_id = (
            credentials.get("account_id")
            or credentials.get("user_id")
            or credentials.get("login")
            or credentials.get("api_key")
            or ""
        )
        key = f"manual:{exchange_type}:{account_id}"

        # Check if already connected — but allow reconnect if subprocess died
        with self._gateway_lock:
            existing = self._gateways.get(key)
            if existing is not None:
                if existing.get("process_mode") == "subprocess":
                    proc = existing.get("process")
                    pid = getattr(proc, "pid", None) if proc else None
                    if pid and _is_pid_alive(int(pid)):
                        return {
                            "gateway_key": key,
                            "status": "connected",
                            "message": "Gateway already active",
                        }
                    # Subprocess died — remove stale entry so we can reconnect
                    logger.info("Removing stale gateway entry %s (subprocess dead)", key)
                    del self._gateways[key]
                else:
                    return {
                        "gateway_key": key,
                        "status": "connected",
                        "message": "Gateway already active",
                    }

        if exchange_type == "CTP":
            return self._connect_ctp_gateway(key, credentials)
        if exchange_type == "IB_WEB":
            return self._connect_ib_web_gateway(key, credentials)
        if exchange_type == "MT5":
            return self._connect_mt5_gateway(key, credentials)
        if exchange_type == "BINANCE":
            return self._connect_binance_gateway(key, credentials)
        if exchange_type == "OKX":
            return self._connect_okx_gateway(key, credentials)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"Unsupported gateway exchange_type: {exchange_type}",
        }

    def _connect_ctp_gateway(
        self, key: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        """Start a CTP gateway runtime from manual credentials."""
        required = ["broker_id", "user_id", "password", "td_front", "md_front"]
        missing = [f for f in required if not credentials.get(f)]
        if missing:
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing)}",
            }
        try:
            kwargs = {
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
                "account_id": credentials.get("account_id") or credentials["user_id"],
                "transport": _DEFAULT_TRANSPORT,
                "gateway_runtime_name": key.replace(":", "-").lower(),
                "md_address": credentials["md_front"],
                "td_address": credentials["td_front"],
                "broker_id": credentials["broker_id"],
                "investor_id": credentials["user_id"],
                "user_id": credentials["user_id"],
                "password": credentials["password"],
                "app_id": credentials.get("app_id", "simnow_client_test"),
                "auth_code": credentials.get("auth_code", "0000000000000000"),
                "gateway_startup_timeout_sec": 30.0,
            }
            config, proc, pid_file, stdout_path, stderr_path = self._start_ctp_gateway_process(kwargs)
            with self._gateway_lock:
                self._gateways[key] = {
                    "config": config,
                    "runtime": None,
                    "process": proc,
                    "process_mode": "subprocess",
                    "pid_file": str(pid_file),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "instances": set(),
                    "ref_count": 0,
                    "lock": threading.Lock(),
                    "manual": True,
                    "exchange_type": "CTP",
                    "asset_type": "FUTURE",
                    "account_id": kwargs["account_id"],
                }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "CTP gateway process started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect CTP gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"CTP连接失败: {type(e).__name__}: {e}",
            }

    def _start_ctp_gateway_process(
        self, kwargs: dict[str, Any]
    ) -> tuple[Any, subprocess.Popen, Path, Path, Path]:
        runtime_name = str(kwargs.get("gateway_runtime_name") or uuid.uuid4().hex)
        gateway_dir = _MANUAL_GATEWAY_DIR / runtime_name
        gateway_dir.mkdir(parents=True, exist_ok=True)
        runtime_kwargs = dict(kwargs)
        runtime_kwargs["gateway_base_dir"] = str(gateway_dir)

        # Kill any stale subprocess from a previous session
        self._kill_stale_gateway_process(gateway_dir, runtime_name)

        # Pre-allocate GatewayConfig so endpoints are determined BEFORE
        # the subprocess starts.  Write them into config.json so the child
        # process reads the *same* ports and avoids "Address in use" errors.
        if _BT_API_PY_DIR.is_dir() and str(_BT_API_PY_DIR) not in sys.path:
            sys.path.insert(0, str(_BT_API_PY_DIR))
        self._ensure_spdlog_safe()
        from bt_api_py.gateway.config import GatewayConfig
        config = GatewayConfig.from_kwargs(**runtime_kwargs)
        runtime_kwargs["gateway_command_endpoint"] = config.command_endpoint
        runtime_kwargs["gateway_event_endpoint"] = config.event_endpoint
        runtime_kwargs["gateway_market_endpoint"] = config.market_endpoint

        config_path = gateway_dir / "config.json"
        stdout_path = gateway_dir / "stdout.log"
        stderr_path = gateway_dir / "stderr.log"
        config_path.write_text(json.dumps(runtime_kwargs, ensure_ascii=False, indent=2), encoding="utf-8")
        # Clear old stderr so stale errors are not misdetected
        stderr_path.write_bytes(b"")

        python_exe = self._select_ctp_python_executable()
        env = dict(os.environ)
        # Strip proxy env vars so the subprocess's MyWebsocketApp does not
        # auto-detect a potentially dead proxy via urllib.request.getproxies().
        # Proxy settings are passed explicitly as http_proxy_host/http_proxy_port
        # in config.json instead.
        for _proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "SOCKS_PROXY",
                           "http_proxy", "https_proxy", "socks_proxy"):
            env.pop(_proxy_var, None)
        python_paths = [str(_BT_API_PY_DIR)]
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(python_paths + ([existing] if existing else []))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        with stdout_path.open("ab") as stdout_handle, stderr_path.open("ab") as stderr_handle:
            proc = subprocess.Popen(
                [python_exe, "-m", "bt_api_py.gateway.process", "start", "--config", str(config_path)],
                cwd=str(_BACKTRADER_WEB_DIR),
                env=env,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creationflags,
            )
        time.sleep(1.5)
        if proc.poll() is not None:
            error_text = ""
            try:
                error_text = stderr_path.read_text(encoding="utf-8", errors="replace")[-500:]
            except Exception:
                pass
            raise RuntimeError(error_text or "Gateway process exited immediately")
        pid_file = gateway_dir / f"{runtime_name}.pid"
        return config, proc, pid_file, stdout_path, stderr_path

    def _kill_stale_gateway_process(self, gateway_dir: Path, runtime_name: str) -> None:
        """Kill a stale gateway subprocess left from a previous session.

        Checks both PID files and processes holding the deterministic ZMQ
        ports so that ``Address in use`` errors are avoided.
        """
        killed_pids: set[int] = set()

        # 1. Kill by PID file
        for pid_path in gateway_dir.glob("*.pid"):
            try:
                old_pid = int(pid_path.read_text(encoding="utf-8").strip())
                if _is_pid_alive(old_pid):
                    logger.info("Killing stale gateway process PID %s in %s", old_pid, gateway_dir)
                    self._force_kill_pid(old_pid)
                    killed_pids.add(old_pid)
                pid_path.unlink(missing_ok=True)
            except Exception:
                pass

        # 2. Kill by port — the deterministic port may still be held by a
        #    process whose PID file was already cleaned up.
        try:
            self._ensure_spdlog_safe()
            from bt_api_py.gateway.config import GatewayConfig
            cfg = GatewayConfig(
                exchange_type="CTP", asset_type="FUTURE", account_id="tmp",
                transport="tcp", runtime_name=runtime_name,
            )
            base_port = int(cfg.command_endpoint.rsplit(":", 1)[-1])
            for port in (base_port, base_port + 1, base_port + 2):
                port_pid = self._find_pid_on_port(port)
                if port_pid and port_pid not in killed_pids:
                    logger.info("Killing process PID %s holding port %s", port_pid, port)
                    self._force_kill_pid(port_pid)
                    killed_pids.add(port_pid)
        except Exception:
            pass

        if killed_pids:
            time.sleep(0.5)

    @staticmethod
    def _force_kill_pid(pid: int) -> None:
        try:
            if sys.platform == "win32":
                subprocess.call(
                    ["taskkill", "/F", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    @staticmethod
    def _find_pid_on_port(port: int) -> int | None:
        """Return the PID listening on *port*, or None."""
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            needle = f":{port} "
            for line in out.splitlines():
                if needle not in line or "LISTENING" not in line:
                    continue
                parts = line.split()
                if parts:
                    return int(parts[-1])
        except Exception:
            pass
        return None

    def _select_ctp_python_executable(self) -> str:
        preferred = Path(r"C:\anaconda3\python.exe")
        if preferred.is_file():
            return str(preferred)
        return sys.executable

    def _get_gateway_proxy_kwargs(self, base_url: str | None = None) -> dict[str, Any]:
        try:
            from app.config import get_settings

            s = get_settings()
        except Exception:
            return {}

        http_proxy = str(getattr(s, "HTTP_PROXY", "") or "").strip()
        https_proxy = str(getattr(s, "HTTPS_PROXY", "") or "").strip()
        proxy_host = str(getattr(s, "PROXY_HOST", "") or "").strip()
        socks_proxy = str(getattr(s, "SOCKS_PROXY", "") or "").strip()
        no_proxy = str(getattr(s, "NO_PROXY", "") or "").strip()
        target_host = ""
        if base_url:
            try:
                from urllib.parse import urlparse

                target_host = str(urlparse(base_url).hostname or "").strip().lower()
            except Exception:
                target_host = ""
        no_proxy_hosts = {
            item.strip().lower().lstrip(".")
            for item in no_proxy.split(",")
            if item.strip()
        }
        if target_host:
            if target_host in {"localhost", "127.0.0.1", "::1"}:
                return {}
            if any(
                target_host == host or target_host.endswith(f".{host}")
                for host in no_proxy_hosts
                if host
            ):
                return {}

        if not http_proxy and proxy_host:
            http_proxy = proxy_host if "://" in proxy_host else f"http://{proxy_host}"
        if not https_proxy and proxy_host:
            https_proxy = proxy_host if "://" in proxy_host else f"http://{proxy_host}"

        # NOTE: Do NOT set os.environ["HTTP_PROXY"] etc. here.
        # Subprocess children inherit env vars, and MyWebsocketApp auto-detects
        # the system proxy via urllib.request.getproxies().  If the configured
        # proxy is not running, ALL WebSocket connections would fail with
        # "Connection refused".  Instead, pass proxy settings explicitly in
        # kwargs so they only apply where intended.

        proxies = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy

        result: dict[str, Any] = {}
        if proxies:
            result["proxies"] = proxies
        if socks_proxy:
            result["async_proxy"] = socks_proxy
        elif https_proxy or http_proxy:
            result["async_proxy"] = https_proxy or http_proxy

        # Extract host/port for websocket-client (used by MyWebsocketApp).
        # Only include if the proxy is actually reachable — a dead proxy
        # causes "Connection refused" for every WebSocket connection.
        proxy_url = https_proxy or http_proxy
        if proxy_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(proxy_url)
                if parsed.hostname and parsed.port:
                    import socket as _sock
                    _s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                    _s.settimeout(1.0)
                    try:
                        _s.connect((parsed.hostname, parsed.port))
                        _s.close()
                        result["http_proxy_host"] = parsed.hostname
                        result["http_proxy_port"] = parsed.port
                    except (OSError, ConnectionRefusedError):
                        logger.warning(
                            "Proxy %s:%s not reachable — WebSocket will connect directly",
                            parsed.hostname, parsed.port,
                        )
                    finally:
                        _s.close()
            except Exception:
                pass
        return result

    def _connect_ib_web_gateway(
        self, key: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        """Start an IB Web gateway runtime from manual credentials."""
        account_id = credentials.get("account_id", "")
        if not account_id:
            return {
                "gateway_key": key,
                "status": "error",
                "message": "Missing required field: account_id",
            }
        try:
            kwargs = {
                "exchange_type": "IB_WEB",
                "asset_type": self._normalize_gateway_asset_type("IB_WEB", credentials.get("asset_type", "STK")),
                "account_id": account_id,
                "transport": _DEFAULT_TRANSPORT,
                "gateway_runtime_name": key.replace(":", "-").lower(),
                "base_url": credentials.get("base_url", "https://localhost:5000"),
                "verify_ssl": self._coerce_bool(credentials.get("verify_ssl"), default=False),
                "timeout": self._coerce_float(credentials.get("timeout"), default=10.0),
            }
            kwargs.update(self._build_ib_web_manual_auth_kwargs(credentials))
            kwargs.update(self._get_gateway_proxy_kwargs(str(kwargs.get("base_url") or "")))
            config, proc, pid_file, stdout_path, stderr_path = self._start_ctp_gateway_process(kwargs)
            with self._gateway_lock:
                self._gateways[key] = {
                    "config": config,
                    "runtime": None,
                    "process": proc,
                    "process_mode": "subprocess",
                    "pid_file": str(pid_file),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "instances": set(),
                    "ref_count": 0,
                    "lock": threading.Lock(),
                    "manual": True,
                    "exchange_type": "IB_WEB",
                    "asset_type": kwargs["asset_type"],
                    "account_id": account_id,
                }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "IB Web gateway process started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect IB Web gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"IB Web连接失败: {type(e).__name__}: {e}",
            }

    def _build_ib_web_manual_auth_kwargs(self, credentials: dict[str, Any]) -> dict[str, Any]:
        from app.config import get_settings

        settings = get_settings()
        def pick_attr(*names: str):
            for name in names:
                value = getattr(settings, name, "")
                if value not in (None, ""):
                    return value
            return ""
        account_id = str(credentials.get("account_id") or "").strip()
        login_mode = str(credentials.get("login_mode") or pick_attr("IB_WEB_LOGIN_MODE") or "").strip().lower()
        if login_mode not in {"paper", "live"}:
            login_mode = "paper" if account_id.upper().startswith("DU") else "live"
        access_token = str(credentials.get("access_token") or pick_attr("IB_WEB_ACCESS_TOKEN", "IB_ACCESS_TOKEN") or "").strip()
        cookie_source = str(credentials.get("cookie_source") or "").strip()
        if not cookie_source:
            cookie_source = str(
                (pick_attr("IB_PAPER_COOKIE_SOURCE") if login_mode == "paper" else pick_attr("IB_LIVE_COOKIE_SOURCE"))
                or pick_attr("IB_WEB_COOKIE_SOURCE", "IB_COOKIE_SOURCE")
                or ""
            ).strip()
        cookie_browser = str(credentials.get("cookie_browser") or pick_attr("IB_WEB_COOKIE_BROWSER", "IB_COOKIE_BROWSER") or "").strip() or "chrome"
        cookie_path = str(credentials.get("cookie_path") or "").strip()
        if not cookie_path:
            cookie_path = str(
                (pick_attr("IB_PAPER_COOKIE_PATH") if login_mode == "paper" else pick_attr("IB_LIVE_COOKIE_PATH"))
                or pick_attr("IB_WEB_COOKIE_PATH", "IB_COOKIE_PATH")
                or "/sso"
            ).strip() or "/sso"
        cookie_output = str(credentials.get("cookie_output") or pick_attr("IB_WEB_COOKIE_OUTPUT", "IB_COOKIE_OUTPUT") or "").strip()
        username = str(credentials.get("username") or pick_attr("IB_WEB_USERNAME", "IB_USERNAME") or "").strip()
        password = str(credentials.get("password") or pick_attr("IB_WEB_PASSWORD", "IB_PASSWORD") or "").strip()
        login_browser = str(credentials.get("login_browser") or pick_attr("IB_WEB_LOGIN_BROWSER", "IB_LOGIN_BROWSER") or cookie_browser).strip() or "chrome"
        login_headless = self._coerce_bool(
            credentials.get("login_headless", pick_attr("IB_WEB_LOGIN_HEADLESS", "IB_LOGIN_HEADLESS")),
            default=False,
        )
        login_timeout = int(
            self._coerce_float(credentials.get("login_timeout", pick_attr("IB_WEB_LOGIN_TIMEOUT", "IB_LOGIN_TIMEOUT")), default=180.0)
        )
        cookies = credentials.get("cookies")

        if cookie_source and cookie_source not in {"browser", "env"} and not cookie_source.startswith("file:"):
            cookie_source = f"file:{cookie_source}"

        if not cookie_source and cookie_output:
            cookie_source = f"file:{cookie_output}"

        if not access_token and not cookie_source and not isinstance(cookies, dict) and not cookie_output:
            cookie_source = "browser"

        auth_kwargs: dict[str, Any] = {}
        if access_token:
            auth_kwargs["access_token"] = access_token
        if cookie_source:
            auth_kwargs["cookie_source"] = cookie_source
        if cookie_browser:
            auth_kwargs["cookie_browser"] = cookie_browser
        if cookie_path:
            auth_kwargs["cookie_path"] = cookie_path
        if cookie_output:
            auth_kwargs["cookie_output"] = cookie_output
        if username:
            auth_kwargs["username"] = username
        if password:
            auth_kwargs["password"] = password
        if login_mode:
            auth_kwargs["login_mode"] = login_mode
        if login_browser:
            auth_kwargs["login_browser"] = login_browser
        auth_kwargs["login_headless"] = login_headless
        auth_kwargs["login_timeout"] = login_timeout
        auth_kwargs["cookie_base_dir"] = str(_BACKTRADER_WEB_DIR)
        if isinstance(cookies, dict) and cookies:
            auth_kwargs["cookies"] = cookies
        return auth_kwargs

    def _connect_mt5_gateway(
        self, key: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        """Start an MT5 gateway runtime from manual credentials."""
        login = credentials.get("login")
        password = credentials.get("password")
        if not login or not password:
            return {
                "gateway_key": key,
                "status": "error",
                "message": "Missing required fields: login, password",
            }
        try:
            account_id = credentials.get("account_id") or str(login)
            kwargs = {
                "exchange_type": "MT5",
                "asset_type": "OTC",
                "account_id": account_id,
                "transport": _DEFAULT_TRANSPORT,
                "gateway_runtime_name": key.replace(":", "-").lower(),
                "login": int(login),
                "password": str(password),
                "server": str(credentials.get("server") or ""),
                "ws_uri": credentials.get("ws_uri", ""),
                "timeout": self._coerce_float(credentials.get("timeout"), default=60.0),
                "symbol_suffix": credentials.get("symbol_suffix", ""),
                "auto_reconnect": True,
            }
            if credentials.get("symbol_map"):
                kwargs["symbol_map"] = credentials["symbol_map"]
            config, proc, pid_file, stdout_path, stderr_path = self._start_ctp_gateway_process(kwargs)
            with self._gateway_lock:
                self._gateways[key] = {
                    "config": config,
                    "runtime": None,
                    "process": proc,
                    "process_mode": "subprocess",
                    "pid_file": str(pid_file),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "instances": set(),
                    "ref_count": 0,
                    "lock": threading.Lock(),
                    "manual": True,
                    "exchange_type": "MT5",
                    "asset_type": "OTC",
                    "account_id": account_id,
                }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "MT5 gateway process started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect MT5 gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"MT5连接失败: {type(e).__name__}: {e}",
            }

    def _connect_binance_gateway(
        self, key: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        api_key = str(credentials.get("api_key") or "").strip()
        secret_key = str(credentials.get("secret_key") or "").strip()
        if not api_key or not secret_key:
            return {
                "gateway_key": key,
                "status": "error",
                "message": "Missing required fields: api_key, secret_key",
            }
        try:
            account_id = str(credentials.get("account_id") or api_key).strip()
            kwargs = {
                "exchange_type": "BINANCE",
                "asset_type": self._normalize_gateway_asset_type("BINANCE", credentials.get("asset_type")),
                "account_id": account_id,
                "transport": _DEFAULT_TRANSPORT,
                "gateway_runtime_name": key.replace(":", "-").lower(),
                "api_key": api_key,
                "secret_key": secret_key,
                "testnet": self._coerce_bool(credentials.get("testnet"), default=False),
            }
            if credentials.get("base_url"):
                kwargs["base_url"] = str(credentials["base_url"])
            kwargs.update(self._get_gateway_proxy_kwargs())
            config, proc, pid_file, stdout_path, stderr_path = self._start_ctp_gateway_process(kwargs)
            with self._gateway_lock:
                self._gateways[key] = {
                    "config": config,
                    "runtime": None,
                    "process": proc,
                    "process_mode": "subprocess",
                    "pid_file": str(pid_file),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "instances": set(),
                    "ref_count": 0,
                    "lock": threading.Lock(),
                    "manual": True,
                    "exchange_type": "BINANCE",
                    "asset_type": kwargs["asset_type"],
                    "account_id": account_id,
                }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "Binance gateway process started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect Binance gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"Binance????: {type(e).__name__}: {e}",
            }

    def _connect_okx_gateway(
        self, key: str, credentials: dict[str, Any]
    ) -> dict[str, Any]:
        api_key = str(credentials.get("api_key") or "").strip()
        secret_key = str(credentials.get("secret_key") or "").strip()
        passphrase = str(credentials.get("passphrase") or "").strip()
        if not api_key or not secret_key or not passphrase:
            return {
                "gateway_key": key,
                "status": "error",
                "message": "Missing required fields: api_key, secret_key, passphrase",
            }
        try:
            account_id = str(credentials.get("account_id") or api_key).strip()
            kwargs = {
                "exchange_type": "OKX",
                "asset_type": self._normalize_gateway_asset_type("OKX", credentials.get("asset_type")),
                "account_id": account_id,
                "transport": _DEFAULT_TRANSPORT,
                "gateway_runtime_name": key.replace(":", "-").lower(),
                "api_key": api_key,
                "secret_key": secret_key,
                "passphrase": passphrase,
                "testnet": self._coerce_bool(credentials.get("testnet"), default=False),
            }
            if credentials.get("base_url"):
                kwargs["base_url"] = str(credentials["base_url"])
            kwargs.update(self._get_gateway_proxy_kwargs())
            config, proc, pid_file, stdout_path, stderr_path = self._start_ctp_gateway_process(kwargs)
            with self._gateway_lock:
                self._gateways[key] = {
                    "config": config,
                    "runtime": None,
                    "process": proc,
                    "process_mode": "subprocess",
                    "pid_file": str(pid_file),
                    "stdout_path": str(stdout_path),
                    "stderr_path": str(stderr_path),
                    "instances": set(),
                    "ref_count": 0,
                    "lock": threading.Lock(),
                    "manual": True,
                    "exchange_type": "OKX",
                    "asset_type": kwargs["asset_type"],
                    "account_id": account_id,
                }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "OKX gateway process started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect OKX gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"OKX????: {type(e).__name__}: {e}",
            }

    def query_gateway_account(self, gateway_key: str) -> dict[str, Any] | None:
        """Query account info from a connected gateway.

        Args:
            gateway_key: The gateway key to query.

        Returns:
            Account dict or None if unavailable.
        """
        with self._gateway_lock:
            state = self._gateways.get(gateway_key)
        if state is None:
            return None
        runtime = state.get("runtime")
        if runtime is None:
            return None
        try:
            health = getattr(runtime, "health", None)
            if health is not None:
                snap = health.snapshot()
                return {
                    "gateway_key": gateway_key,
                    "exchange": state.get("exchange_type", snap.get("exchange", "")),
                    "account_id": state.get("account_id", snap.get("account_id", "")),
                    "state": snap.get("state", "unknown"),
                    "market_connection": snap.get("market_connection", "unknown"),
                    "trade_connection": snap.get("trade_connection", "unknown"),
                }
            return {"gateway_key": gateway_key, "state": "connected"}
        except Exception:
            return {"gateway_key": gateway_key, "state": "error"}

    def query_gateway_positions(self, gateway_key: str) -> list[dict[str, Any]]:
        """Query positions from a connected gateway.

        Args:
            gateway_key: The gateway key to query.

        Returns:
            A list of position dicts.
        """
        with self._gateway_lock:
            state = self._gateways.get(gateway_key)
        if state is None:
            return []
        runtime = state.get("runtime")
        if runtime is None:
            return []
        try:
            positions = getattr(runtime, "positions", None)
            if positions is not None and callable(positions):
                return list(positions())
            pos_dict = getattr(runtime, "_positions", None)
            if isinstance(pos_dict, dict):
                return list(pos_dict.values())
            return []
        except Exception:
            return []

    def list_connected_gateways(self) -> list[dict[str, Any]]:
        """List all manually connected gateways with basic info.

        Returns:
            A list of dicts with gateway_key and metadata.
        """
        results: list[dict[str, Any]] = []
        with self._gateway_lock:
            gateway_items = list(self._gateways.items())
        for key, state in gateway_items:
            if not state.get("manual"):
                continue
            results.append({
                "gateway_key": key,
                "exchange_type": state.get("exchange_type", ""),
                "account_id": state.get("account_id", ""),
                "has_runtime": state.get("runtime") is not None,
            })
        return results

    def disconnect_gateway(self, gateway_key: str) -> dict[str, Any]:
        """Disconnect a manually-started gateway.

        Args:
            gateway_key: The gateway key to disconnect.

        Returns:
            A dict with gateway_key, status, and message.
        """
        with self._gateway_lock:
            state = self._gateways.get(gateway_key)
        if state is None:
            return {
                "gateway_key": gateway_key,
                "status": "error",
                "message": "Gateway not found",
            }
        if not state.get("manual"):
            return {
                "gateway_key": gateway_key,
                "status": "error",
                "message": "Cannot disconnect a strategy-owned gateway",
            }
        runtime = state.get("runtime")
        if runtime is not None:
            try:
                runtime.stop()
            except Exception:
                pass
        if state.get("process_mode") == "subprocess":
            proc = state.get("process")
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3.0)
                except Exception:
                    pass
            pid_file = state.get("pid_file")
            if pid_file:
                try:
                    pid = int(Path(pid_file).read_text(encoding="utf-8").strip())
                except Exception:
                    pid = None
                if pid:
                    self._kill_pid(pid)
        with self._gateway_lock:
            self._gateways.pop(gateway_key, None)
        return {
            "gateway_key": gateway_key,
            "status": "disconnected",
            "message": "Gateway disconnected",
        }

    def get_gateway_presets(self) -> list[dict[str, Any]]:
        return [
            {
                "description": "Shared CTP gateway preset for domestic futures accounts.",
                "id": "ctp_futures_gateway",
                "name": "CTP Futures Gateway",
                "editable_fields": [
                    {
                        "key": "account_id",
                        "label": "账户",
                        "input_type": "string",
                        "placeholder": "请输入期货账户",
                    }
                ],
                "params": {
                    "gateway": {
                        "enabled": True,
                        "provider": "ctp_gateway",
                        "exchange_type": "CTP",
                        "asset_type": "FUTURE",
                        "account_id": "",
                    }
                },
            },
            {
                "description": "IB Web preset for US stock trading via gateway mode.",
                "id": "ib_web_stock_gateway",
                "name": "IB Web Stock Gateway",
                "editable_fields": [
                    {
                        "key": "account_id",
                        "label": "账户",
                        "input_type": "string",
                        "placeholder": "如 DU123456",
                    },
                    {
                        "key": "base_url",
                        "label": "Base URL",
                        "input_type": "string",
                        "placeholder": "如 https://localhost:5000",
                    },
                    {
                        "key": "verify_ssl",
                        "label": "SSL校验",
                        "input_type": "boolean",
                    },
                ],
                "params": {
                    "gateway": {
                        "enabled": True,
                        "provider": "gateway",
                        "exchange_type": "IB_WEB",
                        "asset_type": "STK",
                        "account_id": "DU123456",
                        "base_url": "https://localhost:5000",
                        "verify_ssl": False,
                    }
                },
            },
            {
                "description": "IB Web preset for futures trading via gateway mode.",
                "id": "ib_web_futures_gateway",
                "name": "IB Web Futures Gateway",
                "editable_fields": [
                    {
                        "key": "account_id",
                        "label": "账户",
                        "input_type": "string",
                        "placeholder": "如 DU123456",
                    },
                    {
                        "key": "base_url",
                        "label": "Base URL",
                        "input_type": "string",
                        "placeholder": "如 https://localhost:5000",
                    },
                    {
                        "key": "verify_ssl",
                        "label": "SSL校验",
                        "input_type": "boolean",
                    },
                ],
                "params": {
                    "gateway": {
                        "enabled": True,
                        "provider": "gateway",
                        "exchange_type": "IB_WEB",
                        "asset_type": "FUT",
                        "account_id": "DU123456",
                        "base_url": "https://localhost:5000",
                        "verify_ssl": False,
                    }
                },
            },
            {
                "description": "Binance SWAP gateway preset for perpetual futures trading.",
                "id": "binance_swap_gateway",
                "name": "Binance SWAP Gateway",
                "editable_fields": [
                    {
                        "key": "account_id",
                        "label": "账户标识",
                        "input_type": "string",
                        "placeholder": "自定义账户标识",
                    },
                    {
                        "key": "api_key",
                        "label": "API Key",
                        "input_type": "string",
                        "placeholder": "Binance API Key",
                    },
                    {
                        "key": "secret_key",
                        "label": "Secret Key",
                        "input_type": "string",
                        "placeholder": "Binance Secret Key",
                    },
                ],
                "params": {
                    "gateway": {
                        "enabled": True,
                        "provider": "gateway",
                        "exchange_type": "BINANCE",
                        "asset_type": "SWAP",
                        "account_id": "",
                        "api_key": "",
                        "secret_key": "",
                    }
                },
            },
            {
                "description": "OKX SWAP gateway preset for perpetual futures trading.",
                "id": "okx_swap_gateway",
                "name": "OKX SWAP Gateway",
                "editable_fields": [
                    {
                        "key": "account_id",
                        "label": "账户标识",
                        "input_type": "string",
                        "placeholder": "自定义账户标识",
                    },
                    {
                        "key": "api_key",
                        "label": "API Key",
                        "input_type": "string",
                        "placeholder": "OKX API Key",
                    },
                    {
                        "key": "secret_key",
                        "label": "Secret Key",
                        "input_type": "string",
                        "placeholder": "OKX Secret Key",
                    },
                    {
                        "key": "passphrase",
                        "label": "Passphrase",
                        "input_type": "string",
                        "placeholder": "OKX Passphrase",
                    },
                ],
                "params": {
                    "gateway": {
                        "enabled": True,
                        "provider": "gateway",
                        "exchange_type": "OKX",
                        "asset_type": "SWAP",
                        "account_id": "",
                        "api_key": "",
                        "secret_key": "",
                        "passphrase": "",
                    }
                },
            },
            {
                "description": "MT5 Forex gateway preset for MetaTrader 5 trading via pymt5 WebSocket.",
                "id": "mt5_forex_gateway",
                "name": "MT5 Forex Gateway",
                "editable_fields": [
                    {
                        "key": "account_id",
                        "label": "账户标识",
                        "input_type": "string",
                        "placeholder": "自定义账户标识",
                    },
                    {
                        "key": "login",
                        "label": "MT5 账号",
                        "input_type": "string",
                        "placeholder": "MT5 登录账号（数字）",
                    },
                    {
                        "key": "password",
                        "label": "MT5 密码",
                        "input_type": "string",
                        "placeholder": "MT5 登录密码",
                    },
                    {
                        "key": "ws_uri",
                        "label": "WebSocket 地址",
                        "input_type": "string",
                        "placeholder": "默认 wss://web.metatrader.app/terminal",
                    },
                ],
                "params": {
                    "gateway": {
                        "enabled": True,
                        "provider": "mt5_gateway",
                        "exchange_type": "MT5",
                        "asset_type": "OTC",
                        "account_id": "",
                        "login": "",
                        "password": "",
                        "ws_uri": "",
                        "symbol_suffix": "",
                    }
                },
            },
        ]

    def add_instance(
        self, strategy_id: str, params: dict[str, Any] | None = None, user_id: str = None
    ) -> dict:
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
        try:
            strategy_dir = self._resolve_strategy_dir(strategy_id)
        except ValueError:
            raise ValueError(f"Invalid strategy_id: {strategy_id}") from None
        if not (strategy_dir / "run.py").is_file():
            raise ValueError(f"Strategy {strategy_id} does not exist or lacks run.py")

        tpl = get_template_by_id(strategy_id)
        name = tpl.name if tpl else strategy_id

        merged_params = dict(params) if params else {}
        if "gateway" not in merged_params:
            inferred = self._infer_gateway_params(strategy_dir)
            if inferred:
                merged_params["gateway"] = inferred

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
            "params": merged_params,
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
        self._release_gateway_for_instance(instance_id)
        return True

    def get_instance(self, instance_id: str, user_id: str = None) -> dict | None:
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
            # Refresh PID alive status (same as list_instances) so callers
            # never see a stale "running" state for a dead process.
            if inst.get("status") == "running":
                pid = inst.get("pid")
                if not pid or not _is_pid_alive(pid):
                    inst["status"] = "stopped"
                    inst["pid"] = None
                    instances[instance_id] = inst
                    _save_instances(instances)
            try:
                strategy_dir = self._resolve_strategy_dir(inst["strategy_id"])
                inst["log_dir"] = _find_latest_log_dir(strategy_dir)
            except ValueError:
                inst["log_dir"] = None
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

        try:
            strategy_dir = self._resolve_strategy_dir(inst["strategy_id"])
        except ValueError as e:
            raise ValueError(f"Invalid strategy_id: {inst['strategy_id']}") from e
        run_py = strategy_dir / "run.py"
        if not run_py.is_file():
            raise ValueError(f"run.py does not exist: {run_py}")

        env = self._build_subprocess_env(instance_id, inst, strategy_dir)
        # On Windows, isolate child processes in a new process group so that
        # console Ctrl+C events do not propagate and crash the parent.
        _sub_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            import subprocess as _sp

            _sub_kwargs["creationflags"] = (
                _sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(run_py),
                cwd=str(strategy_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                **_sub_kwargs,
            )
        except Exception:
            self._release_gateway_for_instance(instance_id)
            raise
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
        self._stopping_instances.add(instance_id)

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
        self._release_gateway_for_instance(instance_id)
        inst["id"] = instance_id
        return inst

    async def start_all(self, user_id: str = None) -> dict:
        """Start all stopped instances, optionally filtered by user.

        Args:
            user_id: Optional user ID to limit operations to that user's instances.

        Returns:
            A dictionary with success/failed counts and details.
        """
        instances = _load_instances()
        success = 0
        failed = 0
        details = []
        for iid, inst in instances.items():
            if user_id and inst.get("user_id") and inst["user_id"] != user_id:
                continue
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

    async def stop_all(self, user_id: str = None) -> dict:
        """Stop all running instances, optionally filtered by user.

        Args:
            user_id: Optional user ID to limit operations to that user's instances.

        Returns:
            A dictionary with success/failed counts and details.
        """
        instances = _load_instances()
        success = 0
        failed = 0
        details = []
        for iid, inst in instances.items():
            if user_id and inst.get("user_id") and inst["user_id"] != user_id:
                continue
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
            was_stopping = instance_id in self._stopping_instances
            instances = _load_instances()
            if instance_id in instances:
                inst = instances[instance_id]
                if was_stopping:
                    inst["status"] = "stopped"
                    inst["error"] = None
                elif proc.returncode != 0:
                    stderr = ""
                    if proc.stderr:
                        try:
                            stderr_bytes = await proc.stderr.read()
                            # Windows Chinese locale uses GBK; try it first, then UTF-8
                            for enc in ("utf-8", "gbk", "cp936"):
                                try:
                                    stderr = stderr_bytes.decode(enc)
                                    break
                                except (UnicodeDecodeError, LookupError):
                                    continue
                            else:
                                stderr = stderr_bytes.decode("utf-8", errors="replace")
                            stderr = stderr[-500:]
                        except Exception:
                            pass
                    inst["status"] = "error"
                    inst["error"] = stderr or f"Process exit code: {proc.returncode}"
                else:
                    inst["status"] = "stopped"
                    inst["error"] = None
                inst["pid"] = None
                inst["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Refresh log directory
                try:
                    strategy_dir = self._resolve_strategy_dir(inst["strategy_id"])
                    inst["log_dir"] = _find_latest_log_dir(strategy_dir)
                except ValueError:
                    inst["log_dir"] = None
                instances[instance_id] = inst
                _save_instances(instances)
            self._processes.pop(instance_id, None)
            self._stopping_instances.discard(instance_id)
            self._release_gateway_for_instance(instance_id)

    @staticmethod
    def _kill_pid(pid: int):
        """Kill a process by PID.

        Args:
            pid: The process ID to kill.
        """
        if sys.platform == "win32":
            import subprocess as _sp

            try:
                _sp.call(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    creationflags=_sp.CREATE_NO_WINDOW,
                )
            except Exception:
                pass
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

    def _build_subprocess_env(
        self, instance_id: str, instance: dict[str, Any], strategy_dir: Path
    ) -> dict[str, str]:
        env = dict(os.environ)
        python_paths = [str(_BT_API_PY_DIR)] if _BT_API_PY_DIR.is_dir() else []
        if python_paths:
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = os.pathsep.join(python_paths + ([existing] if existing else []))
        gateway = self._acquire_gateway_for_instance(instance_id, instance, strategy_dir)
        if gateway is None:
            return env
        config = gateway["config"]
        exchange_type = config.exchange_type
        if exchange_type == "MT5":
            env["BT_STORE_PROVIDER"] = "mt5_gateway"
        else:
            env["BT_STORE_PROVIDER"] = "ctp_gateway"
        env["BT_GATEWAY_START_LOCAL_RUNTIME"] = "0"
        env["BT_GATEWAY_COMMAND_ENDPOINT"] = config.command_endpoint
        env["BT_GATEWAY_EVENT_ENDPOINT"] = config.event_endpoint
        env["BT_GATEWAY_MARKET_ENDPOINT"] = config.market_endpoint
        env["BT_GATEWAY_ACCOUNT_ID"] = config.account_id
        env["BT_GATEWAY_EXCHANGE_TYPE"] = config.exchange_type
        env["BT_GATEWAY_ASSET_TYPE"] = config.asset_type
        env["BT_GATEWAY_STARTUP_TIMEOUT_SEC"] = str(config.startup_timeout_sec)
        env["BT_GATEWAY_COMMAND_TIMEOUT_SEC"] = str(config.command_timeout_sec)
        return env

    def _acquire_gateway_for_instance(
        self, instance_id: str, instance: dict[str, Any], strategy_dir: Path
    ) -> dict[str, Any] | None:
        gateway_params = self._get_gateway_params(instance)
        if not gateway_params.get("enabled"):
            return None
        try:
            launch = self._build_gateway_launch(instance, strategy_dir, gateway_params)
        except Exception as exc:
            logger.warning(
                "Gateway launch config failed for {}, falling back to direct mode: {}",
                instance_id, exc,
            )
            return None
        key = launch["config"].runtime_name
        with self._gateway_lock:
            state = self._gateways.get(key)
        logger.info(
            "Gateway acquire for {}: key={}, existing={}, endpoints={}/{}/{}",
            instance_id, key, state is not None,
            launch["config"].command_endpoint,
            launch["config"].event_endpoint,
            launch["config"].market_endpoint,
        )
        if state is None:
            try:
                runtime = launch["runtime_cls"](launch["config"], **launch["runtime_kwargs"])
                runtime.start_in_thread()
            except Exception as exc:
                logger.warning(
                    "Gateway runtime failed to start for {}, falling back to direct mode: {}",
                    instance_id, exc,
                )
                return None
            state = {
                "config": launch["config"],
                "runtime": runtime,
                "instances": set(),
                "ref_count": 0,
                "lock": threading.Lock(),
            }
            with self._gateway_lock:
                self._gateways[key] = state
        state["instances"].add(instance_id)
        state["ref_count"] += 1
        with self._gateway_lock:
            self._instance_gateways[instance_id] = key
        return state

    def _release_gateway_for_instance(self, instance_id: str) -> None:
        with self._gateway_lock:
            key = self._instance_gateways.pop(instance_id, None)
        if not key:
            return
        with self._gateway_lock:
            state = self._gateways.get(key)
        if state is None:
            return
        state["instances"].discard(instance_id)
        state["ref_count"] = max(0, int(state.get("ref_count", 0)) - 1)
        if state["instances"] or state["ref_count"] > 0:
            return
        runtime = state.get("runtime")
        if runtime is not None:
            try:
                runtime.stop()
            except Exception:
                logger.debug("Gateway runtime stop error for %s (ignored)", key, exc_info=True)
        with self._gateway_lock:
            self._gateways.pop(key, None)

    @staticmethod
    def _infer_gateway_params(strategy_dir: Path) -> dict[str, Any] | None:
        """Read config.yaml and infer gateway params when not provided by the user.

        Returns a gateway dict suitable for ``instance["params"]["gateway"]``,
        or *None* if no gateway / CTP section is found.
        """
        config_path = strategy_dir / "config.yaml"
        if not config_path.is_file():
            return None
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return None

        # Explicit gateway section (MT5 strategies)
        gw = cfg.get("gateway")
        if isinstance(gw, dict) and gw.get("enabled"):
            return {
                "enabled": True,
                "provider": str(gw.get("provider", "ctp_gateway")),
                "exchange_type": str(gw.get("exchange_type", "CTP")),
                "asset_type": str(gw.get("asset_type", "FUTURE")),
            }

        # CTP section present → infer ctp_gateway
        if isinstance(cfg.get("ctp"), dict):
            return {
                "enabled": True,
                "provider": "ctp_gateway",
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
            }

        return None

    def _get_gateway_params(self, instance: dict[str, Any]) -> dict[str, Any]:
        params = instance.get("params") or {}
        if not isinstance(params, dict):
            return {"enabled": False}
        gateway = params.get("gateway") or {}
        if not isinstance(gateway, dict):
            gateway = {}
        provider = str(gateway.get("provider") or params.get("provider") or "").strip().lower()
        exchange_type = self._normalize_gateway_exchange_type(
            gateway.get("exchange_type")
            or gateway.get("exchange")
            or params.get("exchange_type")
            or params.get("exchange"),
            provider,
        )
        enabled = (
            bool(gateway.get("enabled"))
            or provider in {"ctp_gateway", "gateway"}
            or provider.endswith("_gateway")
        )
        return {
            "enabled": enabled,
            "provider": provider or "ctp",
            "exchange_type": exchange_type,
            "transport": str(gateway.get("transport") or _DEFAULT_TRANSPORT),
            "asset_type": self._normalize_gateway_asset_type(
                exchange_type, gateway.get("asset_type") or params.get("asset_type")
            ),
            "account_id": str(gateway.get("account_id") or ""),
            "base_dir": str(gateway.get("base_dir") or ""),
            "base_url": str(gateway.get("base_url") or ""),
            "access_token": str(gateway.get("access_token") or ""),
            "verify_ssl": gateway.get("verify_ssl"),
            "cookie_source": str(gateway.get("cookie_source") or ""),
            "cookie_browser": str(gateway.get("cookie_browser") or ""),
            "cookie_path": str(gateway.get("cookie_path") or ""),
            "cookies": gateway.get("cookies"),
        }

    def _build_gateway_launch(
        self, instance: dict[str, Any], strategy_dir: Path, gateway_params: dict[str, Any]
    ) -> dict[str, Any]:
        config_data = self._load_strategy_config(strategy_dir)
        env_data = self._load_strategy_env(strategy_dir)
        gateway_config_cls, gateway_runtime_cls = self._import_gateway_runtime_classes()
        strategy_gateway = dict(config_data.get("gateway", {}) or {})
        exchange_type = self._normalize_gateway_exchange_type(
            gateway_params.get("exchange_type")
            or strategy_gateway.get("exchange_type")
            or strategy_gateway.get("exchange"),
            str(gateway_params.get("provider") or ""),
        )
        if exchange_type == "IB_WEB":
            runtime_kwargs = self._build_ib_web_gateway_runtime_kwargs(
                config_data=config_data,
                env_data=env_data,
                gateway_params=gateway_params,
            )
        elif exchange_type == "MT5":
            runtime_kwargs = self._build_mt5_gateway_runtime_kwargs(
                config_data=config_data,
                env_data=env_data,
                gateway_params=gateway_params,
            )
        else:
            runtime_kwargs = self._build_ctp_gateway_runtime_kwargs(
                config_data=config_data,
                env_data=env_data,
                gateway_params=gateway_params,
            )
        return {
            "config": gateway_config_cls.from_kwargs(**runtime_kwargs),
            "runtime_cls": gateway_runtime_cls,
            "runtime_kwargs": runtime_kwargs,
        }

    def _build_ctp_gateway_runtime_kwargs(
        self,
        config_data: dict[str, Any],
        env_data: dict[str, str],
        gateway_params: dict[str, Any],
    ) -> dict[str, Any]:
        ctp = dict(config_data.get("ctp", {}) or {})
        live = dict(config_data.get("live", {}) or {})
        fronts = dict(ctp.get("fronts", {}) or {})
        network = str(live.get("network") or "simnow")
        front = dict(fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {})
        investor_id = (
            env_data.get("CTP_INVESTOR_ID")
            or env_data.get("CTP_USER_ID")
            or ctp.get("investor_id", "")
            or ctp.get("user_id", "")
        )
        broker_id = env_data.get("CTP_BROKER_ID") or ctp.get("broker_id", "")
        password = env_data.get("CTP_PASSWORD") or ctp.get("password", "")
        app_id = env_data.get("CTP_APP_ID") or ctp.get("app_id", "simnow_client_test")
        auth_code = env_data.get("CTP_AUTH_CODE") or ctp.get("auth_code", "0000000000000000")
        td_address = front.get("td_address", "")
        md_address = front.get("md_address", "")
        account_id = gateway_params.get("account_id") or investor_id
        if not all([account_id, investor_id, broker_id, password, td_address, md_address]):
            raise ValueError("CTP gateway requires complete CTP credentials and front addresses")
        return {
            "exchange_type": "CTP",
            "asset_type": self._normalize_gateway_asset_type(
                "CTP", gateway_params.get("asset_type")
            ),
            "account_id": account_id,
            "transport": gateway_params.get("transport") or _DEFAULT_TRANSPORT,
            "gateway_base_dir": gateway_params.get("base_dir") or "",
            "md_address": md_address,
            "td_address": td_address,
            "broker_id": broker_id,
            "investor_id": investor_id,
            "user_id": investor_id,
            "password": password,
            "app_id": app_id,
            "auth_code": auth_code,
        }

    def _build_ib_web_gateway_runtime_kwargs(
        self,
        config_data: dict[str, Any],
        env_data: dict[str, str],
        gateway_params: dict[str, Any],
    ) -> dict[str, Any]:
        ib_web = dict(config_data.get("ib_web", {}) or {})
        account_id = (
            gateway_params.get("account_id")
            or env_data.get("IB_WEB_ACCOUNT_ID")
            or ib_web.get("account_id", "")
        )
        if not account_id:
            raise ValueError("IB_WEB gateway requires account_id")
        base_url = (
            gateway_params.get("base_url")
            or env_data.get("IB_WEB_BASE_URL")
            or ib_web.get("base_url")
            or "https://localhost:5000"
        )
        access_token = (
            gateway_params.get("access_token")
            or env_data.get("IB_WEB_ACCESS_TOKEN")
            or ib_web.get("access_token", "")
        )
        verify_ssl_value = gateway_params.get("verify_ssl")
        if verify_ssl_value is None:
            verify_ssl_value = env_data.get("IB_WEB_VERIFY_SSL", ib_web.get("verify_ssl"))
        verify_ssl = self._coerce_bool(
            verify_ssl_value,
            default=False,
        )
        timeout = self._coerce_float(
            env_data.get("IB_WEB_TIMEOUT", ib_web.get("timeout")),
            default=10.0,
        )
        cookie_source = (
            gateway_params.get("cookie_source")
            or env_data.get("IB_WEB_COOKIE_SOURCE")
            or ib_web.get("cookie_source", "")
        )
        cookie_browser = (
            gateway_params.get("cookie_browser")
            or env_data.get("IB_WEB_COOKIE_BROWSER")
            or ib_web.get("cookie_browser")
            or "chrome"
        )
        cookie_path = (
            gateway_params.get("cookie_path")
            or env_data.get("IB_WEB_COOKIE_PATH")
            or ib_web.get("cookie_path")
            or "/sso"
        )
        cookie_output = (
            gateway_params.get("cookie_output")
            or env_data.get("IB_WEB_COOKIE_OUTPUT")
            or ib_web.get("cookie_output")
            or ""
        )
        username = (
            gateway_params.get("username")
            or env_data.get("IB_WEB_USERNAME")
            or ib_web.get("username", "")
        )
        password = (
            gateway_params.get("password")
            or env_data.get("IB_WEB_PASSWORD")
            or ib_web.get("password", "")
        )
        login_mode = (
            gateway_params.get("login_mode")
            or env_data.get("IB_WEB_LOGIN_MODE")
            or ib_web.get("login_mode", "")
        )
        if not login_mode:
            login_mode = "paper" if str(account_id).upper().startswith("DU") else "live"
        login_browser = (
            gateway_params.get("login_browser")
            or env_data.get("IB_WEB_LOGIN_BROWSER")
            or ib_web.get("login_browser")
            or cookie_browser
            or "chrome"
        )
        login_headless = self._coerce_bool(
            gateway_params.get(
                "login_headless",
                env_data.get("IB_WEB_LOGIN_HEADLESS", ib_web.get("login_headless")),
            ),
            default=False,
        )
        login_timeout = int(
            self._coerce_float(
                gateway_params.get(
                    "login_timeout",
                    env_data.get("IB_WEB_LOGIN_TIMEOUT", ib_web.get("login_timeout")),
                ),
                default=180.0,
            )
        )
        cookies = gateway_params.get("cookies") or self._parse_json_dict(
            env_data.get("IB_WEB_COOKIES_JSON")
        )
        if cookies is None and isinstance(ib_web.get("cookies"), dict):
            cookies = ib_web.get("cookies")
        if cookie_source and cookie_source not in {"browser", "env"} and not str(cookie_source).startswith("file:"):
            cookie_source = f"file:{cookie_source}"
        if not cookie_source and cookie_output:
            cookie_source = f"file:{cookie_output}"
        runtime_kwargs = {
            "exchange_type": "IB_WEB",
            "asset_type": self._normalize_gateway_asset_type(
                "IB_WEB",
                gateway_params.get("asset_type") or ib_web.get("asset_type"),
            ),
            "account_id": account_id,
            "transport": gateway_params.get("transport") or _DEFAULT_TRANSPORT,
            "gateway_base_dir": gateway_params.get("base_dir") or "",
            "base_url": base_url,
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cookie_base_dir": str(_BACKTRADER_WEB_DIR),
        }
        if access_token:
            runtime_kwargs["access_token"] = access_token
        if cookie_source:
            runtime_kwargs["cookie_source"] = cookie_source
        if cookie_browser:
            runtime_kwargs["cookie_browser"] = cookie_browser
        if cookie_path:
            runtime_kwargs["cookie_path"] = cookie_path
        if cookie_output:
            runtime_kwargs["cookie_output"] = cookie_output
        if username:
            runtime_kwargs["username"] = username
        if password:
            runtime_kwargs["password"] = password
        if login_mode:
            runtime_kwargs["login_mode"] = login_mode
        if login_browser:
            runtime_kwargs["login_browser"] = login_browser
        runtime_kwargs["login_headless"] = login_headless
        runtime_kwargs["login_timeout"] = login_timeout
        if cookies:
            runtime_kwargs["cookies"] = cookies
        return runtime_kwargs

    def _build_mt5_gateway_runtime_kwargs(
        self,
        config_data: dict[str, Any],
        env_data: dict[str, str],
        gateway_params: dict[str, Any],
    ) -> dict[str, Any]:
        mt5 = dict(config_data.get("mt5", {}) or {})
        login = (
            gateway_params.get("login")
            or env_data.get("MT5_LOGIN")
            or mt5.get("login", "")
        )
        password = (
            gateway_params.get("password")
            or env_data.get("MT5_PASSWORD")
            or mt5.get("password", "")
        )
        account_id = (
            gateway_params.get("account_id")
            or env_data.get("MT5_ACCOUNT_ID")
            or mt5.get("account_id")
            or str(login)
        )
        ws_uri = (
            gateway_params.get("ws_uri")
            or env_data.get("MT5_WS_URI")
            or mt5.get("ws_uri", "")
        )
        symbol_suffix = (
            gateway_params.get("symbol_suffix")
            or env_data.get("MT5_SYMBOL_SUFFIX")
            or mt5.get("symbol_suffix", "")
        )
        if not login or not password:
            raise ValueError("MT5 gateway requires login and password")
        runtime_kwargs: dict[str, Any] = {
            "exchange_type": "MT5",
            "asset_type": self._normalize_gateway_asset_type(
                "MT5", gateway_params.get("asset_type") or mt5.get("asset_type")
            ),
            "account_id": account_id,
            "transport": gateway_params.get("transport") or "tcp",
            "login": int(login),
            "password": str(password),
            "ws_uri": ws_uri,
            "symbol_suffix": symbol_suffix,
            "auto_reconnect": True,
            "gateway_startup_timeout_sec": 60.0,
            "gateway_command_timeout_sec": 30.0,
        }
        symbol_map = mt5.get("symbol_map")
        if isinstance(symbol_map, dict) and symbol_map:
            runtime_kwargs["symbol_map"] = symbol_map
        return runtime_kwargs

    def _normalize_gateway_exchange_type(self, value: Any, provider: str = "") -> str:
        text = str(value or "").strip().upper()
        provider_text = str(provider or "").strip().lower()
        if text in {"IB", "IB_WEB", "IBWEB"} or provider_text.startswith("ib_web"):
            return "IB_WEB"
        if text == "MT5" or provider_text.startswith("mt5"):
            return "MT5"
        if text in {"CTP", ""}:
            return "CTP"
        return text

    def _normalize_gateway_asset_type(self, exchange_type: str, value: Any) -> str:
        text = str(value or "").strip().upper()
        if exchange_type == "IB_WEB":
            if text in {"", "STOCK", "STK", "EQUITY"}:
                return "STK"
            if text in {"FUT", "FUTURE"}:
                return "FUT"
        if exchange_type == "CTP":
            if text in {"", "FUT", "FUTURE"}:
                return "FUTURE"
        if exchange_type == "MT5":
            return text or "OTC"
        if exchange_type in {"BINANCE", "OKX"}:
            if text in {"", "SWAP", "FUT", "FUTURE"}:
                return "SWAP"
            if text == "SPOT":
                return "SPOT"
        return text or "FUTURE"

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off", ""}

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        if value in {None, ""}:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _ping_subprocess_gateway_ready(self, state: dict[str, Any]) -> bool:
        config = state.get("config")
        command_endpoint = self._get_config_value(config, "command_endpoint")
        if not command_endpoint:
            return False
        try:
            import zmq
        except ImportError:
            return False
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.DEALER)
        sock.setsockopt(zmq.IDENTITY, uuid.uuid4().hex.encode("utf-8"))
        sock.setsockopt(zmq.SNDTIMEO, 1500)
        sock.setsockopt(zmq.RCVTIMEO, 1500)
        try:
            sock.connect(command_endpoint)
            sock.send(json.dumps({
                "request_id": uuid.uuid4().hex,
                "command": "ping",
                "payload": {},
            }).encode("utf-8"))
            resp = json.loads(sock.recv().decode("utf-8"))
            return bool(isinstance(resp, dict) and (resp.get("data") or {}).get("ready"))
        except Exception:
            return False
        finally:
            sock.close()

    @staticmethod
    def _get_config_value(config: Any, key: str) -> Any:
        if config is None:
            return None
        if isinstance(config, dict):
            return config.get(key)
        return getattr(config, key, None)

    def _read_subprocess_recent_errors(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        stderr_path = state.get("stderr_path")
        if not stderr_path:
            return []
        try:
            text = Path(stderr_path).read_text(encoding="utf-8", errors="replace")[-4000:]
        except Exception:
            return []
        fatal_markers = (
            "Adapter failed to connect after",
            "ImportError:",
            "ModuleNotFoundError:",
            "Traceback",
        )
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        matched: list[str] = []
        seen: set[str] = set()
        for line in reversed(lines):
            if not any(marker in line for marker in fatal_markers):
                continue
            if line in seen:
                continue
            seen.add(line)
            matched.append(line)
            if len(matched) >= 3:
                break
        matched.reverse()
        return [{"source": "gateway", "message": line} for line in matched]

    def _parse_json_dict(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not value:
            return None
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    @staticmethod
    def _ensure_spdlog_safe() -> None:
        """Guard against spdlog C extension crash in console-less Windows processes.

        When the backend is launched with ``Start-Process -WindowStyle Hidden``
        (as ``restart_app.bat`` does), the spdlog native extension may segfault
        because there is no console.  Install a lightweight stub unconditionally
        so that the ``import bt_api_py`` chain never triggers the real extension.
        The real spdlog is NOT needed by the web backend — it only needs
        GatewayConfig (pure Python) and delegates actual gateway work to
        subprocesses that have their own spdlog.
        """
        if "spdlog" not in sys.modules:
            import types
            stub = types.ModuleType("spdlog")
            stub.__file__ = "spdlog_stub"
            sys.modules["spdlog"] = stub

    def _import_gateway_runtime_classes(self):
        if _BT_API_PY_DIR.is_dir() and str(_BT_API_PY_DIR) not in sys.path:
            sys.path.insert(0, str(_BT_API_PY_DIR))
        self._ensure_spdlog_safe()
        from bt_api_py.gateway.config import GatewayConfig
        from bt_api_py.gateway.runtime import GatewayRuntime

        return GatewayConfig, GatewayRuntime

    def _load_strategy_config(self, strategy_dir: Path) -> dict[str, Any]:
        config_path = strategy_dir / "config.yaml"
        if not config_path.is_file():
            return {}
        with config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def _load_strategy_env(self, strategy_dir: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for candidate in (strategy_dir / ".env", _BACKTRADER_WEB_DIR / ".env"):
            if not candidate.is_file():
                continue
            with candidate.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text or text.startswith("#") or "=" not in text:
                        continue
                    key, _, value = text.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in result:
                        result[key] = value
        return result

    def _resolve_strategy_dir(self, strategy_id: str) -> Path:
        text = str(strategy_id or "")
        if ".." in text or text.startswith("/") or "\\" in text:
            raise ValueError(f"Invalid strategy_id: {strategy_id}")
        path = STRATEGIES_DIR / text
        if isinstance(STRATEGIES_DIR, Path):
            return path.resolve()
        return path


# Global singleton
_manager: LiveTradingManager | None = None


def get_live_trading_manager() -> LiveTradingManager:
    """Get the global live trading manager singleton.

    Returns:
        The LiveTradingManager instance.
    """
    global _manager
    if _manager is None:
        _manager = LiveTradingManager()
    return _manager
