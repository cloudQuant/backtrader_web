from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401 - Required for Alembic metadata discovery
from alembic import context
from app.config import get_settings
from app.db.database import Base

config = context.config
settings = get_settings()
_FALLBACK_DATABASE_URL = "sqlite+aiosqlite:///../../data/dev/backtrader.db"
if config.get_main_option("sqlalchemy.url") in {None, "", _FALLBACK_DATABASE_URL}:
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_VERSION_TABLE = "alembic_version"
_VERSION_COLUMN_LENGTH = 255


def _ensure_version_table_capacity(connection) -> None:
    """Create a version table that can store this project's long revision IDs."""
    inspector = sa.inspect(connection)
    if not inspector.has_table(_VERSION_TABLE):
        metadata = sa.MetaData()
        sa.Table(
            _VERSION_TABLE,
            metadata,
            sa.Column("version_num", sa.String(_VERSION_COLUMN_LENGTH), primary_key=True),
        ).create(bind=connection)
        return

    columns = {column["name"]: column for column in inspector.get_columns(_VERSION_TABLE)}
    version_column = columns.get("version_num")
    current_length = getattr(version_column.get("type"), "length", None) if version_column else None
    if current_length is None or current_length >= _VERSION_COLUMN_LENGTH:
        return

    if connection.dialect.name == "mysql":
        connection.execute(
            sa.text(
                f"ALTER TABLE {_VERSION_TABLE} "
                f"MODIFY COLUMN version_num VARCHAR({_VERSION_COLUMN_LENGTH}) NOT NULL"
            )
        )
    elif connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                f"ALTER TABLE {_VERSION_TABLE} "
                f"ALTER COLUMN version_num TYPE VARCHAR({_VERSION_COLUMN_LENGTH})"
            )
        )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    _ensure_version_table_capacity(connection)
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    existing_connection = config.attributes.get("connection")
    if existing_connection is not None:
        do_run_migrations(existing_connection)
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def run() -> None:
        # MySQL implicitly commits DDL, but Alembic writes the final revision
        # number afterwards. A transaction context commits that trailing update.
        async with connectable.begin() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    import asyncio

    asyncio.run(run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
