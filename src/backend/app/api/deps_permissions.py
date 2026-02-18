"""
Permission dependencies.

Implements role-based permission checks.
"""
from typing import List
from fastapi import Depends, HTTPException, status
from app.models.permission import Permission, Role, ROLE_PERMISSIONS
from app.models.user import User


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


def require_permission(permission: Permission):
    """Create a dependency that enforces a permission.

    Args:
        permission: The required permission.

    Returns:
        A dependency function that checks for the permission.
    """
    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return user

    return permission_checker


def get_current_user():
    """Return current user (delegates to the implementation in deps.py)."""
    from app.api.deps import get_current_user as _real_get_current_user
    return _real_get_current_user()


# Common permission dependencies
RequireCreateStrategy = Depends(require_permission(Permission.CREATE_STRATEGY))
RequireUpdateStrategy = Depends(require_permission(Permission.UPDATE_STRATEGY))
RequireDeleteStrategy = Depends(require_permission(Permission.DELETE_STRATEGY))
RequireRunBacktest = Depends(require_permission(Permission.RUN_BACKTEST))
RequireExportBacktest = Depends(require_permission(Permission.EXPORT_BACKTEST))
RequireManageUsers = Depends(require_permission(Permission.MANAGE_USERS))


# Batch permission check
def require_any_permission(*permissions: Permission):
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
                detail=f"Insufficient permissions, requires one of: {', '.join([p.value for p in permissions])}"
            )
        return user

    return permission_checker
