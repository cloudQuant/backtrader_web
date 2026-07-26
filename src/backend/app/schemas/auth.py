"""
Authentication schemas.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """User registration request schema."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Username",
        examples=["quant_trader_01"],
    )
    email: EmailStr = Field(..., description="Email address", examples=["zhangsan@example.com"])
    password: str = Field(..., min_length=8, description="Password", examples=["Str0ng!Pass"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "quant_trader_01",
                    "email": "zhangsan@example.com",
                    "password": "Str0ng!Pass",
                },
                {
                    "username": "策略研究员",
                    "email": "lisi@quant.cn",
                    "password": "MyP@ssw0rd",
                },
            ]
        }
    )


class UserLogin(BaseModel):
    """User login request schema."""

    username: str = Field(..., description="Username", examples=["quant_trader_01"])
    password: str = Field(..., description="Password", examples=["Str0ng!Pass"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "quant_trader_01",
                    "password": "Str0ng!Pass",
                }
            ]
        }
    )


class UserResponse(BaseModel):
    """User response schema."""

    id: str = Field(..., description="User ID", examples=["usr_a1b2c3d4e5f6"])
    username: str = Field(..., description="Username", examples=["quant_trader_01"])
    email: str = Field(..., description="Email", examples=["zhangsan@example.com"])
    is_active: bool = Field(True, description="Whether active")
    is_admin: bool = Field(False, description="Whether the user has admin access")
    created_at: datetime = Field(..., description="Creation time")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "usr_a1b2c3d4e5f6",
                    "username": "quant_trader_01",
                    "email": "zhangsan@example.com",
                    "is_active": True,
                    "is_admin": False,
                    "created_at": "2025-01-15T08:30:00Z",
                }
            ]
        },
    )


class Token(BaseModel):
    """JWT token response schema."""

    access_token: str = Field(..., description="Access token", examples=["eyJhbGciOiJIUzI1NiIs..."])
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Expiration time (seconds)", examples=[3600])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c3JfYTFiMmMzZDRlNWY2In0.signature",
                    "token_type": "bearer",
                    "expires_in": 3600,
                }
            ]
        }
    )


class ChangePassword(BaseModel):
    """Change password request schema."""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


class TokenPayload(BaseModel):
    """JWT token payload schema."""

    sub: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    exp: int | None = Field(None, description="Expiration timestamp")
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
