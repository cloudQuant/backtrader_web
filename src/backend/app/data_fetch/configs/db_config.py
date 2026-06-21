"""
Database configuration for data fetch module
"""

from sqlalchemy.engine import make_url

from app.config import get_settings

settings = get_settings()


def _build_db_config() -> dict[str, str | int]:
    configured_urls = [
        (settings.AKSHARE_DATA_DATABASE_URL or "").strip(),
        (settings.DATABASE_URL or "").strip(),
    ]
    for database_url in configured_urls:
        if not database_url:
            continue
        try:
            parsed = make_url(database_url)
        except Exception:
            continue
        if parsed.drivername.startswith("mysql"):
            return {
                "host": parsed.host or settings.SYNC_LOCAL_MYSQL_HOST,
                "user": parsed.username or settings.SYNC_LOCAL_MYSQL_USER,
                "password": parsed.password or settings.SYNC_LOCAL_MYSQL_PASSWORD,
                "database": "akshare_data",
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
