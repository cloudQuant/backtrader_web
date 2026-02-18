"""
Authentication API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.auth import (
    UserCreate,
    UserLogin,
    UserResponse,
    Token,
    ChangePassword,
)
from app.services.auth_service import AuthService
from app.api.deps import get_current_user

router = APIRouter()


def get_auth_service():
    return AuthService()


@router.post("/register", response_model=UserResponse, summary="User registration")
async def register(
    user_create: UserCreate,
    service: AuthService = Depends(get_auth_service),
):
    """Register a new user account.

    Args:
        user_create: Registration payload with username, email, and password.
        service: Auth service dependency.

    Returns:
        The created user information.

    Raises:
        HTTPException: If the username or email already exists (400).
    """
    user = await service.register(user_create)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        )
    return user


@router.post("/login", response_model=Token, summary="User login")
async def login(
    user_login: UserLogin,
    service: AuthService = Depends(get_auth_service),
):
    """Authenticate and return a JWT access token.

    Args:
        user_login: Login payload with username and password.
        service: Auth service dependency.

    Returns:
        A token response containing the JWT access token.

    Raises:
        HTTPException: If credentials are invalid (401).
    """
    result = await service.login(user_login)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return result


@router.put("/change-password", summary="Change password")
async def change_password(
    req: ChangePassword,
    current_user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """Change the current user's password.

    Args:
        req: Password change request with old and new passwords.
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
async def get_me(
    current_user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """Get information about the currently authenticated user.

    Args:
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
