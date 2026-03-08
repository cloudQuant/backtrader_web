"""
Authentication API routes.
"""
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.rate_limit import limiter
from app.schemas.auth import (
    ChangePassword,
    RefreshTokenRequest,
    RefreshTokenResponse,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.utils.logger import audit_logger, get_logger

router = APIRouter()
logger = get_logger(__name__)


@lru_cache
def get_auth_service():
    return AuthService()


@router.post("/register", response_model=UserResponse, summary="User registration")
@limiter.limit("5/hour")
async def register(
    user_create: UserCreate,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    """Register a new user account.

    Rate limited to 5 requests per hour per IP to prevent abuse.

    Args:
        user_create: Registration payload with username, email, and password.
        request: FastAPI request for rate limiting.
        service: Auth service dependency.

    Returns:
        The created user information.

    Raises:
        HTTPException: If the username or email already exists (400).
    """
    # Apply rate limiting via decorator is handled at router level
    user = await service.register(user_create)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        )
    return user


@router.post("/login", response_model=Token, summary="User login")
@limiter.limit("10/minute")
async def login(
    user_login: UserLogin,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    """Authenticate and return a JWT access token.

    Rate limited to 10 requests per minute per IP to prevent brute force attacks.

    Args:
        user_login: Login payload with username and password.
        request: FastAPI request for client IP and rate limiting.
        service: Auth service dependency.

    Returns:
        A token response containing the JWT access token.

    Raises:
        HTTPException: If credentials are invalid (401) or rate limit exceeded (429).
    """
    result = await service.login(user_login)
    client_ip = request.client.host if request.client else "unknown"

    if result is None:
        audit_logger.log_login(user_login.username, success=False, ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    audit_logger.log_login(user_login.username, success=True, ip=client_ip)
    logger.info(f"User logged in: {user_login.username}", user_id=user_login.username)
    return result


@router.post(
    "/login/refresh",
    response_model=RefreshTokenResponse,
    summary="User login with refresh token"
)
@limiter.limit("10/minute")
async def login_with_refresh(
    user_login: UserLogin,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    """Authenticate and return JWT access and refresh tokens.

    This endpoint provides enhanced security by issuing both an access token
    (short-lived) and a refresh token (long-lived). The refresh token can be
    used to obtain new access tokens without re-authenticating.

    Rate limited to 10 requests per minute per IP to prevent brute force attacks.

    Args:
        user_login: Login payload with username and password.
        request: FastAPI request for client IP and rate limiting.
        service: Auth service dependency.

    Returns:
        A token response containing both JWT access and refresh tokens.

    Raises:
        HTTPException: If credentials are invalid (401) or rate limit exceeded (429).
    """
    result = await service.login_with_refresh(user_login)
    client_ip = request.client.host if request.client else "unknown"

    if result is None:
        audit_logger.log_login(user_login.username, success=False, ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    audit_logger.log_login(user_login.username, success=True, ip=client_ip)
    logger.info(f"User logged in with refresh token: {user_login.username}")
    return result


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token"
)
@limiter.limit("30/minute")
async def refresh_tokens(
    request: Request,
    request_data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Refresh an access token using a refresh token.

    This endpoint implements token rotation - the old refresh token is
    revoked and a new one is issued with each refresh.

    Rate limited to 30 requests per minute per IP.

    Args:
        request: FastAPI request for rate limiting.
        request_data: Refresh token request containing the refresh token.
        auth_service: Auth service dependency.

    Returns:
        A new token response with fresh access and refresh tokens.

    Raises:
        HTTPException: If the refresh token is invalid, expired, or revoked (401).
    """
    result = await auth_service.refresh_tokens(request_data)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return result


@router.post("/logout", summary="Logout user")
@limiter.limit("30/minute")
async def logout(
    request: Request,
    request_data: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Logout user by revoking their refresh token.

    Args:
        request: FastAPI request for rate limiting.
        request_data: Request containing the refresh token to revoke.
        auth_service: Auth service dependency.

    Returns:
        Success message.
    """
    success = await auth_service.logout(request_data.refresh_token)

    if success:
        logger.info("User logged out successfully")
        return {"message": "Logged out successfully"}

    # Even if token revocation fails, return success for idempotency
    return {"message": "Logged out successfully"}


@router.put("/change-password", summary="Change password")
@limiter.limit("5/minute")
async def change_password(
    req: ChangePassword,
    request: Request,
    current_user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """Change the current user's password.

    Note: Changing password will revoke all existing refresh tokens
    for security reasons.

    Args:
        req: Password change request with old and new passwords.
        request: FastAPI request for rate limiting.
        current_user: Authenticated user from JWT token.
        service: Auth service dependency.

    Returns:
        Success message.

    Raises:
        HTTPException: If current password is incorrect (400).
    """
    success = await service.change_password(
        current_user.sub, req.old_password, req.new_password
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse, summary="Get current user info")
@limiter.limit("60/minute")
async def get_me(
    request: Request,
    current_user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """Get information about the currently authenticated user.

    Args:
        request: FastAPI request for rate limiting.
        current_user: Authenticated user from JWT token.
        service: Auth service dependency.

    Returns:
        Current user information.

    Raises:
        HTTPException: If user not found (404).
    """
    user = await service.get_user_by_id(current_user.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
