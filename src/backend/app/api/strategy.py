"""
Strategy API routes.
"""

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_current_user
from app.schemas.strategy import (
    StrategyCopilotBacktestRequest,
    StrategyCopilotBacktestResponse,
    StrategyCopilotDraftRequest,
    StrategyCopilotDraftResponse,
    StrategyCreate,
    StrategyDraftWorkspaceAddRequest,
    StrategyDraftWorkspaceAddResponse,
    StrategyListResponse,
    StrategyResponse,
    StrategyUpdate,
)
from app.services.strategy_service import (
    StrategyService,
    get_strategy_dir,
    get_strategy_readme,
    get_template_by_id,
)
from app.utils.response_cache import cache_response

_logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache
def get_strategy_service():
    return StrategyService()


@router.post("/", response_model=StrategyResponse, summary="Create strategy")
async def create_strategy(
    strategy: StrategyCreate,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Create a new strategy.

    Args:
        strategy: Strategy payload.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        The created strategy.
    """
    result = await service.create_strategy(current_user.sub, strategy)
    return result


@router.get("/", response_model=StrategyListResponse, summary="List strategies")
@cache_response(ttl=30, key_prefix="strategies")
async def list_strategies(
    request: Request,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: str = Query(None, description="Filter by category"),
):
    """List strategies for the current user.

    Args:
        current_user: Authenticated user.
        service: Strategy service dependency.
        limit: Maximum number of records to return.
        offset: Number of records to skip.
        category: Optional category filter.

    Returns:
        List of strategies.
    """
    results = await service.list_strategies(current_user.sub, limit, offset, category)
    return results


@router.get("/templates", summary="Get strategy templates")
async def get_templates(
    category: str = Query(None, description="Filter by category"),
    strategy_type: str = Query(
        None, description="Filter by strategy type (backtest/simulate/live)"
    ),
    service: StrategyService = Depends(get_strategy_service),
):
    """Get built-in strategy templates (optionally filtered by category).

    Args:
        category: Optional category filter.
        strategy_type: Optional strategy type filter.
        service: Strategy service dependency.

    Returns:
        Dictionary containing templates and total count.
    """
    from app.schemas.strategy import StrategyType

    stype = None
    if strategy_type:
        try:
            stype = StrategyType(strategy_type)
        except ValueError as e:
            _logger.debug(f"Invalid strategy_type '{strategy_type}': {e}")

    templates = await service.get_templates(stype)
    if category:
        templates = [t for t in templates if t.category == category]
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{template_id:path}/readme", summary="Get strategy README documentation")
async def get_template_readme(template_id: str):
    """Get the template README.md content (Markdown).

    Args:
        template_id: The strategy template identifier.

    Returns:
        Dictionary containing template_id and README content.

    Raises:
        HTTPException: If README not found.
    """
    readme = get_strategy_readme(template_id)
    if readme is None:
        raise HTTPException(status_code=404, detail="README not found")
    return {"template_id": template_id, "content": readme}


@router.get("/templates/{template_id:path}/config", summary="Get strategy configuration")
async def get_template_config(template_id: str):
    """Read `config.yaml` for a strategy template.

    Args:
        template_id: The strategy template identifier.

    Returns:
        A dict containing:
        - strategy: name/description/author
        - params: parameter specs (including defaults)
        - data: data settings (symbol, data type)
        - backtest: backtest settings (initial cash, commission)

    Raises:
        HTTPException: If config file not found.
    """
    import yaml as _yaml

    try:
        config_path = get_strategy_dir(template_id) / "config.yaml"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not config_path.is_file():
        raise HTTPException(status_code=404, detail="Strategy configuration file not found")

    with open(config_path, encoding="utf-8") as f:
        config = _yaml.safe_load(f) or {}

    return {
        "strategy_id": template_id,
        "strategy": config.get("strategy", {}),
        "params": config.get("params", {}),
        "data": config.get("data", {}),
        "backtest": config.get("backtest", {}),
    }


@router.get("/templates/{template_id:path}", summary="Get strategy template detail")
async def get_template_detail(template_id: str):
    """Get a single strategy template (includes code and params).

    Args:
        template_id: The strategy template identifier.

    Returns:
        The strategy template.

    Raises:
        HTTPException: If template not found.
    """
    template = get_template_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Strategy template not found")
    return template


@router.post(
    "/copilot/draft",
    response_model=StrategyCopilotDraftResponse,
    summary="Generate strategy copilot draft",
)
async def generate_strategy_copilot_draft(
    data: StrategyCopilotDraftRequest,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Generate a structured strategy draft from natural language input."""
    return await service.generate_copilot_draft(current_user.sub, data)


@router.post(
    "/copilot/workspaces/{workspace_id}/units",
    response_model=StrategyDraftWorkspaceAddResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add strategy copilot draft to workspace",
)
async def add_strategy_copilot_draft_to_workspace(
    workspace_id: str,
    data: StrategyDraftWorkspaceAddRequest,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Persist a strategy draft and add it to a workspace unit."""
    result = await service.add_copilot_draft_to_workspace(current_user.sub, workspace_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Workspace or strategy not found")
    return result


@router.post(
    "/copilot/workspaces/{workspace_id}/backtest",
    response_model=StrategyCopilotBacktestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add strategy copilot draft to workspace and run backtest",
)
async def backtest_strategy_copilot_draft(
    workspace_id: str,
    data: StrategyCopilotBacktestRequest,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Persist a strategy draft, create a workspace unit, and trigger backtest."""
    result = await service.backtest_copilot_draft(current_user.sub, workspace_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Workspace or strategy not found")
    return result


@router.get("/{strategy_id}", response_model=StrategyResponse, summary="Get strategy detail")
async def get_strategy(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Get a strategy detail by id.

    Args:
        strategy_id: The strategy ID.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        The strategy details.

    Raises:
        HTTPException: If strategy not found.
    """
    strategy = await service.get_strategy(strategy_id, current_user.sub)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse, summary="Update strategy")
async def update_strategy(
    strategy_id: str,
    strategy_update: StrategyUpdate,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Update a strategy.

    Args:
        strategy_id: The strategy ID.
        strategy_update: Strategy update payload.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        The updated strategy.

    Raises:
        HTTPException: If strategy not found or no permission.
    """
    result = await service.update_strategy(strategy_id, current_user.sub, strategy_update)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found or no permission to modify",
        )
    return result


@router.delete("/{strategy_id}", summary="Delete strategy")
async def delete_strategy(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """Delete a strategy.

    Args:
        strategy_id: The strategy ID.
        current_user: Authenticated user.
        service: Strategy service dependency.

    Returns:
        Success message.

    Raises:
        HTTPException: If strategy not found or no permission.
    """
    success = await service.delete_strategy(strategy_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found or no permission to delete",
        )
    return {"message": "Deleted successfully"}
