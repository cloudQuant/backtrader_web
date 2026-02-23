"""
Authentication service.
"""
from datetime import timedelta
from typing import Optional

from app.config import get_settings
from app.db.sql_repository import SQLRepository
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserLogin, UserResponse
from app.utils.security import create_access_token, get_password_hash, verify_password

settings = get_settings()


class AuthService:
    """Service for user authentication and authorization."""

    def __init__(self) -> None:
        """Initialize the AuthService.

        Attributes:
            user_repo: Repository for user CRUD operations.
        """
        self.user_repo = SQLRepository(User)

    async def register(self, user_create: UserCreate) -> Optional[UserResponse]:
        """Register a new user.

        Args:
            user_create: User registration data including username,
                email, and password.

        Returns:
            UserResponse: Registration successful, returns user information.
            None: Username or email already exists.
        """
        # Check if username already exists
        existing = await self.user_repo.get_by_field("username", user_create.username)
        if existing:
            return None

        # Check if email already exists
        existing = await self.user_repo.get_by_field("email", user_create.email)
        if existing:
            return None

        # Create user
        user = User(
            username=user_create.username,
            email=user_create.email,
            hashed_password=get_password_hash(user_create.password),
        )

        user = await self.user_repo.create(user)

        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        )

    async def login(self, user_login: UserLogin) -> Optional[Token]:
        """Authenticate a user and generate JWT token.

        Args:
            user_login: User login credentials including username and password.

        Returns:
            Token: Login successful, returns JWT access token.
            None: Invalid username or password.
        """
        # Find user
        user = await self.user_repo.get_by_field("username", user_login.username)
        if not user:
            return None

        # Verify password
        if not verify_password(user_login.password, user.hashed_password):
            return None

        # Generate token
        access_token = create_access_token(
            data={
                "sub": user.id,
                "username": user.username,
            },
            expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    async def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """Change user password.

        Args:
            user_id: The ID of the user.
            old_password: Current password for verification.
            new_password: New password to set.

        Returns:
            True: Password changed successfully.
            False: Old password incorrect or user not found.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False
        if not verify_password(old_password, user.hashed_password):
            return False
        await self.user_repo.update(
            user.id, {"hashed_password": get_password_hash(new_password)}
        )
        return True

    async def get_user_by_id(self, user_id: str) -> Optional[UserResponse]:
        """Get user by ID.

        Args:
            user_id: The unique identifier for the user.

        Returns:
            UserResponse if found, None otherwise.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return None

        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        )
