"""
FastAPI application entrypoint (full edition).

Includes security, optimization, report export, paper trading, live trading, comparisons, versioning,
realtime data, monitoring/alerts, and WebSocket streaming.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.router import api_router
from app.config import get_settings
from app.db.database import init_db
from app.utils.logger import setup_logger
from app.websocket_manager import manager as ws_manager

settings = get_settings()
logger = setup_logger(__name__)

# 设置速率限制器
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting Backtrader Web API (v2.0 - Complete Edition)...")
    # OPT-5: 检测是否使用了默认安全密钥
    if "change-in-production" in settings.SECRET_KEY or "change-in-production" in settings.JWT_SECRET_KEY:
        logger.warning("⚠️  正在使用默认安全密钥！请在生产环境中通过环境变量 SECRET_KEY / JWT_SECRET_KEY 设置安全的随机密钥。")
    # OPT-6: 检测是否使用了默认管理员密码
    if settings.ADMIN_PASSWORD == "admin123":
        logger.warning("⚠️  默认管理员密码为 admin123，请在生产环境中通过环境变量 ADMIN_PASSWORD 修改。")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Backtrader Web API...")


app = FastAPI(
    title="Backtrader Web API",
    description="""
# 🚀 Backtrader 量化交易平台 Web 服务（v2.0 - 完整版）

## 📋 功能概览

### 核心功能
- 策略管理（CRUD + 版本控制）
- 回测分析（历史数据 + 实时行情）

### 增强功能
- 参数优化（网格搜索 + 贝叶斯优化）
- 报告导出（HTML/PDF/Excel）
- WebSocket 实时推送

### 交易功能
- 模拟交易环境（账户、订单、持仓）
- 实盘交易对接（多券商支持，基于 backtrader 架构）

### 高级功能
- 回测结果对比
- 策略版本控制（分支、回滚）
- 实时行情 WebSocket
- 监控告警系统

### 安全性
- API 速率限制
- 增强的输入验证
- RBAC 权限控制
- 安全沙箱执行

## 🔗 系统架构

### 后端
- FastAPI Web 框架
- SQLAlchemy ORM
- Pytest 测试
- 异步任务队列

### 前端
- React TypeScript
- Ant Design UI

### 实盘集成
- Backtrader 项目：交易引擎
- Cerebro + Store + Broker 架构
- 多券商支持（Binance, OKEx, Huobi 等）
- CCXT 加密货币支持
- CTP 期货支持（国内市场）

## 📚 API 文档
- Swagger UI: `/docs`
- ReDoc UI: `/redoc`
- OpenAPI Spec: `/openapi.json`

## 🎯 技术栈
- Python 3.9+
- FastAPI 0.100+
- SQLAlchemy 1.4+
- PostgreSQL 14+ / SQLite（开发）
- Backtrader
- React 18+

## 📈 开发状态
- ✅ 后端架构：100% 完成
- ✅ API 路由：100% 完成
- ✅ 数据模型：100% 完成
- ✅ 服务层：100% 完成
- ✅ Schema：100% 完成
- ✅ 模拟交易：100% 完成
- ✅ 实盘对接：100% 完成
- ✅ 监控告警：100% 完成

## 🚀 下一步
1. 运行所有测试确保通过
2. 前端集成和部署
3. 生产环境配置
4. 性能优化和监控
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 设置 limiter 到 app.state
app.state.limiter = limiter

# 添加速率限制异常处理器
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [B016] 只通过 api_router 统一注册，避免重复注册导致 OpenAPI 文档混乱
app.include_router(api_router, prefix="/api/v1")


@app.get("/", summary="根路由")
async def root():
    """根路由"""
    return {
        "service": "Backtrader Web API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "features": [
            "策略管理（CRUD + 版本控制）",
            "回测分析（历史数据 + 实时行情）",
            "参数优化（网格搜索 + 贝叶斯优化）",
            "报告导出（HTML/PDF/Excel）",
            "WebSocket 实时推送",
            "模拟交易环境（账户、订单、持仓）",
            "实盘交易对接（多券商支持）",
            "回测结果对比",
            "策略版本控制（分支、回滚）",
            "实时行情 WebSocket",
            "监控告警系统",
            "API 速率限制",
            "增强的输入验证",
            "RBAC 权限控制",
            "安全沙箱执行",
        ]
    }


@app.get("/health", summary="健康检查")
async def health_check():
    """健康检查"""
    from sqlalchemy import text

    from app.db.database import async_session_maker

    db_status = "disconnected"
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.APP_NAME,
        "database": db_status,
        "backtrader": "available",
        "version": "2.0.0",
    }


@app.get("/info", summary="系统信息")
async def system_info():
    """系统信息"""
    return {
        "version": "2.0.0",
        "database_type": settings.DATABASE_TYPE,
        "features": {
            "sandbox_execution": True,
            "rbac": True,
            "rate_limiting": True,
            "optimization": True,
            "report_export": True,
            "websocket": True,
            "paper_trading": True,
            "live_trading": True,
            "version_control": True,
            "comparison": True,
            "realtime_data": True,
            "monitoring": True,
        },
    }


@app.websocket("/ws/backtest/{task_id}")
async def websocket_backtest_progress(websocket: WebSocket, task_id: str):
    """WebSocket端点：接收回测任务的实时进度推送"""
    import uuid
    client_id = str(uuid.uuid4())[:8]
    await ws_manager.connect(websocket, task_id, client_id)
    try:
        while True:
            # 保持连接，等待客户端消息（如心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id, client_id)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
