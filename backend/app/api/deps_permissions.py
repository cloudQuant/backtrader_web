"""
权限控制依赖项

实现基于角色的权限检查中间件
"""
from typing import List
from fastapi import Depends, HTTPException, status
from app.models.permission import Permission, Role, ROLE_PERMISSIONS
from app.models.user import User


def has_permission(user: User, permission: Permission) -> bool:
    """
    检查用户是否有特定权限

    Args:
        user: 用户对象
        permission: 要检查的权限

    Returns:
        bool: 是否有权限
    """
    # 收集用户所有角色的权限
    user_permissions = []
    for role in user.roles:
        user_permissions.extend(ROLE_PERMISSIONS.get(role.role, []))
    
    return permission in user_permissions


def require_permission(permission: Permission):
    """
    权限检查装饰器

    Args:
        permission: 需要的权限

    Returns:
        依赖项函数
    """
    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        return user
    
    return permission_checker


def get_current_user():
    """
    获取当前用户（占位，实际应从 JWT 解析）

    TODO: 实现从 JWT Token 解析用户
    """
    # 临时实现，实际应从认证中间件获取
    pass


# 常用权限检查依赖项
RequireCreateStrategy = Depends(require_permission(Permission.CREATE_STRATEGY))
RequireUpdateStrategy = Depends(require_permission(Permission.UPDATE_STRATEGY))
RequireDeleteStrategy = Depends(require_permission(Permission.DELETE_STRATEGY))
RequireRunBacktest = Depends(require_permission(Permission.RUN_BACKTEST))
RequireExportBacktest = Depends(require_permission(Permission.EXPORT_BACKTEST))
RequireManageUsers = Depends(require_permission(Permission.MANAGE_USERS))


# 批量权限检查
def require_any_permission(*permissions: Permission):
    """
    需要任意一个权限

    Args:
        *permissions: 权限列表

    Returns:
        依赖项函数
    """
    async def permission_checker(user: User = Depends(get_current_user)) -> User:
        user_permissions = []
        for role in user.roles:
            user_permissions.extend(ROLE_PERMISSIONS.get(role.role, []))
        
        has_any = any(p in user_permissions for p in permissions)
        if not has_any:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要以下任一权限: {', '.join([p.value for p in permissions])}"
            )
        return user
    
    return permission_checker
