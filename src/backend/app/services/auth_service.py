"""
认证服务
"""
from typing import Optional
from datetime import timedelta

from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, UserResponse, Token
from app.db.sql_repository import SQLRepository
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.config import get_settings

settings = get_settings()


class AuthService:
    """认证服务"""
    
    def __init__(self):
        self.user_repo = SQLRepository(User)
    
    async def register(self, user_create: UserCreate) -> Optional[UserResponse]:
        """
        用户注册
        
        Returns:
            UserResponse: 注册成功返回用户信息
            None: 用户名或邮箱已存在
        """
        # 检查用户名是否已存在
        existing = await self.user_repo.get_by_field("username", user_create.username)
        if existing:
            return None
        
        # 检查邮箱是否已存在
        existing = await self.user_repo.get_by_field("email", user_create.email)
        if existing:
            return None
        
        # 创建用户
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
        """
        用户登录
        
        Returns:
            Token: 登录成功返回JWT令牌
            None: 用户名或密码错误
        """
        # 查找用户
        user = await self.user_repo.get_by_field("username", user_login.username)
        if not user:
            return None
        
        # 验证密码
        if not verify_password(user_login.password, user.hashed_password):
            return None
        
        # 生成令牌
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
    
    async def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """
        修改密码
        
        Returns:
            True: 修改成功
            False: 旧密码错误或用户不存在
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return False
        if not verify_password(old_password, user.hashed_password):
            return False
        await self.user_repo.update(user.id, {"hashed_password": get_password_hash(new_password)})
        return True

    async def get_user_by_id(self, user_id: str) -> Optional[UserResponse]:
        """根据ID获取用户"""
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
