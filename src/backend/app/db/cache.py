"""
缓存层 - Redis可选，不配置则使用内存缓存
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from app.config import get_settings


class MemoryCache:
    """
    内存缓存 - 默认实现，无需Redis
    
    适用于单机部署或开发环境
    """
    _cache: Dict[str, Dict[str, Any]] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        if entry.get("expire_at") and datetime.now() > entry["expire_at"]:
            del self._cache[key]
            return None
        
        return entry["value"]
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """设置缓存"""
        expire_at = datetime.now() + timedelta(seconds=ttl) if ttl > 0 else None
        self._cache[key] = {
            "value": value,
            "expire_at": expire_at,
        }
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return await self.get(key) is not None
    
    async def clear(self):
        """清空缓存"""
        self._cache.clear()


class RedisCache:
    """
    Redis缓存 - 可选，配置REDIS_URL后启用
    
    适用于分布式部署
    """
    def __init__(self, url: str):
        import redis.asyncio as redis
        self.redis = redis.from_url(url, decode_responses=True)
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """设置缓存"""
        data = json.dumps(value, default=str)
        if ttl > 0:
            await self.redis.setex(key, ttl, data)
        else:
            await self.redis.set(key, data)
    
    async def delete(self, key: str) -> bool:
        """删除缓存"""
        return await self.redis.delete(key) > 0
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return await self.redis.exists(key) > 0


# 缓存单例
_cache_instance = None


def get_cache():
    """获取缓存实例 - 有Redis用Redis，否则用内存"""
    global _cache_instance
    
    if _cache_instance is None:
        settings = get_settings()
        if settings.REDIS_URL:
            _cache_instance = RedisCache(settings.REDIS_URL)
        else:
            _cache_instance = MemoryCache()
    
    return _cache_instance
