"""
Database factory - Create Repository based on environment variables.
"""

from typing import TypeVar

from app.config import get_settings
from app.db.base import BaseRepository
from app.db.cache import get_cache
from app.db.sql_repository import SQLRepository

T = TypeVar("T")


def get_repository(model_class: type[T]) -> BaseRepository[T]:
    """Get Repository instance.

    Automatically selects implementation based on DATABASE_TYPE environment variable:
    - postgresql/mysql/sqlite: SQLRepository
    - mongodb: Planned feature (not yet implemented)

    Note: MongoDB support is planned for a future release. Currently, only
    SQLite, PostgreSQL, and MySQL are supported. See config.py for the
    list of supported database types.

    Usage:
        from app.db import get_repository
        from app.models import User

        user_repo = get_repository(User)
        user = await user_repo.get_by_id("123")

    Args:
        model_class: The model class.

    Returns:
        A repository instance for the model.

    Raises:
        NotImplementedError: If MongoDB is requested (planned feature, not yet implemented).
        ValueError: If an unsupported database type is specified.
    """
    settings = get_settings()
    db_type = settings.DATABASE_TYPE

    if db_type in ("postgresql", "mysql", "sqlite"):
        return SQLRepository(model_class)
    elif db_type == "mongodb":
        # MongoDB implementation is planned for a future release
        # Currently, config.py validator will reject mongodb, so this branch
        # is unreachable via normal configuration. Kept for future compatibility.
        raise NotImplementedError(
            "MongoDB support is planned for a future release. "
            "Currently supported: sqlite, postgresql, mysql"
        )
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


__all__ = ["get_repository", "get_cache"]
