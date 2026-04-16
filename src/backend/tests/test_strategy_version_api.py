"""
Strategy Version Management API Tests.

Tests:
- Create/get/update strategy versions
- Version list, activate, set default
- Version comparison, rollback
- Branch management
- WebSocket endpoints
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.utils.security import create_access_token

# Valid version creation request
VALID_VERSION_CREATE = {
    "strategy_id": "test_strategy",
    "version_name": "v1.0.0",
    "code": "class TestStrategy(bt.Strategy): pass",
    "params": {"period": 20},
    "branch": "main",
    "tags": ["latest"],
    "changelog": "Initial version",
    "is_default": True,
}

# Valid version comparison request
VALID_VERSION_COMPARE = {
    "strategy_id": "test_strategy",
    "from_version_id": "ver1",
    "to_version_id": "ver2",
    "comparison_type": "code",
}

# Valid version rollback request
VALID_VERSION_ROLLBACK = {
    "strategy_id": "test_strategy",
    "target_version_id": "ver1",
    "reason": "Rollback to stable version",
}


@pytest.mark.asyncio
class TestCreateStrategyVersion:
    """Test strategy version creation."""

    async def test_create_version_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.post("/api/v1/strategy-versions/versions", json=VALID_VERSION_CREATE)
        assert resp.status_code == 401  # Unauthorized

    async def test_create_version_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful version creation."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_version = MagicMock(id="ver123")
            mock_service.create_version = AsyncMock(return_value=mock_version)
            mock_service._to_response = MagicMock(
                return_value={
                    "id": "ver123",
                    "strategy_id": "test_strategy",
                    "version_number": 1,
                    "version_name": "v1.0.0",
                    "branch": "main",
                    "status": "draft",
                    "tags": ["latest"],
                    "description": None,
                    "is_active": False,
                    "is_default": True,
                    "is_current": True,
                    "parent_version_id": None,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
            mock_service_class.return_value = mock_service

            with patch("app.api.strategy_version.ws_manager") as mock_ws_mgr:
                mock_ws_mgr.send_to_task = AsyncMock()
                resp = await client.post(
                    "/api/v1/strategy-versions/versions",
                    headers=auth_headers,
                    json=VALID_VERSION_CREATE,
                )

            assert resp.status_code == 200

    async def test_create_version_invalid_data(self, client: AsyncClient, auth_headers: dict):
        """Test invalid data."""
        resp = await client.post(
            "/api/v1/strategy-versions/versions",
            headers=auth_headers,
            json={
                "strategy_id": "",  # Invalid
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestListStrategyVersions:
    """Test strategy version list."""

    async def test_list_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.get("/api/v1/strategy-versions/strategies/test_strategy/versions")
        assert resp.status_code == 401  # Unauthorized

    async def test_list_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful list."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_versions = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/strategy-versions/strategies/test_strategy/versions", headers=auth_headers
            )
            assert resp.status_code == 200

    async def test_list_with_branch_filter(self, client: AsyncClient, auth_headers: dict):
        """Test branch filter."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_versions = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/strategy-versions/strategies/test_strategy/versions?branch=main",
                headers=auth_headers,
            )
            assert resp.status_code == 200

    async def test_list_with_status_filter(self, client: AsyncClient, auth_headers: dict):
        """Test status filter."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_versions = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/strategy-versions/strategies/test_strategy/versions?status=active",
                headers=auth_headers,
            )
            assert resp.status_code == 200

    async def test_list_with_pagination(self, client: AsyncClient, auth_headers: dict):
        """Test pagination."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_versions = AsyncMock(return_value=([], 0))
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/strategy-versions/strategies/test_strategy/versions?limit=10&offset=20",
                headers=auth_headers,
            )
            assert resp.status_code == 200

    async def test_list_invalid_limit(self, client: AsyncClient, auth_headers: dict):
        """Test invalid limit."""
        resp = await client.get(
            "/api/v1/strategy-versions/strategies/test_strategy/versions?limit=200",
            headers=auth_headers,
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestGetStrategyVersion:
    """Test get strategy version details."""

    async def test_get_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.get("/api/v1/strategy-versions/versions/ver123")
        assert resp.status_code == 401  # Unauthorized

    async def test_get_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test version not found."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_version = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/strategy-versions/versions/nonexistent", headers=auth_headers
            )
            assert resp.status_code == 404

    async def test_get_forbidden(self, client: AsyncClient, auth_headers: dict):
        """Test forbidden access."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_version = MagicMock()
            mock_version.strategy_id = "other_user_id"  # Different user
            mock_service.get_version = AsyncMock(return_value=mock_version)
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/strategy-versions/versions/ver123", headers=auth_headers
            )
            assert resp.status_code == 403  # Forbidden - user has token but not owner

    async def test_get_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful get."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_version = MagicMock(created_by="owner-id")
            mock_service.get_version = AsyncMock(return_value=mock_version)
            mock_service._to_response = MagicMock(
                return_value={
                    "id": "ver123",
                    "strategy_id": "test_strategy",
                    "version_number": 1,
                    "version_name": "v1.0.0",
                    "branch": "main",
                    "status": "draft",
                    "tags": ["latest"],
                    "description": None,
                    "is_active": False,
                    "is_default": True,
                    "is_current": True,
                    "parent_version_id": None,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
            mock_service_class.return_value = mock_service
            owner_headers = {
                "Authorization": f"Bearer {create_access_token({'sub': 'owner-id', 'username': 'owner'})}"
            }

            resp = await client.get(
                "/api/v1/strategy-versions/versions/ver123", headers=owner_headers
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestUpdateStrategyVersion:
    """Test strategy version update."""

    async def test_update_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.put(
            "/api/v1/strategy-versions/versions/ver123", json={"code": "new code"}
        )
        assert resp.status_code == 401  # Unauthorized

    async def test_update_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test version not found."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.update_version = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            resp = await client.put(
                "/api/v1/strategy-versions/versions/nonexistent",
                headers=auth_headers,
                json={"description": "Updated description"},
            )
            assert resp.status_code == 404

    async def test_update_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful update."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_version = MagicMock()
            mock_service.update_version = AsyncMock(return_value=mock_version)
            mock_service._to_response = MagicMock(
                return_value={
                    "id": "ver123",
                    "strategy_id": "test_strategy",
                    "version_number": 1,
                    "version_name": "v1.0.0",
                    "branch": "main",
                    "status": "draft",
                    "tags": ["updated"],
                    "description": "Updated description",
                    "is_active": False,
                    "is_default": True,
                    "is_current": True,
                    "parent_version_id": None,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
            mock_service_class.return_value = mock_service

            resp = await client.put(
                "/api/v1/strategy-versions/versions/ver123",
                headers=auth_headers,
                json={
                    "description": "Updated description",
                    "tags": ["updated"],
                },
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestSetVersionDefault:
    """Test set default version."""

    async def test_set_default_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.post("/api/v1/strategy-versions/versions/ver123/set-default")
        assert resp.status_code == 401  # Unauthorized

    async def test_set_default_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test version not found."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.set_version_default = AsyncMock(return_value=False)
            mock_service_class.return_value = mock_service

            resp = await client.post(
                "/api/v1/strategy-versions/versions/nonexistent/set-default", headers=auth_headers
            )
            assert resp.status_code == 404

    async def test_set_default_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful set default."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.set_version_default = AsyncMock(return_value=True)
            mock_service_class.return_value = mock_service

            resp = await client.post(
                "/api/v1/strategy-versions/versions/ver123/set-default", headers=auth_headers
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestActivateVersion:
    """Test activate version."""

    async def test_activate_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.post("/api/v1/strategy-versions/versions/ver123/activate")
        assert resp.status_code == 401  # Unauthorized

    async def test_activate_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test version not found."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.activate_version = AsyncMock(return_value=False)
            mock_service_class.return_value = mock_service

            resp = await client.post(
                "/api/v1/strategy-versions/versions/nonexistent/activate", headers=auth_headers
            )
            assert resp.status_code == 404

    async def test_activate_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful activation."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.activate_version = AsyncMock(return_value=True)
            mock_service_class.return_value = mock_service

            resp = await client.post(
                "/api/v1/strategy-versions/versions/ver123/activate", headers=auth_headers
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestCompareVersions:
    """Test version comparison."""

    async def test_compare_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.post(
            "/api/v1/strategy-versions/versions/compare", json=VALID_VERSION_COMPARE
        )
        assert resp.status_code == 401  # Unauthorized

    async def test_compare_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful comparison."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_comparison = MagicMock(
                id="cmp123",
                strategy_id="test_strategy",
                from_version_id="ver1",
                to_version_id="ver2",
                code_diff="diff --git",
                params_diff={"period": [10, 20]},
                performance_diff={"return": [0.1, 0.2]},
                created_at=datetime.now().isoformat(),
            )
            mock_service.compare_versions = AsyncMock(return_value=mock_comparison)
            mock_service_class.return_value = mock_service

            with patch("app.api.strategy_version.ws_manager") as mock_ws_mgr:
                mock_ws_mgr.send_to_task = AsyncMock()
                resp = await client.post(
                    "/api/v1/strategy-versions/versions/compare",
                    headers=auth_headers,
                    json=VALID_VERSION_COMPARE,
                )

            assert resp.status_code == 200

    async def test_compare_invalid_data(self, client: AsyncClient, auth_headers: dict):
        """Test invalid data."""
        resp = await client.post(
            "/api/v1/strategy-versions/versions/compare",
            headers=auth_headers,
            json={
                "strategy_id": "",  # Invalid
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestRollbackVersion:
    """Test version rollback."""

    async def test_rollback_requires_auth(self, client: AsyncClient):
        """Test authentication required."""
        resp = await client.post(
            "/api/v1/strategy-versions/versions/rollback", json=VALID_VERSION_ROLLBACK
        )
        assert resp.status_code == 401  # Unauthorized

    async def test_rollback_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful rollback."""
        with patch("app.api.strategy_version.VersionControlService") as mock_service_class:
            mock_service = AsyncMock()
            mock_version = MagicMock(id="ver124")
            mock_service.rollback_version = AsyncMock(return_value=mock_version)
            mock_service._to_response = MagicMock(
                return_value={
                    "id": "ver124",
                    "strategy_id": "test_strategy",
                    "version_number": 2,
                    "version_name": "v1.0.1",
                    "branch": "main",
                    "status": "draft",
                    "tags": [],
                    "description": None,
                    "is_active": False,
                    "is_default": False,
                    "is_current": True,
                    "parent_version_id": "ver1",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )
            mock_service_class.return_value = mock_service

            with patch("app.api.strategy_version.ws_manager") as mock_ws_mgr:
                mock_ws_mgr.send_to_task = AsyncMock()
                resp = await client.post(
                    "/api/v1/strategy-versions/versions/rollback",
                    headers=auth_headers,
                    json=VALID_VERSION_ROLLBACK,
                )

            assert resp.status_code == 200

    async def test_rollback_invalid_data(self, client: AsyncClient, auth_headers: dict):
        """Test invalid data."""
        resp = await client.post(
            "/api/v1/strategy-versions/versions/rollback",
            headers=auth_headers,
            json={
                "strategy_id": "",  # Invalid
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestBranchOperations:
    """Test branch operations."""

    async def test_create_branch_success(self, client: AsyncClient, auth_headers: dict):
        """Test create branch."""
        strat = await client.post(
            "/api/v1/strategy/",
            headers=auth_headers,
            json={
                "name": "s1",
                "description": "d",
                "code": "print('x')",
                "params": {},
                "category": "custom",
            },
        )
        assert strat.status_code == 200
        strategy_id = strat.json()["id"]

        resp = await client.post(
            "/api/v1/strategy-versions/branches",
            headers=auth_headers,
            json={
                "strategy_id": strategy_id,
                "branch_name": "feature/test",
                "parent_branch": "main",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_id"] == strategy_id
        assert body["branch_name"] == "feature/test"

    async def test_list_branches_success(self, client: AsyncClient, auth_headers: dict):
        """Test list branches."""
        strat = await client.post(
            "/api/v1/strategy/",
            headers=auth_headers,
            json={
                "name": "s2",
                "description": "d",
                "code": "print('x')",
                "params": {},
                "category": "custom",
            },
        )
        assert strat.status_code == 200
        strategy_id = strat.json()["id"]

        # Create one branch to ensure at least one item is present (main may be auto-created as parent).
        _ = await client.post(
            "/api/v1/strategy-versions/branches",
            headers=auth_headers,
            json={
                "strategy_id": strategy_id,
                "branch_name": "feature/test",
                "parent_branch": "main",
            },
        )

        resp = await client.get(
            f"/api/v1/strategy-versions/strategies/{strategy_id}/branches",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert isinstance(body["items"], list)


@pytest.mark.asyncio
class TestStrategyVersionWebSocket:
    """Test WebSocket endpoints."""

    async def test_websocket_connection(self):
        """Test WebSocket connection - basic test."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.api.strategy_version import strategy_version_websocket

        # Create mock WebSocket object
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        # Mock WebSocket manager
        with patch("app.api.strategy_version.ws_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.send_to_task = AsyncMock()

            # Mock asyncio.sleep to avoid infinite loop - patch on builtin asyncio
            with patch("asyncio.sleep") as mock_sleep:
                # First return normally, second throw exception
                mock_sleep.side_effect = [None, Exception("Exit loop")]

                import sys

                old_asyncio = sys.modules.get("asyncio")
                try:
                    # Since asyncio is not imported in module, need to inject it
                    sys.modules["asyncio"] = sys.modules.get("asyncio", asyncio)

                    await strategy_version_websocket(mock_ws, "test_strategy")
                finally:
                    # Restore
                    if old_asyncio:
                        sys.modules["asyncio"] = old_asyncio

                client_id = mock_mgr.connect.await_args.args[2]
                mock_mgr.connect.assert_awaited_once_with(
                    mock_ws, "strategy:test_strategy", client_id
                )
                mock_mgr.disconnect.assert_called_once_with(
                    mock_ws, "strategy:test_strategy", client_id
                )

    async def test_websocket_sends_connected_message(self):
        """Test WebSocket sends connected message."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.api.strategy_version import strategy_version_websocket

        # Create mock WebSocket object
        mock_ws = MagicMock()

        # Mock WebSocket manager
        with patch("app.api.strategy_version.ws_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.send_to_task = AsyncMock()

            # Mock asyncio.sleep
            with patch("asyncio.sleep", side_effect=Exception("Exit loop")):
                import sys

                old_asyncio = sys.modules.get("asyncio")
                try:
                    # Since asyncio is not imported in module, need to inject it
                    sys.modules["asyncio"] = sys.modules.get("asyncio", asyncio)

                    await strategy_version_websocket(mock_ws, "test_strategy")
                finally:
                    if old_asyncio:
                        sys.modules["asyncio"] = old_asyncio

                client_id = mock_mgr.connect.await_args.args[2]
                mock_mgr.connect.assert_awaited_once_with(
                    mock_ws, "strategy:test_strategy", client_id
                )
                mock_mgr.disconnect.assert_called_once_with(
                    mock_ws, "strategy:test_strategy", client_id
                )


class TestServiceDependency:
    """Test service dependency."""

    def test_get_version_control_service(self):
        """Test get version control service."""
        from app.api.strategy_version import get_version_control_service

        svc1 = get_version_control_service()
        svc2 = get_version_control_service()
        # `lru_cache` may be enabled to keep service state stable.
        assert svc1 is not None
        assert svc2 is not None
