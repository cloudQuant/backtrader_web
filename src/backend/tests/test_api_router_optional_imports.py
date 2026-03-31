import importlib
from unittest.mock import patch


def test_api_router_handles_optional_import_errors():
    """
    app/api/router.py conditionally includes optional routers via
    importlib.import_module().  This test forces ImportError for those
    optional modules to ensure the except paths are covered.
    """
    import app.api.router as router_module

    blocked = {
        "app.api.auto_trading",
        "app.api.paper_trading",
        "app.api.comparison",
        "app.api.strategy_version",
        "app.api.realtime_data",
        "app.api.monitoring",
        "app.api.data",
        "app.api.live_trading",
        "app.api.risk_control",
    }

    original_import_module = importlib.import_module

    def _fake_import_module(name, package=None):
        if name in blocked:
            raise ImportError(f"blocked import for test: {name}")
        return original_import_module(name, package)

    try:
        with patch("importlib.import_module", side_effect=_fake_import_module):
            importlib.reload(router_module)

        assert router_module.optional_router_status["paper_trading"]["available"] is False
        assert router_module.optional_router_status["comparison"]["available"] is False
        assert router_module.optional_router_status["strategy_version"]["available"] is False
        assert router_module.optional_router_status["realtime_data"]["available"] is False
        assert router_module.optional_router_status["monitoring"]["available"] is False
        assert router_module.optional_router_status["data"]["available"] is False
        assert router_module.optional_router_status["live_trading_legacy"]["available"] is False
    finally:
        importlib.reload(router_module)
