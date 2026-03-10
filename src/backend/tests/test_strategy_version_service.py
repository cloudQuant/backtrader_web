"""
Strategy Version Management Service Tests.

Tests:
- Create strategy version
- Get/update version
- Set default version
- Activate version
- Version comparison
- Version rollback
- Branch management
- Helper functions (code diff, params diff)
"""
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestVersionControlServiceInitialization:
    """Test service initialization."""

    def test_initialization(self):
        """Test initialization."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        assert service.version_repo is not None
        assert service.branch_repo is not None
        assert service.comparison_repo is not None
        assert service.rollback_repo is not None
        assert service.strategy_repo is not None


class TestGenerateCodeDiff:
    """Test code diff generation."""

    def test_generate_code_diff_identical(self):
        """Test diff for identical code."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        code = "def test():\n    return 1\n"

        diff = service._generate_code_diff(code, code, "v1", "v2")

        # Identical code should have no diff (or only header)
        assert isinstance(diff, str)

    def test_generate_code_diff_different(self):
        """Test diff for different code."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        code1 = "def test():\n    return 1\n"
        code2 = "def test():\n    return 2\n"

        diff = service._generate_code_diff(code1, code2, "v1", "v2")

        # Should have diff
        assert isinstance(diff, str)
        assert len(diff) > 0

    def test_generate_code_diff_with_lines(self):
        """Test diff for multi-line code."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        code1 = "line1\nline2\nline3\n"
        code2 = "line1\nline2modified\nline3\n"

        diff = service._generate_code_diff(code1, code2, "v1", "v2")

        assert isinstance(diff, str)


class TestGenerateParamsDiff:
    """Test parameter diff generation."""

    def test_generate_params_diff_identical(self):
        """Test diff for identical parameters."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        params1 = {"a": 1, "b": 2}
        params2 = {"a": 1, "b": 2}

        diff = service._generate_params_diff(params1, params2)

        assert "added" in diff
        assert "removed" in diff
        assert "modified" in diff
        assert "unchanged" in diff
        # All params should be unchanged
        assert len(diff["unchanged"]) == 2
        assert len(diff["added"]) == 0
        assert len(diff["removed"]) == 0
        assert len(diff["modified"]) == 0

    def test_generate_params_diff_added(self):
        """Test adding parameters."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        params1 = {"a": 1}
        params2 = {"a": 1, "b": 2}

        diff = service._generate_params_diff(params1, params2)

        assert len(diff["added"]) == 1
        assert diff["added"]["b"] == 2
        assert len(diff["unchanged"]) == 1

    def test_generate_params_diff_removed(self):
        """Test removing parameters."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        params1 = {"a": 1, "b": 2}
        params2 = {"a": 1}

        diff = service._generate_params_diff(params1, params2)

        assert len(diff["removed"]) == 1
        assert diff["removed"]["b"] == 2
        assert len(diff["unchanged"]) == 1

    def test_generate_params_diff_modified(self):
        """Test modifying parameters."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        params1 = {"a": 1, "b": 2}
        params2 = {"a": 1, "b": 3}

        diff = service._generate_params_diff(params1, params2)

        assert len(diff["modified"]) == 1
        assert diff["modified"]["b"]["from"] == 2
        assert diff["modified"]["b"]["to"] == 3
        assert len(diff["unchanged"]) == 1

    def test_generate_params_diff_complex(self):
        """Test complex parameter diff."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()
        params1 = {"a": 1, "b": 2, "c": 3}
        params2 = {"a": 1, "b": 4, "d": 5}

        diff = service._generate_params_diff(params1, params2)

        assert len(diff["added"]) == 1  # d
        assert len(diff["removed"]) == 1  # c
        assert len(diff["modified"]) == 1  # b
        assert len(diff["unchanged"]) == 1  # a


class TestToResponse:
    """Test response conversion."""

    def test_to_response(self):
        """Test conversion to response."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        version = Mock()
        version.id = "ver_123"
        version.strategy_id = "strat_123"
        version.version_number = 1
        version.version_name = "v1.0.0"
        version.branch = "main"
        version.status = "stable"
        version.tags = ["production"]
        version.description = "Initial version"
        version.params = {"param1": 1}
        version.is_active = True
        version.is_default = True
        version.is_current = True
        version.parent_version_id = None
        version.created_at = datetime(2024, 1, 1, 12, 0, 0)
        version.updated_at = datetime(2024, 1, 1, 12, 0, 0)

        response = service._to_response(version)

        assert response["id"] == "ver_123"
        assert response["strategy_id"] == "strat_123"
        assert response["version_number"] == 1
        assert response["version_name"] == "v1.0.0"
        assert response["branch"] == "main"
        assert response["status"] == "stable"
        assert response["tags"] == ["production"]
        assert response["description"] == "Initial version"
        assert response["params"] == {"param1": 1}
        assert response["is_active"] is True
        assert response["is_default"] is True
        assert response["is_current"] is True
        assert response["parent_version_id"] is None


