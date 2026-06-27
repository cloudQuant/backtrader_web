"""
Live trading instance manager.

Manages strategy instances (CRUD/start/stop). Uses a JSON file for persistence and runs strategies
in subprocesses.
"""

import asyncio
import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, cast

from app.services.gateway import health as gateway_health_service
from app.services.gateway import launch_builder as gateway_launch_builder
from app.services.gateway import manual as manual_gateway_service
from app.services.gateway import runtime as gateway_runtime_service
from app.services.gateway.preset import get_gateway_presets as _get_gateway_presets
from app.services.instance_store import InstanceStore
from app.services.live_trading import execution as live_execution_service
from app.services.live_trading import instance as live_instance_service
from app.services.process_supervisor import (
    is_pid_alive as _is_pid_alive_impl,
)
from app.services.process_supervisor import (
    kill_pid as _kill_pid_impl,
)
from app.services.process_supervisor import (
    scan_running_strategy_pids as _scan_running_strategy_pids_impl,
)
from app.services.strategy import runtime_support as strategy_runtime_support
from app.services.strategy.core import STRATEGIES_DIR, get_template_by_id
from app.types.live_trading import (
    ConnectResult,
    GatewayCredentials,
    GatewayData,
    HealthStatus,
    InstanceData,
    OperationResult,
    StartResult,
    StopResult,
)
from app.utils.backend_data_paths import get_backend_data_path

_logger: Any
try:
    from loguru import logger as _logger
except ImportError:
    _logger = logging.getLogger(__name__)

logger: Any = _logger

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
_DATA_DIR = get_backend_data_path()
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"
_MANUAL_GATEWAYS_FILE = _DATA_DIR / "manual_gateways.json"
_BACKTRADER_DIR = _PROJECT_ROOT.parent / "backtrader"
if not _BACKTRADER_DIR.is_dir():
    _BACKTRADER_DIR = Path.home() / "Documents" / "backtrader"


def _resolve_bt_api_py_import_dir() -> Path:
    try:
        installed_pkg_dir = manual_gateway_service._installed_bt_api_py_dir()
    except Exception:
        installed_pkg_dir = None
    if installed_pkg_dir is not None and installed_pkg_dir.is_dir():
        return installed_pkg_dir.parent

    local_src_dir = _PROJECT_ROOT / "src"
    if (local_src_dir / "bt_api_py").is_dir():
        return local_src_dir
    return Path()


_BT_API_PY_DIR = _resolve_bt_api_py_import_dir()

_DEFAULT_TRANSPORT = "tcp" if sys.platform == "win32" else "ipc"
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}


def _should_restore_manual_gateways() -> bool:
    """Return whether persisted manual gateways should auto-restore on boot."""
    raw = os.getenv("LIVE_TRADING_RESTORE_MANUAL_GATEWAYS", "true").strip().lower()
    return raw not in _FALSE_ENV_VALUES


def _load_instances() -> dict[str, dict]:
    """Load instances from the JSON file.

    Returns:
        A dictionary of instances keyed by instance ID.

    Note:
        Delegates to InstanceStore. Kept for backward compatibility.
    """
    return InstanceStore(instances_file=_INSTANCES_FILE).load_all()


def _save_instances(data: dict[str, dict]) -> None:
    """Save instances to the JSON file.

    Args:
        data: The instances dictionary to save.

    Note:
        Delegates to InstanceStore. Kept for backward compatibility.
    """
    InstanceStore(instances_file=_INSTANCES_FILE).save_all(data)


def _instance_store_lock():
    return InstanceStore(instances_file=_INSTANCES_FILE).locked()


class _AsyncInstanceStoreLock:
    def __init__(self, async_lock: asyncio.Lock | None = None) -> None:
        self._async_lock = async_lock
        self._file_lock: contextlib.AbstractContextManager | None = None
        self._async_lock_acquired = False

    async def __aenter__(self):
        if self._async_lock is not None:
            await self._async_lock.acquire()
            self._async_lock_acquired = True
        try:
            self._file_lock = _instance_store_lock()
            self._file_lock.__enter__()
        except Exception:
            self._file_lock = None
            if self._async_lock_acquired and self._async_lock is not None:
                self._async_lock.release()
                self._async_lock_acquired = False
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            if self._file_lock is not None:
                self._file_lock.__exit__(exc_type, exc, tb)
        finally:
            self._file_lock = None
            if self._async_lock_acquired and self._async_lock is not None:
                self._async_lock.release()
                self._async_lock_acquired = False
        return False


