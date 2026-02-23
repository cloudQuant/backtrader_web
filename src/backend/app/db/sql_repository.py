"""
SQL database Repository implementation - Supports PostgreSQL/MySQL/SQLite.
"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import asc, delete, desc, func, select, update

from app.db.base import BaseRepository
from app.db.database import async_session_maker

T = TypeVar('T')


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

    async def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        """Update an entity.

        Args:
            id: The entity ID.
            data: Dictionary of fields to update.

        Returns:
            The updated entity, or None if not found.
        """
        async with async_session_maker() as session:
            await session.execute(
                update(self.model_class)
                .where(self.model_class.id == id)
                .values(**data)
            )
            await session.commit()
            return await self.get_by_id(id)

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

        Returns:
            The count of matching entities.
        """
        async with async_session_maker() as session:
            query = select(func.count()).select_from(self.model_class)

            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        query = query.where(
                            getattr(self.model_class, key) == value
                        )

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
