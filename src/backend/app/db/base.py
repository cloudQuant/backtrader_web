"""
Repository base class - Unified CRUD interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Repository base class - Unified CRUD interface, all databases implement this interface.

    Supported databases:
    - SQLite/PostgreSQL/MySQL: SQLRepository
    - MongoDB: MongoRepository
    """

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create an entity.

        Args:
            entity: The entity to create.

        Returns:
            The created entity.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by ID.

        Args:
            id: The entity ID.

        Returns:
            The entity, or None if not found.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def update(self, id: str, entity: Dict[str, Any]) -> Optional[T]:
        """Update an entity.

        Args:
            id: The entity ID.
            entity: Dictionary of fields to update.

        Returns:
            The updated entity, or None if not found.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity.

        Args:
            id: The entity ID.

        Returns:
            True if deleted, False otherwise.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def list(
        self, filters: Dict[str, Any] = None, skip: int = 0, limit: int = 100
    ) -> List[T]:
        """List entities with optional filtering.

        Args:
            filters: Optional filter dictionary.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of entities.
        """
        pass  # pragma: no cover

    @abstractmethod
    async def count(self, filters: Dict[str, Any] = None) -> int:
        """Count entities with optional filtering.

        Args:
            filters: Optional filter dictionary.

        Returns:
            The count of matching entities.
        """
        pass  # pragma: no cover
