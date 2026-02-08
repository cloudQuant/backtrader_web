"""
数据库模块测试
"""
import pytest
from app.db.database import Base, get_db
from app.db.sql_repository import SQLRepository
from app.models.user import User


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
