"""
API dependencies.
"""

import logging
import typing

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.permission import ROLE_PERMISSIONS, Permission
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.utils.security import decode_access_token

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
WEBSOCKET_TOKEN_PROTOCOL = "access-token"


def _extract_websocket_token(websocket: WebSocket) -> tuple[str | None, str | None]:
    protocols = websocket.headers.get("sec-websocket-protocol", "")
    offered = [item.strip() for item in protocols.split(",") if item.strip()]
    if len(offered) >= 2 and offered[0] == WEBSOCKET_TOKEN_PROTOCOL and offered[1]:
        return offered[1], WEBSOCKET_TOKEN_PROTOCOL
    return None, None


def get_websocket_current_user(websocket: WebSocket) -> tuple[TokenPayload | None, str | None]:
    token, accepted_subprotocol = _extract_websocket_token(websocket)
    if not token:
        return None, accepted_subprotocol

    payload = decode_access_token(token)
    if payload is None:
        return None, accepted_subprotocol

    return TokenPayload(**payload), accepted_subprotocol


async def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> TokenPayload:
    """Return the current authenticated user.

    Args:
        credentials: The HTTP authorization credentials.

    Returns:
        The token payload containing user information.

    Raises:
        HTTPException: If authentication credentials are invalid or missing.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_user = TokenPayload(**payload)
    request.state.user_id = current_user.sub
    return current_user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
) -> TokenPayload | None:
    """Optionally return the current user (None if not authenticated).

    Args:
        credentials: Optional HTTP authorization credentials.

    Returns:
        The token payload if authenticated, None otherwise.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        return None

    current_user = TokenPayload(**payload)
    request.state.user_id = current_user.sub
    return current_user


def has_permission(user: User, permission: Permission) -> bool:
    """Check whether a user has a specific permission.

    Args:
        user: The user object to check permissions for.
        permission: The permission to verify.

    Returns:
        True if the user has the permission, False otherwise.
    """
    # Aggregate permissions from all user roles.
    user_permissions = []
    for role in user.roles:
        user_permissions.extend(ROLE_PERMISSIONS.get(role.role, []))

    return permission in user_permissions


def require_permission(permission: Permission) -> typing.Any:
    """Create a dependency that enforces a permission.

    Args:
        permission: The required permission.

    Returns:
        A dependency function that checks for the permission.
    """

    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return permission_checker


# Common permission dependencies
RequireCreateStrategy = Depends(require_permission(Permission.CREATE_STRATEGY))
RequireUpdateStrategy = Depends(require_permission(Permission.UPDATE_STRATEGY))
RequireDeleteStrategy = Depends(require_permission(Permission.DELETE_STRATEGY))
RequireRunBacktest = Depends(require_permission(Permission.RUN_BACKTEST))
RequireExportBacktest = Depends(require_permission(Permission.EXPORT_BACKTEST))
RequireManageUsers = Depends(require_permission(Permission.MANAGE_USERS))


# Batch permission check
def require_any_permission(*permissions: Permission) -> typing.Any:
    """Require any one of the given permissions.

    Args:
        *permissions: Variable number of permissions to check against.

    Returns:
        A dependency function that checks for any of the specified permissions.
    """

    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        user_permissions = []
        for role in user.roles:
            user_permissions.extend(ROLE_PERMISSIONS.get(role.role, []))

        has_any = any(p in user_permissions for p in permissions)
        if not has_any:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions, requires one of: {', '.join([p.value for p in permissions])}",
            )
        return user

    return permission_checker
