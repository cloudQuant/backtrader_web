"""
Database module tests.
"""
import pytest
from sqlalchemy import select, text
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.database import Base, get_db, init_db, create_default_admin, engine, async_session_maker
from app.db.sql_repository import SQLRepository
from app.models.user import User
from app.config import get_settings


class TestBase:
    """ORM base class tests."""

    def test_base_is_declarative(self):
        """Test that Base is DeclarativeBase."""
        from sqlalchemy.orm import DeclarativeBase
        assert isinstance(Base, type)
        # Base should be a subclass of DeclarativeBase
        assert hasattr(Base, 'metadata')

    def test_base_metadata_exists(self):
        """Test that Base metadata exists."""
        assert Base.metadata is not None


class TestEngineAndSessionMaker:
    """Engine and session factory tests."""

    def test_engine_exists(self):
        """Test that the engine is created."""
        assert engine is not None

    def test_async_session_maker_exists(self):
        """Test that the session factory is created."""
        assert async_session_maker is not None


class TestInitDb:
    """Database initialization tests."""

    async def test_init_db_creates_tables(self):
        """Test that init_db creates tables."""
        # Drop all tables first
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        # Call init_db
        await init_db()

        # Verify tables are created (by querying user table)
        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            tables = result.fetchall()
            assert len(tables) >= 1

    async def test_init_db_idempotent(self):
        """Test that init_db can be called multiple times."""
        # First call
        await init_db()
        # Second call should not error
        await init_db()


class TestCreateDefaultAdmin:
    """Default admin creation tests."""

    async def test_create_default_admin_when_not_exists(self):
        """Test admin creation when it does not exist."""
        from sqlalchemy import delete
        from app.utils.security import get_password_hash

        settings = get_settings()

        # Delete admin if it exists
        async with async_session_maker() as session:
            await session.execute(
                delete(User).where(User.username == settings.ADMIN_USERNAME)
            )
            await session.commit()

        # Create default admin
        await create_default_admin()

        # Verify admin is created
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
        """Test that admin is not recreated when it already exists."""
        from app.utils.security import get_password_hash
        from sqlalchemy import delete

        settings = get_settings()

        # Create an admin first
        async with async_session_maker() as session:
            await session.execute(
                delete(User).where(User.username == settings.ADMIN_USERNAME)
            )
            await session.commit()

        # First creation
        await create_default_admin()

        # Get the first created admin ID
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admin_first = result.scalar_one_or_none()
            first_id = admin_first.id if admin_first else None

        # Second creation (should not create new one)
        await create_default_admin()

        # Verify no duplicate creation
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admin_second = result.scalar_one_or_none()

        assert admin_second is not None
        if first_id:
            assert admin_second.id == first_id


class TestGetDb:
    """Database session tests."""

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
    """SQL repository tests."""

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
        """Test pagination functionality."""
        repo = SQLRepository(User)

        # Create multiple users
        for i in range(5):
            await repo.create(User(username=f"page_{i}", email=f"page_{i}@t.com", hashed_password="x"))

        # Test limit and skip
        page1 = await repo.list(limit=2, skip=0)
        page2 = await repo.list(limit=2, skip=2)

        assert len(page1) == 2
        assert len(page2) == 2
        # Ensure pagination results are different
        if page1 and page2:
            assert page1[0].id != page2[0].id

    async def test_update_nonexistent(self):
        """Test updating a nonexistent record."""
        repo = SQLRepository(User)
        result = await repo.update("nonexistent-id-xyz", {"email": "test@test.com"})
        assert result is None

    async def test_list_with_ordering(self):
        """Test ordering functionality."""
        repo = SQLRepository(User)

        # Create multiple users
        await repo.create(User(username="order_a", email="order_a@t.com", hashed_password="x"))
        await repo.create(User(username="order_b", email="order_b@t.com", hashed_password="x"))
        await repo.create(User(username="order_c", email="order_c@t.com", hashed_password="x"))

        # Test ascending order
        items_asc = await repo.list(order_by="username", order_desc=False, limit=10)
        # Test descending order
        items_desc = await repo.list(order_by="username", order_desc=True, limit=10)

        assert len(items_asc) >= 3
        assert len(items_desc) >= 3
