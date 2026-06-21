import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from bt_api_py.brokers.gateway_bridge import GatewayBridgeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_record import AuditRecord
from app.models.broker_profile import BrokerConnectionProfile

_ROTATION_WARNING_DAYS = 90


class BrokerProfileService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_profile(
        self,
        *,
        user_id: str,
        broker_id: str,
        account_alias: str,
        capabilities: list[str],
        credentials_ref: dict[str, str],
        runtime_gateway_key: str | None,
        runtime_account_id: str | None,
        credentials_rotated_at: datetime | None,
    ) -> dict[str, Any]:
        profile = BrokerConnectionProfile(
            broker_id=broker_id,
            account_alias=account_alias,
            capabilities=list(capabilities),
            credentials_ref=dict(credentials_ref),
            runtime_gateway_key=str(runtime_gateway_key or "").strip() or None,
            runtime_account_id=str(runtime_account_id or "").strip() or None,
            enabled=True,
            created_by=user_id,
            is_destructive_enabled=False,
            credentials_rotated_at=credentials_rotated_at,
        )
        self.db.add(profile)
        await self.db.commit()
        await self.db.refresh(profile)
        return self.serialize_profile(profile)

    async def list_profiles(self, *, user_id: str) -> dict[str, Any]:
        result = await self.db.execute(
            select(BrokerConnectionProfile)
            .where(BrokerConnectionProfile.created_by == user_id)
            .order_by(BrokerConnectionProfile.created_at.desc())
        )
        items = [self.serialize_profile(item) for item in result.scalars().all()]
        return {"items": items, "total": len(items)}

    async def get_profile(
        self,
        profile_id: str,
        *,
        user_id: str,
        allow_admin: bool = False,
    ) -> BrokerConnectionProfile | None:
        result = await self.db.execute(
            select(BrokerConnectionProfile).where(BrokerConnectionProfile.id == profile_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return None
        if allow_admin or profile.created_by == user_id:
            return profile
        return None

    async def health(self, profile: BrokerConnectionProfile) -> dict[str, Any]:
        demo_health = self._demo_health(profile)
        if demo_health is not None:
            profile.last_health = demo_health
            await self.db.commit()
            await self.db.refresh(profile)
            return demo_health
        runtime_health = self._get_runtime_health(profile)
        if runtime_health is not None:
            profile.last_health = runtime_health
            await self.db.commit()
            await self.db.refresh(profile)
            return runtime_health
        adapter = await self._build_adapter(profile)
        payload = await adapter.health()
        profile.last_health = payload
        await self.db.commit()
        await self.db.refresh(profile)
        return payload

    async def list_accounts(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]]:
        demo_accounts = self._demo_accounts(profile)
        if demo_accounts is not None:
            return demo_accounts
        runtime_accounts = self._get_runtime_accounts(profile)
        if runtime_accounts is not None:
            return runtime_accounts
        adapter = await self._build_adapter(profile)
        items = await adapter.list_accounts()
        return [self._normalize_item(item) for item in items]

    async def list_positions(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]]:
        demo_positions = self._demo_positions(profile)
        if demo_positions is not None:
            return demo_positions
        runtime_positions = self._get_runtime_positions(profile)
        if runtime_positions is not None:
            return runtime_positions
        adapter = await self._build_adapter(profile)
        reader = getattr(adapter, "get_positions", None)
        if callable(reader):
            items = await reader()
            if isinstance(items, list):
                return [self._normalize_item(item) for item in items]
        return []

    async def list_orders(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]]:
        demo_orders = self._demo_orders(profile)
        if demo_orders is not None:
            return demo_orders
        runtime_orders = self._get_runtime_orders(profile)
        if runtime_orders is not None:
            return runtime_orders
        adapter = await self._build_adapter(profile)
        reader = getattr(adapter, "get_orders", None)
        if callable(reader):
            items = await reader()
            if isinstance(items, list):
                return [self._normalize_item(item) for item in items]
        return []

    async def get_quote(
        self,
        profile: BrokerConnectionProfile,
        symbol: str,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        demo_quote = self._demo_quote(profile, symbol)
        if demo_quote is not None:
            return demo_quote
        runtime_quote = self._get_runtime_quote(profile, symbol, user_id=user_id)
        if runtime_quote is not None:
            return runtime_quote
        adapter = await self._build_adapter(profile)
        return self._normalize_item(await adapter.get_quote(symbol))

    async def enable_live_write(
        self,
        profile: BrokerConnectionProfile,
        *,
        actor_user_id: str,
        confirmation_text: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        profile.is_destructive_enabled = True
        self.db.add(
            AuditRecord(
                user_id=actor_user_id,
                session_id=None,
                event_type="broker_profile.enable_live_write",
                event_target=profile.id,
                page_path=f"/api/v1/brokers/profiles/{profile.id}/enable-write",
                event_data=json.dumps(
                    {
                        "broker_id": profile.broker_id,
                        "account_alias": profile.account_alias,
                        "confirmation_text": confirmation_text,
                        "idempotency_key": idempotency_key,
                    },
                    ensure_ascii=False,
                ),
                client_timestamp=datetime.now(timezone.utc),
                client_ip=None,
            )
        )
        await self.db.commit()
        await self.db.refresh(profile)
        return self.serialize_profile(profile)

    def serialize_profile(self, profile: BrokerConnectionProfile) -> dict[str, Any]:
        return {
            "id": profile.id,
            "broker_id": profile.broker_id,
            "account_alias": profile.account_alias,
            "capabilities": list(profile.capabilities or []),
            "credentials_ref": self._mask_credentials_ref(dict(profile.credentials_ref or {})),
            "runtime_gateway_key": profile.runtime_gateway_key,
            "runtime_account_id": profile.runtime_account_id,
            "enabled": bool(profile.enabled),
            "last_health": dict(profile.last_health or {})
            if profile.last_health is not None
            else None,
            "created_by": profile.created_by,
            "is_destructive_enabled": bool(profile.is_destructive_enabled),
            "credentials_rotated_at": profile.credentials_rotated_at.isoformat()
            if profile.credentials_rotated_at is not None
            else None,
            "rotation_warning": self._rotation_warning(profile),
            "runtime_binding": self._resolve_runtime_binding(profile),
            "created_at": profile.created_at.isoformat()
            if profile.created_at is not None
            else None,
            "updated_at": profile.updated_at.isoformat()
            if profile.updated_at is not None
            else None,
        }

    async def _build_adapter(self, profile: BrokerConnectionProfile) -> GatewayBridgeAdapter:
        adapter = GatewayBridgeAdapter(
            gateway_service=profile.last_health or {},
            account_id=profile.account_alias,
        )
        await adapter.connect()
        return adapter

    def _mask_credentials_ref(self, credentials_ref: dict[str, str]) -> dict[str, str]:
        return {
            key: self._mask_secret_ref(value)
            for key, value in credentials_ref.items()
            if isinstance(value, str)
        }

    def _rotation_warning(self, profile: BrokerConnectionProfile) -> str | None:
        rotated_at = profile.credentials_rotated_at
        if rotated_at is None:
            return None
        if rotated_at.tzinfo is None:
            rotated_at = rotated_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - rotated_at > timedelta(days=_ROTATION_WARNING_DAYS):
            return "credentials_rotation_overdue"
        return None

    def _mask_secret_ref(self, value: str) -> str:
        text = str(value or "")
        if not text:
            return "***"
        return f"***{text[-4:]}"

    def _is_demo_profile(self, profile: BrokerConnectionProfile) -> bool:
        credentials = dict(profile.credentials_ref or {})
        return (
            str(profile.broker_id or "") == "roadshow_demo"
            or str(credentials.get("mode") or "") == "roadshow_demo"
        )

    def _demo_health(self, profile: BrokerConnectionProfile) -> dict[str, Any] | None:
        if not self._is_demo_profile(profile):
            return None
        return {
            "status": "ok",
            "mode": "paper_readonly",
            "gateway_key": profile.runtime_gateway_key or "roadshow:paper:readonly",
            "account_id": profile.runtime_account_id or profile.account_alias,
            "market_connection": "connected",
            "trade_connection": "readonly",
            "message": "Roadshow demo profile: simulated data only, live write disabled.",
        }

    def _demo_accounts(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]] | None:
        if not self._is_demo_profile(profile):
            return None
        return [
            {
                "account_id": profile.runtime_account_id or profile.account_alias,
                "currency": "CNY",
                "cash": 738500.0,
                "equity": 1286400.0,
                "available_cash": 612300.0,
                "mode": "paper_readonly",
            }
        ]

    def _demo_positions(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]] | None:
        if not self._is_demo_profile(profile):
            return None
        return [
            {
                "symbol": "510300.SH",
                "name": "沪深300ETF",
                "quantity": 82000,
                "avg_cost": 3.92,
                "last_price": 4.08,
                "market_value": 334560.0,
                "unrealized_pnl": 13120.0,
            },
            {
                "symbol": "159915.SZ",
                "name": "创业板ETF",
                "quantity": 120000,
                "avg_cost": 1.88,
                "last_price": 1.94,
                "market_value": 232800.0,
                "unrealized_pnl": 7200.0,
            },
        ]

    def _demo_orders(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]] | None:
        if not self._is_demo_profile(profile):
            return None
        return [
            {
                "order_id": "roadshow-order-001",
                "symbol": "510300.SH",
                "side": "buy",
                "order_type": "limit",
                "quantity": 20000,
                "price": 4.02,
                "status": "filled",
                "mode": "paper_readonly",
            },
            {
                "order_id": "roadshow-order-002",
                "symbol": "159915.SZ",
                "side": "sell",
                "order_type": "limit",
                "quantity": 10000,
                "price": 1.96,
                "status": "working",
                "mode": "paper_readonly",
            },
        ]

    def _demo_quote(
        self,
        profile: BrokerConnectionProfile,
        symbol: str,
    ) -> dict[str, Any] | None:
        if not self._is_demo_profile(profile):
            return None
        normalized = str(symbol or "510300.SH").strip().upper()
        prices = {
            "510300.SH": 4.08,
            "159915.SZ": 1.94,
            "RB2510": 3568.0,
        }
        return {
            "symbol": normalized,
            "last_price": prices.get(normalized, 100.0),
            "bid": round(prices.get(normalized, 100.0) * 0.999, 4),
            "ask": round(prices.get(normalized, 100.0) * 1.001, 4),
            "source": "roadshow_demo",
            "mode": "paper_readonly",
        }

    def get_enable_write_confirmation_text(self, profile: BrokerConnectionProfile) -> str:
        return f"ENABLE {profile.account_alias}"

    def _get_runtime_manager(self) -> Any | None:
        try:
            from app.services.live_trading_manager import get_live_trading_manager

            return get_live_trading_manager()
        except Exception:
            return None

    def _resolve_runtime_binding(self, profile: BrokerConnectionProfile) -> dict[str, Any] | None:
        explicit_gateway_key = str(profile.runtime_gateway_key or "").strip()
        explicit_account_id = str(profile.runtime_account_id or "").strip()
        normalized_alias = str(profile.account_alias or "").strip()

        manager = self._get_runtime_manager()
        if manager is None:
            if explicit_gateway_key or explicit_account_id:
                return {
                    "gateway_key": explicit_gateway_key,
                    "exchange_type": "",
                    "account_id": explicit_account_id or normalized_alias,
                    "has_runtime": False,
                }
            return None
        try:
            gateways = manager.list_connected_gateways()
        except Exception:
            if explicit_gateway_key or explicit_account_id:
                return {
                    "gateway_key": explicit_gateway_key,
                    "exchange_type": "",
                    "account_id": explicit_account_id or normalized_alias,
                    "has_runtime": False,
                }
            return None

        if not normalized_alias:
            return None

        explicit_matches: list[dict[str, Any]] = []
        if explicit_gateway_key:
            explicit_matches = [
                gateway
                for gateway in gateways
                if str(gateway.get("gateway_key") or "").strip() == explicit_gateway_key
            ]
            if explicit_account_id:
                account_matches = [
                    gateway
                    for gateway in explicit_matches
                    if str(gateway.get("account_id") or "").strip() == explicit_account_id
                ]
                if account_matches:
                    explicit_matches = account_matches
        elif explicit_account_id:
            explicit_matches = [
                gateway
                for gateway in gateways
                if str(gateway.get("account_id") or "").strip() == explicit_account_id
            ]

        exact_matches = explicit_matches or [
            gateway
            for gateway in gateways
            if str(gateway.get("account_id") or "").strip() == normalized_alias
        ]
        if not exact_matches:
            if explicit_gateway_key or explicit_account_id:
                return {
                    "gateway_key": explicit_gateway_key,
                    "exchange_type": "",
                    "account_id": explicit_account_id or normalized_alias,
                    "has_runtime": False,
                }
            return None

        exact_matches.sort(key=lambda item: 0 if item.get("has_runtime") else 1)
        selected = exact_matches[0]
        return {
            "gateway_key": str(selected.get("gateway_key") or explicit_gateway_key),
            "exchange_type": str(selected.get("exchange_type") or ""),
            "account_id": str(
                selected.get("account_id") or explicit_account_id or normalized_alias
            ),
            "has_runtime": bool(selected.get("has_runtime")),
        }

    def _get_runtime_health(self, profile: BrokerConnectionProfile) -> dict[str, Any] | None:
        binding = self._resolve_runtime_binding(profile)
        if not binding or not binding.get("has_runtime"):
            return None

        manager = self._get_runtime_manager()
        if manager is None:
            return None
        gateway_key = str(binding.get("gateway_key") or "")
        if not gateway_key:
            return None
        try:
            snapshots = manager.get_gateway_health()
        except Exception:
            return None
        for snapshot in snapshots:
            if str(snapshot.get("gateway_key") or "") == gateway_key:
                return self._normalize_item(snapshot)
        return None

    def _get_runtime_accounts(
        self, profile: BrokerConnectionProfile
    ) -> list[dict[str, Any]] | None:
        binding = self._resolve_runtime_binding(profile)
        if not binding or not binding.get("has_runtime"):
            return None

        manager = self._get_runtime_manager()
        if manager is None:
            return None
        reader = getattr(manager, "query_gateway_account", None)
        gateway_key = str(binding.get("gateway_key") or "")
        if not gateway_key or not callable(reader):
            return None
        payload = reader(gateway_key)
        if payload is None:
            return None
        return [self._normalize_item(payload)]

    def _get_runtime_positions(
        self, profile: BrokerConnectionProfile
    ) -> list[dict[str, Any]] | None:
        binding = self._resolve_runtime_binding(profile)
        if not binding or not binding.get("has_runtime"):
            return None

        manager = self._get_runtime_manager()
        if manager is None:
            return None
        reader = getattr(manager, "query_gateway_positions", None)
        gateway_key = str(binding.get("gateway_key") or "")
        if not gateway_key or not callable(reader):
            return None
        items = reader(gateway_key)
        if not isinstance(items, list):
            return None
        return [self._normalize_item(item) for item in items]

    def _get_runtime_orders(self, profile: BrokerConnectionProfile) -> list[dict[str, Any]] | None:
        binding = self._resolve_runtime_binding(profile)
        if not binding or not binding.get("has_runtime"):
            return None

        manager = self._get_runtime_manager()
        if manager is None:
            return None
        reader = getattr(manager, "query_gateway_orders", None)
        gateway_key = str(binding.get("gateway_key") or "")
        if not gateway_key or not callable(reader):
            return None
        items = reader(gateway_key)
        if not isinstance(items, list):
            return None
        return [self._normalize_item(item) for item in items]

    def _get_runtime_quote(
        self,
        profile: BrokerConnectionProfile,
        symbol: str,
        *,
        user_id: str | None,
    ) -> dict[str, Any] | None:
        binding = self._resolve_runtime_binding(profile)
        if not binding or not binding.get("has_runtime") or not user_id:
            return None

        source = str(binding.get("exchange_type") or "").upper()
        if not source:
            return None

        try:
            from app.services.quote_service import get_quote_service

            payload = get_quote_service().get_quotes(source, user_id=user_id, symbols=[symbol])
        except Exception:
            return None

        ticks = payload.get("ticks") if isinstance(payload, dict) else None
        if not isinstance(ticks, list) or not ticks:
            return None

        tick = self._normalize_item(ticks[0])
        tick.setdefault("source", str(payload.get("source") or source))
        return tick

    def _normalize_item(self, item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="python")
        if hasattr(item, "dict"):
            return item.dict()
        if is_dataclass(item):
            return asdict(item)
        if hasattr(item, "__dict__"):
            return {key: value for key, value in vars(item).items() if not key.startswith("_")}
        return {"value": item}


async def get_broker_profile_service(db: AsyncSession) -> BrokerProfileService:
    return BrokerProfileService(db)
