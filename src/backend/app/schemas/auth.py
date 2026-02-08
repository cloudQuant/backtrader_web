"""
认证相关Pydantic模型
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=8, description="密码")
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "trader",
                "email": "trader@example.com",
                "password": "password123"
            }
        }


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户响应"""
    id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    email: str = Field(..., description="邮箱")
    is_active: bool = Field(True, description="是否激活")
    created_at: datetime = Field(..., description="创建时间")
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT令牌响应"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间(秒)")


class ChangePassword(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=8, description="新密码")


class TokenPayload(BaseModel):
    """JWT令牌载荷"""
    sub: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    exp: Optional[int] = Field(None, description="过期时间戳")
