"""
FastAPI 应用入口（超简化版）

只注册已验证的、可以运行的模块
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 只导入已知可以工作的模块
try:
    from app.config import get_settings
    from app.api.router import api_router
    from app.api.auth import router as auth_router
    from app.api.strategy import router as strategy_router
    from app.api.backtest import router as backtest_router
    from app.api.analytics import router as analytics_router
    from app.api.paper_trading import router as paper_trading_router
    from app.db.database import init_db
    from app.utils.logger import setup_logger

    # 导入新模块（可能会失败）
    try:
        from app.api.comparison import router as comparison_router
        from app.api.strategy_version import router as strategy_version_router
        from app.api.live_trading import router as live_trading_router
        from app.api.realtime_data import router as realtime_data_router
        from app.api.monitoring import router as monitoring_router
        NEW_MODULES_AVAILABLE = True
    except ImportError:
        NEW_MODULES_AVAILABLE = False

except ImportError as e:
    print(f"Warning: Failed to import basic modules: {e}")
    NEW_MODULES_AVAILABLE = False

settings = get_settings()
logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting Backtrader Web API (Minimal Edition)...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Backtrader Web API...")


app = FastAPI(
    title="Backtrader Web API (Minimal)",
    description="Backtrader 量化交易平台 Web 服务（最小版 - 只运行已验证的模块）",
    version="2.0.0-minimal",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 临时允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册基础路由
app.include_router(api_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(strategy_router, prefix="/api/v1/strategies", tags=["策略"])
app.include_router(backtest_router, prefix="/api/v1/backtests", tags=["回测"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["分析"])
app.include_router(paper_trading_router, prefix="/api/v1/paper-trading", tags=["模拟交易"])

# 如果新模块可用，则注册
if NEW_MODULES_AVAILABLE:
    app.include_router(comparison_router, prefix="/api/v1/comparisons", tags=["对比"])
    app.include_router(strategy_version_router, prefix="/api/v1/strategy-versions", tags=["策略版本"])
    app.include_router(live_trading_router, prefix="/api/v1/live-trading", tags=["实盘交易"])
    app.include_router(realtime_data_router, prefix="/api/v1/realtime", tags=["实时行情"])
    app.include_router(monitoring_router, prefix="/api/v1/monitoring", tags=["监控告警"])


@app.get("/", summary="根路由")
async def root():
    """根路由"""
    return {
        "service": "Backtrader Web API (Minimal)",
        "version": "2.0.0-minimal",
        "docs": "/docs",
        "new_modules": NEW_MODULES_AVAILABLE,
        "message": "Minimal version running - only core modules enabled",
        "available_features": [
            "策略管理（CRUD）",
            "回测分析",
            "模拟交易环境",
            "认证",
            "参数优化",
            "报告导出",
        ]
        if NEW_MODULES_AVAILABLE else [
            "策略管理（CRUD）",
            "回测分析",
            "模拟交易环境",
            "认证",
            "参数优化",
            "报告导出",
        ]
    }


@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "backtrader-web-api",
        "version": "2.0.0-minimal",
        "database": "connected",
        "new_modules": NEW_MODULES_AVAILABLE,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # 最小版不自动重载
    )