@pytest.mark.asyncio
class TestGetVersion:
    """Test getting version."""

    async def test_get_version_success(self):
        """Test successful version retrieval."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_version = Mock()
        mock_version.id = "ver_123"

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=mock_version)

        result = await service.get_version("ver_123")

        assert result is not None
        assert result.id == "ver_123"

    async def test_get_version_not_found(self):
        """Test getting non-existent version."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_version("nonexistent")

        assert result is None


@pytest.mark.asyncio
class TestSetVersionDefault:
    """Test setting default version."""

    async def test_set_version_default_success(self):
        """Test successful default version set."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_version = Mock()
        mock_version.id = "ver_123"
        mock_version.strategy_id = "strat_123"
        mock_version.branch = "main"
        mock_version.created_by = "user_123"

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=mock_version)
        service.version_repo.update = AsyncMock(return_value=mock_version)
        service.version_repo.list = AsyncMock(return_value=[])

        result = await service.set_version_default("ver_123", "user_123")

        assert result is True

    async def test_set_version_default_not_found(self):
        """Test setting non-existent version as default."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.set_version_default("nonexistent", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestActivateVersion:
    """Test activating version."""

    async def test_activate_version_success(self):
        """Test successful version activation."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_version = Mock()
        mock_version.id = "ver_123"
        mock_version.strategy_id = "strat_123"
        mock_version.branch = "main"
        mock_version.created_by = "user_123"

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=mock_version)
        service.version_repo.update = AsyncMock(return_value=mock_version)
        service.version_repo.list = AsyncMock(return_value=[])

        result = await service.activate_version("ver_123", "user_123")

        assert result is True

    async def test_activate_version_not_found(self):
        """Test activating non-existent version."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.activate_version("nonexistent", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestUpdateVersion:
    """Test updating version."""

    async def test_update_version_success(self):
        """Test successful version update."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_version = Mock()
        mock_version.id = "ver_123"
        mock_version.status = "draft"
        mock_version.created_by = "user_123"

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=mock_version)
        service.version_repo.update = AsyncMock(return_value=mock_version)

        update_data = Mock()
        update_data.code = "new code"
        update_data.params = None
        update_data.description = None
        update_data.tags = None
        update_data.status = None
        update_data.changelog = None

        # Mock ws_manager.send_to_task as async
        with patch('app.services.strategy_version_service.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            result = await service.update_version("ver_123", "user_123", update_data)

            assert result is not None

    async def test_update_version_not_found(self):
        """Test updating non-existent version."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        update_data = Mock()
        update_data.code = None
        update_data.params = None
        update_data.description = None
        update_data.tags = None
        update_data.status = None

        result = await service.update_version("nonexistent", "user_123", update_data)

        assert result is None


@pytest.mark.asyncio
class TestCompareVersions:
    """Test version comparison."""

    async def test_compare_versions_success(self):
        """Test successful version comparison."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_version1 = Mock()
        mock_version1.id = "ver_1"
        mock_version1.code = "code1"
        mock_version1.params = {"a": 1}
        mock_version1.version_name = "v1.0.0"
        mock_version1.created_by = "user_123"

        mock_version2 = Mock()
        mock_version2.id = "ver_2"
        mock_version2.code = "code2"
        mock_version2.params = {"a": 2}
        mock_version2.version_name = "v2.0.0"
        mock_version2.created_by = "user_123"

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(side_effect=[mock_version1, mock_version2])

        mock_comparison = Mock()
        mock_comparison.id = "comp_123"

        service.comparison_repo = AsyncMock()
        service.comparison_repo.create = AsyncMock(return_value=mock_comparison)

        result = await service.compare_versions(
            "user_123", "strat_123", "ver_1", "ver_2"
        )

        assert result is not None

    async def test_compare_versions_not_found(self):
        """Test comparing non-existent versions."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Version not found"):
            await service.compare_versions(
                "user_123", "strat_123", "nonexistent1", "nonexistent2"
            )


