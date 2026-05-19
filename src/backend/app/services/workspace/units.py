"""Unit management operations (simple CRUD subset).

Handles delete, bulk-delete, reorder, and rename operations for strategy
units. These methods have no dependency on ``TradingWorkspaceService`` and
can be extracted cleanly.

The more complex unit operations (create, batch_create, list, get, update)
remain on :class:`app.services.workspace_service.WorkspaceService` because
they depend on ``self.trading_service`` for hydration and normalization.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.workspace import StrategyUnit
from app.schemas.workspace import GroupRenameRequest, UnitRenameRequest
from app.services import workspace_unit_runtime
from app.services.workspace._helpers import compute_rename

logger = logging.getLogger(__name__)


async def delete_unit(workspace_id: str, unit_id: str, user_id: str) -> bool:
    """Delete a single strategy unit and its runtime directory."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None:
            return False
        await session.delete(unit)
        await session.commit()
        workspace_unit_runtime.remove_unit_dir(workspace_id, unit_id)
        return True


async def bulk_delete_units(workspace_id: str, user_id: str, unit_ids: list[str]) -> int:
    """Delete multiple units in one transaction."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return 0

        result = await session.execute(
            sa_delete(StrategyUnit).where(
                StrategyUnit.workspace_id == workspace_id,
                StrategyUnit.id.in_(unit_ids),
            )
        )
        await session.commit()
        for uid in unit_ids:
            workspace_unit_runtime.remove_unit_dir(workspace_id, uid)
        return result.rowcount or 0


async def reorder_units(workspace_id: str, user_id: str, unit_ids: list[str]) -> bool:
    """Set ``sort_order`` for units based on the provided id list."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        for idx, uid in enumerate(unit_ids):
            unit = await WorkspaceService._get_unit(session, workspace_id, uid)
            if unit:
                unit.sort_order = idx
        await session.commit()
        return True


async def rename_group(workspace_id: str, user_id: str, req: GroupRenameRequest) -> bool:
    """Rename the group for a set of units."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False

        q = select(StrategyUnit).where(
            StrategyUnit.workspace_id == workspace_id,
            StrategyUnit.id.in_(req.unit_ids),
        )
        result = await session.execute(q)
        units = list(result.scalars().all())

        for unit in units:
            unit.group_name = compute_rename(
                unit, req.mode, req.value, req.search, req.replace
            )

        await session.commit()
        return True


async def rename_unit(workspace_id: str, user_id: str, req: UnitRenameRequest) -> bool:
    """Rename a single unit's strategy_name."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        unit = await WorkspaceService._get_unit(session, workspace_id, req.unit_id)
        if unit is None:
            return False
        unit.strategy_name = compute_rename(
            unit, req.mode, req.value, req.search, req.replace
        )
        await session.commit()
        return True
