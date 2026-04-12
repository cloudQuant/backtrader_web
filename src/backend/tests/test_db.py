"""
Database module tests.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select, text

from app.config import get_settings
from app.db.database import (
    Base,
    async_session_maker,
    create_default_admin,
    create_tables,
    engine,
    ensure_database_ready,
    get_db,
    init_db,
)
from app.db.session_provider import unit_of_work
from app.db.sql_repository import SQLRepository
from app.models.permission import Role, user_roles
from app.models.user import User


class TestBase:
    """ORM base class tests."""

    def test_base_metadata_exists(self):
        assert Base.metadata is not None


class TestEngineAndSessionMaker:
    """Engine and session factory tests."""

    def test_engine_exists(self):
        assert engine is not None

    def test_async_session_maker_exists(self):
        assert async_session_maker is not None


@pytest.mark.asyncio
class TestDatabaseInitialization:
    """Database initialization tests."""

    async def test_create_tables_creates_schema(self):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await create_tables()

        async with engine.begin() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            )
            assert len(result.fetchall()) == 1
            ak_result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='ak_data_scripts'")
            )
            assert len(ak_result.fetchall()) == 1

    async def test_init_db_only_creates_tables(self):
        settings = get_settings()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await init_db()

        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            assert result.scalar_one_or_none() is None

    async def test_create_default_admin_when_not_exists(self):
        settings = get_settings()
        await create_tables()

        async with async_session_maker() as session:
            await session.execute(delete(User).where(User.username == settings.ADMIN_USERNAME))
            await session.execute(delete(user_roles))
            await session.commit()

        await create_default_admin()

        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admin = result.scalar_one_or_none()
            role_result = await session.execute(
                select(user_roles.c.role).where(user_roles.c.user_id == admin.id)
            )
            roles = set(role_result.scalars().all())

        assert admin is not None
        assert admin.username == settings.ADMIN_USERNAME
        assert admin.email == settings.ADMIN_EMAIL
        assert admin.is_active is True
        assert Role.ADMIN.value in roles

    async def test_create_default_admin_is_idempotent(self):
        settings = get_settings()
        await create_tables()

        async with async_session_maker() as session:
            await session.execute(delete(User).where(User.username == settings.ADMIN_USERNAME))
            await session.execute(delete(user_roles))
            await session.commit()

        await create_default_admin()
        await create_default_admin()

        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )
            admins = list(result.scalars().all())
            role_result = await session.execute(
                select(user_roles.c.role).where(user_roles.c.user_id == admins[0].id)
            )
            roles = list(role_result.scalars().all())

        assert len(admins) == 1
        assert roles.count(Role.ADMIN.value) == 1

    async def test_ensure_database_ready_creates_schema_when_enabled(self, monkeypatch):
        create_tables_mock = AsyncMock()
        verify_connection_mock = AsyncMock()
        create_default_admin_mock = AsyncMock()

        monkeypatch.setattr("app.db.database.create_tables", create_tables_mock)
        monkeypatch.setattr("app.db.database.verify_database_connection", verify_connection_mock)
        monkeypatch.setattr("app.db.database.create_default_admin", create_default_admin_mock)
        monkeypatch.setattr(
            "app.db.database.settings",
            type(
                "S",
                (),
                {"DB_AUTO_CREATE_SCHEMA": True, "DB_AUTO_CREATE_DEFAULT_ADMIN": False},
            )(),
        )

        await ensure_database_ready()

        assert create_tables_mock.await_count == 1
        assert verify_connection_mock.await_count == 0
        assert create_default_admin_mock.await_count == 0

    async def test_ensure_database_ready_only_verifies_connection_when_disabled(self, monkeypatch):
        create_tables_mock = AsyncMock()
        verify_connection_mock = AsyncMock()
        create_default_admin_mock = AsyncMock()

        monkeypatch.setattr("app.db.database.create_tables", create_tables_mock)
        monkeypatch.setattr("app.db.database.verify_database_connection", verify_connection_mock)
        monkeypatch.setattr("app.db.database.create_default_admin", create_default_admin_mock)
        monkeypatch.setattr(
            "app.db.database.settings",
            type(
                "S",
                (),
                {"DB_AUTO_CREATE_SCHEMA": False, "DB_AUTO_CREATE_DEFAULT_ADMIN": False},
            )(),
        )

        await ensure_database_ready()

        assert create_tables_mock.await_count == 0
        assert verify_connection_mock.await_count == 1
        assert create_default_admin_mock.await_count == 0

    async def test_ensure_database_ready_creates_default_admin_when_enabled(self, monkeypatch):
        create_tables_mock = AsyncMock()
        verify_connection_mock = AsyncMock()
        create_default_admin_mock = AsyncMock()

        monkeypatch.setattr("app.db.database.create_tables", create_tables_mock)
        monkeypatch.setattr("app.db.database.verify_database_connection", verify_connection_mock)
        monkeypatch.setattr("app.db.database.create_default_admin", create_default_admin_mock)
        monkeypatch.setattr(
            "app.db.database.settings",
            type(
                "S",
                (),
                {"DB_AUTO_CREATE_SCHEMA": True, "DB_AUTO_CREATE_DEFAULT_ADMIN": True},
            )(),
        )

        await ensure_database_ready()

        assert create_tables_mock.await_count == 1
        assert verify_connection_mock.await_count == 0
        assert create_default_admin_mock.await_count == 1


@pytest.mark.asyncio
class TestGetDb:
    """Database session tests."""

    async def test_get_db_yields_session(self):
        async for session in get_db():
            assert session is not None
            break


@pytest.mark.asyncio
class TestSQLRepository:
    """SQL repository tests."""

    async def test_create_and_get(self):
        repo = SQLRepository(User)
        created = await repo.create(
            User(username="repo_test", email="repo@test.com", hashed_password="fakehash")
        )

        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.username == "repo_test"

    async def test_update_and_delete(self):
        repo = SQLRepository(User)
        created = await repo.create(
            User(username="upd_test", email="upd@test.com", hashed_password="x")
        )

        updated = await repo.update(created.id, {"email": "updated@test.com"})
        assert updated is not None
        assert updated.email == "updated@test.com"
        assert await repo.delete(created.id) is True
        assert await repo.get_by_id(created.id) is None

    async def test_filters_and_count(self):
        repo = SQLRepository(User)
        await repo.create(User(username="filter_u", email="filter@t.com", hashed_password="x"))

        items = await repo.list(filters={"username": "filter_u"})
        assert len(items) == 1
        assert await repo.count(filters={"username": "filter_u"}) == 1
        assert await repo.exists(filters={"username": "filter_u"}) is True

    async def test_external_session_commits_at_unit_of_work_boundary(self):
        async with unit_of_work() as session:
            repo = SQLRepository(User, session=session)
            await repo.create(
                User(username="uow_commit", email="uow_commit@test.com", hashed_password="x")
            )

        repo = SQLRepository(User)
        created = await repo.get_by_field("username", "uow_commit")
        assert created is not None

    async def test_external_session_rolls_back_on_error(self):
        with pytest.raises(RuntimeError):
            async with unit_of_work() as session:
                repo = SQLRepository(User, session=session)
                await repo.create(
                    User(
                        username="uow_rollback",
                        email="uow_rollback@test.com",
                        hashed_password="x",
                    )
                )
                raise RuntimeError("force rollback")

        repo = SQLRepository(User)
        rolled_back = await repo.get_by_field("username", "uow_rollback")
        assert rolled_back is None