@pytest.mark.asyncio
class TestGetNextVersionNumber:
    """Test getting next version number."""

    async def test_get_next_version_number_new_branch(self):
        """Test version number for new branch."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.list = AsyncMock(return_value=[])

        result = await service._get_next_version_number("strat_123", "main")

        assert result == 1

    async def test_get_next_version_number_existing_branch(self):
        """Test version number for existing branch."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_version = Mock()
        mock_version.version_number = 5

        service.version_repo = AsyncMock()
        service.version_repo.list = AsyncMock(return_value=[mock_version])

        result = await service._get_next_version_number("strat_123", "main")

        assert result == 6


@pytest.mark.asyncio
class TestGetOrCreateBranch:
    """Test getting or creating branch."""

    async def test_get_existing_branch(self):
        """Test getting existing branch."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_branch = Mock()
        mock_branch.id = "branch_123"

        service.branch_repo = AsyncMock()
        service.branch_repo.list = AsyncMock(return_value=[mock_branch])

        result = await service._get_or_create_branch("strat_123", "user_123", "main")

        assert result.id == "branch_123"

    async def test_create_new_branch(self):
        """Test creating new branch."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_branch = Mock()
        mock_branch.id = "branch_123"

        service.branch_repo = AsyncMock()
        service.branch_repo.list = AsyncMock(return_value=[])
        service.branch_repo.create = AsyncMock(return_value=mock_branch)

        result = await service._get_or_create_branch("strat_123", "user_123", "feature")

        assert result is not None


@pytest.mark.asyncio
class TestRollbackVersion:
    """Test version rollback."""

    async def test_rollback_version_success(self):
        """Test successful version rollback."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        mock_target_version = Mock()
        mock_target_version.id = "target_ver"
        mock_target_version.code = "old code"
        mock_target_version.params = {"a": 1}
        mock_target_version.description = "old version"
        mock_target_version.version_name = "v1.0.0"
        mock_target_version.created_by = "user_123"
        mock_target_version.strategy_id = "strat_123"

        mock_current_version = Mock()
        mock_current_version.id = "current_ver"
        mock_current_version.code = "new code"
        mock_current_version.params = {"a": 2}
        mock_current_version.description = "new version"
        mock_current_version.created_by = "user_123"
        mock_current_version.strategy_id = "strat_123"

        mock_new_version = Mock()
        mock_new_version.id = "new_rollback_ver"

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=mock_target_version)
        service.version_repo.list = AsyncMock(return_value=[])
        service.version_repo.create = AsyncMock(return_value=mock_new_version)

        service.rollback_repo = AsyncMock()
        service.rollback_repo.create = AsyncMock()

        # Strategy ownership check used by rollback_version.
        mock_strategy = Mock()
        mock_strategy.id = "strat_123"
        mock_strategy.user_id = "user_123"
        service.strategy_repo = AsyncMock()
        service.strategy_repo.get_by_id = AsyncMock(return_value=mock_strategy)

        with patch.object(service, '_get_current_version', return_value=mock_current_version):
            with patch.object(service, '_get_next_version_number', return_value=3):
                with patch.object(service, '_unset_active_versions'):
                    result = await service.rollback_version(
                        "user_123", "strat_123", "target_ver", "Bug fix"
                    )

                    assert result is not None

    async def test_rollback_version_not_found(self):
        """Test rollback to non-existent version."""
        from app.services.strategy_version_service import VersionControlService

        service = VersionControlService()

        service.version_repo = AsyncMock()
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Target version not found"):
            await service.rollback_version(
                "user_123", "strat_123", "nonexistent", "test"
            )
