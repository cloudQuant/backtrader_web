"""
Authentication schemas.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """User registration request schema."""

    username: str = Field(..., min_length=3, max_length=50, description="Username")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "trader",
                "email": "trader@example.com",
                "password": "password123",
            }
        }
    )


class UserLogin(BaseModel):
    """User login request schema."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class UserResponse(BaseModel):
    """User response schema."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email")
    is_active: bool = Field(True, description="Whether active")
    created_at: datetime = Field(..., description="Creation time")

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """JWT token response schema."""

    access_token: str = Field(..., description="Access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Expiration time (seconds)")


class ChangePassword(BaseModel):
    """Change password request schema."""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


class TokenPayload(BaseModel):
    """JWT token payload schema."""

    sub: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    exp: Optional[int] = Field(None, description="Expiration timestamp")
    token_type: str = Field("access", description="Token type: access or refresh")


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""

    refresh_token: str = Field(..., description="Refresh token")


class RefreshTokenResponse(BaseModel):
    """Refresh token response schema."""

    access_token: str = Field(..., description="New access token")
    refresh_token: str = Field(..., description="New refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Expiration time (seconds)")
