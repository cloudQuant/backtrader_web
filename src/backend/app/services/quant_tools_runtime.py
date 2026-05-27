from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import async_session_maker
from app.models.ai_call_log import AICallLog
from app.models.audit_record import AuditRecord
from app.services.data_connectors import DataGovernanceService
from app.services.data_topic_hub import get_shared_data_topic_hub
from app.services.news_intelligence import get_news_intelligence_service
from app.services.portfolio_ledger import get_portfolio_ledger_service

_SETTINGS = get_settings()
_AUDIT_LIMIT = 4096
_AUTH_ORDER = {"user": 0, "trader": 1, "admin": 2}
_MASKED_KEYS = ("token", "secret", "password", "credential")


class QuantToolRateLimiter:
    def __init__(self) -> None:
        self._calls: dict[tuple[str, str], list[float]] = {}

    def check(self, user_id: str, tool_name: str, limit: int = 30, window_sec: int = 60) -> bool:
        now = time.time()
        key = (user_id, tool_name)
        items = [value for value in self._calls.get(key, []) if now - value <= window_sec]
        allowed = len(items) < limit
        if allowed:
            items.append(now)
        self._calls[key] = items
        return allowed


class QuantToolsService:
    def __init__(self) -> None:
        self._limiter = QuantToolRateLimiter()
        self._hub = get_shared_data_topic_hub()
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        self._register_tool(
            {
                "name": "markets.get_quote",
                "description": "Get a latest market quote",
                "input_schema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}, "price": {"type": "number"}},
                    "required": ["symbol", "price"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_get_quote,
            }
        )
        self._register_tool(
            {
                "name": "markets.get_history",
                "description": "Get recent market history rows",
                "input_schema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}, "rows": {"type": "array"}},
                    "required": ["symbol", "rows"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_get_history,
            }
        )
        self._register_tool(
            {
                "name": "portfolio_ledger.get_summary",
                "description": "Get a portfolio ledger summary",
                "input_schema": {
                    "type": "object",
                    "properties": {"portfolio_id": {"type": "string"}},
                    "required": ["portfolio_id"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "portfolio_id": {"type": "string"},
                        "exists": {"type": "boolean"},
                        "holdings_count": {"type": "integer"},
                    },
                    "required": ["portfolio_id", "exists", "holdings_count"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_portfolio_summary,
            }
        )
        self._register_tool(
            {
                "name": "risk.var_cvar",
                "description": (
                    "Calculate VaR/CVaR from explicit returns or deterministic market history"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "returns": {"type": "array", "items": {"type": "number"}},
                    },
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "sample_size": {"type": "integer"},
                        "var_95": {"type": "number"},
                        "cvar_95": {"type": "number"},
                    },
                    "required": ["symbol", "sample_size", "var_95", "cvar_95"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_var_cvar,
            }
        )
        self._register_tool(
            {
                "name": "factor.evaluate",
                "description": "Evaluate a simple factor signal",
                "input_schema": {
                    "type": "object",
                    "properties": {"factor": {"type": "string"}},
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"factor": {"type": "string"}, "score": {"type": "number"}},
                    "required": ["factor", "score"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_factor_evaluate,
            }
        )
        self._register_tool(
            {
                "name": "news.latest",
                "description": "Get latest news item",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object", "properties": {}},
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_news_latest,
            }
        )
        self._register_tool(
            {
                "name": "data_governance.endpoint_preview",
                "description": "Preview a governed endpoint metadata snapshot",
                "input_schema": {
                    "type": "object",
                    "properties": {"endpoint": {"type": "string"}},
                    "required": ["endpoint"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"endpoint": {"type": "string"}, "preview": {"type": "object"}},
                    "required": ["endpoint", "preview"],
                },
                "auth_level": "admin",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_endpoint_preview,
            }
        )
        self._register_tool(
            {
                "name": "data_topics.list",
                "description": "List data topics",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {
                    "type": "object",
                    "properties": {"items": {"type": "array"}, "total": {"type": "integer"}},
                    "required": ["items", "total"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_topics_list,
            }
        )
        self._register_tool(
            {
                "name": "data_topics.peek",
                "description": "Peek a topic current cached value",
                "input_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}, "value": {}},
                    "required": ["topic", "value"],
                },
                "auth_level": "admin",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_topics_peek,
            }
        )
        self._register_tool(
            {
                "name": "portfolio_ledger.import_transactions",
                "description": "Import transactions into portfolio ledger",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "portfolio_id": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                        "transactions": {"type": "array"},
                        "confirmation_token": {"type": "string"},
                    },
                    "required": ["idempotency_key"],
                },
                "output_schema": {"type": "object", "properties": {}},
                "auth_level": "user",
                "is_destructive": True,
                "requires_confirmation": True,
                "timeout_ms": 5000,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_import_transactions,
            }
        )
        self._register_tool(
            {
                "name": "debug.sleep",
                "description": "Internal timeout probe",
                "input_schema": {
                    "type": "object",
                    "properties": {"delay_ms": {"type": "integer"}},
                    "required": ["delay_ms"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"slept_ms": {"type": "integer"}},
                    "required": ["slept_ms"],
                },
                "auth_level": "user",
                "is_destructive": False,
                "requires_confirmation": False,
                "timeout_ms": 5,
                "rate_limit_per_user_per_min": 30,
                "handler": self._handle_debug_sleep,
                "internal": True,
            }
        )

    def _register_tool(self, tool: dict[str, Any]) -> None:
        descriptor = dict(tool)
        descriptor["destructive"] = descriptor["is_destructive"]
        self._tools[descriptor["name"]] = descriptor

    def list_tools(self) -> dict[str, Any]:
        items = [
            self._public_tool(tool)
            for tool in self._tools.values()
            if not tool.get("internal")
        ]
        items.sort(key=lambda item: str(item["name"]))
        return {"tools": items}

    async def call_tool(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        username: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        tool = self._tools.get(tool_name)
        if tool is None:
            return 404, {"detail": "tool_not_found"}
        if not self._limiter.check(
            user_id,
            tool_name,
            limit=int(tool["rate_limit_per_user_per_min"]),
        ):
            return 429, {"detail": "rate_limited"}
        if not self._is_auth_level_allowed(username, str(tool["auth_level"])):
            return 403, {"detail": "insufficient_auth_level"}
        if not self._validate_schema(tool["input_schema"], payload):
            return 422, {"detail": "invalid_tool_input"}
        if tool["requires_confirmation"] and not payload.get("confirmation_token"):
            return 403, {"detail": "confirmation_required"}
        try:
            result = await asyncio.wait_for(
                self._dispatch(tool, user_id=user_id, payload=payload),
                timeout=max(int(tool["timeout_ms"]), 1) / 1000,
            )
        except TimeoutError:
            await self._log(
                db,
                user_id=user_id,
                tool_name=tool_name,
                payload=payload,
                result={"detail": "tool_timeout"},
                status="timeout",
                error_code="tool_timeout",
                error_message="tool_timeout",
            )
            return 504, {"detail": "tool_timeout"}
        await self._log(
            db,
            user_id=user_id,
            tool_name=tool_name,
            payload=payload,
            result=result,
            status="success",
            error_code=None,
            error_message=None,
        )
        return 200, {"status": "ok", "tool_name": tool_name, "result": result}

    async def simulate_chat(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        username: str,
        tool_calls: list[str],
    ) -> tuple[int, dict[str, Any]]:
        payloads = {
            "markets.get_quote": {"symbol": "RB2510"},
            "data_topics.list": {},
            "news.latest": {},
        }
        results = []
        for tool_name in tool_calls:
            status_code, _ = await self.call_tool(
                db,
                user_id=user_id,
                username=username,
                tool_name=tool_name,
                payload=dict(payloads.get(tool_name) or {}),
            )
            results.append(
                {"tool_name": tool_name, "status": "ok" if status_code == 200 else "failed"}
            )
        return 200, {"called_count": len(tool_calls), "results": results}

    async def _dispatch(
        self,
        tool: dict[str, Any],
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> Any:
        handler = tool["handler"]
        return await handler(user_id=user_id, payload=payload)

    async def _handle_get_quote(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        del user_id
        symbol = str(payload.get("symbol") or "RB2510")
        return {"symbol": symbol, "price": 100.0}

    async def _handle_get_history(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        del user_id
        symbol = str(payload.get("symbol") or "RB2510")
        return {
            "symbol": symbol,
            "rows": [
                {"date": "2026-05-24", "close": 99.0},
                {"date": "2026-05-25", "close": 100.0},
                {"date": "2026-05-26", "close": 101.0},
            ],
        }

    async def _handle_portfolio_summary(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        portfolio_id = str(payload.get("portfolio_id") or "")
        async with async_session_maker() as session:
            ledger = get_portfolio_ledger_service(session)
            portfolio = await ledger.get_portfolio(user_id, portfolio_id)
            holdings = (
                await ledger.holdings(user_id, portfolio_id)
                if portfolio is not None
                else None
            )
        return {
            "portfolio_id": portfolio_id,
            "exists": portfolio is not None,
            "holdings_count": len((holdings or {}).get("items") or []),
        }

    async def _handle_var_cvar(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, float]:
        del user_id
        symbol = str(payload.get("symbol") or "RB2510")
        raw_returns = payload.get("returns")
        if isinstance(raw_returns, list) and raw_returns:
            returns = [float(item) for item in raw_returns]
        else:
            closes = [99.0, 100.0, 101.0, 99.5, 102.0, 101.2, 103.6]
            returns = [
                round((closes[index] - closes[index - 1]) / closes[index - 1], 6)
                for index in range(1, len(closes))
            ]
        ordered = sorted(returns)
        tail_index = max(math.ceil(len(ordered) * 0.05) - 1, 0)
        var_95 = ordered[tail_index]
        tail = ordered[: tail_index + 1] or [var_95]
        cvar_95 = sum(tail) / len(tail)
        return {
            "symbol": symbol,
            "sample_size": len(ordered),
            "var_95": round(var_95, 6),
            "cvar_95": round(cvar_95, 6),
        }

    async def _handle_factor_evaluate(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        del user_id
        factor = str(payload.get("factor") or "momentum")
        return {"factor": factor, "score": 0.61}

    async def _handle_news_latest(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        async with async_session_maker() as session:
            news = get_news_intelligence_service(session)
            return await news.latest(user_id)

    async def _handle_endpoint_preview(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        del user_id
        endpoint = str(payload.get("endpoint") or "")
        params = dict(payload.get("params") or {})
        async with async_session_maker() as session:
            service = DataGovernanceService(session)
            await service.bootstrap()
            row = await service.get_endpoint_by_name(endpoint)
            if row is None:
                return {
                    "endpoint": endpoint,
                    "preview": {"status": "failed", "error": "endpoint_not_found"},
                }
            endpoint_model, _provider = row
            preview = await service.preview_endpoint(endpoint_model.id, params)
            return {"endpoint": endpoint, "preview": preview}

    async def _handle_topics_list(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        del user_id, payload
        items = self._hub.list_topics()
        return {"items": items, "total": len(items)}

    async def _handle_topics_peek(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        del user_id
        topic = str(payload.get("topic") or "")
        value = await self._hub.peek(topic) if topic else None
        return {"topic": topic, "value": value}

    async def _handle_import_transactions(self, *, user_id: str, payload: dict[str, Any]) -> Any:
        async with async_session_maker() as session:
            ledger = get_portfolio_ledger_service(session)
            return await ledger.import_transactions(
                user_id,
                str(payload.get("portfolio_id") or ""),
                idempotency_key=str(payload["idempotency_key"]),
                transactions=list(payload.get("transactions") or []),
            )

    async def _handle_debug_sleep(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, int]:
        del user_id
        delay_ms = int(payload.get("delay_ms") or 0)
        await asyncio.sleep(delay_ms / 1000)
        return {"slept_ms": delay_ms}

    async def _log(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        tool_name: str,
        payload: dict[str, Any],
        result: Any,
        status: str,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        sanitized_payload = self._sanitize(payload)
        sanitized_result = self._sanitize(result)
        payload_text = self._to_limited_text(sanitized_payload)
        result_text = self._to_limited_text(sanitized_result)
        prompt_hash = hashlib.sha256(f"{tool_name}:{payload_text}".encode()).hexdigest()
        db.add(
            AICallLog(
                user_id=user_id,
                request_id=None,
                service_name="quant_tool",
                mode=tool_name,
                model_name="tool-runtime",
                provider="internal",
                prompt_template_id=None,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=1,
                status=status,
                error_code=error_code,
                error_message=error_message,
                created_at=datetime.now(timezone.utc),
                response_chars=len(result_text),
                prompt_hash=prompt_hash,
            )
        )
        db.add(
            AuditRecord(
                user_id=user_id,
                session_id=None,
                event_type="quant_tool.call",
                event_target=tool_name,
                page_path="/api/v1/quant-tools/call",
                event_data=self._to_limited_text(
                    {"input": sanitized_payload, "result": sanitized_result, "status": status}
                ),
                client_timestamp=datetime.now(timezone.utc),
                server_timestamp=datetime.now(timezone.utc),
                client_ip=None,
            )
        )
        await db.commit()

    def _public_tool(self, tool: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["input_schema"],
            "output_schema": tool["output_schema"],
            "auth_level": tool["auth_level"],
            "is_destructive": tool["is_destructive"],
            "destructive": tool["is_destructive"],
            "requires_confirmation": tool["requires_confirmation"],
            "timeout_ms": tool["timeout_ms"],
            "rate_limit_per_user_per_min": tool["rate_limit_per_user_per_min"],
        }

    def _is_auth_level_allowed(self, username: str, required_level: str) -> bool:
        current_level = "admin" if username == _SETTINGS.ADMIN_USERNAME else "user"
        return _AUTH_ORDER[current_level] >= _AUTH_ORDER.get(required_level, 0)

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                lowered = str(key).lower()
                if any(token in lowered for token in _MASKED_KEYS):
                    sanitized[str(key)] = "***"
                else:
                    sanitized[str(key)] = self._sanitize(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value

    def _to_limited_text(self, value: Any) -> str:
        text = json.dumps(value, ensure_ascii=False, default=str)
        return text[:_AUDIT_LIMIT]

    def _validate_schema(self, schema: dict[str, Any], value: Any) -> bool:
        expected_type = schema.get("type")
        if expected_type is None:
            return True
        if expected_type == "object":
            if not isinstance(value, dict):
                return False
            required = schema.get("required") or []
            if any(key not in value for key in required):
                return False
            properties = schema.get("properties") or {}
            for key, item in value.items():
                property_schema = properties.get(key)
                if property_schema is not None and not self._validate_schema(property_schema, item):
                    return False
            return True
        if expected_type == "array":
            if not isinstance(value, list):
                return False
            item_schema = schema.get("items")
            if item_schema is None:
                return True
            return all(self._validate_schema(item_schema, item) for item in value)
        if expected_type == "string":
            return isinstance(value, str)
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_type == "boolean":
            return isinstance(value, bool)
        return True


_quant_tools_service = QuantToolsService()


def get_quant_tools_service() -> QuantToolsService:
    return _quant_tools_service
