"""
Authentication service.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session_provider import unit_of_work
from app.db.sql_repository import SQLRepository
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    RefreshTokenRequest,
    RefreshTokenResponse,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.utils.logger import get_logger
from app.utils.security import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    generate_refresh_token_id,
    get_password_hash,
    hash_token,
    verify_password,
)

settings = get_settings()
logger = get_logger(__name__)


class AuthService:
    """Service for user authentication and authorization."""

    def __init__(self) -> None:
        """Initialize the AuthService.

        Attributes:
            user_repo: Repository for user CRUD operations.
            refresh_token_repo: Repository for refresh token operations.
        """
        self.user_repo = SQLRepository(User)
        self.refresh_token_repo = SQLRepository(RefreshToken)

    def _get_user_repo(self, session: Optional[AsyncSession] = None) -> SQLRepository[User]:
        """Return a user repository bound to the requested session scope."""
        if session is None or not isinstance(self.user_repo, SQLRepository):
            return self.user_repo
        return SQLRepository(User, session=session)

    def _get_refresh_token_repo(
        self,
        session: Optional[AsyncSession] = None,
    ) -> SQLRepository[RefreshToken]:
        """Return a refresh-token repository bound to the requested session scope."""
        if session is None or not isinstance(self.refresh_token_repo, SQLRepository):
            return self.refresh_token_repo
        return SQLRepository(RefreshToken, session=session)

    async def _issue_refresh_token(self, session: AsyncSession, user: User) -> str:
        """Create and persist one refresh token inside the caller transaction."""
        refresh_token_id = generate_refresh_token_id()
        refresh_token = create_refresh_token(
            data={
                "sub": user.id,
                "username": user.username,
                "jti": refresh_token_id,
            },
            expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

        token_record = RefreshToken(
            id=refresh_token_id,
            token_hash=hash_token(refresh_token),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
        await self._get_refresh_token_repo(session).create(token_record)
        return refresh_token

    async def _revoke_refresh_token_in_session(
        self,
        session: AsyncSession,
        token_record: RefreshToken,
    ) -> bool:
        """Mark one refresh token as revoked without committing the transaction."""
        if token_record.is_revoked:
            return False

        token_record.is_revoked = True
        token_record.revoked_at = datetime.now(timezone.utc)
        await session.flush()
        return True

    async def _revoke_all_user_tokens_in_session(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> int:
        """Revoke all active refresh tokens for one user inside the caller transaction."""
        result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked == False,  # noqa: E712 SQLAlchemy filter
            )
        )
        tokens = result.scalars().all()
        revoked_at = datetime.now(timezone.utc)
        for token in tokens:
            token.is_revoked = True
            token.revoked_at = revoked_at

        await session.flush()
        return len(tokens)

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

        # Generate access token
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

    async def login_with_refresh(
        self,
        user_login: UserLogin
    ) -> Optional[RefreshTokenResponse]:
        """Authenticate a user and generate JWT tokens with refresh token.

        Args:
            user_login: User login credentials including username and password.

        Returns:
            RefreshTokenResponse: Login successful, returns JWT access and refresh tokens.
            None: Invalid username or password, or user is inactive.
        """
        async with unit_of_work() as session:
            user_repo = self._get_user_repo(session)

            # Find user
            user = await user_repo.get_by_field("username", user_login.username)
            if not user:
                return None

            # Verify password
            if not verify_password(user_login.password, user.hashed_password):
                return None

            # Check if user is active
            if not user.is_active:
                return None

            # Generate access token
            access_token = create_access_token(
                data={
                    "sub": user.id,
                    "username": user.username,
                },
                expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
            )
            refresh_token = await self._issue_refresh_token(session, user)

        logger.info(f"User logged in with refresh token: {user.username}")

        return RefreshTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    async def refresh_tokens(
        self,
        request: RefreshTokenRequest
    ) -> Optional[RefreshTokenResponse]:
        """Refresh access token using refresh token.

        Args:
            request: Refresh token request containing the refresh token.

        Returns:
            RefreshTokenResponse: New access and refresh tokens.
            None: Invalid or expired refresh token.
        """
        from app.utils.security import decode_refresh_token

        # Decode and validate refresh token
        payload = decode_refresh_token(request.refresh_token)
        if not payload:
            return None

        user_id = payload.get("sub")
        token_id = payload.get("jti")
        if not user_id or not token_id:
            return None

        async with unit_of_work() as session:
            token_repo = self._get_refresh_token_repo(session)
            user_repo = self._get_user_repo(session)

            # Verify token exists in database and is not revoked
            token_record = await token_repo.get_by_id(token_id)
            if not token_record or token_record.is_revoked:
                return None

            # Check if token has expired (handle timezone issues with SQLite)
            expires_at = token_record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                await self._revoke_refresh_token_in_session(session, token_record)
                return None

            # Verify user still exists and is active
            user = await user_repo.get_by_id(user_id)
            if not user or not user.is_active:
                return None

            # Revoke old refresh token and issue a new one atomically.
            await self._revoke_refresh_token_in_session(session, token_record)
            access_token = create_access_token(
                data={
                    "sub": user.id,
                    "username": user.username,
                },
                expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
            )
            new_refresh_token = await self._issue_refresh_token(session, user)

        logger.info(f"Tokens refreshed for user: {user.username}")

        return RefreshTokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        )

    async def revoke_refresh_token(self, token_id: str) -> bool:
        """Revoke a refresh token.

        Args:
            token_id: The refresh token ID to revoke.

        Returns:
            True if successfully revoked, False otherwise.
        """
        async with unit_of_work() as session:
            token_record = await self._get_refresh_token_repo(session).get_by_id(token_id)
            if not token_record:
                return False
            return await self._revoke_refresh_token_in_session(session, token_record)

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user.

        Args:
            user_id: The user ID to revoke tokens for.

        Returns:
            Number of tokens revoked.
        """
        async with unit_of_work() as session:
            return await self._revoke_all_user_tokens_in_session(session, user_id)

    async def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """Change user password and revoke all refresh tokens.

        Args:
            user_id: The ID of the user.
            old_password: Current password for verification.
            new_password: New password to set.

        Returns:
            True: Password changed successfully.
            False: Old password incorrect or user not found.
        """
        async with unit_of_work() as session:
            user_repo = self._get_user_repo(session)
            user = await user_repo.get_by_id(user_id)
            if not user:
                return False
            if not verify_password(old_password, user.hashed_password):
                return False

            user.hashed_password = get_password_hash(new_password)
            await session.flush()

            # Revoke all refresh tokens for security in the same transaction.
            await self._revoke_all_user_tokens_in_session(session, user_id)

        logger.info(f"Password changed for user: {user.username}")

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

    async def logout(self, refresh_token: str) -> bool:
        """Logout user by revoking their refresh token.

        Args:
            refresh_token: The refresh token to revoke.

        Returns:
            True if successfully logged out, False otherwise.
        """
        from app.utils.security import decode_refresh_token

        payload = decode_refresh_token(refresh_token)
        if not payload:
            return False

        token_id = payload.get("jti")
        return await self.revoke_refresh_token(token_id)
