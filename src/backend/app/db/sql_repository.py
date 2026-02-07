"""
SQL数据库Repository实现 - 支持PostgreSQL/MySQL/SQLite
"""
from typing import TypeVar, Generic, List, Optional, Dict, Any, Type
from sqlalchemy import select, update, delete, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import BaseRepository
from app.db.database import async_session_maker

T = TypeVar('T')


class SQLRepository(BaseRepository[T], Generic[T]):
    """
    SQL数据库实现 - PostgreSQL/MySQL/SQLite共用
    
    使用SQLAlchemy 2.0异步接口
    """
    
    def __init__(self, model_class: Type[T]):
        self.model_class = model_class
    
    async def create(self, entity: T) -> T:
        """创建实体"""
        async with async_session_maker() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity
    
    async def get_by_id(self, id: str) -> Optional[T]:
        """根据ID获取实体"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(self.model_class).where(self.model_class.id == id)
            )
            return result.scalar_one_or_none()
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        """更新实体"""
        async with async_session_maker() as session:
            await session.execute(
                update(self.model_class)
                .where(self.model_class.id == id)
                .values(**data)
            )
            await session.commit()
            return await self.get_by_id(id)
    
    async def delete(self, id: str) -> bool:
        """删除实体"""
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
    ) -> List[T]:
        """列表查询，支持排序"""
        async with async_session_maker() as session:
            query = select(self.model_class)
            
            if filters:
                for key, value in filters.items():
                    if hasattr(self.model_class, key):
                        query = query.where(
                            getattr(self.model_class, key) == value
                        )
            
            if order_by and hasattr(self.model_class, order_by):
                col = getattr(self.model_class, order_by)
                query = query.order_by(desc(col) if order_desc else asc(col))
            
            query = query.offset(skip).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def count(self, filters: Dict[str, Any] = None) -> int:
        """计数"""
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
        """根据字段获取实体"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(self.model_class).where(
                    getattr(self.model_class, field) == value
                )
            )
            return result.scalar_one_or_none()
