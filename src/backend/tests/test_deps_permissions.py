"""
Permission control dependency tests

Tests:
- has_permission function
- require_permission decorator
- require_any_permission function
- Common permission check dependencies
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi import HTTPException, status

from app.api.deps_permissions import (
    has_permission,
    require_permission,
    require_any_permission,
    RequireCreateStrategy,
    RequireUpdateStrategy,
    RequireDeleteStrategy,
    RequireRunBacktest,
    RequireExportBacktest,
    RequireManageUsers,
)
from app.models.permission import Permission, Role, ROLE_PERMISSIONS
from app.models.user import User


class TestHasPermission:
    """Test has_permission function"""

    def test_user_with_permission(self):
        """Test user with permission"""
        user = Mock(spec=User)
        admin_role = Mock(spec=Role)
        admin_role.role = Role.ADMIN
        user.roles = [admin_role]

        # Admin should have all permissions
        assert has_permission(user, Permission.CREATE_STRATEGY) is True
        assert has_permission(user, Permission.DELETE_STRATEGY) is True
        assert has_permission(user, Permission.MANAGE_USERS) is True

    def test_user_without_permission(self):
        """Test user without permission"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        # Guest should not have admin permissions
        assert has_permission(user, Permission.MANAGE_USERS) is False
        assert has_permission(user, Permission.DELETE_STRATEGY) is False

    def test_user_with_multiple_roles(self):
        """Test user with multiple roles"""
        user = Mock(spec=User)
        user_role = Mock(spec=Role)
        user_role.role = Role.USER
        premium_role = Mock(spec=Role)
        premium_role.role = Role.PREMIUM
        user.roles = [user_role, premium_role]

        # Should have all user and premium user permissions
        assert has_permission(user, Permission.CREATE_STRATEGY) is True
        assert has_permission(user, Permission.RUN_BACKTEST) is True
        assert has_permission(user, Permission.EXPORT_BACKTEST) is True

    def test_user_with_no_roles(self):
        """Test user with no roles"""
        user = Mock(spec=User)
        user.roles = []

        assert has_permission(user, Permission.CREATE_STRATEGY) is False


