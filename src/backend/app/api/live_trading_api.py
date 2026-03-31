"""
Live trading instance management API routes.

This module provides endpoints for managing live trading strategy instances,
including starting, stopping, and monitoring live trading operations.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.analytics import (
    BacktestDetailResponse,
    KlineWithSignalsResponse,
    MonthlyReturnsResponse,
    PerformanceMetrics,
)
from app.schemas.live_trading_instance import (
    GatewayConnectRequest,
    GatewayConnectResponse,
    LiveBatchResponse,
    LiveGatewayPresetListResponse,
    LiveInstanceCreate,
    LiveInstanceInfo,
    LiveInstanceListResponse,
)
from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser_service import (
    find_latest_log_dir,
    parse_all_logs,
    parse_data_log,
    parse_trade_log,
    parse_value_log,
)
from app.services.strategy_service import get_strategy_dir

_logger = logging.getLogger(__name__)

router = APIRouter()


def _get_manager() -> LiveTradingManager:
    """Get the live trading manager instance.

    Returns:
        The global LiveTradingManager instance.
    """
    return get_live_trading_manager()


def _first_non_empty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return ""


@router.get("/", response_model=LiveInstanceListResponse, summary="List live trading instances")
async def list_instances(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """List all live trading instances for the current user.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A list of live trading instances belonging to the user.
    """
    instances = mgr.list_instances(user_id=current_user.sub)
    return {"total": len(instances), "instances": instances}


@router.get(
    "/presets",
    response_model=LiveGatewayPresetListResponse,
    summary="List live trading gateway presets",
)
async def list_gateway_presets(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    presets = mgr.get_gateway_presets()
    return {"total": len(presets), "presets": presets}


@router.get(
    "/gateways/credentials",
    summary="Get saved gateway credentials for form pre-fill",
)
async def get_gateway_credentials(
    current_user=Depends(get_current_user),
):
    """Return credentials from .env for pre-filling the connect form.

    All fields are returned as-is; the frontend can override any value.
    """
    from app.config import get_settings
    s = get_settings()
    ib_web_login_mode = str(s.IB_WEB_LOGIN_MODE or "").strip().lower()
    ib_web_default_is_paper = ib_web_login_mode == "paper"
    ib_web_default_is_live = ib_web_login_mode == "live"
    return {
        "CTP": {
            "broker_id": s.CTP_BROKER_ID,
            "user_id": s.CTP_USER_ID or s.CTP_INVESTOR_ID,
            "password": s.CTP_PASSWORD,
            "app_id": s.CTP_APP_ID,
            "auth_code": s.CTP_AUTH_CODE,
        },
        "MT5": {
            "login": s.MT5_LOGIN,
            "password": s.MT5_PASSWORD,
            "server": s.MT5_SERVER,
            "ws_uri": s.MT5_WS_URI,
            "symbol_suffix": s.MT5_SYMBOL_SUFFIX,
            "timeout": s.MT5_TIMEOUT,
            "demo": {
                "login": s.MT5_DEMO_LOGIN or s.MT5_LOGIN,
                "password": s.MT5_DEMO_PASSWORD or s.MT5_PASSWORD,
                "server": s.MT5_DEMO_SERVER or s.MT5_SERVER,
                "ws_uri": s.MT5_DEMO_WS_URI or s.MT5_WS_URI,
                "symbol_suffix": s.MT5_SYMBOL_SUFFIX,
                "timeout": s.MT5_TIMEOUT,
            },
            "live": {
                "login": s.MT5_LIVE_LOGIN or s.MT5_LOGIN,
                "password": s.MT5_LIVE_PASSWORD or s.MT5_PASSWORD,
                "server": s.MT5_LIVE_SERVER or s.MT5_SERVER,
                "ws_uri": s.MT5_LIVE_WS_URI or s.MT5_WS_URI,
                "symbol_suffix": s.MT5_SYMBOL_SUFFIX,
                "timeout": s.MT5_TIMEOUT,
            },
        },
        "IB_WEB": {
            "account_id": _first_non_empty(s.IB_WEB_ACCOUNT_ID, s.IB_ACCOUNT_ID),
            "asset_type": _first_non_empty(s.IB_WEB_ASSET_TYPE, s.IB_ASSET_TYPE, "STK"),
            "base_url": _first_non_empty(s.IB_WEB_BASE_URL, s.IB_BASE_URL),
            "access_token": _first_non_empty(s.IB_WEB_ACCESS_TOKEN, s.IB_ACCESS_TOKEN),
            "verify_ssl": s.IB_WEB_VERIFY_SSL if s.IB_WEB_BASE_URL or s.IB_WEB_ACCOUNT_ID or s.IB_WEB_COOKIE_SOURCE or s.IB_WEB_USERNAME else s.IB_VERIFY_SSL,
            "timeout": _first_non_empty(s.IB_WEB_TIMEOUT, s.IB_TIMEOUT, 10),
            "cookie_source": _first_non_empty(s.IB_WEB_COOKIE_SOURCE, s.IB_COOKIE_SOURCE),
            "cookie_browser": _first_non_empty(s.IB_WEB_COOKIE_BROWSER, s.IB_COOKIE_BROWSER, "chrome"),
            "cookie_path": _first_non_empty(s.IB_WEB_COOKIE_PATH, s.IB_COOKIE_PATH, "/sso"),
            "username": _first_non_empty(s.IB_WEB_USERNAME, s.IB_USERNAME),
            "password": _first_non_empty(s.IB_WEB_PASSWORD, s.IB_PASSWORD),
            "login_mode": _first_non_empty(s.IB_WEB_LOGIN_MODE, "paper"),
            "login_browser": _first_non_empty(s.IB_WEB_LOGIN_BROWSER, s.IB_LOGIN_BROWSER, "chrome"),
            "login_headless": s.IB_WEB_LOGIN_HEADLESS if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME else s.IB_LOGIN_HEADLESS,
            "login_timeout": _first_non_empty(s.IB_WEB_LOGIN_TIMEOUT, s.IB_LOGIN_TIMEOUT, 180),
            "cookie_output": _first_non_empty(s.IB_WEB_COOKIE_OUTPUT, s.IB_COOKIE_OUTPUT),
            "paper": {
                "account_id": _first_non_empty(s.IB_PAPER_ACCOUNT_ID, s.IB_WEB_ACCOUNT_ID if ib_web_default_is_paper else "", s.IB_ACCOUNT_ID),
                "asset_type": _first_non_empty(s.IB_PAPER_ASSET_TYPE, s.IB_WEB_ASSET_TYPE if ib_web_default_is_paper else "", s.IB_ASSET_TYPE, "STK"),
                "base_url": _first_non_empty(s.IB_PAPER_BASE_URL, s.IB_WEB_BASE_URL if ib_web_default_is_paper else "", s.IB_BASE_URL),
                "access_token": _first_non_empty(s.IB_PAPER_ACCESS_TOKEN, s.IB_WEB_ACCESS_TOKEN if ib_web_default_is_paper else "", s.IB_ACCESS_TOKEN),
                "verify_ssl": s.IB_PAPER_VERIFY_SSL if s.IB_PAPER_BASE_URL or s.IB_PAPER_ACCOUNT_ID or s.IB_PAPER_ACCESS_TOKEN else s.IB_VERIFY_SSL,
                "timeout": _first_non_empty(s.IB_PAPER_TIMEOUT, s.IB_WEB_TIMEOUT if ib_web_default_is_paper else 0, s.IB_TIMEOUT, 10),
                "cookie_source": _first_non_empty(s.IB_PAPER_COOKIE_SOURCE, s.IB_WEB_COOKIE_SOURCE if ib_web_default_is_paper else "", s.IB_COOKIE_SOURCE),
                "cookie_browser": _first_non_empty(s.IB_PAPER_COOKIE_BROWSER, s.IB_WEB_COOKIE_BROWSER if ib_web_default_is_paper else "", s.IB_COOKIE_BROWSER, "chrome"),
                "cookie_path": _first_non_empty(s.IB_PAPER_COOKIE_PATH, s.IB_WEB_COOKIE_PATH if ib_web_default_is_paper else "", s.IB_COOKIE_PATH, "/sso"),
                "username": _first_non_empty(s.IB_WEB_USERNAME, s.IB_USERNAME),
                "password": _first_non_empty(s.IB_WEB_PASSWORD, s.IB_PASSWORD),
                "login_mode": "paper",
                "login_browser": _first_non_empty(s.IB_WEB_LOGIN_BROWSER, s.IB_LOGIN_BROWSER, "chrome"),
                "login_headless": s.IB_WEB_LOGIN_HEADLESS if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME else s.IB_LOGIN_HEADLESS,
                "login_timeout": _first_non_empty(s.IB_WEB_LOGIN_TIMEOUT, s.IB_LOGIN_TIMEOUT, 180),
                "cookie_output": _first_non_empty(s.IB_WEB_COOKIE_OUTPUT, s.IB_COOKIE_OUTPUT),
            },
            "live": {
                "account_id": _first_non_empty(s.IB_LIVE_ACCOUNT_ID, s.IB_WEB_ACCOUNT_ID if ib_web_default_is_live else "", s.IB_ACCOUNT_ID),
                "asset_type": _first_non_empty(s.IB_LIVE_ASSET_TYPE, s.IB_WEB_ASSET_TYPE if ib_web_default_is_live else "", s.IB_ASSET_TYPE, "STK"),
                "base_url": _first_non_empty(s.IB_LIVE_BASE_URL, s.IB_WEB_BASE_URL if ib_web_default_is_live else "", s.IB_BASE_URL),
                "access_token": _first_non_empty(s.IB_LIVE_ACCESS_TOKEN, s.IB_WEB_ACCESS_TOKEN if ib_web_default_is_live else "", s.IB_ACCESS_TOKEN),
                "verify_ssl": s.IB_LIVE_VERIFY_SSL if s.IB_LIVE_BASE_URL or s.IB_LIVE_ACCOUNT_ID or s.IB_LIVE_ACCESS_TOKEN else s.IB_VERIFY_SSL,
                "timeout": _first_non_empty(s.IB_LIVE_TIMEOUT, s.IB_WEB_TIMEOUT if ib_web_default_is_live else 0, s.IB_TIMEOUT, 10),
                "cookie_source": _first_non_empty(s.IB_LIVE_COOKIE_SOURCE, s.IB_WEB_COOKIE_SOURCE if ib_web_default_is_live else "", s.IB_COOKIE_SOURCE),
                "cookie_browser": _first_non_empty(s.IB_LIVE_COOKIE_BROWSER, s.IB_WEB_COOKIE_BROWSER if ib_web_default_is_live else "", s.IB_COOKIE_BROWSER, "chrome"),
                "cookie_path": _first_non_empty(s.IB_LIVE_COOKIE_PATH, s.IB_WEB_COOKIE_PATH if ib_web_default_is_live else "", s.IB_COOKIE_PATH, "/sso"),
                "username": _first_non_empty(s.IB_WEB_USERNAME, s.IB_USERNAME),
                "password": _first_non_empty(s.IB_WEB_PASSWORD, s.IB_PASSWORD),
                "login_mode": "live",
                "login_browser": _first_non_empty(s.IB_WEB_LOGIN_BROWSER, s.IB_LOGIN_BROWSER, "chrome"),
                "login_headless": s.IB_WEB_LOGIN_HEADLESS if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME else s.IB_LOGIN_HEADLESS,
                "login_timeout": _first_non_empty(s.IB_WEB_LOGIN_TIMEOUT, s.IB_LOGIN_TIMEOUT, 180),
                "cookie_output": _first_non_empty(s.IB_WEB_COOKIE_OUTPUT, s.IB_COOKIE_OUTPUT),
            },
        },
        "BINANCE": {
            "account_id": s.BINANCE_ACCOUNT_ID,
            "asset_type": s.BINANCE_ASSET_TYPE,
            "api_key": s.BINANCE_API_KEY,
            "secret_key": s.BINANCE_SECRET_KEY,
            "testnet": s.BINANCE_TESTNET,
            "base_url": s.BINANCE_BASE_URL,
        },
        "OKX": {
            "account_id": s.OKX_ACCOUNT_ID,
            "asset_type": s.OKX_ASSET_TYPE,
            "api_key": s.OKX_API_KEY,
            "secret_key": s.OKX_SECRET_KEY,
            "passphrase": s.OKX_PASSPHRASE,
            "testnet": s.OKX_TESTNET,
            "base_url": s.OKX_BASE_URL,
        },
    }


@router.get(
    "/gateways/health",
    summary="Get health status of all active gateways",
)
async def get_gateway_health(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Return health snapshots for all active gateway runtimes.

    Returns:
        A list of gateway health snapshots with state, connection,
        heartbeat, tick/order counts, and recent errors.
    """
    gateways = mgr.get_gateway_health()
    return {"total": len(gateways), "gateways": gateways}


