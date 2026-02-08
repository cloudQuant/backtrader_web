"""
权限模型测试
"""
from app.models.permission import Permission, Role, ROLE_PERMISSIONS


class TestPermission:
    def test_permission_values(self):
        assert Permission.CREATE_STRATEGY == "strategy:create"
        assert Permission.RUN_BACKTEST == "backtest:run"
        assert Permission.MANAGE_USERS == "admin:users"

    def test_all_permissions_are_strings(self):
        for p in Permission:
            assert isinstance(p.value, str)


class TestRole:
    def test_role_values(self):
        assert Role.GUEST == "guest"
        assert Role.USER == "user"
        assert Role.PREMIUM == "premium"
        assert Role.ADMIN == "admin"


class TestRolePermissions:
    def test_guest_limited(self):
        perms = ROLE_PERMISSIONS[Role.GUEST]
        assert Permission.READ_STRATEGY in perms
        assert Permission.CREATE_STRATEGY not in perms

    def test_user_has_crud(self):
        perms = ROLE_PERMISSIONS[Role.USER]
        assert Permission.CREATE_STRATEGY in perms
        assert Permission.RUN_BACKTEST in perms
        assert Permission.MANAGE_USERS not in perms

    def test_admin_has_all(self):
        perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.MANAGE_USERS in perms
        assert Permission.MANAGE_ROLES in perms
        assert len(perms) == len(Permission)

    def test_premium_has_export(self):
        perms = ROLE_PERMISSIONS[Role.PREMIUM]
        assert Permission.EXPORT_BACKTEST in perms
        assert Permission.SHARE_STRATEGY in perms
