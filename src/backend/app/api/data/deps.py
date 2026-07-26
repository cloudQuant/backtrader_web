"""
Dependencies for the data management module.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import security
from app.config import get_settings
from app.db.database import get_db
from app.models.permission import Role, user_roles
from app.models.user import User
from app.utils.security import decode_access_token

settings = get_settings()


async def get_current_db_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Load the authenticated database user from the access token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub") if isinstance(payload, dict) else None
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    request.state.user_id = user.id
    return user


async def user_has_admin_access(db: AsyncSession, user: User) -> bool:
    """Return whether the user has admin access for data management."""
    if user.username == settings.ADMIN_USERNAME:
        return True

    result = await db.execute(
        select(user_roles.c.role).where(
            user_roles.c.user_id == user.id,
            user_roles.c.role == Role.ADMIN.value,
        )
    )
    return result.scalar_one_or_none() is not None


async def require_data_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require an authenticated admin-capable user for data management writes."""
    user = await get_current_db_user(request=request, credentials=credentials, db=db)
    if not await user_has_admin_access(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user
