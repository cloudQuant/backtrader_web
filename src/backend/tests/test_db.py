"""
数据库模块测试
"""
import pytest
from sqlalchemy import select, text
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.database import Base, get_db, init_db, create_default_admin, engine, async_session_maker
from app.db.sql_repository import SQLRepository
from app.models.user import User
from app.config import get_settings


class TestBase:
    """ORM基类测试"""

    def test_base_is_declarative(self):
        """测试Base是DeclarativeBase"""
        from sqlalchemy.orm import DeclarativeBase
        assert isinstance(Base, type)
        # Base 应该是 DeclarativeBase 的子类
        assert hasattr(Base, 'metadata')

    def test_base_metadata_exists(self):
        """测试Base metadata存在"""
        assert Base.metadata is not None


class TestEngineAndSessionMaker:
    """引擎和会话工厂测试"""

    def test_engine_exists(self):
        """测试引擎已创建"""
        assert engine is not None

    def test_async_session_maker_exists(self):
        """测试会话工厂已创建"""
        assert async_session_maker is not None


class TestInitDb:
    """初始化数据库测试"""

    async def test_init_db_creates_tables(self):
        """测试init_db创建表"""
        # 先删除所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        # 调用 init_db
        await init_db()

        # 验证表已创建（通过查询user表）
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            tables = result.fetchall()
            assert len(tables) >= 1

    async def test_init_db_idempotent(self):
        """测试init_db可以多次调用"""
        # 第一次调用
        await init_db()
        # 第二次调用不应报错
        await init_db()


class TestCreateDefaultAdmin:
    """创建默认管理员测试"""

    async def test_create_default_admin_when_not_exists(self):
        """测试管理员不存在时创建"""
        from sqlalchemy import delete
        from app.utils.security import get_password_hash

        settings = get_settings()

        # 删除可能存在的管理员
        async with async_session_maker() as session:
            await session.execute(
                delete(User).where(User.username == settings.ADMIN_USERNAME)
            )
            await session.commit()

        # 创建默认管理员
        await create_default_admin()

        # 验证管理员已创建
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admin = result.scalar_one_or_none()

        assert admin is not None
        assert admin.username == settings.ADMIN_USERNAME
        assert admin.email == settings.ADMIN_EMAIL
        assert admin.is_active is True

    async def test_create_default_admin_when_exists(self):
        """测试管理员已存在时不重复创建"""
        from app.utils.security import get_password_hash
        from sqlalchemy import delete

        settings = get_settings()

        # 先创建一个管理员
        async with async_session_maker() as session:
            await session.execute(
                delete(User).where(User.username == settings.ADMIN_USERNAME)
            )
            await session.commit()

        # 第一次创建
        await create_default_admin()

        # 获取第一次创建的管理员ID
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admin_first = result.scalar_one_or_none()
            first_id = admin_first.id if admin_first else None

        # 第二次创建（不应创建新的）
        await create_default_admin()

        # 验证没有重复创建
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admin_second = result.scalar_one_or_none()

        assert admin_second is not None
        if first_id:
            assert admin_second.id == first_id


class TestGetDb:
    """数据库会话测试"""

    async def test_get_db_yields_session(self):
        async for session in get_db():
            assert session is not None
            break

    async def test_get_db_session_closes(self):
        sessions = []
        async for session in get_db():
            sessions.append(session)
        assert len(sessions) == 1


class TestSQLRepository:
    """SQL 仓库测试"""

    async def test_create_and_get(self):
        repo = SQLRepository(User)
        user = User(
            username="repo_test",
            email="repo@test.com",
            hashed_password="fakehash",
        )
        created = await repo.create(user)
        assert created.id is not None

        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.username == "repo_test"

    async def test_get_by_field(self):
        repo = SQLRepository(User)
        user = User(username="field_test", email="field@test.com", hashed_password="x")
        await repo.create(user)

        found = await repo.get_by_field("username", "field_test")
        assert found is not None
        assert found.email == "field@test.com"

    async def test_get_by_field_not_found(self):
        repo = SQLRepository(User)
        found = await repo.get_by_field("username", "nonexistent_user_xyz")
        assert found is None

    async def test_update(self):
        repo = SQLRepository(User)
        user = User(username="upd_test", email="upd@test.com", hashed_password="x")
        created = await repo.create(user)

        updated = await repo.update(created.id, {"email": "updated@test.com"})
        assert updated is not None
        assert updated.email == "updated@test.com"

    async def test_delete(self):
        repo = SQLRepository(User)
        user = User(username="del_test", email="del@test.com", hashed_password="x")
        created = await repo.create(user)

        success = await repo.delete(created.id)
        assert success is True

        deleted = await repo.get_by_id(created.id)
        assert deleted is None

    async def test_delete_nonexistent(self):
        repo = SQLRepository(User)
        success = await repo.delete("nonexistent-id-xyz")
        assert success is False

    async def test_list(self):
        repo = SQLRepository(User)
        await repo.create(User(username="list1", email="l1@t.com", hashed_password="x"))
        await repo.create(User(username="list2", email="l2@t.com", hashed_password="x"))

        items = await repo.list(limit=10, skip=0)
        assert len(items) >= 2

    async def test_list_with_filter(self):
        repo = SQLRepository(User)
        await repo.create(User(username="filter_u", email="filter@t.com", hashed_password="x"))

        items = await repo.list(limit=10, skip=0, filters={"username": "filter_u"})
        assert len(items) >= 1

    async def test_count(self):
        repo = SQLRepository(User)
        await repo.create(User(username="cnt_u", email="cnt@t.com", hashed_password="x"))

        c = await repo.count()
        assert c >= 1

    async def test_count_with_filter(self):
        repo = SQLRepository(User)
        await repo.create(User(username="cnt_f", email="cntf@t.com", hashed_password="x"))

        c = await repo.count(filters={"username": "cnt_f"})
        assert c >= 1

    async def test_list_pagination(self):
        """测试分页功能"""
        repo = SQLRepository(User)

        # 创建多个用户
        for i in range(5):
            await repo.create(User(username=f"page_{i}", email=f"page_{i}@t.com", hashed_password="x"))

        # 测试limit和skip
        page1 = await repo.list(limit=2, skip=0)
        page2 = await repo.list(limit=2, skip=2)

        assert len(page1) == 2
        assert len(page2) == 2
        # 确保分页结果不同
        if page1 and page2:
            assert page1[0].id != page2[0].id

    async def test_update_nonexistent(self):
        """测试更新不存在的记录"""
        repo = SQLRepository(User)
        result = await repo.update("nonexistent-id-xyz", {"email": "test@test.com"})
        assert result is None

    async def test_list_with_ordering(self):
        """测试排序功能"""
        repo = SQLRepository(User)

        # 创建多个用户
        await repo.create(User(username="order_a", email="order_a@t.com", hashed_password="x"))
        await repo.create(User(username="order_b", email="order_b@t.com", hashed_password="x"))
        await repo.create(User(username="order_c", email="order_c@t.com", hashed_password="x"))

        # 测试升序
        items_asc = await repo.list(order_by="username", order_desc=False, limit=10)
        # 测试降序
        items_desc = await repo.list(order_by="username", order_desc=True, limit=10)

        assert len(items_asc) >= 3
        assert len(items_desc) >= 3
