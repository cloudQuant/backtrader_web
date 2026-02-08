"""
认证API路由
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


@router.post("/register", response_model=UserResponse, summary="用户注册")
async def register(
    user_create: UserCreate,
    service: AuthService = Depends(get_auth_service),
):
    """
    用户注册
    
    - **username**: 用户名 (3-50字符)
    - **email**: 邮箱地址
    - **password**: 密码 (至少8位)
    """
    user = await service.register(user_create)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名或邮箱已存在",
        )
    return user


@router.post("/login", response_model=Token, summary="用户登录")
async def login(
    user_login: UserLogin,
    service: AuthService = Depends(get_auth_service),
):
    """
    用户登录
    
    - **username**: 用户名
    - **password**: 密码
    
    返回JWT访问令牌
    """
    result = await service.login(user_login)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return result


@router.put("/change-password", summary="修改密码")
async def change_password(
    req: ChangePassword,
    current_user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """修改当前用户密码"""
    success = await service.change_password(current_user.sub, req.old_password, req.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前密码错误",
        )
    return {"message": "密码修改成功"}


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(
    current_user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    """获取当前登录用户信息"""
    user = await service.get_user_by_id(current_user.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user
