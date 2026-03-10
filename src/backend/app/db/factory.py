"""
Database factory - Create Repository based on environment variables.
"""

from typing import Type, TypeVar

from app.config import get_settings
from app.db.base import BaseRepository
from app.db.cache import get_cache
from app.db.sql_repository import SQLRepository

T = TypeVar("T")


def get_repository(model_class: Type[T]) -> BaseRepository[T]:
    """Get Repository instance.

    Automatically selects implementation based on DATABASE_TYPE environment variable:
    - postgresql/mysql/sqlite: SQLRepository
    - mongodb: MongoRepository (to be implemented)

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
        NotImplementedError: If MongoDB is requested (not yet implemented).
        ValueError: If an unsupported database type is specified.
    """
    settings = get_settings()
    db_type = settings.DATABASE_TYPE

    if db_type in ("postgresql", "mysql", "sqlite"):
        return SQLRepository(model_class)
    elif db_type == "mongodb":
        # MongoDB implementation to be added
        raise NotImplementedError("MongoDB support coming soon")
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


__all__ = ["get_repository", "get_cache"]
