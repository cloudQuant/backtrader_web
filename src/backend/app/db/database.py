"""
Database connection management.
"""

import logging

import sqlalchemy as sa
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Lazy engine / session-maker to avoid "Future attached to a different loop"
# when using MySQL async drivers (asyncmy / aiomysql).
_engine = None
_async_session_maker = None


def _get_engine():
    global _engine
    if _engine is None:
        # Use NullPool for MySQL async drivers to prevent connection-pool futures
        # from being reused across different asyncio Tasks, which causes
        # "Future attached to a different loop" errors.
        extra_kwargs = {}
        if settings.DATABASE_URL.startswith("mysql"):
            extra_kwargs["poolclass"] = NullPool
        else:
            extra_kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.SQL_ECHO,
            **extra_kwargs,
        )
    return _engine


def _get_session_maker():
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


class _EngineProxy:
    """Proxy that lazily resolves the real engine on first use."""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def begin(self):
        return _get_engine().begin()

    async def dispose(self):
        return await _get_engine().dispose()


class _SessionMakerProxy:
    """Proxy that lazily resolves the real session maker on first use."""

    def __call__(self, *args, **kwargs):
        return _get_session_maker()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(_get_session_maker(), name)


engine = _EngineProxy()
async_session_maker = _SessionMakerProxy()


class Base(DeclarativeBase):
    """ORM base class.

    This class serves as the declarative base for all SQLAlchemy models.
    Models inherit from this class to gain ORM functionality.
    """

    pass


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _get_column_names(bind, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def _get_index_names(bind, table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def _add_column_if_missing(bind, table_name: str, column_name: str, ddl: str) -> bool:
    if not _has_table(bind, table_name):
        return False
    if column_name in _get_column_names(bind, table_name):
        return False

    bind.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))
    logger.warning(
        "Added missing database column %s.%s during startup schema sync", table_name, column_name
    )
    return True


def _ensure_index_if_missing(bind, table_name: str, index_name: str, column_name: str) -> None:
    if not _has_table(bind, table_name):
        return
    if index_name in _get_index_names(bind, table_name):
        return

    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)
    sa.Index(index_name, table.c[column_name]).create(bind=bind)
    logger.warning("Added missing database index %s on %s(%s)", index_name, table_name, column_name)


