from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db.database import async_session_maker, create_default_admin
from app.models.audit_record import AuditRecord
from tests.conftest import register_and_login

settings = get_settings()


async def _get_admin_headers(client) -> dict[str, str]:
    await create_default_admin()
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_broker_profiles_create_and_list_masked_credentials(client):
    _, headers = await register_and_login(client, username="broker_profile_user")

    created = await client.post(
        "/api/v1/brokers/profiles",
        headers=headers,
        json={
            "broker_id": "gateway_bridge",
            "account_alias": "sim-account",
            "capabilities": ["health", "accounts", "quotes"],
            "credentials_ref": {
                "api_key_env": "BT_BROKER_SIM_KEY",
                "api_secret_env": "BT_BROKER_SIM_SECRET",
            },
            "credentials_rotated_at": (
                datetime.now(timezone.utc) - timedelta(days=91)
            ).isoformat(),
        },
    )
    listed = await client.get("/api/v1/brokers/profiles", headers=headers)

    _, other_headers = await register_and_login(client, username="broker_profile_other_user")
    listed_other = await client.get("/api/v1/brokers/profiles", headers=other_headers)

    assert created.status_code == 201
    payload = created.json()
    assert payload["broker_id"] == "gateway_bridge"
    assert payload["account_alias"] == "sim-account"
    assert payload["enabled"] is True
    assert payload["is_destructive_enabled"] is False
    assert payload["credentials_ref"]["api_key_env"].startswith("***")
    assert payload["credentials_ref"]["api_secret_env"].startswith("***")
    assert "BT_BROKER_SIM_KEY" not in str(payload)
    assert "BT_BROKER_SIM_SECRET" not in str(payload)

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["rotation_warning"] == "credentials_rotation_overdue"
    assert listed.json()["items"][0]["credentials_ref"]["api_key_env"].startswith("***")

    assert listed_other.status_code == 200
    assert listed_other.json()["total"] == 0


@pytest.mark.asyncio
async def test_broker_profiles_runtime_reads_and_enable_write_requires_admin(client):
    _, headers = await register_and_login(client, username="broker_profile_runtime_user")

    created = await client.post(
        "/api/v1/brokers/profiles",
        headers=headers,
        json={
            "broker_id": "gateway_bridge",
            "account_alias": "sim-account",
            "capabilities": ["health", "accounts", "positions", "orders", "quotes"],
            "credentials_ref": {
                "api_key_env": "BT_BROKER_SIM_KEY",
            },
            "credentials_rotated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]

    health = await client.get(f"/api/v1/brokers/profiles/{profile_id}/health", headers=headers)
    accounts = await client.get(f"/api/v1/brokers/profiles/{profile_id}/accounts", headers=headers)
    positions = await client.get(f"/api/v1/brokers/profiles/{profile_id}/positions", headers=headers)
    orders = await client.get(f"/api/v1/brokers/profiles/{profile_id}/orders", headers=headers)
    quotes = await client.get(
        f"/api/v1/brokers/profiles/{profile_id}/quotes?symbol=RB2510",
        headers=headers,
    )
    enable_non_admin = await client.post(
        f"/api/v1/brokers/profiles/{profile_id}/enable-write",
        headers=headers,
    )
    enable_admin_missing_confirmation = await client.post(
        f"/api/v1/brokers/profiles/{profile_id}/enable-write",
        headers=await _get_admin_headers(client),
        json={"confirmation_text": "", "idempotency_key": "req-1"},
    )
    enable_admin = await client.post(
        f"/api/v1/brokers/profiles/{profile_id}/enable-write",
        headers=await _get_admin_headers(client),
        json={
            "confirmation_text": "ENABLE sim-account",
            "idempotency_key": "req-2",
        },
    )
    listed = await client.get("/api/v1/brokers/profiles", headers=headers)

    assert health.status_code == 200
    assert health.json()["adapter"] == "gateway_bridge"
    assert health.json()["connected"] is True

    assert accounts.status_code == 200
    assert accounts.json()["items"][0]["account_id"] == "sim-account"

    assert positions.status_code == 200
    assert positions.json()["items"] == []

    assert orders.status_code == 200
    assert orders.json()["items"] == []

    assert quotes.status_code == 200
    assert quotes.json()["symbol"] == "RB2510"
    assert quotes.json()["provider"] == "gateway_bridge"

    assert enable_non_admin.status_code == 403
    assert enable_admin_missing_confirmation.status_code == 400
    assert enable_admin_missing_confirmation.json()["error"] == "HTTP_400"
    assert enable_admin_missing_confirmation.json()["message"] == "write_enable_confirmation_required"
    assert enable_admin.status_code == 200
    assert enable_admin.json()["is_destructive_enabled"] is True

    assert listed.status_code == 200
    assert listed.json()["items"][0]["is_destructive_enabled"] is True
    assert listed.json()["items"][0]["last_health"]["connected"] is True

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditRecord).where(AuditRecord.event_type == "broker_profile.enable_live_write")
        )
        record = result.scalar_one_or_none()

    assert record is not None
    assert record.event_target == profile_id


