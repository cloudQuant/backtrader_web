"""Shared timestamp helpers for database-backed models."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Return the current UTC time for ``DateTime(timezone=False)`` columns.

    The application schema stores timestamps without a PostgreSQL time zone.
    Normalizing timezone-aware UTC values before persistence keeps SQLite and
    asyncpg behaviour consistent while retaining UTC as the canonical clock.
    """

    return datetime.now(timezone.utc).replace(tzinfo=None)
