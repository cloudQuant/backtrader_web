"""
Database configuration for data fetch module
"""

from urllib.parse import urlparse

from app.config import get_settings

settings = get_settings()


def _build_db_config() -> dict[str, str | int]:
    if settings.AKSHARE_DATA_DATABASE_URL:
        parsed = urlparse(settings.AKSHARE_DATA_DATABASE_URL)
        if parsed.scheme.startswith("mysql"):
            return {
                "host": parsed.hostname or settings.SYNC_LOCAL_MYSQL_HOST,
                "user": parsed.username or settings.SYNC_LOCAL_MYSQL_USER,
                "password": parsed.password or settings.SYNC_LOCAL_MYSQL_PASSWORD,
                "database": parsed.path.lstrip("/") or "akshare_data",
                "port": parsed.port or settings.SYNC_LOCAL_MYSQL_PORT,
            }

    return {
        "host": settings.SYNC_LOCAL_MYSQL_HOST,
        "user": settings.SYNC_LOCAL_MYSQL_USER,
        "password": settings.SYNC_LOCAL_MYSQL_PASSWORD,
        "database": "akshare_data",
        "port": settings.SYNC_LOCAL_MYSQL_PORT,
    }


DB_CONFIG = _build_db_config()
