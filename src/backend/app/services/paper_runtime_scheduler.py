"""Lifecycle-managed mark-to-market snapshots for workspace paper runtimes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Final

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.workspace import StrategyUnit, Workspace
from app.services.paper_runtime_service import PaperRuntimeService
from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_INTERVAL_SECONDS: Final[int] = 60
DEFAULT_CLEANUP_INTERVAL_SECONDS: Final[int] = 24 * 60 * 60


class PaperRuntimeSnapshotScheduler:
    """Maintain at most one snapshot worker for each running paper unit."""

    def __init__(self, *, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
        self.interval_seconds = max(int(interval_seconds), 1)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._service = PaperRuntimeService()
        self._cleanup_lock = asyncio.Lock()
        self._last_cleanup_at: datetime | None = None

    def ensure_running(self, user_id: str, instance_id: str) -> None:
        """Start the per-instance worker only when it is not already active."""
        task = self._tasks.get(instance_id)
        if task is not None and not task.done():
            return
        self._tasks[instance_id] = asyncio.create_task(
            self._run(user_id, instance_id),
            name=f"paper-runtime-snapshot:{instance_id}",
        )

    async def stop(self, instance_id: str) -> None:
        """Cancel and await a runtime worker without leaking shutdown tasks."""
        task = self._tasks.pop(instance_id, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def start_existing(self) -> int:
        """Restore workers for currently running, unlocked paper units after restart."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(Workspace.user_id, StrategyUnit.trading_instance_id)
                .join(StrategyUnit, StrategyUnit.workspace_id == Workspace.id)
                .where(
                    Workspace.workspace_type == "trading",
                    StrategyUnit.trading_mode == "paper",
                    StrategyUnit.run_status == "running",
                    StrategyUnit.lock_running.is_(False),
                    StrategyUnit.trading_instance_id.is_not(None),
                )
            )
            rows = list(result.all())
        for user_id, instance_id in rows:
            self.ensure_running(str(user_id), str(instance_id))
        return len(rows)

    async def shutdown(self) -> None:
        """Stop all workers during application shutdown."""
        await asyncio.gather(
            *(self.stop(instance_id) for instance_id in list(self._tasks)),
            return_exceptions=True,
        )

    async def _run(self, user_id: str, instance_id: str) -> None:
        try:
            while True:
                snapshot = await self._service.capture_mark_to_market_snapshot(
                    user_id,
                    instance_id,
                    min_interval_seconds=self.interval_seconds,
                )
                if snapshot is None:
                    return
                await self._cleanup_due_snapshots()
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Paper runtime snapshot worker failed for %s", instance_id)
            await self._service.emit_alert(
                user_id,
                instance_id,
                alert_type="system",
                severity="error",
                title="资金快照任务失败",
                message="模拟运行时的定时资金快照失败，已停止该实例的快照任务。",
                dedupe_key=f"{instance_id}:snapshot-worker-error",
            )
        finally:
            self._tasks.pop(instance_id, None)

    async def _cleanup_due_snapshots(self) -> None:
        """Run one retry-safe retention pass per process/day, not per runtime."""
        now = datetime.now(timezone.utc)
        if self._last_cleanup_at is not None and now - self._last_cleanup_at < timedelta(
            seconds=DEFAULT_CLEANUP_INTERVAL_SECONDS
        ):
            return
        async with self._cleanup_lock:
            if self._last_cleanup_at is not None and now - self._last_cleanup_at < timedelta(
                seconds=DEFAULT_CLEANUP_INTERVAL_SECONDS
            ):
                return
            result = await self._service.cleanup_snapshots(now=now)
            self._last_cleanup_at = now
            logger.info(
                "Paper runtime snapshot retention completed: deleted=%s daily_retained=%s failed=%s",
                result["deleted"],
                result["daily_retained"],
                result["failed"],
            )


_scheduler: PaperRuntimeSnapshotScheduler | None = None


def get_paper_runtime_snapshot_scheduler() -> PaperRuntimeSnapshotScheduler:
    """Return the process-local scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = PaperRuntimeSnapshotScheduler()
    return _scheduler
