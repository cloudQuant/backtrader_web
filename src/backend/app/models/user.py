"""
User ORM model.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):
    """User account table.

    Attributes:
        id: Unique user identifier (UUID).
        username: Unique username for login.
        email: Unique email address.
        hashed_password: Bcrypt hashed password.
        is_active: Whether the account is active.
        created_at: Account creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    strategies = relationship("Strategy", back_populates="user")
    backtest_tasks = relationship("BacktestTask", back_populates="user")
    comparisons = relationship("Comparison", back_populates="user")
    paper_trading_accounts = relationship("Account", back_populates="user")
    alerts = relationship("Alert", back_populates="user")
    alert_rules = relationship("AlertRule", back_populates="user")
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """Refresh token storage for JWT token rotation.

    Attributes:
        id: Unique token identifier.
        token: The refresh token value (hashed).
        user_id: The user who owns this token.
        expires_at: Token expiration timestamp.
        created_at: Token creation timestamp.
        revoked_at: Token revocation timestamp (None if active).
        is_revoked: Whether the token has been revoked.
    """

    __tablename__ = "refresh_tokens"

    id = Column(String(64), primary_key=True)
    token_hash = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime, nullable=True)
    is_revoked = Column(Boolean, default=False, index=True)

    # Relationship
    user = relationship("User", back_populates="refresh_tokens")
