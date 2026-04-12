"""
Akshare data warehouse database connection management.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# Lazy initialization to avoid event loop mismatch with MySQL async drivers.
_akshare_data_engine = None
_akshare_data_session_maker = None


def _get_akshare_data_engine():
    global _akshare_data_engine
    if _akshare_data_engine is None:
        if not settings.AKSHARE_DATA_DATABASE_URL:
            return None
        extra_kwargs = {}
        if settings.AKSHARE_DATA_DATABASE_URL.startswith("mysql"):
            extra_kwargs["poolclass"] = NullPool
        else:
            extra_kwargs["pool_pre_ping"] = True
        _akshare_data_engine = create_async_engine(
            settings.AKSHARE_DATA_DATABASE_URL,
            echo=settings.SQL_ECHO,
            **extra_kwargs,
        )
    return _akshare_data_engine


def _get_akshare_data_session_maker():
    global _akshare_data_session_maker
    if _akshare_data_session_maker is None:
        eng = _get_akshare_data_engine()
        if eng is None:
            return None
        _akshare_data_session_maker = async_sessionmaker(
            eng,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _akshare_data_session_maker


async def get_akshare_data_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session for the akshare data warehouse."""
    maker = _get_akshare_data_session_maker()
    if maker is None:
        raise RuntimeError("AKSHARE_DATA_DATABASE_URL is not configured")

    async with maker() as session:
        try:
            yield session
        finally:
            await session.close()
