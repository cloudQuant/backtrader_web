from types import SimpleNamespace

import pytest
from starlette.requests import Request as StarletteRequest

from app.api.data_management_deps import get_current_db_user, require_data_admin_user
from app.db.database import async_session_maker, create_tables
from app.models.permission import Role, user_roles
from app.models.user import User
from app.utils.security import get_password_hash


def make_request() -> StarletteRequest:
    return StarletteRequest(
        {
            "type": "http",
            "method": "GET",
            "path": "/data/test",
            "headers": [],
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
async def test_get_current_db_user_returns_database_user(monkeypatch):
    await create_tables()

    async with async_session_maker() as session:
        user = User(
            username="data-user",
            email="data-user@test.example.com",
            hashed_password=get_password_hash("StrongPass1!"),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        monkeypatch.setattr(
            "app.api.data_management_deps.decode_access_token",
            lambda _: {"sub": user.id, "username": user.username},
            raising=True,
        )

        request = make_request()
        credentials = SimpleNamespace(credentials="valid-token")
        resolved_user = await get_current_db_user(
            request=request,
            credentials=credentials,
            db=session,
        )

    assert resolved_user.id == user.id
    assert request.state.user_id == user.id


@pytest.mark.asyncio
async def test_require_data_admin_user_accepts_admin_role(monkeypatch):
    await create_tables()

    async with async_session_maker() as session:
        user = User(
            username="role-admin",
            email="role-admin@test.example.com",
            hashed_password=get_password_hash("StrongPass1!"),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        await session.execute(
            user_roles.insert().values(user_id=user.id, role=Role.ADMIN.value)
        )
        await session.commit()
        await session.refresh(user)

        monkeypatch.setattr(
            "app.api.data_management_deps.decode_access_token",
            lambda _: {"sub": user.id, "username": user.username},
            raising=True,
        )

        request = make_request()
        credentials = SimpleNamespace(credentials="valid-token")
        resolved_user = await require_data_admin_user(
            request=request,
            credentials=credentials,
            db=session,
        )

    assert resolved_user.id == user.id


@pytest.mark.asyncio
async def test_require_data_admin_user_rejects_non_admin(monkeypatch):
    await create_tables()

    async with async_session_maker() as session:
        user = User(
            username="plain-user",
            email="plain-user@test.example.com",
            hashed_password=get_password_hash("StrongPass1!"),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        monkeypatch.setattr(
            "app.api.data_management_deps.decode_access_token",
            lambda _: {"sub": user.id, "username": user.username},
            raising=True,
        )

        request = make_request()
        credentials = SimpleNamespace(credentials="valid-token")
        with pytest.raises(Exception) as exc_info:
            await require_data_admin_user(
                request=request,
                credentials=credentials,
                db=session,
            )

    assert getattr(exc_info.value, "status_code", None) == 403
