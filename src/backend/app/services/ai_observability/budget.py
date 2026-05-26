from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.config import get_settings
from app.db.session_provider import unit_of_work
from app.models.ai_call_log import AICallLog
from app.models.user import User


@dataclass(frozen=True)
class AIBudgetSettings:
    global_daily_usd: float | None = None
    global_mode: str = "soft"

    @classmethod
    def from_app_settings(cls) -> AIBudgetSettings:
        settings = get_settings()
        return cls(
            global_daily_usd=getattr(settings, "AI_BUDGET_DAILY_USD", None),
            global_mode=str(getattr(settings, "AI_BUDGET_MODE", "soft") or "soft"),
        )


@dataclass(frozen=True)
class AIBudgetSnapshot:
    user_id: str | None
    limit_usd: float | None
    used_usd: float
    remaining_usd: float | None
    mode: str
    exceeded: bool
    reset_at: datetime


class AIBudgetExceededError(HTTPException):
    def __init__(
        self,
        *,
        reason_code: str,
        limit_usd: float,
        used_usd: float,
        reset_at: datetime,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "reason_code": reason_code,
                "message": "AI budget exceeded",
                "limit_usd": limit_usd,
                "used_usd": used_usd,
                "reset_at": reset_at.isoformat(),
            },
        )


class AIBudgetService:
    def __init__(self, settings: AIBudgetSettings | None = None) -> None:
        self.settings = settings or AIBudgetSettings.from_app_settings()

    async def get_daily_budget_snapshot(self, *, user_id: str | None) -> AIBudgetSnapshot:
        now = datetime.now(timezone.utc)
        start_at = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        reset_at = start_at + timedelta(days=1)
        limit_usd = self.settings.global_daily_usd
        mode = _normalize_mode(self.settings.global_mode)

        async with unit_of_work() as session:
            if user_id:
                user = await session.get(User, user_id)
                if user is not None:
                    user_limit = getattr(user, "ai_budget_daily_usd", None)
                    user_mode = getattr(user, "ai_budget_mode", None)
                    if user_limit is not None:
                        limit_usd = float(user_limit)
                    if user_mode:
                        mode = _normalize_mode(str(user_mode))

            filters = [AICallLog.created_at >= start_at, AICallLog.created_at < reset_at]
            if user_id:
                filters.append(AICallLog.user_id == user_id)
            result = await session.execute(select(func.sum(AICallLog.estimated_cost_usd)).where(*filters))
            used_usd = float(result.scalar_one_or_none() or 0.0)

        remaining_usd = None if limit_usd is None else max(float(limit_usd) - used_usd, 0.0)
        exceeded = False if limit_usd is None else used_usd >= float(limit_usd)
        return AIBudgetSnapshot(
            user_id=user_id,
            limit_usd=None if limit_usd is None else float(limit_usd),
            used_usd=used_usd,
            remaining_usd=remaining_usd,
            mode=mode,
            exceeded=exceeded,
            reset_at=reset_at,
        )

    async def ensure_budget_available(self, *, user_id: str | None) -> None:
        snapshot = await self.get_daily_budget_snapshot(user_id=user_id)
        if snapshot.limit_usd is None:
            return
        if snapshot.mode != "hard" or not snapshot.exceeded:
            return
        raise AIBudgetExceededError(
            reason_code="budget_exceeded",
            limit_usd=snapshot.limit_usd,
            used_usd=snapshot.used_usd,
            reset_at=snapshot.reset_at,
        )


def _normalize_mode(value: str) -> str:
    normalized = str(value or "soft").strip().lower()
    return "hard" if normalized == "hard" else "soft"
