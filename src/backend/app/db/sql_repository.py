"""
SQL database repository implementation for PostgreSQL, MySQL, and SQLite.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import asc, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaseRepository
from app.db.database import async_session_maker

T = TypeVar("T")


class BulkUpdateResult:
    """Result of a bulk update operation."""

    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class SQLRepository(BaseRepository[T], Generic[T]):
    """Generic async SQLAlchemy repository."""

    def __init__(self, model_class: Type[T], session: Optional[AsyncSession] = None):
        self.model_class = model_class
        self._external_session = session

    @property
    def _owns_session(self) -> bool:
        return self._external_session is None

    @asynccontextmanager
    async def _session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        if self._external_session is not None:
            yield self._external_session
            return

        async with async_session_maker() as session:
            yield session

    async def _finalize_write(self, session: AsyncSession) -> None:
        if self._owns_session:
            await session.commit()
        else:
            await session.flush()

    def _apply_filters(self, query, filters: Optional[Dict[str, Any]]):
        if not filters:
            return query

        for key, value in filters.items():
            if not hasattr(self.model_class, key):
                continue

            column = getattr(self.model_class, key)
            if isinstance(value, (list, tuple, set)):
                if value:
                    query = query.where(column.in_(value))
            elif value is None:
                query = query.where(column.is_(None))
            else:
                query = query.where(column == value)
        return query

    async def create(self, entity: T) -> T:
        async with self._session_scope() as session:
            session.add(entity)
            await self._finalize_write(session)
            await session.refresh(entity)
            return entity

    async def get_by_id(self, id: str) -> Optional[T]:
        async with self._session_scope() as session:
            result = await session.execute(
                select(self.model_class).where(self.model_class.id == id)
            )
            return result.scalar_one_or_none()

    async def update(self, id: str, data: Dict[str, Any], refresh: bool = True) -> Optional[T]:
        async with self._session_scope() as session:
            result = await session.execute(
                update(self.model_class).where(self.model_class.id == id).values(**data)
            )
            if not result.rowcount:
                if self._owns_session:
                    await session.rollback()
                return None

            await self._finalize_write(session)

            if not refresh:
                return None

            refreshed = await session.execute(
                select(self.model_class).where(self.model_class.id == id)
            )
            return refreshed.scalar_one_or_none()

    async def delete(self, id: str) -> bool:
        async with self._session_scope() as session:
            result = await session.execute(
                delete(self.model_class).where(self.model_class.id == id)
            )
            if not result.rowcount:
                if self._owns_session:
                    await session.rollback()
                return False

            await self._finalize_write(session)
            return True

    async def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> List[T]:
        if sort_by and not order_by:
            order_by = sort_by
        if sort_order:
            order_desc = sort_order.lower() == "desc"

        async with self._session_scope() as session:
            query = self._apply_filters(select(self.model_class), filters)

            if order_by and hasattr(self.model_class, order_by):
                column = getattr(self.model_class, order_by)
                query = query.order_by(desc(column) if order_desc else asc(column))

            result = await session.execute(query.offset(skip).limit(limit))
            return list(result.scalars().all())

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        async with self._session_scope() as session:
            query = self._apply_filters(
                select(func.count()).select_from(self.model_class),
                filters,
            )
            result = await session.execute(query)
            return result.scalar() or 0

    async def get_by_field(self, field: str, value: Any) -> Optional[T]:
        async with self._session_scope() as session:
            result = await session.execute(
                select(self.model_class).where(getattr(self.model_class, field) == value)
            )
            return result.scalar_one_or_none()

    async def exists(self, filters: Optional[Dict[str, Any]] = None) -> bool:
        """Check existence with LIMIT 1 for early exit (more efficient than full count)."""
        async with self._session_scope() as session:
            query = self._apply_filters(
                select(self.model_class.id).limit(1),
                filters,
            )
            result = await session.execute(query)
            return result.first() is not None

    async def bulk_create(self, entities: List[T]) -> List[T]:
        if not entities:
            return []

        async with self._session_scope() as session:
            session.add_all(entities)
            await self._finalize_write(session)
            for entity in entities:
                await session.refresh(entity)
            return entities

    async def bulk_update(self, ids: List[str], data: Dict[str, Any]) -> BulkUpdateResult:
        if not ids:
            return BulkUpdateResult(rowcount=0)

        async with self._session_scope() as session:
            result = await session.execute(
                update(self.model_class).where(self.model_class.id.in_(ids)).values(**data)
            )
            await self._finalize_write(session)
            return BulkUpdateResult(rowcount=result.rowcount or 0)

    async def bulk_delete(self, ids: List[str]) -> int:
        if not ids:
            return 0

        async with self._session_scope() as session:
            result = await session.execute(
                delete(self.model_class).where(self.model_class.id.in_(ids))
            )
            await self._finalize_write(session)
            return result.rowcount or 0

    async def get_by_fields(self, filters: Dict[str, Any], limit: int = 1) -> List[T]:
        async with self._session_scope() as session:
            query = self._apply_filters(select(self.model_class), filters).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())
