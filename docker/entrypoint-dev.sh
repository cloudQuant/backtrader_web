#!/bin/bash
set -e

echo "=== AI for Trader Backend Dev Entrypoint ==="

# Wait for database to be ready
MAX_RETRIES=30
RETRY_INTERVAL=2
RETRIES=0

echo "Waiting for database to be ready..."
while [ $RETRIES -lt $MAX_RETRIES ]; do
    if python -c "
import sys
try:
    from sqlalchemy import create_engine, text
    import os
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        print('DATABASE_URL not set, skipping DB wait')
        sys.exit(0)
    # Convert async URL to sync for connection check
    sync_url = url.replace('+asyncpg', '').replace('+aiomysql', '+pymysql')
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('Database is ready!')
    sys.exit(0)
except Exception as e:
    print(f'Database not ready: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
        break
    fi
    RETRIES=$((RETRIES + 1))
    echo "  Retry $RETRIES/$MAX_RETRIES - waiting ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

if [ $RETRIES -eq $MAX_RETRIES ]; then
    echo "ERROR: Database not ready after $((MAX_RETRIES * RETRY_INTERVAL))s" >&2
    exit 1
fi

# Auto-create database schema if enabled
if [ "${DB_AUTO_CREATE_SCHEMA:-false}" = "true" ]; then
    echo "DB_AUTO_CREATE_SCHEMA=true: Creating database schema..."
    python -c "
from app.db.database import ensure_database_ready
import asyncio
asyncio.run(ensure_database_ready())
print('Database schema created successfully.')
" || echo "WARNING: Schema creation failed, continuing anyway..."
fi

# Auto-create default admin if enabled
if [ "${DB_AUTO_CREATE_DEFAULT_ADMIN:-false}" = "true" ]; then
    echo "DB_AUTO_CREATE_DEFAULT_ADMIN=true: Creating default admin user..."
    python -c "
import asyncio, os
from app.db.database import get_async_session_context
from app.services.auth_service import AuthService

async def create_admin():
    username = os.environ.get('ADMIN_USERNAME', 'admin')
    password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    async with get_async_session_context() as session:
        service = AuthService(session)
        existing = await service.get_user_by_username(username)
        if existing:
            print(f'Admin user \"{username}\" already exists, skipping.')
        else:
            await service.register(username=username, password=password, email=email)
            print(f'Default admin user \"{username}\" created.')

asyncio.run(create_admin())
" || echo "WARNING: Admin creation failed, continuing anyway..."
fi

# Run seed data script if enabled
if [ "${SEED_DATA:-false}" = "true" ]; then
    echo "SEED_DATA=true: Checking if seed data is needed..."
    if [ -f "/opt/workspace/ai-for-trader/scripts/seed_dev_data.py" ]; then
        python /opt/workspace/ai-for-trader/scripts/seed_dev_data.py || \
            echo "WARNING: Seed data script failed, continuing anyway..."
    else
        echo "INFO: Seed script not found, skipping. (Will be available after task 5.5)"
    fi
fi

echo "=== Starting application ==="
exec "$@"
