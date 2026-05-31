import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient


@pytest.mark.asyncio
async def test_lifespan_runs_startup_and_shutdown(monkeypatch):
    import app.main as main_module

    ensure_database_ready = AsyncMock()
    monkeypatch.setattr(main_module, "ensure_database_ready", ensure_database_ready, raising=True)

    # Force warnings to trigger using actual default values from _DEFAULT_SECRETS.
    monkeypatch.setattr(
        main_module.settings, "SECRET_KEY", "your-secret-key-change-in-production", raising=False
    )
    monkeypatch.setattr(
        main_module.settings,
        "JWT_SECRET_KEY",
        "your-jwt-secret-change-in-production",
        raising=False,
    )
    monkeypatch.setattr(main_module.settings, "ADMIN_PASSWORD", "admin123", raising=False)

    logs = {"info": 0, "warning": 0}
    ai_sink = SimpleNamespace(start=AsyncMock(), shutdown=AsyncMock())

    class FakeLogger:
        def info(self, *_args, **_kwargs):
            logs["info"] += 1

        def warning(self, *_args, **_kwargs):
            logs["warning"] += 1

    monkeypatch.setattr(main_module, "logger", FakeLogger(), raising=True)
    monkeypatch.setattr(
        "app.services.ai_observability.logger.get_ai_call_log_sink",
        lambda: ai_sink,
        raising=True,
    )

    async with main_module.lifespan(main_module.app):
        pass

    assert ensure_database_ready.await_count == 1
    assert ai_sink.start.await_count == 1
    assert ai_sink.shutdown.await_count == 1
    assert logs["warning"] >= 2  # default key + default admin password
    assert logs["info"] >= 2  # startup + shutdown


@pytest.mark.skip(reason="Complex integration test with timing issues")
def test_main_websocket_ping_pong_and_disconnect(monkeypatch):
    from app.main import app

    with TestClient(app) as client:
        register_resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "ws_user",
                "email": "ws_user@test.com",
                "password": "Test12345678",
            },
        )
        assert register_resp.status_code == 200

        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "ws_user",
                "password": "Test12345678",
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        async def _get_task_status(_task_id: str, user_id: str | None = None):
            assert user_id is not None
            return SimpleNamespace(value="running")

        monkeypatch.setattr(
            "app.api.backtest_enhanced.get_backtest_service",
            lambda: SimpleNamespace(get_task_status=_get_task_status),
            raising=True,
        )

        with client.websocket_connect(
            "/ws/backtest/task123", subprotocols=["access-token", token]
        ) as ws:
            # First message comes from ws_manager.connect()
            msg = ws.receive_json()
            assert msg["type"] == "connected"

            ws.send_text("ping")
            pong = ws.receive_json()
            assert pong["type"] == "pong"


def test_main_websocket_rejects_query_token_fallback(monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    from app.main import app

    with TestClient(app) as client:
        register_resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "ws_query_user",
                "email": "ws_query_user@test.com",
                "password": "Test12345678",
            },
        )
        assert register_resp.status_code == 200

        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "ws_query_user",
                "password": "Test12345678",
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        async def _get_task_status(_task_id: str, user_id: str | None = None):
            assert user_id is not None
            return SimpleNamespace(value="running")

        monkeypatch.setattr(
            "app.api.backtest_enhanced.get_backtest_service",
            lambda: SimpleNamespace(get_task_status=_get_task_status),
            raising=True,
        )

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/backtest/task123?token={token}"):
                pass

        assert exc_info.value.code == 1008


@pytest.mark.flaky(reruns=3, reruns_delay=1)
def test_data_topics_websocket_streams_single_topic_update(monkeypatch):
    import app.services.data_topic_hub as data_topic_module
    import app.services.ws_gateway as ws_gateway_module
    from app.main import app

    hub = data_topic_module.DataTopicHub()
    gateway = ws_gateway_module.WSGateway(token_validator=lambda token: bool(token))
    monkeypatch.setattr(data_topic_module, "_shared_hub", hub, raising=True)
    monkeypatch.setattr(ws_gateway_module, "_shared_gateway", gateway, raising=False)

    with TestClient(app) as client:
        register_resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "topic_ws_user",
                "email": "topic_ws_user@test.com",
                "password": "Test12345678",
            },
        )
        assert register_resp.status_code == 200

        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "topic_ws_user",
                "password": "Test12345678",
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        with client.websocket_connect(
            "/ws/data-topics/market:quote:RB2510", subprotocols=["access-token", token]
        ) as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"
            assert connected["topic"] == "market:quote:RB2510"

            asyncio.run(hub.push("market:quote:RB2510", {"price": 101}))

            update = ws.receive_json()
            assert update["type"] == "topic_update"
            assert update["topic"] == "market:quote:RB2510"
            assert update["value"] == {"price": 101}


def test_data_topics_websocket_pattern_route_receives_matching_update(monkeypatch):
    import app.services.data_topic_hub as data_topic_module
    import app.services.ws_gateway as ws_gateway_module
    from app.main import app

    hub = data_topic_module.DataTopicHub()
    gateway = ws_gateway_module.WSGateway(token_validator=lambda token: bool(token))
    monkeypatch.setattr(data_topic_module, "_shared_hub", hub, raising=True)
    monkeypatch.setattr(ws_gateway_module, "_shared_gateway", gateway, raising=False)

    with TestClient(app) as client:
        register_resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "topic_pattern_ws_user",
                "email": "topic_pattern_ws_user@test.com",
                "password": "Test12345678",
            },
        )
        assert register_resp.status_code == 200

        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "topic_pattern_ws_user",
                "password": "Test12345678",
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        with client.websocket_connect(
            "/ws/data-topics?pattern=market:quote:*", subprotocols=["access-token", token]
        ) as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"
            assert connected["pattern"] == "market:quote:*"

            asyncio.run(hub.push("market:quote:RB2510", {"price": 102}))

            update = ws.receive_json()
            assert update["type"] == "topic_update"
            assert update["topic"] == "market:quote:RB2510"
            assert update["value"] == {"price": 102}


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
