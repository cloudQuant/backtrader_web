"""
API dependencies.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import TokenPayload
from app.utils.security import decode_access_token

security = HTTPBearer()


async def get_current_user(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    """Return the current authenticated user.

    Args:
        credentials: The HTTP authorization credentials.

    Returns:
        The token payload containing user information.

    Raises:
        HTTPException: If authentication credentials are invalid.
    """
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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[TokenPayload]:
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
