from app.api._dependencies import (
    RequireCreateStrategy,
    RequireDeleteStrategy,
    RequireExportBacktest,
    RequireManageUsers,
    RequireRunBacktest,
    RequireUpdateStrategy,
    has_permission,
    require_any_permission,
    require_permission,
)


def get_current_user():
    from app.api.deps import get_current_user as _real_get_current_user

    return _real_get_current_user()


__all__ = [
    "RequireCreateStrategy",
    "RequireDeleteStrategy",
    "RequireExportBacktest",
    "RequireManageUsers",
    "RequireRunBacktest",
    "RequireUpdateStrategy",
    "get_current_user",
    "has_permission",
    "require_any_permission",
    "require_permission",
]
