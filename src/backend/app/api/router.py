"""
API router registry.

All sub-routers are registered here (B016: avoid duplicate registration in main.py).
"""

import importlib
import logging

from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.backtest import router as backtest_router
from app.api.backtest_enhanced import router as backtest_enhanced_router
from app.api.live_trading_api import router as live_trading_router
from app.api.metrics import router as metrics_router
from app.api.optimization_api import router as optimization_router
from app.api.portfolio_api import router as portfolio_router
from app.api.simulation import router as simulation_router
from app.api.status import router as status_router
from app.api.strategy import router as strategy_router
from app.api.workspace_api import router as workspace_router

logger = logging.getLogger(__name__)

api_router = APIRouter()
optional_router_status: dict[str, dict[str, str | bool | None]] = {}


def _set_optional_router_status(name: str, available: bool, error: str | None = None) -> None:
    optional_router_status[name] = {"available": available, "error": error}


def _register_optional_router(
    name: str,
    module_path: str,
    prefix: str = "",
    tags: list[str] | None = None,
    deprecated: bool = False,
) -> None:
    """Register an optional router with graceful degradation.

    Attempts to import the router module and register it on the api_router.
    If the import fails, logs a warning and records the failure status.

    Args:
        name: Short identifier for status tracking (e.g., "paper_trading").
        module_path: Dotted module path (e.g., "app.api.paper_trading").
        prefix: URL prefix for the router (e.g., "/paper-trading").
        tags: OpenAPI tags for the router.
        deprecated: Whether to mark the router as deprecated.
    """
    try:
        module = importlib.import_module(module_path)
        router = module.router
        kwargs: dict = {}
        if prefix:
            kwargs["prefix"] = prefix
        if tags:
            kwargs["tags"] = tags
        if deprecated:
            kwargs["deprecated"] = True
        api_router.include_router(router, **kwargs)
        _set_optional_router_status(name, True)
    except (ImportError, AttributeError) as exc:
        _set_optional_router_status(name, False, str(exc))
        logger.warning("Optional router %s unavailable: %s", name, exc)


# ── Core routers (always available) ──────────────────────────────────────────
api_router.include_router(status_router, tags=["System Status"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(metrics_router, tags=["Metrics"])
api_router.include_router(
    backtest_router, prefix="/backtest", tags=["Backtest"], deprecated=True,
)
api_router.include_router(
    backtest_enhanced_router, prefix="/backtests", tags=["Enhanced Backtest"],
)
api_router.include_router(strategy_router, prefix="/strategy", tags=["Strategy"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(live_trading_router, prefix="/live-trading", tags=["Live Trading"])
api_router.include_router(portfolio_router, prefix="/portfolio", tags=["Portfolio"])
api_router.include_router(optimization_router, prefix="/optimization", tags=["Optimization"])
api_router.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])
api_router.include_router(workspace_router, prefix="/workspace", tags=["Workspace"])

# ── Optional routers (graceful degradation) ──────────────────────────────────
_OPTIONAL_ROUTERS = [
    ("auto_trading",        "app.api.auto_trading",     "/auto-trading",        ["Auto Trading"]),
    ("paper_trading",       "app.api.paper_trading",    "/paper-trading",       ["Paper Trading"]),
    ("comparison",          "app.api.comparison",       "/comparisons",         ["Comparison"]),
    ("strategy_version",    "app.api.strategy_version", "/strategy-versions",   ["Strategy Version"]),
    ("realtime_data",       "app.api.realtime_data",    "/realtime",            ["Realtime Data"]),
    ("monitoring",          "app.api.monitoring",       "/monitoring",          ["Monitoring"]),
    ("data",                "app.api.data",             "/data",                ["Market Data"]),
    ("risk_control",        "app.api.risk_control",     "",                     ["Risk Control"]),
]

for _name, _module, _prefix, _tags in _OPTIONAL_ROUTERS:
    _register_optional_router(_name, _module, prefix=_prefix, tags=_tags)

# Legacy deprecated router
_register_optional_router(
    "live_trading_legacy",
    "app.api.live_trading",
    prefix="/live-trading-crypto",
    tags=["Crypto Trading (Legacy)"],
    deprecated=True,
)

_register_optional_router(
    "quote",
    "app.api.quote",
    prefix="/quote",
    tags=["Quote"],
)
