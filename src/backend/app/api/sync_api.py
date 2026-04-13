from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.data_management_deps import require_data_admin_user
from app.schemas.sync import SyncConfig, SyncRequest
from app.services.sync_service import get_sync_service

router = APIRouter()


@router.get("/sync/config")
async def get_sync_config(current_user=Depends(require_data_admin_user)):
    return get_sync_service().get_config()


@router.put("/sync/config")
async def save_sync_config(payload: SyncConfig, current_user=Depends(require_data_admin_user)):
    return get_sync_service().save_config(payload)


@router.post("/sync/test-connection")
async def test_sync_connection(payload: SyncConfig, current_user=Depends(require_data_admin_user)):
    try:
        return await get_sync_service().test_connection(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sync/databases")
async def list_sync_databases(current_user=Depends(require_data_admin_user)):
    try:
        items = await get_sync_service().list_databases(get_sync_service().get_config())
        return {"items": items}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sync/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_databases(payload: SyncRequest, current_user=Depends(require_data_admin_user)):
    try:
        return await get_sync_service().start_upload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sync/download", status_code=status.HTTP_202_ACCEPTED)
async def download_databases(payload: SyncRequest, current_user=Depends(require_data_admin_user)):
    try:
        return await get_sync_service().start_download(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/sync/status/{task_id}")
async def get_sync_status(task_id: str, current_user=Depends(require_data_admin_user)):
    task = await get_sync_service().get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sync task not found")
    return task


@router.get("/sync/history")
async def get_sync_history(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(require_data_admin_user),
):
    return {"items": await get_sync_service().get_history(limit=limit)}
