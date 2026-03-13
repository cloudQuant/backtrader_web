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
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id

logger = logging.getLogger(__name__)

_WORKSPACE_DIR = Path(__file__).resolve().parents[5]
_BACKTRADER_WEB_DIR = Path(__file__).resolve().parents[4]
_BT_API_PY_DIR = _WORKSPACE_DIR / "bt_api_py"
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"

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
    expected = {"value.log", "data.log", "trade.log"}
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
        for key, state in self._gateways.items():
            runtime = state.get("runtime")
            if runtime is None:
                continue
            health = getattr(runtime, "health", None)
            snap: dict[str, Any] = health.snapshot() if health is not None else {}
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
        account_id = credentials.get("account_id") or credentials.get("user_id") or ""
        key = f"manual:{exchange_type}:{account_id}"

        # Check if already connected
        if key in self._gateways:
            return {"gateway_key": key, "status": "connected", "message": "Gateway already active"}

        if exchange_type == "CTP":
            return self._connect_ctp_gateway(key, credentials)
        if exchange_type == "IB_WEB":
            return self._connect_ib_web_gateway(key, credentials)
        if exchange_type == "MT5":
            return self._connect_mt5_gateway(key, credentials)
        # Binance / OKX — placeholder: store as connected without runtime
        self._gateways[key] = {
            "config": None,
            "runtime": None,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": exchange_type,
            "account_id": account_id,
        }
        return {
            "gateway_key": key,
            "status": "connected",
            "message": f"{exchange_type} gateway registered (no runtime)",
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
            gateway_config_cls, gateway_runtime_cls = self._import_gateway_runtime_classes()
            kwargs = {
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
                "account_id": credentials.get("account_id") or credentials["user_id"],
                "transport": _DEFAULT_TRANSPORT,
                "md_address": credentials["md_front"],
                "td_address": credentials["td_front"],
                "broker_id": credentials["broker_id"],
                "investor_id": credentials["user_id"],
                "user_id": credentials["user_id"],
                "password": credentials["password"],
                "app_id": credentials.get("app_id", "simnow_client_test"),
                "auth_code": credentials.get("auth_code", "0000000000000000"),
            }
            config = gateway_config_cls.from_kwargs(**kwargs)
            runtime = gateway_runtime_cls(config, **kwargs)
            runtime.start_in_thread()
            self._gateways[key] = {
                "config": config,
                "runtime": runtime,
                "instances": set(),
                "ref_count": 0,
                "lock": threading.Lock(),
                "manual": True,
                "exchange_type": "CTP",
                "account_id": kwargs["account_id"],
            }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "CTP gateway started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect CTP gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"CTP连接失败: {type(e).__name__}: {e}",
            }

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
            gateway_config_cls, gateway_runtime_cls = self._import_gateway_runtime_classes()
            kwargs = {
                "exchange_type": "IB_WEB",
                "asset_type": credentials.get("asset_type", "STK"),
                "account_id": account_id,
                "transport": _DEFAULT_TRANSPORT,
                "base_url": credentials.get("base_url", "https://localhost:5000"),
                "verify_ssl": self._coerce_bool(credentials.get("verify_ssl"), default=False),
                "timeout": self._coerce_float(credentials.get("timeout"), default=10.0),
            }
            if credentials.get("access_token"):
                kwargs["access_token"] = credentials["access_token"]
            config = gateway_config_cls.from_kwargs(**kwargs)
            runtime = gateway_runtime_cls(config, **kwargs)
            runtime.start_in_thread()
            self._gateways[key] = {
                "config": config,
                "runtime": runtime,
                "instances": set(),
                "ref_count": 0,
                "lock": threading.Lock(),
                "manual": True,
                "exchange_type": "IB_WEB",
                "account_id": account_id,
            }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "IB Web gateway started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect IB Web gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"IB Web连接失败: {type(e).__name__}: {e}",
            }

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
            gateway_config_cls, gateway_runtime_cls = self._import_gateway_runtime_classes()
            account_id = credentials.get("account_id") or str(login)
            kwargs = {
                "exchange_type": "MT5",
                "asset_type": "OTC",
                "account_id": account_id,
                "transport": "tcp",
                "login": int(login),
                "password": str(password),
                "ws_uri": credentials.get("ws_uri", ""),
                "symbol_suffix": credentials.get("symbol_suffix", ""),
                "auto_reconnect": True,
            }
            if credentials.get("symbol_map"):
                kwargs["symbol_map"] = credentials["symbol_map"]
            config = gateway_config_cls.from_kwargs(**kwargs)
            runtime = gateway_runtime_cls(config, **kwargs)
            runtime.start_in_thread()
            self._gateways[key] = {
                "config": config,
                "runtime": runtime,
                "instances": set(),
                "ref_count": 0,
                "lock": threading.Lock(),
                "manual": True,
                "exchange_type": "MT5",
                "account_id": account_id,
            }
            return {
                "gateway_key": key,
                "status": "connected",
                "message": "MT5 gateway started successfully",
            }
        except Exception as e:
            logger.exception("Failed to connect MT5 gateway %s", key)
            return {
                "gateway_key": key,
                "status": "error",
                "message": f"MT5连接失败: {type(e).__name__}: {e}",
            }

    def query_gateway_account(self, gateway_key: str) -> dict[str, Any] | None:
        """Query account info from a connected gateway.

        Args:
            gateway_key: The gateway key to query.

        Returns:
            Account dict or None if unavailable.
        """
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
        for key, state in self._gateways.items():
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
        return env

    def _acquire_gateway_for_instance(
        self, instance_id: str, instance: dict[str, Any], strategy_dir: Path
    ) -> dict[str, Any] | None:
        gateway_params = self._get_gateway_params(instance)
        if not gateway_params.get("enabled"):
            return None
        launch = self._build_gateway_launch(instance, strategy_dir, gateway_params)
        key = launch["config"].runtime_name
        state = self._gateways.get(key)
        if state is None:
            runtime = launch["runtime_cls"](launch["config"], **launch["runtime_kwargs"])
            runtime.start_in_thread()
            state = {
                "config": launch["config"],
                "runtime": runtime,
                "instances": set(),
                "ref_count": 0,
                "lock": threading.Lock(),
            }
            self._gateways[key] = state
        state["instances"].add(instance_id)
        state["ref_count"] += 1
        self._instance_gateways[instance_id] = key
        return state

    def _release_gateway_for_instance(self, instance_id: str) -> None:
        key = self._instance_gateways.pop(instance_id, None)
        if not key:
            return
        state = self._gateways.get(key)
        if state is None:
            return
        state["instances"].discard(instance_id)
        state["ref_count"] = max(int(state.get("ref_count", 0)) - 1, 0)
        if state["ref_count"] > 0:
            return
        runtime = state.get("runtime")
        if runtime is not None:
            runtime.stop()
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
        cookies = gateway_params.get("cookies") or self._parse_json_dict(
            env_data.get("IB_WEB_COOKIES_JSON")
        )
        if cookies is None and isinstance(ib_web.get("cookies"), dict):
            cookies = ib_web.get("cookies")
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
        }
        if access_token:
            runtime_kwargs["access_token"] = access_token
        if cookie_source:
            runtime_kwargs["cookie_source"] = cookie_source
        if cookie_browser:
            runtime_kwargs["cookie_browser"] = cookie_browser
        if cookie_path:
            runtime_kwargs["cookie_path"] = cookie_path
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

    def _import_gateway_runtime_classes(self):
        if _BT_API_PY_DIR.is_dir() and str(_BT_API_PY_DIR) not in sys.path:
            sys.path.insert(0, str(_BT_API_PY_DIR))
        # Guard: the spdlog C extension may crash the process on some Windows
        # environments.  Pre-insert a lightweight stub into sys.modules so that
        # ``import spdlog`` inside bt_api_py returns the stub instead of
        # attempting to load the native DLL.  We unconditionally stub because
        # a try/except cannot catch a native DLL segfault.
        if "spdlog" not in sys.modules:
            import types
            sys.modules["spdlog"] = types.ModuleType("spdlog")
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
