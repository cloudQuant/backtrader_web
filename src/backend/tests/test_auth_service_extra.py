from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_change_password_user_not_found_returns_false():
    from app.services.auth_service import AuthService

    svc = AuthService()
    svc.user_repo = AsyncMock()
    svc.user_repo.get_by_id = AsyncMock(return_value=None)

    assert await svc.change_password("missing", "old", "new") is False


@pytest.mark.asyncio
async def test_get_user_by_id_missing_returns_none():
    from app.services.auth_service import AuthService

    svc = AuthService()
    svc.user_repo = AsyncMock()
    svc.user_repo.get_by_id = AsyncMock(return_value=None)

    assert await svc.get_user_by_id("missing") is None

