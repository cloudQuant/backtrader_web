"""
权限控制依赖项测试

测试：
- has_permission 函数
- require_permission 装饰器
- require_any_permission 函数
- 常用权限检查依赖项
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


@pytest.mark.asyncio
class TestHasPermission:
    """测试 has_permission 函数"""

    def test_user_with_permission(self):
        """测试有权限的用户"""
        user = Mock(spec=User)
        admin_role = Mock(spec=Role)
        admin_role.role = Role.ADMIN
        user.roles = [admin_role]

        # 管理员应该有所有权限
        assert has_permission(user, Permission.CREATE_STRATEGY) is True
        assert has_permission(user, Permission.DELETE_STRATEGY) is True
        assert has_permission(user, Permission.MANAGE_USERS) is True

    def test_user_without_permission(self):
        """测试没有权限的用户"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        # 访客不应该有管理权限
        assert has_permission(user, Permission.MANAGE_USERS) is False
        assert has_permission(user, Permission.DELETE_STRATEGY) is False

    def test_user_with_multiple_roles(self):
        """测试有多重角色的用户"""
        user = Mock(spec=User)
        user_role = Mock(spec=Role)
        user_role.role = Role.USER
        premium_role = Mock(spec=Role)
        premium_role.role = Role.PREMIUM
        user.roles = [user_role, premium_role]

        # 应该有用户和高级用户的所有权限
        assert has_permission(user, Permission.CREATE_STRATEGY) is True
        assert has_permission(user, Permission.RUN_BACKTEST) is True
        assert has_permission(user, Permission.EXPORT_BACKTEST) is True

    def test_user_with_no_roles(self):
        """测试没有角色的用户"""
        user = Mock(spec=User)
        user.roles = []

        assert has_permission(user, Permission.CREATE_STRATEGY) is False


@pytest.mark.asyncio
class TestRequirePermission:
    """测试 require_permission 装饰器"""

    async def test_permission_granted(self):
        """测试有权限时通过"""
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
        """测试无权限时抛出异常"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_permission(Permission.MANAGE_USERS)
            with pytest.raises(HTTPException) as exc_info:
                await checker(user)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert exc_info.value.detail == "权限不足"


@pytest.mark.asyncio
class TestRequireAnyPermission:
    """测试 require_any_permission 函数"""

    async def test_has_one_required_permission(self):
        """测试有其中一个权限即可"""
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
        """测试没有任何权限时拒绝"""
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
            assert "权限不足" in exc_info.value.detail

    async def test_empty_permission_list(self):
        """测试空权限列表"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        with patch('app.api.deps_permissions.get_current_user', return_value=user):
            checker = require_any_permission()
            with pytest.raises(HTTPException) as exc_info:
                await checker(user)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
class TestPermissionDependencies:
    """测试预定义的权限依赖项"""

    def test_require_create_strategy_dependency(self):
        """测试创建策略依赖项"""
        assert RequireCreateStrategy is not None
        assert hasattr(RequireCreateStrategy, 'dependency')

    def test_require_update_strategy_dependency(self):
        """测试更新策略依赖项"""
        assert RequireUpdateStrategy is not None
        assert hasattr(RequireUpdateStrategy, 'dependency')

    def test_require_delete_strategy_dependency(self):
        """测试删除策略依赖项"""
        assert RequireDeleteStrategy is not None
        assert hasattr(RequireDeleteStrategy, 'dependency')

    def test_require_run_backtest_dependency(self):
        """测试运行回测依赖项"""
        assert RequireRunBacktest is not None
        assert hasattr(RequireRunBacktest, 'dependency')

    def test_require_export_backtest_dependency(self):
        """测试导出回测依赖项"""
        assert RequireExportBacktest is not None
        assert hasattr(RequireExportBacktest, 'dependency')

    def test_require_manage_users_dependency(self):
        """测试管理用户依赖项"""
        assert RequireManageUsers is not None
        assert hasattr(RequireManageUsers, 'dependency')


@pytest.mark.asyncio
class TestRolePermissionsIntegration:
    """测试角色权限集成"""

    def test_admin_role_has_all_permissions(self):
        """测试管理员角色有所有权限"""
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
        """测试普通用户角色权限"""
        user = Mock(spec=User)
        user_role = Mock(spec=Role)
        user_role.role = Role.USER
        user.roles = [user_role]

        # 用户角色应该有的权限（根据实际模型）
        assert has_permission(user, Permission.CREATE_STRATEGY) is True
        assert has_permission(user, Permission.READ_STRATEGY) is True
        assert has_permission(user, Permission.UPDATE_STRATEGY) is True
        assert has_permission(user, Permission.DELETE_STRATEGY) is True
        assert has_permission(user, Permission.RUN_BACKTEST) is True
        assert has_permission(user, Permission.READ_BACKTEST) is True
        assert has_permission(user, Permission.DELETE_BACKTEST) is True
        assert has_permission(user, Permission.READ_DATA) is True

        # 用户角色不应该有的权限
        assert has_permission(user, Permission.MANAGE_USERS) is False
        assert has_permission(user, Permission.MANAGE_ROLES) is False
        assert has_permission(user, Permission.EXPORT_BACKTEST) is False
        assert has_permission(user, Permission.SHARE_STRATEGY) is False
        assert has_permission(user, Permission.UPLOAD_DATA) is False
        assert has_permission(user, Permission.DELETE_DATA) is False

    def test_premium_role_permissions(self):
        """测试高级用户角色权限"""
        user = Mock(spec=User)
        premium_role = Mock(spec=Role)
        premium_role.role = Role.PREMIUM
        user.roles = [premium_role]

        # 高级用户应该有导出权限
        assert has_permission(user, Permission.EXPORT_BACKTEST) is True
        assert has_permission(user, Permission.CREATE_STRATEGY) is True

        # 高级用户不应该有管理用户权限
        assert has_permission(user, Permission.MANAGE_USERS) is False

    def test_guest_role_permissions(self):
        """测试访客角色权限"""
        user = Mock(spec=User)
        guest_role = Mock(spec=Role)
        guest_role.role = Role.GUEST
        user.roles = [guest_role]

        # 访客只有查看权限
        assert has_permission(user, Permission.CREATE_STRATEGY) is False
        assert has_permission(user, Permission.DELETE_STRATEGY) is False
        assert has_permission(user, Permission.MANAGE_USERS) is False
