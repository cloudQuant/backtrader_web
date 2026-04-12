"""
API routes for akshare scripts.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data_management_deps import get_current_db_user, require_data_admin_user
from app.db.database import get_db
from app.schemas.akshare_mgmt import DataScriptCreate, DataScriptUpdate, ScriptRunRequest
from app.services.akshare_script_service import AkshareScriptService

router = APIRouter()


@router.get("/scripts")
async def list_scripts(
    category: str | None = None,
    keyword: str | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    service = AkshareScriptService(db)
    items, total = await service.list_scripts(
        category=category,
        keyword=keyword,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/scripts/categories")
async def list_script_categories(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    return await AkshareScriptService(db).get_categories()


@router.get("/scripts/stats")
async def get_script_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    return await AkshareScriptService(db).get_stats()


@router.post("/scripts/scan")
async def scan_scripts(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    return await AkshareScriptService(db).scan_and_register_scripts()


@router.get("/scripts/{script_id}")
async def get_script(
    script_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_db_user),
):
    script = await AkshareScriptService(db).get_script(script_id)
    if script is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return script


@router.put("/scripts/{script_id}/toggle")
async def toggle_script(
    script_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    script = await AkshareScriptService(db).toggle_script(script_id)
    if script is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return script


@router.post("/scripts/{script_id}/run")
async def run_script(
    script_id: str,
    payload: ScriptRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    execution = await AkshareScriptService(db).run_script(
        script_id,
        parameters=payload.parameters,
        operator_id=current_user.id,
    )
    return {"execution_id": execution.execution_id, "status": execution.status.value}


@router.post("/scripts/admin/scripts", status_code=status.HTTP_201_CREATED)
async def create_script(
    payload: DataScriptCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    return await AkshareScriptService(db).create_script(payload.model_dump(), operator_id=current_user.id)


@router.put("/scripts/admin/scripts/{script_id}")
async def update_script(
    script_id: str,
    payload: DataScriptUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    script = await AkshareScriptService(db).update_script(
        script_id,
        payload.model_dump(exclude_none=True),
        operator_id=current_user.id,
    )
    if script is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return script


@router.delete("/scripts/admin/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_data_admin_user),
):
    try:
        deleted = await AkshareScriptService(db).delete_script(script_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
