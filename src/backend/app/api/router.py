"""
API路由汇总
"""
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.backtest import router as backtest_router
from app.api.strategy import router as strategy_router
from app.api.analytics import router as analytics_router

api_router = APIRouter()

# 注册各模块路由
api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(backtest_router, prefix="/backtest", tags=["回测"])
api_router.include_router(strategy_router, prefix="/strategy", tags=["策略"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["分析"])
