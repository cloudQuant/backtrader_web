"""
Strategy version control API routes (full version).

Supports versioning, branch management, rollback, and comparisons.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging
import asyncio
import difflib
from datetime import datetime

from app.schemas.strategy_version import (
    VersionCreate,
    VersionUpdate,
    VersionResponse,
    VersionListResponse,
    VersionComparisonRequest,
    VersionComparisonResponse,
    VersionRollbackRequest,
    BranchCreate,
    BranchResponse,
    BranchListResponse,
)
from app.services.strategy_version_service import VersionControlService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


def get_version_control_service():
    """Dependency injection for VersionControlService.

    Returns:
        VersionControlService: An instance of the version control service.
    """
    return VersionControlService()


# ==================== Strategy Version API ====================

@router.post("/versions", response_model=VersionResponse, summary="Create strategy version")
async def create_strategy_version(
    request: VersionCreate,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Create a new strategy version.

    Args:
        request: The version creation request containing:
            - strategy_id: Strategy ID
            - version_name: Version name (e.g., v1.0.0)
            - code: Strategy code
            - params: Default parameters
            - branch: Branch name (default: main)
            - tags: Version tags (e.g., latest, stable)
            - changelog: Version changelog
            - is_default: Whether to set as default version
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        VersionResponse: The created version details.

    Raises:
        HTTPException: If user lacks permission to access the strategy (403).
    """
    try:
        version = await service.create_version(
            user_id=current_user.sub,
            strategy_id=request.strategy_id,
            version_name=request.version_name,
            code=request.code,
            params=request.params,
            branch=request.branch,
            tags=request.tags,
            changelog=request.changelog,
            is_default=request.is_default,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this strategy")

    # Push version creation notification
    await ws_manager.send_to_task(f"strategy:{request.strategy_id}", {
        "type": MessageType.PROGRESS,
        "strategy_id": request.strategy_id,
        "version_id": version.id,
        "message": "Strategy version has been created",
    })

    return service._to_response(version)


@router.get("/strategies/{strategy_id}/versions", response_model=VersionListResponse, summary="List strategy versions")
async def list_strategy_versions(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
    branch: Optional[str] = Query(None, description="Branch name"),
    status: Optional[str] = Query(None, description="Version status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get all versions of a strategy.

    Args:
        strategy_id: The unique identifier of the strategy.
        current_user: The authenticated user.
        service: The version control service.
        branch: Filter by branch name.
        status: Filter by version status.
        limit: Maximum number of versions to return (1-100).
        offset: Number of versions to skip.

    Returns:
        VersionListResponse: Response containing total count and version list.
    """
    versions, total = await service.list_versions(
        user_id=current_user.sub,
        strategy_id=strategy_id,
        branch=branch,
        status=status,
        limit=limit,
        offset=offset,
    )

    return VersionListResponse(total=total, items=versions)


@router.get("/versions/{version_id}", response_model=VersionResponse, summary="Get strategy version details")
async def get_strategy_version(
    version_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Get strategy version details by ID.

    Args:
        version_id: The unique identifier of the version.
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        VersionResponse: The version details.

    Raises:
        HTTPException: If the version does not exist (404) or user lacks
            permission to access it (403).
    """
    version = await service.get_version(version_id)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found"
        )

    # Permission check: versions are owned by the strategy owner (created_by).
    if getattr(version, "created_by", None) != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission to access this version"
        )

    return service._to_response(version)


@router.put("/versions/{version_id}", response_model=VersionResponse, summary="Update strategy version")
async def update_strategy_version(
    version_id: str,
    request: VersionUpdate,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Update a strategy version.

    Args:
        version_id: The unique identifier of the version to update.
        request: The update request containing:
            - code: Strategy code (optional)
            - params: Default parameters (optional)
            - description: Version description
            - tags: Version tags (optional)
            - status: Version status (optional)
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        VersionResponse: The updated version details.

    Raises:
        HTTPException: If the version does not exist or user lacks permission (404).
    """
    version = await service.update_version(version_id=version_id, user_id=current_user.sub, update_data=request)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found or no permission to update"
        )

    return service._to_response(version)


@router.post("/versions/{version_id}/set-default", summary="Set as default version")
async def set_version_default(
    version_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Set a strategy version as the default version for its branch.

    Each branch can have only one default version.

    Args:
        version_id: The unique identifier of the version.
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        A message confirming the version has been set as default.

    Raises:
        HTTPException: If the version does not exist or user lacks permission (404).
    """
    success = await service.set_version_default(version_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found or no permission to set"
        )

    return {"message": "Version has been set as default"}


@router.post("/versions/{version_id}/activate", summary="Activate strategy version")
async def activate_strategy_version(
    version_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Activate a strategy version.

    Each branch can have only one active version (currently in use).

    Args:
        version_id: The unique identifier of the version.
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        A message confirming the version has been activated.

    Raises:
        HTTPException: If the version does not exist or user lacks permission (404).
    """
    success = await service.activate_version(version_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy version not found or no permission to activate"
        )

    return {"message": "Version has been activated"}


# ==================== Version Comparison API ====================

@router.post("/versions/compare", response_model=VersionComparisonResponse, summary="Compare strategy versions")
async def compare_strategy_versions(
    request: VersionComparisonRequest,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Compare two strategy versions.

    Args:
        request: The comparison request containing:
            - strategy_id: Strategy ID
            - from_version_id: Source version ID
            - to_version_id: Target version ID
            - comparison_type: Comparison type (code, params, performance)
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        VersionComparisonResponse: The comparison results including code_diff,
            params_diff, performance_diff, and created_at timestamp.

    Raises:
        HTTPException: If user lacks permission to access the versions (403).
    """
    # comparison_type is specified in the request, but the service performs full comparison
    try:
        comparison = await service.compare_versions(
            user_id=current_user.sub,
            strategy_id=request.strategy_id,
            from_version_id=request.from_version_id,
            to_version_id=request.to_version_id,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access these versions")

    # Push comparison completion notification
    await ws_manager.send_to_task(f"strategy:{request.strategy_id}", {
        "type": MessageType.PROGRESS,
        "strategy_id": request.strategy_id,
        "comparison_id": comparison.id,
        "message": "Strategy version comparison completed",
    })

    return {
        "comparison_id": comparison.id,
        "strategy_id": comparison.strategy_id,
        "from_version_id": comparison.from_version_id,
        "to_version_id": comparison.to_version_id,
        "code_diff": comparison.code_diff,
        "params_diff": comparison.params_diff,
        "performance_diff": comparison.performance_diff,
        "created_at": comparison.created_at,
    }


# ==================== Version Rollback API ====================

@router.post("/versions/rollback", response_model=VersionResponse, summary="Rollback strategy version")
async def rollback_strategy_version(
    request: VersionRollbackRequest,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Rollback a strategy to a previous version.

    Creates a new version containing the target version's code and parameters.

    Args:
        request: The rollback request containing:
            - strategy_id: Strategy ID
            - target_version_id: Target version ID to rollback to
            - reason: Reason for rollback
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        VersionResponse: The newly created version from the rollback.

    Raises:
        HTTPException: If user lacks permission to access the versions (403).
    """
    try:
        new_version = await service.rollback_version(
            user_id=current_user.sub,
            strategy_id=request.strategy_id,
            target_version_id=request.target_version_id,
            reason=request.reason,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this version")

    # Push rollback notification
    await ws_manager.send_to_task(f"strategy:{request.strategy_id}", {
        "type": MessageType.PROGRESS,
        "strategy_id": request.strategy_id,
        "version_id": new_version.id,
        "message": "Strategy version has been rolled back",
    })

    return service._to_response(new_version)


# ==================== Strategy Branch API ====================

@router.post("/branches", response_model=BranchResponse, summary="Create strategy branch")
async def create_strategy_branch(
    request: BranchCreate,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """Create a new strategy branch.

    Args:
        request: The branch creation request containing:
            - strategy_id: Strategy ID
            - branch_name: Branch name (e.g., feature/new-indicator)
            - parent_branch: Parent branch name (e.g., main)
        current_user: The authenticated user.
        service: The version control service.

    Returns:
        BranchResponse: The created branch details.

    Branch types:
        - main: Main branch
        - dev: Development branch
        - feature/*: Feature branch
        - bugfix/*: Bug fix branch
        - release/*: Release branch

    Raises:
        HTTPException: If user lacks permission (403) or strategy not found (404).
    """
    try:
        branch = await service.create_branch(
            user_id=current_user.sub,
            strategy_id=request.strategy_id,
            branch_name=request.branch_name,
            parent_branch=request.parent_branch,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this strategy")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return service.branch_to_response(branch)


@router.get("/strategies/{strategy_id}/branches", response_model=BranchListResponse, summary="List strategy branches")
async def list_strategy_branches(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get all branches of a strategy.

    Args:
        strategy_id: The unique identifier of the strategy.
        current_user: The authenticated user.
        service: The version control service.
        limit: Maximum number of branches to return (1-100).
        offset: Number of branches to skip.

    Returns:
        BranchListResponse: Response containing total count and branch list.

    Raises:
        HTTPException: If user lacks permission (403) or strategy not found (404).
    """
    try:
        branches, total = await service.list_branches(
            user_id=current_user.sub,
            strategy_id=strategy_id,
            limit=limit,
            offset=offset,
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this strategy")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return BranchListResponse(
        total=total,
        items=[service.branch_to_response(b) for b in branches],
    )


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws/strategies/{strategy_id}")
async def strategy_version_websocket(
    websocket,
    strategy_id: str,
):
    """WebSocket endpoint for strategy version real-time updates.

    Pushes:
        - Version creation
        - Version updates
        - Version comparison completion
        - Version rollback
        - Branch updates

    Connection URL: ws://host/api/v1/strategy-versions/ws/strategies/{strategy_id}

    Message types:
        - connected: Connection successful
        - version_created: New version created
        - version_updated: Version updated
        - version_compared: Version comparison completed
        - version_rolled_back: Version rolled back
        - branch_created: New branch created
        - branch_updated: Branch updated

    Example message:
        {
            "type": "version_created",
            "strategy_id": "strategy-123",
            "version_id": "version-456",
            "data": {
                "version_name": "v1.0.0",
                "branch": "main",
                "created_at": "2024-01-01T00:00:00Z",
            }
        }

    Args:
        websocket: The WebSocket connection instance.
        strategy_id: The unique identifier of the strategy.
    """
    client_id = f"ws-version-client-{id(websocket)}"

    # Establish connection
    await ws_manager.connect(websocket, f"strategy:{strategy_id}", client_id)

    try:
        # Send initial message
        await ws_manager.send_to_task(f"strategy:{strategy_id}", {
            "type": MessageType.CONNECTED,
            "strategy_id": strategy_id,
            "message": "Strategy version control WebSocket connection successful",
        })

        # Keep connection alive
        while True:
            await asyncio.sleep(1)

            # Latest data should be fetched from version control service
            # and pushed via WebSocket
            # Temporarily using polling; should use event-driven in production

    except Exception as e:
        logger.error(f"Strategy version WebSocket error: {e}")
        ws_manager.disconnect(websocket, f"strategy:{strategy_id}", client_id)
