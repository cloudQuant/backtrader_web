"""
Akshare interface CRUD service.

Encapsulates the SQLAlchemy queries and persistence for the
``ak_data_interfaces`` and ``ak_interface_categories`` tables so that the
matching API routes (:mod:`app.api.akshare.interfaces`) only handle request
parsing and response shaping.

Service-layer conventions (per AGENTS.md):

* Return ``None`` for *expected* "not found" cases; the API layer converts to
  HTTP 404.
* Raise on unexpected DB errors so the FastAPI exception handler logs them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.akshare_mgmt import DataInterface, InterfaceCategory
from app.schemas.akshare_mgmt import DataInterfaceCreate, DataInterfaceUpdate


class AkshareInterfaceService:
    """CRUD service for akshare data interfaces and their categories."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_categories(self) -> list[InterfaceCategory]:
        """Return all interface categories ordered by ``sort_order``."""
        result = await self.db.execute(
            select(InterfaceCategory).order_by(InterfaceCategory.sort_order)
        )
        return list(result.scalars().all())

    async def list_interfaces(
        self,
        *,
        category_id: int | None = None,
        search: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Return a paginated list of interfaces with optional filters.

        Args:
            category_id: Filter by category id.
            search: Case-insensitive substring matched against
                ``name``/``display_name``/``description``.
            is_active: Filter by active flag.
            page: 1-based page number.
            page_size: Items per page.

        Returns:
            Dict with keys ``items``, ``total``, ``page``, ``page_size``.
        """
        stmt = select(DataInterface).options(selectinload(DataInterface.params))
        count_stmt = select(func.count(DataInterface.id))

        if category_id is not None:
            stmt = stmt.where(DataInterface.category_id == category_id)
            count_stmt = count_stmt.where(DataInterface.category_id == category_id)

        if search:
            like_clause = (
                DataInterface.name.ilike(f"%{search}%")
                | DataInterface.display_name.ilike(f"%{search}%")
                | DataInterface.description.ilike(f"%{search}%")
            )
            stmt = stmt.where(like_clause)
            count_stmt = count_stmt.where(like_clause)

        if is_active is not None:
            stmt = stmt.where(DataInterface.is_active == is_active)
            count_stmt = count_stmt.where(DataInterface.is_active == is_active)

        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        stmt = (
            stmt.order_by(DataInterface.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        return {
            "items": list(result.scalars().all()),
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_interface(self, interface_id: int) -> DataInterface | None:
        """Return a single interface with its params eagerly loaded.

        Returns:
            The interface, or ``None`` if not found.
        """
        result = await self.db.execute(
            select(DataInterface)
            .options(selectinload(DataInterface.params))
            .where(DataInterface.id == interface_id)
        )
        return result.scalar_one_or_none()

    async def create_interface(self, payload: DataInterfaceCreate) -> DataInterface:
        """Persist a new interface and return the refreshed instance."""
        interface = DataInterface(**payload.model_dump())
        self.db.add(interface)
        await self.db.commit()
        await self.db.refresh(interface)
        return interface

    async def update_interface(
        self, interface_id: int, payload: DataInterfaceUpdate
    ) -> DataInterface | None:
        """Update an interface in place.

        Returns:
            The refreshed interface, or ``None`` if not found.
        """
        interface = await self.db.get(DataInterface, interface_id)
        if interface is None:
            return None
        for key, value in payload.model_dump(exclude_none=True).items():
            setattr(interface, key, value)
        await self.db.commit()
        await self.db.refresh(interface)
        return interface

    async def delete_interface(self, interface_id: int) -> bool:
        """Delete an interface.

        Returns:
            ``True`` if the row was deleted, ``False`` if not found.
        """
        interface = await self.db.get(DataInterface, interface_id)
        if interface is None:
            return False
        await self.db.delete(interface)
        await self.db.commit()
        return True
