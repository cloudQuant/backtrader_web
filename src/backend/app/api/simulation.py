"""
Simulation trading instance management API routes.

This module provides endpoints for managing simulation (paper/live-like) strategy
instances, including starting, stopping, and analyzing simulated trading runs.

The implementation reuses the existing LiveTradingManager and schemas, since the
data model for instances is identical to live trading. This keeps the API
surface consistent with the frontend `simulationApi` while avoiding duplication.

Analytics endpoints (detail, kline, monthly-returns) are in simulation_analytics.py.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse

from app.api.deps import get_current_user
from app.api.simulation_analytics import router as analytics_router
from app.schemas.live_trading_instance import (
    LiveBatchResponse,
    LiveInstanceCreate,
    LiveInstanceInfo,
    LiveInstanceListResponse,
)
from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser_service import find_latest_log_dir
from app.services.strategy_service import get_strategy_dir

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(analytics_router)


def _get_manager() -> LiveTradingManager:
    """Get the manager instance used for simulation trading.

    Currently this reuses the global LiveTradingManager implementation, since the
    lifecycle and data model are identical for live and simulated instances.

    Returns:
        The global LiveTradingManager instance.
    """
    return get_live_trading_manager()


@router.get("/", response_model=LiveInstanceListResponse, summary="List simulation instances")
async def list_instances(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """List all simulation trading instances for the current user.

    Args:
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        A list of simulation instances belonging to the user.
    """
    instances = mgr.list_instances(user_id=current_user.sub)
    return {"total": len(instances), "instances": instances}


@router.post("/", response_model=LiveInstanceInfo, summary="Add simulation instance")
async def add_instance(
    req: LiveInstanceCreate,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Add a new simulation trading instance.

    Args:
        req: The instance creation request.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        The created instance information.

    Raises:
        HTTPException: If the instance cannot be created.
    """
    try:
        return mgr.add_instance(req.strategy_id, req.params, user_id=current_user.sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{instance_id}", summary="Delete simulation instance")
async def remove_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Delete a simulation trading instance.

    Args:
        instance_id: The ID of the instance to delete.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        A success message.

    Raises:
        HTTPException: If the instance is not found.
    """
    if not mgr.remove_instance(instance_id, user_id=current_user.sub):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return {"message": "Deleted successfully"}


@router.get(
    "/{instance_id}", response_model=LiveInstanceInfo, summary="Get simulation instance details"
)
async def get_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get details of a specific simulation trading instance.

    Args:
        instance_id: The ID of the instance.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

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
    "/{instance_id}/start",
    response_model=LiveInstanceInfo,
    summary="Start simulation instance",
)
async def start_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Start a simulation trading instance.

    Args:
        instance_id: The ID of the instance to start.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

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
    "/{instance_id}/stop",
    response_model=LiveInstanceInfo,
    summary="Stop simulation instance",
)
async def stop_instance(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Stop a simulation trading instance.

    Args:
        instance_id: The ID of the instance to stop.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

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
    "/start-all", response_model=LiveBatchResponse, summary="Start all simulation instances"
)
async def start_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Start all simulation trading instances for the current user.

    Args:
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        A summary of the batch start operation.
    """
    return await mgr.start_all(user_id=current_user.sub)


@router.post("/stop-all", response_model=LiveBatchResponse, summary="Stop all simulation instances")
async def stop_all(
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Stop all simulation trading instances for the current user.

    Args:
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        A summary of the batch stop operation.
    """
    return await mgr.stop_all(user_id=current_user.sub)


def _get_strategy_log_dir(mgr: LiveTradingManager, instance_id: str, user_id: str) -> Path:
    """Get the latest log directory for a simulation strategy instance.

    Args:
        mgr: The simulation manager instance.
        instance_id: The ID of the simulation instance.
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
            status_code=404,
            detail="No log data available, please run the strategy first",
        )
    return log_dir


# ==================== Log Endpoints ====================

_ALLOWED_LOG_EXTENSIONS = {".log", ".yaml", ".yml", ".json"}


def _safe_log_filename(filename: str) -> bool:
    """Check that filename is safe (no path traversal, allowed extension)."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return False
    p = Path(filename)
    return p.suffix.lower() in _ALLOWED_LOG_EXTENSIONS or filename in (
        "current_position.yaml",
        "run_info.json",
    )


@router.get(
    "/{instance_id}/logs",
    summary="List simulation log files",
)
async def list_simulation_logs(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """List log files available for a simulation instance.

    Returns:
        List of {name, size} for each log file in the strategy's log directory.
    """
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)
    files = []
    for f in sorted(log_dir.iterdir()):
        if f.is_file() and _safe_log_filename(f.name):
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            files.append({"name": f.name, "size": size})
    return {"files": files}


@router.get(
    "/{instance_id}/logs/{filename}",
    response_class=PlainTextResponse,
    summary="Get simulation log content",
)
async def get_simulation_log(
    instance_id: str,
    filename: str,
    tail: int | None = Query(default=None, ge=1, le=50000, description="Return last N lines"),
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get content of a log file. Use tail param for large files."""
    if not _safe_log_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)
    filepath = log_dir / filename
    if not filepath.is_file() or not filepath.resolve().is_relative_to(log_dir.resolve()):
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("Failed to read log %s: %s", filepath, e)
        raise HTTPException(status_code=500, detail="Failed to read log file") from e
    if tail is not None:
        lines = content.splitlines()
        content = "\n".join(lines[-tail:]) if len(lines) > tail else content
    return PlainTextResponse(content)


