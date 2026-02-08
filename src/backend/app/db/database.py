"""
数据库连接管理
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
)

# 创建会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """ORM基类"""
    pass


async def init_db():
    """初始化数据库 - 创建表并创建默认管理员账户"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 创建默认管理员账户
    await create_default_admin()


async def create_default_admin():
    """创建默认管理员账户（如果不存在）"""
    from app.models.user import User
    from app.utils.security import get_password_hash
    from app.config import get_settings
    from sqlalchemy import select
    
    settings = get_settings()
    
    async with async_session_maker() as session:
        # 检查管理员账户是否已存在
        result = await session.execute(
            select(User).where(User.username == settings.ADMIN_USERNAME)
        )
        existing_user = result.scalar_one_or_none()
        
        if not existing_user:
            # 创建管理员账户
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            print(f"✓ 默认管理员账户已创建: {settings.ADMIN_USERNAME}")


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
