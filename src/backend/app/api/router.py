"""
API router registry.

All sub-routers are registered here (B016: avoid duplicate registration in main.py).
"""

import importlib
import logging

from fastapi import APIRouter

from app.api.ai_observability import router as ai_observability_router
from app.api.airflow_callback import router as airflow_callback_router
from app.api.airflow_dags import router as airflow_dags_router
from app.api.analytics import router as analytics_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.backtest_enhanced import router as backtest_enhanced_router
from app.api.brokers import router as brokers_router
from app.api.data.governance import router as data_governance_router
from app.api.data.topics import router as data_topics_router
from app.api.docs import router as docs_router
from app.api.equity_research import router as equity_research_router
from app.api.factor_lib import router as factor_lib_router
from app.api.live_trading import router as live_trading_router
from app.api.metrics import router as metrics_router
from app.api.news_intelligence import router as news_intelligence_router
from app.api.optimization_api import router as optimization_router
from app.api.options_chain import router as options_chain_router
from app.api.overfitting import router as overfitting_router
from app.api.perf_attribution import router as perf_attribution_router
from app.api.portfolio import router as portfolio_router
from app.api.prompt_templates import router as prompt_templates_router
from app.api.quant_tools import router as quant_tools_router
from app.api.risk_analytics import router as risk_analytics_router
from app.api.scanners import router as scanners_router
from app.api.simulation import router as simulation_router
from app.api.status import router as status_router
from app.api.strategy import router as strategy_router
from app.api.workspace_api import router as workspace_router
from app.api.workspace_optimization_api import router as workspace_optimization_router

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
api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])
api_router.include_router(airflow_callback_router, prefix="/data", tags=["Airflow Callback"])
api_router.include_router(airflow_dags_router, prefix="/data/airflow", tags=["Airflow DAGs"])
api_router.include_router(ai_observability_router, tags=["AI Observability"])
api_router.include_router(prompt_templates_router, tags=["Prompt Templates"])
api_router.include_router(risk_analytics_router)
api_router.include_router(factor_lib_router)
api_router.include_router(perf_attribution_router)
api_router.include_router(brokers_router)
api_router.include_router(data_governance_router)
api_router.include_router(data_topics_router)
api_router.include_router(equity_research_router)
api_router.include_router(news_intelligence_router)
api_router.include_router(options_chain_router)
api_router.include_router(scanners_router)
api_router.include_router(quant_tools_router)
api_router.include_router(metrics_router, tags=["Metrics"])
api_router.include_router(
    backtest_enhanced_router,
    prefix="/backtests",
    tags=["Enhanced Backtest"],
)
api_router.include_router(strategy_router, prefix="/strategy", tags=["Strategy"])
api_router.include_router(overfitting_router, prefix="/strategy", tags=["Overfitting"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(live_trading_router, prefix="/live-trading", tags=["Live Trading"])
api_router.include_router(portfolio_router)
api_router.include_router(optimization_router, prefix="/optimization", tags=["Optimization"])
api_router.include_router(simulation_router, prefix="/simulation", tags=["Simulation"])
api_router.include_router(workspace_router, prefix="/workspace", tags=["Workspace"])
api_router.include_router(workspace_optimization_router, prefix="/workspace", tags=["Workspace"])
api_router.include_router(docs_router, prefix="/docs", tags=["Documentation"])

# ── Optional routers (graceful degradation) ──────────────────────────────────
_OPTIONAL_ROUTERS = [
    ("auto_trading", "app.api.auto_trading", "/auto-trading", ["Auto Trading"]),
    ("paper_trading", "app.api.paper_trading", "/paper-trading", ["Paper Trading"]),
    ("comparison", "app.api.comparison", "/comparisons", ["Comparison"]),
    ("strategy_version", "app.api.strategy.version", "/strategy-versions", ["Strategy Version"]),
    ("realtime_data", "app.api.realtime_data", "/realtime", ["Realtime Data"]),
    ("monitoring", "app.api.monitoring", "/monitoring", ["Monitoring"]),
    ("data", "app.api.data", "/data", ["Market Data"]),
    ("akshare", "app.api.akshare", "/data", []),
    ("data_sync", "app.api.sync_api", "/data", ["Data Sync"]),
    ("risk_control", "app.api.risk_control", "", ["Risk Control"]),
    ("knowledge_base", "app.api.knowledge_base", "/knowledge-base", ["Knowledge Base"]),
    ("rag", "app.api.rag", "/rag", ["RAG"]),
    ("kb_chat", "app.api.kb_chat", "/kb-chat", ["KB Chat"]),
    ("ai_trading", "app.api.ai_trading", "/ai-trading", ["AI Trading"]),
]

for _name, _module, _prefix, _tags in _OPTIONAL_ROUTERS:
    _register_optional_router(_name, _module, prefix=_prefix, tags=_tags)

_register_optional_router(
    "quote",
    "app.api.quote",
    prefix="/quote",
    tags=["Quote"],
)