@pytest.mark.asyncio
async def test_broker_profiles_runtime_prefers_connected_gateway_binding(client):
    _, headers = await register_and_login(client, username="broker_profile_bound_runtime_user")

    created = await client.post(
        "/api/v1/brokers/profiles",
        headers=headers,
        json={
            "broker_id": "gateway_bridge",
            "account_alias": "DU123456",
            "capabilities": ["health", "accounts", "positions", "orders", "quotes"],
            "credentials_ref": {
                "api_key_env": "BT_BROKER_SIM_KEY",
            },
            "credentials_rotated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]

    fake_manager = SimpleNamespace(
        list_connected_gateways=lambda: [
            {
                "gateway_key": "manual:IB_WEB:DU123456",
                "exchange_type": "IB_WEB",
                "account_id": "DU123456",
                "has_runtime": True,
            }
        ],
        get_gateway_health=lambda: [
            {
                "gateway_key": "manual:IB_WEB:DU123456",
                "state": "running",
                "is_healthy": True,
                "market_connection": "connected",
                "trade_connection": "connected",
                "uptime_sec": 12,
                "last_heartbeat": None,
                "heartbeat_age_sec": None,
                "last_tick_time": None,
                "last_order_time": None,
                "strategy_count": 0,
                "symbol_count": 1,
                "tick_count": 5,
                "order_count": 1,
                "recent_errors": [],
                "ref_count": 0,
                "instances": [],
                "exchange": "IB_WEB",
                "asset_type": "STK",
                "account_id": "DU123456",
            }
        ],
        query_gateway_account=lambda gateway_key: {
            "gateway_key": gateway_key,
            "exchange": "IB_WEB",
            "account_id": "DU123456",
            "state": "running",
            "market_connection": "connected",
            "trade_connection": "connected",
        },
        query_gateway_positions=lambda gateway_key: [
            {"symbol": "AAPL", "direction": "LONG", "size": 2}
        ],
        query_gateway_orders=lambda gateway_key: [
            {"order_id": "ord-1", "symbol": "AAPL", "status": "Submitted"}
        ],
    )
    fake_quote_service = SimpleNamespace(
        get_quotes=lambda source, user_id, symbols=None: {
            "source": source,
            "total": 1,
            "ticks": [
                {
                    "symbol": "AAPL",
                    "last_price": 212.34,
                    "status": "normal",
                }
            ],
        }
    )

    with (
        patch(
            "app.services.live_trading_manager.get_live_trading_manager",
            return_value=fake_manager,
        ),
        patch(
            "app.services.quote_service.get_quote_service",
            return_value=fake_quote_service,
        ),
    ):
        listed = await client.get("/api/v1/brokers/profiles", headers=headers)
        health = await client.get(f"/api/v1/brokers/profiles/{profile_id}/health", headers=headers)
        accounts = await client.get(f"/api/v1/brokers/profiles/{profile_id}/accounts", headers=headers)
        positions = await client.get(f"/api/v1/brokers/profiles/{profile_id}/positions", headers=headers)
        orders = await client.get(f"/api/v1/brokers/profiles/{profile_id}/orders", headers=headers)
        quotes = await client.get(
            f"/api/v1/brokers/profiles/{profile_id}/quotes?symbol=AAPL",
            headers=headers,
        )

    assert listed.status_code == 200
    assert listed.json()["items"][0]["runtime_binding"] == {
        "gateway_key": "manual:IB_WEB:DU123456",
        "exchange_type": "IB_WEB",
        "account_id": "DU123456",
        "has_runtime": True,
    }

    assert health.status_code == 200
    assert health.json()["gateway_key"] == "manual:IB_WEB:DU123456"
    assert health.json()["exchange"] == "IB_WEB"

    assert accounts.status_code == 200
    assert accounts.json()["items"][0]["gateway_key"] == "manual:IB_WEB:DU123456"

    assert positions.status_code == 200
    assert positions.json()["items"] == [{"symbol": "AAPL", "direction": "LONG", "size": 2}]

    assert orders.status_code == 200
    assert orders.json()["items"] == [{"order_id": "ord-1", "symbol": "AAPL", "status": "Submitted"}]

    assert quotes.status_code == 200
    assert quotes.json()["symbol"] == "AAPL"
    assert quotes.json()["last_price"] == 212.34
    assert quotes.json()["source"] == "IB_WEB"


@pytest.mark.asyncio
async def test_broker_profiles_runtime_prefers_explicit_gateway_binding_over_alias_matching(client):
    _, headers = await register_and_login(client, username="broker_profile_explicit_binding_user")

    created = await client.post(
        "/api/v1/brokers/profiles",
        headers=headers,
        json={
            "broker_id": "gateway_bridge",
            "account_alias": "main-equities",
            "runtime_gateway_key": "manual:IB_WEB:DU123456",
            "runtime_account_id": "DU123456",
            "capabilities": ["health", "accounts", "positions", "orders", "quotes"],
            "credentials_ref": {
                "api_key_env": "BT_BROKER_SIM_KEY",
            },
            "credentials_rotated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["runtime_gateway_key"] == "manual:IB_WEB:DU123456"
    assert payload["runtime_account_id"] == "DU123456"
    profile_id = payload["id"]

    fake_manager = SimpleNamespace(
        list_connected_gateways=lambda: [
            {
                "gateway_key": "manual:IB_WEB:DU123456",
                "exchange_type": "IB_WEB",
                "account_id": "DU123456",
                "has_runtime": True,
            },
            {
                "gateway_key": "manual:IB_WEB:DU999999",
                "exchange_type": "IB_WEB",
                "account_id": "main-equities",
                "has_runtime": True,
            },
        ],
        get_gateway_health=lambda: [
            {
                "gateway_key": "manual:IB_WEB:DU123456",
                "exchange": "IB_WEB",
                "state": "running",
                "account_id": "DU123456",
            },
            {
                "gateway_key": "manual:IB_WEB:DU999999",
                "exchange": "IB_WEB",
                "state": "running",
                "account_id": "main-equities",
            },
        ],
        query_gateway_account=lambda gateway_key: {
            "gateway_key": gateway_key,
            "account_id": "DU123456" if gateway_key.endswith("DU123456") else "main-equities",
        },
        query_gateway_positions=lambda gateway_key: [
            {"gateway_key": gateway_key, "symbol": "AAPL", "direction": "LONG", "size": 1}
        ],
        query_gateway_orders=lambda gateway_key: [
            {"gateway_key": gateway_key, "order_id": "ord-1", "status": "Submitted"}
        ],
    )
    fake_quote_service = SimpleNamespace(
        get_quotes=lambda source, user_id, symbols=None: {
            "source": source,
            "total": 1,
            "ticks": [
                {
                    "symbol": symbols[0],
                    "last_price": 212.34,
                    "status": "normal",
                }
            ],
        }
    )

    with (
        patch(
            "app.services.live_trading_manager.get_live_trading_manager",
            return_value=fake_manager,
        ),
        patch(
            "app.services.quote_service.get_quote_service",
            return_value=fake_quote_service,
        ),
    ):
        listed = await client.get("/api/v1/brokers/profiles", headers=headers)
        health = await client.get(f"/api/v1/brokers/profiles/{profile_id}/health", headers=headers)
        accounts = await client.get(f"/api/v1/brokers/profiles/{profile_id}/accounts", headers=headers)
        positions = await client.get(f"/api/v1/brokers/profiles/{profile_id}/positions", headers=headers)
        orders = await client.get(f"/api/v1/brokers/profiles/{profile_id}/orders", headers=headers)

    assert listed.status_code == 200
    assert listed.json()["items"][0]["runtime_binding"] == {
        "gateway_key": "manual:IB_WEB:DU123456",
        "exchange_type": "IB_WEB",
        "account_id": "DU123456",
        "has_runtime": True,
    }

    assert health.status_code == 200
    assert health.json()["gateway_key"] == "manual:IB_WEB:DU123456"

    assert accounts.status_code == 200
    assert accounts.json()["items"][0]["gateway_key"] == "manual:IB_WEB:DU123456"

    assert positions.status_code == 200
    assert positions.json()["items"][0]["gateway_key"] == "manual:IB_WEB:DU123456"

    assert orders.status_code == 200
    assert orders.json()["items"][0]["gateway_key"] == "manual:IB_WEB:DU123456"
