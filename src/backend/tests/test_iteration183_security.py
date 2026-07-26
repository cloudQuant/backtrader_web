"""Regression coverage for iteration 183 authorization and boundary controls."""

from __future__ import annotations

import os
import socket
import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from httpx import AsyncClient

from app.services.live_trading import instance as instance_service
from app.services.live_trading import manager as manager_module
from app.utils.safe_webhook import (
    UnsafeWebhookURL,
    _PinnedHTTPConnection,
    _validated_target,
    _WebhookTarget,
)


def _address_record(address: str) -> list[tuple[object, object, object, object, tuple[str, int]]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.8", "169.254.169.254", "::1", "fe80::1"])
def test_webhook_rejects_non_public_resolved_addresses(monkeypatch, address: str):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _address_record(address))

    with pytest.raises(UnsafeWebhookURL, match="non-public"):
        _validated_target("https://webhook.example.test/alerts")


def test_webhook_rejects_unsupported_scheme_and_url_credentials():
    with pytest.raises(UnsafeWebhookURL, match="http or https"):
        _validated_target("file:///etc/passwd")
    with pytest.raises(UnsafeWebhookURL, match="credentials"):
        _validated_target("https://user:password@webhook.example.test/alerts")


def test_webhook_connection_uses_validated_address(monkeypatch):
    target = _WebhookTarget(
        url="https://webhook.example.test/alerts",
        hostname="webhook.example.test",
        port=443,
        address="8.8.8.8",
    )
    connection = _PinnedHTTPConnection(target, timeout=1)
    fake_socket = MagicMock()
    create_connection = MagicMock(return_value=fake_socket)
    monkeypatch.setattr(socket, "create_connection", create_connection)

    connection.connect()

    create_connection.assert_called_once_with(("8.8.8.8", 443), 1, None)
    assert connection.sock is fake_socket


def test_ownerless_instances_are_invisible_to_authenticated_users():
    records = {
        "ownerless": {"user_id": None, "status": "stopped", "strategy_id": "legacy"},
        "owned": {"user_id": "owner", "status": "stopped", "strategy_id": "owned"},
    }

    with pytest.raises(instance_service.InstanceAccessError):
        instance_service.require_instance_access("ownerless", "attacker", lambda: records)

    assert (
        instance_service.get_instance(
            "ownerless",
            "attacker",
            lambda: records,
            lambda _records: None,
            lambda _pid: False,
            lambda: {},
            lambda _strategy_id: None,
            lambda _strategy_dir: None,
        )
        is None
    )
    assert not instance_service.remove_instance(
        "ownerless",
        "attacker",
        lambda: records,
        lambda _records: None,
        lambda _pid: None,
        lambda _instance_id: None,
        {},
    )


@pytest.mark.asyncio
async def test_manager_rejects_unauthorized_stop_before_cancelling_orders(monkeypatch):
    records = {
        "owned": {
            "user_id": "owner",
            "status": "running",
            "strategy_id": "owned",
            "pid": None,
        }
    }
    monkeypatch.setattr(manager_module, "_load_instances", lambda: records)
    manager = manager_module.LiveTradingManager()
    cancel_orders = MagicMock()
    monkeypatch.setattr(manager, "_cancel_open_orders_for_instance", cancel_orders)

    with pytest.raises(instance_service.InstanceAccessError):
        await manager.stop_instance("owned", user_id="attacker")

    cancel_orders.assert_not_called()


@pytest.mark.asyncio
async def test_live_control_api_passes_authenticated_user_to_manager():
    from app.api.live_trading import api

    manager = MagicMock()
    manager.start_instance = AsyncMock(return_value={"id": "owned", "status": "running"})
    user = SimpleNamespace(sub="owner")

    await api.start_instance("owned", current_user=user, mgr=manager)

    manager.start_instance.assert_awaited_once_with("owned", user_id="owner")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module_name, handler_name, args",
    [
        ("app.api.data.realtime", "realtime_tick_websocket", ("broker",)),
        ("app.api.monitoring", "alerts_websocket", ()),
        ("app.api.strategy.version", "strategy_version_websocket", ("strategy",)),
    ],
)
async def test_iteration183_websockets_reject_missing_token(
    monkeypatch, module_name, handler_name, args
):
    module = __import__(module_name, fromlist=[handler_name])
    websocket = MagicMock()
    websocket.close = AsyncMock()
    monkeypatch.setattr(module, "get_websocket_current_user", lambda _websocket: (None, None))

    await getattr(module, handler_name)(websocket, *args)

    websocket.close.assert_awaited_once_with(code=status.WS_1008_POLICY_VIOLATION)


