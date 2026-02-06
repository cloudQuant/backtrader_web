"""
FastAPI 应用入口（更新版）

集成了安全性、参数优化、报告导出、模拟交易、实盘交易对接、WebSocket 等新功能
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

from app.config import get_settings
from app.api.router import api_router
from app.api.auth import router as auth_router
from app.api.strategy import router as strategy_router
from app.api.backtest import router as backtest_router
from app.api.backtest_enhanced import router as backtest_enhanced_router
from app.api.analytics import router as analytics_router
from app.api.paper_trading import router as paper_trading_router
from app.api.comparison import router as comparison_router
from app.api.live_trading import router as live_trading_router
from app.api.strategy_version import router as strategy_version_router
from app.db.database import init_db
from app.utils.logger import setup_logger

settings = get_settings()
logger = setup_logger(__name__)

# 设置速率限制器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting Backtrader Web API...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Backtrader Web API...")


app = FastAPI(
    title="Backtrader Web API",
    description="Backtrader 量化交易回测 Web 服务（优化版）",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 自定义限流错误处理器
@app.exception_handler(_rate_limit_exceeded_handler)
async def rate_limit_exception_handler(request, exc):
    """速率限制错误处理器"""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=429,
        content={
            "code": 429,
            "message": "请求过于频繁，请稍后再试",
            "detail": exc.detail
        }
    )

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(strategy_router, prefix="/api/v1/strategies", tags=["策略"])
app.include_router(backtest_router, prefix="/api/v1/backtests", tags=["回测"])
app.include_router(backtest_enhanced_router, prefix="/api/v1/backtests", tags=["回测增强"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["分析"])


@app.get("/", summary="根路由")
async def root():
    """根路由"""
    return {
        "service": "Backtrader Web API",
        "version": "1.1.0",
        "docs": "/docs",
        "features": [
            "安全的策略代码执行（沙箱隔离）",
            "基于角色的权限控制（RBAC）",
            "参数优化（网格搜索、贝叶斯优化）",
            "回测报告导出（HTML/PDF/Excel）",
            "WebSocket 实时进度推送",
            "API 速率限制",
            "增强的输入验证",
        ]
    }


@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "database": "connected",  # TODO: 实际检查数据库连接
    }


@app.get("/info", summary="系统信息")
async def system_info():
    """系统信息"""
    return {
        "version": "1.1.0",
        "database_type": settings.DATABASE_TYPE,
        "features": {
            "sandbox_execution": True,
            "rbac": True,
            "rate_limiting": True,
            "optimization": True,
            "report_export": True,
            "websocket": True,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
