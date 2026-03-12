from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient


@pytest.mark.asyncio
async def test_lifespan_runs_startup_and_shutdown(monkeypatch):
    import app.main as main_module

    init_db = AsyncMock()
    monkeypatch.setattr(main_module, "init_db", init_db, raising=True)

    # Force warnings to trigger.
    monkeypatch.setattr(main_module.settings, "SECRET_KEY", "change-in-production", raising=False)
    monkeypatch.setattr(
        main_module.settings, "JWT_SECRET_KEY", "change-in-production", raising=False
    )
    monkeypatch.setattr(main_module.settings, "ADMIN_PASSWORD", "admin123", raising=False)

    logs = {"info": 0, "warning": 0}

    class FakeLogger:
        def info(self, *_args, **_kwargs):
            logs["info"] += 1

        def warning(self, *_args, **_kwargs):
            logs["warning"] += 1

    monkeypatch.setattr(main_module, "logger", FakeLogger(), raising=True)

    async with main_module.lifespan(main_module.app):
        pass

    assert init_db.await_count == 1
    assert logs["warning"] >= 2  # default key + default admin password
    assert logs["info"] >= 2  # startup + shutdown


def test_main_websocket_ping_pong_and_disconnect():
    from app.main import app

    with TestClient(app) as client:
        with client.websocket_connect("/ws/backtest/task123") as ws:
            # First message comes from ws_manager.connect()
            msg = ws.receive_json()
            assert msg["type"] == "connected"

            ws.send_text("ping")
            pong = ws.receive_json()
            assert pong["type"] == "pong"


@pytest.mark.asyncio
async def test_health_check_connected_branch(monkeypatch):
    import app.main as main_module

    class FakeSession:
        async def execute(self, _stmt):
            return None

    class FakeSessionCtx:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "app.db.database.async_session_maker", lambda: FakeSessionCtx(), raising=True
    )

    data = await main_module.health_check()
    assert data["database"] == "connected"
