#!/usr/bin/env python3
"""
Database initialization script.

Usage:
    python scripts/init_db.py --create-tables
    python scripts/init_db.py --create-admin
    python scripts/init_db.py --init-all
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.db.database import create_default_admin, create_tables
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def init_all() -> None:
    """Create tables and the default administrator account."""
    settings = get_settings()
    logger.info("Creating database tables...")
    await create_tables()
    logger.info("Database tables created successfully")
    logger.info(f"Checking for default admin account: {settings.ADMIN_USERNAME}")
    await create_default_admin()
    logger.info("Database initialization completed successfully")


def main() -> None:
    """Parse CLI arguments and run the selected action."""
    parser = argparse.ArgumentParser(
        description="Database initialization script for Backtrader Web"
    )
    parser.add_argument("--create-tables", action="store_true", help="Create database tables")
    parser.add_argument("--create-admin", action="store_true", help="Create default admin account")
    parser.add_argument(
        "--init-all", action="store_true", help="Initialize everything (tables + admin account)"
    )
    args = parser.parse_args()

    if not any([args.create_tables, args.create_admin, args.init_all]):
        parser.print_help()
        sys.exit(1)

    try:
        if args.init_all:
            asyncio.run(init_all())
        elif args.create_tables:
            asyncio.run(create_tables())
        elif args.create_admin:
            asyncio.run(create_default_admin())
    except Exception as exc:
        logger.error(f"Database initialization failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
