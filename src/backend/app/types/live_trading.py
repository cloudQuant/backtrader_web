"""
Type definitions for live trading module.

Provides TypedDict and type aliases to replace Any types in live trading services.
"""

from typing import TypedDict

from typing_extensions import NotRequired


class InstanceData(TypedDict, total=False):
    """Live trading instance data structure."""

    id: str
    strategy_id: str
    user_id: str
    status: str  # pending, running, stopped, error
    pid: int
    created_at: str
    updated_at: str
    params: dict[str, str | int | float | bool]
    gateway_type: str
    gateway_key: str
    log_dir: str
    error: str


class GatewayCredentials(TypedDict, total=False):
    """Gateway connection credentials."""

    # CTP specific
    userid: str
    password: str
    brokerid: str
    td_address: str
    md_address: str
    appid: str
    auth_code: str
    # IB specific
    host: str
    port: int
    client_id: int
    # MT5 specific
    login: int
    server: str
    # Common
    exchange_type: str
    asset_type: str
    provider: str


class GatewayData(TypedDict, total=False):
    """Gateway runtime data."""

    key: str
    type: str
    status: str  # connected, disconnected, error
    gateway: object  # GatewayRuntime instance
    account_info: dict[str, str | float]
    positions: list[dict[str, str | float]]
    error: str
    pid: int


class GatewayPreset(TypedDict):
    """Gateway preset configuration."""

    type: str
    name: str
    exchange_type: str
    asset_type: str
    provider: str
    fields: list[dict[str, str]]


class StrategyConfig(TypedDict, total=False):
    """Strategy configuration from config.yaml."""

    strategy: dict[str, str | int | float | bool]
    gateway: dict[str, str | int | float | bool]
    data: dict[str, str | int | float | bool]


class SubprocessEnv(TypedDict):
    """Environment variables for subprocess."""

    PYTHONPATH: str
    STRATEGY_ID: str
    INSTANCE_ID: str
    LOG_DIR: str
    GATEWAY_TYPE: NotRequired[str]
    GATEWAY_KEY: NotRequired[str]


class GatewayLaunchParams(TypedDict, total=False):
    """Parameters for launching a gateway."""

    gateway_type: str
    transport: str
    td_address: str
    md_address: str
    userid: str
    password: str
    brokerid: str
    appid: str
    auth_code: str
    host: str
    port: int
    client_id: int
    login: int
    server: str


class HealthStatus(TypedDict, total=False):
    """Gateway health status.

    Mirrors the dict produced by ``gateway.health`` snapshots and
    ``LiveTradingManager._build_subprocess_gateway_health``.
    """

    gateway_key: str
    state: str
    is_healthy: bool
    exchange: str
    asset_type: str
    account_id: str
    market_connection: str
    trade_connection: str
    uptime_sec: float
    last_heartbeat: float | None
    heartbeat_age_sec: float | None
    last_tick_time: float | None
    last_order_time: float | None
    strategy_count: int
    symbol_count: int
    tick_count: int
    order_count: int
    ref_count: int
    instances: list[str]
    recent_errors: list[dict[str, str]]


class InstanceListResult(TypedDict):
    """Result of listing instances."""

    instances: list[InstanceData]
    total: int


class OperationResult(TypedDict, total=False):
    """Result of an operation.

    Mirrors the dict shape returned by gateway/instance service helpers,
    which use ``status``/``message`` (and an optional ``gateway_key``).
    """

    status: str
    message: str
    gateway_key: str
    success: bool
    data: dict


class StartResult(OperationResult, total=False):
    """Result of starting an instance."""

    pid: int


class StopResult(OperationResult, total=False):
    """Result of stopping an instance."""

    was_running: bool


class ConnectResult(OperationResult, total=False):
    """Result of connecting a gateway."""

    key: str
