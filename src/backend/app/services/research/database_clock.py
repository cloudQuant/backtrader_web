"""Database-authoritative UTC clock primitives for fenced research leases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.functions import FunctionElement


class DatabaseUtcNow(FunctionElement[datetime]):
    """The database server's current UTC timestamp.

    There is deliberately no generic compiler.  A deployment using an
    unrecognized dialect must fail closed instead of silently falling back to
    an application-host clock for an external-dispatch lease.
    """

    type = DateTime(timezone=True)
    inherit_cache = True


class DatabaseUtcAfter(FunctionElement[datetime]):
    """A bound seconds offset from statement-time database UTC, not host time."""

    type = DateTime(timezone=True)
    inherit_cache = True

    def __init__(self, seconds: int) -> None:
        if type(seconds) is not int or not 0 <= seconds <= 7200:
            raise ValueError("RESEARCH_DATABASE_CLOCK_OFFSET_INVALID")
        super().__init__(seconds)


@compiles(DatabaseUtcAfter, "sqlite")
def _sqlite_database_utc_after(
    element: DatabaseUtcAfter, compiler: SQLCompiler, **kwargs: Any
) -> str:
    seconds = compiler.process(element.clauses, **kwargs)
    return f"strftime('%Y-%m-%d %H:%M:%f000', 'now', '+' || {seconds} || ' seconds')"


@compiles(DatabaseUtcAfter, "postgresql")
def _postgresql_database_utc_after(
    element: DatabaseUtcAfter, compiler: SQLCompiler, **kwargs: Any
) -> str:
    seconds = compiler.process(element.clauses, **kwargs)
    return f"(clock_timestamp() + {seconds} * INTERVAL '1 second')"


@compiles(DatabaseUtcAfter, "mysql")
def _mysql_database_utc_after(
    element: DatabaseUtcAfter, compiler: SQLCompiler, **kwargs: Any
) -> str:
    seconds = compiler.process(element.clauses, **kwargs)
    return f"TIMESTAMPADD(SECOND, {seconds}, UTC_TIMESTAMP(6))"


@compiles(DatabaseUtcNow, "sqlite")
def _sqlite_database_utc_now(element: DatabaseUtcNow, compiler: SQLCompiler, **kwargs: Any) -> str:
    # SQLite's clock is millisecond precision; normalize to six digits so it
    # round-trips through SQLAlchemy's DateTime result processor.
    return "strftime('%Y-%m-%d %H:%M:%f000', 'now')"


@compiles(DatabaseUtcNow, "postgresql")
def _postgresql_database_utc_now(
    element: DatabaseUtcNow, compiler: SQLCompiler, **kwargs: Any
) -> str:
    return "clock_timestamp()"


@compiles(DatabaseUtcNow, "mysql")
def _mysql_database_utc_now(element: DatabaseUtcNow, compiler: SQLCompiler, **kwargs: Any) -> str:
    return "UTC_TIMESTAMP(6)"


async def database_utc_now(session: AsyncSession) -> datetime:
    """Read UTC now through the caller's database session."""

    value = (await session.execute(select(DatabaseUtcNow()))).scalar_one()
    if not isinstance(value, datetime):
        raise RuntimeError("RESEARCH_DATABASE_CLOCK_INVALID")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
