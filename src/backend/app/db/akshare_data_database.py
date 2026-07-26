"""
Akshare data warehouse database connection management.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# Lazy initialization to avoid event loop mismatch with MySQL async drivers.
_akshare_data_engine = None
_akshare_data_session_maker = None


def _resolve_akshare_data_database_url() -> str | URL | None:
    """Resolve the data warehouse URL from explicit config or the local MySQL app DB."""
    explicit_url = settings.AKSHARE_DATA_DATABASE_URL.strip()
    if explicit_url:
        return explicit_url

    primary_url = settings.DATABASE_URL.strip()
    if not primary_url:
        return None

    try:
        parsed = make_url(primary_url)
    except Exception:
        return None

    if not parsed.drivername.startswith("mysql"):
        return None

    return parsed.set(database="akshare_data")


def _database_url_drivername(database_url: str | URL) -> str:
    if isinstance(database_url, URL):
        return database_url.drivername
    return make_url(database_url).drivername


def _get_akshare_data_engine():
    global _akshare_data_engine
    if _akshare_data_engine is None:
        database_url = _resolve_akshare_data_database_url()
        if database_url is None:
            return None
        extra_kwargs = {}
        if _database_url_drivername(database_url).startswith("mysql"):
            extra_kwargs["poolclass"] = NullPool
        else:
            extra_kwargs["pool_pre_ping"] = True
        _akshare_data_engine = create_async_engine(
            database_url,
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
        raise RuntimeError(
            "AKSHARE_DATA_DATABASE_URL is not configured and DATABASE_URL is not a MySQL URL"
        )

    async with maker() as session:
        try:
            yield session
        finally:
            await session.close()