@router.get(
    "/{instance_id}/logs/{filename}/download",
    response_class=FileResponse,
    summary="Download simulation log file",
)
async def download_simulation_log(
    instance_id: str,
    filename: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Download a log file."""
    if not _safe_log_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)
    filepath = log_dir / filename
    if not filepath.is_file() or not filepath.resolve().is_relative_to(log_dir.resolve()):
        raise HTTPException(status_code=404, detail="Log file not found")
    return FileResponse(path=filepath, filename=filename, media_type="text/plain")


# ==================== Config Management Endpoints ====================


def _get_strategy_config_path(
    mgr: LiveTradingManager, instance_id: str, user_id: str
) -> Path:
    """Resolve the config.yaml path for a simulation instance.

    Args:
        mgr: The simulation manager instance.
        instance_id: The ID of the simulation instance.
        user_id: User ID for permission check.

    Returns:
        Path to the config.yaml file.

    Raises:
        HTTPException: If the instance is not found or config file doesn't exist.
    """
    inst = mgr.get_instance(instance_id, user_id=user_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    try:
        strategy_dir = get_strategy_dir(inst["strategy_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return strategy_dir / "config.yaml"


@router.get(
    "/{instance_id}/config",
    summary="Get simulation instance config",
)
async def get_instance_config(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Get the full config.yaml content for a simulation instance.

    Args:
        instance_id: The ID of the simulation instance.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        The parsed YAML config as a dict, plus the raw YAML text.

    Raises:
        HTTPException: If the instance or config file is not found.
    """
    import yaml as _yaml

    config_path = _get_strategy_config_path(mgr, instance_id, current_user.sub)
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail="Config file not found")

    try:
        raw = config_path.read_text(encoding="utf-8")
        parsed = _yaml.safe_load(raw) or {}
    except Exception as e:
        logger.warning("Failed to read config %s: %s", config_path, e)
        raise HTTPException(status_code=500, detail="Failed to read config") from e

    return {"config": parsed, "raw": raw}


@router.put(
    "/{instance_id}/config",
    summary="Update simulation instance config",
)
async def update_instance_config(
    instance_id: str,
    body: dict,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Update the config.yaml for a simulation instance.

    Accepts either raw YAML text (field ``raw``) or a parsed config dict
    (field ``config``).  When ``raw`` is provided it is written directly;
    otherwise the ``config`` dict is serialised to YAML.

    Args:
        instance_id: The ID of the simulation instance.
        body: Request body with ``raw`` (string) or ``config`` (dict).
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        Success message.

    Raises:
        HTTPException: If the instance is not found or write fails.
    """
    import yaml as _yaml

    config_path = _get_strategy_config_path(mgr, instance_id, current_user.sub)

    raw_text = body.get("raw")
    config_dict = body.get("config")

    if raw_text is not None:
        content = str(raw_text)
    elif config_dict is not None:
        try:
            content = _yaml.dump(
                config_dict, default_flow_style=False, allow_unicode=True, sort_keys=False
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid config: {e}") from e
    else:
        raise HTTPException(status_code=400, detail="Provide 'raw' or 'config' in body")

    # Validate YAML before writing
    try:
        _yaml.safe_load(content)
    except _yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e

    try:
        config_path.write_text(content, encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to write config %s: %s", config_path, e)
        raise HTTPException(status_code=500, detail="Failed to write config") from e

    return {"message": "Config updated successfully"}


# ==================== Log Clearing Endpoints ====================


@router.delete(
    "/{instance_id}/logs/{filename}",
    summary="Clear a simulation log file",
)
async def clear_simulation_log(
    instance_id: str,
    filename: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Clear (truncate) a single log file for a simulation instance.

    Args:
        instance_id: The ID of the simulation instance.
        filename: The log file to clear.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        Success message.

    Raises:
        HTTPException: If the file is invalid or not found.
    """
    if not _safe_log_filename(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)
    filepath = log_dir / filename
    if not filepath.is_file() or not filepath.resolve().is_relative_to(log_dir.resolve()):
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        filepath.write_text("", encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to clear log %s: %s", filepath, e)
        raise HTTPException(status_code=500, detail="Failed to clear log") from e
    return {"message": f"Log file '{filename}' cleared"}


@router.delete(
    "/{instance_id}/logs",
    summary="Clear all simulation log files",
)
async def clear_all_simulation_logs(
    instance_id: str,
    current_user=Depends(get_current_user),
    mgr: LiveTradingManager = Depends(_get_manager),
):
    """Clear (truncate) all log files for a simulation instance.

    Args:
        instance_id: The ID of the simulation instance.
        current_user: The authenticated user.
        mgr: The simulation manager instance.

    Returns:
        Summary of cleared files.

    Raises:
        HTTPException: If the log directory is not found.
    """
    log_dir = _get_strategy_log_dir(mgr, instance_id, current_user.sub)
    cleared = []
    for f in sorted(log_dir.iterdir()):
        if f.is_file() and _safe_log_filename(f.name):
            try:
                f.write_text("", encoding="utf-8")
                cleared.append(f.name)
            except OSError as e:
                logger.warning("Failed to clear log %s: %s", f, e)
    return {"message": f"Cleared {len(cleared)} log files", "cleared": cleared}
