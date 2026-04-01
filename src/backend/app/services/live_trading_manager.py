"""
Live trading instance manager.

Manages strategy instances (CRUD/start/stop). Uses a JSON file for persistence and runs strategies
in subprocesses.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from app.services import (
    gateway_health_service,
    gateway_launch_builder,
    gateway_runtime_service,
    live_execution_service,
    live_instance_service,
    manual_gateway_service,
    strategy_runtime_support,
)
from app.services.gateway_preset_service import get_gateway_presets as _get_gateway_presets
from app.services.instance_store import InstanceStore
from app.services.process_supervisor import (
    is_pid_alive as _is_pid_alive_impl,
)
from app.services.process_supervisor import (
    kill_pid as _kill_pid_impl,
)
from app.services.process_supervisor import (
    scan_running_strategy_pids as _scan_running_strategy_pids_impl,
)
from app.services.strategy_service import STRATEGIES_DIR, get_template_by_id
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

try:
    from loguru import logger  # type: ignore[import-untyped]  # loguru lacks py.typed marker
except ImportError:
    logger = logging.getLogger(__name__)

_WORKSPACE_DIR = Path(__file__).resolve().parents[5]
_BACKTRADER_WEB_DIR = Path(__file__).resolve().parents[4]
_BT_API_PY_DIR = _WORKSPACE_DIR / "bt_api_py"
_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"
_MANUAL_GATEWAYS_FILE = _DATA_DIR / "manual_gateways.json"

_DEFAULT_TRANSPORT = "tcp" if sys.platform == "win32" else "ipc"


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

    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._gateways: dict[str, GatewayData] = {}
        self._instance_gateways: dict[str, str] = {}
        self._stopping_instances: set[str] = set()
        # Sync process status on startup
        self._sync_status_on_boot()
        self._restore_manual_gateways()

    def _sync_status_on_boot(self) -> None:
        live_instance_service.sync_status_on_boot(
            load_instances=_load_instances,
            save_instances=_save_instances,
            is_pid_alive=_is_pid_alive,
        )

    # ---- CRUD ----

    def list_instances(self, user_id: str = None) -> list[dict]:
        return live_instance_service.list_instances(
            user_id=user_id,
            load_instances=_load_instances,
            save_instances=_save_instances,
            scan_running_strategy_pids=_scan_running_strategy_pids,
            is_pid_alive=_is_pid_alive,
            resolve_strategy_dir=self._resolve_strategy_dir,
            find_latest_log_dir=_find_latest_log_dir,
        )

    def get_gateway_health(self) -> list[HealthStatus]:
        return gateway_health_service.get_gateway_health(
            gateways=self._gateways,
            load_instances=_load_instances,
            is_pid_alive=_is_pid_alive,
            resolve_strategy_dir=self._resolve_strategy_dir,
            load_strategy_config=self._load_strategy_config,
            load_strategy_env=self._load_strategy_env,
        )

    def connect_gateway(
        self, exchange_type: str, credentials: GatewayCredentials
    ) -> ConnectResult:
        result = manual_gateway_service.connect_gateway(
            gateways=self._gateways,
            exchange_type=exchange_type,
            credentials=credentials,
            normalize_exchange_type=self._normalize_gateway_exchange_type,
            coerce_bool=self._coerce_bool,
            coerce_float=self._coerce_float,
            import_gateway_runtime_classes=self._import_gateway_runtime_classes,
            default_transport=_DEFAULT_TRANSPORT,
            logger=logger,
        )
        if result.get("status") != "error":
            gateway_key = str(result.get("gateway_key") or "").strip()
            normalized_exchange_type = self._normalize_gateway_exchange_type(exchange_type)
            self._persist_manual_gateway(gateway_key, normalized_exchange_type, credentials)
        return result

    def _connect_ctp_gateway(
        self, key: str, credentials: GatewayCredentials
    ) -> ConnectResult:
        return manual_gateway_service.connect_ctp_gateway(
            gateways=self._gateways,
            key=key,
            credentials=credentials,
            import_gateway_runtime_classes=self._import_gateway_runtime_classes,
            default_transport=_DEFAULT_TRANSPORT,
            logger=logger,
        )

    def _connect_ib_web_gateway(
        self, key: str, credentials: GatewayCredentials
    ) -> ConnectResult:
        return manual_gateway_service.connect_ib_web_gateway(
            gateways=self._gateways,
            key=key,
            credentials=credentials,
            coerce_bool=self._coerce_bool,
            coerce_float=self._coerce_float,
            import_gateway_runtime_classes=self._import_gateway_runtime_classes,
            default_transport=_DEFAULT_TRANSPORT,
            logger=logger,
        )

    def _connect_mt5_gateway(
        self, key: str, credentials: GatewayCredentials
    ) -> ConnectResult:
        return manual_gateway_service.connect_mt5_gateway(
            gateways=self._gateways,
            key=key,
            credentials=credentials,
            import_gateway_runtime_classes=self._import_gateway_runtime_classes,
            logger=logger,
        )

    def query_gateway_account(self, gateway_key: str) -> dict[str, str | float] | None:
        return manual_gateway_service.query_gateway_account(self._gateways, gateway_key)

    def query_gateway_positions(self, gateway_key: str) -> list[dict[str, str | float]]:
        return manual_gateway_service.query_gateway_positions(self._gateways, gateway_key)

    def list_connected_gateways(self) -> list[GatewayData]:
        return manual_gateway_service.list_connected_gateways(self._gateways)

    def disconnect_gateway(self, gateway_key: str) -> OperationResult:
        result = manual_gateway_service.disconnect_gateway(self._gateways, gateway_key)
        if result.get("status") != "error":
            self._remove_persisted_manual_gateway(gateway_key)
        return result

    def _restore_manual_gateways(self) -> None:
        for entry in _load_manual_gateways():
            exchange_type = str(entry.get("exchange_type") or "").strip()
            credentials = entry.get("credentials")
            gateway_key = str(entry.get("gateway_key") or "").strip()
            if not exchange_type or not isinstance(credentials, dict):
                continue
            result = manual_gateway_service.connect_gateway(
                gateways=self._gateways,
                exchange_type=exchange_type,
                credentials=credentials,
                normalize_exchange_type=self._normalize_gateway_exchange_type,
                coerce_bool=self._coerce_bool,
                coerce_float=self._coerce_float,
                import_gateway_runtime_classes=self._import_gateway_runtime_classes,
                default_transport=_DEFAULT_TRANSPORT,
                logger=logger,
            )
            if result.get("status") == "error":
                target = gateway_key or exchange_type
                logger.warning(
                    "Failed to restore manual gateway %s: %s",
                    target,
                    result.get("message", "unknown error"),
                )

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
        self, strategy_id: str, params: dict[str, str | int | float | bool] | None = None, user_id: str = None
    ) -> InstanceData:
        return live_instance_service.add_instance(
            strategy_id=strategy_id,
            params=params,
            user_id=user_id,
            load_instances=_load_instances,
            save_instances=_save_instances,
            resolve_strategy_dir=self._resolve_strategy_dir,
            get_template_by_id=get_template_by_id,
            infer_gateway_params=self._infer_gateway_params,
            find_latest_log_dir=_find_latest_log_dir,
        )

    def remove_instance(self, instance_id: str, user_id: str = None) -> bool:
        return live_instance_service.remove_instance(
            instance_id=instance_id,
            user_id=user_id,
            load_instances=_load_instances,
            save_instances=_save_instances,
            kill_pid=self._kill_pid,
            release_gateway_for_instance=self._release_gateway_for_instance,
            processes=self._processes,
        )

    def get_instance(self, instance_id: str, user_id: str = None) -> InstanceData | None:
        return live_instance_service.get_instance(
            instance_id=instance_id,
            user_id=user_id,
            load_instances=_load_instances,
            save_instances=_save_instances,
            is_pid_alive=_is_pid_alive,
            resolve_strategy_dir=self._resolve_strategy_dir,
            find_latest_log_dir=_find_latest_log_dir,
        )

    # ---- Start/Stop ----

    async def start_instance(self, instance_id: str) -> StartResult:
        return await live_execution_service.start_instance(
            instance_id=instance_id,
            load_instances=_load_instances,
            save_instances=_save_instances,
            is_pid_alive=_is_pid_alive,
            resolve_strategy_dir=self._resolve_strategy_dir,
            build_subprocess_env=self._build_subprocess_env,
            release_gateway_for_instance=self._release_gateway_for_instance,
            wait_process_callback=self._wait_process,
            processes=self._processes,
        )

    async def stop_instance(self, instance_id: str) -> StopResult:
        return await live_execution_service.stop_instance(
            instance_id=instance_id,
            load_instances=_load_instances,
            save_instances=_save_instances,
            is_pid_alive=_is_pid_alive,
            kill_pid=self._kill_pid,
            release_gateway_for_instance=self._release_gateway_for_instance,
            processes=self._processes,
            stopping_instances=self._stopping_instances,
        )

    async def start_all(self, user_id: str = None) -> dict[str, StartResult]:
        return await live_execution_service.start_all(
            user_id=user_id,
            load_instances=_load_instances,
            is_pid_alive=_is_pid_alive,
            start_instance_callback=self.start_instance,
        )

    async def stop_all(self, user_id: str = None) -> dict[str, StopResult]:
        return await live_execution_service.stop_all(
            user_id=user_id,
            load_instances=_load_instances,
            stop_instance_callback=self.stop_instance,
        )

    # ---- Internal Methods ----

    async def _wait_process(self, instance_id: str, proc: asyncio.subprocess.Process):
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
        )

    @staticmethod
    def _kill_pid(pid: int):
        """Kill a process by PID.

        Args:
            pid: The process ID to kill.

        Note:
            Delegates to process_supervisor.kill_pid.
        """
        _kill_pid_impl(pid)

    def _build_subprocess_env(
        self, instance_id: str, instance: dict[str, Any], strategy_dir: Path
    ) -> dict[str, str]:
        return gateway_runtime_service.build_subprocess_env(
            instance_id=instance_id,
            instance=instance,
            strategy_dir=strategy_dir,
            acquire_gateway_for_instance=self._acquire_gateway_for_instance,
            os_environ=os.environ,
            bt_api_py_dir=_BT_API_PY_DIR,
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

    def _import_gateway_runtime_classes(self):
        if _BT_API_PY_DIR.is_dir() and str(_BT_API_PY_DIR) not in sys.path:
            sys.path.insert(0, str(_BT_API_PY_DIR))
        # Guard: the spdlog C extension may crash on some Windows environments.
        # Try importing the real module first; only fall back to a lightweight
        # stub when the native extension is genuinely unavailable.
        if "spdlog" not in sys.modules:
            try:
                import spdlog as _spdlog_real  # noqa: F401
            except Exception:
                import types
                sys.modules["spdlog"] = types.ModuleType("spdlog")
        from bt_api_py.gateway.config import GatewayConfig
        from bt_api_py.gateway.runtime import GatewayRuntime

        return GatewayConfig, GatewayRuntime

    def _load_strategy_config(self, strategy_dir: Path) -> dict[str, Any]:
        return strategy_runtime_support.load_strategy_config(strategy_dir)

    def _load_strategy_env(self, strategy_dir: Path) -> dict[str, str]:
        return strategy_runtime_support.load_strategy_env(strategy_dir, _BACKTRADER_WEB_DIR)

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