@router.post(
    "/gateways/connect",
    response_model=GatewayConnectResponse,
    summary="Manually connect a gateway",
)
def connect_gateway(
    req: GatewayConnectRequest,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Manually connect a gateway with provided credentials.

    Supports CTP, IB_WEB, BINANCE, MT5, and OKX exchange types.
    Uses ``def`` (not ``async def``) so the blocking subprocess start
    runs in a thread-pool instead of stalling the event loop.
    """
    result = mgr.connect_gateway(req.exchange_type, req.credentials)
    if result["status"] == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result


@router.post(
    "/gateways/disconnect",
    response_model=GatewayConnectResponse,
    summary="Disconnect a manually-started gateway",
)
async def disconnect_gateway(
    gateway_key: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Disconnect a manually-started gateway by its key."""
    result = mgr.disconnect_gateway(gateway_key)
    if result["status"] == "error":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    return result


@router.get(
    "/gateways/connected",
    summary="List manually connected gateways",
)
async def list_connected_gateways(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """List all manually connected gateways with basic info."""
    gateways = mgr.list_connected_gateways()
    return {"total": len(gateways), "gateways": gateways}


@router.get(
    "/gateways/{gateway_key}/account",
    summary="Query account info from a connected gateway",
)
async def query_gateway_account(
    gateway_key: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Query account info from a connected gateway."""
    result = mgr.query_gateway_account(gateway_key)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gateway '{gateway_key}' not found or has no runtime",
        )
    return result


@router.get(
    "/gateways/{gateway_key}/positions",
    summary="Query positions from a connected gateway",
)
async def query_gateway_positions(
    gateway_key: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Query positions from a connected gateway."""
    positions = mgr.query_gateway_positions(gateway_key)
    return {"total": len(positions), "positions": positions}


@router.post("/", response_model=LiveInstanceInfo, summary="Add live trading instance")
async def add_instance(
    req: LiveInstanceCreate,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Add a new live trading instance.

    Args:
        req: The instance creation request.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The created instance information.

    Raises:
        HTTPException: If the instance cannot be created.
    """
    try:
        return mgr.add_instance(req.strategy_id, req.params, user_id=current_user.sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{instance_id}", summary="Delete live trading instance")
async def remove_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Delete a live trading instance.

    Args:
        instance_id: The ID of the instance to delete.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A success message.

    Raises:
        HTTPException: If the instance is not found.
    """
    if not mgr.remove_instance(instance_id, user_id=current_user.sub):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return {"message": "Deleted successfully"}


@router.get(
    "/{instance_id}", response_model=LiveInstanceInfo, summary="Get live trading instance details"
)
async def get_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get details of a specific live trading instance.

    Args:
        instance_id: The ID of the instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The instance information.

    Raises:
        HTTPException: If the instance is not found.
    """
    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return inst


@router.post(
    "/{instance_id}/start", response_model=LiveInstanceInfo, summary="Start live trading instance"
)
async def start_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Start a live trading instance.

    Args:
        instance_id: The ID of the instance to start.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The updated instance information.

    Raises:
        HTTPException: If the instance cannot be started.
    """
    try:
        return await mgr.start_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{instance_id}/stop", response_model=LiveInstanceInfo, summary="Stop live trading instance"
)
async def stop_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Stop a live trading instance.

    Args:
        instance_id: The ID of the instance to stop.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        The updated instance information.

    Raises:
        HTTPException: If the instance cannot be stopped.
    """
    try:
        return await mgr.stop_instance(instance_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/start-all", response_model=LiveBatchResponse, summary="Start all live trading instances"
)
async def start_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Start all live trading instances.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A summary of the batch start operation.
    """
    return await mgr.start_all(user_id=current_user.sub)


@router.post(
    "/stop-all", response_model=LiveBatchResponse, summary="Stop all live trading instances"
)
async def stop_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Stop all live trading instances.

    Args:
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        A summary of the batch stop operation.
    """
    return await mgr.stop_all(user_id=current_user.sub)


# ==================== Analytics Endpoints ====================


def _get_strategy_log_dir(mgr: LiveTradingManager, instance_id: str, user_id: str) -> Path:
    """Get the latest log directory for a strategy instance.

    Args:
        mgr: The live trading manager instance.
        instance_id: The ID of the live trading instance.
        user_id: User ID for permission check.

    Returns:
        The path to the log directory.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    inst = mgr.get_instance(instance_id, user_id=user_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    try:
        strategy_dir = get_strategy_dir(inst["strategy_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_dir = find_latest_log_dir(strategy_dir)
    if not log_dir:
        raise HTTPException(
            status_code=404, detail="No log data available, please run the strategy first"
        )
    return log_dir


@router.get(
    "/{instance_id}/detail",
    response_model=BacktestDetailResponse,
    summary="Get live trading analysis details",
)
async def get_live_detail(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get detailed analysis for a live trading instance.

    Args:
        instance_id: The ID of the live trading instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        Detailed backtest analysis response including metrics, equity curve, and trades.

    Raises:
        HTTPException: If the instance or log data is not found.
    """
    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        strategy_dir = get_strategy_dir(inst["strategy_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_result = parse_all_logs(strategy_dir)
    if not log_result:
        raise HTTPException(status_code=404, detail="No log data available")

    # Construct response in the same format as backtest analysis
    equity_dates = log_result.get("equity_dates", [])
    equity_values = log_result.get("equity_curve", [])
    cash_values = log_result.get("cash_curve", [])
    _dd_values = log_result.get("drawdown_curve", [])
    trades_raw = log_result.get("trades", [])

    equity_curve = []
    drawdown_curve = []
    peak = 0.0
    for i, dt in enumerate(equity_dates):
        val = equity_values[i] if i < len(equity_values) else 0
        c = cash_values[i] if i < len(cash_values) else 0
        pv = val - c
        equity_curve.append(
            {
                "date": dt,
                "total_assets": val,
                "cash": c,
                "position_value": round(pv, 2),
                "benchmark": None,
            }
        )
        if val > peak:
            peak = val
        dd_pct = -((peak - val) / peak) if peak > 0 else 0
        drawdown_curve.append(
            {
                "date": dt,
                "drawdown": round(dd_pct, 6),
                "peak": round(peak, 2),
                "trough": round(val, 2),
            }
        )

    trades = []
    cum_pnl = 0.0
    for i, t in enumerate(trades_raw):
        pnl = t.get("pnlcomm", t.get("pnl", 0))
        cum_pnl += pnl
        trades.append(
            {
                "id": i + 1,
                "datetime": t.get("datetime", t.get("dtclose", "")),
                "symbol": t.get("data_name", inst["strategy_id"]),
                "direction": t.get("direction", "long"),
                "price": t.get("price", 0),
                "size": t.get("size", 0),
                "value": t.get("value", 0),
                "commission": t.get("commission", 0),
                "pnl": round(pnl, 2),
                "return_pct": None,
                "holding_days": t.get("barlen", 0),
                "cumulative_pnl": round(cum_pnl, 2),
            }
        )

    metrics = PerformanceMetrics(
        initial_capital=log_result.get("initial_cash", 100000),
        final_assets=log_result.get("final_value", 0),
        total_return=log_result.get("total_return", 0),
        annualized_return=log_result.get("annual_return", 0),
        max_drawdown=log_result.get("max_drawdown", 0),
        sharpe_ratio=log_result.get("sharpe_ratio", 0),
        win_rate=log_result.get("win_rate", 0),
        trade_count=log_result.get("total_trades", 0),
    )

    return BacktestDetailResponse(
        task_id=instance_id,
        strategy_name=inst.get("strategy_name", inst["strategy_id"]),
        symbol=inst["strategy_id"],
        start_date=equity_dates[0] if equity_dates else "",
        end_date=equity_dates[-1] if equity_dates else "",
        metrics=metrics,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trades,
        created_at=inst.get("created_at", ""),
    )


@router.get(
    "/{instance_id}/kline",
    response_model=KlineWithSignalsResponse,
    summary="Get live trading K-line data",
)
async def get_live_kline(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get K-line data with trading signals for a live trading instance.

    Args:
        instance_id: The ID of the live trading instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        K-line data with buy/sell signals and indicators.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    inst = mgr.get_instance(instance_id, user_id=current_user.sub)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)

    kline_data = parse_data_log(log_dir)
    trades_raw = parse_trade_log(log_dir)

    kline_dates = kline_data.get("dates", [])
    ohlc_data = kline_data.get("ohlc", [])
    volumes = kline_data.get("volumes", [])
    log_indicators = kline_data.get("indicators", {})

    klines = []
    for j, dt in enumerate(kline_dates):
        if j >= len(ohlc_data):
            break
        row = ohlc_data[j]
        klines.append(
            {
                "date": dt,
                "open": round(row[0], 4),
                "high": round(row[3], 4),
                "low": round(row[2], 4),
                "close": round(row[1], 4),
                "volume": volumes[j] if j < len(volumes) else 0,
            }
        )

    # Build K-line close price mapping for signal price lookup
    kline_close_map = {}
    for k in klines:
        kline_close_map[k["date"]] = k["close"]

    # Trading signals (distinguish long/short direction, prefer K-line close price)
    signals = []
    for t in trades_raw:
        is_long = t.get("direction", "buy") == "buy" or t.get("long", True)
        if t.get("dtopen"):
            open_date = t["dtopen"][:10]
            signals.append(
                {
                    "date": open_date,
                    "type": "buy" if is_long else "sell",
                    "price": kline_close_map.get(open_date, t.get("price", 0)),
                    "reason": "open",
                }
            )
        if t.get("dtclose"):
            close_date = t["dtclose"][:10]
            signals.append(
                {
                    "date": close_date,
                    "type": "sell" if is_long else "buy",
                    "price": kline_close_map.get(close_date, t.get("price", 0)),
                    "reason": "close",
                }
            )

    indicators = log_indicators if log_indicators else {}

    return KlineWithSignalsResponse(
        symbol=inst["strategy_id"] if inst else "",
        klines=klines,
        signals=signals,
        indicators=indicators,
    )


@router.get(
    "/{instance_id}/monthly-returns",
    response_model=MonthlyReturnsResponse,
    summary="Get live trading monthly returns",
)
async def get_live_monthly_returns(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get monthly returns for a live trading instance.

    Args:
        instance_id: The ID of the live trading instance.
        current_user: The authenticated user.
        mgr: The live trading manager instance.

    Returns:
        Monthly returns data with yearly summaries.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)
    value_data = parse_value_log(log_dir)

    equity_dates = value_data.get("dates", [])
    equity_values = value_data.get("equity_curve", [])

    # Calculate monthly returns
    monthly_returns = {}
    current_month = None
    month_start_value = 0.0

    for i, dt in enumerate(equity_dates):
        value = equity_values[i] if i < len(equity_values) else 0
        try:
            month_key = dt[:7]  # "YYYY-MM"
            if month_key != current_month:
                if current_month and month_start_value > 0:
                    ret = (equity_values[i - 1] - month_start_value) / month_start_value
                    monthly_returns[current_month] = round(ret, 6)
                month_start_value = value
                current_month = month_key
        except Exception as e:
            _logger.debug(f"Error calculating monthly return for {dt}: {e}")

    if current_month and month_start_value > 0:
        ret = (equity_values[-1] - month_start_value) / month_start_value
        monthly_returns[current_month] = round(ret, 6)

    # Format returns
    returns = []
    years_set = set()
    for ym, ret in monthly_returns.items():
        parts = ym.split("-")
        y, m = int(parts[0]), int(parts[1])
        years_set.add(y)
        returns.append({"year": y, "month": m, "return_pct": ret})

    years = sorted(years_set)

    # Yearly summary
    summary = {}
    for y in years:
        year_rets = [r["return_pct"] for r in returns if r["year"] == y]
        total = 1.0
        for r in year_rets:
            total *= 1 + r
        summary[str(y)] = round(total - 1, 6)

    return MonthlyReturnsResponse(
        returns=returns,
        years=years,
        summary=summary,
    )
