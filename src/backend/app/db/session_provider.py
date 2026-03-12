"""
Session provider and unit-of-work helpers for database transactions.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker


class SessionProvider:
    """Provide request-scoped sessions and explicit transactional scopes."""

    @staticmethod
    @asynccontextmanager
    async def get_session() -> AsyncGenerator[AsyncSession, None]:
        """Yield a session managed by the provider."""
        async with async_session_maker() as session:
            try:
                yield session
            finally:
                await session.close()

    @staticmethod
    @asynccontextmanager
    async def unit_of_work(commit: bool = True) -> AsyncGenerator[AsyncSession, None]:
        """Yield a session and commit or rollback it as one transaction."""
        async with async_session_maker() as session:
            try:
                yield session
                if commit:
                    await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @staticmethod
    def create_dependency() -> Callable[[], AsyncGenerator[AsyncSession, None]]:
        """Create a FastAPI dependency that yields one request-scoped session."""

        async def dependency() -> AsyncGenerator[AsyncSession, None]:
            async with async_session_maker() as session:
                try:
                    yield session
                finally:
                    await session.close()

        return dependency


get_session = SessionProvider.get_session
unit_of_work = SessionProvider.unit_of_work
create_dependency = SessionProvider.create_dependency
SessionDependency = Callable[[], AsyncGenerator[AsyncSession, None]]