def _modify_mysql_column_type_if_needed(
    bind,
    table_name: str,
    column_name: str,
    ddl: str,
    expected_type_fragment: str,
) -> None:
    if bind.dialect.name != "mysql" or not _has_table(bind, table_name):
        return

    columns = {column["name"]: column for column in sa.inspect(bind).get_columns(table_name)}
    column = columns.get(column_name)
    if column is None:
        return

    current_type = str(column["type"]).upper()
    if expected_type_fragment.upper() in current_type:
        return

    bind.execute(text(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {ddl}"))
    logger.warning(
        "Modified MySQL column %s.%s to %s during startup schema sync",
        table_name,
        column_name,
        ddl,
    )


def _make_column_nullable_if_needed(
    bind,
    table_name: str,
    column_name: str,
    ddl: str,
) -> None:
    if not _has_table(bind, table_name):
        return

    columns = {column["name"]: column for column in sa.inspect(bind).get_columns(table_name)}
    column = columns.get(column_name)
    if column is None or column.get("nullable", True):
        return

    dialect_name = bind.dialect.name
    if dialect_name == "mysql":
        bind.execute(text(f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {ddl}"))
    elif dialect_name == "postgresql":
        bind.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP NOT NULL"))
    elif dialect_name == "sqlite" and table_name == "chat_conversations":
        _rebuild_sqlite_chat_conversations_with_nullable_kb(bind)
    else:
        logger.warning(
            "Cannot automatically make %s.%s nullable for dialect %s",
            table_name,
            column_name,
            dialect_name,
        )
        return

    logger.warning(
        "Made database column %s.%s nullable during startup schema sync",
        table_name,
        column_name,
    )


def _rebuild_sqlite_chat_conversations_with_nullable_kb(bind) -> None:
    """Rebuild SQLite chat_conversations so knowledge_base_id can be NULL."""
    bind.execute(text("PRAGMA foreign_keys=OFF"))
    bind.execute(text("DROP TABLE IF EXISTS chat_conversations_new"))
    bind.execute(
        text(
            """
            CREATE TABLE chat_conversations_new (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                knowledge_base_id VARCHAR(36),
                user_id VARCHAR(36) NOT NULL,
                title VARCHAR(255) NOT NULL,
                model_id VARCHAR(200),
                settings JSON,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
    )
    existing_columns = _get_column_names(bind, "chat_conversations")
    copy_columns = [
        column
        for column in (
            "id",
            "knowledge_base_id",
            "user_id",
            "title",
            "model_id",
            "settings",
            "created_at",
            "updated_at",
        )
        if column in existing_columns
    ]
    if copy_columns:
        columns_sql = ", ".join(copy_columns)
        bind.execute(
            text(
                f"INSERT INTO chat_conversations_new ({columns_sql}) "
                f"SELECT {columns_sql} FROM chat_conversations"
            )
        )
    bind.execute(text("DROP TABLE chat_conversations"))
    bind.execute(text("ALTER TABLE chat_conversations_new RENAME TO chat_conversations"))
    bind.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chat_conversations_knowledge_base_id "
            "ON chat_conversations (knowledge_base_id)"
        )
    )
    bind.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chat_conversations_user_id "
            "ON chat_conversations (user_id)"
        )
    )
    bind.execute(text("PRAGMA foreign_keys=ON"))


def _ensure_workspace_schema_compatibility_sync(bind) -> None:
    dialect_name = bind.dialect.name
    false_literal = "FALSE" if dialect_name == "postgresql" else "0"

    if _has_table(bind, "workspaces"):
        _add_column_if_missing(
            bind,
            "workspaces",
            "workspace_type",
            "workspace_type VARCHAR(32) NOT NULL DEFAULT 'research'",
        )
        _add_column_if_missing(
            bind,
            "workspaces",
            "trading_config",
            "trading_config JSON",
        )
        if "workspace_type" in _get_column_names(bind, "workspaces"):
            bind.execute(
                text(
                    "UPDATE workspaces SET workspace_type = 'research' WHERE workspace_type IS NULL"
                )
            )
            _ensure_index_if_missing(
                bind,
                "workspaces",
                "ix_workspaces_workspace_type",
                "workspace_type",
            )

    if _has_table(bind, "strategy_units"):
        _add_column_if_missing(
            bind,
            "strategy_units",
            "trading_mode",
            "trading_mode VARCHAR(20) NOT NULL DEFAULT 'paper'",
        )
        _add_column_if_missing(
            bind,
            "strategy_units",
            "gateway_config",
            "gateway_config JSON",
        )
        _add_column_if_missing(
            bind,
            "strategy_units",
            "lock_trading",
            f"lock_trading BOOLEAN NOT NULL DEFAULT {false_literal}",
        )
        _add_column_if_missing(
            bind,
            "strategy_units",
            "lock_running",
            f"lock_running BOOLEAN NOT NULL DEFAULT {false_literal}",
        )
        _add_column_if_missing(
            bind,
            "strategy_units",
            "trading_instance_id",
            "trading_instance_id VARCHAR(36)",
        )
        _add_column_if_missing(
            bind,
            "strategy_units",
            "trading_snapshot",
            "trading_snapshot JSON",
        )

        unit_columns = _get_column_names(bind, "strategy_units")
        if "trading_mode" in unit_columns:
            bind.execute(
                text("UPDATE strategy_units SET trading_mode = 'paper' WHERE trading_mode IS NULL")
            )
        if "lock_trading" in unit_columns:
            bind.execute(
                text(
                    f"UPDATE strategy_units SET lock_trading = {false_literal} "
                    "WHERE lock_trading IS NULL"
                )
            )
        if "lock_running" in unit_columns:
            bind.execute(
                text(
                    f"UPDATE strategy_units SET lock_running = {false_literal} "
                    "WHERE lock_running IS NULL"
                )
            )


def _ensure_knowledge_base_schema_compatibility_sync(bind) -> None:
    """Create or patch tables used by the knowledge-base and AI chat modules."""
    from app.models.knowledge_base import (
        ChatConversation,
        ChatMessage,
        DocumentChunk,
        KBDocument,
        KnowledgeBase,
        ModelConfig,
        ModelUsageLog,
    )

    for table in (
        KnowledgeBase.__table__,
        KBDocument.__table__,
        DocumentChunk.__table__,
        ChatConversation.__table__,
        ChatMessage.__table__,
        ModelConfig.__table__,
        ModelUsageLog.__table__,
    ):
        table.create(bind=bind, checkfirst=True)

    dialect_name = bind.dialect.name
    json_type = "JSON" if dialect_name != "sqlite" else "JSON"
    datetime_type = "TIMESTAMP" if dialect_name == "postgresql" else "DATETIME"

    _add_column_if_missing(
        bind,
        "chat_conversations",
        "user_id",
        "user_id VARCHAR(36)",
    )
    _add_column_if_missing(
        bind,
        "chat_conversations",
        "model_id",
        "model_id VARCHAR(200)",
    )
    _add_column_if_missing(
        bind,
        "chat_conversations",
        "settings",
        f"settings {json_type}",
    )
    _add_column_if_missing(
        bind,
        "chat_conversations",
        "created_at",
        f"created_at {datetime_type}",
    )
    _add_column_if_missing(
        bind,
        "chat_conversations",
        "updated_at",
        f"updated_at {datetime_type}",
    )
    _make_column_nullable_if_needed(
        bind,
        "chat_conversations",
        "knowledge_base_id",
        "VARCHAR(36) NULL",
    )

    if _has_table(bind, "chat_messages"):
        _add_column_if_missing(bind, "chat_messages", "citations", f"citations {json_type}")
        _add_column_if_missing(bind, "chat_messages", "tokens_used", "tokens_used INTEGER")
        _add_column_if_missing(bind, "chat_messages", "model_id", "model_id VARCHAR(200)")
        _add_column_if_missing(bind, "chat_messages", "reasoning", "reasoning TEXT")
        _add_column_if_missing(bind, "chat_messages", "metadata", f"metadata {json_type}")
        _add_column_if_missing(bind, "chat_messages", "created_at", f"created_at {datetime_type}")

    _modify_mysql_column_type_if_needed(
        bind, "kb_documents", "content", "LONGTEXT NULL", "LONGTEXT"
    )
    _modify_mysql_column_type_if_needed(
        bind, "document_chunks", "content", "LONGTEXT NOT NULL", "LONGTEXT"
    )
    _modify_mysql_column_type_if_needed(
        bind, "chat_messages", "content", "LONGTEXT NOT NULL", "LONGTEXT"
    )
    _modify_mysql_column_type_if_needed(
        bind, "chat_messages", "reasoning", "LONGTEXT NULL", "LONGTEXT"
    )


def _ensure_airflow_schema_compatibility_sync(bind) -> None:
    """Add Airflow-related columns to ak_task_executions if missing."""
    if _has_table(bind, "ak_task_executions"):
        _add_column_if_missing(
            bind, "ak_task_executions", "airflow_dag_id", "airflow_dag_id VARCHAR(200)"
        )
        _add_column_if_missing(
            bind, "ak_task_executions", "airflow_run_id", "airflow_run_id VARCHAR(200)"
        )
        _add_column_if_missing(
            bind, "ak_task_executions", "airflow_task_id", "airflow_task_id VARCHAR(200)"
        )


def _ensure_ai_budget_schema_compatibility_sync(bind) -> None:
    if _has_table(bind, "users"):
        _add_column_if_missing(bind, "users", "ai_budget_daily_usd", "ai_budget_daily_usd FLOAT")
        _add_column_if_missing(bind, "users", "ai_budget_mode", "ai_budget_mode VARCHAR(20)")
        _add_column_if_missing(
            bind, "users", "ai_preferred_provider", "ai_preferred_provider VARCHAR(50)"
        )
        _add_column_if_missing(
            bind, "users", "ai_preferred_model", "ai_preferred_model VARCHAR(100)"
        )


def _ensure_prompt_template_schema_compatibility_sync(bind) -> None:
    from app.models.prompt_template import PromptTemplate

    PromptTemplate.__table__.create(bind=bind, checkfirst=True)
    _add_column_if_missing(
        bind,
        "prompt_templates",
        "rollout_percentage",
        "rollout_percentage INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        bind,
        "ai_call_logs",
        "prompt_template_version",
        "prompt_template_version VARCHAR(50)",
    )
    _ensure_index_if_missing(
        bind,
        "ai_call_logs",
        "ix_ai_call_logs_prompt_template_version",
        "prompt_template_version",
    )


def _ensure_broker_profiles_schema_compatibility_sync(bind) -> None:
    if _has_table(bind, "broker_connection_profiles"):
        _add_column_if_missing(
            bind,
            "broker_connection_profiles",
            "runtime_gateway_key",
            "runtime_gateway_key VARCHAR(120)",
        )
        _add_column_if_missing(
            bind,
            "broker_connection_profiles",
            "runtime_account_id",
            "runtime_account_id VARCHAR(100)",
        )
        _ensure_index_if_missing(
            bind,
            "broker_connection_profiles",
            "ix_broker_connection_profiles_runtime_gateway_key",
            "runtime_gateway_key",
        )


def _ensure_portfolio_ledger_schema_compatibility_sync(bind) -> None:
    from app.models.portfolio_ledger import (
        PortfolioLedgerImportModel,
        PortfolioLedgerModel,
        PortfolioLedgerSnapshotModel,
        PortfolioLedgerTransactionModel,
    )

    for table in (
        PortfolioLedgerModel.__table__,
        PortfolioLedgerImportModel.__table__,
        PortfolioLedgerTransactionModel.__table__,
        PortfolioLedgerSnapshotModel.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def _ensure_news_intelligence_schema_compatibility_sync(bind) -> None:
    from app.models.news_intelligence import (
        NewsAnalysisModel,
        NewsArticleModel,
        NewsSourceModel,
    )

    for table in (
        NewsSourceModel.__table__,
        NewsArticleModel.__table__,
        NewsAnalysisModel.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def _ensure_stock_analysis_schema_compatibility_sync(bind) -> None:
    from app.models.stock_analysis import (
        StockAnalysisExportModel,
        StockAnalysisReportModel,
        StockAnalysisTaskModel,
    )

    for table in (
        StockAnalysisTaskModel.__table__,
        StockAnalysisReportModel.__table__,
        StockAnalysisExportModel.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def _ensure_scanner_plan_schema_compatibility_sync(bind) -> None:
    from app.models.scanner_plan import ScannerPlanModel, ScannerPlanRunModel

    for table in (
        ScannerPlanModel.__table__,
        ScannerPlanRunModel.__table__,
    ):
        table.create(bind=bind, checkfirst=True)

    if _has_table(bind, "scanner_plans"):
        _add_column_if_missing(
            bind,
            "scanner_plans",
            "result_table_name",
            "result_table_name VARCHAR(120)",
        )
        _add_column_if_missing(
            bind,
            "scanner_plans",
            "result_table_status",
            "result_table_status VARCHAR(20) DEFAULT 'missing' NOT NULL",
        )
        _ensure_index_if_missing(
            bind,
            "scanner_plans",
            "ix_scanner_plans_result_table_name",
            "result_table_name",
        )


async def ensure_schema_compatibility() -> None:
    """Patch legacy databases with columns required by the current ORM schema."""
    async with engine.begin() as conn:
        await conn.run_sync(_ensure_workspace_schema_compatibility_sync)
        await conn.run_sync(_ensure_knowledge_base_schema_compatibility_sync)
        await conn.run_sync(_ensure_airflow_schema_compatibility_sync)
        await conn.run_sync(_ensure_ai_budget_schema_compatibility_sync)
        await conn.run_sync(_ensure_prompt_template_schema_compatibility_sync)
        await conn.run_sync(_ensure_broker_profiles_schema_compatibility_sync)
        await conn.run_sync(_ensure_portfolio_ledger_schema_compatibility_sync)
        await conn.run_sync(_ensure_news_intelligence_schema_compatibility_sync)
        await conn.run_sync(_ensure_stock_analysis_schema_compatibility_sync)
        await conn.run_sync(_ensure_scanner_plan_schema_compatibility_sync)


async def create_tables() -> None:
    """Create all ORM tables."""
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_workspace_schema_compatibility_sync)
        await conn.run_sync(_ensure_knowledge_base_schema_compatibility_sync)
        await conn.run_sync(_ensure_airflow_schema_compatibility_sync)
        await conn.run_sync(_ensure_ai_budget_schema_compatibility_sync)
        await conn.run_sync(_ensure_prompt_template_schema_compatibility_sync)
        await conn.run_sync(_ensure_broker_profiles_schema_compatibility_sync)
        await conn.run_sync(_ensure_portfolio_ledger_schema_compatibility_sync)
        await conn.run_sync(_ensure_news_intelligence_schema_compatibility_sync)
        await conn.run_sync(_ensure_stock_analysis_schema_compatibility_sync)
        await conn.run_sync(_ensure_scanner_plan_schema_compatibility_sync)


async def init_db():
    """Initialize database tables.

    This helper is retained for backward compatibility in tests and scripts.
    It no longer creates the default administrator account implicitly.
    """
    await create_tables()


async def verify_database_connection() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def ensure_database_ready() -> None:
    """Ensure schema and default bootstrap data exist."""
    if settings.DB_AUTO_CREATE_SCHEMA:
        await create_tables()
    else:
        await verify_database_connection()
        await ensure_schema_compatibility()
    if settings.DB_AUTO_CREATE_DEFAULT_ADMIN:
        await create_default_admin()


async def create_default_admin():
    """Create default admin account (if it doesn't exist)."""
    from app.models.permission import Role, user_roles
    from app.models.user import User
    from app.utils.security import get_password_hash

    settings = get_settings()

    async with async_session_maker() as session:
        # Check if admin account already exists
        result = await session.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        existing_user = result.scalar_one_or_none()

        if existing_user is None:
            # Create admin account
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
            )
            session.add(admin_user)
            await session.flush()
            existing_user = admin_user
            logger.info("Default admin account created: %s", settings.ADMIN_USERNAME)

        role_result = await session.execute(
            select(user_roles.c.role).where(user_roles.c.user_id == existing_user.id)
        )
        assigned_roles = {str(role) for role in role_result.scalars().all()}
        if Role.ADMIN.value not in assigned_roles:
            await session.execute(
                insert(user_roles).values(user_id=existing_user.id, role=Role.ADMIN.value)
            )

        await session.commit()


async def get_db() -> AsyncSession:
    """Get database session.

    Yields:
        An async database session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
