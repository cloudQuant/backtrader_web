"""
Permission model tests.
"""

from app.models.permission import ROLE_PERMISSIONS, Permission, Role


class TestPermission:
    """Permission enum tests."""

    def test_permission_values(self):
        """Test permission enum values."""
        assert Permission.CREATE_STRATEGY == "strategy:create"
        assert Permission.RUN_BACKTEST == "backtest:run"
        assert Permission.MANAGE_USERS == "admin:users"

    def test_all_permissions_are_strings(self):
        """Test all permissions are string values."""
        for p in Permission:
            assert isinstance(p.value, str)


class TestRole:
    """Role enum tests."""

    def test_role_values(self):
        """Test role enum values."""
        assert Role.GUEST == "guest"
        assert Role.USER == "user"
        assert Role.PREMIUM == "premium"
        assert Role.ADMIN == "admin"


class TestRolePermissions:
    """Role permissions mapping tests."""

    def test_guest_limited(self):
        """Test guest has limited permissions."""
        perms = ROLE_PERMISSIONS[Role.GUEST]
        assert Permission.READ_STRATEGY in perms
        assert Permission.CREATE_STRATEGY not in perms

    def test_user_has_crud(self):
        """Test user has CRUD permissions."""
        perms = ROLE_PERMISSIONS[Role.USER]
        assert Permission.CREATE_STRATEGY in perms
        assert Permission.RUN_BACKTEST in perms
        assert Permission.MANAGE_USERS not in perms

    def test_admin_has_all(self):
        """Test admin has all permissions."""
        perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.MANAGE_USERS in perms
        assert Permission.MANAGE_ROLES in perms
        assert len(perms) == len(Permission)

    def test_premium_has_export(self):
        """Test premium has export permissions."""
        perms = ROLE_PERMISSIONS[Role.PREMIUM]
        assert Permission.EXPORT_BACKTEST in perms
        assert Permission.SHARE_STRATEGY in perms