@pytest.mark.asyncio
class TestRequirePermission:
    """Test require_permission decorator"""

    async def test_permission_granted(self):
        """Test permission granted passes"""
        user = Mock(spec=User)
        admin_role = Mock(spec=Role)
        admin_role.role = Role.ADMIN
        user.roles = [admin_role]

        # Mock get_current_user
        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_permission(Permission.MANAGE_USERS)
            result = await checker(user)
            assert result is user

    async def test_permission_denied(self):
        """Test permission denied raises exception"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_permission(Permission.MANAGE_USERS)
            with pytest.raises(HTTPException) as exc_info:
                await checker(user)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert exc_info.value.detail == "Insufficient permissions"


@pytest.mark.asyncio
class TestRequireAnyPermission:
    """Test require_any_permission function"""

    async def test_has_one_required_permission(self):
        """Test having one of the required permissions is enough"""
        user = Mock(spec=User)
        user_role = Mock(spec=Role)
        user_role.role = Role.USER
        user.roles = [user_role]

        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_any_permission(
                Permission.CREATE_STRATEGY,
                Permission.MANAGE_USERS
            )
            result = await checker(user)
            assert result is user

    async def test_has_none_required_permission(self):
        """Test having none of the required permissions is denied"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_any_permission(
                Permission.MANAGE_USERS,
                Permission.DELETE_STRATEGY
            )
            with pytest.raises(HTTPException) as exc_info:
                await checker(user)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Insufficient permissions" in exc_info.value.detail

    async def test_empty_permission_list(self):
        """Test empty permission list"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_any_permission()
            with pytest.raises(HTTPException) as exc_info:
                await checker(user)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestPermissionDependencies:
    """Test predefined permission dependencies"""

    def test_require_create_strategy_dependency(self):
        """Test create strategy dependency"""
        assert RequireCreateStrategy is not None
        assert hasattr(RequireCreateStrategy, 'dependency')

    def test_require_update_strategy_dependency(self):
        """Test update strategy dependency"""
        assert RequireUpdateStrategy is not None
        assert hasattr(RequireUpdateStrategy, 'dependency')

    def test_require_delete_strategy_dependency(self):
        """Test delete strategy dependency"""
        assert RequireDeleteStrategy is not None
        assert hasattr(RequireDeleteStrategy, 'dependency')

    def test_require_run_backtest_dependency(self):
        """Test run backtest dependency"""
        assert RequireRunBacktest is not None
        assert hasattr(RequireRunBacktest, 'dependency')

    def test_require_export_backtest_dependency(self):
        """Test export backtest dependency"""
        assert RequireExportBacktest is not None
        assert hasattr(RequireExportBacktest, 'dependency')

    def test_require_manage_users_dependency(self):
        """Test manage users dependency"""
        assert RequireManageUsers is not None
        assert hasattr(RequireManageUsers, 'dependency')


class TestRolePermissionsIntegration:
    """Test role permissions integration"""

    def test_admin_role_has_all_permissions(self):
        """Test admin role has all permissions"""
        all_permissions = [
            Permission.CREATE_STRATEGY,
            Permission.UPDATE_STRATEGY,
            Permission.DELETE_STRATEGY,
            Permission.RUN_BACKTEST,
            Permission.EXPORT_BACKTEST,
            Permission.MANAGE_USERS,
        ]

        user = Mock(spec=User)
        admin_role = Mock(spec=Role)
        admin_role.role = Role.ADMIN
        user.roles = [admin_role]

        for permission in all_permissions:
            assert has_permission(user, permission), f"Admin should have {permission}"

    def test_user_role_permissions(self):
        """Test regular user role permissions"""
        user = Mock(spec=User)
        user_role = Mock(spec=Role)
        user_role.role = Role.USER
        user.roles = [user_role]

        # Permissions user role should have (based on actual model)
        assert has_permission(user, Permission.CREATE_STRATEGY) is True
        assert has_permission(user, Permission.READ_STRATEGY) is True
        assert has_permission(user, Permission.UPDATE_STRATEGY) is True
        assert has_permission(user, Permission.DELETE_STRATEGY) is True
        assert has_permission(user, Permission.RUN_BACKTEST) is True
        assert has_permission(user, Permission.READ_BACKTEST) is True
        assert has_permission(user, Permission.DELETE_BACKTEST) is True
        assert has_permission(user, Permission.READ_DATA) is True

        # Permissions user role should not have
        assert has_permission(user, Permission.MANAGE_USERS) is False
        assert has_permission(user, Permission.MANAGE_ROLES) is False
        assert has_permission(user, Permission.EXPORT_BACKTEST) is False
        assert has_permission(user, Permission.SHARE_STRATEGY) is False
        assert has_permission(user, Permission.UPLOAD_DATA) is False
        assert has_permission(user, Permission.DELETE_DATA) is False

    def test_premium_role_permissions(self):
        """Test premium user role permissions"""
        user = Mock(spec=User)
        premium_role = Mock(spec=Role)
        premium_role.role = Role.PREMIUM
        user.roles = [premium_role]

        # Premium users should have export permission
        assert has_permission(user, Permission.EXPORT_BACKTEST) is True
        assert has_permission(user, Permission.CREATE_STRATEGY) is True

        # Premium users should not have manage users permission
        assert has_permission(user, Permission.MANAGE_USERS) is False

    def test_guest_role_permissions(self):
        """Test guest role permissions"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        # Guest only has read permission
        assert has_permission(user, Permission.CREATE_STRATEGY) is False
        assert has_permission(user, Permission.DELETE_STRATEGY) is False
        assert has_permission(user, Permission.MANAGE_USERS) is False
