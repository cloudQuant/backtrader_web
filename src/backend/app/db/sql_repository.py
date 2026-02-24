"""
SQL database Repository implementation - Supports PostgreSQL/MySQL/SQLite.
"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import asc, delete, desc, func, select, update

from app.db.base import BaseRepository
from app.db.database import async_session_maker

T = TypeVar('T')


class BulkUpdateResult:
    """Result of a bulk update operation.

    Attributes:
        rowcount: Number of rows updated.
    """

    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class SQLRepository(BaseRepository[T], Generic[T]):
    """SQL database implementation - Shared by PostgreSQL/MySQL/SQLite.

    Uses SQLAlchemy 2.0 async interface.

    Attributes:
        model_class: The model class this repository handles.
    """

    def __init__(self, model_class: Type[T]):
        """Initialize the repository.

        Args:
            model_class: The model class to manage.
        """
        self.model_class = model_class

    async def create(self, entity: T) -> T:
        """Create an entity.

        Args:
            entity: The entity to create.

        Returns:
            The created entity.
        """
        async with async_session_maker() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity

    async def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by ID.

        Args:
            id: The entity ID.

        Returns:
            The entity, or None if not found.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(self.model_class).where(self.model_class.id == id)
            )
            return result.scalar_one_or_none()

    async def update(
        self,
        id: str,
        data: Dict[str, Any],
        refresh: bool = True
    ) -> Optional[T]:
        """Update an entity.

        Args:
            id: The entity ID.
            data: Dictionary of fields to update.
            refresh: Whether to fetch and return the updated entity.
                     Set to False for better performance when the return value is not needed.

        Returns:
            The updated entity if refresh=True, None otherwise or if not found.
        """
        async with async_session_maker() as session:
            await session.execute(
                update(self.model_class)
                .where(self.model_class.id == id)
                .values(**data)
            )
            await session.commit()

            if refresh:
                return await self.get_by_id(id)
            return None

    async def delete(self, id: str) -> bool:
        """Delete an entity.

        Args:
            id: The entity ID.

        Returns:
            True if deleted, False otherwise.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                delete(self.model_class).where(self.model_class.id == id)
            )
            await session.commit()
            return result.rowcount > 0

    async def list(
        self,
        filters: Dict[str, Any] = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str = None,
        order_desc: bool = True,
        sort_by: str = None,
        sort_order: str = None,
    ) -> List[T]:
        """List entities with optional filtering and sorting.

        Supports sort_by/sort_order alias for compatibility.

        Supported filter types:
        - Regular value: field == value
        - List value: field.in_(values)  # IN query
        - None value: field.is_(None)     # IS NULL query

        Args:
            filters: Optional filter dictionary.
            skip: Number of records to skip.
            limit: Maximum number of records to return.
            order_by: Field to order by.
            order_desc: Whether to order descending.
            sort_by: Alias for order_by.
            sort_order: "asc" or "desc".

        Returns:
            List of entities.
        """
        # Alias compatibility
        if sort_by and not order_by:
            order_by = sort_by
        if sort_order is not None and sort_order != "":
            order_desc = sort_order.lower() == "desc"

        async with async_session_maker() as session:
            query = select(self.model_class)

            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        col = getattr(self.model_class, key)
                        # Support IN query: if value is list/tuple/set
                        if isinstance(value, (list, tuple, set)):
                            if value:  # Only add condition if non-empty
                                query = query.where(col.in_(value))
                        elif value is None:
                            query = query.where(col.is_(None))
                        else:
                            query = query.where(col == value)

            if order_by and hasattr(self.model_class, order_by):
                col = getattr(self.model_class, order_by)
                query = query.order_by(desc(col) if order_desc else asc(col))

            query = query.offset(skip).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def count(self, filters: Dict[str, Any] = None) -> int:
        """Count entities with optional filtering.

        Args:
            filters: Optional filter dictionary.
                     Supports IN queries when value is a list/tuple/set.
                     Supports IS NULL queries when value is None.

        Returns:
            The count of matching entities.
        """
        async with async_session_maker() as session:
            query = select(func.count()).select_from(self.model_class)

            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        col = getattr(self.model_class, key)
                        # Support IN query: if value is list/tuple/set
                        if isinstance(value, (list, tuple, set)):
                            if value:  # Only add condition if non-empty
                                query = query.where(col.in_(value))
                        elif value is None:
                            query = query.where(col.is_(None))
                        else:
                            query = query.where(col == value)

            result = await session.execute(query)
            return result.scalar() or 0

    async def get_by_field(self, field: str, value: Any) -> Optional[T]:
        """Get entity by field value.

        Args:
            field: The field name.
            value: The field value.

        Returns:
            The entity, or None if not found.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(self.model_class).where(
                    getattr(self.model_class, field) == value
                )
            )
            return result.scalar_one_or_none()

    async def exists(self, filters: Dict[str, Any] = None) -> bool:
        """Check if any entity matches the given filters.

        More efficient than count() when you only need to know if records exist.

        Args:
            filters: Optional filter dictionary.
                     Supports IN queries when value is a list/tuple/set.

        Returns:
            True if at least one matching entity exists, False otherwise.
        """
        async with async_session_maker() as session:
            query = select(func.count()).select_from(self.model_class)

            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        col = getattr(self.model_class, key)
                        if isinstance(value, (list, tuple, set)):
                            if value:
                                query = query.where(col.in_(value))
                        elif value is None:
                            query = query.where(col.is_(None))
                        else:
                            query = query.where(col == value)

            # Use limit(1) for optimization - database stops counting after finding first row
            result = await session.execute(query.limit(1))
            return (result.scalar() or 0) > 0

    async def bulk_create(self, entities: List[T]) -> List[T]:
        """Create multiple entities in a single transaction.

        More efficient than creating entities one by one.

        Args:
            entities: List of entities to create.

        Returns:
            List of created entities.
        """
        if not entities:
            return []

        async with async_session_maker() as session:
            session.add_all(entities)
            await session.commit()
            # Refresh all entities to get generated IDs
            for entity in entities:
                await session.refresh(entity)
            return entities

    async def bulk_update(
        self,
        ids: List[str],
        data: Dict[str, Any]
    ) -> BulkUpdateResult:
        """Update multiple entities with the same data in a single query.

        Args:
            ids: List of entity IDs to update.
            data: Dictionary of fields to update (same for all entities).

        Returns:
            BulkUpdateResult with the number of rows updated.
        """
        if not ids:
            return BulkUpdateResult(rowcount=0)

        async with async_session_maker() as session:
            result = await session.execute(
                update(self.model_class)
                .where(self.model_class.id.in_(ids))
                .values(**data)
            )
            await session.commit()
            return BulkUpdateResult(rowcount=result.rowcount)

    async def bulk_delete(self, ids: List[str]) -> int:
        """Delete multiple entities in a single query.

        Args:
            ids: List of entity IDs to delete.

        Returns:
            Number of rows deleted.
        """
        if not ids:
            return 0

        async with async_session_maker() as session:
            result = await session.execute(
                delete(self.model_class).where(self.model_class.id.in_(ids))
            )
            await session.commit()
            return result.rowcount

    async def get_by_fields(
        self,
        filters: Dict[str, Any],
        limit: int = 1
    ) -> List[T]:
        """Get entities by multiple field values.

        Args:
            filters: Dictionary of field=value conditions.
            limit: Maximum number of results to return. Defaults to 1.

        Returns:
            List of matching entities.
        """
        async with async_session_maker() as session:
            query = select(self.model_class)

            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    col = getattr(self.model_class, key)
                    if isinstance(value, (list, tuple, set)):
                        if value:
                            query = query.where(col.in_(value))
                    elif value is None:
                        query = query.where(col.is_(None))
                    else:
                        query = query.where(col == value)

            query = query.limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())
