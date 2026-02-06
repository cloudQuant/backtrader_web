"""
Repository基类 - 统一CRUD接口
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Dict, Any
from pydantic import BaseModel

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Repository基类 - 统一CRUD接口，所有数据库实现此接口
    
    支持的数据库:
    - SQLite/PostgreSQL/MySQL: SQLRepository
    - MongoDB: MongoRepository
    """
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """创建实体"""
        pass
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """根据ID获取实体"""
        pass
    
    @abstractmethod
    async def update(self, id: str, entity: Dict[str, Any]) -> Optional[T]:
        """更新实体"""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """删除实体"""
        pass
    
    @abstractmethod
    async def list(
        self,
        filters: Dict[str, Any] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[T]:
        """列表查询"""
        pass
    
    @abstractmethod
    async def count(self, filters: Dict[str, Any] = None) -> int:
        """计数"""
        pass
