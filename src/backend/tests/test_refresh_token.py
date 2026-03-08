"""
Tests for refresh token functionality.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.user import RefreshToken, User
from app.schemas.auth import RefreshTokenRequest, UserLogin
from app.services.auth_service import AuthService
from app.utils.security import decode_refresh_token, get_password_hash, verify_password


@pytest.mark.asyncio
class TestRefreshTokenService:
    """Test suite for refresh token service methods."""

    async def test_login_with_refresh_token_returns_both_tokens(self, setup_db):
        """Test that login with refresh returns both access and refresh tokens."""
        service = AuthService()

        # Create a test user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Login with refresh token
        login_data = UserLogin(username="testuser", password="Test@123")
        result = await service.login_with_refresh(login_data)

        assert result is not None
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.token_type == "bearer"
        assert result.expires_in > 0

    async def test_refresh_token_creates_record_in_db(self, setup_db):
        """Test that a refresh token record is created in the database."""
        service = AuthService()

        # Create a test user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Login with refresh token
        login_data = UserLogin(username="testuser", password="Test@123")
        await service.login_with_refresh(login_data)

        # Verify refresh token was created
        async with async_session_maker() as session:
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.user_id == user.id)
            )
            tokens = result.scalars().all()

        assert len(tokens) == 1
        assert tokens[0].is_revoked is False
        assert tokens[0].revoked_at is None
        # Compare timestamps - handle potential timezone issues
        if tokens[0].expires_at.tzinfo is None:
            expires_at = tokens[0].expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = tokens[0].expires_at
        assert expires_at > datetime.now(timezone.utc)

    async def test_refresh_token_rotation(self, setup_db):
        """Test that refresh token rotation works (old token revoked, new one created)."""
        import asyncio
        service = AuthService()

        # Create a test user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Initial login
        login_data = UserLogin(username="testuser", password="Test@123")
        first_result = await service.login_with_refresh(login_data)
        first_refresh_token = first_result.refresh_token

        # Small delay to ensure different timestamps
        await asyncio.sleep(0.01)

        # Refresh tokens
        refresh_request = RefreshTokenRequest(refresh_token=first_refresh_token)
        second_result = await service.refresh_tokens(refresh_request)

        assert second_result is not None
        # Verify new tokens were generated (different from original)
        assert second_result.refresh_token != first_result.refresh_token

        # Verify old token is revoked
        async with async_session_maker() as session:
            result = await session.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.is_revoked.is_(True),
                )
            )
            revoked_tokens = result.scalars().all()
        assert len(revoked_tokens) == 1

    async def test_refresh_rotation_rolls_back_when_new_token_issue_fails(
        self,
        setup_db,
        monkeypatch,
    ):
        """Test that old refresh token is not revoked if rotation fails mid-transaction."""
        service = AuthService()

        async with async_session_maker() as session:
            user = User(
                username="rotation_rollback_user",
                email="rotation_rollback@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        login_data = UserLogin(username="rotation_rollback_user", password="Test@123")
        initial_tokens = await service.login_with_refresh(login_data)
        payload = decode_refresh_token(initial_tokens.refresh_token)

        async def fail_issue_refresh_token(session, user):
            del session, user
            raise RuntimeError("simulated issue failure")

        monkeypatch.setattr(service, "_issue_refresh_token", fail_issue_refresh_token)

        with pytest.raises(RuntimeError, match="simulated issue failure"):
            await service.refresh_tokens(
                RefreshTokenRequest(refresh_token=initial_tokens.refresh_token)
            )

        async with async_session_maker() as session:
            token = await session.get(RefreshToken, payload["jti"])

        assert token is not None
        assert token.is_revoked is False

    async def test_refresh_invalid_token_returns_none(self, setup_db):
        """Test that an invalid refresh token returns None."""
        service = AuthService()

        request = RefreshTokenRequest(refresh_token="invalid_token")
        result = await service.refresh_tokens(request)

        assert result is None

    async def test_refresh_revoked_token_returns_none(self, setup_db):
        """Test that a revoked refresh token cannot be used."""
        service = AuthService()

        # Create a test user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Login and get refresh token
        login_data = UserLogin(username="testuser", password="Test@123")
        first_result = await service.login_with_refresh(login_data)

        # Revoke the token
        payload = decode_refresh_token(first_result.refresh_token)
        await service.revoke_refresh_token(payload["jti"])

        # Try to refresh with revoked token
        refresh_request = RefreshTokenRequest(refresh_token=first_result.refresh_token)
        result = await service.refresh_tokens(refresh_request)

        assert result is None

    async def test_logout_revokes_refresh_token(self, setup_db):
        """Test that logout revokes the refresh token."""
        service = AuthService()

        # Create a test user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Login
        login_data = UserLogin(username="testuser", password="Test@123")
        result = await service.login_with_refresh(login_data)

        # Logout
        success = await service.logout(result.refresh_token)
        assert success is True

        # Verify token is revoked
        async with async_session_maker() as session:
            payload = decode_refresh_token(result.refresh_token)
            db_result = await session.execute(
                select(RefreshToken).where(RefreshToken.id == payload["jti"])
            )
            token = db_result.scalar_one()

        assert token.is_revoked is True
        assert token.revoked_at is not None

    async def test_change_password_revokes_all_tokens(self, setup_db):
        """Test that changing password revokes all refresh tokens."""
        service = AuthService()

        # Create a test user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Create multiple refresh tokens
        login_data = UserLogin(username="testuser", password="Test@123")
        await service.login_with_refresh(login_data)
        await service.login_with_refresh(login_data)

        # Verify 2 tokens exist
        async with async_session_maker() as session:
            result = await session.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.is_revoked.is_(False),
                )
            )
            active_tokens = result.scalars().all()
        assert len(active_tokens) == 2

        # Change password
        success = await service.change_password(user.id, "Test@123", "NewTest@456")
        assert success is True

        # Verify all tokens are revoked
        async with async_session_maker() as session:
            result = await session.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.is_revoked.is_(False),
                )
            )
            active_tokens = result.scalars().all()
        assert len(active_tokens) == 0

    async def test_change_password_rolls_back_if_token_revocation_fails(
        self,
        setup_db,
        monkeypatch,
    ):
        """Test that password update is rolled back when token revocation fails."""
        service = AuthService()

        async with async_session_maker() as session:
            user = User(
                username="password_rollback_user",
                email="password_rollback@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        login_data = UserLogin(username="password_rollback_user", password="Test@123")
        await service.login_with_refresh(login_data)
        await service.login_with_refresh(login_data)

        async def fail_revoke_all_tokens(session, user_id):
            del session, user_id
            raise RuntimeError("simulated revoke failure")

        monkeypatch.setattr(service, "_revoke_all_user_tokens_in_session", fail_revoke_all_tokens)

        with pytest.raises(RuntimeError, match="simulated revoke failure"):
            await service.change_password(user.id, "Test@123", "NewTest@456")

        async with async_session_maker() as session:
            refreshed_user = await session.get(User, user.id)
            result = await session.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.is_revoked.is_(False),
                )
            )
            active_tokens = result.scalars().all()

        assert refreshed_user is not None
        assert verify_password("Test@123", refreshed_user.hashed_password)
        assert len(active_tokens) == 2

    async def test_refresh_token_for_inactive_user_fails(self, setup_db):
        """Test that refresh token fails for inactive users."""
        service = AuthService()

        # Create an inactive user
        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
                is_active=False,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Try to create a refresh token for inactive user
        login_data = UserLogin(username="testuser", password="Test@123")
        result = await service.login_with_refresh(login_data)

        # Should return None for inactive user
        assert result is None


@pytest.mark.asyncio
class TestRefreshTokenSecurity:
    """Test suite for refresh token security features."""

    async def test_refresh_token_has_proper_expiration(self, setup_db):
        """Test that refresh tokens have proper expiration (30 days)."""
        service = AuthService()

        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        login_data = UserLogin(username="testuser", password="Test@123")
        result = await service.login_with_refresh(login_data)

        # Get the token from DB
        async with async_session_maker() as session:
            payload = decode_refresh_token(result.refresh_token)
            db_result = await session.execute(
                select(RefreshToken).where(RefreshToken.id == payload["jti"])
            )
            token = db_result.scalar_one()

        # Verify expiration is approximately 30 days from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(days=30)
        # Handle timezone issues
        if token.expires_at.tzinfo is None:
            expires_at = token.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = token.expires_at
        time_diff = abs((expires_at - expected_expiry).total_seconds())
        assert time_diff < 60  # Within 1 minute tolerance

    async def test_refresh_token_hash_is_stored(self, setup_db):
        """Test that refresh tokens are stored as hashes, not plaintext."""
        service = AuthService()

        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        login_data = UserLogin(username="testuser", password="Test@123")
        result = await service.login_with_refresh(login_data)

        # Get the token from DB
        async with async_session_maker() as session:
            payload = decode_refresh_token(result.refresh_token)
            db_result = await session.execute(
                select(RefreshToken).where(RefreshToken.id == payload["jti"])
            )
            token = db_result.scalar_one()

        # Verify stored hash is not the plaintext token
        assert token.token_hash != result.refresh_token
        assert len(token.token_hash) >= 60  # Hash should be longer

    async def test_expired_refresh_token_fails(self, setup_db):
        """Test that an expired refresh token cannot be used."""
        service = AuthService()

        async with async_session_maker() as session:
            user = User(
                username="testuser",
                email="test@example.com",
                hashed_password=get_password_hash("Test@123"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Create an expired token
        login_data = UserLogin(username="testuser", password="Test@123")
        result = await service.login_with_refresh(login_data)

        # Manually expire the token
        payload = decode_refresh_token(result.refresh_token)

        async with async_session_maker() as session:
            db_result = await session.execute(
                select(RefreshToken).where(RefreshToken.id == payload["jti"])
            )
            token = db_result.scalar_one()
            # Set expiration in the past - use timezone-aware datetime
            token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            await session.commit()

        # Try to refresh with expired token
        refresh_request = RefreshTokenRequest(refresh_token=result.refresh_token)
        refresh_result = await service.refresh_tokens(refresh_request)

        assert refresh_result is None
