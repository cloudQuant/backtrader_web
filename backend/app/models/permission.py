"""
权限控制模型

实现基于角色的访问控制（RBAC）
"""
import enum
from sqlalchemy import Column, String, DateTime, Table, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base


class Permission(str, enum.Enum):
    """权限枚举"""
    
    # 策略权限
    CREATE_STRATEGY = "strategy:create"
    READ_STRATEGY = "strategy:read"
    UPDATE_STRATEGY = "strategy:update"
    DELETE_STRATEGY = "strategy:delete"
    SHARE_STRATEGY = "strategy:share"
    
    # 回测权限
    RUN_BACKTEST = "backtest:run"
    READ_BACKTEST = "backtest:read"
    DELETE_BACKTEST = "backtest:delete"
    EXPORT_BACKTEST = "backtest:export"
    
    # 数据权限
    UPLOAD_DATA = "data:upload"
    READ_DATA = "data:read"
    DELETE_DATA = "data:delete"
    
    # 管理权限
    MANAGE_USERS = "admin:users"
    MANAGE_ROLES = "admin:roles"


class Role(str, enum.Enum):
    """角色枚举"""
    GUEST = "guest"
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"


# 权限映射
ROLE_PERMISSIONS = {
    Role.GUEST: [
        Permission.READ_STRATEGY,
        Permission.READ_BACKTEST,
    ],
    Role.USER: [
        Permission.CREATE_STRATEGY,
        Permission.READ_STRATEGY,
        Permission.UPDATE_STRATEGY,
        Permission.DELETE_STRATEGY,
        Permission.RUN_BACKTEST,
        Permission.READ_BACKTEST,
        Permission.DELETE_BACKTEST,
        Permission.READ_DATA,
    ],
    Role.PREMIUM: [
        Permission.CREATE_STRATEGY,
        Permission.READ_STRATEGY,
        Permission.UPDATE_STRATEGY,
        Permission.DELETE_STRATEGY,
        Permission.SHARE_STRATEGY,
        Permission.RUN_BACKTEST,
        Permission.READ_BACKTEST,
        Permission.DELETE_BACKTEST,
        Permission.EXPORT_BACKTEST,
        Permission.UPLOAD_DATA,
        Permission.READ_DATA,
    ],
    Role.ADMIN: [
        Permission.CREATE_STRATEGY,
        Permission.READ_STRATEGY,
        Permission.UPDATE_STRATEGY,
        Permission.DELETE_STRATEGY,
        Permission.SHARE_STRATEGY,
        Permission.RUN_BACKTEST,
        Permission.READ_BACKTEST,
        Permission.DELETE_BACKTEST,
        Permission.EXPORT_BACKTEST,
        Permission.UPLOAD_DATA,
        Permission.READ_DATA,
        Permission.DELETE_DATA,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
    ],
}


# 用户角色关联表
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', String(36), ForeignKey('users.id'), primary_key=True),
    Column('role', String(20), primary_key=True),
)
