"""
API dependencies.
"""

import logging

from fastapi import Depends, HTTPException, Request, Response, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.auth import TokenPayload
from app.utils.security import decode_access_token

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)
WEBSOCKET_TOKEN_PROTOCOL = "access-token"


def mark_deprecated(response: Response, successor: str, endpoint_name: str) -> None:
    """Add deprecation headers to response.

    Args:
        response: The FastAPI response object.
        successor: The successor endpoint path.
        endpoint_name: Human-readable name for logging.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'
    logger.warning(
        "Deprecated %s endpoint called. Successor: %s. "
        "This endpoint will be removed in v2.0.0.",
        endpoint_name,
        successor,
    )


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