def _load_manual_gateways() -> list[dict[str, Any]]:
    """Load manually connected gateways from the JSON file."""
    if not _MANUAL_GATEWAYS_FILE.is_file():
        return []
    try:
        raw = json.loads(_MANUAL_GATEWAYS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load manual gateways: %s", exc)
        return []
    if not isinstance(raw, list):
        return []
    results: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        exchange_type = str(item.get("exchange_type") or "").strip()
        credentials = item.get("credentials")
        gateway_key = str(item.get("gateway_key") or "").strip()
        if not exchange_type or not isinstance(credentials, dict):
            continue
        entry: dict[str, Any] = {
            "exchange_type": exchange_type,
            "credentials": credentials,
        }
        if gateway_key:
            entry["gateway_key"] = gateway_key
        results.append(entry)
    return results


def _save_manual_gateways(data: list[dict[str, Any]]) -> None:
    """Persist manually connected gateways to disk."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _MANUAL_GATEWAYS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_gateway_connect_error_result(
    exchange_type: str,
    exc: Exception,
) -> ConnectResult:
    normalized = str(exchange_type or "gateway").strip().upper() or "GATEWAY"
    message = str(exc).strip()
    if message:
        message = f"{normalized}连接失败: {type(exc).__name__}: {message}"
    else:
        message = f"{normalized}连接失败: {type(exc).__name__}"
    return {
        "gateway_key": "",
        "status": "error",
        "message": message,
    }


def _find_latest_log_dir(strategy_dir: Path) -> str | None:
    """Find the latest log directory for a strategy.

    Supports logs/<subdir>/ or flat logs/ (no subdirs) for simulate strategies.

    Args:
        strategy_dir: The strategy directory path.

    Returns:
        The path to the latest log directory, or None if not found.
    """
    return strategy_runtime_support.find_latest_log_dir(strategy_dir)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Args:
        pid: The process ID to check.

    Returns:
        True if the process is alive, False otherwise.

    Note:
        Delegates to process_supervisor. Kept for backward compatibility.
    """
    return _is_pid_alive_impl(pid)


def _scan_running_strategy_pids() -> dict[str, int]:
    """Scan OS processes for running strategy run.py files.

    Returns:
        A dict mapping the absolute run.py path to its PID.

    Note:
        Delegates to process_supervisor. Kept for backward compatibility.
    """
    return _scan_running_strategy_pids_impl()


class LiveTradingManager:
    """Live trading manager (singleton pattern usage).

    Attributes:
        _processes: Dictionary of running subprocesses by instance ID.
    """

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._gateways: dict[str, dict[str, Any]] = {}
        self._instance_gateways: dict[str, str] = {}
        self._stopping_instances: set[str] = set()
        self._gateway_lock = threading.RLock()
        self._instance_op_lock = asyncio.Lock()
        self._restore_thread: threading.Thread | None = None
        # Sync process status on startup
        self._sync_status_on_boot()
        if _should_restore_manual_gateways():
            self._start_restore_manual_gateways_background()
        else:
            logger.info("Manual gateway auto-restore disabled by environment")

    def _sync_status_on_boot(self) -> None:
        with _instance_store_lock():
            live_instance_service.sync_status_on_boot(
                load_instances=_load_instances,
                save_instances=_save_instances,
                is_pid_alive=_is_pid_alive,
            )

    # ---- CRUD ----

    def list_instances(self, user_id: str | None = None) -> list[dict]:
        with _instance_store_lock():
            return live_instance_service.list_instances(
                user_id=user_id,
                load_instances=_load_instances,
                save_instances=_save_instances,
                scan_running_strategy_pids=_scan_running_strategy_pids,
                is_pid_alive=_is_pid_alive,
                resolve_strategy_dir=self._resolve_strategy_dir,
                find_latest_log_dir=_find_latest_log_dir,
            )

    @staticmethod
    def _subprocess_gateway_recent_errors(stderr_path: str) -> list[dict[str, str]]:
        path = Path(str(stderr_path or "")).expanduser()
        if not path.is_file():
            return []
        try:
            lines = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            return []
        if not lines:
            return []
        return [{"source": "gateway", "message": lines[-1]}]

    def _ping_subprocess_gateway_ready(self, state: dict[str, Any]) -> bool:
        config = state.get("config")
        command_endpoint = str(getattr(config, "command_endpoint", "") or "").strip()
        return bool(command_endpoint)

    def _build_subprocess_gateway_health(self, key: str, state: dict[str, Any]) -> HealthStatus:
        process = state.get("process")
        pid = getattr(process, "pid", None)
        is_alive = bool(pid and _is_pid_alive(pid))
        recent_errors = self._subprocess_gateway_recent_errors(str(state.get("stderr_path") or ""))
        is_ready = is_alive and self._ping_subprocess_gateway_ready(state)
        gateway_state = "running" if is_ready else ("error" if is_alive else "stopped")
        market_connection = "connected" if is_ready else "error"
        trade_connection = "connected" if is_ready else "error"
        instances = state.get("instances", set()) or set()
        ref_count = max(int(state.get("ref_count", 0) or 0), len(instances))
        if state.get("manual") and ref_count == 0:
            ref_count = 1
        return {
            "gateway_key": key,
            "state": gateway_state,
            "is_healthy": is_ready,
            "exchange": str(state.get("exchange_type") or ""),
            "asset_type": str(state.get("asset_type") or ""),
            "account_id": str(state.get("account_id") or ""),
            "market_connection": market_connection,
            "trade_connection": trade_connection,
            "uptime_sec": 0,
            "last_heartbeat": None,
            "heartbeat_age_sec": None,
            "last_tick_time": None,
            "last_order_time": None,
            "strategy_count": 0,
            "symbol_count": 0,
            "tick_count": 0,
            "order_count": 0,
            "ref_count": ref_count,
            "instances": sorted(str(item) for item in instances if item is not None),
            "recent_errors": [] if is_ready else recent_errors,
        }

    def get_gateway_health(self) -> list[HealthStatus]:
        with self._gateway_lock:
            gateways = dict(self._gateways)
        try:
            results = cast(
                "list[HealthStatus]",
                gateway_health_service.get_gateway_health(
                    gateways=gateways,
                    load_instances=_load_instances,
                    is_pid_alive=_is_pid_alive,
                    resolve_strategy_dir=self._resolve_strategy_dir,
                    load_strategy_config=self._load_strategy_config,
                    load_strategy_env=self._load_strategy_env,
                ),
            )
        except Exception:
            logger.exception("Failed to collect gateway health snapshots")
            return []
        overrides: dict[str, HealthStatus] = {}
        for key, state in gateways.items():
            if not isinstance(state, dict):
                continue
            if state.get("process_mode") != "subprocess" or state.get("runtime") is not None:
                continue
            overrides[key] = self._build_subprocess_gateway_health(key, state)
        if not overrides:
            return results
        merged: list[HealthStatus] = []
        seen: set[str] = set()
        for item in results:
            gateway_key = str(item.get("gateway_key") or "")
            if gateway_key in overrides:
                merged.append(overrides[gateway_key])
                seen.add(gateway_key)
            else:
                merged.append(item)
        for gateway_key, item in overrides.items():
            if gateway_key not in seen:
                merged.append(item)
        return merged

    def connect_gateway(self, exchange_type: str, credentials: GatewayCredentials) -> ConnectResult:
        normalized_exchange_type = self._normalize_gateway_exchange_type(exchange_type)
        try:
            with self._gateway_lock:
                result = manual_gateway_service.connect_gateway(
                    gateways=self._gateways,
                    exchange_type=exchange_type,
                    credentials=cast("dict[str, Any]", credentials),
                    normalize_exchange_type=self._normalize_gateway_exchange_type,
                    coerce_bool=self._coerce_bool,
                    coerce_float=self._coerce_float,
                    import_gateway_runtime_classes=self._import_gateway_runtime_classes,
                    default_transport=_DEFAULT_TRANSPORT,
                    logger=logger,
                )
        except Exception as exc:
            logger.exception(
                "Unhandled exception while connecting gateway %s", normalized_exchange_type
            )
            return _build_gateway_connect_error_result(normalized_exchange_type, exc)
        if result.get("status") != "error":
            gateway_key = str(result.get("gateway_key") or "").strip()
            if normalized_exchange_type == "MT5":
                try:
                    from app.services.quote_service import QuoteService

                    QuoteService().resume_auto_connect("MT5")
                except Exception:
                    logger.debug(
                        "Failed to resume MT5 auto-connect after manual connect", exc_info=True
                    )
            try:
                self._persist_manual_gateway(gateway_key, normalized_exchange_type, credentials)
            except Exception:
                logger.exception("Failed to persist manual gateway %s", gateway_key)
                message = str(result.get("message") or "").strip() or "网关已连接"
                result = dict(result)
                result["message"] = f"{message}；本地保存失败，重启后需要重新连接"
        return cast(ConnectResult, result)

    def _connect_ctp_gateway(self, key: str, credentials: GatewayCredentials) -> ConnectResult:
        return cast(
            ConnectResult,
            manual_gateway_service.connect_ctp_gateway(
                gateways=self._gateways,
                key=key,
                credentials=cast("dict[str, Any]", credentials),
                import_gateway_runtime_classes=self._import_gateway_runtime_classes,
                default_transport=_DEFAULT_TRANSPORT,
                logger=logger,
            ),
        )

    def _connect_ib_web_gateway(self, key: str, credentials: GatewayCredentials) -> ConnectResult:
        return cast(
            ConnectResult,
            manual_gateway_service.connect_ib_web_gateway(
                gateways=self._gateways,
                key=key,
                credentials=cast("dict[str, Any]", credentials),
                coerce_bool=self._coerce_bool,
                coerce_float=self._coerce_float,
                import_gateway_runtime_classes=self._import_gateway_runtime_classes,
                default_transport=_DEFAULT_TRANSPORT,
                logger=logger,
            ),
        )

    def _connect_mt5_gateway(self, key: str, credentials: GatewayCredentials) -> ConnectResult:
        return cast(
            ConnectResult,
            manual_gateway_service.connect_mt5_gateway(
                gateways=self._gateways,
                key=key,
                credentials=cast("dict[str, Any]", credentials),
                import_gateway_runtime_classes=self._import_gateway_runtime_classes,
                logger=logger,
            ),
        )

    def query_gateway_account(self, gateway_key: str) -> dict[str, str | float] | None:
        with self._gateway_lock:
            return manual_gateway_service.query_gateway_account(self._gateways, gateway_key)

    def query_gateway_positions(
        self,
        gateway_key: str,
        *,
        strict: bool = False,
    ) -> list[dict[str, Any]]:
        with self._gateway_lock:
            return manual_gateway_service.query_gateway_positions(
                self._gateways,
                gateway_key,
                strict=strict,
            )

    def query_gateway_trades(
        self,
        gateway_key: str,
        *,
        symbol: str | None = None,
        limit: int = 100,
        strict: bool = False,
    ) -> list[dict[str, Any]]:
        with self._gateway_lock:
            return manual_gateway_service.query_gateway_trades(
                self._gateways,
                gateway_key,
                symbol=symbol,
                limit=limit,
                strict=strict,
            )

    def query_gateway_orders(self, gateway_key: str) -> list[dict[str, Any]]:
        with self._gateway_lock:
            return manual_gateway_service.query_gateway_orders(self._gateways, gateway_key)

    @staticmethod
    def _instance_order_owner_ids(instance_id: str, instance: dict[str, Any]) -> set[str]:
        params = instance.get("params") if isinstance(instance.get("params"), dict) else {}
        workspace_unit = (
            params.get("workspace_unit") if isinstance(params.get("workspace_unit"), dict) else {}
        )
        candidates = {
            str(instance_id or "").strip(),
            str(instance.get("id") or "").strip(),
            str(instance.get("trading_instance_id") or "").strip(),
            str(workspace_unit.get("unit_id") or "").strip(),
        }
        return {item for item in candidates if item}

    def _cancel_open_orders_for_instance(
        self,
        instance_id: str,
        instance: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._gateway_lock:
            gateway_key = self._gateway_key_for_instance_unlocked(str(instance_id))
            if not gateway_key:
                return None
            state = self._gateways.get(gateway_key)
            if not isinstance(state, dict):
                return None
            active_instances = {
                str(item) for item in (state.get("instances", set()) or set()) if item is not None
            }
            ref_count = max(int(state.get("ref_count", 0) or 0), len(active_instances))
            cancel_unowned = ref_count <= 1 and (
                not active_instances or active_instances == {str(instance_id)}
            )
            return manual_gateway_service.cancel_gateway_open_orders(
                self._gateways,
                gateway_key,
                owner_ids=self._instance_order_owner_ids(instance_id, instance),
                cancel_unowned=cancel_unowned,
            )

    @staticmethod
    def _persist_instance_stop_metadata(instance_id: str, metadata: dict[str, Any]) -> None:
        if not metadata:
            return
        with _instance_store_lock():
            instances = _load_instances()
            inst = instances.get(instance_id)
            if not isinstance(inst, dict):
                return
            inst.update(metadata)
            instances[instance_id] = inst
            _save_instances(instances)

    def _raise_on_failed_open_order_cancel(
        self,
        instance_id: str,
        open_order_cancel: dict[str, Any] | None,
    ) -> None:
        if not isinstance(open_order_cancel, dict):
            return
        if str(open_order_cancel.get("status") or "").lower() != "error":
            return
        self._persist_instance_stop_metadata(
            instance_id,
            {"open_order_cancel": open_order_cancel},
        )
        message = str(open_order_cancel.get("message") or "failed to cancel open orders")
        exc = RuntimeError(f"停止策略前撤销交易所挂单失败：{message}")
        exc.open_order_cancel = open_order_cancel
        raise exc

    def _gateway_key_for_instance_unlocked(self, instance_id: str) -> str:
        key = str(self._instance_gateways.get(instance_id) or "").strip()
        if key:
            return key
        for gateway_key, state in self._gateways.items():
            instances = state.get("instances", set()) or set()
            if instance_id in instances or str(instance_id) in {str(item) for item in instances}:
                return str(gateway_key)
        return ""

    def has_instance_gateway(self, instance_id: str) -> bool:
        with self._gateway_lock:
            return bool(self._gateway_key_for_instance_unlocked(str(instance_id)))

    def query_instance_gateway_positions(self, instance_id: str) -> list[dict[str, Any]]:
        with self._gateway_lock:
            gateway_key = self._gateway_key_for_instance_unlocked(str(instance_id))
            if not gateway_key:
                return []
            return manual_gateway_service.query_gateway_positions(
                self._gateways,
                gateway_key,
                strict=True,
            )

    def query_instance_gateway_trades(
        self,
        instance_id: str,
        *,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._gateway_lock:
            gateway_key = self._gateway_key_for_instance_unlocked(str(instance_id))
            if not gateway_key:
                return []
            return manual_gateway_service.query_gateway_trades(
                self._gateways,
                gateway_key,
                symbol=symbol,
                limit=limit,
                strict=True,
            )

    def query_instance_gateway_account(self, instance_id: str) -> dict[str, Any] | None:
        with self._gateway_lock:
            gateway_key = self._gateway_key_for_instance_unlocked(str(instance_id))
            if not gateway_key:
                return None
            return manual_gateway_service.query_gateway_account(
                self._gateways,
                gateway_key,
                strict=True,
            )

    def query_instance_asset_specs(
        self,
        instance_id: str,
        symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        requested_symbols = [str(symbol or "").strip() for symbol in symbols]
        requested_symbols = [symbol for symbol in requested_symbols if symbol]
        if not requested_symbols:
            return {}

        with self._gateway_lock:
            gateway_key = self._gateway_key_for_instance_unlocked(str(instance_id))
            gateway = self._gateways.get(gateway_key) if gateway_key else None

        try:
            from app.services.trading_asset_info_service import (
                persist_asset_specs,
                normalize_asset_spec,
                query_gateway_asset_spec,
                query_gateway_last_price,
                query_local_asset_spec,
                resolve_asset_specs,
                symbol_aliases,
            )
        except Exception:
            return {}

        try:
            instances = _load_instances()
            instance = dict(instances.get(str(instance_id)) or {})
        except Exception:
            instance = {}

        strategy_dir: Path | None = None
        runtime_dir = str(instance.get("runtime_dir") or "").strip()
        if runtime_dir:
            strategy_dir = Path(runtime_dir).expanduser()
        else:
            strategy_id = str(instance.get("strategy_id") or "").strip()
            if strategy_id:
                try:
                    strategy_dir = self._resolve_strategy_dir(strategy_id)
                except Exception:
                    strategy_dir = None

        def _persist_resolved_specs(current_specs: dict[str, dict[str, Any]]) -> None:
            if strategy_dir is None or not current_specs:
                return
            try:
                persist_asset_specs(strategy_dir, instance, current_specs)
                with _instance_store_lock():
                    latest = _load_instances()
                    latest_instance = latest.get(str(instance_id))
                    if not isinstance(latest_instance, dict):
                        return
                    params = (
                        dict(latest_instance.get("params") or {})
                        if isinstance(latest_instance.get("params"), dict)
                        else {}
                    )
                    metadata = (
                        dict(params.get("contract_metadata") or {})
                        if isinstance(params.get("contract_metadata"), dict)
                        else {}
                    )
                    instance_params = (
                        instance.get("params") if isinstance(instance.get("params"), dict) else {}
                    )
                    resolved_metadata = instance_params.get("contract_metadata")
                    if isinstance(resolved_metadata, dict):
                        for key, value in resolved_metadata.items():
                            if isinstance(value, dict):
                                metadata[str(key)] = dict(value)
                    if metadata:
                        params["contract_metadata"] = metadata
                        latest_instance["params"] = params
                        latest[str(instance_id)] = latest_instance
                        _save_instances(latest)
            except Exception:
                logger.debug(
                    "Failed to persist queried asset specs for instance %s",
                    instance_id,
                    exc_info=True,
                )

        specs: dict[str, dict[str, Any]] = {}
        if strategy_dir is not None:
            try:
                specs = resolve_asset_specs(
                    instance,
                    strategy_dir,
                    gateway,
                    symbols=requested_symbols,
                )
            except Exception:
                specs = {}
            if specs:
                _persist_resolved_specs(specs)

        if not specs:
            for symbol in requested_symbols:
                local_spec = query_local_asset_spec(symbol)
                if not local_spec:
                    continue
                for key in symbol_aliases(symbol):
                    specs[str(key)] = dict(local_spec)

        if not gateway:
            _persist_resolved_specs(specs)
            return specs

        for symbol in requested_symbols:
            spec: dict[str, Any] = {}
            for key in symbol_aliases(symbol):
                item = specs.get(str(key))
                if isinstance(item, dict):
                    spec.update(item)
                    break
            if not spec:
                spec = dict(query_local_asset_spec(symbol) or {})
            gateway_spec = query_gateway_asset_spec(gateway, symbol)
            if gateway_spec:
                spec.update(gateway_spec)
            last_price = query_gateway_last_price(gateway, symbol)
            if last_price and last_price > 0:
                spec = dict(spec or {})
                spec["current_price"] = last_price
                spec["latest_price"] = last_price
                spec["last_price"] = last_price
            if spec:
                normalized_spec = normalize_asset_spec(
                    spec,
                    symbol=symbol,
                    source=str(spec.get("source") or "resolved"),
                )
                if normalized_spec:
                    for key in symbol_aliases(symbol):
                        specs[str(key)] = dict(normalized_spec)
        _persist_resolved_specs(specs)
        return specs

    def list_connected_gateways(self) -> list[GatewayData]:
        with self._gateway_lock:
            return cast(
                "list[GatewayData]",
                manual_gateway_service.list_connected_gateways(self._gateways),
            )

    def disconnect_gateway(self, gateway_key: str) -> OperationResult:
        with self._gateway_lock:
            result = manual_gateway_service.disconnect_gateway(self._gateways, gateway_key)
        if result.get("status") != "error":
            normalized_gateway_key = str(gateway_key or "").strip()
            if normalized_gateway_key.startswith("manual:MT5:"):
                try:
                    from app.services.quote_service import QuoteService

                    QuoteService().suppress_auto_connect("MT5")
                except Exception:
                    logger.debug(
                        "Failed to suppress MT5 auto-connect after manual disconnect", exc_info=True
                    )
            try:
                self._remove_persisted_manual_gateway(gateway_key)
            except Exception:
                logger.exception("Failed to remove persisted manual gateway %s", gateway_key)
        return cast(OperationResult, result)

    def _start_restore_manual_gateways_background(self) -> None:
        self._restore_thread = threading.Thread(target=self._restore_manual_gateways, daemon=True)
        self._restore_thread.start()

    def _restore_manual_gateways(self) -> None:
        restored_gateways: dict[str, dict[str, Any]] = {}
        for entry in _load_manual_gateways():
            exchange_type = str(entry.get("exchange_type") or "").strip()
            credentials = entry.get("credentials")
            gateway_key = str(entry.get("gateway_key") or "").strip()
            if not exchange_type or not isinstance(credentials, dict):
                continue
            result = manual_gateway_service.connect_gateway(
                gateways=restored_gateways,
                exchange_type=exchange_type,
                credentials=credentials,
                normalize_exchange_type=self._normalize_gateway_exchange_type,
                coerce_bool=self._coerce_bool,
                coerce_float=self._coerce_float,
                import_gateway_runtime_classes=self._import_gateway_runtime_classes,
                default_transport=_DEFAULT_TRANSPORT,
                logger=logger,
                allow_interactive_login=False,
            )
            if result.get("status") == "error":
                target = gateway_key or exchange_type
                logger.warning(
                    "Failed to restore manual gateway %s: %s",
                    target,
                    result.get("message", "unknown error"),
                )
        if restored_gateways:
            with self._gateway_lock:
                for key, state in restored_gateways.items():
                    self._gateways.setdefault(key, state)

    def _persist_manual_gateway(
        self,
        gateway_key: str,
        exchange_type: str,
        credentials: GatewayCredentials,
    ) -> None:
        serialized_credentials = json.loads(
            json.dumps(dict(credentials), ensure_ascii=False, default=str)
        )
        records = _load_manual_gateways()
        records = [item for item in records if item.get("gateway_key") != gateway_key]
        records.append(
            {
                "gateway_key": gateway_key,
                "exchange_type": exchange_type,
                "credentials": serialized_credentials,
            }
        )
        _save_manual_gateways(records)

    def _remove_persisted_manual_gateway(self, gateway_key: str) -> None:
        records = _load_manual_gateways()
        new_records = [item for item in records if item.get("gateway_key") != gateway_key]
        if len(new_records) != len(records):
            _save_manual_gateways(new_records)

    def get_gateway_presets(self) -> list[dict[str, str | list[dict[str, str]]]]:
        return _get_gateway_presets()

    def add_instance(
        self,
        strategy_id: str,
        params: dict[str, str | int | float | bool] | None = None,
        user_id: str | None = None,
        runtime_dir: str | None = None,
    ) -> InstanceData:
        with _instance_store_lock():
            return cast(
                InstanceData,
                live_instance_service.add_instance(
                    strategy_id=strategy_id,
                    params=params,
                    user_id=user_id,
                    runtime_dir=runtime_dir,
                    load_instances=_load_instances,
                    save_instances=_save_instances,
                    resolve_strategy_dir=self._resolve_strategy_dir,
                    get_template_by_id=get_template_by_id,
                    infer_gateway_params=self._infer_gateway_params,
                    find_latest_log_dir=_find_latest_log_dir,
                ),
            )

    def remove_instance(self, instance_id: str, user_id: str | None = None) -> bool:
        with _instance_store_lock():
            return live_instance_service.remove_instance(
                instance_id=instance_id,
                user_id=user_id,
                load_instances=_load_instances,
                save_instances=_save_instances,
                kill_pid=self._kill_pid,
                release_gateway_for_instance=self._release_gateway_for_instance,
                processes=self._processes,
            )

    def get_instance(self, instance_id: str, user_id: str | None = None) -> InstanceData | None:
        with _instance_store_lock():
            return cast(
                "InstanceData | None",
                live_instance_service.get_instance(
                    instance_id=instance_id,
                    user_id=user_id,
                    load_instances=_load_instances,
                    save_instances=_save_instances,
                    is_pid_alive=_is_pid_alive,
                    scan_running_strategy_pids=_scan_running_strategy_pids,
                    resolve_strategy_dir=self._resolve_strategy_dir,
                    find_latest_log_dir=_find_latest_log_dir,
                ),
            )

    # ---- Start/Stop ----

    async def start_instance(self, instance_id: str) -> StartResult:
        async with self._instance_op_lock:
            return cast(
                StartResult,
                await live_execution_service.start_instance(
                    instance_id=instance_id,
                    load_instances=_load_instances,
                    save_instances=_save_instances,
                    is_pid_alive=_is_pid_alive,
                    resolve_strategy_dir=self._resolve_strategy_dir,
                    build_subprocess_env=self._build_subprocess_env,
                    release_gateway_for_instance=self._release_gateway_for_instance,
                    wait_process_callback=self._wait_process,
                    processes=self._processes,
                    stopping_instances=self._stopping_instances,
                    instance_lock=_AsyncInstanceStoreLock(),
                ),
            )

    async def stop_instance(self, instance_id: str) -> StopResult:
        async with self._instance_op_lock:
            instances = _load_instances()
            inst = instances.get(instance_id, {})
            open_order_cancel = (
                self._cancel_open_orders_for_instance(instance_id, inst)
                if isinstance(inst, dict)
                else None
            )
            self._raise_on_failed_open_order_cancel(instance_id, open_order_cancel)
            return cast(
                StopResult,
                self._attach_stop_metadata(
                    instance_id,
                    await live_execution_service.stop_instance(
                        instance_id=instance_id,
                        load_instances=_load_instances,
                        save_instances=_save_instances,
                        is_pid_alive=_is_pid_alive,
                        kill_pid=self._kill_pid,
                        release_gateway_for_instance=self._release_gateway_for_instance,
                        processes=self._processes,
                        stopping_instances=self._stopping_instances,
                        instance_lock=_AsyncInstanceStoreLock(),
                    ),
                    open_order_cancel,
                ),
            )

    def _attach_stop_metadata(
        self,
        instance_id: str,
        result: dict[str, Any],
        open_order_cancel: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if open_order_cancel is None:
            return result
        result = dict(result)
        result["open_order_cancel"] = open_order_cancel
        self._persist_instance_stop_metadata(
            instance_id,
            {"open_order_cancel": open_order_cancel},
        )
        return result

    async def start_all(self, user_id: str | None = None) -> dict[str, StartResult]:
        return await live_execution_service.start_all(
            user_id=user_id,
            load_instances=_load_instances,
            is_pid_alive=_is_pid_alive,
            start_instance_callback=self.start_instance,
        )

    async def stop_all(self, user_id: str | None = None) -> dict[str, StopResult]:
        return await live_execution_service.stop_all(
            user_id=user_id,
            load_instances=_load_instances,
            stop_instance_callback=self.stop_instance,
        )

    # ---- Internal Methods ----

    async def _wait_process(self, instance_id: str, proc: asyncio.subprocess.Process) -> None:
        await live_execution_service.wait_process(
            instance_id=instance_id,
            proc=proc,
            load_instances=_load_instances,
            save_instances=_save_instances,
            resolve_strategy_dir=self._resolve_strategy_dir,
            find_latest_log_dir=_find_latest_log_dir,
            release_gateway_for_instance=self._release_gateway_for_instance,
            processes=self._processes,
            stopping_instances=self._stopping_instances,
            instance_lock=_AsyncInstanceStoreLock(self._instance_op_lock),
        )

    @staticmethod
    def _kill_pid(pid: int) -> None:
        """Kill a process by PID.

        Args:
            pid: The process ID to kill.

        Note:
            Delegates to process_supervisor.kill_pid.
        """
        _kill_pid_impl(pid, force_after_seconds=1.0)

    def _build_subprocess_env(
        self, instance_id: str, instance: dict[str, Any], strategy_dir: Path
    ) -> dict[str, str]:
        return gateway_runtime_service.build_subprocess_env(
            instance_id=instance_id,
            instance=instance,
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=self._acquire_gateway_for_instance,
            os_environ=dict(os.environ),
            bt_api_py_dir=_BT_API_PY_DIR,
            backtrader_dir=_BACKTRADER_DIR,
        )

    def _acquire_gateway_for_instance(
        self, instance_id: str, instance: dict[str, Any], strategy_dir: Path
    ) -> dict[str, Any] | None:
        return gateway_runtime_service.acquire_gateway_for_instance(
            instance_id=instance_id,
            instance=instance,
            strategy_dir=strategy_dir,
            get_gateway_params=self._get_gateway_params,
            build_gateway_launch=self._build_gateway_launch,
            gateways=self._gateways,
            instance_gateways=self._instance_gateways,
            logger=logger,
        )

    def _release_gateway_for_instance(self, instance_id: str) -> None:
        gateway_runtime_service.release_gateway_for_instance(
            instance_id=instance_id,
            gateways=self._gateways,
            instance_gateways=self._instance_gateways,
            logger=logger,
        )

    @staticmethod
    def _infer_gateway_params(strategy_dir: Path) -> dict[str, Any] | None:
        return strategy_runtime_support.infer_gateway_params(strategy_dir)

    def _get_gateway_params(self, instance: dict[str, Any]) -> dict[str, Any]:
        return gateway_launch_builder.get_gateway_params(instance, _DEFAULT_TRANSPORT)

    def _build_gateway_launch(
        self, instance: dict[str, Any], strategy_dir: Path, gateway_params: dict[str, Any]
    ) -> dict[str, Any]:
        config_data = self._load_strategy_config(strategy_dir)
        env_data = self._load_strategy_env(strategy_dir)
        gateway_config_cls, gateway_runtime_cls = self._import_gateway_runtime_classes()
        return gateway_launch_builder.build_gateway_launch(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            gateway_config_cls=gateway_config_cls,
            gateway_runtime_cls=gateway_runtime_cls,
            default_transport=_DEFAULT_TRANSPORT,
        )

    def _build_ctp_gateway_runtime_kwargs(
        self,
        config_data: dict[str, Any],
        env_data: dict[str, str],
        gateway_params: dict[str, Any],
    ) -> dict[str, Any]:
        return gateway_launch_builder.build_ctp_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            default_transport=_DEFAULT_TRANSPORT,
        )

    def _build_ib_web_gateway_runtime_kwargs(
        self,
        config_data: dict[str, Any],
        env_data: dict[str, str],
        gateway_params: dict[str, Any],
    ) -> dict[str, Any]:
        return gateway_launch_builder.build_ib_web_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            default_transport=_DEFAULT_TRANSPORT,
        )

    def _build_mt5_gateway_runtime_kwargs(
        self,
        config_data: dict[str, Any],
        env_data: dict[str, str],
        gateway_params: dict[str, Any],
    ) -> dict[str, Any]:
        return gateway_launch_builder.build_mt5_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
        )

    def _normalize_gateway_exchange_type(self, value: Any, provider: str = "") -> str:
        return gateway_launch_builder.normalize_gateway_exchange_type(value, provider)

    def _normalize_gateway_asset_type(self, exchange_type: str, value: Any) -> str:
        return gateway_launch_builder.normalize_gateway_asset_type(exchange_type, value)

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        return gateway_launch_builder.coerce_bool(value, default)

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        return gateway_launch_builder.coerce_float(value, default)

    def _parse_json_dict(self, value: Any) -> dict[str, Any] | None:
        return gateway_launch_builder.parse_json_dict(value)

    _gateway_import_ok: bool | None = None

    def _import_gateway_runtime_classes(self) -> tuple[Any, Any]:
        # Pre-flight: test import in an isolated subprocess to avoid crashing
        # the main process if a native C extension (CTP SDK, spdlog, etc.) is
        # broken or incompatible.  The check runs only once and is cached.
        if LiveTradingManager._gateway_import_ok is None:
            env = dict(os.environ)
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import sys, types; "
                        "sys.modules.setdefault('spdlog', types.ModuleType('spdlog')); "
                        "from bt_api_base.gateway.config import GatewayConfig; "
                        "from bt_api_base.gateway.runtime import GatewayRuntime; "
                        "sys.stdout.write('ok')",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                )
                if result.returncode != 0 or "ok" not in result.stdout:
                    stderr = (result.stderr or "").strip()[:500]
                    LiveTradingManager._gateway_import_ok = False
                    raise ImportError(
                        f"bt_api_base 网关模块无法加载 (插件或原生扩展不可用/已损坏)。"
                        f" stderr: {stderr}"
                    )
            except subprocess.TimeoutExpired:
                LiveTradingManager._gateway_import_ok = False
                raise ImportError(
                    "bt_api_base 网关模块导入超时，插件或原生扩展可能已损坏"
                ) from None
            LiveTradingManager._gateway_import_ok = True

        if LiveTradingManager._gateway_import_ok is False:
            raise ImportError(
                "bt_api_base 网关模块不可用 (之前的检测已失败)。请修复对应插件或原生扩展后重启后端。"
            )

        # Guard: the spdlog C extension causes a native segfault on this
        # Windows environment.  Always use a lightweight stub – spdlog is only
        # used for logging inside bt_api_py and is not essential.
        if "spdlog" not in sys.modules:
            import types

            sys.modules["spdlog"] = types.ModuleType("spdlog")
        from bt_api_base.gateway.config import GatewayConfig
        from bt_api_base.gateway.runtime import GatewayRuntime

        return GatewayConfig, GatewayRuntime

    def _load_strategy_config(self, strategy_dir: Path) -> dict[str, Any]:
        return strategy_runtime_support.load_strategy_config(strategy_dir)

    def _load_strategy_env(self, strategy_dir: Path) -> dict[str, str]:
        return strategy_runtime_support.load_strategy_env(strategy_dir, _PROJECT_ROOT)

    def _resolve_strategy_dir(self, strategy_id: str) -> Path:
        return strategy_runtime_support.resolve_strategy_dir(strategy_id, STRATEGIES_DIR)


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
