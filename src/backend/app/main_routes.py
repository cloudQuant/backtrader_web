import sys
import time as _time
from typing import Any

from fastapi import FastAPI, WebSocket

from app.api.backtest_enhanced import websocket_endpoint as stream_backtest_progress
from app.api.data_topics import websocket_pattern_endpoint as stream_data_topic_pattern
from app.api.data_topics import websocket_topic_endpoint as stream_data_topic
from app.api.overfitting import websocket_endpoint as stream_overfitting_progress


def register_runtime_routes(
    app: FastAPI,
    settings: Any,
    logger: Any,
    optional_router_status: dict[str, dict[str, str | bool | None]],
) -> dict[str, Any]:
    feature_flags_cache: dict[str, bool] | None = None
    health_cache: dict | None = None
    health_cache_ts = 0.0
    health_cache_ttl = 10

    def _reset_feature_flags_cache() -> None:
        nonlocal feature_flags_cache
        feature_flags_cache = None

    def _get_feature_flags() -> dict[str, bool]:
        nonlocal feature_flags_cache
        if feature_flags_cache is not None:
            return feature_flags_cache

        route_paths = {route.path for route in app.routes if hasattr(route, "path")}

        def has_prefix(prefix: str) -> bool:
            return any(path.startswith(prefix) for path in route_paths)

        feature_flags_cache = {
            "sandbox_execution": True,
            "rbac": True,
            "rate_limiting": True,
            "optimization": has_prefix("/api/v1/optimization"),
            "report_export": any(
                path.startswith("/api/v1/backtests/") and "/report/" in path
                for path in route_paths
            ),
            "websocket": "/ws/backtest/{task_id}" in route_paths
            or "/api/v1/backtests/ws/backtest/{task_id}" in route_paths,
            "paper_trading": has_prefix("/api/v1/paper-trading"),
            "live_trading": has_prefix("/api/v1/live-trading"),
            "version_control": has_prefix("/api/v1/strategy-versions"),
            "comparison": has_prefix("/api/v1/comparisons"),
            "realtime_data": has_prefix("/api/v1/realtime"),
            "monitoring": has_prefix("/api/v1/monitoring"),
        }
        return feature_flags_cache

    def _get_root_features() -> list[str]:
        feature_flags = _get_feature_flags()
        features = [
            "Strategy Management",
            "Backtesting Analysis",
            "API Rate Limiting",
            "Secure Sandbox Execution",
        ]
        optional_features = [
            ("optimization", "Parameter Optimization"),
            ("report_export", "Report Export"),
            ("websocket", "WebSocket Real-time Push"),
            ("paper_trading", "Paper Trading"),
            ("live_trading", "Live Trading Integration"),
            ("comparison", "Backtest Result Comparison"),
            ("version_control", "Strategy Version Control"),
            ("realtime_data", "Real-time Market Data"),
            ("monitoring", "Monitoring and Alerts"),
        ]
        for key, label in optional_features:
            if feature_flags.get(key):
                features.append(label)
        return features

    def _get_optional_router_status() -> dict[str, dict[str, str | bool | None]]:
        return {
            name: {"available": status["available"], "error": status["error"]}
            for name, status in optional_router_status.items()
        }

    @app.get("/", summary="Root route")
    async def root():
        return {
            "service": "Backtrader Web API",
            "version": "2.0.0",
            "status": "running",
            "docs": "/docs",
            "features": _get_root_features(),
        }

    @app.get("/health", summary="Health check")
    async def health_check():
        nonlocal health_cache, health_cache_ts
        main_module = sys.modules.get("app.main")
        if main_module is not None:
            external_cache = getattr(main_module, "_health_cache", health_cache)
            external_cache_ts = getattr(main_module, "_health_cache_ts", health_cache_ts)
            if external_cache is None:
                health_cache = None
                health_cache_ts = 0.0
            else:
                health_cache = external_cache
                health_cache_ts = external_cache_ts

        now = _time.monotonic()
        if health_cache is not None and (now - health_cache_ts) < health_cache_ttl:
            return health_cache

        from sqlalchemy import text

        from app.db.database import _get_engine, async_session_maker

        db_status = "disconnected"
        pool_info = None
        try:
            async with async_session_maker() as session:
                await session.execute(text("SELECT 1"))
            db_status = "connected"

            real_engine = _get_engine()
            pool = real_engine.pool
            if hasattr(pool, "size"):
                pool_info = {
                    "pool_size": pool.size(),
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                    "invalid": pool.status(),
                }
        except Exception:
            logger.exception("Health check database probe failed")

        unavailable_optional_routers = sorted(
            name for name, status in _get_optional_router_status().items() if not status["available"]
        )
        result = {
            "status": "healthy" if db_status == "connected" else "degraded",
            "service": settings.APP_NAME,
            "database": db_status,
            "database_pool": pool_info,
            "backtrader": "available",
            "optional_routers": {
                "unavailable_count": len(unavailable_optional_routers),
                "unavailable": unavailable_optional_routers,
            },
            "version": "2.0.0",
        }
        health_cache = result
        health_cache_ts = now
        if main_module is not None:
            main_module._health_cache = health_cache
            main_module._health_cache_ts = health_cache_ts
        return result

    @app.get("/info", summary="System information")
    async def system_info():
        return {
            "version": "2.0.0",
            "database_type": settings.DATABASE_TYPE,
            "features": _get_feature_flags(),
            "optional_routers": _get_optional_router_status(),
        }

    @app.websocket("/ws/backtest/{task_id}")
    async def websocket_backtest_progress(websocket: WebSocket, task_id: str):
        await stream_backtest_progress(websocket, task_id)

    @app.websocket("/ws/overfitting/{task_id}")
    async def websocket_overfitting_progress(websocket: WebSocket, task_id: str):
        await stream_overfitting_progress(websocket, task_id)

    @app.websocket("/ws/data-topics")
    async def websocket_data_topics_pattern(websocket: WebSocket):
        await stream_data_topic_pattern(websocket)

    @app.websocket("/ws/data-topics/{topic:path}")
    async def websocket_data_topics_topic(websocket: WebSocket, topic: str):
        await stream_data_topic(websocket, topic)

    return {
        "_get_feature_flags": _get_feature_flags,
        "_get_optional_router_status": _get_optional_router_status,
        "_get_root_features": _get_root_features,
        "_reset_feature_flags_cache": _reset_feature_flags_cache,
        "health_check": health_check,
        "root": root,
        "system_info": system_info,
        "websocket_backtest_progress": websocket_backtest_progress,
        "websocket_data_topics_pattern": websocket_data_topics_pattern,
        "websocket_data_topics_topic": websocket_data_topics_topic,
        "websocket_overfitting_progress": websocket_overfitting_progress,
    }
