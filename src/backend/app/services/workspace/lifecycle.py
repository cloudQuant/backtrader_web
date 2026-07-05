"""Workspace CRUD operations.

Handles create, get, list, update, and delete for the ``workspaces`` table.
Extracted from :class:`app.services.workspace_service.WorkspaceService`.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.database import async_session_maker
from app.models.workspace import Workspace
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services import workspace_unit_runtime

logger = logging.getLogger(__name__)


async def create_workspace(user_id: str, data: WorkspaceCreate) -> WorkspaceResponse:
    """Create a new workspace and return its response representation."""
    from app.services.workspace_service import (
        _normalize_workspace_settings,
        _normalize_workspace_trading_config,
        _normalize_workspace_type,
        _workspace_to_response,
    )

    async with async_session_maker() as session:
        ws = Workspace(
            user_id=user_id,
            name=data.name,
            description=data.description,
            workspace_type=_normalize_workspace_type(data.workspace_type),
            settings=_normalize_workspace_settings(data.settings),
            trading_config=_normalize_workspace_trading_config(data.trading_config),
        )
        session.add(ws)
        await session.commit()
        await session.refresh(ws, attribute_names=["strategy_units"])
        workspace_unit_runtime.ensure_workspace_dir(str(ws.id))
        return _workspace_to_response(ws)


async def get_workspace(workspace_id: str, user_id: str) -> WorkspaceResponse | None:
    """Load a single workspace by id and owner."""
    from app.services.workspace_service import (
        WorkspaceService,
        _workspace_to_response,
    )

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(session, workspace_id, user_id)
        if ws is None:
            return None
        return _workspace_to_response(ws)


async def list_workspaces(
    user_id: str,
    skip: int = 0,
    limit: int = 50,
    workspace_type: str | None = None,
) -> tuple[int, list[WorkspaceResponse]]:
    """Return paginated workspaces for a user, optionally filtered by type."""
    from app.services.workspace_service import (
        _normalize_workspace_type,
        _workspace_to_response,
    )

    async with async_session_maker() as session:
        normalized_workspace_type = (
            _normalize_workspace_type(workspace_type) if workspace_type else None
        )
        count_q = select(func.count()).select_from(Workspace).where(Workspace.user_id == user_id)
        if normalized_workspace_type:
            count_q = count_q.where(Workspace.workspace_type == normalized_workspace_type)
        total = (await session.execute(count_q)).scalar() or 0

        id_q = (
            select(Workspace.id)
            .where(Workspace.user_id == user_id)
            .order_by(Workspace.updated_at.desc(), Workspace.id.desc())
            .offset(skip)
            .limit(limit)
        )
        if normalized_workspace_type:
            id_q = id_q.where(Workspace.workspace_type == normalized_workspace_type)
        id_result = await session.execute(id_q)
        workspace_ids = [str(item) for item in id_result.scalars().all()]
        if not workspace_ids:
            return total, []

        q = (
            select(Workspace)
            .where(Workspace.id.in_(workspace_ids))
            .options(selectinload(Workspace.strategy_units))
        )
        result = await session.execute(q)
        workspace_by_id = {str(ws.id): ws for ws in result.scalars().unique().all()}
        return total, [
            _workspace_to_response(workspace_by_id[workspace_id])
            for workspace_id in workspace_ids
            if workspace_id in workspace_by_id
        ]


async def update_workspace(
    workspace_id: str, user_id: str, data: WorkspaceUpdate
) -> WorkspaceResponse | None:
    """Update workspace fields with deep-merge for settings/trading_config."""
    from app.services.workspace_service import (
        WorkspaceService,
        _normalize_workspace_settings,
        _normalize_workspace_trading_config,
        _normalize_workspace_type,
        _workspace_to_response,
    )

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(session, workspace_id, user_id)
        if ws is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        ws_row: Any = ws
        for key, value in update_data.items():
            if key == "settings" and isinstance(value, dict):
                existing = _normalize_workspace_settings(cast("dict[str, Any] | None", ws.settings))
                for settings_key, settings_value in value.items():
                    if settings_key != "data_source":
                        existing[settings_key] = settings_value
                if isinstance(value.get("data_source"), dict):
                    merged_data_source = dict(existing.get("data_source") or {})
                    for source_key, source_value in value["data_source"].items():
                        if source_key in {
                            "csv",
                            "mysql",
                            "postgresql",
                            "mongodb",
                        } and isinstance(source_value, dict):
                            current_section = dict(merged_data_source.get(source_key) or {})
                            current_section.update(source_value)
                            merged_data_source[source_key] = current_section
                        else:
                            merged_data_source[source_key] = source_value
                    existing["data_source"] = merged_data_source
                ws_row.settings = existing
            elif key == "workspace_type":
                ws_row.workspace_type = _normalize_workspace_type(value)
            elif key == "trading_config" and isinstance(value, dict):
                existing = _normalize_workspace_trading_config(
                    cast("dict[str, Any] | None", ws.trading_config)
                )
                existing.update(value)
                ws_row.trading_config = existing
            else:
                setattr(ws, key, value)
        await session.commit()
        await session.refresh(ws, attribute_names=["strategy_units"])
        for unit in ws.strategy_units or []:
            workspace_unit_runtime.sync_workspace_unit_runtime(
                unit,
                cast("dict[str, Any]", ws.settings) or {},
                str(ws.workspace_type),
            )
        return _workspace_to_response(ws)


async def delete_workspace(workspace_id: str, user_id: str) -> bool:
    """Delete a workspace and its runtime directory."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return False
        await session.delete(ws)
        await session.commit()
        workspace_unit_runtime.remove_workspace_dir(workspace_id)
        return True
