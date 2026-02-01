"""
配置管理 - 从环境变量读取配置
"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    APP_NAME: str = "backtrader_web"
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-change-in-production"
    
    # 数据库配置
    DATABASE_TYPE: str = "sqlite"  # postgresql, mysql, mongodb, sqlite
    DATABASE_URL: str = "sqlite+aiosqlite:///./backtrader.db"
    
    # 可选: 文档数据库
    DOCUMENT_DB_TYPE: Optional[str] = None
    DOCUMENT_DB_URL: Optional[str] = None
    
    # 可选: 时序数据库
    TIMESERIES_DB_TYPE: Optional[str] = None
    TIMESERIES_DB_URL: Optional[str] = None
    
    # 可选: Redis缓存
    REDIS_URL: Optional[str] = None
    
    # JWT配置
    JWT_SECRET_KEY: str = "your-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24小时
    
    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
