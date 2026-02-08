"""
配置管理 - 从环境变量读取配置
"""
import os
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

    # 回测子进程超时（秒）
    BACKTEST_TIMEOUT: int = 300

    # CORS 允许的源（逗号分隔）
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # SQL 日志（独立于 DEBUG，避免过多噪音）
    SQL_ECHO: bool = False

    # 默认管理员账户
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_EMAIL: str = "admin@example.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 使用简单缓存避免 lru_cache 在 pydantic-settings v2 中的问题
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取配置单例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
