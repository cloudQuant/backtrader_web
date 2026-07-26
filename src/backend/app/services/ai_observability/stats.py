from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_call_log import AICallLog

_FAILED_STATUSES = {"failed", "timeout"}


class AICallStatsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_usage(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        user_id: str | None = None,
        service_name: str | None = None,
        model_name: str | None = None,
        include_user_breakdown: bool = True,
    ) -> dict[str, Any]:
        logs = await self._fetch_logs(
            start_at=start_at,
            end_at=end_at,
            user_id=user_id,
            service_name=service_name,
            model_name=model_name,
        )
        payload: dict[str, Any] = {
            "summary": self._summary(logs),
            "by_day": self._group(logs, "date", lambda item: item.created_at.date().isoformat()),
            "by_service": self._group(logs, "service_name", lambda item: item.service_name),
            "by_model": self._group(logs, "model_name", lambda item: item.model_name),
        }
        if include_user_breakdown:
            payload["by_user"] = self._group(
                logs, "user_id", lambda item: item.user_id or "anonymous"
            )
        return payload

    async def get_failures(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        service_name: str | None = None,
        model_name: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        logs = await self._fetch_logs(
            start_at=start_at,
            end_at=end_at,
            service_name=service_name,
            model_name=model_name,
        )
        failures = [item for item in logs if str(item.status) in _FAILED_STATUSES]
        recent = sorted(failures, key=lambda item: item.created_at, reverse=True)[:limit]
        return {
            "summary": self._failure_summary(logs, failures),
            "by_error_code": self._failure_group(
                failures, "error_code", lambda item: item.error_code or "unknown"
            ),
            "by_service": self._failure_group(
                failures, "service_name", lambda item: item.service_name
            ),
            "recent_failures": [self._diagnostic_record(item) for item in recent],
        }

    async def get_slow_calls(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        service_name: str | None = None,
        model_name: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        logs = await self._fetch_logs(
            start_at=start_at,
            end_at=end_at,
            service_name=service_name,
            model_name=model_name,
        )
        top_calls = sorted(logs, key=lambda item: item.latency_ms, reverse=True)[:limit]
        return {
            "summary": {
                "total_calls": len(logs),
                "avg_latency_ms": self._average_latency(logs),
                "p95_latency_ms": self._percentile_latency(logs, 0.95),
                "p99_latency_ms": self._percentile_latency(logs, 0.99),
            },
            "by_service": self._latency_group(logs, "service_name", lambda item: item.service_name),
            "top_calls": [self._slow_call_record(item) for item in top_calls],
        }

    async def _fetch_logs(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        user_id: str | None = None,
        service_name: str | None = None,
        model_name: str | None = None,
    ) -> list[AICallLog]:
        stmt = select(AICallLog)
        if start_at is not None:
            stmt = stmt.where(AICallLog.created_at >= start_at)
        if end_at is not None:
            stmt = stmt.where(AICallLog.created_at <= end_at)
        if user_id is not None:
            stmt = stmt.where(AICallLog.user_id == user_id)
        if service_name is not None:
            stmt = stmt.where(AICallLog.service_name == service_name)
        if model_name is not None:
            stmt = stmt.where(AICallLog.model_name == model_name)
        result = await self.db.execute(stmt.order_by(AICallLog.created_at.asc()))
        return list(result.scalars().all())

    def _summary(self, logs: list[AICallLog]) -> dict[str, Any]:
        failed_calls = sum(1 for item in logs if str(item.status) in _FAILED_STATUSES)
        return {
            "total_calls": len(logs),
            "successful_calls": sum(1 for item in logs if str(item.status) == "success"),
            "failed_calls": failed_calls,
            "total_tokens": sum(int(item.total_tokens or 0) for item in logs),
            "estimated_cost_usd": self._cost(logs),
            "avg_latency_ms": self._average_latency(logs),
        }

    def _failure_summary(self, logs: list[AICallLog], failures: list[AICallLog]) -> dict[str, Any]:
        return {
            "total_calls": len(logs),
            "failed_calls": len(failures),
            "failure_rate": len(failures) / len(logs) if logs else 0.0,
        }

    def _group(self, logs: list[AICallLog], field_name: str, key_fn) -> list[dict[str, Any]]:
        buckets: dict[str, list[AICallLog]] = {}
        for item in logs:
            buckets.setdefault(str(key_fn(item)), []).append(item)
        return [
            {field_name: key, **self._summary(items)}
            for key, items in sorted(
                buckets.items(), key=lambda entry: (-len(entry[1]), str(entry[0]))
            )
        ]

    def _failure_group(
        self, logs: list[AICallLog], field_name: str, key_fn
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[AICallLog]] = {}
        for item in logs:
            buckets.setdefault(str(key_fn(item)), []).append(item)
        return [
            {
                field_name: key,
                "failed_calls": len(items),
                "total_tokens": sum(int(item.total_tokens or 0) for item in items),
                "estimated_cost_usd": self._cost(items),
            }
            for key, items in sorted(
                buckets.items(), key=lambda entry: (-len(entry[1]), str(entry[0]))
            )
        ]

    def _latency_group(
        self, logs: list[AICallLog], field_name: str, key_fn
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[AICallLog]] = {}
        for item in logs:
            buckets.setdefault(str(key_fn(item)), []).append(item)
        return [
            {
                field_name: key,
                "total_calls": len(items),
                "avg_latency_ms": self._average_latency(items),
                "p95_latency_ms": self._percentile_latency(items, 0.95),
                "p99_latency_ms": self._percentile_latency(items, 0.99),
            }
            for key, items in sorted(
                buckets.items(),
                key=lambda entry: (-self._percentile_latency(entry[1], 0.95), str(entry[0])),
            )
        ]

    def _diagnostic_record(self, item: AICallLog) -> dict[str, Any]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "service_name": item.service_name,
            "mode": item.mode,
            "model_name": item.model_name,
            "provider": item.provider,
            "total_tokens": int(item.total_tokens or 0),
            "estimated_cost_usd": float(item.estimated_cost_usd or 0.0),
            "latency_ms": int(item.latency_ms or 0),
            "status": item.status,
            "error_code": item.error_code,
            "error_message": item.error_message,
            "created_at": item.created_at,
        }

    def _slow_call_record(self, item: AICallLog) -> dict[str, Any]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "service_name": item.service_name,
            "mode": item.mode,
            "model_name": item.model_name,
            "provider": item.provider,
            "total_tokens": int(item.total_tokens or 0),
            "estimated_cost_usd": float(item.estimated_cost_usd or 0.0),
            "latency_ms": int(item.latency_ms or 0),
            "status": item.status,
            "error_code": item.error_code,
            "created_at": item.created_at,
        }

    def _cost(self, logs: list[AICallLog]) -> float:
        return round(sum(float(item.estimated_cost_usd or 0.0) for item in logs), 8)

    def _average_latency(self, logs: list[AICallLog]) -> int:
        if not logs:
            return 0
        return int(round(sum(int(item.latency_ms or 0) for item in logs) / len(logs)))

    def _percentile_latency(self, logs: list[AICallLog], percentile: float) -> int:
        if not logs:
            return 0
        values = sorted(int(item.latency_ms or 0) for item in logs)
        index = max(0, min(len(values) - 1, int(len(values) * percentile + 0.999999) - 1))
        return values[index]
