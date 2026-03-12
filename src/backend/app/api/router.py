"""
API router registry.

All sub-routers are registered here (B016: avoid duplicate registration in main.py).
"""

from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.backtest import router as backtest_router
from app.api.live_trading_api import router as live_trading_router
from app.api.optimization_api import router as optimization_router
from app.api.portfolio_api import router as portfolio_router
from app.api.simulation import router as simulation_router
from app.api.strategy import router as strategy_router

api_router = APIRouter()

# Core routers
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(backtest_router, prefix="/backtest", tags=["Backtest"])
api_router.include_router(strategy_router, prefix="/strategy", tags=["Strategy"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(live_trading_router, prefix="/live-trading", tags=["Live Trading"])
api_router.include_router(portfolio_router, prefix="/portfolio", tags=["Portfolio"])
api_router.include_router(optimization_router, prefix="/optimization", tags=["Optimization"])
api_router.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])

try:
    from app.api.auto_trading import router as auto_trading_router

    api_router.include_router(
        auto_trading_router, prefix="/auto-trading", tags=["Auto Trading"]
    )
except ImportError:
    pass

# Optional/extended routers (previously duplicated in main.py)
try:
    from app.api.backtest_enhanced import router as backtest_enhanced_router

    api_router.include_router(
        backtest_enhanced_router, prefix="/backtests", tags=["Enhanced Backtest"]
    )
except ImportError:
    pass

try:
    from app.api.paper_trading import router as paper_trading_router

    api_router.include_router(paper_trading_router, prefix="/paper-trading", tags=["Paper Trading"])
except ImportError:
    pass

try:
    from app.api.comparison import router as comparison_router

    api_router.include_router(comparison_router, prefix="/comparisons", tags=["Comparison"])
except ImportError:
    pass

try:
    from app.api.strategy_version import router as strategy_version_router

    api_router.include_router(
        strategy_version_router, prefix="/strategy-versions", tags=["Strategy Version"]
    )
except ImportError:
    pass

try:
    from app.api.realtime_data import router as realtime_data_router

    api_router.include_router(realtime_data_router, prefix="/realtime", tags=["Realtime Data"])
except ImportError:
    pass

try:
    from app.api.monitoring import router as monitoring_router

    api_router.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
except ImportError:
    pass

try:
    from app.api.data import router as data_router

    api_router.include_router(data_router, prefix="/data", tags=["Market Data"])
except ImportError:
    pass

try:
    from app.api.live_trading import router as live_trading_old_router

    api_router.include_router(
        live_trading_old_router, prefix="/live-trading-crypto", tags=["Crypto Trading"]
    )
except ImportError:
    pass
