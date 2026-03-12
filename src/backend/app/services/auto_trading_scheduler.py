"""
Auto-trading scheduler service.

Manages automatic start/stop of trading strategy instances based on
Chinese futures market trading hours.  When auto-trading is enabled the
scheduler starts all instances 15 minutes before market open and stops
them 15 minutes after market close.

Chinese futures market sessions (Beijing time, UTC+8):
- Day session:   09:00 – 11:30, 13:30 – 15:00
- Night session: 21:00 – 23:00  (some products trade until 01:00 or 02:30
  the next day, but we use 23:00 as the conservative close)

With a 15-minute buffer the schedule becomes:
- Start at  08:45  (15 min before 09:00 day open)
- Stop  at  15:15  (15 min after  15:00 day close)
- Start at  20:45  (15 min before 21:00 night open)
- Stop  at  23:15  (15 min after  23:00 night close)
"""

import asyncio
import json
import logging
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SHANGHAI_TZ = timezone(timedelta(hours=8))

_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_CONFIG_FILE = _DATA_DIR / "auto_trading_config.json"

# Default Chinese futures market schedule (Beijing time)
DEFAULT_SESSIONS: list[dict[str, str]] = [
    {"name": "day", "open": "09:00", "close": "15:00"},
    {"name": "night", "open": "21:00", "close": "23:00"},
]

DEFAULT_BUFFER_MINUTES = 15


def _load_config() -> dict[str, Any]:
    """Load auto-trading config from disk."""
    if _CONFIG_FILE.is_file():
        try:
            return json.loads(_CONFIG_FILE.read_text("utf-8"))
        except Exception:
            return {}
    return {}


def _save_config(data: dict[str, Any]) -> None:
    """Persist auto-trading config to disk."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' into a datetime.time."""
    parts = s.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


class AutoTradingScheduler:
    """Scheduler that starts/stops strategy instances around market hours."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def get_config(self) -> dict[str, Any]:
        """Return current auto-trading configuration."""
        cfg = _load_config()
        return {
            "enabled": cfg.get("enabled", False),
            "buffer_minutes": cfg.get("buffer_minutes", DEFAULT_BUFFER_MINUTES),
            "sessions": cfg.get("sessions", DEFAULT_SESSIONS),
            "scope": cfg.get("scope", "all"),
        }

    def update_config(
        self,
        *,
        enabled: bool | None = None,
        buffer_minutes: int | None = None,
        sessions: list[dict[str, str]] | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Update and persist auto-trading configuration.

        Args:
            enabled: Whether auto-trading is enabled.
            buffer_minutes: Minutes before open / after close.
            sessions: Market session definitions.
            scope: 'all', 'simulation', or 'live'.

        Returns:
            The updated configuration dict.
        """
        cfg = _load_config()
        if enabled is not None:
            cfg["enabled"] = enabled
        if buffer_minutes is not None:
            cfg["buffer_minutes"] = max(0, buffer_minutes)
        if sessions is not None:
            cfg["sessions"] = sessions
        if scope is not None:
            cfg["scope"] = scope
        _save_config(cfg)

        # Start or stop the background loop accordingly
        if cfg.get("enabled"):
            self.ensure_running()
        else:
            self.stop()

        return self.get_config()

    # ------------------------------------------------------------------
    # Schedule computation
    # ------------------------------------------------------------------

    def get_schedule(self) -> list[dict[str, str]]:
        """Compute today's start/stop times based on config.

        Returns:
            A list of dicts with keys ``session``, ``start``, ``stop``.
        """
        cfg = self.get_config()
        buf = cfg["buffer_minutes"]
        result = []
        for sess in cfg["sessions"]:
            open_t = _parse_time(sess["open"])
            close_t = _parse_time(sess["close"])
            start_dt = datetime.combine(datetime.today(), open_t) - timedelta(minutes=buf)
            stop_dt = datetime.combine(datetime.today(), close_t) + timedelta(minutes=buf)
            result.append({
                "session": sess.get("name", ""),
                "start": start_dt.strftime("%H:%M"),
                "stop": stop_dt.strftime("%H:%M"),
                "market_open": sess["open"],
                "market_close": sess["close"],
            })
        return result

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def ensure_running(self) -> None:
        """Start the background scheduler loop if not already running."""
        if self._running:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._running = True
        self._task = loop.create_task(self._loop())
        logger.info("Auto-trading scheduler started")

    def stop(self) -> None:
        """Stop the background scheduler loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        logger.info("Auto-trading scheduler stopped")

    async def _loop(self) -> None:
        """Background loop that checks every 30 seconds."""
        from app.services.live_trading_manager import get_live_trading_manager

        while self._running:
            try:
                cfg = self.get_config()
                if not cfg.get("enabled"):
                    break

                now_sh = datetime.now(_SHANGHAI_TZ)
                now_hm = now_sh.strftime("%H:%M")
                buf = cfg["buffer_minutes"]
                scope = cfg.get("scope", "all")
                mgr = get_live_trading_manager()

                for sess in cfg["sessions"]:
                    open_t = _parse_time(sess["open"])
                    close_t = _parse_time(sess["close"])
                    start_dt = datetime.combine(now_sh.date(), open_t) - timedelta(minutes=buf)
                    stop_dt = datetime.combine(now_sh.date(), close_t) + timedelta(minutes=buf)
                    start_hm = start_dt.strftime("%H:%M")
                    stop_hm = stop_dt.strftime("%H:%M")

                    if now_hm == start_hm:
                        logger.info(
                            "Auto-trading: starting instances for session %s",
                            sess.get("name", ""),
                        )
                        try:
                            await mgr.start_all()
                        except Exception:
                            logger.exception("Auto-trading start_all failed")

                    if now_hm == stop_hm:
                        logger.info(
                            "Auto-trading: stopping instances for session %s",
                            sess.get("name", ""),
                        )
                        try:
                            await mgr.stop_all()
                        except Exception:
                            logger.exception("Auto-trading stop_all failed")

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Auto-trading scheduler error")

            await asyncio.sleep(30)

        self._running = False


_scheduler_instance: AutoTradingScheduler | None = None


@lru_cache(maxsize=1)
def get_auto_trading_scheduler() -> AutoTradingScheduler:
    """Return the global AutoTradingScheduler singleton."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AutoTradingScheduler()
        # Auto-start if previously enabled
        cfg = _scheduler_instance.get_config()
        if cfg.get("enabled"):
            _scheduler_instance.ensure_running()
    return _scheduler_instance
