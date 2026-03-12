import builtins
import importlib


def test_api_router_handles_optional_import_errors():
    """
    app/api/router.py conditionally includes optional routers under try/except ImportError.

    This test forces ImportError for those optional modules to ensure the except paths are covered.
    """
    import app.api.router as router_module

    original_import = builtins.__import__
    blocked = {
        "app.api.backtest_enhanced",
        "app.api.paper_trading",
        "app.api.comparison",
        "app.api.strategy_version",
        "app.api.realtime_data",
        "app.api.monitoring",
        "app.api.data",
        "app.api.live_trading",
    }

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in blocked:
            raise ImportError(f"blocked import for test: {name}")
        return original_import(name, globals, locals, fromlist, level)

    try:
        builtins.__import__ = _import
        importlib.reload(router_module)
    finally:
        builtins.__import__ = original_import
        importlib.reload(router_module)
