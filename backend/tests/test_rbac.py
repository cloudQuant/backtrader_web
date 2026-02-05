"""
RBAC 权限控制测试

测试基于角色的权限控制功能
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.permission import Permission, Role, ROLE_PERMISSIONS
from app.models.user import User
from app.db.database import Base, get_async_session
from app.api.deps_permissions import has_permission, require_permission, RequireCreateStrategy
from app.schemas.auth import RegisterRequest


@pytest.fixture
async def db_session():
    """创建测试数据库会话"""
    # 使用 SQLite 内存数据库
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()


@pytest.fixture
def test_user_with_roles():
    """创建测试用户和角色"""
    return User(
        id="test-user-1",
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
    )


class TestPermissionEnum:
    """测试权限枚举"""

    def test_permission_values(self):
        """测试权限枚举值"""
        # 策略权限
        assert Permission.CREATE_STRATEGY.value == "strategy:create"
        assert Permission.UPDATE_STRATEGY.value == "strategy:update"
        assert Permission.DELETE_STRATEGY.value == "strategy:delete"

        # 回测权限
        assert Permission.RUN_BACKTEST.value == "backtest:run"
        assert Permission.EXPORT_BACKTEST.value == "backtest:export"

        # 管理权限
        assert Permission.MANAGE_USERS.value == "admin:users"


class TestRoleEnum:
    """测试角色枚举"""

    def test_role_values(self):
        """测试角色枚举值"""
        assert Role.GUEST.value == "guest"
        assert Role.USER.value == "user"
        assert Role.PREMIUM.value == "premium"
        assert Role.ADMIN.value == "admin"


class TestRolePermissions:
    """测试角色权限映射"""

    def test_guest_permissions(self):
        """测试 Guest 角色权限"""
        permissions = ROLE_PERMISSIONS[Role.GUEST]

        assert Permission.READ_STRATEGY in permissions
        assert Permission.READ_BACKTEST in permissions

        # Guest 不应该有写权限
        assert Permission.CREATE_STRATEGY not in permissions
        assert Permission.RUN_BACKTEST not in permissions

    def test_user_permissions(self):
        """测试 User 角色权限"""
        permissions = ROLE_PERMISSIONS[Role.USER]

        assert Permission.CREATE_STRATEGY in permissions
        assert Permission.RUN_BACKTEST in permissions
        assert Permission.DELETE_STRATEGY in permissions

        # User 不应该有分享和导出权限
        assert Permission.SHARE_STRATEGY not in permissions
        assert Permission.EXPORT_BACKTEST not in permissions

    def test_premium_permissions(self):
        """测试 Premium 角色权限"""
        permissions = ROLE_PERMISSIONS[Role.PREMIUM]

        assert Permission.SHARE_STRATEGY in permissions
        assert Permission.EXPORT_BACKTEST in permissions
        assert Permission.UPLOAD_DATA in permissions

    def test_admin_permissions(self):
        """测试 Admin 角色权限"""
        permissions = ROLE_PERMISSIONS[Role.ADMIN]

        assert Permission.MANAGE_USERS in permissions
        assert Permission.MANAGE_ROLES in permissions
        assert Permission.DELETE_DATA in permissions

    def test_role_hierarchy(self):
        """测试角色权限层次"""
        guest_perms = set(ROLE_PERMISSIONS[Role.GUEST])
        user_perms = set(ROLE_PERMISSIONS[Role.USER])
        premium_perms = set(ROLE_PERMISSIONS[Role.PREMIUM])
        admin_perms = set(ROLE_PERMISSIONS[Role.ADMIN])

        # 权限应该随着角色增加
        assert guest_perms.issubset(user_perms)
        assert user_perms.issubset(premium_perms)
        assert premium_perms.issubset(admin_perms)


class TestHasPermission:
    """测试权限检查函数"""

    def test_user_has_permission(self, db_session):
        """测试用户拥有权限"""
        # 创建用户
        user = User(
            id="test-user-2",
            username="testuser",
            email="test2@example.com",
            hashed_password="hashed",
        )
        db_session.add(user)
        db_session.commit()

        # 手动添加角色（临时）
        user.roles = [Role.USER]

        # 检查 USER 角色的权限
        assert has_permission(user, Permission.CREATE_STRATEGY)
        assert has_permission(user, Permission.RUN_BACKTEST)

        # 检查 USER 角色不拥有的权限
        assert not has_permission(user, Permission.SHARE_STRATEGY)
        assert not has_permission(user, Permission.EXPORT_BACKTEST)

    def test_guest_has_limited_permissions(self, db_session):
        """测试 Guest 用户只有有限权限"""
        user = User(
            id="test-user-3",
            username="guestuser",
            email="guest@example.com",
            hashed_password="hashed",
        )
        db_session.add(user)
        db_session.commit()

        # 添加 Guest 角色
        user.roles = [Role.GUEST]

        # Guest 只有读权限
        assert has_permission(user, Permission.READ_STRATEGY)
        assert has_permission(user, Permission.READ_BACKTEST)

        # Guest 没有写权限
        assert not has_permission(user, Permission.CREATE_STRATEGY)
        assert not has_permission(user, Permission.RUN_BACKTEST)


@pytest.mark.asyncio
class TestRequirePermissionDep:
    """测试权限检查依赖项"""

    async def test_require_permission_granted(self):
        """测试有权限时通过"""
        # Mock 用户有权限
        user = User(
            id="test-user-4",
            username="testuser",
            email="test4@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.USER]

        # 创建依赖项
        dep = require_permission(Permission.CREATE_STRATEGY)

        # 模拟依赖项调用
        result = await dep(user)

        assert result == user

    async def test_require_permission_denied(self):
        """测试无权限时抛出异常"""
        # Mock 用户没有权限
        user = User(
            id="test-user-5",
            username="guestuser",
            email="guest2@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.GUEST]

        # 创建依赖项
        dep = require_permission(Permission.CREATE_STRATEGY)

        # 应该抛出 403 错误
        with pytest.raises(HTTPException) as exc_info:
            await dep(user)

        assert exc_info.value.status_code == 403
        assert "权限不足" in str(exc_info.value.detail)


class TestConveniencePermissionDeps:
    """测试便捷权限依赖项"""

    async def test_require_create_strategy(self):
        """测试创建策略权限依赖项"""
        user = User(
            id="test-user-6",
            username="testuser",
            email="test6@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.USER]

        dep = RequireCreateStrategy
        result = await dep(user)

        assert result == user

    async def test_require_create_strategy_denied_for_guest(self):
        """测试 Guest 用户不能创建策略"""
        user = User(
            id="test-user-7",
            username="guestuser",
            email="guest3@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.GUEST]

        dep = RequireCreateStrategy

        with pytest.raises(HTTPException) as exc_info:
            await dep(user)

        assert exc_info.value.status_code == 403

    async def test_require_export_backtest(self):
        """测试导出回测权限依赖项"""
        # Premium 用户可以导出
        user = User(
            id="test-user-8",
            username="premiumuser",
            email="premium@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.PREMIUM]

        dep = RequireExportBacktest
        result = await dep(user)

        assert result == user

    async def test_require_export_backtest_denied_for_user(self):
        """测试普通用户不能导出回测"""
        # 普通用户不能导出
        user = User(
            id="test-user-9",
            username="normaluser",
            email="normal@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.USER]

        dep = RequireExportBacktest

        with pytest.raises(HTTPException) as exc_info:
            await dep(user)

        assert exc_info.value.status_code == 403


class TestRequireAnyPermission:
    """测试需要任意一个权限"""

    async def test_require_any_permission_has_one(self):
        """测试拥有所需权限中的任意一个"""
        user = User(
            id="test-user-10",
            username="testuser",
            email="test10@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.USER]  # 有 CREATE_STRATEGY 权限

        # 测试需要 CREATE_STRATEGY 或 DELETE_STRATEGY
        from app.api.deps_permissions import require_any_permission

        dep = require_any_permission(Permission.CREATE_STRATEGY, Permission.DELETE_STRATEGY)
        result = await dep(user)

        assert result == user

    async def test_require_any_permission_has_none(self):
        """测试没有所需权限中的任意一个"""
        user = User(
            id="test-user-11",
            username="guestuser",
            email="guest4@example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.GUEST]  # 没有 CREATE_STRATEGY 也没有 DELETE_STRATEGY

        # 测试需要 CREATE_STRATEGY 或 DELETE_STRATEGY
        from app.api.deps_permissions import require_any_permission

        dep = require_any_permission(Permission.CREATE_STRATEGY, Permission.DELETE_STRATEGY)

        with pytest.raises(HTTPException) as exc_info:
            await dep(user)

        assert exc_info.value.status_code == 403
        assert "权限不足" in str(exc_info.value.detail)