@pytest.mark.asyncio
async def test_strategy_version_websocket_rejects_non_owner(monkeypatch):
    from app.api.strategy import version as api

    websocket = MagicMock()
    websocket.close = AsyncMock()
    service = MagicMock()
    service._require_strategy_owner = AsyncMock(side_effect=PermissionError("forbidden"))
    monkeypatch.setattr(
        api,
        "get_websocket_current_user",
        lambda _websocket: (SimpleNamespace(sub="attacker"), "access-token"),
    )
    monkeypatch.setattr(api, "get_version_control_service", lambda: service)

    await api.strategy_version_websocket(websocket, "owned-strategy")

    service._require_strategy_owner.assert_awaited_once_with(
        strategy_id="owned-strategy", user_id="attacker"
    )
    websocket.close.assert_awaited_once_with(code=status.WS_1008_POLICY_VIOLATION)


def test_sandbox_blocks_base_class_escape_path():
    from app.utils.sandbox import StrategySandbox

    with pytest.raises(ValueError, match="__base__"):
        StrategySandbox._check_code_safety("x = object.__base__")


@pytest.mark.asyncio
async def test_gateway_credentials_require_admin(client: AsyncClient, auth_headers: dict[str, str]):
    response = await client.get("/api/v1/live-trading/gateways/credentials", headers=auth_headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_data_topic_acl_limits_reads_and_writes_to_authorized_namespaces():
    from app.api.data.topics import _require_topic_access, _require_topic_pattern_access

    _require_topic_access("market:quote:RB2510", "user-a")
    _require_topic_access("user:user-a:watchlist", "user-a", write=True)
    _require_topic_pattern_access("market:quote:*", "user-a")

    with pytest.raises(Exception, match="Topic access denied"):
        _require_topic_access("user:user-b:watchlist", "user-a")
    with pytest.raises(Exception, match="Topic access denied"):
        _require_topic_access("market:quote:RB2510", "user-a", write=True)
    with pytest.raises(Exception, match="Topic subscription denied"):
        _require_topic_pattern_access("user:user-b:*", "user-a")


def test_production_settings_reject_disabled_ib_tls_and_docker_sandbox():
    from pydantic import ValidationError

    from app.config import Settings

    secure_settings = {
        "DEBUG": False,
        "SECRET_KEY": "a" * 32,
        "JWT_SECRET_KEY": "b" * 32,
        "ADMIN_PASSWORD": "SecurePass@123!",
        "CORS_ORIGINS": "https://app.example.test",
        "IB_VERIFY_SSL": True,
        "IB_WEB_VERIFY_SSL": True,
        "IB_PAPER_VERIFY_SSL": True,
        "IB_LIVE_VERIFY_SSL": True,
    }
    with pytest.raises(ValidationError, match="IB_LIVE_VERIFY_SSL=False"):
        Settings(**(secure_settings | {"IB_LIVE_VERIFY_SSL": False}))
    with pytest.raises(ValidationError, match="AI_STRATEGY_SANDBOX_USE_DOCKER"):
        Settings(**(secure_settings | {"AI_STRATEGY_SANDBOX_USE_DOCKER": False}))


def test_sync_credentials_are_persisted_owner_only(tmp_path):
    from app.schemas.sync import SyncConfig
    from app.services.sync_service import SyncService

    service = SyncService()
    service._config_file = tmp_path / "sync_config.json"

    service.save_config(
        SyncConfig(
            local_mysql_password="local-secret",
            remote_mysql_password="remote-secret",
        )
    )

    assert service._config_file.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(service._config_file.stat().st_mode) == 0o600


def test_ai_provider_credentials_are_persisted_owner_only(monkeypatch, tmp_path):
    from app.services.ai_router import provider_config_store

    target = tmp_path / "ai-providers.json"
    monkeypatch.setattr(provider_config_store, "get_provider_config_path", lambda: target)

    provider_config_store._write_raw_config(
        {"providers": {"example": {"api_key": "encrypted-value"}}}
    )

    assert target.is_file()
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
