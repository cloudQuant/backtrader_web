"""
Permission models.

Implements role-based access control (RBAC).
"""
import enum
from sqlalchemy import Column, String, DateTime, Table, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.database import Base


class Permission(str, enum.Enum):
    """Permission enum."""

    # Strategy permissions
    CREATE_STRATEGY = "strategy:create"
    READ_STRATEGY = "strategy:read"
    UPDATE_STRATEGY = "strategy:update"
    DELETE_STRATEGY = "strategy:delete"
    SHARE_STRATEGY = "strategy:share"

    # Backtest permissions
    RUN_BACKTEST = "backtest:run"
    READ_BACKTEST = "backtest:read"
    DELETE_BACKTEST = "backtest:delete"
    EXPORT_BACKTEST = "backtest:export"

    # Data permissions
    UPLOAD_DATA = "data:upload"
    READ_DATA = "data:read"
    DELETE_DATA = "data:delete"

    # Admin permissions
    MANAGE_USERS = "admin:users"
    MANAGE_ROLES = "admin:roles"


class Role(str, enum.Enum):
    """Role enum."""
    GUEST = "guest"
    USER = "user"
    PREMIUM = "premium"
    ADMIN = "admin"


# Permission mapping
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


# User role association table
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', String(36), ForeignKey('users.id'), primary_key=True),
    Column('role', String(20), primary_key=True),
)
