"""
数据库工厂 - 根据环境变量创建Repository
"""
from typing import Type, TypeVar

from app.config import get_settings
from app.db.base import BaseRepository
from app.db.sql_repository import SQLRepository
from app.db.cache import get_cache, MemoryCache, RedisCache

T = TypeVar('T')


def get_repository(model_class: Type[T]) -> BaseRepository[T]:
    """
    获取Repository实例
    
    根据DATABASE_TYPE环境变量自动选择实现:
    - postgresql/mysql/sqlite: SQLRepository
    - mongodb: MongoRepository (待实现)
    
    使用方法:
        from app.db import get_repository
        from app.models import User
        
        user_repo = get_repository(User)
        user = await user_repo.get_by_id("123")
    """
    settings = get_settings()
    db_type = settings.DATABASE_TYPE
    
    if db_type in ("postgresql", "mysql", "sqlite"):
        return SQLRepository(model_class)
    elif db_type == "mongodb":
        # MongoDB实现待添加
        raise NotImplementedError("MongoDB支持即将推出")
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


__all__ = ["get_repository", "get_cache"]
