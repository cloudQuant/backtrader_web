"""
API路由汇总 — 所有子路由统一在此注册（B016: 避免 main.py 重复注册）
"""
from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.backtest import router as backtest_router
from app.api.strategy import router as strategy_router
from app.api.analytics import router as analytics_router
from app.api.live_trading_api import router as live_trading_router
from app.api.portfolio_api import router as portfolio_router
from app.api.optimization_api import router as optimization_router

api_router = APIRouter()

# 核心模块路由
api_router.include_router(auth_router, prefix="/auth", tags=["认证"])
api_router.include_router(backtest_router, prefix="/backtest", tags=["回测"])
api_router.include_router(strategy_router, prefix="/strategy", tags=["策略"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["分析"])
api_router.include_router(live_trading_router, prefix="/live-trading", tags=["实盘交易"])
api_router.include_router(portfolio_router, prefix="/portfolio", tags=["组合管理"])
api_router.include_router(optimization_router, prefix="/optimization", tags=["参数优化"])

# 扩展模块路由（原在 main.py 中重复注册，现统一到此处）
try:
    from app.api.backtest_enhanced import router as backtest_enhanced_router
    api_router.include_router(backtest_enhanced_router, prefix="/backtests", tags=["回测增强"])
except ImportError:
    pass

try:
    from app.api.paper_trading import router as paper_trading_router
    api_router.include_router(paper_trading_router, prefix="/paper-trading", tags=["模拟交易"])
except ImportError:
    pass

try:
    from app.api.comparison import router as comparison_router
    api_router.include_router(comparison_router, prefix="/comparisons", tags=["对比"])
except ImportError:
    pass

try:
    from app.api.strategy_version import router as strategy_version_router
    api_router.include_router(strategy_version_router, prefix="/strategy-versions", tags=["策略版本"])
except ImportError:
    pass

try:
    from app.api.realtime_data import router as realtime_data_router
    api_router.include_router(realtime_data_router, prefix="/realtime", tags=["实时行情"])
except ImportError:
    pass

try:
    from app.api.monitoring import router as monitoring_router
    api_router.include_router(monitoring_router, prefix="/monitoring", tags=["监控告警"])
except ImportError:
    pass

try:
    from app.api.data import router as data_router
    api_router.include_router(data_router, prefix="/data", tags=["行情数据"])
except ImportError:
    pass

try:
    from app.api.live_trading import router as live_trading_old_router
    api_router.include_router(live_trading_old_router, prefix="/live-trading-crypto", tags=["加密货币交易"])
except ImportError:
    pass
