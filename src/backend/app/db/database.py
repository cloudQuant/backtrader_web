"""
Database connection management.
"""

import logging

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Lazy engine / session-maker to avoid "Future attached to a different loop"
# when using MySQL async drivers (asyncmy / aiomysql).
_engine = None
_async_session_maker = None


def _get_engine():
    global _engine
    if _engine is None:
        # Use NullPool for MySQL async drivers to prevent connection-pool futures
        # from being reused across different asyncio Tasks, which causes
        # "Future attached to a different loop" errors.
        extra_kwargs = {}
        if settings.DATABASE_URL.startswith("mysql"):
            extra_kwargs["poolclass"] = NullPool
        else:
            extra_kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.SQL_ECHO,
            **extra_kwargs,
        )
    return _engine


def _get_session_maker():
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


class _EngineProxy:
    """Proxy that lazily resolves the real engine on first use."""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def begin(self):
        return _get_engine().begin()

    async def dispose(self):
        return await _get_engine().dispose()


class _SessionMakerProxy:
    """Proxy that lazily resolves the real session maker on first use."""

    def __call__(self, *args, **kwargs):
        return _get_session_maker()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(_get_session_maker(), name)


engine = _EngineProxy()
async_session_maker = _SessionMakerProxy()


class Base(DeclarativeBase):
    """ORM base class.

    This class serves as the declarative base for all SQLAlchemy models.
    Models inherit from this class to gain ORM functionality.
    """

    pass


async def create_tables() -> None:
    """Create all ORM tables."""
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_db():
    """Initialize database tables.

    This helper is retained for backward compatibility in tests and scripts.
    It no longer creates the default administrator account implicitly.
    """
    await create_tables()


async def verify_database_connection() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def ensure_database_ready() -> None:
    """Ensure schema and default bootstrap data exist."""
    if settings.DB_AUTO_CREATE_SCHEMA:
        await create_tables()
    else:
        await verify_database_connection()
    if settings.DB_AUTO_CREATE_DEFAULT_ADMIN:
        await create_default_admin()


async def create_default_admin():
    """Create default admin account (if it doesn't exist)."""
    from app.models.permission import Role, user_roles
    from app.models.user import User
    from app.utils.security import get_password_hash

    settings = get_settings()

    async with async_session_maker() as session:
        # Check if admin account already exists
        result = await session.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        existing_user = result.scalar_one_or_none()

        if existing_user is None:
            # Create admin account
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
            )
            session.add(admin_user)
            await session.flush()
            existing_user = admin_user
            logger.info("Default admin account created: %s", settings.ADMIN_USERNAME)

        role_result = await session.execute(
            select(user_roles.c.role).where(user_roles.c.user_id == existing_user.id)
        )
        assigned_roles = {str(role) for role in role_result.scalars().all()}
        if Role.ADMIN.value not in assigned_roles:
            await session.execute(
                insert(user_roles).values(user_id=existing_user.id, role=Role.ADMIN.value)
            )

        await session.commit()


async def get_db() -> AsyncSession:
    """Get database session.

    Yields:
        An async database session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
