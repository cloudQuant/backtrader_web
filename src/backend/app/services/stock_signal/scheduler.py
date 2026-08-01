"""Lifecycle-safe APScheduler wrapper for nightly research signals."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.services.stock_signal.batch import Sse50SignalBatchRunner


class StockSignalScheduler:
    """Schedule one after-close SSE 50 research batch, disabled by default."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.scheduler: Any = None
        self.runner = Sse50SignalBatchRunner()

    def _ensure_scheduler(self) -> Any:
        if self.scheduler is not None:
            return self.scheduler
        try:
            from apscheduler.executors.asyncio import AsyncIOExecutor
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError as exc:
            raise RuntimeError("APScheduler is not installed") from exc
        scheduler = AsyncIOScheduler(
            executors={"default": AsyncIOExecutor()},
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
            timezone=self.settings.STOCK_SIGNAL_SCHEDULE_TIMEZONE,
        )
        scheduler.add_job(
            self._run_job,
            trigger=CronTrigger.from_crontab(
                self.settings.STOCK_SIGNAL_SCHEDULE_CRON,
                timezone=self.settings.STOCK_SIGNAL_SCHEDULE_TIMEZONE,
            ),
            id="nightly_sse50_stock_signals",
            replace_existing=True,
        )
        self.scheduler = scheduler
        return scheduler

    async def _run_job(self) -> None:
        await self.runner.run()
        await self.runner.score_pending()

    async def start(self) -> bool:
        """Start only when an operator enabled it and evaluation assumptions are explicit."""
        if not self.settings.STOCK_SIGNAL_SCHEDULE_ENABLED:
            return False
        if not self.runner.configuration_ready():
            raise RuntimeError("stock_signal_evaluation_configuration_incomplete")
        scheduler = self._ensure_scheduler()
        if not scheduler.running:
            scheduler.start()
        return True

    async def shutdown(self) -> None:
        if self.scheduler is not None and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.scheduler = None


@lru_cache
def get_stock_signal_scheduler() -> StockSignalScheduler:
    return StockSignalScheduler()
