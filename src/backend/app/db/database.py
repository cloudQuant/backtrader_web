"""
Database connection management.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """ORM base class."""
    pass


async def init_db():
    """Initialize database - Create tables and create default admin account."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create default admin account
    await create_default_admin()


async def create_default_admin():
    """Create default admin account (if it doesn't exist)."""
    from app.models.user import User
    from app.utils.security import get_password_hash
    from app.config import get_settings
    from sqlalchemy import select

    settings = get_settings()

    async with async_session_maker() as session:
        # Check if admin account already exists
        result = await session.execute(
            select(User).where(User.username == settings.ADMIN_USERNAME)
        )
        existing_user = result.scalar_one_or_none()

        if not existing_user:
            # Create admin account
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            print(f"Default admin account created: {settings.ADMIN_USERNAME}")


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
