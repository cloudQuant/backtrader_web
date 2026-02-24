"""
Tests to achieve 100% code coverage.

Covers remaining gaps in:
- app/api/strategy_version.py: lines 85, 308, 364, 415-418, 453-456
  (PermissionError/ValueError exception handlers)
- app/db/sql_repository.py: lines 142-143, 145
  (list filter with list values and None values)
- app/services/strategy_service.py: line 49
  (_infer_category returning "arbitrage")
- app/utils/sandbox.py: lines 198-202
  (ValueError re-raise and generic Exception -> RuntimeError)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.db.sql_repository import SQLRepository
from app.models.user import User
from app.services.strategy_service import _infer_category
from app.utils.sandbox import StrategySandbox


# ==================== strategy_version.py PermissionError handlers ====================


@pytest.mark.asyncio
class TestStrategyVersionPermissionErrors:
    """Test PermissionError exception handlers in strategy_version API."""

    async def test_create_version_permission_error(self, client: AsyncClient, auth_headers: dict):
        """Cover line 85: PermissionError in create_strategy_version."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.create_version = AsyncMock(side_effect=PermissionError("no access"))
            mock_cls.return_value = mock_svc

            resp = await client.post(
                "/api/v1/strategy-versions/versions",
                headers=auth_headers,
                json={
                    "strategy_id": "s1",
                    "version_name": "v1.0.0",
                    "code": "class S(bt.Strategy): pass",
                    "params": {},
                    "branch": "main",
                    "tags": [],
                    "changelog": "",
                    "is_default": False,
                },
            )
            assert resp.status_code == 403  # Forbidden when permission denied

    async def test_compare_versions_permission_error(self, client: AsyncClient, auth_headers: dict):
        """Cover line 308: PermissionError in compare_strategy_versions."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.compare_versions = AsyncMock(side_effect=PermissionError("no access"))
            mock_cls.return_value = mock_svc

            resp = await client.post(
                "/api/v1/strategy-versions/versions/compare",
                headers=auth_headers,
                json={
                    "strategy_id": "s1",
                    "from_version_id": "v1",
                    "to_version_id": "v2",
                    "comparison_type": "code",
                },
            )
            assert resp.status_code == 403  # Forbidden when permission denied

    async def test_rollback_version_permission_error(self, client: AsyncClient, auth_headers: dict):
        """Cover line 364: PermissionError in rollback_strategy_version."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.rollback_version = AsyncMock(side_effect=PermissionError("no access"))
            mock_cls.return_value = mock_svc

            resp = await client.post(
                "/api/v1/strategy-versions/versions/rollback",
                headers=auth_headers,
                json={
                    "strategy_id": "s1",
                    "target_version_id": "v1",
                    "reason": "revert",
                },
            )
            assert resp.status_code == 403  # Forbidden when permission denied

    async def test_create_branch_permission_error(self, client: AsyncClient, auth_headers: dict):
        """Cover lines 415-416: PermissionError in create_strategy_branch."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.create_branch = AsyncMock(side_effect=PermissionError("no access"))
            mock_cls.return_value = mock_svc

            resp = await client.post(
                "/api/v1/strategy-versions/branches",
                headers=auth_headers,
                json={
                    "strategy_id": "s1",
                    "branch_name": "feature/x",
                    "parent_branch": "main",
                },
            )
            assert resp.status_code == 403  # Forbidden when permission denied

    async def test_create_branch_value_error(self, client: AsyncClient, auth_headers: dict):
        """Cover lines 417-418: ValueError in create_strategy_branch."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.create_branch = AsyncMock(side_effect=ValueError("strategy not found"))
            mock_cls.return_value = mock_svc

            resp = await client.post(
                "/api/v1/strategy-versions/branches",
                headers=auth_headers,
                json={
                    "strategy_id": "s1",
                    "branch_name": "feature/x",
                    "parent_branch": "main",
                },
            )
            assert resp.status_code == 404

    async def test_list_branches_permission_error(self, client: AsyncClient, auth_headers: dict):
        """Cover lines 453-454: PermissionError in list_strategy_branches."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.list_branches = AsyncMock(side_effect=PermissionError("no access"))
            mock_cls.return_value = mock_svc

            resp = await client.get(
                "/api/v1/strategy-versions/strategies/s1/branches",
                headers=auth_headers,
            )
            assert resp.status_code == 403  # Forbidden when permission denied

    async def test_list_branches_value_error(self, client: AsyncClient, auth_headers: dict):
        """Cover lines 455-456: ValueError in list_strategy_branches."""
        with patch("app.api.strategy_version.VersionControlService") as mock_cls:
            mock_svc = AsyncMock()
            mock_svc.list_branches = AsyncMock(side_effect=ValueError("strategy not found"))
            mock_cls.return_value = mock_svc

            resp = await client.get(
                "/api/v1/strategy-versions/strategies/s1/branches",
                headers=auth_headers,
            )
            assert resp.status_code == 404


# ==================== sql_repository.py list filter edge cases ====================


@pytest.mark.asyncio
class TestSQLRepositoryListFilters:
    """Test list() filter for list values and None values."""

    async def test_list_filter_with_list_value(self):
        """Cover lines 142-143: filter with non-empty list triggers IN query."""
        repo = SQLRepository(User)
        # Filter with a list value — should produce WHERE col IN (...)
        results = await repo.list(filters={"username": ["alice", "bob"]})
        assert isinstance(results, list)

    async def test_list_filter_with_empty_list_value(self):
        """Cover line 142 false branch: empty list is skipped."""
        repo = SQLRepository(User)
        results = await repo.list(filters={"username": []})
        assert isinstance(results, list)

    async def test_list_filter_with_none_value(self):
        """Cover line 145: filter with None triggers IS NULL query."""
        repo = SQLRepository(User)
        results = await repo.list(filters={"email": None})
        assert isinstance(results, list)

    async def test_list_filter_with_tuple_value(self):
        """Cover line 141: filter with tuple also triggers IN query."""
        repo = SQLRepository(User)
        results = await repo.list(filters={"username": ("alice",)})
        assert isinstance(results, list)

    async def test_list_filter_with_set_value(self):
        """Cover line 141: filter with set also triggers IN query."""
        repo = SQLRepository(User)
        results = await repo.list(filters={"username": {"alice"}})
        assert isinstance(results, list)


# ==================== strategy_service.py _infer_category ====================


class TestInferCategoryArbitrage:
    """Test _infer_category returns 'arbitrage'."""

    def test_arbitrage_category(self):
        """Cover line 49: return 'arbitrage'."""
        assert _infer_category("PairTrading", "a pair trading strategy") == "arbitrage"

    def test_hedge_category(self):
        """Hedge keyword also returns arbitrage."""
        assert _infer_category("HedgeBot", "hedge fund style") == "arbitrage"

    def test_long_short_category(self):
        """long_short keyword also returns arbitrage."""
        assert _infer_category("LS", "long_short equity") == "arbitrage"


# ==================== sandbox.py ValueError and generic Exception ====================


class TestSandboxExceptionHandlers:
    """Test sandbox exception paths for ValueError and generic Exception."""

    def test_value_error_reraise(self):
        """Cover lines 198-200: ValueError during exec is re-raised directly."""
        # int('abc') raises ValueError; int is in allowed builtins
        code = "x = int('not_a_number')"
        with pytest.raises(ValueError):
            StrategySandbox.execute_strategy_code(code)

    def test_generic_exception_becomes_runtime_error(self):
        """Cover lines 201-202: generic Exception during exec becomes RuntimeError."""
        # 1/0 raises ZeroDivisionError which is not specifically caught
        code = "x = 1 / 0"
        with pytest.raises(RuntimeError, match="Strategy code execution failed"):
            StrategySandbox.execute_strategy_code(code)
